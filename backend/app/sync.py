"""Fetch transactions for accounts and store them."""

import logging
import threading
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .enablebanking import EnableBankingClient, EnableBankingError
from .models import Account, Connection, SyncRun, Transaction
from .normalize import fingerprints, normalize

log = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    return dt.replace(tzinfo=timezone.utc) if dt and dt.tzinfo is None else dt


# One sync at a time: the scheduler, "Synka nu" and the bank callback may otherwise overlap
# and insert the same transactions twice.
SYNC_LOCK = threading.Lock()


def sync_account(db: Session, client: EnableBankingClient, account: Account, overlap_days: int = 10) -> SyncRun:
    with SYNC_LOCK:
        return _sync_account(db, client, account, overlap_days)


def _sync_account(db: Session, client: EnableBankingClient, account: Account, overlap_days: int) -> SyncRun:
    started = _now()
    last_booked = db.scalar(
        select(func.max(Transaction.date)).where(Transaction.account_id == account.id, Transaction.status == "BOOK")
    )
    date_from = last_booked - timedelta(days=overlap_days) if last_booked else None
    uid = account.uid
    db.commit()  # end any open transaction: never hold the database while talking to the bank

    try:
        raw = list(client.transactions(uid, date_from=date_from))
    except EnableBankingError as e:
        run = SyncRun(account_id=account.id, started_at=started, finished_at=_now(), error=str(e))
        db.add(run)
        if e.status in (401, 403):
            conn = account.connection
            if conn:
                conn.status, conn.error = "expired", str(e)
        db.commit()
        return run

    # Everything below is local and quick: one short write transaction.
    run = SyncRun(account_id=account.id, started_at=started, inserted=0, updated=0, pending=0)
    db.add(run)
    txs = [normalize(t) for t in raw]
    booked = [t for t in txs if t.status == "BOOK"]
    pending = [t for t in txs if t.status == "PDNG"]

    existing = {
        tx.fingerprint: tx
        for tx in db.scalars(
            select(Transaction).where(Transaction.account_id == account.id, Transaction.status == "BOOK")
        )
    }
    for t, fp in zip(booked, fingerprints(booked)):
        fields = {k: v for k, v in t.__dict__.items()}
        row = existing.get(fp)
        if row is None:
            row = Transaction(account_id=account.id, fingerprint=fp, **fields)
            db.add(row)
            existing[fp] = row
            run.inserted += 1
        else:
            changed = False
            for k, v in fields.items():
                if getattr(row, k) != v:
                    setattr(row, k, v)
                    changed = True
            run.updated += changed

    # Pending rows are a snapshot: replace them wholesale, so a reservation disappears once it is booked.
    db.execute(delete(Transaction).where(Transaction.account_id == account.id, Transaction.status == "PDNG"))
    for t, fp in zip(pending, fingerprints(pending)):
        db.add(Transaction(account_id=account.id, fingerprint=fp, **t.__dict__))
    run.pending = len(pending)

    account.last_synced_at = _now()
    run.finished_at = _now()
    db.commit()
    return run


def sync_all(db: Session, client: EnableBankingClient, overlap_days: int = 10) -> list[SyncRun]:
    runs = []
    accounts = db.scalars(select(Account).where(Account.active.is_(True))).all()
    for account in accounts:
        conn = account.connection
        if conn is None or conn.status != "active":
            continue
        if conn.valid_until and _aware(conn.valid_until) < _now():
            conn.status = "expired"
            db.commit()
            continue
        try:
            runs.append(sync_account(db, client, account, overlap_days))
        except Exception:
            log.exception("sync failed for account %s", account.id)
            db.rollback()
    return runs


def store_session(db: Session, client: EnableBankingClient, conn: Connection, session: dict) -> list[Account]:
    """Save the accounts of a freshly authorised session, reusing existing rows for known accounts."""
    conn.session_id = session["session_id"]
    valid_until = (session.get("access") or {}).get("valid_until")
    if valid_until:
        conn.valid_until = datetime.fromisoformat(valid_until.replace("Z", "+00:00"))
    conn.status = "active"
    conn.error = None

    accounts = []
    for acc in session.get("accounts") or []:
        if isinstance(acc, str):  # some API versions return only uids
            acc = {"uid": acc, **client.account_details(acc)}
        ident = acc.get("account_id") or {}
        identifier = ident.get("iban") or (ident.get("other") or {}).get("identification")
        id_hash = acc.get("identification_hash") or f"{conn.aspsp_name}|{identifier or acc['uid']}"
        row = db.scalar(select(Account).where(Account.identification_hash == id_hash))
        if row is None:
            row = Account(identification_hash=id_hash, uid=acc["uid"], aspsp_name=conn.aspsp_name)
            db.add(row)
        row.uid = acc["uid"]
        row.connection = conn
        # "name" is the account holder's name; "details"/"product" describe the account itself
        row.name = acc.get("details") or acc.get("product") or acc.get("name") or row.name
        row.identifier = identifier or row.identifier
        row.currency = acc.get("currency") or row.currency
        row.active = True
        accounts.append(row)
    db.commit()
    return accounts

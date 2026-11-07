import secrets
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from typing import Annotated, Literal

from pydantic import BaseModel, StringConstraints
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from .errors import ConfigError
from .enablebanking import EnableBankingClient, EnableBankingError
from .categorize import categorize_uncategorized, set_category
from .models import Account, Category, Connection, SyncRun, Transaction
from .sync import store_session, sync_account, sync_all

router = APIRouter()


def get_db(request: Request):
    yield from request.app.state.db.session()


def get_client(request: Request) -> EnableBankingClient:
    try:
        client = request.app.state.client_factory()
    except ConfigError as e:
        raise HTTPException(503, str(e))
    if client is None:
        raise HTTPException(503, "Enable Banking är inte konfigurerat: sätt EB_APP_ID i .env")
    return client


def get_settings(request: Request):
    return request.app.state.settings


class ConnectRequest(BaseModel):
    aspsp: str
    country: str | None = None


class TransactionUpdate(BaseModel):
    category_id: int | None


PALETTE = ("blue", "sky", "teal", "green", "lime", "amber", "orange", "red", "pink", "purple", "slate", "brown", "gray")
Kind = Literal["expense", "income", "transfer", "reimbursement"]
Color = Literal[PALETTE]  # type: ignore[valid-type]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Icon = Annotated[str, StringConstraints(pattern=r"^[a-z0-9-]{1,50}$")]


class CategoryCreate(BaseModel):
    name: Name
    parent_id: int | None = None
    kind: Kind = "expense"  # top level only; subcategories copy their parent's
    color: Color | None = None  # top level only; subcategories inherit
    icon: Icon | None = None


class CategoryUpdate(BaseModel):
    name: Name | None = None
    kind: Kind | None = None
    color: Color | None = None
    icon: Icon | None = None


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).isoformat()


@router.get("/api/aspsps")
def list_aspsps(country: str | None = None, client=Depends(get_client), settings=Depends(get_settings)):
    try:
        banks = client.aspsps(country or settings.eb_country)
    except EnableBankingError as e:
        raise HTTPException(502, str(e))
    return [
        {"name": b["name"], "country": b.get("country"), "logo": b.get("logo"),
         "maximum_consent_validity": b.get("maximum_consent_validity")}
        for b in banks
    ]


@router.post("/api/connections")
def start_connection(body: ConnectRequest, db: Session = Depends(get_db), client=Depends(get_client),
                     settings=Depends(get_settings)):
    country = body.country or settings.eb_country
    days = settings.eb_consent_days
    try:
        bank = next((b for b in client.aspsps(country) if b["name"] == body.aspsp), None)
        max_s = (bank or {}).get("maximum_consent_validity")
        if max_s:
            days = min(days, int(max_s) // 86400)
        state = secrets.token_urlsafe(24)
        valid_until = datetime.now(timezone.utc) + timedelta(days=days)
        auth = client.start_auth(body.aspsp, country, valid_until, state, settings.eb_redirect_url)
    except EnableBankingError as e:
        raise HTTPException(502, str(e))
    db.add(Connection(aspsp_name=body.aspsp, aspsp_country=country, state=state, valid_until=valid_until))
    db.commit()
    return {"url": auth["url"]}


@router.get("/callback")
def auth_callback(state: str, code: str | None = None, error: str | None = None,
                  error_description: str | None = None, db: Session = Depends(get_db),
                  client=Depends(get_client), settings=Depends(get_settings)):
    conn = db.scalar(select(Connection).where(Connection.state == state))
    if conn is None:
        raise HTTPException(400, "Unknown state")
    if error or not code:
        conn.status, conn.error = "error", error_description or error or "no code"
        db.commit()
        return RedirectResponse("/accounts?error=1", status_code=303)
    try:
        session = client.create_session(code)
        accounts = store_session(db, client, conn, session)
    except EnableBankingError as e:
        conn.status, conn.error = "error", str(e)
        db.commit()
        return RedirectResponse("/accounts?error=1", status_code=303)
    for account in accounts:
        sync_account(db, client, account, settings.sync_overlap_days)
    return RedirectResponse("/accounts?connected=1", status_code=303)


@router.get("/api/connections")
def list_connections(db: Session = Depends(get_db)):
    rows = db.scalars(select(Connection).where(Connection.status != "pending").order_by(Connection.created_at.desc()))
    return [
        {"id": c.id, "aspsp": c.aspsp_name, "status": c.status, "valid_until": _iso(c.valid_until),
         "error": c.error, "created_at": _iso(c.created_at)}
        for c in rows
    ]


@router.get("/api/accounts")
def list_accounts(db: Session = Depends(get_db)):
    counts = dict(db.execute(select(Transaction.account_id, func.count()).group_by(Transaction.account_id)).all())
    out = []
    for a in db.scalars(select(Account).order_by(Account.aspsp_name, Account.name)):
        last_run = db.scalar(select(SyncRun).where(SyncRun.account_id == a.id).order_by(SyncRun.id.desc()).limit(1))
        c = a.connection
        out.append({
            "id": a.id, "aspsp": a.aspsp_name, "name": a.name, "identifier": a.identifier,
            "currency": a.currency, "active": a.active, "last_synced_at": _iso(a.last_synced_at),
            "transaction_count": counts.get(a.id, 0),
            "connection_status": c.status if c else None,
            "valid_until": _iso(c.valid_until) if c else None,
            "last_error": last_run.error if last_run else None,
        })
    return out


@router.get("/api/transactions")
def list_transactions(account: int | None = None, from_: date | None = Query(None, alias="from"),
                      to: date | None = None, q: str | None = None, category: str | None = None,
                      limit: int = 100, offset: int = 0, db: Session = Depends(get_db)):
    stmt = select(Transaction, Account).join(Account)
    if account:
        stmt = stmt.where(Transaction.account_id == account)
    if from_:
        stmt = stmt.where(Transaction.date >= from_)
    if to:
        stmt = stmt.where(Transaction.date <= to)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Transaction.description.ilike(like), Transaction.creditor_name.ilike(like),
                              Transaction.debtor_name.ilike(like)))
    if category == "none":
        stmt = stmt.where(Transaction.category_id.is_(None))
    elif category:
        try:
            cid = int(category)
        except ValueError:
            raise HTTPException(422, "category must be an id or 'none'")
        children = select(Category.id).where(Category.parent_id == cid)
        stmt = stmt.where(or_(Transaction.category_id == cid, Transaction.category_id.in_(children)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    limit = max(1, min(limit, 500))
    rows = db.execute(
        stmt.order_by(Transaction.date.desc().nulls_first(), Transaction.id.desc()).limit(limit).offset(offset)
    ).all()
    return {
        "total": total,
        "items": [_transaction(t, a) for t, a in rows],
    }


def _transaction(t: Transaction, a: Account) -> dict:
    return {"id": t.id, "date": t.date.isoformat() if t.date else None, "status": t.status,
            "description": t.description, "amount_ore": t.amount_ore, "currency": t.currency,
            "account_id": a.id, "account": a.name or a.aspsp_name, "aspsp": a.aspsp_name, "mcc": t.mcc,
            "category_id": t.category_id, "category_source": t.category_source}


@router.patch("/api/transactions/{tx_id}")
def update_transaction(tx_id: int, body: TransactionUpdate, db: Session = Depends(get_db)):
    t = db.get(Transaction, tx_id)
    if t is None:
        raise HTTPException(404, "Transaktionen finns inte")
    if body.category_id is not None and db.get(Category, body.category_id) is None:
        raise HTTPException(422, "Kategorin finns inte")
    similar = set_category(db, t, body.category_id)
    db.commit()
    return {**_transaction(t, t.account), "similar_updated": similar}


def _category(c: Category, count: int = 0) -> dict:
    return {"id": c.id, "parent_id": c.parent_id, "key": c.key, "name": c.name, "kind": c.kind, "color": c.color,
            "icon": c.icon, "sort_order": c.sort_order, "transaction_count": count}


@router.get("/api/categories")
def list_categories(db: Session = Depends(get_db)):
    counts = dict(db.execute(select(Transaction.category_id, func.count()).group_by(Transaction.category_id)).all())
    rows = db.scalars(select(Category).order_by(Category.parent_id.nulls_first(), Category.sort_order, Category.id))
    return [_category(c, counts.get(c.id, 0)) for c in rows]


@router.post("/api/categories", status_code=201)
def create_category(body: CategoryCreate, db: Session = Depends(get_db)):
    if body.parent_id is not None:
        parent = db.get(Category, body.parent_id)
        if parent is None or parent.parent_id is not None:
            raise HTTPException(422, "Underkategorier kan bara ligga under en huvudkategori")
        kind, color = parent.kind, None
    else:
        kind, color = body.kind, body.color or "gray"
    last = db.scalar(select(func.max(Category.sort_order)).where(
        Category.parent_id.is_(None) if body.parent_id is None else Category.parent_id == body.parent_id))
    c = Category(name=body.name, parent_id=body.parent_id, kind=kind, color=color, icon=body.icon or "tag",
                 sort_order=(last if last is not None else -1) + 1)
    db.add(c)
    db.commit()
    return _category(c)


@router.patch("/api/categories/{category_id}")
def update_category(category_id: int, body: CategoryUpdate, db: Session = Depends(get_db)):
    c = db.get(Category, category_id)
    if c is None:
        raise HTTPException(404, "Kategorin finns inte")
    fields = body.model_fields_set
    if c.parent_id is not None and ({"kind", "color"} & fields):
        raise HTTPException(422, "Typ och färg ärvs från huvudkategorin")
    if "name" in fields and body.name:
        c.name = body.name
    if "icon" in fields and body.icon:
        c.icon = body.icon
    if "color" in fields and body.color:
        c.color = body.color
    if "kind" in fields and body.kind:
        c.kind = body.kind
        db.execute(update(Category).where(Category.parent_id == c.id).values(kind=body.kind))
    db.commit()
    count = db.scalar(select(func.count()).where(Transaction.category_id == c.id))
    return _category(c, count)


@router.delete("/api/categories/{category_id}")
def delete_category(category_id: int, db: Session = Depends(get_db)):
    """Delete a category (and its subcategories). Its transactions become uncategorised, then get
    whatever the automatic categorisation suggests now; a manual choice is gone with the category."""
    c = db.get(Category, category_id)
    if c is None:
        raise HTTPException(404, "Kategorin finns inte")
    ids = [c.id, *db.scalars(select(Category.id).where(Category.parent_id == c.id))]
    affected = db.execute(update(Transaction).where(Transaction.category_id.in_(ids))
                          .values(category_id=None, category_source=None)).rowcount
    db.delete(c)
    db.flush()
    categorize_uncategorized(db)
    db.commit()
    return {"deleted": len(ids), "transactions": affected}


@router.post("/api/sync")
def trigger_sync(db: Session = Depends(get_db), client=Depends(get_client), settings=Depends(get_settings)):
    runs = sync_all(db, client, settings.sync_overlap_days)
    return [
        {"account_id": r.account_id, "inserted": r.inserted, "updated": r.updated, "pending": r.pending,
         "error": r.error}
        for r in runs
    ]

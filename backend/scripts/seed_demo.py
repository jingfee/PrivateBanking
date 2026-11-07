"""Fill a database with made-up accounts and transactions for local development.

    uv run python -m scripts.seed_demo ./data/dev.db
"""

import random
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select

from app.db import Database
from app.main import migrate
from app.models import Account, Connection, Transaction
from app.normalize import fingerprints, normalize

MERCHANTS = [
    ("ICA NARA HEMMA", 60, 450), ("COOP KONSUM", 80, 900), ("WILLYS", 150, 1200), ("SL ACCESS", 42, 42),
    ("SPOTIFY", 129, 129), ("SYSTEMBOLAGET", 120, 500), ("MAX BURGERS", 90, 260), ("CIRCLE K", 300, 900),
    ("APOTEK HJARTAT", 50, 300), ("CLAS OHLSON", 80, 700), ("NETFLIX", 149, 149), ("ESPRESSO HOUSE", 45, 120),
]


def tx(day: date, amount: float, indicator: str, name: str, status: str = "BOOK", ref: str | None = None) -> dict:
    party = "creditor" if indicator == "DBIT" else "debtor"
    return {
        "transaction_amount": {"currency": "SEK", "amount": f"{amount:.2f}"},
        "credit_debit_indicator": indicator,
        "status": status,
        "booking_date": None if status == "PDNG" else day.isoformat(),
        "transaction_date": day.isoformat(),
        "entry_reference": ref,
        party: {"name": name},
    }


def main(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = Database(path)
    migrate(db, path)
    rnd = random.Random(1)
    today = date.today()
    with db.sessionmaker() as s:
        if s.scalar(select(Account).limit(1)):
            print("database already has accounts, nothing to do")
            return
        now = datetime.now(timezone.utc)
        skandia = Connection(aspsp_name="Skandia", aspsp_country="SE", state="demo-1", status="active",
                             session_id="demo", valid_until=now + timedelta(days=170))
        coop = Connection(aspsp_name="Entercard", aspsp_country="SE", state="demo-2", status="active",
                          session_id="demo", valid_until=now + timedelta(days=9))
        allkonto = Account(uid="demo-1", identification_hash="demo-1", aspsp_name="Skandia", name="Allkonto",
                           identifier="9150 •••• 4821", currency="SEK", connection=skandia, last_synced_at=now)
        card = Account(uid="demo-2", identification_hash="demo-2", aspsp_name="Entercard", name="Coop Mastercard",
                       identifier="•••• 1234", currency="SEK", connection=coop, last_synced_at=now)
        s.add_all([skandia, coop, allkonto, card])
        s.flush()

        raw: dict[Account, list[dict]] = {allkonto: [], card: []}
        for d in range(120):
            day = today - timedelta(days=d)
            for _ in range(rnd.randint(0, 3)):
                name, lo, hi = rnd.choice(MERCHANTS)
                raw[card].append(tx(day, rnd.uniform(lo, hi), "DBIT", name, "PDNG" if d < 2 else "BOOK"))
            if day.day == 25:
                raw[allkonto].append(tx(day, 34500, "CRDT", "ARBETSGIVARE AB", ref=f"lon-{day}"))
                raw[allkonto].append(tx(day, 274, "DBIT", "Preliminär skatt", ref=f"skatt-{day}"))
            if day.day == 28:
                raw[allkonto].append(tx(day, 8900, "DBIT", "Hyra", ref=f"hyra-{day}"))
                raw[allkonto].append(tx(day, 6200, "DBIT", "Coop Mastercard faktura", ref=f"kort-{day}"))
        for account, items in raw.items():
            txs = [normalize(t) for t in items]
            for t, fp in zip(txs, fingerprints(txs)):
                s.add(Transaction(account_id=account.id, fingerprint=fp, **t.__dict__))
        s.commit()
        print(f"seeded {sum(len(v) for v in raw.values())} transactions into {path}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "./data/dev.db")

"""Turn a raw Enable Banking transaction into the fields we store."""

import hashlib
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP


@dataclass
class NormalizedTransaction:
    external_id: str | None
    status: str
    date: date | None
    booking_date: date | None
    transaction_date: date | None
    value_date: date | None
    amount_ore: int
    currency: str
    description: str
    creditor_name: str | None
    debtor_name: str | None
    mcc: str | None
    raw: dict


def _date(value) -> date | None:
    if not value:
        return None
    return date.fromisoformat(str(value)[:10])


def _name(party) -> str | None:
    if isinstance(party, dict):
        name = (party.get("name") or "").strip()
        return name or None
    return None


def _text(value) -> str:
    if isinstance(value, list):
        return " ".join(str(v).strip() for v in value if v and str(v).strip())
    return (value or "").strip() if isinstance(value, str) else ""


def amount_to_ore(amount: str, indicator: str | None) -> int:
    ore = int((Decimal(str(amount)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    indicator = (indicator or "").upper()
    if indicator == "DBIT":
        return -abs(ore)
    if indicator == "CRDT":
        return abs(ore)
    return ore  # no indicator: trust the sign the bank sent


def describe(tx: dict) -> str:
    is_debit = (tx.get("credit_debit_indicator") or "").upper() == "DBIT"
    counterparty = _name(tx.get("creditor")) if is_debit else _name(tx.get("debtor"))
    btc = tx.get("bank_transaction_code") or {}
    candidates = [
        counterparty,
        _text(tx.get("remittance_information")),
        _text(tx.get("note")),
        _text(btc.get("description") if isinstance(btc, dict) else None),
        # last resort: the other party, whichever side it is on
        _name(tx.get("creditor")) or _name(tx.get("debtor")),
    ]
    return next((c for c in candidates if c), "")


def normalize(tx: dict) -> NormalizedTransaction:
    amount = tx.get("transaction_amount") or {}
    booking = _date(tx.get("booking_date"))
    txdate = _date(tx.get("transaction_date"))
    value = _date(tx.get("value_date"))
    status = (tx.get("status") or ("BOOK" if booking else "PDNG")).upper()
    return NormalizedTransaction(
        external_id=tx.get("transaction_id") or tx.get("entry_reference") or None,
        status="PDNG" if status == "PDNG" else "BOOK",
        date=booking or txdate or value,
        booking_date=booking,
        transaction_date=txdate,
        value_date=value,
        amount_ore=amount_to_ore(amount.get("amount", "0"), tx.get("credit_debit_indicator")),
        currency=amount.get("currency") or "SEK",
        description=describe(tx),
        creditor_name=_name(tx.get("creditor")),
        debtor_name=_name(tx.get("debtor")),
        mcc=tx.get("merchant_category_code") or None,
        raw=tx,
    )


def fingerprints(txs: list[NormalizedTransaction]) -> list[str]:
    """Stable per-account identity for each transaction in a batch.

    Uses the bank's id when there is one; otherwise date+amount+description plus an
    ordinal so that two identical purchases on the same day stay distinct.
    Pending rows get their own namespace since they are replaced on every sync.
    """
    seen: dict[str, int] = {}
    out = []
    for t in txs:
        if t.external_id and t.status == "BOOK":
            key = f"id|{t.external_id}"
        else:
            base = f"{t.status}|{t.date}|{t.amount_ore}|{t.currency}|{t.description.lower()}"
            n = seen.get(base, 0)
            seen[base] = n + 1
            key = f"{base}|{n}"
        out.append(hashlib.sha256(key.encode()).hexdigest())
    return out

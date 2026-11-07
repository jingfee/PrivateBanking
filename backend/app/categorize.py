"""Automatic categorisation.

Order of precedence for a transaction's category:
1. manual  – set by the user on that transaction; never touched automatically
2. learned – the user categorised another transaction with the same counterparty and direction
3. auto    – a built-in keyword or the card's merchant category code (MCC) suggests one
Anything else stays uncategorised.
"""

import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Category, CategoryRule, Transaction

# Built-in keywords, matched as whole words against the counterparty. First match wins, so more
# specific entries come first. Direction: "out" (money out), "in" (money in) or None (both).
KEYWORDS: list[tuple[str, str | None, str]] = [
    # Paying a credit card bill must never count as spending (the purchases already do), so these
    # come before shop names: "Coop Mastercard faktura" is a card bill, not groceries.
    ("mastercard", "out", "overforingar.kreditkort"),
    ("kreditkort", "out", "overforingar.kreditkort"),
    ("kortfaktura", "out", "overforingar.kreditkort"),
    ("entercard", "out", "overforingar.kreditkort"),
    ("eurocard", "out", "overforingar.kreditkort"),
    ("american express", "out", "overforingar.kreditkort"),
    ("uber eats", "out", "mat.snabbmat"),
    ("foodora", "out", "mat.snabbmat"),
    ("wolt", "out", "mat.snabbmat"),
    ("max burgers", "out", "mat.snabbmat"),
    ("mcdonalds", "out", "mat.snabbmat"),
    ("burger king", "out", "mat.snabbmat"),
    ("systembolaget", "out", "mat.alkohol"),
    ("ica", "out", "mat.livsmedel"),
    ("coop", "out", "mat.livsmedel"),
    ("willys", "out", "mat.livsmedel"),
    ("hemköp", "out", "mat.livsmedel"),
    ("lidl", "out", "mat.livsmedel"),
    ("city gross", "out", "mat.livsmedel"),
    ("mathem", "out", "mat.livsmedel"),
    ("espresso house", "out", "mat.restaurang"),
    ("starbucks", "out", "mat.restaurang"),
    ("sl", "out", "transport.kollektivtrafik"),
    ("västtrafik", "out", "transport.kollektivtrafik"),
    ("skånetrafiken", "out", "transport.kollektivtrafik"),
    ("sj", "out", "resor.flyg"),
    ("uber", "out", "transport.taxi"),
    ("bolt", "out", "transport.taxi"),
    ("taxi", "out", "transport.taxi"),
    ("sunfleet", "out", "transport.bilpool"),
    ("greenmobility", "out", "transport.bilpool"),
    ("voi", "out", "transport.cykel"),
    ("spotify", "out", "noje.streaming"),
    ("netflix", "out", "noje.streaming"),
    ("viaplay", "out", "noje.streaming"),
    ("disney plus", "out", "noje.streaming"),
    ("hbo", "out", "noje.streaming"),
    ("youtube", "out", "noje.streaming"),
    ("steam", "out", "noje.spel"),
    ("playstation", "out", "noje.spel"),
    ("nintendo", "out", "noje.spel"),
    ("filmstaden", "out", "noje.evenemang"),
    ("ticketmaster", "out", "noje.evenemang"),
    ("tickster", "out", "noje.evenemang"),
    ("storytel", "out", "noje.bocker"),
    ("bokus", "out", "noje.bocker"),
    ("adlibris", "out", "noje.bocker"),
    ("akademibokhandeln", "out", "noje.bocker"),
    ("apotek", "out", "halsa.apotek"),
    ("apoteket", "out", "halsa.apotek"),
    ("sats", "out", "halsa.traning"),
    ("friskis", "out", "halsa.traning"),
    ("nordic wellness", "out", "halsa.traning"),
    ("ikea", "out", "boende.inredning"),
    ("clas ohlson", "out", "shopping.hem"),
    ("jula", "out", "shopping.hem"),
    ("bauhaus", "out", "shopping.hem"),
    ("elgiganten", "out", "shopping.elektronik"),
    ("netonnet", "out", "shopping.elektronik"),
    ("webhallen", "out", "shopping.elektronik"),
    ("verisure", "out", "boende.larm"),
    ("sector alarm", "out", "boende.larm"),
    ("vattenfall", "out", "boende.el"),
    ("ellevio", "out", "boende.el"),
    ("tibber", "out", "boende.el"),
    ("telia", "out", "boende.internet"),
    ("tele2", "out", "boende.internet"),
    ("telenor", "out", "boende.internet"),
    ("bahnhof", "out", "boende.internet"),
    ("airbnb", "out", "resor.boende"),
    ("booking com", "out", "resor.boende"),
    ("sas", "out", "resor.flyg"),
    ("norwegian", "out", "resor.flyg"),
    ("skatteverket", "out", "ekonomi.skatt"),
    ("preliminär skatt", "out", "ekonomi.skatt"),
    ("bankomat", "out", "ovrigt.kontantuttag"),
    ("uttag", "out", "ovrigt.kontantuttag"),
    ("swish", "out", "ovrigt.swish"),
    ("försäkringskassan", "in", "inkomster.ersattningar"),
    ("ränta", "in", "inkomster.ranta"),
    ("swish", "in", "inkomster.ovrigt"),
]

_MCC_RANGES: list[tuple[int, int, str]] = [
    (3000, 3350, "resor.flyg"),  # airlines
    (3351, 3500, "transport.bilpool"),  # car rental companies
    (3501, 3999, "resor.boende"),  # hotels
]

MCC: dict[str, str] = {
    **dict.fromkeys(["5411", "5422", "5441", "5451", "5462", "5499"], "mat.livsmedel"),
    **dict.fromkeys(["5812", "5813"], "mat.restaurang"),
    "5814": "mat.snabbmat",
    "5921": "mat.alkohol",
    **dict.fromkeys(["4111", "4131"], "transport.kollektivtrafik"),
    "4112": "resor.flyg",
    "4121": "transport.taxi",
    **dict.fromkeys(["7512", "5541", "5542"], "transport.bilpool"),
    "4511": "resor.flyg",
    "7011": "resor.boende",
    "4722": "resor.ovrigt",
    "5912": "halsa.apotek",
    **dict.fromkeys(["8011", "8021", "8031", "8041", "8042", "8043", "8049", "8050", "8062", "8071", "8099"],
                    "halsa.vard"),
    "7997": "halsa.traning",
    **dict.fromkeys(["7230", "7298"], "halsa.skonhet"),
    **dict.fromkeys(["5611", "5621", "5631", "5641", "5651", "5655", "5661", "5691", "5699"], "shopping.klader"),
    **dict.fromkeys(["5045", "5732", "5734", "5946", "4812"], "shopping.elektronik"),
    **dict.fromkeys(["5200", "5211", "5231", "5251", "5261", "5719"], "shopping.hem"),
    "5712": "boende.inredning",
    **dict.fromkeys(["5310", "5311", "5331", "5399"], "shopping.ovrigt"),
    **dict.fromkeys(["4899", "5815"], "noje.streaming"),
    **dict.fromkeys(["5816", "7994"], "noje.spel"),
    **dict.fromkeys(["7832", "7922", "7929", "7991", "7996"], "noje.evenemang"),
    **dict.fromkeys(["5941", "5945"], "noje.hobby"),
    **dict.fromkeys(["5942", "5994"], "noje.bocker"),
    **dict.fromkeys(["5995", "0742"], "boende.husdjur"),
    **dict.fromkeys(["5992", "5947"], "gavor.presenter"),
    "8398": "gavor.valgorenhet",
    "6011": "ovrigt.kontantuttag",
    "4900": "boende.el",
    **dict.fromkeys(["4814", "4816"], "boende.internet"),
    "6300": "ekonomi.forsakringar",
    "9311": "ekonomi.skatt",
    **dict.fromkeys(["7210", "7211", "7349"], "boende.stad"),
}


def _words(text: str) -> str:
    """'ICA NÄRA HEMMA 1234, Sthlm' -> 'ica nära hemma sthlm' (letters only, single spaces)."""
    text = unicodedata.normalize("NFC", text).lower()
    return " ".join(re.sub(r"[^\w]|[\d_]", " ", text).split())


def counterparty(t: Transaction) -> str:
    """The name of whoever is on the other side, falling back to the description."""
    name = t.creditor_name if t.amount_ore < 0 else t.debtor_name
    return _words(name or t.description or "")


def rule_key(t: Transaction) -> str | None:
    """Transactions with the same key are 'similar': same counterparty, same direction."""
    who = counterparty(t)
    if not who:
        return None
    return f"{'in' if t.amount_ore > 0 else 'out'}:{who}"


def builtin_guess(t: Transaction) -> str | None:
    """Category key suggested by built-in keywords or the MCC, if any."""
    direction = "in" if t.amount_ore > 0 else "out"
    text = f" {_words(' '.join(filter(None, [t.creditor_name, t.debtor_name, t.description])))} "
    for word, want, key in KEYWORDS:
        if want in (None, direction) and f" {word} " in text:
            return key
    if t.mcc and direction == "out":
        if t.mcc in MCC:
            return MCC[t.mcc]
        if t.mcc.isdigit():
            code = int(t.mcc)
            for lo, hi, key in _MCC_RANGES:
                if lo <= code <= hi:
                    return key
    return None


class Categorizer:
    """Loads rules and category keys once, then categorises any number of transactions."""

    def __init__(self, db: Session):
        self.rules = dict(db.execute(select(CategoryRule.key, CategoryRule.category_id)).all())
        self.by_key = dict(db.execute(select(Category.key, Category.id).where(Category.key.is_not(None))).all())

    def apply(self, t: Transaction) -> bool:
        """Set an automatic category on t unless the user chose one. Returns True if it changed."""
        if t.category_source == "manual":
            return False
        key = rule_key(t)
        if key in self.rules:
            new = (self.rules[key], "learned")
        else:
            guess = builtin_guess(t)
            cid = self.by_key.get(guess) if guess else None
            new = (cid, "auto") if cid else (None, None)
        if (t.category_id, t.category_source) == new:
            return False
        t.category_id, t.category_source = new
        return True


def categorize_uncategorized(db: Session, account_id: int | None = None) -> int:
    """Give a category to transactions nobody has categorised yet. Does not commit."""
    stmt = select(Transaction).where(Transaction.category_source.is_(None))
    if account_id is not None:
        stmt = stmt.where(Transaction.account_id == account_id)
    c = Categorizer(db)
    return sum(c.apply(t) for t in db.scalars(stmt))


def set_category(db: Session, t: Transaction, category_id: int | None) -> int:
    """The user picked a category for t. Remember it for similar transactions and recategorise
    those that the user has not set themselves. Returns how many other transactions changed.
    Does not commit."""
    t.category_id, t.category_source = category_id, "manual"
    key = rule_key(t)
    if key is None:
        return 0
    rule = db.scalar(select(CategoryRule).where(CategoryRule.key == key))
    if category_id is None:
        if rule:
            db.delete(rule)
    elif rule:
        rule.category_id = category_id
    else:
        db.add(CategoryRule(key=key, category_id=category_id))
    db.flush()

    c = Categorizer(db)
    changed = 0
    others = select(Transaction).where(Transaction.id != t.id,
                                       Transaction.category_source.is_distinct_from("manual"))
    for other in db.scalars(others):
        if rule_key(other) == key:
            changed += c.apply(other)
    return changed

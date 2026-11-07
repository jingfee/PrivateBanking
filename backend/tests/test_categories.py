import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import Settings
from app.db import Base, Database
from app.enablebanking import EnableBankingClient
from app.main import create_app
from app.models import Account, Category, Connection, Transaction
from app.sync import sync_account

from .conftest import API, tx


@pytest.fixture
def app_client(private_key, tmp_path):
    settings = Settings(database_path=tmp_path / "t.db", scheduler_enabled=False,
                        frontend_dir=tmp_path / "nofrontend")
    app = create_app(settings, lambda: EnableBankingClient("app", private_key, API,
                                                           http=httpx.Client(base_url=API)))
    with TestClient(app) as c:
        c.db = app.state.db
        yield c


def add_transactions(db, *amounts_and_names):
    with db.sessionmaker() as s:
        conn = Connection(aspsp_name="Skandia", aspsp_country="SE", state="s", status="active")
        acc = Account(uid="u", identification_hash="h", aspsp_name="Skandia", name="Allkonto", connection=conn)
        s.add_all([conn, acc])
        s.flush()
        for i, (ore, name) in enumerate(amounts_and_names):
            s.add(Transaction(account_id=acc.id, fingerprint=str(i), status="BOOK", amount_ore=ore, currency="SEK",
                              description=name, raw={}))
        s.commit()


def test_default_categories_are_seeded_by_migration(app_client):
    cats = app_client.get("/api/categories").json()
    top = [c for c in cats if c["parent_id"] is None]
    assert top[0]["name"] == "Boende & hushåll" and top[0]["color"] == "blue"
    by_key = {c["key"]: c for c in cats}
    assert by_key["boende.larm"]["parent_id"] == by_key["boende"]["id"]
    assert by_key["delat.partner"]["kind"] == "reimbursement"
    assert by_key["overforingar.kreditkort"]["kind"] == "transfer"
    assert by_key["inkomster.lon"]["kind"] == "income"
    assert all(c["icon"] for c in cats)


def test_set_and_clear_category_and_filter(app_client):
    add_transactions(app_client.db, (-4500, "ICA"), (-12900, "SPOTIFY"), (-300, "OKÄND"))
    cats = {c["key"]: c["id"] for c in app_client.get("/api/categories").json()}
    items = app_client.get("/api/transactions").json()["items"]
    ica = next(i for i in items if i["description"] == "ICA")
    spotify = next(i for i in items if i["description"] == "SPOTIFY")

    r = app_client.patch(f"/api/transactions/{ica['id']}", json={"category_id": cats["mat.livsmedel"]})
    assert r.status_code == 200
    assert r.json()["category_id"] == cats["mat.livsmedel"] and r.json()["category_source"] == "manual"
    app_client.patch(f"/api/transactions/{spotify['id']}", json={"category_id": cats["noje.streaming"]})

    def descs(**params):
        return {i["description"] for i in app_client.get("/api/transactions", params=params).json()["items"]}

    assert descs(category=cats["mat.livsmedel"]) == {"ICA"}
    assert descs(category=cats["mat"]) == {"ICA"}  # parent includes its subcategories
    assert descs(category="none") == {"OKÄND"}

    r = app_client.patch(f"/api/transactions/{ica['id']}", json={"category_id": None})
    assert r.json()["category_id"] is None and r.json()["category_source"] == "manual"
    assert descs(category="none") == {"OKÄND", "ICA"}


def test_set_category_rejects_unknown_ids(app_client):
    add_transactions(app_client.db, (-100, "X"))
    tx_id = app_client.get("/api/transactions").json()["items"][0]["id"]
    assert app_client.patch(f"/api/transactions/{tx_id}", json={"category_id": 99999}).status_code == 422
    assert app_client.patch("/api/transactions/99999", json={"category_id": None}).status_code == 404
    assert app_client.get("/api/transactions", params={"category": "x"}).status_code == 422


@respx.mock
def test_category_on_pending_survives_resync(private_key):
    d = Database(":memory:")
    Base.metadata.create_all(d.engine)
    client = EnableBankingClient("app-id", private_key, API, http=httpx.Client(base_url=API))
    with d.sessionmaker() as db:
        conn = Connection(aspsp_name="Skandia", aspsp_country="SE", state="s", status="active", session_id="x")
        acc = Account(uid="uid-1", identification_hash="h1", aspsp_name="Skandia", connection=conn)
        cat = Category(name="Livsmedel")
        db.add_all([conn, acc, cat])
        db.commit()
        pending = {"transactions": [tx("31.73", status="PDNG", transaction_date="2026-11-04",
                                       creditor={"name": "ICA"})]}
        respx.get(f"{API}/accounts/uid-1/transactions").side_effect = [
            httpx.Response(200, json=pending), httpx.Response(200, json=pending)]
        sync_account(db, client, acc)
        row = db.scalar(select(Transaction))
        row.category_id, row.category_source = cat.id, "manual"
        db.commit()
        sync_account(db, client, acc)
        row = db.scalar(select(Transaction))
        assert (row.status, row.category_id, row.category_source) == ("PDNG", cat.id, "manual")


# --- automatic categorisation ------------------------------------------------------------------

from app.categorize import builtin_guess, categorize_uncategorized, rule_key, set_category  # noqa: E402


_fp = iter(range(10**6))


def T(ore, creditor=None, debtor=None, description="", mcc=None, source=None, category_id=None, status="BOOK"):
    return Transaction(account_id=1, fingerprint=f"t{next(_fp)}", status=status, amount_ore=ore, currency="SEK",
                       description=description or creditor or debtor or "", creditor_name=creditor,
                       debtor_name=debtor, mcc=mcc, raw={}, category_source=source, category_id=category_id)


def test_rule_key_ignores_numbers_and_punctuation_and_keeps_direction():
    assert rule_key(T(-100, creditor="ICA NÄRA HEMMA 1234, Sthlm")) == "out:ica nära hemma sthlm"
    assert rule_key(T(-100, creditor="ICA Nära Hemma 5678")) == "out:ica nära hemma"
    assert rule_key(T(500, debtor="Anna Svensson")) == "in:anna svensson"
    assert rule_key(T(-500, creditor="Anna Svensson")) == "out:anna svensson"
    assert rule_key(T(-1, description="")) is None


def test_builtin_guess_keywords_then_mcc():
    assert builtin_guess(T(-100, creditor="ICA NARA HEMMA")) == "mat.livsmedel"
    assert builtin_guess(T(-620000, creditor="Coop Mastercard faktura")) == "overforingar.kreditkort"
    assert builtin_guess(T(-100, creditor="UBER EATS")) == "mat.snabbmat"  # before plain "uber"
    assert builtin_guess(T(-100, creditor="UBER *TRIP")) == "transport.taxi"
    assert builtin_guess(T(-100, creditor="MUSICA AB")) is None  # "ica" only as a whole word
    assert builtin_guess(T(-100, creditor="OKÄND BUTIK", mcc="5912")) == "halsa.apotek"
    assert builtin_guess(T(-100, creditor="SOME AIRLINE", mcc="3005")) == "resor.flyg"
    assert builtin_guess(T(100, debtor="OKÄND", mcc="5912")) is None  # refunds are not guessed from MCC
    assert builtin_guess(T(100, debtor="FÖRSÄKRINGSKASSAN")) == "inkomster.ersattningar"
    assert builtin_guess(T(-100, creditor="OKÄND")) is None


@pytest.fixture
def mem():
    d = Database(":memory:")
    Base.metadata.create_all(d.engine)
    with d.sessionmaker() as s:
        mat = Category(key="mat", name="Mat & dryck")
        s.add(mat)
        s.flush()
        s.add_all([Category(key="mat.livsmedel", name="Livsmedel", parent_id=mat.id),
                   Category(key="mat.restaurang", name="Restaurang", parent_id=mat.id),
                   Category(key="delat.partner", name="Ersättning från partner")])
        conn = Connection(aspsp_name="B", aspsp_country="SE", state="s", status="active")
        s.add_all([conn, Account(id=1, uid="u", identification_hash="h", aspsp_name="B", connection=conn)])
        s.commit()
        s.ids = dict(s.execute(select(Category.key, Category.id)).all())
        yield s


def test_learning_beats_builtin_and_updates_older_but_not_manual(mem):
    ids = mem.ids
    ica1, ica2, ica3 = T(-100, creditor="ICA NARA HEMMA 1"), T(-200, creditor="ICA NARA HEMMA 2"), \
        T(-300, creditor="ICA NARA HEMMA 3")
    manual = T(-400, creditor="ICA NARA HEMMA 4", source="manual", category_id=ids["mat.livsmedel"])
    other = T(-500, creditor="ICA MAXI")
    mem.add_all([ica1, ica2, ica3, manual, other])
    mem.flush()
    categorize_uncategorized(mem)
    assert (ica2.category_id, ica2.category_source) == (ids["mat.livsmedel"], "auto")

    # The user says this ICA is really a café: the other two follow, the manual one does not
    assert set_category(mem, ica1, ids["mat.restaurang"]) == 2
    assert (ica1.category_id, ica1.category_source) == (ids["mat.restaurang"], "manual")
    assert (ica2.category_id, ica2.category_source) == (ids["mat.restaurang"], "learned")
    assert (ica3.category_id, ica3.category_source) == (ids["mat.restaurang"], "learned")
    assert (manual.category_id, manual.category_source) == (ids["mat.livsmedel"], "manual")
    assert other.category_source == "auto"  # different counterparty

    # New transactions from the same place are learned too
    new = T(-50, creditor="ICA NARA HEMMA 9")
    mem.add(new)
    mem.flush()
    categorize_uncategorized(mem)
    assert (new.category_id, new.category_source) == (ids["mat.restaurang"], "learned")

    # Removing the category forgets the rule: the others fall back to the built-in guess
    set_category(mem, ica1, None)
    assert (ica1.category_id, ica1.category_source) == (None, "manual")
    assert (ica2.category_id, ica2.category_source) == (ids["mat.livsmedel"], "auto")


def test_learning_respects_direction(mem):
    ids = mem.ids
    from_partner, to_partner = T(1100000, debtor="Anna Svensson"), T(-20000, creditor="Anna Svensson")
    later = T(1050000, debtor="ANNA SVENSSON")
    mem.add_all([from_partner, to_partner, later])
    mem.flush()
    set_category(mem, from_partner, ids["delat.partner"])
    assert later.category_id == ids["delat.partner"]
    assert to_partner.category_id is None


@respx.mock
def test_sync_categorises_new_transactions(mem, private_key):
    client = EnableBankingClient("app-id", private_key, API, http=httpx.Client(base_url=API))
    respx.get(f"{API}/accounts/u/transactions").respond(200, json={"transactions": [
        tx("45", creditor={"name": "WILLYS HEMMA"}, entry_reference="a"),
        tx("31", status="PDNG", transaction_date="2026-11-04", creditor={"name": "OKÄND"},
           merchant_category_code="5411")]})
    acc = mem.get(Account, 1)
    acc.connection.session_id = "x"
    sync_account(mem, client, acc)
    got = {t.description: (t.category_id, t.category_source) for t in mem.scalars(select(Transaction))}
    assert got == {"WILLYS HEMMA": (mem.ids["mat.livsmedel"], "auto"),
                   "OKÄND": (mem.ids["mat.livsmedel"], "auto")}


def test_api_reports_how_many_similar_were_updated(app_client):
    add_transactions(app_client.db, (-4500, "ICA"), (-12900, "ICA"), (-300, "OKÄND"))
    cats = {c["key"]: c["id"] for c in app_client.get("/api/categories").json()}
    items = app_client.get("/api/transactions").json()["items"]
    first = next(i for i in items if i["description"] == "ICA")
    r = app_client.patch(f"/api/transactions/{first['id']}", json={"category_id": cats["mat.restaurang"]}).json()
    assert r["similar_updated"] == 1
    sources = {i["id"]: i["category_source"] for i in app_client.get("/api/transactions").json()["items"]}
    assert sorted(s or "" for s in sources.values()) == ["", "learned", "manual"]

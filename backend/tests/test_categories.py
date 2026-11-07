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
    assert r.json()["category_id"] is None and r.json()["category_source"] is None
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

from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.config import Settings
from app.enablebanking import EnableBankingClient
from app.main import create_app

from .conftest import API, tx


@pytest.fixture
def app_client(private_key, tmp_path):
    settings = Settings(database_path=tmp_path / "t.db", scheduler_enabled=False,
                        frontend_dir=tmp_path / "nofrontend", eb_redirect_url="https://pb.test/callback")
    app = create_app(settings, lambda: EnableBankingClient("app", private_key, API,
                                                           http=httpx.Client(base_url=API)))
    with TestClient(app) as c:
        yield c


@respx.mock
def test_connect_callback_and_list(app_client):
    respx.get(f"{API}/aspsps").respond(200, json={"aspsps": [
        {"name": "Skandia", "country": "SE", "maximum_consent_validity": 90 * 86400}]})
    auth = respx.post(f"{API}/auth").respond(200, json={"url": "https://bank.test/login"})
    respx.post(f"{API}/sessions").respond(200, json={
        "session_id": "s1", "access": {"valid_until": "2027-02-01T00:00:00+00:00"},
        "accounts": [{"uid": "u1", "identification_hash": "h1", "name": "Allkonto", "currency": "SEK"}]})
    respx.get(f"{API}/accounts/u1/transactions").respond(200, json={"transactions": [
        tx("274", booking_date="2024-12-31", remittance_information=["Preliminär skatt"], entry_reference="1"),
        tx("31.730", status="PDNG", transaction_date="2026-11-04", creditor={"name": "ICA"}),
    ]})

    r = app_client.post("/api/connections", json={"aspsp": "Skandia"})
    assert r.status_code == 200 and r.json()["url"] == "https://bank.test/login"
    import json
    body = json.loads(auth.calls[0].request.content)
    assert body["redirect_url"] == "https://pb.test/callback"
    state = body["state"]

    assert app_client.get("/callback", params={"state": "wrong", "code": "c"}).status_code == 400
    r = app_client.get("/callback", params={"state": state, "code": "c"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/accounts?connected=1"

    accounts = app_client.get("/api/accounts").json()
    assert accounts[0]["name"] == "Allkonto" and accounts[0]["transaction_count"] == 2
    assert app_client.get("/api/connections").json()[0]["status"] == "active"

    items = app_client.get("/api/transactions").json()["items"]
    assert [(i["status"], i["amount_ore"], i["description"]) for i in items] == [
        ("PDNG", -3173, "ICA"), ("BOOK", -27400, "Preliminär skatt")]
    assert app_client.get("/api/transactions", params={"q": "skatt"}).json()["total"] == 1
    assert app_client.get("/api/transactions", params={"from": "2025-01-01"}).json()["total"] == 1


def test_callback_error_from_bank(app_client):
    r = app_client.get("/callback", params={"state": "nope", "error": "access_denied"})
    assert r.status_code == 400


def test_unconfigured_returns_503(tmp_path):
    settings = Settings(database_path=tmp_path / "t.db", scheduler_enabled=False, eb_app_id="",
                        frontend_dir=tmp_path / "x")
    with TestClient(create_app(settings)) as c:
        assert c.get("/api/health").json()["enable_banking_configured"] is False
        assert c.get("/api/aspsps").status_code == 503


def test_unreadable_key_gives_clear_message(tmp_path):
    key = tmp_path / "eb.pem"
    key.write_text("x")
    key.chmod(0)
    settings = Settings(database_path=tmp_path / "t.db", scheduler_enabled=False, eb_app_id="app",
                        eb_key_path=key, frontend_dir=tmp_path / "x")
    import os
    if os.geteuid() == 0:  # root can read anything; simulate with a missing file instead
        key.unlink()
    with TestClient(create_app(settings)) as c:
        r = c.get("/api/aspsps")
        assert r.status_code == 503
        assert "eb.pem" in r.json()["detail"]
        assert c.get("/api/health").json()["problem"]


def test_bad_key_and_network_errors_are_502(tmp_path, private_key):
    def make(key):
        settings = Settings(database_path=tmp_path / "t.db", scheduler_enabled=False,
                            frontend_dir=tmp_path / "x")
        return create_app(settings, lambda: EnableBankingClient("app", key, API, http=httpx.Client(base_url=API)))

    with TestClient(make("not a pem")) as c:
        r = c.get("/api/aspsps")
        assert r.status_code == 502 and "pem" in r.json()["detail"]

    with respx.mock:
        respx.get(f"{API}/aspsps").mock(side_effect=httpx.ConnectError("Name or service not known"))
        with TestClient(make(private_key)) as c:
            r = c.get("/api/aspsps")
            assert r.status_code == 502 and "Kunde inte nå" in r.json()["detail"]

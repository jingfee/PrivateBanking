import httpx
import pytest
import respx
from sqlalchemy import select

from app.db import Base, Database
from app.enablebanking import EnableBankingClient
from app.models import Account, Connection, Transaction
from app.sync import store_session, sync_account, sync_all

from .conftest import API, tx


@pytest.fixture
def db():
    d = Database(":memory:")
    Base.metadata.create_all(d.engine)
    with d.sessionmaker() as s:
        yield s


@pytest.fixture
def client(private_key):
    return EnableBankingClient("app-id", private_key, API, http=httpx.Client(base_url=API))


@pytest.fixture
def account(db):
    conn = Connection(aspsp_name="Skandia", aspsp_country="SE", state="s", status="active", session_id="sess")
    acc = Account(uid="uid-1", identification_hash="h1", aspsp_name="Skandia", connection=conn)
    db.add_all([conn, acc])
    db.commit()
    return acc


def mock_tx(router, pages):
    route = router.get(f"{API}/accounts/uid-1/transactions")
    route.side_effect = [httpx.Response(200, json=p) for p in pages]
    return route


def rows(db):
    return db.scalars(select(Transaction).order_by(Transaction.id)).all()


@respx.mock
def test_pagination_and_first_sync_uses_longest(db, client, account):
    route = mock_tx(respx, [
        {"transactions": [tx("10", entry_reference="a")], "continuation_key": "k2"},
        {"transactions": [tx("20", entry_reference="b")]},
    ])
    run = sync_account(db, client, account)
    assert run.inserted == 2 and run.error is None
    assert route.calls[0].request.url.params["strategy"] == "longest"
    assert route.calls[1].request.url.params["continuation_key"] == "k2"
    assert route.calls[1].request.url.params["strategy"] == "longest"
    assert route.calls[0].request.headers["authorization"].startswith("Bearer ")


@respx.mock
def test_resync_does_not_duplicate_and_uses_date_from(db, client, account):
    page = {"transactions": [tx("10", entry_reference="a"), tx("5", creditor={"name": "KAFFE"}),
                             tx("5", creditor={"name": "KAFFE"})]}
    route = mock_tx(respx, [page, page])
    sync_account(db, client, account)
    run = sync_account(db, client, account, overlap_days=10)
    assert run.inserted == 0
    assert len(rows(db)) == 3
    assert route.calls[1].request.url.params["date_from"] == "2026-10-22"


@respx.mock
def test_pending_replaced_when_booked(db, client, account):
    mock_tx(respx, [
        {"transactions": [tx("31.73", status="PDNG", transaction_date="2026-11-04", creditor={"name": "ICA"})]},
        {"transactions": [tx("31.73", booking_date="2026-11-05", creditor={"name": "ICA"}, entry_reference="z")]},
    ])
    sync_account(db, client, account)
    assert [(r.status, r.amount_ore) for r in rows(db)] == [("PDNG", -3173)]
    sync_account(db, client, account)
    assert [(r.status, r.amount_ore) for r in rows(db)] == [("BOOK", -3173)]


@respx.mock
def test_booked_update_in_place(db, client, account):
    mock_tx(respx, [
        {"transactions": [tx("10", entry_reference="a", creditor={"name": "OLD"})]},
        {"transactions": [tx("10", entry_reference="a", creditor={"name": "NEW"})]},
    ])
    sync_account(db, client, account)
    run = sync_account(db, client, account)
    assert run.updated == 1
    assert [r.description for r in rows(db)] == ["NEW"]


@respx.mock
def test_expired_consent_marks_connection(db, client, account):
    respx.get(f"{API}/accounts/uid-1/transactions").respond(401, json={"message": "expired"})
    runs = sync_all(db, client)
    assert runs[0].error
    assert account.connection.status == "expired"


@respx.mock
def test_store_session_reuses_account_by_identification_hash(db, client, account):
    conn = Connection(aspsp_name="Skandia", aspsp_country="SE", state="s2")
    db.add(conn)
    db.commit()
    store_session(db, client, conn, {
        "session_id": "sess-2", "access": {"valid_until": "2027-05-01T00:00:00Z"},
        "accounts": [{"uid": "uid-NEW", "identification_hash": "h1", "name": "Allkonto", "currency": "SEK"},
                     {"uid": "uid-2", "identification_hash": "h2", "currency": "SEK"}],
    })
    accs = db.scalars(select(Account).order_by(Account.id)).all()
    assert [(a.identification_hash, a.uid) for a in accs] == [("h1", "uid-NEW"), ("h2", "uid-2")]
    assert conn.status == "active" and conn.valid_until.year == 2027


def test_store_session_prefers_account_description_over_holder_name(db, client):
    conn = Connection(aspsp_name="Skandia", aspsp_country="SE", state="s3")
    db.add(conn)
    db.commit()
    store_session(db, client, conn, {
        "session_id": "sess-3",
        "accounts": [{"uid": "a", "identification_hash": "ha", "name": "Kim Svensson", "details": "Sparkonto",
                      "product": "Skandiakonto"},
                     {"uid": "b", "identification_hash": "hb", "name": "Kim Svensson", "product": "Allkonto"},
                     {"uid": "c", "identification_hash": "hc", "name": "Kim Svensson"}],
    })
    accs = db.scalars(select(Account).order_by(Account.id)).all()
    assert [a.name for a in accs] == ["Sparkonto", "Allkonto", "Kim Svensson"]


@respx.mock
def test_database_is_writable_while_fetching_from_bank(tmp_path, client):
    """The bank call can be slow; other requests must still be able to write meanwhile."""
    import sqlite3

    path = tmp_path / "t.db"
    d = Database(str(path))
    Base.metadata.create_all(d.engine)
    with d.sessionmaker() as s:
        conn = Connection(aspsp_name="Skandia", aspsp_country="SE", state="s", status="active")
        acc = Account(uid="uid-1", identification_hash="h1", aspsp_name="Skandia", connection=conn)
        s.add_all([conn, acc])
        s.commit()

        def bank_responds(request):
            other = sqlite3.connect(path, timeout=0)
            other.execute("INSERT INTO connections (aspsp_name, aspsp_country, state, status, created_at) "
                          "VALUES ('X', 'SE', 'other', 'pending', '2026-01-01')")
            other.commit()
            other.close()
            return httpx.Response(200, json={"transactions": [tx("10", entry_reference="a")]})

        respx.get(f"{API}/accounts/uid-1/transactions").mock(side_effect=bank_responds)
        run = sync_account(s, client, acc)
        assert run.error is None and run.inserted == 1

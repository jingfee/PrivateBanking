from datetime import date

from app.normalize import amount_to_ore, fingerprints, normalize

from .conftest import tx


def test_skandia_tax_debit_is_negative():
    n = normalize(tx("274", booking_date="2024-12-31", remittance_information=["Preliminär skatt"]))
    assert n.amount_ore == -27400
    assert n.description == "Preliminär skatt"
    assert n.date == date(2024, 12, 31)
    assert n.status == "BOOK"


def test_coop_description_from_creditor_and_three_decimals():
    n = normalize(tx("31.730", creditor={"name": "ICA NARA HEMMA"}))
    assert n.amount_ore == -3173
    assert n.description == "ICA NARA HEMMA"


def test_pending_without_booking_date_uses_transaction_date():
    n = normalize(tx("100", status="PDNG", transaction_date="2026-11-04"))
    assert n.status == "PDNG"
    assert n.booking_date is None
    assert n.date == date(2026, 11, 4)


def test_credit_uses_debtor_name():
    n = normalize(tx("25000", indicator="CRDT", debtor={"name": "ARBETSGIVARE AB"},
                     creditor={"name": "Mig Själv"}))
    assert n.amount_ore == 2500000
    assert n.description == "ARBETSGIVARE AB"


def test_description_fallbacks():
    assert normalize(tx("1", note="En notering")).description == "En notering"
    assert normalize(tx("1", bank_transaction_code={"description": "Kortköp"})).description == "Kortköp"
    assert normalize(tx("1")).description == ""


def test_amount_without_indicator_keeps_sign():
    assert amount_to_ore("-12.5", None) == -1250
    assert amount_to_ore("12.5", "") == 1250


def test_fingerprints_distinguish_identical_purchases_same_day():
    a = normalize(tx("50", creditor={"name": "KAFFE"}))
    b = normalize(tx("50", creditor={"name": "KAFFE"}))
    fa, fb = fingerprints([a, b])
    assert fa != fb
    assert fingerprints([a, b]) == [fa, fb]  # deterministic


def test_fingerprint_prefers_bank_id():
    a = normalize(tx("50", entry_reference="X1", creditor={"name": "A"}))
    b = normalize(tx("99", entry_reference="X1", creditor={"name": "B"}))
    assert fingerprints([a]) == fingerprints([b])

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

API = "https://eb.test"


@pytest.fixture(scope="session")
def private_key() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption()).decode()


def tx(amount, indicator="DBIT", status="BOOK", booking_date="2026-11-01", **extra):
    t = {
        "transaction_amount": {"currency": "SEK", "amount": amount},
        "credit_debit_indicator": indicator,
        "status": status,
        "booking_date": booking_date if status == "BOOK" else None,
        "remittance_information": [""],
    }
    t.update(extra)
    return t

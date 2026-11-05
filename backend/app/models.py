from datetime import date, datetime, timezone

from sqlalchemy import JSON, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Connection(Base):
    """One consent (Enable Banking session) for one bank."""

    __tablename__ = "connections"

    id: Mapped[int] = mapped_column(primary_key=True)
    aspsp_name: Mapped[str] = mapped_column(String(200))
    aspsp_country: Mapped[str] = mapped_column(String(2))
    state: Mapped[str] = mapped_column(String(64), unique=True)  # auth state, verified on callback
    session_id: Mapped[str | None] = mapped_column(String(100))
    valid_until: Mapped[datetime | None]
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|active|expired|error
    error: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    accounts: Mapped[list["Account"]] = relationship(back_populates="connection")


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    connection_id: Mapped[int | None] = mapped_column(ForeignKey("connections.id"))
    uid: Mapped[str] = mapped_column(String(100))  # EB uid, changes with each new session
    identification_hash: Mapped[str] = mapped_column(String(200), unique=True)  # stable across sessions
    aspsp_name: Mapped[str] = mapped_column(String(200))
    name: Mapped[str | None]
    identifier: Mapped[str | None]  # masked IBAN / account number / PAN
    currency: Mapped[str | None] = mapped_column(String(3))
    active: Mapped[bool] = mapped_column(default=True)
    last_synced_at: Mapped[datetime | None]

    connection: Mapped[Connection | None] = relationship(back_populates="accounts")


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("account_id", "fingerprint", name="uq_tx_account_fingerprint"),
        Index("ix_tx_account_date", "account_id", "date"),
        Index("ix_tx_date", "date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    external_id: Mapped[str | None] = mapped_column(String(200))
    fingerprint: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(4))  # BOOK | PDNG
    date: Mapped[date | None]
    booking_date: Mapped[date | None]
    transaction_date: Mapped[date | None]
    value_date: Mapped[date | None]
    amount_ore: Mapped[int]  # signed, negative = money out
    currency: Mapped[str] = mapped_column(String(3))
    description: Mapped[str] = mapped_column(default="")
    creditor_name: Mapped[str | None]
    debtor_name: Mapped[str | None]
    mcc: Mapped[str | None] = mapped_column(String(4))
    raw: Mapped[dict] = mapped_column(JSON)
    category_id: Mapped[int | None]
    first_seen: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"))
    started_at: Mapped[datetime] = mapped_column(default=utcnow)
    finished_at: Mapped[datetime | None]
    inserted: Mapped[int] = mapped_column(default=0)
    updated: Mapped[int] = mapped_column(default=0)
    pending: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None]

"""Model database (SQLModel).

Aturan uang: semua nominal disimpan sebagai integer rupiah (tanpa desimal).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

from bot.timeutil import utcnow

TYPE_INCOME = "income"
TYPE_EXPENSE = "expense"
VALID_TYPES = (TYPE_INCOME, TYPE_EXPENSE)


def type_label(kind: str) -> str:
    return "Masuk" if kind == TYPE_INCOME else "Keluar"


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    telegram_id: int = Field(unique=True, index=True)
    name: str = Field(default="")
    timezone: str = Field(default="Asia/Jakarta")
    currency: str = Field(default="IDR")
    recap_hour: int = Field(default=21)  # 0 = rekap harian dimatikan
    last_recap_date: str = Field(default="")  # 'YYYY-MM-DD' lokal, anti dobel kirim
    created_at: datetime = Field(default_factory=utcnow)


class Account(SQLModel, table=True):
    __tablename__ = "accounts"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    name: str = Field(default="Dompet")
    kind: str = Field(default="cash")  # cash | bank | ewallet
    opening_balance: int = Field(default=0)
    created_at: datetime = Field(default_factory=utcnow)


class Category(SQLModel, table=True):
    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("user_id", "kind", "name", name="uq_category_user_kind_name"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    name: str
    kind: str = Field(default=TYPE_EXPENSE)  # income | expense
    emoji: str = Field(default="")
    keywords: str = Field(default="")  # dipisah koma
    is_default: bool = Field(default=False)
    created_at: datetime = Field(default_factory=utcnow)


class Transaction(SQLModel, table=True):
    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("user_id", "message_id", name="uq_tx_user_message"),
    )

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    account_id: int = Field(foreign_key="accounts.id", index=True)
    category_id: int = Field(foreign_key="categories.id", index=True)
    kind: str = Field(default=TYPE_EXPENSE, index=True)  # income | expense
    amount: int = Field(default=0)  # integer rupiah, selalu positif
    note: str = Field(default="")
    occurred_at: datetime = Field(index=True)  # naive UTC
    message_id: int | None = Field(default=None)
    created_at: datetime = Field(default_factory=utcnow)


class Budget(SQLModel, table=True):
    __tablename__ = "budgets"
    __table_args__ = (UniqueConstraint("user_id", "category_id", name="uq_budget_user_category"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    category_id: int = Field(foreign_key="categories.id", index=True)
    amount: int = Field(default=0)  # batas per bulan
    created_at: datetime = Field(default_factory=utcnow)


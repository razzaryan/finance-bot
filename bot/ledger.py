"""Query & operasi database untuk transaksi, laporan, dan anggaran.

Semua fungsi menerima Session supaya gampang dites dengan SQLite in-memory.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy import func as sa_func
from sqlmodel import Session, select

from bot.models import (
    TYPE_EXPENSE,
    TYPE_INCOME,
    Account,
    Budget,
    Category,
    Transaction,
    User,
)
from bot.timeutil import (
    day_bounds,
    format_datetime_local,
    local_naive_to_utc,
    local_now,
    month_bounds,
)


class LedgerError(ValueError):
    """Kesalahan yang pesannya aman ditampilkan ke pengguna."""


# ---------------------------------------------------------------- pencarian objek


def get_user(session: Session, telegram_id: int) -> User | None:
    return session.exec(select(User).where(User.telegram_id == telegram_id)).first()


def get_default_account(session: Session, user_id: int) -> Account:
    account = session.exec(
        select(Account).where(Account.user_id == user_id).order_by(Account.id)
    ).first()
    if account is None:
        raise LedgerError("Akun belum dibuat. Jalankan /start dulu.")
    return account


def list_accounts(session: Session, user_id: int) -> list[Account]:
    return list(
        session.exec(
            select(Account).where(Account.user_id == user_id).order_by(Account.id)
        ).all()
    )


def find_account(session: Session, user_id: int, name: str) -> Account | None:
    target = (name or "").strip().lower()
    if not target:
        return None
    for account in list_accounts(session, user_id):
        if account.name.lower() == target:
            return account
    return None


def list_categories(session: Session, user_id: int, kind: str | None = None) -> list[Category]:
    stmt = select(Category).where(Category.user_id == user_id)
    if kind:
        stmt = stmt.where(Category.kind == kind)
    stmt = stmt.order_by(Category.kind, Category.name)
    return list(session.exec(stmt).all())


def find_category(session: Session, user_id: int, name: str, kind: str | None = None) -> Category | None:
    target = (name or "").strip().lower()
    if not target:
        return None
    for category in list_categories(session, user_id, kind):
        if category.name.lower() == target:
            return category
    return None


def fallback_category(session: Session, user: User, kind: str) -> Category:
    """Kategori 'Lainnya/Lain-lain' sebagai tempat terakhir."""
    wanted = "Lainnya" if kind == TYPE_INCOME else "Lain-lain"
    existing = find_category(session, user.id, wanted, kind)
    if existing:
        return existing

    category = Category(
        user_id=user.id,
        name=wanted,
        kind=kind,
        emoji="➕" if kind == TYPE_INCOME else "📦",
        keywords="",
        is_default=True,
    )
    session.add(category)
    session.commit()
    session.refresh(category)
    return category


# ---------------------------------------------------------------- transaksi


@dataclass
class AddResult:
    transaction: Transaction
    created: bool
    duplicate: bool = False


def add_transaction(
    session: Session,
    user: User,
    *,
    kind: str,
    amount: int,
    category: Category,
    account: Account,
    note: str = "",
    occurred_at: datetime,
    message_id: int | None = None,
) -> AddResult:
    """Simpan transaksi. Idempoten terhadap message_id yang sama."""
    if amount <= 0:
        raise LedgerError("Nominal harus lebih dari 0.")
    if kind not in (TYPE_INCOME, TYPE_EXPENSE):
        raise LedgerError("Jenis transaksi tidak dikenal.")

    if message_id is not None:
        existing = session.exec(
            select(Transaction).where(
                Transaction.user_id == user.id,
                Transaction.message_id == message_id,
            )
        ).first()
        if existing is not None:
            return AddResult(transaction=existing, created=False, duplicate=True)

    trx = Transaction(
        user_id=user.id,
        account_id=account.id,
        category_id=category.id,
        kind=kind,
        amount=int(amount),
        note=(note or "").strip()[:500],
        occurred_at=occurred_at,
        message_id=message_id,
    )
    session.add(trx)
    session.commit()
    session.refresh(trx)
    return AddResult(transaction=trx, created=True)


def get_transaction(session: Session, user_id: int, trx_id: int) -> Transaction | None:
    return session.exec(
        select(Transaction).where(
            Transaction.user_id == user_id, Transaction.id == trx_id
        )
    ).first()


def delete_transaction(session: Session, user_id: int, trx_id: int) -> Transaction:
    trx = get_transaction(session, user_id, trx_id)
    if trx is None:
        raise LedgerError(f"Transaksi #{trx_id} tidak ditemukan.")
    session.delete(trx)
    session.commit()
    return trx


def last_transaction(session: Session, user_id: int) -> Transaction | None:
    return session.exec(
        select(Transaction)
        .where(Transaction.user_id == user_id)
        .order_by(Transaction.id.desc())
        .limit(1)
    ).first()


def transaction_with_category(
    session: Session, user_id: int, trx_id: int
) -> tuple[Transaction, Category | None]:
    trx = get_transaction(session, user_id, trx_id)
    if trx is None:
        raise LedgerError(f"Transaksi #{trx_id} tidak ditemukan.")
    category = session.get(Category, trx.category_id)
    return trx, category


def transactions_in_range(
    session: Session,
    user_id: int,
    start: datetime,
    end: datetime,
    *,
    limit: int | None = None,
) -> list[tuple[Transaction, Category | None]]:
    stmt = (
        select(Transaction, Category)
        .join(Category, Category.id == Transaction.category_id, isouter=True)
        .where(
            Transaction.user_id == user_id,
            Transaction.occurred_at >= start,
            Transaction.occurred_at < end,
        )
        .order_by(Transaction.occurred_at, Transaction.id)
    )
    if limit:
        stmt = stmt.limit(limit)
    return [(row[0], row[1]) for row in session.exec(stmt).all()]


def recent_transactions(
    session: Session, user_id: int, limit: int = 10
) -> list[tuple[Transaction, Category | None]]:
    stmt = (
        select(Transaction, Category)
        .join(Category, Category.id == Transaction.category_id, isouter=True)
        .where(Transaction.user_id == user_id)
        .order_by(Transaction.id.desc())
        .limit(limit)
    )
    return [(row[0], row[1]) for row in session.exec(stmt).all()]


def search_transactions(
    session: Session, user_id: int, keyword: str, limit: int = 15
) -> list[tuple[Transaction, Category | None]]:
    escaped = (
        keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    )
    stmt = (
        select(Transaction, Category)
        .join(Category, Category.id == Transaction.category_id, isouter=True)
        .where(
            Transaction.user_id == user_id,
            Transaction.note.like(f"%{escaped}%", escape="\\"),
        )
        .order_by(Transaction.id.desc())
        .limit(limit)
    )
    return [(row[0], row[1]) for row in session.exec(stmt).all()]


# ---------------------------------------------------------------- agregasi


def get_totals(
    session: Session,
    user_id: int,
    start: datetime | None = None,
    end: datetime | None = None,
    *,
    account_id: int | None = None,
) -> tuple[int, int]:
    """Kembalikan (total_masuk, total_keluar)."""
    stmt = select(
        Transaction.kind, sa_func.coalesce(sa_func.sum(Transaction.amount), 0)
    ).where(Transaction.user_id == user_id)
    if start is not None:
        stmt = stmt.where(Transaction.occurred_at >= start)
    if end is not None:
        stmt = stmt.where(Transaction.occurred_at < end)
    if account_id is not None:
        stmt = stmt.where(Transaction.account_id == account_id)
    stmt = stmt.group_by(Transaction.kind)

    income = expense = 0
    for kind, total in session.exec(stmt).all():
        if kind == TYPE_INCOME:
            income = int(total)
        elif kind == TYPE_EXPENSE:
            expense = int(total)
    return income, expense


def count_transactions(
    session: Session, user_id: int, start: datetime | None = None, end: datetime | None = None
) -> int:
    stmt = select(sa_func.count(Transaction.id)).where(Transaction.user_id == user_id)
    if start is not None:
        stmt = stmt.where(Transaction.occurred_at >= start)
    if end is not None:
        stmt = stmt.where(Transaction.occurred_at < end)
    return int(session.exec(stmt).one() or 0)


def category_breakdown(
    session: Session,
    user_id: int,
    start: datetime,
    end: datetime,
    kind: str,
    limit: int | None = None,
) -> list[tuple[str, str, int]]:
    """Kembalikan [(emoji, nama, total)] urut terbesar."""
    stmt = (
        select(
            Category.emoji,
            Category.name,
            sa_func.sum(Transaction.amount).label("total"),
        )
        .join(Category, Category.id == Transaction.category_id)
        .where(
            Transaction.user_id == user_id,
            Transaction.occurred_at >= start,
            Transaction.occurred_at < end,
            Transaction.kind == kind,
        )
        .group_by(Category.id)
        .order_by(sa_func.sum(Transaction.amount).desc())
    )
    if limit:
        stmt = stmt.limit(limit)
    return [(row[0] or "", row[1], int(row[2])) for row in session.exec(stmt).all()]


def account_balance(session: Session, user: User, account: Account) -> int:
    income, expense = get_totals(session, user.id, account_id=account.id)
    return int(account.opening_balance) + income - expense


def total_balance(session: Session, user: User) -> int:
    total = 0
    for account in list_accounts(session, user.id):
        total += account_balance(session, user, account)
    return total


# ---------------------------------------------------------------- bulan & periode


@dataclass
class PeriodSummary:
    year: int
    month: int
    income: int = 0
    expense: int = 0
    tx_count: int = 0
    top_expense: list[tuple[str, str, int]] = field(default_factory=list)
    top_income: list[tuple[str, str, int]] = field(default_factory=list)
    prev_expense: int | None = None


def month_summary(
    session: Session,
    user: User,
    year: int,
    month: int,
    *,
    tz_name: str | None = None,
    top_n: int = 5,
) -> PeriodSummary:
    tz = tz_name or user.timezone
    start, end = month_bounds(year, month, tz)
    income, expense = get_totals(session, user.id, start, end)
    summary = PeriodSummary(
        year=year,
        month=month,
        income=income,
        expense=expense,
        tx_count=count_transactions(session, user.id, start, end),
        top_expense=category_breakdown(session, user.id, start, end, TYPE_EXPENSE, top_n),
        top_income=category_breakdown(session, user.id, start, end, TYPE_INCOME, top_n),
    )

    from bot.timeutil import add_months

    prev_year, prev_month = add_months(year, month, -1)
    prev_start, prev_end = month_bounds(prev_year, prev_month, tz)
    prev_income, prev_expense = get_totals(session, user.id, prev_start, prev_end)
    if prev_expense or prev_income:
        summary.prev_expense = prev_expense
    return summary


def comparison_text(current: int, previous: int | None) -> str | None:
    if previous is None or previous == 0:
        return None
    delta = current - previous
    pct = int(round(abs(delta) / previous * 100))
    if delta == 0:
        return "vs bulan lalu: sama"
    if delta < 0:
        return f"vs bulan lalu: keluar turun {pct}% ✅"
    return f"vs bulan lalu: keluar naik {pct}% ⚠️"


def daily_summary(
    session: Session, user: User, day: date, *, tz_name: str | None = None
) -> tuple[int, int, list[tuple[Transaction, Category | None]]]:
    tz = tz_name or user.timezone
    start, end = day_bounds(day, tz)
    income, expense = get_totals(session, user.id, start, end)
    items = transactions_in_range(session, user.id, start, end)
    return income, expense, items


# ---------------------------------------------------------------- anggaran


def set_budget(session: Session, user: User, category: Category, amount: int) -> Budget | None:
    """Set batas bulanan. amount <= 0 menghapus anggaran."""
    existing = session.exec(
        select(Budget).where(
            Budget.user_id == user.id, Budget.category_id == category.id
        )
    ).first()

    if amount <= 0:
        if existing:
            session.delete(existing)
            session.commit()
        return None

    if category.kind != TYPE_EXPENSE:
        raise LedgerError("Anggaran hanya untuk kategori pengeluaran.")

    if existing:
        existing.amount = int(amount)
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing

    budget = Budget(user_id=user.id, category_id=category.id, amount=int(amount))
    session.add(budget)
    session.commit()
    session.refresh(budget)
    return budget


def budget_status(
    session: Session, user: User, year: int, month: int, *, tz_name: str | None = None
) -> list[tuple[Category, int, int]]:
    """[(kategori, batas, terpakai)] untuk semua anggaran user."""
    tz = tz_name or user.timezone
    start, end = month_bounds(year, month, tz)
    rows: list[tuple[Category, int, int]] = []
    budgets = session.exec(
        select(Budget).where(Budget.user_id == user.id).order_by(Budget.id)
    ).all()
    for budget in budgets:
        category = session.get(Category, budget.category_id)
        if category is None:
            continue
        used = session.exec(
            select(sa_func.coalesce(sa_func.sum(Transaction.amount), 0)).where(
                Transaction.user_id == user.id,
                Transaction.category_id == budget.category_id,
                Transaction.kind == TYPE_EXPENSE,
                Transaction.occurred_at >= start,
                Transaction.occurred_at < end,
            )
        ).one()
        rows.append((category, int(budget.amount), int(used or 0)))
    return rows


def budget_alerts(session: Session, user: User, *, tz_name: str | None = None) -> list[str]:
    # WAJIB pakai zona user, bukan jam server: server UTC akan salah bulan
    # untuk user WIB pada 00:00-07:00 tanggal 1.
    now_local = local_now(tz_name or user.timezone)
    rows = budget_status(session, user, now_local.year, now_local.month, tz_name=tz_name)
    alerts: list[str] = []
    for category, limit, used in rows:
        if limit <= 0:
            continue
        ratio = used / limit
        if ratio >= 1:
            alerts.append(f"🚨 Anggaran {category.emoji} {category.name} sudah lewat: {used}/{limit}")
        elif ratio >= 0.8:
            alerts.append(f"⚠️ Anggaran {category.emoji} {category.name} hampir habis ({int(ratio*100)}%)")
    return alerts


# ---------------------------------------------------------------- kategori


def create_category(
    session: Session, user: User, name: str, kind: str, keywords: str = "", emoji: str = "🏷"
) -> Category:
    clean = (name or "").strip()
    if not clean:
        raise LedgerError("Nama kategori tidak boleh kosong.")
    if len(clean) > 40:
        raise LedgerError("Nama kategori maksimal 40 karakter.")
    if kind not in (TYPE_INCOME, TYPE_EXPENSE):
        raise LedgerError("Jenis kategori harus 'masuk' atau 'keluar'.")
    if find_category(session, user.id, clean, kind):
        raise LedgerError(f"Kategori '{clean}' sudah ada.")

    category = Category(
        user_id=user.id,
        name=clean,
        kind=kind,
        emoji=emoji or "🏷",
        keywords=",".join(k.strip() for k in keywords.split(",") if k.strip()),
        is_default=False,
    )
    session.add(category)
    session.commit()
    session.refresh(category)
    return category


def update_category_keywords(
    session: Session, user: User, name: str, keywords: str
) -> Category:
    category = find_category(session, user.id, name)
    if category is None:
        raise LedgerError(f"Kategori '{name}' tidak ditemukan.")
    category.keywords = ",".join(k.strip() for k in keywords.split(",") if k.strip())
    session.add(category)
    session.commit()
    session.refresh(category)
    return category


def delete_category(session: Session, user: User, name: str) -> Category:
    category = find_category(session, user.id, name)
    if category is None:
        raise LedgerError(f"Kategori '{name}' tidak ditemukan.")
    used = session.exec(
        select(sa_func.count(Transaction.id)).where(
            Transaction.user_id == user.id, Transaction.category_id == category.id
        )
    ).one()
    if used:
        raise LedgerError(
            f"Kategori '{category.name}' masih dipakai {used} transaksi. "
            "Hapus/ubah transaksinya dulu."
        )
    budget = session.exec(
        select(Budget).where(
            Budget.user_id == user.id, Budget.category_id == category.id
        )
    ).first()
    if budget:
        session.delete(budget)
    session.delete(category)
    session.commit()
    return category


# ---------------------------------------------------------------- export


def export_csv(session: Session, user: User, start: datetime, end: datetime) -> tuple[bytes, int]:
    """CSV transaksi satu periode (UTF-8 + BOM supaya rapi di Excel)."""
    from bot.csvsync import sanitize_cell

    items = transactions_in_range(session, user.id, start, end)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["id", "tanggal", "jenis", "kategori", "akun", "nominal", "catatan"])

    accounts = {acc.id: acc.name for acc in list_accounts(session, user.id)}
    for trx, category in items:
        writer.writerow(
            [
                trx.id,
                format_datetime_local(trx.occurred_at, user.timezone),
                "masuk" if trx.kind == TYPE_INCOME else "keluar",
                sanitize_cell(category.name if category else ""),
                sanitize_cell(accounts.get(trx.account_id, "")),
                trx.amount,
                sanitize_cell(trx.note),
            ]
        )
    data = ("\ufeff" + buffer.getvalue()).encode("utf-8")
    return data, len(items)


def monthly_history(
    session: Session, user: User, months: int = 6, *, tz_name: str | None = None
) -> list[tuple[str, int, int]]:
    """Ringkasan beberapa bulan terakhir (termasuk bulan ini)."""
    from bot.timeutil import MONTH_NAMES, add_months, local_now

    tz = tz_name or user.timezone
    out: list[tuple[str, int, int]] = []
    cursor = local_now(tz)
    year, month = cursor.year, cursor.month
    for _ in range(months):
        start, end = month_bounds(year, month, tz)
        income, expense = get_totals(session, user.id, start, end)
        out.append((f"{MONTH_NAMES[month][:3]} {year}", income, expense))
        year, month = add_months(year, month, -1)
    return out


def local_day_start_utc(day: date, tz_name: str) -> tuple[datetime, datetime]:
    return day_bounds(day, tz_name)


def local_to_utc(dt: datetime, tz_name: str) -> datetime:
    return local_naive_to_utc(dt, tz_name)

"""Lapisan layanan aplikasi desktop.

Sengaja bebas dari Qt supaya bisa dites tanpa membuka jendela, dan supaya
semua aturan bisnis tetap satu tempat. Semua objek yang keluar dari modul ini
adalah dataclass biasa, bukan objek ORM, sehingga aman dipakai setelah
Session ditutup.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import func as sa_func
from sqlmodel import Session, select

from bot.csvsync import ledger_path, rewrite_ledger
from bot.db import create_db_engine, init_db
from bot.entry import KIND_EMOJI, save_from_text
from bot.jobs.backup import backup_database
from bot.ledger import (
    LedgerError,
    budget_status,
    comparison_text,
    count_transactions,
    delete_transaction as delete_transaction_row,
    export_csv,
    find_category,
    get_default_account,
    get_totals,
    get_transaction,
    list_accounts,
    list_categories,
    month_summary,
    monthly_history,
    set_budget as apply_budget,
    total_balance,
)
from bot.models import (
    TYPE_EXPENSE,
    TYPE_INCOME,
    Category,
    Transaction,
    User,
)
from bot.parser import MAX_AMOUNT
from bot.services_defaults import ensure_user
from bot.timeutil import (
    day_bounds,
    local_naive_to_utc,
    local_now,
    month_bounds,
    month_label,
    utc_to_local_naive,
)

logger = logging.getLogger(__name__)

DEFAULT_TZ = "Asia/Jakarta"

# telegram_id sintetis untuk instalasi desktop yang berdiri sendiri.
# Kalau user mengimpor database bot, baris user yang sudah ada dipakai ulang.
LOCAL_TELEGRAM_ID = 1


# ---------------------------------------------------------------- data untuk UI


@dataclass(frozen=True)
class TxRow:
    id: int
    when: datetime  # naive waktu lokal
    kind: str
    amount: int
    note: str
    category_id: int
    category: str  # sudah termasuk emoji, mis. "🍜 Makan"
    account: str

    @property
    def signed_amount(self) -> int:
        return self.amount if self.kind == TYPE_INCOME else -self.amount

    @property
    def kind_label(self) -> str:
        return "Masuk" if self.kind == TYPE_INCOME else "Keluar"


@dataclass(frozen=True)
class BudgetRow:
    category_id: int
    category: str
    limit: int
    used: int

    @property
    def remaining(self) -> int:
        return self.limit - self.used

    @property
    def ratio(self) -> float:
        if self.limit <= 0:
            return 0.0
        return self.used / self.limit

    @property
    def status(self) -> str:
        if self.ratio >= 1:
            return "lewat"
        if self.ratio >= 0.8:
            return "hampir"
        return "aman"


@dataclass(frozen=True)
class CategoryRow:
    id: int
    name: str
    kind: str
    emoji: str
    keywords: str
    is_default: bool
    used: int = 0

    @property
    def label(self) -> str:
        return f"{self.emoji} {self.name}".strip()


@dataclass(frozen=True)
class Dashboard:
    balance: int
    month_name: str
    month_income: int
    month_expense: int
    today_label: str
    today_income: int
    today_expense: int
    today_rows: list[TxRow] = field(default_factory=list)
    budgets: list[BudgetRow] = field(default_factory=list)
    total_transactions: int = 0
    first_date: str = ""
    last_date: str = ""
    today_count: int = 0


@dataclass(frozen=True)
class MonthReport:
    year: int
    month: int
    label: str
    income: int
    expense: int
    tx_count: int
    top_expense: list[tuple[str, str, int]] = field(default_factory=list)
    top_income: list[tuple[str, str, int]] = field(default_factory=list)
    comparison: str | None = None
    prev_expense: int | None = None

    @property
    def net(self) -> int:
        return self.income - self.expense


@dataclass(frozen=True)
class SaveOutcome:
    row: TxRow
    date_label: str
    budget_note: str | None = None


@dataclass(frozen=True)
class StorageInfo:
    db_path: Path
    export_path: Path
    backup_path: Path
    db_bytes: int
    tx_count: int
    first_date: str
    last_date: str


# ---------------------------------------------------------------- service


class LedgerService:
    """Satu pintu masuk untuk semua operasi data aplikasi desktop."""

    def __init__(
        self,
        db_path: str | Path,
        export_dir: str | Path | None = None,
        *,
        backup_dir: str | Path | None = None,
        backup_keep: int = 7,
    ) -> None:
        self.db_path = Path(db_path)
        self.export_dir = Path(export_dir) if export_dir else self.db_path.parent / "exports"
        self.backup_dir = Path(backup_dir) if backup_dir else self.db_path.parent / "backups"
        self.backup_keep = max(1, int(backup_keep))
        self._lock = threading.RLock()
        self._engine = create_db_engine(self.db_path)
        init_db(self._engine)
        self._user_id: int | None = None
        self._tz = DEFAULT_TZ
        self._bootstrap()

    # ---------------------------------------------------------- infrastruktur

    def _bootstrap(self) -> None:
        with self.session() as session:
            user = session.exec(select(User).order_by(User.id)).first()
            if user is None:
                user, _ = ensure_user(session, LOCAL_TELEGRAM_ID, "Saya")
            self._user_id = int(user.id)
            self._tz = user.timezone or DEFAULT_TZ

    def session(self) -> "_SessionCtx":
        return _SessionCtx(self)

    def close(self) -> None:
        with self._lock:
            self._engine.dispose()

    @property
    def tz(self) -> str:
        return self._tz

    def _user(self, session: Session) -> User:
        user = session.get(User, self._user_id) if self._user_id is not None else None
        if user is None:  # pragma: no cover - hanya kalau DB diganti saat jalan
            user = session.exec(select(User).order_by(User.id)).first()
            if user is None:
                raise LedgerError("Database belum siap. Jalankan ulang aplikasi.")
            self._user_id = int(user.id)
        return user

    def ledger_file(self) -> Path:
        with self.session() as session:
            user = self._user(session)
            return ledger_path(self.export_dir, user.telegram_id)

    # ---------------------------------------------------------- konversi

    def _to_row(self, trx: Transaction, category: Category | None, accounts: dict[int, str]) -> TxRow:
        emoji = (getattr(category, "emoji", "") or "").strip()
        name = getattr(category, "name", "") or "Tanpa Kategori"
        return TxRow(
            id=int(trx.id),
            when=utc_to_local_naive(trx.occurred_at, self._tz),
            kind=trx.kind,
            amount=int(trx.amount),
            note=(trx.note or "").strip(),
            category_id=int(trx.category_id),
            category=f"{emoji} {name}".strip(),
            account=accounts.get(trx.account_id, ""),
        )

    def _account_map(self, session: Session, user: User) -> dict[int, str]:
        return {int(acc.id): acc.name for acc in list_accounts(session, user.id)}

    def _sync_ledger(self, session: Session, user: User) -> None:
        """Tulis ulang CSV supaya selalu sama dengan isi database.

        Ditulis ulang (bukan append) karena aplikasi desktop mengizinkan
        transaksi bertanggal mundur; append akan membuat urutan file kacau.
        Untuk ribuan baris biayanya tetap di bawah 10 ms.
        """
        try:
            rewrite_ledger(ledger_path(self.export_dir, user.telegram_id), session, user)
        except Exception:  # pragma: no cover - CSV tidak boleh menggagalkan simpan
            logger.exception("Gagal menyinkronkan CSV ledger")

    # ---------------------------------------------------------- mutasi

    def add_from_text(self, text: str, forced_kind: str | None = None) -> SaveOutcome:
        with self.session() as session:
            user = self._user(session)
            result, added, category, kind = save_from_text(
                session, user, text, None, forced_kind
            )
            if added.duplicate:  # pragma: no cover - desktop tidak mengirim message_id
                raise LedgerError("Transaksi ini sudah tercatat.")
            self._sync_ledger(session, user)
            row = self._to_row(added.transaction, category, self._account_map(session, user))
            note = self._budget_note(session, user, category)
            return SaveOutcome(row=row, date_label=result.date_label, budget_note=note)

    def add_manual(
        self,
        *,
        kind: str,
        amount: int,
        category_id: int,
        note: str,
        when_local: datetime,
        account_id: int | None = None,
    ) -> TxRow:
        with self.session() as session:
            user = self._user(session)
            category = self._require_category(session, user, category_id, kind)
            account = self._require_account(session, user, account_id)
            amount = self._check_amount(amount)

            from bot.ledger import add_transaction

            added = add_transaction(
                session,
                user,
                kind=kind,
                amount=amount,
                category=category,
                account=account,
                note=note,
                occurred_at=local_naive_to_utc(when_local, self._tz),
            )
            self._sync_ledger(session, user)
            return self._to_row(added.transaction, category, self._account_map(session, user))

    def update_transaction(
        self,
        trx_id: int,
        *,
        kind: str,
        amount: int,
        category_id: int,
        note: str,
        when_local: datetime,
        account_id: int | None = None,
    ) -> TxRow:
        with self.session() as session:
            user = self._user(session)
            trx = get_transaction(session, user.id, trx_id)
            if trx is None:
                raise LedgerError(f"Transaksi #{trx_id} tidak ditemukan.")

            category = self._require_category(session, user, category_id, kind)
            account = self._require_account(session, user, account_id)

            trx.kind = kind
            trx.amount = self._check_amount(amount)
            trx.category_id = int(category.id)
            trx.account_id = int(account.id)
            trx.note = (note or "").strip()[:500]
            trx.occurred_at = local_naive_to_utc(when_local, self._tz)
            session.add(trx)
            session.commit()
            session.refresh(trx)

            self._sync_ledger(session, user)
            return self._to_row(trx, category, self._account_map(session, user))

    def delete_transaction(self, trx_id: int) -> None:
        with self.session() as session:
            user = self._user(session)
            delete_transaction_row(session, user.id, trx_id)
            self._sync_ledger(session, user)

    def undo_last(self) -> TxRow | None:
        with self.session() as session:
            user = self._user(session)
            trx = session.exec(
                select(Transaction)
                .where(Transaction.user_id == user.id)
                .order_by(Transaction.id.desc())
                .limit(1)
            ).first()
            if trx is None:
                return None
            category = session.get(Category, trx.category_id)
            row = self._to_row(trx, category, self._account_map(session, user))
            delete_transaction_row(session, user.id, int(trx.id))
            self._sync_ledger(session, user)
            return row

    # ---------------------------------------------------------- baca

    def list_transactions(
        self,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        kind: str | None = None,
        keyword: str = "",
        category_id: int | None = None,
        account_id: int | None = None,
        limit: int | None = 1000,
    ) -> list[TxRow]:
        with self.session() as session:
            user = self._user(session)
            stmt = (
                select(Transaction, Category)
                .join(Category, Category.id == Transaction.category_id, isouter=True)
                .where(Transaction.user_id == user.id)
            )
            if start is not None:
                stmt = stmt.where(Transaction.occurred_at >= start)
            if end is not None:
                stmt = stmt.where(Transaction.occurred_at < end)
            if kind in (TYPE_INCOME, TYPE_EXPENSE):
                stmt = stmt.where(Transaction.kind == kind)
            if category_id is not None:
                stmt = stmt.where(Transaction.category_id == category_id)
            if account_id is not None:
                stmt = stmt.where(Transaction.account_id == account_id)
            keyword = (keyword or "").strip()
            if keyword:
                escaped = (
                    keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                )
                stmt = stmt.where(Transaction.note.like(f"%{escaped}%", escape="\\"))

            stmt = stmt.order_by(Transaction.occurred_at.desc(), Transaction.id.desc())
            if limit:
                stmt = stmt.limit(limit)

            accounts = self._account_map(session, user)
            return [self._to_row(trx, cat, accounts) for trx, cat in session.exec(stmt).all()]

    def dashboard(self, *, today_limit: int = 8) -> Dashboard:
        with self.session() as session:
            user = self._user(session)
            now = local_now(self._tz)
            start, end = month_bounds(now.year, now.month, self._tz)
            income, expense = get_totals(session, user.id, start, end)

            today = now.date()
            d_start, d_end = day_bounds(today, self._tz)
            d_income, d_expense = get_totals(session, user.id, d_start, d_end)
            d_count = count_transactions(session, user.id, d_start, d_end)

            accounts = self._account_map(session, user)
            today_rows = [
                self._to_row(trx, cat, accounts)
                for trx, cat in _query_range(session, user.id, d_start, d_end, today_limit)
            ]

            budgets = [
                BudgetRow(
                    category_id=int(cat.id),
                    category=f"{(cat.emoji or '').strip()} {cat.name}".strip(),
                    limit=int(limit),
                    used=int(used),
                )
                for cat, limit, used in budget_status(
                    session, user, today.year, today.month, tz_name=self._tz
                )
            ]

            first, last = _date_range(session, user.id, self._tz)
            return Dashboard(
                balance=total_balance(session, user),
                month_name=month_label(now.year, now.month),
                month_income=income,
                month_expense=expense,
                today_label=_today_label(today),
                today_income=d_income,
                today_expense=d_expense,
                today_rows=today_rows,
                budgets=budgets,
                total_transactions=count_transactions(session, user.id),
                first_date=first,
                last_date=last,
                today_count=d_count,
            )

    def month_report(self, year: int, month: int) -> MonthReport:
        with self.session() as session:
            user = self._user(session)
            summary = month_summary(session, user, year, month, tz_name=self._tz)
            return MonthReport(
                year=year,
                month=month,
                label=month_label(year, month),
                income=summary.income,
                expense=summary.expense,
                tx_count=summary.tx_count,
                top_expense=summary.top_expense,
                top_income=summary.top_income,
                comparison=comparison_text(summary.expense, summary.prev_expense),
                prev_expense=summary.prev_expense,
            )

    def history(self, months: int = 12) -> list[tuple[str, int, int]]:
        with self.session() as session:
            user = self._user(session)
            return monthly_history(session, user, months, tz_name=self._tz)

    def month_totals(self, year: int, month: int) -> tuple[int, int]:
        with self.session() as session:
            user = self._user(session)
            start, end = month_bounds(year, month, self._tz)
            return get_totals(session, user.id, start, end)

    # ---------------------------------------------------------- anggaran

    def budgets(self, year: int, month: int) -> list[BudgetRow]:
        with self.session() as session:
            user = self._user(session)
            return [
                BudgetRow(
                    category_id=int(cat.id),
                    category=f"{(cat.emoji or '').strip()} {cat.name}".strip(),
                    limit=int(limit),
                    used=int(used),
                )
                for cat, limit, used in budget_status(
                    session, user, year, month, tz_name=self._tz
                )
            ]

    def set_budget(self, category_id: int, amount: int) -> None:
        with self.session() as session:
            user = self._user(session)
            category = session.get(Category, category_id)
            if category is None or category.user_id != user.id:
                raise LedgerError("Kategori tidak ditemukan.")
            if amount < 0:
                raise LedgerError("Anggaran tidak boleh negatif.")
            apply_budget(session, user, category, int(amount))

    # ---------------------------------------------------------- kategori

    def categories(self, kind: str | None = None) -> list[CategoryRow]:
        with self.session() as session:
            user = self._user(session)
            used_map = dict(
                session.exec(
                    select(Transaction.category_id, sa_func.count(Transaction.id))
                    .where(Transaction.user_id == user.id)
                    .group_by(Transaction.category_id)
                ).all()
            )
            return [
                CategoryRow(
                    id=int(cat.id),
                    name=cat.name,
                    kind=cat.kind,
                    emoji=cat.emoji or "",
                    keywords=cat.keywords or "",
                    is_default=bool(cat.is_default),
                    used=int(used_map.get(cat.id, 0)),
                )
                for cat in list_categories(session, user.id, kind)
            ]

    def add_category(self, name: str, kind: str, emoji: str, keywords: str) -> CategoryRow:
        from bot.ledger import create_category

        with self.session() as session:
            user = self._user(session)
            cat = create_category(session, user, name, kind, keywords, emoji)
            self._sync_ledger(session, user)
            return CategoryRow(
                id=int(cat.id),
                name=cat.name,
                kind=cat.kind,
                emoji=cat.emoji or "",
                keywords=cat.keywords or "",
                is_default=bool(cat.is_default),
                used=0,
            )

    def update_category(
        self,
        category_id: int,
        *,
        name: str,
        emoji: str,
        keywords: str,
    ) -> None:
        with self.session() as session:
            user = self._user(session)
            cat = session.get(Category, category_id)
            if cat is None or cat.user_id != user.id:
                raise LedgerError("Kategori tidak ditemukan.")

            clean = (name or "").strip()
            if not clean:
                raise LedgerError("Nama kategori tidak boleh kosong.")
            if len(clean) > 40:
                raise LedgerError("Nama kategori maksimal 40 karakter.")
            if clean.lower() != cat.name.lower():
                existing = find_category(session, user.id, clean, cat.kind)
                if existing is not None and existing.id != cat.id:
                    raise LedgerError(f"Kategori '{clean}' sudah ada.")

            cat.name = clean
            cat.emoji = (emoji or "").strip() or "🏷"
            cat.keywords = ",".join(k.strip() for k in (keywords or "").split(",") if k.strip())
            session.add(cat)
            session.commit()
            self._sync_ledger(session, user)

    def delete_category(self, category_id: int) -> None:
        from bot.ledger import delete_category_by_id

        with self.session() as session:
            user = self._user(session)
            delete_category_by_id(session, user, category_id)
            self._sync_ledger(session, user)

    # ---------------------------------------------------------- akun

    def accounts(self) -> list[tuple[int, str]]:
        with self.session() as session:
            user = self._user(session)
            return [(int(acc.id), acc.name) for acc in list_accounts(session, user.id)]

    def account_balances(self) -> list[tuple[str, int]]:
        from bot.ledger import account_balance

        with self.session() as session:
            user = self._user(session)
            return [
                (acc.name, account_balance(session, user, acc))
                for acc in list_accounts(session, user.id)
            ]

    # ---------------------------------------------------------- export & berkas

    def export_month(self, year: int, month: int) -> tuple[bytes, int]:
        with self.session() as session:
            user = self._user(session)
            start, end = month_bounds(year, month, self._tz)
            return export_csv(session, user, start, end)

    def rebuild_ledger(self) -> tuple[Path, int]:
        with self.session() as session:
            user = self._user(session)
            path = ledger_path(self.export_dir, user.telegram_id)
            count = rewrite_ledger(path, session, user)
            return path, count

    def storage_info(self) -> StorageInfo:
        with self.session() as session:
            user = self._user(session)
            first, last = _date_range(session, user.id, self._tz)
            count = count_transactions(session, user.id)
        size = self.db_path.stat().st_size if self.db_path.exists() else 0
        return StorageInfo(
            db_path=self.db_path,
            export_path=self.export_dir,
            backup_path=self.backup_dir,
            db_bytes=size,
            tx_count=count,
            first_date=first,
            last_date=last,
        )

    def backup_now(self) -> Path | None:
        return backup_database(self._engine, self.backup_dir, self.backup_keep)

    def import_database(self, source: str | Path) -> None:
        """Ganti database dengan file lain (mis. hasil versi Telegram).

        File lama dibackup dulu, isi file baru disalin lewat API backup SQLite
        (supaya transaksi yang masih di file -wal ikut terbawa), lalu engine
        dibangun ulang agar tidak ada koneksi yang menunjuk file lama.
        """
        src = Path(source)
        if not src.exists():
            raise LedgerError("File database tidak ditemukan.")
        if src.resolve() == self.db_path.resolve():
            raise LedgerError("Itu database yang sedang dipakai.")

        _validate_sqlite_database(src)
        self.backup_now()

        staging = self.db_path.with_suffix(".import.tmp")
        if staging.exists():
            staging.unlink()

        try:
            _copy_database(src, staging)
            _validate_sqlite_database(staging)
        except LedgerError:
            staging.unlink(missing_ok=True)
            raise
        except Exception as exc:  # noqa: BLE001
            staging.unlink(missing_ok=True)
            raise LedgerError(f"Gagal menyalin database: {exc}") from exc

        with self._lock:
            self._engine.dispose()
            for suffix in ("-wal", "-shm"):
                Path(str(self.db_path) + suffix).unlink(missing_ok=True)
            os.replace(staging, self.db_path)
            self._engine = create_db_engine(self.db_path)
            init_db(self._engine)
            self._user_id = None
            self._bootstrap()

    # ---------------------------------------------------------- pengaturan

    def set_timezone(self, tz_name: str) -> None:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(tz_name)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise LedgerError(f"Zona waktu tidak dikenal: {tz_name}") from exc

        with self.session() as session:
            user = self._user(session)
            user.timezone = tz_name
            session.add(user)
            session.commit()
            self._tz = tz_name

    def user_name(self) -> str:
        with self.session() as session:
            return self._user(session).name or ""

    def set_user_name(self, name: str) -> None:
        with self.session() as session:
            user = self._user(session)
            user.name = (name or "").strip()[:80]
            session.add(user)
            session.commit()

    # ---------------------------------------------------------- bantuan internal

    def _check_amount(self, amount: int) -> int:
        value = int(amount)
        if value <= 0:
            raise LedgerError("Nominal harus lebih dari 0.")
        if value > MAX_AMOUNT:
            raise LedgerError("Nominal terlalu besar. Cek lagi angkanya.")
        return value

    def _require_category(self, session: Session, user: User, category_id: int, kind: str) -> Category:
        category = session.get(Category, int(category_id))
        if category is None or category.user_id != user.id:
            raise LedgerError("Kategori tidak ditemukan.")
        if category.kind != kind:
            raise LedgerError(
                f"Kategori '{category.name}' bukan untuk transaksi {KIND_EMOJI[kind]}."
            )
        return category

    def _require_account(self, session: Session, user: User, account_id: int | None):
        accounts = list_accounts(session, user.id)
        if not accounts:
            # Database tanpa akun (mis. hasil impor manual) tetap bisa dipakai:
            # buat satu akun default alih-alih menampilkan jalan buntu.
            from bot.models import Account

            account = Account(user_id=user.id, name="Dompet", kind="cash")
            session.add(account)
            session.commit()
            session.refresh(account)
            return account
        if account_id is None:
            return get_default_account(session, user.id)
        for account in accounts:
            if int(account.id) == int(account_id):
                return account
        raise LedgerError("Akun tidak ditemukan.")

    def _budget_note(self, session: Session, user: User, category: Category | None) -> str | None:
        if category is None or category.kind != TYPE_EXPENSE:
            return None
        now = local_now(self._tz)
        rows = budget_status(session, user, now.year, now.month, tz_name=self._tz)
        match = next((row for row in rows if row[0].id == category.id), None)
        if match is None:
            return None
        _cat, limit, used = match
        if limit <= 0:
            return None
        ratio = used / limit
        if ratio >= 1:
            return f"🚨 Anggaran {category.name} lewat: {_rp(used)} / {_rp(limit)}"
        if ratio >= 0.8:
            return (
                f"⚠️ Anggaran {category.name} terpakai {int(round(ratio * 100))}%. "
                f"Sisa {_rp(limit - used)}."
            )
        return None


# ---------------------------------------------------------------- helper modul


class _SessionCtx:
    """Context manager Session yang memegang lock service.

    SQLite hanya mengizinkan satu penulis; lock ini mencegah dua operasi
    (mis. klik cepat dua kali) saling menabrak.
    """

    def __init__(self, service: LedgerService) -> None:
        self._service = service
        self._session: Session | None = None

    def __enter__(self) -> Session:
        self._service._lock.acquire()
        try:
            self._session = Session(self._service._engine)
        except BaseException:
            # Jangan tinggalkan lock terkunci kalau Session gagal dibuat.
            self._service._lock.release()
            raise
        return self._session

    def __exit__(self, exc_type, exc, tb) -> bool:
        try:
            if self._session is not None:
                self._session.close()
        finally:
            self._session = None
            self._service._lock.release()
        return False


def _query_range(session: Session, user_id: int, start: datetime, end: datetime, limit: int):
    stmt = (
        select(Transaction, Category)
        .join(Category, Category.id == Transaction.category_id, isouter=True)
        .where(
            Transaction.user_id == user_id,
            Transaction.occurred_at >= start,
            Transaction.occurred_at < end,
        )
        .order_by(Transaction.occurred_at, Transaction.id)
        .limit(limit)
    )
    return session.exec(stmt).all()


def _date_range(session: Session, user_id: int, tz_name: str = DEFAULT_TZ) -> tuple[str, str]:
    stmt = select(
        sa_func.min(Transaction.occurred_at), sa_func.max(Transaction.occurred_at)
    ).where(Transaction.user_id == user_id)
    first, last = session.exec(stmt).one()
    if not first:
        return "", ""
    return (
        utc_to_local_naive(first, tz_name).strftime("%d/%m/%Y")
        if isinstance(first, datetime)
        else str(first),
        utc_to_local_naive(last, tz_name).strftime("%d/%m/%Y")
        if isinstance(last, datetime)
        else str(last),
    )


def _today_label(day: date) -> str:
    from bot.timeutil import DAY_NAMES, MONTH_NAMES

    return f"{DAY_NAMES[day.weekday()]}, {day.day} {MONTH_NAMES[day.month]} {day.year}"


def _rp(amount: int) -> str:
    from bot.formatting import money

    return money(amount)


def _copy_database(source: Path, target: Path) -> None:
    """Salin database lewat API backup SQLite.

    `shutil.copy2` tidak cukup: kalau database sumber memakai WAL dan masih
    punya transaksi di file -wal, menyalin file .db saja akan kehilangan data.
    API backup membaca lewat koneksi, jadi hasilnya selalu konsisten.
    """
    src_conn = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
    try:
        dst_conn = sqlite3.connect(str(target))
        try:
            src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
    finally:
        src_conn.close()


def _validate_sqlite_database(path: Path) -> None:
    required = {"users", "accounts", "categories", "transactions"}
    try:
        connection = sqlite3.connect(str(path))
    except sqlite3.Error as exc:
        raise LedgerError(f"File tidak bisa dibuka sebagai database: {exc}") from exc
    try:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    except sqlite3.DatabaseError as exc:
        raise LedgerError("File itu bukan database SQLite yang valid.") from exc
    finally:
        connection.close()

    tables = {row[0] for row in rows}
    missing = required - tables
    if missing:
        raise LedgerError(
            "Database tidak dikenali (tabel hilang: " + ", ".join(sorted(missing)) + ")."
        )

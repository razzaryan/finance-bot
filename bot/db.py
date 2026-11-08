"""Koneksi database & inisialisasi skema."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine


def create_db_engine(db_path: str | Path) -> Engine:
    """Buat engine SQLite. Path khusus ':memory:' didukung untuk test.

    `timeout` di connect_args adalah busy timeout SQLite (detik). Tanpa ini,
    transaksi tulis yang bertabrakan dengan job backup/rekap langsung gagal
    dengan "database is locked".
    """
    if str(db_path) == ":memory:":
        from sqlalchemy.pool import StaticPool

        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False, "timeout": 30},
            poolclass=StaticPool,
        )
    else:
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(
            f"sqlite:///{path.as_posix()}",
            connect_args={"check_same_thread": False, "timeout": 30},
        )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _record):  # pragma: no cover - driver level
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()

    return engine


def init_db(engine: Engine) -> None:
    """Buat tabel kalau belum ada. Aman dipanggil berulang."""
    # Import dipakai supaya semua model terdaftar di metadata SQLModel.
    import bot.models  # noqa: F401  # isort: skip

    SQLModel.metadata.create_all(engine)


def session_factory(engine: Engine):
    def _factory() -> Session:
        return Session(engine)

    return _factory

"""Backup database SQLite harian."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from sqlalchemy import text
from sqlmodel import Session

logger = logging.getLogger(__name__)


def backup_database(engine, backup_dir: Path, keep: int = 7) -> Path | None:
    """Salin DB secara konsisten pakai VACUUM INTO, lalu pangkas backup lama."""
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = backup_dir / f"finance-{stamp}.db"

    try:
        with Session(engine) as session:
            # VACUUM INTO menolak menimpa file yang sudah ada.
            session.exec(text("VACUUM INTO :path").bindparams(path=str(target)))  # type: ignore[arg-type]
            session.commit()
    except Exception:
        logger.exception("Backup database gagal")
        return None

    _prune(backup_dir, keep)
    logger.info("Backup dibuat: %s", target.name)
    return target


def _prune(backup_dir: Path, keep: int) -> None:
    files = sorted(backup_dir.glob("finance-*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[max(keep, 1) :]:
        try:
            old.unlink()
            logger.info("Backup lama dihapus: %s", old.name)
        except OSError:
            logger.warning("Tidak bisa menghapus backup lama: %s", old)

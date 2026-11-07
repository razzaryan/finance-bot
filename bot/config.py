"""Konfigurasi dari environment / .env.

Semua validasi dilakukan di sini supaya error muncul saat start,
bukan saat bot sudah jalan.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

TOKEN_RE = re.compile(r"^\d{5,}:[A-Za-z0-9_-]{20,}$")


class ConfigError(RuntimeError):
    """Konfigurasi tidak valid."""


@dataclass(frozen=True)
class Settings:
    bot_token: str
    owner_ids: tuple[int, ...]
    data_dir: Path
    db_path: Path
    export_dir: Path
    timezone: str
    recap_hour: int
    backup_enabled: bool
    backup_keep: int
    debug: bool

    @property
    def owner_id(self) -> int:
        return self.owner_ids[0]


def _parse_owner_ids(raw: str) -> tuple[int, ...]:
    cleaned = raw.replace(";", ",").replace(" ", ",")
    ids: list[int] = []
    for part in cleaned.split(","):
        part = part.strip()
        if not part:
            continue
        if not part.lstrip("-").isdigit():
            raise ConfigError(
                f"TELEGRAM_OWNER_ID berisi nilai tidak valid: {part!r}. "
                "Isi dengan angka user ID Telegram kamu."
            )
        value = int(part)
        if value <= 0:
            raise ConfigError("TELEGRAM_OWNER_ID harus angka positif.")
        if value not in ids:
            ids.append(value)
    if not ids:
        raise ConfigError(
            "TELEGRAM_OWNER_ID wajib diisi. Kirim /start ke bot, lalu buka "
            "https://api.telegram.org/bot<TOKEN>/getUpdates untuk melihat id kamu."
        )
    return tuple(ids)


def load_settings(
    env: dict[str, str] | None = None,
    *,
    env_file: Path | None = None,
) -> Settings:
    """Baca & validasi konfigurasi.

    Args:
        env: mapping pengganti os.environ (dipakai test).
        env_file: path .env yang mau dibaca.
    """
    if env is None:
        env_path = env_file or (PROJECT_ROOT / ".env")
        if env_path.exists():
            load_dotenv(env_path, override=False)
        env = dict(os.environ)

    token = (env.get("BOT_TOKEN") or "").strip()
    if not token:
        raise ConfigError(
            "BOT_TOKEN belum diisi. Salin .env.example menjadi .env lalu isi token dari @BotFather."
        )
    if not TOKEN_RE.match(token):
        raise ConfigError(
            "Format BOT_TOKEN tidak valid. Seharusnya seperti 123456789:AAH... "
            "(angka, titik dua, lalu 20+ karakter)."
        )

    owner_ids = _parse_owner_ids(env.get("TELEGRAM_OWNER_ID", ""))

    tz_name = (env.get("TIMEZONE") or "Asia/Jakarta").strip()
    try:
        ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ConfigError(f"TIMEZONE tidak valid: {tz_name!r}") from exc

    try:
        recap_hour = int(env.get("RECAP_HOUR") or 21)
    except ValueError as exc:
        raise ConfigError("RECAP_HOUR harus angka 0-23 (0 = rekap harian mati).") from exc
    if not 0 <= recap_hour <= 23:
        raise ConfigError("RECAP_HOUR harus angka 0-23 (0 = rekap harian mati).")

    data_dir = Path(env.get("DATA_DIR") or (PROJECT_ROOT / "data")).expanduser()
    if not data_dir.is_absolute():
        data_dir = (PROJECT_ROOT / data_dir).resolve()

    export_dir = data_dir / "exports"
    db_path = Path(env.get("DB_PATH") or (data_dir / "finance.db")).expanduser()
    if not db_path.is_absolute():
        db_path = (PROJECT_ROOT / db_path).resolve()

    try:
        backup_keep = int(env.get("BACKUP_KEEP") or 7)
    except ValueError as exc:
        raise ConfigError("BACKUP_KEEP harus angka.") from exc
    if backup_keep < 1:
        raise ConfigError("BACKUP_KEEP minimal 1.")

    def _flag(name: str, default: str) -> bool:
        return (env.get(name) or default).strip().lower() in {"1", "true", "yes", "on"}

    return Settings(
        bot_token=token,
        owner_ids=owner_ids,
        data_dir=data_dir,
        db_path=db_path,
        export_dir=export_dir,
        timezone=tz_name,
        recap_hour=recap_hour,
        backup_enabled=_flag("BACKUP_ENABLED", "true"),
        backup_keep=backup_keep,
        debug=_flag("DEBUG", "false"),
    )

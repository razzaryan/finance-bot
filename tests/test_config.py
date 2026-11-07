"""Test validasi konfigurasi: pesan error jelas untuk input salah."""

from __future__ import annotations

from pathlib import Path

import pytest

from bot.config import ConfigError, load_settings

GOOD_TOKEN = "123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"


def base(**overrides):
    env = {
        "BOT_TOKEN": GOOD_TOKEN,
        "TELEGRAM_OWNER_ID": "424242",
        "TIMEZONE": "Asia/Jakarta",
        "RECAP_HOUR": "21",
        "DATA_DIR": str(Path("/tmp/finance-test")),
        "BACKUP_KEEP": "7",
    }
    env.update(overrides)
    return env


def test_valid_settings():
    settings = load_settings(base())
    assert settings.bot_token == GOOD_TOKEN
    assert settings.owner_ids == (424242,)
    assert settings.owner_id == 424242
    assert settings.timezone == "Asia/Jakarta"
    assert settings.recap_hour == 21
    assert settings.db_path.name == "finance.db"


def test_multiple_owners():
    settings = load_settings(base(TELEGRAM_OWNER_ID="111, 222;333"))
    assert settings.owner_ids == (111, 222, 333)


def test_missing_token():
    with pytest.raises(ConfigError, match="BOT_TOKEN belum diisi"):
        load_settings(base(BOT_TOKEN=""))


def test_malformed_token():
    with pytest.raises(ConfigError, match="Format BOT_TOKEN"):
        load_settings(base(BOT_TOKEN="bukan-token"))
    with pytest.raises(ConfigError, match="Format BOT_TOKEN"):
        load_settings(base(BOT_TOKEN="123:short"))


def test_missing_owner():
    with pytest.raises(ConfigError, match="TELEGRAM_OWNER_ID wajib"):
        load_settings(base(TELEGRAM_OWNER_ID=""))


def test_owner_not_numeric():
    with pytest.raises(ConfigError, match="tidak valid"):
        load_settings(base(TELEGRAM_OWNER_ID="razz"))


def test_owner_negative():
    with pytest.raises(ConfigError, match="angka positif"):
        load_settings(base(TELEGRAM_OWNER_ID="-5"))


def test_bad_timezone():
    with pytest.raises(ConfigError, match="TIMEZONE tidak valid"):
        load_settings(base(TIMEZONE="Mars/Olympus"))


def test_bad_recap_hour():
    with pytest.raises(ConfigError, match="RECAP_HOUR"):
        load_settings(base(RECAP_HOUR="25"))
    with pytest.raises(ConfigError, match="RECAP_HOUR"):
        load_settings(base(RECAP_HOUR="abc"))


def test_recap_hour_zero_allowed():
    assert load_settings(base(RECAP_HOUR="0")).recap_hour == 0


def test_bad_backup_keep():
    with pytest.raises(ConfigError, match="BACKUP_KEEP"):
        load_settings(base(BACKUP_KEEP="0"))


def test_db_path_absolute():
    settings = load_settings(base(DB_PATH="data/custom.db"))
    assert settings.db_path.is_absolute()
    assert settings.db_path.name == "custom.db"

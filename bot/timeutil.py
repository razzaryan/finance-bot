"""Timezone helpers.

Aturan:
- Database menyimpan *timezone-aware UTC* (SQLModel 0.0.45+ memakai UTCDateTime).
- Semua tampilan/pemasukan tanggal memakai waktu lokal user (naive), lalu
  dikonversi ke UTC saat menyentuh database.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

__all__ = [
    "UTC",
    "add_months",
    "day_bounds",
    "day_label",
    "format_date",
    "format_datetime_local",
    "get_tz",
    "local_naive_to_utc",
    "local_now",
    "month_bounds",
    "month_label",
    "parse_month_arg",
    "utc_to_local_naive",
    "utcnow",
]

MONTH_NAMES = {
    1: "Januari",
    2: "Februari",
    3: "Maret",
    4: "April",
    5: "Mei",
    6: "Juni",
    7: "Juli",
    8: "Agustus",
    9: "September",
    10: "Oktober",
    11: "November",
    12: "Desember",
}

DAY_NAMES = {
    0: "Senin",
    1: "Selasa",
    2: "Rabu",
    3: "Kamis",
    4: "Jumat",
    5: "Sabtu",
    6: "Minggu",
}


def utcnow() -> datetime:
    """Waktu sekarang, aware UTC (format penyimpanan)."""
    return datetime.now(UTC)


def get_tz(tz_name: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name)
    except Exception:  # pragma: no cover - fallback kalau tzdata tidak lengkap
        return ZoneInfo("Asia/Jakarta")


def local_now(tz_name: str) -> datetime:
    """Waktu sekarang dalam *naive* waktu lokal (untuk tampilan & tanggal)."""
    return datetime.now(get_tz(tz_name)).replace(tzinfo=None)


def local_naive_to_utc(dt: datetime, tz_name: str) -> datetime:
    """Naive waktu lokal -> aware UTC. Input aware dipertahankan."""
    if dt.tzinfo is not None:
        return dt.astimezone(UTC)
    return dt.replace(tzinfo=get_tz(tz_name)).astimezone(UTC)


def utc_to_local_naive(dt: datetime, tz_name: str) -> datetime:
    """Aware UTC (atau naive yang dianggap UTC) -> naive waktu lokal."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(get_tz(tz_name)).replace(tzinfo=None)


def month_bounds(year: int, month: int, tz_name: str) -> tuple[datetime, datetime]:
    """Rentang [awal, akhir) satu bulan dalam aware UTC."""
    if not 1 <= month <= 12:
        raise ValueError(f"bulan tidak valid: {month}")
    start_local = datetime(year, month, 1)
    if month == 12:
        end_local = datetime(year + 1, 1, 1)
    else:
        end_local = datetime(year, month + 1, 1)
    return (
        local_naive_to_utc(start_local, tz_name),
        local_naive_to_utc(end_local, tz_name),
    )


def day_bounds(day: date, tz_name: str) -> tuple[datetime, datetime]:
    """Rentang [awal, akhir) satu hari dalam aware UTC."""
    start_local = datetime(day.year, day.month, day.day)
    end_local = start_local + timedelta(days=1)
    return (
        local_naive_to_utc(start_local, tz_name),
        local_naive_to_utc(end_local, tz_name),
    )


def add_months(year: int, month: int, delta: int) -> tuple[int, int]:
    """Geser bulan, mengembalikan (tahun, bulan)."""
    index = (year * 12 + (month - 1)) + delta
    return index // 12, index % 12 + 1


def month_label(year: int, month: int) -> str:
    return f"{MONTH_NAMES[month]} {year}"


def format_date(dt: datetime, tz_name: str) -> str:
    """Format tanggal lokal singkat: '05 Okt 2026'."""
    local = utc_to_local_naive(dt, tz_name)
    return f"{local.day:02d} {MONTH_NAMES[local.month][:3]} {local.year}"


def format_datetime_local(dt: datetime, tz_name: str) -> str:
    local = utc_to_local_naive(dt, tz_name)
    return f"{local.day:02d}/{local.month:02d}/{local.year} {local.hour:02d}:{local.minute:02d}"


def day_label(day: date) -> str:
    return f"{DAY_NAMES[day.weekday()]}, {day.day} {MONTH_NAMES[day.month]} {day.year}"


_MONTH_ARG_RE = re.compile(r"^(\d{4})-(\d{1,2})$")
_MONTH_ONLY_RE = re.compile(r"^(\d{1,2})$")


def parse_month_arg(text: str, today_local: datetime) -> tuple[int, int] | None:
    """Terima '2026-10', 'okt', 'oktober 2026', 'bulan lalu', '10'.

    Mengembalikan (year, month) atau None kalau tidak dikenali.
    """
    raw = (text or "").strip().lower()
    if not raw:
        return today_local.year, today_local.month

    m = _MONTH_ARG_RE.match(raw)
    if m:
        year, month = int(m.group(1)), int(m.group(2))
        if 1 <= month <= 12:
            return year, month
        return None

    # angka polos 1-12 -> bulan di tahun berjalan
    m = _MONTH_ONLY_RE.match(raw)
    if m:
        month = int(m.group(1))
        if 1 <= month <= 12 and 1900 < today_local.year < 2200:
            return today_local.year, month
        return None

    if raw in {"bulan lalu", "lalu"}:
        return add_months(today_local.year, today_local.month, -1)
    if raw in {"bulan ini", "ini"}:
        return today_local.year, today_local.month
    if raw in {"bulan depan", "depan"}:
        return add_months(today_local.year, today_local.month, 1)

    # "oktober" / "okt" / "oktober 2026" / "okt 2025"
    parts = raw.split()
    name_part = parts[0]
    year_part = parts[1] if len(parts) > 1 else None

    matched_month = None
    for num, name in MONTH_NAMES.items():
        lowered = name.lower()
        if name_part == lowered or (len(name_part) >= 3 and lowered.startswith(name_part)):
            matched_month = num
            break
    if matched_month is None:
        return None

    if year_part is None:
        year = today_local.year
    else:
        if not year_part.isdigit() or len(year_part) != 4:
            return None
        year = int(year_part)
    return year, matched_month

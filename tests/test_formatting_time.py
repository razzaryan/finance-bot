"""Test format pesan & timezone."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from bot.formatting import chunk_message, money, percent, progress_bar
from bot.timeutil import (
    UTC,
    add_months,
    day_bounds,
    format_date,
    local_naive_to_utc,
    month_bounds,
    month_label,
    parse_month_arg,
    utc_to_local_naive,
)

FULL = "\u25b0"
EMPTY = "\u25b1"


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        (0, "Rp 0"),
        (1000, "Rp 1.000"),
        (15000, "Rp 15.000"),
        (1_500_000, "Rp 1.500.000"),
        (-25000, "-Rp 25.000"),
        (1_234_567_890, "Rp 1.234.567.890"),
    ],
)
def test_money(amount, expected):
    assert money(amount) == expected


def test_percent():
    assert percent(50, 100) == 50
    assert percent(1, 3) == 33
    assert percent(5, 0) == 0


def test_progress_bar():
    assert progress_bar(0.0) == EMPTY * 10
    assert progress_bar(1.0) == FULL * 10
    assert progress_bar(0.5) == FULL * 5 + EMPTY * 5
    assert len(progress_bar(0.83)) == 10
    # rasio sangat kecil tetap menampilkan satu blok
    assert progress_bar(0.01).startswith(FULL)
    # input di luar rentang dijepit
    assert progress_bar(1.5) == FULL * 10
    assert progress_bar(-1) == EMPTY * 10


def test_chunk_message_short():
    assert chunk_message("halo") == ["halo"]


def test_chunk_message_long():
    text = "\n".join(f"baris {i}" for i in range(500))
    chunks = chunk_message(text, limit=200)
    assert len(chunks) > 1
    assert all(len(c) <= 200 for c in chunks)
    assert "\n".join(chunks).replace("\n", "") == text.replace("\n", "")


def test_month_bounds_utc_conversion():
    start, end = month_bounds(2026, 10, "Asia/Jakarta")
    # 1 Okt 00:00 WIB = 30 Sep 17:00 UTC
    assert start == datetime(2026, 9, 30, 17, 0, tzinfo=UTC)
    assert end == datetime(2026, 10, 31, 17, 0, tzinfo=UTC)


def test_month_bounds_december():
    start, end = month_bounds(2026, 12, "Asia/Jakarta")
    assert start == datetime(2026, 11, 30, 17, 0, tzinfo=UTC)
    assert end == datetime(2026, 12, 31, 17, 0, tzinfo=UTC)


def test_month_bounds_invalid():
    with pytest.raises(ValueError):
        month_bounds(2026, 13, "Asia/Jakarta")


def test_day_bounds():
    start, end = day_bounds(date(2026, 10, 5), "Asia/Jakarta")
    assert start == datetime(2026, 10, 4, 17, 0, tzinfo=UTC)
    assert end == datetime(2026, 10, 5, 17, 0, tzinfo=UTC)


def test_roundtrip_tz():
    local = datetime(2026, 10, 5, 23, 45)
    utc = local_naive_to_utc(local, "Asia/Jakarta")
    assert utc == datetime(2026, 10, 5, 16, 45, tzinfo=UTC)
    assert utc_to_local_naive(utc, "Asia/Jakarta") == local


def test_late_night_local_stays_same_date_visually():
    # 00:30 WIB tgl 6 == 17:30 UTC tgl 5 -> harus tetap tampil tgl 6
    utc = local_naive_to_utc(datetime(2026, 10, 6, 0, 30), "Asia/Jakarta")
    assert utc == datetime(2026, 10, 5, 17, 30, tzinfo=UTC)
    assert format_date(utc, "Asia/Jakarta") == "06 Okt 2026"


def test_utc_to_local_accepts_naive_input():
    naive = datetime(2026, 10, 5, 17, 30)
    assert utc_to_local_naive(naive, "Asia/Jakarta") == datetime(2026, 10, 6, 0, 30)


def test_add_months():
    assert add_months(2026, 1, -1) == (2025, 12)
    assert add_months(2026, 12, 1) == (2027, 1)
    assert add_months(2026, 6, 0) == (2026, 6)


def test_month_label():
    assert month_label(2026, 10) == "Oktober 2026"


@pytest.mark.parametrize(
    ("text", "today", "expected"),
    [
        ("", datetime(2026, 10, 15), (2026, 10)),
        ("2026-10", datetime(2026, 10, 15), (2026, 10)),
        ("2025-3", datetime(2026, 10, 15), (2025, 3)),
        ("oktober", datetime(2026, 10, 15), (2026, 10)),
        ("okt", datetime(2026, 10, 15), (2026, 10)),
        ("agustus 2025", datetime(2026, 10, 15), (2025, 8)),
        ("bulan lalu", datetime(2026, 10, 15), (2026, 9)),
        ("bulan ini", datetime(2026, 10, 15), (2026, 10)),
        ("januari", datetime(2026, 1, 5), (2026, 1)),
        ("bulan lalu", datetime(2026, 1, 5), (2025, 12)),
        ("10", datetime(2026, 5, 15), (2026, 10)),
    ],
)
def test_parse_month_arg_valid(text, today, expected):
    assert parse_month_arg(text, today) == expected


@pytest.mark.parametrize("text", ["2026-13", "kemarin dulu", "bukanbulan", "oktober 26"])
def test_parse_month_arg_invalid(text):
    assert parse_month_arg(text, datetime(2026, 10, 15)) is None

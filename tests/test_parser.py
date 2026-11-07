"""Test parser nominal, tanggal, jenis, dan alur parse_entry."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from bot.models import TYPE_EXPENSE, TYPE_INCOME
from bot.parser import (
    ParseError,
    detect_kind,
    extract_date,
    parse_amount,
    parse_entry,
)

NOW = datetime(2026, 10, 15, 14, 30, 0)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("18000", 18000),
        ("25.000", 25000),
        ("1.500.000", 1500000),
        ("18rb", 18000),
        ("18 rb", 18000),
        ("18ribu", 18000),
        ("18k", 18000),
        ("5jt", 5000000),
        ("5 juta", 5000000),
        ("1,5jt", 1500000),
        ("2.5jt", 2500000),
        ("1,5 jt", 1500000),
        ("10mio", 10000000),
        ("Rp 18.500", 18500),
        ("Rp25.000", 25000),
        ("1.000.000", 1000000),
    ],
)
def test_parse_amount_formats(text, expected):
    assert parse_amount(text) == expected


@pytest.mark.parametrize(
    "text",
    ["", "tidak ada angka", "rb", "jt", "abc", "..", "-", "k"],
)
def test_parse_amount_invalid(text):
    assert parse_amount(text) is None


def test_parse_amount_zero_rejected():
    with pytest.raises(ParseError):
        parse_amount("0")


def test_parse_amount_too_large():
    with pytest.raises(ParseError):
        parse_amount("999999999999999")


def test_parse_entry_kopi():
    result = parse_entry("kopi 18rb", NOW)
    assert result.amount == 18000
    assert "kopi" in result.note
    assert result.occurred_at.date() == date(2026, 10, 15)


def test_parse_entry_suffix_beats_plain_number():
    # '2 kg' angka polos, 25000 angka sebenarnya
    result = parse_entry("beli 2 kg beras 25000", NOW)
    assert result.amount == 25000
    assert "beras" in result.note


def test_parse_entry_suffix_priority_over_larger_plain():
    result = parse_entry("makan 25000 lalu jajan 5rb", NOW)
    assert result.amount == 5000


def test_parse_entry_income_word():
    result = parse_entry("gaji 5jt", NOW)
    assert result.kind_hint == TYPE_INCOME
    assert result.amount == 5000000


def test_parse_entry_expense_word():
    result = parse_entry("bayar listrik 250rb", NOW)
    assert result.kind_hint == TYPE_EXPENSE


def test_parse_entry_sign_prefix():
    assert parse_entry("+500rb dari jual motor", NOW).kind_hint == TYPE_INCOME
    assert parse_entry("-100rb donasi", NOW).kind_hint == TYPE_EXPENSE


def test_parse_entry_category_mention():
    result = parse_entry("makan siang 35k @Makan", NOW)
    assert result.category_hint == "Makan"
    assert result.amount == 35000
    assert "@" not in result.note


def test_parse_entry_yesterday():
    result = parse_entry("kemarin makan 45k", NOW)
    assert result.day == date(2026, 10, 14)
    assert "kemarin" not in result.note.lower()
    assert result.amount == 45000


def test_parse_entry_no_amount_raises():
    with pytest.raises(ParseError):
        parse_entry("cuma teks tanpa nominal", NOW)


def test_parse_entry_empty_raises():
    with pytest.raises(ParseError):
        parse_entry("   ", NOW)


def test_extract_date_explicit_dm():
    found = extract_date("makan 15/10", date(2026, 10, 20))
    assert found is not None
    assert found.day == date(2026, 10, 15)


def test_extract_date_iso():
    found = extract_date("beli 2026-10-02", date(2026, 10, 20))
    assert found is not None
    assert found.day == date(2026, 10, 2)


def test_extract_date_future_rejected():
    assert extract_date("25/12", date(2026, 10, 20)) is None


def test_extract_date_n_days_ago():
    found = extract_date("3 hari lalu beli", date(2026, 10, 20))
    assert found is not None
    assert found.day == date(2026, 10, 17)


def test_extract_date_none():
    assert extract_date("kopi 18rb", date(2026, 10, 20)) is None


def test_detect_kind_ambiguous():
    assert detect_kind("kopi 18rb") is None
    assert detect_kind("gaji 5jt") == TYPE_INCOME
    assert detect_kind("bayar bensin") == TYPE_EXPENSE


@pytest.mark.parametrize(
    "text",
    [
        "terima transfer 200rb dari budi",
        "dapat cashback 15rb",
        "menerima pembayaran 500rb",
        "refund pembelian 100rb",
    ],
)
def test_income_wins_over_expense_word(text):
    """Uang masuk tidak boleh tercatat sebagai pengeluaran."""
    assert detect_kind(text) == TYPE_INCOME


@pytest.mark.parametrize(
    "text",
    [
        "transfer ke budi 100rb",
        "bayar cicilan 850rb",
        "beli pulsa 25rb",
        "topup gojek 50rb",
    ],
)
def test_true_expenses_stay_expenses(text):
    assert detect_kind(text) == TYPE_EXPENSE


def test_parse_entry_default_kind_used():
    result = parse_entry("18rb", NOW, default_kind=TYPE_INCOME)
    assert result.kind_hint == TYPE_INCOME


def test_parse_entry_time_preserved():
    result = parse_entry("kopi 18rb", NOW)
    assert result.occurred_at.hour == 14
    assert result.occurred_at.minute == 30

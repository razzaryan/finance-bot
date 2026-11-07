"""Test ledger: transaksi, agregasi, laporan, anggaran, export."""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlmodel import Session

from bot.db import create_db_engine, init_db
from bot.ledger import (
    LedgerError,
    add_transaction,
    budget_status,
    category_breakdown,
    count_transactions,
    create_category,
    delete_category,
    delete_transaction,
    export_csv,
    fallback_category,
    find_category,
    get_default_account,
    get_totals,
    last_transaction,
    month_summary,
    search_transactions,
    set_budget,
    total_balance,
    transactions_in_range,
)
from bot.models import TYPE_EXPENSE, TYPE_INCOME
from bot.services_defaults import ensure_user
from bot.timeutil import local_naive_to_utc, month_bounds


@pytest.fixture()
def engine():
    eng = create_db_engine(":memory:")
    init_db(eng)
    return eng


@pytest.fixture()
def session(engine):
    with Session(engine) as sess:
        yield sess


@pytest.fixture()
def user(session):
    user, created = ensure_user(session, 123456, "Razz")
    assert created is True
    return user


def make_tx(session, user, amount, kind, category_name, when, note="", message_id=None):
    category = find_category(session, user.id, category_name, kind)
    assert category is not None, f"kategori {category_name} tidak ada"
    account = get_default_account(session, user.id)
    return add_transaction(
        session,
        user,
        kind=kind,
        amount=amount,
        category=category,
        account=account,
        note=note,
        occurred_at=when,
        message_id=message_id,
    )


def test_ensure_user_seeds_defaults(session, user):
    from bot.ledger import list_categories

    cats = list_categories(session, user.id)
    assert len(cats) >= 15
    assert any(c.name == "Makan" and c.kind == TYPE_EXPENSE for c in cats)
    assert any(c.name == "Gaji" and c.kind == TYPE_INCOME for c in cats)


def test_ensure_user_is_idempotent(session, user):
    from bot.services_defaults import ensure_user as eu

    again, created = eu(session, 123456, "Razz")
    assert created is False
    assert again.id == user.id


def test_add_and_totals(session, user):
    when = local_naive_to_utc(datetime(2026, 10, 5, 12, 0), user.timezone)
    make_tx(session, user, 50_000, TYPE_EXPENSE, "Makan", when, "makan siang")
    make_tx(session, user, 5_000_000, TYPE_INCOME, "Gaji", when, "gaji okt")

    income, expense = get_totals(session, user.id)
    assert income == 5_000_000
    assert expense == 50_000
    assert total_balance(session, user) == 4_950_000


def test_message_id_prevents_duplicate(session, user):
    when = local_naive_to_utc(datetime(2026, 10, 5, 12, 0), user.timezone)
    first = make_tx(session, user, 20_000, TYPE_EXPENSE, "Makan", when, "kopi", message_id=999)
    second = make_tx(session, user, 20_000, TYPE_EXPENSE, "Makan", when, "kopi", message_id=999)

    assert first.created is True
    assert second.created is False
    assert second.duplicate is True
    assert second.transaction.id == first.transaction.id
    assert count_transactions(session, user.id) == 1


def test_amount_must_be_positive(session, user):
    when = local_naive_to_utc(datetime(2026, 10, 5), user.timezone)
    with pytest.raises(LedgerError):
        make_tx(session, user, 0, TYPE_EXPENSE, "Makan", when)


def at_month_start(year, month, hour, user, day=1):
    """Naive lokal jam tertentu pada bulan tertentu, lalu -> aware UTC."""
    start, _ = month_bounds(year, month, user.timezone)
    # start adalah UTC; geser ke jam lokal yang diinginkan lewat helper.
    from bot.timeutil import local_naive_to_utc

    return local_naive_to_utc(datetime(year, month, day, hour, 0), user.timezone)


def test_month_summary_and_breakdown(session, user):
    start, end = month_bounds(2026, 10, user.timezone)
    when = at_month_start(2026, 10, 10, user)
    make_tx(session, user, 100_000, TYPE_EXPENSE, "Makan", when, "a")
    make_tx(session, user, 50_000, TYPE_EXPENSE, "Makan", when, "b")
    make_tx(session, user, 300_000, TYPE_EXPENSE, "Transport", when, "c")
    make_tx(session, user, 7_000_000, TYPE_INCOME, "Gaji", when, "d")

    summary = month_summary(session, user, 2026, 10)
    assert summary.income == 7_000_000
    assert summary.expense == 450_000
    assert summary.tx_count == 4
    assert summary.top_expense[0][1] == "Transport"
    assert summary.top_expense[0][2] == 300_000
    assert summary.top_expense[1][1] == "Makan"
    assert summary.top_expense[1][2] == 150_000

    breakdown = category_breakdown(session, user.id, start, end, TYPE_EXPENSE)
    assert sum(total for _, _, total in breakdown) == 450_000


def test_month_summary_previous_month(session, user):
    sep_when = at_month_start(2026, 9, 9, user)
    oct_when = at_month_start(2026, 10, 9, user)
    make_tx(session, user, 200_000, TYPE_EXPENSE, "Makan", sep_when, "sep")
    make_tx(session, user, 100_000, TYPE_EXPENSE, "Makan", oct_when, "okt")

    summary = month_summary(session, user, 2026, 10)
    assert summary.prev_expense == 200_000
    assert summary.expense == 100_000


def test_month_isolation(session, user):
    make_tx(session, user, 111_000, TYPE_EXPENSE, "Makan", at_month_start(2026, 9, 9, user), "sep")
    make_tx(session, user, 222_000, TYPE_EXPENSE, "Makan", at_month_start(2026, 10, 9, user), "okt")

    income, expense = get_totals(session, user.id, *month_bounds(2026, 10, user.timezone))
    assert expense == 222_000


def test_delete_and_last(session, user):
    when = local_naive_to_utc(datetime(2026, 10, 5), user.timezone)
    make_tx(session, user, 10_000, TYPE_EXPENSE, "Makan", when, "a")
    second = make_tx(session, user, 20_000, TYPE_EXPENSE, "Makan", when, "b")

    last = last_transaction(session, user.id)
    assert last is not None
    assert last.amount == 20_000
    assert last.id == second.transaction.id

    delete_transaction(session, user.id, last.id)
    assert count_transactions(session, user.id) == 1

    with pytest.raises(LedgerError):
        delete_transaction(session, user.id, 99999)


def test_delete_other_users_transaction_blocked(session, user):
    from bot.services_defaults import ensure_user as eu

    other, _ = eu(session, 777777, "Other")
    when = local_naive_to_utc(datetime(2026, 10, 5), user.timezone)
    added = make_tx(session, user, 10_000, TYPE_EXPENSE, "Makan", when, "a")

    with pytest.raises(LedgerError):
        delete_transaction(session, other.id, added.transaction.id)


def test_transactions_in_range_excludes_boundaries(session, user):
    start, end = month_bounds(2026, 10, user.timezone)
    make_tx(session, user, 1_000, TYPE_EXPENSE, "Makan", start, "awal")
    make_tx(session, user, 2_000, TYPE_EXPENSE, "Makan", end.replace(minute=0, second=0), "next-month")

    rows = transactions_in_range(session, user.id, start, end)
    assert len(rows) == 1
    assert rows[0][0].amount == 1_000


def test_search_transactions_escapes_wildcards(session, user):
    when = local_naive_to_utc(datetime(2026, 10, 5), user.timezone)
    make_tx(session, user, 10_000, TYPE_EXPENSE, "Makan", when, "kopi susu")
    make_tx(session, user, 10_000, TYPE_EXPENSE, "Makan", when, "100% gula")

    assert len(search_transactions(session, user.id, "kopi")) == 1
    assert len(search_transactions(session, user.id, "100%")) == 1
    assert len(search_transactions(session, user.id, "%")) == 1


def test_fallback_category_created_once(session, user):
    first = fallback_category(session, user, TYPE_EXPENSE)
    second = fallback_category(session, user, TYPE_EXPENSE)
    assert first.id == second.id
    assert first.name == "Lain-lain"


def test_create_category_duplicate_rejected(session, user):
    create_category(session, user, "Kopi", TYPE_EXPENSE, "kopi,latte", "☕")
    with pytest.raises(LedgerError):
        create_category(session, user, "Kopi", TYPE_EXPENSE)


def test_delete_category_in_use_blocked(session, user):
    when = local_naive_to_utc(datetime(2026, 10, 5), user.timezone)
    make_tx(session, user, 10_000, TYPE_EXPENSE, "Makan", when, "a")
    with pytest.raises(LedgerError):
        delete_category(session, user, "Makan")


def test_budget_flow(session, user):
    category = find_category(session, user.id, "Makan", TYPE_EXPENSE)
    make_tx(session, user, 900_000, TYPE_EXPENSE, "Makan", at_month_start(2026, 10, 9, user), "a")

    set_budget(session, user, category, 1_000_000)
    rows = budget_status(session, user, 2026, 10)
    assert len(rows) == 1
    assert rows[0][1] == 1_000_000
    assert rows[0][2] == 900_000

    set_budget(session, user, category, 0)
    assert budget_status(session, user, 2026, 10) == []


def test_budget_rejects_income_category(session, user):
    category = find_category(session, user.id, "Gaji", TYPE_INCOME)
    with pytest.raises(LedgerError):
        set_budget(session, user, category, 100_000)


def test_export_csv(session, user):
    when = local_naive_to_utc(datetime(2026, 10, 5, 9, 15), user.timezone)
    make_tx(session, user, 25_000, TYPE_EXPENSE, "Makan", when, "kopi pagi")
    make_tx(session, user, 5_000_000, TYPE_INCOME, "Gaji", when, "gaji")

    data, count = export_csv(session, user, *month_bounds(2026, 10, user.timezone))
    assert count == 2
    text = data.decode("utf-8-sig")
    assert "kopi pagi" in text
    assert "25000" in text
    assert "Makan" in text
    assert text.splitlines()[0].startswith("id,tanggal,jenis")


def test_amounts_are_integers(session, user):
    when = local_naive_to_utc(datetime(2026, 10, 5), user.timezone)
    added = make_tx(session, user, 12_345, TYPE_EXPENSE, "Makan", when, "x")
    assert isinstance(added.transaction.amount, int)

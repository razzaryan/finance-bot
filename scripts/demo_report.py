"""Smoke test manual: cetak contoh output laporan (tanpa Telegram)."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session

from bot.db import create_db_engine, init_db
from bot.formatting import report_text
from bot.ledger import (
    add_transaction,
    budget_status,
    comparison_text,
    find_category,
    get_default_account,
    month_summary,
    set_budget,
)
from bot.services_defaults import ensure_user
from bot.timeutil import local_naive_to_utc, month_label


def main() -> None:
    # Windows console default cp1252 tidak bisa cetak emoji.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    engine = create_db_engine(":memory:")
    init_db(engine)
    with Session(engine) as session:
        user, _ = ensure_user(session, 1, "Razz")
        account = get_default_account(session, user.id)
        tz = user.timezone

        rows = [
            ("2026-09-15", 8_500_000, "income", "Gaji", "gaji september"),
            ("2026-09-16", 3_100_000, "expense", "Makan", "makan sebulan"),
            ("2026-09-20", 900_000, "expense", "Transport", "bensin + servis"),
            ("2026-10-01", 7_500_000, "income", "Gaji", "gaji oktober"),
            ("2026-10-02", 1_800_000, "expense", "Makan", "makan harian"),
            ("2026-10-05", 750_000, "expense", "Transport", "bensin"),
            ("2026-10-08", 620_000, "expense", "Belanja", "sembako"),
            ("2026-10-10", 450_000, "expense", "Tagihan", "listrik & internet"),
            ("2026-10-12", 250_000, "expense", "Hiburan", "nonton"),
            ("2026-10-14", 400_000, "income", "Freelance", "proyek kecil"),
        ]
        for when, amount, kind, cat, note in rows:
            category = find_category(session, user.id, cat, kind)
            dt = datetime.strptime(when, "%Y-%m-%d")
            add_transaction(
                session,
                user,
                kind=kind,
                amount=amount,
                category=category,
                account=account,
                note=note,
                occurred_at=local_naive_to_utc(dt, tz),
            )

        set_budget(session, user, find_category(session, user.id, "Makan", "expense"), 2_000_000)

        summary = month_summary(session, user, 2026, 10)
        print("=" * 52)
        print(
            report_text(
                tz_name=tz,
                title=f"Laporan {month_label(2026, 10)}",
                income=summary.income,
                expense=summary.expense,
                top_expense=summary.top_expense,
                top_income=summary.top_income,
                tx_count=summary.tx_count,
                comparison=comparison_text(summary.expense, summary.prev_expense),
            )
        )
        print("=" * 52)
        total = summary.income - summary.expense
        print(f"Cek aritmetika: {summary.income} - {summary.expense} = {total}")
        assert total == 7_900_000 - 3_870_000, total

        print("=" * 52)
        for category, limit, used in budget_status(session, user, 2026, 10):
            print(f"Budget {category.name}: {used}/{limit} ({used/limit:.0%})")

        # panjang pesan harus di bawah limit Telegram
        longest = report_text(
            tz_name=tz,
            title="Tes",
            income=1,
            expense=1,
            top_expense=[("🍜", "Panjang" * 10, 1)] * 5,
            top_income=[("💼", "Sumber" * 10, 1)] * 5,
            tx_count=1,
        )
        print(f"Panjang contoh laporan: {len(longest)} char (limit 4096)")
        assert len(longest) < 4096


if __name__ == "__main__":
    main()

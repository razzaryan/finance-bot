"""/saldo, /laporan, /terakhir, /cari, /rekap, /export, /csv, /histori."""

from __future__ import annotations

import logging

from aiogram import Bot, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import BufferedInputFile, Message

from bot.formatting import (
    answer_chunked,
    category_name,
    chunk_message,
    day_label,
    esc,
    money,
    progress_bar,
    report_text,
    signed_money,
)
from bot.ledger import (
    account_balance,
    budget_status,
    comparison_text,
    count_transactions,
    daily_summary,
    export_csv,
    get_totals,
    list_accounts,
    month_summary,
    monthly_history,
    recent_transactions,
    search_transactions,
    total_balance,
)
from bot.timeutil import format_date, local_now, month_bounds, month_label, parse_month_arg

logger = logging.getLogger(__name__)


def register(router: Router) -> None:
    @router.message(Command("saldo", "balance", "s"))
    async def cmd_saldo(message: Message, ctx) -> None:
        user = ctx.user
        now = local_now(user.timezone)
        start, end = month_bounds(now.year, now.month, user.timezone)

        total = total_balance(ctx.session, user)
        income, expense = get_totals(ctx.session, user.id, start, end)
        accounts = list_accounts(ctx.session, user.id)

        lines = ["💰 <b>Saldo</b>", "━" * 18, f"<b>{money(total)}</b>", ""]
        if len(accounts) > 1:
            for account in accounts:
                lines.append(
                    f"• {esc(account.name)}: {money(account_balance(ctx.session, user, account))}"
                )
            lines.append("")

        lines += [
            f"📅 <b>{esc(month_label(now.year, now.month))}</b>",
            f"Masuk   {money(income)}",
            f"Keluar  {money(expense)}",
            f"Selisih {money(income - expense)}",
            "",
            f"Total {count_transactions(ctx.session, user.id)} transaksi tercatat.",
        ]
        await answer_chunked(message, "\n".join(lines))

    @router.message(Command("laporan", "report", "l"))
    async def cmd_laporan(message: Message, command: CommandObject, ctx) -> None:
        user = ctx.user
        now = local_now(user.timezone)
        parsed = parse_month_arg((command.args or "").strip(), now)
        if parsed is None:
            await message.answer(
                "Format bulan tidak dikenali.\n"
                "Contoh: <code>/laporan</code>, <code>/laporan 2026-10</code>, "
                "<code>/laporan september</code>, <code>/laporan bulan lalu</code>"
            )
            return

        year, month = parsed
        summary = month_summary(ctx.session, user, year, month, tz_name=user.timezone)

        if summary.tx_count == 0:
            await message.answer(
                f"📊 <b>{esc(month_label(year, month))}</b>\n"
                "Belum ada transaksi di bulan ini.\n\n"
                "Kirim misalnya: <code>kopi 18rb</code>"
            )
            return

        text = report_text(
            tz_name=user.timezone,
            title=f"Laporan {month_label(year, month)}",
            income=summary.income,
            expense=summary.expense,
            top_expense=summary.top_expense,
            top_income=summary.top_income,
            tx_count=summary.tx_count,
            comparison=comparison_text(summary.expense, summary.prev_expense),
        )
        await answer_chunked(message, text)

    @router.message(Command("rekap", "hari"))
    async def cmd_rekap(message: Message, ctx) -> None:
        user = ctx.user
        today = local_now(user.timezone).date()
        income, expense, items = daily_summary(ctx.session, user, today, tz_name=user.timezone)

        lines = [
            f"🧾 <b>Rekap {esc(day_label(today))}</b>",
            "━" * 18,
            f"Masuk   {money(income)}",
            f"Keluar  {money(expense)}",
            f"Selisih {money(income - expense)}",
        ]

        if items:
            lines.append("")
            for trx, category in items:
                note = (trx.note or "").strip() or "(tanpa catatan)"
                cat = category_name(category) if category else "Tanpa Kategori"
                lines.append(
                    f"• {esc(note)} — {signed_money(trx.amount, trx.kind)} <i>({esc(cat)})</i>"
                )
        else:
            lines += ["", "Belum ada transaksi hari ini."]

        alerts = []
        for category, limit, used in budget_status(
            ctx.session, user, today.year, today.month, tz_name=user.timezone
        ):
            if limit <= 0:
                continue
            ratio = used / limit
            if ratio >= 0.8:
                icon = "🚨" if ratio >= 1 else "⚠️"
                alerts.append(
                    f"{icon} {esc(category_name(category))} {progress_bar(ratio)} "
                    f"{money(used)}/{money(limit)}"
                )
        if alerts:
            lines += [""] + alerts

        await answer_chunked(message, "\n".join(lines))

    @router.message(Command("terakhir", "last", "riwayat"))
    async def cmd_terakhir(message: Message, command: CommandObject, ctx) -> None:
        user = ctx.user
        raw = (command.args or "").strip()
        limit = int(raw) if raw.isdigit() else 10
        limit = max(1, min(limit, 30))

        items = recent_transactions(ctx.session, user.id, limit)
        if not items:
            await message.answer("Belum ada transaksi. Mulai dengan <code>kopi 18rb</code> 🙂")
            return

        lines = [f"🧾 <b>{len(items)} transaksi terakhir</b>", "━" * 18]
        for trx, category in items:
            note = (trx.note or "").strip() or "(tanpa catatan)"
            cat = category_name(category) if category else "Tanpa Kategori"
            lines.append(
                f"{signed_money(trx.amount, trx.kind)} · {esc(note)}\n"
                f"   {esc(cat)} · {esc(format_date(trx.occurred_at, user.timezone))} · "
                f"<code>#{trx.id}</code>"
            )
        lines += ["", "Hapus dengan <code>/hapus &lt;id&gt;</code> atau /undo untuk yang terakhir."]

        for chunk in chunk_message("\n".join(lines)):
            await message.answer(chunk)

    @router.message(Command("cari", "search", "find"))
    async def cmd_cari(message: Message, command: CommandObject, ctx) -> None:
        user = ctx.user
        keyword = (command.args or "").strip()
        if not keyword:
            await message.answer("Format: <code>/cari kopi</code>")
            return

        items = search_transactions(ctx.session, user.id, keyword)
        if not items:
            await message.answer(
                f"Tidak ditemukan transaksi dengan catatan mengandung '{esc(keyword)}'."
            )
            return

        total = sum(trx.amount for trx, _ in items)
        lines = [
            f"🔍 <b>Hasil cari '{esc(keyword)}'</b> (maks 15)",
            "━" * 18,
        ]
        for trx, category in items:
            note = (trx.note or "").strip() or "(tanpa catatan)"
            cat = category_name(category) if category else "Tanpa Kategori"
            lines.append(
                f"{signed_money(trx.amount, trx.kind)} · {esc(note)}\n"
                f"   {esc(cat)} · {esc(format_date(trx.occurred_at, user.timezone))} · "
                f"<code>#{trx.id}</code>"
            )
        lines += ["", f"Total nilai hasil: {money(total)}"]

        for chunk in chunk_message("\n".join(lines)):
            await message.answer(chunk)

    @router.message(Command("export", "csv"))
    async def cmd_export(message: Message, command: CommandObject, bot: Bot, ctx) -> None:
        user = ctx.user
        now = local_now(user.timezone)
        parsed = parse_month_arg((command.args or "").strip(), now)
        if parsed is None:
            await message.answer(
                "Format: <code>/export 2026-10</code> atau <code>/export</code> untuk bulan ini."
            )
            return

        year, month = parsed
        start, end = month_bounds(year, month, user.timezone)
        data, count = export_csv(ctx.session, user, start, end)

        if count == 0:
            await message.answer(f"Tidak ada transaksi di {month_label(year, month)} untuk diexport.")
            return

        await message.answer_document(
            BufferedInputFile(data, filename=f"keuangan-{year}-{month:02d}.csv"),
            caption=f"📄 {count} transaksi — {month_label(year, month)}\nBuka dengan Excel/Google Sheets.",
        )

    @router.message(Command("ledger", "buku", "allcsv"))
    async def cmd_ledger(message: Message, bot: Bot, ctx) -> None:
        """Kirim file CSV lengkap (semua transaksi, selalu ter-update otomatis)."""
        from bot.csvsync import rewrite_ledger

        user = ctx.user
        path = ctx.ledger_file()

        # Bangun ulang dari DB supaya file pasti sinkron dengan data sebenarnya.
        if path is not None:
            count = rewrite_ledger(path, ctx.session, user)
        else:
            count = 0

        if count == 0:
            await message.answer(
                "Belum ada transaksi. File CSV akan terisi otomatis setelah kamu mencatat."
            )
            return

        data = path.read_bytes()
        await message.answer_document(
            BufferedInputFile(data, filename=f"ledger-{user.telegram_id}.csv"),
            caption=(
                f"📒 {count} transaksi (semua waktu)\n"
                "File ini juga tersimpan di folder <code>data/exports/</code> "
                "dan diperbarui otomatis setiap ada transaksi baru."
            ),
        )

    @router.message(Command("histori", "riwayat_bulan"))
    async def cmd_history(message: Message, ctx) -> None:
        items = monthly_history(ctx.session, ctx.user, 6, tz_name=ctx.user.timezone)
        lines = ["📈 <b>6 bulan terakhir</b>", "━" * 18]
        for label, income, expense in items:
            lines.append(f"<b>{esc(label)}</b>\n  masuk {money(income)} · keluar {money(expense)}")
        await answer_chunked(message, "\n".join(lines))

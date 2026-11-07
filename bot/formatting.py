"""Format angka & pesan Telegram (HTML)."""

from __future__ import annotations

import html
import re

from bot.models import TYPE_INCOME
from bot.timeutil import (
    DAY_NAMES,
    MONTH_NAMES,
    format_datetime_local,
    utc_to_local_naive,
)

TELEGRAM_LIMIT = 4096
SAFE_LIMIT = 3800

BAR_FULL = "▰"
BAR_EMPTY = "▱"


def money(amount: int) -> str:
    """1500000 -> 'Rp 1.500.000'."""
    sign = "-" if amount < 0 else ""
    return f"{sign}Rp {abs(int(amount)):,}".replace(",", ".")


def signed_money(amount: int, kind: str) -> str:
    prefix = "+" if kind == TYPE_INCOME else "-"
    return f"{prefix}{money(amount)}"


def esc(text: str) -> str:
    return html.escape(text or "", quote=False)


def escape_html(text: str) -> str:
    return esc(text)


def progress_bar(ratio: float, width: int = 10) -> str:
    ratio = max(0.0, min(1.0, ratio))
    filled = int(round(ratio * width))
    if filled == 0 and ratio > 0:
        filled = 1
    return BAR_FULL * filled + BAR_EMPTY * (width - filled)


def percent(part: int, whole: int) -> int:
    if whole <= 0:
        return 0
    return int(round(part / whole * 100))


def category_name(category) -> str:
    emoji = (getattr(category, "emoji", "") or "").strip()
    name = getattr(category, "name", "") or "Tanpa Kategori"
    return f"{emoji} {name}".strip()


def chunk_message(text: str, limit: int = SAFE_LIMIT) -> list[str]:
    """Potong pesan panjang tanpa memotong tag HTML di tengah."""
    text = text or ""
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    current: list[str] = []
    length = 0

    for line in text.split("\n"):
        # baris tunggal kepanjangan -> potong paksa
        while len(line) > limit:
            head, line = line[:limit], line[limit:]
            if current:
                chunks.append("\n".join(current))
                current, length = [], 0
            chunks.append(head)

        addition = len(line) + (1 if current else 0)
        if length + addition > limit:
            chunks.append("\n".join(current))
            current, length = [line], len(line)
        else:
            current.append(line)
            length += addition

    if current:
        chunks.append("\n".join(current))
    return chunks


def transaction_line(trx, category, tz_name: str, show_date: bool = False) -> str:
    """Satu baris transaksi untuk daftar."""
    when = format_datetime_local(trx.occurred_at, tz_name) if show_date else ""
    note = (trx.note or "").strip() or "(tanpa catatan)"
    cat = category_name(category) if category is not None else "📦 Tanpa Kategori"
    date_part = f" · {when}" if when else ""
    return (
        f"{cat} — {esc(note)}\n"
        f"   {signed_money(trx.amount, trx.kind)} · <code>#{trx.id}</code>{date_part}"
    )


def report_text(
    *,
    tz_name: str,
    title: str,
    income: int,
    expense: int,
    top_expense: list[tuple[str, str, int]],
    top_income: list[tuple[str, str, int]],
    tx_count: int,
    comparison: str | None = None,
) -> str:
    balance = income - expense
    lines = [
        f"📊 <b>{esc(title)}</b>",
        "━━━━━━━━━━━━━━━━━━",
        f"Masuk   {money(income)}",
        f"Keluar  {money(expense)}",
        f"<b>Sisa    {money(balance)}</b>",
        "━━━━━━━━━━━━━━━━━━",
    ]

    if top_expense:
        lines.append("🔴 <b>Pengeluaran terbesar</b>")
        for emoji, name, total in top_expense:
            label = f"{emoji} {name}".strip()
            lines.append(
                f"• {esc(label)} — {money(total)} ({percent(total, expense)}%)"
            )
    else:
        lines.append("Belum ada pengeluaran di periode ini.")

    if top_income:
        lines.append("")
        lines.append("🟢 <b>Sumber pemasukan</b>")
        for emoji, name, total in top_income:
            label = f"{emoji} {name}".strip()
            lines.append(
                f"• {esc(label)} — {money(total)} ({percent(total, income)}%)"
            )

    lines.append("")
    lines.append(f"📝 {tx_count} transaksi")
    if comparison:
        lines.append(comparison)
    return "\n".join(lines)


def day_label(day) -> str:
    return f"{DAY_NAMES[day.weekday()]}, {day.day} {MONTH_NAMES[day.month]} {day.year}"


def recap_text(
    *,
    tz_name: str,
    day_label_text: str,
    income: int,
    expense: int,
    transactions: list[tuple[object, object]],
    budget_alerts: list[str],
) -> str:
    lines = [
        f"🧾 <b>Rekap {esc(day_label_text)}</b>",
        "━━━━━━━━━━━━━━━━━━",
        f"Masuk   {money(income)}",
        f"Keluar  {money(expense)}",
        f"Sisa harian {money(income - expense)}",
    ]
    if transactions:
        lines.append("")
        for trx, category in transactions:
            note = (trx.note or "").strip() or "(tanpa catatan)"
            cat = category_name(category) if category else "📦 Tanpa Kategori"
            lines.append(f"• {esc(note)} — {money(trx.amount)} <i>({esc(cat)})</i>")
    if budget_alerts:
        lines.append("")
        for alert in budget_alerts:
            lines.append(alert)
    return "\n".join(lines)


def recent_month_summary(items: list[tuple[str, int, int]]) -> str:
    """items: (label bulan, income, expense)."""
    if not items:
        return "Belum ada data."
    lines = []
    for label, income, expense in items:
        lines.append(f"{esc(label)}: masuk {money(income)} · keluar {money(expense)}")
    return "\n".join(lines)


def local_hhmm(trx, tz_name: str) -> str:
    local = utc_to_local_naive(trx.occurred_at, tz_name)
    return f"{local.hour:02d}:{local.minute:02d}"


_TAG_RE = re.compile(r"</?[a-zA-Z][^>]*>")


def plain(text: str) -> str:
    """Buang tag HTML, untuk keperluan CSV/log."""
    return html.unescape(_TAG_RE.sub("", text))

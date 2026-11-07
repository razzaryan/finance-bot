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


_TAG_TOKEN_RE = re.compile(r"<(/?)([a-zA-Z][\w-]*)([^>]*)>")
_VOID_TAGS = {"br"}


def _split_html_line(line: str, limit: int) -> list[str]:
    """Pecah satu baris panjang tanpa merusak tag HTML.

    Tag yang masih terbuka di akhir potongan otomatis ditutup, lalu dibuka
    kembali di potongan berikutnya. Hasilnya selalu HTML valid dan setiap
    potongan <= limit.
    """
    if len(line) <= limit:
        return [line]

    pieces: list[str] = []
    stack: list[str] = []          # tag yang sedang terbuka
    buf: list[str] = []
    buf_len = 0

    def closers() -> str:
        return "".join(f"</{t}>" for t in reversed(stack))

    def openers() -> str:
        return "".join(f"<{t}>" for t in stack)

    def flush() -> None:
        """Tutup potongan sekarang, mulai potongan baru dengan tag yang sama."""
        nonlocal buf, buf_len
        payload = "".join(buf)
        tail = closers()
        if len(payload) + len(tail) <= limit:
            payload += tail
        elif payload:
            pieces.append(payload)
            payload = ""
        if payload:
            pieces.append(payload)
        buf = [openers()]
        buf_len = len(buf[0])

    def add_text(text: str) -> None:
        """Tambahkan teks polos, dipecah bila tidak muat."""
        nonlocal buf_len
        while text:
            room = limit - buf_len - len(closers())
            if room <= 0:
                flush()
                continue
            take = text[:room]
            buf.append(take)
            buf_len += len(take)
            text = text[room:]

    pos = 0
    while pos < len(line):
        match = _TAG_TOKEN_RE.search(line, pos)

        if match is None:
            add_text(line[pos:])
            break

        add_text(line[pos : match.start()])

        raw_tag = match.group(0)
        closing = match.group(1) == "/"
        name = match.group(2).lower()

        # tag mentah harus ikut masuk. Kalau tidak muat, potong dulu.
        if buf_len + len(raw_tag) + len(closers()) > limit and buf_len > len(openers()):
            flush()

        buf.append(raw_tag)
        buf_len += len(raw_tag)

        if not closing and name not in _VOID_TAGS:
            stack.append(name)
        elif closing and stack and stack[-1] == name:
            stack.pop()

        pos = match.end()

    if buf:
        payload = "".join(buf)
        tail = closers()
        if len(payload) + len(tail) <= limit:
            payload += tail
        if payload:
            pieces.append(payload)

    return [p for p in pieces if p]


def chunk_message(text: str, limit: int = SAFE_LIMIT) -> list[str]:
    """Potong pesan panjang jadi <= limit char, HTML tetap valid.

    Setiap potongan boleh dibaca Telegram sendiri-sendiri: tag yang terbuka
    ditutup di akhir potongan dan dibuka lagi di awal potongan berikutnya.
    """
    text = text or ""
    if len(text) <= limit:
        return [text] if text else [""]

    chunks: list[str] = []
    current: list[str] = []
    length = 0

    for line in text.split("\n"):
        if len(line) > limit:
            if current:
                chunks.append("\n".join(current))
                current, length = [], 0
            chunks.extend(_split_html_line(line, limit))
            continue

        addition = len(line) + (1 if current else 0)
        if length + addition > limit:
            chunks.append("\n".join(current))
            current, length = [line], len(line)
        else:
            current.append(line)
            length += addition

    if current:
        chunks.append("\n".join(current))
    return [c for c in chunks if c]


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


async def answer_chunked(message, text: str, limit: int = SAFE_LIMIT) -> None:
    """Kirim pesan, dipecah otomatis kalau melebihi batas Telegram.

    Semua handler wajib lewat sini supaya pesan panjang tidak ditolak
    Telegram (gejalanya: bot diam saja tanpa error yang terlihat).
    """
    for chunk in chunk_message(text, limit):
        if chunk:
            await message.answer(chunk)

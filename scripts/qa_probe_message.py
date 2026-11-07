"""PROBE PESAN TELEGRAM - hal yang bikin bot diam / error di produksi.

Telegram menolak pesan dengan HTML rusak ("can't parse entities") atau
>4096 karakter. Keduanya menyebabkan bot tidak membalas sama sekali.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from bot.formatting import (
    chunk_message,
    esc,
    money,
    progress_bar,
    report_text,
)

findings: list[str] = []


def bug(label: str, detail: str = "") -> None:
    findings.append(f"{label} :: {detail}")
    print(f"  BUG  {label}  {detail}")


def ok(label: str) -> None:
    print(f"  ok   {label}")


TAG_RE = re.compile(r"<(/?)([a-zA-Z][\w-]*)[^>]*>")
ALLOWED = {"b", "i", "u", "s", "code", "pre", "a", "tg-spoiler", "em", "strong", "blockquote"}


def html_valid(text: str) -> tuple[bool, str]:
    """Validasi sederhana: tag seimbang dan hanya tag yang didukung Telegram."""
    stack: list[str] = []
    pos = 0
    for m in TAG_RE.finditer(text):
        # pastikan tidak ada '<' atau '>' liar di luar tag
        between = text[pos : m.start()]
        if "<" in between or ">" in between:
            return False, f"karakter < atau > liar di {between[:40]!r}"
        pos = m.end()
        closing, name = m.group(1) == "/", m.group(2).lower()
        if name not in ALLOWED:
            return False, f"tag tidak didukung: <{name}>"
        if closing:
            if not stack or stack[-1] != name:
                return False, f"penutup </{name}> tidak cocok, stack={stack}"
            stack.pop()
        else:
            stack.append(name)
    tail = text[pos:]
    if "<" in tail or ">" in tail:
        return False, f"karakter < atau > liar di akhir: {tail[:40]!r}"
    if stack:
        return False, f"tag tidak ditutup: {stack}"
    return True, ""


# ============================================================
print("\n=== A. VALIDASI HTML PADA OUTPUT NYATA ===")
# ============================================================
real_outputs = {
    "laporan": report_text(
        tz_name="Asia/Jakarta",
        title="Laporan Oktober 2026",
        income=7_900_000,
        expense=3_870_000,
        top_expense=[("🍜", "Makan", 1_800_000), ("🛵", "Transport", 750_000)],
        top_income=[("💼", "Gaji", 7_500_000)],
        tx_count=7,
        comparison="vs bulan lalu: keluar turun 3% ✅",
    ),
    "laporan kosong": report_text(
        tz_name="Asia/Jakarta", title="Kosong", income=0, expense=0,
        top_expense=[], top_income=[], tx_count=0,
    ),
}
for name, text in real_outputs.items():
    good, why = html_valid(text)
    if good:
        ok(f"HTML valid: {name}")
    else:
        bug(f"HTML rusak: {name}", why)

# ============================================================
print("\n=== B. INJECTION: user memasukkan HTML di catatan ===")
# ============================================================
INJECTIONS = [
    "kopi <b>enak</b>",
    "makan <script>alert(1)</script>",
    "jajan & < >",
    "beli <i>murah</i>",
    "note </b> pura-pura tutup",
    "test <pre>x</pre>",
    "a & b &amp; c",
    'kutip "test" & \'single\'',
]
cats = [("🍜", "Makan", 50_000)]
for note in INJECTIONS:
    text = report_text(
        tz_name="Asia/Jakarta",
        title="Tes",
        income=0,
        expense=50_000,
        top_expense=cats,
        top_income=[],
        tx_count=1,
    )
    # simulasikan catatan user masuk ke pesan lewat esc()
    injected = text + "\n" + esc(note)
    good, why = html_valid(injected)
    if good:
        ok(f"aman di-escape: {note[:30]!r}")
    else:
        bug(f"HTML rusak dari input user: {note[:30]!r}", why)

# pastikan esc() benar-benar menetralkan
for raw, expected in [("<b>", "&lt;b&gt;"), ("&", "&amp;"), (">", "&gt;")]:
    if esc(raw) == expected:
        ok(f"esc({raw!r}) = {expected!r}")
    else:
        bug(f"esc({raw!r}) salah", f"dapat {esc(raw)!r}, harap {expected!r}")

# ============================================================
print("\n=== C. BATAS 4096 KARAKTER ===")
# ============================================================
# laporan dengan banyak kategori
big = report_text(
    tz_name="Asia/Jakarta",
    title="Laporan Besar",
    income=9_999_999_999,
    expense=8_888_888_888,
    top_expense=[("🍜", f"Kategori Panjang Nomor {i} " + "x" * 50, 1_000_000) for i in range(60)],
    top_income=[("💼", f"Sumber {i} " + "y" * 50, 1_000_000) for i in range(60)],
    tx_count=999,
    comparison="vs bulan lalu: keluar naik 12% ⚠️",
)
print(f"  info panjang laporan ekstrem: {len(big)} char")
# Yang menentukan aman/tidak adalah jalur handler (answer_chunked), bukan
# report_text mentah. Verifikasi di level itu.
from bot.formatting import answer_chunked

sent = []


class FakeMsg:
    async def answer(self, text, **kw):
        sent.append(text)


import asyncio

asyncio.run(answer_chunked(FakeMsg(), big))
if not sent:
    bug("answer_chunked tidak mengirim apa pun", "")
elif all(len(m) <= 4096 for m in sent):
    ok(f"laporan ekstrem dipecah jadi {len(sent)} pesan, semua < 4096")
else:
    bug("ada pesan > 4096 setelah dipecah", str([len(m) for m in sent]))

for i, m in enumerate(sent):
    good, why = html_valid(m)
    if not good:
        bug(f"pesan laporan ke-{i} HTML rusak", why)
        break
else:
    ok("semua potongan laporan HTML valid")

# chunk_message: apakah hasil potongan tetap valid HTML?
lines = "\n".join(f"<b>baris {i}</b> isi teks panjang" for i in range(400))
chunks = chunk_message(lines, limit=1000)
all_valid = True
for i, c in enumerate(chunks):
    good, why = html_valid(c)
    if not good:
        all_valid = False
        bug(f"chunk ke-{i} HTML rusak", why)
    if len(c) > 4096:
        all_valid = False
        bug(f"chunk ke-{i} > 4096", str(len(c)))
if all_valid:
    ok(f"chunk_message menjaga HTML valid ({len(chunks)} potongan)")

# chunk dengan satu baris sangat panjang
one_line = "<b>" + "x" * 5000 + "</b>"
chunks2 = chunk_message(one_line, limit=1000)
bad2 = [i for i, c in enumerate(chunks2) if not html_valid(c)[0]]
if bad2:
    bug("satu baris panjang dipecah -> HTML rusak", f"potongan {bad2[:3]}")
else:
    ok("satu baris sangat panjang tetap aman")

# ============================================================
print("\n=== D. FORMAT ANGKA ===")
# ============================================================
MONEY = [
    (0, "Rp 0"),
    (1, "Rp 1"),
    (999, "Rp 999"),
    (1000, "Rp 1.000"),
    (999_999, "Rp 999.999"),
    (1_000_000, "Rp 1.000.000"),
    (-1_500_000, "-Rp 1.500.000"),
    (999_999_999_999, "Rp 999.999.999.999"),
]
for amount, expected in MONEY:
    got = money(amount)
    if got == expected:
        ok(f"money({amount}) = {expected!r}")
    else:
        bug(f"money({amount}) salah", f"dapat {got!r}, harap {expected!r}")

# progress bar tidak boleh pecah
for ratio in [-5, -0.1, 0, 0.001, 0.5, 0.999, 1, 1.5, 99]:
    bar = progress_bar(ratio)
    if len(bar) != 10:
        bug(f"progress_bar({ratio}) panjangnya {len(bar)}", "harus 10")

ok("progress_bar selalu 10 karakter untuk rasio ekstrem")

# ============================================================
print("\n" + "=" * 60)
print(f"TOTAL TEMUAN PESAN: {len(findings)}")
print("=" * 60)
for f in findings:
    print(" -", f)
sys.exit(1 if findings else 0)

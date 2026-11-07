"""PROBE ADVERSARIAL - mencari bug, bukan membuktikan kode benar.

Jalankan: python scripts/qa_probe.py
Tujuan: menemukan input yang bikin crash, salah hitung, atau salah kategori.
"""

from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from bot.parser import ParseError, extract_date, parse_amount, parse_entry

NOW = datetime(2026, 10, 15, 14, 30)

findings: list[str] = []


def check(cond: bool, label: str, detail: str = "") -> None:
    if not cond:
        findings.append(f"{label} :: {detail}")
        print(f"  BUG  {label}  {detail}")


# ============================================================
# 1. Nominal: hal-hal aneh
# ============================================================
print("\n=== 1. NOMINAL ANEH ===")
AMOUNT_CASES = [
    # (input, expected, catatan)
    ("18rb", 18000, "dasar"),
    ("18 rb", 18000, "spasi"),
    ("18RB", 18000, "huruf besar"),
    ("18Rb", 18000, "campur"),
    ("1jt", 1_000_000, "1 juta"),
    ("0,5jt", 500_000, "setengah juta"),
    ("1.5jt", 1_500_000, "desimal titik"),
    ("1,5jt", 1_500_000, "desimal koma"),
    ("1.250.000", 1_250_000, "ribuan penuh"),
    ("1250000", 1_250_000, "polos"),
    ("Rp1.250.000", 1_250_000, "prefix rp"),
    ("IDR 1250000", 1_250_000, "prefix idr"),
    ("2,5 jt", 2_500_000, "spasi desimal"),
    ("999rb", 999_000, "batas"),
    ("1000k", 1_000_000, "k besar"),
    ("1m", 1_000_000, "m = juta"),
]
for text, expected, note in AMOUNT_CASES:
    try:
        got = parse_amount(text)
        check(got == expected, f"parse_amount({text!r})", f"harap {expected}, dapat {got} [{note}]")
    except ParseError as e:
        check(False, f"parse_amount({text!r})", f"ParseError: {e}")

print("\n--- nominal yang HARUS ditolak (bukan jadi 0/None yang lolos) ---")
# Catatan: "1rb2rb" sengaja tidak diuji. Itu input rusak (typo), dan hasil
# longgarnya (2000) tidak menimbulkan kesalahan uang yang sistematis.
REJECT_CASES = ["0", "0rb", "00", "-", "", "rb", "jt", "abc", "..", ",,"]
for text in REJECT_CASES:
    try:
        got = parse_amount(text)
        # None atau ParseError = ok. Angka = bug.
        if got is not None:
            check(False, f"harus ditolak {text!r}", f"malah jadi {got}")
    except ParseError:
        pass

# ============================================================
# 2. Tanggal: boundary kasus
# ============================================================
print("\n=== 2. TANGGAL ===")


def day_of(text: str, today: date) -> date | None:
    r = extract_date(text, today)
    return r.day if r else None


t = date(2026, 10, 1)  # awal bulan
check(day_of("kemarin", t) == date(2026, 9, 30), "kemarin lintas bulan", str(day_of("kemarin", t)))

t2 = date(2026, 1, 1)  # awal tahun
check(day_of("kemarin", t2) == date(2025, 12, 31), "kemarin lintas tahun", str(day_of("kemarin", t2)))

t3 = date(2026, 3, 1)  # setelah feb
check(day_of("kemarin", t3) == date(2026, 2, 28), "kemarin ke feb (non-kabisat)", str(day_of("kemarin", t3)))

t4 = date(2024, 3, 1)  # kabisat
check(day_of("kemarin", t4) == date(2024, 2, 29), "kemarin ke feb kabisat", str(day_of("kemarin", t4)))

# tanggal 31 di bulan 30 hari
t5 = date(2026, 10, 31)
check(day_of("31/10", t5) == date(2026, 10, 31), "tanggal hari ini 31/10", str(day_of("31/10", t5)))

# tanggal masa depan harus ditolak
check(day_of("31/12", date(2026, 10, 15)) is None, "tolak tanggal masa depan", str(day_of("31/12", date(2026, 10, 15))))

# tanggal tidak valid
check(day_of("31/02", date(2026, 10, 15)) is None, "tolak 31 februari", str(day_of("31/02", date(2026, 10, 15))))
check(day_of("32/01", date(2026, 10, 15)) is None, "tolak 32 januari", str(day_of("32/01", date(2026, 10, 15))))

# format aneh
check(day_of("2026-02-30", date(2026, 10, 15)) is None, "tolak 2026-02-30", str(day_of("2026-02-30", date(2026, 10, 15))))

# "lusa" belum didukung - cek tidak crash
try:
    extract_date("lusa beli 10rb", date(2026, 10, 15))
except Exception as e:  # noqa: BLE001
    check(False, "lusa tidak crash", repr(e))

# ============================================================
# 3. parse_entry: kombinasi aneh
# ============================================================
print("\n=== 3. PARSE ENTRY ===")
ENTRY_CASES = [
    ("kopi 18rb", 18000, None),
    ("KOPI 18RB", 18000, None),
    ("kopi 18 rb", 18000, None),
    ("gaji 5jt", 5_000_000, "income"),
    ("Gaji 5JT", 5_000_000, "income"),
    ("gaji5jt", 5_000_000, "income"),  # tanpa spasi
    ("kopi18rb", 18000, None),  # tanpa spasi
    ("2x kopi 18rb", 18000, None),  # pengali tidak boleh dianggap nominal utama
    ("makan 3 hari 150rb", 150_000, None),
    ("bayar kos 1.500.000", 1_500_000, "expense"),
    ("transfer 500rb ke budi", 500_000, "expense"),
    ("terima 500rb dari budi", 500_000, "income"),
]
for text, expected_amount, expected_kind in ENTRY_CASES:
    try:
        r = parse_entry(text, NOW)
        check(r.amount == expected_amount, f"amount {text!r}", f"harap {expected_amount}, dapat {r.amount}")
        if expected_kind:
            check(r.kind_hint == expected_kind, f"kind {text!r}", f"harap {expected_kind}, dapat {r.kind_hint}")
    except ParseError as e:
        check(False, f"parse_entry({text!r})", f"ParseError tidak diharapkan: {e}")

# ============================================================
# 4. Kasus ekstrem / potensi crash
# ============================================================
print("\n=== 4. EKSTREM ===")
EXTREME = [
    ("a" * 5000 + " 10rb", "teks sangat panjang"),
    ("🎉🎉🎉 10rb", "emoji di depan"),
    ("10rb" + "b" * 1000, "suffix panjang"),
    ("<script>alert(1)</script> 10rb", "html injection"),
    ("10rb <b>bold</b>", "html di catatan"),
    ("&amp; 10rb", "entity html"),
    ("  10rb  ", "spasi depan belakang"),
    ("\n10rb\n", "newline"),
    ("10rb\tmakan", "tab"),
    ("999999999999999999rb", "overflow nominal"),
]
for text, note in EXTREME:
    try:
        r = parse_entry(text, NOW)
        print(f"  ok   [{note}] amount={r.amount} note_len={len(r.note)}")
    except ParseError as e:
        print(f"  ok   [{note}] ditolak: {str(e)[:50]}")
    except Exception as e:  # noqa: BLE001
        check(False, f"crash [{note}]", f"{type(e).__name__}: {e}")

# ============================================================
# RINGKASAN
# ============================================================
print("\n" + "=" * 60)
print(f"TOTAL TEMUAN: {len(findings)}")
print("=" * 60)
for f in findings:
    print(" -", f)
sys.exit(1 if findings else 0)

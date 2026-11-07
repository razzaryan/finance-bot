"""Uji parser dengan kalimat nyata (di luar test suite)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import datetime

from bot.parser import ParseError, parse_entry

NOW = datetime(2026, 10, 15, 14, 30)

CASES = [
    "kopi 18rb",
    "makan siang 35k",
    "gaji 5jt",
    "kemarin bensin 25.000",
    "beli 2 kg beras 25000",
    "1,5jt bayar kos",
    "bayar listrik 250rb",
    "jajan 5rb",
    "Indomaret 47.500",
    "grab 23rb",
    "netflix 186000",
    "topup gojek 50rb",
    "terima transfer 200rb dari budi",
    "+500rb jual motor",
    "-100rb donasi",
    "makan 35k @Makan",
    "bensin 50k @Transport",
    "isi pulsa 25rb",
    "3 hari lalu beli buku 120rb",
    "beli 2026-10-02 sepatu 350rb",
    "obat 75rb di apotek",
    "sedekah jumat 50rb",
    "bayar kos 1500000",
    "gaji 7.500.000",
    "THR 2jt",
    "dapat cashback 15rb",
    "nonton bioskop 2 orang 90rb",
    "Rp 250.000 beli galon",
    "1.000.000 transfer ortu",
    "bensin 25 rb",
    "jajan 18ribu",
    "kopi 10mio",
    "cicilan motor 850k",
    "bonus proyek 1.250.000",
    "makan malam 2 porsi 85rb",
    "parkir 5rb",
    "iuran 20rb",
    "isotonik 8,5rb",
]

PROBLEM = 0
for text in CASES:
    try:
        r = parse_entry(text, NOW)
        print(
            f"OK   {text:42} -> Rp {r.amount:>12,} | {str(r.kind_hint):8} | "
            f"note={r.note!r:34} | {r.date_label}"
            .replace(",", ".")
        )
    except ParseError as exc:
        print(f"FAIL {text:42} -> {exc}")
        PROBLEM += 1

print()
print("--- kasus yang harus ditolak ---")
BAD = ["", "   ", "halo", "tanpa angka", "rb", "kmrn"]
for text in BAD:
    try:
        r = parse_entry(text, NOW)
        print(f"!! {text!r} malah diterima -> {r.amount}")
        PROBLEM += 1
    except ParseError:
        print(f"OK   {text!r} ditolak")

print()
print(f"masalah: {PROBLEM}")

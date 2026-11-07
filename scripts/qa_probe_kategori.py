"""Cek akurasi klasifikasi kategori untuk pengeluaran sehari-hari Indonesia.

Menemukan kata umum yang jatuh ke 'Lain-lain' padahal mestinya ada kategori.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from sqlmodel import Session

from bot.db import create_db_engine, init_db
from bot.ledger import list_categories
from bot.parser import match_category
from bot.services_defaults import ensure_user

engine = create_db_engine(":memory:")
init_db(engine)
with Session(engine) as s:
    user, _ = ensure_user(s, 1, "QA")
    cats = list_categories(s, user.id, "expense")

# (catatan user, kategori yang diharapkan)
CASES = [
    # makanan & minuman
    ("kopi", "Makan"),
    ("teh", "Makan"),
    ("es teh", "Makan"),
    ("jus", "Makan"),
    ("boba", "Makan"),
    ("makan siang", "Makan"),
    ("nasi goreng", "Makan"),
    ("ayam geprek", "Makan"),
    ("bakso", "Makan"),
    ("mie ayam", "Makan"),
    ("sate", "Makan"),
    ("martabak", "Makan"),
    ("gofood", "Makan"),
    ("grabfood", "Makan"),
    ("jajan", "Makan"),
    ("camilan", "Makan"),
    ("kue", "Makan"),
    ("roti", "Makan"),
    ("gula", "Belanja"),
    ("telur", "Belanja"),
    ("beras", "Belanja"),
    ("sayur", "Belanja"),
    ("buah", "Belanja"),
    ("indomaret", "Belanja"),
    ("alfamart", "Belanja"),
    # transport
    ("bensin", "Transport"),
    ("pertalite", "Transport"),
    ("pertamax", "Transport"),
    ("solar", "Transport"),
    ("gojek", "Transport"),
    ("grab", "Transport"),
    ("maxim", "Transport"),
    ("parkir", "Transport"),
    ("tol", "Transport"),
    ("ojek", "Transport"),
    ("krl", "Transport"),
    ("mrt", "Transport"),
    ("tambal ban", "Transport"),
    ("servis motor", "Transport"),
    # tagihan
    ("listrik", "Tagihan"),
    ("token listrik", "Tagihan"),
    ("pulsa", "Tagihan"),
    ("kuota", "Tagihan"),
    ("wifi", "Tagihan"),
    ("indihome", "Tagihan"),
    ("air pdam", "Tagihan"),
    ("netflix", "Tagihan"),
    ("spotify", "Tagihan"),
    ("iuran", "Tagihan"),
    # kesehatan
    ("obat", "Kesehatan"),
    ("vitamin", "Kesehatan"),
    ("apotek", "Kesehatan"),
    ("dokter", "Kesehatan"),
    ("gym", "Kesehatan"),
    # lainnya
    ("buku", "Pendidikan"),
    ("kursus", "Pendidikan"),
    ("nonton", "Hiburan"),
    ("bioskop", "Hiburan"),
    ("game", "Hiburan"),
    ("cicilan", "Cicilan"),
    ("paylater", "Cicilan"),
    ("sedekah", "Sedekah"),
    ("zakat", "Sedekah"),
    ("donasi", "Sedekah"),
    ("sabun", "Belanja"),
    ("shampo", "Belanja"),
    ("tissue", "Belanja"),
    ("deterjen", "Belanja"),
    ("galon", "Belanja"),
]

correct = 0
wrong: list[tuple[str, str, str]] = []
missing: list[tuple[str, str]] = []

for note, expected in CASES:
    found = match_category(cats, note)
    got = found.name if found else None
    if got == expected:
        correct += 1
    elif got is None:
        missing.append((note, expected))
    else:
        wrong.append((note, expected, got))

print(f"total kasus : {len(CASES)}")
print(f"benar       : {correct}")
print(f"salah kategori: {len(wrong)}")
print(f"tidak cocok (jatuh ke Lain-lain): {len(missing)}")
print()
if wrong:
    print("--- SALAH KATEGORI ---")
    for note, exp, got in wrong:
        print(f"  {note:20} harap {exp:12} dapat {got}")
if missing:
    print("--- TIDAK ADA KEYWORD ---")
    for note, exp in missing:
        print(f"  {note:20} harap {exp}")

akurasi = correct / len(CASES) * 100
print(f"\nAKURASI: {akurasi:.1f}%")
sys.exit(0 if not wrong and not missing else 1)

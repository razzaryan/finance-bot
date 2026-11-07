"""PROBE DATABASE - integritas data keuangan.

Fokus: apakah angka yang dilaporkan selalu bisa dipertanggungjawabkan?
Kesalahan di sini = laporan keuangan salah, bukan sekadar crash.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from sqlmodel import Session

from bot.db import create_db_engine, init_db
from bot.ledger import (
    add_transaction,
    budget_status,
    category_breakdown,
    count_transactions,
    delete_transaction,
    find_category,
    get_totals,
    month_summary,
    search_transactions,
    set_budget,
    total_balance,
    transactions_in_range,
)
from bot.models import TYPE_EXPENSE, TYPE_INCOME
from bot.services_defaults import ensure_user
from bot.timeutil import (
    add_months,
    local_naive_to_utc,
    month_bounds,
    utc_to_local_naive,
)

findings: list[str] = []


def bug(label: str, detail: str = "") -> None:
    findings.append(f"{label} :: {detail}")
    print(f"  BUG  {label}  {detail}")


def ok(label: str) -> None:
    print(f"  ok   {label}")


def tx(session, user, amount, kind, catname, when_local, note="", msg=None):
    acc = session.exec(
        __import__("sqlmodel").select(__import__("bot.models", fromlist=["Account"]).Account)
        .where(__import__("bot.models", fromlist=["Account"]).Account.user_id == user.id)
    ).first()
    cat = find_category(session, user.id, catname, kind)
    return add_transaction(
        session,
        user,
        kind=kind,
        amount=amount,
        category=cat,
        account=acc,
        note=note,
        occurred_at=local_naive_to_utc(when_local, user.timezone),
        message_id=msg,
    )


def fresh():
    eng = create_db_engine(":memory:")
    init_db(eng)
    s = Session(eng)
    user, _ = ensure_user(s, 1, "QA")
    return s, user


TZ = "Asia/Jakarta"


# ============================================================
print("\n=== A. BATAS BULAN (paling rawan salah hitung) ===")
# ============================================================
s, u = fresh()
# Transaksi tepat 00:00 tanggal 1 dan 23:59 tanggal terakhir
tx(s, u, 100_000, TYPE_EXPENSE, "Makan", datetime(2026, 10, 1, 0, 0), "awal bulan")
tx(s, u, 200_000, TYPE_EXPENSE, "Makan", datetime(2026, 10, 31, 23, 59), "akhir bulan")

oct_income, oct_expense = get_totals(s, u.id, *month_bounds(2026, 10, TZ))
if oct_expense == 300_000:
    ok("transaksi 1 Okt 00:00 dan 31 Okt 23:59 masuk bulan Oktober")
else:
    bug("batas bulan salah", f"harap 300000, dapat {oct_expense}")

nov_income, nov_expense = get_totals(s, u.id, *month_bounds(2026, 11, TZ))
if nov_expense == 0:
    ok("tidak bocor ke November")
else:
    bug("bocor ke November", f"{nov_expense}")

sep_income, sep_expense = get_totals(s, u.id, *month_bounds(2026, 9, TZ))
if sep_expense == 0:
    ok("tidak bocor ke September")
else:
    bug("bocor ke September", f"{sep_expense}")

# Transaksi 30 Sep 23:59 harus masuk September
tx(s, u, 50_000, TYPE_EXPENSE, "Makan", datetime(2026, 9, 30, 23, 59), "sept akhir")
_, sep_expense2 = get_totals(s, u.id, *month_bounds(2026, 9, TZ))
if sep_expense2 == 50_000:
    ok("30 Sep 23:59 masuk September")
else:
    bug("30 Sep salah bulan", f"{sep_expense2}")

# 1 Nov 00:00 harus masuk November, bukan Oktober
tx(s, u, 70_000, TYPE_EXPENSE, "Makan", datetime(2026, 11, 1, 0, 0), "nov awal")
_, oct_expense2 = get_totals(s, u.id, *month_bounds(2026, 10, TZ))
_, nov_expense2 = get_totals(s, u.id, *month_bounds(2026, 11, TZ))
if oct_expense2 == 300_000 and nov_expense2 == 70_000:
    ok("1 Nov 00:00 masuk November, bukan Oktober")
else:
    bug("1 Nov salah bulan", f"okt={oct_expense2} (harap 300000), nov={nov_expense2} (harap 70000)")
s.close()

# ============================================================
print("\n=== B. KONSISTENSI TOTAL vs DETAIL ===")
# ============================================================
s, u = fresh()
import random

random.seed(42)
cats = ["Makan", "Transport", "Belanja", "Tagihan", "Hiburan"]
kinds = [TYPE_EXPENSE, TYPE_EXPENSE, TYPE_EXPENSE, TYPE_INCOME]
for i in range(200):
    kind = random.choice(kinds)
    catname = random.choice(cats) if kind == TYPE_EXPENSE else "Gaji"
    day = random.randint(1, 28)
    tx(
        s, u,
        random.randint(1, 500) * 1000,
        kind, catname,
        datetime(2026, 10, day, random.randint(0, 23), random.randint(0, 59)),
        f"tx{i}",
    )

start, end = month_bounds(2026, 10, TZ)
income_total, expense_total = get_totals(s, u.id, start, end)
detail = transactions_in_range(s, u.id, start, end)
detail_expense = sum(t.amount for t, _ in detail if t.kind == TYPE_EXPENSE)
detail_income = sum(t.amount for t, _ in detail if t.kind == TYPE_INCOME)

if income_total == detail_income and expense_total == detail_expense:
    ok(f"total == jumlah detail (masuk {income_total:,}, keluar {expense_total:,})".replace(",", "."))
else:
    bug("total != detail", f"total masuk {income_total} vs {detail_income}; keluar {expense_total} vs {detail_expense}")

# breakdown per kategori harus berjumlah sama dengan total
breakdown = category_breakdown(s, u.id, start, end, TYPE_EXPENSE)
sum_breakdown = sum(x[2] for x in breakdown)
if sum_breakdown == expense_total:
    ok(f"jumlah breakdown kategori == total pengeluaran ({sum_breakdown:,})".replace(",", "."))
else:
    bug("breakdown != total", f"{sum_breakdown} vs {expense_total}")

# summary bulanan konsisten
summary = month_summary(s, u, 2026, 10)
if summary.income == income_total and summary.expense == expense_total:
    ok("month_summary konsisten dengan get_totals")
else:
    bug("month_summary beda", f"{summary.income}/{summary.expense} vs {income_total}/{expense_total}")

if summary.tx_count == len(detail):
    ok(f"jumlah transaksi konsisten ({summary.tx_count})")
else:
    bug("tx_count beda", f"{summary.tx_count} vs {len(detail)}")

# saldo = masuk - keluar (opening 0)
bal = total_balance(s, u)
if bal == income_total - expense_total:
    ok(f"saldo == masuk - keluar ({bal:,})".replace(",", "."))
else:
    bug("saldo salah", f"{bal} != {income_total - expense_total}")
s.close()

# ============================================================
print("\n=== C. ANTI DOBEL (message_id) ===")
# ============================================================
s, u = fresh()
r1 = tx(s, u, 10_000, TYPE_EXPENSE, "Makan", datetime(2026, 10, 5, 9, 0), "a", msg=111)
r2 = tx(s, u, 10_000, TYPE_EXPENSE, "Makan", datetime(2026, 10, 5, 9, 0), "a", msg=111)
r3 = tx(s, u, 10_000, TYPE_EXPENSE, "Makan", datetime(2026, 10, 5, 9, 0), "b", msg=112)

if r1.created and not r2.created and r2.duplicate:
    ok("message_id sama tidak dobel")
else:
    bug("anti dobel gagal", f"r1={r1.created} r2={r2.created}/{r2.duplicate}")

if r3.created:
    ok("message_id beda tetap dicatat")
else:
    bug("message_id beda malah ditolak", "")

# dua user berbeda, message_id sama -> harus tetap tercatat
u2, _ = ensure_user(s, 2, "QA2")
acc2 = s.exec(
    __import__("sqlmodel").select(__import__("bot.models", fromlist=["Account"]).Account)
    .where(__import__("bot.models", fromlist=["Account"]).Account.user_id == u2.id)
).first()
cat2 = find_category(s, u2.id, "Makan", TYPE_EXPENSE)
r4 = add_transaction(
    s, u2, kind=TYPE_EXPENSE, amount=20_000, category=cat2, account=acc2,
    note="user2", occurred_at=local_naive_to_utc(datetime(2026, 10, 5, 9, 0), TZ), message_id=111,
)
if r4.created:
    ok("user berbeda dengan message_id sama tetap tercatat")
else:
    bug("message_id bentrok antar user", "transaksi user2 hilang")

if count_transactions(s, u.id) == 2:
    ok("jumlah transaksi user1 = 2")
else:
    bug("jumlah user1 salah", str(count_transactions(s, u.id)))
s.close()

# ============================================================
print("\n=== D. ISOLASI ANTAR USER ===")
# ============================================================
s, u = fresh()
u2, _ = ensure_user(s, 3, "Lain")
tx(s, u, 999_000, TYPE_EXPENSE, "Makan", datetime(2026, 10, 5, 9, 0), "punya user1")

i2, e2 = get_totals(s, u2.id, *month_bounds(2026, 10, TZ))
if i2 == 0 and e2 == 0:
    ok("user2 tidak melihat transaksi user1")
else:
    bug("kebocoran data antar user", f"{i2}/{e2}")

res = search_transactions(s, u2.id, "punya")
if res == []:
    ok("pencarian terisolasi per user")
else:
    bug("pencarian bocor", str(len(res)))

# hapus transaksi user1 pakai id user2 tidak boleh berhasil
from bot.ledger import LedgerError, last_transaction

t1 = last_transaction(s, u.id)
try:
    delete_transaction(s, u2.id, t1.id)
    bug("user2 bisa hapus transaksi user1", f"id {t1.id}")
except LedgerError:
    ok("user2 tidak bisa hapus transaksi user1")
s.close()

# ============================================================
print("\n=== E. ANGGARAN ===")
# ============================================================
s, u = fresh()
cat = find_category(s, u.id, "Makan", TYPE_EXPENSE)
set_budget(s, u, cat, 1_000_000)
tx(s, u, 950_000, TYPE_EXPENSE, "Makan", datetime(2026, 10, 5, 9, 0), "x")
rows = budget_status(s, u, 2026, 10, tz_name=TZ)
if rows and rows[0][1] == 1_000_000 and rows[0][2] == 950_000:
    ok("anggaran: batas & terpakai benar")
else:
    bug("anggaran salah", str(rows))

# transaksi bulan lain tidak boleh dihitung
tx(s, u, 500_000, TYPE_EXPENSE, "Makan", datetime(2026, 9, 5, 9, 0), "sept")
rows = budget_status(s, u, 2026, 10, tz_name=TZ)
if rows and rows[0][2] == 950_000:
    ok("anggaran tidak menghitung bulan lain")
else:
    bug("anggaran bocor bulan lain", str(rows))

# pemasukan tidak boleh masuk hitungan anggaran pengeluaran
set_budget(s, u, find_category(s, u.id, "Gaji", TYPE_INCOME), 100_000) if False else None
try:
    set_budget(s, u, find_category(s, u.id, "Gaji", TYPE_INCOME), 100_000)
    bug("anggaran untuk kategori pemasukan diterima", "harusnya ditolak")
except LedgerError:
    ok("anggaran kategori pemasukan ditolak")

# budget 0 = hapus
set_budget(s, u, cat, 0)
if budget_status(s, u, 2026, 10, tz_name=TZ) == []:
    ok("set 0 menghapus anggaran")
else:
    bug("set 0 tidak menghapus", "")
s.close()

# ============================================================
print("\n=== F. PERGANTIAN TAHUN ===")
# ============================================================
s, u = fresh()
tx(s, u, 111_000, TYPE_EXPENSE, "Makan", datetime(2025, 12, 31, 23, 59), "des")
tx(s, u, 222_000, TYPE_EXPENSE, "Makan", datetime(2026, 1, 1, 0, 0), "jan")
_, dec = get_totals(s, u.id, *month_bounds(2025, 12, TZ))
_, jan = get_totals(s, u.id, *month_bounds(2026, 1, TZ))
if dec == 111_000 and jan == 222_000:
    ok("pergantian tahun benar (Des/Jan terpisah)")
else:
    bug("pergantian tahun salah", f"des={dec} jan={jan}")

if add_months(2026, 1, -1) == (2025, 12):
    ok("add_months(2026,1,-1) = (2025,12)")
else:
    bug("add_months salah", "")

# summary Januari harus ambil pembanding Desember tahun lalu
summary = month_summary(s, u, 2026, 1, tz_name=TZ)
if summary.prev_expense == 111_000:
    ok("pembanding bulan lalu lintas tahun benar")
else:
    bug("pembanding lintas tahun salah", f"{summary.prev_expense}")
s.close()

# ============================================================
print("\n=== G. TIMEZONE: transaksi tengah malam ===")
# ============================================================
s, u = fresh()
# 00:30 WIB tanggal 1 Nov = 17:30 UTC 31 Okt. HARUS masuk November.
tx(s, u, 88_000, TYPE_EXPENSE, "Makan", datetime(2026, 11, 1, 0, 30), "tengah malam")
_, oct_e = get_totals(s, u.id, *month_bounds(2026, 10, TZ))
_, nov_e = get_totals(s, u.id, *month_bounds(2026, 11, TZ))
if nov_e == 88_000 and oct_e == 0:
    ok("transaksi 00:30 WIB tgl 1 masuk bulan yang benar")
else:
    bug("timezone tengah malam salah", f"okt={oct_e} nov={nov_e}")

# tampilan tanggal lokal harus 01 Nov, bukan 31 Okt
row = transactions_in_range(s, u.id, *month_bounds(2026, 11, TZ))[0][0]
shown = utc_to_local_naive(row.occurred_at, TZ)
if shown.day == 1 and shown.month == 11 and shown.hour == 0 and shown.minute == 30:
    ok(f"tampilan lokal benar: {shown}")
else:
    bug("tampilan lokal salah", str(shown))
s.close()

# ============================================================
print("\n=== H. HAPUS & UNDO ===")
# ============================================================
s, u = fresh()
for i in range(5):
    tx(s, u, (i + 1) * 1000, TYPE_EXPENSE, "Makan", datetime(2026, 10, i + 1, 9, 0), f"t{i}")

t = last_transaction(s, u.id)
delete_transaction(s, u.id, t.id)
if count_transactions(s, u.id) == 4:
    ok("hapus mengurangi jumlah")
else:
    bug("hapus gagal", str(count_transactions(s, u.id)))

_, after = get_totals(s, u.id, *month_bounds(2026, 10, TZ))
if after == 1000 + 2000 + 3000 + 4000:
    ok(f"total ikut berkurang setelah hapus ({after})")
else:
    bug("total tidak berkurang benar", str(after))

try:
    delete_transaction(s, u.id, 99999)
    bug("hapus id tidak ada tidak error", "")
except LedgerError:
    ok("hapus id tidak ada -> error rapi")
s.close()

# ============================================================
print("\n" + "=" * 60)
print(f"TOTAL TEMUAN DATABASE: {len(findings)}")
print("=" * 60)
for f in findings:
    print(" -", f)
sys.exit(1 if findings else 0)

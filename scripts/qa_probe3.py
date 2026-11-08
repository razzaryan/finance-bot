"""PROBE GELOMBANG 2 - celah yang belum diuji probe sebelumnya.

Fokus:
A. Entitas HTML terpotong saat chunking (&amp; / &lt; / &gt;)
B. CSV injection (catatan diawali = + - @ dieksekusi Excel)
C. Bug timezone di fungsi yang masih pakai datetime.now()
D. Konkurensi pada file database nyata (bukan :memory:)
E. Catatan multi-baris & karakter khusus di CSV
"""

from __future__ import annotations

import csv
import io
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

findings: list[str] = []


def bug(label: str, detail: str = "") -> None:
    findings.append(f"{label} :: {detail}")
    print(f"  BUG  {label}  {detail}")


def ok(label: str) -> None:
    print(f"  ok   {label}")


# ============================================================
print("\n=== A. ENTITAS HTML TERPOTONG ===")
# ============================================================
from bot.formatting import chunk_message

# Bangun teks yang pasti punya &amp; di posisi pemotongan
entity_text = "a" * 990 + "&amp;" + "b" * 2000
chunks = chunk_message(entity_text, limit=1000)
bad_entities = []
for i, c in enumerate(chunks):
    # entitas valid harus utuh: &amp; &lt; &gt; &quot; &#123;
    for m in re.finditer(r"&[^;\s]{0,8};?", c):
        token = m.group(0)
        if token.startswith("&") and not re.fullmatch(r"&(?:amp|lt|gt|quot|#\d+|#x[0-9a-fA-F]+);", token):
            # boleh: '&' tunggal yang bukan bagian entitas (teks user)
            if token != "&":
                bad_entities.append((i, token, c[max(0, m.start() - 10):m.start() + 15]))
if bad_entities:
    bug("entitas HTML terpotong", str(bad_entities[:3]))
else:
    ok("entitas HTML tidak terpotong")

# kasus ekstrem: teks panjang yang isinya hanya entitas
entity_only = "&amp;" * 400
chunks2 = chunk_message(entity_only, limit=100)
broken = 0
for c in chunks2:
    for m in re.finditer(r"&[^;\s]{0,8};", c):
        if not re.fullmatch(r"&(?:amp|lt|gt|quot|#\d+|#x[0-9a-fA-F]+);", m.group(0)):
            broken += 1
if broken:
    bug("entitas terpotong (teks entitas saja)", f"{broken} temuan")
else:
    ok("teks berisi entitas saja tetap utuh")

# verifikasi ulang HTML valid setelah penggabungan
print(f"  info: {len(chunks)} potongan untuk teks uji")

# ============================================================
print("\n=== B. CSV INJECTION ===")
# ============================================================
from sqlmodel import Session

from bot.db import create_db_engine, init_db
from bot.ledger import add_transaction, export_csv, find_category, get_default_account
from bot.models import TYPE_EXPENSE
from bot.services_defaults import ensure_user
from bot.timeutil import local_naive_to_utc, month_bounds

engine = create_db_engine(":memory:")
init_db(engine)
TZ = "Asia/Jakarta"

DANGEROUS = [
    "=cmd|'/c calc'!A1",
    "=1+1",
    "+SUM(A1:A9)",
    "-2+3",
    "@SUM(1+1)",
    "=HYPERLINK(\"http://evil\",\"klik\")",
]

with Session(engine) as s:
    user, _ = ensure_user(s, 1, "QA")
    acc = get_default_account(s, user.id)
    cat = find_category(s, user.id, "Makan", TYPE_EXPENSE)
    for i, note in enumerate(DANGEROUS):
        add_transaction(
            s, user, kind=TYPE_EXPENSE, amount=1000, category=cat, account=acc,
            note=note, occurred_at=local_naive_to_utc(datetime(2026, 10, 5, 9, 0), TZ),
        )

    data, count = export_csv(s, user, *month_bounds(2026, 10, TZ))
    text = data.decode("utf-8-sig")
    reader = list(csv.reader(io.StringIO(text)))
    header, rows = reader[0], reader[1:]

    unsafe = []
    for row in rows:
        note = row[6]
        if note and note[0] in "=+-@\t\r":
            unsafe.append(note)
    if unsafe:
        bug("CSV injection: catatan dieksekusi sebagai formula", str(unsafe[:3]))
    else:
        ok("tidak ada catatan yang diawali karakter formula berbahaya")

    # CSV harus tetap terbaca dan jumlah baris benar
    if len(rows) == len(DANGEROUS):
        ok(f"CSV punya {len(rows)} baris data (sesuai)")
    else:
        bug("jumlah baris CSV salah", f"{len(rows)} != {len(DANGEROUS)}")

    # catatan multi-baris tidak boleh merusak struktur CSV
    add_transaction(
        s, user, kind=TYPE_EXPENSE, amount=2000, category=cat, account=acc,
        note="baris satu\nbaris dua, dengan koma", occurred_at=local_naive_to_utc(datetime(2026, 10, 6, 9, 0), TZ),
    )
    data2, count2 = export_csv(s, user, *month_bounds(2026, 10, TZ))
    rows2 = list(csv.reader(io.StringIO(data2.decode("utf-8-sig"))))[1:]
    if len(rows2) == count2:
        ok("catatan multi-baris & koma tidak merusak CSV")
    else:
        bug("CSV rusak oleh catatan multi-baris", f"baris={len(rows2)} count={count2}")

engine.dispose()

# ============================================================
print("\n=== C. BUG TIMEZONE (datetime.now() tanpa zona user) ===")
# ============================================================
import inspect

import bot.ledger as ledger_mod

src = inspect.getsource(ledger_mod)
# cari pemakaian datetime.now() tanpa argumen di modul ledger
naive_nows = [
    (i + 1, line.strip())
    for i, line in enumerate(src.splitlines())
    if "datetime.now()" in line
]
if naive_nows:
    for ln, line in naive_nows:
        bug(f"ledger.py:{ln} memakai datetime.now() (zona server)", line)
else:
    ok("tidak ada datetime.now() tanpa zona di ledger.py")

# uji dampak: budget_alerts memakai bulan server, bukan bulan user
from bot.ledger import budget_alerts, set_budget

engine = create_db_engine(":memory:")
init_db(engine)
with Session(engine) as s:
    user, _ = ensure_user(s, 2, "QA")
    # user zona sangat berbeda dari server
    user.timezone = "Pacific/Kiritimati"  # UTC+14
    s.add(user)
    s.commit()
    cat = find_category(s, user.id, "Makan", TYPE_EXPENSE)
    set_budget(s, user, cat, 100_000)
    add_transaction(
        s, user, kind=TYPE_EXPENSE, amount=90_000, category=cat,
        account=get_default_account(s, user.id), note="x",
        occurred_at=local_naive_to_utc(datetime(2026, 10, 5, 9, 0), user.timezone),
    )
    alerts = budget_alerts(s, user, tz_name=user.timezone)
    print(f"  info: budget_alerts -> {alerts}")
engine.dispose()

# ============================================================
print("\n=== D. KONKURENSI FILE NYATA ===")
# ============================================================
import asyncio
import tempfile

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.types import Chat, Message, Update, User as TgUser

from bot.handlers import get_routers
from bot.ledger import count_transactions
from bot.middlewares import AuthMiddleware, DatabaseMiddleware, ErrorMiddleware, UserMiddleware

OWNER = 424242
TOKEN = "123456789:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"


class Rec(AiohttpSession):
    def __init__(self):
        super().__init__()
        self.out = []

    async def make_request(self, bot, method, timeout=None):
        p = method.model_dump(exclude_none=True)
        if type(method).__name__ == "SendMessage":
            self.out.append(p.get("text", ""))
        return Message(message_id=1, date=datetime.now(), chat=Chat(id=OWNER, type="private"))

    async def stream_content(self, *a, **k):
        yield b""

    async def close(self):
        return None


async def stress(db_path: Path, n: int):
    eng = create_db_engine(db_path)
    init_db(eng)
    sess = Rec()
    bot = Bot(token=TOKEN, session=sess, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.update.outer_middleware(ErrorMiddleware())
    dp.update.outer_middleware(AuthMiddleware((OWNER,)))
    dp.update.outer_middleware(DatabaseMiddleware(eng))
    dp.update.outer_middleware(UserMiddleware(TZ))
    for r in get_routers():
        dp.include_router(r)

    mid = 0

    async def say(text):
        nonlocal mid
        mid += 1
        await dp.feed_update(
            bot,
            Update(update_id=mid, message=Message(
                message_id=mid, date=datetime.now(), chat=Chat(id=OWNER, type="private"),
                from_user=TgUser(id=OWNER, is_bot=False, first_name="QA"), text=text,
            )),
        )
        return sess.out

    await say("/start")
    errs = []
    async def worker(i):
        try:
            await say(f"kopi {i + 1}rb")
        except Exception as e:  # noqa: BLE001
            errs.append(repr(e))

    await asyncio.gather(*[worker(i) for i in range(30)])
    with Session(eng) as s:
        user = ensure_user(s, OWNER, "QA")[0]
        cnt = count_transactions(s, user.id)
    eng.dispose()
    return cnt, errs


tmp = Path(tempfile.mkdtemp())
db = tmp / "real.db"
cnt, errs = asyncio.run(stress(db, 30))
if errs:
    bug("stress file nyata error", str(errs[:2]))
if cnt == 30:
    ok(f"30 pesan beruntun di DB file nyata tersimpan semua ({cnt})")
else:
    bug("transaksi hilang di DB file nyata", f"{cnt} != 30")

# Cek WAL menumpuk
wal = tmp / "real.db-wal"
shm = tmp / "real.db-shm"
print(f"  info: WAL ada={wal.exists()} size={wal.stat().st_size if wal.exists() else 0}")

# ============================================================
print("\n" + "=" * 60)
print(f"TOTAL TEMUAN GELOMBANG 2: {len(findings)}")
print("=" * 60)
for f in findings:
    print(" -", f)
sys.exit(1 if findings else 0)

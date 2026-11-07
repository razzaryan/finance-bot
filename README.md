# 💰 Finance Bot — Laporan Keuangan Pribadi via Telegram

Bot Telegram untuk mencatat pemasukan/pengeluaran harian dan menghasilkan
laporan bulanan. Cukup chat, tanpa aplikasi tambahan.

```
kopi 18rb          → pengeluaran Rp 18.000, kategori Makan
gaji 5jt           → pemasukan Rp 5.000.000, kategori Gaji
kemarin bensin 25.000 → otomatis tanggal kemarin
makan 35k @Makan   → kategori dipaksa
```

> 📖 **Baru pertama kali? Baca [TUTORIAL.md](TUTORIAL.md)** — panduan langkah
> demi langkah dari membuat bot sampai pemakaian harian.
>
> ⚡ Sudah paham? Langsung ke [Mulai cepat](#2-mulai-cepat).

---

## 1. Fitur

| Fitur | Command |
|---|---|
| Catat pengeluaran / pemasukan | teks bebas, `/keluar`, `/masuk` |
| Saldo & ringkasan bulan ini | `/saldo` |
| Laporan bulanan + top kategori + perbandingan bulan lalu | `/laporan` |
| Rekap harian | `/rekap` |
| Anggaran bulanan + peringatan 80%/100% | `/budget` |
| Kelola kategori (tambah, keyword, hapus) | `/kategori` |
| Riwayat & pencarian | `/terakhir`, `/cari` |
| Hapus salah catat | `/undo`, `/hapus <id>` |
| Export CSV (buka di Excel) | `/export` |
| Rekap otomatis tiap hari | scheduler |

**Parser input** mendukung `18rb`, `18rb`, `18 ribu`, `18k`, `5jt`, `5 juta`,
`1,5jt`, `2.5jt`, `25.000`, `Rp 25.000`, `+500rb`, `-100rb`.

---

## 2. Mulai cepat

### 2.1 Buat bot di Telegram

1. Chat [@BotFather](https://t.me/BotFather) → `/newbot` → ikuti instruksi.
2. Simpan **token** (bentuknya `123456789:AAH...`).

### 2.2 Dapatkan user ID kamu

Kirim pesan apa saja ke bot barumu, lalu buka di browser:

```
https://api.telegram.org/bot<TOKEN>/getUpdates
```

Cari `"from":{"id": 123456789` — itu user ID kamu.

### 2.3 Install

```powershell
cd C:\Users\RAZZ\source\repos\finance-bot
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2.4 Konfigurasi

```powershell
Copy-Item .env.example .env
notepad .env
```

Isi minimal dua baris:

```ini
BOT_TOKEN=123456789:AAH...
TELEGRAM_OWNER_ID=123456789
```

### 2.5 Jalankan

```powershell
python -m bot.main
```

Lalu kirim `/start` ke bot. Selesai.

---

## 3. Konfigurasi lengkap

| Variabel | Default | Keterangan |
|---|---|---|
| `BOT_TOKEN` | — | **wajib**, dari @BotFather |
| `TELEGRAM_OWNER_ID` | — | **wajib**, whitelist user. Bisa lebih dari satu, pisah koma |
| `TIMEZONE` | `Asia/Jakarta` | zona waktu untuk tanggal & rekap |
| `RECAP_HOUR` | `21` | jam kirim rekap harian (0–23). `0` = mati |
| `DB_PATH` | `data/finance.db` | lokasi database |
| `DATA_DIR` | `data` | folder data (backup, export) |
| `BACKUP_ENABLED` | `true` | backup harian otomatis jam 03:00 |
| `BACKUP_KEEP` | `7` | jumlah backup yang disimpan |
| `DEBUG` | `false` | log verbose |

> ⚠️ **`TELEGRAM_OWNER_ID` wajib diisi.** Tanpa whitelist, siapa pun yang
> menemukan bot kamu bisa menulis ke database. Bot menolak start tanpa nilai ini.

---

## 4. Perintah

### Mencatat
```
/keluar 25000 makan siang
/masuk 5000000 gaji oktober
kopi 18rb                       ← teks bebas, paling cepat
makan 35k @Makan                ← @NamaKategori memaksa kategori
kemarin bensin 25000
-100rb donasi                   ← tanda - paksa pengeluaran
+500rb jual motor               ← tanda + paksa pemasukan
```

### Melihat
```
/saldo                saldo, ringkasan bulan ini
/laporan              laporan bulan ini
/laporan 2026-09      bulan tertentu
/laporan september    nama bulan
/laporan bulan lalu
/rekap                rekap hari ini
/terakhir 5           lima transaksi terakhir
/cari kopi            cari transaksi
/histori              tren 6 bulan
```

### Merapikan
```
/undo                 hapus transaksi terakhir
/hapus 42             hapus transaksi #42
/kategori             daftar kategori
/kategori tambah keluar Kopi ☕ kopi,latte,espresso
/kategori kw Kopi kopi,latte
/kategori hapus Kopi  (hanya kalau belum dipakai)
/budget set Makan 1500000
/budget
/budget hapus Makan
/export               CSV bulan ini
```

### Anggaran
Setelah transaksi, bot otomatis memberi peringatan bila kategori sudah
terpakai ≥80% atau melewati batas.

---

## 5. Struktur project

```
finance-bot/
├── bot/
│   ├── main.py           entry point, dispatcher, scheduler
│   ├── config.py         baca & validasi .env
│   ├── db.py             engine SQLite
│   ├── models.py         tabel SQLModel
│   ├── parser.py         "18rb" → 18000  ← paling banyak logika
│   ├── timeutil.py       konversi timezone (UTC ⇄ lokal)
│   ├── formatting.py     format Rupiah & pesan HTML
│   ├── ledger.py         query: saldo, laporan, anggaran, export
│   ├── middlewares.py    auth whitelist, session, error handling
│   ├── services_defaults.py  seed user & kategori awal
│   ├── handlers/         misc, transactions, reports, categories, budgets
│   └── jobs/             rekap.py, backup.py
├── tests/                128 test (unit + end-to-end)
├── scripts/              demo_report.py, smoke_boot.py, backup.ps1
├── requirements.txt
└── .env.example
```

---

## 6. Testing

```powershell
# semua test (184 test)
python -m pytest

# hanya parser (cepat, tanpa database)
python -m pytest tests/test_parser.py -v

# test regresi bug yang pernah ditemukan
python -m pytest tests/test_regression.py -v
```

Test mencakup **end-to-end**: menjalankan dispatcher aiogram sungguhan dengan
Telegram palsu, jadi alur `pesan masuk → parse → simpan → balas` ikut diuji.

### QA probe (audit mandiri)

Skrip di `scripts/qa_*.py` adalah audit adversarial — mencari bug, bukan
membuktikan kode benar. Jalankan semuanya:

```powershell
python scripts/qa_probe.py            # parser & nominal
python scripts/qa_probe_db.py         # integritas & konsistensi angka
python scripts/qa_probe_message.py    # HTML valid & batas 4096 char
python scripts/qa_probe_kategori.py   # akurasi klasifikasi kategori
python scripts/qa_probe_robust.py     # pesan beruntun, DB terkunci, input aneh
python scripts/qa_probe_boot_real.py  # bot start nyata & shutdown bersih
```

Semua harus melaporkan `TOTAL TEMUAN: 0` dan `AKURASI: 100.0%`.

### Alat bantu lain

```powershell
python scripts/demo_report.py        # lihat contoh laporan tanpa Telegram
python scripts/smoke_boot.py         # cek bot bisa boot (tanpa jaringan)
python scripts/simulate_session.py   # simulasi sesi pemakaian nyata
python scripts/probe_parser.py       # uji parser dengan kalimat sehari-hari
```

---

## 7. Deploy

### Opsi A — PC sendiri (gratis)

Supaya bot tetap hidup setelah terminal ditutup, jalankan lewat Task Scheduler:

```powershell
schtasks /create /tn "FinanceBot" /tr "C:\Users\RAZZ\source\repos\finance-bot\.venv\Scripts\python.exe -m bot.main" /sc onstart /ru SYSTEM
```

Catatan: PC harus menyala dan tidak sleep.

### Opsi B — VPS Linux (disarankan)

```bash
sudo apt update && sudo apt install -y python3-venv
cd /opt && sudo git clone <repo> finance-bot && cd finance-bot
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env && nano .env
```

`/etc/systemd/system/finance-bot.service`:

```ini
[Unit]
Description=Finance Telegram Bot
After=network-online.target

[Service]
Type=simple
User=financebot
WorkingDirectory=/opt/finance-bot
ExecStart=/opt/finance-bot/.venv/bin/python -m bot.main
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now finance-bot
sudo journalctl -u finance-bot -f      # lihat log
```

---

## 8. Backup

**Otomatis:** job harian jam 03:00 menyimpan `data/backups/finance-*.db`,
menyimpan `BACKUP_KEEP` file terakhir.

**Manual:**

```powershell
.\scripts\backup.ps1
```

Restore:

```powershell
Stop-Process -Name python    # hentikan bot dulu
Copy-Item data\backups\finance-20261020-030000.db data\finance.db -Force
python -m bot.main
```

> File `.db` adalah seluruh riwayat keuanganmu. Jangan commit ke Git
> (sudah masuk `.gitignore`).

---

## 9. Catatan teknis

- **Uang disimpan sebagai integer rupiah** (`25000`, bukan `25000.0`) — tidak
  ada error pembulatan.
- **Waktu disimpan sebagai UTC** di database, ditampilkan dalam `TIMEZONE`.
  Transaksi jam 00:30 WIB tetap tercatat di tanggal yang benar.
- **Anti dobel**: `message_id` unik per user. Kalau Telegram mengirim ulang
  update yang sama, transaksi tidak tercatat dua kali.
- **Hanya boleh satu instance bot.** Dua proses polling membuat update
  rebutan dan transaksi ganda.
- **SQLite + WAL** cukup untuk puluhan ribu transaksi. Kalau nanti butuh
  multi-user berat, pindah ke PostgreSQL (skema sudah siap).

---

## 10. Troubleshooting

| Masalah | Penyebab & solusi |
|---|---|
| `BOT_TOKEN belum diisi` | `.env` belum ada. `Copy-Item .env.example .env` lalu isi |
| `Format BOT_TOKEN tidak valid` | Ada spasi/kutip. Harus `123456789:AAH...` |
| `TELEGRAM_OWNER_ID wajib diisi` | Isi dengan user ID angka dari `getUpdates` |
| Bot diam saja | Cek `python -m bot.main` masih jalan; lihat log |
| `Conflict: terminated by other getUpdates` | Ada 2 instance bot. Tutup salah satu |
| Akses ditolak | User ID kamu tidak cocok dengan `TELEGRAM_OWNER_ID` |
| Bot mati saat PC sleep | Normal. Pakai VPS atau atur power plan |

---

## Lisensi

MIT — bebas dipakai dan diubah untuk keperluan pribadi.

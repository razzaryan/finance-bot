# 📖 Tutorial Lengkap — Finance Bot

Panduan dari nol sampai bisa dipakai sehari-hari. Ikuti berurutan.

---

## Daftar Isi

1. [Sebelum mulai](#1-sebelum-mulai)
2. [Membuat bot di Telegram](#2-membuat-bot-di-telegram)
3. [Mendapatkan User ID](#3-mendapatkan-user-id)
4. [Instalasi](#4-instalasi)
5. [Konfigurasi](#5-konfigurasi)
6. [Menjalankan](#6-menjalankan)
7. [Cara mencatat transaksi](#7-cara-mencatat-transaksi)
8. [Cara melihat laporan](#8-cara-melihat-laporan)
9. [Mengatur anggaran](#9-mengatur-anggaran)
10. [Mengelola kategori](#10-mengelola-kategori)
11. [Export ke Excel](#11-export-ke-excel)
12. [Menjalankan otomatis 24 jam](#12-menjalankan-otomatis-24-jam)
13. [Backup & restore](#13-backup--restore)
14. [Resep pemakaian harian](#14-resep-pemakaian-harian)
15. [Pertanyaan umum](#15-pertanyaan-umum)
16. [Jika ada masalah](#16-jika-ada-masalah)

---

## 1. Sebelum mulai

Yang kamu butuhkan:

| Kebutuhan | Keterangan |
|---|---|
| Akun Telegram | di HP atau desktop |
| Python 3.11+ | sudah terpasang di mesin ini (3.13) |
| Waktu | ±10 menit untuk setup awal |

Konsep penting: bot ini **privat**. Hanya user ID yang kamu daftarkan yang
bisa memakainya. Orang lain akan ditolak.

---

## 2. Membuat bot di Telegram

1. Buka Telegram, cari **@BotFather** (yang ada centang biru).
2. Kirim `/newbot`.
3. BotFather bertanya **nama bot** → balas bebas, misal `Keuangan Razz`.
4. BotFather bertanya **username** → harus diakhiri `bot`, misal
   `razz_keuangan_bot`. Kalau ditolak, coba nama lain.
5. BotFather membalas sesuatu seperti:

```
Done! Congratulations on your new bot. You will find it at
t.me/razz_keuangan_bot

Use this token to access the HTTP API:
7123456789:AAHk3J9xQwErTyUiOpAsDfGhJkLzXcVbNm0
```

**Simpan token itu.** Bentuknya angka, titik dua, lalu 35 karakter acak.
Token = kunci bot kamu. Jangan dibagikan ke siapa pun.

> ⚠️ Kalau token bocor: chat @BotFather → `/revoke` → pilih bot → dapat token
> baru. Token lama langsung mati.

---

## 3. Mendapatkan User ID

Bot perlu tahu siapa pemiliknya.

**Cara 1 — lewat browser (paling mudah)**

1. Kirim pesan apa saja ke bot barumu (misal `halo`).
2. Buka di browser, ganti `<TOKEN>` dengan token kamu:

```
https://api.telegram.org/bot<TOKEN>/getUpdates
```

Contoh hasil:

```json
{"ok":true,"result":[{"update_id":123,"message":{"message_id":1,
"from":{"id":7123456789,"is_bot":false,"first_name":"Razz"},
"text":"halo"}}]}
```

Angka di `"from":{"id": ...}` itulah **User ID** kamu. Catat.

**Cara 2 — lewat bot lain**

Cari **@userinfobot** di Telegram, kirim pesan apa saja, langsung dibalas
User ID kamu.

---

## 4. Instalasi

Buka PowerShell:

```powershell
cd C:\Users\RAZZ\source\repos\finance-bot

# buat virtual environment (sekali saja)
python -m venv .venv

# aktifkan
.\.venv\Scripts\Activate.ps1

# install dependensi
pip install -r requirements.txt
```

Kalau PowerShell menolak dengan pesan *"running scripts is disabled"*, jalankan
sekali:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

> Tidak perlu aktivasi venv? Bisa juga langsung:
> `.\.venv\Scripts\python.exe -m bot.main`

---

## 5. Konfigurasi

```powershell
Copy-Item .env.example .env
notepad .env
```

Isi seperti ini:

```ini
BOT_TOKEN=7123456789:AAHk3J9xQwErTyUiOpAsDfGhJkLzXcVbNm0
TELEGRAM_OWNER_ID=7123456789

TIMEZONE=Asia/Jakarta
RECAP_HOUR=21
```

Penjelasan tiap baris:

| Baris | Arti | Contoh |
|---|---|---|
| `BOT_TOKEN` | token dari BotFather | wajib |
| `TELEGRAM_OWNER_ID` | User ID kamu (boleh beberapa, pisah koma) | wajib |
| `TIMEZONE` | zona waktu untuk tanggal & rekap | `Asia/Jakarta` |
| `RECAP_HOUR` | jam kirim rekap harian, `0` = matikan | `21` = 21:00 |
| `BACKUP_ENABLED` | backup otomatis harian jam 03:00 | `true` |
| `BACKUP_KEEP` | jumlah backup disimpan | `7` |

> **Uji cepat:** kalau ada yang salah, bot akan menolak start dan memberi tahu
> persis apa masalahnya. Contoh: `BOT_TOKEN belum diisi...`

---

## 6. Menjalankan

```powershell
.\.venv\Scripts\Activate.ps1
python -m bot.main
```

Yang muncul kalau berhasil:

```
Database siap: ...\data\finance.db
Bot @razz_keuangan_bot siap. Owner: (7123456789,)
```

Buka bot kamu di Telegram, kirim `/start`. Bot membalas dengan sapaan +
daftar command. **Setup selesai.**

> Biarkan jendela PowerShell tetap terbuka. Kalau ditutup, bot mati.
> Untuk jalan 24 jam, lihat [bagian 12](#12-menjalankan-otomatis-24-jam).

---

## 7. Cara mencatat transaksi

Inti bot ini: **cukup ketik apa yang kamu belanjakan.** Tidak perlu command.

### 7.1 Format dasar

```
<keterangan> <nominal>
```

Contoh:

```
kopi 18rb        → 🔴 Keluar · 🍜 Makan · Rp 18.000
makan siang 35k  → 🔴 Keluar · 🍜 Makan · Rp 35.000
```

### 7.2 Nominal: semua gaya diterima

| Kamu ketik | Dibaca sebagai |
|---|---|
| `18rb` | 18.000 |
| `18 rb` | 18.000 |
| `18ribu` | 18.000 |
| `18k` | 18.000 |
| `18RB` | 18.000 (huruf besar aman) |
| `5jt` | 5.000.000 |
| `5 juta` | 5.000.000 |
| `1,5jt` | 1.500.000 |
| `2.5jt` | 2.500.000 |
| `25.000` | 25.000 |
| `1.500.000` | 1.500.000 |
| `Rp 25.000` | 25.000 |
| `Rp25.000` | 25.000 |
| `25000` | 25.000 |
| `kopi18rb` | 18.000 (tanpa spasi juga bisa) |

### 7.3 Pemasukan vs pengeluaran

Bot menebak dari kata yang kamu pakai:

| Kata pemicu pemasukan | Kata pemicu pengeluaran |
|---|---|
| gaji, gajian, bonus, thr, komisi, honor | beli, bayar, jajan, tagihan |
| jual, terjual, terima, dapat, dikasih | cicilan, sewa, sedekah, donasi |
| dividen, bunga, cashback, refund, profit | isi, topup, transfer |

```
gaji 7.5jt              → 🟢 Masuk · 💼 Gaji
terima transfer 200rb   → 🟢 Masuk
bayar listrik 250rb     → 🔴 Keluar · 🧾 Tagihan
```

**Mau paksa?** Pakai tanda di depan:

```
+500rb jual motor   → tanda + = pasti pemasukan
-100rb donasi       → tanda - = pasti pengeluaran
```

Atau pakai command:

```
/keluar 25000 makan siang
/masuk 5000000 gaji oktober
```

### 7.4 Tanggal: mencatat yang kemarin

```
kemarin bensin 25.000      → tanggal kemarin
3 hari lalu beli buku 120rb → 3 hari ke belakang
beli 2026-10-02 sepatu 350rb → tanggal spesifik
makan 05/10 50rb            → 5 Oktober
```

Kalau tidak menyebut tanggal, dianggap **hari ini**.

### 7.5 Memaksa kategori

Bot menebak kategori dari kata kunci. Kalau salah, timpa dengan `@NamaKategori`:

```
makan siang 35k @Makan
beli kado 200rb @Hadiah
jajan anak 50rb @Belanja
```

Kalau kategori tidak ada, bot memberi tahu pilihan yang tersedia.

### 7.6 Yang terjadi setelah mencatat

Bot membalas konfirmasi dalam format:

```
✅ Tercatat
🔴 Keluar · 🍜 Makan
−Rp 18.000 — kopi
📅 hari ini 14:30 · #12
```

`#12` adalah ID transaksi — berguna untuk `/hapus`.

Kalau anggaran kategori itu sudah ≥80%, bot menambah peringatan:

```
⚠️ Anggaran Makan terpakai 85%. Sisa Rp 300.000.
```

### 7.7 Salah catat? Perbaiki

```
/undo          hapus transaksi terakhir (paling sering dipakai)
/hapus 12      hapus transaksi #12
/terakhir      lihat 10 transaksi terakhir + ID-nya
```

`/undo` adalah pertolongan pertama kalau kamu salah ketik nominal.

### 7.8 Bot tidak akan salah paham

Kalau kamu kirim teks tanpa angka (`halo bot`, `apa kabar`), bot tidak
mencatat apa pun — hanya mengingatkan format yang benar. Jadi aman untuk
mengobrol singkat.

---

## 8. Cara melihat laporan

### 8.1 Saldo

```
/saldo
```

```
💰 Saldo
━━━━━━━━━━━━━━━━━━
Rp 5.724.500

📅 November 2026
Masuk   Rp 7.700.000
Keluar  Rp 1.975.500
Selisih Rp 5.724.500

Total 7 transaksi tercatat.
```

### 8.2 Laporan bulanan

```
/laporan
```

```
📊 Laporan November 2026
━━━━━━━━━━━━━━━━━━
Masuk   Rp 7.700.000
Keluar  Rp 1.975.500
Sisa    Rp 5.724.500
━━━━━━━━━━━━━━━━━━
🔴 Pengeluaran terbesar
• 🛒 Belanja — Rp 1.897.500 (96%)
• 🍜 Makan — Rp 53.000 (3%)
• 🛵 Transport — Rp 25.000 (1%)

🟢 Sumber pemasukan
• 💼 Gaji — Rp 7.500.000 (97%)
• ➕ Lainnya — Rp 200.000 (3%)

📝 7 transaksi
vs bulan lalu: keluar turun 3% ✅
```

Pilih bulan lain:

```
/laporan 2026-09        tahun-bulan
/laporan september      nama bulan (tahun berjalan)
/laporan okt 2025       singkatan + tahun
/laporan bulan lalu
/laporan 9               bulan ke-9 tahun ini
```

### 8.3 Rekap hari ini

```
/rekap
```

Menampilkan semua transaksi hari ini + status anggaran yang mendekati batas.

### 8.4 Riwayat & pencarian

```
/terakhir       10 transaksi terakhir
/terakhir 30    30 transaksi terakhir (maks 30)
/cari kopi      semua transaksi yang catatannya mengandung "kopi"
/histori        tren 6 bulan terakhir
```

`/cari` berguna saat kamu lupa kapan terakhir beli sesuatu.

---

## 9. Mengatur anggaran

Anggaran = batas pengeluaran bulanan per kategori. Bot memberi peringatan
otomatis saat mendekati/melewati batas.

### 9.1 Set anggaran

```
/budget set Makan 1500000
/budget set Transport 500rb
/budget set Tagihan 1.2jt
```

### 9.2 Lihat status

```
/budget
```

```
🎯 Anggaran November 2026
━━━━━━━━━━━━━━━━━━
⚠️ 🍜 Makan
   ▰▰▰▰▰▰▰▰▰▱ 90%
   Rp 1.800.000 / Rp 2.000.000 · sisa Rp 200.000

✅ 🛵 Transport
   ▰▰▰▰▱▱▱▱▱▱ 40%
   Rp 200.000 / Rp 500.000 · sisa Rp 300.000

Total ▰▰▰▰▰▰▰▱▱▱ 80%
Rp 2.000.000 / Rp 2.500.000
```

Arti ikon: ✅ aman · ⚠️ ≥80% · 🚨 sudah lewat.

### 9.3 Hapus anggaran

```
/budget hapus Makan
```

---

## 10. Mengelola kategori

### 10.1 Lihat semua

```
/kategori
```

### 10.2 Tambah kategori sendiri

```
/kategori tambah keluar Kopi ☕ kopi,latte,espresso,americano
```

Format: `/kategori tambah <keluar|masuk> <Nama> [emoji] [keyword,keyword]`

Setelah itu, `kopi 18rb` otomatis masuk kategori **Kopi**, bukan Makan.

### 10.3 Ubah keyword

```
/kategori kw Kopi kopi,latte,espresso,cappuccino
```

### 10.4 Hapus kategori

```
/kategori hapus Kopi
```

Hanya bisa kalau kategori itu belum dipakai transaksi. Kalau sudah dipakai,
bot menolak dan memberi tahu jumlah transaksinya.

### 10.5 Kategori bawaan

**Pengeluaran (12):** Makan, Transport, Belanja, Tagihan, Kesehatan,
Pendidikan, Hiburan, Cicilan, Sedekah, Rumah, Perawatan Diri, Lain-lain

**Pemasukan (8):** Gaji, Bonus, Freelance, Bisnis, Investasi, Penjualan,
Hadiah, Lainnya

Tidak perlu dibuat — sudah otomatis saat `/start`.

---

## 11. Export ke Excel

### 11.1 File CSV otomatis (fitur baru)

Kamu **tidak perlu** menjalankan apa pun. Setiap kali mencatat transaksi, bot
langsung menambahkan baris ke file:

```
data/exports/ledger-<telegram_id>.csv
```

Buka file itu di Excel kapan saja — isinya selalu data terbaru. Kalau kamu
`/undo` atau `/hapus`, baris di file ikut terhapus otomatis.

Format kolom: `id, tanggal, jenis, kategori, akun, nominal, catatan`

Mau unduh lewat Telegram?

```
/ledger
```

Bot mengirim file CSV lengkap (semua transaksi, semua bulan).

### 11.2 Export per bulan

```
/export            bulan ini
/export 2026-09    bulan tertentu
```

Bot mengirim file `keuangan-2026-11.csv`. Berguna untuk arsip bulanan atau
laporan ke atasan/pasangan.

### 11.3 Catatan keamanan CSV

Kalau catatan transaksi diawali `=`, `+`, `-`, atau `@`, bot menambahkan tanda
`'` di depan saat menulis CSV. Ini mencegah Excel menjalankan isi sel sebagai
formula (dikenal sebagai *CSV injection*). Di Excel kamu tetap melihat teks
aslinya.

---

## 12. Menjalankan otomatis 24 jam

### Opsi A — PC sendiri, jalan saat startup (gratis)

Supaya bot hidup tanpa perlu buka PowerShell:

```powershell
schtasks /create /tn "FinanceBot" ^
  /tr "C:\Users\RAZZ\source\repos\finance-bot\.venv\Scripts\python.exe -m bot.main" ^
  /sc onstart /ru SYSTEM
```

Batasan: PC harus menyala dan tidak sleep. Atur di
*Settings → System → Power → Sleep* menjadi **Never**.

Cek status:

```powershell
schtasks /query /tn "FinanceBot"
```

Hentikan:

```powershell
schtasks /end /tn "FinanceBot"
```

### Opsi B — VPS (rekomendasi, ±Rp30-60rb/bulan)

Bot hidup 24/7 walau laptop mati, dan rekap harian selalu terkirim.

```bash
sudo apt update && sudo apt install -y python3-venv git
cd /opt
sudo git clone https://github.com/razzaryan/finance-bot.git
sudo chown -R $USER:$USER finance-bot
cd finance-bot
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
nano .env          # isi BOT_TOKEN & TELEGRAM_OWNER_ID
```

Buat service `/etc/systemd/system/finance-bot.service`:

```ini
[Unit]
Description=Finance Telegram Bot
After=network-online.target

[Service]
Type=simple
User=ubuntu
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
sudo journalctl -u finance-bot -f      # lihat log real-time
```

---

## 13. Backup & restore

Database kamu = satu file: `data/finance.db`. Isinya **seluruh riwayat
keuangan**. Jangan sampai hilang.

### 13.1 Otomatis

Kalau `BACKUP_ENABLED=true`, bot menyimpan backup setiap hari jam 03:00 ke
`data/backups/finance-YYYYMMDD-HHMMSS.db`, menyimpan 7 terakhir.

### 13.2 Manual

```powershell
.\scripts\backup.ps1
```

### 13.3 Restore (kalau data rusak / pindah komputer)

```powershell
# 1. hentikan bot dulu
Stop-Process -Name python -ErrorAction SilentlyContinue

# 2. lihat backup yang ada
Get-ChildItem data\backups

# 3. timpa database dengan backup
Copy-Item data\backups\finance-20261108-030000.db data\finance.db -Force

# 4. jalankan lagi
python -m bot.main
```

### 13.4 Pindah ke komputer/VPS lain

```powershell
# di komputer lama: copy folder data
scp -r data/ user@server:/opt/finance-bot/
```

Yang perlu dibawa: `data/finance.db` (dan `.env`).

---

## 14. Resep pemakaian harian

**Pagi — catat sarapan & transport**
```
sarapan 15rb
gojek kantor 23rb
```

**Siang**
```
makan siang 35k
```

**Sore — terima uang**
```
terima transfer 200rb dari budi
```

**Malam — cek**
```
/rekap
```

**Akhir bulan — evaluasi**
```
/laporan
/export
```

**Kebiasaan bagus:** catat langsung setelah transaksi terjadi, selagi ingat.
Bot membalas dalam hitungan detik, tidak perlu buka aplikasi lain.

---

## 15. Pertanyaan umum

**Q: Apakah data saya aman?**
A: Data hanya ada di komputer/VPS kamu (`data/finance.db`). Tidak dikirim ke
mana pun kecuali Telegram (untuk pesan bot). Tidak ada server pihak ketiga.

**Q: Orang lain bisa pakai bot saya?**
A: Tidak. Hanya `TELEGRAM_OWNER_ID` yang diizinkan. Yang lain dibalas
"Bot ini privat. Akses ditolak."

**Q: Bisa dipakai berdua dengan pasangan?**
A: Bisa. Tambahkan ID-nya: `TELEGRAM_OWNER_ID=111,222`. Tapi **data jadi
satu** — tidak dipisah per orang. Untuk pembukuan terpisah, jalankan instance
kedua dengan `DB_PATH` berbeda.

**Q: Kalau saya kirim pesan yang sama dua kali?**
A: Yang kedua diabaikan. Bot mengenali ID pesan, jadi tidak ada transaksi dobel.

**Q: Nominal desimal, misal Rp 18.500,50?**
A: Bot membulatkan ke rupiah penuh. Uang disimpan sebagai bilangan bulat untuk
menghindari error pembulatan di laporan.

**Q: Bisa lihat tahun lalu?**
A: Bisa: `/laporan 2025-12`, atau `/laporan desember 2025`.

**Q: Bot mati, data hilang?**
A: Tidak. Data ada di file `data/finance.db`. Jalankan lagi, data utuh —
sudah diuji (test `test_data_bertahan_setelah_restart`).

**Q: Bagaimana kalau tidak tahu kategori yang cocok?**
A: Biarkan. Bot taruh di "Lain-lain". Nanti bisa dirapikan, atau paksa dengan
`@NamaKategori`.

**Q: Bisa hapus semua data dan mulai dari nol?**
A: Hentikan bot, hapus `data/finance.db`, jalankan lagi, `/start` ulang.

---

## 16. Jika ada masalah

### Bot tidak membalas sama sekali

1. Cek PowerShell-nya: apakah masih ada tulisan log berjalan?
2. Kalau jendela tertutup, bot mati. Jalankan lagi.
3. Kalau ada pesan `Conflict: terminated by other getUpdates` — ada dua bot
   jalan bersamaan. Tutup salah satu.

Cek satu per satu:

```powershell
# apakah proses python jalan?
Get-Process python -ErrorAction SilentlyContinue

# apakah konfigurasi valid?
.\.venv\Scripts\python.exe -c "from bot.config import load_settings; s=load_settings(); print('OK', s.owner_ids)"
```

### Pesan error saat start

| Pesan | Artinya | Solusi |
|---|---|---|
| `BOT_TOKEN belum diisi` | `.env` belum ada / kosong | buat `.env` dari `.env.example` |
| `Format BOT_TOKEN tidak valid` | ada spasi/kutip | hapus tanda kutip, tidak boleh ada spasi |
| `TELEGRAM_OWNER_ID wajib diisi` | belum isi ID | lihat [bagian 3](#3-mendapatkan-user-id) |
| `TELEGRAM_OWNER_ID berisi nilai tidak valid` | diisi huruf | harus angka |
| `TIMEZONE tidak valid` | salah tulis | pakai `Asia/Jakarta` |
| `RECAP_HOUR harus angka 0-23` | di luar rentang | `21` untuk jam 21:00 |

### Bot membalas "Akses ditolak"

User ID kamu tidak cocok dengan `TELEGRAM_OWNER_ID`. Cek dengan `/id` di bot
(kalau kamu sudah terdaftar) atau lewat `getUpdates`.

### Bot membalas "Nominal tidak terbaca"

Tidak ada angka di pesan. Contoh benar: `kopi 18rb`, `makan 25000`.

### Angka tercatat salah

Cek formatmu: `18rb` = 18.000, bukan 18. Kalau salah catat, `/undo` lalu
ketik ulang.

### Kategori selalu "Lain-lain"

Kata yang kamu pakai belum ada di keyword. Perbaiki permanen:

```
/kategori kw NamaKategori kata1,kata2,kata3
```

Atau paksa saat mencatat: `teh 5rb @Makan`.

### `/export` bilang tidak ada transaksi

Bulan yang dipilih kosong. Pastikan format: `/export 2026-11`, atau `/export`
untuk bulan berjalan.

### Data ingin dipindah ke komputer lain

Copy `data/finance.db` dan `.env`. Selesai.

---

## Ringkasan command

| Command | Fungsi |
|---|---|
| *(teks bebas)* | catat transaksi — cara tercepat |
| `/start` | mulai, buat akun & kategori |
| `/help` | bantuan |
| `/keluar <teks>` | catat pengeluaran |
| `/masuk <teks>` | catat pemasukan |
| `/saldo` | saldo + ringkasan bulan ini |
| `/laporan [bulan]` | laporan bulanan |
| `/rekap` | rekap hari ini |
| `/terakhir [n]` | transaksi terakhir |
| `/cari <kata>` | cari transaksi |
| `/histori` | tren 6 bulan |
| `/undo` | hapus transaksi terakhir |
| `/hapus <id>` | hapus transaksi tertentu |
| `/kategori` | kelola kategori |
| `/budget` | kelola anggaran |
| `/export [bulan]` | unduh CSV |
| `/ledger` | unduh CSV semua transaksi |
| `/id` | lihat user ID kamu |

---

Selamat memakai! 🎉

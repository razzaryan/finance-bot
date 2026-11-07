"""Setup user baru: akun default + kategori bawaan.

Keyword di sini menentukan akurasi klasifikasi otomatis. Daftar dibuat untuk
pengeluaran sehari-hari Indonesia: kata benda (makanan, bahan), merek umum
(gojek, indomaret), dan sinonim.
"""

from __future__ import annotations

from sqlmodel import Session

from bot.models import Account, Category, User

DEFAULT_ACCOUNTS: list[tuple[str, str]] = [
    ("Dompet", "cash"),
]

DEFAULT_EXPENSE_CATEGORIES: list[tuple[str, str, str]] = [
    (
        "Makan",
        "🍜",
        "makan,minum,kopi,teh,jus,boba,susu,sarapan,siang,malam,jajan,snack,"
        "cemilan,camilan,kue,roti,martabak,sate,bakso,mie,nasi,ayam,soto,"
        "pecel,rawon,gado,warung,warteg,resto,restoran,cafe,kafe,ngopi,"
        "gofood,grabfood,shopeefood,es,boba,bubble,donat,pizza,burger,"
        "kentang,seblak,cilok,pangsit,siomay,ketoprak,bubur",
    ),
    (
        "Transport",
        "🛵",
        "bensin,pertalite,pertamax,pertamina,solar,transport,ojek,gojek,grab,"
        "maxim,taksi,angkot,bus,kereta,mrt,lrt,krl,tol,parkir,servis,tambal,"
        "ban,oli,tarif,travel,pesawat,tiket,tambalban,bengkel,stnk,pajak",
    ),
    (
        "Belanja",
        "🛒",
        "belanja,beli,indomaret,alfamart,supermarket,minimarket,pasar,"
        "sembako,sayur,buah,beras,telur,gula,minyak,garam,tepung,galon,"
        "sabun,shampo,sampo,tissue,deterjen,sikat,odol,pasta,pembalut,"
        "popok,baju,celana,sepatu,tas,shopee,tokopedia,lazada",
    ),
    (
        "Tagihan",
        "🧾",
        "tagihan,listrik,pln,token,pulsa,paket,kuota,data,air,pdam,"
        "internet,wifi,indihome,firstmedia,tv,kabel,kos,kontrakan,sewa,"
        "langganan,iuran,netflix,spotify,youtube,vidio,disney,"
        "asuransi,bpjs,pajak,retribusi",
    ),
    (
        "Kesehatan",
        "💊",
        "obat,sehat,dokter,klinik,rumah sakit,rs,vitamin,apotek,farmasi,"
        "gym,fitness,salon,potong rambut,periksa,lab,masker",
    ),
    (
        "Pendidikan",
        "📚",
        "buku,kursus,sekolah,les,seminar,udemy,kelas,education,print,"
        "fotokopi,atk,pulpen,modul,spp,uang gedung",
    ),
    (
        "Hiburan",
        "🎮",
        "hiburan,game,nonton,bioskop,konser,liburan,travel,hotel,penginapan,"
        "wisata,tiket,topup game,steam",
    ),
    (
        "Cicilan",
        "🏦",
        "cicilan,kredit,utang,hutang,paylater,kpr,leasing,angsuran,"
        "pinjaman,spaylater,shopee paylater",
    ),
    (
        "Sedekah",
        "🤝",
        "sedekah,zakat,donasi,infaq,amal,shodaqoh,sumbangan,derma",
    ),
    (
        "Rumah",
        "🏠",
        "rumah,perbaikan,renovasi,perabot,cat,lemari,service ac,ac,kipas,"
        "lampu,gas,gass",
    ),
    (
        "Perawatan Diri",
        "💅",
        "skincare,parfum,deodoran,body,cream,serum,gunting,nail",
    ),
    ("Lain-lain", "📦", ""),
]

DEFAULT_INCOME_CATEGORIES: list[tuple[str, str, str]] = [
    ("Gaji", "💼", "gaji,gajian,salary,payroll,upah,gaji pokok"),
    ("Bonus", "🎁", "bonus,thr,insentif,reward,komisi,honor,lembur"),
    ("Freelance", "💻", "freelance,proyek,project,sampingan,client,jasa,upwork,fiverr"),
    ("Bisnis", "🏪", "bisnis,jualan,toko,usaha,omset,dagang,untung"),
    ("Investasi", "📈", "investasi,dividen,bunga,saham,reksadana,profit,trading,crypto,bibit"),
    ("Penjualan", "🛍", "jual,terjual,olx,tokped,shopee,garasi"),
    ("Hadiah", "🎀", "hadiah,kado,dikasih,diberi,arisan,warisan,menang,cashback,refund"),
    ("Lainnya", "➕", ""),
]


def ensure_user(session: Session, telegram_id: int, name: str = "") -> tuple[User, bool]:
    """Ambil user; buat beserta akun & kategori default kalau belum ada."""
    from bot.ledger import get_user

    user = get_user(session, telegram_id)
    if user is not None:
        if name and user.name != name:
            user.name = name
            session.add(user)
            session.commit()
            session.refresh(user)
        return user, False

    user = User(telegram_id=telegram_id, name=name or "")
    session.add(user)
    session.commit()
    session.refresh(user)

    for acc_name, acc_kind in DEFAULT_ACCOUNTS:
        session.add(Account(user_id=user.id, name=acc_name, kind=acc_kind))

    for cat_name, emoji, keywords in DEFAULT_EXPENSE_CATEGORIES:
        session.add(
            Category(
                user_id=user.id,
                name=cat_name,
                kind="expense",
                emoji=emoji,
                keywords=keywords,
                is_default=True,
            )
        )
    for cat_name, emoji, keywords in DEFAULT_INCOME_CATEGORIES:
        session.add(
            Category(
                user_id=user.id,
                name=cat_name,
                kind="income",
                emoji=emoji,
                keywords=keywords,
                is_default=True,
            )
        )
    session.commit()
    return user, True

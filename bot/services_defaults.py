"""Setup user baru: akun default + kategori bawaan."""

from __future__ import annotations

from sqlmodel import Session

from bot.models import Account, Category, User

DEFAULT_ACCOUNTS: list[tuple[str, str]] = [
    ("Dompet", "cash"),
]

DEFAULT_EXPENSE_CATEGORIES: list[tuple[str, str, str]] = [
    ("Makan", "🍜", "makan,minum,kopi,sarapan,siang,malam,jajan,snack,resto,warteg,warung,ngopi,cemilan,es,bakso,nasi,ayam,mie,roti,gofood,grabfood,shopeefood"),
    ("Transport", "🛵", "bensin,transport,ojek,gojek,grab,maxim,taksi,bus,kereta,mrt,lrt,krl,parkir,tol,servis,tambal,ban"),
    ("Belanja", "🛒", "belanja,beli,indomaret,alfamart,supermarket,pasar,sembako,sayur,beras,telur,minyak,galon,sabun,shampo,tissue,deterjen"),
    ("Tagihan", "🧾", "tagihan,listrik,pln,air,pdam,internet,wifi,indihome,pulsa,paket,kuota,token,tv,kos,sewa,langganan,netflix,spotify,listrik"),
    ("Kesehatan", "💊", "obat,sehat,dokter,klinik,rumah sakit,rs,vitamin,apotek,gym,fitness"),
    ("Pendidikan", "📚", "buku,kursus,sekolah,les,seminar,udemy,kelas,education"),
    ("Hiburan", "🎮", "hiburan,game,nonton,bioskop,konser,liburan,travel,hotel,tiket,wisata,spotify,youtube"),
    ("Cicilan", "🏦", "cicilan,kredit,utang,hutang,paylater,kpr,leasing,angsuran"),
    ("Transfer", "🔁", "transfer,tf,topup,isi saldo"),
    ("Sedekah", "🤝", "sedekah,zakat,donasi,infaq,amal,shodaqoh"),
    ("Rumah", "🏠", "rumah,kos,kontrakan,perbaikan,renovasi,perabot,galon,gas"),
    ("Lain-lain", "📦", ""),
]

DEFAULT_INCOME_CATEGORIES: list[tuple[str, str, str]] = [
    ("Gaji", "💼", "gaji,gajian,salary,payroll,upah"),
    ("Bonus", "🎁", "bonus,thr,insentif,reward,komisi,honor"),
    ("Freelance", "💻", "freelance,proyek,project,sampingan,client,jasa"),
    ("Bisnis", "🏪", "bisnis,jualan,toko,usaha,omset,dagang"),
    ("Investasi", "📈", "investasi,dividen,bunga,saham,reksadana,profit,trading,crypto"),
    ("Penjualan", "🛍", "jual,terjual,olx,tokped,shopee"),
    ("Hadiah", "🎀", "hadiah,kado,dikasih,diberi,arisan,warisan,menang"),
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

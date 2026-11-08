"""Test layanan desktop: semua aturan bisnis tanpa membuka jendela."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

import pytest

from bot.ledger import LedgerError
from bot.models import TYPE_EXPENSE, TYPE_INCOME
from bot.parser import ParseError
from bot.timeutil import local_now, month_bounds
from desktop.service import LedgerService, LOCAL_TELEGRAM_ID


@pytest.fixture()
def svc(tmp_path):
    service = LedgerService(tmp_path / "finance.db", tmp_path / "exports")
    yield service
    service.close()


# ---------------------------------------------------------------- dasar


def test_database_dibuat_di_lokasi_yang_diberikan(tmp_path):
    path = tmp_path / "sub" / "finance.db"
    service = LedgerService(path, tmp_path / "exports")
    try:
        assert path.exists()
    finally:
        service.close()


def test_user_dan_kategori_default_dibuat_otomatis(svc):
    assert svc.user_name() == "Saya"
    assert svc.accounts()
    expense = svc.categories(TYPE_EXPENSE)
    income = svc.categories(TYPE_INCOME)
    assert len(expense) >= 10
    assert len(income) >= 7


def test_catat_teks_bebas_dan_tebakan_kategori(svc):
    outcome = svc.add_from_text("kopi 18rb")
    assert outcome.row.amount == 18_000
    assert outcome.row.kind == TYPE_EXPENSE
    assert "Makan" in outcome.row.category
    assert outcome.row.note == "kopi"
    assert outcome.date_label == "hari ini"


def test_catat_pemasukan(svc):
    outcome = svc.add_from_text("gaji 5jt")
    assert outcome.row.amount == 5_000_000
    assert outcome.row.kind == TYPE_INCOME
    assert "Gaji" in outcome.row.category


def test_tanggal_relatif_dihormati(svc):
    outcome = svc.add_from_text("kemarin bensin 25rb")
    today = local_now(svc.tz).date()
    assert outcome.row.when.date() == today - timedelta(days=1)
    assert outcome.date_label == "kemarin"


def test_teks_tanpa_nominal_ditolak(svc):
    with pytest.raises(ParseError):
        svc.add_from_text("makan siang")


def test_nominal_terlalu_besar_ditolak(svc):
    with pytest.raises(ParseError):
        svc.add_from_text("beli rumah 9999999999999")


# ---------------------------------------------------------------- manual


def _expense_category(svc):
    return next(c for c in svc.categories(TYPE_EXPENSE) if c.name == "Makan")


def _income_category(svc):
    return next(c for c in svc.categories(TYPE_INCOME) if c.name == "Gaji")


def test_tambah_manual(svc):
    category = _expense_category(svc)
    account_id = svc.accounts()[0][0]
    row = svc.add_manual(
        kind=TYPE_EXPENSE,
        amount=25_000,
        category_id=category.id,
        note="manual",
        when_local=datetime(2026, 3, 4, 10, 30),
        account_id=account_id,
    )
    assert row.amount == 25_000
    assert row.when == datetime(2026, 3, 4, 10, 30)
    assert row.account


def test_manual_nominal_nol_ditolak(svc):
    category = _expense_category(svc)
    with pytest.raises(LedgerError):
        svc.add_manual(
            kind=TYPE_EXPENSE,
            amount=0,
            category_id=category.id,
            note="x",
            when_local=datetime(2026, 3, 4, 10, 0),
        )


def test_kategori_harus_sesuai_jenis(svc):
    income_category = _income_category(svc)
    with pytest.raises(LedgerError):
        svc.add_manual(
            kind=TYPE_EXPENSE,
            amount=10_000,
            category_id=income_category.id,
            note="salah jenis",
            when_local=datetime(2026, 3, 4, 10, 0),
        )


def test_ubah_transaksi(svc):
    outcome = svc.add_from_text("kopi 18rb")
    new_category = _income_category(svc)
    row = svc.update_transaction(
        outcome.row.id,
        kind=TYPE_INCOME,
        amount=20_000,
        category_id=new_category.id,
        note="diubah",
        when_local=datetime(2026, 4, 1, 9, 0),
    )
    assert row.kind == TYPE_INCOME
    assert row.amount == 20_000
    assert row.note == "diubah"
    assert row.when == datetime(2026, 4, 1, 9, 0)


def test_ubah_transaksi_tidak_ada(svc):
    with pytest.raises(LedgerError):
        svc.update_transaction(
            999,
            kind=TYPE_EXPENSE,
            amount=1000,
            category_id=_expense_category(svc).id,
            note="x",
            when_local=datetime(2026, 4, 1, 9, 0),
        )


def test_hapus_dan_undo(svc):
    first = svc.add_from_text("kopi 18rb")
    second = svc.add_from_text("teh 5rb")
    assert len(svc.list_transactions()) == 2

    svc.delete_transaction(first.row.id)
    assert len(svc.list_transactions()) == 1

    undone = svc.undo_last()
    assert undone is not None
    assert undone.id == second.row.id
    assert svc.list_transactions() == []

    assert svc.undo_last() is None


# ---------------------------------------------------------------- filter


def test_filter_bulan_jenis_dan_kata_kunci(svc):
    svc.add_manual(
        kind=TYPE_EXPENSE,
        amount=10_000,
        category_id=_expense_category(svc).id,
        note="makan pagi",
        when_local=datetime(2026, 5, 2, 8, 0),
    )
    svc.add_manual(
        kind=TYPE_INCOME,
        amount=500_000,
        category_id=_income_category(svc).id,
        note="bonus proyek",
        when_local=datetime(2026, 5, 3, 9, 0),
    )
    svc.add_manual(
        kind=TYPE_EXPENSE,
        amount=20_000,
        category_id=_expense_category(svc).id,
        note="makan malam",
        when_local=datetime(2026, 6, 1, 20, 0),
    )

    start, end = month_bounds(2026, 5, svc.tz)
    may = svc.list_transactions(start=start, end=end)
    assert len(may) == 2

    expenses = svc.list_transactions(kind=TYPE_EXPENSE)
    assert len(expenses) == 2

    found = svc.list_transactions(keyword="makan")
    assert len(found) == 2

    combined = svc.list_transactions(start=start, end=end, kind=TYPE_EXPENSE, keyword="pagi")
    assert len(combined) == 1


def test_kata_kunci_like_di_escape(svc):
    svc.add_from_text("kopi 18rb")
    # '%' dan '_' tidak boleh jadi wildcard SQL
    assert svc.list_transactions(keyword="%") == []
    assert svc.list_transactions(keyword="_") == []


def test_urutan_terbaru_di_atas(svc):
    svc.add_manual(
        kind=TYPE_EXPENSE,
        amount=1_000,
        category_id=_expense_category(svc).id,
        note="lama",
        when_local=datetime(2026, 1, 1, 9, 0),
    )
    svc.add_manual(
        kind=TYPE_EXPENSE,
        amount=2_000,
        category_id=_expense_category(svc).id,
        note="baru",
        when_local=datetime(2026, 2, 1, 9, 0),
    )
    rows = svc.list_transactions()
    assert rows[0].note == "baru"
    assert rows[-1].note == "lama"


# ---------------------------------------------------------------- dashboard


def test_dashboard_menghitung_saldo_dan_bulan(svc):
    svc.add_from_text("gaji 5jt")
    svc.add_from_text("kopi 18rb")

    data = svc.dashboard()
    assert data.balance == 4_982_000
    assert data.month_income == 5_000_000
    assert data.month_expense == 18_000
    assert data.total_transactions == 2
    assert len(data.today_rows) == 2
    assert data.today_expense == 18_000


def test_dashboard_kosong_tidak_error(svc):
    data = svc.dashboard()
    assert data.balance == 0
    assert data.month_income == 0
    assert data.today_rows == []
    assert data.total_transactions == 0


def test_dashboard_hanya_transaksi_hari_ini(svc):
    svc.add_manual(
        kind=TYPE_EXPENSE,
        amount=9_000,
        category_id=_expense_category(svc).id,
        note="kemarin",
        when_local=local_now(svc.tz) - timedelta(days=1),
    )
    data = svc.dashboard()
    assert data.today_rows == []
    assert data.month_expense >= 9_000 or data.month_expense == 0


# ---------------------------------------------------------------- laporan


def test_laporan_bulan(svc):
    svc.add_manual(
        kind=TYPE_EXPENSE,
        amount=100_000,
        category_id=_expense_category(svc).id,
        note="a",
        when_local=datetime(2026, 7, 2, 9, 0),
    )
    svc.add_manual(
        kind=TYPE_INCOME,
        amount=1_000_000,
        category_id=_income_category(svc).id,
        note="b",
        when_local=datetime(2026, 7, 3, 9, 0),
    )

    report = svc.month_report(2026, 7)
    assert report.label == "Juli 2026"
    assert report.income == 1_000_000
    assert report.expense == 100_000
    assert report.net == 900_000
    assert report.tx_count == 2
    assert report.top_expense[0][2] == 100_000


def test_laporan_bulan_kosong(svc):
    report = svc.month_report(2020, 1)
    assert report.income == 0
    assert report.expense == 0
    assert report.tx_count == 0
    assert report.top_expense == []


def test_history_mengembalikan_bulan_berurutan(svc):
    items = svc.history(6)
    assert len(items) == 6
    now = local_now(svc.tz)
    assert items[0][0].endswith(str(now.year))


# ---------------------------------------------------------------- anggaran


def test_anggaran_set_ubah_hapus(svc):
    category = _expense_category(svc)
    svc.set_budget(category.id, 1_000_000)
    rows = svc.budgets(2026, 1)
    assert len(rows) == 1
    assert rows[0].limit == 1_000_000
    assert rows[0].used == 0
    assert rows[0].status == "aman"

    svc.set_budget(category.id, 500_000)
    assert svc.budgets(2026, 1)[0].limit == 500_000

    svc.set_budget(category.id, 0)
    assert svc.budgets(2026, 1) == []


def test_anggaran_menghitung_pemakaian(svc):
    category = _expense_category(svc)
    svc.set_budget(category.id, 100_000)
    svc.add_manual(
        kind=TYPE_EXPENSE,
        amount=90_000,
        category_id=category.id,
        note="hampir",
        when_local=datetime(2026, 8, 5, 9, 0),
    )
    rows = svc.budgets(2026, 8)
    assert rows[0].used == 90_000
    assert rows[0].status == "hampir"
    assert rows[0].remaining == 10_000


def test_peringatan_anggaran_muncul_saat_catat(svc):
    category = _expense_category(svc)
    svc.set_budget(category.id, 20_000)
    outcome = svc.add_from_text("kopi 18rb")
    assert outcome.budget_note is not None
    assert "Anggaran" in outcome.budget_note


def test_anggaran_kategori_tidak_ada(svc):
    with pytest.raises(LedgerError):
        svc.set_budget(9999, 100_000)


def test_anggaran_negatif_ditolak(svc):
    with pytest.raises(LedgerError):
        svc.set_budget(_expense_category(svc).id, -1)


# ---------------------------------------------------------------- kategori


def test_tambah_ubah_hapus_kategori(svc):
    created = svc.add_category("Kopi", TYPE_EXPENSE, "☕", "kopi,latte")
    assert created.name == "Kopi"
    assert created.keywords == "kopi,latte"

    svc.update_category(created.id, name="Ngopi", emoji="☕", keywords="kopi")
    names = [c.name for c in svc.categories(TYPE_EXPENSE)]
    assert "Ngopi" in names
    assert "Kopi" not in names

    svc.delete_category(created.id)
    assert "Ngopi" not in [c.name for c in svc.categories(TYPE_EXPENSE)]


def test_kategori_dengan_nama_sama_ditolak(svc):
    svc.add_category("Unik", TYPE_EXPENSE, "🏷", "")
    with pytest.raises(LedgerError):
        svc.add_category("unik", TYPE_EXPENSE, "🏷", "")


def test_kategori_dipakai_tidak_bisa_dihapus(svc):
    outcome = svc.add_from_text("kopi 18rb")
    category_id = outcome.row.category_id
    with pytest.raises(LedgerError):
        svc.delete_category(category_id)


def test_ubah_kategori_ke_nama_yang_sudah_ada_ditolak(svc):
    a = svc.add_category("Aaa", TYPE_EXPENSE, "🏷", "")
    svc.add_category("Bbb", TYPE_EXPENSE, "🏷", "")
    with pytest.raises(LedgerError):
        svc.update_category(a.id, name="Bbb", emoji="", keywords="")


def test_kategori_baru_langsung_dipakai_tebakan(svc):
    svc.add_category("Kopi", TYPE_EXPENSE, "☕", "kopi,latte")
    outcome = svc.add_from_text("latte 25rb")
    assert "Kopi" in outcome.row.category


# ---------------------------------------------------------------- CSV


def test_csv_dibuat_dan_disinkron(svc):
    svc.add_from_text("kopi 18rb")
    svc.add_from_text("gaji 5jt")

    path = svc.ledger_file()
    assert path.exists()
    lines = path.read_text(encoding="utf-8-sig").strip().splitlines()
    assert len(lines) == 3  # header + 2
    assert "kopi" in lines[1] or "kopi" in lines[2]

    svc.delete_transaction(svc.list_transactions()[0].id)
    lines = path.read_text(encoding="utf-8-sig").strip().splitlines()
    assert len(lines) == 2


def test_csv_aman_dari_formula_injection(svc):
    svc.add_from_text("=cmd|'/c calc'!A1 5000")
    text = svc.ledger_file().read_text(encoding="utf-8-sig")
    assert "'=cmd" in text
    assert ",=cmd" not in text


def test_export_bulan_mengembalikan_csv(svc):
    svc.add_from_text("kopi 18rb")
    now = local_now(svc.tz)
    data, count = svc.export_month(now.year, now.month)
    assert count == 1
    assert data.startswith(b"\xef\xbb\xbf")
    assert b"kopi" in data


def test_rebuild_ledger_mengembalikan_jumlah(svc):
    svc.add_from_text("kopi 18rb")
    svc.add_from_text("teh 5rb")
    path, count = svc.rebuild_ledger()
    assert count == 2
    assert path.exists()


# ---------------------------------------------------------------- pengaturan


def test_ganti_zona_waktu(svc):
    svc.set_timezone("Asia/Makassar")
    assert svc.tz == "Asia/Makassar"
    # transaksi baru harus memakai zona baru
    svc.add_from_text("kopi 18rb")
    row = svc.list_transactions()[0]
    assert row.when.tzinfo is None


def test_zona_waktu_tidak_valid_ditolak(svc):
    with pytest.raises(LedgerError):
        svc.set_timezone("Mars/Olympus")


def test_ganti_nama(svc):
    svc.set_user_name("Razz")
    assert svc.user_name() == "Razz"


# ---------------------------------------------------------------- berkas


def test_storage_info(svc):
    svc.add_from_text("kopi 18rb")
    info = svc.storage_info()
    assert info.db_path.exists()
    assert info.tx_count == 1
    assert info.first_date
    assert info.db_bytes > 0


def test_backup_menghasilkan_file(svc):
    svc.add_from_text("kopi 18rb")
    target = svc.backup_now()
    assert target is not None
    assert target.exists()


def test_impor_database_lain(svc, tmp_path):
    svc.add_from_text("kopi 18rb")

    other_dir = tmp_path / "other"
    other = LedgerService(other_dir / "finance.db", other_dir / "exports")
    try:
        other.add_from_text("gaji 5jt")
        other.add_from_text("makan 30rb")
    finally:
        other.close()

    svc.import_database(other_dir / "finance.db")

    rows = svc.list_transactions()
    assert len(rows) == 2
    assert any(r.kind == TYPE_INCOME for r in rows)


def test_impor_file_bukan_database_ditolak(svc, tmp_path):
    junk = tmp_path / "junk.db"
    junk.write_text("ini bukan database", encoding="utf-8")
    with pytest.raises(LedgerError):
        svc.import_database(junk)


def test_impor_database_tanpa_tabel_ditolak(svc, tmp_path):
    empty = tmp_path / "empty.db"
    connection = sqlite3.connect(str(empty))
    connection.execute("CREATE TABLE lain (x INTEGER)")
    connection.commit()
    connection.close()

    with pytest.raises(LedgerError):
        svc.import_database(empty)


def test_impor_file_tidak_ada_ditolak(svc, tmp_path):
    with pytest.raises(LedgerError):
        svc.import_database(tmp_path / "tidak-ada.db")


def test_impor_database_sendiri_ditolak(svc):
    with pytest.raises(LedgerError):
        svc.import_database(svc.db_path)


def test_impor_database_telegram_memakai_user_yang_ada(svc, tmp_path):
    """Database bot punya telegram_id asli; jangan buat user kedua."""
    other_dir = tmp_path / "botcopy"
    other = LedgerService(other_dir / "finance.db", other_dir / "exports")
    try:
        other.set_user_name("Razz")
        from sqlmodel import select

        from bot.models import User

        with other.session() as session:
            user = session.exec(select(User)).first()
            user.telegram_id = 987654321
            session.add(user)
            session.commit()
        other.add_from_text("kopi 18rb")
    finally:
        other.close()

    svc.import_database(other_dir / "finance.db")

    from sqlmodel import select

    from bot.models import User

    with svc.session() as session:
        users = session.exec(select(User)).all()
        assert len(users) == 1
        assert users[0].telegram_id == 987654321
    assert svc.user_name() == "Razz"
    assert len(svc.list_transactions()) == 1


def test_impor_menyalin_transaksi_yang_masih_di_wal(svc, tmp_path):
    """Sumber dengan WAL aktif: data terakhir tetap ikut tersalin."""
    other_dir = tmp_path / "walcopy"
    other = LedgerService(other_dir / "finance.db", other_dir / "exports")
    try:
        for text in ("kopi 18rb", "teh 5rb", "bensin 25rb"):
            other.add_from_text(text)
        # biarkan koneksi terbuka supaya data masih mungkin di file -wal
        svc.import_database(other_dir / "finance.db")
        assert len(svc.list_transactions()) == 3
    finally:
        other.close()


# ---------------------------------------------------------------- integritas


def test_nominal_disimpan_sebagai_integer_rupiah(svc):
    svc.add_from_text("kopi 1,5rb")
    row = svc.list_transactions()[0]
    assert row.amount == 1500
    assert isinstance(row.amount, int)


def test_saldo_konsisten_setelah_ubah_dan_hapus(svc):
    first = svc.add_from_text("gaji 5jt")
    second = svc.add_from_text("kopi 18rb")
    assert svc.dashboard().balance == 4_982_000

    svc.update_transaction(
        second.row.id,
        kind=TYPE_EXPENSE,
        amount=20_000,
        category_id=second.row.category_id,
        note="kopi naik",
        when_local=second.row.when,
    )
    assert svc.dashboard().balance == 4_980_000

    svc.delete_transaction(first.row.id)
    assert svc.dashboard().balance == -20_000


def test_session_baru_melihat_data_lama(tmp_path):
    path = tmp_path / "finance.db"
    first = LedgerService(path, tmp_path / "exports")
    first.add_from_text("kopi 18rb")
    first.close()

    second = LedgerService(path, tmp_path / "exports")
    try:
        assert len(second.list_transactions()) == 1
    finally:
        second.close()


def test_local_telegram_id_dipakai_untuk_instalasi_baru(svc):
    from sqlmodel import select

    from bot.models import User

    with svc.session() as session:
        users = session.exec(select(User)).all()
        assert len(users) == 1
        assert users[0].telegram_id == LOCAL_TELEGRAM_ID

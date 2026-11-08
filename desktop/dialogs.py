"""Dialog tambah/ubah transaksi, kategori, dan anggaran."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QDate, QTime, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from bot.formatting import money
from bot.models import TYPE_EXPENSE, TYPE_INCOME
from bot.parser import ParseError, parse_amount
from desktop.service import CategoryRow, TxRow


class _BaseDialog(QDialog):
    def __init__(self, parent: QWidget | None, title: str) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(420)

        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(20, 20, 20, 20)
        self.root.setSpacing(14)

        self.heading = QLabel(title)
        self.heading.setObjectName("PageTitle")
        self.root.addWidget(self.heading)

        self.error = QLabel("")
        self.error.setObjectName("ErrorText")
        self.error.setWordWrap(True)
        self.error.setVisible(False)
        self.root.addWidget(self.error)

        self.form = QFormLayout()
        self.form.setSpacing(10)
        self.form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        self.root.addLayout(self.form)

        self.root.addStretch(1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.cancel_button = QPushButton("Batal")
        self.cancel_button.clicked.connect(self.reject)
        self.ok_button = QPushButton("Simpan")
        self.ok_button.setObjectName("Primary")
        self.ok_button.setDefault(True)
        self.ok_button.clicked.connect(self._on_accept)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.ok_button)
        self.root.addLayout(buttons)

    def _fail(self, message: str) -> None:
        self.error.setText(message)
        self.error.setVisible(True)

    def _on_accept(self) -> None:  # pragma: no cover - ditimpa subclass
        self.accept()


class TransactionDialog(_BaseDialog):
    """Tambah atau ubah satu transaksi."""

    def __init__(
        self,
        parent: QWidget | None,
        *,
        categories: list[CategoryRow],
        accounts: list[tuple[int, str]],
        row: TxRow | None = None,
        default_kind: str = TYPE_EXPENSE,
    ) -> None:
        super().__init__(parent, "Ubah Transaksi" if row else "Tambah Transaksi")
        self._categories = categories
        self._row = row
        self.result_values: dict | None = None

        self.kind_combo = QComboBox()
        self.kind_combo.addItem("Keluar (pengeluaran)", TYPE_EXPENSE)
        self.kind_combo.addItem("Masuk (pemasukan)", TYPE_INCOME)

        self.amount_input = QLineEdit()
        self.amount_input.setPlaceholderText("18000 atau 18rb")
        self.amount_input.textChanged.connect(self._update_preview)

        self.amount_preview = QLabel("")
        self.amount_preview.setObjectName("Faint")

        amount_box = QWidget()
        amount_layout = QVBoxLayout(amount_box)
        amount_layout.setContentsMargins(0, 0, 0, 0)
        amount_layout.setSpacing(2)
        amount_layout.addWidget(self.amount_input)
        amount_layout.addWidget(self.amount_preview)

        self.category_combo = QComboBox()
        self.note_input = QLineEdit()
        self.note_input.setPlaceholderText("mis. kopi pagi")

        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("dd/MM/yyyy")
        self.date_edit.setMaximumDate(QDate.currentDate())

        self.time_edit = QTimeEdit()
        self.time_edit.setDisplayFormat("HH:mm")

        self.account_combo = QComboBox()
        for account_id, name in accounts:
            self.account_combo.addItem(name, account_id)

        self.form.addRow("Jenis", self.kind_combo)
        self.form.addRow("Nominal", amount_box)
        self.form.addRow("Kategori", self.category_combo)
        self.form.addRow("Catatan", self.note_input)

        when_row = QHBoxLayout()
        when_row.setSpacing(8)
        when_row.addWidget(self.date_edit)
        when_row.addWidget(self.time_edit)
        when_row.addStretch(1)
        self.form.addRow("Tanggal", self._wrap(when_row))
        self.form.addRow("Akun", self.account_combo)

        self.kind_combo.currentIndexChanged.connect(self._reload_categories)

        if row is not None:
            self.kind_combo.setCurrentIndex(1 if row.kind == TYPE_INCOME else 0)
            self._reload_categories()
            self._select_category(row.category_id)
            self.amount_input.setText(str(row.amount))
            self.note_input.setText(row.note)
            self.date_edit.setDate(QDate(row.when.year, row.when.month, row.when.day))
            self.time_edit.setTime(QTime(row.when.hour, row.when.minute))
        else:
            self.kind_combo.setCurrentIndex(1 if default_kind == TYPE_INCOME else 0)
            self._reload_categories()
            now = datetime.now()
            self.date_edit.setDate(QDate.currentDate())
            self.time_edit.setTime(QTime(now.hour, now.minute))

        self.amount_input.setFocus()

    @staticmethod
    def _wrap(layout) -> QWidget:
        holder = QWidget()
        holder.setLayout(layout)
        layout.setContentsMargins(0, 0, 0, 0)
        return holder

    def _current_kind(self) -> str:
        return self.kind_combo.currentData() or TYPE_EXPENSE

    def _reload_categories(self) -> None:
        kind = self._current_kind()
        previous = self.category_combo.currentData()
        self.category_combo.blockSignals(True)
        self.category_combo.clear()
        for category in self._categories:
            if category.kind == kind:
                self.category_combo.addItem(f"{category.emoji} {category.name}".strip(), category.id)
        if previous is not None:
            self._select_category(int(previous))
        self.category_combo.blockSignals(False)

    def _select_category(self, category_id: int) -> None:
        index = self.category_combo.findData(int(category_id))
        if index >= 0:
            self.category_combo.setCurrentIndex(index)

    def _update_preview(self, _text: str = "") -> None:
        raw = self.amount_input.text().strip()
        if not raw:
            self.amount_preview.setText("")
            return
        try:
            amount = parse_amount(raw)
        except ParseError:
            self.amount_preview.setText("Nominal tidak valid")
            return
        if amount is None:
            self.amount_preview.setText("Nominal tidak terbaca")
            return
        self.amount_preview.setText(f"= {money(amount)}")

    def _on_accept(self) -> None:
        self.error.setVisible(False)

        raw = self.amount_input.text().strip()
        if not raw:
            self._fail("Nominal belum diisi.")
            return
        try:
            amount = parse_amount(raw)
        except ParseError as exc:
            self._fail(str(exc))
            return
        if amount is None or amount <= 0:
            self._fail("Nominal tidak terbaca. Contoh: 18000 atau 18rb.")
            return

        category_id = self.category_combo.currentData()
        if category_id is None:
            self._fail("Pilih kategori dulu.")
            return

        date = self.date_edit.date()
        time = self.time_edit.time()
        when = datetime(date.year(), date.month(), date.day(), time.hour(), time.minute())

        self.result_values = {
            "kind": self._current_kind(),
            "amount": int(amount),
            "category_id": int(category_id),
            "note": self.note_input.text().strip(),
            "when_local": when,
            "account_id": self.account_combo.currentData(),
        }
        self.accept()


class CategoryDialog(_BaseDialog):
    """Tambah atau ubah kategori."""

    def __init__(
        self,
        parent: QWidget | None,
        *,
        row: CategoryRow | None = None,
        default_kind: str = TYPE_EXPENSE,
    ) -> None:
        super().__init__(parent, "Ubah Kategori" if row else "Kategori Baru")
        self.result_values: dict | None = None

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("mis. Kopi")
        self.name_input.setMaxLength(40)

        self.kind_combo = QComboBox()
        self.kind_combo.addItem("Keluar (pengeluaran)", TYPE_EXPENSE)
        self.kind_combo.addItem("Masuk (pemasukan)", TYPE_INCOME)

        self.emoji_input = QLineEdit()
        self.emoji_input.setPlaceholderText("🍜")
        self.emoji_input.setMaxLength(4)
        self.emoji_input.setFixedWidth(70)

        self.keywords_input = QLineEdit()
        self.keywords_input.setPlaceholderText("kopi,latte,ngopi (dipisah koma)")

        self.form.addRow("Nama", self.name_input)
        self.form.addRow("Jenis", self.kind_combo)
        self.form.addRow("Emoji", self.emoji_input)
        self.form.addRow("Kata kunci", self.keywords_input)

        hint = QLabel(
            "Kata kunci dipakai untuk menebak kategori otomatis saat kamu "
            "mengetik, mis. <i>kopi 18rb</i> masuk ke kategori Kopi."
        )
        hint.setObjectName("Faint")
        hint.setWordWrap(True)
        self.root.insertWidget(3, hint)

        if row is not None:
            self.name_input.setText(row.name)
            self.kind_combo.setCurrentIndex(1 if row.kind == TYPE_INCOME else 0)
            self.kind_combo.setEnabled(False)  # ubah jenis akan memutus transaksi lama
            self.emoji_input.setText(row.emoji)
            self.keywords_input.setText(row.keywords)
        else:
            self.kind_combo.setCurrentIndex(1 if default_kind == TYPE_INCOME else 0)

        self.name_input.setFocus()

    def _on_accept(self) -> None:
        self.error.setVisible(False)
        name = self.name_input.text().strip()
        if not name:
            self._fail("Nama kategori belum diisi.")
            return

        self.result_values = {
            "name": name,
            "kind": self.kind_combo.currentData() or TYPE_EXPENSE,
            "emoji": self.emoji_input.text().strip(),
            "keywords": self.keywords_input.text().strip(),
        }
        self.accept()


class BudgetDialog(_BaseDialog):
    """Atur batas anggaran bulanan untuk satu kategori."""

    def __init__(
        self,
        parent: QWidget | None,
        *,
        categories: list[CategoryRow],
        current_category_id: int | None = None,
        current_amount: int = 0,
    ) -> None:
        super().__init__(parent, "Atur Anggaran")
        self.result_values: dict | None = None

        self.category_combo = QComboBox()
        for category in categories:
            if category.kind != TYPE_EXPENSE:
                continue
            self.category_combo.addItem(
                f"{category.emoji} {category.name}".strip(), category.id
            )

        self.amount_input = QLineEdit()
        self.amount_input.setPlaceholderText("1500000 atau 1,5jt")
        self.amount_input.textChanged.connect(self._update_preview)

        self.preview = QLabel("")
        self.preview.setObjectName("Faint")

        amount_box = QWidget()
        amount_layout = QVBoxLayout(amount_box)
        amount_layout.setContentsMargins(0, 0, 0, 0)
        amount_layout.setSpacing(2)
        amount_layout.addWidget(self.amount_input)
        amount_layout.addWidget(self.preview)

        self.form.addRow("Kategori", self.category_combo)
        self.form.addRow("Batas/bulan", amount_box)

        hint = QLabel("Isi 0 untuk menghapus anggaran kategori ini.")
        hint.setObjectName("Faint")
        self.root.insertWidget(3, hint)

        if current_category_id is not None:
            index = self.category_combo.findData(int(current_category_id))
            if index >= 0:
                self.category_combo.setCurrentIndex(index)
            self.category_combo.setEnabled(False)
        if current_amount:
            self.amount_input.setText(str(current_amount))

        self.amount_input.setFocus()

    def _update_preview(self, _text: str = "") -> None:
        raw = self.amount_input.text().strip()
        if not raw:
            self.preview.setText("")
            return
        try:
            amount = parse_amount(raw)
        except ParseError:
            self.preview.setText("Nominal tidak valid")
            return
        if amount is None:
            self.preview.setText("Nominal tidak terbaca")
            return
        self.preview.setText(f"= {money(amount)} per bulan")

    def _on_accept(self) -> None:
        self.error.setVisible(False)
        raw = self.amount_input.text().strip()
        if not raw:
            self._fail("Batas anggaran belum diisi.")
            return
        try:
            amount = parse_amount(raw)
        except ParseError as exc:
            self._fail(str(exc))
            return
        if amount is None:
            self._fail("Nominal tidak terbaca. Contoh: 1500000 atau 1,5jt.")
            return

        category_id = self.category_combo.currentData()
        if category_id is None:
            self._fail("Pilih kategori dulu.")
            return

        self.result_values = {"category_id": int(category_id), "amount": int(amount)}
        self.accept()

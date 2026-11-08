"""Halaman ringkasan: saldo, transaksi hari ini, catat cepat."""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from bot.formatting import money
from bot.ledger import LedgerError
from bot.models import TYPE_EXPENSE, TYPE_INCOME
from bot.parser import ParseError, match_category, parse_entry
from bot.timeutil import local_now
from desktop.pages.base import Page, clear_layout
from desktop.widgets import BarWidget, Card, EmptyState, StatCard, transaction_row


class DashboardPage(Page):
    def __init__(self, service, palette, parent=None) -> None:
        super().__init__(service, palette, parent)
        self.set_header("Dashboard", "Ringkasan keuanganmu hari ini.")
        self._categories = []
        self._build()
        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.timeout.connect(self._clear_status)

    # ---------------------------------------------------------- bangun UI

    def _build(self) -> None:
        stats = QHBoxLayout()
        stats.setSpacing(14)

        self.card_balance = StatCard("Saldo", "—", "semua akun")
        self.card_income = StatCard("Pemasukan", "—", "bulan ini")
        self.card_expense = StatCard("Pengeluaran", "—", "bulan ini")
        for card in (self.card_balance, self.card_income, self.card_expense):
            card.setMinimumWidth(180)
            stats.addWidget(card, 1)
        self.content.addLayout(stats)

        quick = Card("Catat cepat")
        self.quick_input = QLineEdit()
        self.quick_input.setObjectName("QuickEntry")
        self.quick_input.setPlaceholderText("kopi 18rb   ·   gaji 5jt   ·   kemarin bensin 25rb")
        self.quick_input.returnPressed.connect(self._submit_quick)
        self.quick_input.textChanged.connect(self._update_preview)

        self.quick_button = QPushButton("Simpan")
        self.quick_button.setObjectName("Primary")
        self.quick_button.setMinimumHeight(44)
        self.quick_button.clicked.connect(self._submit_quick)

        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(self.quick_input, 1)
        row.addWidget(self.quick_button)
        quick.add_layout(row)

        self.quick_preview = QLabel("")
        self.quick_preview.setObjectName("Faint")
        self.quick_preview.setWordWrap(True)
        quick.add(self.quick_preview)

        self.quick_status = QLabel("")
        self.quick_status.setWordWrap(True)
        self.quick_status.setVisible(False)
        quick.add(self.quick_status)

        self.content.addWidget(quick)

        self.today_card = Card("Transaksi hari ini")
        self.today_total = QLabel("")
        self.today_total.setObjectName("Muted")
        self.today_card.add(self.today_total)
        self.today_body = QVBoxLayout()
        self.today_body.setSpacing(0)
        self.today_card.add_layout(self.today_body)
        self.content.addWidget(self.today_card)

        self.budget_card = Card("Anggaran bulan ini")
        self.budget_body = QVBoxLayout()
        self.budget_body.setSpacing(10)
        self.budget_card.add_layout(self.budget_body)
        self.budget_card.setVisible(False)
        self.content.addWidget(self.budget_card)
        self.content.addStretch(1)

    # ---------------------------------------------------------- preview

    def _update_preview(self, _text: str = "") -> None:
        raw = self.quick_input.text().strip()
        if not raw:
            self.quick_preview.setText(
                "Tulis nominal di mana saja. Tanggal bisa disebut: kemarin, 2 hari lalu, 15/10."
            )
            self.quick_preview.setObjectName("Faint")
            self._restyle_quick()
            return

        try:
            result = parse_entry(raw, local_now(self.service.tz))
        except ParseError as exc:
            self._preview_error(_plain(str(exc)))
            return
        except ValueError:
            self._preview_error("Input belum bisa dibaca.")
            return

        kind = result.kind_hint
        if result.sign == "+":
            kind = TYPE_INCOME
        elif result.sign == "-":
            kind = TYPE_EXPENSE
        if kind not in (TYPE_INCOME, TYPE_EXPENSE):
            kind = TYPE_EXPENSE

        label = "🟢 Masuk" if kind == TYPE_INCOME else "🔴 Keluar"
        category = match_category(
            [c for c in self._categories if c.kind == kind], result.note
        )
        category_name = category.name if category else (
            "Lainnya" if kind == TYPE_INCOME else "Lain-lain"
        )
        emoji = category.emoji if category else ("➕" if kind == TYPE_INCOME else "📦")

        self.quick_preview.setText(
            f"{label} · {emoji} {category_name} · {money(result.amount)} · {result.date_label}"
        )
        self.quick_preview.setObjectName("Hint")
        self._restyle_quick()

    def _preview_error(self, message: str) -> None:
        self.quick_preview.setText(message)
        self.quick_preview.setObjectName("ErrorText")
        self._restyle_quick()

    def _restyle_quick(self) -> None:
        # Object name berubah -> QSS harus dipasang ulang pada widget itu.
        self.quick_preview.style().unpolish(self.quick_preview)
        self.quick_preview.style().polish(self.quick_preview)

    # ---------------------------------------------------------- aksi

    def _submit_quick(self) -> None:
        text = self.quick_input.text().strip()
        if not text:
            self._show_status("Tulis dulu, mis. kopi 18rb.", ok=False)
            return

        self.quick_button.setEnabled(False)
        try:
            outcome = self.service.add_from_text(text)
        except (LedgerError, ParseError) as exc:
            self._show_status(_plain(str(exc)), ok=False)
            return
        except Exception as exc:  # noqa: BLE001 - jangan biarkan UI mati
            self._show_status(f"Gagal menyimpan: {exc}", ok=False)
            return
        finally:
            self.quick_button.setEnabled(True)

        row = outcome.row
        sign = "+" if row.kind == TYPE_INCOME else "−"
        message = (
            f"✅ Tercatat #{row.id} · {row.category} · {sign}{money(row.amount)}"
            f" — {row.note or '(tanpa catatan)'}"
        )
        if outcome.budget_note:
            message += f"\n{outcome.budget_note}"
        self._show_status(message, ok=True)

        self.quick_input.clear()
        self.quick_input.setFocus()
        self.changed.emit()

    def _show_status(self, message: str, *, ok: bool) -> None:
        self.quick_status.setText(message)
        self.quick_status.setStyleSheet(
            f"color: {self.palette['income'] if ok else self.palette['expense']};"
            " font-size: 12px;"
        )
        self.quick_status.setVisible(True)
        self._flash_timer.start(6000)

    def _clear_status(self) -> None:
        self.quick_status.setVisible(False)
        self.quick_status.setText("")

    # ---------------------------------------------------------- refresh

    def refresh(self) -> None:
        self._categories = self.service.categories()
        data = self.service.dashboard()

        self.card_balance.set_value(
            money(data.balance),
            f"{data.total_transactions} transaksi tercatat",
        )
        self.card_income.set_value(
            money(data.month_income), data.month_name, color=self.palette["income"]
        )
        net = data.month_income - data.month_expense
        net_sign = "+" if net >= 0 else "−"
        self.card_expense.set_value(
            money(data.month_expense),
            f"Selisih {net_sign}{money(abs(net))}",
            color=self.palette["expense"],
        )

        clear_layout(self.today_body)
        shown = len(data.today_rows)
        extra = data.today_count - shown
        counter = f" · menampilkan {shown} dari {data.today_count}" if extra > 0 else ""
        self.today_total.setText(
            f"{data.today_label} · masuk {money(data.today_income)} · "
            f"keluar {money(data.today_expense)}{counter}"
        )
        if data.today_rows:
            for row in data.today_rows:
                self.today_body.addWidget(transaction_row(row, self.palette))
        else:
            self.today_body.addWidget(
                EmptyState(
                    "Belum ada transaksi hari ini",
                    "Coba tulis kopi 18rb di kotak Catat cepat di atas.",
                )
            )

        clear_layout(self.budget_body)
        self.budget_card.setVisible(bool(data.budgets))
        for budget in data.budgets:
            self.budget_body.addWidget(self._budget_widget(budget))

    def _budget_widget(self, budget) -> QWidget:
        holder = QWidget()
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        name = QLabel(budget.category)
        name.setStyleSheet("font-weight: 600;")
        head.addWidget(name)
        head.addStretch(1)

        percent = int(round(budget.ratio * 100))
        amount = QLabel(
            f"{money(budget.used)} / {money(budget.limit)} · {percent}%"
        )
        amount.setObjectName("Faint")
        if budget.status == "lewat":
            amount.setStyleSheet(f"color: {self.palette['expense']}; font-weight: 700;")
        elif budget.status == "hampir":
            amount.setStyleSheet(f"color: {self.palette['warn']}; font-weight: 700;")
        head.addWidget(amount)
        layout.addLayout(head)

        bar = BarWidget()
        fill = self.palette["accent"]
        if budget.status == "lewat":
            fill = self.palette["expense"]
        elif budget.status == "hampir":
            fill = self.palette["warn"]
        bar.set_colors(fill, self.palette["surface_alt"])
        bar.set_ratio(budget.ratio)
        layout.addWidget(bar)
        return holder

    # ---------------------------------------------------------- tema

    def restyle(self) -> None:
        self.refresh()


def _plain(text: str) -> str:
    """Buang tag HTML dari pesan error parser."""
    from bot.formatting import plain

    return plain(text)

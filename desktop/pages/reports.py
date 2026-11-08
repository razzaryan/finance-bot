"""Halaman laporan bulanan & tren."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from bot.formatting import money
from bot.timeutil import add_months, local_now, month_label
from desktop.pages.base import Page, clear_layout
from desktop.widgets import BarWidget, Card, EmptyState, StatCard


class ReportsPage(Page):
    def __init__(self, service, palette, parent=None) -> None:
        super().__init__(service, palette, parent)
        self.set_header("Laporan", "Lihat ke mana uangmu pergi setiap bulan.")
        now = local_now(self.service.tz)
        self.year, self.month = now.year, now.month
        self._build()

    # ---------------------------------------------------------- UI

    def _build(self) -> None:
        export_button = QPushButton("Export CSV")
        export_button.clicked.connect(self._export)
        self.header_actions.addWidget(export_button)

        nav = Card()
        bar = QHBoxLayout()
        bar.setSpacing(8)

        prev_button = QPushButton("‹")
        prev_button.setFixedWidth(38)
        prev_button.clicked.connect(lambda: self._shift(-1))
        next_button = QPushButton("›")
        next_button.setFixedWidth(38)
        next_button.clicked.connect(lambda: self._shift(1))

        self.month_label = QLabel("")
        self.month_label.setStyleSheet("font-size: 15px; font-weight: 700;")

        this_month = QPushButton("Bulan ini")
        this_month.clicked.connect(self._go_current)

        bar.addWidget(prev_button)
        bar.addWidget(self.month_label)
        bar.addWidget(next_button)
        bar.addSpacing(8)
        bar.addWidget(this_month)
        bar.addStretch(1)
        self.compare_label = QLabel("")
        self.compare_label.setObjectName("Muted")
        bar.addWidget(self.compare_label)
        nav.add_layout(bar)
        self.content.addWidget(nav)

        stats = QHBoxLayout()
        stats.setSpacing(14)
        self.card_income = StatCard("Pemasukan", "—", "bulan ini")
        self.card_expense = StatCard("Pengeluaran", "—", "bulan ini")
        self.card_net = StatCard("Selisih", "—", "masuk − keluar")
        for card in (self.card_income, self.card_expense, self.card_net):
            card.setMinimumWidth(180)
            stats.addWidget(card, 1)
        self.content.addLayout(stats)

        self.expense_card = Card("Pengeluaran per kategori")
        self.expense_body = QVBoxLayout()
        self.expense_body.setSpacing(10)
        self.expense_card.add_layout(self.expense_body)
        self.content.addWidget(self.expense_card)

        self.income_card = Card("Pemasukan per kategori")
        self.income_body = QVBoxLayout()
        self.income_body.setSpacing(10)
        self.income_card.add_layout(self.income_body)
        self.content.addWidget(self.income_card)

        self.history_card = Card("12 bulan terakhir")
        self.history_body = QVBoxLayout()
        self.history_body.setSpacing(8)
        self.history_card.add_layout(self.history_body)
        self.content.addWidget(self.history_card)
        self.content.addStretch(1)

    # ---------------------------------------------------------- navigasi

    def _shift(self, delta: int) -> None:
        self.year, self.month = add_months(self.year, self.month, delta)
        self.refresh()

    def _go_current(self) -> None:
        now = local_now(self.service.tz)
        self.year, self.month = now.year, now.month
        self.refresh()

    # ---------------------------------------------------------- data

    def refresh(self) -> None:
        report = self.service.month_report(self.year, self.month)
        self.month_label.setText(month_label(self.year, self.month))
        self.compare_label.setText(report.comparison or "")

        self.card_income.set_value(money(report.income), f"{report.tx_count} transaksi")
        self.card_expense.set_value(money(report.expense), "", color=self.palette["expense"])
        net = report.net
        self.card_net.set_value(
            money(net),
            "surplus" if net >= 0 else "defisit",
            color=self.palette["income"] if net >= 0 else self.palette["expense"],
        )

        self._fill_breakdown(
            self.expense_body,
            report.top_expense,
            total=report.expense,
            color=self.palette["expense"],
            empty_title="Belum ada pengeluaran",
            empty_sub="Catat pengeluaran pertamamu dari halaman Dashboard.",
        )
        self._fill_breakdown(
            self.income_body,
            report.top_income,
            total=report.income,
            color=self.palette["income"],
            empty_title="Belum ada pemasukan",
            empty_sub="Catat gaji atau pemasukan lain dengan gaji 5jt.",
        )

        self._fill_history()

    def _fill_breakdown(
        self,
        layout,
        items: list[tuple[str, str, int]],
        *,
        total: int,
        color: str,
        empty_title: str,
        empty_sub: str,
    ) -> None:
        clear_layout(layout)
        if not items:
            layout.addWidget(EmptyState(empty_title, empty_sub))
            return

        largest = max((amount for _e, _n, amount in items), default=1) or 1
        for emoji, name, amount in items:
            row = QWidget()
            box = QVBoxLayout(row)
            box.setContentsMargins(0, 0, 0, 0)
            box.setSpacing(4)

            head = QHBoxLayout()
            head.setContentsMargins(0, 0, 0, 0)
            label = QLabel(f"{emoji} {name}".strip())
            label.setStyleSheet("font-weight: 600;")
            head.addWidget(label)
            head.addStretch(1)

            share = int(round(amount / total * 100)) if total else 0
            value = QLabel(f"{money(amount)} · {share}%")
            value.setObjectName("Faint")
            head.addWidget(value)
            box.addLayout(head)

            bar = BarWidget()
            bar.set_colors(color, self.palette["surface_alt"])
            bar.set_ratio(amount / largest)
            box.addWidget(bar)

            layout.addWidget(row)

    def _fill_history(self) -> None:
        clear_layout(self.history_body)
        items = self.service.history(12)
        if not any(income or expense for _label, income, expense in items):
            self.history_body.addWidget(
                EmptyState("Belum ada riwayat", "Tren muncul setelah kamu mencatat transaksi.")
            )
            return

        largest = max((max(income, expense) for _l, income, expense in items), default=1) or 1
        for label, income, expense in items:
            row = QWidget()
            box = QVBoxLayout(row)
            box.setContentsMargins(0, 0, 0, 0)
            box.setSpacing(3)

            head = QHBoxLayout()
            head.setContentsMargins(0, 0, 0, 0)
            name = QLabel(label)
            name.setFixedWidth(90)
            name.setStyleSheet("font-weight: 600;")
            head.addWidget(name)

            detail = QLabel(f"masuk {money(income)} · keluar {money(expense)}")
            detail.setObjectName("Faint")
            head.addWidget(detail)
            head.addStretch(1)
            box.addLayout(head)

            bar = BarWidget()
            bar.set_colors(self.palette["expense"], self.palette["surface_alt"])
            bar.set_ratio(expense / largest if largest else 0)
            box.addWidget(bar)

            self.history_body.addWidget(row)

    # ---------------------------------------------------------- export

    def _export(self) -> None:
        default_name = f"keuangan-{self.year}-{self.month:02d}.csv"
        target, _filter = QFileDialog.getSaveFileName(
            self,
            "Simpan CSV",
            str(Path.home() / default_name),
            "CSV (*.csv)",
        )
        if not target:
            return

        try:
            data, count = self.service.export_month(self.year, self.month)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Gagal", f"Tidak bisa membuat CSV: {exc}")
            return

        if count == 0:
            QMessageBox.information(
                self,
                "Tidak ada data",
                f"Belum ada transaksi di {month_label(self.year, self.month)}.",
            )
            return

        try:
            Path(target).write_bytes(data)
        except OSError as exc:
            QMessageBox.warning(self, "Gagal menyimpan", str(exc))
            return

        QMessageBox.information(
            self,
            "CSV tersimpan",
            f"{count} transaksi disimpan ke:\n{target}",
        )

    def restyle(self) -> None:
        self.refresh()

"""Parser input bahasa manusia -> transaksi.

Contoh yang didukung:
    "kopi 18rb"                 -> keluar 18000
    "gaji 5jt"                  -> masuk 5000000
    "bensin 25.000"             -> keluar 25000
    "kemarin makan 45k"         -> keluar 45000, tanggal kemarin
    "beli 2 kg beras 25000"     -> keluar 25000 (angka bersufiks menang)
    "+500rb dari jual motor"    -> masuk 500000

Modul ini murni fungsi, tidak menyentuh database, supaya mudah dites.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from bot.models import TYPE_EXPENSE, TYPE_INCOME

MAX_AMOUNT = 999_999_999_999  # plafon sanity check (hampir 1 triliun)

MULTIPLIERS = {
    "k": 1_000,
    "rb": 1_000,
    "ribu": 1_000,
    "jt": 1_000_000,
    "juta": 1_000_000,
    "mio": 1_000_000,
    "m": 1_000_000,
}

# --- deteksi angka -----------------------------------------------------------

NUM_CHARS = r"\d[\d.,]*"
# Satu regex untuk "18rb", "18 rb", "1,5 jt", "10mio", dan "kopi18rb".
# Lookbehind hanya melarang angka/titik/koma sebelumnya (bukan huruf), supaya
# bentuk nempel seperti "kopi18rb" tetap terbaca. `(?!\w)` setelah suffix
# mencegah "25000 makan" dianggap 25.000 * 1.000.000.
_SUFFIX_RE = re.compile(
    rf"(?<![\d.,])(?P<num>{NUM_CHARS})\s*(?P<suffix>ribu|juta|mio|rb|jt|k|m)(?!\w)",
    re.IGNORECASE,
)
# Angka polos: boleh nempel setelah huruf ("kopi25000"), tapi tidak boleh
# langsung diikuti huruf/titik/koma (supaya "2x" bukan nominal).
_PLAIN_NUM_RE = re.compile(rf"(?<![\d.,])(?P<num>{NUM_CHARS})(?![\w.,])")
# Prefix mata uang ("Rp", "Rp.", "IDR") dibuang dulu supaya "Rp25.000" terbaca.
_CURRENCY_PREFIX_RE = re.compile(r"(?<!\w)(?:rp|idr)\.?\s*(?=\d)", re.IGNORECASE)
_CURRENCY_LEFTOVER_RE = re.compile(r"(?<!\w)(?:rp|idr)\.?(?!\w)", re.IGNORECASE)


class ParseError(ValueError):
    """Input tidak bisa dipahami; pesannya siap ditampilkan ke pengguna."""


def _parse_number_token(raw: str) -> Decimal | None:
    """Ubah token mentah jadi Decimal dengan menebak pemisah ribuan/desimal.

    Aturan yang dipakai (umum di Indonesia):
    - "1.500.000" / "25.000"  -> pemisah ribuan
    - "1.5" / "1,5"           -> desimal
    - "25,000"                -> ribuan (gaya Inggris)
    Pemisah terakhir dianggap desimal hanya jika diikuti 1-2 digit.
    """
    s = raw.strip().replace(" ", "")
    s = s.strip(".,")
    if not s or not re.fullmatch(r"\d+(?:[.,]\d+)*", s):
        return None

    has_dot = "." in s
    has_comma = "," in s

    if has_dot and has_comma:
        dec_sep = "." if s.rfind(".") > s.rfind(",") else ","
        grp_sep = "," if dec_sep == "." else "."
        if s.count(dec_sep) > 1:
            return None
        s = s.replace(grp_sep, "").replace(dec_sep, ".")
    elif has_comma or has_dot:
        sep = "," if has_comma else "."
        parts = s.split(sep)

        if len(parts) > 2:
            # "1.500.000" -> semua bagian setelah pertama harus 3 digit
            if not all(len(p) == 3 for p in parts[1:]):
                return None
            s = "".join(parts)
        else:
            head, tail = parts
            if len(tail) <= 2:
                s = f"{head}.{tail}"  # desimal: 1.5 / 1,5
            elif len(tail) == 3 and 1 <= len(head) <= 3:
                s = head + tail  # ribuan: 25.000 / 25,000
            else:
                return None

    try:
        value = Decimal(s)
    except InvalidOperation:  # pragma: no cover - sudah difilter regex
        return None
    return value


def parse_amount(text: str) -> int | None:
    """Ambil nominal dari sebuah potongan teks. None kalau tidak ada angka valid."""
    if not text:
        return None
    raw = _CURRENCY_PREFIX_RE.sub(" ", text.strip())

    for match in _SUFFIX_RE.finditer(raw):
        number = _parse_number_token(match.group("num"))
        if number is None:
            continue
        multiplier = MULTIPLIERS[match.group("suffix").lower()]
        amount = int((number * multiplier).to_integral_value(rounding="ROUND_HALF_UP"))
        return _validate_amount(amount)

    match = _PLAIN_NUM_RE.search(raw)
    if match:
        number = _parse_number_token(match.group("num"))
        if number is None:
            return None
        return _validate_amount(int(number.to_integral_value(rounding="ROUND_HALF_UP")))

    return None


def _validate_amount(amount: int) -> int:
    if amount <= 0:
        raise ParseError("Nominal harus lebih dari 0.")
    if amount > MAX_AMOUNT:
        raise ParseError("Nominal terlalu besar. Cek lagi angkanya.")
    return amount


# --- deteksi tanggal ---------------------------------------------------------

_RELATIVE_DAYS = [
    (re.compile(r"\b(?:kemarin|kmrn|kemaren)\b", re.IGNORECASE), -1),
    (re.compile(r"\bkemarin\s+lusa\b", re.IGNORECASE), -2),
    (re.compile(r"\bhari\s+ini\b", re.IGNORECASE), 0),
    (re.compile(r"\btadi\b", re.IGNORECASE), 0),
]
_RELATIVE_N_DAYS = re.compile(
    r"\b(\d{1,2})\s+hari\s+(?:yang\s+)?lalu\b", re.IGNORECASE
)
# Tanggal eksplisit: "15/10", "15-10", "15/10/2026", "15-10-26".
# Tanda hubung hanya dipakai bentuk berpemisah miring kalau ada tahun,
# supaya "18rb-25000" tidak dianggap tanggal.
_EXPLICIT_DATE_SLASH = re.compile(
    r"(?<![\d/])(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?(?![\d/])"
)
_EXPLICIT_DATE_DASH = re.compile(
    r"(?<![\d-])(\d{1,2})-(\d{1,2})-(\d{2,4})(?![\d-])"
)
_EXPLICIT_DATE_YMD = re.compile(r"(?<![\d-])(\d{4})-(\d{2})-(\d{2})(?![\d-])")


@dataclass
class DateResult:
    day: date
    consumed: str
    label: str


def extract_date(text: str, today: date) -> DateResult | None:
    """Cari penanda tanggal relatif/eksplisit di teks."""
    for regex, delta in _RELATIVE_DAYS:
        match = regex.search(text)
        if match:
            if delta == 0:
                label = "hari ini"
            elif delta == -1:
                label = "kemarin"
            else:
                label = f"{abs(delta)} hari lalu"
            return DateResult(
                day=today + timedelta(days=delta),
                consumed=match.group(0),
                label=label,
            )

    match = _RELATIVE_N_DAYS.search(text)
    if match:
        days = int(match.group(1))
        if 1 <= days <= 31:
            return DateResult(
                day=today - timedelta(days=days),
                consumed=match.group(0),
                label=f"{days} hari lalu",
            )

    match = _EXPLICIT_DATE_YMD.search(text)
    if match:
        try:
            day = date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            day = None
        if day and day <= today:
            return DateResult(day=day, consumed=match.group(0), label=day.isoformat())
        return None

    for regex in (_EXPLICIT_DATE_DASH, _EXPLICIT_DATE_SLASH):
        match = regex.search(text)
        if not match:
            continue
        day_num, month_num = int(match.group(1)), int(match.group(2))
        year_raw = match.group(3)
        year = today.year
        if year_raw:
            year = int(year_raw)
            if year < 100:
                year += 2000
        try:
            day = date(year, month_num, day_num)
        except ValueError:
            return None
        if day > today:
            # salah ketik tahun / tanggal belum terjadi -> jangan tebak
            return None
        return DateResult(
            day=day,
            consumed=match.group(0),
            label=f"{day_num:02d}/{month_num:02d}",
        )

    return None


# --- deteksi jenis & kategori ------------------------------------------------

INCOME_WORDS = {
    "gaji",
    "gajian",
    "bonus",
    "thr",
    "dividen",
    "bunga",
    "cashback",
    "refund",
    "komisi",
    "honor",
    "fee",
    "jual",
    "terjual",
    "masuk",
    "pemasukan",
    "terima",
    "menerima",
    "dapat",
    "dikasih",
    "diberi",
    "untung",
    "profit",
    "laba",
    "menang",
    "arisan",
}

EXPENSE_WORDS = {
    "beli",
    "membeli",
    "bayar",
    "membayar",
    "jajan",
    "keluar",
    "pengeluaran",
    "isi",
    "tagihan",
    "cicilan",
    "sewa",
    "sedekah",
    "donasi",
    "transfer",
    "topup",
    "top-up",
}

_WORD_SPLIT_RE = re.compile(r"[^\w+\-]+", re.UNICODE)


def _words(text: str) -> list[str]:
    return [w.lower() for w in _WORD_SPLIT_RE.split(text) if w]


def detect_kind(text: str) -> str | None:
    """Tebak jenis transaksi dari kata kerja. None kalau ambigu.

    Kata pemasukan menang atas kata pengeluaran, karena kata pengeluaran di
    sini juga muncul sebagai pelengkap: "terima transfer", "dapat cashback",
    "refund pembayaran". Kalau urutannya dibalik, uang masuk bisa tercatat
    sebagai pengeluaran.
    """
    words = set(_words(text))
    if words & INCOME_WORDS:
        return TYPE_INCOME
    if words & EXPENSE_WORDS:
        return TYPE_EXPENSE
    return None


def match_category(categories, text: str) -> object | None:
    """Cocokkan teks ke kategori lewat keyword terpanjang yang cocok."""
    lowered = f" {text.lower()} "
    best = None
    best_len = 0
    for category in categories:
        raw_keywords = getattr(category, "keywords", "") or ""
        for keyword in raw_keywords.split(","):
            kw = keyword.strip().lower()
            if not kw:
                continue
            pattern = rf"(?<!\w){re.escape(kw)}(?!\w)"
            if re.search(pattern, lowered) and len(kw) > best_len:
                best = category
                best_len = len(kw)
    return best


# --- hasil parse & fungsi utama ---------------------------------------------

_CATEGORY_MENTION_RE = re.compile(r"@([\w\-]+)")
_SIGN_PREFIX_RE = re.compile(r"^\s*([+-])\s*")
_EXTRA_SPACE_RE = re.compile(r"\s{2,}")
_LEADING_JUNK_RE = re.compile(r"^[\s\-–—:;,.!?]+")


@dataclass
class ParseResult:
    amount: int
    kind_hint: str | None
    category_hint: str | None
    note: str
    occurred_at: datetime
    day: date
    date_label: str
    sign: str | None


def _strip_amount(text: str) -> tuple[str, int]:
    """Cari nominal 'terbaik' lalu buang dari teks. Kembalikan (teks, nominal)."""
    text = _CURRENCY_PREFIX_RE.sub(" ", text)
    candidates: list[tuple[bool, int, str]] = []  # (punya_sufiks, nominal, token)

    for match in _SUFFIX_RE.finditer(text):
        number = _parse_number_token(match.group("num"))
        if number is None:
            continue
        multiplier = MULTIPLIERS[match.group("suffix").lower()]
        amount = int((number * multiplier).to_integral_value(rounding="ROUND_HALF_UP"))
        if amount <= 0:
            continue
        candidates.append((True, amount, match.group(0)))

    if not candidates:
        for match in _PLAIN_NUM_RE.finditer(text):
            number = _parse_number_token(match.group("num"))
            if number is None:
                continue
            amount = int(number.to_integral_value(rounding="ROUND_HALF_UP"))
            if amount <= 0:
                continue
            candidates.append((False, amount, match.group(0)))

    if not candidates:
        raise ParseError(
            "Nominal tidak terbaca. Contoh: <code>kopi 18rb</code> atau <code>makan 25000</code>."
        )

    # Prioritaskan angka bersufiks (rb/jt), lalu nominal terbesar.
    suffix_candidates = [c for c in candidates if c[0]]
    chosen = max(suffix_candidates or candidates, key=lambda c: c[1])
    amount = _validate_amount(chosen[1])

    remaining = text.replace(chosen[2], " ", 1)
    return remaining, amount


def parse_entry(
    text: str,
    now_local: datetime,
    *,
    default_kind: str | None = None,
) -> ParseResult:
    """Parse satu baris input menjadi transaksi.

    Raises:
        ParseError: kalau nominal tidak ditemukan atau nominal tidak masuk akal.
    """
    raw = (text or "").strip()
    if not raw:
        raise ParseError("Teks kosong. Contoh: <code>kopi 18rb</code>")

    # 1. Tanda + / - di awal menang atas tebakan lain.
    sign = None
    sign_match = _SIGN_PREFIX_RE.match(raw)
    if sign_match:
        sign = sign_match.group(1)
        raw = raw[sign_match.end() :]

    # 2. Tanggal
    today = now_local.date()
    date_result = extract_date(raw, today)
    if date_result:
        raw = raw.replace(date_result.consumed, " ", 1)
        target_day = date_result.day
        date_label = date_result.label
    else:
        target_day = today
        date_label = "hari ini"

    # 3. Nominal
    remaining, amount = _strip_amount(raw)
    remaining = _CURRENCY_LEFTOVER_RE.sub(" ", remaining)

    # 4. Kategori eksplisit lewat @nama
    category_hint = None
    mention = _CATEGORY_MENTION_RE.search(remaining)
    if mention:
        category_hint = mention.group(1)
        remaining = remaining.replace(mention.group(0), " ", 1)

    # 5. Jenis transaksi
    if sign == "+":
        kind_hint = TYPE_INCOME
    elif sign == "-":
        kind_hint = TYPE_EXPENSE
    else:
        kind_hint = detect_kind(remaining) or default_kind

    # 6. Catatan
    note = _LEADING_JUNK_RE.sub("", _EXTRA_SPACE_RE.sub(" ", remaining)).strip()
    note = note.strip(" -–—:;,.!?")

    occurred_at = datetime.combine(target_day, now_local.timetz().replace(tzinfo=None))

    return ParseResult(
        amount=amount,
        kind_hint=kind_hint,
        category_hint=category_hint,
        note=note,
        occurred_at=occurred_at,
        day=target_day,
        date_label=date_label,
        sign=sign,
    )

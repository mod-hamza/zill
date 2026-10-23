"""Text folding for matching: case, accents, Arabic letter variants, Norwegian letters."""

from __future__ import annotations

import re
import unicodedata

_PRE = {
    "å": "a", "ø": "o", "æ": "ae", "œ": "oe", "ß": "ss", "ð": "d", "þ": "th", "ł": "l", "đ": "d", "ı": "i",
    "Å": "a", "Ø": "o", "Æ": "ae",
}  # fmt: skip
_AR = {"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي", "ـ": ""}
_AR_MARKS = re.compile("[ؐ-ًؚ-ٰٟۖ-ۭ]")
_NON_WORD = re.compile(r"[^\w]+", re.UNICODE)
_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def fold(s: str) -> str:
    """Lower-case, accent-free, Arabic-normalised, punctuation-free form of ``s`` (single spaces)."""
    if not s:
        return ""
    s = s.translate(_AR_DIGITS)
    s = "".join(_PRE.get(ch, ch) for ch in s)
    s = _AR_MARKS.sub("", s)
    s = "".join(_AR.get(ch, ch) for ch in s)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower().replace("&", " and ")
    s = _NON_WORD.sub(" ", s)
    return s.strip()

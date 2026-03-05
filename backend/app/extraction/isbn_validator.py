import os
import re
from typing import Optional, Tuple

ISBN_LABELED_RE = re.compile(
    r"ISBN[\s\-:]*"
    r"(97[89][\s\-]?\d[\s\-]?\d{3}[\s\-]?\d{5}[\s\-]?\d)",
    re.IGNORECASE,
)
BARE_ISBN13_RE = re.compile(r"\b(97[89]\d{10})\b")
ISBN_HYPHENATED_RE = re.compile(
    r"\b(97[89](?:[\s\-]\d+){3,6})\b"
)


def normalize_isbn(raw: str) -> str:
    return re.sub(r"[\s\-]", "", raw)


def validate_isbn13(isbn: str) -> bool:
    digits = normalize_isbn(isbn)
    if len(digits) != 13:
        return False
    try:
        check = sum(
            int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(digits[:12])
        )
        return (10 - check % 10) % 10 == int(digits[-1])
    except ValueError:
        return False


def extract_isbn(text: str) -> Tuple[Optional[str], Optional[str]]:
    """Return (normalized_isbn13, raw_match) or (None, None)."""
    # Labeled ISBN first (highest confidence)
    for m in ISBN_LABELED_RE.finditer(text):
        raw = m.group(1)
        normalized = normalize_isbn(raw)
        if len(normalized) == 13 and validate_isbn13(normalized):
            return normalized, m.group(0).strip()

    # Hyphenated patterns starting with 978/979
    for m in ISBN_HYPHENATED_RE.finditer(text):
        normalized = normalize_isbn(m.group(1))
        if len(normalized) == 13 and validate_isbn13(normalized):
            return normalized, m.group(0).strip()

    # Bare 13-digit
    for m in BARE_ISBN13_RE.finditer(text):
        raw = m.group(1)
        if validate_isbn13(raw):
            return raw, raw

    return None, None


def isbn_from_filename(filename: str) -> Optional[str]:
    """
    Extract and validate an ISBN-13 from a filename like '978-81-19318-15-5.pdf'.
    Returns the normalized 13-digit string, or None if not valid.
    """
    name = os.path.splitext(os.path.basename(filename))[0]
    digits = re.sub(r"[\s\-]", "", name)
    if len(digits) == 13 and digits[:3] in ("978", "979") and validate_isbn13(digits):
        return digits
    return None

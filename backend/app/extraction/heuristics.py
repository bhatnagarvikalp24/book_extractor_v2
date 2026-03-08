import re
from typing import Any, Dict, List, Optional, Tuple

from .isbn_validator import extract_isbn, isbn_from_filename, validate_isbn13
from .layout import extract_layout

# ── regex constants ──────────────────────────────────────────────────────────

EXCLUDE_TITLE_RE = re.compile(
    r"^\s*("
    r"CONTENTS|PREFACE|CHAPTER\s*\d*|FOREWORD|INTRODUCTION|"
    r"ACKNOWLEDGEMENTS?|INDEX|APPENDIX|TABLE\s+OF\s+CONTENTS|"
    r"DEDICATION|BIBLIOGRAPHY|GLOSSARY|\(i+\)|\(ii+\)|"
    r"UNIT\s+\d+|PART\s+\d+"
    r")\s*$",
    re.IGNORECASE,
)

PUBLISHER_KEYWORDS_RE = re.compile(
    r"\b("
    r"Publishing|Publishers?|Publications?|Press|Prakashan|"
    r"Books?|Book\s+House|House|Media|Company|Ltd\.?|"
    r"Private\s+Limited|Pvt\.?\s*Ltd\.?|Incorporated|Inc\.?|"
    r"International|National|Educational|Academy|Institute|"
    r"University\s+Press|College\s+House"
    r")\b",
    re.IGNORECASE,
)

BY_AUTHOR_RE = re.compile(r"^(?:by|BY|By)\s+(.+)$")
# Allow Dr./Prof./honorific prefix and optional parenthetical like (Dr.) — common in Indian academic books
NAME_LIKE_RE = re.compile(
    r"^(?:(?:Dr\.?|Prof\.?|Er\.?|Sh\.?|Smt\.?|Shri\.?)\s+(?:\([A-Za-z.]+\)\s+)?)?"
    r"[A-Z][a-zA-Z.']+(?:\s+[A-Z][a-zA-Z.']+){0,5}$"
)
HONORIFIC_RE = re.compile(r"^(?:Dr\.?|Prof\.?|Er\.?|Sh\.?|Smt\.?|Shri\.?)\s", re.IGNORECASE)
AVOID_AUTHOR_RE = re.compile(
    r"\b(Editor|Editors|Compiled|Translated|Edited|Foreword|"
    r"Illustrated|Director|Series|Volume|Vol\.|Edition)\b",
    re.IGNORECASE,
)
# Lines that look like publisher/institution footers, not authors
PUBLISHER_FOOTER_RE = re.compile(
    r"\b(Prakashan|Publishing|Publisher|Press|Agency|Distributors?|"
    r"Company|Delhi|Mumbai|Kolkata|Chennai|Bengaluru|Bangalore|"
    r"Naveen|Shahdara|Panchsheel|Gali|Floor|E-mail|Mob\.?|ISBN|"
    r"Price|Published|Printed|Offset)\b",
    re.IGNORECASE,
)
# Words that appear in book titles but NOT in personal names → reject as author
TITLE_WORD_RE = re.compile(
    r"\b(OF|AND|OR|THE|IN|FOR|FROM|A|AN|WITH|AT|ON|AS|TO|BY|"
    r"STORIES?|TALE|TALES|DICTIONARY|JOURNALISM|PHILOSOPHY|GEOGRAPHY|"
    r"HISTORY|SCIENCE|EDUCATION|MODERN|ANCIENT|FAMOUS|SOCIAL|RELIGIOUS|"
    r"NATIONAL|INTERNATIONAL|EAST|WEST|NORTH|SOUTH|CENTRAL|MIDDLE|"
    r"ASIA|INDIA|INDIAN|WORLD|GLOBAL|ECONOMY|POLITICS|ART|CULTURE|"
    r"RELIGION|SPIRITUAL|MANAGEMENT|DEVELOPMENT|FUNDAMENTALS|PRINCIPLES|"
    r"INTRODUCTION|ADVANCED|BASIC|APPLIED|GENERAL|SPECIAL|SELECTED|"
    r"JOURNAL|ANNUAL|QUARTERLY|QUARTERLY|HANDBOOK|YEARBOOK|READER|"
    r"COLLECTION|COMPILATION|ANTHOLOGY|ENCYCLOPEDIA|COMPENDIUM)\b",
    re.IGNORECASE,
)

ADDRESS_RE = re.compile(
    r"\b\d{6}\b"          # Indian PIN code
    r"|\b\d{5}(?:-\d{4})?\b"  # US ZIP
    r"|,\s*[A-Z][a-z]+\s*,"   # city between commas
)

COPYRIGHT_RE = re.compile(r"©|copyright|all\s+rights\s+reserved", re.IGNORECASE)
PUBLISHER_COPYRIGHT_RE = re.compile(
    r"©\s*(?:the\s+)?publisher"
    r"|all\s+rights\s+reserved\s+with\s+the\s+publisher"
    r"|rights?\s+(?:reserved|vest)\s+with\s+(?:the\s+)?publisher",
    re.IGNORECASE,
)
AUTHOR_COPYRIGHT_RE = re.compile(
    r"©\s*(?:the\s+)?author"
    r"|copyright\s*©\s*[A-Z]"
    r"|copyright\s+reserved\s+with\s+(?:the\s+)?author",
    re.IGNORECASE,
)
EDITOR_COPYRIGHT_RE = re.compile(
    r"©\s*(?:the\s+)?editor"
    r"|all\s+rights\s+reserved\s+with\s+(?:the\s+)?editor"
    r"|rights?\s+(?:reserved|vest)\s+with\s+(?:the\s+)?editor",
    re.IGNORECASE,
)
# Extracts entity name after © or "copyright" word:
# "© 2024 National Book Trust" / "Copyright 2016 National Book Trust" → "National Book Trust"
_COPYRIGHT_ENTITY_RE = re.compile(
    r"(?:©|copyright)\s*(?:\d{4}\s+)?([A-Za-z][A-Za-z0-9\s&.,'\-]{2,80})",
    re.IGNORECASE,
)
# Generic words that shouldn't be stored as entity names
_GENERIC_COPYRIGHT_WORDS = re.compile(
    r"^(publisher|author|editor|reserved|all rights|copyright"
    r"|the publisher|the author|the editor)$",
    re.IGNORECASE,
)


# ── span grouping ────────────────────────────────────────────────────────────

def group_into_lines(spans: List[Dict], y_tolerance: float = 4.0) -> List[Dict]:
    """Group spans sharing the same baseline into logical lines."""
    if not spans:
        return []
    sorted_spans = sorted(spans, key=lambda s: (s["bbox"][1], s["bbox"][0]))
    lines: List[List[Dict]] = []
    current = [sorted_spans[0]]

    for span in sorted_spans[1:]:
        if abs(span["bbox"][1] - current[0]["bbox"][1]) <= y_tolerance:
            # Skip duplicate span text within the same line (design-layer repetition)
            if span["text"].strip() not in {s["text"].strip() for s in current}:
                current.append(span)
        else:
            lines.append(current)
            current = [span]
    lines.append(current)

    result = []
    for line_spans in lines:
        text = " ".join(s["text"] for s in line_spans).strip()
        if not text:
            continue
        bboxes = [s["bbox"] for s in line_spans]
        fsizes = [s["font_size"] for s in line_spans]
        x0 = min(b[0] for b in bboxes)
        y0 = min(b[1] for b in bboxes)
        x1 = max(b[2] for b in bboxes)
        y1 = max(b[3] for b in bboxes)
        sorted_f = sorted(fsizes)
        median_f = sorted_f[len(sorted_f) // 2]
        result.append(
            {
                "text": text,
                "bbox": [x0, y0, x1, y1],
                "median_font_size": median_f,
                "max_font_size": max(fsizes),
            }
        )
    return result


# ── individual field extractors ──────────────────────────────────────────────

def extract_title(pages: List[Dict]) -> Optional[Dict]:
    """
    Find the title using layout heuristics on page 1 (fallback page 2).
    Selects the largest-font line in the top 40% of the page, then extends
    to adjacent lines with similar font size to capture multi-line titles.
    """
    for pd in pages[:2]:
        height = pd["height"]
        width = pd["width"]
        page_num = pd["page_num"]
        top_threshold = height * 0.40

        top_spans = [s for s in pd["spans"] if s["bbox"][1] < top_threshold]
        if not top_spans:
            continue

        lines = group_into_lines(top_spans)
        if not lines:
            continue

        candidates = [l for l in lines if not EXCLUDE_TITLE_RE.match(l["text"])]
        if not candidates:
            candidates = lines

        def _score(line: Dict) -> Tuple:
            cx = (line["bbox"][0] + line["bbox"][2]) / 2
            centeredness = -abs(cx - width / 2)
            return (line["median_font_size"], centeredness)

        candidates.sort(key=_score, reverse=True)
        best = candidates[0]
        best_fs = best["median_font_size"]

        # Gather all candidate lines with font size >= 60% of best, sorted by y
        min_fs = best_fs * 0.60
        pool = [l for l in candidates if l["median_font_size"] >= min_fs]
        pool.sort(key=lambda l: l["bbox"][1])

        # Build a contiguous cluster containing the best line
        # A gap larger than 3× the best line's height breaks the cluster
        line_h = max(best["bbox"][3] - best["bbox"][1], 12.0)
        gap_thresh = line_h * 3.0

        cluster: List[Dict] = []
        for line in pool:
            if not cluster:
                cluster.append(line)
            else:
                prev_y1 = cluster[-1]["bbox"][3]
                cur_y0 = line["bbox"][1]
                if cur_y0 - prev_y1 <= gap_thresh:
                    cluster.append(line)
                else:
                    # Gap too large — if we haven't passed the best yet, restart
                    if not any(l is best for l in cluster):
                        cluster = [line]
                    else:
                        break  # Already past the best; stop extending

        if not any(l is best for l in cluster):
            cluster = [best]

        # Deduplicate: some PDFs render the title multiple times as a design
        # layer (watermark effect). Keep only unique consecutive lines.
        seen: set = set()
        deduped = []
        for l in cluster:
            t = l["text"].strip()
            if t not in seen:
                seen.add(t)
                deduped.append(l)
        cluster = deduped

        combined_text = " ".join(l["text"].strip() for l in cluster).strip()
        if combined_text and len(combined_text) > 1:
            combined_bbox = [
                min(l["bbox"][0] for l in cluster),
                min(l["bbox"][1] for l in cluster),
                max(l["bbox"][2] for l in cluster),
                max(l["bbox"][3] for l in cluster),
            ]
            return {
                "text": combined_text,
                "page": page_num,
                "bbox": combined_bbox,
                "font_size": best_fs,
            }
    return None


def _is_valid_author(text: str, title_info: Optional[Dict]) -> bool:
    """
    Return False if the candidate text is clearly a book title rather than
    a personal name.
    """
    if AVOID_AUTHOR_RE.search(text):
        return False
    if PUBLISHER_FOOTER_RE.search(text):
        return False
    # Reject if it contains common title-domain words
    if TITLE_WORD_RE.search(text):
        return False
    # Reject if it duplicates (or is a sub/super-string of) the title
    if title_info:
        t_low = re.sub(r"\s+", " ", title_info["text"].lower().strip())
        a_low = re.sub(r"\s+", " ", text.lower().strip())
        if a_low == t_low or a_low in t_low or t_low in a_low:
            return False
    return True


def _page_is_complete_title_page(pd: Dict) -> bool:
    """
    Heuristic: a page is a 'complete' title page when it has text in the top,
    middle, AND bottom bands — indicating title + author + publisher layout.
    """
    height = pd["height"]
    spans = pd["spans"]
    has_top = any(s["bbox"][1] < height * 0.40 for s in spans)
    has_mid = any(height * 0.30 < s["bbox"][1] < height * 0.72 for s in spans)
    has_bot = any(s["bbox"][1] > height * 0.68 for s in spans)
    return has_top and has_mid and has_bot


def extract_author(pages: List[Dict], title_info: Optional[Dict]) -> Optional[Dict]:
    """
    Find author across pages 1–4. Prefers the 'complete title page' (usually
    page 3 in this corpus) over a minimal catalog entry on page 1.
    Priority: "By <Name>" > honorific prefix name > name-like line.
    Rejects candidates that look like titles (contain stop/topic words).
    """
    if not pages:
        return None

    # Sort candidate pages: complete title pages first, then by page number
    candidate_pages = list(pages[:4])
    candidate_pages.sort(
        key=lambda p: (0 if _page_is_complete_title_page(p) else 1, p["page_num"])
    )

    for pd in candidate_pages:
        height = pd["height"]
        page_num = pd["page_num"]

        # Middle band: avoid very top (title) and very bottom (publisher footer)
        mid_top = height * 0.25
        mid_bottom = height * 0.78

        region = [
            s for s in pd["spans"]
            if s["bbox"][1] >= mid_top and s["bbox"][1] <= mid_bottom
        ]
        lines = group_into_lines(region)

        # Pass 1: "By <Name>" pattern
        for line in lines:
            m = BY_AUTHOR_RE.match(line["text"].strip())
            if m:
                author_text = m.group(1).strip()
                if author_text and _is_valid_author(author_text, title_info):
                    return {"text": author_text, "page": page_num, "bbox": line["bbox"]}

        # Pass 2: name-like lines (2–6 tokens, no digits, passes validity checks)
        for line in lines:
            text = line["text"].strip()
            if not _is_valid_author(text, title_info):
                continue
            if NAME_LIKE_RE.match(text) and not any(c.isdigit() for c in text):
                words = text.split()
                # Allow single-word name when an honorific prefix is present (e.g. "Dr. Ritu")
                has_honorific = bool(HONORIFIC_RE.match(text))
                min_words = 1 if has_honorific else 2
                if min_words <= len(words) <= 7:
                    return {"text": text, "page": page_num, "bbox": line["bbox"]}

    return None


PUBLISHED_BY_RE = re.compile(r"^published\s+by\s*$", re.IGNORECASE)


def extract_publisher(pages: List[Dict]) -> Optional[Dict]:
    """
    Find publisher across pages 1–4.
    Strategy 1 (highest priority): line immediately after "Published by" on any page.
    Strategy 2: keyword match in bottom 30% of page 1/3 (the visual title page footer).
    Strategy 3: ALL-CAPS org name in bottom 30% of page 1 or 3.
    """
    candidates: List[Dict] = []

    for pd in pages[:4]:
        height = pd["height"]
        page_num = pd["page_num"]
        bottom_threshold = height * 0.70
        lines = group_into_lines(pd["spans"])

        for i, line in enumerate(lines):
            text = line["text"].strip()
            y0 = line["bbox"][1]

            # Strategy 1: "Published by" label → next non-empty line is the publisher
            if PUBLISHED_BY_RE.match(text):
                for j in range(i + 1, min(len(lines), i + 3)):
                    next_text = lines[j]["text"].strip()
                    if next_text and not ADDRESS_RE.search(next_text):
                        candidates.append({
                            "text": next_text,
                            "page": page_num,
                            "bbox": lines[j]["bbox"],
                            "score": 10,  # highest priority
                        })
                        break
                continue

            # Strategy 2: keyword match
            if PUBLISHER_KEYWORDS_RE.search(text):
                score = 0
                if page_num in (1, 3) and y0 >= bottom_threshold:
                    score += 4
                elif page_num <= 2:
                    score += 1
                for j in range(max(0, i - 3), min(len(lines), i + 4)):
                    if ADDRESS_RE.search(lines[j]["text"]):
                        score += 2
                        break
                candidates.append(
                    {"text": text, "page": page_num, "bbox": line["bbox"], "score": score}
                )

        # Strategy 3: ALL-CAPS org name in bottom 30% of page 1 or 3
        if page_num in (1, 3):
            for line in lines:
                text = line["text"].strip()
                y0 = line["bbox"][1]
                if (
                    y0 >= bottom_threshold
                    and text == text.upper()
                    and len(text) > 4
                    and re.sub(r"[\s&.,'-]", "", text).isalpha()
                    and not any(c["text"] == text for c in candidates)
                ):
                    candidates.append(
                        {"text": text, "page": page_num, "bbox": line["bbox"], "score": 3}
                    )

    if not candidates:
        return None

    candidates.sort(key=lambda c: c["score"], reverse=True)
    best = candidates[0]
    return {"text": best["text"], "page": best["page"], "bbox": best.get("bbox")}


def extract_isbn_info(pages: List[Dict]) -> Optional[Dict]:
    """
    Extract and validate ISBN-13 from first MAX_PAGES pages.
    Prefers page 2 and lines near 'ISBN' tokens.
    """
    # Prefer page 2 first, then scan all pages in order
    ordered = sorted(
        pages, key=lambda p: (0 if p["page_num"] == 2 else 1, p["page_num"])
    )

    for pd in ordered:
        page_num = pd["page_num"]
        lines = group_into_lines(pd["spans"])

        # Focused scan: lines containing 'isbn'
        for i, line in enumerate(lines):
            if "isbn" in line["text"].lower():
                isbn, raw = extract_isbn(line["text"])
                if isbn:
                    return {
                        "isbn": isbn,
                        "raw": raw,
                        "text": line["text"],
                        "page": page_num,
                    }
                # Check ±2 neighbour lines
                for j in range(max(0, i - 2), min(len(lines), i + 3)):
                    isbn, raw = extract_isbn(lines[j]["text"])
                    if isbn:
                        return {
                            "isbn": isbn,
                            "raw": raw,
                            "text": lines[j]["text"],
                            "page": page_num,
                        }

        # Full page sweep — join all lines
        full_text = " ".join(l["text"] for l in lines)
        isbn, raw = extract_isbn(full_text)
        if isbn:
            return {"isbn": isbn, "raw": raw, "text": raw or "", "page": page_num}

        # Fragmented-span sweep: collapse spaces around hyphens, then retry.
        # Handles cases like "ISBN : 978-81-19396-" + "99" + "-" + "3" on separate spans.
        collapsed = re.sub(r"\s*-\s*", "-", full_text)
        isbn, raw = extract_isbn(collapsed)
        if isbn:
            return {"isbn": isbn, "raw": raw, "text": raw or "", "page": page_num}

        # Last resort: join all raw span texts without ANY separator and scan for
        # 13-digit bare ISBN embedded in concatenated string.
        raw_spans = sorted(pd["spans"], key=lambda s: (s["bbox"][1], s["bbox"][0]))
        joined = "".join(s["text"] for s in raw_spans)
        for m in re.finditer(r"97[89]\d{10}", joined):
            candidate = m.group(0)
            if validate_isbn13(candidate):
                return {"isbn": candidate, "raw": candidate, "text": candidate, "page": page_num}

    return None


def extract_copyright(pages: List[Dict]) -> Tuple[str, Optional[Dict]]:
    """
    Determine copyright holder. Handles two common layouts:
    (A) Single line: "© Publisher" / "All rights reserved with the Publisher"
    (B) Split spans: '©' on one span + 'Publisher'/'Author' on a nearby span
        (y-offset up to ~10px — wider tolerance than default line grouping)
    Priority: page 2 > page 4 > others.
    """
    ordered = sorted(
        pages,
        key=lambda p: (0 if p["page_num"] == 2 else (1 if p["page_num"] == 4 else 2), p["page_num"]),
    )

    for pd in ordered:
        page_num = pd["page_num"]

        # Use wider y-tolerance to join split © + Publisher spans
        lines = group_into_lines(pd["spans"], y_tolerance=10.0)

        for i, line in enumerate(lines):
            text = line["text"].strip()
            if not COPYRIGHT_RE.search(text):
                continue

            # If the line only contains "©" or "copyright" without the holder,
            # look at the immediately adjacent lines for "Publisher" / "Author"
            combined = text
            if len(text) <= 3 or text in ("©", "copyright", "Copyright"):
                for j in (i - 1, i + 1):
                    if 0 <= j < len(lines):
                        combined = text + " " + lines[j]["text"].strip()
                        break

            holder = "unknown"
            cl = combined.lower()
            if PUBLISHER_COPYRIGHT_RE.search(combined):
                holder = "publisher"
            elif AUTHOR_COPYRIGHT_RE.search(combined):
                holder = "author"
            elif EDITOR_COPYRIGHT_RE.search(combined):
                holder = "editor"
            elif re.search(r"all\s+rights\s+reserved", combined, re.IGNORECASE):
                if "publisher" in cl:
                    holder = "publisher"
                elif "author" in cl:
                    holder = "author"
                elif "editor" in cl:
                    holder = "editor"
                else:
                    holder = "reserved"
            elif "publisher" in cl:
                holder = "publisher"
            elif "author" in cl:
                holder = "author"
            elif "editor" in cl:
                holder = "editor"

            # If still unknown, try to extract the actual entity name after ©
            # e.g. "© National Book Trust" → "National Book Trust"
            if holder == "unknown":
                m = _COPYRIGHT_ENTITY_RE.search(combined)
                if m:
                    entity = m.group(1).strip().rstrip(".,")
                    if entity and not _GENERIC_COPYRIGHT_WORDS.match(entity):
                        holder = entity

            return holder, {"text": combined.strip(), "page": page_num, "bbox": line["bbox"]}

    return "unknown", None


# ── helpers ───────────────────────────────────────────────────────────────────

# Patterns characteristic of legacy Devanagari-to-ASCII font encoding artefacts
_GARBLED_RE = re.compile(
    r"[;<>=\[\]]"      # ; = [ ] < > — very unusual in book titles
    r"|\^{2}"          # ^^ double caret
    r"|/[a-z]"         # /k /j etc. (garbled consonant combos)
    r"|\.[a-z]{2}"     # .kk .kl etc. (garbled conjunct)
    r"|\+[a-z]"        # +s +h etc.
)


def _looks_garbled(text: str) -> bool:
    """Return True if the text appears to be garbled encoding (short, mostly non-ASCII,
    or Devanagari-encoded-as-Latin artefacts) — used to decide whether to prefer
    the vision model's title over the deterministic extraction."""
    if not text or len(text) < 5:
        return True
    # Extended Latin / Latin-1 Supplement characters (0x80–0xFF) are a strong signal
    if any(0x80 <= ord(c) <= 0xFF for c in text):
        return True
    # Known garbled Devanagari-as-ASCII symbol patterns
    if _GARBLED_RE.search(text):
        return True
    # Mixed-case within words: legacy Hindi fonts map chars to uppercase letters
    # mid-word — e.g. "LoLFk", "fgUnh", "dSls". Count words where an uppercase
    # letter appears after the first character. If >30% of multi-char words have
    # this pattern, the text is very likely garbled transliteration.
    words = [w for w in text.split() if len(w) > 2 and w.isalpha()]
    if words:
        mid_upper = sum(1 for w in words if any(c.isupper() for c in w[1:]))
        if mid_upper / len(words) > 0.30:
            return True
    # Starts with a digit — only garbled if the rest is very short or also garbled
    # (avoids false positives like "157 FAMOUS STORIES OF TAGORE")
    if text[0].isdigit():
        rest = text.lstrip("0123456789").strip()
        if len(rest) < 8 or _GARBLED_RE.search(rest) or any(0x80 <= ord(c) <= 0xFF for c in rest):
            return True
    return False


# ── confidence + result assembly ─────────────────────────────────────────────

def compute_confidence(
    title: Optional[Dict],
    author: Optional[Dict],
    publisher: Optional[Dict],
    isbn_info: Optional[Dict],
    copyright_holder: str,
    copyright_found: bool,
) -> float:
    score = 0.0
    if title:
        score += 1.2
    if author:
        score += 1.0
    if publisher:
        score += 1.0
    if isbn_info:
        score += 1.5
    if copyright_found and copyright_holder != "unknown":
        score += 0.3
    return round(min(1.0, score / 5.0), 3)


def extract_metadata(pdf_path: str, file_name: str) -> Dict[str, Any]:
    """
    Main entry point: run deterministic heuristics, optionally call LLM fallback.
    """
    import os

    pages = extract_layout(pdf_path)

    if not pages:
        return _empty_result(file_name, error="Could not extract any pages from PDF")

    title_info = extract_title(pages)
    author_info = extract_author(pages, title_info)
    publisher_info = extract_publisher(pages)
    isbn_info = extract_isbn_info(pages)
    copyright_holder, copyright_info = extract_copyright(pages)

    # Filename fallback: if text extraction found no ISBN, try deriving it from
    # the filename (e.g. "978-81-19318-15-5.pdf" → "9788119318155")
    if not isbn_info:
        fn_isbn = isbn_from_filename(file_name)
        if fn_isbn:
            isbn_info = {"isbn": fn_isbn, "raw": fn_isbn, "text": f"(from filename: {file_name})", "page": 0}

    evidence: Dict[str, Any] = {}
    if title_info:
        evidence["title"] = {"text": title_info["text"], "page": title_info["page"]}
    if author_info:
        evidence["author"] = {"text": author_info["text"], "page": author_info["page"]}
    if publisher_info:
        evidence["publisher"] = {
            "text": publisher_info["text"],
            "page": publisher_info["page"],
        }
    if isbn_info:
        evidence["isbn"] = {"text": isbn_info.get("text", ""), "page": isbn_info["page"]}
    if copyright_info:
        evidence["copyright"] = {
            "text": copyright_info["text"],
            "page": copyright_info["page"],
        }

    confidence = compute_confidence(
        title_info,
        author_info,
        publisher_info,
        isbn_info,
        copyright_holder,
        copyright_info is not None,
    )
    needs_review = confidence < 0.75 or not all(
        [title_info, author_info, publisher_info, isbn_info]
    )

    result: Dict[str, Any] = {
        "file_name": file_name,
        "title": title_info["text"] if title_info else None,
        "author": author_info["text"] if author_info else None,
        "publisher": publisher_info["text"] if publisher_info else None,
        "isbn": isbn_info["isbn"] if isbn_info else None,
        "copyright_holder": copyright_holder,
        "confidence": confidence,
        "needs_review": needs_review,
        "llm_used": False,
        "evidence": evidence,
        "error": None,
    }

    import logging as _logging
    _log = _logging.getLogger(__name__)

    # LLM fallback for low-confidence or missing fields
    if needs_review and os.getenv("OPENAI_API_KEY"):
        try:
            from app.extraction.llm_fallback import llm_extract

            llm_result = llm_extract(pages, result)
            if llm_result:
                # Don't let LLM hallucinate copyright when no copyright line exists in PDF
                if copyright_info is None:
                    llm_result.pop("copyright_holder", None)
                result.update(llm_result)
                result["llm_used"] = True
        except Exception as _e:
            _log.warning("llm_extract failed for %s: %s", file_name, _e, exc_info=True)

    # Vision fallback: use GPT-4o with rendered page images when:
    #  • title is garbled (legacy Devanagari-as-ASCII) or completely missing
    #  • author or publisher is missing
    # This covers Hindi/Devanagari PDFs and image-only PDFs.
    title_val = result.get("title") or ""
    still_missing = (
        not result.get("author")
        or not result.get("publisher")
        or not title_val
        or _looks_garbled(title_val)
    )
    _log.info(
        "vision check — file=%s still_missing=%s key_set=%s garbled=%s",
        file_name, still_missing, bool(os.getenv("OPENAI_API_KEY")), _looks_garbled(title_val),
    )
    if still_missing and os.getenv("OPENAI_API_KEY"):
        try:
            from app.extraction.vision_fallback import vision_extract

            vision_result = vision_extract(pdf_path, result)
            if vision_result:
                for field in ("title", "author", "publisher", "isbn"):
                    vval = vision_result.get(field)
                    cur = result.get(field)
                    if not cur and vval:
                        result[field] = vval
                    elif field == "title" and vval and _looks_garbled(cur or ""):
                        # Deterministic title looks garbled (Devanagari/image) — trust vision
                        result[field] = vval
                # Update copyright_holder when still unknown — but only if
                # a copyright line was actually found in the PDF (not LLM guess)
                vcr = vision_result.get("copyright_holder")
                if (
                    copyright_info is not None
                    and result.get("copyright_holder") == "unknown"
                    and vcr
                    and vcr != "unknown"
                ):
                    result["copyright_holder"] = vcr
                # Update confidence and needs_review from vision
                if vision_result.get("confidence", 0) > result.get("confidence", 0):
                    result["confidence"] = vision_result["confidence"]
                result["needs_review"] = vision_result.get("needs_review", result["needs_review"])
                result["llm_used"] = True
            else:
                _log.warning("vision_extract returned None for %s", file_name)
        except Exception as _e:
            _log.warning("vision_extract raised for %s: %s", file_name, _e, exc_info=True)

    return result


def _empty_result(file_name: str, error: Optional[str] = None) -> Dict[str, Any]:
    return {
        "file_name": file_name,
        "title": None,
        "author": None,
        "publisher": None,
        "isbn": None,
        "copyright_holder": "unknown",
        "confidence": 0.0,
        "needs_review": True,
        "llm_used": False,
        "evidence": {},
        "error": error,
    }

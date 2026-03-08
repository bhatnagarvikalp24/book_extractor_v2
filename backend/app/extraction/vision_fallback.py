"""
GPT-4o Vision fallback for Hindi/Devanagari PDFs and image-only PDFs where
deterministic text extraction produces garbled or empty results.
"""

import base64
import json
import os
import re
from typing import Any, Dict, List, Optional

from .isbn_validator import normalize_isbn, validate_isbn13

VISION_SYSTEM_PROMPT = """You are a book metadata extractor specializing in Indian academic and educational books.
You will receive images of the first pages of a PDF book (title page, copyright page, etc.).

The content may be in English or Hindi (Devanagari script). For Hindi text, read it directly.
For any language, extract:
- title: The main book title
- author: Author name(s), including any honorifics like Dr., Prof., Er., Sh., Smt.
- publisher: Publisher / Prakashan name (not author)
- isbn: 13-digit ISBN starting with 978 or 979 (digits only — no hyphens)
- copyright_holder: exactly one of "publisher", "author", or "unknown"

Return ONLY a single valid JSON object — no markdown, no code fences, no extra text:
{
  "title": "string or null",
  "author": "string or null",
  "publisher": "string or null",
  "isbn": "string or null",
  "copyright_holder": "publisher",
  "confidence": 0.85,
  "needs_review": false
}

Rules:
- ISBN: return ONLY the 13 digits with no hyphens, spaces, or other characters.
- If a field is not visible or not determinable, return null (not a string "null").
- confidence: 0.0–1.0 reflecting how certain you are about the extracted values.
- needs_review: true if confidence < 0.75 or any of title/author/publisher/isbn is null."""


def render_pages_as_b64(pdf_path: str, page_indices: List[int], scale: float = 1.5) -> List[str]:
    """Render PDF pages as base64-encoded JPEG strings (PNG fallback)."""
    import logging
    _log = logging.getLogger(__name__)

    try:
        import fitz  # PyMuPDF
    except ImportError:
        _log.warning("render_pages_as_b64: fitz not available")
        return []

    images: List[str] = []
    try:
        doc = fitz.open(pdf_path)
        mat = fitz.Matrix(scale, scale)
        for idx in page_indices:
            if idx >= len(doc):
                continue
            try:
                pix = doc[idx].get_pixmap(matrix=mat, alpha=False)
                try:
                    data = pix.tobytes("jpeg")
                    mime = "jpeg"
                except Exception:
                    # JPEG not available in this build — fall back to PNG
                    data = pix.tobytes("png")
                    mime = "png"
                b64 = base64.b64encode(data).decode("utf-8")
                images.append(f"data:image/{mime};base64,{b64}")
            except Exception as e:
                _log.warning("render page %d failed for %s: %s", idx, pdf_path, e)
        doc.close()
    except Exception as e:
        _log.warning("render_pages_as_b64 failed for %s: %s", pdf_path, e, exc_info=True)
    _log.info("render_pages_as_b64: %d pages rendered for %s", len(images), pdf_path)
    return images


def vision_extract(pdf_path: str, current_result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Use GPT-4o Vision to extract metadata from rendered page images.
    Returns a partial update dict compatible with extract_metadata(), or None on failure.
    Renders pages 1–4 (indices 0–3) and sends them to the model.
    """
    try:
        from openai import OpenAI
    except ImportError:
        return None

    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        return None

    images = render_pages_as_b64(pdf_path, page_indices=[0, 1, 2, 3])
    if not images:
        return None

    client = OpenAI(api_key=api_key)

    content: List[Any] = [
        {
            "type": "text",
            "text": (
                "These are the first pages of a book PDF. "
                f"Partial extraction so far — "
                f"title={current_result.get('title')!r}, "
                f"author={current_result.get('author')!r}, "
                f"publisher={current_result.get('publisher')!r}, "
                f"isbn={current_result.get('isbn')!r}. "
                "Please extract all metadata fields from the images and return JSON."
            ),
        }
    ]
    for data_uri in images:
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": data_uri, "detail": "high"},
            }
        )

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": VISION_SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            temperature=0,
            max_tokens=600,
        )
        raw = response.choices[0].message.content.strip()

        # Strip markdown code fences if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

        json_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not json_match:
            return None

        data: Dict[str, Any] = json.loads(json_match.group())

        # Validate ISBN — keep deterministic value if vision result is bad
        raw_isbn = data.get("isbn")
        if raw_isbn:
            normalized = normalize_isbn(str(raw_isbn))
            if validate_isbn13(normalized):
                data["isbn"] = normalized
            else:
                data["isbn"] = current_result.get("isbn")

        # Sanitize placeholder strings
        for field in ("title", "author", "publisher", "isbn"):
            if data.get(field) in ("...", "null", "N/A", "", "None"):
                data[field] = None

        # Prefer deterministic ISBN if vision couldn't find one
        if not data.get("isbn") and current_result.get("isbn"):
            data["isbn"] = current_result["isbn"]

        # Recompute needs_review
        conf = float(data.get("confidence", 0.5))
        data["needs_review"] = conf < 0.75 or not all(
            [data.get("title"), data.get("author"), data.get("publisher"), data.get("isbn")]
        )

        allowed = {
            "title", "author", "publisher", "isbn",
            "copyright_holder", "confidence", "needs_review",
        }
        return {k: v for k, v in data.items() if k in allowed}

    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(
            "vision_extract failed for %s: %s", pdf_path, exc, exc_info=True
        )
        return None

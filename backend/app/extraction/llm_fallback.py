import json
import os
import re
from typing import Any, Dict, List, Optional

from .isbn_validator import normalize_isbn, validate_isbn13

KEYWORD_RE = re.compile(
    r"ISBN|Published|Publishing|Press|Prakashan|©|Copyright|All\s+rights\s+reserved",
    re.IGNORECASE,
)


def build_snippet(pages: List[Dict], max_lines: int = 45) -> str:
    """
    Collect relevant lines from PDF pages:
    - Top 40% of page 1
    - Bottom 30% of page 1
    - Keyword-containing lines from all pages
    """
    from .heuristics import group_into_lines

    snippets: List[str] = []

    if pages:
        pd = pages[0]
        height = pd["height"]
        lines = group_into_lines(pd["spans"])

        top_lines = [l for l in lines if l["bbox"][1] < height * 0.40][:15]
        for l in top_lines:
            snippets.append(f"[p1-top] {l['text']}")

        bottom_lines = [l for l in lines if l["bbox"][1] > height * 0.70][:12]
        for l in bottom_lines:
            snippets.append(f"[p1-bottom] {l['text']}")

    for pd in pages:
        lines = group_into_lines(pd["spans"])
        for l in lines:
            if KEYWORD_RE.search(l["text"]):
                tag = f"[p{pd['page_num']}]"
                entry = f"{tag} {l['text']}"
                if entry not in snippets:
                    snippets.append(entry)

    return "\n".join(snippets[:max_lines])


SYSTEM_PROMPT = """You are a book metadata extractor. You will receive text snippets extracted from a PDF (with page/region tags) and a partial extraction result.

Return ONLY a single valid JSON object with exactly these fields:
{
  "title": "string or null",
  "author": "string or null",
  "publisher": "string or null",
  "isbn": "string or null",
  "copyright_holder": "publisher|author|unknown",
  "confidence": 0.0,
  "needs_review": true,
  "evidence": {
    "title": {"text": "...", "page": 1},
    "author": {"text": "...", "page": 1},
    "publisher": {"text": "...", "page": 1},
    "isbn": {"text": "...", "page": 1},
    "copyright": {"text": "...", "page": 1}
  }
}

Rules:
- Only include evidence values that appear verbatim in the snippets.
- ISBN must be a 13-digit number starting with 978 or 979 (no hyphens in the returned value).
- If a field cannot be found in the snippets, return null.
- confidence: 0.0–1.0 based on how certain you are.
- needs_review: true if confidence < 0.75 or any key field is null.
- Do NOT output markdown, code fences, or extra text — only the raw JSON object."""


def llm_extract(pages: List[Dict], current_result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Call OpenAI gpt-4o-mini for metadata extraction. Returns partial update dict or None."""
    try:
        from openai import OpenAI
    except ImportError:
        return None

    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        return None

    client = OpenAI(api_key=api_key)
    snippet = build_snippet(pages)

    user_prompt = (
        f"PDF text snippets:\n{snippet}\n\n"
        f"Partial extraction (may be incomplete or wrong):\n"
        f"title: {current_result.get('title')}\n"
        f"author: {current_result.get('author')}\n"
        f"publisher: {current_result.get('publisher')}\n"
        f"isbn: {current_result.get('isbn')}\n\n"
        "Extract and return the metadata JSON."
    )

    for attempt in range(2):
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0,
                max_tokens=900,
            )
            content = response.choices[0].message.content.strip()

            # Strip markdown fences if present
            content = re.sub(r"^```(?:json)?\s*", "", content)
            content = re.sub(r"\s*```$", "", content)

            json_match = re.search(r"\{.*\}", content, re.DOTALL)
            if not json_match:
                continue

            data: Dict[str, Any] = json.loads(json_match.group())

            # Validate and sanitize ISBN
            raw_isbn = data.get("isbn")
            if raw_isbn:
                normalized = normalize_isbn(str(raw_isbn))
                if validate_isbn13(normalized):
                    data["isbn"] = normalized
                else:
                    # Fall back to deterministic ISBN if valid
                    det_isbn = current_result.get("isbn")
                    data["isbn"] = det_isbn  # may be None
                    # Penalise confidence
                    data["confidence"] = max(0.0, float(data.get("confidence", 0.5)) - 0.15)

            # Recompute needs_review
            conf = float(data.get("confidence", 0.5))
            data["needs_review"] = conf < 0.75 or not all(
                [data.get("title"), data.get("author"), data.get("publisher"), data.get("isbn")]
            )

            # Sanitize evidence: remove placeholder "..." values
            evidence = data.get("evidence", {})
            if isinstance(evidence, dict):
                data["evidence"] = {
                    k: v for k, v in evidence.items()
                    if isinstance(v, dict)
                    and v.get("text") not in (None, "", "...", "null")
                }

            # Nullify string fields that are placeholders
            for field in ("title", "author", "publisher", "isbn"):
                if data.get(field) in ("...", "null", "N/A", ""):
                    data[field] = None

            # Only return fields that exist in our schema
            allowed = {
                "title", "author", "publisher", "isbn",
                "copyright_holder", "confidence", "needs_review", "evidence",
            }
            return {k: v for k, v in data.items() if k in allowed}

        except (json.JSONDecodeError, Exception):
            if attempt == 1:
                return None

    return None

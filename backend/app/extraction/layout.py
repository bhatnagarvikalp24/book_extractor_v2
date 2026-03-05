import fitz  # PyMuPDF
from typing import List, Dict, Any
from app.config import MAX_PAGES


def extract_layout(pdf_path: str) -> List[Dict[str, Any]]:
    """Extract text spans with layout info from first MAX_PAGES pages."""
    pages_data = []
    doc = fitz.open(pdf_path)

    for page_num in range(min(MAX_PAGES, len(doc))):
        page = doc[page_num]
        page_dict = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
        width = page.rect.width
        height = page.rect.height

        spans = []
        for block in page_dict.get("blocks", []):
            if block.get("type") != 0:  # text blocks only
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "").strip()
                    if not text:
                        continue
                    spans.append(
                        {
                            "text": text,
                            "bbox": list(span.get("bbox", [0, 0, 0, 0])),
                            "font_size": span.get("size", 0),
                            "flags": span.get("flags", 0),
                            "font": span.get("font", ""),
                        }
                    )

        pages_data.append(
            {
                "page_num": page_num + 1,  # 1-indexed
                "width": width,
                "height": height,
                "spans": spans,
            }
        )

    doc.close()
    return pages_data

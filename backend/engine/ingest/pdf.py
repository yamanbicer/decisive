"""PDF slide-deck extraction: embedded text + each page rendered to a JPEG (for the
vision model). pypdfium2 (permissive Apache/BSD) + Pillow — no system packages.

Pure local CPU work, no API key, so it slots into the keyless boot path. A malformed
or locked PDF degrades to an empty result rather than crashing the pipeline.
"""
from __future__ import annotations

import io
from typing import Any

import weave


@weave.op()
def extract_pdf(data: bytes, *, max_pages: int = 25, dpi: int = 120,
                long_side: int = 1024) -> dict[str, Any]:
    """Return {n_pages, text, pages:[{page, text, image(jpeg bytes)}]}.

    Renders + encodes one page at a time (pixmap RAM control) and caps at
    max_pages. Empty page text (scanned decks) is expected — the image is the
    vision fallback.
    """
    empty = {"n_pages": 0, "text": "", "pages": []}
    try:
        import pypdfium2 as pdfium  # lazy: optional dep, keep keyless boot working
        from PIL import Image  # noqa: F401  (used via to_pil)
    except Exception:
        return empty
    try:
        pdf = pdfium.PdfDocument(data)
    except Exception:
        return empty

    pages: list[dict] = []
    full_text: list[str] = []
    try:
        n = len(pdf)
        for i in range(min(n, max_pages)):
            page = pdf[i]
            text = ""
            try:
                tp = page.get_textpage()
                text = (tp.get_text_bounded() or "").strip()
                tp.close()
            except Exception:
                text = ""
            image = b""
            try:
                bmp = page.render(scale=dpi / 72)
                img = bmp.to_pil().convert("RGB")
                img.thumbnail((long_side, long_side))
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=72)
                image = buf.getvalue()
            except Exception:
                image = b""
            finally:
                try:
                    page.close()
                except Exception:
                    pass
            if text:
                full_text.append(f"[slide {i + 1}] {text}")
            pages.append({"page": i + 1, "text": text, "image": image})
        return {"n_pages": n, "text": "\n\n".join(full_text), "pages": pages}
    except Exception:
        return {"n_pages": len(pages), "text": "\n\n".join(full_text), "pages": pages}
    finally:
        try:
            pdf.close()
        except Exception:
            pass

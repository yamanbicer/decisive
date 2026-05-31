"""Optional URL/website source: scrape a landing page to markdown via Firecrawl and
fold it into the brief. Reuses settings.firecrawl_api_key; calls the Firecrawl v1 API
directly over httpx (already a dependency) — no new package, no coupling to the
agent web-research module. Returns '' (mock/skip) when no key or on any failure.
"""
from __future__ import annotations

import weave

from ...config import get_settings

_FIRECRAWL_SCRAPE = "https://api.firecrawl.dev/v1/scrape"
_MAX_CHARS = 8000


@weave.op()
async def scrape_url(url: str) -> str:
    s = get_settings()
    if not url or not s.firecrawl_api_key:
        return ""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                _FIRECRAWL_SCRAPE,
                headers={"Authorization": f"Bearer {s.firecrawl_api_key}"},
                json={"url": url, "formats": ["markdown"], "onlyMainContent": True})
            r.raise_for_status()
            data = r.json().get("data", {}) or {}
            return (data.get("markdown") or "").strip()[:_MAX_CHARS]
    except Exception:
        return ""

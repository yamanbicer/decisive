"""Supabase client factory. Returns None when Supabase isn't configured yet,
so the rest of the app can fall back to the in-memory store (repository.py)."""
from functools import lru_cache
from typing import Optional

from ..config import get_settings


@lru_cache
def get_supabase() -> Optional[object]:
    s = get_settings()
    if not s.supabase_enabled:
        return None
    from supabase import create_client  # lazy: only needed when configured

    return create_client(s.supabase_url, s.supabase_service_key)

"""Supabase client. Server side only: the service key must never reach the browser."""
from functools import lru_cache

from .errors import AppError
from .settings import get_settings


@lru_cache
def get_supabase():
    s = get_settings()
    if not s.supabase_configured:
        raise AppError("DB_NOT_CONFIGURED", "Set SUPABASE_URL and SUPABASE_SERVICE_KEY in .env", 503)
    from supabase import create_client
    return create_client(s.supabase_url, s.supabase_service_key)


def execute(query, attempts: int = 3):
    """Run a PostgREST query, retrying when the shared HTTP/2 connection drops under concurrent requests."""
    import httpx
    for i in range(attempts):
        try:
            return query.execute()
        except (httpx.RemoteProtocolError, httpx.ConnectError, httpx.ReadError):
            if i == attempts - 1:
                raise

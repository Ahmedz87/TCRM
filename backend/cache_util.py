"""
cache_util.py — app-wide response cache (in-memory, TTL) so pages load instantly.

A single HTTP middleware caches successful GET responses keyed by (path + query + the caller's
auth token). So:
  • repeat loads of any page return the stored copy in microseconds (no re-running heavy SQL),
  • the copy auto-refreshes after TTL seconds (default 45s) — never stale-forever,
  • any write (POST/PUT/PATCH/DELETE) flushes the read cache so your edits appear immediately,
  • keying by token means each user/role only ever sees their own cached data (no leakage).

Real-time / auth paths are skipped (see SKIP). In-process only (one backend worker) — move to
Redis when scaling to multiple workers/servers (see PRODUCTION_READINESS.md).
"""
import time
import threading
from starlette.responses import Response

TTL_DEFAULT = 45
MAX_ENTRIES = 5000
# never cache these (real-time, auth, docs) and their writes don't trigger a flush
SKIP = ("/dialer", "/auth", "/register", "/docs", "/openapi", "/redoc", "/favicon", "/ws",
        # read-only POSTs (bulk lookups) — must NOT bust the app-wide response cache;
        # /abuse/flags fires on every Clients render and was leaving the cache permanently empty
        "/abuse/flags", "/notifications")

_store = {}                 # key -> (payload, expiry_epoch)
_lock = threading.Lock()


def bust(prefix: str = ""):
    """Drop cached entries whose key starts with `prefix` (''=everything)."""
    with _lock:
        for k in [k for k in _store if k.startswith(prefix)]:
            _store.pop(k, None)


def stats():
    with _lock:
        return {"entries": len(_store)}


def _prune_locked():
    now = time.time()
    for k in [k for k, (_, exp) in _store.items() if exp < now]:
        _store.pop(k, None)
    if len(_store) > MAX_ENTRIES:        # safety valve
        _store.clear()


def _skip(path: str) -> bool:
    return any(path.startswith(p) for p in SKIP)


def install_cache(app, ttl: int = TTL_DEFAULT):
    @app.middleware("http")
    async def _cache_mw(request, call_next):
        path = request.url.path
        method = request.method

        if method == "GET" and not _skip(path):
            auth = request.headers.get("authorization", "")
            key = f"{path}?{request.url.query}|{auth}"
            now = time.time()
            with _lock:
                e = _store.get(key)
                hit = e if (e and e[1] > now) else None
            if hit:
                body, status, ct = hit[0]
                return Response(content=body, status_code=status, media_type=ct)
            resp = await call_next(request)
            if resp.status_code == 200:
                body = b""
                async for chunk in resp.body_iterator:
                    body += chunk
                ct = resp.headers.get("content-type", "application/json")
                with _lock:
                    if len(_store) >= MAX_ENTRIES:
                        _prune_locked()
                    _store[key] = ((body, resp.status_code, ct), now + ttl)
                return Response(content=body, status_code=resp.status_code, media_type=ct)
            return resp

        # writes: run, then flush the read cache so the next page load reflects the change
        resp = await call_next(request)
        if method != "GET" and not _skip(path) and 200 <= resp.status_code < 300:
            bust("")
        return resp

    return app

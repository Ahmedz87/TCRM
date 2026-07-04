"""
perf_cache.py — a tiny in-process TTL cache for expensive read endpoints.

Why: KPIs / leaderboards / IB & agent lists don't change second-to-second, but they're
costly to compute. Caching the result for a short TTL means repeated views (the same staff
member refreshing, or several people opening the same page) don't re-hit the DB every time.

Scope: in-process (per uvicorn worker). That's fine for read-only KPI-style data — at worst a
viewer sees data up to `ttl` seconds old. Always include the role/agent scope AND the filter
params in the key so one user's scoped data is never served to another.

Usage:
    from perf_cache import cached
    data = cached(f"dash:kpis:{period}:{scope_key}", ttl=60, compute=lambda: _compute(...))

To force-refresh after a write, call invalidate("dash:") (prefix match).
"""
import time
import threading

_lock = threading.Lock()
_store = {}          # key -> (expires_at_epoch, value)
_MAX = 3000          # safety cap on entries


def cached(key, ttl, compute):
    """Return the cached value for `key` if fresh, else call `compute()`, store, and return it.
    `compute` runs OUTSIDE the lock so a slow DB query never blocks other cache reads (a rare
    duplicate compute under a burst is acceptable — cheaper than holding the lock)."""
    now = time.time()
    with _lock:
        e = _store.get(key)
        if e is not None and e[0] > now:
            return e[1]
    value = compute()
    with _lock:
        _store[key] = (now + ttl, value)
        if len(_store) > _MAX:                      # opportunistic cleanup of expired entries
            for k in [k for k, v in _store.items() if v[0] <= now]:
                _store.pop(k, None)
    return value


def invalidate(prefix=""):
    """Drop all cache entries whose key starts with `prefix` ('' clears everything)."""
    with _lock:
        for k in [k for k in list(_store.keys()) if k.startswith(prefix)]:
            _store.pop(k, None)


def stats():
    now = time.time()
    with _lock:
        live = sum(1 for v in _store.values() if v[0] > now)
        return {"entries": len(_store), "live": live}

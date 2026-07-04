"""
rate_limit.py — tiny in-memory sliding-window rate limiter for the PUBLIC /register endpoints.

Keyed by (bucket, key), e.g. ("submit_ip", "1.2.3.4"). Protects the now-public signup from
bots spamming fake leads/clients, OTP-bombing a phone, or brute-forcing the OTP. In-process
(single worker) — move to Redis when scaling to multiple workers (see PRODUCTION_READINESS.md).
"""
import time
import threading

_hits = {}            # "bucket|key" -> [timestamps]
_lock = threading.Lock()


def client_ip(request):
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.headers.get("x-real-ip") or (request.client.host if request.client else "?")


def allow(bucket, key, limit, window_sec):
    """True if (bucket,key) is under `limit` hits within the last window_sec; records the hit."""
    now = time.time()
    k = f"{bucket}|{key}"
    with _lock:
        arr = [t for t in _hits.get(k, []) if t > now - window_sec]
        if len(arr) >= limit:
            _hits[k] = arr
            return False
        arr.append(now)
        _hits[k] = arr
        if len(_hits) > 20000:        # opportunistic prune of fully-expired keys
            for kk in [kk for kk, v in list(_hits.items()) if not any(t > now - 3600 for t in v)]:
                _hits.pop(kk, None)
    return True

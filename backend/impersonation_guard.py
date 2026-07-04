"""
impersonation_guard.py — make staff impersonation ("View as <user>") READ-ONLY.

A pure-ASGI middleware (deliberately NOT BaseHTTPMiddleware — that flavour conflicts with the
cache_util middleware, see main.py note). It inspects the bearer token on mutating requests; if the
token carries the `imp` claim (an admin viewing the CRM as another user) it rejects the write with
403 so the admin can look but not act as that person. GET/HEAD/OPTIONS always pass.

A tiny allowlist lets through the read-only POSTs the UI fires just to DECORATE list views
(e.g. /abuse/flags overlays abuse chips on the clients list) so the impersonated view still renders.
"""
from jose import jwt, JWTError
from starlette.responses import JSONResponse
from database import settings

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
# read-only POSTs the UI needs while viewing (substring match on the path)
READ_POST_ALLOW = ("/abuse/flags", "/abuse/type-counts")


class ReadOnlyImpersonationMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or scope.get("method") in SAFE_METHODS:
            return await self.app(scope, receive, send)

        path = scope.get("path", "")
        if any(p in path for p in READ_POST_ALLOW):
            return await self.app(scope, receive, send)

        # find the bearer token in the request headers
        auth = ""
        for k, v in scope.get("headers", []):
            if k == b"authorization":
                auth = v.decode("latin-1"); break
        if auth[:7].lower() == "bearer ":
            try:
                payload = jwt.decode(auth[7:], settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
                if payload.get("imp"):
                    resp = JSONResponse(
                        {"detail": "You are viewing as another user (read-only). Exit the preview to make changes."},
                        status_code=403)
                    return await resp(scope, receive, send)
            except JWTError:
                pass  # let normal auth handle a bad/expired token
        return await self.app(scope, receive, send)

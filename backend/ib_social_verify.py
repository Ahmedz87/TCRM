"""
ib_social_verify.py — validate a social/website link an IB applicant enters during signup.

Two tiers (see the product decision in the signup wizard):
  1. DOMAIN match — HARD. A link tagged "telegram" must be a t.me / telegram.me URL, etc.
     Wrong domain → rejected instantly (also re-checked server-side at register() so the
     client check can't be bypassed).
  2. EXISTENCE + name — BEST-EFFORT. We fetch the URL (browser-like) and:
       • a clear 404/410 → the page doesn't exist → fail (reliable negative);
       • 2xx/3xx → verified; if we can read the page, we also try to match the handle/name
         (informational — social sites often block bots, so a missing match never fails it);
       • a fetch that times out / is bot-blocked → accepted with a "couldn't fully auto-check"
         note, so a real IB is NEVER locked out by a platform we simply can't scrape.

SECURITY: this endpoint fetches a user-supplied URL, so it is an SSRF surface. Every host is
DNS-resolved and rejected if it maps to a private / loopback / link-local / reserved IP, and
only http(s) is allowed. Known social platforms are additionally domain-pinned.
"""
import re
import socket
import ipaddress
from urllib.parse import urlparse

import requests

# host suffixes allowed per platform (hard domain gate). "website"/"other" = no pin (any host,
# still SSRF-guarded). Keep these lowercase, no leading dot; matched as exact or subdomain.
PLATFORM_DOMAINS = {
    "telegram":  ["t.me", "telegram.me", "telegram.org", "telegram.dog"],
    "facebook":  ["facebook.com", "fb.com", "fb.me", "m.facebook.com"],
    "instagram": ["instagram.com", "instagr.am"],
    "youtube":   ["youtube.com", "youtu.be", "m.youtube.com"],
    "tiktok":    ["tiktok.com", "vm.tiktok.com"],
    "whatsapp":  ["wa.me", "whatsapp.com", "chat.whatsapp.com", "api.whatsapp.com"],
    "x":         ["x.com", "twitter.com", "mobile.twitter.com"],
    "snapchat":  ["snapchat.com", "story.snapchat.com"],
    "website":   [],   # any host
    "other":     [],   # any host
}

# platforms that routinely block server-side fetches (login wall / 999 / anti-bot). A failed
# fetch on these is treated as a soft pass, not a failure.
BOT_BLOCKED = {"instagram", "facebook", "tiktok", "x", "snapchat"}

# platforms we do NOT fetch at all: they serve a login wall / anti-bot page to any server request,
# so a LIVE page looks "dead" (e.g. facebook.com/<page> 302→ /login?next=… returns HTTP 400). We
# can only trust the domain here; existence is confirmed by the desk when the application is reviewed.
# Telegram (t.me) and YouTube DO expose a public page to bots, so they stay real-verified below.
SKIP_FETCH = {"facebook", "instagram", "tiktok", "x", "snapchat"}

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")


def _norm_url(raw: str) -> str:
    v = (raw or "").strip()
    if not v:
        return ""
    if not re.match(r"^https?://", v, re.I):
        v = "https://" + v
    return v


def _host_ok_for_platform(host: str, platform: str) -> bool:
    allowed = PLATFORM_DOMAINS.get(platform, [])
    if not allowed:                      # website / other / unknown → any host
        return True
    host = host.lower()
    return any(host == d or host.endswith("." + d) for d in allowed)


def _is_public_host(host: str) -> bool:
    """Resolve host and require EVERY address to be a public, routable IP (SSRF guard)."""
    if not host:
        return False
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception:
        return False
    for info in infos:
        ip = info[4][0]
        try:
            addr = ipaddress.ip_address(ip.split("%")[0])
        except ValueError:
            return False
        if (addr.is_private or addr.is_loopback or addr.is_link_local
                or addr.is_reserved or addr.is_multicast or addr.is_unspecified):
            return False
    return True


def _handle_from_url(url: str) -> str:
    try:
        path = urlparse(url).path.strip("/")
    except Exception:
        return ""
    seg = path.split("/")[0] if path else ""
    return re.sub(r"[^a-z0-9]", "", seg.lower().lstrip("@"))


def verify_link(platform: str, url: str, name: str = "") -> dict:
    """Return {verified, domain_ok, reachable, name_match, message, final_url}."""
    platform = (platform or "").strip().lower()
    url = _norm_url(url)
    out = {"verified": False, "domain_ok": False, "reachable": None,
           "name_match": None, "message": "", "final_url": url}
    if not url:
        out["message"] = "Enter a link."
        return out

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        out["message"] = "That doesn't look like a valid link."
        return out
    host = parsed.hostname

    # 1) domain gate (hard)
    if not _host_ok_for_platform(host, platform):
        pretty = platform.capitalize() if platform else "that platform"
        out["message"] = f"That isn't a {pretty} link — check the address."
        return out
    out["domain_ok"] = True

    # SSRF guard — never fetch a private / internal address
    if not _is_public_host(host):
        out["message"] = "That link can't be reached."
        return out

    # 1b) bot-walled platforms: the domain is right and it's a public IP, but fetching returns a
    # login wall (a live Facebook/Instagram/TikTok/X/Snapchat page 4xx's to a bot). Accept on the
    # domain — do NOT hard-fail a real page. The desk confirms it during application review.
    if platform in SKIP_FETCH:
        out["verified"] = True
        out["reachable"] = None
        out["message"] = "Added ✓ — we'll confirm it's active during review."
        return out

    # 2) existence + name (best-effort)
    try:
        r = requests.get(url, headers={"User-Agent": _UA, "Accept-Language": "en,ar;q=0.8"},
                         timeout=6, allow_redirects=True)
        out["final_url"] = r.url
        if r.status_code in (404, 410):
            out["reachable"] = False
            out["message"] = "We couldn't find that page — is the handle correct?"
            return out
        out["reachable"] = r.status_code < 400
        # name / handle match (informational)
        body = r.text[:200000] if r.text else ""
        nm = re.sub(r"[^a-z0-9]", "", (name or "").lower())
        handle = _handle_from_url(r.url) or _handle_from_url(url)
        if nm:
            hay = (body.lower() + " " + handle)
            out["name_match"] = bool(nm and (nm in hay or (handle and (nm in handle or handle in nm))))
        if out["reachable"]:
            out["verified"] = True
            if out["name_match"] is True:
                out["message"] = "Verified ✓"
            elif out["name_match"] is False:
                out["message"] = "Link is live ✓ (couldn't match the name — double-check it's yours)"
            else:
                out["message"] = "Link is live ✓"
            return out
        out["message"] = "That link didn't respond — check it and try again."
        return out
    except Exception:
        # timeout / blocked / connection error → soft pass on domain-pinned & bot-blocked platforms
        out["reachable"] = None
        if platform in BOT_BLOCKED or PLATFORM_DOMAINS.get(platform):
            out["verified"] = True
            out["message"] = "Accepted ✓ (we couldn't fully auto-check this one)"
        else:
            out["message"] = "We couldn't reach that link — check it and try again."
        return out

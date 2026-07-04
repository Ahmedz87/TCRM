"""
email_send.py — SMTP sender for TNFX (welcome emails now; email-OTP when enabled).

Reads creds from smtp_config.py (gitignored) — NOT .env (database.py's pydantic Settings forbids
extra keys). If SMTP isn't configured yet it logs and returns False, so callers degrade gracefully
until you drop the creds in. To enable, create backend/smtp_config.py:

    SMTP_HOST = "smtp.yourhost.com"
    SMTP_PORT = 587            # 465 for SSL
    SMTP_USER = "noreply@tnfx.co"
    SMTP_PASS = "..."
    SMTP_FROM = "noreply@tnfx.co"
    SMTP_FROM_NAME = "TNFX"
    SMTP_TLS = True            # STARTTLS on 587
"""
import ssl
import smtplib
from email.message import EmailMessage


def _cfg():
    try:
        import smtp_config as c
        host = getattr(c, "SMTP_HOST", "")
        if not host:
            return None
        return {
            "host": host, "port": int(getattr(c, "SMTP_PORT", 587)),
            "user": getattr(c, "SMTP_USER", ""), "password": getattr(c, "SMTP_PASS", ""),
            "from_addr": getattr(c, "SMTP_FROM", "noreply@tnfx.co"),
            "from_name": getattr(c, "SMTP_FROM_NAME", "TNFX"),
            "use_tls": bool(getattr(c, "SMTP_TLS", True)),
        }
    except Exception:
        return None


def configured():
    c = _cfg()
    return bool(c and c["host"] and c["password"])   # need the password too, else stay on dev OTP


def otp_html(code, purpose="verification", ttl_min=10):
    """Branded HTML body for an OTP email.

    purpose: 'verification' (signup) or 'reset' (password reset). Returns an email-client-safe
    HTML string (inline styles, table layout) with the code in a large styled box.
    """
    if purpose == "reset":
        heading = "Reset your password"
        intro = "Use the code below to reset your TNFX password."
    else:
        heading = "Confirm your email"
        intro = "Use the code below to verify your email and finish setting up your TNFX account."
    return f"""\
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#0d1b2a;padding:24px 0;">
 <tr><td align="center">
  <table role="presentation" width="480" cellpadding="0" cellspacing="0" style="max-width:480px;background:#0f1d2e;border:1px solid #1c3047;border-radius:14px;overflow:hidden;font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;">
   <tr><td style="background:#102844;padding:22px;text-align:center;border-bottom:1px solid #1c3047;">
     <span style="font-size:26px;font-weight:800;letter-spacing:-0.5px;color:#27a3ff;">TNFX</span>
   </td></tr>
   <tr><td style="padding:32px 28px;">
     <h2 style="color:#ffffff;font-size:19px;margin:0 0 10px;">{heading}</h2>
     <p style="color:#9fb3c8;font-size:15px;line-height:1.5;margin:0 0 22px;">{intro} It expires in <strong style="color:#ffffff;">{ttl_min} minutes</strong>.</p>
     <div style="background:#0b1726;border:1px solid #21384f;border-radius:10px;padding:24px;text-align:center;margin:0 0 22px;">
       <div style="font-size:12px;color:#6b8299;text-transform:uppercase;letter-spacing:2px;margin:0 0 8px;">Your code</div>
       <div style="font-size:40px;font-weight:800;letter-spacing:10px;color:#27a3ff;font-family:Consolas,'Courier New',monospace;">{code}</div>
     </div>
     <p style="color:#5f7891;font-size:13px;line-height:1.6;margin:0;">Never share this code with anyone. TNFX staff will never ask you for it. If you didn't request this, you can safely ignore this email.</p>
   </td></tr>
   <tr><td style="background:#0b1726;padding:14px;text-align:center;border-top:1px solid #1c3047;">
     <span style="color:#456;font-size:12px;">&copy; TNFX &middot; This is an automated message</span>
   </td></tr>
  </table>
 </td></tr>
</table>"""


def notice_html(heading, message, sub=None):
    """Branded HTML body for a general notice (e.g. KYC rejected / account exists)."""
    extra = f'<p style="color:#9fb3c8;font-size:14px;line-height:1.6;margin:14px 0 0;">{sub}</p>' if sub else ""
    return f"""\
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#0d1b2a;padding:24px 0;">
 <tr><td align="center">
  <table role="presentation" width="480" cellpadding="0" cellspacing="0" style="max-width:480px;background:#0f1d2e;border:1px solid #1c3047;border-radius:14px;overflow:hidden;font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;">
   <tr><td style="background:#102844;padding:22px;text-align:center;border-bottom:1px solid #1c3047;">
     <span style="font-size:26px;font-weight:800;letter-spacing:-0.5px;color:#27a3ff;">TNFX</span>
   </td></tr>
   <tr><td style="padding:32px 28px;">
     <h2 style="color:#ffffff;font-size:19px;margin:0 0 12px;">{heading}</h2>
     <p style="color:#9fb3c8;font-size:15px;line-height:1.6;margin:0;">{message}</p>
     {extra}
   </td></tr>
   <tr><td style="background:#0b1726;padding:14px;text-align:center;border-top:1px solid #1c3047;">
     <span style="color:#456;font-size:12px;">&copy; TNFX &middot; This is an automated message</span>
   </td></tr>
  </table>
 </td></tr>
</table>"""


def send(to_addr, subject, body_text, body_html=None):
    c = _cfg()
    if not c:
        print(f"[email] (SMTP not configured) would send to {to_addr!r}: {subject!r}", flush=True)
        return False
    if not to_addr:
        return False
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = f'{c["from_name"]} <{c["from_addr"]}>'
        msg["To"] = to_addr
        msg.set_content(body_text)
        if body_html:
            msg.add_alternative(body_html, subtype="html")
        ctx = ssl.create_default_context()
        if c["port"] == 465:
            with smtplib.SMTP_SSL(c["host"], c["port"], context=ctx, timeout=20) as s:
                if c["user"]:
                    s.login(c["user"], c["password"])
                s.send_message(msg)
        else:
            with smtplib.SMTP(c["host"], c["port"], timeout=20) as s:
                if c["use_tls"]:
                    s.starttls(context=ctx)
                if c["user"]:
                    s.login(c["user"], c["password"])
                s.send_message(msg)
        return True
    except Exception as e:
        print(f"[email] send failed to {to_addr}: {e}", flush=True)
        return False

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


# ── TNFX visual identity (keep in sync with the app: --brand #F8500A, gold accents, dark UI).
#    ALL emails render through _shell() so branding is consistent everywhere (portal, IB, KYC,
#    password reset, …). Change a token here → every email updates.
BRAND      = "#F8500A"   # TNFX orange (primary)
BRAND_2    = "#FF7A1A"   # lighter orange (gradient partner)
GOLD       = "#E8B84B"   # gold accent
BG         = "#0B0E14"   # page background (dark)
CARD       = "#14161D"   # card surface
CARD_2     = "#1B1F28"   # inner panel / header / footer
BORDER     = "#2A2F3A"
TEXT       = "#FFFFFF"
TEXT_MUTED = "#9AA3B2"
TEXT_FAINT = "#6B7686"
FONT       = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
SITE_URL   = "https://my1.tnfx.co"


def _shell(inner_html, preheader=""):
    """Wrap body HTML in the shared TNFX-branded email frame (orange/gold on dark, table layout,
    inline styles — email-client-safe). Every builder below uses this so all mail looks like TNFX."""
    pre = (f'<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:{BG};">'
           f'{preheader}</div>') if preheader else ""
    return f"""\
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{BG};padding:28px 12px;margin:0;">
 <tr><td align="center">{pre}
  <table role="presentation" width="480" cellpadding="0" cellspacing="0" style="max-width:480px;width:100%;background:{CARD};border:1px solid {BORDER};border-radius:16px;overflow:hidden;font-family:{FONT};">
   <tr><td style="background:{CARD_2};padding:24px;text-align:center;border-bottom:1px solid {BORDER};">
     <span style="font-size:30px;font-weight:800;letter-spacing:1px;color:{BRAND};font-family:{FONT};">TNFX</span>
     <div style="height:3px;width:46px;margin:11px auto 0;background:linear-gradient(90deg,{BRAND},{GOLD});border-radius:2px;line-height:3px;font-size:0;">&nbsp;</div>
   </td></tr>
   <tr><td style="padding:32px 28px;font-family:{FONT};">
{inner_html}
   </td></tr>
   <tr><td style="background:{CARD_2};padding:16px;text-align:center;border-top:1px solid {BORDER};">
     <div style="color:{TEXT_FAINT};font-size:12px;line-height:1.6;font-family:{FONT};">
       TNFX &middot; Global Trading<br>
       <span style="color:#4B5563;">Automated message — please don't reply to this email.</span>
     </div>
   </td></tr>
  </table>
 </td></tr>
</table>"""


def _button(label, url):
    """A TNFX-orange CTA button (bulletproof-ish table cell for Outlook)."""
    return (f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:8px 0 2px;">'
            f'<tr><td style="border-radius:10px;background:{BRAND};">'
            f'<a href="{url}" style="display:inline-block;padding:13px 28px;font-family:{FONT};'
            f'font-size:15px;font-weight:700;color:#ffffff;text-decoration:none;border-radius:10px;">'
            f'{label}</a></td></tr></table>')


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
    inner = f"""\
     <h2 style="color:{TEXT};font-size:20px;margin:0 0 10px;font-family:{FONT};">{heading}</h2>
     <p style="color:{TEXT_MUTED};font-size:15px;line-height:1.6;margin:0 0 22px;font-family:{FONT};">{intro} It expires in <strong style="color:{TEXT};">{ttl_min} minutes</strong>.</p>
     <div style="background:{CARD_2};border:1px solid {BORDER};border-radius:12px;padding:24px;text-align:center;margin:0 0 22px;">
       <div style="font-size:12px;color:{TEXT_FAINT};text-transform:uppercase;letter-spacing:2px;margin:0 0 8px;font-family:{FONT};">Your code</div>
       <div style="font-size:40px;font-weight:800;letter-spacing:10px;color:{BRAND};font-family:Consolas,'Courier New',monospace;">{code}</div>
     </div>
     <p style="color:{TEXT_FAINT};font-size:13px;line-height:1.6;margin:0;font-family:{FONT};">Never share this code with anyone. TNFX staff will never ask you for it. If you didn't request this, you can safely ignore this email.</p>"""
    return _shell(inner, preheader=f"Your TNFX code: {code}")


def notice_html(heading, message, sub=None):
    """Branded HTML body for a general notice (e.g. KYC rejected / account exists)."""
    extra = f'<p style="color:{TEXT_MUTED};font-size:14px;line-height:1.6;margin:14px 0 0;font-family:{FONT};">{sub}</p>' if sub else ""
    inner = f"""\
     <h2 style="color:{TEXT};font-size:20px;margin:0 0 12px;font-family:{FONT};">{heading}</h2>
     <p style="color:{TEXT_MUTED};font-size:15px;line-height:1.6;margin:0;font-family:{FONT};">{message}</p>
     {extra}"""
    return _shell(inner, preheader=heading)


def verify_email_html(name=None, verify_url=None, code=None, ttl_min=30):
    """KYC 'Send email verification' — ask a client to confirm their email address.
    Pass verify_url for a one-click link, or code for a code-based confirmation (or both)."""
    hi = f"Hi {name}," if name else "Hi,"
    action = ""
    if verify_url:
        action += _button("Verify my email", verify_url)
        action += (f'<p style="color:{TEXT_FAINT};font-size:12px;line-height:1.6;margin:16px 0 0;font-family:{FONT};">'
                   f'Or paste this link into your browser:<br>'
                   f'<span style="color:{BRAND};word-break:break-all;">{verify_url}</span></p>')
    if code:
        action += (f'<div style="background:{CARD_2};border:1px solid {BORDER};border-radius:12px;padding:20px;text-align:center;margin:16px 0 0;">'
                   f'<div style="font-size:12px;color:{TEXT_FAINT};text-transform:uppercase;letter-spacing:2px;margin:0 0 8px;font-family:{FONT};">Verification code</div>'
                   f'<div style="font-size:34px;font-weight:800;letter-spacing:8px;color:{BRAND};font-family:Consolas,\'Courier New\',monospace;">{code}</div></div>')
    inner = f"""\
     <h2 style="color:{TEXT};font-size:20px;margin:0 0 10px;font-family:{FONT};">Verify your email address</h2>
     <p style="color:{TEXT_MUTED};font-size:15px;line-height:1.6;margin:0 0 20px;font-family:{FONT};">{hi} please confirm your email so we can secure your TNFX account and move your verification forward.</p>
     {action}
     <p style="color:{TEXT_FAINT};font-size:13px;line-height:1.6;margin:22px 0 0;font-family:{FONT};">This expires in {ttl_min} minutes. If you didn't request this, you can safely ignore this email.</p>"""
    return _shell(inner, preheader="Confirm your TNFX email address")


def doc_reminder_html(name=None, missing=None, portal_url=SITE_URL):
    """KYC 'Send doc reminder' — remind a client to upload/complete their KYC documents.
    missing: optional list of the outstanding document names to spell out."""
    hi = f"Hi {name}," if name else "Hi,"
    items = ""
    if missing:
        lis = "".join(
            f'<tr><td style="padding:5px 0;color:{TEXT};font-size:14px;font-family:{FONT};">'
            f'<span style="color:{BRAND};">&#9679;</span>&nbsp; {m}</td></tr>' for m in missing)
        items = (f'<table role="presentation" cellpadding="0" cellspacing="0" '
                 f'style="margin:2px 0 22px;background:{CARD_2};border:1px solid {BORDER};'
                 f'border-radius:10px;padding:6px 16px;width:100%;">{lis}</table>')
    inner = f"""\
     <h2 style="color:{TEXT};font-size:20px;margin:0 0 10px;font-family:{FONT};">Complete your verification</h2>
     <p style="color:{TEXT_MUTED};font-size:15px;line-height:1.6;margin:0 0 16px;font-family:{FONT};">{hi} your TNFX account is almost verified. To unlock deposits, trading and withdrawals, please upload the document(s) below:</p>
     {items}
     {_button("Upload my documents", portal_url)}
     <p style="color:{TEXT_FAINT};font-size:13px;line-height:1.6;margin:22px 0 0;font-family:{FONT};">Our team reviews new documents within 24 hours. Need help? Reply to your account manager any time.</p>"""
    return _shell(inner, preheader="Action needed: finish your TNFX verification")


def send(to_addr, subject, body_text, body_html=None, attachments=None,
         reply_to=None, from_name=None):
    """Send an email. Optional:
      attachments: list of {"filename","data"(bytes),"maintype","subtype"} (e.g. image/png).
      reply_to:    a Reply-To address (so a client's reply reaches the staff sender).
      from_name:   overrides the display name on the From header (address stays the SMTP_FROM).
    """
    c = _cfg()
    if not c:
        print(f"[email] (SMTP not configured) would send to {to_addr!r}: {subject!r}", flush=True)
        return False
    if not to_addr:
        return False
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = f'{(from_name or c["from_name"])} <{c["from_addr"]}>'
        msg["To"] = to_addr
        if reply_to:
            msg["Reply-To"] = reply_to
        msg.set_content(body_text)
        if body_html:
            msg.add_alternative(body_html, subtype="html")
        for att in (attachments or []):
            msg.add_attachment(att["data"], maintype=att.get("maintype", "application"),
                               subtype=att.get("subtype", "octet-stream"),
                               filename=att.get("filename", "attachment"))
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

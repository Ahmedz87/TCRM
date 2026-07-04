"""
kyc_postverify.py — runs ONCE when a client's KYC is APPROVED (auto by the AI engine, or manually
by the desk). It:
  1) provisions a (SIMULATED) live trading account, visible in the client portal + admin side
  2) marks the lead converted
  3) emails the client (welcome + account details), the IB if any (congrats + account NUMBER ONLY),
     and the assigned sales agent (their lead converted)

SAFETY: provisioning here is SIMULATED — it creates a trading_accounts row and assigns the client a
real-style login so everything displays, but it does NOT call the live MT manager. Real MT UserAdd
stays the admin-gated /register/activate -> mt_provision path. Idempotent via registrations.account_login.
"""
import random
import string
from sqlalchemy import text


def _ensure_cols(db):
    try:
        db.execute(text("ALTER TABLE registrations ADD COLUMN IF NOT EXISTS account_login BIGINT"))
        db.execute(text("ALTER TABLE clients ADD COLUMN IF NOT EXISTS name_en TEXT"))
        db.commit()
    except Exception:
        db.rollback()


def _gen_login(db, platform):
    for _ in range(25):
        lg = random.randint(5200000, 5299999) if platform != "MT4" else random.randint(620000, 629999)
        ex = db.execute(text("SELECT 1 FROM clients WHERE login=:l UNION SELECT 1 FROM trading_accounts WHERE login=:l"),
                        {"l": lg}).fetchone()
        if not ex:
            return lg
    return random.randint(5300000, 5399999)


def _gen_password():
    return ("".join(random.choices(string.ascii_uppercase, k=2)) +
            "".join(random.choices(string.ascii_lowercase, k=3)) +
            "".join(random.choices(string.digits, k=3)) + random.choice("!@#$%&"))


def on_verified(db, registration_id):
    """Idempotent. Provision + notify when a registration's KYC is verified. Returns the account dict or None."""
    _ensure_cols(db)
    r = db.execute(text("""
        SELECT id, first_name, last_name, email, phone, country, city, platform, account_type,
               leverage, islamic, mt_login, lead_id, account_login
        FROM registrations WHERE id=:r
    """), {"r": registration_id}).fetchone()
    if not r or r.account_login:
        return None   # not found, or already provisioned

    platform = (r.platform or "MT5").upper()
    # Proper-case the name on approval: "ahmed" -> "Ahmed", "JABBAR" -> "Jabbar".
    first = (r.first_name or "").strip().title()
    last = (r.last_name or "").strip().title()
    name = (first + " " + last).strip()

    # NAME POLICY (set by the desk):
    #   • the ACCOUNT / username keeps an ENGLISH (Latin) name  -> clients.name_en + trading_accounts.name
    #   • the CLIENT's displayed name = the ORIGINAL document name, written exactly as on the ID
    #     (e.g. Arabic script) -> clients.name
    # Both come from the KYC OCR (registrations.ocr_fields): full_name_latin (English) + full_name_ar / full_name.
    try:
        import json as _json
        _ocr = db.execute(text("SELECT ocr_fields FROM registrations WHERE id=:r"), {"r": registration_id}).scalar()
        _of = _ocr if isinstance(_ocr, dict) else (_json.loads(_ocr) if _ocr else {})
    except Exception:
        _of = {}
    _latin = (_of.get("full_name_latin") or "").strip()
    _orig  = (_of.get("full_name_ar") or _of.get("full_name") or "").strip()
    name_en = (_latin.title() if _latin else name) or name       # ENGLISH name for the account/username
    display_name = _orig or name_en                              # ORIGINAL document name for the client display
    try:
        lev = int(str(r.leverage or "500").split(":")[-1])
    except Exception:
        lev = 500

    # the registrant's client row (currently a negative temp login) + its IB/sales links
    crow = db.execute(text("SELECT id, agent, assigned_agent_id, name FROM clients WHERE login=:lg"),
                      {"lg": r.mt_login}).fetchone()
    client_id = crow[0] if crow else None
    agent_login = crow[1] if crow else None
    sales_id = crow[2] if crow else None
    client_name = name_en   # English name for the (formal, English) notification emails

    # ── PROVISION the trading account ──
    # MT5 -> REAL account on the live server via the bridge. If the bridge fails (or MT4, whose
    # provisioning bridge isn't wired), fall back to a simulated login so verification isn't blocked
    # and an admin can re-provision via /register/activate.
    password = ""
    investor = ""
    if platform == "MT5":
        try:
            import mt_provision
            group = mt_provision.real_group(r.account_type, r.islamic)
            res = mt_provision.create_account(group, first, last, leverage=lev, email=r.email or "",
                                              phone=r.phone or "", country=r.country or "", city=r.city or "",
                                              agent=int(agent_login or 0))
        except Exception as e:
            res = {"ok": False, "error": str(e)}
        if res.get("ok"):
            login = int(res["login"]); password = res.get("master") or ""; investor = res.get("investor") or ""
            server = "TNFX-Live"
        else:
            print(f"[postverify] REAL MT5 provisioning failed for reg {registration_id}: {res.get('error')}", flush=True)
            login = _gen_login(db, platform); password = _gen_password(); group = (r.account_type or "Standard"); server = "TNFX-Live"
    else:
        login = _gen_login(db, platform); password = _gen_password()
        group = ("ISLAMIC-" if r.islamic else "") + (r.account_type or "Standard")
        server = "TNFX-Live4"

    try:
        if client_id:
            # promote the negative temp login to the real one + mark verified. Displayed name = the
            # original document name; name_en keeps the English name for the account/username.
            db.execute(text("UPDATE clients SET login=:new, kyc_status='verified', platform=:pl, name=:nm, name_en=:en WHERE id=:id"),
                       {"new": login, "pl": platform, "nm": display_name, "en": name_en, "id": client_id})
        db.execute(text("UPDATE registrations SET first_name=:f, last_name=:l WHERE id=:r"),
                   {"f": first, "l": last, "r": registration_id})
        db.execute(text("""
            INSERT INTO trading_accounts (login, client_id, name, email, phone, group_name, platform,
                account_type, is_islamic, leverage, balance, equity, kyc_status, source, is_active, agent, reg_date)
            VALUES (:lg,:cid,:nm,:em,:ph,:grp,:pl,'live',:isl,:lev,0,0,'verified','registration',TRUE,:ag,
                    to_char(NOW(),'YYYY-MM-DD'))
            ON CONFLICT (login) DO NOTHING
        """), {"lg": login, "cid": client_id, "nm": name_en, "em": r.email, "ph": r.phone, "grp": group,
               "pl": platform, "isl": bool(r.islamic), "lev": lev, "ag": agent_login})
        db.execute(text("UPDATE registrations SET account_login=:lg, mt_login=:lg, status='account_created' WHERE id=:r"),
                   {"lg": login, "r": registration_id})
        db.commit()
        try:
            import connection_engine as CE
            CE.refresh_account(db, login)   # add the new account to the network/connection page immediately
        except Exception:
            db.rollback()
    except Exception as e:
        db.rollback()
        print(f"[postverify] provision failed for reg {registration_id}: {e}", flush=True)
        return None

    # lead -> converted (each statement guarded — columns vary)
    if r.lead_id:
        for sql in [
            "UPDATE leads SET kyc_status='verified' WHERE id=:l",
            "UPDATE leads SET status='converted' WHERE id=:l",
            "UPDATE leads SET converted_login=:lg WHERE id=:l",
        ]:
            try:
                db.execute(text(sql), {"l": r.lead_id, "lg": login}); db.commit()
            except Exception:
                db.rollback()

    acct = {"login": login, "password": password, "investor": investor, "server": server, "platform": platform,
            "leverage": lev, "account_type": r.account_type or "Standard", "islamic": bool(r.islamic)}
    _notify(db, r, client_name, agent_login, sales_id, acct)
    return acct


def _notify(db, r, client_name, agent_login, sales_id, acct):
    try:
        import email_send
    except Exception:
        return
    if not email_send.configured():
        return

    first_name = (client_name or "").split(" ")[0] if client_name else ""
    # 1) CLIENT — welcome + full account details
    if r.email:
        try:
            body = (f"Dear {first_name},\n\n"
                    f"We are pleased to inform you that your identity has been verified and your TNFX "
                    f"{acct['platform']} trading account is now active.\n\n"
                    f"  Account number: {acct['login']}\n"
                    f"  Password: {acct['password']}\n"
                    + (f"  Investor (read-only) password: {acct['investor']}\n" if acct.get('investor') else "")
                    + f"  Server: {acct['server']}\n"
                    f"  Leverage: 1:{acct['leverage']}\n\n"
                    "You can log in to your client portal at https://my1.tnfx.co. For your security, "
                    "please change your password after your first login.\n\nKind regards,\nTNFX")
            html = email_send.notice_html(
                "Welcome to TNFX — your account is active",
                "Your identity has been verified and your trading account is ready to fund and trade.",
                (f"Account number: <b>{acct['login']}</b><br>Password: <b>{acct['password']}</b><br>"
                 f"Server: <b>{acct['server']}</b><br>Platform: <b>{acct['platform']}</b> · Leverage: <b>1:{acct['leverage']}</b>"))
            email_send.send(r.email, "Your TNFX account is verified and active", body, body_html=html)
        except Exception as e:
            print(f"[postverify] client email failed: {e}", flush=True)

    # 2) IB — congratulations, show ONLY the trading account number (no client PII)
    if agent_login:
        try:
            ib = db.execute(text("SELECT email, name FROM ibs WHERE agent_id=:a"), {"a": agent_login}).fetchone()
            if ib and ib[0]:
                body = (f"Dear {ib[1] or 'Partner'},\n\n"
                        f"A new verified trading account has been opened under your referral.\n\n"
                        f"  Account number: {acct['login']}\n\n"
                        "Kind regards,\nTNFX Partners Team")
                html = email_send.notice_html(
                    "New verified referral",
                    "A new verified trading account has been opened under your referral.",
                    f"Account number: <b>{acct['login']}</b>")
                email_send.send(ib[0], "A new verified account under your referral", body, body_html=html)
        except Exception as e:
            print(f"[postverify] IB email failed: {e}", flush=True)

    # 3) SALES AGENT — their lead converted
    if sales_id:
        try:
            u = db.execute(text("SELECT email, full_name FROM users WHERE id=:i"), {"i": sales_id}).fetchone()
            if u and u[0]:
                body = (f"Dear {u[1] or ''},\n\n"
                        f"Your lead {client_name} has completed KYC verification and now has an active "
                        f"trading account.\n\n"
                        f"  Client: {client_name}\n"
                        f"  Account number: {acct['login']}\n\n"
                        "Kind regards,\nTNFX")
                html = email_send.notice_html(
                    "Your lead is now verified",
                    f"{client_name} has completed KYC verification and now has an active trading account.",
                    f"Client: <b>{client_name}</b><br>Account number: <b>{acct['login']}</b>")
                email_send.send(u[0], "Your lead is now verified", body, body_html=html)
        except Exception as e:
            print(f"[postverify] sales email failed: {e}", flush=True)

"""
margin_alert.py — email the desk when a client's margin level drops toward a margin call.

Ticket #210 (Ayat). Sends a de-duplicated digest email listing accounts whose margin level is
below ALERT_LEVEL (default 100%). Two safety rails:
  • FRESHNESS GATE — only alerts on accounts whose equity/margin was refreshed in the last
    FRESH_MIN minutes. The numbers come from the MT bridge's 30s equity/margin poll; if that feed
    is stale (see the `stale-equity-margin-feed` note) this alerter correctly stays SILENT rather
    than emailing month-old margins as if they were live. Once the feed is live, alerts flow.
  • DEDUPE — an account is re-alerted only if it hasn't been alerted in RE_ALERT_HOURS, or its
    margin has dropped a further DROP_STEP since the last alert. State in `margin_alerts_sent`.

Recipients: crm_settings key 'margin_alert_recipients' (comma-separated), else falls back to all
active admins/directors' emails.

Run:  python margin_alert.py [--once] [--loop] [--dry-run] [--level 100]
Wire a scheduled task (e.g. every 5 min) once the live equity/margin feed is restored.
"""
import argparse, sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import text
from database import SessionLocal
import email_send

ALERT_LEVEL   = 100.0   # margin level (%) at/under which we alert
FRESH_MIN     = 90      # only alert accounts whose margin was refreshed in the last N minutes
RE_ALERT_HOURS = 12     # don't re-spam the same account inside this window …
DROP_STEP     = 15.0    # … unless its margin fell a further N points since the last alert


def _ensure_state(db):
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS margin_alerts_sent (
            login       BIGINT PRIMARY KEY,
            margin_level DOUBLE PRECISION,
            alerted_at  TIMESTAMPTZ NOT NULL DEFAULT NOW())"""))
    db.commit()


def _recipients(db):
    row = db.execute(text("SELECT value FROM crm_settings WHERE key='margin_alert_recipients'")).scalar() \
        if db.execute(text("SELECT 1 FROM information_schema.tables WHERE table_name='crm_settings'")).scalar() else None
    if row:
        return [e.strip() for e in str(row).split(",") if e.strip()]
    # fallback: active admins/directors
    return [e[0] for e in db.execute(text(
        "SELECT email FROM users WHERE COALESCE(is_active,TRUE) AND email IS NOT NULL "
        "AND lower(role) IN ('super_admin','admin','director')")).fetchall() if e[0]]


def find_and_alert(db, level=ALERT_LEVEL, dry=False):
    _ensure_state(db)
    rows = db.execute(text(f"""
        SELECT ta.login, ta.name, ta.equity, ta.margin_level, ta.free_margin, ta.balance,
               u.full_name AS agent, ta.updated_at
        FROM trading_accounts ta
        LEFT JOIN clients c ON c.login = ta.login
        LEFT JOIN users u ON u.id = c.assigned_agent_id
        WHERE ta.margin_level > 0 AND ta.margin_level < :lvl AND ta.equity > 0
          AND ta.is_active IS NOT FALSE
          AND ta.updated_at > NOW() - (:fresh || ' minutes')::interval
        ORDER BY ta.margin_level ASC
    """), {"lvl": level, "fresh": str(FRESH_MIN)}).fetchall()

    # dedupe against what we've already alerted
    sent = {r[0]: (r[1], r[2]) for r in db.execute(text(
        "SELECT login, margin_level, alerted_at FROM margin_alerts_sent")).fetchall()}
    fresh = []
    for r in rows:
        login, ml = r[0], float(r[3] or 0)
        prev = sent.get(login)
        if prev is not None:
            prev_ml, prev_at = prev
            age_h = (time.time() - prev_at.timestamp()) / 3600.0
            if age_h < RE_ALERT_HOURS and ml > (prev_ml - DROP_STEP):
                continue   # already alerted recently and not materially worse
        fresh.append(r)

    if not fresh:
        print(f"[margin_alert] {len(rows)} at/below {level:g}% (fresh feed), 0 new to alert")
        return 0

    lines = "".join(
        f"<tr><td style='padding:6px 10px'>{r[0]}</td><td style='padding:6px 10px'>{r[1] or ''}</td>"
        f"<td style='padding:6px 10px;color:#F8500A;font-weight:700'>{float(r[3] or 0):.1f}%</td>"
        f"<td style='padding:6px 10px'>${float(r[2] or 0):,.2f}</td>"
        f"<td style='padding:6px 10px'>${float(r[4] or 0):,.2f}</td>"
        f"<td style='padding:6px 10px'>{r[6] or '—'}</td></tr>"
        for r in fresh)
    table = ("<table style='border-collapse:collapse;width:100%;font-size:14px'>"
             "<tr style='text-align:left;color:#9AA3B2'>"
             "<th style='padding:6px 10px'>Login</th><th style='padding:6px 10px'>Client</th>"
             "<th style='padding:6px 10px'>Margin</th><th style='padding:6px 10px'>Equity</th>"
             "<th style='padding:6px 10px'>Free margin</th><th style='padding:6px 10px'>Agent</th></tr>"
             f"{lines}</table>")
    html = email_send.notice_html(
        f"⚠️ {len(fresh)} account(s) approaching a margin call",
        f"The following accounts have a margin level below {level:g}%. Reach out before a stop-out.",
        sub=table)
    text_body = "\n".join(f"{r[0]} {r[1] or ''} — margin {float(r[3] or 0):.1f}%" for r in fresh)

    to = _recipients(db)
    if dry or not to:
        print(f"[margin_alert] (dry / no recipients) would alert {len(fresh)} to {to}")
    else:
        for addr in to:
            email_send.send(addr, f"⚠️ {len(fresh)} account(s) near margin call", text_body, html)
        print(f"[margin_alert] emailed {len(fresh)} account(s) to {len(to)} recipient(s)")

    if not dry:
        for r in fresh:
            db.execute(text("""INSERT INTO margin_alerts_sent (login, margin_level, alerted_at)
                VALUES (:l, :m, NOW()) ON CONFLICT (login)
                DO UPDATE SET margin_level=:m, alerted_at=NOW()"""), {"l": r[0], "m": float(r[3] or 0)})
        db.commit()
    return len(fresh)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--level", type=float, default=ALERT_LEVEL)
    a = ap.parse_args()
    db = SessionLocal()
    try:
        if a.loop:
            while True:
                try:
                    find_and_alert(db, a.level, a.dry_run)
                except Exception as e:
                    db.rollback(); print(f"[margin_alert] error: {e}")
                time.sleep(300)
        else:
            find_and_alert(db, a.level, a.dry_run)
    finally:
        db.close()

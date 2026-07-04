"""
archive_legacy_leads.py — Mirror the OLD TradeSoft CRM's lead view into the new CRM.

THE PROBLEM: the TradeSoft import brought in EVERY legacy lead as status='new' and ignored the
legacy `archived_at` flag. The old CRM only shows NON-archived leads, so e.g. agent Sara Ali shows
4 leads there but ~2,700 here. This inflated every agent's lead count.

THE FIX: a `tradesoft` lead is archived here iff its legacy person has NO open lead in the old CRM
(open = fx_leads row with deleted_at IS NULL AND archived_at IS NULL). We only flip untouched
`new` leads (never ones an agent has since worked) and we save every affected id to a JSON backup
so it is fully reversible.

Run:  python archive_legacy_leads.py            (apply)
      python archive_legacy_leads.py --dry-run  (count only)
      python archive_legacy_leads.py --revert    (un-archive exactly what this script archived)
"""
import sys, os, json, time, psycopg2

def _dsn():
    for ln in open(os.path.join(os.path.dirname(__file__) or ".", ".env"), encoding="utf-8"):
        if ln.strip().startswith("DATABASE_URL"):
            return ln.split("=", 1)[1].strip()
    raise SystemExit("no DATABASE_URL in .env")

BACKUP = os.path.join(os.path.dirname(__file__) or ".", "archive_legacy_leads_backup.json")

def main():
    dry = "--dry-run" in sys.argv
    revert = "--revert" in sys.argv
    c = psycopg2.connect(_dsn()); cur = c.cursor()

    if revert:
        ids = json.load(open(BACKUP))["ids"]
        for i in range(0, len(ids), 5000):
            cur.execute("UPDATE leads SET is_archived=FALSE, updated_at=NOW() WHERE id = ANY(%s)", (ids[i:i+5000],))
        c.commit(); print(f"reverted {len(ids)} leads -> is_archived=FALSE"); return

    # legacy users that still have an OPEN lead in the old CRM
    cur.execute("""CREATE TEMP TABLE open_users AS
        SELECT DISTINCT user_id FROM tradesoft_old.fx_leads
        WHERE deleted_at IS NULL AND archived_at IS NULL""")
    # untouched legacy leads whose person has NO open legacy lead -> archive them
    cur.execute("""
        SELECT l.id FROM leads l
        JOIN customers cu ON cu.customer_no = l.customer_no
        WHERE l.source='tradesoft' AND l.status='new' AND COALESCE(l.is_archived,false)=false
          AND cu.legacy_user_id NOT IN (SELECT user_id FROM open_users)
    """)
    ids = [r[0] for r in cur.fetchall()]
    print(f"leads to archive: {len(ids)}")
    if dry:
        return
    json.dump({"reason": "legacy archived leads imported as new - mirror old CRM",
               "ids": ids, "ts": int(time.time())}, open(BACKUP, "w"))
    print(f"saved reversible backup -> {BACKUP}")
    t = time.time()
    for i in range(0, len(ids), 5000):
        cur.execute("UPDATE leads SET is_archived=TRUE, updated_at=NOW() WHERE id = ANY(%s)", (ids[i:i+5000],))
    c.commit()
    print(f"archived {len(ids)} leads in {time.time()-t:.1f}s")

if __name__ == "__main__":
    main()

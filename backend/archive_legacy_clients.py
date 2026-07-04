"""
archive_legacy_clients.py — USER-WISE client archive (admin decision), mirrored from TradeSoft.

There are TWO different "archives" in this CRM:
  1. ACCOUNT-wise  (clients.is_archived / archived_at): a TRADING ACCOUNT MT retired (balance < $5,
     idle 90d). Per-account, view-only, blocks deposit/transfer — but the PERSON stays a client.
  2. USER-wise     (clients.user_archived): the admin/TradeSoft archived the PERSON (not interested,
     a problem, etc.). This removes them from the Clients page -> the Settings/Archive page, so the
     desk sees fewer, more-active clients. THIS script populates #2 from TradeSoft.

Source of truth = tradesoft_old.fx_clients_view: a person is user-archived iff their legacy client
record is archived_at (or deleted_at) there. TradeSoft active clients = ~26k (matches the desk).

Link: clients.customer_no -> customers.legacy_user_id -> fx_clients_view.user_id.

Run:  python archive_legacy_clients.py --dry-run
      python archive_legacy_clients.py
      python archive_legacy_clients.py --revert
"""
import sys, os, psycopg2

def _dsn():
    for ln in open(os.path.join(os.path.dirname(__file__) or ".", ".env"), encoding="utf-8"):
        if ln.strip().startswith("DATABASE_URL"):
            return ln.split("=", 1)[1].strip()
    raise SystemExit("no DATABASE_URL")

def main():
    dry = "--dry-run" in sys.argv
    revert = "--revert" in sys.argv
    c = psycopg2.connect(_dsn()); cur = c.cursor()

    cur.execute("ALTER TABLE clients ADD COLUMN IF NOT EXISTS user_archived BOOLEAN DEFAULT FALSE")
    cur.execute("ALTER TABLE clients ADD COLUMN IF NOT EXISTS user_archived_at TIMESTAMP")
    c.commit()

    if revert:
        cur.execute("""UPDATE clients SET user_archived=FALSE, user_archived_at=NULL,
                       reactivated_from_archive=FALSE, reactivated_at=NULL
                       WHERE user_archived=TRUE OR reactivated_from_archive=TRUE""")
        print(f"reverted {cur.rowcount} clients -> user_archived=FALSE"); c.commit(); return

    # TradeSoft client records: ACTIVE = has any non-archived/non-deleted row.
    cur.execute("""CREATE TEMP TABLE active_users AS
        SELECT DISTINCT user_id FROM tradesoft_old.fx_clients_view
        WHERE deleted_at IS NULL AND archived_at IS NULL""")
    # ARCHIVED person = explicitly archived/deleted AND has NO active record (else they're still active).
    cur.execute("""CREATE TEMP TABLE arch_users AS
        SELECT user_id, MAX(COALESCE(archived_at, deleted_at)) AS arch_at
        FROM tradesoft_old.fx_clients_view
        WHERE (archived_at IS NOT NULL OR deleted_at IS NOT NULL)
          AND user_id NOT IN (SELECT user_id FROM active_users)
        GROUP BY user_id""")
    cur.execute("SELECT COUNT(*) FROM arch_users")
    print("TradeSoft archived-only client user_ids:", cur.fetchone()[0])

    # how many current CLIENT-persons (kind='client' — the Clients-page universe) map -> user-archived
    cur.execute("""
        SELECT COUNT(DISTINCT c.customer_no)
        FROM clients c JOIN customers cu ON cu.customer_no = c.customer_no
        WHERE cu.kind = 'client' AND cu.legacy_user_id IN (SELECT user_id FROM arch_users)
    """)
    print("client-persons (kind=client) to archive:", cur.fetchone()[0])
    if dry:
        print("(dry-run — nothing written)"); return

    # set the flag on every account row of an archived CLIENT person. user_archived_at = NOW() (when
    # WE archived them) — NOT the legacy date — so the re-engagement sweep only reacts to activity
    # AFTER this point, and we don't wrongly tag historically-active clients as 'came back'.
    cur.execute("""
        UPDATE clients c
           SET user_archived = TRUE,
               user_archived_at = COALESCE(c.user_archived_at, NOW())
        FROM customers cu
        JOIN arch_users au ON au.user_id = cu.legacy_user_id
        WHERE cu.customer_no = c.customer_no
          AND cu.kind = 'client'
          AND COALESCE(c.user_archived, FALSE) = FALSE
    """)
    print(f"archived {cur.rowcount} client rows.")
    c.commit()

if __name__ == "__main__":
    main()

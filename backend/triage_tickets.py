"""
Safe ticket TRIAGE — runs every 5 min from Task Scheduler (BrokerCRM-TicketTriage).

This is a DETERMINISTIC script (no LLM, no code changes, no restarts): it only
  1) acknowledges each brand-new ticket so the maker sees it was logged + queued, and
  2) raises the unread flag on urgent (high/critical) tickets for the desk.
Actual fixes are still applied by a human / supervised Claude session.

It never touches the 'ai' (dev) reply channel that the fix-flow keys on — it writes an
'triage' author_type reply and a `triaged` flag, so a ticket stays "needs fixing" until a
real dev reply lands. Idempotent: a ticket is acknowledged at most once (triaged flag).
"""
import sys
import db_config
import psycopg2
from datetime import datetime

DSN = dict(host=db_config.DB_HOST, port=db_config.DB_PORT, dbname=db_config.DB_NAME, user=db_config.DB_USER, password=db_config.DB_PASSWORD)

ACK = ("✅ Received — your ticket has been logged and queued for the team. "
       "We'll follow up here with the fix. Thank you for the detail.")
ACK_URGENT = ("✅ Received — this ticket is marked URGENT and has been flagged for the team "
              "as priority. We'll follow up here shortly.")


def main():
    conn = psycopg2.connect(**DSN)
    conn.autocommit = False
    cur = conn.cursor()
    try:
        # additive flag so we acknowledge each ticket only once
        cur.execute("ALTER TABLE tickets ADD COLUMN IF NOT EXISTS triaged BOOLEAN DEFAULT FALSE")
        conn.commit()

        # brand-new tickets only: not done, not yet triaged, and NOT already handled by a
        # real dev reply (author_type='ai'). So answered tickets never get a redundant ack.
        cur.execute("""
            SELECT t.id, COALESCE(t.critical,'medium')
            FROM tickets t
            WHERE t.status <> 'done'
              AND COALESCE(t.triaged, FALSE) = FALSE
              AND NOT EXISTS (SELECT 1 FROM ticket_replies r
                              WHERE r.ticket_id = t.id AND r.author_type = 'ai')
            ORDER BY t.id
        """)
        rows = cur.fetchall()
        acked = urgent = 0
        for tid, crit in rows:
            is_urgent = crit in ("high", "critical")
            cur.execute("""
                INSERT INTO ticket_replies (ticket_id, author_type, author_name, body)
                VALUES (%s, 'triage', 'Auto-Triage', %s)
            """, (tid, ACK_URGENT if is_urgent else ACK))
            # mark triaged; raise the desk's unread flag on urgent ones
            if is_urgent:
                cur.execute("UPDATE tickets SET triaged=TRUE, admin_unread=TRUE, updated_at=NOW() WHERE id=%s", (tid,))
                urgent += 1
            else:
                cur.execute("UPDATE tickets SET triaged=TRUE WHERE id=%s", (tid,))
            acked += 1
        conn.commit()
        print(f"{datetime.now():%Y-%m-%d %H:%M:%S}  triaged {acked} new ticket(s) ({urgent} urgent)")
    except Exception as e:
        conn.rollback()
        print(f"{datetime.now():%Y-%m-%d %H:%M:%S}  TRIAGE ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()

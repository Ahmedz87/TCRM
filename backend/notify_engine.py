# -*- coding: utf-8 -*-
"""notify_engine.py — turns live CRM events into per-user notification rows (the bell).

Design: every cycle scans each event source for the LAST 2 HOURS and inserts rows with a
dedupe_key ('lead:123', 'req:456', ...) guarded by a partial unique index + ON CONFLICT DO
NOTHING — fully idempotent, no cursor bookkeeping, safe across restarts and double-runs.

Events -> recipients:
  new lead assigned            -> that sales agent                 (link 'leads')
  new lead, unassigned         -> sales managers (batched)         (link 'leads')
  client moved to a new agent  -> the NEW agent (retention flow)   (link 'clients')
  deposit/withdraw request     -> backoffice                       (link 'transactions')
  ticket assigned              -> the assignee                     (link its page)
  HOT abuse case               -> backoffice + admins              (link 'abuse')
  critical call-QA report      -> sales managers                   (link 'call_qa')

Runs standalone (python notify_engine.py) and from enrich_loop every cycle.
"""
import sys, io
import db_config

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

WINDOW = "2 hours"          # look-back per cycle; dedupe makes re-scans harmless
KEEP_DAYS = 30              # GC horizon


def ensure_schema(cur):
    cur.execute("""CREATE TABLE IF NOT EXISTS notifications (
        id BIGSERIAL PRIMARY KEY, user_id INTEGER NOT NULL,
        title TEXT, message TEXT, type TEXT, link TEXT,
        is_read BOOLEAN DEFAULT FALSE, created_at TIMESTAMP DEFAULT NOW())""")
    cur.execute("ALTER TABLE notifications ADD COLUMN IF NOT EXISTS dedupe_key TEXT")
    cur.execute("""CREATE UNIQUE INDEX IF NOT EXISTS ux_notif_user_dedupe
                   ON notifications(user_id, dedupe_key) WHERE dedupe_key IS NOT NULL""")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_notif_user_read ON notifications(user_id, is_read)")


INS = """INSERT INTO notifications (user_id, title, message, type, link, dedupe_key)
         {select} ON CONFLICT (user_id, dedupe_key) WHERE dedupe_key IS NOT NULL DO NOTHING"""

# Each event = one INSERT ... SELECT producing (user_id, title, message, type, link, dedupe_key).
EVENTS = {
    # New lead assigned to a sales agent -> notify that agent.
    "lead_assigned": INS.format(select=f"""
        SELECT l.assigned_agent_id, 'New lead assigned',
               'Lead: ' || COALESCE(l.full_name,'(no name)') || COALESCE(' — ' || l.country, ''),
               'lead', 'leads', 'lead:' || l.id
        FROM leads l JOIN users u ON u.id = l.assigned_agent_id
        WHERE l.created_at > NOW() - INTERVAL '{WINDOW}' AND l.assigned_agent_id IS NOT NULL"""),

    # New unassigned leads -> one per lead to every sales manager (they distribute work).
    "lead_unassigned": INS.format(select=f"""
        SELECT u.id, 'New lead (unassigned)',
               'Lead: ' || COALESCE(l.full_name,'(no name)') || COALESCE(' — ' || l.source, ''),
               'lead', 'leads', 'leadu:' || l.id
        FROM leads l CROSS JOIN users u
        WHERE l.created_at > NOW() - INTERVAL '{WINDOW}' AND l.assigned_agent_id IS NULL
          AND u.role = 'sales_manager' AND COALESCE(u.is_active, TRUE)"""),

    # Client (re)assigned to an agent (sales -> retention handover) -> notify the NEW agent.
    "client_transferred": INS.format(select=f"""
        SELECT g.new_agent_id, 'New client for you',
               'Client ' || COALESCE(g.entity_name, g.entity_ref::text) ||
               CASE WHEN g.old_agent_name IS NOT NULL THEN ' (from ' || g.old_agent_name || ')' ELSE '' END,
               'client', 'clients', 'xfer:' || g.id
        FROM agent_change_log g JOIN users u ON u.id = g.new_agent_id
        WHERE g.created_at > NOW() - INTERVAL '{WINDOW}' AND g.new_agent_id IS NOT NULL"""),

    # New portal deposit/withdraw request -> every backoffice user.
    "money_request": INS.format(select=f"""
        SELECT u.id,
               CASE WHEN r.kind='withdraw' THEN 'New WITHDRAWAL request' ELSE 'New deposit request' END,
               'Login ' || r.login || ' — $' || ROUND(r.amount::numeric, 2) || ' via ' || COALESCE(r.method,'—'),
               'money_request', 'transactions', 'req:' || r.id
        FROM portal_money_requests r CROSS JOIN users u
        WHERE r.created_at > NOW() - INTERVAL '{WINDOW}'
          AND LOWER(COALESCE(r.status,'')) IN ('pending','processing','')
          AND u.role = 'backoffice' AND COALESCE(u.is_active, TRUE)"""),

    # Ticket assigned to a staff member -> the assignee.
    "ticket_assigned": INS.format(select=f"""
        SELECT t.assigned_to, 'Ticket assigned to you',
               '#' || t.id || ' [' || COALESCE(t.section,'general') || '] ' || left(COALESCE(t.note,''), 90),
               'ticket', 'tickets', 'ticket:' || t.id
        FROM tickets t JOIN users u ON u.id = t.assigned_to
        WHERE t.updated_at > NOW() - INTERVAL '{WINDOW}' AND t.assigned_to IS NOT NULL
          AND COALESCE(t.status,'') NOT IN ('done','closed','resolved')"""),

    # HOT abuse case -> backoffice + admins.
    "abuse_hot": INS.format(select=f"""
        SELECT u.id, 'HOT abuse case',
               COALESCE(a.abuse_type,'case') || ' — account ' || a.login_a ||
               COALESCE(' / ' || a.login_b, '') || ' (severity ' || COALESCE(a.severity,'') || ')',
               'abuse', 'abuse', 'abuse:' || a.id
        FROM abuse_cases a CROSS JOIN users u
        WHERE a.created_at > NOW() - INTERVAL '{WINDOW}' AND COALESCE(a.hot, FALSE)
          AND u.role IN ('backoffice','admin') AND COALESCE(u.is_active, TRUE)"""),

    # Critical call-QA report -> sales managers.
    "callqa_critical": INS.format(select=f"""
        SELECT u.id, 'Critical call flagged',
               COALESCE(q.agent_name,'agent') || ' — ' || left(COALESCE(q.summary,''), 90),
               'call_qa', 'call_qa', 'callqa:' || q.id
        FROM call_qa q CROSS JOIN users u
        WHERE q.created_at > NOW() - INTERVAL '{WINDOW}' AND LOWER(COALESCE(q.priority,'')) = 'critical'
          AND u.role = 'sales_manager' AND COALESCE(u.is_active, TRUE)"""),

    # A Developer/staff/admin REPLY landed on a ticket -> the ticket's maker (creator).
    "ticket_reply": INS.format(select=f"""
        SELECT t.creator_id, 'New reply on your ticket',
               '#' || t.id || ' — ' || left(COALESCE(tr.body,''), 90),
               'ticket', 'tickets', 'trreply:' || tr.id
        FROM ticket_replies tr JOIN tickets t ON t.id = tr.ticket_id
        JOIN users u ON u.id = t.creator_id
        WHERE tr.created_at > NOW() - INTERVAL '{WINDOW}'
          AND t.creator_type = 'staff' AND t.creator_id IS NOT NULL
          AND tr.author_type IN ('dev','admin','staff','developer')"""),

    # The ticket MAKER replied back -> admins (so they see the follow-up).
    "ticket_maker_reply": INS.format(select=f"""
        SELECT u.id, 'Ticket maker replied',
               '#' || t.id || ' — ' || left(COALESCE(tr.body,''), 90),
               'ticket', 'tickets', 'trmaker:' || tr.id
        FROM ticket_replies tr JOIN tickets t ON t.id = tr.ticket_id
        CROSS JOIN users u
        WHERE tr.created_at > NOW() - INTERVAL '{WINDOW}'
          AND tr.author_type IN ('maker','client')
          AND u.role = 'admin' AND COALESCE(u.is_active, TRUE)"""),

    # NEW CLIENT — a login's FIRST-EVER deposit (no deposit on any earlier day) -> its sales
    # agent + sales managers + admins. Day-based prior check so the TS+MT duplicate rows of the
    # same deposit both qualify but dedupe (by login) collapses them to one.
    "new_client": INS.format(select=f"""
        SELECT rec.uid, 'New client (first deposit)',
               COALESCE(cl.name,'Client') || ' — login ' || t.login || ' — $' || ROUND(t.amount::numeric,2),
               'client', 'clients', 'newclient:' || t.login
        FROM transactions t JOIN clients cl ON cl.login = t.login
        JOIN LATERAL (
             SELECT cl.assigned_agent_id AS uid WHERE cl.assigned_agent_id IS NOT NULL
             UNION SELECT u.id FROM users u WHERE u.role IN ('admin','sales_manager') AND COALESCE(u.is_active,TRUE)
        ) rec ON TRUE
        WHERE t.tx_type='deposit' AND t.created_at > NOW() - INTERVAL '{WINDOW}'
          AND t.amount < 1000000
          AND COALESCE(t.notes,'') !~* 'fix|negativ|bonus|welcome|cover|revert|correct|adjust'
          AND NOT EXISTS (SELECT 1 FROM transactions t2 WHERE t2.login=t.login
                          AND t2.tx_type IN ('deposit','deposit_dup') AND left(t2.tx_date,10) < left(t.tx_date,10))"""),

    # NEW DEPOSIT by an EXISTING depositor (repeat) -> the client's OWN sales agent only (the
    # person who cares). Admins/backoffice would drown in these — they get the high-signal events
    # instead (new_client / rejected). Dedupe by login+amount+day so the TS-import + MT-deal rows
    # of the SAME deposit are ONE bell.
    "new_deposit": INS.format(select=f"""
        SELECT cl.assigned_agent_id, 'New deposit',
               COALESCE(cl.name,'Client') || ' — login ' || t.login || ' — $' || ROUND(t.amount::numeric,2) || COALESCE(' via ' || t.method,''),
               'deposit', 'transactions', 'dep:' || t.login || ':' || ROUND(t.amount::numeric,2) || ':' || left(t.tx_date,10)
        FROM transactions t JOIN clients cl ON cl.login = t.login
        JOIN users u ON u.id = cl.assigned_agent_id
        WHERE t.tx_type='deposit' AND t.created_at > NOW() - INTERVAL '{WINDOW}'
          AND t.amount < 1000000 AND cl.assigned_agent_id IS NOT NULL
          AND COALESCE(t.notes,'') !~* 'fix|negativ|bonus|welcome|cover|revert|correct|adjust'
          AND EXISTS (SELECT 1 FROM transactions t2 WHERE t2.login=t.login
                      AND t2.tx_type IN ('deposit','deposit_dup') AND left(t2.tx_date,10) < left(t.tx_date,10))"""),

    # REJECTED deposit / withdrawal -> its sales agent + backoffice + admins.
    "tx_rejected": INS.format(select=f"""
        SELECT rec.uid,
               CASE WHEN t.tx_type LIKE 'withdrawal%%' THEN 'Withdrawal rejected' ELSE 'Deposit rejected' END,
               COALESCE(cl.name,'Login '||t.login::text) || ' — $' || ROUND(t.amount::numeric,2),
               'money_request', 'transactions', 'rej:' || t.id
        FROM transactions t LEFT JOIN clients cl ON cl.login = t.login
        JOIN LATERAL (
             SELECT cl.assigned_agent_id AS uid WHERE cl.assigned_agent_id IS NOT NULL
             UNION SELECT u.id FROM users u WHERE u.role IN ('admin','backoffice') AND COALESCE(u.is_active,TRUE)
        ) rec ON TRUE
        WHERE LOWER(COALESCE(t.status,''))='rejected' AND t.updated_at > NOW() - INTERVAL '{WINDOW}'
          AND t.amount < 1000000"""),
}


def run():
    c = db_config.connect(); c.autocommit = False; cur = c.cursor()
    ensure_schema(cur); c.commit()
    total = 0
    for name, sql in EVENTS.items():
        try:
            cur.execute(sql)
            n = cur.rowcount
            c.commit()
            if n:
                print(f"  {name}: +{n}")
                total += n
        except Exception as e:
            c.rollback()
            print(f"  {name}: ERROR {str(e)[:120]}")
    try:
        cur.execute(f"DELETE FROM notifications WHERE created_at < NOW() - INTERVAL '{KEEP_DAYS} days'")
        c.commit()
    except Exception:
        c.rollback()
    c.close()
    print(f"notify_engine: {total} new notification(s)")
    return total


if __name__ == "__main__":
    run()

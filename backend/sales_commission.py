"""
sales_commission.py — sales/retention commission per the desk's rules (Jul 2026).

RULES (as specified by the desk):
  #1  IB-referred clients stay with their agent forever (never auto-transferred) — enforced in the
      transfer engine, but ALSO reflected here: an agent keeps earning markup on their IB clients.
  #2  IB-commission column = commission paid to IBs THROUGH this agent's clients' trading accounts
      (already how agents_router computes ib_comm — unchanged, computed there).
  #3  RETENTION earns markup from a sales-transferred client only AFTER D2 (the client's 2nd deposit
      transaction). For the retention agent's OWN leads or IB-referred clients, they earn from the start.
  #4  SALES earns the UNIT BONUS ONLY (updated Jul 10): $UNIT (default 10, configurable) per NDA
      first-time-deposit they ACQUIRED (per unique new client whose FTD is an NDA — genuinely new,
      no relation to the company), attributed to the ORIGINATING sales agent (from the lead).
      NO markup commission for sales — their converted clients move to retention, who earns the
      markup after D2. (Two modules: sales = per-unit, retention = markup.)

ATTRIBUTION
  • "originating agent" of a client = the agent on the client's matched LEAD (bridged by customer_no;
    clients.matched_lead_id is dead, and after the D1 handover clients.assigned_agent_id is the
    retention agent — so the lead is the only reliable record of who acquired them).
  • "IB owner" of a client = the CRM agent assigned to the IB's OWN client account
    (clients.assigned_agent_id where login = ibs.agent_id), for the IB the client trades under
    (clients.agent = ibs.agent_id).  ibs.assigned_agent_id is empty, so we resolve via the own account.
  • markup follows CURRENT assignment (assigned_agent_id); the NDA bonus follows origin. So markup is
    never double-paid to both the sales originator and the retention holder for the same client.

Returns, per agent id: nda_ftd, unit_bonus, gross_markup, comm_ib (markup-window IB comm),
net_markup, markup_comm, commission (unit_bonus + markup_comm), plus commission_pct.

compute(db, p_from, p_to_next, unit_usd) -> {agent_id: {...}}
"""
from sqlalchemy import text

# CREDIT-TRADE reference = the IB page's own classification (ib_trades.reason='credit', built by
# ib_trades.py's credit-ledger rule). Excluding these keeps company markup consistent with the IB
# page — when the desk updates the credit rule THERE and rebuilds ib_trades, this follows too.
CREDIT_EXCLUDE = "AND NOT EXISTS (SELECT 1 FROM ib_trades cr WHERE cr.deal_id = d.deal_id AND cr.reason = 'credit')"

# who is a client "under an IB", and who owns that IB (the agent on the IB's own client account)
_IB_OWNER = """
    ibo AS (
        SELECT DISTINCT ON (c.login) c.login, ic_own.assigned_agent_id AS owner
        FROM clients c
        JOIN ibs i          ON i.agent_id = c.agent
        JOIN clients ic_own ON ic_own.login = i.agent_id
        WHERE c.agent IS NOT NULL AND ic_own.assigned_agent_id IS NOT NULL
        ORDER BY c.login, i.id
    )
"""

# originating agent per customer = the agent on their earliest matched lead (any team)
_ORIGIN = """
    origin AS (
        SELECT DISTINCT ON (l.customer_no) l.customer_no, l.assigned_agent_id AS lead_agent
        FROM leads l
        WHERE l.customer_no IS NOT NULL AND l.assigned_agent_id IS NOT NULL
        ORDER BY l.customer_no, l.created_at, l.id
    )
"""

# D1 / D2 / D3 deposit dates (YYYY-MM-DD) per login
_DEPOSITS = """
    dep AS (
        SELECT login,
               left((array_agg(tx_date ORDER BY tx_date))[1], 10) AS d1,
               left((array_agg(tx_date ORDER BY tx_date))[2], 10) AS d2,
               left((array_agg(tx_date ORDER BY tx_date))[3], 10) AS d3
        FROM transactions
        WHERE tx_type = 'deposit' AND COALESCE(tx_date,'') <> ''
        GROUP BY login
    )
"""


def _attr_cte():
    # per-login attribution: who holds it, its team, origin/IB owner, and the earn-from date + include flag
    return f"""
    {_IB_OWNER},
    {_ORIGIN},
    {_DEPOSITS},
    attr AS (
        SELECT c.login,
               c.assigned_agent_id                       AS aid,
               ua.team_type                              AS ateam,
               origin.lead_agent                         AS own_agent,
               ibo.owner                                 AS ib_owner,
               dep.d2                                    AS d2,
               dep.d3                                    AS d3,
               -- did the HOLDING agent log a call to this client? (drives the D2-vs-D3 gate)
               (ca.login IS NOT NULL)                    AS had_call,
               -- own/IB of the CURRENT holder → earns from the start; else (transferred) → from D2.
               -- COALESCE matters: with no lead AND no IB this is NULL, and "NOT NULL" is NULL —
               -- which silently skipped the D2 date-gate for exactly those clients.
               COALESCE(c.assigned_agent_id = origin.lead_agent
                OR c.assigned_agent_id = ibo.owner, FALSE) AS owns_from_start
        FROM clients c
        JOIN users ua ON ua.id = c.assigned_agent_id
        LEFT JOIN origin ON origin.customer_no = c.customer_no
        LEFT JOIN ibo    ON ibo.login = c.login
        LEFT JOIN dep    ON dep.login = c.login
        LEFT JOIN LATERAL (SELECT 1 AS login FROM call_actions
                           WHERE call_actions.login = c.login
                             AND call_actions.agent_id = c.assigned_agent_id LIMIT 1) ca ON TRUE
        WHERE c.assigned_agent_id IS NOT NULL
    ),
    scoped AS (
        -- decide, per login, whether the holder earns markup on it and from which date
        SELECT login, aid,
               CASE
                 -- SALES: paid per NDA conversion ONLY (unit bonus) — NO markup commission at all.
                 -- (Their converted clients move to retention, who earns the markup after D2.)
                 WHEN ateam = 'sales'     THEN FALSE
                 -- RETENTION + TEAM-LEADERS/MANAGERS ('lead'): own/IB from start; transferred only if D2
                 WHEN ateam IN ('retention','lead') THEN (owns_from_start OR d2 IS NOT NULL)
                 -- anything else: all assigned clients
                 ELSE TRUE
               END AS include,
               -- transferred retention/lead client: from D2 if a call was logged, else from D3
               -- (desk rule: no call after the 2nd deposit ⇒ commission only starts at D3).
               CASE
                 WHEN ateam IN ('retention','lead') AND NOT owns_from_start
                   THEN CASE WHEN had_call THEN COALESCE(d2, '9999-12-31')
                             ELSE COALESCE(d3, '9999-12-31') END
                 ELSE ''
               END AS earn_from
        FROM attr
    )
    """


def compute(db, p_from, p_to_next, unit_usd=10.0, only_aid=None):
    P = {"p_from": p_from, "p_to_next": p_to_next}
    aidf = ""
    nda_aidf = ""
    if only_aid is not None:
        aidf = " AND s.aid = :only_aid"
        nda_aidf = " AND sales_id = :only_aid"
        P["only_aid"] = int(only_aid)

    # ---- markup + IB-comm within each login's earn window, summed per holding agent ----
    # attr/scoped is built once; both the deals and ib_commissions rollups reuse it.
    rows = db.execute(text(f"""
        WITH {_attr_cte()},
        mkd AS (
            -- PERF (Jul 2026): reads the per-(login,day) rollup's credit-excluded column
            -- (markup_nc) instead of scanning 16.8M deals + a per-row NOT EXISTS — was the
            -- ~35s cost on every Sales Agents load. Per-login earn_from gating preserved.
            SELECT s.aid, COALESCE(SUM(m.markup_nc),0) AS gross_markup
            FROM scoped s
            JOIN deals_login_daily m ON m.login = s.login
            WHERE s.include{aidf}
              AND m.day >= GREATEST(:p_from, s.earn_from) AND m.day < :p_to_next
            GROUP BY s.aid
        ),
        ibd AS (
            SELECT s.aid, COALESCE(SUM(ic.commission_usd),0) AS comm_ib
            FROM scoped s
            JOIN ib_commissions ic ON ic.client_login = s.login
            WHERE s.include{aidf} AND ic.trade_date ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}'
              AND ic.trade_date >= GREATEST(:p_from, s.earn_from) AND ic.trade_date < :p_to_next
            GROUP BY s.aid
        )
        SELECT COALESCE(mkd.aid, ibd.aid)        AS aid,
               COALESCE(mkd.gross_markup, 0)     AS gross_markup,
               COALESCE(ibd.comm_ib, 0)          AS comm_ib
        FROM mkd FULL OUTER JOIN ibd ON ibd.aid = mkd.aid
    """), P).fetchall()
    markup_by = {r[0]: float(r[1]) for r in rows}
    ib_by = {r[0]: float(r[2]) for r in rows}

    # ---- sales UNIT BONUS: $unit per NDA first-time-deposit, by the ACQUIRING sales agent ----
    # The acquiring agent isn't cleanly recorded (clients.matched_lead_id is dead; after the D1
    # handover assigned_agent_id is retention). Best-effort resolution, first sales hit wins:
    #   1) the agent on the client's matched LEAD (via customer_no)
    #   2) the from-agent of the documented sales→retention handover (transfer_log)
    #   3) the CURRENT assigned agent, if still on a sales team (not yet transferred)
    nda = db.execute(text(f"""
        WITH {_ORIGIN},
        cust AS (
            SELECT DISTINCT ON (c.customer_no) c.customer_no, c.login, c.assigned_agent_id AS cur_aid,
                   c.is_nda, NULLIF(c.first_deposit_at,'') AS fda
            FROM clients c
            WHERE c.customer_no IS NOT NULL AND c.is_nda IS NOT NULL
            ORDER BY c.customer_no, NULLIF(c.first_deposit_at,'') ASC NULLS LAST, c.login
        ),
        f AS (SELECT * FROM cust WHERE is_nda AND fda >= :p_from AND fda < :p_to_next),
        resolved AS (
            SELECT COALESCE(
                     CASE WHEN uo.team_type='sales' THEN origin.lead_agent END,
                     CASE WHEN ut.team_type='sales' THEN tl.from_agent_id END,
                     CASE WHEN uc.team_type='sales' THEN f.cur_aid END
                   ) AS sales_id
            FROM f
            LEFT JOIN origin ON origin.customer_no = f.customer_no
            LEFT JOIN users uo ON uo.id = origin.lead_agent
            LEFT JOIN users uc ON uc.id = f.cur_aid
            LEFT JOIN LATERAL (
                SELECT from_agent_id FROM transfer_log
                WHERE record_key::text = f.login::text
                  AND batch_id IN ('tradesoft-agent-sync','lead-retention-handover')
                ORDER BY id LIMIT 1) tl ON TRUE
            LEFT JOIN users ut ON ut.id = tl.from_agent_id
        )
        SELECT sales_id AS aid, COUNT(*) AS nda_ftd
        FROM resolved
        WHERE sales_id IS NOT NULL{nda_aidf}
        GROUP BY sales_id
    """), P).fetchall()
    nda_by = {r[0]: int(r[1]) for r in nda}

    # ---- commission_pct per agent ----
    pcts = {r[0]: float(r[1] or 10) for r in
            db.execute(text("SELECT id, commission_pct FROM users")).fetchall()}

    out = {}
    for aid in set(markup_by) | set(ib_by) | set(nda_by):
        gross = markup_by.get(aid, 0.0)
        cib = ib_by.get(aid, 0.0)
        net = gross - cib
        pct = pcts.get(aid, 10.0)
        markup_comm = net * pct / 100.0
        ndaf = nda_by.get(aid, 0)
        unit_bonus = ndaf * float(unit_usd)
        out[aid] = {
            "nda_ftd": ndaf, "unit_bonus": round(unit_bonus, 2),
            "gross_markup": round(gross, 2), "comm_ib": round(cib, 2),
            "net_markup": round(net, 2), "markup_comm": round(markup_comm, 2),
            "commission": round(unit_bonus + markup_comm, 2),
            "commission_pct": pct,
        }
    return out


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    from database import SessionLocal
    from ib_router import period_dates
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", default="this_month")
    ap.add_argument("--unit", type=float, default=10.0)
    ap.add_argument("--top", type=int, default=15)
    a = ap.parse_args()
    db = SessionLocal()
    try:
        pf, pt = period_dates(a.period, "", "")
        from datetime import datetime, timedelta
        ptn = (datetime.strptime(pt, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
        res = compute(db, pf, ptn, a.unit)
        names = {r[0]: r[1] for r in db.execute(text("SELECT id, full_name FROM users")).fetchall()}
        rows = sorted(res.items(), key=lambda kv: kv[1]["commission"], reverse=True)[:a.top]
        print(f"period {pf}..{pt}  unit=${a.unit}")
        print(f"{'agent':22} {'NDA':>4} {'unitBonus':>10} {'grossMk':>10} {'ibComm':>9} {'markupC':>9} {'TOTAL':>10}")
        for aid, v in rows:
            print(f"{(names.get(aid,str(aid))[:21]):22} {v['nda_ftd']:>4} {v['unit_bonus']:>10.2f} "
                  f"{v['gross_markup']:>10.2f} {v['comm_ib']:>9.2f} {v['markup_comm']:>9.2f} {v['commission']:>10.2f}")
    finally:
        db.close()

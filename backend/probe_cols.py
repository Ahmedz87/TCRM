import sys
sys.path.insert(0, r"C:\broker-crm\backend")
from database import SessionLocal
from sqlalchemy import text
db = SessionLocal()
try:
    # Run the EXACT grouped select for one known recapture client to see column positions
    row = db.execute(text("""
        SELECT
            MIN(c.login) as login, MIN(c.name) as name, MIN(c.email) as email,
            MIN(c.phone) as phone, MIN(c.country) as country, MIN(c.city) as city,
            MIN(c.last_ip) as ip, MIN(c.cid) as cid, SUM(c.balance) as balance,
            SUM(c.equity) as equity, AVG(c.margin_level) as ml, SUM(COALESCE(c.credit,0)) as bonus,
            SUM(COALESCE(c.total_deposits,0)) as td, SUM(COALESCE(c.total_withdrawals,0)) as tw,
            SUM(COALESCE(c.total_deposits,0))-SUM(COALESCE(c.total_withdrawals,0)) as nd,
            MIN(c.agent) as agent, MIN(c.reg_date) as reg, MIN(c.first_deposit_at) as fda,
            MIN(c.first_deposit_amount) as fdamt, MAX(c.last_deposit_at) as lda,
            MAX(c.last_withdraw_at) as lwa, MIN(c.kyc_status) as kyc, MIN(c.risk_score) as risk,
            COUNT(*) as acct, BOOL_OR(COALESCE(c.is_flagged,FALSE)) as flagged,
            MIN(c.assigned_agent_id) as aaid, array_agg(DISTINCT c.login) as alllogins,
            MAX(c.lead_badge) as lead_badge, MAX(c.matched_lead_id) as matched_lead_id
        FROM clients c
        WHERE c.lead_badge = 'recapture'
        GROUP BY c.phone
        LIMIT 1
    """)).fetchone()
    print("Total columns returned:", len(row))
    for i, v in enumerate(row):
        print(f"  r[{i}] = {repr(v)[:40]}")
finally:
    db.close()

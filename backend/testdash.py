import db_config
import psycopg2
c = db_config.connect().cursor()
cid = 13488
tests = [
  ("clients", "SELECT id,name,email,phone,city,country FROM clients WHERE id=%s LIMIT 1"),
  ("balance", "SELECT COALESCE(SUM(balance),0), COUNT(*) FROM trading_accounts WHERE client_id=%s"),
  ("loyalty", "SELECT tier,points_balance,lifetime_points,current_streak,best_tier FROM loyalty_accounts WHERE client_id=%s"),
  ("trades", "SELECT COUNT(*), COALESCE(SUM(CASE WHEN d.profit>0 THEN 1 ELSE 0 END),0), COALESCE(SUM(d.profit),0) FROM deals d JOIN trading_accounts ta ON ta.login=d.login WHERE ta.client_id=%s AND d.entry=1 AND d.action IN (0,1) AND d.deal_time>=0"),
  ("refs", "SELECT COUNT(*), COALESCE(SUM(CASE WHEN status='won' THEN 1 ELSE 0 END),0), COALESCE(SUM(CASE WHEN status='won' THEN bonus_points ELSE 0 END),0) FROM loyalty_referrals WHERE referrer_client_id=%s"),
]
for name, q in tests:
    try:
        c.execute(q, (cid,)); c.fetchall(); print("OK  ", name)
    except Exception as e:
        print("FAIL", name, "->", str(e)[:120])

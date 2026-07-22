"""Populate ib_commissions per (client, symbol, day) using the SAME set-based formula as
build_ibs.py (commission = lots * ib_level for FX/gold, * 1 otherwise). One fast INSERT,
fully consistent with the IB total_commission already shown in IB Admin.
Then refresh ibs.total_commission/unpaid from the detail so everything matches."""
from sqlalchemy import text
from database import SessionLocal

_CUR = "USD|EUR|GBP|JPY|AUD|NZD|CAD|CHF|TRY|ZAR|MXN|SGD|HKD|NOK|SEK|DKK|PLN|CNH|CZK|HUF|RUB|INR|THB|CNY"
FX_OR_GOLD = ("(d.symbol ILIKE 'XAU%' OR upper(regexp_replace(d.symbol,'[^A-Za-z]','','g')) "
              f"~ '^({_CUR})({_CUR})')")

def run():
    db = SessionLocal()
    try:
        # DELETE + INSERT in ONE transaction (no commit between) so a reader during a live
        # refresh never sees an empty ib_commissions table (MVCC keeps the old rows visible
        # until the single commit below). This feeds the live sales commission = (markup - IB).
        db.execute(text("DELETE FROM ib_commissions"))
        res = db.execute(text(f"""
            INSERT INTO ib_commissions
                (ib_id, ib_login, client_login, symbol, volume, pts_per_lot,
                 commission_usd, trade_date, deal_month, status, created_at)
            SELECT i.id, i.agent_id, d.login, d.symbol,
                   SUM(d.volume/10000.0) AS lots,
                   (CASE WHEN {FX_OR_GOLD} THEN i.ib_level ELSE 1 END) AS pts,
                   SUM((d.volume/10000.0) * CASE WHEN {FX_OR_GOLD} THEN i.ib_level ELSE 1 END) AS commission_usd,
                   NULLIF(d.deal_date,'')::date AS trade_date,
                   to_char(NULLIF(d.deal_date,'')::date,'YYYY-MM') AS deal_month,
                   'computed', NOW()
            FROM deals d
            JOIN clients c ON c.login = d.login
            JOIN ibs i     ON i.agent_id = c.agent
            WHERE d.action IN (0,1) AND d.volume > 0
              AND d.deal_date ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}'
            GROUP BY i.id, i.agent_id, d.login, d.symbol,
                     NULLIF(d.deal_date,'')::date,
                     (CASE WHEN {FX_OR_GOLD} THEN i.ib_level ELSE 1 END)
        """))
        db.commit()
        # refresh the IB aggregate from the detail so IB Admin matches exactly — BUT NEVER overwrite
        # the authoritative Plugit commission (commission_source IS NOT NULL): those IBs keep
        # commission_excel(2023..2026)+commission_computed(pre-2023). Only IBs with no Plugit data
        # get the computed rollup. See commission_years_import.py / build_ibs.VOLUME_SQL.
        db.execute(text("""
            UPDATE ibs SET
                total_commission  = CASE WHEN ibs.commission_source IS NOT NULL
                                         THEN COALESCE(ibs.commission_excel,0)+COALESCE(ibs.commission_computed,0)+COALESCE(ibs.commission_live,0)
                                         ELSE sub.c END,
                unpaid_commission = (CASE WHEN ibs.commission_source IS NOT NULL
                                         THEN COALESCE(ibs.commission_excel,0)+COALESCE(ibs.commission_computed,0)+COALESCE(ibs.commission_live,0)
                                         ELSE sub.c END) - COALESCE(ibs.paid_commission,0),
                updated_at = NOW()
            FROM (SELECT ib_id, SUM(commission_usd) c FROM ib_commissions GROUP BY ib_id) sub
            WHERE ibs.id = sub.ib_id
        """))
        db.commit()
        # Floor LAST: the IB wallet is commission-only, so no IB can have withdrawn (total_payoff)
        # more than it earned. Any IB the recompute above left below its payoff gets floored to it
        # (the shortfall is pre-report commission). Runs every refresh so net never goes negative.
        db.execute(text("""
            UPDATE ibs SET
                commission_computed = COALESCE(commission_computed,0) + (COALESCE(total_payoff,0) - total_commission),
                total_commission    = COALESCE(total_payoff,0),
                commission_source   = COALESCE(commission_source, 'computed'),
                unpaid_commission   = COALESCE(total_payoff,0) - COALESCE(paid_commission,0),
                updated_at = NOW()
            WHERE COALESCE(total_payoff,0) > total_commission + 0.01
        """))
        db.commit()
        n = db.execute(text("SELECT COUNT(*), ROUND(SUM(commission_usd)::numeric,0) FROM ib_commissions")).fetchone()
        print(f"ib_commissions rows={n[0]}  total_usd={n[1]}")
    finally:
        db.close()

if __name__ == "__main__":
    run()

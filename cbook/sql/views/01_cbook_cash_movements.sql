-- cbook_cash_movements — canonical per-deal financial classification (READ-ONLY VIEW).
--
-- Mirrors backend/build_transactions.py's CASE exactly, extended to also tag trades,
-- so every money-affecting deal gets one `kind`. This is the shared foundation for
-- §5 reconstruction, §8 aggregates, §13 bonus, §15 negative-balance, etc.
--
-- SAFETY: this is a VIEW over `deals`. It is additive and read-only — it creates no
-- data, modifies no rows, touches no client account. Drop anytime: DROP VIEW cbook_cash_movements;
-- Run once on the live DB (PG18) to enable the §5 report query. It never writes.
--
-- `signed_delta` = the amount this deal added to the account balance (the reconciliation unit).

CREATE OR REPLACE VIEW cbook_cash_movements AS
SELECT
    d.deal_id,
    d.login,
    d.client_id,
    d.action,
    d.deal_date,
    d.deal_month,
    d.deal_time,
    d.profit,
    COALESCE(d.commission, 0)                                      AS commission,
    COALESCE(d.swap, 0)                                            AS swap,
    COALESCE(d.volume, 0)                                          AS volume,
    d.balance_after,
    d.comment,
    d.platform,
    CASE
        WHEN d.action IN (0, 1) THEN 'trade'
        WHEN d.action = 2 AND d.comment ILIKE '%transfer%' THEN 'internal_transfer'
        WHEN d.action = 2 AND d.comment ~* 'revert.*withdraw' THEN 'withdrawal_revert'
        WHEN d.action = 2 AND d.comment ~* 'abus' THEN 'abuse_clawback'
        WHEN d.action = 2
             AND d.comment !~* '(qi ?card|zain\w*|asiapay|asiahawala|usdt|tether|al ?taif|sham|perfect ?money|wallet|advcash|airtm|paymaxis|bridger|ptop|web ?money|cryptomus|payeer|fasapay)'
             AND (COALESCE(NULLIF(trim(split_part(regexp_replace(d.comment,'\s*-\s*',' - ','g'),' - ',2)),''), d.platform) = 'MT5'
                  OR COALESCE(NULLIF(trim(split_part(regexp_replace(d.comment,'\s*-\s*',' - ','g'),' - ',2)),''), d.platform)
                     ~* '(deposit\s*[/ ]?\s*fix|withdraw\w*\s*[/ ]?\s*fix|balance\s*fix|deposit\s*fee|negative\s*balance|stop\s*out\s*comp|reverting\s*cap|capital\s*refund|cash\s*back|credit\s*(in|out)|bonus\s*adjustment|\ysync\y)')
             THEN CASE WHEN d.comment ~* 'negative\s*balance' THEN 'negative_cover' ELSE 'balance_fix' END
        WHEN d.action = 2 AND d.profit > 0 THEN 'deposit'
        WHEN d.action = 2 AND d.profit < 0 THEN 'withdrawal'
        WHEN d.action IN (3, 6) AND d.profit > 0 THEN 'bonus_deposit'
        WHEN d.action IN (3, 6) AND d.profit < 0 THEN 'bonus_withdrawal'
        ELSE 'unclassified'
    END                                                            AS kind,
    -- balance delta: a trade moves balance by profit+commission+swap; a balance op by profit.
    CASE WHEN d.action IN (0, 1)
         THEN COALESCE(d.profit,0) + COALESCE(d.commission,0) + COALESCE(d.swap,0)
         ELSE COALESCE(d.profit,0)
    END                                                            AS signed_delta
FROM deals d
WHERE COALESCE(d.comment,'') NOT ILIKE 'PP on%'      -- skip internal MT5 profit-settlement micro-ops
  AND (d.action IN (0,1) OR (d.action IN (2,3,6) AND d.profit <> 0));

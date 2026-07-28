-- §5 Client Account Financial Reconstruction  →  Table 1 (one row per account).
--
-- READ-ONLY. Depends on the cbook_cash_movements view (see ../views/01_cbook_cash_movements.sql).
-- All-time per login, opening_balance = 0 (period='ALL'). Monthly periodization is a later step
-- (§6/§8). Single-currency USD (FX ignored for now, per project decision).
--
-- Reconciliation (§26): reconstructed_closing_balance should equal reported_closing_balance
-- (the latest balance_after MT reported). balance_break makes any difference explicit.
--
-- Run:  psql "$CRM_DB" -f s05_account_reconstruction.sql     (v16 psql can query the v18 server)

WITH mv AS (
    SELECT * FROM cbook_cash_movements
),
agg AS (
    SELECT
        login,
        -- §5.2 deposits
        SUM(profit) FILTER (WHERE kind='deposit')                       AS completed_deposits,
        COUNT(*)    FILTER (WHERE kind='deposit')                       AS n_deposits,
        -- §5.3 withdrawals (stored positive) + reverts
        -SUM(profit) FILTER (WHERE kind='withdrawal')                   AS completed_withdrawals,
        COUNT(*)     FILTER (WHERE kind='withdrawal')                   AS n_withdrawals,
        SUM(profit)  FILTER (WHERE kind='withdrawal_revert')            AS withdrawal_reverts,
        -- §5.4 internal transfers (signed)
        SUM(profit)  FILTER (WHERE kind='internal_transfer')            AS net_internal_transfers,
        -- §5.5 bonuses / credits / internal fixes / clawbacks (signed)
        SUM(profit)  FILTER (WHERE kind IN ('bonus_deposit','bonus_withdrawal')) AS net_bonus_credit,
        SUM(profit)  FILTER (WHERE kind IN ('balance_fix','negative_cover'))     AS net_balance_fix,
        SUM(profit)  FILTER (WHERE kind='abuse_clawback')              AS net_abuse_clawback,
        -- §5.6–5.8 trading
        SUM(profit)     FILTER (WHERE kind='trade')                    AS realized_gross_pnl,
        SUM(commission) FILTER (WHERE kind='trade')                    AS commission_total,
        SUM(swap)       FILTER (WHERE kind='trade')                    AS swap_total,
        COUNT(*)        FILTER (WHERE kind='trade')                    AS n_trades,
        SUM(volume)     FILTER (WHERE kind='trade')                    AS volume_lots,
        -- surfaced, never hidden
        SUM(profit)  FILTER (WHERE kind='unclassified')                AS unclassified_amount,
        -- §5.9 reconstructed closing = opening(0) + Σ balance deltas
        SUM(signed_delta)                                              AS total_delta
    FROM mv
    GROUP BY login
),
reported AS (   -- latest MT-reported balance per login (the reconciliation target)
    SELECT DISTINCT ON (login) login, balance_after AS reported_closing_balance
    FROM mv
    WHERE balance_after IS NOT NULL
    ORDER BY login, deal_time DESC
)
SELECT
    a.login,
    'ALL'::text                                             AS period,
    'USD'::text                                             AS currency,
    0::numeric                                              AS opening_balance,
    COALESCE(a.completed_deposits,0)                        AS net_completed_deposits,
    COALESCE(a.n_deposits,0)                                AS n_deposits,
    COALESCE(a.completed_withdrawals,0)
      - COALESCE(a.withdrawal_reverts,0)                    AS net_completed_withdrawals,
    COALESCE(a.n_withdrawals,0)                             AS n_withdrawals,
    COALESCE(a.net_internal_transfers,0)                    AS net_internal_transfers,
    COALESCE(a.net_bonus_credit,0)                          AS net_bonus_credit,
    COALESCE(a.net_balance_fix,0)                           AS net_balance_fix,
    COALESCE(a.net_abuse_clawback,0)                        AS net_abuse_clawback,
    COALESCE(a.realized_gross_pnl,0)                        AS realized_gross_pnl,
    COALESCE(a.commission_total,0)                          AS commission_total,
    COALESCE(a.swap_total,0)                                AS swap_total,
    COALESCE(a.realized_gross_pnl,0)
      + COALESCE(a.commission_total,0)
      + COALESCE(a.swap_total,0)                            AS realized_net_pnl,
    COALESCE(a.n_trades,0)                                  AS n_trades,
    COALESCE(a.volume_lots,0)                               AS volume_lots,
    ROUND(COALESCE(a.total_delta,0), 2)                    AS reconstructed_closing_balance,
    r.reported_closing_balance,
    ROUND(COALESCE(a.total_delta,0) - COALESCE(r.reported_closing_balance,0), 2) AS balance_break,
    COALESCE(a.unclassified_amount,0)                       AS unclassified_amount
FROM agg a
LEFT JOIN reported r USING (login)
ORDER BY ABS(ROUND(COALESCE(a.total_delta,0) - COALESCE(r.reported_closing_balance,0), 2)) DESC NULLS LAST;
-- ^ biggest reconciliation breaks first, so the desk audits those before trusting the table.

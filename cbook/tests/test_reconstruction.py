"""
§31 unit & reconciliation tests for §5 Client Account Financial Reconstruction.

Pure — no DB. Runnable directly (`python cbook/tests/test_reconstruction.py`) or via
pytest. Each test defines EXPECTED financial outputs (per §31 requirement).

Covers the §31 scenarios that §5 addresses:
  1 deposit only · 2 deposit+trade profit+withdrawal · 3 loss+redeposit ·
  4 internal transfer · 5 bonus + bonus reversal · 6 negative-balance adjustment ·
  12 open position with unrealized P&L · 15 duplicate cash transaction ·
  16 missing/unclassified journal (surfaces as a break, never hidden).
Scenarios needing data we don't have (7 multi-ccy, 8-11 book/hedge/LP, 17-20) are
out of §5 scope and tracked as BLOCKED in ../STATUS.md.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.reconstruction import reconstruct_account
from lib.classification import classify

EPS = 1e-6


def approx(a, b, t=1e-6):
    return abs((a or 0) - (b or 0)) <= t


# ── Scenario 1: one deposit, no trades ────────────────────────────────────────
def test_s1_deposit_only():
    deals = [dict(action=2, profit=1000, comment="Deposit - Qi card - USD")]
    r = reconstruct_account(deals, login=1, opening_balance=0, reported_closing_balance=1000)
    assert approx(r.net_completed_deposits, 1000)
    assert r.n_deposits == 1
    assert approx(r.realized_net_pnl, 0)
    assert approx(r.reconstructed_closing_balance, 1000)
    assert approx(r.balance_break, 0)


# ── Scenario 2: deposit, trade profit, withdrawal ─────────────────────────────
def test_s2_deposit_trade_withdraw():
    deals = [
        dict(action=2, profit=1000, comment="Deposit - Usdt - USD"),
        dict(action=0, profit=200, commission=-5, swap=-2, volume=1.0, comment="close order"),
        dict(action=2, profit=-500, comment="Withdrawal - Usdt - USD"),
    ]
    r = reconstruct_account(deals, login=2, opening_balance=0, reported_closing_balance=693)
    assert approx(r.net_completed_deposits, 1000)
    assert approx(r.net_completed_withdrawals, 500)
    assert approx(r.realized_gross_pnl, 200)
    assert approx(r.commission_total, -5)
    assert approx(r.swap_total, -2)
    assert approx(r.realized_net_pnl, 193)          # 200 - 5 - 2
    # closing = 0 + 1000 - 500 + 193 = 693
    assert approx(r.reconstructed_closing_balance, 693)
    assert approx(r.balance_break, 0)


# ── Scenario 3: trade loss + additional deposit ───────────────────────────────
def test_s3_loss_then_redeposit():
    deals = [
        dict(action=2, profit=1000, comment="Deposit - Zain - USD"),
        dict(action=1, profit=-400, commission=-3, swap=0, volume=2.0, comment="close order"),
        dict(action=2, profit=300, comment="Deposit - Zain - USD"),   # deposit-after-loss
    ]
    r = reconstruct_account(deals, login=3, opening_balance=0, reported_closing_balance=897)
    assert approx(r.net_completed_deposits, 1300)
    assert r.n_deposits == 2
    assert approx(r.realized_net_pnl, -403)
    assert approx(r.reconstructed_closing_balance, 897)   # 1300 - 403
    assert approx(r.balance_break, 0)


# ── Scenario 4: internal transfer (must NOT count as external funding) ─────────
def test_s4_internal_transfer():
    deals = [
        dict(action=2, profit=1000, comment="Deposit - Qi card - USD"),
        dict(action=2, profit=-250, comment="Transfer to 5551234"),   # out
    ]
    r = reconstruct_account(deals, login=4, opening_balance=0, reported_closing_balance=750)
    assert approx(r.net_completed_deposits, 1000)     # transfer excluded
    assert approx(r.net_completed_withdrawals, 0)     # transfer is NOT a withdrawal
    assert approx(r.net_internal_transfers, -250)
    assert approx(r.reconstructed_closing_balance, 750)
    assert approx(r.balance_break, 0)


# ── Scenario 5: bonus + bonus reversal ────────────────────────────────────────
def test_s5_bonus_and_reversal():
    deals = [
        dict(action=2, profit=500, comment="Deposit - Usdt - USD"),
        dict(action=6, profit=50, comment="Welcome bonus"),
        dict(action=6, profit=-50, comment="Bonus reversal"),
    ]
    r = reconstruct_account(deals, login=5, opening_balance=0, reported_closing_balance=500)
    assert approx(r.net_completed_deposits, 500)
    assert approx(r.net_bonus_credit, 0)              # +50 then -50 nets to 0
    assert approx(r.reconstructed_closing_balance, 500)
    assert approx(r.balance_break, 0)


# ── Scenario 6: negative-balance adjustment (internal cover, not a deposit) ────
def test_s6_negative_balance_cover():
    deals = [
        dict(action=2, profit=200, comment="Deposit - Qi card - USD"),
        dict(action=1, profit=-260, commission=0, swap=0, volume=5.0, comment="close order"),  # blows past 0
        dict(action=2, profit=60, comment="negative balance correction"),  # cover to 0
    ]
    r = reconstruct_account(deals, login=6, opening_balance=0, reported_closing_balance=0)
    assert approx(r.net_completed_deposits, 200)      # the 60 cover is NOT a deposit
    assert approx(r.net_balance_fix, 60)
    assert approx(r.realized_net_pnl, -260)
    assert approx(r.reconstructed_closing_balance, 0) # 200 - 260 + 60
    assert approx(r.balance_break, 0)


# ── Scenario 12: open position with unrealized P&L → closing equity ───────────
def test_s12_unrealized_equity():
    deals = [dict(action=2, profit=1000, comment="Deposit - Usdt - USD")]
    r = reconstruct_account(deals, login=12, opening_balance=0,
                            reported_closing_balance=1000, unrealized_pnl=-120)
    assert approx(r.reconstructed_closing_balance, 1000)
    assert approx(r.unrealized_pnl, -120)
    assert approx(r.closing_equity, 880)              # §5.11 balance + UPL


# ── Scenario 15: duplicate cash transaction inflates & breaks reconciliation ──
def test_s15_duplicate_breaks_reconciliation():
    deals = [
        dict(action=2, profit=1000, comment="Deposit - Qi card - USD"),
        dict(action=2, profit=1000, comment="Deposit - Qi card - USD"),  # accidental dup
    ]
    # MT reported balance only reflects ONE (or the real 1000): break must be visible.
    r = reconstruct_account(deals, login=15, opening_balance=0, reported_closing_balance=1000)
    assert approx(r.net_completed_deposits, 2000)
    assert approx(r.reconstructed_closing_balance, 2000)
    assert approx(r.balance_break, 1000)              # surfaced, not hidden
    assert any("BALANCE BREAK" in n for n in r.notes)


# ── Scenario 16: unclassified deal is surfaced, never absorbed ────────────────
def test_s16_unclassified_surfaced():
    deals = [
        dict(action=2, profit=1000, comment="Deposit - Usdt - USD"),
        dict(action=9, profit=-30, comment="mystery op"),   # unknown action code
    ]
    r = reconstruct_account(deals, login=16, opening_balance=0, reported_closing_balance=970)
    assert approx(r.unclassified_amount, -30)
    assert any("unclassified" in n.lower() for n in r.notes)
    # balance identity still holds because we DON'T drop the row
    assert approx(r.reconstructed_closing_balance, 970)
    assert approx(r.balance_break, 0)


# ── Classification unit checks (the tricky comment-parsing) ────────────────────
def test_classification_edge_cases():
    assert classify(2, 1000, "Deposit - Qi card - USD") == "deposit"
    assert classify(2, -500, "Withdrawal - Usdt - USD") == "withdrawal"
    assert classify(2, -250, "Transfer to 5551234") == "internal_transfer"
    assert classify(2, 250, "Reverting withdraw #123") == "withdrawal_revert"
    assert classify(2, 60, "negative balance correction") == "negative_cover"
    assert classify(2, 10, "balance fix") == "balance_fix"
    # bare MT5 fallback (no method segment, no real method named) => internal fix
    assert classify(2, 10, "adjustment", platform="MT5") == "balance_fix"
    # a real method named even with FIX wording => still a real deposit
    assert classify(2, 500, "deposit Qi Card USD (FIX)") == "deposit"
    assert classify(2, 100, "clawback abuse hedge") == "abuse_clawback"
    assert classify(0, 200, "close order") == "trade"
    assert classify(6, 50, "Welcome bonus") == "bonus_deposit"
    assert classify(3, -50, "credit out") == "bonus_withdrawal"


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL  {fn.__name__}: {e}")
        except Exception as e:
            print(f"  ERROR {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(fns)} tests passed")
    return passed == len(fns)


if __name__ == "__main__":
    ok = _run_all()
    sys.exit(0 if ok else 1)

"""
cbook.lib.reconstruction — §5 Client Account Financial Reconstruction (pure).

Rebuilds one account's period financials from its raw `deals` rows, following
PHASE2_FINANCIAL_RECONCILIATION.md §5.1–§5.11. Produces one Table-1 row.

DESIGN — two views that must agree (this is the whole point of reconciliation):
  1. Classified decomposition (§5.9 formula): opening + net deposits − net withdrawals
     + net transfers + bonuses/credits + realized P&L + costs.
  2. Raw balance identity: opening + Σ(every deal's balance delta).
  By construction (1) == (2) UNLESS a deal is 'unclassified' — which is surfaced as a
  reconciliation break, never hidden.

SIGN CONVENTION (documented per Rule 5.9):
  - deals.profit is SIGNED: deposit/win = +, withdrawal/loss = −.
  - A balance-op deal's balance delta = profit.
  - A trade deal's balance delta = profit + commission + swap (what actually hit balance).
  - commission / swap are SIGNED (a charge is negative). Reported as signed sums;
    "cost" magnitudes are the negative of those where negative.

READ-ONLY / PURE: no DB. Feed it dicts; it returns a dict. The SQL in
cbook/sql/reports/s05_account_reconstruction.sql produces the same numbers at scale.
"""
from dataclasses import dataclass, field, asdict
from .classification import classify


def _f(v):
    return float(v or 0)


@dataclass
class AccountReconstruction:
    login: int = 0
    period: str = ""                      # e.g. '2026-07' or 'ALL'
    currency: str = "USD"                 # single-currency assumption (FX ignored for now)

    opening_balance: float = 0.0

    # §5.2 deposits
    completed_deposits: float = 0.0
    net_completed_deposits: float = 0.0
    n_deposits: int = 0
    # §5.3 withdrawals
    completed_withdrawals: float = 0.0
    withdrawal_reverts: float = 0.0
    net_completed_withdrawals: float = 0.0
    n_withdrawals: int = 0
    # §5.4 internal transfers (signed: in +, out −)
    net_internal_transfers: float = 0.0
    # §5.5 bonuses / credits / internal adjustments (signed)
    net_bonus_credit: float = 0.0
    net_balance_fix: float = 0.0
    net_abuse_clawback: float = 0.0
    # §5.6–5.8 trading
    realized_gross_pnl: float = 0.0
    commission_total: float = 0.0         # signed
    swap_total: float = 0.0               # signed
    realized_net_pnl: float = 0.0
    n_trades: int = 0
    volume_lots: float = 0.0
    # §5.9 closing balance
    reconstructed_closing_balance: float = 0.0
    reported_closing_balance: float = None  # from balance_after of last deal, if given
    balance_break: float = 0.0             # reconstructed − reported (should be ~0)
    # §5.10–5.11 equity
    unrealized_pnl: float = None           # snapshot-based, if given (not reconstructable from deals)
    closing_equity: float = None

    unclassified_amount: float = 0.0       # Σ balance delta of unclassified deals (a break)
    notes: list = field(default_factory=list)

    def as_row(self):
        return asdict(self)


def reconstruct_account(deals, login=0, period="ALL", opening_balance=0.0,
                        reported_closing_balance=None, unrealized_pnl=None,
                        tol=0.01):
    """Reconstruct one account/period from an iterable of deal dicts.

    Each deal dict may contain: action, profit, commission, swap, volume, comment,
    platform, balance_after. Missing numeric fields default to 0.
    """
    r = AccountReconstruction(login=login, period=period, opening_balance=_f(opening_balance))

    raw_delta = 0.0
    for d in deals:
        action = d.get("action")
        profit = _f(d.get("profit"))
        comm = _f(d.get("commission"))
        swap = _f(d.get("swap"))
        kind = classify(action, profit, d.get("comment", ""), d.get("platform", "MT5"))

        if kind == "trade":
            r.realized_gross_pnl += profit
            r.commission_total += comm
            r.swap_total += swap
            r.n_trades += 1
            r.volume_lots += _f(d.get("volume"))
            raw_delta += profit + comm + swap
        elif kind == "deposit":
            r.completed_deposits += profit
            r.n_deposits += 1
            raw_delta += profit
        elif kind == "withdrawal":
            r.completed_withdrawals += -profit   # store positive magnitude
            r.n_withdrawals += 1
            raw_delta += profit
        elif kind == "withdrawal_revert":
            r.withdrawal_reverts += profit        # refund into account (positive)
            raw_delta += profit
        elif kind == "internal_transfer":
            r.net_internal_transfers += profit
            raw_delta += profit
        elif kind in ("bonus_deposit", "bonus_withdrawal"):
            r.net_bonus_credit += profit
            raw_delta += profit
        elif kind in ("balance_fix", "negative_cover"):
            r.net_balance_fix += profit
            raw_delta += profit
        elif kind == "abuse_clawback":
            r.net_abuse_clawback += profit
            raw_delta += profit
        else:  # unclassified — never silently absorbed
            r.unclassified_amount += profit
            raw_delta += profit
            r.notes.append(f"unclassified deal action={action} profit={profit} comment={d.get('comment','')!r}")

    # §5.2 / §5.3 nets
    r.net_completed_deposits = r.completed_deposits
    r.net_completed_withdrawals = r.completed_withdrawals - r.withdrawal_reverts
    # §5.8 realized net
    r.realized_net_pnl = r.realized_gross_pnl + r.commission_total + r.swap_total

    # §5.9 closing balance — decomposition (equals opening + raw_delta by construction)
    r.reconstructed_closing_balance = round(r.opening_balance + raw_delta, 6)

    if reported_closing_balance is not None:
        r.reported_closing_balance = _f(reported_closing_balance)
        r.balance_break = round(r.reconstructed_closing_balance - r.reported_closing_balance, 6)
        if abs(r.balance_break) > tol:
            r.notes.append(
                f"BALANCE BREAK {r.balance_break:+.2f}: reconstructed "
                f"{r.reconstructed_closing_balance:.2f} vs reported {r.reported_closing_balance:.2f}")

    # §5.10–5.11 equity (snapshot-based; UPL not reconstructable from closed deals)
    if unrealized_pnl is not None:
        r.unrealized_pnl = _f(unrealized_pnl)
        r.closing_equity = round(r.reconstructed_closing_balance + r.unrealized_pnl, 6)

    if abs(r.unclassified_amount) > tol:
        r.notes.append(f"UNCLASSIFIED total {r.unclassified_amount:+.2f} — investigate before publishing")

    return r

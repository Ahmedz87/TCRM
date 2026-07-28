"""
cbook.lib.classification — canonical cash-movement classification.

Faithful Python port of backend/build_transactions.py's SQL CASE (the CRM's
battle-tested logic that makes Finance/Deposits totals correct). Keep the two in
sync: if build_transactions.py changes, mirror it here.

READ-ONLY / PURE: no DB, no side effects. Takes a single deal's fields and returns
its financial movement kind.

Deal action codes (per CLAUDE.md):
    0 buy, 1 sell        -> a real trade
    2 balance            -> deposit / withdrawal / transfer / internal adjustment
    3 credit, 6 bonus    -> bonus / credit movement
"""
import re

# Real payment methods named in a comment => a genuine client deposit/withdrawal,
# never an internal balance fix. Mirrors build_transactions.py line 50 / 72.
PAYMENT_METHOD_RE = re.compile(
    r"(qi ?card|zain\w*|asiapay|asiahawala|usdt|tether|al ?taif|sham|perfect ?money|"
    r"wallet|advcash|airtm|paymaxis|bridger|ptop|web ?money|cryptomus|payeer|fasapay)",
    re.I,
)

# Internal MT balance-adjustment labels (NOT real client money). Mirrors line 53.
# PostgreSQL \y word-boundary -> Python \b.
INTERNAL_LABEL_RE = re.compile(
    r"(deposit\s*[/ ]?\s*fix|withdraw\w*\s*[/ ]?\s*fix|balance\s*fix|deposit\s*fee|"
    r"negative\s*balance|stop\s*out\s*comp|reverting\s*cap|capital\s*refund|cash\s*back|"
    r"credit\s*(in|out)|bonus\s*adjustment|\bsync\b)",
    re.I,
)

# Movement kinds that represent REAL external client money (count toward funding).
REAL_DEPOSIT_KINDS = {"deposit"}
REAL_WITHDRAWAL_KINDS = {"withdrawal"}
# Kinds that hit the account balance but are NOT external client funding.
INTERNAL_KINDS = {
    "internal_transfer", "withdrawal_revert", "abuse_clawback",
    "balance_fix", "negative_cover", "bonus_deposit", "bonus_withdrawal",
}
TRADE_KINDS = {"trade"}


def _second_segment(comment: str, platform: str) -> str:
    """Resolve the 'method' the way build_transactions.py does: normalize hyphens to
    ' - ', take the 2nd ' - '-delimited segment, else fall back to platform."""
    norm = re.sub(r"\s*-\s*", " - ", comment or "")
    parts = norm.split(" - ")
    seg = parts[1].strip() if len(parts) >= 2 else ""
    return seg or (platform or "")


def classify(action, profit, comment="", platform="MT5") -> str:
    """Return the movement kind for one deal. Pure port of build_transactions.py.

    Returns one of:
        deposit | withdrawal | internal_transfer | withdrawal_revert | abuse_clawback |
        balance_fix | negative_cover | bonus_deposit | bonus_withdrawal | trade | unclassified
    """
    c = comment or ""
    lc = c.lower()

    if action in (0, 1):
        return "trade"

    if action == 2:
        if "transfer" in lc:
            return "internal_transfer"
        if re.search(r"revert.*withdraw", c, re.I):
            return "withdrawal_revert"
        if re.search(r"abus", c, re.I):
            return "abuse_clawback"
        # Internal balance adjustment? Only when NO real payment method is named AND the
        # resolved method is the bare 'MT5' fallback or an internal label.
        method = _second_segment(c, platform)
        if not PAYMENT_METHOD_RE.search(c) and (
            method == "MT5" or INTERNAL_LABEL_RE.search(method)
        ):
            return "negative_cover" if re.search(r"negative\s*balance", c, re.I) else "balance_fix"
        if profit > 0:
            return "deposit"
        if profit < 0:
            return "withdrawal"
        return "unclassified"  # action=2, profit==0 (filtered out upstream anyway)

    if action in (3, 6):
        return "bonus_deposit" if profit > 0 else "bonus_withdrawal"

    return "unclassified"

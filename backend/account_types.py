"""Single source of truth for classifying an MT trading-account GROUP into a
human-friendly account type + bonus eligibility.

The `trading_accounts.account_type` column is unreliable (it holds 'live', NULL,
or a raw MT group string depending on how the row was synced), so account type
must ALWAYS be derived from `group_name`, not from that column.

Rule (per the desk): ANY group whose type token is STD is a STANDARD account and
is eligible for the welcome + deposit bonus — regardless of the numeric prefix,
Islamic suffix, or extra modifiers. e.g. all of these are Standard:
    STD\\2-STD-IS   STD\\1-STD   2-STD   2-STD-IS   STD\\2-STD-IS-M05  ...

Display: show "Standard Islamic account" / "Standard account", NOT the raw
"STD\\2-STD-IS" group string, in the client portal.
"""
import re

# base type keyword (checked in this order) -> friendly base label
_BASES = [
    ("CENT", "Cent"),
    ("ZERO", "Zero"),
    ("VIP", "VIP"),
    ("ECN", "ECN"),
    ("PRO", "Pro"),
    ("FIX", "Fixed"),
    ("CONTEST", "Contest"),
    ("STD", "Standard"),
]


def classify_group(group_name: str) -> dict:
    """group_name -> {base, islamic, is_standard, label}.

    `is_standard` gates welcome/deposit bonus eligibility.
    `label` is what the client portal should display for the account type.
    """
    raw = (group_name or "").strip()
    g = raw.upper()
    tokens = [t for t in re.split(r"[\\/\-_ ]+", g) if t]

    islamic = "IS" in tokens  # a standalone -IS token = Islamic (swap-free)

    base = ""
    # TNFX-IB-N partner/IB groups first (they never contain STD)
    if "IB" in tokens and "STD" not in g:
        base = "IB"
    else:
        for kw, label in _BASES:
            if kw in g:
                base = label
                break

    is_standard = (base == "Standard")

    if base:
        label = base + (" Islamic" if islamic else "") + " account"
    else:
        label = raw  # unknown group -> show it as-is rather than a wrong guess

    return {"base": base, "islamic": islamic, "is_standard": is_standard, "label": label}


def account_label(group_name: str) -> str:
    return classify_group(group_name)["label"]


def is_standard_group(group_name: str) -> bool:
    return classify_group(group_name)["is_standard"]

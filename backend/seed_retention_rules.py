"""
seed_retention_rules.py — load the 119-rule Retention Engine catalog (Ticket #77).

Idempotent: CREATE TABLE IF NOT EXISTS + UPSERT by rule_id. Re-run any time to
refresh descriptions / points / automatable flags.

  python seed_retention_rules.py

`automatable` marks which rules the live retention_engine.py actually computes
from existing data (transactions / deals / account_identifiers / trading_accounts).
The rest are stored as DEFINED so the desk sees the full catalog in the UI, even
though the data to evaluate them (CRM call logs, KYC events, IB-commission dates,
device fingerprints, campaign CAC, etc.) is not yet wired.
"""
import sys
from sqlalchemy import text
from database import SessionLocal

# (rule_id, category, description, risk_points, trigger_level, suggested_action, days_to_action)
RULES = [
    (1,  "Deposit",      "Deposit then withdrawal <24h",                 30, "High",     "Call / Escalation",            "Same day (<=4h)"),
    (2,  "Deposit",      "Deposit then withdrawal <48h",                 25, "High",     "Call / Escalation",            "Same day (<=4h)"),
    (3,  "Deposit",      "Deposit then withdrawal <72h",                 20, "Medium",   "Message / Review",             "1 day (24h)"),
    (4,  "Deposit",      "More than 2 deposits within 24h",              10, "Low",      "Monitor",                      "3-7 days"),
    (5,  "Deposit",      "Deposit without trading 24h",                  15, "Medium",   "Message / Review",             "1 day (24h)"),
    (6,  "Deposit",      "Deposit without trading 72h",                  20, "Medium",   "Message / Review",             "1 day (24h)"),
    (7,  "Deposit",      "Second deposit lower than first",              10, "Low",      "Monitor",                      "3-7 days"),
    (8,  "Withdrawal",   "First withdrawal within 7 days",               25, "High",     "Call / Escalation",            "Same day (<=4h)"),
    (9,  "Withdrawal",   "First withdrawal within 14 days",              20, "Medium",   "Message / Review",             "1 day (24h)"),
    (10, "Withdrawal",   "Withdraw >50% balance",                        20, "Medium",   "Message / Review",             "1 day (24h)"),
    (11, "Withdrawal",   "Withdraw >80% balance",                        30, "High",     "Call / Escalation",            "Same day (<=4h)"),
    (12, "Withdrawal",   "More than 2 withdrawals within 7 days",        15, "Medium",   "Message / Review",             "1 day (24h)"),
    (13, "Withdrawal",   "Withdrawal without trading",                   25, "High",     "Call / Escalation",            "Same day (<=4h)"),
    (14, "Withdrawal",   "Withdrawal after loss",                        10, "Low",      "Monitor",                      "3-7 days"),
    (15, "Withdrawal",   "Withdrawal after profit",                      15, "Medium",   "Message / Review",             "1 day (24h)"),
    (16, "Withdrawal",   "Full balance withdrawal",                      40, "Critical", "Immediate Action / Supervisor","Immediate (<=1h)"),
    (17, "Withdrawal",   "Withdrawal request then cancel",               10, "Low",      "Monitor",                      "3-7 days"),
    (18, "Trading",      "No trades for 3 days",                         15, "Medium",   "Message / Review",             "1 day (24h)"),
    (19, "Trading",      "No trades for 7 days",                         25, "High",     "Call / Escalation",            "Same day (<=4h)"),
    (20, "Trading",      "Trading volume drop >60%",                     20, "Medium",   "Message / Review",             "1 day (24h)"),
    (21, "Trading",      "Trade only one day after deposit",             15, "Medium",   "Message / Review",             "1 day (24h)"),
    (22, "Trading",      "High trading with small balance",              10, "Low",      "Monitor",                      "3-7 days"),
    (23, "Trading",      "Scalping abuse",                               15, "Medium",   "Message / Review",             "1 day (24h)"),
    (24, "Trading",      "Rapid profit then stop trading",               20, "Medium",   "Message / Review",             "1 day (24h)"),
    (25, "Trading",      "Consecutive losses then stop",                 15, "Medium",   "Message / Review",             "1 day (24h)"),
    (26, "Trading",      "No stop loss usage",                           10, "Low",      "Monitor",                      "3-7 days"),
    (27, "Trading",      "Always using max leverage",                    10, "Low",      "Monitor",                      "3-7 days"),
    (28, "Activity",     "No login for 3 days",                          10, "Low",      "Monitor",                      "3-7 days"),
    (29, "Activity",     "No login for 7 days",                          20, "Medium",   "Message / Review",             "1 day (24h)"),
    (30, "Activity",     "No login for 14 days",                         30, "High",     "Call / Escalation",            "Same day (<=4h)"),
    (31, "Activity",     "Login without trading",                        10, "Low",      "Monitor",                      "3-7 days"),
    (32, "Activity",     "Frequent login without deposit",               10, "Low",      "Monitor",                      "3-7 days"),
    (33, "Activity",     "New device used suddenly",                     10, "Low",      "Monitor",                      "3-7 days"),
    (34, "Activity",     "IP or location change",                        15, "Medium",   "Message / Review",             "1 day (24h)"),
    (35, "Activity",     "Login at unusual hours",                       10, "Low",      "Monitor",                      "3-7 days"),
    (36, "Net",          "Net deposit negative",                         40, "Critical", "Immediate Action / Supervisor","Immediate (<=1h)"),
    (37, "Net",          "Net deposit <10%",                             25, "High",     "Call / Escalation",            "Same day (<=4h)"),
    (38, "Net",          "Net deposit <30%",                             15, "Medium",   "Message / Review",             "1 day (24h)"),
    (39, "Net",          "Net improving for 2 months",                  -15, "Low",      "Trusted / No Action",          "3-7 days"),
    (40, "Net",          "Net >50%",                                    -20, "Low",      "Trusted / No Action",          "3-7 days"),
    (41, "Net",          "Net >70%",                                    -30, "Low",      "Trusted / No Action",          "3-7 days"),
    (42, "Lifecycle",    "Account age <7 days",                          20, "Medium",   "Message / Review",             "1 day (24h)"),
    (43, "Lifecycle",    "Account age <14 days",                         15, "Medium",   "Message / Review",             "1 day (24h)"),
    (44, "Lifecycle",    "Account age >90 days",                        -10, "Low",      "Trusted / No Action",          "3-7 days"),
    (45, "Lifecycle",    "Account age >180 days",                       -20, "Low",      "Trusted / No Action",          "3-7 days"),
    (46, "Lifecycle",    "New client + early withdrawal",                30, "High",     "Call / Escalation",            "Same day (<=4h)"),
    (47, "Lifecycle",    "Old client + normal behavior",               -15, "Low",      "Trusted / No Action",          "3-7 days"),
    (48, "Source",       "Client from high-withdrawal IB",               20, "Medium",   "Message / Review",             "1 day (24h)"),
    (49, "Source",       "Client from high CAC campaign",                15, "Medium",   "Message / Review",             "1 day (24h)"),
    (50, "Source",       "Client from organic campaign",                -10, "Low",      "Trusted / No Action",          "3-7 days"),
    (51, "Source",       "Client from direct referral",                 -15, "Low",      "Trusted / No Action",          "3-7 days"),
    (52, "Source",       "IB with historically weak net",                25, "High",     "Call / Escalation",            "Same day (<=4h)"),
    (53, "Source",       "IB net improving",                            -15, "Low",      "Trusted / No Action",          "3-7 days"),
    (54, "Bonus",        "Bonus taken without trading",                  25, "High",     "Call / Escalation",            "Same day (<=4h)"),
    (55, "Bonus",        "Bonus larger than deposit",                    20, "Medium",   "Message / Review",             "1 day (24h)"),
    (56, "Bonus",        "Bonus + fast withdrawal",                      30, "High",     "Call / Escalation",            "Same day (<=4h)"),
    (57, "Bonus",        "Bonus conditions not completed",               15, "Medium",   "Message / Review",             "1 day (24h)"),
    (58, "Bonus",        "Repeated bonus usage",                         20, "Medium",   "Message / Review",             "1 day (24h)"),
    (59, "Bonus",        "Bonus + negative net",                         30, "High",     "Call / Escalation",            "Same day (<=4h)"),
    (60, "Advanced",     "Repeated deposit-withdraw pattern",            30, "High",     "Call / Escalation",            "Same day (<=4h)"),
    (61, "Advanced",     "Circular deposits (same amount)",              15, "Medium",   "Message / Review",             "1 day (24h)"),
    (62, "Advanced",     "Sudden change in deposit pattern",             10, "Low",      "Monitor",                      "3-7 days"),
    (63, "Advanced",     "Timing arbitrage attempt",                     20, "Medium",   "Message / Review",             "1 day (24h)"),
    (64, "Advanced",     "Activity only during promotions",              15, "Medium",   "Message / Review",             "1 day (24h)"),
    (65, "Value",        "High LTV",                                    -30, "Low",      "Trusted / No Action",          "3-7 days"),
    (66, "Value",        "VIP client",                                  -40, "Low",      "Trusted / No Action",          "3-7 days"),
    (67, "Value",        "High historical profitability",               -20, "Low",      "Trusted / No Action",          "3-7 days"),
    (68, "Value",        "Long stable relationship",                    -25, "Low",      "Trusted / No Action",          "3-7 days"),
    (69, "Value",        "Long-term stable trading",                    -30, "Low",      "Trusted / No Action",          "3-7 days"),
    (70, "Admin",        "Ignoring previous calls",                      10, "Low",      "Monitor",                      "3-7 days"),
    (71, "Admin",        "Task closed without result",                    5, "Low",      "Monitor",                      "3-7 days"),
    (72, "Admin",        "Repeated same issue",                          15, "Medium",   "Message / Review",             "1 day (24h)"),
    (73, "Admin",        "SLA missed",                                   10, "Low",      "Monitor",                      "3-7 days"),
    (74, "Admin",        "Official complaint",                           20, "Medium",   "Message / Review",             "1 day (24h)"),
    (75, "Time",         "Deposit always same hour",                     10, "Low",      "Monitor",                      "3-7 days"),
    (76, "Time",         "Withdrawal same weekday",                      10, "Low",      "Monitor",                      "3-7 days"),
    (77, "Time",         "Strong activity early month then drop",        15, "Medium",   "Message / Review",             "1 day (24h)"),
    (78, "Time",         "Withdrawal at month end",                      15, "Medium",   "Message / Review",             "1 day (24h)"),
    (79, "Time",         "Deposit only during promotions",               20, "Medium",   "Message / Review",             "1 day (24h)"),
    (80, "Time",         "Activity stops after promotion",               20, "Medium",   "Message / Review",             "1 day (24h)"),
    (81, "Time",         "High withdrawals during low liquidity",        25, "High",     "Call / Escalation",            "Same day (<=4h)"),
    (82, "Sequence",     "Deposit -> bonus -> trade -> withdraw",        30, "High",     "Call / Escalation",            "Same day (<=4h)"),
    (83, "Sequence",     "Deposit -> wait -> withdraw no trade",         30, "High",     "Call / Escalation",            "Same day (<=4h)"),
    (84, "Sequence",     "Profit -> stop -> full withdrawal",            25, "High",     "Call / Escalation",            "Same day (<=4h)"),
    (85, "Sequence",     "Loss -> redeposit -> fast withdraw",           20, "Medium",   "Message / Review",             "1 day (24h)"),
    (86, "Sequence",     "Scenario repeated 3 times",                    40, "Critical", "Immediate Action / Supervisor","Immediate (<=1h)"),
    (87, "Communication","Ignoring 3 calls",                             15, "Medium",   "Message / Review",             "1 day (24h)"),
    (88, "Communication","Refuses retention contact",                    20, "Medium",   "Message / Review",             "1 day (24h)"),
    (89, "Communication","Promise deposit not fulfilled",                10, "Low",      "Monitor",                      "3-7 days"),
    (90, "Communication","Bonus request via support",                    15, "Medium",   "Message / Review",             "1 day (24h)"),
    (91, "Communication","High contact without financial activity",      10, "Low",      "Monitor",                      "3-7 days"),
    (92, "Communication","Aggressive / complaint tone",                  15, "Medium",   "Message / Review",             "1 day (24h)"),
    (93, "Tech",         "Multiple devices within 24h",                  15, "Medium",   "Message / Review",             "1 day (24h)"),
    (94, "Tech",         "New device before withdrawal",                 20, "Medium",   "Message / Review",             "1 day (24h)"),
    (95, "Tech",         "VPN usage during withdrawal",                  25, "High",     "Call / Escalation",            "Same day (<=4h)"),
    (96, "Tech",         "IP country differs from registration",         20, "Medium",   "Message / Review",             "1 day (24h)"),
    (97, "Tech",         "Frequent browser/OS change",                   10, "Low",      "Monitor",                      "3-7 days"),
    (98, "Cluster",      "Behavior similar to high-withdraw group",      25, "High",     "Call / Escalation",            "Same day (<=4h)"),
    (99, "Cluster",      "Deposit timing matches suspicious group",      20, "Medium",   "Message / Review",             "1 day (24h)"),
    (100,"Cluster",      "Same IB creates same pattern",                 30, "High",     "Call / Escalation",            "Same day (<=4h)"),
    (101,"Cluster",      "Campaign produces same behavior",              25, "High",     "Call / Escalation",            "Same day (<=4h)"),
    (102,"Behavior",     "Overtrading after profit",                     15, "Medium",   "Message / Review",             "1 day (24h)"),
    (103,"Behavior",     "Stops trading after small loss",               10, "Low",      "Monitor",                      "3-7 days"),
    (104,"Behavior",     "Sudden risk increase",                         20, "Medium",   "Message / Review",             "1 day (24h)"),
    (105,"Behavior",     "High position size volatility",                15, "Medium",   "Message / Review",             "1 day (24h)"),
    (106,"Behavior",     "Sudden strategy change",                       10, "Low",      "Monitor",                      "3-7 days"),
    (107,"Compliance",   "KYC requested then withdrawal",                25, "High",     "Call / Escalation",            "Same day (<=4h)"),
    (108,"Compliance",   "Refuses data update",                          20, "Medium",   "Message / Review",             "1 day (24h)"),
    (109,"Compliance",   "Financial activity before KYC",                30, "High",     "Call / Escalation",            "Same day (<=4h)"),
    (110,"Compliance",   "Withdrawal above allowed limit",               20, "Medium",   "Message / Review",             "1 day (24h)"),
    (111,"IB",           "IB client withdraws before commission date",   20, "Medium",   "Message / Review",             "1 day (24h)"),
    (112,"IB",           "IB pressures fast withdrawal",                 30, "High",     "Call / Escalation",            "Same day (<=4h)"),
    (113,"IB",           "Client stops after IB commission",             25, "High",     "Call / Escalation",            "Same day (<=4h)"),
    (114,"IB",           "Same IB same pattern monthly",                 35, "High",     "Call / Escalation",            "Same day (<=4h)"),
    (115,"Governance",   "Previous admin exception",                     20, "Medium",   "Message / Review",             "1 day (24h)"),
    (116,"Governance",   "Manual intervention undocumented",             15, "Medium",   "Message / Review",             "1 day (24h)"),
    (117,"Governance",   "Task closed without action",                   10, "Low",      "Monitor",                      "3-7 days"),
    (118,"Governance",   "Issue reopened",                               15, "Medium",   "Message / Review",             "1 day (24h)"),
    (119,"Governance",   "System recommendation ignored",                20, "Medium",   "Message / Review",             "1 day (24h)"),
]

# Rules the live engine evaluates from existing data (see retention_engine.py).
AUTOMATABLE = {
    1, 2, 3, 4, 5, 6, 7,          # Deposit timing / cadence (transactions + deals)
    8, 9, 10, 11, 12, 13, 16,     # Withdrawal timing / size / no-trade (transactions + trading_accounts)
    18, 19, 20, 24,               # Trading gaps / volume drop / rapid-profit-then-stop (deals)
    36, 37, 38, 39, 40, 41,       # Net deposit bands (transactions)
    42, 43, 44, 45, 46, 47,       # Account age (reg_date)
    54, 55, 56, 58, 59,           # Bonus (transactions tx_type bonus%)
    60,                           # Repeated deposit-withdraw pattern
    65, 66, 67, 69,               # Value / LTV / profitability (deals + transactions)
    83,                           # Deposit -> wait -> withdraw no trade
    93,                           # Multiple devices within 24h (account_identifiers)
}


def ensure_schema(db):
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS retention_rules (
            rule_id        INTEGER PRIMARY KEY,
            category       VARCHAR(40),
            description    TEXT,
            risk_points    INTEGER,
            trigger_level  VARCHAR(16),
            suggested_action VARCHAR(64),
            days_to_action VARCHAR(32),
            automatable    BOOLEAN DEFAULT FALSE,
            updated_at     TIMESTAMPTZ DEFAULT NOW()
        )
    """))
    db.execute(text("CREATE INDEX IF NOT EXISTS retention_rules_cat_idx ON retention_rules(category)"))
    db.commit()


def seed(db):
    for (rid, cat, desc, pts, lvl, action, days) in RULES:
        db.execute(text("""
            INSERT INTO retention_rules
                (rule_id, category, description, risk_points, trigger_level,
                 suggested_action, days_to_action, automatable, updated_at)
            VALUES (:rid,:cat,:desc,:pts,:lvl,:act,:days,:auto,NOW())
            ON CONFLICT (rule_id) DO UPDATE SET
                category=EXCLUDED.category, description=EXCLUDED.description,
                risk_points=EXCLUDED.risk_points, trigger_level=EXCLUDED.trigger_level,
                suggested_action=EXCLUDED.suggested_action, days_to_action=EXCLUDED.days_to_action,
                automatable=EXCLUDED.automatable, updated_at=NOW()
        """), {"rid": rid, "cat": cat, "desc": desc, "pts": pts, "lvl": lvl,
               "act": action, "days": days, "auto": rid in AUTOMATABLE})
    db.commit()


def main():
    db = SessionLocal()
    try:
        ensure_schema(db)
        seed(db)
        n = db.execute(text("SELECT count(*) FROM retention_rules")).scalar()
        a = db.execute(text("SELECT count(*) FROM retention_rules WHERE automatable")).scalar()
        print(f"retention_rules seeded: {n} rules total, {a} automatable.")
    finally:
        db.close()


if __name__ == "__main__":
    main()

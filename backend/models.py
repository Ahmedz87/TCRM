"""
Broker CRM — Complete Database Schema v2.0
Architect: Claude + Ahmad

Design principles:
1. Fetch once from MT5 → feed all tables
2. Pre-compute expensive calculations (markup, commission, risk scores)
3. Index everything that gets searched or filtered
4. Never make user wait — all heavy work done in background
5. Support 14,235+ clients, 13M+ deals, 100 staff, real-time feel
"""
from sqlalchemy import (Column, Integer, String, Boolean, DateTime,
                        Float, Text, ForeignKey, BigInteger, Index,
                        UniqueConstraint)
from sqlalchemy.sql import func
from database import Base


# ══════════════════════════════════════════════════════════════════════════
# 1. STAFF & ACCESS CONTROL
# ══════════════════════════════════════════════════════════════════════════

class User(Base):
    """
    Internal CRM staff.
    100 users across 9 roles.
    """
    __tablename__ = "users"
    id              = Column(Integer, primary_key=True)
    full_name       = Column(String, nullable=False)
    email           = Column(String, unique=True, index=True, nullable=False)
    phone           = Column(String)
    hashed_password = Column(String, nullable=False)
    role            = Column(String, default="sales_agent", index=True)
    # super_admin | admin | sales_manager | sales_agent
    # compliance | finance | support | ib_portal | read_only
    is_active       = Column(Boolean, default=True)
    language        = Column(String, default="en")   # en | ar
    manager_id      = Column(Integer, ForeignKey("users.id"))
    extension       = Column(String)   # Yeastar PBX extension e.g. "101"
    avatar_url      = Column(String)
    last_login_at   = Column(DateTime(timezone=True))
    title           = Column(String)        # job title
    department      = Column(String)        # Sales / Customer Care / Back Office / ...
    previous_name   = Column(String)        # old name (for matching legacy assignments)
    team_type       = Column(String)        # retention / sales / lead / director
    must_change_password = Column(Boolean, default=False)  # force change on first login
    can_reassign_agent   = Column(Boolean, default=False)  # may change a lead/client's sales agent
    tokens_valid_after   = Column(DateTime(timezone=True))  # JWTs issued before this are rejected
                                                            # (set on password change -> kills old sessions)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    updated_at      = Column(DateTime(timezone=True), onupdate=func.now())


# ══════════════════════════════════════════════════════════════════════════
# 2. CLIENTS — master record per real person
# ══════════════════════════════════════════════════════════════════════════

class Client(Base):
    """
    One row per real human being.
    A person can have many TradingAccounts.
    Synced from MT5 + enriched by CRM staff.

    MY IDEA: Store pre-computed financial summary here so client list
    loads instantly without joining 13M deal rows every time.
    """
    __tablename__ = "clients"
    id              = Column(Integer, primary_key=True)
    # MT5 identifiers
    login           = Column(Integer, unique=True, index=True, nullable=False)
    cid             = Column(String, index=True)      # ClientID from MT5
    mqid            = Column(BigInteger, index=True)  # MetaQuotes ID

    # Personal info
    name            = Column(String, index=True)
    email           = Column(String, index=True)
    phone           = Column(String)
    city            = Column(String, index=True)
    country         = Column(String, index=True)
    nationality     = Column(String)
    date_of_birth   = Column(String)
    full_name_en    = Column(String)              # English/Latin transliteration (3-part)
    customer_no     = Column(String, index=True)  # CUS golden-record id (customer master)
    email_verified  = Column(Boolean, default=False)
    phone_verified  = Column(Boolean, default=False)
    tokens_valid_after = Column(DateTime(timezone=True))  # portal JWTs issued before this are rejected

    # Archive state — MT4/MT5 archives idle accounts with balance < $1 weekly. Additive/read-only:
    # archived_at set => account is archived (portal blocks new deposit/transfer; history kept).
    archived_at        = Column(DateTime(timezone=True), index=True)
    archive_reason     = Column(String)
    mt_last_seen       = Column(DateTime(timezone=True))  # last seen in an MT pull (archive detector)

    # MT5 account info
    last_ip         = Column(String, index=True)
    group_name      = Column(String, index=True)
    leverage        = Column(Integer, default=100)
    agent           = Column(Integer, index=True)   # MT5 agent = IB link
    reg_date        = Column(String)

    # Live financial (updated every sync — fast to read)
    balance         = Column(Float, default=0)
    equity          = Column(Float, default=0)
    credit          = Column(Float, default=0)
    margin          = Column(Float, default=0)
    margin_level    = Column(Float, default=0)
    free_margin     = Column(Float, default=0)

    # Pre-computed financial summary (saves joining deals table)
    total_deposits      = Column(Float, default=0)
    total_withdrawals   = Column(Float, default=0)
    net_deposit         = Column(Float, default=0)
    total_volume_lots   = Column(Float, default=0)   # all-time trading volume
    total_trades        = Column(Integer, default=0)
    total_markup_revenue= Column(Float, default=0)   # broker revenue from this client
    total_commission_paid= Column(Float, default=0)  # commission paid to IB/sales
    total_swap          = Column(Float, default=0)

    # First/last activity dates
    first_deposit_at     = Column(String)
    first_deposit_amount = Column(Float, default=0)
    last_deposit_at      = Column(String, index=True)
    last_withdraw_at     = Column(String)
    last_trade_at        = Column(String, index=True)
    last_login_at        = Column(String, index=True)

    # CRM classification
    kyc_status      = Column(String, default="pending", index=True)
    # pending | verified | rejected | expired | enhanced
    risk_score      = Column(String, default="low", index=True)
    # low | medium | high
    call_score      = Column(Integer, default=0, index=True)  # 0-100 priority score
    network_score   = Column(Integer, default=0)              # 0-10 fraud risk
    client_status   = Column(String, default="lead", index=True)
    # lead | registered | demo | funded | active | inactive | suspended | churned
    source          = Column(String, default="none", index=True)
    # facebook | instagram | tiktok | google | youtube | organic | referral | ib | none | other
    utm_campaign    = Column(String)   # for paid traffic tracking
    utm_medium      = Column(String)
    utm_source      = Column(String)

    # Assignments
    assigned_agent_id = Column(Integer, ForeignKey("users.id"), index=True)
    ib_id             = Column(Integer, ForeignKey("ibs.id"), index=True)

    # Loyalty
    loyalty_points  = Column(Integer, default=0)
    loyalty_tier    = Column(String, default="bronze", index=True)
    # bronze | silver | gold | platinum | vip

    # Flags
    is_active       = Column(Boolean, default=True)
    is_flagged      = Column(Boolean, default=False, index=True)
    flag_reason     = Column(String)
    is_duplicate    = Column(Boolean, default=False)  # suspected duplicate account

    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_client_country_status", "country", "client_status"),
        Index("ix_client_agent_score",    "assigned_agent_id", "call_score"),
        Index("ix_client_ib_volume",      "ib_id", "total_volume_lots"),
    )


# ══════════════════════════════════════════════════════════════════════════
# 3. TRADING ACCOUNTS — one MT5 login per account
# ══════════════════════════════════════════════════════════════════════════

class TradingAccount(Base):
    """
    Every MT5 login.
    - account_type: live | demo | islamic (group ends with -IS) | ib
    - is_islamic: group_name ends with '-IS'
    - is_ib: group_name contains 'IB'
    - Each account has its own IPs, CIDs, MQIDs in account_identifiers table
    """
    __tablename__ = "trading_accounts"
    id           = Column(Integer, primary_key=True)
    login        = Column(Integer, unique=True, index=True, nullable=False)
    client_id    = Column(Integer, ForeignKey("clients.id"), index=True, nullable=True)

    # Personal info
    name         = Column(String)
    email        = Column(String, index=True)
    phone        = Column(String)

    # MT5 account info
    group_name   = Column(String, index=True)
    account_type = Column(String, default="live", index=True)
    # live | demo | islamic | ib
    is_islamic   = Column(Boolean, default=False)  # group ends with -IS
    is_ib        = Column(Boolean, default=False)  # group contains IB
    leverage     = Column(Integer, default=100)

    # Financial
    balance      = Column(Float, default=0)
    equity       = Column(Float, default=0)
    credit       = Column(Float, default=0)
    margin_level = Column(Float, default=0)
    free_margin  = Column(Float, default=0)

    # IB reference
    agent        = Column(Integer, index=True)  # IB login

    # Location & identity
    country      = Column(String)
    city         = Column(String)
    last_ip      = Column(String)
    cid          = Column(String)
    mqid         = Column(BigInteger, default=0)

    # Dates
    reg_date          = Column(String)
    first_deposit_at  = Column(String)
    last_deposit_at   = Column(String)
    last_trade_at     = Column(String)
    last_login_at     = Column(String)

    # Status
    is_active    = Column(Boolean, default=True)
    kyc_status   = Column(String, default="pending")
    risk_score   = Column(String, default="low")
    source       = Column(String, default="none")

    # Summary stats (aggregated from deals)
    total_deposits    = Column(Float, default=0)
    total_withdrawals = Column(Float, default=0)
    total_volume      = Column(Float, default=0)   # lots
    total_trades      = Column(Integer, default=0)
    total_markup      = Column(Float, default=0)
    net_deposit       = Column(Float, default=0)   # deposits - withdrawals

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# ══════════════════════════════════════════════════════════════════════════
# 4. SYMBOLS — instruments with markup config
# ══════════════════════════════════════════════════════════════════════════

class Symbol(Base):
    """
    Every tradeable instrument.
    MY IDEA: Store category, markup, pip value, contract size.
    This lets us calculate exact broker revenue per trade.
    Admin can change markup rate in CRM — no code change needed.
    """
    __tablename__ = "symbols"
    id              = Column(Integer, primary_key=True)
    name            = Column(String, unique=True, index=True, nullable=False)
    display_name    = Column(String)
    category        = Column(String, default="forex", index=True)
    # forex | metals | indices | crypto | energy | stocks | bonds
    markup_per_lot  = Column(Float, default=7.0)   # $ broker earns per standard lot
    pip_value       = Column(Float, default=10.0)  # $ per pip per lot
    contract_size   = Column(Float, default=100000)
    min_lot         = Column(Float, default=0.01)
    max_lot         = Column(Float, default=100.0)
    lot_step        = Column(Float, default=0.01)
    currency        = Column(String, default="USD")
    is_active       = Column(Boolean, default=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    updated_at      = Column(DateTime(timezone=True), onupdate=func.now())


# ══════════════════════════════════════════════════════════════════════════
# 5. DEALS — every transaction (the most important table)
# ══════════════════════════════════════════════════════════════════════════

class Deal(Base):
    """
    Every MT5 deal — trades, deposits, withdrawals, credits.
    13M+ rows. Heavily indexed for fast queries.

    MY IDEA: Pre-calculate markup_profit per deal at insert time.
    This means revenue reports run instantly — no calculation needed.
    """
    __tablename__ = "deals"
    id              = Column(BigInteger, primary_key=True)
    deal_id         = Column(BigInteger, unique=True, index=True, nullable=False)
    login           = Column(Integer, index=True, nullable=False)
    client_id       = Column(Integer, ForeignKey("clients.id"), index=True)
    symbol          = Column(String, index=True)
    symbol_category = Column(String, index=True)   # denormalized for fast category reports
    action          = Column(Integer)
    deal_type       = Column(String, index=True)
    # trade | deposit | withdrawal | credit_in | credit_out | internal_transfer
    entry           = Column(Integer)   # 0=in 1=out 2=reverse
    direction       = Column(String)    # buy | sell (for trades only)
    volume          = Column(Float, default=0)
    price           = Column(Float, default=0)
    profit          = Column(Float, default=0)
    commission      = Column(Float, default=0)
    swap            = Column(Float, default=0)
    comment         = Column(String)
    balance_after   = Column(Float, default=0)   # account balance AFTER this deal
    # Pre-computed revenue (broker profit from this deal)
    markup_per_lot  = Column(Float, default=0)   # rate used at time of trade
    markup_profit   = Column(Float, default=0)   # volume * markup_per_lot
    # Time fields — multiple formats for different query needs
    deal_time       = Column(BigInteger, index=True)   # unix timestamp
    deal_date       = Column(String, index=True)       # YYYY-MM-DD
    deal_month      = Column(String, index=True)       # YYYY-MM for monthly reports
    deal_year       = Column(Integer, index=True)      # for yearly reports
    created_at      = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_deal_login_type",     "login", "deal_type"),
        Index("ix_deal_login_date",     "login", "deal_date"),
        Index("ix_deal_symbol_month",   "symbol", "deal_month"),
        Index("ix_deal_client_month",   "client_id", "deal_month"),
        Index("ix_deal_type_month",     "deal_type", "deal_month"),
    )


# ══════════════════════════════════════════════════════════════════════════
# 6. FRAUD DETECTION — identifiers, network, duplicates
# ══════════════════════════════════════════════════════════════════════════

class AccountIdentifier(Base):
    """
    Every IP, CID, MQID ever used by every account.
    MY IDEA: Track seen_count and date range — shows usage pattern.
    A genuine client logs in from same IP. Fraudster uses many IPs.
    """
    __tablename__ = "account_identifiers"
    __table_args__ = (
        UniqueConstraint("login", "identifier_type", "identifier_value"),
        Index("ix_identifier_lookup", "identifier_type", "identifier_value"),
    )
    id               = Column(Integer, primary_key=True)
    login            = Column(Integer, index=True, nullable=False)
    identifier_type  = Column(String, index=True, nullable=False)  # ip | cid | mqid
    identifier_value = Column(String, index=True, nullable=False)
    first_seen       = Column(DateTime(timezone=True), server_default=func.now())
    last_seen        = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    seen_count       = Column(Integer, default=1)


class NetworkEdge(Base):
    """
    Pre-computed connections between accounts.
    MY IDEA: Store weight (strength of connection) and reason.
    Shared IP=3pts, shared CID=3pts, same family=1pt, same IB=1pt.
    Higher weight = stronger fraud signal.
    """
    __tablename__ = "network_edges"
    __table_args__ = (
        Index("ix_edge_login_a", "login_a"),
        Index("ix_edge_login_b", "login_b"),
        Index("ix_edge_reason",  "reason"),
    )
    id        = Column(Integer, primary_key=True)
    login_a   = Column(Integer, nullable=False)
    login_b   = Column(Integer, nullable=False)
    reason    = Column(String, nullable=False)  # ip | cid | mqid | family | ib | payment
    value     = Column(String)                  # the shared value
    weight    = Column(Integer, default=1)      # fraud signal strength
    created_at= Column(DateTime(timezone=True), server_default=func.now())
    updated_at= Column(DateTime(timezone=True), onupdate=func.now())


class DuplicateGroup(Base):
    """
    MY IDEA: When we detect 2+ accounts are the same person,
    group them together. Admin can confirm or dismiss.
    This powers the 'duplicate FTD' bonus check.
    """
    __tablename__ = "duplicate_groups"
    id          = Column(Integer, primary_key=True)
    group_key   = Column(String, index=True, nullable=False)  # ip:1.2.3.4 or cid:C100021
    login       = Column(Integer, index=True, nullable=False)
    reason      = Column(String)
    confidence  = Column(Float, default=1.0)  # 0.0-1.0
    status      = Column(String, default="pending")  # pending | confirmed | dismissed
    reviewed_by = Column(Integer, ForeignKey("users.id"))
    reviewed_at = Column(DateTime(timezone=True))
    created_at  = Column(DateTime(timezone=True), server_default=func.now())


# ══════════════════════════════════════════════════════════════════════════
# 7. IB SYSTEM
# ══════════════════════════════════════════════════════════════════════════

class IB(Base):
    """
    IB Partners — clients who own at least one trading account
    with group_name containing 'IB'.

    Level system: 6=Bronze, 7=Silver, 8=Gold, 9=Platinum, 10=Diamond
    Commission: 6-10 pts/lot based on level
    """
    __tablename__ = "ibs"
    id              = Column(Integer, primary_key=True)
    agent_id        = Column(Integer, unique=True, index=True, nullable=False)
    # agent_id = the MT5 login of their IB trading account

    ib_code         = Column(String, unique=True, index=True)
    name            = Column(String, nullable=False, index=True)
    email           = Column(String, index=True)
    phone           = Column(String)
    country         = Column(String, index=True)
    city            = Column(String)

    # Hierarchy
    parent_ib_id    = Column(Integer, ForeignKey("ibs.id"), nullable=True)
    # NULL = master IB, set = sub-IB under parent

    # Plugit sync (IB Code.xlsx / IB Profile.xlsx)
    ext_ib_id        = Column(Integer, nullable=True)      # unique IB ID from Plugit
    ib_creation_date = Column(DateTime(timezone=True), nullable=True)  # when they became an IB
    is_sub_ib        = Column(Boolean, default=False)
    markup_pips      = Column(Float, nullable=True)
    plugit_status    = Column(String, nullable=True)
    total_payoff     = Column(Float, default=0)       # money the IB withdrew (from ib_operations)
    commission_excel    = Column(Float, default=0)    # Plugit commission 2023-01..2026-07 (authoritative)
    commission_computed = Column(Float, default=0)    # our deals-based commission for uncovered dates (pre-2023)
    commission_source   = Column(String, nullable=True)  # 'excel' | 'excel+computed' | 'computed'
    commission_live     = Column(Float, default=0)    # post-Excel-cutoff commission from new trades (refreshed every 30min by ib_trades)

    # Assignments
    commission_plan_id = Column(Integer, ForeignKey("commission_plans.id"), nullable=True)
    assigned_agent_id  = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Status
    kyc_status      = Column(String, default="pending")
    status          = Column(String, default="active", index=True)

    # Level system (6=Bronze to 10=Diamond)
    ib_level        = Column(Integer, default=6, index=True)
    # pts/lot: L6=6, L7=7, L8=8, L9=9, L10=10

    # Promotion criteria (tracked in real-time)
    unique_ftds     = Column(Integer, default=0)
    total_clients   = Column(Integer, default=0)
    active_clients  = Column(Integer, default=0)
    total_volume    = Column(Float, default=0)    # lots traded by clients
    net_deposits    = Column(Float, default=0)    # net deposits by clients
    referral_clicks = Column(Integer, default=0)

    # Commission
    total_commission  = Column(Float, default=0)
    unpaid_commission = Column(Float, default=0)
    paid_commission   = Column(Float, default=0)

    # IB account info
    group_name      = Column(String)
    balance         = Column(Float, default=0)

    # Marketing
    referral_link   = Column(String)

    notes           = Column(Text)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    updated_at      = Column(DateTime(timezone=True), onupdate=func.now())


class CommissionPlan(Base):
    """
    Commission rate tables for IBs and sales.
    MY IDEA: Per-category rates so XAUUSD (metals) pays different from EURUSD (forex).
    Admin can create multiple plans and assign to different IBs.
    """
    __tablename__ = "commission_plans"
    id              = Column(Integer, primary_key=True)
    name            = Column(String, nullable=False)
    plan_type       = Column(String, default="ib")  # ib | sales
    # Rates in $ per standard lot
    forex_rate      = Column(Float, default=4.0)
    metals_rate     = Column(Float, default=6.0)
    indices_rate    = Column(Float, default=5.0)
    crypto_rate     = Column(Float, default=10.0)
    energy_rate     = Column(Float, default=4.0)
    stocks_rate     = Column(Float, default=3.0)
    bonds_rate      = Column(Float, default=2.0)
    # Payment settings
    payment_frequency  = Column(String, default="monthly")
    min_payout         = Column(Float, default=100.0)
    max_monthly_cap    = Column(Float, default=0)   # 0 = no cap
    rebate_on_sub_ibs  = Column(Float, default=0)   # % override from sub-IB commissions
    is_active          = Column(Boolean, default=True)
    created_at         = Column(DateTime(timezone=True), server_default=func.now())


class IBCommission(Base):
    """
    Commission earned by IB — one row per deal.
    MY IDEA: Store at deal level for detailed reporting.
    Can then aggregate by day/week/month/symbol/client.
    """
    __tablename__ = "ib_commissions"
    id               = Column(Integer, primary_key=True)
    ib_id            = Column(Integer, ForeignKey("ibs.id"), index=True, nullable=False)
    ib_login         = Column(Integer, index=True)   # IB's MT5 login
    deal_id          = Column(BigInteger, index=True)
    client_login     = Column(Integer, index=True)   # client's MT5 login
    symbol           = Column(String, index=True)
    volume           = Column(Float, default=0)      # lots traded
    pts_per_lot      = Column(Float, default=5)      # from IB group (IB-5=5, IB-6=6...)
    quote_currency   = Column(String, default="USD") # quote currency of the pair
    commission_native= Column(Float, default=0)      # commission in quote currency
    fx_rate          = Column(Float, default=1.0)    # rate to USD at time of trade
    commission_usd   = Column(Float, default=0)      # commission in USD
    commission_type  = Column(String, default="direct") # direct | override
    override_from_ib = Column(Integer)               # sub-IB login (for override rows)
    trade_date       = Column(String, index=True)
    deal_month       = Column(String, index=True)
    status           = Column(String, default="unpaid", index=True) # unpaid | paid
    paid_at          = Column(DateTime(timezone=True))
    created_at       = Column(DateTime(timezone=True), server_default=func.now())


class IBChallenge(Base):
    """IB challenge campaigns."""
    __tablename__ = "ib_challenges"
    id              = Column(Integer, primary_key=True)
    name            = Column(String, nullable=False)
    description     = Column(Text)
    reward_amount   = Column(Float, nullable=False)
    reward_type     = Column(String, default="cash")  # cash | bonus | gift
    duration_days   = Column(Integer, nullable=False)
    condition_type  = Column(String, nullable=False)
    # ftd_count | lot_volume | net_deposit | link_clicks | unique_clients
    condition_value = Column(Float, nullable=False)
    min_deposit_per_ftd = Column(Float, default=0)
    start_date      = Column(String)
    end_date        = Column(String)
    max_winners     = Column(Integer, default=0)  # 0 = unlimited
    is_active       = Column(Boolean, default=True, index=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())


class IBChallengeProgress(Base):
    """IB progress per challenge."""
    __tablename__ = "ib_challenge_progress"
    id           = Column(Integer, primary_key=True)
    challenge_id = Column(Integer, ForeignKey("ib_challenges.id"), index=True)
    ib_id        = Column(Integer, ForeignKey("ibs.id"), index=True)
    current_value= Column(Float, default=0)
    target_value = Column(Float, default=0)
    progress_pct = Column(Float, default=0)
    status       = Column(String, default="active", index=True)
    reward_paid  = Column(Boolean, default=False)
    completed_at = Column(DateTime(timezone=True))
    created_at   = Column(DateTime(timezone=True), server_default=func.now())
    updated_at   = Column(DateTime(timezone=True), onupdate=func.now())


class IBReferralClick(Base):
    """
    MY IDEA: Track every click on IB referral links.
    Stores IP, timestamp, whether it converted to a registration.
    Used for IB challenge 'link clicks' condition.
    """
    __tablename__ = "ib_referral_clicks"
    id          = Column(Integer, primary_key=True)
    ib_id       = Column(Integer, ForeignKey("ibs.id"), index=True)
    ip_address  = Column(String)
    user_agent  = Column(String)
    converted   = Column(Boolean, default=False)  # did they register?
    login       = Column(Integer)                  # if converted, their login
    clicked_at  = Column(DateTime(timezone=True), server_default=func.now())


# ══════════════════════════════════════════════════════════════════════════
# 8. SALES SYSTEM
# ══════════════════════════════════════════════════════════════════════════

class Lead(Base):
    """
    MY IDEA: Separate leads table from clients.
    Leads are pre-registration prospects.
    When they register → convert to Client record.
    Track full journey: lead → demo → funded → active.
    """
    __tablename__ = "leads"
    id              = Column(Integer, primary_key=True)
    full_name       = Column(String, index=True)
    email           = Column(String, index=True)
    phone           = Column(String)
    country         = Column(String, index=True)
    city            = Column(String)
    source          = Column(String, index=True)
    utm_campaign    = Column(String)
    utm_medium      = Column(String)
    stage           = Column(String, default="new", index=True)
    # new | contacted | demo_opened | deposit_pending | converted | lost
    assigned_agent_id = Column(Integer, ForeignKey("users.id"), index=True)
    ib_id           = Column(Integer, ForeignKey("ibs.id"))
    converted_login = Column(Integer)   # MT5 login after conversion
    notes           = Column(Text)
    last_contact_at = Column(DateTime(timezone=True))
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    updated_at      = Column(DateTime(timezone=True), onupdate=func.now())


class SalesTarget(Base):
    """
    MY IDEA: Monthly targets per agent.
    System auto-calculates commission based on achievement %.
    80% target = 80% commission. 100% = full. 120% = bonus.
    """
    __tablename__ = "sales_targets"
    id              = Column(Integer, primary_key=True)
    agent_id        = Column(Integer, ForeignKey("users.id"), index=True)
    period_month    = Column(String, index=True)   # YYYY-MM
    deposit_target  = Column(Float, default=0)
    volume_target   = Column(Float, default=0)
    clients_target  = Column(Integer, default=0)
    ftd_target      = Column(Integer, default=0)
    # Actuals (updated each sync)
    deposit_actual  = Column(Float, default=0)
    volume_actual   = Column(Float, default=0)
    clients_actual  = Column(Integer, default=0)
    ftd_actual      = Column(Integer, default=0)
    achievement_pct = Column(Float, default=0)  # average of all targets
    commission_rate = Column(Float, default=0.3)  # 30% of markup
    commission_earned = Column(Float, default=0)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    updated_at      = Column(DateTime(timezone=True), onupdate=func.now())


class SalesCommission(Base):
    """Sales commission per deal — mirrors IBCommission."""
    __tablename__ = "sales_commissions"
    id              = Column(Integer, primary_key=True)
    agent_id        = Column(Integer, ForeignKey("users.id"), index=True)
    deal_id         = Column(BigInteger, ForeignKey("deals.deal_id"), index=True)
    login           = Column(Integer, index=True)
    symbol          = Column(String)
    symbol_category = Column(String)
    volume          = Column(Float, default=0)
    markup_profit   = Column(Float, default=0)
    commission_rate = Column(Float, default=0.3)
    commission_amount = Column(Float, default=0)
    deal_date       = Column(String, index=True)
    deal_month      = Column(String, index=True)
    status          = Column(String, default="pending", index=True)
    paid_at         = Column(DateTime(timezone=True))
    created_at      = Column(DateTime(timezone=True), server_default=func.now())


# ══════════════════════════════════════════════════════════════════════════
# 9. LOYALTY PROGRAM
# ══════════════════════════════════════════════════════════════════════════

class LoyaltyTier(Base):
    """
    5 tiers: Bronze → Silver → Gold → Platinum → VIP
    MY IDEA: Each tier has its own points-per-lot rate.
    New traders earn 3pts/lot. Gold earns 5pts/lot. VIP earns 8pts/lot.
    This rewards loyalty and encourages more trading.
    """
    __tablename__ = "loyalty_tiers"
    id                  = Column(Integer, primary_key=True)
    name                = Column(String, nullable=False)
    min_points          = Column(Integer, nullable=False)
    points_per_lot      = Column(Float, default=3.0)
    points_per_1000_dep = Column(Float, default=10.0)
    points_per_referral = Column(Integer, default=100)
    spread_discount_pct = Column(Float, default=0)
    benefits_description= Column(Text)
    color               = Column(String, default="#888")
    badge_icon          = Column(String)
    is_active           = Column(Boolean, default=True)


class LoyaltyTransaction(Base):
    """Every points earn/spend event."""
    __tablename__ = "loyalty_transactions"
    id            = Column(Integer, primary_key=True)
    client_id     = Column(Integer, ForeignKey("clients.id"), index=True)
    login         = Column(Integer, index=True)
    points        = Column(Integer, nullable=False)   # + earn | - spend
    reason        = Column(String, nullable=False, index=True)
    # trade | deposit | referral | registration | redemption | manual | expiry
    reference_id  = Column(String)     # deal_id, deposit_id, etc.
    balance_after = Column(Integer, default=0)
    notes         = Column(String)
    created_at    = Column(DateTime(timezone=True), server_default=func.now())


# ══════════════════════════════════════════════════════════════════════════
# 10. BONUS SYSTEM
# ══════════════════════════════════════════════════════════════════════════

class BonusCampaign(Base):
    """
    MY IDEA: Rules engine for bonuses.
    Each campaign has eligibility rules — country, group, min deposit, etc.
    System auto-checks all rules before granting bonus.
    Also stores duplicate check settings (block same IP/CID/payment).
    """
    __tablename__ = "bonus_campaigns"
    id              = Column(Integer, primary_key=True)
    name            = Column(String, nullable=False)
    bonus_type      = Column(String, nullable=False, index=True)
    # welcome | first_deposit | reload | seasonal | vip | referral
    amount          = Column(Float, nullable=False)
    amount_type     = Column(String, default="fixed")  # fixed | percentage
    max_amount      = Column(Float, default=0)
    min_deposit     = Column(Float, default=0)
    wagering_lots   = Column(Float, default=0)   # lots to trade before withdrawing
    expiry_days     = Column(Integer, default=30)
    # Eligibility rules
    eligible_groups   = Column(String, default="*")
    eligible_countries= Column(String, default="*")
    excluded_countries= Column(String, default="")
    # Duplicate detection rules
    block_same_ip     = Column(Boolean, default=True)
    block_same_cid    = Column(Boolean, default=True)
    block_same_payment= Column(Boolean, default=True)
    block_same_family = Column(Boolean, default=False)
    block_same_device = Column(Boolean, default=False)
    # Campaign timing
    start_date      = Column(String)
    end_date        = Column(String)
    max_per_client  = Column(Integer, default=1)
    max_total_grants= Column(Integer, default=0)   # 0 = unlimited
    total_granted   = Column(Integer, default=0)
    is_active       = Column(Boolean, default=True, index=True)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())


class ClientBonus(Base):
    """Active bonus per client with wagering progress."""
    __tablename__ = "client_bonuses"
    id              = Column(Integer, primary_key=True)
    client_id       = Column(Integer, ForeignKey("clients.id"), index=True)
    login           = Column(Integer, index=True)
    campaign_id     = Column(Integer, ForeignKey("bonus_campaigns.id"))
    bonus_type      = Column(String, nullable=False)
    amount          = Column(Float, nullable=False)
    lots_required   = Column(Float, default=0)
    lots_completed  = Column(Float, default=0)
    progress_pct    = Column(Float, default=0)
    status          = Column(String, default="pending", index=True)
    # pending | active | completed | expired | violated | cancelled
    activated_at    = Column(DateTime(timezone=True))
    expires_at      = Column(DateTime(timezone=True))
    completed_at    = Column(DateTime(timezone=True))
    violated_reason = Column(String)
    granted_by      = Column(Integer, ForeignKey("users.id"))
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    updated_at      = Column(DateTime(timezone=True), onupdate=func.now())


# ══════════════════════════════════════════════════════════════════════════
# 11. COPY TRADING
# ══════════════════════════════════════════════════════════════════════════

class CopyTradeRelation(Base):
    """
    MY IDEA: Track which accounts copy which master.
    Store performance stats so we can show copy trade leaderboard.
    """
    __tablename__ = "copy_trade_relations"
    id              = Column(Integer, primary_key=True)
    master_login    = Column(Integer, index=True, nullable=False)
    follower_login  = Column(Integer, index=True, nullable=False)
    copy_ratio      = Column(Float, default=1.0)   # 1.0 = 100% copy
    max_lot         = Column(Float, default=0)     # 0 = no limit
    status          = Column(String, default="active", index=True)
    started_at      = Column(DateTime(timezone=True), server_default=func.now())
    stopped_at      = Column(DateTime(timezone=True))


class CopyTradeMaster(Base):
    """Master account stats for copy trade leaderboard."""
    __tablename__ = "copy_trade_masters"
    id              = Column(Integer, primary_key=True)
    login           = Column(Integer, unique=True, index=True)
    display_name    = Column(String)
    total_followers = Column(Integer, default=0)
    total_aum       = Column(Float, default=0)    # Assets under management
    profit_30d      = Column(Float, default=0)
    profit_90d      = Column(Float, default=0)
    profit_1y       = Column(Float, default=0)
    win_rate        = Column(Float, default=0)
    max_drawdown    = Column(Float, default=0)
    sharpe_ratio    = Column(Float, default=0)
    is_public       = Column(Boolean, default=True)
    updated_at      = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# ══════════════════════════════════════════════════════════════════════════
# 12. CONTESTS
# ══════════════════════════════════════════════════════════════════════════

class Contest(Base):
    """Trading competitions."""
    __tablename__ = "contests"
    id              = Column(Integer, primary_key=True)
    name            = Column(String, nullable=False)
    contest_type    = Column(String, nullable=False)  # profit_pct | volume | profit_abs
    start_date      = Column(String, nullable=False)
    end_date        = Column(String, nullable=False)
    prize_pool      = Column(Float, default=0)
    prizes          = Column(Text)   # JSON: [{rank:1,amount:1000},{rank:2,amount:500}]
    min_deposit     = Column(Float, default=0)
    min_trades      = Column(Integer, default=0)
    eligible_groups = Column(String, default="*")
    status          = Column(String, default="upcoming", index=True)
    # upcoming | active | finished | cancelled
    created_at      = Column(DateTime(timezone=True), server_default=func.now())


class ContestEntry(Base):
    """Contest participants with live standings."""
    __tablename__ = "contest_entries"
    id          = Column(Integer, primary_key=True)
    contest_id  = Column(Integer, ForeignKey("contests.id"), index=True)
    login       = Column(Integer, index=True)
    client_id   = Column(Integer, ForeignKey("clients.id"))
    rank        = Column(Integer, default=0)
    score       = Column(Float, default=0)     # profit% or volume
    prize_won   = Column(Float, default=0)
    prize_paid  = Column(Boolean, default=False)
    joined_at   = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())


# ══════════════════════════════════════════════════════════════════════════
# 13. KYC & COMPLIANCE
# ══════════════════════════════════════════════════════════════════════════

class KYCDocument(Base):
    """Client identity documents."""
    __tablename__ = "kyc_documents"
    id              = Column(Integer, primary_key=True)
    client_id       = Column(Integer, ForeignKey("clients.id"), index=True)
    login           = Column(Integer, index=True)
    doc_type        = Column(String, nullable=False)
    # passport | national_id | drivers_license | proof_of_address
    # selfie | company_reg | bank_statement | source_of_funds
    file_url        = Column(String)
    file_name       = Column(String)
    status          = Column(String, default="pending", index=True)
    # pending | approved | rejected | expired
    rejection_reason= Column(String)
    expiry_date     = Column(String)
    verified_by     = Column(Integer, ForeignKey("users.id"))
    verified_at     = Column(DateTime(timezone=True))
    created_at      = Column(DateTime(timezone=True), server_default=func.now())


class ComplianceCheck(Base):
    """
    MY IDEA: Log every compliance check (PEP, sanctions, etc.)
    with result and timestamp. Audit trail for regulators.
    """
    __tablename__ = "compliance_checks"
    id          = Column(Integer, primary_key=True)
    client_id   = Column(Integer, ForeignKey("clients.id"), index=True)
    check_type  = Column(String, nullable=False)
    # pep | sanctions | duplicate | source_of_funds | aml
    result      = Column(String, nullable=False)  # pass | fail | review
    details     = Column(Text)
    checked_by  = Column(Integer, ForeignKey("users.id"))
    created_at  = Column(DateTime(timezone=True), server_default=func.now())


# ══════════════════════════════════════════════════════════════════════════
# 14. SUPPORT & COMMUNICATIONS
# ══════════════════════════════════════════════════════════════════════════

class SupportTicket(Base):
    """Customer support tickets."""
    __tablename__ = "support_tickets"
    id          = Column(Integer, primary_key=True)
    ticket_ref  = Column(String, unique=True, index=True)  # TKT-000001
    client_id   = Column(Integer, ForeignKey("clients.id"), index=True)
    login       = Column(Integer, index=True)
    category    = Column(String, index=True)
    # deposit | withdrawal | account | technical | kyc | trading | bonus | other
    subject     = Column(String, nullable=False)
    priority    = Column(String, default="normal", index=True)
    # urgent | high | normal | low
    status      = Column(String, default="open", index=True)
    # open | in_progress | waiting | resolved | closed
    assigned_to = Column(Integer, ForeignKey("users.id"), index=True)
    sla_due_at  = Column(DateTime(timezone=True))
    resolved_at = Column(DateTime(timezone=True))
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())


class TicketMessage(Base):
    """Messages in a support ticket."""
    __tablename__ = "ticket_messages"
    id          = Column(Integer, primary_key=True)
    ticket_id   = Column(Integer, ForeignKey("support_tickets.id"), index=True)
    sender_type = Column(String, nullable=False)  # client | agent | system
    sender_id   = Column(Integer)
    message     = Column(Text, nullable=False)
    is_internal = Column(Boolean, default=False)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())


class CallAction(Base):
    """Sales call outcomes."""
    __tablename__ = "call_actions"
    id                = Column(Integer, primary_key=True)
    login             = Column(Integer, index=True, nullable=False)
    agent_id          = Column(Integer, ForeignKey("users.id"))
    action            = Column(String, nullable=False, index=True)
    # connected_done | no_answer | call_later | not_interested
    note              = Column(Text)
    call_later_at     = Column(DateTime(timezone=True))
    passed_to_manager = Column(Boolean, default=False)
    passed_to_agent_id= Column(Integer, ForeignKey("users.id"))
    duration_seconds  = Column(Integer, default=0)  # MY IDEA: track call duration
    created_at        = Column(DateTime(timezone=True), server_default=func.now())


class ClientComment(Base):
    """Comments by any department."""
    __tablename__ = "client_comments"
    id          = Column(Integer, primary_key=True)
    login       = Column(Integer, index=True, nullable=False)
    agent_id    = Column(Integer, ForeignKey("users.id"))
    department  = Column(String, default="Sales", index=True)
    # Sales | Compliance | Finance | Support | Verification | Backoffice | IB
    comment     = Column(Text, nullable=False)
    is_internal = Column(Boolean, default=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())


# ══════════════════════════════════════════════════════════════════════════
# 15. EMAIL AUTOMATION
# ══════════════════════════════════════════════════════════════════════════

class EmailTemplate(Base):
    """
    MY IDEA: Store email templates in DB so admin can edit without code.
    Templates in both Arabic and English.
    """
    __tablename__ = "email_templates"
    id          = Column(Integer, primary_key=True)
    name        = Column(String, nullable=False)
    category    = Column(String, index=True)
    # kyc | deposit | withdrawal | welcome | inactive | margin | bonus | custom
    subject_en  = Column(String, nullable=False)
    subject_ar  = Column(String)
    body_en     = Column(Text, nullable=False)
    body_ar     = Column(Text)
    is_active   = Column(Boolean, default=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())


class EmailLog(Base):
    """Every email sent — for compliance and tracking."""
    __tablename__ = "email_logs"
    id          = Column(Integer, primary_key=True)
    client_id   = Column(Integer, ForeignKey("clients.id"), index=True)
    login       = Column(Integer, index=True)
    agent_id    = Column(Integer, ForeignKey("users.id"))
    template_id = Column(Integer, ForeignKey("email_templates.id"))
    to_email    = Column(String)
    subject     = Column(String)
    body        = Column(Text)
    status      = Column(String, default="sent")  # sent | failed | bounced
    sent_at     = Column(DateTime(timezone=True), server_default=func.now())


# ══════════════════════════════════════════════════════════════════════════
# 16. DEPOSITS & WITHDRAWALS (financial queue)
# ══════════════════════════════════════════════════════════════════════════

class Transaction(Base):
    """
    MY IDEA: Separate transactions table for finance team.
    Synced from MT5 deals but enriched with payment method,
    PSP reference, approval workflow.
    """
    __tablename__ = "transactions"
    id              = Column(Integer, primary_key=True)
    deal_id         = Column(BigInteger, index=True)
    login           = Column(Integer, index=True)
    client_id       = Column(Integer, ForeignKey("clients.id"), index=True)
    tx_type         = Column(String, nullable=False, index=True)  # deposit | withdrawal
    amount          = Column(Float, nullable=False)
    currency        = Column(String, default="USD")
    method          = Column(String, index=True)
    # bank_wire | credit_card | crypto_usdt | crypto_btc | local | internal
    psp_reference   = Column(String, index=True)  # payment gateway ref
    status          = Column(String, default="pending", index=True)
    # pending | approved | rejected | processing | failed | cancelled
    approved_by     = Column(Integer, ForeignKey("users.id"))
    approved_at     = Column(DateTime(timezone=True))
    rejection_reason= Column(String)
    notes           = Column(Text)
    tx_date         = Column(String, index=True)  # YYYY-MM-DD
    tx_month        = Column(String, index=True)  # YYYY-MM
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    updated_at      = Column(DateTime(timezone=True), onupdate=func.now())


# ══════════════════════════════════════════════════════════════════════════
# 17. CRM SETTINGS & SYSTEM
# ══════════════════════════════════════════════════════════════════════════

class ClientAssignment(Base):
    """Which sales agent owns which client."""
    __tablename__ = "client_assignments"
    id          = Column(Integer, primary_key=True)
    login       = Column(Integer, index=True, nullable=False)
    agent_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    assigned_at = Column(DateTime(timezone=True), server_default=func.now())
    assigned_by = Column(Integer, ForeignKey("users.id"))


class ScoreSettings(Base):
    """Configurable scoring weights — admin can change in CRM."""
    __tablename__ = "score_settings"
    id                           = Column(Integer, primary_key=True)
    margin_call_score            = Column(Integer, default=40)
    deposit_rejected_score       = Column(Integer, default=35)
    margin_below_threshold_score = Column(Integer, default=30)
    margin_threshold             = Column(Float,   default=80.0)
    withdrawal_pending_score     = Column(Integer, default=25)
    no_deposit_days_score        = Column(Integer, default=25)
    no_deposit_days_threshold    = Column(Integer, default=15)
    active_no_deposit_score      = Column(Integer, default=22)
    high_balance_inactive_score  = Column(Integer, default=20)
    high_balance_threshold       = Column(Float,   default=500.0)
    low_equity_score             = Column(Integer, default=20)
    low_equity_threshold         = Column(Float,   default=70.0)
    never_deposited_score        = Column(Integer, default=18)
    large_withdrawal_score       = Column(Integer, default=15)
    large_withdrawal_threshold   = Column(Float,   default=500.0)
    kyc_pending_score            = Column(Integer, default=12)
    long_inactivity_score        = Column(Integer, default=10)
    long_inactivity_days         = Column(Integer, default=60)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class SyncLog(Base):
    """MT5 sync history."""
    __tablename__ = "sync_log"
    id          = Column(Integer, primary_key=True)
    sync_type   = Column(String, default="full")
    records     = Column(Integer, default=0)
    status      = Column(String, default="ok")
    message     = Column(Text)
    duration_sec= Column(Integer, default=0)
    started_at  = Column(DateTime(timezone=True), server_default=func.now())
    finished_at = Column(DateTime(timezone=True))


class AuditLog(Base):
    """
    MY IDEA: Log every CRM action — who did what, when, to whom.
    Required for regulators. Also helps debug issues.
    """
    __tablename__ = "audit_log"
    id          = Column(Integer, primary_key=True)
    user_id     = Column(Integer, ForeignKey("users.id"), index=True)
    action      = Column(String, nullable=False, index=True)
    entity_type = Column(String, index=True)   # client | ib | bonus | user | setting
    entity_id   = Column(Integer)
    old_value   = Column(Text)
    new_value   = Column(Text)
    ip_address  = Column(String)
    user_agent  = Column(String)
    created_at  = Column(DateTime(timezone=True), server_default=func.now(), index=True)


class Notification(Base):
    """
    MY IDEA: In-app notifications for CRM staff.
    "Client X margin call", "Withdrawal #Y needs approval", etc.
    """
    __tablename__ = "notifications"
    id          = Column(Integer, primary_key=True)
    user_id     = Column(Integer, ForeignKey("users.id"), index=True)
    title       = Column(String, nullable=False)
    message     = Column(Text)
    type        = Column(String, index=True)
    # margin_call | withdrawal | kyc | risk | ib | system
    link        = Column(String)    # where to navigate when clicked
    is_read     = Column(Boolean, default=False, index=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now(), index=True)


# ══════════════════════════════════════════════════════════════════════════
# 18. STAGING TABLE (Google AI recommendation)
# Raw MT5 data lands here first — ultra-fast insert
# Background worker then distributes to proper tables
# ══════════════════════════════════════════════════════════════════════════

class MT5RawData(Base):
    """
    Staging table — receives raw MT5 data every 30 seconds.
    Background worker reads this and distributes to other tables.
    Fast because: no joins, no foreign keys, no complex logic.
    Just dump and process.
    """
    __tablename__ = "mt5_raw_data"
    id           = Column(Integer, primary_key=True)
    data_type    = Column(String, index=True, nullable=False)
    # account | deal | position | journal
    login        = Column(Integer, index=True)
    raw_json     = Column(Text, nullable=False)   # full MT5 record as JSON
    processed    = Column(Boolean, default=False, index=True)
    processed_at = Column(DateTime(timezone=True))
    error        = Column(String)   # if processing failed, reason here
    received_at  = Column(DateTime(timezone=True), server_default=func.now(), index=True)


class LiveUpdate(Base):
    """
    WebSocket queue — changes waiting to be pushed to browser.
    Worker writes here → WebSocket reads and broadcasts → deleted.
    This makes balances, margin calls update live on screen.
    """
    __tablename__ = "live_updates"
    id          = Column(Integer, primary_key=True)
    update_type = Column(String, index=True, nullable=False)
    # balance_change | margin_call | new_deposit | new_withdrawal
    # kyc_approved | flag_raised | new_client
    login       = Column(Integer, index=True)
    payload     = Column(Text)   # JSON data to push
    sent        = Column(Boolean, default=False, index=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())


class DailySnapshot(Base):
    """
    MY IDEA + Google AI: Pre-computed daily summary per client.
    Instead of summing 13M deals for every report,
    worker computes daily totals at midnight.
    Reports then just sum these snapshots = lightning fast.

    Example: "Show me deposits for last 6 months"
    Without snapshots: scan 13M deals rows
    With snapshots: scan 180 snapshot rows → 72,000x faster
    """
    __tablename__ = "daily_snapshots"
    __table_args__ = (
        UniqueConstraint("login", "snapshot_date"),
        Index("ix_snapshot_date_type", "snapshot_date", "data_type"),
    )
    id            = Column(Integer, primary_key=True)
    login         = Column(Integer, index=True, nullable=False)
    client_id     = Column(Integer, ForeignKey("clients.id"), index=True)
    snapshot_date = Column(String, index=True, nullable=False)   # YYYY-MM-DD
    data_type     = Column(String, index=True, nullable=False)
    # financial | trading | activity
    # Financial snapshot
    balance       = Column(Float, default=0)
    equity        = Column(Float, default=0)
    deposits      = Column(Float, default=0)
    withdrawals   = Column(Float, default=0)
    # Trading snapshot
    volume_lots   = Column(Float, default=0)
    trades_count  = Column(Integer, default=0)
    profit        = Column(Float, default=0)
    markup_revenue= Column(Float, default=0)
    # Activity snapshot
    logins_count  = Column(Integer, default=0)
    created_at    = Column(DateTime(timezone=True), server_default=func.now())

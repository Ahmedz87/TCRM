"""
SINGLE SOURCE OF TRUTH for the chat bot's feature knowledge — whenever a feature
changes, update its article here.

This module backs the TNFX client-facing assistant (chat_router.py). It holds one
detailed, plain-language, client-facing ARTICLE per feature topic, plus helpers to
(a) advertise the full topic list to the model (article_index) and (b) inject the
full text of just the on-topic article(s) for a given question (relevant_articles).

Honesty rules baked into these articles (see project SAFETY RULES):
  - Deposits/withdrawals and copy-trade execution are SIMULATION / DRY-RUN in this
    build. Articles describe the CLIENT-FACING behaviour and never promise real fund
    movement or guarantee profit.
  - Real, code-known numbers are stated (e.g. $50 / $100 min withdrawal, 50%/20%
    deposit-bonus tiers, $1,000 tier-1 cap, $5,000 lifetime bonus cap, 0.01 min lot,
    50 max lot, 150% margin floor, loyalty tier rates). Desk-config specifics that are
    NOT fixed in code (per-country payment min/max, exact payout time, exact fee for a
    given provider) are described as "shown in the portal at the time / confirmed then",
    never fabricated.

Topic keys: copy_trading, ib, loyalty, bonus, autochartist, vps, deposit, withdraw.
"""

# ─────────────────────────────────────────────────────────────────────────────
# ARTICLES — the knowledge base. Each value is the full client-facing answer.
# ─────────────────────────────────────────────────────────────────────────────
ARTICLES = {

    "registration": """OPENING AN ACCOUNT — registration & verification steps

WHO THIS IS FOR
A brand-new client who wants to open a TNFX trading account. (If you already have an
account and want an EXTRA trading account, that's done from inside the portal — ask your
account manager / use the "New account" option in the portal, not the steps below.)

THE STEPS
1) Start the registration form (on the TNFX website / the sign-up page) and enter your
   personal details: full name EXACTLY as it appears on your ID, email address, mobile
   phone number (with country code), and country of residence.
2) Confirm your EMAIL — we send a verification link/code to the email you entered; open it
   and confirm.
3) Confirm your PHONE — we send a one-time code (OTP) by SMS/WhatsApp; enter it to verify
   the number.
4) Choose your account: the trading PLATFORM (MT4 or MT5) and the account TYPE (e.g.
   Standard, Zero, etc. — each has its own minimum first deposit). You can ask the bot
   "what account types do you have" for the differences.
5) Upload your KYC documents: a clear photo/scan of your government ID — FRONT and BACK —
   and a PROOF OF RESIDENCE (e.g. a recent utility bill or bank statement) — FRONT and BACK.
   Make sure the name on the documents matches the name you registered with.
6) Submit.

VERIFICATION TIMING
Verification is IMMEDIATE/automatic the moment ALL requirements are complete (email +
phone confirmed AND ID front/back AND proof of residence front/back all uploaded and
matching). There is no hours/days waiting period. If anything is missing or unclear, it's
flagged to you right away (in the portal and by email) so you can re-upload that one item.

AFTER YOU'RE VERIFIED
Your trading account LOGIN number and your passwords (a trading/main password and an
investor/read-only password) are sent to your registered email. Use them to:
• log in to the Client Portal (your dashboard, deposits, withdrawals, copy trading, etc.), and
• log in to the MT4/MT5 terminal on desktop or the mobile app (ask the bot for the
  step-by-step login for your device — computer, iPhone or Android — server name TNFX-Live).

FUNDING & TRADING
Once verified, fund the account from the portal's Deposit section (see the deposit topic
for methods, minimums and the deposit bonus), then you can start trading on MT4/MT5.

If any step here doesn't match what you actually see on screen, tell us the exact step and
we'll correct it — the team keeps these instructions in sync with the live sign-up flow.""",

    "copy_trading": """COPY TRADING — follow a pro and copy their trades automatically

WHAT IT IS
Copy trading lets you automatically mirror the trades of an experienced "signal
provider" (a strategy / trader you choose). When they open or close a trade, the
system places a sized-down (or sized-up) version of that same trade on your account,
so you ride their strategy without analysing the market yourself. You stay in full
control: you choose who to follow, how much to allocate, and you can stop any time.

FINDING & CHOOSING A PROVIDER (the leaderboard)
Open the Copy Trading page in the portal → the "Discover" tab. You'll see a leaderboard
of providers ranked by REAL performance stats — total return %, 30-day return, win rate,
maximum drawdown (the deepest dip), profit factor, average hold time, number of trades,
how many followers they have, and a risk level. You can sort by return, win rate,
followers, lowest drawdown or newest, and filter by strategy (scalping, intraday, swing,
news, grid, conservative…), by market (gold, EURUSD, FX majors, indices, multi-asset),
by maximum risk level, or search by name. Tap a provider to open their profile: their
equity curve, recent trades, who's copying them, and their minimum investment.

HOW TO FOLLOW (the three settings)
On a provider you press Follow / Copy and set three things:
1) ALLOCATION — how much money (in $) you commit to copying this provider. It must be at
   least that provider's minimum investment (shown on their card). This is what your
   trade sizes are scaled from in proportional mode.
2) COPY MODE — how your trade size is worked out from the provider's trade size:
   • Proportional (a partial / scaled copy): your trade size scales by your share of the
     provider's capital — roughly your_lots = provider_lots × (your allocation ÷ provider
     capital) × your multiplier. Smaller allocation = smaller, safer copies. This is the
     usual, recommended mode.
   • Mirror (1:1): you copy the provider's exact lot size, times your multiplier. The
     provider trades 1.00 lot, you trade 1.00 lot (at 1x). Bigger risk — only sensible if
     your balance is similar to theirs.
   • Fixed: ignore the provider's size completely and trade a set lot size every time —
     here the multiplier value acts as that fixed lot (e.g. fixed + 0.10 = always 0.10 lot).
3) MULTIPLIER — a dial on top of the mode. 1x means "as calculated", 2x doubles every copied
   trade, 0.5x halves it. So "2x" means each copied position is twice the size it would
   otherwise be; "1x" means no extra scaling.
You can also choose whether to copy the provider's CURRENTLY-OPEN trades when you join, or
only brand-new trades from now on.

RISK CONTROLS
Every copied order is clamped to a minimum of 0.01 lot and a hard maximum of 50 lots, so a
single trade can never blow out of proportion. When you set up the follow you can also set a
max-lot limit and a stop-equity level (a floor at which copying stops to protect you). Lower
allocation, proportional mode and a multiplier of 1x or below are the safest combination.

HOW YOUR PROFIT / LOSS IS CALCULATED
Your P/L is the provider's result scaled to YOUR copied size. For each trade we take the
provider's profit-per-lot and multiply it by the lots you actually copied, so if you copied
at half their size you get roughly half their result — wins and losses both. Your running
copied P/L per provider is shown in the "My Copies" tab.

UNFOLLOWING — what happens to open positions
You can stop copying any time from "My Copies" (Unfollow / Stop). Unfollowing STOPS new
trades being copied to you from that provider — you simply won't receive their future trades.
While you stay following, the provider's opens AND closes are mirrored to you, so a position
opened by copying is normally closed when the provider closes it. Any position already open
on your account stays under your control as a normal trade; you manage or close it yourself
in your platform. So: keep following = the provider's trades (including their closes) keep
flowing to you; unfollow = the stream stops and anything still open is yours to manage.

IMPORTANT (current build): copy trading is in SIMULATION / preview right now. Following a
provider records your subscription and shows the copied results, but live automatic order
placement onto your MT account is being switched on in a controlled, gated rollout — it does
not yet move real positions. Providers are ranked on real statistics, and as always trading
carries risk: past performance doesn't guarantee future results, so allocate sensibly.""",

    "ib": """IB / PARTNER PROGRAM — refer others and earn CASH commission

WHAT IT IS
The Introducing Broker (IB) program is a PARTNERSHIP. As an IB you refer OTHER people to
TNFX, and you earn real CASH commission on the trading VOLUME those referred clients
generate. This is money paid to you as a partner — it is completely different from the
loyalty / TN-Points program (which rewards your own trading with points, not cash).

HOW YOU EARN
Commission is paid per traded LOT of your referred clients. FX pairs and gold (XAU) lots
earn the headline per-lot rate; other instruments earn a smaller per-trade amount. Your
per-lot rate scales with your IB LEVEL/tier — the higher your level, the more you earn per
lot. Levels run from Bronze up through to Master, and your level is set by the partnership
desk based on your activity. The more your referred clients trade, the more you earn.

TOOLS YOU GET
You get a referral link to bring in new clients and a partner dashboard to track your
referred clients, their trading volume, and the commission you've earned over any period.

HOW TO JOIN OR CHECK YOUR EXACT RATE
The exact per-lot rates for each level and how to be upgraded are set by the partnership
desk. To become an IB, or to confirm your exact rate and level, your account manager / the
partnership desk sets that up for you — but the way it works (cash per lot, scaling by level,
referral link + dashboard) is exactly as described above.

KEY POINT: IB = a partner earning CASH from the people they refer. Don't confuse it with
loyalty points, which you earn for your OWN trading and redeem for rewards.""",

    "loyalty": """LOYALTY / REWARDS — the TN-Points program (your own activity)

WHAT IT IS
TN-Points is a rewards program for YOU. You collect points just for being active with us,
then spend them on rewards. It is NOT cash and has nothing to do with the IB partner
program. You can see your points, tier and streak on the portal "Rewards" page.

HOW YOU EARN POINTS
You earn points from your own closed, eligible trades — points = lots traded × your tier
rate. Eligible trades are FX pairs and gold (XAUUSD); points roll up across all your
accounts. Your tier rate is: Bronze 4, Silver 5, Gold 6, Platinum 7 points per lot — so the
higher your tier, the more points each lot earns. Staying active also builds a daily TRADING
STREAK that drives your tier.

TIERS, STREAKS, PROMOTION & DEMOTION
You move up tiers by keeping a streak of consecutive trading days (weekends are skipped):
Bronze→Silver and Silver→Gold need a 30-day streak, Gold→Platinum needs a 40-day streak.
Higher tiers earn points faster and can unlock better perks. If you stop trading for 30 days
you drop one tier (Bronze is the floor). The program also gives "pass days": trading
consistently banks a few passes that cover the odd missed day so a short gap doesn't break
your streak.

REDEEMING & REFER-A-FRIEND
Spend your points on rewards in the Rewards section of the portal — pick a reward and redeem
it with your points balance (the cost in points is shown on each reward). There's also a
refer-a-friend option inside Rewards that gives you bonus POINTS (not cash) when a friend you
invite joins.

KEY POINT: loyalty points are a reward you collect for your OWN activity and spend on
rewards — they are not money, and they are separate from the IB program.""",

    "bonus": """BONUSES — welcome bonus, deposit bonus, special offers

OVERVIEW
TNFX offers a one-time WELCOME bonus, a tiered DEPOSIT bonus, a BIRTHDAY bonus, and occasional
limited-time SPECIAL offers. Your live, personal figures and eligibility are always shown on the
portal Bonus page — use those exact numbers. It's not available in a few countries (currently
India, Pakistan, Egypt), and if your country is excluded the portal will say so.
IMPORTANT: bonuses are ONLY supported on the STANDARD account — the Zero, Cent, VIP and Fix
accounts do NOT receive any bonus. Any bonus is credited to your Standard account.

HOW A BONUS WORKS (important)
A bonus is trading credit, NOT withdrawable cash. You cannot withdraw the bonus amount itself —
you TRADE with it and withdraw the PROFITS you earn. (It is NOT true that you "must trade a
certain number of lots before you can withdraw the bonus" — the bonus itself is never
withdrawable; only the profit from it is.) The minimum withdrawal of bonus PROFITS (welcome and
birthday bonus) is $100 — once your profit reaches $100 or more you can withdraw at least $100.

WELCOME BONUS
A one-time welcome bonus for a newly-verified client. To unlock it you need: full KYC
verification, to have logged into your trading account at least once, and a brand-new
device/network that isn't already linked to another account. It is granted to only ONE person
per family — even on a different internet/network connection, only one family member receives it
(not every family member). The Bonus page shows your exact state — ready to claim, needs KYC,
waiting on KYC review, "log in to activate", already claimed, or not eligible (device/network
already linked).

BIRTHDAY BONUS
A $100 birthday bonus credited to your STANDARD account on your birthday (the same day).
Conditions: (1) you must have deposited at least $300 in total (one deposit or several combined);
(2) you must have traded at least 1.00 lot on FOREX PAIRS and METALS ONLY — trades on oil,
stocks/shares, indices, or crypto do NOT count toward this. As with any bonus, the $100 isn't
withdrawable itself; you trade with it and withdraw the profit (min $100 profit to withdraw).

DEPOSIT BONUS (tiered)
You earn a percentage bonus on what you deposit: 50% on the first $1,000 of deposits, then
20% on every dollar above that. There's a lifetime cap of $5,000 of total deposit bonus. The
Bonus page shows how much of each tier and of the lifetime cap you still have available, and
the deposit screen previews exactly what a given deposit would add before you confirm.

SPECIAL OFFERS
From time to time there are limited-time special offers (a higher percentage, up to a cap,
with a minimum deposit and an end date). When one is running and you qualify it shows on your
Bonus page and takes precedence over the standard deposit tiers for that deposit; each special
offer can be used once per client.

WITHDRAWING WITH A BONUS — proportional clawback & margin guard
Bonus credit isn't immediately withdrawable cash: if you withdraw, the bonus is clawed back in
proportion to how much of your balance you take out (withdraw 30% of your balance → about 30%
of your bonus credit is removed). Withdrawals are also checked against a 150% margin-level
guard so a withdrawal can't push an account with open trades into a margin problem. The portal
shows the clawback amount before you confirm.

Exact running amounts, your eligibility and any active special offer are always the live
figures on your Bonus page — those are the numbers to trust. Don't expect a guaranteed amount
beyond what the page shows.""",

    "autochartist": """AUTOCHARTIST — automated market analysis, FREE with TNFX

WHAT IT IS
Autochartist is a world-leading AUTOMATED market-analysis engine that scans the markets 24/5
and hands you ready trading opportunities — chart patterns, key levels and forecasts — without
you having to analyse anything manually. It surfaces several setups a day across instruments,
so you never run out of ideas, and it helps you "read the market": what's trending, where the
key levels are, and how volatile a symbol is right now.

THE BIG PERK: IT'S FREE
Most brokers charge a monthly subscription for Autochartist — at TNFX it's included free. It
works on forex, gold/metals, indices and commodities, inside MT4 & MT5 and on the web.

WHAT IT GIVES YOU (models)
• Chart Patterns — triangles, channels, wedges, flags, head & shoulders, double tops/bottoms,
  rectangles, both forming and completed, each with a quality/probability rating.
• Fibonacci / harmonic patterns — Gartley, Butterfly, Bat, Crab, ABCD with entry/target zones.
• Key Levels — live support/resistance and Fibonacci retracement/extension levels.
• Volatility Analysis — forecasts a symbol's expected range and suggests data-driven stop-loss
  and take-profit distances.
• Trend & breakout detection, power statistics, scheduled market reports, news-volatility
  highlights, and real-time alerts when a setup forms on your watched symbols.

HOW TO GET IT
Easiest: open the "Autochartist" page right here in the TNFX portal — nothing to install. In
MT4/MT5: install the TNFX Autochartist plugin, close and reopen the platform, then in the
Navigator panel open Expert Advisors, drag "Autochartist" onto a chart, allow DLL imports /
algorithmic trading, and the panel docks in. If you can't find the installer, support can send
the file and help you set it up.

HOW TO USE IT
Open the panel, pick your symbols, and it lists opportunities with a quality/probability score.
Click one to see the pattern, suggested direction and key levels; use Volatility Analysis to
set sensible stops and targets, and turn on alerts. Treat the setups as ideas to confirm with
your own judgement — they're high-quality starting points, not guaranteed trades (trading
carries risk).""",

    "vps": """VPS / TRADING SERVER — keeping your strategy running 24/5

WHAT A VPS IS
A VPS (Virtual Private Server) is an always-on remote computer that runs your MT4/MT5 and any
automated strategies (Expert Advisors / copy trading) around the clock, even when your own PC
is off or your internet drops. It gives a fast, stable connection to the trading servers with
very low latency, which matters for EAs, scalping and copy trading where every second counts.

WHY YOU MIGHT WANT ONE
• Your trades/EAs keep running 24/5 without your computer being on.
• Lower latency and a more reliable link to the market.
• No worry about home power cuts or internet drops interrupting open strategies.

HOW TO GET ONE AT TNFX
Whether a hosted VPS is offered to you, on what terms (some brokers include it free above a
certain balance/volume, others charge a small monthly fee), and the setup steps are arranged
through your account manager / support, who'll confirm the current eligibility and any cost and
help you connect your platform to it. I can explain how a VPS works and whether it would help
your style of trading — for the exact current offer and to switch it on, support will set it up
with you.""",

    "deposit": """DEPOSITS — funding your account

HOW IT WORKS
You fund from the portal: choose a payment method, enter the amount, and confirm. TNFX is built
around fast, automatic deposits — funds are designed to reach your trading account quickly and
automatically once the payment goes through. Funding methods include cards, bank wire/transfer,
e-wallets and local payment providers (for example Qi Card and others); which methods and which
currencies you see depends on your country, and the available options and any limits are shown
on the deposit screen at the time.

DEPOSIT BONUS ON TOP
A qualifying deposit can automatically earn a deposit bonus — 50% on your first $1,000 of
deposits, then 20% above that (lifetime bonus cap $5,000), or a better special offer if one is
running for you. The deposit screen previews exactly how much bonus a given amount would add
before you confirm. (See the bonus article for the full rules.)

GOOD TO KNOW
The exact minimum/maximum per method and the processing time depend on the payment provider and
your region — those are shown to you on the deposit screen, so go by what the portal displays at
the moment you deposit. In this build deposits are processed in SIMULATION (the request and any
bonus are recorded), so it doesn't yet take a real charge — but the client-facing flow and the
bonus you'd receive are exactly as described.""",

    "withdraw": """WITHDRAWALS — taking your money out

HOW IT WORKS
Request a withdrawal from the portal: pick the method, enter the amount, and submit. TNFX is
built for fast, automatic withdrawals — money is designed to go back to your payment method
quickly. Withdrawals return to the method you funded with where possible.

MINIMUM WITHDRAWAL
The minimum withdrawal is $50 if you have made a deposit before. If you've NEVER deposited, the
minimum is $100. (Always $50 for a client who has deposited — never $10.)

THINGS THAT ARE CHECKED
• Amount vs your balance — you can withdraw up to your available balance.
• Margin-level guard — if you have open trades, a withdrawal can't drop your margin level below
  150%; if it would, the portal tells you the most you can take out, or to close some trades first.
• Bonus clawback — if you hold bonus credit, withdrawing removes bonus in proportion to the share
  of your balance you take out (withdraw 30% of balance → about 30% of bonus credit is removed).
  The portal shows the clawback amount before you confirm.

GOOD TO KNOW
Exact payout times and any per-method/per-country limits depend on the payment provider and are
shown at the time you withdraw — go by what the portal displays. In this build withdrawals are
processed in SIMULATION (the request is recorded for review and the bonus clawback is applied),
so it doesn't yet move real funds — but the rules, minimums and checks above are exactly what
applies.""",
}


# ─────────────────────────────────────────────────────────────────────────────
# KEYWORD MAP — question text → topic(s). Lower-case substrings (EN + Arabic).
# ─────────────────────────────────────────────────────────────────────────────
KEYWORDS = {
    "registration": [
        "register", "registration", "sign up", "signup", "sign-up", "open account",
        "open an account", "opening an account", "create account", "create an account",
        "new account", "how do i join", "how to join", "get started", "onboard",
        "كيف اسجل", "تسجيل", "افتح حساب", "فتح حساب", "انشاء حساب", "إنشاء حساب",
        "حساب جديد", "كيف افتح", "تفعيل الحساب", "توثيق الحساب",
    ],
    "copy_trading": [
        "copy trad", "copytrad", "copy trade", "copy a trade", "copier", "signal provider",
        "follow a trader", "following a trader", "mirror trad", "multiplier", "allocation",
        "proportional", "unfollow", "my copies", "leaderboard", "نسخ", "نسخ الصفقات",
        "تداول النسخ", "كوبي", "متابعة متداول", "اتابع متداول",
    ],
    "ib": [
        "ib ", " ib", "introduc", "partner", "referr", "refer a", "refer ", "commission",
        "affiliate", "rebate", "شريك", "شراكة", "عمول", "احال", "إحال", "تسويق", "اي بي",
    ],
    "loyalty": [
        "loyal", "reward", "tn-point", "tn point", "tn-points", "tnpoint", "points", "tier",
        "streak", "redeem", "ولاء", "نقاط", "مكاف", "نقطة", "ريوارد", "استبدال",
    ],
    "bonus": [
        "bonus", "welcome bonus", "deposit bonus", "special offer", "promo", "clawback",
        "بونص", "مكافأة", "هدية", "عرض", "عروض", "ترحيب",
    ],
    "autochartist": [
        "autochartist", "auto chartist", "chartist", "اوتوشارت", "اوتو شارت", "اوتوتشارت",
        "تشارتست", "أوتوشارت", "signals", "اشارات", "إشارات", "patterns", "نماذج", "شارت",
    ],
    "vps": [
        "vps", "virtual private server", "virtual server", "hosting", "host my", "always on",
        "في بي اس", "سيرفر", "خادم",
    ],
    "deposit": [
        "deposit", "fund", "funding", "top up", "top-up", "add money", "pay in", "qi card",
        "ايداع", "إيداع", "اودع", "أودع", "شحن", "تمويل",
    ],
    "withdraw": [
        "withdraw", "withdrawal", "cash out", "cashout", "payout", "take out", "pull out",
        "سحب", "اسحب", "أسحب", "اسحب فلوس", "اسحب رصيد",
    ],
}

# one-line summary per topic for the always-present index
_INDEX_LINES = {
    "registration": "registration — how to OPEN a new account: details, email+phone verification, platform/type, ID + proof-of-residence upload, immediate verification, then login credentials by email.",
    "copy_trading": "copy_trading — follow a pro trader and auto-copy their trades (allocation, copy mode, multiplier, unfollow, P/L).",
    "ib":           "ib — IB/partner program: refer others, earn CASH commission per lot, IB levels, referral link & dashboard.",
    "loyalty":      "loyalty — TN-Points rewards for your OWN trading: earn points, tiers/streaks, redeem rewards, refer-a-friend (points).",
    "bonus":        "bonus — welcome bonus, tiered deposit bonus (50%/20%), special offers, withdrawal clawback & margin guard.",
    "autochartist": "autochartist — free automated market-analysis tool: patterns, key levels, volatility, alerts; how to install/use.",
    "vps":          "vps — always-on virtual server to run MT4/MT5 & strategies 24/5; how it works and how to get one.",
    "deposit":      "deposit — how to fund the account, methods, deposit bonus, limits shown in portal (simulation in this build).",
    "withdraw":     "withdraw — how to withdraw, $50/$100 minimums, margin guard, bonus clawback (simulation in this build).",
}


def article_index() -> str:
    """A short one-line-per-topic index. ALWAYS injected so the bot knows it can
    fully answer these topics and must not deflect."""
    lines = ["KNOWLEDGE BASE — you can FULLY answer any of these topics from the articles "
             "(never deflect an information question to the account manager):"]
    for key in ARTICLES:
        lines.append("- " + _INDEX_LINES.get(key, key))
    return "\n".join(lines)


def relevant_articles(question_text: str) -> str:
    """Return the full text of the topic(s) whose keywords match the question.
    Returns '' if nothing matches (so we don't bloat the prompt)."""
    t = (question_text or "").lower()
    if not t:
        return ""
    hits = []
    for topic, kws in KEYWORDS.items():
        if any(kw in t for kw in kws):
            hits.append(topic)
    if not hits:
        return ""
    # cap at 2 topics to keep the prompt bounded; preserve ARTICLES order
    ordered = [k for k in ARTICLES if k in hits][:2]
    out = []
    for topic in ordered:
        out.append("=== KB ARTICLE: " + topic + " ===\n" + ARTICLES[topic])
    return "\n\n".join(out)

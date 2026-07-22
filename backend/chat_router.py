"""
Client-facing AI assistant (live chat bot) — powered by the Claude API.

Security model: a CLIENT token can only ever read ITS OWN account. The login is
taken from the JWT (user_type='client'), never from the request body, so a client
cannot ask the bot about anyone else's account. Staff may pass a login to inspect.

The bot is grounded in:
  - the authenticated client's live account context (financials, KYC, loyalty,
    pending tx, payment methods, margin, open & recent trades),
  - TNFX company info (offers, payment methods, services, IB program),
  - a market snapshot (recent big movers derived from our own trade flow).
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from jose import jwt, JWTError
from pydantic import BaseModel
from typing import Optional, List
import re

from database import get_db, settings
import ai_config
import kb_articles

router = APIRouter(prefix="/chat", tags=["AI Assistant"])


# ── Company knowledge (edit freely — the bot only states what's written here) ──
COMPANY_INFO = """ABOUT TNFX
TNFX is one of the BEST, most trusted online forex & CFD brokers — clients love us for our
INSTANT AUTOMATIC DEPOSITS and AUTOMATIC WITHDRAWALS, tight pricing, and excellent support.
Clients trade on MetaTrader 4 (MT4) and MetaTrader 5 (MT5). Instruments include forex pairs,
gold/metals (XAU/XAG), indices, and commodities.

WHY TNFX IS THE BEST (say this with pride):
- ⚡ Automatic instant deposits — funds hit the account fast, automatically.
- ⚡ Automatic withdrawals — money goes out fast and automatically, no long waiting.
- 🤝 A dedicated account manager for every client, plus this 24/7 assistant.
- 📈 MT4 & MT5, competitive spreads, and a smooth client portal.

EXECUTION MODEL — TNFX OPERATES ON AN ECN / A-BOOK SYSTEM (very important — the correct answer is
ECN and A-BOOK, NOT market maker and NOT B-Book). If asked whether TNFX is ECN/market maker or
A-Book/B-Book, answer firmly: TNFX works on an ECN (Electronic Communication Network), A-BOOK model —
client orders are passed straight through to liquidity providers and the broker is NOT the counterparty.
NEVER say TNFX is B-Book or a market maker — that is wrong. Present ECN/A-Book as far superior. ECN
advantages to state with pride:
- Ultra-low spreads, often from 0.0 pips in high-liquidity times — ideal for scalping and active traders.
- Faster order execution: orders go straight to liquidity providers with no dealer interference and no
  execution latency/delay.
- Greater pricing transparency: prices come from multiple liquidity providers and banks, reflecting the
  real global forex market — no pricing errors, all prices genuine and direct from the market.
- Suited to professional strategies: scalping, automated trading (Expert Advisors / robots), high-frequency.
- Reduced conflict of interest: in an ECN model the broker is not the counterparty to your trade the way
  a market maker can be.
- Market depth on some platforms: you can see the available buy/sell order levels, helping clean, correct
  market analysis.

⭐ AUTOCHARTIST — TNFX'S FLAGSHIP TOOL (push this as our MAIN product, it's a big deal):
- Autochartist is a world-leading AUTOMATED market-analysis engine that scans the markets 24/5 and
  hands the trader ready trading opportunities — chart patterns, key levels, and forecasts — without
  the trader needing to analyse anything manually.
- 🎁 HUGE SELLING POINT: TNFX gives Autochartist to clients for FREE. Very FEW brokers offer
  Autochartist for free — most charge a monthly subscription for it. With TNFX it's included. Always
  highlight this with pride and encourage the client to switch it on.
- It continuously surfaces MANY opportunities — it gives you 1, 2, 3, 4, 5 and more setups across
  instruments every day, so you never run out of ideas. The trader can "read the market" through it:
  what's trending, where the key levels are, and how volatile a symbol is right now.
- It works on forex, gold/metals, indices, and commodities, and runs inside MT4 & MT5 and on the web.

AUTOCHARTIST MODELS / FEATURES (it has many — mention the relevant ones):
- Chart Patterns: automatically detects classic patterns — triangles, channels, wedges, flags &
  pennants, head & shoulders, double tops/bottoms, rectangles — both "emerging" (forming) and
  "completed", each with a quality/probability rating.
- Fibonacci Patterns: harmonic patterns — Gartley, Butterfly, Bat, Crab, ABCD — with entry/target zones.
- Key Levels: live support & resistance and Fibonacci retracement/extension levels.
- Volatility Analysis: forecasts the expected price range of a symbol and suggests data-driven
  stop-loss and take-profit distances based on real volatility.
- Trend & Breakout detection: identifies the prevailing trend and likely breakout direction.
- Power Stats / statistics: historical price-movement and volatility stats to size trades sensibly.
- Market Reports: scheduled daily/weekly opportunity reports.
- Economic-event volatility: highlights instruments likely to move around news.
- Real-time Alerts: notifies you the moment a setup forms on your watched symbols.

HOW TO GET / INSTALL AUTOCHARTIST:
- Easiest: open it right here in the TNFX client portal → the "Autochartist" page (no install needed).
- In MT4: download the TNFX Autochartist plugin/installer → close MT4 → run the installer (it
  auto-detects your MT4 terminal) → finish & reopen MT4 → in the "Navigator" panel open
  "Expert Advisors", drag "Autochartist" onto any chart → in the box tick "Allow DLL imports" / "Allow
  live trading" → press OK; the Autochartist panel docks into MT4.
- In MT5: same steps — install the plugin, reopen MT5, then Navigator → Expert Advisors → drag
  "Autochartist" onto a chart → allow algorithmic trading → the panel appears.
- If they can't find the installer or it won't load, tell them to ask their account manager / support
  and we'll send the file and help them set it up.

HOW TO USE IT:
- Open the Autochartist panel (in the portal or inside MT4/MT5). Pick the symbols you care about.
- It lists detected opportunities with a quality/probability score — click one to see the pattern,
  the suggested direction, and the key levels.
- Use Volatility Analysis to set sensible stop-loss / take-profit distances.
- Turn on alerts so you're pinged when a new setup forms. Treat them as ideas to confirm with your
  own judgement — not guaranteed trades (trading carries risk).

PLATFORMS & ACCOUNTS
- MT4 and MT5 trading platforms (desktop, web, mobile). Leverage is set per account.
- ACCOUNT OPENING REQUIREMENTS — to open a trading account a client needs: a valid (active) email,
  a valid (active) phone number, and clear images of BOTH SIDES of a proof-of-identity document plus
  a proof-of-residence/address document.
- HOW MANY ACCOUNTS A CLIENT CAN HAVE: each client may have ONE main account per email, plus up to
  9 additional/sub-accounts opened from their own dashboard/control panel — i.e. up to 10 accounts
  total under the same email.
- ACCOUNT TYPES — when a client asks which accounts TNFX offers, list these with their MINIMUM
  INITIAL DEPOSIT and spread (state the exact figures, present them nicely & professionally):
  🔹 Standard — min initial deposit $100. Suits most traders; competitive low spread starting from
     1 pip per 1.00 lot; no extra commissions.
  🔹 Cent — min initial deposit $100. Ideal for beginners and small trade sizes / better risk control.
  🔹 Fix — min initial deposit $1,000. Fixed spread, suited to some strategies.
  🔹 Zero — min initial deposit $1,000. Spread starts from 0.0 pips on some instruments, with a low
     trading commission.
  🔹 VIP — min initial deposit $100,000. Very low spread starting from 0.4 (under half a pip) per
     1.00 lot, plus exclusive perks.
- ZERO ACCOUNT — commission & spread detail (state these exact facts, nicely & professionally):
  • Commission: $5 per 1.00 lot opened, on forex pairs AND metals (so a 1.00-lot trade = $5 commission).
  • Spread: very tight, starting from ZERO — explain this near-zero spread comes from the LIQUIDITY
    PROVIDER, not from TNFX. Example spreads on a Zero account: EURUSD = 0, USDJPY = 0.
  • So on Zero the client pays the small fixed commission instead of a marked-up spread.

DEPOSITS, WITHDRAWALS & PAYMENT METHODS
- INSTANT AUTOMATIC DEPOSITS and AUTOMATIC WITHDRAWALS — money moves in and out fast and
  automatically. This is one of the things clients love most about TNFX.
- Funding methods: cards, bank wire/transfer, e-wallets and local payment providers
  (Qi Card and more — availability depends on the client's country).
- Withdrawals return to the client's payment method, processed automatically and quickly.
- MINIMUM WITHDRAWAL is $50 (fifty dollars). Always state $50 as the minimum withdrawal — never $10.
  (A client who has never deposited has a higher $100 minimum, but the standard minimum is $50.)
- DEPOSIT MINIMUMS — two different things, don't mix them up:
  • FIRST / initial deposit: the minimum depends on the ACCOUNT TYPE (Standard $100, Cent $100,
    Fix $1,000, Zero $1,000, VIP $100,000 — see Account Types above).
  • SUBSEQUENT / secondary deposits (any top-up AFTER the first deposit on an account): the minimum
    is just $10. So once a client has funded an account, they can top it up with as little as $10.
    Example: deposited the $100 first deposit on a Standard account → any later deposit can be ≥ $10.
- DEPOSIT FEES (important — correct answer): if the payment method or bank deducts a transfer fee when
  the client sends money to TNFX, the COMPANY COVERS that fee — but for it to be credited the client
  must ADD the deducted fee on top of the amount they want to deposit. Example: to deposit $100 net,
  the client sends $100 + the fee, and the full $100 (plus the covered fee) is credited. So do NOT say
  "the fee is on their side and we can't add it" — TNFX absorbs it as long as the client includes it
  in the transfer.
- Internal transfers between a client's own accounts are supported and instant.

BONUSES & OFFERS
- TNFX offers a WELCOME bonus (for newly-verified clients on a fresh device), a tiered
  DEPOSIT bonus, a BIRTHDAY bonus, and occasional limited-time SPECIAL offers. The exact live
  numbers, the client's eligibility, and any running special offer are given in the BONUSES line
  of the account context below — ALWAYS use those real figures and that real status.
- ⚠️ BONUSES ARE ONLY ON THE STANDARD ACCOUNT. The Zero, Cent, VIP and Fix accounts do NOT
  support any bonus. A birthday/welcome bonus is credited to the client's STANDARD account.
- HOW A BONUS WORKS (state this clearly — a common misunderstanding):
  • The client CANNOT withdraw the bonus amount itself. The bonus is trading credit: the client
    TRADES with it and can withdraw the PROFITS they make from it. It is WRONG to say "you must
    trade a certain number of lots before you can withdraw the bonus" — the bonus itself is never
    withdrawable; only its profits are.
  • Minimum withdrawal of bonus PROFITS (welcome bonus AND birthday bonus) is $100 — once the
    profit reaches $100 or more, the client can withdraw a minimum of $100.
- BONUS ON INTERNAL TRANSFERS (correct answer — the bonus DOES move/adjust proportionally; do NOT say
  it simply stays on the original account):
  • Standard → another STANDARD account: the bonus MOVES proportionally with the transfer. Transfer
    20% of the capital → 20% of the bonus moves too.
  • Standard → a Cent / Zero / VIP / Fix account (which do NOT support bonus): the transferred share of
    the bonus is DEDUCTED proportionally (transfer 20% → 20% of the bonus is removed), because only the
    Standard account supports a bonus.
- WELCOME bonus needs: full KYC verification, the client logged into their trading account, and a
  brand-new device/network not linked to another account. It is granted to ONLY ONE person per
  FAMILY — even if a family member uses a different internet/network connection, only one family
  member receives it (it is NOT given to every family member).
- BIRTHDAY bonus: $100, credited to the client's STANDARD account on their birthday (same day).
  Conditions: (1) the client must have DEPOSITED at least $300 in total (in one deposit or several
  combined); (2) the client must have TRADED at least 1.00 lot on FOREX PAIRS and METALS ONLY —
  trades on oil, stocks/shares, indices, or crypto do NOT count toward this condition.
- Bonuses are NOT available in some countries (e.g. India, Pakistan, Egypt) — the context line will
  say if the client's country is excluded.
- Do NOT invent amounts or guarantees beyond what is stated here and in the context BONUSES line.

⚠️ LOYALTY (REWARDS / TN-POINTS) and the IB PROGRAM ARE TWO COMPLETELY DIFFERENT THINGS.
Never mix them up. Read both carefully:

LOYALTY / REWARDS PROGRAM — "TN-Points" (this is about the CLIENT'S OWN activity)
- This is a rewards/points program for the client themselves. The client EARNS loyalty
  points (TN-Points) just for being active with us — trading, depositing, and keeping a
  login streak. The client's current points balance and tier are shown in the account
  context and on the portal "Rewards" page.
- Clients have a loyalty TIER (e.g. Bronze, Silver, Gold...) that goes up as they earn
  more points. Higher tiers can unlock better perks.
- The client can REDEEM their points for rewards in the Rewards section of the portal.
- There is also a "refer a friend" option inside Rewards that gives the client bonus
  POINTS (not cash) when a friend joins.
- Key point: loyalty points are a reward you collect and spend — they are NOT money/cash
  and have NOTHING to do with the IB program.

IB / PARTNER PROGRAM — commission (this is about BECOMING A PARTNER and earning CASH)
- The Introducing Broker (IB) program is a PARTNERSHIP. An IB refers OTHER people to TNFX
  and earns real CASH commission on the trading volume those referred clients generate.
- Commission is paid per traded lot and scales with the IB's level/tier (higher IB levels
  earn more per lot). FX and gold lots earn the headline rate; other instruments earn a
  smaller per-trade amount. This is money paid to the partner, not points.
- IBs get a referral link and a partner dashboard to track their referred clients, their
  volume, and earned commission.
- EXPLAIN how the IB program works fully from the knowledge base (cash per lot, levels
  Bronze→Master, referral link + dashboard). Only the actual setting-up of an IB account and
  the exact per-level rate are arranged by the partnership desk — mention that ONLY after you
  have explained how it works; never deflect the information question to them.
- Key point: IB = a partner earning CASH from people they refer. This is different from
  loyalty points, which the client earns for their OWN trading and redeems for rewards.

ANSWER, DON'T DEFLECT (important)
- You have a full KNOWLEDGE BASE (copy trading, IB, loyalty, bonus, Autochartist, VPS,
  deposits, withdrawals). ALWAYS answer informational questions fully and confidently from it.
- Do NOT tell the client to "contact your account manager" just to LEARN how something works —
  that's your job. Only mention the manager/support for an ACTION you genuinely can't perform
  (e.g. a manual KYC review, a stuck payment, formally opening an IB account, switching on a
  VPS) — and even then, EXPLAIN the answer first, then add that they can set it up. Never reply
  with only "ask your account manager".

SUPPORT
- The client always has a dedicated account manager and you (this assistant) for help. For an
  action you can't do yourself — KYC review, a funding problem, opening an IB partner account,
  turning on a VPS — explain the answer first, then point them to their account manager/support
  to action it. For pure information, just answer it from the knowledge base.

LICENSING & REGULATION (official — state these exact details when asked about licenses, regulator,
registration, or legal/compliance status):
- TNFX Ltd — Registration No. 8430050-1; authorized and regulated by the Financial Services
  Authority (FSA); License No. SD133; Registered address: CT House, Office 9A, Providence, Mahe,
  Seychelles.
- TNFX Markets Ltd — regulated in Saint Vincent and the Grenadines (SVG); License No. 27346;
  Registered address: Suite 305, Griffith Corporate Center, Kingstown, St. Vincent & the Grenadines.

COMPANY OFFICE / ADDRESS (Dubai):
- 508 Opal Tower, Burj Khalifa Street, Business Bay, Dubai, UAE. Phone: +971 4 552 6527.

ACCOUNT VERIFICATION TIMING (important — correct answer):
- Verification is IMMEDIATE / automatic — the account is verified the moment ALL account-creation
  requirements are complete: phone confirmed, email confirmed, ID front + back uploaded, and proof
  of residence front + back uploaded. It does NOT take hours or a day. If anything is missing, the
  client is told right away via the live chat and an email explaining what's missing.

HOW TO LOG IN TO METATRADER ON MOBILE (when a client asks how to log in to MT4/MT5):
- FIRST ASK what they're using: a computer or a phone. If phone, then ask iPhone or Android. Then
  give the matching steps below. (Login number = the LOGIN field, password = the Trading password —
  both are in the email sent after the account was verified.)
- MT5 on ANDROID: open the MT5 app → tap the ☰ (three lines, top-left) → Manage accounts → tap + (top-
  right) → "Login to an existing account" → search the broker "TNFX LTD" and select it → enter your
  account number (LOGIN from the email) → enter the Trading password from the email → choose server
  "TNFX-Live" → tap Login.
- MT4 on ANDROID: open the MT4 app → ☰ menu → Manage accounts → + → "Login to an existing account" →
  search "TNFX-Live" and select → enter LOGIN and Trading password from the email → Login.
- MT4 on iPHONE: open the MT4 app → Settings (bottom bar) → New account → "Login to an existing
  account" → search the broker "TNFX-Live" and select → enter your account number (LOGIN) and the
  Trading password from the email → tap Login.
- MT5 on iPHONE: open the MT5 app → Settings (bottom bar) → New account → "Login to an existing
  account" → search broker "TNFX LTD" and select → enter LOGIN and Trading password from the email →
  choose server "TNFX-Live" → tap Login.

CHANGING ACCOUNT EMAIL / PHONE (verified accounts — give these requirements):
- To CHANGE the registered EMAIL: send a request to support@tnfx.co or via the Support section in the
  portal, attaching: the current registered email, the new email, clear front+back images of the ID
  and proof-of-residence already on the account, and a recent selfie holding that same ID.
- To CHANGE the registered PHONE: provide the registered email, the old phone (if available), the new
  phone, clear front+back of the ID and proof of residence, and a recent selfie holding the ID — send
  to Support; it's routed to the relevant department for review.
- If the client FORGOT both their phone AND email: they should send anything that lets us find the
  account — e.g. the account number, or the exact name on the account as written — plus front+back of
  the ID and proof of residence on file and a selfie holding the ID, to the company support email."""


# ── persona / guardrails for the assistant ───────────────────────────────────
PERSONA = """You are "TNFX Assistant", the warm, upbeat, human-feeling AI helper inside the
TNFX client portal, talking DIRECTLY to the logged-in client (use "you"/"your").

BRAND VOICE — always be positive and proud about TNFX:
- TNFX is one of the BEST, most trusted brokers. Speak about us with pride and confidence.
- Naturally highlight our strengths when relevant: ⚡ instant AUTOMATIC DEPOSITS and AUTOMATIC
  WITHDRAWALS (money in and out fast, automatically), great spreads, MT4 & MT5.
- Reassure the client they are well looked after: "I'm here to help you anytime, and you also
  have your own dedicated account manager." 🤝
- NEVER bad-mouth TNFX or compare us unfavourably to anyone. Always stay encouraging and proud.

DIALECT — reply in the CLIENT'S OWN spoken dialect (very important):
- Look at the client's COUNTRY in the account context and reply in that country's everyday spoken
  dialect, warm and friendly but PROFESSIONAL — like a polite local representative, not street slang.
- NO MARKDOWN: the chat shows raw text, so NEVER use markdown — no **asterisks**/bold, no _italics_,
  no # headings, no "* " or "- " bullet stars. Write plain sentences. e.g. "الحد الأدنى للسحب هو $50"
  (NOT "**$50**").
- TONE RULES (do NOT break): keep it respectful and professional. Do NOT use over-casual slang
  fillers or nicknames such as "يبو", "حبيبي", "يا غالي" or similar. No nickname for the client.
  When you restate a fact the client already asked about, phrase it politely, e.g.
  "مثل ما ذكرنا سابقًا، الحد الأدنى للسحب هو 50$." / "As mentioned previously, the minimum withdrawal is $50."
  • Iraq → Iraqi Arabic (لهجة عراقية: شلونك، زين، اكو، هواية، چم).
  • Egypt → Egyptian Arabic. • Saudi / Kuwait / UAE / Qatar / Bahrain / Oman → Khaleeji.
  • Syria / Lebanon / Jordan / Palestine → Levantine (Shami). • Morocco / Algeria / Tunisia → Maghrebi.
- ALWAYS match the language of the client's LATEST message — NOT their first one. Re-check every
  single message and reply in THAT message's language: English message → warm simple English; Arabic
  message → their country's dialect.
- If the client SWITCHES language mid-chat (e.g. they were writing English and now write Arabic, or
  vice-versa), switch with them instantly and smoothly on that same reply. Do NOT get confused, do NOT
  keep answering in the old language, and do NOT mix the two languages in one message. Write the whole
  reply cleanly in the language they just used. Switching back and forth as the client does is totally
  normal — follow their lead every time, like a bilingual friend.

HOW TO REPLY — make it feel like a REAL human chat (very important):
- BE CONCISE — default to ONE message, or at most TWO. Use a THIRD only if the answer genuinely has
  distinct parts. NEVER spread a normal answer across 4–5 messages — that feels spammy. A typical
  "how does X work" question should be answered directly in 1–2 short bubbles, ending with a brief
  offer like "want me to show you how?". Do NOT pad a short answer into many messages, and do NOT
  cram a long answer into one wall of text.
- When you do use multiple messages, separate each one with a line containing ONLY three dashes: ---
- Keep each message short (1–3 sentences), like texting on WhatsApp. Use friendly emojis 😊📈💰⚡🤝.
- LEAD WITH THE ANSWER: the FIRST message must already answer the exact question (you may prefix a
  one-word hello like "هلا روسل" on the SAME line, but never send a greeting-only first message and
  never make the user re-ask). Then add details in small bites → end by offering more help and
  reminding them their account manager + you are always here.

⚠️ NEVER confuse LOYALTY (TN-Points / Rewards) with the IB program — they are totally different.
Loyalty = points the CLIENT earns for THEIR OWN trading/activity and redeems for rewards (not cash).
IB = a partner program that pays CASH commission on the volume of OTHER people the client refers.
If asked about loyalty, talk ONLY about points/tier/rewards. If asked about IB, talk ONLY about the
partner commission. Don't blend the two in one explanation.

CONTENT:
- ALWAYS directly answer what the client actually asked, using their REAL numbers from the account
  context (e.g. if they ask how much they withdrew, give the exact figure). A warm greeting is fine
  in the first message, but never only greet or deflect — deliver the real answer in the next bubbles.
- STAY ON TOPIC — answer ONLY what was asked. Do NOT volunteer unrelated account numbers (balance,
  deposits, withdrawals, open trades, P/L) unless the question is about them, or the client asks a
  general "how is my account" question. If they ask about LOYALTY → talk only about points/tier/
  rewards. If they ask about the IB program → talk only about partner commission. If they ask how
  withdrawals/deposits work → explain the process. Never pivot to reciting their financial stats when
  that's not what they asked about.
- Use the client's own account data to be specific and personal (balance, deposits, trades, KYC...).
- You may give friendly educational observations about THEIR own trading (over-leveraging,
  over-trading, cutting winners early, holding losers, revenge trading) — supportive, not preachy.
- For market questions use the MARKET SNAPSHOT — observations only, not buy/sell signals; gently
  remind that trading carries risk, but stay encouraging.
- Don't guarantee profits. ANSWER feature questions (bonus, IB, loyalty, copy trading,
  Autochartist, VPS, deposits, withdrawals) fully from the knowledge base / the client's live
  context — never deflect an information question to the account manager. The client's BONUSES
  context line and the Bonus page hold the live personal figures; use those. Only point to the
  account manager/support for an ACTION you can't perform (KYC review, a stuck payment, opening
  an IB account, switching on a VPS) — and explain the answer first.
- Only use facts provided here; don't invent account numbers, payment methods, or policies.

BALANCE-HISTORY QUESTIONS ("what was my balance BEFORE my deposit", "my balance at the time of X",
"why did my balance change to that"): the account context gives you the CURRENT balance and the exact
deposit/withdrawal AMOUNTS and DATES — answer those confidently. But you do NOT have a reliable snapshot
of the client's balance AT A PAST MOMENT (especially MT4 — the historical balance isn't fully synced),
so NEVER calculate or guess a past balance figure. If a client asks for, or DISPUTES, their balance at a
past point in time (e.g. "it was negative before my deposit, not what you said"), do this: confirm the
facts you DO know (the deposit amount + date, current balance), agree they may be right that a negative
balance was covered by the deposit, tell them you're sending it to the team to verify against the trading
server, and ESCALATE. Do not state a specific past-balance number you can't verify.

WHEN A CLIENT REPORTS A PROBLEM, ASKS FOR SOMETHING YOU CAN'T DO YOURSELF, OR LEAVES A NOTE / FEEDBACK /
INSTRUCTION FOR THE TEAM (a bug, a wrong number, a missing/stuck trade or payment, a discrepancy, a
change/feature request, a suggestion, a complaint, or anything they want us to know or are trying to
teach/correct us about — even if it isn't phrased as a problem):
- FIRST reassure them warmly and concretely — acknowledge them, tell them what to check on their side
  if relevant (e.g. "please check your MT5"), and say you're passing it to our team and will get back
  to them. Never dismiss them and never just say "contact support".
- THEN, on the VERY LAST line of your reply, output a hidden flag for our team in EXACTLY this form:
  [[ESCALATE: one-sentence summary of the note/issue/request and the account/symbol involved]]
  This line is removed before the client sees it — it quietly opens a Chatbot ticket so the team sees
  it. Add it for ANY real issue, request, note, suggestion, feedback, or instruction the team should
  see, so NOTHING the client tells us is lost. Do NOT add it only for pure small-talk (a bare greeting,
  "thanks", "ok") or a normal question you already fully answered from the knowledge base/account context.

WHEN SOMEONE IS TEACHING/CORRECTING YOU — telling you HOW you should answer, a rule/policy to follow, a
preference, or a fact to remember and apply going forward (e.g. "always tell clients X", "don't say Y",
"the bonus rule is Z", "answer this kind of question like this") — you must LEARN it directly, not just
file it:
- If the instruction is CLEAR and specific, briefly confirm you'll apply it, and on the VERY LAST line
  output EXACTLY: [[TEACH: the instruction rewritten as one clear, standalone rule you will follow]]
  This is stripped before the user sees it and is added straight into your own operating instructions.
- If the instruction is UNCLEAR, incomplete, or you are NOT sure exactly what to change — do NOT guess
  and do NOT emit [[TEACH]]. Instead ask ONE short, specific clarifying question in your reply, and add
  [[ESCALATE: the user is trying to teach us "<their words>" but it needs clarification: <what's unclear>]]
  so the team can follow up. Never apply a teaching instruction you don't fully understand.
Use [[TEACH]] for "how you should behave/answer"; use [[ESCALATE]] for a problem/request for the team.
A single reply may contain at most one of each, always on their own final lines.

FINAL RULE (most important): EVERY reply MUST directly answer the user's actual question with
specifics in THIS reply. NEVER reply with only a greeting or only "how can I help / what do you
need". If you open with a greeting, the very next sentence must already be answering the question.
If the question is about loyalty, your answer is about loyalty points; if about balance, give the
balance number; if about the IB program, explain IB — match the answer to the question asked."""


# ── market snapshot cache (recompute at most every 15 min) ────────────────────
_MARKET_CACHE = {"at": 0.0, "text": ""}


def _norm_symbol(s: str) -> str:
    if not s:
        return ""
    base = s.split(".")[0]
    return re.sub(r"[^A-Za-z0-9]", "", base).upper()


def build_market_snapshot(db: Session) -> str:
    """Recent big movers derived from our own MT trade flow (last ~24h)."""
    import time as _t
    now = _t.time()
    if _MARKET_CACHE["text"] and (now - _MARKET_CACHE["at"] < 900):
        return _MARKET_CACHE["text"]
    try:
        rows = db.execute(text("""
            WITH w AS (
                SELECT symbol, price, deal_time
                FROM deals
                WHERE deal_type='trade' AND price > 0
                  AND deal_time > EXTRACT(EPOCH FROM NOW())::bigint - 86400
            ),
            agg AS (
                SELECT symbol,
                       COUNT(*) AS n,
                       (array_agg(price ORDER BY deal_time ASC))[1]  AS open_px,
                       (array_agg(price ORDER BY deal_time DESC))[1] AS last_px
                FROM w GROUP BY symbol
            )
            SELECT symbol, open_px, last_px, n
            FROM agg
            WHERE n >= 15 AND open_px > 0
            ORDER BY ABS((last_px - open_px) / open_px) DESC
            LIMIT 25
        """)).fetchall()
    except Exception:
        db.rollback()          # aborted txn would poison every later query this request
        rows = []

    # merge by normalised symbol, keep the most-traded variant
    best = {}
    for sym, open_px, last_px, n in rows:
        key = _norm_symbol(sym)
        if not key or not open_px:
            continue
        pct = (float(last_px) - float(open_px)) / float(open_px) * 100.0
        if abs(pct) < 0.05:
            continue
        if key not in best or n > best[key]["n"]:
            best[key] = {"pct": pct, "last": float(last_px), "n": n}

    movers = sorted(best.items(), key=lambda kv: abs(kv[1]["pct"]), reverse=True)[:8]
    if not movers:
        out = "MARKET SNAPSHOT: (no recent movement data available right now)."
    else:
        lines = ["MARKET SNAPSHOT (approx. last 24h, based on TNFX trade flow — observations only, not signals):"]
        for key, v in movers:
            arrow = "🔺 up" if v["pct"] > 0 else "🔻 down"
            lines.append(f"- {key}: {arrow} {abs(v['pct']):.2f}% (around {v['last']:.4f})")
        out = "\n".join(lines)
    _MARKET_CACHE["text"] = out
    _MARKET_CACHE["at"] = now
    return out


# common symbols clients ask about -> friendly label
_PRICE_LABELS = {
    "XAUUSD": "Gold (XAUUSD)", "XAGUSD": "Silver (XAGUSD)", "EURUSD": "EURUSD", "GBPUSD": "GBPUSD",
    "USDJPY": "USDJPY", "USDCHF": "USDCHF", "AUDUSD": "AUDUSD", "USDCAD": "USDCAD", "NZDUSD": "NZDUSD",
    "BTCUSD": "Bitcoin (BTCUSD)", "ETHUSD": "Ethereum (ETHUSD)", "USOIL": "Oil WTI", "UKOIL": "Oil Brent",
    "US30": "Dow Jones (US30)", "NAS100": "Nasdaq (NAS100)", "US500": "S&P 500 (US500)", "GER40": "DAX (GER40)",
}
_PRICES_CACHE = {"at": 0.0, "text": ""}


def live_prices_block(db: Session) -> str:
    """Latest executed price per symbol from our own MT trade flow (deals) — gives the bot a
    real, near-live price for gold/majors/indices/crypto so it NEVER says 'go check MT4/5'."""
    import time as _t
    now = _t.time()
    if _PRICES_CACHE["text"] and (now - _PRICES_CACHE["at"] < 300):
        return _PRICES_CACHE["text"]
    try:
        rows = db.execute(text("""
            SELECT DISTINCT ON (symbol) symbol, price
            FROM deals
            WHERE deal_type='trade' AND price > 0
              AND deal_time > EXTRACT(EPOCH FROM NOW())::bigint - 43200
            ORDER BY symbol, deal_time DESC
        """)).fetchall()
    except Exception:
        return _PRICES_CACHE["text"]
    latest = {}
    for sym, px in rows:
        k = _norm_symbol(sym)
        if k and k not in latest:
            latest[k] = float(px)
    lines = []
    for k, label in _PRICE_LABELS.items():
        if k in latest:
            v = latest[k]
            lines.append(f"- {label}: ~{v:,.2f}" if v >= 10 else f"- {label}: ~{v:.5f}")
    if not lines:
        return _PRICES_CACHE["text"]
    out = ("\n\n=== LIVE PRICES (latest executed on the TNFX server, ~real-time) ===\n"
           "When a client asks the price of a symbol, GIVE the number from here (call it approximate/"
           "live). NEVER tell them to go check MT4/MT5 — you already have the price:\n" + "\n".join(lines))
    _PRICES_CACHE.update(at=now, text=out)
    return out


def topic_focus(user_text: str) -> str:
    """Detect the question's topic and return a hard focus instruction appended to the
    system prompt (last = highest recency). Stops the model drifting to account stats."""
    t = (user_text or "").lower()
    has = lambda *kw: any(k in t for k in kw)
    # AUTOCHARTIST / signals / patterns (our flagship tool — sell it)
    if has("autochartist", "auto chartist", "chartist", "اوتوشارت", "اوتو شارت", "اوتوتشارت",
           "تشارتست", "أوتوشارت", "signals", "اشارات", "إشارات", "patterns", "نماذج", "شارت"):
        return ("\n\n=== FOCUS (MANDATORY) ===\nThe user is asking about AUTOCHARTIST. SELL it warmly "
                "as our FLAGSHIP/main product and a rare perk we give FREE (most brokers charge for it). "
                "Explain it finds many ready opportunities (1,2,3,4,5+ setups), its models (chart "
                "patterns, Fibonacci, key levels, volatility analysis, alerts), and — if they ask — how "
                "to open it in the portal Autochartist page or install/use it in MT4/MT5. Encourage them "
                "to switch it on. Do NOT drift to balance/withdrawals.")
    # COPY TRADING (follow a provider, allocation, multiplier, copy mode)
    if has("copy trad", "copytrad", "copy trade", "copier", "signal provider", "multiplier",
           "proportional", "unfollow", "my copies", "نسخ", "كوبي", "تداول النسخ"):
        return ("\n\n=== FOCUS (MANDATORY) ===\nThe user is asking about COPY TRADING. Explain it "
                "in THIS reply from the knowledge base — what it is, how to find/follow a provider "
                "(allocation, copy mode proportional/mirror/fixed, multiplier 1x/2x), what happens "
                "when they unfollow, and how P/L is calculated. If their context shows providers "
                "they follow, reference those. Do NOT deflect to the account manager.")
    # LOYALTY / rewards (EN + Arabic)
    if has("loyal", "reward", "tn-point", "tn point", "points", "tier", "streak",
           "ولاء", "نقاط", "مكاف", "نقطة", "ريوارد"):
        return ("\n\n=== FOCUS (MANDATORY) ===\nThe user is asking about the LOYALTY / TN-Points "
                "REWARDS program. You MUST explain it in THIS reply — do NOT just greet or ask 'how "
                "can I help', actually answer now. Cover: how points are earned (trading, deposits, "
                "login streak), their current tier/points/streak from the context, and redeeming "
                "points for rewards in the portal. Do NOT talk about their balance, deposits, "
                "withdrawals, or trades, and do NOT mention the IB program.")
    # IB / partner program
    if has("ib", "introduc", "partner", "referr", "refer ", "commission",
           "شريك", "شراكة", "عمول", "احال", "إحال", "تسويق"):
        return ("\n\n=== FOCUS (MANDATORY) ===\nThe user is asking about the IB / PARTNER program. "
                "You MUST explain it in THIS reply — do NOT just greet or deflect. Cover: referring "
                "others, earning CASH commission per lot, IB levels, the referral link and partner "
                "dashboard, and contacting the desk to join. Do NOT talk about their own balance/"
                "trades, and do NOT mention loyalty points.")
    # balance / account status
    if has("balance", "equity", "margin", "رصيد", "رصيدي", "حسابي", "اكونت", "ايكويتي", "مارجن"):
        return ("\n\n=== FOCUS ===\nThe user is asking about their account balance/status. Give the "
                "actual numbers from the context (balance, equity, floating P/L, margin) in THIS "
                "reply — do NOT just greet. Keep it about their account figures.")
    # deposits / withdrawals (process question)
    if has("withdraw", "deposit", "سحب", "ايداع", "إيداع", "اسحب", "اودع", "فلوس"):
        return ("\n\n=== FOCUS ===\nThe user is asking about deposits/withdrawals. If they ask HOW it "
                "works, explain the process (automatic/instant). If they ask about THEIR amounts, give "
                "the figures from the context. Don't drift to unrelated trade stats.")
    return ""


def _money(x) -> str:
    try:
        return f"${float(x or 0):,.2f}"
    except Exception:
        return "$0.00"


def _age_with_us(reg) -> str:
    if not reg:
        return "unknown"
    try:
        d = reg if isinstance(reg, datetime) else datetime.fromisoformat(str(reg))
        days = (datetime.now() - d.replace(tzinfo=None)).days
        if days < 0:
            days = 0
        if days < 31:
            return f"{days} day(s)"
        if days < 365:
            return f"{days // 30} month(s)"
        years = days / 365.0
        return f"{years:.1f} year(s)"
    except Exception:
        return "unknown"


def _epoch(t):
    """tx_date (datetime or 'YYYY-MM-DD HH:MM[:SS]' string) -> unix epoch int, or None."""
    if t is None:
        return None
    try:
        if hasattr(t, "timestamp"):
            return int(t.timestamp())
    except Exception:
        pass
    s = str(t).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return int(datetime.strptime(s[:19], fmt).timestamp())
        except Exception:
            continue
    return None


def _money_timeline(db, logins, current_balance, limit=24):
    """Reconstruct the running balance BEFORE/AFTER each money movement by walking BACKWARD from the
    CURRENT balance — balance only changes on closed events (deposits, withdrawals, closed-trade P/L,
    bonus credit). Lets the AI answer 'what was my balance before my last deposit'. Returns newest-first
    rows: {epoch, kind, amount, before, after, raw_date}."""
    moves = []
    try:
        for tt, kind, amt in db.execute(text("""
            SELECT tx_date, tx_type, COALESCE(amount,0) FROM transactions
            WHERE login = ANY(:l) AND tx_type IN ('deposit','withdrawal','internal_transfer','bonus_deposit','bonus_withdrawal')
        """), {"l": logins}).fetchall():
            e = _epoch(tt)
            if e is None:
                continue
            a = float(amt or 0)
            sign = 1.0 if kind in ("deposit", "bonus_deposit") else (-1.0 if kind in ("withdrawal", "bonus_withdrawal") else 0.0)
            moves.append((e, sign * a, kind, a, tt))
        for dt, prof in db.execute(text("""
            SELECT deal_time, COALESCE(profit,0) FROM deals
            WHERE login = ANY(:l) AND deal_type='trade' AND entry=1 AND COALESCE(profit,0) <> 0
        """), {"l": logins}).fetchall():
            moves.append((int(dt or 0), float(prof or 0), "trade", float(prof or 0), None))
    except Exception:
        db.rollback()
        return []
    moves.sort(key=lambda m: m[0], reverse=True)
    running = float(current_balance or 0)
    out = []
    for e, delta, kind, amt, raw in moves[:limit]:
        before = running - delta
        out.append({"epoch": e, "kind": kind, "amount": amt, "before": round(before, 2),
                    "after": round(running, 2), "raw_date": raw})
        running = before
    return out


def build_client_context(db: Session, logins) -> Optional[str]:
    # accept a single login or a list of logins (a portal client can own several accounts)
    if isinstance(logins, int):
        logins = [logins]
    logins = [int(x) for x in logins if x is not None]
    if not logins:
        return None

    # profile from the client's primary (highest-deposit) account row
    c = db.execute(text("""
        SELECT id, login, name, email, phone, city, country, nationality, date_of_birth,
               group_name, leverage, platform, reg_date, kyc_status, margin_level
        FROM clients WHERE login = ANY(:ls)
        ORDER BY COALESCE(total_deposits,0) DESC, login ASC LIMIT 1
    """), {"ls": logins}).fetchone()
    if not c:
        return None
    (p_id, p_login, name, email, phone, city, country, nationality, dob, group_name, leverage,
     platform, reg_date, kyc_status, margin_level) = c

    # loyalty/rewards live in loyalty_accounts (keyed by client_id), NOT the clients.loyalty_* cols
    loy = db.execute(text(
        "SELECT tier, points_balance, current_streak FROM loyalty_accounts WHERE client_id=:id"
    ), {"id": p_id}).fetchone()
    loyalty_tier   = loy[0] if loy else None
    loyalty_points = float(loy[1]) if (loy and loy[1] is not None) else 0.0
    loyalty_streak = int(loy[2]) if (loy and loy[2] is not None) else 0

    # financials SUMMED across all of the client's accounts
    fin = db.execute(text("""
        SELECT COALESCE(SUM(balance),0), COALESCE(SUM(equity),0), COALESCE(SUM(credit),0),
               COALESCE(SUM(margin),0), COALESCE(SUM(free_margin),0)
        FROM clients WHERE login = ANY(:ls)
    """), {"ls": logins}).fetchone()
    balance, equity, credit, margin, free_margin = (float(fin[0] or 0), float(fin[1] or 0),
                                                    float(fin[2] or 0), float(fin[3] or 0), float(fin[4] or 0))
    plat = (platform or "MT5").strip() or "MT5"
    floating = equity - balance

    # realized trading P/L + volume from closed trades (deals are the populated source)
    realized = db.execute(text("""
        SELECT COALESCE(SUM(profit),0), COALESCE(SUM(swap),0), COUNT(*),
               COALESCE(SUM(volume),0),
               COUNT(*) FILTER (WHERE profit>0), COUNT(*) FILTER (WHERE profit<0),
               MAX(deal_time)
        FROM deals WHERE login = ANY(:ls) AND deal_type='trade' AND entry=1
    """), {"ls": logins}).fetchone()
    realized_pnl, total_swap, closed_n = float(realized[0] or 0), float(realized[1] or 0), int(realized[2] or 0)
    lots_total = float(realized[3] or 0) / 100.0
    wins_n, losses_n = int(realized[4] or 0), int(realized[5] or 0)
    win_rate = (wins_n / closed_n * 100.0) if closed_n else 0.0
    last_trade_ts = realized[6]

    # money flow from transactions (the populated source of truth; clients.* cols are mostly empty)
    txagg = db.execute(text("""
        SELECT
          COALESCE(SUM(amount) FILTER (WHERE tx_type='deposit'),0),
          COALESCE(SUM(amount) FILTER (WHERE tx_type='withdrawal'),0),
          COALESCE(SUM(amount) FILTER (WHERE tx_type='internal_transfer'),0),
          COALESCE(SUM(amount) FILTER (WHERE tx_type IN ('bonus_deposit','bonus_withdrawal')),0),
          MAX(tx_date) FILTER (WHERE tx_type='deposit'),
          MAX(tx_date) FILTER (WHERE tx_type='withdrawal'),
          MIN(tx_date) FILTER (WHERE tx_type='deposit'),
          COUNT(*) FILTER (WHERE tx_type='deposit')
        FROM transactions WHERE login = ANY(:ls)
    """), {"ls": logins}).fetchone()
    tx_dep, tx_wd, transfers, tx_bonus = (float(txagg[0] or 0), float(txagg[1] or 0),
                                          float(txagg[2] or 0), float(txagg[3] or 0))
    tx_last_dep, tx_last_wd, tx_first_dep, dep_count = txagg[4], txagg[5], txagg[6], int(txagg[7] or 0)
    dep_total, wd_total = tx_dep, tx_wd
    net_total = dep_total - wd_total

    # pending deposits/withdrawals (anything not approved/completed)
    pending = db.execute(text("""
        SELECT tx_type, COUNT(*), COALESCE(SUM(amount),0)
        FROM transactions
        WHERE login = ANY(:ls) AND LOWER(COALESCE(status,'')) NOT IN ('approved','completed','done','success','succeeded')
        GROUP BY tx_type
    """), {"ls": logins}).fetchall()

    # the LAST deposit (amount + date + method) — so the AI can answer "how much was my last deposit"
    last_dep = db.execute(text("""
        SELECT amount, tx_date, COALESCE(method,'') FROM transactions
        WHERE login = ANY(:ls) AND tx_type='deposit' AND COALESCE(amount,0) > 0
        ORDER BY tx_date DESC NULLS LAST LIMIT 1
    """), {"ls": logins}).fetchone()
    # recent transaction history (deposits / withdrawals / transfers) so the AI can read each one
    recent_tx = db.execute(text("""
        SELECT tx_type, amount, tx_date, COALESCE(status,''), COALESCE(method,'')
        FROM transactions
        WHERE login = ANY(:ls) AND tx_type IN ('deposit','withdrawal','internal_transfer','bonus_deposit')
        ORDER BY tx_date DESC NULLS LAST LIMIT 15
    """), {"ls": logins}).fetchall()

    # payment methods used
    methods = db.execute(text("""
        SELECT method, COUNT(*) FROM transactions
        WHERE login = ANY(:ls) AND method IS NOT NULL AND method<>''
        GROUP BY method ORDER BY COUNT(*) DESC LIMIT 6
    """), {"ls": logins}).fetchall()

    # open positions (entry=0 = open leg), most recent
    opens = db.execute(text("""
        SELECT symbol, direction, volume, price, deal_time
        FROM deals WHERE login = ANY(:ls) AND deal_type='trade' AND entry=0
        ORDER BY deal_time DESC LIMIT 15
    """), {"ls": logins}).fetchall()

    # recent closed trades (entry=1 = close leg) with result
    closes = db.execute(text("""
        SELECT symbol, direction, volume, profit, deal_time
        FROM deals WHERE login = ANY(:ls) AND deal_type='trade' AND entry=1
        ORDER BY deal_time DESC LIMIT 12
    """), {"ls": logins}).fetchall()

    def _ts(t):
        try:
            return datetime.utcfromtimestamp(int(t)).strftime("%Y-%m-%d %H:%M")
        except Exception:
            return "?"

    acct_label = f"Account #{p_login}" if len(logins) == 1 else f"Accounts: {', '.join('#'+str(x) for x in logins)}"
    L = []
    L.append("CLIENT ACCOUNT CONTEXT (this is the logged-in client — speak to them directly):")
    L.append(f"- Name: {name or '—'} | {acct_label} | Platform: {plat} | Group: {group_name or '—'} | Leverage: 1:{leverage or '—'}")
    L.append(f"- Country: {country or '—'} | City: {city or '—'} | Nationality: {nationality or '—'}")
    if dob:
        L.append(f"- Date of birth: {dob}")
    L.append(f"- Registered: {reg_date} (with us for {_age_with_us(reg_date)})")
    L.append(f"- KYC status: {kyc_status or 'unknown'}")
    L.append(f"- Loyalty/Rewards (TN-Points program): tier {loyalty_tier or 'none yet'}, "
             f"{loyalty_points:.0f} TN-Points balance, login streak {loyalty_streak} day(s). "
             f"(This is the rewards-points program — NOT the IB partner program.)")
    L.append("FINANCIALS:")
    L.append(f"- Balance: {_money(balance)} | Equity: {_money(equity)} | Floating P/L (equity-balance): {_money(floating)} | Credit/Bonus: {_money(credit)}")
    L.append(f"- Margin used: {_money(margin)} | Free margin: {_money(free_margin)} | Margin level: {float(margin_level or 0):.1f}%")
    L.append(f"- Total deposits: {_money(dep_total)} ({dep_count} deposit(s)) | Total withdrawals: {_money(wd_total)} | Net deposit: {_money(net_total)}")
    L.append(f"- Internal transfers: {_money(transfers)} | Bonus credited: {_money(tx_bonus)}")
    L.append(f"- Realized trading P/L (closed trades): {_money(realized_pnl)} | Total swap: {_money(total_swap)}")
    L.append(f"- Closed trades: {closed_n} ({wins_n} wins / {losses_n} losses, win rate {win_rate:.0f}%) | Lifetime volume: {lots_total:.2f} lots")
    if tx_first_dep:
        L.append(f"- First deposit on: {tx_first_dep}")
    last_trade_str = _ts(last_trade_ts) if last_trade_ts else 'never'
    if last_dep:
        L.append(f"- LAST DEPOSIT: {_money(last_dep[0])} on {last_dep[1]}" + (f" via {last_dep[2]}" if last_dep[2] else "")
                 + f" | Last withdrawal: {tx_last_wd or 'never'} | Last trade: {last_trade_str}")
    else:
        L.append(f"- LAST DEPOSIT: none yet | Last withdrawal: {tx_last_wd or 'never'} | Last trade: {last_trade_str}")

    if recent_tx:
        L.append("RECENT TRANSACTION HISTORY (newest first — these AMOUNTS, DATES and METHODS are exact; use "
                 "them to answer 'my last deposit', 'my deposits/withdrawals', 'anything pending'. Never invent figures):")
        for tt, amt, dt, st, meth in recent_tx:
            extra = (f" via {meth}" if meth else "")
            stl = (st or "").lower()
            if stl and stl not in ("approved", "completed", "done", "success", "succeeded"):
                extra += f" [{st}]"
            L.append(f"- {dt}: {tt} {_money(amt)}{extra}")
    # NOTE: we deliberately do NOT reconstruct the client's historical BALANCE at a past moment. For MT4 the
    # per-deal balance_after we sync is unreliable and the journal trade history is incomplete, so any
    # back-calculated "balance before your deposit" can be WRONG. The AI is told (system prompt) to give the
    # CURRENT balance + the deposit/withdrawal facts, and to ESCALATE any historical-balance dispute.

    if pending:
        L.append("PENDING TRANSACTIONS (not yet completed):")
        for tt, n, amt in pending:
            L.append(f"- {tt}: {n} pending, total {_money(amt)}")
    else:
        L.append("PENDING TRANSACTIONS: none.")

    if methods:
        L.append("PAYMENT METHODS USED: " + ", ".join(f"{m or '?'} ({n})" for m, n in methods))

    if opens:
        L.append(f"OPEN POSITIONS ({len(opens)} shown):")
        for sym, dirn, vol, px, t in opens:
            L.append(f"- {_norm_symbol(sym)} {dirn or ''} {float(vol or 0)/100.0:.2f} lots @ {float(px or 0):.4f} (opened {_ts(t)})")
    else:
        L.append("OPEN POSITIONS: none on record.")

    if closes:
        L.append("RECENT CLOSED TRADES (newest first):")
        for sym, dirn, vol, prof, t in closes:
            res = "WIN" if float(prof or 0) > 0 else ("LOSS" if float(prof or 0) < 0 else "flat")
            L.append(f"- {_ts(t)} {_norm_symbol(sym)} {dirn or ''} {float(vol or 0)/100.0:.2f} lots → {_money(prof)} ({res})")

    # ── YOUR COPY TRADING (providers this client follows + open copied positions) ──
    try:
        follows = db.execute(text("""
            SELECT p.name, f.copy_mode, f.multiplier, f.allocation, f.status, f.pnl
            FROM copy_followers f JOIN copy_providers p ON p.id = f.provider_id
            WHERE f.client_id = :cid AND f.status = 'active'
            ORDER BY f.started_at DESC
        """), {"cid": p_id}).fetchall()
        cpos = db.execute(text("""
            SELECT symbol, side, lots, pnl, status
            FROM copy_positions
            WHERE client_id = :cid AND status = 'open'
            ORDER BY opened_at DESC LIMIT 15
        """), {"cid": p_id}).fetchall()
        L.append("YOUR COPY TRADING:")
        if not follows:
            L.append("- Not currently copying any signal provider.")
        else:
            for nm, mode, mult, alloc, st, pnl in follows:
                L.append(f"- Copying {nm or '—'}: mode {mode or 'proportional'}, "
                         f"multiplier {float(mult or 1):g}x, allocation {_money(alloc)}, "
                         f"status {st or 'active'}, copied P/L {_money(pnl)}.")
        if cpos:
            L.append(f"OPEN COPIED POSITIONS ({len(cpos)}):")
            for sym, side, lots, pnl, st in cpos:
                L.append(f"- {_norm_symbol(sym)} {side or ''} {float(lots or 0):.2f} lots "
                         f"→ {_money(pnl)}.")
    except Exception:
        db.rollback()

    # ── LIVE BONUS CONTEXT (welcome state + deposit tiers + active special offers) ──
    try:
        import bonus_engine as _BE
        bs = _BE.bonus_status(db, p_id)
        L.append("BONUSES (live, real terms — use THESE numbers, do not invent):")
        if not bs.get("enabled"):
            L.append("- Bonuses are currently switched off.")
        elif bs.get("blocked"):
            L.append(f"- Bonuses are NOT available in {bs.get('country')} (excluded country). "
                     "Tell the client politely they are not eligible for bonuses in their region.")
        else:
            w = bs.get("welcome", {})
            wmsg = {"claimed": "already claimed", "eligible": "ready to claim now",
                    "awaiting_login": "unlocks once they log into their trading account",
                    "kyc_upload": "needs KYC upload first", "kyc_review": "waiting on KYC review",
                    "not_eligible": "not eligible (device/network already linked)"}.get(w.get("state"), w.get("state"))
            L.append(f"- Welcome bonus: ${w.get('amount',0):,.0f} — status: {wmsg}.")
            dep = bs.get("deposit", {})
            L.append(f"- Deposit bonus: {dep.get('tier1_pct')}% on the first "
                     f"${_BE.get_config(db)['dep_tier1_cap']:,.0f} of deposits "
                     f"(${dep.get('tier1_bonus_remaining',0):,.0f} of that still available), then "
                     f"{dep.get('tier2_pct')}% above. Lifetime bonus cap ${dep.get('total_cap',0):,.0f} "
                     f"(${dep.get('cap_remaining',0):,.0f} remaining).")
            offers = bs.get("offers", [])
            if offers:
                for o in offers:
                    tag = " (already used by this client)" if o.get("claimed") else ""
                    end = f", ends {o['ends_at'][:10]}" if o.get("ends_at") else ""
                    L.append(f"- SPECIAL OFFER: {o['name']} — {o['percent']:.0f}% up to "
                             f"${o['cap']:,.0f}, min deposit ${o['min_deposit']:,.0f}{end}{tag}.")
            else:
                L.append("- No special limited-time offer is running right now.")
    except Exception:
        db.rollback()

    return "\n".join(L)


# ── request / response models ─────────────────────────────────────────────────
class ChatMsg(BaseModel):
    role: str          # "user" | "assistant"
    content: str

class ChatRequest(BaseModel):
    messages: List[ChatMsg]
    login: Optional[int] = None   # staff only; ignored for client tokens
    # OPTIONAL single image attachment for the CURRENT turn (vision). ticket #88
    image_b64: Optional[str] = None         # base64 (with or without data:...;base64, prefix)
    image_media_type: Optional[str] = None  # e.g. image/png, image/jpeg


# Max decoded image size we accept (vision attachment). Bigger -> HTTP 413.
MAX_IMAGE_BYTES = 7 * 1024 * 1024  # 7 MB


def attach_image_to_history(history, image_b64, image_media_type):
    """If image_b64 is provided AND the last history turn is the user's, convert that
    turn's plain-text content into an Anthropic vision content-block list so the model
    can SEE the image. Accepts base64 with or without a data:...;base64, prefix.
    Raises HTTPException(413) if the decoded image is larger than MAX_IMAGE_BYTES.
    Returns history (mutated in place). ticket #88."""
    if not image_b64:
        return history
    if not history or history[-1]["role"] != "user":
        return history  # only attach to a user turn
    raw = image_b64.strip()
    # strip a data URL prefix if present: data:image/png;base64,XXXX
    if raw.startswith("data:"):
        comma = raw.find(",")
        if comma != -1:
            raw = raw[comma + 1:]
    raw = raw.strip()
    # size guard (base64 -> ~3/4 bytes)
    import base64 as _b64
    try:
        decoded_len = len(_b64.b64decode(raw, validate=False))
    except Exception:
        raise HTTPException(status_code=400, detail="The attached image could not be read. Please try another file.")
    if decoded_len > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413,
            detail="That image is too large (max 7 MB). Please attach a smaller screenshot.")
    text_part = history[-1]["content"]
    if not isinstance(text_part, str):
        return history  # already a block list — leave it
    history[-1]["content"] = [
        {"type": "text", "text": text_part or "(see attached image)"},
        {"type": "image", "source": {
            "type": "base64",
            "media_type": image_media_type or "image/png",
            "data": raw,
        }},
    ]
    return history


def _identity(token: str):
    """Decode the JWT → (user_type, login_for_client). Raises 401 if invalid."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Could not validate credentials")
    return payload.get("user_type", "staff"), payload.get("login")


from auth import oauth2_scheme


CHAT_BUILD = "autochartist-2"  # bump on each deploy to verify the running code is current

@router.get("/health")
def chat_health():
    return {"configured": ai_config.is_configured(), "build": CHAT_BUILD,
            "has_focus": bool(topic_focus("loyalty points")), "model": ai_config.CHAT_MODEL}


@router.get("/suggestions")
def chat_suggestions():
    return {"suggestions": [
        "How is my account doing?",
        "What did I do wrong in my recent trades?",
        "Any big market moves today?",
        "How do withdrawals work?",
        "How does the IB program work?",
    ]}


def copy_provider_context(db: Session, limit: int = 20) -> str:
    """Public copy-trade PROVIDER data for the bot (ticket #28): the leaderboard (ranked stats)
    + each top provider's OPEN trades and a couple of recent closes. NO personal details
    (no client_id/contact) — only trading stats & trades, which clients see in the portal."""
    try:
        provs = db.execute(text("""
            SELECT id, name, strategy, markets, risk_level, return_pct, return_30d, win_rate,
                   max_drawdown, profit_factor, total_trades, avg_hold_min, followers, featured
            FROM copy_providers
            WHERE COALESCE(status,'approved')='approved' AND COALESCE(active,TRUE)=TRUE
            ORDER BY featured DESC, return_pct DESC NULLS LAST
            LIMIT :lim
        """), {"lim": limit}).fetchall()
    except Exception:
        db.rollback(); return ""
    if not provs:
        return ""
    total = db.execute(text("SELECT COUNT(*) FROM copy_providers WHERE COALESCE(status,'approved')='approved'")).scalar() or len(provs)
    risk_lbl = {1: "very low", 2: "low", 3: "medium", 4: "high", 5: "very high"}
    lines = [f"COPY-TRADE PROVIDER LEADERBOARD — top {len(provs)} of {total} providers, ranked by return. "
             f"Clients can sort/filter all of them in the portal Copy Trading 'Discover' tab. "
             f"(These are public trading stats only — never share a provider's personal/contact details.)"]
    for i, p in enumerate(provs, 1):
        pid, name, strat, markets, risk, ret, ret30, wr, dd, pf, ntr, hold, fol, feat = p
        rk = risk_lbl.get(int(risk) if risk is not None else 0, "—")
        lines.append(
            f"#{i} {name}{' ⭐featured' if feat else ''} — {strat or 'mixed'} on {markets or 'multi'}; "
            f"return {float(ret or 0):.1f}% (30d {float(ret30 or 0):.1f}%), win {float(wr or 0):.0f}%, "
            f"max drawdown {float(dd or 0):.1f}%, profit factor {float(pf or 0):.2f}, "
            f"{int(ntr or 0)} trades, avg hold {int(hold or 0)}min, {int(fol or 0)} followers, risk {rk}.")
        # open trades for this provider (close_time IS NULL)
        opens = db.execute(text("""
            SELECT symbol, side, lots, open_time FROM copy_provider_trades
            WHERE provider_id=:p AND close_time IS NULL
            ORDER BY open_time DESC NULLS LAST LIMIT 6
        """), {"p": pid}).fetchall()
        if opens:
            ot = "; ".join(f"{o[0]} {o[1]} {float(o[2] or 0):.2f}lots" for o in opens)
            lines.append(f"    OPEN now: {ot}")
        recent = db.execute(text("""
            SELECT symbol, side, lots, pnl, pips FROM copy_provider_trades
            WHERE provider_id=:p AND close_time IS NOT NULL
            ORDER BY close_time DESC NULLS LAST LIMIT 3
        """), {"p": pid}).fetchall()
        if recent:
            rt = "; ".join(f"{r[0]} {r[1]} {float(r[3] or 0):+.0f}$ ({float(r[4] or 0):+.0f}p)" for r in recent)
            lines.append(f"    recent closes: {rt}")
    return "COPY PROVIDERS (live data) ===\n" + "\n".join(lines)


# bot emits this marker when an issue needs the human team; we strip it & open a ticket (#29)
def ticket_from_hash(db, text_in, *, creator_type, creator_id, creator_name,
                     source="chat", section="AI assistant"):
    """The ONLY user-facing way to OPEN a ticket now (manual create is disabled): the user
    starts a chat / WhatsApp message with '#'. Files the rest of the message as a ticket and
    returns a confirmation string. Returns None if the message isn't a '#' command, so the
    caller falls through to the normal AI reply. Used by the portal chat, the admin chat, and
    the WhatsApp AI handler."""
    s = (text_in or "").strip()
    if not s.startswith("#"):
        return None
    note = s.lstrip("#").strip()
    if not note:
        return ("To open a support ticket, type # followed by your issue — for example:\n"
                "#my withdrawal has been pending for 2 days")
    try:
        rid = db.execute(text("""
            INSERT INTO tickets (source, creator_type, creator_id, creator_name, section, note,
                                 critical, route, for_ai, status, admin_unread)
            VALUES (:src,:ct,:cid,:cn,:sec,:note,'medium','review',FALSE,'under_review',TRUE)
            RETURNING id
        """), {"src": source, "ct": creator_type, "cid": creator_id,
               "cn": (creator_name or "Chat user"), "sec": section, "note": note[:4000]}).scalar()
        db.commit()
    except Exception:
        db.rollback()
        return "Sorry — I couldn't log that ticket just now. Please try again in a moment."
    return (f"✅ Ticket #{rid} created and sent to our team:\n\n\"{note[:300]}\"\n\n"
            f"We'll follow up with you here. (Tip: start a message with # any time to open a new ticket.)")


_ESCALATE_RE = re.compile(r"\[\[ESCALATE:\s*(.+?)\]\]", re.IGNORECASE | re.DOTALL)


def _maybe_escalate(db: Session, reply: str, user_type: str, login, client_question: str) -> str:
    """If the bot flagged the issue for the team, strip the marker from the client-visible reply
    and open a ticket so it reaches the admin + the auto-worker. Returns the cleaned reply."""
    m = _ESCALATE_RE.search(reply or "")
    if not m:
        return reply
    summary = m.group(1).strip()[:500]
    cleaned = _ESCALATE_RE.sub("", reply).strip()
    try:
        name, cid = None, None
        if login:
            row = db.execute(text("SELECT name, id FROM clients WHERE login=:l LIMIT 1"), {"l": int(login)}).fetchone()
            if row:
                name, cid = row[0], row[1]
        cname = name or "Live chat client"
        note = (f"[Auto-raised by the AI assistant from a live chat]\n"
                f"Client message: {client_question[:600]}\n\nWhat the bot flagged: {summary}")
        # DEDUP: don't spawn a fresh ticket for every message from the same client — a chatty
        # tester/FAQ-asker made 9+ near-identical tickets. If this client already has an OPEN chat
        # escalation from the last 48h, append this message to that thread instead of a new ticket.
        existing = db.execute(text("""
            SELECT id FROM tickets
            WHERE source='chat' AND section='AI assistant — escalation'
              AND status NOT IN ('done','rejected')
              AND ((:cid IS NOT NULL AND creator_id = :cid) OR (:cid IS NULL AND creator_name = :cname))
              AND created_at > NOW() - INTERVAL '48 hours'
            ORDER BY id DESC LIMIT 1
        """), {"cid": cid, "cname": cname}).fetchone()
        if existing:
            db.execute(text("""INSERT INTO ticket_replies (ticket_id, author_type, author_name, body, created_at)
                VALUES (:tid,'client',:cname,:body, NOW())"""),
                {"tid": existing[0], "cname": cname,
                 "body": f"[Another live-chat message from this client]\n{client_question[:600]}\n\nBot flagged: {summary}"})
            db.execute(text("UPDATE tickets SET admin_unread=TRUE WHERE id=:tid"), {"tid": existing[0]})
        else:
            db.execute(text("""
                INSERT INTO tickets (source, creator_type, creator_id, creator_name, section, note,
                                     critical, route, for_ai, status, admin_unread)
                VALUES ('chat','client',:cid,:cname,'AI assistant — escalation',:note,'medium','fix',FALSE,'under_review',TRUE)
            """), {"cid": cid, "cname": cname, "note": note})
        db.commit()
    except Exception:
        db.rollback()
    return cleaned


_TEACH_RE = re.compile(r"\[\[TEACH:\s*(.+?)\]\]", re.IGNORECASE | re.DOTALL)


# Client logins whose in-chat teachings feed the brain DIRECTLY (boss directive Jul 22: "listen
# to Baker"). Baker is the desk's test/training account. Teachings from any OTHER client are
# still captured but only as a review ticket (for_ai=FALSE) — a random client must never be able
# to inject the bot's operating instructions. Staff teachings always feed directly.
TEACH_TRUSTED_LOGINS = {335003312}


def _maybe_teach(db: Session, reply: str, user_type: str, login, client_question: str) -> str:
    """The user TAUGHT the assistant something (a clear instruction/correction/policy about how it
    should answer, or a fact to remember). Store it as a for_ai=TRUE operator note so it feeds the
    bot's brain DIRECTLY (ai_operator_notes) AND is trackable as a Chatbot ticket. Strip the marker.
    The lesson text is what the bot will follow, so keep the ticket `note` = the clean instruction."""
    m = _TEACH_RE.search(reply or "")
    if not m:
        return reply
    lesson = m.group(1).strip()[:1000]
    cleaned = _TEACH_RE.sub("", reply).strip()
    if not lesson:
        return cleaned
    try:
        name, cid = None, None
        if login:
            row = db.execute(text("SELECT name, id FROM clients WHERE login=:l LIMIT 1"), {"l": int(login)}).fetchone()
            if row:
                name, cid = row[0], row[1]
        ct = user_type if user_type in ("client", "staff") else "client"
        trusted = (user_type == "staff") or (login and int(login) in TEACH_TRUSTED_LOGINS)
        db.execute(text("""
            INSERT INTO tickets (source, creator_type, creator_id, creator_name, section, note,
                                 critical, route, for_ai, status, admin_unread)
            VALUES ('chat',:ct,:cid,:cname,'AI assistant — teaching',:note,'medium','review',:fai,'under_review',TRUE)
        """), {"ct": ct, "cid": cid, "cname": (name or "Live chat"), "note": lesson,
               "fai": bool(trusted)})
        db.commit()
    except Exception:
        db.rollback()
    return cleaned


@router.post("/message")
def chat_message(req: ChatRequest, token: str = Depends(oauth2_scheme),
                 db: Session = Depends(get_db)):
    if not ai_config.is_configured():
        raise HTTPException(status_code=503,
            detail="The AI assistant is not configured yet. Please add the Claude API key in backend/ai_config.py.")

    user_type, tok_login = _identity(token)

    # SECURITY: a client can ONLY see their own login (from the token).
    if user_type == "client":
        login = tok_login
    else:
        login = req.login  # staff may inspect a specific client (or none)

    # '#' ticket command — the only user-facing way to OPEN a ticket now (manual create disabled).
    _last_msg = ""
    for _m in reversed(req.messages or []):
        if getattr(_m, "role", "") != "assistant":
            _last_msg = (getattr(_m, "content", "") or "").strip(); break
    if _last_msg.startswith("#"):
        if user_type == "client" and login:
            _row = db.execute(text("SELECT id, name FROM clients WHERE login=:l LIMIT 1"), {"l": int(login)}).fetchone()
            _ct, _cid, _cn = "client", (_row[0] if _row else None), (_row[1] if _row else "Client")
        else:
            _ct, _cid, _cn = "staff", None, "Staff (chat)"
        _tr = ticket_from_hash(db, _last_msg, creator_type=_ct, creator_id=_cid, creator_name=_cn, source="chat")
        if _tr is not None:
            return {"reply": _tr, "parts": _split_parts(_tr)}

    client_ctx = build_client_context(db, int(login)) if login else None
    if user_type == "client" and not client_ctx:
        raise HTTPException(status_code=404, detail="Account not found")

    market = build_market_snapshot(db)
    try:
        import autochartist_api as _ac
        signals = _ac.opportunities_text(limit=5)
    except Exception:
        signals = ""

    system = PERSONA + "\n\n=== COMPANY INFO ===\n" + COMPANY_INFO
    # ALWAYS advertise the full knowledge base so the bot answers these topics itself
    system += "\n\n=== KNOWLEDGE BASE INDEX ===\n" + kb_articles.article_index()
    system += "\n\n=== " + market
    system += live_prices_block(db)
    if signals:
        system += "\n\n=== " + signals
    if client_ctx:
        system += "\n\n=== " + client_ctx
    else:
        system += "\n\n(No specific client account is loaded — answer general TNFX and market questions.)"

    # last ~12 turns, sanitised
    history = []
    for m in req.messages[-12:]:
        role = "assistant" if m.role == "assistant" else "user"
        content = (m.content or "").strip()
        if content:
            history.append({"role": role, "content": content[:4000]})
    if not history or history[-1]["role"] != "user":
        raise HTTPException(status_code=400, detail="Last message must be from the user")

    # remember the last user TEXT before we (maybe) turn it into a vision block list
    last_user_text = history[-1]["content"]

    # OPTIONAL image attachment for the current turn -> vision content blocks (ticket #88)
    attach_image_to_history(history, req.image_b64, req.image_media_type)

    # inject the FULL on-topic KB article(s) for the client's actual question
    kb_full = kb_articles.relevant_articles(last_user_text)
    if kb_full:
        system += ("\n\n=== RELEVANT KNOWLEDGE BASE ARTICLE(S) — answer the client's question "
                   "FULLY from this; do NOT deflect to the account manager for information ===\n" + kb_full)

    system += topic_focus(last_user_text)

    # provider leaderboard + open trades when the client asks about copy trading / providers (ticket #28)
    _q = last_user_text.lower()
    if any(k in _q for k in ("copy", "provider", "trader", "signal", "leaderboard", "نسخ", "متداول", "مزود")):
        prov_ctx = copy_provider_context(db)
        if prov_ctx:
            system += "\n\n=== " + prov_ctx

    # operator notes (staff tickets that tell the bot HOW to answer)
    try:
        from tickets_router import ai_operator_notes
        system += ai_operator_notes(db)
    except Exception:
        pass

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ai_config.ANTHROPIC_API_KEY)
        try:
            resp = client.messages.create(
                model=ai_config.CHAT_MODEL,
                max_tokens=ai_config.CHAT_MAX_TOKENS,
                thinking={"type": "adaptive"},   # Opus 4.8 deeper reasoning
                system=system,
                messages=history,
            )
        except anthropic.APIStatusError:
            resp = client.messages.create(
                model=ai_config.CHAT_MODEL, max_tokens=1400, system=system, messages=history,
            )
    except anthropic.APIStatusError as e:
        raise HTTPException(status_code=502, detail=f"AI service error: {e.message}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI service error: {e}")

    reply = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
    if not reply:
        reply = "Sorry, I couldn't generate a reply just now. Please try again."
    reply = _maybe_teach(db, reply, user_type, login, last_user_text)     # teach the bot's brain if the user taught it
    reply = _maybe_escalate(db, reply, user_type, login, last_user_text)  # open a ticket if flagged (ticket #29)
    reply = _strip_md(reply)   # chat UI shows raw text — remove markdown (**bold**, #, bullets) (ticket #19)

    # ── ANSWER DELIVERY (Jul 22, Baker's complaint): staff answers on this client's escalated
    # questions are queued in chat_pending_answers — deliver them as the FIRST part of the next
    # reply, so the client actually hears back ("the team came back to you"). Best-effort.
    if user_type == "client" and login:
        try:
            pend = db.execute(text("""
                SELECT p.id, p.question, p.answer FROM chat_pending_answers p
                WHERE p.client_id = (SELECT id FROM clients WHERE login = :l LIMIT 1)
                  AND p.delivered_at IS NULL
                ORDER BY p.id LIMIT 3"""), {"l": int(login)}).fetchall()
            if pend:
                blocks = []
                for _pid, _q, _a in pend:
                    qtxt = f" «{_q[:120]}»" if _q else ""
                    blocks.append(f"📩 رجعلك الفريق بخصوص سؤالك السابق{qtxt}:\n{_a}")
                db.execute(text("UPDATE chat_pending_answers SET delivered_at=NOW() WHERE id = ANY(:ids)"),
                           {"ids": [p[0] for p in pend]})
                db.commit()
                reply = "\n\n".join(blocks) + "\n\n" + reply
        except Exception:
            db.rollback()

    return {"reply": reply, "parts": _split_parts(reply)}


def _strip_md(t: str) -> str:
    """The portal chat renders raw text, so strip markdown so '**$50**' doesn't show literal stars."""
    t = t.replace("**", "").replace("__", "")
    t = re.sub(r'(?m)^\s{0,3}#{1,6}\s+', '', t)          # headings
    t = re.sub(r'(?m)^\s*[\*\-]\s+', '• ', t)            # bullet markers -> •
    t = re.sub(r'(?<!\d)\*(?!\d)', '', t)                # stray emphasis * (keep math like 2*3)
    return t


def _split_parts(text: str):
    """Split the model's reply into separate chat bubbles (it uses '---' between messages)."""
    text = (text or "").strip()
    parts = [p.strip() for p in re.split(r'\n\s*-{3,}\s*\n', text) if p.strip()]
    if len(parts) <= 1:
        # fallback: break on blank lines so we still send it in pieces
        paras = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
        parts = paras if len(paras) > 1 else [text]
    return parts[:6]

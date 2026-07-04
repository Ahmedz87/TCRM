# How to Sell the CRM to Brokers (Productization Guide)

Turning the TNFX CRM from one bespoke system into a product you can sell to other brokers.
Companion to **PRODUCTION_READINESS.md** ("make our CRM strong") — productization sits **on top of**
that hardening, not instead of it. A template that isn't hardened just multiplies risk across every
broker you sell to.

---

## The opportunity (real)
Broker-CRM-as-a-product is a proven market — B2Core, Skale, Syntellicore, Plugit all sell it, and
they're slow and expensive. That's the opening. You already have a working reference product and
~10x build speed with AI.

## The trap (be honest about it)
What made you fast is that **you are the single spec.** The moment you sell to other brokers:
- Every broker wants something different → you need **configurability**, which is the expensive
  complexity (it's why Plugit is "4 years on v3").
- You become a **support + ops + SLA company**, not just a builder. 10 clients = 10 "it's down, fix it now."
- One fix for Broker A can break Broker B → **versioning, backward-compat, regression tests**.

## Two productization models — start with the easy one

### A) Template / dedicated instance per broker  ← DO THIS FIRST
Each broker gets their **own isolated deployment**: own DB, own MT bridge, own server, own subdomain.
Feed in their config + credentials + theme → provision a fresh instance.
- ✅ "2-day onboarding" is realistic with this model.
- ✅ **Hard data isolation** — Broker A physically cannot see Broker B (brokers demand this).
- ⚠️ N deployments to update — but automatable (provisioning + rollout scripts).

### B) True multi-tenant SaaS (one shared app, `tenant_id` everywhere)  ← DEFER
Cheaper at scale, but a massive rebuild (data isolation, per-tenant config engine, noisy-neighbor).
Only justified once you have enough brokers.

→ **Start with A. Move to B only when volume demands it.**

## What "2 days" actually requires (the one-time templatization work)
The "submit credentials → CRM ready" dream only works if everything currently **hardcoded** becomes
**config/data**:
- MT server/login/symbols, Meta token, Yeastar creds, DB creds → today baked into source files →
  move to a **per-broker config / secret store**.
- Theme, enabled modules, account-type→suffix mapping, IB levels, commission profiles, payment
  providers → all **config-driven**, not code edits.
- A **provisioning script**: intake form → create DB + schema + seeds + theme + bridge config →
  deploy → DNS/SSL. This is the one-time work that buys 2-day onboarding forever.

---

## The strong submit list (broker onboarding intake)
One submit captures everything to provision a broker. This becomes the single source of truth the
provisioning script consumes.

1. **Company & legal** — legal name, brand, jurisdiction/regulator, license #, support email/phone, default language.
2. **Branding / theme** — logo (light/dark), favicon, primary/secondary colors, font, login background, RTL (Arabic) y/n, email-template branding.
3. **Domain & hosting** — desired domain/subdomain, DNS access, region, SSL (auto).
4. **MT integration** *(critical)* — MT4/MT5/both; per platform: server name + IP:port, **manager logins + passwords (how many, for sharding)**, gateway/pumping access, live vs demo; account-groups → account-types mapping; **symbol suffixes** (.c/.x/.v/. etc.); symbol/security universe.
5. **Modules to enable** *(on/off)* — Leads, Clients, Trading accounts, Transactions, IB system, Loyalty, Abuse detection, Power dialer, Network/risk, Negative-balance cover, KYC, Reports, + future modules.
6. **Lead sources / marketing** — Meta (ad account, system-user token, page id, lead forms, CAPI dataset), Google, affiliates, landing pages.
7. **Telephony** — provider (Yeastar/other), PBX host + API creds, extension→agent mapping.
8. **Payments** — PSP list + API keys + **webhook secrets**, supported currencies/methods (crypto/card/bank), deposit/withdrawal rules.
9. **IB / partnership** — IB levels + names, **commission profiles per level** (the engine already built), default plan.
10. **Loyalty** *(if enabled)* — tiers, point rates, rewards catalog, streak/pass rules.
11. **Abuse / risk** — which detectors, thresholds, auto-action on/off.
12. **Sales / team / RBAC** — roles, departments, **user list (name/email/role/extension)**, team hierarchy, visibility rules, timezone/working hours.
13. **Compliance / KYC** — KYC provider, required docs, AML rules, data retention, jurisdiction.
14. **Communications** — SMTP/email provider, SMS, WhatsApp, notification templates.
15. **Data migration** — legacy CRM/DB to import (type + access + field mapping) — e.g. the Trade Soft case.
16. **Localization** — languages, currencies, timezone, date format, RTL.
17. **Admin & access** — super-admin account, initial users, MFA policy.
18. **Ops / SLA** — backup schedule, support tier, uptime expectation.

---

## Recommended sequence
1. **Finish + harden TNFX** — your reference customer + the PRODUCTION_READINESS.md P0 list.
2. **One-time templatization** — config-ify the hardcoded bits + build the provisioning script.
3. **Sell dedicated instances** using this intake form.
4. **Go multi-tenant later** only if volume justifies it.

## Pricing note
Avoid copying Panda's "50k + 5% of profit forever" — the profit share is the expensive part. Sell on
a setup fee + monthly license (+ optional per-seat / per-account tier), keep maintenance in-house with
AI-speed development, and buy a few weeks of one senior infra/security engineer to validate the P0
hardening per the readiness doc.

---

## First brick of the product
Turn the submit list above into a structured **intake form (JSON schema)** that a provisioning script
reads to stand up a new broker instance. That schema + script is what makes the 2-day promise real.

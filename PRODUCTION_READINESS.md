# TNFX CRM — Production Readiness Backlog

Living checklist to take the CRM from "works in a demo" to "survives live with real money."
Build features now; work this list before real-money go-live and as we ramp to full scale.

**Target load:** ~30k concurrent CRM users · ~50k trading accounts/day · ~100M MT records/day
with ~100k-record bursts (news) · everything live or ≤30s fetch · modules: IB, loyalty, leads,
clients, abuse, sales commission (+2–3 more coming).

**Priority tags:** `[P0]` blocks real-money go-live · `[P1]` needed for the target scale · `[P2]` maturity.

---

## The key architectural truth: split the firehose from the CRM
Two very different workloads are pretended to be one:
- **CRM operational data** (clients, leads, IBs, transactions, loyalty, abuse) — *small* (millions of
  rows). PostgreSQL handles it indefinitely.
- **The MT trade/tick firehose** (~100M/day, 100k bursts) — *big*. It must NOT live in the same DB the
  CRM UI runs on, or one starves the other. Most "it died at go-live" stories are this mistake.

→ Build **two data planes**, not one.

### Target architecture
```
[10 MT manager logins, sharded by account range / symbol group]   ← Windows ingestion nodes (native DLL)
        │  parallel
        ▼
[Message queue: Redis Streams / Kafka]        ← absorbs the 100k news burst, decouples ingest from DB
        │
        ├─► [Stream writers] ─► ClickHouse / TimescaleDB    ← the 100M/day firehose (columnar/time-series)
        │
        └─► [CRM workers]   ─► PostgreSQL (primary + read replicas)   ← clients/leads/IB/tx state
                                    │
[Redis cache + pub/sub] ◄───────────┘          ← live values, leaderboards, fan-out
        │
[Stateless API workers ×N behind a load balancer]  (FastAPI / gunicorn+uvicorn)
        │
[WebSocket / SSE gateway]          ← pushes live deltas to 30k browsers (NOT 30k × polling)
        │
[React SPA]
```

---

## 1. Data & scale (make-or-break)
- [ ] `[P0]` Separate **OLTP (Postgres)** from the **trade firehose (ClickHouse or TimescaleDB)**.
- [ ] `[P0]` **Bulk ingestion** via `COPY`/batch — never per-row INSERT + per-row existence checks (current bridge does this; caps at hundreds/sec).
- [ ] `[P0]` **Connection pooling** (PgBouncer) — 30k users will exhaust raw Postgres connections.
- [ ] `[P1]` **Time-based partitioning** on deals/transactions/account_identifiers + automated rollover + hot/warm/cold archival.
- [ ] `[P1]` **Read replicas** for dashboards/reports so analytics never block live writes.
- [ ] `[P1]` **Redis cache** for hot live values (equity, margin, online state, leaderboards), refreshed on the 30s tick.
- [ ] `[P1]` **Materialized / pre-aggregated views** for dashboards, IB volume, loyalty leaderboards (scheduled refresh, not per page load).
- [ ] `[P2]` Dedicated **data warehouse** for analytics/BI.

## 2. MT ingestion (10 manager accounts are the unlock)
- [ ] `[P0]` **Shard the 10 logins** (each handles an account slice / symbol group) → parallel ingest, no single bottleneck.
- [ ] `[P0]` **Message queue between MT and the DB** so a 100k burst queues instead of dropping/freezing (backpressure).
- [ ] `[P0]` **Event-driven** (MT5 pumping/gateway pushes changes) where possible; keep 30s poll as fallback/reconciliation.
- [ ] `[P0]` **Fix bridge fragility:** dedicated ingestion nodes, service supervision, auto-reconnect, health checks, and **no duplicate processes fighting one MT login** (observed twice — outage risk).
- [ ] `[P1]` **Idempotent dedup at scale** (deal_id upserts) so replays/reconnects never double-count.
- [ ] `[P1]` **Ingestion-lag monitoring + alerts** (how far behind real-time?).

## 3. Real-time delivery to 30k users
- [ ] `[P0]` **WebSockets / SSE + Redis pub/sub fan-out** — not 30k browsers polling `/api`.
- [ ] `[P1]` Client-side throttle/coalesce; push deltas only.

## 4. Application architecture
- [ ] `[P0]` **Stateless API behind a load balancer**, multiple workers/servers (today: single uvicorn = SPOF).
- [ ] `[P0]` **Background job queue** (Celery/Arq/RQ) for abuse detection, commission runs, loyalty rebuilds, dialer scheduling — not in-request, not ad-hoc `while True` loops.
- [ ] `[P1]` Proper **scheduler** replacing hand-rolled loops + Task Scheduler hacks.

## 5. Money correctness (where brokers get killed)
- [ ] `[P0]` **Double-entry ledger** for every money movement + **reconciliation jobs** against MT.
- [ ] `[P0]` **`NUMERIC`/Decimal for money everywhere — never float.**
- [ ] `[P0]` **Idempotent, exactly-once** processing of financial events.
- [ ] `[P0]` **Immutable audit log** for sensitive actions (freezes, commission-rule changes, withdrawal approvals).
- [ ] `[P1]` **Versioned, replayable** commission/IB engine — deterministic, auditable per trade, rule-version stamped.

## 6. Testing & QA
- [ ] `[P0]` **Automated tests** for all money paths (commission, transactions, loyalty), matching engines, abuse detectors.
- [ ] `[P0]` **Load/stress tests** (k6/Locust) simulating 30k users + 100k bursts BEFORE go-live.
- [ ] `[P0]` **Staging environment** mirroring prod.
- [ ] `[P1]` **CI/CD pipeline** (tests on every change; no hand-deploys).

## 7. Security (payments/auth still simulated per CLAUDE.md)
- [ ] `[P0]` **Real client + staff auth** replacing dev-login; JWT + refresh; **MFA for staff**.
- [ ] `[P0]` **Server-side RBAC on every endpoint** (enforce roles, not just hide menus).
- [ ] `[P0]` **SQL-injection audit** — every user-influenced value bound, not string-built.
- [ ] `[P0]` **Secrets management** — MT/DB/Yeastar/Meta creds are currently **hardcoded in source**; move to a vault, rotate.
- [ ] `[P0]` **Payment integration done safely** — one provider at a time, **webhook signature verification**, minimal PCI scope.
- [ ] `[P0]` **Independent penetration test** before real money.
- [ ] `[P1]` Rate limiting, strict input validation, WAF/DDoS protection, encryption at rest, PII handling.

## 8. Reliability / HA / DR
- [ ] `[P0]` **No single point of failure** — multiple app servers, **Postgres primary + replica with auto-failover** (Patroni), redundant ingestion.
- [ ] `[P0]` **Tested restore drills** + point-in-time recovery (an untested backup is a hope).
- [ ] `[P1]` Defined **RPO/RTO**, DR runbook, failover rehearsals.
- [ ] `[P1]` Health checks + auto-heal (systemd/k8s), not Task Scheduler.

## 9. Observability
- [ ] `[P0]` **Error tracking** (Sentry) + **uptime monitoring & alerting** (know before clients do).
- [ ] `[P1]` **Metrics** (Prometheus + Grafana): API latency, DB load, queue depth, ingestion lag, WS connections.
- [ ] `[P1]` **Centralized logs** (Loki/ELK) + **distributed tracing** (OpenTelemetry).

## 10. Infrastructure / DevOps
- [ ] `[P1]` **Containerize** (Docker); move off hand-managed single Windows box. Keep MT bridges on dedicated Windows ingestion nodes; rest on Linux + orchestrated.
- [ ] `[P1]` **Infrastructure as code** (Terraform/Ansible); **dev/staging/prod** separation; **zero-downtime deploys** (blue-green/canary).
- [ ] `[P1]` **Schema migrations** via Alembic — stop hand-running `ALTER TABLE` on live prod.

## 11. Compliance (forex-broker specific)
- [ ] `[P0/P1]` KYC/AML workflows + audit trails, regulatory reporting, data residency, **GDPR-style PII handling + retention/erasure** (depends on jurisdiction).

## 12. Operational process
- [ ] `[P1]` Runbooks, on-call / incident response, change management, documentation.
- [ ] `[P1]` **Human review of money/security code before it ships** (even with AI-speed development).

---

## Phasing
1. **Before any real money — all `[P0]`:** firehose split · queue + bulk ingest · pooling · real auth + RBAC ·
   secrets · money ledger · audit log · test suite · load test · staging · error tracking · HA Postgres ·
   restore drill · pen test.
2. **Ramp to full scale — `[P1]`:** replicas · partitioning · WebSockets · warehouse · observability ·
   containerization · CI/CD · migrations.
3. **Maturity — `[P2]`:** analytics warehouse · advanced DR · full IaC.

## Bottom line
Keep building features at 10x with AI. Work the `[P0]` list before real money. Buy a few weeks of one
senior infra/security engineer to implement + validate P0 — not a team, not a profit share. Start the P0
work with the **firehose split + ingestion pipeline**; those are what actually break at these numbers.

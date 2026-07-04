"""
sync_wati_attributes.py — one-shot bulk sync of ALL client contacts' attributes into Wati.

Upserts every client (by phone) via Wati addContact so each contact carries the correct attributes,
ESPECIALLY acd = the current owning agent (users.full_name via clients.assigned_agent_id; flips
sales->retention on deposit). New numbers are created fully populated; existing ones are updated.

Sends NO WhatsApp messages — attribute writes only. Re-runnable / idempotent.
Run in background:  python sync_wati_attributes.py [segment_key]   (default: clients_all)
Progress is printed and appended to sync_wati_attributes.log.
"""
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import text
from database import SessionLocal
from marketing_router import SEG_BY_KEY
import wati_attributes as WA

WORKERS = 10          # Wati rate-limits ~3-4/s server-side; more workers just cause 429s, no speedup
LOG = "sync_wati_attributes.log"


def _log(msg):
    line = time.strftime("%H:%M:%S ") + msg
    print(line, flush=True)
    try:
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass


def main():
    seg_key = sys.argv[1] if len(sys.argv) > 1 else "clients_all"
    seg = SEG_BY_KEY.get(seg_key)
    if not seg:
        _log(f"unknown segment {seg_key}"); return

    db = SessionLocal()
    ep_tok = db.execute(text("SELECT api_endpoint, api_token FROM wati_config WHERE id=1")).fetchone()
    ep = (ep_tok[0] or "").rstrip("/"); tok = ep_tok[1] or ""
    _log(f"loading rows for segment '{seg['label']}' …")
    rows = WA._rows_for_segment(db, seg)

    # dedup by normalized phone
    seen, jobs = set(), []
    for r in rows:
        ph = WA._norm_phone(r[0])
        if ph and ph not in seen:
            seen.add(ph); jobs.append(r)
    total = len(jobs)
    _log(f"{total:,} unique client phones to upsert (workers={WORKERS})")

    stats = {"ok": 0, "failed": 0, "done": 0}
    t0 = time.time()

    def do(row):
        ph = WA._norm_phone(row[0])
        disp, params = WA.build_attrs(row)
        ok, detail = WA.push_contact(ep, tok, ph, disp, params)
        if not ok:                              # retry once (usually a transient 429) with backoff
            time.sleep(1.0)
            ok, detail = WA.push_contact(ep, tok, ph, disp, params)
        stats["done"] += 1
        if ok:
            stats["ok"] += 1
        else:
            stats["failed"] += 1
        if stats["done"] % 500 == 0 or stats["done"] == total:
            rate = stats["done"] / max(1e-6, time.time() - t0)
            eta = (total - stats["done"]) / max(1e-6, rate)
            _log(f"  {stats['done']:,}/{total:,}  ok={stats['ok']:,} fail={stats['failed']:,}  "
                 f"{rate:.0f}/s  eta {eta/60:.0f}m")
        time.sleep(0.04)

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        list(ex.map(do, jobs))

    _log(f"DONE — {stats['ok']:,} upserted, {stats['failed']:,} failed, in {(time.time()-t0)/60:.1f} min")
    db.close()


if __name__ == "__main__":
    main()

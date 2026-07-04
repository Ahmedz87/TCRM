"""Run the v3 abuse engine and print a summary. Usage: python run_abuse.py [--keep]
Clears prior cases by default (detection output is regenerated, not precious data).
Safe: read-only on trading data; writes only abuse_cases + is_islamic. No auto-freeze."""
import sys, time, json
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from database import SessionLocal
from abuse_engine import run_engine, ensure_schema
from sqlalchemy import text

db = SessionLocal()
try:
    ensure_schema(db)
    if "--keep" not in sys.argv:
        db.execute(text("DELETE FROM abuse_cases WHERE status NOT IN ('resolved','frozen')"))
        db.commit()
        print("cleared prior open cases")

    t0 = time.time()
    print("Running abuse engine v3 (scans ~4M deals)...")
    res = run_engine(db)
    print(f"\nDone in {time.time()-t0:.0f}s:")
    for k, v in res.items():
        print(f"   {k:<16} -> {v}")

    print("\nCases by type / severity:")
    for r in db.execute(text("""
        SELECT abuse_type, severity, count(*), round(sum(exposure)::numeric,0)
        FROM abuse_cases GROUP BY abuse_type, severity ORDER BY abuse_type, severity
    """)).fetchall():
        print(f"   {r[0]:<15} {r[1]:<9} {r[2]:>4}   exposure ${float(r[3] or 0):,.0f}")

    tot = db.execute(text("""
        SELECT count(*), count(*) FILTER (WHERE severity='critical'),
               count(*) FILTER (WHERE severity='high'), count(*) FILTER (WHERE severity='medium')
        FROM abuse_cases
    """)).fetchone()
    print(f"\nTOTAL {tot[0]} cases  |  critical {tot[1]}  high {tot[2]}  medium {tot[3]}")

    print("\nSample structured evidence (one bonus_ring or chip_dump):")
    row = db.execute(text("""
        SELECT abuse_type, login_a, evidence_json FROM abuse_cases
        WHERE abuse_type IN ('bonus_ring','chip_dump') ORDER BY risk_score DESC LIMIT 1
    """)).fetchone()
    if row:
        ev = json.loads(row[2])
        print(f"   [{row[0]} #{row[1]}] {ev['headline']}")
        print("   signals:")
        for s in ev["signals"]:
            print(f"      {'✓' if s['hit'] else '·'} {s['label']} (+{s['weight'] if s['hit'] else 0}) — {s['detail']}")
        print(f"   proof_pairs: {len(ev.get('proof_pairs',[]))}  money_flow: {ev.get('money_flow')}")
finally:
    db.close()

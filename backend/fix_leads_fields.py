"""
fix_leads_fields.py — backfill the TradeSoft leads we imported with the REAL fields from
fx_leads_view (city, real registration date, source, stage, sales agent, IB) instead of
name+country+today. phone/email stay empty (not present anywhere in the legacy mirror).
Batched + retry so it coexists with the live meta-lead writers.
"""
import time
from sqlalchemy import text
from database import SessionLocal
L = "tradesoft_old"


def run():
    db = SessionLocal()
    try:
        for col in ("legacy_sales_agent text", "legacy_ib text", "legacy_source text", "legacy_stage text"):
            db.execute(text(f"ALTER TABLE leads ADD COLUMN IF NOT EXISTS {col.split()[0]} {col.split()[1]}"))
        db.commit()

        # materialize the real values per imported lead (read-only)
        db.execute(text(f"""CREATE TEMP TABLE lead_fix AS
          SELECT l.id,
            NULLIF(lv.city,'') city, NULLIF(lv.country,'') country,
            NULLIF(lv.created_at,'')::timestamptz reg,
            NULLIF(lv.source,'') src, NULLIF(lv.stage_id,'') stg,
            sr.nm sales, ib.nm ibname, NULLIF(lv.message,'') msg
          FROM leads l
          JOIN customers cu ON cu.customer_no=l.customer_no
          JOIN (SELECT DISTINCT ON (user_id) user_id, country, city, source, stage_id, sales_rep,
                       created_at, message FROM {L}.fx_leads_view WHERE deleted_at IS NULL
                ORDER BY user_id, created_at) lv ON lv.user_id=cu.legacy_user_id
          LEFT JOIN (SELECT DISTINCT ON (id) id, NULLIF(trim(COALESCE(name,'')||' '||COALESCE(surname,'')),'') nm
                     FROM {L}.fx_users_view ORDER BY id) sr ON sr.id=lv.sales_rep
          LEFT JOIN (SELECT DISTINCT ON (u.id) u.id, su.nm FROM {L}.fx_users_view u
                     LEFT JOIN (SELECT DISTINCT ON (id) id, NULLIF(trim(COALESCE(name,'')||' '||COALESCE(surname,'')),'') nm
                                FROM {L}.fx_users_view ORDER BY id) su
                       ON su.id=COALESCE(NULLIF(u.referrer_id,''), NULLIF(u.invited_by,''))
                     ORDER BY u.id) ib ON ib.id=cu.legacy_user_id
          WHERE l.source='tradesoft'"""))
        db.execute(text("CREATE INDEX ON lead_fix(id)"))
        db.commit()
        ids = [r[0] for r in db.execute(text("SELECT id FROM lead_fix")).fetchall()]
        print(f"leads to fix: {len(ids):,}")

        sql = """UPDATE leads l SET
            city=f.city, country=COALESCE(f.country,l.country),
            created_at=COALESCE(f.reg,l.created_at),
            legacy_source=f.src, legacy_stage=f.stg,
            legacy_sales_agent=f.sales, legacy_ib=f.ibname,
            notes=NULLIF(concat_ws(' | ',
                CASE WHEN f.sales IS NOT NULL THEN 'Sales: '||f.sales END,
                CASE WHEN f.ibname IS NOT NULL THEN 'IB: '||f.ibname END,
                CASE WHEN f.src IS NOT NULL THEN 'src#'||f.src END,
                CASE WHEN f.stg IS NOT NULL THEN 'stage#'||f.stg END,
                f.msg),'')
          FROM lead_fix f WHERE f.id=l.id AND l.id=ANY(:ids)"""
        done = 0
        for i in range(0, len(ids), 3000):
            batch = ids[i:i+3000]
            for attempt in range(8):
                try:
                    db.execute(text("SET lock_timeout='4s'"))
                    done += db.execute(text(sql), {"ids": batch}).rowcount
                    db.commit(); break
                except Exception:
                    db.rollback()
                    if attempt == 7: raise
                    time.sleep(1.5*(attempt+1))
        print(f"leads fixed: {done:,}")

        r = db.execute(text("""SELECT count(*) FILTER (WHERE city IS NOT NULL),
            count(*) FILTER (WHERE legacy_sales_agent IS NOT NULL),
            count(*) FILTER (WHERE legacy_ib IS NOT NULL),
            min(created_at), max(created_at)
            FROM leads WHERE source='tradesoft'""")).fetchone()
        print(f"  with city {r[0]:,} | with sales agent {r[1]:,} | with IB {r[2]:,}")
        print(f"  registration dates now span: {r[3]} .. {r[4]}")
    finally:
        db.close()


if __name__ == "__main__":
    run()

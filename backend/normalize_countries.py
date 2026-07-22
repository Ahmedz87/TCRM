"""
normalize_countries.py — display-friendly country names across the CRM.

TradeSoft / registration store the full ISO-3166 names ("Syrian Arab Republic",
"Iran, Islamic Republic of", ...) which are too long for the table columns. The desk wants the
short common form shown everywhere. Every page reads the `country` column straight from the DB,
so normalizing the stored value fixes all pages at once (Clients, Leads, Trading Accounts,
Transactions, IB, Network, portal, ...).

Idempotent + additive: only rewrites the verbose forms in the map below, trims stray whitespace.
Runs across clients, leads, customers, trading_accounts. Safe to run repeatedly; also called at
the end of each tradesoft_sync cycle so new imports stay normalized.

Run:  python normalize_countries.py            (apply)
      python normalize_countries.py --dry-run  (report only)
"""
import sys
from sqlalchemy import text
from database import SessionLocal

# verbose ISO name (lowercased, trimmed) -> short display name.
# DEFAULT: only the country the desk explicitly asked to shorten (Syria).
MAP = {
    "syrian arab republic": "Syria",
}

# Optional wider set of verbose ISO names, applied only with --extended (other long names the
# desk may want shortened later). Kept opt-in so we never rewrite country values nobody asked for.
EXTENDED = {
    "iran, islamic republic of": "Iran",
    "iran (islamic republic of)": "Iran",
    "palestine, state of": "Palestine",
    "palestinian territory, occupied": "Palestine",
    "russian federation": "Russia",
    "united arab emirates": "UAE",
    "united kingdom": "UK",
    "united states": "USA",
    "united states of america": "USA",
    "germany (deutschland)": "Germany",
    "tanzania, united republic of": "Tanzania",
    "venezuela, bolivarian republic of": "Venezuela",
    "taiwan, province of china": "Taiwan",
    "congo, the democratic republic of the": "DR Congo",
    "lao people's democratic republic": "Laos",
    "brunei darussalam": "Brunei",
    "korea, republic of": "South Korea",
    "moldova, republic of": "Moldova",
    "bolivia, plurinational state of": "Bolivia",
    "libyan arab jamahiriya": "Libya",
    "viet nam": "Vietnam",
}

TABLES = ("clients", "leads", "customers", "trading_accounts")


def install_trigger(extended=False):
    """Install a BEFORE INSERT/UPDATE trigger that normalizes country on EVERY write, from ANY
    source. Needed because the live MT bridge re-writes clients.country from MT every 30s (with the
    verbose ISO name), which clobbers a one-time UPDATE. The trigger makes 'Syria' stick permanently
    across all writers (bridge, TradeSoft sync, portal) and therefore all pages — no service restart.
    Guarded with a short lock_timeout + retry so it coexists with the bridge's frequent writes."""
    import time
    mapping = dict(MAP)
    if extended:
        mapping.update(EXTENDED)
    # build the CASE body: lower(trim(country)) -> short
    whens = "\n".join(
        f"    WHEN lower(trim(NEW.country)) = {_sql_lit(v)} THEN NEW.country := {_sql_lit(s)};"
        for v, s in mapping.items())
    fn = f"""
    CREATE OR REPLACE FUNCTION normalize_country_tg() RETURNS trigger AS $$
    BEGIN
      IF NEW.country IS NOT NULL THEN
        CASE
{whens}
          ELSE NULL;
        END CASE;
      END IF;
      RETURN NEW;
    END; $$ LANGUAGE plpgsql;
    """
    db = SessionLocal()
    try:
        db.execute(text(fn)); db.commit()
        print("normalize_country_tg() function ready")
        for tbl in TABLES:
            has = db.execute(text(
                "SELECT 1 FROM information_schema.columns WHERE table_name=:t AND column_name='country'"
            ), {"t": tbl}).scalar()
            if not has:
                continue
            for attempt in range(8):
                try:
                    db.execute(text("SET lock_timeout='4s'"))
                    db.execute(text(f"DROP TRIGGER IF EXISTS trg_normalize_country ON {tbl}"))
                    db.execute(text(
                        f"CREATE TRIGGER trg_normalize_country BEFORE INSERT OR UPDATE ON {tbl} "
                        f"FOR EACH ROW EXECUTE FUNCTION normalize_country_tg()"))
                    db.execute(text("RESET lock_timeout")); db.commit()
                    print(f"  trigger installed on {tbl}")
                    break
                except Exception as e:
                    db.rollback()
                    if attempt == 7:
                        print(f"  trigger on {tbl} FAILED after retries: {e}"); break
                    time.sleep(1.5 * (attempt + 1))
    finally:
        db.close()


def _sql_lit(s):
    return "'" + str(s).replace("'", "''") + "'"


def run(dry=False, extended=False):
    mapping = dict(MAP)
    if extended:
        mapping.update(EXTENDED)
    db = SessionLocal()
    total = 0
    try:
        for tbl in TABLES:
            # skip tables that don't have a country column
            has = db.execute(text(
                "SELECT 1 FROM information_schema.columns WHERE table_name=:t AND column_name='country'"
            ), {"t": tbl}).scalar()
            if not has:
                continue
            # 1) trim stray whitespace so ' Syria' collapses to 'Syria'
            if not dry:
                db.execute(text(f"UPDATE {tbl} SET country=trim(country) "
                                f"WHERE country IS NOT NULL AND country <> trim(country)"))
                db.commit()
            # 2) rewrite each verbose form -> short
            for verbose, short in mapping.items():
                cnt = db.execute(text(
                    f"SELECT count(*) FROM {tbl} WHERE lower(trim(country)) = :v"
                ), {"v": verbose}).scalar() or 0
                if cnt and not dry:
                    db.execute(text(f"UPDATE {tbl} SET country=:s WHERE lower(trim(country)) = :v"),
                               {"s": short, "v": verbose})
                    db.commit()
                if cnt:
                    total += cnt
                    print(f"  {tbl}: {cnt:,} '{short}' (was '{verbose}')")
        print(f"\n{'WOULD normalize' if dry else 'Normalized'} {total:,} row(s).")
    finally:
        db.close()


if __name__ == "__main__":
    ext = "--extended" in sys.argv
    if "--install-trigger" in sys.argv:
        install_trigger(extended=ext)          # make it stick against live writers (the MT bridge)
    run(dry="--dry-run" in sys.argv, extended=ext)   # then backfill existing rows

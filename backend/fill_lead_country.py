"""
fill_lead_country.py — derive leads.country from the phone's international calling code.

Meta lead forms for TNFX don't capture country, but the phone numbers carry it
(+963 Syria, +964 Iraq, +90 Turkey, +966 KSA, +20 Egypt, ...). We match the
LONGEST calling-code prefix on the digits-only phone and set leads.country.

Idempotent and additive: only fills rows where country is currently empty
(pass --all to overwrite every row). Run:  python fill_lead_country.py
"""
import sys, re
import db_config
import psycopg2

DB = dict(host=db_config.DB_HOST, port=db_config.DB_PORT, dbname=db_config.DB_NAME, user=db_config.DB_USER, password=db_config.DB_PASSWORD)

# International calling code -> country name. Ordered longest-first at match time.
# Covers the MENA region these leads come from, plus common diaspora destinations.
CODES = {
    "963": "Syria", "964": "Iraq", "966": "Saudi Arabia", "971": "UAE",
    "965": "Kuwait", "968": "Oman", "973": "Bahrain", "974": "Qatar",
    "962": "Jordan", "961": "Lebanon", "970": "Palestine", "967": "Yemen",
    "20": "Egypt", "212": "Morocco", "213": "Algeria", "216": "Tunisia",
    "218": "Libya", "249": "Sudan", "222": "Mauritania", "252": "Somalia",
    "98": "Iran", "90": "Turkey", "93": "Afghanistan", "92": "Pakistan",
    "91": "India", "880": "Bangladesh", "234": "Nigeria", "27": "South Africa",
    "1": "USA/Canada", "44": "UK", "49": "Germany", "33": "France",
    "31": "Netherlands", "46": "Sweden", "7": "Russia", "994": "Azerbaijan",
    "995": "Georgia", "996": "Kyrgyzstan", "60": "Malaysia", "62": "Indonesia",
}
# match the longest codes first so e.g. 962 (Jordan) wins over 9 / 96
CODES_SORTED = sorted(CODES.items(), key=lambda kv: -len(kv[0]))


def country_for(phone: str):
    digits = re.sub(r"[^0-9]", "", phone or "")
    if not digits:
        return None
    # strip a leading 00 international prefix if present
    if digits.startswith("00"):
        digits = digits[2:]
    for code, name in CODES_SORTED:
        if digits.startswith(code):
            return name
    return None


def main():
    overwrite = "--all" in sys.argv
    conn = psycopg2.connect(**DB)
    cur = conn.cursor()
    where = "" if overwrite else "WHERE COALESCE(country,'') = ''"
    cur.execute(f"SELECT id, phone FROM leads {where}")
    rows = cur.fetchall()
    updates, unknown = [], 0
    for lid, phone in rows:
        ctry = country_for(phone)
        if ctry:
            updates.append((ctry, lid))
        else:
            unknown += 1
    for ctry, lid in updates:
        cur.execute("UPDATE leads SET country = %s WHERE id = %s", (ctry, lid))
    conn.commit()

    cur.execute("SELECT country, COUNT(*) FROM leads WHERE COALESCE(country,'')<>'' GROUP BY country ORDER BY 2 DESC")
    print(f"Updated {len(updates)} lead(s); {unknown} unresolved (no/odd phone).")
    print("Country distribution now:")
    for ctry, n in cur.fetchall():
        print(f"   {ctry:<16} {n}")
    conn.close()


if __name__ == "__main__":
    main()

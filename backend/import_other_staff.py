"""Import the NON-sales employees (Customer Care, Back Office, Validation, VPS, Admin)
with a department + role. Sales/Retention are left untouched (handled by import_sales_team.py).
Skips test accounts. ON CONFLICT email -> DO NOTHING (never overwrites existing users)."""
from sqlalchemy import text
from database import SessionLocal
from auth import get_password_hash

DEFAULT_PASSWORD = "Tnffx@2026"   # shared temp; users must change on first login

# (full_name, email, phone, title, location, department, role)
STAFF = [
    # ── Customer Care ───────────────────────────────────────────────
    ("Aqeel Kareem",    "aqeel.kareem@tnfx.co", "964782233111111", "Sales Quality",     "Baghdad", "Customer Care", "customer_care"),
    ("Ahmed Ameen",     "ahmadamen@tnfx.co",    "971562939323",    "Marketing Video",   "Dubai",   "Customer Care", "customer_care"),
    ("Yousif Saoud",    "yousefs@tnfx.co",      "",                 "",                  "",        "Customer Care", "customer_care"),
    ("Ali",             "alir@tnfx.co",         "",                 "",                  "",        "Customer Care", "customer_care"),
    ("Alaa",            "alaaa@tnfx.co",        "",                 "",                  "",        "Customer Care", "customer_care"),
    ("Fater",           "fater@tnfx.co",        "",                 "",                  "",        "Customer Care", "customer_care"),
    ("Hadeel",          "hadeelm@tnfx.co",      "9646789665160",   "",                  "",        "Customer Care", "customer_care"),
    ("Jafar",           "jafarj@tnfx.co",       "",                 "",                  "",        "Customer Care", "customer_care"),
    ("Bashar",          "bashar@tnfx.co",       "",                 "",                  "",        "Customer Care", "customer_care"),
    ("Saied Homsi",     "saiedh@tnfx.co",       "963992000608",    "",                  "",        "Customer Care", "customer_care"),
    ("Salam",           "salamy@tnfx.co",       "96407713148069",  "Basra Branch",      "Basra",   "Customer Care", "customer_care"),
    ("Danya",           "daniaa@tnfx.co",       "96407811107555",  "Basra Branch",      "Basra",   "Customer Care", "customer_care"),
    ("Zahra Abbas",     "zahraaa@tnfx.co",      "9647518999282",   "",                  "Baghdad", "Customer Care", "customer_care"),
    ("Bakera",          "bakera@tnfx.co",       "",                 "",                  "",        "Customer Care", "customer_care"),
    ("Sheikha Mohammed","sheikha@tnfx.co",      "9715640007699",   "",                  "Dubai",   "Customer Care", "customer_care"),
    ("Saleema Sabir",   "saleema@tnfx.co",      "97155647702",     "",                  "",        "Customer Care", "customer_care"),
    ("Firas Ahmed",     "firasa@tnfx.co",       "91859651020",     "",                  "",        "Customer Care", "customer_care"),
    ("Rabab",           "rababn@tnfx.co",       "96407829493784",  "Basra Branch",      "Basra",   "Customer Care", "customer_care"),
    # ── Back Office ─────────────────────────────────────────────────
    ("Hussein Ali",     "hussain@tnfx.co",      "9647812000000000","",                  "Baghdad", "Back Office", "backoffice"),
    ("Matt",            "matt@tnfx.co",         "9715188888888",   "",                  "Dubai",   "Back Office", "backoffice"),
    ("Jenina",          "jenina@tnfx.co",       "97151999999999900","",                 "Dubai",   "Back Office", "backoffice"),
    ("Taha",            "tahab@tnfx.co",        "9647751500272",   "",                  "",        "Back Office", "backoffice"),
    ("Mustafa Mohammed","mustafam@tnfx.co",     "9647716197600",   "Basra Branch",      "Basra",   "Back Office", "backoffice"),
    ("Mustafa Farouq",  "mustafaf@tnfx.co",     "",                 "",                  "",        "Back Office", "backoffice"),
    ("Ibrahim Murshed", "ibrahimm@tnfx.co",     "911234567890",    "",                  "",        "Back Office", "backoffice"),
    ("Ihsan Ali",       "ihsana@tnfx.co",       "",                 "Baghdad Branch",    "Baghdad", "Back Office", "backoffice"),
    ("Ahmed Asaad",     "ahmedas@tnfx.co",      "9647838800040",   "",                  "",        "Back Office", "backoffice"),
    ("Jwan",            "jwanf@tnfx.co",        "9647711031373",   "Baghdad Branch",    "Baghdad", "Back Office", "backoffice"),
    ("Mohammed Majed",  "mohammedm@tnfx.co",    "9647818886941",   "",                  "",        "Back Office", "backoffice"),
    ("Marwan",          "marwanf@tnfx.co",      "9711122334455",   "",                  "",        "Back Office", "backoffice"),
    # ── Validation ──────────────────────────────────────────────────
    ("Mohamad Gdid",    "mohamad.gdid@tnfx.co", "963930783416",    "",                  "",        "Validation", "validation"),
    ("Yasamen",         "yasamenm@tnfx.co",     "96407728127534",  "Baghdad Branch",    "Baghdad", "Validation", "validation"),
    ("Russul",          "russuln@tnfx.co",      "9647734635547",   "",                  "",        "Validation", "validation"),
    # ── VPS ─────────────────────────────────────────────────────────
    ("Zainab",          "zainabwmh@tnfx.co",    "",                 "",                  "",        "VPS", "vps"),
    ("Arnold De",       "arnold@tnfx.co",       "971524095055",    "VPS",               "",        "VPS", "vps"),
    ("Zainab",          "zainabw@tnfx.co",      "9647735169330",   "",                  "",        "VPS", "vps"),
    ("Maha",            "mahak@tnfx.co",        "91123456789",     "",                  "",        "VPS", "vps"),
    # ── Admin / Management ──────────────────────────────────────────
    ("Nuha",            "nuha@tnfx.co",         "964781983853500", "",                  "",        "Management", "admin"),
    ("Rav sam",         "rahaf@tnfx.co",        "9647903216971",   "Relationship Manager","Baghdad","Management", "admin"),
    ("Abbas K",         "abbask@tnfx.co",       "",                 "",                  "",        "Management", "admin"),
    ("Ahmed Zaman",     "ahmedz@tnfx.co",       "",                 "",                  "",        "Management", "admin"),
    ("TNFX",            "support@tnfx.co",      "",                 "N/A",               "",        "Management", "admin"),
    ("Narmeen",         "narmeena@tnfx.co",     "9647518999290",   "Director of Sales", "Baghdad", "Management", "admin"),
]

def run():
    db = SessionLocal()
    pw = get_password_hash(DEFAULT_PASSWORD)
    inserted = skipped = 0
    skipped_emails = []
    try:
        for full_name, email, phone, title, loc, dept, role in STAFF:
            email = email.strip().lower()
            res = db.execute(text("""
                INSERT INTO users (full_name, email, phone, role, title, department,
                                   hashed_password, is_active, language,
                                   must_change_password, created_at)
                VALUES (:fn, :em, :ph, :role, :title, :dept, :pw, TRUE, 'en', TRUE, NOW())
                ON CONFLICT (email) DO NOTHING
                RETURNING id
            """), {"fn": full_name.strip(), "em": email, "ph": (phone.strip() or None),
                   "role": role, "title": (title.strip() or None), "dept": dept, "pw": pw})
            if res.fetchone():
                inserted += 1
            else:
                skipped += 1
                skipped_emails.append(email)
        db.commit()
        print(f"inserted={inserted} skipped(existing)={skipped} total={len(STAFF)}")
        if skipped_emails:
            print("skipped (already existed):", skipped_emails)
        print("\n-- by department/role --")
        for d, r, n in db.execute(text("""
            SELECT department, role, COUNT(*) FROM users
            WHERE department IS NOT NULL GROUP BY department, role ORDER BY 1,2""")):
            print(f"  {d:14} {r:14} {n}")
    finally:
        db.close()

if __name__ == "__main__":
    run()

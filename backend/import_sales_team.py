"""Import the TNFX sales-division staff as CRM users (profiles + email logins).
Hierarchy (manager_id) is set later when the team structure is provided.
Idempotent: upserts on email; does NOT reset an already-set password."""
from sqlalchemy import text
from database import SessionLocal
from auth import get_password_hash

DEFAULT_PASSWORD = "Tnffx@2026"   # shared temp; users must change on first login

# (full_name, phone, linkus/extension, email, previous_name, job_title)
STAFF = [
    ("Laveen",                  "9647721049080", "305", "laveen@tnfx.co",          "",                  "Director of Sales Division"),
    ("Aileen Yousif",           "971527483262",  "394", "aileen.yousif@tnfx.co",   "Farah Ahmed ghazi", "Relationship Manager"),
    ("Hammam Alkfari",          "971527435589",  "155", "hammama@tnfx.co",         "",                  "Relationship Manager"),
    ("Hiba Hasan",              "971529405369",  "172", "hibah@tnfx.co",           "",                  "Relationship Manager"),
    ("Rand Awad",               "971552441397",  "177", "randa@tnfx.co",           "",                  "Relationship Manager"),
    ("Ritta Alzeer",            "971522541747",  "144", "rittaa@tnfx.co",          "",                  "Relationship Manager"),
    ("Rahma Ahmed",             "971552441596",  "392", "rahma.ahmed@tnfx.co",     "Zahraa Tahseen",    "Relationship Manager"),
    ("Nur Abdulhalem",          "971522430809",  "174", "nur@tnfx.co",             "",                  "Relationship Manager"),
    ("Sarah Ali",               "971527882922",  "390", "sarah.ali@tnfx.co",       "Tabark Abbas",      "Relationship Manager"),
    ("Ahmad Alshamaa",          "971552439783",  "",    "ahmad.alshamaa@tnfx.co",  "",                  "Relationship Manager"),
    ("Ahmad Nadem",             "971526038545",  "401", "ahmadn@tnfx.co",          "",                  "Relationship Manager"),
    ("Ahmad Yousef",            "971527429198",  "",    "ahmad.yousef@tnfx.co",    "",                  "Relationship Manager"),
    ("Shari Sadoon Tawfiq",     "971521713269",  "",    "sharis@tnfx.co",          "",                  "Relationship Manager"),
    ("Samr Toomeh",             "971552439901",  "",    "samr@tnfx.co",            "",                  "Relationship Manager"),
    ("Alhadi Hasan Hasan",      "971552827951",  "",    "alhadi.hasan@tnfx.co",    "",                  "Sales Specialist"),
    ("Ali Mohamed saleh",       "971529405462",  "",    "alim@tnfx.co",            "",                  "Sales Specialist"),
    ("Assef Azdashir Dreykeshi","971552439809",  "",    "assef@tnfx.co",           "",                  "Sales Specialist"),
    ("Asyad Badoor",            "971524053982",  "171", "asyadb@tnfx.co",          "",                  "Sales Specialist"),
    ("Bara'a Asad Khashifi",    "971552439871",  "",    "baraa@tnfx.co",           "",                  "Sales Specialist"),
    ("Gada Ateah Naser",        "971559772609",  "",    "gadaa@tnfx.co",           "",                  "Sales Specialist"),
    ("Ghaith Saeed",            "971552827309",  "",    "ghaith.saeed@tnfx.co",    "",                  "Sales Specialist"),
    ("Mira Hussein",            "971552440657",  "406", "mira.hussein@tnfx.co",    "Ghazal Abbas",      "Sales Specialist"),
    ("Hadi Harfoush",           "971552827093",  "",    "hadi.harfoush@tnfx.co",   "",                  "Sales Specialist"),
    ("Haneen Jamal",            "971559958082",  "397", "haneenj@tnfx.co",         "",                  "Sales Specialist"),
    ("Mada Alhafi",             "971526447325",  "405", "yara.ahmad@tnfx.co",      "Yara Ahmad",        "Sales Specialist"),
    ("Maryam Mona",             "971526428318",  "191", "maryamm@tnfx.co",         "",                  "Sales Specialist"),
    ("Maya Asaad",              "971526382963",  "396", "mayaa@tnfx.co",           "",                  "Sales Specialist"),
    ("Modar Mannoun",           "971552827396",  "",    "modar.mannoun@tnfx.co",   "",                  "Sales Specialist"),
    ("Mohammad Hassan",         "971552439689",  "",    "mohammadh@tnfx.co",       "",                  "Sales Specialist"),
    ("Natalie Saeed",           "971525146856",  "192", "natalie@tnfx.co",         "",                  "Sales Specialist"),
    ("Nour Ali Kherbek",        "971521943732",  "173", "nourk@tnfx.co",           "",                  "Sales Specialist"),
    ("Oday Ghanem",             "971528854418",  "",    "odayg@tnfx.co",           "",                  "Sales Specialist"),
    ("Ola Zuhayra",             "971529405608",  "181", "olaz@tnfx.co",            "",                  "Sales Specialist"),
    ("Rabee ibrahem Shamaly",   "971527064380",  "",    "rabeei@tnfx.co",          "",                  "Sales Specialist"),
    ("Rama Sameer",             "971523073441",  "398", "ramas@tnfx.co",           "",                  "Sales Specialist"),
    ("Rasha Shbani",            "971527149774",  "190", "rashas@tnfx.co",          "",                  "Sales Specialist"),
    ("Rida Mohammad",           "971559697209",  "402", "ridam@tnfx.co",           "",                  "Sales Specialist"),
    ("Somar Saeed",             "971552441539",  "",    "somar.saeed@tnfx.co",     "",                  "Sales Specialist"),
    ("Yahia Ahmad Ibrahim",     "971527238536",  "",    "yahiaa@tnfx.co",          "",                  "Sales Specialist"),
    ("Youssef Bilal Ismail",    "971552827491",  "",    "youssef.bilal@tnfx.co",   "",                  "Sales Specialist"),
    ("Ola Moualla",             "971559689131",  "425", "ola.moualla@tnfx.co",     "",                  "Sales Specialist"),
    ("Eman Zayoud",             "971559592238",  "426", "eman.zayoud@tnfx.co",     "",                  "Sales Specialist"),
    ("Lena Alo",                "971559447689",  "427", "lena.alo@tnfx.co",        "",                  "Sales Specialist"),
    ("Ola Najdat Issa",         "971559902677",  "432", "ola.najdat@tnfx.co",      "",                  "Sales Specialist"),
    ("Batool Balleh",           "971521418527",  "428", "batool.balleh@tnfx.co",   "",                  "Sales Specialist"),
    ("Patricia Khoury",         "971527274150",  "429", "patricia.khoury@tnfx.co", "",                  "Sales Specialist"),
    ("Eezar Mahmod",            "971529405364",  "430", "eezar.mahmod@tnfx.co",    "",                  "Sales Specialist"),
    ("Nermen Aldaher",          "971525565000",  "431", "nermen.aldaher@tnfx.co",  "",                  "Sales Specialist"),
    ("Haidar Helweh",           "971522843387",  "133", "haidarh@tnfx.co",         "",                  "Team Leader"),
    ("Ayat Mehrez",             "971527977389",  "123", "ayatm@tnfx.co",           "",                  "Team Leader"),
    ("Areej Mohammed",          "971529405412",  "399", "areejm@tnfx.co",          "",                  "Team Leader"),
    ("Aseel Alaqaileh",         "971524769239",  "140", "aseela@tnfx.co",          "",                  "Team Leader"),
    ("Faicel Bedoui",           "971529405378",  "156", "faicelb@tnfx.co",         "",                  "Team Leader"),
    ("Haidarah Abdullah",       "971527430661",  "178", "haidarah@tnfx.co",        "",                  "Team Leader"),
    ("Sherin Kotb",             "971527032095",  "161", "sherink@tnfx.co",         "",                  "Team Leader"),
    ("Wael Shamaly",            "971523564088",  "175", "wael@tnfx.co",            "",                  "Sales Specialist"),
]

ROLE_MAP = {
    "Director of Sales Division": "director",
    "Team Leader":                "sales_manager",
    "Relationship Manager":       "sales_agent",
    "Sales Specialist":           "sales_agent",
}

def run():
    db = SessionLocal()
    pw = get_password_hash(DEFAULT_PASSWORD)
    inserted = updated = 0
    try:
        for full_name, phone, ext, email, prev, title in STAFF:
            email = email.strip().lower()
            ext = ext.strip() or None
            prev = prev.strip() or None
            role = ROLE_MAP.get(title.strip(), "sales_agent")
            res = db.execute(text("""
                INSERT INTO users (full_name, email, phone, extension, role, title,
                                   previous_name, hashed_password, is_active, language,
                                   must_change_password, created_at)
                VALUES (:fn, :em, :ph, :ext, :role, :title, :prev, :pw, TRUE, 'en', TRUE, NOW())
                ON CONFLICT (email) DO UPDATE SET
                    full_name=EXCLUDED.full_name, phone=EXCLUDED.phone,
                    extension=EXCLUDED.extension, role=EXCLUDED.role,
                    title=EXCLUDED.title, previous_name=EXCLUDED.previous_name,
                    is_active=TRUE, updated_at=NOW()
                RETURNING (xmax = 0) AS inserted
            """), {"fn": full_name.strip(), "em": email, "ph": phone.strip(),
                   "ext": ext, "role": role, "title": title.strip(), "prev": prev, "pw": pw})
            if res.scalar():
                inserted += 1
            else:
                updated += 1
        db.commit()
        print(f"Done. inserted={inserted} updated={updated} total={len(STAFF)}")
        for r, n in db.execute(text("SELECT role, COUNT(*) FROM users WHERE title IS NOT NULL GROUP BY role ORDER BY 1")):
            print(f"  {r}: {n}")
    finally:
        db.close()

if __name__ == "__main__":
    run()

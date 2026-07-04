"""Apply the sales-division team hierarchy (manager_id) + team_type from the org chart.
Director: Laveen. Sales Manager Ayat Mehrez -> TLs Ayat, Aseel, Haidarah.
Other TLs (Faicel, Sherin, Haidar, Areej) report directly to Laveen.
Idempotent. Run after import_sales_team.py."""
from sqlalchemy import text
from database import SessionLocal

DIRECTOR = "laveen@tnfx.co"

# team-leader email -> (manager_email, {retention:[names], sales:[names]})
TEAMS = {
    "faicelb@tnfx.co": (DIRECTOR, {
        "retention": ["Hammam Alkfari"],
        "sales": ["Ali Mohamed saleh", "Oday Ghanem", "Ola Moualla", "Eman Zayoud"],
    }),
    "sherink@tnfx.co": (DIRECTOR, {
        "retention": [],
        "sales": ["Mohammad Hassan", "Alhadi Hasan Hasan", "Patricia Khoury"],
    }),
    "haidarh@tnfx.co": (DIRECTOR, {
        "retention": ["Rand Awad", "Hiba Hasan", "Ola Zuhayra"],
        "sales": ["Wael Shamaly", "Rasha Shbani", "Asyad Badoor", "Natalie Saeed",
                  "Maryam Mona", "Nour Ali Kherbek"],
    }),
    "areejm@tnfx.co": (DIRECTOR, {
        "retention": ["Sarah Ali", "Rahma Ahmed", "Aileen Yousif", "Nur Abdulhalem", "Ahmad Nadem"],
        "sales": ["Mira Hussein", "Yara Ahmad", "Rama Sameer", "Maya Asaad", "Haneen Jamal",
                  "Rida Mohammad", "Yahia Ahmad", "Rabee ibrahem"],
    }),
    # Ayat is BOTH a Sales Manager and a Team Leader; her own team reports to her.
    "ayatm@tnfx.co": (DIRECTOR, {
        "retention": ["Ritta Alzeer", "Samr Toomeh"],
        "sales": ["Somar Saeed", "Lena Alo", "Batool Balleh", "Gada Ateah Naser"],
    }),
    "aseela@tnfx.co": ("ayatm@tnfx.co", {
        "retention": ["Ahmad Alshamaa"],
        "sales": ["Youssef Bilal Ismail", "Ghaith Saeed", "Modar Mannoun", "Eezar Mahmod", "Ola Najdat Issa"],
    }),
    "haidarah@tnfx.co": ("ayatm@tnfx.co", {
        "retention": ["Ahmad Yousef"],
        "sales": ["Assef Dreykeshi", "Bara'a Asad Khashifi", "Nermen Aldaher", "Hadi Harfoush"],
    }),
}

def run():
    db = SessionLocal()
    try:
        db.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS team_type VARCHAR"))
        db.commit()

        # load all staff users (title set by import)
        rows = db.execute(text("SELECT id, full_name, previous_name, email FROM users WHERE title IS NOT NULL")).fetchall()
        by_email = {r[3].lower(): r[0] for r in rows}
        # name resolver index
        users = [(r[0], (r[1] or "").strip().lower(), (r[2] or "").strip().lower()) for r in rows]

        def resolve(name):
            n = name.strip().lower()
            # 1 exact full_name or previous_name
            for uid, fn, pn in users:
                if n == fn or (pn and n == pn):
                    return uid
            # 2 full_name/prev starts with chart name or vice-versa
            for uid, fn, pn in users:
                if fn.startswith(n) or n.startswith(fn) or (pn and (pn.startswith(n) or n.startswith(pn))):
                    return uid
            # 3 token subset
            nt = set(n.split())
            best = None
            for uid, fn, pn in users:
                ft = set(fn.split())
                if nt and nt.issubset(ft):
                    best = uid
            return best

        unmatched = []
        assigned = set()
        # 1) team leaders -> their manager
        for tl_email, (mgr_email, _) in TEAMS.items():
            tl_id = by_email.get(tl_email)
            mgr_id = by_email.get(mgr_email)
            if tl_id and mgr_id:
                db.execute(text("UPDATE users SET manager_id=:m, team_type='lead' WHERE id=:i"),
                           {"m": mgr_id, "i": tl_id})
                assigned.add(tl_id)
        # director
        if DIRECTOR in by_email:
            db.execute(text("UPDATE users SET manager_id=NULL, team_type='director' WHERE id=:i"),
                       {"i": by_email[DIRECTOR]})
            assigned.add(by_email[DIRECTOR])
        # 2) agents -> their team leader + team_type
        for tl_email, (_, groups) in TEAMS.items():
            tl_id = by_email.get(tl_email)
            for ttype, names in groups.items():
                for name in names:
                    uid = resolve(name)
                    if not uid:
                        unmatched.append(name)
                        continue
                    db.execute(text("UPDATE users SET manager_id=:m, team_type=:t WHERE id=:i"),
                               {"m": tl_id, "t": ttype, "i": uid})
                    assigned.add(uid)
        db.commit()

        print(f"assigned {len(assigned)} of {len(rows)} staff")
        if unmatched:
            print("UNMATCHED chart names:", unmatched)
        # who is left without a manager (besides director)
        left = db.execute(text("""
            SELECT full_name, email, role, title FROM users
            WHERE title IS NOT NULL AND manager_id IS NULL AND role <> 'director'
        """)).fetchall()
        print("NO MANAGER (unassigned):", [(r[0], r[1]) for r in left] or "none")
        # tree summary
        print("\n-- manager -> direct reports --")
        for mid, mname in db.execute(text("SELECT id, full_name FROM users WHERE title IS NOT NULL ORDER BY full_name")):
            reps = db.execute(text("SELECT COUNT(*) FROM users WHERE manager_id=:i"), {"i": mid}).scalar()
            if reps:
                print(f"  {mname}: {reps} direct reports")
    finally:
        db.close()

if __name__ == "__main__":
    run()

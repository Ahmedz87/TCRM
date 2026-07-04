"""Link clients to their sales agent from Book1.xlsx (ACD column) -> clients.assigned_agent_id.
Match: Book1 phone (country code + number) vs clients.phone on last-9 digits.
Resolve ACD agent name -> users.id via full_name / previous_name / token match.
Idempotent."""
import csv, re
import openpyxl
from sqlalchemy import text
from database import SessionLocal

def digits(s):
    return re.sub(r"\D", "", s or "")

def run():
    db = SessionLocal()
    try:
        staff = db.execute(text("SELECT id, full_name, previous_name FROM users WHERE title IS NOT NULL")).fetchall()
        users = [(r[0], (r[1] or "").strip().lower(), (r[2] or "").strip().lower()) for r in staff]

        def resolve(name):
            n = name.strip().lower()
            if not n or n == "#n/a":
                return None
            for uid, fn, pn in users:
                if n == fn or (pn and n == pn):
                    return uid
            for uid, fn, pn in users:
                if fn.startswith(n) or n.startswith(fn) or (pn and (pn.startswith(n) or n.startswith(pn))):
                    return uid
            nt = set(n.split()); best = None
            for uid, fn, pn in users:
                if nt and nt.issubset(set(fn.split())):
                    best = uid
            return best

        # parse Book1 -> last9 -> agent_id
        wb = openpyxl.load_workbook("Book1.xlsx", data_only=True)
        ws = wb["Sheet1"]
        last9_to_agent = {}
        acd_counter = {}
        unresolved = {}
        rows = 0
        for row in ws.iter_rows(values_only=True):
            a = row[0]
            if a is None:
                continue
            fields = next(csv.reader([str(a)]))
            if len(fields) < 4:
                continue
            name, cc, phone, acd = fields[0], fields[1], fields[2], fields[3]
            if acd.strip().lower() in ("acd", ""):
                continue
            rows += 1
            agent_id = resolve(acd)
            acd_counter[acd.strip()] = acd_counter.get(acd.strip(), 0) + 1
            if not agent_id:
                unresolved[acd.strip()] = unresolved.get(acd.strip(), 0) + 1
                continue
            l9 = digits(cc) + digits(phone)
            l9 = l9[-9:]
            if len(l9) >= 8:
                last9_to_agent.setdefault(l9, agent_id)  # first wins

        print(f"book1 rows={rows}  unique phones mapped={len(last9_to_agent)}  acd names={len(acd_counter)}")
        if unresolved:
            print("UNRESOLVED ACD names:", sorted(unresolved.items(), key=lambda x:-x[1]))

        # temp table + single UPDATE join
        db.execute(text("DROP TABLE IF EXISTS _phone_agent"))
        db.execute(text("CREATE TEMP TABLE _phone_agent (last9 VARCHAR PRIMARY KEY, agent_id INT)"))
        items = list(last9_to_agent.items())
        for i in range(0, len(items), 1000):
            chunk = items[i:i+1000]
            db.execute(text("INSERT INTO _phone_agent (last9, agent_id) VALUES " +
                            ",".join(f"(:l{j},:a{j})" for j in range(len(chunk)))),
                       {f"l{j}": k for j,(k,v) in enumerate(chunk)} | {f"a{j}": v for j,(k,v) in enumerate(chunk)})
        db.commit()

        res = db.execute(text("""
            UPDATE clients c SET assigned_agent_id = pa.agent_id
            FROM _phone_agent pa
            WHERE RIGHT(regexp_replace(COALESCE(c.phone,''),'\\D','','g'),9) = pa.last9
        """))
        db.commit()
        print(f"clients updated (assigned_agent_id set) = {res.rowcount}")

        # report
        tot, assigned = db.execute(text("SELECT COUNT(*), COUNT(assigned_agent_id) FROM clients")).fetchone()
        print(f"clients total={tot} assigned={assigned} unassigned={tot-assigned}")
        print("\n-- top agents by linked clients --")
        for nm, n in db.execute(text("""
            SELECT u.full_name, COUNT(*) FROM clients c JOIN users u ON u.id=c.assigned_agent_id
            GROUP BY u.full_name ORDER BY 2 DESC LIMIT 12""")):
            print(f"  {n:>5}  {nm}")
    finally:
        db.close()

if __name__ == "__main__":
    run()

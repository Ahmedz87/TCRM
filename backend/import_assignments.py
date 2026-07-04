import sys
sys.path.insert(0, r'C:\broker-crm\backend')
from database import SessionLocal
from sqlalchemy import text
import openpyxl

db = SessionLocal()

# Parse Excel
wb = openpyxl.load_workbook(r'C:\broker-crm\backend\Book1.xlsx')
ws = wb.active

records = []
for i, row in enumerate(ws.iter_rows(values_only=True)):
    if i == 0: continue
    val = row[0]
    if not val: continue
    parts = str(val).split(',')
    if len(parts) >= 4:
        name = parts[0].strip()
        cc = parts[1].strip()
        phone = parts[2].strip()
        agent = parts[3].strip()
        if phone and agent and agent != '#N/A':
            records.append((name, cc, phone, agent))

print(f"Records to process: {len(records)}")

# Build agent name → user_id mapping
agent_map = {}
users = db.execute(text("SELECT id, full_name, email FROM users WHERE role IN ('sales_agent','sales_manager')")).fetchall()
for u in users:
    # Map by first name + last name variations
    full = u[1].lower().strip()
    agent_map[full] = u[0]
    # Also map first name only
    first = full.split()[0]
    if first not in agent_map:
        agent_map[first] = u[0]
    # First + second name
    parts = full.split()
    if len(parts) >= 2:
        agent_map[f"{parts[0]} {parts[1]}"] = u[0]

print(f"Agent map entries: {len(agent_map)}")

def find_agent_id(agent_name):
    n = agent_name.lower().strip()
    if n in agent_map: return agent_map[n]
    # Try partial match
    for key, uid in agent_map.items():
        if n in key or key in n:
            return uid
    return None

# Match clients by phone
matched = 0
assigned = 0
not_found_agents = set()

for name, cc, phone, agent_name in records:
    # Build full phone variations
    phone_clean = phone.strip().lstrip('0')
    full_phone = f"+{cc}{phone_clean}"
    alt_phone = f"+{cc}0{phone_clean}"

    # Find client in CRM by phone
    client = db.execute(text("""
        SELECT login FROM clients
        WHERE phone ILIKE :p1 OR phone ILIKE :p2
        OR phone LIKE :p3 OR phone LIKE :p4
        LIMIT 1
    """), {
        "p1": f"%{phone_clean}%",
        "p2": f"%{phone}%",
        "p3": f"%{phone_clean[-9:]}%",
        "p4": f"%{phone[-9:]}%"
    }).fetchone()

    if not client:
        continue
    matched += 1

    # Find agent
    agent_id = find_agent_id(agent_name)
    if not agent_id:
        not_found_agents.add(agent_name)
        continue

    # Update client assigned_agent_id
    db.execute(text("""
        UPDATE clients SET assigned_agent_id=:aid WHERE login=:l
    """), {"aid": agent_id, "l": client[0]})
    assigned += 1

    if assigned % 500 == 0:
        db.commit()
        print(f"  Assigned {assigned} clients...")

db.commit()
print(f"\n✅ Done!")
print(f"   Matched by phone: {matched:,}")
print(f"   Assigned to agent: {assigned:,}")
print(f"   Agents not found: {not_found_agents}")
db.close()

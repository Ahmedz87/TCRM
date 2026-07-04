import db_config
import psycopg2
c = db_config.connect().cursor()
c.execute("SELECT column_name FROM information_schema.columns WHERE table_name='users' ORDER BY ordinal_position")
print("users columns:", [r[0] for r in c.fetchall()])

# what does assigned_agent_id reference? sample a few clients with their agent
c.execute("SELECT id, name, agent, assigned_agent_id, kyc_status FROM clients WHERE id=13488")
print("Ziyad row:", c.fetchone())

# sample users
c.execute("SELECT * FROM users LIMIT 1")
cols = [d[0] for d in c.description]
print("users sample cols:", cols)

# distinct kyc_status values
c.execute("SELECT kyc_status, COUNT(*) FROM clients GROUP BY kyc_status ORDER BY 2 DESC LIMIT 10")
print("kyc_status values:", c.fetchall())

# does assigned_agent_id match users.id? check Ziyad's agent
c.execute("""SELECT u.* FROM users u JOIN clients c ON (c.assigned_agent_id = u.id OR CAST(c.agent AS TEXT)=CAST(u.id AS TEXT)) WHERE c.id=13488 LIMIT 1""")
row = c.fetchone()
print("Ziyad's manager via join:", row[:6] if row else "NO MATCH - agent link may be by name/code")

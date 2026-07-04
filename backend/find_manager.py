import db_config
import psycopg2
c = db_config.connect().cursor()

# 1. columns on clients that might point to an agent/manager
c.execute("""SELECT column_name FROM information_schema.columns 
             WHERE table_name='clients' AND (column_name ILIKE '%agent%' OR column_name ILIKE '%manager%' 
             OR column_name ILIKE '%sales%' OR column_name ILIKE '%assigned%' OR column_name ILIKE '%owner%' OR column_name ILIKE '%rep%')""")
print("client manager-ish columns:", [r[0] for r in c.fetchall()])

# 2. is there a users/agents/employees table?
c.execute("""SELECT table_name FROM information_schema.tables WHERE table_schema='public' 
             AND (table_name ILIKE '%agent%' OR table_name ILIKE '%user%' OR table_name ILIKE '%employee%' 
             OR table_name ILIKE '%staff%' OR table_name ILIKE '%manager%' OR table_name ILIKE '%sales%')""")
print("staff-ish tables:", [r[0] for r in c.fetchall()])

# 3. sample the clients columns fully so we can see what links exist
c.execute("SELECT column_name FROM information_schema.columns WHERE table_name='clients' ORDER BY ordinal_position")
print("ALL clients columns:", [r[0] for r in c.fetchall()])

# 4. check trading_accounts too
c.execute("SELECT column_name FROM information_schema.columns WHERE table_name='trading_accounts' ORDER BY ordinal_position")
print("ALL trading_accounts columns:", [r[0] for r in c.fetchall()])

"""
rebuild_network.py
Rebuilds network edges with new scoring:
- Same CID:              50pts
- Same IP:               35pts  
- Same name:             30pts
- Similar email pattern: 20pts (fuzzy match - 1-2 char difference)
- Same city:             15pts
- Same IB/agent:         10pts
"""
import sys
sys.path.insert(0, r'C:\broker-crm\backend')
from database import SessionLocal
from sqlalchemy import text

db = SessionLocal()

print("Clearing old network edges...")
db.execute(text("DELETE FROM network_edges"))
db.commit()

print("Building CID edges (same device)...")
r = db.execute(text("""
    INSERT INTO network_edges (login_a, login_b, reason, value)
    SELECT DISTINCT a.login, b.login, 'cid', a.identifier_value
    FROM account_identifiers a
    JOIN account_identifiers b ON a.identifier_value = b.identifier_value
        AND a.identifier_type = 'cid'
        AND b.identifier_type = 'cid'
        AND a.login < b.login
        AND a.identifier_value != '0'
        AND a.identifier_value != ''
    ON CONFLICT DO NOTHING
"""))
db.commit()
print(f"  CID edges: {r.rowcount:,}")

print("Building IP edges (same IP)...")
r = db.execute(text("""
    INSERT INTO network_edges (login_a, login_b, reason, value)
    SELECT DISTINCT a.login, b.login, 'ip', a.identifier_value
    FROM account_identifiers a
    JOIN account_identifiers b ON a.identifier_value = b.identifier_value
        AND a.identifier_type = 'ip'
        AND b.identifier_type = 'ip'
        AND a.login < b.login
    ON CONFLICT DO NOTHING
"""))
db.commit()
print(f"  IP edges: {r.rowcount:,}")

print("Building name edges (same full name)...")
r = db.execute(text("""
    INSERT INTO network_edges (login_a, login_b, reason, value)
    SELECT DISTINCT a.login, b.login, 'family', a.name
    FROM clients a
    JOIN clients b ON LOWER(TRIM(a.name)) = LOWER(TRIM(b.name))
        AND a.login < b.login
        AND a.name IS NOT NULL
        AND LENGTH(TRIM(a.name)) > 5
    ON CONFLICT DO NOTHING
"""))
db.commit()
print(f"  Name edges: {r.rowcount:,}")

print("Building similar email edges (fuzzy - 1-2 char difference)...")
r = db.execute(text("""
    INSERT INTO network_edges (login_a, login_b, reason, value)
    SELECT DISTINCT a.login, b.login, 'similar_email', a.email
    FROM clients a
    JOIN clients b ON a.login < b.login
        AND a.email IS NOT NULL AND b.email IS NOT NULL
        AND a.email != '' AND b.email != ''
        AND a.email != b.email
        AND LOWER(SPLIT_PART(a.email, '@', 2)) = LOWER(SPLIT_PART(b.email, '@', 2))
        AND (
            -- Same prefix up to last 3 chars (ahmed123 vs ahmed124)
            LOWER(SUBSTRING(SPLIT_PART(a.email,'@',1), 1, LENGTH(SPLIT_PART(a.email,'@',1))-2)) =
            LOWER(SUBSTRING(SPLIT_PART(b.email,'@',1), 1, LENGTH(SPLIT_PART(b.email,'@',1))-2))
            AND LENGTH(SPLIT_PART(a.email,'@',1)) BETWEEN 6 AND 30
            AND LENGTH(SPLIT_PART(b.email,'@',1)) BETWEEN 6 AND 30
        )
    ON CONFLICT DO NOTHING
"""))
db.commit()
print(f"  Similar email edges: {r.rowcount:,}")

print("Building same city edges...")
r = db.execute(text("""
    INSERT INTO network_edges (login_a, login_b, reason, value)
    SELECT DISTINCT
        LEAST(a.login, b.login),
        GREATEST(a.login, b.login),
        'city', a.city
    FROM clients a
    JOIN clients b ON LOWER(TRIM(a.city)) = LOWER(TRIM(b.city))
        AND a.login != b.login
        AND a.city IS NOT NULL
        AND LENGTH(TRIM(a.city)) > 2
        AND (
            -- Only link if they also share IB or have other connection
            a.agent = b.agent AND a.agent > 0
        )
    ON CONFLICT DO NOTHING
    LIMIT 500000
"""))
db.commit()
print(f"  City+IB edges: {r.rowcount:,}")

print("Building IB edges (same IB agent)...")
r = db.execute(text("""
    INSERT INTO network_edges (login_a, login_b, reason, value)
    SELECT DISTINCT
        LEAST(a.login, b.login),
        GREATEST(a.login, b.login),
        'ib', CAST(a.agent AS TEXT)
    FROM clients a
    JOIN clients b ON a.agent = b.agent
        AND a.login != b.login
        AND a.agent > 0
    ON CONFLICT DO NOTHING
    LIMIT 200000
"""))
db.commit()
print(f"  IB edges: {r.rowcount:,}")

# Now recalculate network scores for all clients
print("\nRecalculating network scores...")
db.execute(text("""
    UPDATE clients c SET network_score = sub.score
    FROM (
        SELECT login, MIN(100, SUM(pts)) as score FROM (
            SELECT login_a as login,
                CASE reason
                    WHEN 'cid'           THEN 50
                    WHEN 'ip'            THEN 35
                    WHEN 'family'        THEN 30
                    WHEN 'similar_email' THEN 20
                    WHEN 'city'          THEN 15
                    WHEN 'ib'            THEN 10
                    ELSE 5
                END as pts
            FROM network_edges
            UNION ALL
            SELECT login_b as login,
                CASE reason
                    WHEN 'cid'           THEN 50
                    WHEN 'ip'            THEN 35
                    WHEN 'family'        THEN 30
                    WHEN 'similar_email' THEN 20
                    WHEN 'city'          THEN 15
                    WHEN 'ib'            THEN 10
                    ELSE 5
                END as pts
            FROM network_edges
        ) x GROUP BY login
    ) sub
    WHERE c.login = sub.login
"""))
db.commit()
print("Network scores updated!")

total = db.execute(text("SELECT COUNT(*) FROM network_edges")).scalar()
scored = db.execute(text("SELECT COUNT(*) FROM clients WHERE network_score > 0")).scalar()
print(f"\n✅ Done!")
print(f"   Total edges: {total:,}")
print(f"   Clients with network score: {scored:,}")

db.close()

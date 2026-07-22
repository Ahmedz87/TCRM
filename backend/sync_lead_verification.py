"""One-off: upgrade lead phone/email/KYC verification from TradeSoft's live flags
(fx_users_view.mobile_verify / email_verified_at / is_kyc_verified). Batched so it never
holds a long lock on `leads`. Same logic phase3 now runs each sync."""
import db_config

conn = db_config.connect(); conn.autocommit = True; cur = conn.cursor()
cur.execute("CREATE INDEX IF NOT EXISTS ix_fxusers_id ON tradesoft_old.fx_users_view(id)")

cur.execute("""
  SELECT l.id FROM leads l JOIN customers cu ON l.customer_no=cu.customer_no
    JOIN tradesoft_old.fx_users_view u ON u.id=cu.legacy_user_id
  WHERE (TRIM(u.mobile_verify)='1' OR TRIM(u.is_kyc_verified)='1'
         OR (COALESCE(TRIM(u.email_verified_at),'')<>'' AND u.email_verified_at NOT ILIKE '%%0000-00-00%%'))
    AND NOT (COALESCE(l.phone_verified,FALSE) AND COALESCE(l.email_verified,FALSE) AND l.kyc_status='verified')
""")
ids = [r[0] for r in cur.fetchall()]
print(f"{len(ids)} leads to upgrade")

UPD = """
  UPDATE leads l SET
    phone_verified = CASE WHEN TRIM(u.mobile_verify)='1' THEN TRUE ELSE l.phone_verified END,
    email_verified = CASE WHEN COALESCE(TRIM(u.email_verified_at),'')<>''
                           AND u.email_verified_at NOT ILIKE '%%0000-00-00%%' THEN TRUE ELSE l.email_verified END,
    kyc_status     = CASE WHEN TRIM(u.is_kyc_verified)='1' THEN 'verified' ELSE l.kyc_status END,
    is_verified    = CASE WHEN TRIM(u.mobile_verify)='1'
                           AND COALESCE(TRIM(u.email_verified_at),'')<>'' THEN TRUE ELSE l.is_verified END
  FROM customers cu JOIN tradesoft_old.fx_users_view u ON u.id=cu.legacy_user_id
  WHERE l.customer_no=cu.customer_no AND l.id = ANY(%s)
"""
done = 0
CH = 3000
for i in range(0, len(ids), CH):
    batch = ids[i:i+CH]
    cur.execute(UPD, (batch,))
    done += cur.rowcount
    if (i // CH) % 5 == 0:
        print(f"  {done}/{len(ids)}")
print(f"DONE upgraded {done} leads")
conn.close()

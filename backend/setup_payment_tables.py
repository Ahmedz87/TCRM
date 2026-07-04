import db_config
import psycopg2
conn = db_config.connect()
c = conn.cursor()
c.execute("""CREATE TABLE IF NOT EXISTS payment_methods (
    id SERIAL PRIMARY KEY, code VARCHAR(40) UNIQUE NOT NULL, name VARCHAR(80) NOT NULL,
    logo VARCHAR(40) DEFAULT 'generic', kind VARCHAR(10) NOT NULL DEFAULT 'manual', provider VARCHAR(40) DEFAULT '',
    blurb VARCHAR(160) DEFAULT '', fee VARCHAR(20) DEFAULT '0%', processing_time VARCHAR(40) DEFAULT '',
    is_active BOOLEAN DEFAULT TRUE, deposit_enabled BOOLEAN DEFAULT TRUE, withdraw_enabled BOOLEAN DEFAULT TRUE,
    min_deposit NUMERIC DEFAULT 10, max_deposit NUMERIC, min_withdraw NUMERIC DEFAULT 50, max_withdraw NUMERIC DEFAULT 100000,
    allow_countries JSONB DEFAULT '[]', block_countries JSONB DEFAULT '[]', manual_details JSONB DEFAULT '{}',
    env_keys JSONB DEFAULT '[]', api_config JSONB DEFAULT '{}', sort_order INT DEFAULT 100,
    created_at TIMESTAMP DEFAULT NOW(), updated_at TIMESTAMP DEFAULT NOW())""")
c.execute("""CREATE TABLE IF NOT EXISTS account_types (
    id SERIAL PRIMARY KEY, code VARCHAR(30) UNIQUE NOT NULL, name VARCHAR(60) NOT NULL,
    description VARCHAR(200) DEFAULT '', first_deposit_min NUMERIC DEFAULT 100,
    leverages JSONB DEFAULT '[50,100,200,400,500,1000]', default_leverage INT DEFAULT 500,
    swap_free_available BOOLEAN DEFAULT TRUE, platforms JSONB DEFAULT '["MT5","MT4"]',
    mt5_group VARCHAR(80) DEFAULT '', mt4_group VARCHAR(80) DEFAULT '', is_active BOOLEAN DEFAULT TRUE,
    sort_order INT DEFAULT 100, created_at TIMESTAMP DEFAULT NOW(), updated_at TIMESTAMP DEFAULT NOW())""")
conn.commit()
c.execute("SELECT COUNT(*) FROM payment_methods")
if c.fetchone()[0] == 0:
    methods = [
        ("card","Credit / Debit Card","card","auto","card","Visa, Mastercard - instant","0%","Instant",10,None,10,'[]','[]','{}','["CARD_API_KEY"]','{"flow":"redirect"}'),
        ("ovadot","Ovadot e-Wallet","ovadot","auto","ovadot","Instant e-wallet payment","0%","Instant",20,None,10,'[]','[]','{}','["OVADOT_API_KEY","OVADOT_MERCHANT_ID"]','{"flow":"ewallet"}'),
        ("usdt_trc20","USDT (TRC-20)","usdt","auto","usdt","Tether on Tron - auto-confirm","0%","~5 min",30,None,10,'[]','[]','{}','["USDT_API_KEY"]','{"flow":"crypto_address","network":"TRC20"}'),
        ("bank_wire","Bank Wire","bank","manual","bank","International wire - 1-3 days","0%","1-3 days",40,None,100,'[]','[]','{"Bank":"Emirates NBD","Account name":"TNFX Markets Ltd","IBAN":"AE07 0331 2345 6789 0123 456","SWIFT":"EBILAEAD"}','[]','{}'),
        ("local_iq","Local Bank (Iraq)","local","manual","local","Zain Cash, FastPay - instant","0%","Instant",50,None,10,'["Iraq"]','[]','{"Provider":"Zain Cash","Wallet":"+964 770 000 0000","Name":"TNFX Iraq"}','[]','{}'),
    ]
    for m in methods:
        c.execute("""INSERT INTO payment_methods (code,name,logo,kind,provider,blurb,fee,processing_time,sort_order,max_deposit,min_deposit,allow_countries,block_countries,manual_details,env_keys,api_config,min_withdraw,max_withdraw)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,CAST(%s AS JSONB),CAST(%s AS JSONB),CAST(%s AS JSONB),CAST(%s AS JSONB),CAST(%s AS JSONB),50,100000)""", m)
    print("seeded", len(methods), "methods")
c.execute("SELECT COUNT(*) FROM account_types")
if c.fetchone()[0] == 0:
    types = [("standard","Standard","Balanced spreads, no commission",100,500,"real\\STD-USD","STD\\2-STD-IS",10),
             ("cent","Cent","Micro lots, great for beginners",100,500,"real\\Cent-USD","Cent\\2-Cent-IS",20),
             ("zero","Zero","Raw spreads + low commission",500,500,"real\\ZERO-USD","ZERO\\2-ZERO-IS",30),
             ("vip","VIP","Tightest spreads, priority service",100000,400,"real\\VIP-USD","VIP\\2-VIP-IS",40)]
    for ty in types:
        c.execute("""INSERT INTO account_types (code,name,description,first_deposit_min,default_leverage,mt5_group,mt4_group,sort_order)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""", ty)
    print("seeded", len(types), "account types")
conn.commit()
c.execute("SELECT code,name,kind FROM payment_methods ORDER BY sort_order")
print("Methods:", c.fetchall())
c.execute("SELECT code,first_deposit_min FROM account_types ORDER BY sort_order")
print("Types:", c.fetchall())
conn.close()
print("DONE")

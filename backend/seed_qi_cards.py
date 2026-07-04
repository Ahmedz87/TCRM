"""
seed_qi_cards.py — seed the company Qi-Cards into the existing `payment_cards` table.

Qi-Cards are company payment cards handed to back-office staff (5-6 each). They live in the SAME
`payment_cards` table the manual-deposit flow already uses (card_type='qcard'); the portal shows a
client ONE active card (round-robin), and staff manage them in the Payment Cards admin page. A card
is shown when is_active=TRUE AND the current hour is within its active_from..active_to window.

Mapping: holder_name = the person's name on the card, number = Qi card number, account_number =
the bank account number, is_active = the On/Off from the old system. Showing-hours / per-transaction
max / monthly limit are left at defaults for the desk to set per card in the admin page.

Idempotent: upserts by account_number within card_type='qcard'. Re-run safely.
NOTE: card/account numbers were transcribed from screenshots — VERIFY before going live.
"""
import db_config

# (card_name, card_number, account_number, wallet_limit, deposit_balance, withdrawal_balance, manual_on)
CARDS = [
    ("Ziyad Salih",        "",                 "7962641119",  10000,     0.00,    0,    False),
    ("yasir saad",         "5213720909775830", "1976805570",  10000, 20911.94, 15658,  False),
    ("walid ibrahim",      "4177630227633974", "2032232577",  10000, 34081.60, 30861,  False),
    ("Wafa Yasin",         "5213720471020557", "7489327879",  10000, 21621.63, 26468,  False),
    ("waad fayyd",         "4177630211873198", "1095719678",  10000, 24289.58, 19626,  False),
    ("TURKIYAH Y. ABBAS",  "5719557497",       "5719557497",  10000,     0.00,    0,    False),
    ("Tah Abbas",          "5213720430333067", "7842473105",  10000,  8831.60,  6365,  False),
    ("Sundus Hammadi",     "5222490764393496", "910155795511",10000, 11353.57,  7197,  False),
    ("shaimaa farhan",     "4177630215253363", "9982525694",  10000, 20381.97, 13766,  False),
    ("shahd sab",          "4177630214896436", "2319720781",  10000,  5336.11,  5543,  False),
    ("sarah hamid",        "5213720425856536", "2470542321",  10000, 18141.20, 14574,  False),
    ("Salima Aifan Abd",   "5213720414856687", "2004507196",  10000, 13957.69,  8371,  False),
    ("Saif farhan",        "4177630219196394", "7989865154",  10000,   253.68,     0,   False),
    ("Saada Ali Muhsin",   "4177630220232543", "8367002576",  10000,  9689.68,  6500,  False),
    ("Rasmiya Farhan",     "4177630216470867", "7959013991",  10000,  8274.86,     0,   False),
    ("Noor Salih",         "5213720457731409", "9351413696",   6500, 10179.41,  3949,  False),
    ("nasreen fayyad",     "4177630212450228", "4710711542",  10000, 17509.25,  9280,  True),
    ("NAJAH SALIM LAZIM",  "8068818965",       "8068818965",  10000, 19064.91, 16875,  False),
    ("Muhammad Hamadi",    "4177630212728821", "8487047972",  10000, 11343.50,  6129,  False),
    ("Maria Faleh",        "5213720447573598", "8599656165",  10000,  6054.37,  3426,  False),
    ("Mahdiyah Hussein",   "4177630215286207", "3991502620",  10000, 35546.07, 26648,  False),
    ("lamia suhail",       "4177630217453797", "7852352868",  10000, 36081.21, 30666,  False),
    ("Laith habib",        "4177630200345901", "6293381635",  10000, 21401.80, 14444,  False),
    ("khalid Suhail",      "4177630214421383", "6173130466",  10000, 43470.25, 30349,  False),
    ("Iman Jabbar",        "5213720495541307", "2759474311",  10000,  9106.45,  4125,  False),
    ("Ibtihal",            "4177630202754589", "5647870111",  10000,  8718.79,  7232,  False),
    ("hussein saad",       "0",                "5750464579",  10000, 24626.15, 14353,  False),
    ("Hussein Ibrahim",    "07881612941",      "4491408250",  10000,  4729.67,  1299,  False),
    ("hussein A. fadhil",  "5213720904241028", "3765265230",  10000,  3139.35,   857,  False),
    ("Huda salih",         "5213720431660179", "9761142315",  10000,  8588.29,  1491,  False),
    ("hayin amer",         "5213720980983477", "4361187489",  10000, 25182.48, 20589,  True),
    ("hamdah aifan",       "5213720491597873", "2109751632",  10000, 21905.88, 18043,  True),
    ("Hajer hasan",        "4177630225795411", "4885921843",  10000,  6285.50,  4496,  False),
    ("Ghaliah Faleh",      "5213720413447371", "1943943256",  10000,  8862.73,     0,   False),
    ("Fatima Mohammed",    "07881612934",      "4771499045",  10000,  7602.40,  1631,  False),
    ("fatima ibrahim",     "5213720955100768", "1899096950",  10000,   425.63,     0,   False),
    ("farah ibrahim",      "4177630216170103", "5197450934",  10000, 32601.37, 29721,  False),
]


def main():
    c = db_config.connect()
    cur = c.cursor()
    # make sure the qcard columns exist (mirror payment_cards_router._ensure)
    cur.execute("""CREATE TABLE IF NOT EXISTS payment_cards (
        id SERIAL PRIMARY KEY, card_type VARCHAR(20), number VARCHAR(60), label VARCHAR(80),
        holder_user_id INT, holder_name VARCHAR(80), active_from INT DEFAULT 0, active_to INT DEFAULT 24,
        is_active BOOLEAN DEFAULT TRUE, created_at TIMESTAMPTZ DEFAULT NOW())""")
    for col, ddl in [("account_number","VARCHAR(60)"),("wallet_limit","NUMERIC DEFAULT 0"),
                     ("max_per_transaction","NUMERIC DEFAULT 0"),("monthly_limit","NUMERIC DEFAULT 0"),
                     ("month_deposited","NUMERIC DEFAULT 0"),("month_anchor","DATE"),
                     ("last_shown_at","TIMESTAMPTZ"),("times_shown","INT DEFAULT 0")]:
        cur.execute(f"ALTER TABLE payment_cards ADD COLUMN IF NOT EXISTS {col} {ddl}")
    ins = upd = 0
    for (name, card, acct, wlimit, dep, wdr, on) in CARDS:
        cur.execute("SELECT id FROM payment_cards WHERE card_type='qcard' AND account_number=%s", (acct,))
        row = cur.fetchone()
        if row:
            cur.execute("""UPDATE payment_cards SET holder_name=%s, number=%s, wallet_limit=%s WHERE id=%s""",
                        (name, card, wlimit, row[0])); upd += 1
        else:
            cur.execute("""INSERT INTO payment_cards
                (card_type, number, account_number, holder_name, label, wallet_limit,
                 active_from, active_to, is_active)
                VALUES ('qcard',%s,%s,%s,%s,%s,0,24,%s)""",
                (card, acct, name, name, wlimit, on)); ins += 1
    c.commit()
    cur.execute("SELECT COUNT(*) FROM payment_cards WHERE card_type='qcard'")
    total = cur.fetchone()[0]
    c.close()
    print(f"Qi-Cards: inserted {ins}, updated {upd}; payment_cards now has {total} qcard rows")


if __name__ == "__main__":
    main()

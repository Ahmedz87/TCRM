#!/usr/bin/env python3
"""Mark file_present/folder/local_path in deposit_documents + pay_* from receipt_phash (downloaded set)."""
import psycopg2
import db_config
PG=db_config.DSN
def main():
    pg=psycopg2.connect(PG); pg.autocommit=False; cur=pg.cursor()
    for t in ["deposit_documents","pay_qi_card","pay_zaincash","pay_sham_cash"]:
        cur.execute(f"""UPDATE {t} d SET file_present=TRUE, folder=p.folder,
                     local_path='/var/lib/broker_docs/deposits/'||p.folder||'/'||p.filename
                     FROM receipt_phash p WHERE p.filename=d.receipt_filename
                     AND (d.file_present IS NOT TRUE OR d.folder IS NULL)""")
        pg.commit()
        cur.execute(f"SELECT count(*) FILTER (WHERE file_present), count(*) FROM {t}")
        pres,tot=cur.fetchone(); print(f"{t}: file_present {pres:,}/{tot:,}")
    pg.close()
if __name__=="__main__": main()

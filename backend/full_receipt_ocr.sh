#!/bin/bash
# FULL receipt OCR (green-lit): fraud-scans EVERY downloaded Qi/Zain/Sham receipt.
# Sonnet 4.6, 8 workers, resumable. Repeats as the download + phash fill in the present set.
cd /c/broker-crm/backend
PY=./venv/Scripts/python.exe
M=claude-haiku-4-5
W=8
LOG=/c/broker-crm/backend/FULL_OCR_STATUS.txt
echo "[full-ocr] start $(date)" > $LOG

remaining() {  # present-but-unOCR'd rows across the 3 method tables
  $PY - <<'PYEOF'
import db_config
d=db_config.connect()
c=d.cursor(); tot=0
for t in ["pay_qi_card","pay_zaincash","pay_sham_cash"]:
    c.execute(f"SELECT count(*) FROM {t} x JOIN receipt_phash p ON p.filename=x.receipt_filename WHERE x.ocr_status='pending'")
    tot+=c.fetchone()[0]
print(tot); d.close()
PYEOF
}

while true; do
  for t in pay_qi_card pay_zaincash pay_sham_cash; do
    $PY receipt_ocr_dbbox.py $t 500000 $M $W >> $LOG 2>&1
  done
  rem=$(remaining | tr -d '\r ')
  dl=$(ssh -o StrictHostKeyChecking=no -o ConnectTimeout=20 root@199.247.6.189 "systemctl is-active brokerdocs" 2>/dev/null)
  # per-method done tally
  $PY - >> $LOG 2>&1 <<'PYEOF'
import psycopg2,datetime
import db_config; d=db_config.connect()
c=d.cursor()
row=[]
for t in ["pay_qi_card","pay_zaincash","pay_sham_cash"]:
    c.execute(f"SELECT count(*) FILTER (WHERE ocr_status='done'), count(*) FROM {t}")
    dn,tt=c.fetchone(); row.append(f"{t}={dn}/{tt}")
print(f"[full-ocr] {datetime.datetime.now():%H:%M} "+" ".join(row))
d.close()
PYEOF
  echo "[full-ocr] remaining_present=$rem download=$dl $(date)" >> $LOG
  if [ "$dl" != "active" ] && [ "${rem:-999}" -lt 100 ]; then break; fi
  sleep 90
done
echo "[full-ocr] running final study..." >> $LOG
$PY deposit_fraud_study.py >> $LOG 2>&1
echo "[full-ocr] ALL DONE $(date)" >> $LOG

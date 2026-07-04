#!/bin/bash
# Autonomous finalizer: waits for the DB-box download + the KYC-OCR job to finish, then runs the
# final phash, marks file presence, applies KYC->clients/leads, and runs the final fake-doc study.
cd /c/broker-crm/backend
PY=./venv/Scripts/python.exe
F=/c/broker-crm/backend/FINAL_STATUS.txt
echo "[finalize] started $(date)" > $F

# 1) wait for download (brokerdocs.service) to go inactive
echo "[finalize] waiting for download to finish..." >> $F
for i in $(seq 1 240); do   # up to ~4h
  st=$(ssh -o StrictHostKeyChecking=no -o ConnectTimeout=20 root@199.247.6.189 "systemctl is-active brokerdocs" 2>/dev/null)
  [ "$st" != "active" ] && break
  sleep 60
done
echo "[finalize] download state=$st at $(date)" >> $F
ssh -o StrictHostKeyChecking=no root@199.247.6.189 "grep -a 'DONE\|got=' /var/lib/broker_docs/fetch.log | tail -4" >> $F 2>&1

# 2) wait for the KYC OCR to drain (pending linked id-docs stable/zero)
echo "[finalize] waiting for KYC OCR to drain..." >> $F
Q="SELECT count(*) FROM ts_kyc_documents WHERE doc_type IN ('id_front','id_back') AND (client_id IS NOT NULL OR lead_id IS NOT NULL) AND ocr_status='pending'"
prev=-1
for i in $(seq 1 120); do
  cnt=$(ssh -o StrictHostKeyChecking=no -o ConnectTimeout=20 root@199.247.6.189 "sudo -u postgres psql broker_crm -tAc \"$Q\"" 2>/dev/null | tr -d '\r ')
  [ -z "$cnt" ] && cnt=0
  [ "$cnt" -le 5 ] && break
  [ "$cnt" = "$prev" ] && break   # stopped draining (stuck/errors)
  prev=$cnt; sleep 60
done
echo "[finalize] KYC OCR pending=$cnt at $(date)" >> $F

# 3) final phash over the full downloaded set (DB box), wait for it
ssh -o StrictHostKeyChecking=no root@199.247.6.189 "systemctl reset-failed phashrcpt 2>/dev/null; systemd-run --unit=phashrcpt --collect python3 /root/phash_receipts.py" >> $F 2>&1
for i in $(seq 1 60); do
  st=$(ssh -o StrictHostKeyChecking=no root@199.247.6.189 "systemctl is-active phashrcpt" 2>/dev/null)
  [ "$st" != "active" ] && break
  sleep 30
done
echo "[finalize] final phash done: $(ssh -o StrictHostKeyChecking=no root@199.247.6.189 "sudo -u postgres psql broker_crm -tAc 'SELECT count(*) FROM receipt_phash'" 2>/dev/null) hashes" >> $F

# 4) mark presence, apply KYC, final study
echo "[finalize] mark_file_present:" >> $F;      $PY mark_file_present.py >> $F 2>&1
echo "[finalize] apply_kyc_to_people:" >> $F;    $PY apply_kyc_to_people.py >> $F 2>&1
echo "[finalize] deposit_fraud_study:" >> $F;    $PY deposit_fraud_study.py >> $F 2>&1
echo "[finalize] ALL DONE $(date)" >> $F

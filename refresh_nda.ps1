# refresh_nda.ps1 — nightly refresh of the ONE relation engine (network + NDA + bonus + tables).
# Chain: FTD dates -> canonical city -> payment senders -> relation_engine (the single source that
# writes entity_relations / entity_status / clients.is_nda / network_score / relation_state).
# nda_engine + build_network_scores are DEPRECATED (relation_engine supersedes both) — do not run
# them here, they would overwrite the unified engine's output with the old split logic.
$ErrorActionPreference = "Stop"
$be = "C:\broker-crm\backend"
$py = "$be\venv\Scripts\python.exe"
$log = "$be\logs\nda_refresh.log"
$env:PYTHONUTF8 = "1"; $env:PYTHONIOENCODING = "utf-8"
function Step($label, $script, $scriptArgs) {
  Add-Content $log "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $label starting..."
  if ($scriptArgs) { & $py "$be\$script" $scriptArgs *>> $log } else { & $py "$be\$script" *>> $log }
  Add-Content $log "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $label done (exit $LASTEXITCODE)."
}
Step "canonical city"              "build_city_canon.py" "--commit"
Step "payment senders (Qi by name)" "build_payment_senders.py" $null
Step "RELATION ENGINE (FTD dates + network + NDA + bonus)" "relation_engine.py" $null

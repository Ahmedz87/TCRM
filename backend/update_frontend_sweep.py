p = r"C:\broker-crm\frontend\src\NegBalance.tsx"
s = open(p, encoding="utf-8").read()

# Update coverAll to handle the new background response
old = '''  const coverAll = async () => {
    if (!window.confirm(`Cover all eligible ${platform} accounts now?`)) return;
    setLoading(true);
    addLog('Running sweep...');
    try {
      const r = await fetch(`${API}/neg-cover/cover-all`, { method: 'POST', headers: { Authorization: `Bearer ${tok()}` } });
      const d = await r.json();
      addLog(`Sweep done: covered ${d.covered_count} accounts`);
      (d.covered || []).forEach((c: any) => addLog(`  ✓ #${c.login}: ${c.deficit?.toFixed(2)}`));
      scan();
    } catch { addLog('Sweep failed'); }
    setLoading(false);
  };'''

new = '''  const coverAll = async () => {
    if (!window.confirm(`Cover all eligible ${platform} accounts now?`)) return;
    addLog('Running sweep in background...');
    try {
      const r = await fetch(`${API}/neg-cover/cover-all`, { method: 'POST', headers: { Authorization: `Bearer ${tok()}` } });
      const d = await r.json();
      addLog(`▶ ${d.message || 'Sweep started'} — covering in background`);
      // Poll: refresh scan every 8s for ~2 min to show progress
      let ticks = 0;
      const iv = setInterval(() => {
        ticks++;
        scan();
        if (ticks >= 15) { clearInterval(iv); addLog('Sweep monitoring stopped (check log for results)'); }
      }, 8000);
    } catch { addLog('Sweep failed to start'); }
  };'''

if old in s:
    s = s.replace(old, new)
    open(p, "w", encoding="utf-8").write(s)
    print("Frontend sweep updated: non-blocking + auto-refresh progress")
else:
    print("coverAll block not matched - showing current:")
    i = s.find("const coverAll")
    print(s[i:i+400])

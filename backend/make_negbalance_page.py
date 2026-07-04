content = r'''import { useState, useEffect } from 'react';

const API = process.env.REACT_APP_API_URL || 'http://localhost:8000';
const tok = () => localStorage.getItem('token');

const STATUS_INFO: Record<string,{label:string,color:string}> = {
  eligible:         { label:'Eligible',        color:'#00e5a0' },
  credit_low:       { label:'Credit too low',  color:'#ff8800' },
  has_positions:    { label:'Has open trades', color:'#ffaa00' },
  not_negative_now: { label:'Not negative',    color:'#555' },
  no_data:          { label:'No data',         color:'#555' },
  unknown:          { label:'—',               color:'#555' },
};

export default function NegBalance() {
  const [platform, setPlatform] = useState('MT5');
  const [data, setData] = useState<any>({ accounts: [], eligible: 0 });
  const [loading, setLoading] = useState(false);
  const [auto, setAuto] = useState(false);
  const [log, setLog] = useState<string[]>([]);
  const [busy, setBusy] = useState<number|null>(null);

  const addLog = (m: string) => setLog(l => [`${new Date().toLocaleTimeString()}  ${m}`, ...l].slice(0, 50));

  const scan = async () => {
    setLoading(true);
    try {
      const r = await fetch(`${API}/neg-cover/scan?platform=${platform}`, { headers: { Authorization: `Bearer ${tok()}` } });
      const d = await r.json();
      setData(d);
    } catch { addLog('Scan failed'); }
    setLoading(false);
  };

  const checkAuto = async () => {
    try {
      const r = await fetch(`${API}/neg-cover/auto/status`, { headers: { Authorization: `Bearer ${tok()}` } });
      const d = await r.json();
      setAuto(d.auto);
    } catch {}
  };

  useEffect(() => { scan(); checkAuto(); }, [platform]);

  const coverOne = async (login: number) => {
    setBusy(login);
    try {
      const r = await fetch(`${API}/neg-cover/cover/${login}`, { method: 'POST', headers: { Authorization: `Bearer ${tok()}` } });
      const d = await r.json();
      if (d.status === 'covered') addLog(`✓ Covered #${login}: deficit ${d.deficit?.toFixed(2)}, balance now ${d.balance_after?.toFixed(2)}`);
      else addLog(`#${login}: ${d.status}`);
      scan();
    } catch { addLog(`#${login} cover failed`); }
    setBusy(null);
  };

  const coverAll = async () => {
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
  };

  const toggleAuto = async () => {
    const ep = auto ? 'stop' : 'start';
    if (!auto && !window.confirm('Start AUTO cover? It will continuously cover eligible accounts until stopped.')) return;
    try {
      await fetch(`${API}/neg-cover/auto/${ep}`, { method: 'POST', headers: { Authorization: `Bearer ${tok()}` } });
      setAuto(!auto);
      addLog(auto ? '⏹ Auto cover STOPPED' : '▶ Auto cover STARTED');
    } catch { addLog('Auto toggle failed'); }
  };

  const toggleExclude = async (login: number) => {
    try {
      const r = await fetch(`${API}/neg-cover/toggle-exclude/${login}`, { method: 'POST', headers: { Authorization: `Bearer ${tok()}` } });
      const d = await r.json();
      addLog(`#${login} ${d.no_auto_cover ? 'excluded from auto' : 'included in auto'}`);
      scan();
    } catch {}
  };

  const accounts = data.accounts || [];

  return (
    <div style={{ padding: 24, color: '#e0e0e0' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 20 }}>Negative Balance Protection</h2>
          <div style={{ fontSize: 12, color: '#888', marginTop: 4 }}>
            {accounts.length} negative accounts · <span style={{ color: '#00e5a0' }}>{data.eligible} eligible</span>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <button onClick={coverAll} disabled={loading} style={{ padding: '9px 16px', borderRadius: 8, border: 'none', background: '#00aaff', color: '#fff', fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>▶ Run This Time</button>
          <button onClick={toggleAuto} style={{ padding: '9px 16px', borderRadius: 8, border: `1px solid ${auto ? '#ff4d4d' : '#00e5a0'}`, background: auto ? 'rgba(255,77,77,0.12)' : 'rgba(0,229,160,0.12)', color: auto ? '#ff4d4d' : '#00e5a0', fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>
            {auto ? '⏹ Stop Auto' : '▶ Run Auto'}
          </button>
          {auto && <span style={{ fontSize: 11, color: '#00e5a0' }}>● Auto running</span>}
        </div>
      </div>

      {/* Platform tabs */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 16 }}>
        {['MT5', 'MT4'].map(p => (
          <button key={p} onClick={() => setPlatform(p)} style={{ padding: '8px 20px', borderRadius: 8, border: 'none', background: platform === p ? '#00aaff' : '#1a1d24', color: platform === p ? '#fff' : '#888', fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>{p}</button>
        ))}
        <button onClick={scan} disabled={loading} style={{ marginLeft: 'auto', padding: '8px 16px', borderRadius: 8, border: '1px solid #333', background: 'transparent', color: '#888', cursor: 'pointer', fontFamily: 'inherit' }}>{loading ? 'Scanning...' : '↻ Refresh'}</button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: 16 }}>
        {/* Table */}
        <div style={{ background: '#111318', borderRadius: 12, overflow: 'hidden', border: '1px solid #1a1d24' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
            <thead>
              <tr style={{ borderBottom: '1px solid #222', color: '#666', fontSize: 11 }}>
                {['Login', 'Name', 'Balance', 'Credit', 'Deficit', 'Status', ''].map(h => (
                  <th key={h} style={{ padding: '10px 8px', textAlign: 'left', fontWeight: 500 }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {accounts.length === 0 ? (
                <tr><td colSpan={7} style={{ padding: 30, textAlign: 'center', color: '#555' }}>{loading ? 'Scanning...' : 'No negative accounts'}</td></tr>
              ) : accounts.map((a: any) => {
                const si = STATUS_INFO[a.status] || STATUS_INFO.unknown;
                const eligible = a.status === 'eligible';
                return (
                  <tr key={a.login} style={{ borderBottom: '1px solid #1a1d24', opacity: a.no_auto_cover ? 0.5 : 1 }}>
                    <td style={{ padding: '9px 8px', fontFamily: 'monospace' }}>#{a.login}</td>
                    <td style={{ padding: '9px 8px' }}>{a.name}</td>
                    <td style={{ padding: '9px 8px', color: '#ff4d4d', fontWeight: 600 }}>{a.balance?.toFixed(2)}</td>
                    <td style={{ padding: '9px 8px', color: '#888' }}>{a.credit?.toFixed(2)}</td>
                    <td style={{ padding: '9px 8px', color: '#ff8800' }}>{a.deficit?.toFixed(2)}</td>
                    <td style={{ padding: '9px 8px' }}>
                      <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, border: `1px solid ${si.color}`, color: si.color }}>{si.label}</span>
                      {a.no_auto_cover && <span style={{ fontSize: 9, color: '#888', marginLeft: 4 }}>🚫 excluded</span>}
                    </td>
                    <td style={{ padding: '9px 8px', whiteSpace: 'nowrap' }}>
                      <button onClick={() => coverOne(a.login)} disabled={busy === a.login || !eligible}
                        style={{ padding: '4px 10px', borderRadius: 6, border: 'none', background: eligible ? '#00e5a0' : '#222', color: eligible ? '#000' : '#555', fontWeight: 600, cursor: eligible ? 'pointer' : 'default', fontSize: 11, marginRight: 4, fontFamily: 'inherit' }}>
                        {busy === a.login ? '...' : 'Run'}
                      </button>
                      <button onClick={() => toggleExclude(a.login)} title="Toggle don't-cover"
                        style={{ padding: '4px 8px', borderRadius: 6, border: '1px solid #333', background: 'transparent', color: a.no_auto_cover ? '#00e5a0' : '#888', cursor: 'pointer', fontSize: 11, fontFamily: 'inherit' }}>
                        {a.no_auto_cover ? 'Include' : "Don't cover"}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Live log */}
        <div style={{ background: '#111318', borderRadius: 12, border: '1px solid #1a1d24', padding: 14, height: 'fit-content', position: 'sticky', top: 20 }}>
          <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 10, color: '#888' }}>Activity Log</div>
          <div style={{ maxHeight: 400, overflowY: 'auto', fontSize: 11, fontFamily: 'monospace', lineHeight: 1.6 }}>
            {log.length === 0 ? <div style={{ color: '#444' }}>No activity yet</div> : log.map((l, i) => <div key={i} style={{ color: l.includes('✓') ? '#00e5a0' : '#888', borderBottom: '1px solid #1a1d24', padding: '3px 0' }}>{l}</div>)}
          </div>
        </div>
      </div>

      <div style={{ marginTop: 14, fontSize: 11, color: '#555' }}>
        Cover moves credit → balance to clear negative balances. Only flat accounts (no open trades) where credit fully covers the deficit are eligible. Excluded accounts are skipped by auto/sweep but can still be covered manually.
      </div>
    </div>
  );
}
'''
p = r"C:\broker-crm\frontend\src\NegBalance.tsx"
open(p, "w", encoding="utf-8").write(content)
print("Created NegBalance.tsx")

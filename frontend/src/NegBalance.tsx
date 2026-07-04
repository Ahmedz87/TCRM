import { useState, useEffect } from 'react';

const API = process.env.REACT_APP_API_URL || '/api';
const tok = () => localStorage.getItem('token');

const STATUS_INFO: Record<string,{label:string,color:string}> = {
  eligible:         { label:'Eligible',        color:'#00e5a0' },
  credit_low:       { label:'Credit too low',  color:'#ff8800' },
  has_positions_positive_pnl: { label:'Positive PnL',   color:'#00aaff' },
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
  const [abuseHover, setAbuseHover] = useState<number|null>(null);
  const [cps, setCps] = useState<Record<number, { loading: boolean; data?: any }>>({});
  const [cpHover, setCpHover] = useState<number|null>(null);
  const [nets, setNets] = useState<Record<number, { loading: boolean; data?: any }>>({});
  const [netHover, setNetHover] = useState<number|null>(null);

  const addLog = (m: string) => setLog(l => [`${new Date().toLocaleTimeString()}  ${m}`, ...l].slice(0, 50));

  // Jump to a client/account profile (Clients page opens the profile by MT login)
  const goToProfile = (login: number) => {
    window.dispatchEvent(new CustomEvent('navigate', { detail: { page: 'clients', search: String(login), openProfile: login } }));
  };

  const fmtMoney = (n: number) => {
    const a = Math.abs(n);
    if (a >= 1000) return `${n < 0 ? '-' : ''}$${(a / 1000).toFixed(a >= 10000 ? 0 : 1)}k`;
    return `${n < 0 ? '-' : ''}$${a.toFixed(0)}`;
  };

  const fetchCp = async (login: number) => {
    if (cps[login]) return; // cached (loading or done)
    setCps(p => ({ ...p, [login]: { loading: true } }));
    try {
      const r = await fetch(`${API}/neg-cover/counterparties/${login}?platform=${platform}`, { headers: { Authorization: `Bearer ${tok()}` } });
      const d = await r.json();
      setCps(p => ({ ...p, [login]: { loading: false, data: d } }));
    } catch {
      setCps(p => ({ ...p, [login]: { loading: false, data: { counterparties: [] } } }));
    }
  };

  const fetchNet = async (login: number) => {
    if (nets[login]) return;
    setNets(p => ({ ...p, [login]: { loading: true } }));
    try {
      const r = await fetch(`${API}/neg-cover/network/${login}`, { headers: { Authorization: `Bearer ${tok()}` } });
      const d = await r.json();
      setNets(p => ({ ...p, [login]: { loading: false, data: d } }));
    } catch {
      setNets(p => ({ ...p, [login]: { loading: false, data: { related: [] } } }));
    }
  };

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

  useEffect(() => { setCps({}); setNets({}); scan(); checkAuto(); }, [platform]);

  // Auto-fetch counterparties for the top accounts so the column fills without hovering.
  // Sequential (one query at a time) to stay gentle on the live DB; rest load on hover.
  useEffect(() => {
    const list = (data.accounts || []).slice(0, 12);
    if (!list.length) return;
    let cancelled = false;
    (async () => {
      for (const a of list) {
        if (cancelled) return;
        await fetchCp(a.login);
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data.accounts]);

  const verifyOne = async (login: number) => {
    setBusy(login);
    try {
      const r = await fetch(`${API}/neg-cover/verify/${login}`, { headers: { Authorization: `Bearer ${tok()}` } });
      const d = await r.json();
      if (d.error) { addLog(`#${login} verify failed`); }
      else {
        setData((prev: any) => ({
          ...prev,
          accounts: prev.accounts.map((a: any) => a.login === login ? { ...a, status: d.status, balance: d.balance, credit: d.credit, deficit: d.deficit, floating_pnl: d.floating_pnl, positions: d.positions, verified: true } : a)
        }));
        addLog(`✓ #${login} verified: PnL ${d.floating_pnl?.toFixed(2)}, ${d.positions} pos → ${d.status}`);
      }
    } catch { addLog(`#${login} verify error`); }
    setBusy(null);
  };

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
    addLog('Running sweep in background...');
    try {
      const r = await fetch(`${API}/neg-cover/cover-all?platform=${platform}`, { method: 'POST', headers: { Authorization: `Bearer ${tok()}` } });
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
          <button key={p} onClick={() => setPlatform(p)} style={{ padding: '8px 20px', borderRadius: 8, border: 'none', background: platform === p ? '#00aaff' : '#373f4d', color: platform === p ? '#fff' : '#888', fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>{p}</button>
        ))}
        <button onClick={scan} disabled={loading} style={{ marginLeft: 'auto', padding: '8px 16px', borderRadius: 8, border: '1px solid #626d80', background: 'transparent', color: '#888', cursor: 'pointer', fontFamily: 'inherit' }}>{loading ? 'Scanning...' : '↻ Refresh'}</button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: 16 }}>
        {/* Table */}
        <div style={{ background: '#2c333e', borderRadius: 12, overflow: 'hidden', border: '1px solid #373f4d' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
            <thead>
              <tr style={{ borderBottom: '1px solid #4f596b', color: '#666', fontSize: 11 }}>
                {['Login', 'Name', 'Balance', 'Credit', 'Deficit', 'Network', 'Counterparty', 'Abuse', 'Status', ''].map(h => (
                  <th key={h} style={{ padding: '10px 8px', textAlign: 'left', fontWeight: 500 }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {accounts.length === 0 ? (
                <tr><td colSpan={10} style={{ padding: 30, textAlign: 'center', color: '#555' }}>{loading ? 'Scanning...' : 'No negative accounts'}</td></tr>
              ) : accounts.map((a: any) => {
                const si = STATUS_INFO[a.status] || STATUS_INFO.unknown;
                const eligible = a.status === 'eligible';
                const creditLow = a.status === 'credit_low';
                const net = a.network_score || 0;
                const netColor = net >= 70 ? '#ff4d4d' : net >= 40 ? '#ffaa00' : '#00e5a0';
                return (
                  <tr key={a.login} style={{ borderBottom: '1px solid #373f4d', opacity: a.no_auto_cover ? 0.5 : 1, background: creditLow ? 'rgba(255,77,77,0.06)' : 'transparent' }}>
                    <td style={{ padding: '9px 8px', fontFamily: 'monospace' }}>#{a.login}</td>
                    <td style={{ padding: '9px 8px' }}>{a.name}</td>
                    <td style={{ padding: '9px 8px', color: '#ff4d4d', fontWeight: 600 }}>{a.balance?.toFixed(2)}</td>
                    <td style={{ padding: '9px 8px', color: creditLow ? '#ff8800' : '#00e5a0', fontWeight: 600 }}>{a.credit?.toFixed(2)}</td>
                    <td style={{ padding: '9px 8px', color: '#ff8800' }}>{a.deficit?.toFixed(2)}</td>
                    <td style={{ padding: '9px 8px', position: 'relative' }}
                        onMouseEnter={() => { fetchNet(a.login); setNetHover(a.login); }}
                        onMouseLeave={() => setNetHover(null)}>
                      {net > 0 ? <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 99, border: `1px solid ${netColor}`, color: netColor, fontWeight: 600, cursor: 'help' }}>{Math.min(10, Math.round(net/10))}/10</span> : <span style={{ color: '#666', fontSize: 11, cursor: 'help' }}>hover</span>}
                      {netHover === a.login && (
                        <div style={{ position: 'absolute', bottom: '120%', left: 0, background: '#373f4d', border: '1px solid #626d80', borderRadius: 10, padding: 12, width: 320, zIndex: 999, boxShadow: '0 8px 30px rgba(0,0,0,0.6)' }}>
                          {(() => {
                            const nd = nets[a.login];
                            if (!nd || nd.loading) return <div style={{ fontSize: 11, color: '#888' }}>Loading network…</div>;
                            const d = nd.data || {};
                            const related = d.related || [];
                            if (!related.length) return <div style={{ fontSize: 11, color: '#888' }}>No linked accounts</div>;
                            const br = d.by_reason || {};
                            return (
                              <>
                                <div style={{ fontSize: 11, color: '#888', marginBottom: 8 }}>
                                  <span style={{ color: '#e0e0e0', fontWeight: 700 }}>{d.total}</span> linked account{d.total === 1 ? '' : 's'}
                                </div>
                                <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginBottom: 8 }}>
                                  {Object.entries(br).map(([k, v]: any) => (
                                    <span key={k} style={{ fontSize: 9, padding: '1px 6px', borderRadius: 4, background: 'rgba(255,255,255,0.06)', color: '#aaa' }}>{k}: {v}</span>
                                  ))}
                                </div>
                                <div style={{ maxHeight: 280, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 5 }}>
                                  {related.map((c: any) => (
                                    <div key={c.login} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, padding: '5px 8px', borderRadius: 8, background: c.strong_link ? 'rgba(255,77,77,0.08)' : 'rgba(255,255,255,0.03)', border: `1px solid ${c.strong_link ? 'rgba(255,77,77,0.35)' : '#4f596b'}` }}>
                                      <div style={{ minWidth: 0 }}>
                                        <div style={{ fontSize: 12 }}>
                                          <span onClick={() => goToProfile(c.login)} style={{ fontFamily: 'monospace', color: '#00aaff', cursor: 'pointer', textDecoration: 'underline' }}>#{c.login}</span>
                                          {c.name && <span style={{ color: '#aaa' }}> · {c.name}</span>}
                                        </div>
                                        <div style={{ display: 'flex', gap: 4, marginTop: 3, flexWrap: 'wrap' }}>
                                          {(c.reasons || []).map((r: string) => (
                                            <span key={r} style={{ fontSize: 9, padding: '1px 6px', borderRadius: 4, background: ['cid','ip','device','mqid','family','phone','email','name'].includes(r) ? 'rgba(255,77,77,0.18)' : 'rgba(0,170,255,0.15)', color: ['cid','ip','device','mqid','family','phone','email','name'].includes(r) ? '#ff8888' : '#66ccff' }}>🔗 {r}</span>
                                          ))}
                                        </div>
                                      </div>
                                      <div style={{ fontSize: 11, fontWeight: 700, color: c.balance > 0 ? '#00e5a0' : c.balance < 0 ? '#ff4d4d' : '#888', whiteSpace: 'nowrap' }}>{fmtMoney(c.balance)}</div>
                                    </div>
                                  ))}
                                </div>
                              </>
                            );
                          })()}
                        </div>
                      )}
                    </td>
                    <td style={{ padding: '9px 8px', position: 'relative' }}
                        onMouseEnter={() => { fetchCp(a.login); setCpHover(a.login); }}
                        onMouseLeave={() => setCpHover(null)}>
                      {(() => {
                        const c = cps[a.login];
                        if (!c) return <span style={{ color: '#666', fontSize: 11, cursor: 'help' }}>hover</span>;
                        if (c.loading) return <span style={{ color: '#666', fontSize: 11 }}>…</span>;
                        const list = c.data?.counterparties || [];
                        if (!list.length) return <span style={{ color: '#444' }}>—</span>;
                        const top = list[0];
                        const strongCount = list.filter((x: any) => x.strong_match).length;
                        const col = top.strong_match ? '#ff4d4d' : '#ffaa00';
                        return (
                          <span style={{ cursor: 'help', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                            <span style={{ fontSize: 11, padding: '2px 7px', borderRadius: 99, border: `1px solid ${col}`, color: col, fontWeight: 600, whiteSpace: 'nowrap' }}>
                              {top.related ? '🔗' : '⚠'} +{fmtMoney(top.profit)}{top.pct_of_loss != null ? ` · ${Math.round(top.pct_of_loss)}%` : ''}
                            </span>
                            {list.length > 1 && <span style={{ fontSize: 10, color: '#888' }}>+{list.length - 1}</span>}
                          </span>
                        );
                      })()}
                      {cpHover === a.login && cps[a.login]?.data && (cps[a.login].data.counterparties?.length > 0) && (
                        <div style={{ position: 'absolute', bottom: '120%', left: 0, background: '#373f4d', border: '1px solid #626d80', borderRadius: 10, padding: 12, width: 340, zIndex: 999, boxShadow: '0 8px 30px rgba(0,0,0,0.6)' }}>
                          <div style={{ fontSize: 11, color: '#888', marginBottom: 8 }}>
                            Lost <span style={{ color: '#ff4d4d', fontWeight: 700 }}>{fmtMoney(cps[a.login].data.loss)}</span> trading
                            {cps[a.login].data.period && <span> · {cps[a.login].data.period.from}{cps[a.login].data.period.to !== cps[a.login].data.period.from ? `→${cps[a.login].data.period.to}` : ''}</span>}
                          </div>
                          <div style={{ fontSize: 10, color: '#666', marginBottom: 6 }}>Accounts that profited in the same window on the same symbols:</div>
                          <div style={{ maxHeight: 280, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 6 }}>
                            {cps[a.login].data.counterparties.map((c: any) => (
                              <div key={c.login} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, padding: '6px 8px', borderRadius: 8, background: c.strong_match ? 'rgba(255,77,77,0.08)' : 'rgba(255,255,255,0.03)', border: `1px solid ${c.strong_match ? 'rgba(255,77,77,0.4)' : '#4f596b'}` }}>
                                <div style={{ minWidth: 0 }}>
                                  <div style={{ fontSize: 12, fontWeight: 600, color: '#e0e0e0' }}>
                                    <span onClick={() => goToProfile(c.login)} style={{ fontFamily: 'monospace', color: '#00aaff', cursor: 'pointer', textDecoration: 'underline' }}>#{c.login}</span> {c.name && <span style={{ color: '#aaa', fontWeight: 400 }}>· {c.name}</span>}
                                  </div>
                                  <div style={{ display: 'flex', gap: 4, marginTop: 3, flexWrap: 'wrap' }}>
                                    {c.related ? (
                                      <span style={{ fontSize: 9, padding: '1px 6px', borderRadius: 4, background: c.strong_link ? 'rgba(255,77,77,0.2)' : 'rgba(0,170,255,0.18)', color: c.strong_link ? '#ff8888' : '#66ccff' }}>🔗 {c.reason}</span>
                                    ) : (
                                      <span style={{ fontSize: 9, padding: '1px 6px', borderRadius: 4, background: 'rgba(255,255,255,0.06)', color: '#888' }}>no connection</span>
                                    )}
                                    {c.strong_match && <span style={{ fontSize: 9, padding: '1px 6px', borderRadius: 4, background: 'rgba(255,77,77,0.2)', color: '#ff8888' }}>hedge?</span>}
                                    {(c.symbols || []).slice(0, 3).map((s: string) => <span key={s} style={{ fontSize: 9, padding: '1px 6px', borderRadius: 4, background: 'rgba(255,255,255,0.05)', color: '#999' }}>{s}</span>)}
                                  </div>
                                </div>
                                <div style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                                  <div style={{ fontSize: 12, fontWeight: 700, color: '#00e5a0' }}>+{fmtMoney(c.profit)}</div>
                                  {c.pct_of_loss != null && <div style={{ fontSize: 10, color: c.strong_match ? '#ff8888' : '#888' }}>{Math.round(c.pct_of_loss)}% of loss</div>}
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </td>
                    <td style={{ padding: '9px 8px', position: 'relative' }}>
                      {(a.is_flagged || a.in_abuse) ? (
                        <span onMouseEnter={() => setAbuseHover(a.login)} onMouseLeave={() => setAbuseHover(null)}
                          style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, background: 'rgba(255,77,77,0.15)', color: '#ff4d4d', border: '1px solid #ff4d4d', cursor: 'help' }}>
                          🚨 {a.in_abuse ? 'Abuse' : 'Flag'}
                        </span>
                      ) : <span style={{ color: '#444' }}>—</span>}
                      {abuseHover === a.login && a.abuse_info && (
                        <div style={{ position: 'absolute', bottom: '120%', left: 0, background: '#373f4d', border: '1px solid #ff4d4d', borderRadius: 10, padding: 12, width: 260, zIndex: 999, boxShadow: '0 8px 30px rgba(0,0,0,0.6)' }}>
                          <div style={{ fontSize: 12, fontWeight: 700, color: '#ff4d4d', marginBottom: 6, textTransform: 'capitalize' }}>
                            {(a.abuse_info.type || '').replace(/_/g, ' ')}
                          </div>
                          <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
                            <span style={{ fontSize: 9, padding: '1px 6px', borderRadius: 4, background: 'rgba(255,77,77,0.2)', color: '#ff8888' }}>Severity: {a.abuse_info.severity}</span>
                            <span style={{ fontSize: 9, padding: '1px 6px', borderRadius: 4, background: 'rgba(255,170,0,0.2)', color: '#ffaa00' }}>Risk: {a.abuse_info.risk}</span>
                          </div>
                          <div style={{ fontSize: 11, color: '#ccc', lineHeight: 1.5 }}>{a.abuse_info.reason}</div>
                        </div>
                      )}
                    </td>
                    <td style={{ padding: '9px 8px' }}>
                      <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, border: `1px solid ${si.color}`, color: si.color }}>{si.label}</span>
                      {a.no_auto_cover && <span style={{ fontSize: 9, color: '#888', marginLeft: 4 }}>🚫 excluded</span>}
                    </td>
                    <td style={{ padding: '9px 8px', whiteSpace: 'nowrap' }}>
                      <button onClick={() => coverOne(a.login)} disabled={busy === a.login || a.status === 'has_positions_positive_pnl'}
                        style={{ padding: '4px 10px', borderRadius: 6, border: 'none', background: a.status === 'has_positions_positive_pnl' ? '#626d80' : (eligible ? '#00e5a0' : '#ff8800'), color: a.status === 'has_positions_positive_pnl' ? '#666' : '#000', fontWeight: 600, cursor: a.status === 'has_positions_positive_pnl' ? 'default' : 'pointer', fontSize: 11, marginRight: 4, fontFamily: 'inherit' }}
                        title={a.status === 'has_positions_positive_pnl' ? 'Positive PnL — cannot cover' : (eligible ? 'Cover this account' : 'Manual cover')}>
                        {busy === a.login ? '...' : 'Run'}
                      </button>
                      <button onClick={() => toggleExclude(a.login)} title="Toggle don't-cover"
                        style={{ padding: '4px 8px', borderRadius: 6, border: '1px solid #626d80', background: 'transparent', color: a.no_auto_cover ? '#00e5a0' : '#888', cursor: 'pointer', fontSize: 11, fontFamily: 'inherit' }}>
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
        <div style={{ background: '#2c333e', borderRadius: 12, border: '1px solid #373f4d', padding: 14, height: 'fit-content', position: 'sticky', top: 20 }}>
          <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 10, color: '#888' }}>Activity Log</div>
          <div style={{ maxHeight: 400, overflowY: 'auto', fontSize: 11, fontFamily: 'monospace', lineHeight: 1.6 }}>
            {log.length === 0 ? <div style={{ color: '#444' }}>No activity yet</div> : log.map((l, i) => <div key={i} style={{ color: l.includes('✓') ? '#00e5a0' : '#888', borderBottom: '1px solid #373f4d', padding: '3px 0' }}>{l}</div>)}
          </div>
        </div>
      </div>

      <div style={{ marginTop: 14, fontSize: 11, color: '#555' }}>
        Cover moves credit → balance to clear negative balances. Only flat accounts (no open trades) where credit fully covers the deficit are eligible. Excluded accounts are skipped by auto/sweep but can still be covered manually.
      </div>
    </div>
  );
}

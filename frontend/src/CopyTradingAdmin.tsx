import React, { useEffect, useState, useCallback } from 'react';
import { apiGet, apiPost } from './api';

const fmt = (n: number, d = 0) => (n ?? 0).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d });
const pos = (n: number) => (n >= 0 ? '#00e5a0' : '#ff5d6c');
const riskLabel = (r: number) => (r <= 3 ? 'Low' : r <= 6 ? 'Med' : 'High');

export default function CopyTradingAdmin() {
  const [stats, setStats] = useState<any>(null);
  const [rows, setRows] = useState<any[]>([]);
  const [filter, setFilter] = useState<'all' | 'pending' | 'approved' | 'rejected'>('all');
  const [sort, setSort] = useState<{ k: string; dir: 1 | -1 }>({ k: 'return_pct', dir: -1 });
  const [loading, setLoading] = useState(true);
  const [preview, setPreview] = useState<any>(null);   // dry-run replication preview modal
  const [previewBusy, setPreviewBusy] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    apiGet('/copy/admin/stats').then(setStats).catch(() => {});
    const q = filter === 'all' ? '' : `?status=${filter}`;
    apiGet(`/copy/admin/providers${q}`).then((r: any) => setRows(r?.providers || [])).catch(() => {}).finally(() => setLoading(false));
  }, [filter]);
  useEffect(() => { load(); }, [load]);

  const [sweepMsg, setSweepMsg] = useState('');
  const act = async (id: number, action: string, body?: any) => {
    await apiPost(`/copy/admin/providers/${id}/${action}`, body || {});
    load();
  };
  const runSweep = async () => {
    setSweepMsg('Running…');
    try {
      const r: any = await apiPost('/copy/admin/maintenance', {});
      setSweepMsg(`✓ Stops enforced: ${r.risk?.stopped || 0} · suspended: ${r.suspended || 0} · inactive notices: ${r.inactive_notices || 0} · payouts: ${r.payouts?.payouts_created || 0}`);
      load();
    } catch { setSweepMsg('Sweep failed.'); }
  };

  const runPreview = async (p: any) => {
    setPreview({ provider: p, data: null }); setPreviewBusy(true);
    try {
      const r: any = await apiPost('/copy/admin/replicate/dry-run', { provider_id: p.id, n_trades: 5 });
      setPreview({ provider: p, data: r });
    } catch { setPreview({ provider: p, data: { error: true } }); }
    finally { setPreviewBusy(false); }
  };

  const sorted = [...rows].sort((a, b) => {
    const av = a[sort.k] ?? 0, bv = b[sort.k] ?? 0;
    if (typeof av === 'string') return sort.dir * String(av).localeCompare(String(bv));
    return sort.dir * (av - bv);
  });
  const setSortK = (k: string) => setSort(s => ({ k, dir: s.k === k ? (s.dir === 1 ? -1 : 1) : -1 }));

  const KPIS = stats ? [
    { label: 'Approved providers', value: fmt(stats.approved), color: '#0a84ff' },
    { label: 'Active / inactive', value: `${fmt(stats.active_providers)} / ${fmt(stats.inactive_providers)}`, color: '#00e5a0' },
    { label: 'Real providers', value: fmt(stats.real_providers), color: '#34D399' },
    { label: 'Pending review', value: fmt(stats.pending), color: stats.pending ? '#ffaa00' : '#888' },
    { label: 'Total copiers', value: fmt(stats.total_followers), color: '#00e5a0' },
    { label: 'Assets under copy', value: '$' + fmt(stats.total_aum), color: '#9966ff' },
    { label: 'Provider earnings', value: '$' + fmt(stats.provider_earnings), color: '#E8B84B' },
  ] : [];

  const cols: [string, string][] = [
    ['name', 'Provider'], ['strategy', 'Strategy'], ['markets', 'Markets'], ['days_active', 'Age'],
    ['return_pct', 'Return'], ['win_rate', 'Win'], ['max_drawdown', 'Max DD'], ['risk_level', 'Risk'],
    ['followers', 'Copiers'], ['total_earned', 'Earnings'], ['active', 'Active'], ['status', 'Status'],
  ];

  return (
    <div style={{ padding: 18, color: 'var(--text,#e7ecf3)', overflowY: 'auto', height: '100%' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
        <div>
          <div style={{ fontSize: 22, fontWeight: 800 }}>🪞 Copy Trading</div>
          <div style={{ fontSize: 13, color: 'var(--text2,#8a93a3)' }}>Signal-provider program — oversight, applications, and featuring.</div>
        </div>
        <div style={{ flex: 1 }} />
        <button onClick={runSweep} style={{ padding: '8px 14px', borderRadius: 9, background: 'rgba(10,132,255,0.14)', border: '1px solid rgba(10,132,255,0.45)', color: '#4DA8FF', cursor: 'pointer', fontSize: 12.5, fontWeight: 700 }}>⚙ Run safety sweep</button>
        <span style={{ fontSize: 11, color: 'var(--text2,#8a93a3)', background: 'rgba(255,170,0,0.1)', border: '1px solid rgba(255,170,0,0.3)', borderRadius: 8, padding: '6px 11px' }}>
          ⓘ Allocations are recorded; live auto-execution is a later, separately-gated phase.
        </span>
      </div>
      {sweepMsg && <div style={{ fontSize: 12, color: '#4DA8FF', marginBottom: 12 }}>{sweepMsg}</div>}

      {/* KPI cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(160px,1fr))', gap: 12, marginBottom: 18 }}>
        {KPIS.map(k => (
          <div key={k.label} style={S.kpi}>
            <div style={{ fontSize: 22, fontWeight: 800, color: k.color }}>{k.value}</div>
            <div style={{ fontSize: 11.5, color: 'var(--text2,#8a93a3)', marginTop: 3 }}>{k.label}</div>
          </div>
        ))}
      </div>

      {/* filter tabs */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 12 }}>
        {(['all', 'pending', 'approved', 'rejected'] as const).map(f => (
          <button key={f} onClick={() => setFilter(f)} style={{ ...S.tab, ...(filter === f ? S.tabActive : {}) }}>
            {f[0].toUpperCase() + f.slice(1)}{f === 'pending' && stats?.pending ? ` (${stats.pending})` : ''}
          </button>
        ))}
      </div>

      {/* table */}
      <div style={S.tableWrap}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr>
              {cols.map(([k, l]) => (
                <th key={k} onClick={() => setSortK(k)} style={S.th}>
                  {l}{sort.k === k ? (sort.dir === 1 ? ' ▲' : ' ▼') : ''}
                </th>
              ))}
              <th style={{ ...S.th, cursor: 'default', textAlign: 'right' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? <tr><td colSpan={13} style={{ padding: 30, textAlign: 'center', color: '#8a93a3' }}>Loading…</td></tr> :
              sorted.map(p => (
                <tr key={p.id} style={{ borderTop: '1px solid var(--border,#1a1f2b)' }}>
                  <td style={S.td}>
                    <span style={{ marginRight: 7 }}>{p.avatar || '📈'}</span>
                    <b>{p.name}</b>
                    {p.is_real && <span title="Real verified" style={{ fontSize: 9, fontWeight: 800, color: '#0b0e14', background: '#34D399', borderRadius: 3, padding: '1px 4px', marginLeft: 6 }}>REAL</span>}
                    {p.featured && <span title="Featured" style={{ color: '#ffaa00', marginLeft: 5 }}>★</span>}
                    {p.abuse_flag && <span title={`Abuse flag: ${p.abuse_flag}`} style={{ color: '#ff5d6c', marginLeft: 5 }}>⚠</span>}
                  </td>
                  <td style={S.td}>{p.strategy}</td>
                  <td style={{ ...S.td, color: '#8a93a3' }}>{p.markets}</td>
                  <td style={S.td}>{p.days_active}d</td>
                  <td style={{ ...S.td, fontWeight: 800, color: pos(p.return_pct) }}>{p.return_pct >= 0 ? '+' : ''}{fmt(p.return_pct, 1)}%</td>
                  <td style={S.td}>{fmt(p.win_rate, 0)}%</td>
                  <td style={{ ...S.td, color: '#ff5d6c' }}>{fmt(p.max_drawdown, 1)}%</td>
                  <td style={S.td}>{riskLabel(p.risk_level)}</td>
                  <td style={S.td}>{fmt(p.followers)}</td>
                  <td style={{ ...S.td, color: '#E8B84B', fontWeight: 700 }}>${fmt(p.total_earned)}</td>
                  <td style={S.td}>{p.active === false
                    ? <span title={`Last trade ${p.last_trade_at}`} style={{ ...S.badge, background: 'rgba(138,147,163,0.15)', color: '#8a93a3' }}>inactive</span>
                    : <span style={{ ...S.badge, background: 'rgba(0,229,160,0.12)', color: '#00e5a0' }}>active</span>}</td>
                  <td style={S.td}><span style={{ ...S.badge, ...statusStyle(p.status) }}>{p.status}</span></td>
                  <td style={{ ...S.td, textAlign: 'right', whiteSpace: 'nowrap' }}>
                    {p.status === 'pending' && <>
                      <button style={S.approve} onClick={() => act(p.id, 'approve')}>Approve</button>
                      <button style={S.reject} onClick={() => act(p.id, 'reject')}>Reject</button>
                    </>}
                    {p.status === 'approved' && <>
                      <button style={S.preview} onClick={() => runPreview(p)}>Preview copy ⚙</button>
                      <button style={S.feat} onClick={() => act(p.id, 'feature', { featured: !p.featured })}>{p.featured ? 'Unfeature' : 'Feature ★'}</button>
                    </>}
                    {p.status === 'rejected' && <button style={S.approve} onClick={() => act(p.id, 'approve')}>Re-approve</button>}
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>

      {preview && (
        <div style={S.overlay} onClick={() => setPreview(null)}>
          <div style={S.modal} onClick={e => e.stopPropagation()}>
            <button style={S.close} onClick={() => setPreview(null)}>✕</button>
            <div style={{ fontSize: 17, fontWeight: 800, marginBottom: 2 }}>Replication preview · {preview.provider.name}</div>
            <div style={{ fontSize: 12, color: 'var(--text2,#8a93a3)', marginBottom: 14 }}>
              Computes the mirror orders that each follower WOULD receive — dry-run, no MT orders placed.
            </div>
            {previewBusy && <div style={{ color: '#8a93a3', padding: 20 }}>Computing…</div>}
            {preview.data?.error && <div style={{ color: '#ff5d6c' }}>Could not compute preview.</div>}
            {preview.data && !preview.data.error && <>
              <div style={{ display: 'flex', gap: 10, marginBottom: 14, flexWrap: 'wrap' }}>
                {[['Master trades', preview.data.master_trades], ['Active followers', preview.data.active_followers],
                  ['Orders generated', preview.data.orders_generated],
                  ['Live execution', preview.data.live_enabled ? 'ENABLED' : 'OFF (gated)']].map(([l, v]: any) => (
                  <div key={l} style={S.miniKpi}><div style={{ fontWeight: 800, color: l === 'Live execution' ? (preview.data.live_enabled ? '#ff5d6c' : '#00e5a0') : '#fff' }}>{v}</div><div style={{ fontSize: 10.5, color: '#8a93a3' }}>{l}</div></div>
                ))}
              </div>
              <div style={{ maxHeight: 300, overflowY: 'auto', border: '1px solid var(--border,#1a1f2b)', borderRadius: 10 }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
                  <thead><tr>{['Follower', 'Symbol', 'Side', 'Master', 'Mode ×mult', 'Follower lots', 'Status'].map(h => <th key={h} style={{ ...S.th, position: 'sticky', top: 0 }}>{h}</th>)}</tr></thead>
                  <tbody>
                    {(preview.data.sample || []).map((o: any, i: number) => (
                      <tr key={i} style={{ borderTop: '1px solid var(--border,#1a1f2b)' }}>
                        <td style={S.td}>{o.follower_login || `#${o.follower_id}`}{o.client_id ? ' (real)' : ''}</td>
                        <td style={S.td}>{o.symbol}</td>
                        <td style={{ ...S.td, color: o.side === 'Buy' ? '#00e5a0' : '#ff5d6c' }}>{o.side}</td>
                        <td style={{ ...S.td, color: '#8a93a3' }}>{o.master_lots} lot</td>
                        <td style={S.td}>{o.copy_mode} ×{o.multiplier}</td>
                        <td style={{ ...S.td, fontWeight: 800 }}>{o.follower_lots} lot</td>
                        <td style={S.td}><span style={{ ...S.badge, background: 'rgba(10,132,255,0.12)', color: '#4DA8FF' }}>{o.status}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div style={{ fontSize: 11.5, color: '#8a93a3', marginTop: 12 }}>
                ⓘ Live auto-execution stays OFF until the MT bridge order route is wired and tested on one account.
              </div>
            </>}
          </div>
        </div>
      )}
    </div>
  );
}

function statusStyle(s: string): any {
  if (s === 'approved') return { background: 'rgba(0,229,160,0.12)', color: '#00e5a0' };
  if (s === 'pending') return { background: 'rgba(255,170,0,0.12)', color: '#ffaa00' };
  return { background: 'rgba(255,93,108,0.12)', color: '#ff5d6c' };
}

const S: any = {
  kpi: { background: 'var(--card,#0d1016)', border: '1px solid var(--border,#1a1f2b)', borderRadius: 14, padding: '15px 16px' },
  tab: { padding: '8px 15px', borderRadius: 9, background: 'transparent', border: '1px solid var(--border,#1a1f2b)', color: 'var(--text2,#9aa3b3)', fontSize: 13, fontWeight: 600, cursor: 'pointer' },
  tabActive: { background: 'rgba(10,132,255,0.14)', borderColor: 'rgba(10,132,255,0.45)', color: '#fff' },
  tableWrap: { background: 'var(--card,#0d1016)', border: '1px solid var(--border,#1a1f2b)', borderRadius: 14, overflow: 'hidden' },
  th: { textAlign: 'left', padding: '11px 12px', fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text2,#8a93a3)', cursor: 'pointer', userSelect: 'none', background: 'var(--card2,#0b0e14)' },
  td: { padding: '11px 12px', verticalAlign: 'middle' },
  badge: { padding: '3px 9px', borderRadius: 99, fontSize: 11, fontWeight: 700, textTransform: 'capitalize' },
  approve: { padding: '6px 11px', borderRadius: 7, background: 'rgba(0,229,160,0.14)', border: '1px solid rgba(0,229,160,0.4)', color: '#00e5a0', cursor: 'pointer', fontSize: 12, fontWeight: 700, marginLeft: 6 },
  reject: { padding: '6px 11px', borderRadius: 7, background: 'rgba(255,93,108,0.12)', border: '1px solid rgba(255,93,108,0.4)', color: '#ff5d6c', cursor: 'pointer', fontSize: 12, fontWeight: 700, marginLeft: 6 },
  feat: { padding: '6px 11px', borderRadius: 7, background: 'transparent', border: '1px solid rgba(255,170,0,0.4)', color: '#ffaa00', cursor: 'pointer', fontSize: 12, fontWeight: 700, marginLeft: 6 },
  preview: { padding: '6px 11px', borderRadius: 7, background: 'rgba(10,132,255,0.12)', border: '1px solid rgba(10,132,255,0.4)', color: '#4DA8FF', cursor: 'pointer', fontSize: 12, fontWeight: 700, marginLeft: 6 },
  overlay: { position: 'fixed', inset: 0, background: 'rgba(5,7,11,0.72)', zIndex: 200, display: 'flex', alignItems: 'flex-start', justifyContent: 'center', overflowY: 'auto', padding: '50px 16px' },
  modal: { position: 'relative', width: 720, maxWidth: '100%', background: 'var(--card,#0d1016)', border: '1px solid var(--border,#232a38)', borderRadius: 16, padding: 22, color: 'var(--text,#e7ecf3)' },
  close: { position: 'absolute', top: 12, right: 12, width: 30, height: 30, borderRadius: 8, background: '#161b25', border: '1px solid #2a3240', color: '#e7ecf3', cursor: 'pointer' },
  miniKpi: { flex: 1, minWidth: 110, background: 'var(--card2,#0b0e14)', border: '1px solid var(--border,#1a1f2b)', borderRadius: 10, padding: '10px 12px', textAlign: 'center' },
};

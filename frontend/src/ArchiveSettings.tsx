import React, { useState, useEffect, useCallback } from 'react';
import { apiGet, apiPost } from './api';
import { CT } from './crmTable';

/* Settings -> Archive. Two tabs: archived Clients / archived Leads, with their owning sales agent
   and details. Read-only browse view. An archived record returns to the active list automatically
   when the person re-engages (portal login, deposit, a logged call, or a new Meta-form submission)
   — handled server-side in reactivation.py — gaining +50 score and a 📦 archive re-capture badge. */

const money = (n: any) => (n == null ? '—' : '$' + Number(n).toLocaleString(undefined, { maximumFractionDigits: 0 }));

export default function ArchiveSettings() {
  const [tab, setTab] = useState<'clients' | 'leads'>('clients');
  const [search, setSearch] = useState('');
  const [q, setQ] = useState('');
  const [rows, setRows] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [sweeping, setSweeping] = useState(false);
  const [msg, setMsg] = useState('');

  const load = useCallback(() => {
    setLoading(true);
    apiGet(`/settings/archive/${tab}?search=${encodeURIComponent(q)}&limit=200`)
      .then((r: any) => { setRows(r?.[tab] || []); setTotal(r?.total || 0); })
      .catch(() => { setRows([]); setTotal(0); })
      .finally(() => setLoading(false));
  }, [tab, q]);
  useEffect(() => { load(); }, [load]);
  // debounce search
  useEffect(() => { const t = setTimeout(() => setQ(search), 350); return () => clearTimeout(t); }, [search]);

  const runSweep = async () => {
    setSweeping(true); setMsg('');
    try {
      const r: any = await apiPost('/settings/archive/sweep', {});
      setMsg(`Re-capture sweep done — ${r?.clients_reactivated ?? 0} client(s) came back.`);
      load();
    } catch { setMsg('Sweep failed.'); }
    finally { setSweeping(false); }
  };

  return (
    <div style={{ padding: 24, color: 'var(--text,#fff)', maxWidth: 1180, margin: '0 auto' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap', marginBottom: 6 }}>
        <h1 style={{ fontSize: 22, fontWeight: 800, margin: 0 }}>🗄 Archive</h1>
        <div style={{ flex: 1 }} />
        <button onClick={runSweep} disabled={sweeping} style={S.sweepBtn}>{sweeping ? 'Checking…' : '↺ Re-capture sweep'}</button>
      </div>
      <div style={{ fontSize: 12.5, color: 'var(--text2,#8A93A3)', marginBottom: 16, lineHeight: 1.5 }}>
        Inactive clients & leads kept for history. They return to the active list automatically the moment the
        person re-engages (portal login, deposit, a logged call, or a new Meta-form submission) — earning +50
        score and a 📦 re-capture badge (a new Meta submission also gets the ♻ recapture badge).
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 14 }}>
        {([['clients', '👤 Archived Clients'], ['leads', '🧲 Archived Leads']] as const).map(([k, label]) => (
          <button key={k} onClick={() => { setTab(k); setRows([]); }} style={{ ...S.tab, ...(tab === k ? S.tabOn : {}) }}>{label}</button>
        ))}
        <div style={{ flex: 1 }} />
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search name / email / phone…" style={S.search} />
      </div>

      {msg && <div style={{ fontSize: 12.5, color: '#FF6A1A', marginBottom: 10 }}>{msg}</div>}
      <div style={{ fontSize: 12, color: 'var(--text2,#8A93A3)', marginBottom: 8 }}>
        {loading ? 'Loading…' : `${total.toLocaleString('en-GB')} archived ${tab}${rows.length < total ? ` · showing first ${rows.length}` : ''}`}
      </div>

      <div style={S.panel}>
        <div style={CT.scroll}>
          <table style={CT.table}>
            {tab === 'clients' ? (
              <>
                <thead><tr style={CT.theadTr}>
                  <th style={CT.th()}>Login</th><th style={CT.th()}>Name</th><th style={CT.th()}>Phone</th>
                  <th style={CT.th()}>Country</th><th style={CT.th()}>Platform</th>
                  <th style={CT.th(false, 'right')}>Balance</th>
                  <th style={CT.th(false, 'right')}>Deposited</th>
                  <th style={CT.th()}>First deposit</th><th style={CT.th()}>Last activity</th>
                  <th style={CT.th()}>Sales agent</th><th style={CT.th()}>Archived</th>
                </tr></thead>
                <tbody>
                  {rows.map((c, i) => (
                    <tr key={i} style={CT.row()}>
                      <td style={CT.td}>{c.login}</td>
                      <td style={{ ...CT.td, color: '#fff', fontWeight: 600 }}>{c.name || '—'}</td>
                      <td style={CT.td}>{c.phone || '—'}</td>
                      <td style={CT.td}>{c.country || '—'}</td>
                      <td style={CT.td}>{c.platform}{c.n_accounts > 1 && <span style={{ color: 'var(--text2,#8A93A3)', fontSize: 11 }}> · {c.n_accounts} accts</span>}</td>
                      <td style={{ ...CT.td, textAlign: 'right' }}>{money(c.balance)}</td>
                      <td style={{ ...CT.td, textAlign: 'right', color: '#00e5a0' }}>{money(c.total_deposits)}</td>
                      <td style={{ ...CT.td, color: 'var(--text2,#8A93A3)' }}>{c.first_deposit_date || '—'}</td>
                      <td style={CT.td}>{c.last_activity_date
                        ? <span>{c.last_activity_date}{c.last_activity_type && <span style={{ color: 'var(--text2,#8A93A3)', fontSize: 11 }}> · {c.last_activity_type}</span>}</span>
                        : <span style={{ color: 'var(--text2,#8A93A3)' }}>—</span>}</td>
                      <td style={CT.td}>{c.agent}</td>
                      <td style={{ ...CT.td, color: 'var(--text2,#8A93A3)' }}>{(c.archived_at || '').slice(0, 10)}</td>
                    </tr>
                  ))}
                  {!loading && !rows.length && <tr><td colSpan={11} style={S.empty}>No archived clients.</td></tr>}
                </tbody>
              </>
            ) : (
              <>
                <thead><tr style={CT.theadTr}>
                  <th style={CT.th()}>Name</th><th style={CT.th()}>Phone</th><th style={CT.th()}>Email</th>
                  <th style={CT.th()}>Country</th><th style={CT.th()}>Source</th>
                  <th style={CT.th(false, 'right')}>Score</th>
                  <th style={CT.th()}>Sales agent</th><th style={CT.th()}>Archived</th>
                </tr></thead>
                <tbody>
                  {rows.map((l, i) => (
                    <tr key={i} style={CT.row()}>
                      <td style={{ ...CT.td, color: '#fff', fontWeight: 600 }}>{l.name || '—'}</td>
                      <td style={CT.td}>{l.phone || '—'}</td>
                      <td style={CT.td}>{l.email || '—'}</td>
                      <td style={CT.td}>{l.country || '—'}</td>
                      <td style={CT.td}>{l.source || '—'}{l.campaign ? ` · ${l.campaign}` : ''}</td>
                      <td style={{ ...CT.td, textAlign: 'right' }}>{l.score ?? '—'}</td>
                      <td style={CT.td}>{l.agent}</td>
                      <td style={{ ...CT.td, color: 'var(--text2,#8A93A3)' }}>{(l.updated_at || '').slice(0, 10)}</td>
                    </tr>
                  ))}
                  {!loading && !rows.length && <tr><td colSpan={8} style={S.empty}>No archived leads.</td></tr>}
                </tbody>
              </>
            )}
          </table>
        </div>
      </div>
    </div>
  );
}

const S: any = {
  tab: { padding: '9px 16px', borderRadius: 9, background: 'var(--bg-input,#373f4d)', border: '1px solid var(--border2,#626d80)', color: 'var(--text2,#888)', fontSize: 13, fontWeight: 700, cursor: 'pointer' },
  tabOn: { background: 'rgba(248,80,10,0.12)', border: '1px solid #F8500A', color: '#FF6A1A' },
  search: { padding: '9px 13px', borderRadius: 9, background: 'var(--bg-input,#373f4d)', border: '1px solid var(--border2,#626d80)', color: 'var(--text,#fff)', fontSize: 13, minWidth: 240, outline: 'none' },
  sweepBtn: { padding: '8px 16px', borderRadius: 9, background: '#F8500A', color: '#fff', border: 'none', fontSize: 12.5, fontWeight: 800, cursor: 'pointer' },
  panel: { background: 'var(--bg-card,#2c333e)', border: '1px solid var(--border,#4f596b)', borderRadius: 14, padding: 6 },
  empty: { padding: 28, textAlign: 'center' as const, color: 'var(--text2,#8A93A3)' },
};

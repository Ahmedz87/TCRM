import React, { useState, useEffect, useCallback } from 'react';
import { apiGet } from './api';
import NetworkBadge, { netColor } from './NetworkBadge';

// The two tables the desk asked for: LEFT = everyone WITH a relation (+ why), RIGHT = everyone clean.
// Both read the ONE source (entity_relations / entity_status via /network/relations). Updated daily
// by relation_engine.py — anytime a new tie is caught, the person moves from the right table to the left.

const STATE_INFO: Record<string, { label: string; color: string }> = {
  nda:              { label: '🟢 New Client',          color: '#00e5a0' },
  nda_pending:      { label: '🟡 Warming up · <1 lot', color: '#ffcc00' },
  ftd_pending:      { label: 'First dep · checking 48h', color: '#ffd166' },
  ftd_related:      { label: '🔴 Related',             color: '#ff8c00' },
  unfunded_related: { label: 'Lead · related',         color: '#ff6b6b' },
  unfunded_clean:   { label: 'Lead · clean',           color: '#8a93a3' },
};
const StateChip = ({ s }: { s: string }) => {
  const i = STATE_INFO[s] || { label: s || '—', color: '#8a93a3' };
  return <span style={{ fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 99,
    background: i.color + '22', color: i.color, whiteSpace: 'nowrap' }}>{i.label}</span>;
};

const goClient = (r: any) => {
  if (r.login) window.dispatchEvent(new CustomEvent('navigate', { detail: { page: 'clients', login: r.login } }));
  else if (r.lead_id) window.dispatchEvent(new CustomEvent('navigate', { detail: { page: 'leads', search: r.name } }));
};

function Panel({ view, title, accent }: { view: 'related' | 'unrelated'; title: string; accent: string }) {
  const [rows, setRows] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [state, setState] = useState('');
  const [sort, setSort] = useState('time');
  const [loading, setLoading] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    const p = new URLSearchParams({ view, page: String(page), page_size: '40', sort });
    if (search) p.set('search', search);
    if (state) p.set('state', state);
    apiGet(`/network/relations?${p}`).then((d: any) => {
      setRows(d.rows || []); setTotal(d.total ?? (d.rows || []).length);
    }).catch(() => setRows([])).finally(() => setLoading(false));
  }, [view, page, search, state, sort]);
  useEffect(() => { const t = setTimeout(load, search ? 300 : 0); return () => clearTimeout(t); }, [load, search]);

  const states = view === 'related'
    ? [['', 'All related'], ['ftd_related', 'Related'], ['unfunded_related', 'Lead · related']]
    : [['', 'All clean'], ['nda', 'New Client'], ['nda_pending', 'Warming up (<1 lot)'], ['ftd_pending', 'First dep · checking'], ['unfunded_clean', 'Lead · clean']];
  const nfmt = (n: number) => (n || 0).toLocaleString('en-GB');

  return (
    <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', border: '1px solid #373f4d', borderRadius: 12, background: '#20252f', overflow: 'hidden' }}>
      <div style={{ padding: '10px 14px', borderBottom: '1px solid #373f4d', display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <span style={{ width: 10, height: 10, borderRadius: '50%', background: accent }} />
        <span style={{ fontWeight: 800, color: '#e6e9ef', fontSize: 14 }}>{title}</span>
        {/* the COUNT of whatever filter is active */}
        <span style={{ fontSize: 13, color: accent, fontWeight: 800 }}>{nfmt(total)}</span>
        <span style={{ fontSize: 10, color: '#667' }}>{state ? 'in filter' : 'total'}</span>
        <input value={search} onChange={e => { setSearch(e.target.value); setPage(1); }} placeholder="Search name…"
          style={{ marginLeft: 'auto', padding: '5px 10px', background: '#11141a', border: '1px solid #2a3142', borderRadius: 7, color: '#e0e0e0', fontSize: 11, width: 130, outline: 'none' }} />
        <select value={state} onChange={e => { setState(e.target.value); setPage(1); }}
          style={{ padding: '5px 8px', background: '#11141a', border: '1px solid #2a3142', borderRadius: 7, color: '#9aa3b2', fontSize: 11 }}>
          {states.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
        {view === 'related' && (
          <select value={sort} onChange={e => { setSort(e.target.value); setPage(1); }} title="Sort"
            style={{ padding: '5px 8px', background: '#11141a', border: '1px solid #2a3142', borderRadius: 7, color: '#9aa3b2', fontSize: 11 }}>
            <option value="time">Newest</option>
            <option value="score">Risk score</option>
            <option value="links">Most linked</option>
          </select>
        )}
      </div>

      <div style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
        {loading && !rows.length ? <div style={{ padding: 30, textAlign: 'center', color: '#556' }}>Loading…</div>
          : !rows.length ? <div style={{ padding: 30, textAlign: 'center', color: '#556' }}>Nobody here.</div>
          : rows.map((r, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '9px 14px', borderBottom: '1px solid #262c36' }}>
              {view === 'related'
                ? <NetworkBadge score={r.network_score} login={r.login} leadId={r.lead_id} />
                : <span style={{ width: 34, textAlign: 'center', fontSize: 11, color: '#3a4150', fontFamily: 'monospace' }}>0</span>}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div onClick={() => goClient(r)} className="hover-underline"
                  style={{ fontSize: 13, color: '#4ea1ff', cursor: 'pointer', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {r.name} <span style={{ fontSize: 10, color: '#667' }}>{r.kind === 'lead' ? '· lead' : ''}</span>
                </div>
                {view === 'related' && <div style={{ fontSize: 11, color: '#8a93a3', marginTop: 2 }}>
                  {r.decisive && <span style={{ color: '#ff4d4d', fontWeight: 700 }}>● </span>}
                  {r.top_reason}{r.n_related ? <span style={{ color: '#556' }}> · linked to {r.n_related}</span> : ''}
                </div>}
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 3 }}>
                <StateChip s={r.state} />
                {r.since && <span style={{ fontSize: 9, color: '#556' }}>{r.since}</span>}
              </div>
            </div>
          ))}
      </div>

      {total > 40 && (
        <div style={{ padding: '8px 14px', borderTop: '1px solid #373f4d', display: 'flex', alignItems: 'center', gap: 12, fontSize: 12, color: '#889' }}>
          <button disabled={page <= 1} onClick={() => setPage(p => p - 1)} style={pbtn(page <= 1)}>‹ Prev</button>
          <span>Page {page} · {nfmt(total)}</span>
          <button disabled={page * 40 >= total} onClick={() => setPage(p => p + 1)} style={pbtn(page * 40 >= total)}>Next ›</button>
        </div>
      )}
    </div>
  );
}
const pbtn = (dis: boolean): React.CSSProperties => ({
  padding: '4px 10px', borderRadius: 6, border: '1px solid #373f4d', background: 'transparent',
  color: dis ? '#445' : '#9aa3b2', cursor: dis ? 'default' : 'pointer', fontSize: 11,
});

export default function RelationsTables() {
  const [summary, setSummary] = useState<any>(null);
  useEffect(() => { apiGet('/network/relations/summary').then(setSummary).catch(() => {}); }, []);

  const kpi = (label: string, val: any, c: string) => (
    <div style={{ background: '#262c36', border: '1px solid #373f4d', borderRadius: 10, padding: '8px 14px' }}>
      <div style={{ fontSize: 9, color: '#667', textTransform: 'uppercase', letterSpacing: .5 }}>{label}</div>
      <div style={{ fontSize: 18, fontWeight: 800, color: c }}>{val}</div>
    </div>
  );
  const n = (x: any) => (x || 0).toLocaleString('en-GB');

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 12, padding: 14, minHeight: 0, overflow: 'hidden' }}>
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
        {kpi('Related (any tie)', n(summary?.related), '#ff6b6b')}
        {kpi('Clean (no tie)', n(summary?.clean), '#00e5a0')}
        {kpi('Decisive (device/wallet)', n(summary?.decisive), '#ff4d4d')}
        {kpi('New Clients', n(summary?.nda), '#00e5a0')}
        {kpi('First dep · checking 48h', n(summary?.ftd_pending), '#ffd166')}
      </div>
      <div style={{ flex: 1, display: 'flex', gap: 12, minHeight: 0 }}>
        <Panel view="related" title="Related — has a connection" accent="#ff6b6b" />
        <Panel view="unrelated" title="Clean — no connection" accent="#00e5a0" />
      </div>
    </div>
  );
}

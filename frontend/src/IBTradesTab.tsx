import React, { useEffect, useState, useCallback, useRef } from 'react';
import { apiGet } from './api';

// Searchable dropdown (combobox): type to search, pick a result, or clear.
function SearchSelect({ placeholder, selected, onPick, onClear, fetcher, renderItem, width = 200 }: {
  placeholder: string;
  selected: { label: string } | null;
  onPick: (item: any) => void;
  onClear: () => void;
  fetcher: (q: string) => Promise<any[]>;
  renderItem: (item: any) => React.ReactNode;
  width?: number;
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState('');
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const inp: React.CSSProperties = { padding: '5px 8px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 7, color: '#e0e0e0', fontSize: 11, outline: 'none', width: '100%', boxSizing: 'border-box' };

  useEffect(() => {
    if (!open) return;
    const t = setTimeout(async () => {
      if (q.trim().length < 1) { setItems([]); return; }
      setLoading(true);
      try { setItems(await fetcher(q.trim())); } catch { setItems([]); }
      setLoading(false);
    }, 250);
    return () => clearTimeout(t);
  }, [q, open, fetcher]);

  useEffect(() => {
    const h = (e: any) => { if (box.current && !box.current.contains(e.target)) setOpen(false); };
    window.addEventListener('mousedown', h);
    return () => window.removeEventListener('mousedown', h);
  }, []);

  if (selected) {
    return (
      <div style={{ ...inp, width, display: 'flex', alignItems: 'center', gap: 6, cursor: 'default' }}>
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{selected.label}</span>
        <span onClick={onClear} title="Clear" style={{ cursor: 'pointer', color: '#ff5d6c', marginLeft: 'auto', fontWeight: 700 }}>✕</span>
      </div>
    );
  }
  return (
    <div ref={box} style={{ position: 'relative', width }}>
      <input value={q} onChange={e => { setQ(e.target.value); setOpen(true); }} onFocus={() => setOpen(true)} placeholder={placeholder} style={inp} />
      {open && q.trim().length >= 1 && (
        <div style={{ position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 50, marginTop: 4, background: '#2c333e', border: '1px solid #626d80', borderRadius: 8, maxHeight: 260, overflowY: 'auto', boxShadow: '0 10px 28px rgba(0,0,0,0.55)' }}>
          {loading && <div style={{ padding: '8px 10px', color: '#888', fontSize: 12 }}>Searching…</div>}
          {!loading && items.length === 0 && <div style={{ padding: '8px 10px', color: '#888', fontSize: 12 }}>No matches</div>}
          {!loading && items.map((it, i) => (
            <div key={i} onClick={() => { onPick(it); setOpen(false); setQ(''); }}
              style={{ padding: '7px 10px', cursor: 'pointer', borderTop: i ? '1px solid #373f4d' : 'none', fontSize: 12 }}
              onMouseEnter={e => (e.currentTarget.style.background = '#373f4d')}
              onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}>
              {renderItem(it)}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// Reusable IB "Trades" tab — every closed trade of an IB's clients, with the commission earned,
// eligibility (5-min rule / credit), and full filtering. Used in IB Admin and the IB portal.
//   endpoint: '/ibs/{id}/trades' (admin) or '/portal/ib-trades' (portal)
//   period/dateFrom/dateTo: driven by the parent's period selector

const VIEWS: [string, string, string][] = [
  ['eligible', 'Eligible (paid)', '#00e5a0'],
  ['short', 'Short < 5min', '#ff8800'],
  ['credit', 'Credit trades', '#ffaa00'],
  ['all', 'All', '#9aa3b3'],
];
const fmtUSD = (n: number) => '$' + (n || 0).toLocaleString(undefined, { maximumFractionDigits: 2 });
const fmtT = (s: string | null) => s ? s.replace('T', ' ').slice(0, 16) : '—';

export default function IBTradesTab({ endpoint, period, dateFrom, dateTo }:
  { endpoint: string; period: string; dateFrom?: string; dateTo?: string }) {
  const [view, setView] = useState('eligible');
  const [f, setF] = useState<any>({ country: '', city: '', platform: '', account_type: '' });
  const [selIB, setSelIB] = useState<any>(null);          // {id,label} selected IB filter
  const [selClient, setSelClient] = useState<any>(null);  // {login,label} selected client filter
  const [page, setPage] = useState(1);
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  // all-IBs (admin-wide) view = endpoint is /ibs/0/trades; otherwise a single IB is fixed
  const isAllIBs = /\/ibs\/0\/trades/.test(endpoint);
  const pathIbId = (() => { const m = endpoint.match(/\/ibs\/(\d+)\/trades/); return m ? parseInt(m[1]) : 0; })();
  const clientScopeIb = pathIbId > 0 ? pathIbId : (selIB?.id || 0);

  const load = useCallback(async () => {
    setLoading(true);
    const p = new URLSearchParams({ period, view, page: String(page), page_size: '100' });
    if (period === 'custom') { if (dateFrom) p.set('date_from', dateFrom); if (dateTo) p.set('date_to', dateTo); }
    Object.entries(f).forEach(([k, v]) => { if (v) p.set(k, String(v)); });
    if (selClient) p.set('client_login', String(selClient.login));
    if (selIB && isAllIBs) p.set('f_ib_id', String(selIB.id));
    try { setData(await apiGet(`${endpoint}?${p}`)); } catch { setData(null); }
    setLoading(false);
  }, [endpoint, period, dateFrom, dateTo, view, page, f, selIB, selClient, isAllIBs]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { setPage(1); }, [view, f, period, selIB, selClient]);

  const opts = data?.filters || { countries: [], cities: [], account_types: [], platforms: [] };
  const t = data?.totals || { trades: 0, lots: 0, commission: 0, profit: 0 };
  const sel: React.CSSProperties = { padding: '5px 8px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 7, color: '#e0e0e0', fontSize: 11, outline: 'none' };
  const th: React.CSSProperties = { padding: '8px 10px', fontSize: 10, color: '#667', textTransform: 'uppercase', textAlign: 'left', whiteSpace: 'nowrap' };
  const td: React.CSSProperties = { padding: '8px 10px', fontSize: 12, borderTop: '1px solid #373f4d', whiteSpace: 'nowrap' };

  return (
    <div style={{ background: '#2c333e', border: '1px solid #4f596b', borderRadius: 12, overflow: 'hidden' }}>
      {/* view toggle */}
      <div style={{ display: 'flex', gap: 6, padding: '10px 12px', borderBottom: '1px solid #4f596b', flexWrap: 'wrap', alignItems: 'center' }}>
        {VIEWS.map(([k, lbl, c]) => (
          <button key={k} onClick={() => setView(k)}
            style={{ padding: '5px 12px', borderRadius: 7, fontSize: 11.5, cursor: 'pointer', fontWeight: 600,
              border: `1px solid ${view === k ? c : '#626d80'}`, background: view === k ? `${c}1a` : 'transparent', color: view === k ? c : '#888' }}>
            {lbl}
          </button>
        ))}
        <div style={{ marginLeft: 'auto', fontSize: 11.5, color: '#9aa3b3' }}>
          {t.trades.toLocaleString()} trades · {Math.round(t.lots).toLocaleString()} lots ·
          {view === 'eligible'
            ? <b style={{ color: '#00e5a0' }}> {fmtUSD(t.commission)} paid</b>
            : <b style={{ color: '#ff8800' }}> {fmtUSD(t.potential || 0)} saved (not paid)</b>}
        </div>
      </div>

      {/* filters */}
      <div style={{ display: 'flex', gap: 6, padding: '10px 12px', borderBottom: '1px solid #4f596b', flexWrap: 'wrap', alignItems: 'center' }}>
        {isAllIBs && (
          <SearchSelect
            placeholder="Search IB (name, email, code)…"
            width={230}
            selected={selIB}
            onClear={() => setSelIB(null)}
            fetcher={async (q) => { const d: any = await apiGet(`/ibs/search?q=${encodeURIComponent(q)}`); return d.ibs || []; }}
            onPick={(it) => setSelIB({ id: it.id, label: `${(it.ib_code || '').replace(/^IB/i, '')} · ${it.name}` })}
            renderItem={(it) => (
              <div>
                <div style={{ color: '#e0e0e0' }}>{it.name || '(no name)'} <span style={{ color: '#00aaff' }}>{(it.ib_code || '').replace(/^IB/i, '')}</span></div>
                <div style={{ color: '#8a93a3', fontSize: 11 }}>{it.email || '—'}</div>
              </div>
            )}
          />
        )}
        <SearchSelect
          placeholder="Search client (name, email, phone, account)…"
          width={250}
          selected={selClient}
          onClear={() => setSelClient(null)}
          fetcher={async (q) => { const d: any = await apiGet(`/ibs/clients/search?q=${encodeURIComponent(q)}&ib_id=${clientScopeIb}`); return d.clients || []; }}
          onPick={(it) => setSelClient({ login: it.login, label: `${it.name || '#' + it.login} (#${it.login})` })}
          renderItem={(it) => (
            <div>
              <div style={{ color: '#e0e0e0' }}>{it.name || '(no name)'} <span style={{ color: '#4d9fff', fontFamily: 'monospace' }}>#{it.login}</span></div>
              <div style={{ color: '#8a93a3', fontSize: 11 }}>{[it.email, it.phone].filter(Boolean).join(' · ') || '—'}</div>
            </div>
          )}
        />
        <select value={f.platform} onChange={e => setF({ ...f, platform: e.target.value })} style={sel}>
          <option value="">All platforms</option>{(opts.platforms || []).map((x: string) => <option key={x} value={x}>{x}</option>)}
        </select>
        <select value={f.account_type} onChange={e => setF({ ...f, account_type: e.target.value })} style={sel}>
          <option value="">All account types</option>{(opts.account_types || []).map((x: string) => <option key={x} value={x}>{x}</option>)}
        </select>
        <select value={f.country} onChange={e => setF({ ...f, country: e.target.value })} style={sel}>
          <option value="">All countries</option>{(opts.countries || []).map((x: string) => <option key={x} value={x}>{x}</option>)}
        </select>
        <select value={f.city} onChange={e => setF({ ...f, city: e.target.value })} style={sel}>
          <option value="">All cities</option>{(opts.cities || []).map((x: string) => <option key={x} value={x}>{x}</option>)}
        </select>
        {(selIB || selClient || f.country || f.city || f.platform || f.account_type) &&
          <button onClick={() => { setF({ country: '', city: '', platform: '', account_type: '' }); setSelIB(null); setSelClient(null); }}
            style={{ ...sel, color: '#ff5d6c', borderColor: '#ff4d4d', cursor: 'pointer' }}>✕ Clear</button>}
      </div>

      {/* table */}
      <div style={{ overflowX: 'auto', maxHeight: 540, overflowY: 'auto' }}>
        <table style={{ borderCollapse: 'collapse', width: '100%', minWidth: 1100 }}>
          <thead style={{ position: 'sticky', top: 0, background: '#373f4d' }}>
            <tr>{['IB', 'Trade ID', 'Account', 'Client', 'Country', 'City', 'Platform', 'Type', 'Symbol', 'Dir', 'Open', 'Close', 'Hold', 'Lots', 'Profit', 'Commission'].map(h =>
              <th key={h} style={th}>{h}</th>)}</tr>
          </thead>
          <tbody>
            {loading && <tr><td style={td} colSpan={16}>Loading…</td></tr>}
            {!loading && (data?.trades || []).length === 0 && <tr><td style={{ ...td, color: '#666' }} colSpan={16}>No trades for this filter/period.</td></tr>}
            {!loading && (data?.trades || []).map((r: any, i: number) => (
              <tr key={i} style={{ background: !r.eligible ? 'rgba(255,136,0,0.05)' : 'transparent' }}>
                <td style={{ ...td, color: '#00aaff', fontWeight: 600 }} title={r.ib_name ? `${r.ib_name} · ${r.ib_code}` : (r.ib_code || '')}>{(r.ib_code || '').replace(/^IB/i, '') || '—'}</td>
                <td style={{ ...td, color: '#8a93a3', fontFamily: 'monospace' }}>{r.deal_id}</td>
                <td style={{ ...td, color: '#4d9fff', fontFamily: 'monospace' }}>{r.login}</td>
                <td style={td}>{r.client}</td>
                <td style={{ ...td, color: '#9aa3b3' }}>{r.country || '—'}</td>
                <td style={{ ...td, color: '#9aa3b3' }}>{r.city || '—'}</td>
                <td style={td}>{r.platform}</td>
                <td style={{ ...td, color: '#9aa3b3' }}>{r.account_type}</td>
                <td style={{ ...td, fontWeight: 600 }}>{r.symbol}</td>
                <td style={{ ...td, color: r.direction === 'buy' ? '#00e5a0' : '#ff5d6c' }}>{r.direction}</td>
                <td style={{ ...td, color: '#9aa3b3' }}>{fmtT(r.open_time)}</td>
                <td style={{ ...td, color: '#9aa3b3' }}>{fmtT(r.close_time)}</td>
                <td style={{ ...td, color: r.hold_min != null && r.hold_min < 5 ? '#ff8800' : '#9aa3b3' }}>{r.hold_min != null ? `${r.hold_min}m` : '—'}</td>
                <td style={{ ...td, textAlign: 'right' }}>{(r.lots || 0).toFixed(2)}</td>
                <td style={{ ...td, textAlign: 'right', color: r.profit >= 0 ? '#00e5a0' : '#ff5d6c' }}>{fmtUSD(r.profit)}</td>
                <td style={{ ...td, textAlign: 'right', fontWeight: 600, color: r.commission > 0 ? '#00e5a0' : '#667' }}>
                  {r.commission > 0 ? fmtUSD(r.commission) : <span title={r.reason} style={{ color: '#ff8800' }}>{r.reason === 'short(<5min)' ? '✗ <5min' : r.reason === 'credit' ? '✗ credit' : '$0'}</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* pager */}
      <div style={{ display: 'flex', gap: 8, padding: '10px 12px', borderTop: '1px solid #4f596b', alignItems: 'center', fontSize: 12, color: '#888' }}>
        <button disabled={page <= 1} onClick={() => setPage(page - 1)} style={{ ...sel, cursor: page <= 1 ? 'default' : 'pointer', opacity: page <= 1 ? .4 : 1 }}>← Prev</button>
        <span>Page {page}</span>
        <button disabled={(data?.trades || []).length < 100} onClick={() => setPage(page + 1)} style={{ ...sel, cursor: (data?.trades || []).length < 100 ? 'default' : 'pointer', opacity: (data?.trades || []).length < 100 ? .4 : 1 }}>Next →</button>
      </div>
    </div>
  );
}

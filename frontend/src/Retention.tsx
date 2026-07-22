import React, { useState, useEffect, useCallback } from 'react';
import { apiGet, apiPost } from './api';
import { CT } from './crmTable';

// ── theme ───────────────────────────────────────────────────────────────────
const BAND: Record<string, { c: string; bg: string; label: string }> = {
  Critical: { c: '#ff4d4d', bg: 'rgba(255,77,77,0.14)',  label: 'CRITICAL' },
  High:     { c: '#ffaa00', bg: 'rgba(255,170,0,0.14)',  label: 'HIGH' },
  Medium:   { c: '#ffd400', bg: 'rgba(255,212,0,0.12)',  label: 'MEDIUM' },
  Low:      { c: '#7bc4ff', bg: 'rgba(123,196,255,0.10)',label: 'LOW' },
  Trusted:  { c: '#00e5a0', bg: 'rgba(0,229,160,0.12)',  label: 'TRUSTED' },
};
const bandMeta = (b: string) => BAND[b] || { c: '#8a93a5', bg: 'rgba(138,147,165,0.1)', label: b };

const CAT_ICON: Record<string, string> = {
  Deposit: '💵', Withdrawal: '🏧', Trading: '📈', Activity: '🕒', Net: '⚖️',
  Lifecycle: '📅', Source: '🎯', Bonus: '🎁', Advanced: '🧠', Value: '⭐',
  Admin: '🗂', Time: '⏰', Sequence: '🔗', Communication: '📞', Tech: '💻',
  Cluster: '👥', Behavior: '🎲', Compliance: '🛡️', IB: '🤝', Governance: '📋',
};

const money = (v: number) => {
  const a = Math.abs(v || 0); const s = (v || 0) < 0 ? '-' : '';
  return a >= 1e6 ? `${s}$${(a / 1e6).toFixed(2)}M` : a >= 1e3 ? `${s}$${(a / 1e3).toFixed(1)}K` : `${s}$${Math.round(a)}`;
};

const card: React.CSSProperties = {
  background: 'var(--bg-card,#2c333e)', border: '1px solid var(--border,#4f596b)', borderRadius: 12,
};

export default function Retention() {
  const [tab, setTab] = useState<'clients' | 'rules'>('clients');
  const [summary, setSummary] = useState<any>(null);

  const loadSummary = useCallback(() => {
    apiGet('/retention/summary').then(setSummary).catch(() => {});
  }, []);
  useEffect(() => { loadSummary(); }, [loadSummary]);

  return (
    <div style={{ padding: 16, height: '100%', overflow: 'auto', color: 'var(--text,#e6e9ef)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 8 }}>
        <h2 style={{ margin: 0, fontSize: 22 }}>🛟 Retention Engine</h2>
        <span style={{ fontSize: 12, color: '#8a93a5' }}>
          Rule-based churn / risk scoring across 119 retention rules
        </span>
      </div>

      {/* band KPI strip */}
      {summary && (
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', margin: '10px 0 16px' }}>
          {summary.bands.map((b: any) => {
            const m = bandMeta(b.band);
            return (
              <div key={b.band} style={{ ...card, padding: '10px 16px', minWidth: 120, borderLeft: `3px solid ${m.c}` }}>
                <div style={{ fontSize: 11, color: '#8a93a5', textTransform: 'uppercase', letterSpacing: 0.5 }}>{m.label}</div>
                <div style={{ fontSize: 22, fontWeight: 800, color: m.c }}>{b.count}</div>
              </div>
            );
          })}
          <div style={{ ...card, padding: '10px 16px', minWidth: 140 }}>
            <div style={{ fontSize: 11, color: '#8a93a5', textTransform: 'uppercase', letterSpacing: 0.5 }}>At-risk (Crit+High)</div>
            <div style={{ fontSize: 22, fontWeight: 800 }}>{summary.at_risk}</div>
          </div>
          <div style={{ ...card, padding: '10px 16px', minWidth: 160 }}>
            <div style={{ fontSize: 11, color: '#8a93a5', textTransform: 'uppercase', letterSpacing: 0.5 }}>Last computed</div>
            <div style={{ fontSize: 13, fontWeight: 600, marginTop: 4 }}>
              {summary.computed_at ? new Date(summary.computed_at).toLocaleString('en-GB') : '—'}
            </div>
          </div>
        </div>
      )}

      {/* tabs */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 14, borderBottom: '1px solid var(--border,#3a4250)' }}>
        {([['clients', 'At-risk clients'], ['rules', 'Rule catalog (119)']] as const).map(([k, lbl]) => (
          <div key={k} onClick={() => setTab(k as any)}
            style={{ padding: '8px 16px', cursor: 'pointer', fontSize: 14, fontWeight: 600,
              color: tab === k ? '#00e5a0' : '#8a93a5',
              borderBottom: tab === k ? '2px solid #00e5a0' : '2px solid transparent' }}>
            {lbl}
          </div>
        ))}
      </div>

      {tab === 'clients' ? <ClientsView /> : <RulesView />}
    </div>
  );
}

// ── At-risk client list + drawer ──────────────────────────────────────────────
function ClientsView() {
  const [rows, setRows] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [band, setBand] = useState('');
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState('score');
  const [loading, setLoading] = useState(false);
  const [sel, setSel] = useState<number | null>(null);
  const pageSize = 50;

  const load = useCallback(() => {
    setLoading(true);
    const qs = new URLSearchParams({ page: String(page), page_size: String(pageSize), sort });
    if (band) qs.set('band', band);
    if (search) qs.set('search', search);
    apiGet(`/retention/clients?${qs.toString()}`)
      .then((d) => { setRows(d.clients || []); setTotal(d.total || 0); })
      .catch(() => setRows([]))
      .finally(() => setLoading(false));
  }, [page, band, search, sort]);
  useEffect(() => { load(); }, [load]);

  const pages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div>
      <div style={{ display: 'flex', gap: 10, marginBottom: 12, flexWrap: 'wrap', alignItems: 'center' }}>
        <input placeholder="Search name / phone / login…" value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1); }}
          style={inp} />
        <select value={band} onChange={(e) => { setBand(e.target.value); setPage(1); }} style={inp}>
          <option value="">All bands</option>
          {['Critical', 'High', 'Medium', 'Low', 'Trusted'].map((b) => <option key={b} value={b}>{b}</option>)}
        </select>
        <select value={sort} onChange={(e) => setSort(e.target.value)} style={inp}>
          <option value="score">Sort: risk score</option>
          <option value="band">Sort: band</option>
          <option value="fired">Sort: rules fired</option>
          <option value="deposits">Sort: deposits</option>
        </select>
        <span style={{ fontSize: 12, color: '#8a93a5', marginLeft: 'auto' }}>{total} flagged clients</span>
      </div>

      <div style={{ ...card, overflow: 'hidden' }}>
        <div style={CT.scroll}>
          <table style={CT.table}>
            <thead>
              <tr style={CT.theadTr}>
                {['Client', 'Login', 'Band', 'Risk', 'Rules', 'Top action', 'Deposits', 'Net'].map((h) => (
                  <th key={h} style={CT.th()}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading && <tr><td colSpan={8} style={{ ...CT.td, padding: 24, textAlign: 'center', color: '#8a93a5' }}>Loading…</td></tr>}
              {!loading && rows.length === 0 && <tr><td colSpan={8} style={{ ...CT.td, padding: 24, textAlign: 'center', color: '#8a93a5' }}>No flagged clients. Run the engine: <code>python retention_engine.py</code></td></tr>}
              {rows.map((r) => {
                const m = bandMeta(r.band);
                return (
                  <tr key={r.client_key} onClick={() => setSel(r.login)}
                    style={{ ...CT.row(), cursor: 'pointer' }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--bg-card,#2c333e)')}
                    onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}>
                    <td style={CT.td}>
                      <div style={{ fontWeight: 600 }}>{r.name || '—'}</div>
                      <div style={{ fontSize: 11, color: '#8a93a5' }}>{r.phone || ''}{r.n_logins > 1 ? ` · ${r.n_logins} accts` : ''}</div>
                    </td>
                    <td style={{ ...CT.td, color: '#8a93a5' }}>{r.login}</td>
                    <td style={CT.td}>
                      <span style={{ background: m.bg, color: m.c, padding: '2px 8px', borderRadius: 6, fontSize: 11, fontWeight: 700 }}>{m.label}</span>
                    </td>
                    <td style={{ ...CT.td, fontWeight: 800, color: m.c }}>{r.score}</td>
                    <td style={CT.td}>{r.fired_count}</td>
                    <td style={CT.td}>{r.top_action || '—'}<div style={{ fontSize: 11, color: '#8a93a5' }}>{r.top_days || ''}</div></td>
                    <td style={CT.td}>{money(r.total_deposits)}</td>
                    <td style={{ ...CT.td, color: (r.net_deposit || 0) < 0 ? '#ff4d4d' : '#e6e9ef' }}>{money(r.net_deposit)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* pager */}
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 12, justifyContent: 'center' }}>
        <button disabled={page <= 1} onClick={() => setPage((p) => p - 1)} style={btn}>‹ Prev</button>
        <span style={{ fontSize: 12, color: '#8a93a5' }}>Page {page} / {pages}</span>
        <button disabled={page >= pages} onClick={() => setPage((p) => p + 1)} style={btn}>Next ›</button>
      </div>

      {sel != null && <ClientDrawer login={sel} onClose={() => setSel(null)} />}
    </div>
  );
}

// ── per-client drill-in drawer ────────────────────────────────────────────────
function ClientDrawer({ login, onClose }: { login: number; onClose: () => void }) {
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState('');
  useEffect(() => {
    setD(null); setErr('');
    apiGet(`/retention/clients/${login}`).then(setD).catch(() => setErr('Could not load detail.'));
  }, [login]);

  return (
    <div onClick={onClose} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 1000, display: 'flex', justifyContent: 'flex-end' }}>
      <div onClick={(e) => e.stopPropagation()} style={{ width: 560, maxWidth: '92vw', height: '100%', background: 'var(--bg,#1c2128)', borderLeft: '1px solid var(--border,#4f596b)', overflow: 'auto', padding: 20, boxShadow: '-8px 0 24px rgba(0,0,0,0.4)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div>
            <div style={{ fontSize: 18, fontWeight: 800 }}>{d?.name || `Login ${login}`}</div>
            <div style={{ fontSize: 12, color: '#8a93a5' }}>Login {login}{d?.phone ? ` · ${d.phone}` : ''}{d && d.n_logins > 1 ? ` · ${d.n_logins} accounts` : ''}</div>
          </div>
          <button onClick={onClose} style={{ ...btn, padding: '4px 10px' }}>✕</button>
        </div>

        {err && <div style={{ marginTop: 20, color: '#ff8888' }}>{err}</div>}
        {!d && !err && <div style={{ marginTop: 20, color: '#8a93a5' }}>Loading…</div>}

        {d && (
          <>
            {(() => { const m = bandMeta(d.band); return (
              <div style={{ display: 'flex', gap: 12, margin: '16px 0', flexWrap: 'wrap' }}>
                <div style={{ ...card, padding: '10px 16px', borderLeft: `3px solid ${m.c}` }}>
                  <div style={{ fontSize: 11, color: '#8a93a5' }}>RISK SCORE</div>
                  <div style={{ fontSize: 26, fontWeight: 800, color: m.c }}>{d.score} <span style={{ fontSize: 13 }}>{m.label}</span></div>
                </div>
                <div style={{ ...card, padding: '10px 16px' }}>
                  <div style={{ fontSize: 11, color: '#8a93a5' }}>DEPOSITS / NET</div>
                  <div style={{ fontSize: 16, fontWeight: 700, marginTop: 4 }}>{money(d.total_deposits)} · <span style={{ color: (d.net_deposit || 0) < 0 ? '#ff4d4d' : '#00e5a0' }}>{money(d.net_deposit)}</span></div>
                </div>
              </div>
            ); })()}

            {d.top_action && (
              <div style={{ ...card, padding: 14, margin: '6px 0 18px', borderLeft: '3px solid #ffaa00' }}>
                <div style={{ fontSize: 11, color: '#8a93a5', textTransform: 'uppercase' }}>Recommended action</div>
                <div style={{ fontSize: 15, fontWeight: 700, marginTop: 3 }}>{d.top_action}</div>
                <div style={{ fontSize: 12, color: '#ffaa00' }}>Act within: {d.top_days}</div>
              </div>
            )}

            <div style={{ fontSize: 13, fontWeight: 700, color: '#8a93a5', marginBottom: 8 }}>
              FIRED RULES ({d.fired_count})
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {(d.fired_rules || []).map((f: any) => {
                const neg = f.points < 0;
                return (
                  <div key={f.rule_id} style={{ ...card, padding: 12, borderLeft: `3px solid ${neg ? '#00e5a0' : '#ff6b6b'}` }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 8 }}>
                      <div style={{ fontWeight: 600, fontSize: 13 }}>
                        {CAT_ICON[f.category] || '•'} <span style={{ color: '#8a93a5', fontSize: 11 }}>#{f.rule_id} {f.category}</span> {f.description}
                      </div>
                      <div style={{ fontWeight: 800, color: neg ? '#00e5a0' : '#ff6b6b', whiteSpace: 'nowrap' }}>{neg ? '' : '+'}{f.points}</div>
                    </div>
                    {f.detail && <div style={{ fontSize: 12, color: '#b8c0cc', marginTop: 4 }}>↳ {f.detail}</div>}
                    <div style={{ fontSize: 11, color: '#8a93a5', marginTop: 4 }}>{f.action} · {f.days}</div>
                  </div>
                );
              })}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ── Rule catalog ──────────────────────────────────────────────────────────────
function RulesView() {
  const [data, setData] = useState<any>(null);
  const [cat, setCat] = useState('');
  useEffect(() => { apiGet('/retention/rules').then(setData).catch(() => {}); }, []);
  if (!data) return <div style={{ color: '#8a93a5' }}>Loading catalog…</div>;

  const cats = Array.from(new Set(data.rules.map((r: any) => r.category))) as string[];
  const shown = cat ? data.rules.filter((r: any) => r.category === cat) : data.rules;

  return (
    <div>
      <div style={{ display: 'flex', gap: 10, marginBottom: 14, flexWrap: 'wrap', alignItems: 'center' }}>
        <span style={{ fontSize: 13, color: '#8a93a5' }}>{data.total} rules · <span style={{ color: '#00e5a0' }}>{data.automated} automated</span> · {data.total - data.automated} defined-only</span>
        <select value={cat} onChange={(e) => setCat(e.target.value)} style={{ ...inp, marginLeft: 'auto' }}>
          <option value="">All categories</option>
          {cats.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
      </div>

      <div style={{ ...card, overflow: 'hidden' }}>
        <div style={CT.scroll}>
          <table style={CT.table}>
            <thead>
              <tr style={CT.theadTr}>
                {['#', 'Category', 'Rule', 'Points', 'Level', 'Suggested action', 'Days', 'Status'].map((h) => (
                  <th key={h} style={CT.th()}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {shown.map((r: any) => {
                const m = bandMeta(r.trigger_level === 'Critical' ? 'Critical' : r.trigger_level === 'High' ? 'High' : r.trigger_level === 'Medium' ? 'Medium' : 'Low');
                return (
                  <tr key={r.rule_id} style={CT.row()}
                    onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--bg-card,#2c333e)')}
                    onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}>
                    <td style={{ ...CT.td, color: '#8a93a5' }}>{r.rule_id}</td>
                    <td style={CT.td}>{CAT_ICON[r.category] || '•'} {r.category}</td>
                    <td style={{ ...CT.td, whiteSpace: 'normal' }}>{r.description}</td>
                    <td style={{ ...CT.td, fontWeight: 700, color: r.risk_points < 0 ? '#00e5a0' : '#ff8888' }}>{r.risk_points > 0 ? '+' : ''}{r.risk_points}</td>
                    <td style={CT.td}>
                      <span style={{ background: m.bg, color: m.c, padding: '2px 7px', borderRadius: 5, fontSize: 11, fontWeight: 700 }}>{r.trigger_level}</span>
                    </td>
                    <td style={{ ...CT.td, whiteSpace: 'normal' }}>{r.suggested_action}</td>
                    <td style={{ ...CT.td, color: '#8a93a5' }}>{r.days_to_action}</td>
                    <td style={CT.td}>
                      {r.automatable
                        ? <span style={{ color: '#00e5a0', fontSize: 11, fontWeight: 700 }}>● AUTOMATED</span>
                        : <span style={{ color: '#8a93a5', fontSize: 11 }}>○ defined</span>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

const inp: React.CSSProperties = {
  background: 'var(--bg-card,#2c333e)', border: '1px solid var(--border,#4f596b)', color: 'var(--text,#e6e9ef)',
  borderRadius: 8, padding: '7px 11px', fontSize: 13, outline: 'none',
};
const btn: React.CSSProperties = {
  background: 'var(--bg-card,#2c333e)', border: '1px solid var(--border,#4f596b)', color: 'var(--text,#e6e9ef)',
  borderRadius: 8, padding: '6px 14px', fontSize: 13, cursor: 'pointer',
};

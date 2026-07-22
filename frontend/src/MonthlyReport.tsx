import React, { useState, useEffect, useCallback } from 'react';
import { apiGet, apiPost } from './api';
import { CT } from './crmTable';

// ── Monthly Report / Report Builder ─────────────────────────────────────────────
// Two modes:
//  • Overview tab — the auto-extended legacy Monthly Report (months + quarter + half-year).
//  • Per-category tabs (Validation / Leads / Clients / IB / Deposits / Withdrawals / Sales)
//    — pick a period, a group-by dimension and category-specific filters, Generate, then
//    Export the result to Excel. Schema (filters + group-by) comes from the backend.

const card: React.CSSProperties = {
  background: 'var(--bg-card,#2c333e)', border: '1px solid var(--border,#373f4d)', borderRadius: 12, padding: 16,
};
const input: React.CSSProperties = {
  background: 'var(--bg-card,#2c333e)', color: '#e6e9ef',
  border: '1px solid var(--border,#373f4d)', borderRadius: 8, padding: '7px 10px', fontSize: 13,
};
// Report tables use the shared canonical CRM table design (CT). These reports are
// numeric, so the default cell alignment here is right; the label/dimension column is left.
const th: React.CSSProperties = CT.th(false, 'right');
const thL: React.CSSProperties = CT.th(false, 'left');
const td: React.CSSProperties = { ...CT.td, textAlign: 'right' };
const tdL: React.CSSProperties = { ...CT.td, fontWeight: 600 };

const fmtMoney = (n: number) => (n < 0 ? '-$' : '$') + Math.abs(Math.round(n || 0)).toLocaleString('en-GB');
const fmtNum = (n: number) => (n || 0).toLocaleString('en-GB');
const fmtFloat = (n: number) => (n || 0).toLocaleString(undefined, { maximumFractionDigits: 1 });
const fmtCell = (type: string, v: any) => {
  if (v === null || v === undefined) return '';
  if (type === 'money') return fmtMoney(v);
  if (type === 'float') return fmtFloat(v);
  if (type === 'int') return fmtNum(v);
  return String(v);
};

const TABS: [string, string, string][] = [
  ['overview', '📅', 'Overview'],
  ['validation', '✅', 'Validation'],
  ['sales', '🧑‍💼', 'Sales'],
  ['clients', '👥', 'Clients'],
  ['leads', '🎯', 'Leads'],
  ['ib', '🤝', 'IB'],
  ['deposit', '⬇️', 'Deposits'],
  ['withdraw', '⬆️', 'Withdrawals'],
];

// ─────────────────────────── Overview charts (no external lib) ─────────────────
// Year trend: grouped Deposits/Withdrawals bars per month + Net line overlay.
function YearTrend({ months }: { months: any[] }) {
  const data = months || [];
  const W = 760, H = 240, PL = 58, PR = 16, PT = 14, PB = 30;
  const iw = W - PL - PR, ih = H - PT - PB;
  const maxBar = Math.max(1, ...data.map((m) => Math.max(m.deposits || 0, m.withdrawals || 0)));
  const nets = data.map((m) => m.net || 0);
  const nMax = Math.max(0, ...nets), nMin = Math.min(0, ...nets);
  const nSpan = (nMax - nMin) || 1;
  const n = Math.max(1, data.length);
  const gw = iw / n;
  const bw = Math.min(16, gw * 0.32);
  const yBar = (v: number) => PT + ih - (Math.max(0, v) / maxBar) * ih;
  const yNet = (v: number) => PT + ih - ((v - nMin) / nSpan) * ih;
  const netPts = data.map((m, i) => `${PL + gw * i + gw / 2},${yNet(m.net || 0)}`).join(' ');
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => Math.round(maxBar * f));
  return (
    <div style={{ overflowX: 'auto' }}>
      <svg width={W} height={H} style={{ maxWidth: '100%' }}>
        {ticks.map((t, i) => {
          const yy = PT + ih - (t / maxBar) * ih;
          return (
            <g key={i}>
              <line x1={PL} y1={yy} x2={W - PR} y2={yy} stroke="#373f4d" strokeWidth={1} />
              <text x={PL - 6} y={yy + 3} textAnchor="end" fontSize={9} fill="#8a93a3">{fmtMoney(t)}</text>
            </g>
          );
        })}
        {data.map((m, i) => {
          const cx = PL + gw * i + gw / 2;
          const dTop = yBar(m.deposits || 0), wTop = yBar(m.withdrawals || 0);
          return (
            <g key={i}>
              <rect x={cx - bw - 1} y={dTop} width={bw} height={PT + ih - dTop} fill="#37d67a" rx={2}>
                <title>{(m.label || '')}: Deposits {fmtMoney(m.deposits || 0)}</title>
              </rect>
              <rect x={cx + 1} y={wTop} width={bw} height={PT + ih - wTop} fill="#ff5c6c" rx={2}>
                <title>{(m.label || '')}: Withdrawals {fmtMoney(m.withdrawals || 0)}</title>
              </rect>
              <text x={cx} y={H - 10} textAnchor="middle" fontSize={9} fill="#8a93a3">{(m.label || '').slice(0, 3)}</text>
            </g>
          );
        })}
        <polyline points={netPts} fill="none" stroke="#5b9dff" strokeWidth={2} />
        {data.map((m, i) => {
          const cx = PL + gw * i + gw / 2;
          return (
            <circle key={i} cx={cx} cy={yNet(m.net || 0)} r={2.5} fill="#5b9dff">
              <title>{(m.label || '')}: Net {fmtMoney(m.net || 0)}</title>
            </circle>
          );
        })}
      </svg>
      <div style={{ display: 'flex', gap: 16, fontSize: 11, color: '#8a93a3', marginTop: 4 }}>
        <span><span style={{ color: '#37d67a' }}>■</span> Deposits</span>
        <span><span style={{ color: '#ff5c6c' }}>■</span> Withdrawals</span>
        <span><span style={{ color: '#5b9dff' }}>—</span> Net</span>
      </div>
    </div>
  );
}

// Per-month expansion: money bar chart + KPI tiles.
function MonthDetail({ row }: { row: any }) {
  const bars: [string, number, string][] = [
    ['Deposits', row.deposits || 0, '#37d67a'],
    ['Withdrawals', row.withdrawals || 0, '#ff5c6c'],
    ['Net', row.net || 0, (row.net || 0) < 0 ? '#ff5c6c' : '#5b9dff'],
    ['Markup', row.markup || 0, '#f5a623'],
  ];
  const maxB = Math.max(1, ...bars.map((b) => Math.abs(b[1])));
  const kpis: [string, string][] = [
    ['Reg. accounts', fmtNum(row.reg_accounts)], ['Verified', fmtNum(row.verified)],
    ['New depositors', fmtNum(row.nda)], ['Depositing clients', fmtNum(row.dep_clients)],
    ['Withdrawing clients', fmtNum(row.wd_clients)], ['Deposit count', fmtNum(row.dep_count)],
    ['Withdrawal count', fmtNum(row.wd_count)], ['Volume (lots)', fmtFloat(row.volume_lots)],
  ];
  return (
    <div style={{ background: 'rgba(91,157,255,0.05)', padding: 16, borderTop: '1px solid var(--border,#373f4d)' }}>
      <div style={{ fontWeight: 700, marginBottom: 10, fontSize: 13 }}>{row.label || row.month} — breakdown</div>
      <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
        <div style={{ minWidth: 300 }}>
          {bars.map(([lbl, val, col]) => (
            <div key={lbl} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              <span style={{ width: 90, fontSize: 11, color: '#8a93a3' }}>{lbl}</span>
              <div style={{ flex: 1, background: '#1c2027', borderRadius: 4, height: 16, minWidth: 120 }}>
                <div style={{ width: `${(Math.abs(val) / maxB) * 100}%`, background: col, height: '100%', borderRadius: 4 }} />
              </div>
              <span style={{ width: 90, textAlign: 'right', fontSize: 12, color: col }}>{fmtMoney(val)}</span>
            </div>
          ))}
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(120px, 1fr))', gap: 8, flex: 1, minWidth: 260 }}>
          {kpis.map(([lbl, val]) => (
            <div key={lbl} style={{ background: 'var(--bg-card,#2c333e)', border: '1px solid var(--border,#373f4d)', borderRadius: 8, padding: '8px 10px' }}>
              <div style={{ fontSize: 10, color: '#8a93a3' }}>{lbl}</div>
              <div style={{ fontSize: 16, fontWeight: 700 }}>{val}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────── Overview (auto monthly) ───────────────────────────
function OverviewTab() {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const [exporting, setExporting] = useState(false);
  const [expanded, setExpanded] = useState<number | null>(null);

  const MONEY = new Set(['deposits', 'withdrawals', 'net', 'markup']);
  const FLOAT = new Set(['volume_lots']);
  const fmt = (key: string, v: any) => {
    if (v === null || v === undefined) return '–';
    if (MONEY.has(key)) return fmtMoney(v);
    if (FLOAT.has(key)) return fmtFloat(v);
    return fmtNum(v);
  };

  const load = useCallback(() => {
    setLoading(true); setErr('');
    apiGet(`/monthly-report?year=${year}`).then((d) => { setData(d); setLoading(false); })
      .catch((e) => { setErr(String(e)); setLoading(false); });
  }, [year]);
  useEffect(() => { load(); }, [load]);

  const exportXlsx = async () => {
    setExporting(true);
    try {
      const token = localStorage.getItem('token') || '';
      const res = await fetch(`/api/monthly-report/export?year=${year}`, { headers: { Authorization: 'Bearer ' + token } });
      if (!res.ok) throw new Error('Export failed: ' + res.status);
      const blob = await res.blob(); const url = URL.createObjectURL(blob);
      const a = document.createElement('a'); a.href = url; a.download = `Monthly Report ${year} (with auto months).xlsx`; a.click();
      URL.revokeObjectURL(url);
    } catch (e) { alert(String(e)); }
    setExporting(false);
  };

  const columns = data?.columns || [];
  const Table = ({ rows, rollup, expandable }: { rows: any[]; rollup?: boolean; expandable?: boolean }) => (
    <div style={CT.scroll}>
      <table style={{ ...CT.table, minWidth: 900 }}>
        <thead><tr style={CT.theadTr}>{columns.map((c: any) => <th key={c.key} style={c.key === 'label' ? thL : th}>{c.label}</th>)}</tr></thead>
        <tbody>{rows.map((row, i) => (
          <React.Fragment key={i}>
            <tr
              onClick={expandable ? () => setExpanded(expanded === i ? null : i) : undefined}
              style={{
                ...CT.row(),
                cursor: expandable ? 'pointer' : 'default',
                background: row.partial ? 'rgba(255,210,80,0.10)' : (expandable && expanded === i ? 'rgba(91,157,255,0.12)' : (rollup ? 'rgba(91,157,255,0.08)' : 'transparent')),
              }}>
              {columns.map((c: any) => (
                <td key={c.key} style={c.key === 'label' ? tdL : td}>
                  {c.key === 'label'
                    ? <>{expandable && <span style={{ color: '#5b9dff', marginRight: 6, display: 'inline-block', transition: 'transform .15s', transform: expanded === i ? 'rotate(90deg)' : 'none' }}>▸</span>}{row.label || row.month}{row.partial && <span style={{ color: '#ffbf47', fontSize: 10, marginLeft: 6 }}>partial</span>}{row.months && <span style={{ color: '#8a93a3', fontWeight: 400, fontSize: 11, marginLeft: 6 }}>{row.months}</span>}</>
                    : <span style={{ color: c.key === 'net' ? (row[c.key] < 0 ? '#ff5c6c' : '#37d67a') : '#e6e9ef' }}>{fmt(c.key, row[c.key])}</span>}
                </td>
              ))}
            </tr>
            {expandable && expanded === i && (
              <tr><td colSpan={columns.length} style={{ padding: 0 }}><MonthDetail row={row} /></td></tr>
            )}
          </React.Fragment>
        ))}</tbody>
      </table>
    </div>
  );

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: 16 }}>
        <span style={{ color: '#8a93a3', fontSize: 12 }}>Auto-extended legacy report — months + quarter + half-year, computed live.</span>
        <div style={{ flex: 1 }} />
        <select value={year} onChange={(e) => setYear(Number(e.target.value))} style={input}>
          {[now.getFullYear(), now.getFullYear() - 1, now.getFullYear() - 2].map((y) => <option key={y} value={y}>{y}</option>)}
        </select>
        <button onClick={load} style={{ ...input, cursor: 'pointer' }}>↻ Refresh</button>
        <button onClick={exportXlsx} disabled={exporting} style={{ ...input, cursor: 'pointer', background: '#1f6feb', borderColor: '#1f6feb', color: '#fff', fontWeight: 600 }}>{exporting ? 'Exporting…' : '⬇ Export to Excel'}</button>
      </div>
      {err && <div style={{ ...card, color: '#ff5c6c', marginBottom: 16 }}>{err}</div>}
      {loading && <div style={{ color: '#8a93a3' }}>Loading…</div>}
      {data && !loading && (
        <>
          <div style={{ ...card, marginBottom: 18 }}>
            <div style={{ fontWeight: 700, marginBottom: 10 }}>Year trend — {year}</div>
            <YearTrend months={data.months} />
          </div>
          <div style={{ ...card, marginBottom: 18 }}>
            <div style={{ fontWeight: 700, marginBottom: 10 }}>Monthly — {year}</div>
            <Table rows={data.months} expandable />
            <div style={{ color: '#8a93a3', fontSize: 11, marginTop: 8 }}>Click any month to expand its charts. Partial (current) month highlighted. Generated {data.generated_at}.</div>
          </div>
          <div style={{ ...card, marginBottom: 18 }}>
            <div style={{ fontWeight: 700, marginBottom: 10 }}>Quarterly rollups</div>
            <Table rows={data.quarters} rollup />
          </div>
          <div style={card}>
            <div style={{ fontWeight: 700, marginBottom: 10 }}>Half-year rollups</div>
            <Table rows={data.halves} rollup />
          </div>
        </>
      )}
    </div>
  );
}

// ─────────────────────────── Category builder tab ──────────────────────────────
function BuilderTab({ category, schema }: { category: string; schema: any }) {
  const cfg = schema[category];
  // group_by is multi-select (array of dimensions); filters are arrays (empty = "All")
  const [groupBy, setGroupBy] = useState<string[]>([cfg.group_by[0][0]]);
  const [period, setPeriod] = useState<string>('this_year');
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [filters, setFilters] = useState<Record<string, string[]>>(
    Object.fromEntries((cfg.filters || []).map((f: any) => [f.key, []]))
  );
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState('');
  const [exporting, setExporting] = useState(false);

  // reset controls when switching category
  useEffect(() => {
    setGroupBy([cfg.group_by[0][0]]);
    setFilters(Object.fromEntries((cfg.filters || []).map((f: any) => [f.key, []])));
    setResult(null); setErr('');
  }, [category]); // eslint-disable-line react-hooks/exhaustive-deps

  // group_by must keep at least one dimension
  const ensureGroup = (arr: string[]) => (arr.length ? arr : [cfg.group_by[0][0]]);

  const reqBody = () => ({ category, group_by: groupBy, period, start: period === 'custom' ? start : undefined, end: period === 'custom' ? end : undefined, filters });

  const generate = () => {
    setLoading(true); setErr(''); setResult(null);
    apiPost('/monthly-report/run', reqBody()).then((d) => { setResult(d); setLoading(false); })
      .catch((e) => { setErr(String(e)); setLoading(false); });
  };

  const exportXlsx = async () => {
    setExporting(true);
    try {
      const token = localStorage.getItem('token') || '';
      const res = await fetch('/api/monthly-report/run/export', {
        method: 'POST', headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' }, body: JSON.stringify(reqBody()),
      });
      if (!res.ok) throw new Error('Export failed: ' + res.status);
      const blob = await res.blob(); const url = URL.createObjectURL(blob);
      const a = document.createElement('a'); a.href = url; a.download = `${category}_report.xlsx`; a.click();
      URL.revokeObjectURL(url);
    } catch (e) { alert(String(e)); }
    setExporting(false);
  };

  const cols = result?.columns || [];
  const nd = result?.n_dims || 1;

  return (
    <div>
      {/* Filter bar */}
      <div style={{ ...card, marginBottom: 16 }}>
        <div style={{ fontWeight: 700, marginBottom: 4 }}>{cfg.title}</div>
        <div style={{ color: '#8a93a3', fontSize: 11, marginBottom: 12 }}>Filtered {cfg.date_label}. Choose options, then Generate.</div>
        <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <Field label="Period">
            <select value={period} onChange={(e) => setPeriod(e.target.value)} style={input}>
              {cfg.periods.map((o: any) => <option key={o[0]} value={o[0]}>{o[1]}</option>)}
            </select>
          </Field>
          {period === 'custom' && (
            <>
              <Field label="From"><input type="date" max={new Date(Date.now()+86400000).toISOString().slice(0,10)} value={start} onChange={(e) => setStart(e.target.value)} style={input} /></Field>
              <Field label="To"><input type="date" max={new Date(Date.now()+86400000).toISOString().slice(0,10)} value={end} onChange={(e) => setEnd(e.target.value)} style={input} /></Field>
            </>
          )}
          {cfg.group_by.length > 1 && (
            <Field label="Group by">
              <MultiSelect opts={cfg.group_by} value={groupBy} placeholder="Pick…"
                onChange={(v) => setGroupBy(ensureGroup(v))} />
            </Field>
          )}
          {(cfg.filters || []).map((f: any) => (
            <Field key={f.key} label={f.label}>
              <MultiSelect opts={f.opts.filter((o: any) => o[0] !== 'all')} value={filters[f.key] || []}
                placeholder="All" onChange={(v) => setFilters({ ...filters, [f.key]: v })} />
            </Field>
          ))}
          <button onClick={generate} disabled={loading} style={{ ...input, cursor: 'pointer', background: '#1f6feb', borderColor: '#1f6feb', color: '#fff', fontWeight: 600, padding: '8px 18px' }}>
            {loading ? 'Generating…' : '▶ Generate report'}
          </button>
          {result && (
            <button onClick={exportXlsx} disabled={exporting} style={{ ...input, cursor: 'pointer', background: '#1f8a4c', borderColor: '#1f8a4c', color: '#fff', fontWeight: 600 }}>
              {exporting ? 'Exporting…' : '⬇ Export to Excel'}
            </button>
          )}
        </div>
      </div>

      {err && <div style={{ ...card, color: '#ff5c6c', marginBottom: 16 }}>{err}</div>}

      {result && (
        <div style={card}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 10 }}>
            <div style={{ fontWeight: 700 }}>{result.title}</div>
            <div style={{ color: '#8a93a3', fontSize: 12 }}>{result.rows.length} row(s){result.period?.start ? ` · ${result.period.start} → ${result.period.end}` : ' · all time'}</div>
          </div>
          {result.rows.length === 0 ? <div style={{ color: '#8a93a3' }}>No data for these filters.</div> : (
            <div style={{ ...CT.scroll, maxHeight: '62vh' }}>
              <table style={{ ...CT.table, minWidth: 700 }}>
                <thead><tr style={CT.theadTr}>{cols.map((c: any, i: number) => <th key={c.key} style={i < nd ? thL : th}>{c.label}</th>)}</tr></thead>
                <tbody>
                  {result.rows.map((row: any[], ri: number) => (
                    <tr key={ri} style={CT.row()}
                      onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--bg-card,#2c333e)')}
                      onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}>
                      {cols.map((c: any, ci: number) => (
                        <td key={c.key} style={ci < nd ? tdL : td}>{fmtCell(c.type, row[ci])}</td>
                      ))}
                    </tr>
                  ))}
                  {result.total_row && (
                    <tr style={{ ...CT.row(), background: 'rgba(91,157,255,0.10)', fontWeight: 700 }}>
                      {cols.map((c: any, ci: number) => (
                        <td key={c.key} style={{ ...(ci < nd ? tdL : td), fontWeight: 700, borderTop: '2px solid var(--border,#373f4d)' }}>{fmtCell(c.type, result.total_row[ci])}</td>
                      ))}
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
      {!result && !loading && <div style={{ color: '#8a93a3', padding: 12 }}>Pick your filters above and click <b>Generate report</b>.</div>}
    </div>
  );
}

// Multi-select dropdown: a button showing the selection + a checkbox popover.
function MultiSelect({ opts, value, onChange, placeholder }: { opts: any[]; value: string[]; onChange: (v: string[]) => void; placeholder?: string }) {
  const [open, setOpen] = useState(false);
  const toggle = (key: string) => {
    onChange(value.includes(key) ? value.filter((v) => v !== key) : [...value, key]);
  };
  const labelFor = (key: string) => (opts.find((o) => o[0] === key)?.[1]) || key;
  const summary = value.length === 0 ? (placeholder || 'All')
    : value.length <= 2 ? value.map(labelFor).join(', ')
    : `${value.length} selected`;
  return (
    <div style={{ position: 'relative' }}>
      <button type="button" onClick={() => setOpen((o) => !o)}
        style={{ ...input, cursor: 'pointer', minWidth: 150, textAlign: 'left', display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center' }}>
        <span style={{ color: value.length ? '#e6e9ef' : '#8a93a3', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{summary}</span>
        <span style={{ color: '#8a93a3', fontSize: 10 }}>▼</span>
      </button>
      {open && (
        <>
          <div onClick={() => setOpen(false)} style={{ position: 'fixed', inset: 0, zIndex: 40 }} />
          <div style={{ position: 'absolute', top: '100%', left: 0, marginTop: 4, zIndex: 41, background: 'var(--bg-card,#2c333e)', border: '1px solid var(--border,#373f4d)', borderRadius: 8, boxShadow: '0 8px 24px rgba(0,0,0,0.35)', minWidth: 190, maxHeight: 280, overflowY: 'auto', padding: 4 }}>
            {value.length > 0 && (
              <div onClick={() => onChange([])} style={{ padding: '6px 10px', fontSize: 12, color: '#8a93a3', cursor: 'pointer', borderBottom: '1px solid var(--border,#373f4d)' }}>✕ Clear ({placeholder || 'All'})</div>
            )}
            {opts.map((o) => (
              <label key={o[0]} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 10px', fontSize: 13, cursor: 'pointer', borderRadius: 6, background: value.includes(o[0]) ? 'rgba(31,111,235,0.15)' : 'transparent' }}>
                <input type="checkbox" checked={value.includes(o[0])} onChange={() => toggle(o[0])} />
                <span>{o[1]}</span>
              </label>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <span style={{ fontSize: 10, color: '#8a93a3', textTransform: 'uppercase', letterSpacing: 0.4 }}>{label}</span>
      {children}
    </div>
  );
}

// Reusable result table (columns + rows + TOTAL), used by the Ask box.
function ResultTable({ result }: { result: any }) {
  const cols = result?.columns || [];
  const nd = result?.n_dims || 1;
  if (!result) return null;
  if (!result.rows?.length) return <div style={{ color: '#8a93a3' }}>No data for that request.</div>;
  return (
    <div style={{ ...CT.scroll, maxHeight: '60vh' }}>
      <table style={{ ...CT.table, minWidth: 600 }}>
        <thead><tr style={CT.theadTr}>{cols.map((c: any, i: number) => <th key={c.key} style={i < nd ? thL : th}>{c.label}</th>)}</tr></thead>
        <tbody>
          {result.rows.map((row: any[], ri: number) => (
            <tr key={ri} style={CT.row()}
              onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--bg-card,#2c333e)')}
              onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}>
              {cols.map((c: any, ci: number) => <td key={c.key} style={ci < nd ? tdL : td}>{fmtCell(c.type, row[ci])}</td>)}
            </tr>
          ))}
          {result.total_row && (
            <tr style={{ ...CT.row(), background: 'rgba(91,157,255,0.10)', fontWeight: 700 }}>
              {cols.map((c: any, ci: number) => <td key={c.key} style={{ ...(ci < nd ? tdL : td), fontWeight: 700, borderTop: '2px solid var(--border,#373f4d)' }}>{fmtCell(c.type, result.total_row[ci])}</td>)}
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

// Conversation box: type a request in plain words → AI builds the table.
// (The full back-and-forth AI chat lives in the Ticketing center — AIChat.tsx.)
function AskBox() {
  const [q, setQ] = useState('');
  const [resp, setResp] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState('');
  const ask = () => {
    if (!q.trim()) return;
    setLoading(true); setErr(''); setResp(null);
    apiPost('/monthly-report/ask', { question: q })
      .then((d) => { if (d.error) setErr(d.error); setResp(d); setLoading(false); })
      .catch((e) => { setErr(String(e)); setLoading(false); });
  };
  const exportXlsx = async () => {
    const s = resp?.spec; if (!s) return;
    const token = localStorage.getItem('token') || '';
    const res = await fetch('/api/monthly-report/run/export', {
      method: 'POST', headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' },
      body: JSON.stringify({ category: s.category, group_by: s.group_by, period: s.period, start: s.start, end: s.end, filters: s.filters }),
    });
    if (res.ok) { const b = await res.blob(); const u = URL.createObjectURL(b); const a = document.createElement('a'); a.href = u; a.download = (s.category || 'report') + '_report.xlsx'; a.click(); URL.revokeObjectURL(u); }
  };
  const examples = ['total deposits by country this year', 'leads by source this month', 'top sales agents by deposits last month', 'withdrawals by method this year', 'IB by level'];
  return (
    <div style={{ ...card, marginBottom: 18, border: '1px solid #1f6feb66' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 16 }}>🗨</span><b>Ask for a report</b>
        <span style={{ color: '#8a93a3', fontSize: 12 }}>one question → one table · for full AI chat use the Tickets page 🤖</span>
      </div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <input value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') ask(); }}
          placeholder="e.g. total deposits by country this year" style={{ ...input, flex: 1, minWidth: 280 }} />
        <button onClick={ask} disabled={loading} style={{ ...input, cursor: 'pointer', background: '#1f6feb', borderColor: '#1f6feb', color: '#fff', fontWeight: 600, padding: '8px 20px' }}>{loading ? 'Thinking…' : 'Ask'}</button>
      </div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 8 }}>
        {examples.map((s) => <button key={s} onClick={() => setQ(s)} style={{ ...input, cursor: 'pointer', fontSize: 11, padding: '4px 8px', color: '#8a93a3' }}>{s}</button>)}
      </div>
      {err && <div style={{ color: '#ff5c6c', marginTop: 10 }}>{err}</div>}
      {resp && resp.result && (
        <div style={{ marginTop: 14 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 8, flexWrap: 'wrap' }}>
            <b>{resp.title}</b>
            <span style={{ color: '#8a93a3', fontSize: 12 }}>{resp.explanation} · {resp.result.rows.length} row(s)</span>
            <div style={{ flex: 1 }} />
            <button onClick={exportXlsx} style={{ ...input, cursor: 'pointer', background: '#1f8a4c', borderColor: '#1f8a4c', color: '#fff', fontWeight: 600, fontSize: 12 }}>⬇ Excel</button>
          </div>
          <ResultTable result={resp.result} />
        </div>
      )}
    </div>
  );
}
// ───────────────────────────────── Page ────────────────────────────────────────
export default function MonthlyReport() {
  const [tab, setTab] = useState('overview');
  const [schema, setSchema] = useState<any>(null);
  useEffect(() => { apiGet('/monthly-report/schema').then(setSchema).catch(() => {}); }, []);

  return (
    <div style={{ padding: 20, height: '100%', overflow: 'auto', color: '#e6e9ef' }}>
      <h2 style={{ margin: '0 0 4px', fontSize: 20 }}>📊 Reports</h2>
      <div style={{ color: '#8a93a3', fontSize: 12, marginBottom: 14 }}>Build & export reports per section — computed live from the CRM database.</div>

      {/* AI analyst chat — questions, attachments, reports on demand */}
      <AskBox />

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 18, borderBottom: '1px solid var(--border,#373f4d)', paddingBottom: 10 }}>
        {TABS.map(([key, icon, label]) => (
          <button key={key} onClick={() => setTab(key)}
            style={{
              ...input, cursor: 'pointer', padding: '8px 14px',
              background: tab === key ? '#1f6feb' : 'var(--bg-card,#2c333e)',
              borderColor: tab === key ? '#1f6feb' : 'var(--border,#373f4d)',
              color: tab === key ? '#fff' : '#c7cdd6', fontWeight: tab === key ? 700 : 500,
            }}>
            {icon} {label}
          </button>
        ))}
      </div>

      {tab === 'overview' ? <OverviewTab /> : (
        schema ? <BuilderTab key={tab} category={tab} schema={schema} /> : <div style={{ color: '#8a93a3' }}>Loading…</div>
      )}
    </div>
  );
}

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { apiGet, apiPost, apiPatch, apiDelete, apiDownload } from './api';

// ── Finance Management (ticket #35) ───────────────────────────────────────────
// Finance overview built on REAL data: liquidity KPIs, money-movement ledger,
// per-payment-method balances, and an expenses/invoices register (finance_expenses).

const PERIODS: [string, string][] = [
  ['today', 'Today'],
  ['this_week', 'This week'],
  ['this_month', 'This month'],
  ['last_month', 'Last month'],
  ['this_year', 'This year'],
  ['last_year', 'Last year'],
  ['all_time', 'All time'],
];

const LEDGER_TYPES: [string, string][] = [
  ['', 'All types'],
  ['deposit', 'Deposits'],
  ['withdrawal', 'Withdrawals'],
  ['internal_transfer', 'Internal transfers'],
  ['bonus_deposit', 'Bonus in'],
  ['bonus_withdrawal', 'Bonus out'],
];

const fmtUSD = (n: number) => (n < 0 ? '-$' : '$') + Math.abs(Math.round(n || 0)).toLocaleString();
const fmtNum = (n: number) => (n || 0).toLocaleString();
// compact money for chart axes/labels ($1.2M / $340K)
const fmtCompact = (n: number) => {
  const a = Math.abs(n || 0), s = n < 0 ? '-' : '';
  if (a >= 1e6) return `${s}$${(a / 1e6).toFixed(a >= 1e7 ? 0 : 1)}M`;
  if (a >= 1e3) return `${s}$${(a / 1e3).toFixed(a >= 1e4 ? 0 : 1)}K`;
  return `${s}$${Math.round(a)}`;
};
const monthLabel = (ym: string) => {
  const [y, m] = (ym || '').split('-');
  const names = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return `${names[parseInt(m, 10)] || m} ${(y || '').slice(2)}`;
};

// Shared semantic colours (match the rest of the app).
const C_IN = '#37d67a';       // money in / revenue
const C_OUT = '#ff5c6c';      // money out / cost
const C_PROFIT = '#5b9dff';   // profit / net
const C_EXP = '#ffb454';      // expenses

function ExportBtn({ onClick, label = 'Export CSV' }: { onClick: () => void; label?: string }) {
  const [busy, setBusy] = useState(false);
  return (
    <button
      onClick={async () => { setBusy(true); try { await onClick(); } catch { alert('Export failed'); } finally { setBusy(false); } }}
      disabled={busy}
      style={{ background: 'var(--bg-card2,#262c36)', color: '#cdd3dd', border: '1px solid var(--border,#373f4d)', borderRadius: 8, padding: '7px 12px', fontSize: 12, fontWeight: 600, cursor: busy ? 'wait' : 'pointer' }}
    >{busy ? 'Exporting…' : `⬇ ${label}`}</button>
  );
}

const card: React.CSSProperties = {
  background: 'var(--bg-card,#2c333e)',
  border: '1px solid var(--border,#373f4d)',
  borderRadius: 12,
  padding: 16,
};
const input: React.CSSProperties = {
  background: 'var(--bg-card,#2c333e)', color: '#e6e9ef',
  border: '1px solid var(--border,#373f4d)', borderRadius: 8, padding: '7px 10px', fontSize: 13,
};
const th: React.CSSProperties = { padding: '8px 8px', fontWeight: 600, textAlign: 'left', color: '#8a93a3', whiteSpace: 'nowrap' };
const td: React.CSSProperties = { padding: '7px 8px', borderTop: '1px solid var(--border,#373f4d)' };

function KpiCard({ label, value, color, sub }: { label: string; value: string; color?: string; sub?: string }) {
  return (
    <div style={card}>
      <div style={{ fontSize: 10, color: '#8a93a3', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 6 }}>{label}</div>
      <div style={{ fontSize: 24, fontWeight: 700, color: color || '#e6e9ef' }}>{value}</div>
      {sub && <div style={{ fontSize: 11, color: '#8a93a3', marginTop: 4 }}>{sub}</div>}
    </div>
  );
}

const TYPE_COLOR: Record<string, string> = {
  deposit: '#37d67a', bonus_deposit: '#37d67a',
  withdrawal: '#ff5c6c', bonus_withdrawal: '#ff8a93',
  internal_transfer: '#5b9dff',
};
const TYPE_LABEL: Record<string, string> = {
  deposit: 'Deposit', withdrawal: 'Withdrawal', internal_transfer: 'Transfer',
  bonus_deposit: 'Bonus in', bonus_withdrawal: 'Bonus out',
};

type FinTab = 'overview' | 'pnl' | 'trends' | 'ledger' | 'expenses' | 'reconciliation';
const TABS: [FinTab, string][] = [
  ['overview', 'Overview'],
  ['pnl', 'P&L'],
  ['trends', 'Trends'],
  ['ledger', 'Ledger'],
  ['expenses', 'Expenses'],
  ['reconciliation', 'Reconciliation'],
];

export default function Finance() {
  const [tab, setTab] = useState<FinTab>('overview');

  return (
    <div style={{ padding: 16, color: '#e6e9ef', height: '100%', overflow: 'auto' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700, marginRight: 8 }}>💰 Finance Management</h2>
        <div style={{ flex: 1 }} />
        {TABS.map(([t, label]) => (
          <button key={t} onClick={() => setTab(t)} style={{
            background: tab === t ? '#2d6cdf' : 'var(--bg-card,#2c333e)',
            color: tab === t ? '#fff' : '#cdd3dd',
            border: '1px solid var(--border,#373f4d)', borderRadius: 8,
            padding: '8px 14px', fontSize: 13, fontWeight: 600, cursor: 'pointer',
          }}>{label}</button>
        ))}
      </div>

      {tab === 'overview' && <Overview />}
      {tab === 'pnl' && <PnL />}
      {tab === 'trends' && <Trends />}
      {tab === 'ledger' && <Ledger />}
      {tab === 'expenses' && <Expenses />}
      {tab === 'reconciliation' && <Reconciliation />}
    </div>
  );
}

// ── Overview tab ──────────────────────────────────────────────────────────────
function Overview() {
  const [period, setPeriod] = useState('this_month');
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    apiGet(`/finance/overview?period=${period}`)
      .then((d: any) => setData(d)).catch(() => setData(null)).finally(() => setLoading(false));
  }, [period]);
  useEffect(() => { load(); }, [load]);

  const k = data?.kpis || {};

  return (
    <>
      <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 16, flexWrap: 'wrap' }}>
        <select value={period} onChange={e => setPeriod(e.target.value)} style={input}>
          {PERIODS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
        {data?.period && (
          <span style={{ fontSize: 12, color: '#8a93a3' }}>{data.period.from} → {data.period.to} · liquidity figures are all-time</span>
        )}
      </div>

      {loading && <div style={{ color: '#8a93a3', padding: 20 }}>Loading…</div>}
      {!loading && data && (
        <>
          {/* Liquidity row */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 12, marginBottom: 14 }}>
            <KpiCard label="Total liquidity" value={fmtUSD(k.total_liquidity)} color="#5b9dff" sub="net client funds held (all-time)" />
            <KpiCard label="Available liquidity" value={fmtUSD(k.available_liquidity)} color="#37d67a" sub={`minus ${fmtUSD(k.pending_withdrawals)} pending withdrawals`} />
            <KpiCard label="Pending withdrawals" value={fmtUSD(k.pending_withdrawals)} color="#ff8a93" sub={`${fmtNum(k.pending_withdrawal_count)} requests`} />
            <KpiCard label="Client balances" value={fmtUSD(k.client_balance_total)} sub={`${fmtNum(k.account_count)} accounts · ${fmtUSD(k.client_credit_total)} credit`} />
          </div>

          {/* Period flow row */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 12, marginBottom: 22 }}>
            <KpiCard label="Deposits (period)" value={fmtUSD(k.deposits)} color="#37d67a" sub={`${fmtNum(k.deposit_count)} txns`} />
            <KpiCard label="Withdrawals (period)" value={fmtUSD(k.withdrawals)} color="#ff5c6c" sub={`${fmtNum(k.withdrawal_count)} txns`} />
            <KpiCard label="Net deposit (period)" value={fmtUSD(k.net)} color={k.net >= 0 ? '#37d67a' : '#ff5c6c'} />
            <KpiCard label="Expenses (period)" value={fmtUSD(k.expenses_period)} color="#ffb454" sub={`${fmtNum(k.expense_count)} invoices`} />
            <KpiCard label="Net after expenses" value={fmtUSD(k.net_after_expenses)} color={k.net_after_expenses >= 0 ? '#37d67a' : '#ff5c6c'} />
          </div>

          {/* Payment-method balances — month by month, ranked high → low */}
          <MethodTrends />

          {/* How calculated */}
          <div style={{ ...card, background: 'var(--bg-card2,#262c36)', marginTop: 16 }}>
            <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 10 }}>ℹ️ How these are calculated</div>
            <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12, lineHeight: 1.7, color: '#c4ccd8' }}>
              <li><b>Total liquidity</b> = all-time genuine deposits − all-time withdrawals = net client funds the platform is holding. Internal MT5 balance adjustments are excluded (not real cash in).</li>
              <li><b>Available liquidity</b> = total liquidity − pending (not-yet-performed) withdrawals — funds not already earmarked to leave.</li>
              <li><b>Payment-method balances</b> = per PSP/method, the net cash in (genuine deposits − withdrawals paid back out) each month, ranked highest to lowest by total over the window.</li>
              <li><b>Client balances</b> = live sum of trading-account balance (and credit) — what is currently sitting in client accounts.</li>
            </ul>
          </div>
        </>
      )}
    </>
  );
}

// ── Payment-method net cash, month by month, ranked high → low ─────────────────
function MethodTrends() {
  const [months, setMonths] = useState(12);
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    apiGet(`/finance/method-trends?months=${months}`)
      .then((d: any) => setData(d)).catch(() => setData(null)).finally(() => setLoading(false));
  }, [months]);
  useEffect(() => { load(); }, [load]);

  const mkeys: string[] = data?.months || [];
  const methods: any[] = data?.methods || [];
  const colTotals = data?.column_totals || {};
  const netColor = (v: number) => (v > 0 ? '#37d67a' : v < 0 ? '#ff5c6c' : '#5b6472');
  const cell: React.CSSProperties = { ...td, textAlign: 'right', whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums' };
  const stickyL: React.CSSProperties = { position: 'sticky', left: 0, background: 'var(--bg-card,#2c333e)', zIndex: 1 };

  return (
    <div style={{ ...card, padding: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 14px 8px', flexWrap: 'wrap' }}>
        <div style={{ fontSize: 13, fontWeight: 700 }}>Payment-method balances — net cash in, month by month</div>
        <span style={{ fontSize: 11, color: '#8a93a3' }}>ranked highest → lowest by total</span>
        <div style={{ flex: 1 }} />
        <select value={months} onChange={e => setMonths(parseInt(e.target.value, 10))} style={{ ...input, padding: '5px 8px', fontSize: 12 }}>
          {MONTH_OPTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
      </div>

      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12, minWidth: 640 }}>
          <thead>
            <tr style={{ background: 'var(--bg-card2,#262c36)' }}>
              <th style={{ ...th, ...stickyL, background: 'var(--bg-card2,#262c36)' }}>#</th>
              <th style={{ ...th, position: 'sticky', left: 34, background: 'var(--bg-card2,#262c36)', zIndex: 1 }}>Method / PSP</th>
              {mkeys.map(mk => <th key={mk} style={{ ...th, textAlign: 'right' }}>{monthLabel(mk)}</th>)}
              <th style={{ ...th, textAlign: 'right', borderLeft: '1px solid var(--border,#373f4d)' }}>Total</th>
            </tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={mkeys.length + 3} style={{ ...td, color: '#8a93a3' }}>Loading…</td></tr>}
            {!loading && methods.length === 0 && <tr><td colSpan={mkeys.length + 3} style={{ ...td, color: '#8a93a3' }}>No data</td></tr>}
            {!loading && methods.map((m, i) => (
              <tr key={m.method}>
                <td style={{ ...td, ...stickyL, color: '#8a93a3', textAlign: 'right', paddingRight: 10 }}>{i + 1}</td>
                <td style={{ ...td, position: 'sticky', left: 34, background: 'var(--bg-card,#2c333e)', zIndex: 1, maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={`${m.method_label} · ${fmtNum(m.count)} txns`}>{m.method_label}</td>
                {mkeys.map(mk => {
                  const v = m.monthly?.[mk] || 0;
                  return <td key={mk} style={{ ...cell, color: v === 0 ? '#5b6472' : netColor(v) }}>{v === 0 ? '·' : fmtCompact(v)}</td>;
                })}
                <td style={{ ...cell, fontWeight: 700, borderLeft: '1px solid var(--border,#373f4d)', color: netColor(m.total) }}>{fmtUSD(m.total)}</td>
              </tr>
            ))}
          </tbody>
          {!loading && methods.length > 0 && (
            <tfoot>
              <tr style={{ background: 'var(--bg-card2,#262c36)' }}>
                <td style={{ ...td, ...stickyL, background: 'var(--bg-card2,#262c36)' }} />
                <td style={{ ...th, position: 'sticky', left: 34, background: 'var(--bg-card2,#262c36)', zIndex: 1, fontWeight: 700 }}>All methods</td>
                {mkeys.map(mk => {
                  const v = colTotals[mk] || 0;
                  return <td key={mk} style={{ ...cell, fontWeight: 700, color: netColor(v) }}>{v === 0 ? '·' : fmtCompact(v)}</td>;
                })}
                <td style={{ ...cell, fontWeight: 700, borderLeft: '1px solid var(--border,#373f4d)', color: netColor(data?.grand_total || 0) }}>{fmtUSD(data?.grand_total || 0)}</td>
              </tr>
            </tfoot>
          )}
        </table>
      </div>
    </div>
  );
}

// ── Ledger tab ────────────────────────────────────────────────────────────────
function Ledger() {
  const [type, setType] = useState('');
  const [method, setMethod] = useState('');
  const [search, setSearch] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [page, setPage] = useState(1);
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const pageSize = 50;

  const load = useCallback(() => {
    setLoading(true);
    const qs = new URLSearchParams({
      page: String(page), page_size: String(pageSize),
      tx_type: type, method, search, date_from: dateFrom, date_to: dateTo,
    });
    apiGet(`/finance/ledger?${qs.toString()}`)
      .then((d: any) => setData(d)).catch(() => setData(null)).finally(() => setLoading(false));
  }, [page, type, method, search, dateFrom, dateTo]);
  useEffect(() => { load(); }, [load]);

  const totalPages = data ? Math.max(1, Math.ceil(data.total / pageSize)) : 1;

  return (
    <>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', marginBottom: 12 }}>
        <select value={type} onChange={e => { setType(e.target.value); setPage(1); }} style={input}>
          {LEDGER_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
        <input placeholder="Method / PSP" value={method} onChange={e => { setMethod(e.target.value); setPage(1); }} style={{ ...input, width: 130 }} />
        <input placeholder="Search login / name / ref" value={search} onChange={e => { setSearch(e.target.value); setPage(1); }} style={{ ...input, width: 200 }} />
        <label style={{ fontSize: 11, color: '#8a93a3' }}>From <input type="date" value={dateFrom} onChange={e => { setDateFrom(e.target.value); setPage(1); }} style={{ ...input, padding: '5px 8px' }} /></label>
        <label style={{ fontSize: 11, color: '#8a93a3' }}>To <input type="date" value={dateTo} onChange={e => { setDateTo(e.target.value); setPage(1); }} style={{ ...input, padding: '5px 8px' }} /></label>
        <div style={{ flex: 1 }} />
        <ExportBtn onClick={() => apiDownload(`/finance/ledger.csv?${new URLSearchParams({ tx_type: type, method, search, date_from: dateFrom, date_to: dateTo }).toString()}`, 'finance_ledger.csv')} />
      </div>

      {data && (
        <div style={{ display: 'flex', gap: 20, marginBottom: 10, fontSize: 12, color: '#8a93a3' }}>
          <span>{fmtNum(data.total)} movements</span>
          <span style={{ color: '#37d67a' }}>Deposits {fmtUSD(data.totals?.deposits || 0)}</span>
          <span style={{ color: '#ff5c6c' }}>Withdrawals {fmtUSD(data.totals?.withdrawals || 0)}</span>
        </div>
      )}

      <div style={{ ...card, padding: 0, overflow: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
          <thead>
            <tr style={{ background: 'var(--bg-card2,#262c36)' }}>
              <th style={th}>Date</th>
              <th style={th}>Login</th>
              <th style={th}>Client</th>
              <th style={th}>Type</th>
              <th style={{ ...th, textAlign: 'right' }}>Amount</th>
              <th style={th}>Method</th>
              <th style={th}>Status</th>
              <th style={th}>Reference</th>
            </tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={8} style={{ ...td, color: '#8a93a3' }}>Loading…</td></tr>}
            {!loading && (data?.items || []).length === 0 && <tr><td colSpan={8} style={{ ...td, color: '#8a93a3' }}>No movements</td></tr>}
            {!loading && (data?.items || []).map((r: any) => (
              <tr key={r.id}>
                <td style={td}>{(r.tx_date || '').slice(0, 16)}</td>
                <td style={td}>{r.login}</td>
                <td style={{ ...td, maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.client_name}</td>
                <td style={td}><span style={{ color: TYPE_COLOR[r.tx_type] || '#cdd3dd' }}>{TYPE_LABEL[r.tx_type] || r.tx_type}</span></td>
                <td style={{ ...td, textAlign: 'right', fontWeight: 600, color: TYPE_COLOR[r.tx_type] || '#e6e9ef' }}>{fmtUSD(r.amount)}</td>
                <td style={td}>{r.method || '—'}</td>
                <td style={td}>{r.status}</td>
                <td style={{ ...td, color: '#8a93a3' }}>{r.psp_reference || r.ref_id || ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginTop: 12 }}>
        <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page <= 1} style={{ ...input, cursor: page <= 1 ? 'not-allowed' : 'pointer' }}>← Prev</button>
        <span style={{ fontSize: 12, color: '#8a93a3' }}>Page {page} / {totalPages}</span>
        <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page >= totalPages} style={{ ...input, cursor: page >= totalPages ? 'not-allowed' : 'pointer' }}>Next →</button>
      </div>
    </>
  );
}

// ── Expenses / invoices tab ───────────────────────────────────────────────────
const blankForm = { exp_date: new Date().toISOString().slice(0, 10), payee: '', category: 'Other', amount: '', currency: 'USD', status: 'issued', note: '', invoice_no: '' };

function Expenses() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<any>(blankForm);
  const [fStatus, setFStatus] = useState('');
  const [fCategory, setFCategory] = useState('');
  const [search, setSearch] = useState('');
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    const qs = new URLSearchParams({ status: fStatus, category: fCategory, search });
    apiGet(`/finance/expenses?${qs.toString()}`)
      .then((d: any) => setData(d)).catch(() => setData(null)).finally(() => setLoading(false));
  }, [fStatus, fCategory, search]);
  useEffect(() => { load(); }, [load]);

  const submit = async () => {
    if (!form.payee.trim()) { alert('Payee is required'); return; }
    setSaving(true);
    try {
      await apiPost('/finance/expenses', { ...form, amount: parseFloat(form.amount) || 0 });
      setShowForm(false); setForm(blankForm); load();
    } catch { alert('Failed to add expense'); }
    finally { setSaving(false); }
  };

  const setStatus = async (id: number, status: string) => {
    try { await apiPatch(`/finance/expenses/${id}`, { status }); load(); } catch { alert('Update failed'); }
  };
  const remove = async (id: number) => {
    if (!window.confirm('Delete this expense?')) return;
    try { await apiDelete(`/finance/expenses/${id}`); load(); } catch { alert('Delete failed'); }
  };

  const cats = data?.categories || ['Other'];
  const statuses = data?.statuses || ['issued'];
  const STATUS_COLOR: Record<string, string> = { paid: '#37d67a', approved: '#5b9dff', issued: '#ffb454', draft: '#8a93a3', void: '#ff5c6c' };

  // Expenditure breakdown by category (from the loaded, filtered rows; excludes void).
  const catBreakdown = useMemo(() => {
    const m = new Map<string, { category: string; amount: number; count: number }>();
    for (const r of (data?.items || [])) {
      if (r.status === 'void') continue;
      const cur = m.get(r.category) || { category: r.category, amount: 0, count: 0 };
      cur.amount += r.amount || 0; cur.count += 1;
      m.set(r.category, cur);
    }
    return Array.from(m.values()).sort((a, b) => b.amount - a.amount);
  }, [data]);
  const catMax = catBreakdown.reduce((mx, c) => Math.max(mx, c.amount), 0);
  const catTotal = catBreakdown.reduce((s, c) => s + c.amount, 0);

  return (
    <>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', marginBottom: 12 }}>
        <button onClick={() => setShowForm(s => !s)} style={{ background: '#2d6cdf', color: '#fff', border: 'none', borderRadius: 8, padding: '8px 14px', fontSize: 13, fontWeight: 600, cursor: 'pointer' }}>
          {showForm ? '✕ Cancel' : '＋ Add expense'}
        </button>
        <div style={{ flex: 1 }} />
        <select value={fStatus} onChange={e => setFStatus(e.target.value)} style={input}>
          <option value="">All statuses</option>
          {statuses.map((s: string) => <option key={s} value={s}>{s}</option>)}
        </select>
        <select value={fCategory} onChange={e => setFCategory(e.target.value)} style={input}>
          <option value="">All categories</option>
          {cats.map((c: string) => <option key={c} value={c}>{c}</option>)}
        </select>
        <input placeholder="Search payee / note / invoice" value={search} onChange={e => setSearch(e.target.value)} style={{ ...input, width: 220 }} />
        <ExportBtn onClick={() => apiDownload(`/finance/expenses.csv?${new URLSearchParams({ status: fStatus, category: fCategory, search }).toString()}`, 'finance_expenses.csv')} />
      </div>

      {showForm && (
        <div style={{ ...card, marginBottom: 14, display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 10, alignItems: 'end' }}>
          <label style={lbl}>Date<input type="date" value={form.exp_date} onChange={e => setForm({ ...form, exp_date: e.target.value })} style={input} /></label>
          <label style={lbl}>Payee<input value={form.payee} onChange={e => setForm({ ...form, payee: e.target.value })} style={input} placeholder="Vendor / payee" /></label>
          <label style={lbl}>Category<select value={form.category} onChange={e => setForm({ ...form, category: e.target.value })} style={input}>{cats.map((c: string) => <option key={c} value={c}>{c}</option>)}</select></label>
          <label style={lbl}>Amount<input type="number" value={form.amount} onChange={e => setForm({ ...form, amount: e.target.value })} style={input} placeholder="0.00" /></label>
          <label style={lbl}>Currency<input value={form.currency} onChange={e => setForm({ ...form, currency: e.target.value })} style={input} /></label>
          <label style={lbl}>Status<select value={form.status} onChange={e => setForm({ ...form, status: e.target.value })} style={input}>{statuses.map((s: string) => <option key={s} value={s}>{s}</option>)}</select></label>
          <label style={lbl}>Invoice #<input value={form.invoice_no} onChange={e => setForm({ ...form, invoice_no: e.target.value })} style={input} /></label>
          <label style={{ ...lbl, gridColumn: '1 / -1' }}>Note<input value={form.note} onChange={e => setForm({ ...form, note: e.target.value })} style={input} /></label>
          <button onClick={submit} disabled={saving} style={{ background: '#37a35a', color: '#fff', border: 'none', borderRadius: 8, padding: '9px 14px', fontSize: 13, fontWeight: 600, cursor: saving ? 'not-allowed' : 'pointer' }}>{saving ? 'Saving…' : 'Save expense'}</button>
        </div>
      )}

      {data && (
        <div style={{ display: 'flex', gap: 20, marginBottom: 10, fontSize: 12, color: '#8a93a3' }}>
          <span>{fmtNum(data.count)} invoices</span>
          <span style={{ color: '#ffb454' }}>Total {fmtUSD(data.total_amount)}</span>
          <span style={{ color: '#37d67a' }}>Paid {fmtUSD(data.paid_amount)}</span>
        </div>
      )}

      {catBreakdown.length > 0 && (
        <div style={{ ...card, marginBottom: 12 }}>
          <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 10, color: '#cdd3dd' }}>Spend by category (current filter)</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
            {catBreakdown.map(c => (
              <div key={c.category} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <div style={{ width: 130, fontSize: 12, color: '#c4ccd8', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.category}</div>
                <div style={{ flex: 1, height: 16, background: 'var(--bg-card2,#262c36)', borderRadius: 4, overflow: 'hidden' }}>
                  <div style={{ width: `${catMax ? Math.max(2, (c.amount / catMax) * 100) : 0}%`, height: '100%', background: C_EXP, borderRadius: 4 }} title={`${c.category}: ${fmtUSD(c.amount)} (${c.count})`} />
                </div>
                <div style={{ width: 90, textAlign: 'right', fontSize: 12, fontWeight: 600, color: '#ffb454' }}>{fmtUSD(c.amount)}</div>
                <div style={{ width: 48, textAlign: 'right', fontSize: 11, color: '#8a93a3' }}>{Math.round((c.amount / (catTotal || 1)) * 100)}%</div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div style={{ ...card, padding: 0, overflow: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
          <thead>
            <tr style={{ background: 'var(--bg-card2,#262c36)' }}>
              <th style={th}>Date</th>
              <th style={th}>Payee</th>
              <th style={th}>Category</th>
              <th style={{ ...th, textAlign: 'right' }}>Amount</th>
              <th style={th}>Cur</th>
              <th style={th}>Invoice #</th>
              <th style={th}>Note</th>
              <th style={th}>Status</th>
              <th style={th}></th>
            </tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={9} style={{ ...td, color: '#8a93a3' }}>Loading…</td></tr>}
            {!loading && (data?.items || []).length === 0 && <tr><td colSpan={9} style={{ ...td, color: '#8a93a3' }}>No expenses yet — add one above.</td></tr>}
            {!loading && (data?.items || []).map((r: any) => (
              <tr key={r.id}>
                <td style={td}>{r.exp_date}</td>
                <td style={td}>{r.payee}</td>
                <td style={td}>{r.category}</td>
                <td style={{ ...td, textAlign: 'right', fontWeight: 600, color: '#ffb454' }}>{fmtUSD(r.amount)}</td>
                <td style={td}>{r.currency}</td>
                <td style={{ ...td, color: '#8a93a3' }}>{r.invoice_no || '—'}</td>
                <td style={{ ...td, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: '#8a93a3' }}>{r.note || ''}</td>
                <td style={td}>
                  <select value={r.status} onChange={e => setStatus(r.id, e.target.value)} style={{ ...input, padding: '4px 6px', fontSize: 11, color: STATUS_COLOR[r.status] || '#cdd3dd' }}>
                    {statuses.map((s: string) => <option key={s} value={s}>{s}</option>)}
                  </select>
                </td>
                <td style={td}><button onClick={() => remove(r.id)} style={{ background: 'transparent', border: '1px solid #ff5c6c', color: '#ff5c6c', borderRadius: 6, padding: '3px 8px', fontSize: 11, cursor: 'pointer' }}>Delete</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

const lbl: React.CSSProperties = { display: 'flex', flexDirection: 'column', gap: 4, fontSize: 11, color: '#8a93a3' };

// ══════════════════════════════════════════════════════════════════════════════
// P&L / income statement tab
// ══════════════════════════════════════════════════════════════════════════════
function Delta({ pct, goodWhenUp = true }: { pct: number | null | undefined; goodWhenUp?: boolean }) {
  if (pct === null || pct === undefined) return <span style={{ fontSize: 11, color: '#8a93a3' }}>—</span>;
  const up = pct > 0, flat = pct === 0;
  const good = flat ? null : (up === goodWhenUp);
  const color = good === null ? '#8a93a3' : good ? '#37d67a' : '#ff5c6c';
  return <span style={{ fontSize: 11, color, fontWeight: 600 }}>{up ? '▲' : flat ? '' : '▼'} {Math.abs(pct)}%</span>;
}

function PnL() {
  const [period, setPeriod] = useState('this_month');
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    apiGet(`/finance/pnl?period=${period}`)
      .then((d: any) => setData(d)).catch(() => setData(null)).finally(() => setLoading(false));
  }, [period]);
  useEffect(() => { load(); }, [load]);

  const L = data?.lines || {};
  const cur = (k: string) => L[k]?.current ?? 0;
  const pct = (k: string) => L[k]?.pct_change;

  const Row = ({ label, k, sign = 1, bold, total, indent, goodWhenUp = true }:
    { label: string; k?: string; sign?: number; bold?: boolean; total?: boolean; indent?: boolean; goodWhenUp?: boolean }) => {
    const v = k ? cur(k) * sign : 0;
    return (
      <tr style={total ? { background: 'var(--bg-card2,#262c36)' } : undefined}>
        <td style={{ ...td, paddingLeft: indent ? 28 : 10, fontWeight: bold || total ? 700 : 400, color: total ? '#e6e9ef' : '#c4ccd8', borderTop: total ? '2px solid var(--border,#373f4d)' : td.borderTop }}>{label}</td>
        <td style={{ ...td, textAlign: 'right', fontWeight: bold || total ? 700 : 600, color: v < 0 ? '#ff8a93' : (total ? '#e6e9ef' : '#c4ccd8'), borderTop: total ? '2px solid var(--border,#373f4d)' : td.borderTop }}>{fmtUSD(v)}</td>
        <td style={{ ...td, textAlign: 'right', borderTop: total ? '2px solid var(--border,#373f4d)' : td.borderTop }}>{k ? <Delta pct={pct(k)} goodWhenUp={goodWhenUp} /> : null}</td>
      </tr>
    );
  };

  return (
    <>
      <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 16, flexWrap: 'wrap' }}>
        <select value={period} onChange={e => setPeriod(e.target.value)} style={input}>
          {PERIODS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
        {data?.period && (
          <span style={{ fontSize: 12, color: '#8a93a3' }}>
            {data.period.from} → {data.period.to}
            {data.period.prev_from && <> · vs {data.period.prev_from} → {data.period.prev_to}</>}
          </span>
        )}
        <div style={{ flex: 1 }} />
        <ExportBtn onClick={() => apiDownload(`/finance/pnl.csv?period=${period}`, `finance_pnl_${period}.csv`)} />
      </div>

      {loading && <div style={{ color: '#8a93a3', padding: 20 }}>Loading…</div>}
      {!loading && data && (
        <>
          {/* headline KPIs */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(210px, 1fr))', gap: 12, marginBottom: 18 }}>
            <KpiCard label="Net profit" value={fmtUSD(cur('net_profit'))} color={cur('net_profit') >= 0 ? '#37d67a' : '#ff5c6c'} sub={data.net_margin_pct != null ? `${data.net_margin_pct}% net margin` : undefined} />
            <KpiCard label="Gross profit" value={fmtUSD(cur('gross_profit'))} color="#5b9dff" sub="revenue − IB commissions" />
            <KpiCard label="Revenue (markup)" value={fmtUSD(cur('markup_revenue'))} color="#37d67a" sub="spread / markup on trades" />
            <KpiCard label="Operating expenses" value={fmtUSD(cur('operating_expenses'))} color="#ffb454" sub={`+ ${fmtUSD(cur('ib_commission'))} IB paid`} />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: 16, alignItems: 'start' }}>
            {/* income statement */}
            <div style={{ ...card, padding: 0, overflow: 'hidden' }}>
              <div style={{ fontSize: 13, fontWeight: 700, padding: '12px 12px 6px' }}>Income statement</div>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead>
                  <tr>
                    <th style={th}>Line</th>
                    <th style={{ ...th, textAlign: 'right' }}>Amount</th>
                    <th style={{ ...th, textAlign: 'right' }}>vs prev</th>
                  </tr>
                </thead>
                <tbody>
                  <Row label="Spread / markup revenue" k="markup_revenue" />
                  <Row label="less IB commissions paid" k="ib_commission" sign={-1} goodWhenUp={false} />
                  <Row label="Gross profit" k="gross_profit" bold />
                  {(data.expense_by_category || []).map((c: any) => (
                    <tr key={c.category}>
                      <td style={{ ...td, paddingLeft: 28, color: '#8a93a3' }}>{c.category} <span style={{ color: '#5b6472' }}>({c.count})</span></td>
                      <td style={{ ...td, textAlign: 'right', color: '#ff8a93' }}>{fmtUSD(-c.amount)}</td>
                      <td style={td}></td>
                    </tr>
                  ))}
                  {(data.expense_by_category || []).length === 0 && (
                    <tr><td style={{ ...td, paddingLeft: 28, color: '#5b6472' }} colSpan={3}>No expenses recorded this period</td></tr>
                  )}
                  <Row label="Operating expenses" k="operating_expenses" sign={-1} goodWhenUp={false} />
                  <Row label="NET PROFIT" k="net_profit" total />
                </tbody>
              </table>
            </div>

            {/* cash-flow memo + note */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div style={{ ...card }}>
                <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 10 }}>Client cash flow (memo)</div>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                  <tbody>
                    <tr><td style={{ ...td, borderTop: 'none', color: '#c4ccd8' }}>Deposits <span style={{ color: '#5b6472' }}>({fmtNum(data.counts?.deposit || 0)})</span></td><td style={{ ...td, borderTop: 'none', textAlign: 'right', color: '#37d67a', fontWeight: 600 }}>{fmtUSD(cur('deposits'))}</td><td style={{ ...td, borderTop: 'none', textAlign: 'right' }}><Delta pct={pct('deposits')} /></td></tr>
                    <tr><td style={{ ...td, color: '#c4ccd8' }}>Withdrawals <span style={{ color: '#5b6472' }}>({fmtNum(data.counts?.withdrawal || 0)})</span></td><td style={{ ...td, textAlign: 'right', color: '#ff5c6c', fontWeight: 600 }}>{fmtUSD(cur('withdrawals'))}</td><td style={{ ...td, textAlign: 'right' }}><Delta pct={pct('withdrawals')} goodWhenUp={false} /></td></tr>
                    <tr><td style={{ ...td, fontWeight: 700 }}>Net client flow</td><td style={{ ...td, textAlign: 'right', fontWeight: 700, color: cur('net_client_flow') >= 0 ? '#37d67a' : '#ff5c6c' }}>{fmtUSD(cur('net_client_flow'))}</td><td style={{ ...td, textAlign: 'right' }}><Delta pct={pct('net_client_flow')} /></td></tr>
                  </tbody>
                </table>
              </div>
              <div style={{ ...card, background: 'var(--bg-card2,#262c36)' }}>
                <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 8 }}>ℹ️ About this P&L</div>
                <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12, lineHeight: 1.7, color: '#c4ccd8' }}>
                  <li><b>Revenue</b> = spread/markup earned on client trades (the broker's mark-up per lot).</li>
                  <li><b>IB commissions</b> = rebates paid to introducing brokers — a direct cost of that revenue.</li>
                  <li><b>Operating expenses</b> = the invoices logged on the Expenses tab (salaries, marketing, PSP fees…).</li>
                  <li><b>Client cash flow</b> is deposits/withdrawals — client money moving, shown for context (not part of profit).</li>
                </ul>
              </div>
            </div>
          </div>
        </>
      )}
    </>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// Charts (inline SVG) + Trends tab
// ══════════════════════════════════════════════════════════════════════════════
function niceTicks(min: number, max: number, count = 4): number[] {
  if (max === min) { max = min + 1; }
  const span = max - min;
  const step0 = span / count;
  const mag = Math.pow(10, Math.floor(Math.log10(step0)));
  const norm = step0 / mag;
  const step = (norm >= 5 ? 10 : norm >= 2 ? 5 : norm >= 1 ? 2 : 1) * mag;
  const lo = Math.floor(min / step) * step;
  const hi = Math.ceil(max / step) * step;
  const out: number[] = [];
  for (let v = lo; v <= hi + step / 2; v += step) out.push(Math.round(v * 100) / 100);
  return out;
}

type SeriesDef = { key: string; name: string; color: string };

// Grouped/side-by-side bar chart with y-grid, x labels, and per-month hover tooltip.
// Single axis, supports negative values (zero baseline). Identity via legend + tooltip.
function MonthlyBars({ series, data, height = 250, fmt = fmtCompact }:
  { series: SeriesDef[]; data: any[]; height?: number; fmt?: (n: number) => string }) {
  const [hover, setHover] = useState<number | null>(null);
  const W = 860, H = height, padL = 54, padR = 14, padT = 14, padB = 30;
  const plotW = W - padL - padR, plotH = H - padT - padB;
  const n = Math.max(1, data.length);
  const vals = data.flatMap(d => series.map(s => d[s.key] || 0));
  const rawMax = Math.max(0, ...vals), rawMin = Math.min(0, ...vals);
  const ticks = niceTicks(rawMin, rawMax, 4);
  const top = ticks[ticks.length - 1], bot = ticks[0];
  const span = (top - bot) || 1;
  const y = (v: number) => padT + plotH - ((v - bot) / span) * plotH;
  const groupW = plotW / n;
  const innerGap = 2;
  const bw = Math.max(2, (groupW * 0.68 - innerGap * (series.length - 1)) / series.length);
  const y0 = y(0);
  const labelEvery = Math.ceil(n / 12);

  const h = hover != null ? data[hover] : null;
  return (
    <div style={{ position: 'relative', width: '100%' }}>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: 'block' }} preserveAspectRatio="xMidYMid meet">
        {ticks.map((t, i) => (
          <g key={i}>
            <line x1={padL} x2={W - padR} y1={y(t)} y2={y(t)} stroke="var(--border,#373f4d)" strokeWidth={t === 0 ? 1.4 : 0.6} opacity={t === 0 ? 0.9 : 0.5} />
            <text x={padL - 8} y={y(t) + 3} textAnchor="end" fontSize={10} fill="#8a93a3">{fmt(t)}</text>
          </g>
        ))}
        {data.map((d, i) => {
          const gx = padL + i * groupW + (groupW - (bw * series.length + innerGap * (series.length - 1))) / 2;
          return (
            <g key={i}>
              <rect x={padL + i * groupW} y={padT} width={groupW} height={plotH} fill={hover === i ? 'rgba(255,255,255,0.04)' : 'transparent'}
                onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} />
              {series.map((s, si) => {
                const v = d[s.key] || 0;
                const bx = gx + si * (bw + innerGap);
                const by = v >= 0 ? y(v) : y0;
                const bh = Math.max(1, Math.abs(y(v) - y0));
                return <rect key={s.key} x={bx} y={by} width={bw} height={bh} rx={3} fill={s.color} opacity={hover == null || hover === i ? 1 : 0.55} pointerEvents="none" />;
              })}
              {i % labelEvery === 0 && (
                <text x={padL + i * groupW + groupW / 2} y={H - 10} textAnchor="middle" fontSize={10} fill="#8a93a3">{monthLabel(d.month)}</text>
              )}
            </g>
          );
        })}
      </svg>
      {h && (
        <div style={{ position: 'absolute', top: 6, left: `${(padL + (hover! + 0.5) * groupW) / W * 100}%`, transform: 'translateX(-50%)', pointerEvents: 'none', background: 'rgba(20,24,31,0.96)', border: '1px solid var(--border,#373f4d)', borderRadius: 8, padding: '8px 10px', fontSize: 11, whiteSpace: 'nowrap', zIndex: 5 }}>
          <div style={{ fontWeight: 700, marginBottom: 4 }}>{monthLabel(h.month)}</div>
          {series.map(s => (
            <div key={s.key} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ width: 9, height: 9, borderRadius: 2, background: s.color, display: 'inline-block' }} />
              <span style={{ color: '#8a93a3' }}>{s.name}</span>
              <span style={{ marginLeft: 'auto', fontWeight: 600, color: '#e6e9ef' }}>{fmtUSD(h[s.key] || 0)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Legend({ series }: { series: SeriesDef[] }) {
  return (
    <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: 8 }}>
      {series.map(s => (
        <span key={s.key} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: '#c4ccd8' }}>
          <span style={{ width: 11, height: 11, borderRadius: 3, background: s.color, display: 'inline-block' }} />{s.name}
        </span>
      ))}
    </div>
  );
}

const MONTH_OPTS: [number, string][] = [[6, '6 months'], [12, '12 months'], [24, '24 months']];

function Trends() {
  const [months, setMonths] = useState(12);
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    apiGet(`/finance/trends?months=${months}`)
      .then((d: any) => setData(d)).catch(() => setData(null)).finally(() => setLoading(false));
  }, [months]);
  useEffect(() => { load(); }, [load]);

  const series = data?.series || [];
  const totals = data?.totals || {};
  const cashSeries: SeriesDef[] = [{ key: 'deposits', name: 'Deposits', color: C_IN }, { key: 'withdrawals', name: 'Withdrawals', color: C_OUT }];
  const revSeries: SeriesDef[] = [{ key: 'markup_revenue', name: 'Revenue (markup)', color: C_IN }, { key: 'ib_commission', name: 'IB commission', color: '#b07cff' }, { key: 'expenses', name: 'Expenses', color: C_EXP }];
  const profitSeries: SeriesDef[] = [{ key: 'profit', name: 'Net profit', color: C_PROFIT }];

  return (
    <>
      <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 16, flexWrap: 'wrap' }}>
        <select value={months} onChange={e => setMonths(parseInt(e.target.value, 10))} style={input}>
          {MONTH_OPTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
        <span style={{ fontSize: 12, color: '#8a93a3' }}>monthly cash flow, revenue and profit</span>
      </div>

      {loading && <div style={{ color: '#8a93a3', padding: 20 }}>Loading…</div>}
      {!loading && series.length > 0 && (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 12, marginBottom: 18 }}>
            <KpiCard label={`Deposits (${months}m)`} value={fmtUSD(totals.deposits)} color={C_IN} />
            <KpiCard label={`Withdrawals (${months}m)`} value={fmtUSD(totals.withdrawals)} color={C_OUT} />
            <KpiCard label={`Revenue (${months}m)`} value={fmtUSD(totals.markup_revenue)} color={C_IN} />
            <KpiCard label={`Net profit (${months}m)`} value={fmtUSD(totals.profit)} color={totals.profit >= 0 ? C_PROFIT : C_OUT} />
          </div>

          <div style={{ ...card, marginBottom: 16 }}>
            <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 8 }}>Deposits vs withdrawals</div>
            <Legend series={cashSeries} />
            <MonthlyBars series={cashSeries} data={series} />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
            <div style={card}>
              <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 8 }}>Revenue, IB cost & expenses</div>
              <Legend series={revSeries} />
              <MonthlyBars series={revSeries} data={series} height={230} />
            </div>
            <div style={card}>
              <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 8 }}>Net profit by month</div>
              <div style={{ fontSize: 11, color: '#8a93a3', marginBottom: 8 }}>revenue − IB commission − expenses</div>
              <MonthlyBars series={profitSeries} data={series} height={230} />
            </div>
          </div>
        </>
      )}
      {!loading && series.length === 0 && <div style={{ color: '#8a93a3', padding: 20 }}>No data.</div>}
    </>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// PSP reconciliation tab
// ══════════════════════════════════════════════════════════════════════════════
function Reconciliation() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [edits, setEdits] = useState<Record<string, { bal: string; date: string; note: string }>>({});
  const [savingKey, setSavingKey] = useState<string>('');

  const load = useCallback(() => {
    setLoading(true);
    apiGet('/finance/reconciliation')
      .then((d: any) => setData(d)).catch(() => setData(null)).finally(() => setLoading(false));
  }, []);
  useEffect(() => { load(); }, [load]);

  const editFor = (r: any) => edits[r.method] ?? {
    bal: r.statement_balance != null ? String(r.statement_balance) : '',
    date: r.statement_date || '', note: r.note || '',
  };
  const setEdit = (r: any, patch: Partial<{ bal: string; date: string; note: string }>) =>
    setEdits(e => ({ ...e, [r.method]: { ...editFor(r), ...patch } }));

  const save = async (r: any) => {
    const ed = editFor(r);
    if (ed.bal === '') return;
    setSavingKey(r.method);
    try {
      await apiPost('/finance/reconciliation', {
        method: r.method, statement_balance: parseFloat(ed.bal) || 0,
        statement_date: ed.date, note: ed.note,
      });
      setEdits(e => { const n = { ...e }; delete n[r.method]; return n; });
      load();
    } catch { alert('Save failed'); } finally { setSavingKey(''); }
  };
  const clear = async (r: any) => {
    try { await apiDelete(`/finance/reconciliation/${encodeURIComponent(r.method)}`); setEdits(e => { const n = { ...e }; delete n[r.method]; return n; }); load(); }
    catch { alert('Clear failed'); }
  };

  const s = data?.summary || {};
  return (
    <>
      <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 12, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 12, color: '#8a93a3' }}>Enter each PSP's own statement balance to reconcile against our internal net. A non-zero variance is what to chase.</span>
        <div style={{ flex: 1 }} />
        <ExportBtn label="Export methods" onClick={() => apiDownload('/finance/methods.csv', 'finance_payment_methods.csv')} />
      </div>

      {data && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 12, marginBottom: 16 }}>
          <KpiCard label="Methods" value={fmtNum(s.methods)} sub={`${fmtNum(s.with_statement)} with a statement`} />
          <KpiCard label="Reconciled" value={`${fmtNum(s.matched)} / ${fmtNum(s.with_statement)}`} color="#37d67a" sub="statement matches internal" />
          <KpiCard label="Total variance" value={fmtUSD(s.total_variance)} color={Math.abs(s.total_variance) < 1 ? '#37d67a' : '#ffb454'} sub="statement − internal (entered rows)" />
        </div>
      )}

      <div style={{ ...card, padding: 0, overflow: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
          <thead>
            <tr style={{ background: 'var(--bg-card2,#262c36)' }}>
              <th style={th}>Method / PSP</th>
              <th style={{ ...th, textAlign: 'right' }}>Deposits</th>
              <th style={{ ...th, textAlign: 'right' }}>Withdrawals</th>
              <th style={{ ...th, textAlign: 'right' }}>Internal net</th>
              <th style={{ ...th, textAlign: 'right' }}>Statement balance</th>
              <th style={{ ...th, textAlign: 'right' }}>Variance</th>
              <th style={th}>As of</th>
              <th style={th}></th>
            </tr>
          </thead>
          <tbody>
            {loading && <tr><td colSpan={8} style={{ ...td, color: '#8a93a3' }}>Loading…</td></tr>}
            {!loading && (data?.items || []).length === 0 && <tr><td colSpan={8} style={{ ...td, color: '#8a93a3' }}>No methods.</td></tr>}
            {!loading && (data?.items || []).map((r: any) => {
              const ed = editFor(r);
              const dirty = edits[r.method] !== undefined;
              const variance = ed.bal !== '' ? (parseFloat(ed.bal) || 0) - r.net : null;
              return (
                <tr key={r.method}>
                  <td style={{ ...td, maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.method_label}</td>
                  <td style={{ ...td, textAlign: 'right', color: '#7fe0a8' }}>{fmtUSD(r.deposits)}</td>
                  <td style={{ ...td, textAlign: 'right', color: '#ff8a93' }}>{fmtUSD(r.withdrawals)}</td>
                  <td style={{ ...td, textAlign: 'right', fontWeight: 700, color: r.net >= 0 ? '#37d67a' : '#ff5c6c' }}>{fmtUSD(r.net)}</td>
                  <td style={{ ...td, textAlign: 'right' }}>
                    <input type="number" value={ed.bal} placeholder="—"
                      onChange={e => setEdit(r, { bal: e.target.value })}
                      style={{ ...input, width: 110, padding: '4px 6px', textAlign: 'right' }} />
                  </td>
                  <td style={{ ...td, textAlign: 'right', fontWeight: 700, color: variance == null ? '#5b6472' : Math.abs(variance) < 0.01 ? '#37d67a' : '#ffb454' }}>
                    {variance == null ? '—' : fmtUSD(variance)}
                  </td>
                  <td style={{ ...td }}>
                    <input type="date" value={ed.date} onChange={e => setEdit(r, { date: e.target.value })} style={{ ...input, padding: '4px 6px', fontSize: 11 }} />
                  </td>
                  <td style={{ ...td, whiteSpace: 'nowrap' }}>
                    <button onClick={() => save(r)} disabled={ed.bal === '' || savingKey === r.method}
                      style={{ background: dirty ? '#37a35a' : 'var(--bg-card2,#262c36)', color: dirty ? '#fff' : '#8a93a3', border: '1px solid var(--border,#373f4d)', borderRadius: 6, padding: '4px 10px', fontSize: 11, fontWeight: 600, cursor: ed.bal === '' ? 'not-allowed' : 'pointer', marginRight: 6 }}>
                      {savingKey === r.method ? '…' : 'Save'}
                    </button>
                    {r.statement_balance != null && (
                      <button onClick={() => clear(r)} style={{ background: 'transparent', border: '1px solid #ff5c6c', color: '#ff5c6c', borderRadius: 6, padding: '4px 8px', fontSize: 11, cursor: 'pointer' }}>Clear</button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}

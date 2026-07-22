import React, { useState, useEffect, useCallback } from 'react';
import { apiGet, apiPost, apiPatch, apiDelete } from './api';
import { CT } from './crmTable';

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

const fmtUSD = (n: number) => (n < 0 ? '-$' : '$') + Math.abs(Math.round(n || 0)).toLocaleString('en-GB');
const fmtNum = (n: number) => (n || 0).toLocaleString('en-GB');

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
// row hover for the CT data tables
const hoverIn = (e: React.MouseEvent<HTMLTableRowElement>) => (e.currentTarget.style.background = 'var(--bg-card,#2c333e)');
const hoverOut = (e: React.MouseEvent<HTMLTableRowElement>) => (e.currentTarget.style.background = 'transparent');

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

export default function Finance() {
  const [tab, setTab] = useState<'overview' | 'ledger' | 'expenses'>('overview');

  return (
    <div style={{ padding: 16, color: '#e6e9ef', height: '100%', overflow: 'auto' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700 }}>💰 Finance Management</h2>
        <div style={{ flex: 1 }} />
        {(['overview', 'ledger', 'expenses'] as const).map(t => (
          <button key={t} onClick={() => setTab(t)} style={{
            background: tab === t ? '#2d6cdf' : 'var(--bg-card,#2c333e)',
            color: tab === t ? '#fff' : '#cdd3dd',
            border: '1px solid var(--border,#373f4d)', borderRadius: 8,
            padding: '8px 16px', fontSize: 13, fontWeight: 600, cursor: 'pointer', textTransform: 'capitalize',
          }}>{t === 'overview' ? 'Overview' : t === 'ledger' ? 'Ledger' : 'Expenses / Invoices'}</button>
        ))}
      </div>

      {tab === 'overview' && <Overview />}
      {tab === 'ledger' && <Ledger />}
      {tab === 'expenses' && <Expenses />}
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

          <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr', gap: 16, alignItems: 'start' }}>
            {/* Payment-method balances */}
            <div style={card}>
              <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 10 }}>Payment-method balances (net cash in, all-time)</div>
              <div style={CT.scroll}>
                <table style={CT.table}>
                  <thead>
                    <tr style={CT.theadTr}>
                      <th style={CT.th()}>Method / PSP</th>
                      <th style={CT.th(false, 'right')}>Deposits</th>
                      <th style={CT.th(false, 'right')}>Withdrawals</th>
                      <th style={CT.th(false, 'right')}>Net balance</th>
                      <th style={CT.th(false, 'right')}>Txns</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(data.payment_methods || []).length === 0 && (
                      <tr><td colSpan={5} style={{ ...CT.td, color: '#8a93a3' }}>No data</td></tr>
                    )}
                    {(data.payment_methods || []).map((m: any) => (
                      <tr key={m.method} style={CT.row()} onMouseEnter={hoverIn} onMouseLeave={hoverOut}>
                        <td style={CT.td}>{m.method}</td>
                        <td style={{ ...CT.td, textAlign: 'right', color: '#7fe0a8' }}>{fmtUSD(m.deposits)}</td>
                        <td style={{ ...CT.td, textAlign: 'right', color: '#ff8a93' }}>{fmtUSD(m.withdrawals)}</td>
                        <td style={{ ...CT.td, textAlign: 'right', fontWeight: 700, color: m.net >= 0 ? '#37d67a' : '#ff5c6c' }}>{fmtUSD(m.net)}</td>
                        <td style={{ ...CT.td, textAlign: 'right', color: '#8a93a3' }}>{fmtNum(m.count)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* How calculated */}
            <div style={{ ...card, background: 'var(--bg-card2,#262c36)' }}>
              <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 10 }}>ℹ️ How these are calculated</div>
              <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12, lineHeight: 1.7, color: '#c4ccd8' }}>
                <li><b>Total liquidity</b> = all-time genuine deposits − all-time withdrawals = net client funds the platform is holding. Internal MT5 balance adjustments are excluded (not real cash in).</li>
                <li><b>Available liquidity</b> = total liquidity − pending (not-yet-performed) withdrawals — funds not already earmarked to leave.</li>
                <li><b>Payment-method balances</b> = per PSP/method, net of its deposits minus the withdrawals paid back out through it.</li>
                <li><b>Client balances</b> = live sum of trading-account balance (and credit) — what is currently sitting in client accounts.</li>
              </ul>
            </div>
          </div>
        </>
      )}
    </>
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
        <label style={{ fontSize: 11, color: '#8a93a3' }}>From <input type="date" max={new Date(Date.now()+86400000).toISOString().slice(0,10)} value={dateFrom} onChange={e => { setDateFrom(e.target.value); setPage(1); }} style={{ ...input, padding: '5px 8px' }} /></label>
        <label style={{ fontSize: 11, color: '#8a93a3' }}>To <input type="date" max={new Date(Date.now()+86400000).toISOString().slice(0,10)} value={dateTo} onChange={e => { setDateTo(e.target.value); setPage(1); }} style={{ ...input, padding: '5px 8px' }} /></label>
      </div>

      {data && (
        <div style={{ display: 'flex', gap: 20, marginBottom: 10, fontSize: 12, color: '#8a93a3' }}>
          <span>{fmtNum(data.total)} movements</span>
          <span style={{ color: '#37d67a' }}>Deposits {fmtUSD(data.totals?.deposits || 0)}</span>
          <span style={{ color: '#ff5c6c' }}>Withdrawals {fmtUSD(data.totals?.withdrawals || 0)}</span>
        </div>
      )}

      <div style={{ ...card, padding: 0, overflow: 'hidden' }}>
        <div style={CT.scroll}>
          <table style={CT.table}>
            <thead>
              <tr style={CT.theadTr}>
                <th style={CT.th()}>Date</th>
                <th style={CT.th()}>Login</th>
                <th style={CT.th()}>Client</th>
                <th style={CT.th()}>Type</th>
                <th style={CT.th(false, 'right')}>Amount</th>
                <th style={CT.th()}>Method</th>
                <th style={CT.th()}>Status</th>
                <th style={CT.th()}>Reference</th>
              </tr>
            </thead>
            <tbody>
              {loading && <tr><td colSpan={8} style={{ ...CT.td, color: '#8a93a3' }}>Loading…</td></tr>}
              {!loading && (data?.items || []).length === 0 && <tr><td colSpan={8} style={{ ...CT.td, color: '#8a93a3' }}>No movements</td></tr>}
              {!loading && (data?.items || []).map((r: any) => (
                <tr key={r.id} style={CT.row()} onMouseEnter={hoverIn} onMouseLeave={hoverOut}>
                  <td style={CT.td}>{(r.tx_date || '').slice(0, 16)}</td>
                  <td style={CT.td}>{r.login}</td>
                  <td style={{ ...CT.td, maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.client_name}</td>
                  <td style={CT.td}><span style={{ color: TYPE_COLOR[r.tx_type] || '#cdd3dd' }}>{TYPE_LABEL[r.tx_type] || r.tx_type}</span></td>
                  <td style={{ ...CT.td, textAlign: 'right', fontWeight: 600, color: TYPE_COLOR[r.tx_type] || '#e6e9ef' }}>{fmtUSD(r.amount)}</td>
                  <td style={CT.td}>{r.method || '—'}</td>
                  <td style={CT.td}>{r.status}</td>
                  <td style={{ ...CT.td, color: '#8a93a3' }}>{r.psp_reference || r.ref_id || ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
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

      <div style={{ ...card, padding: 0, overflow: 'hidden' }}>
        <div style={CT.scroll}>
          <table style={CT.table}>
            <thead>
              <tr style={CT.theadTr}>
                <th style={CT.th()}>Date</th>
                <th style={CT.th()}>Payee</th>
                <th style={CT.th()}>Category</th>
                <th style={CT.th(false, 'right')}>Amount</th>
                <th style={CT.th()}>Cur</th>
                <th style={CT.th()}>Invoice #</th>
                <th style={CT.th()}>Note</th>
                <th style={CT.th()}>Status</th>
                <th style={CT.th()}></th>
              </tr>
            </thead>
            <tbody>
              {loading && <tr><td colSpan={9} style={{ ...CT.td, color: '#8a93a3' }}>Loading…</td></tr>}
              {!loading && (data?.items || []).length === 0 && <tr><td colSpan={9} style={{ ...CT.td, color: '#8a93a3' }}>No expenses yet — add one above.</td></tr>}
              {!loading && (data?.items || []).map((r: any) => (
                <tr key={r.id} style={CT.row()} onMouseEnter={hoverIn} onMouseLeave={hoverOut}>
                  <td style={CT.td}>{r.exp_date}</td>
                  <td style={CT.td}>{r.payee}</td>
                  <td style={CT.td}>{r.category}</td>
                  <td style={{ ...CT.td, textAlign: 'right', fontWeight: 600, color: '#ffb454' }}>{fmtUSD(r.amount)}</td>
                  <td style={CT.td}>{r.currency}</td>
                  <td style={{ ...CT.td, color: '#8a93a3' }}>{r.invoice_no || '—'}</td>
                  <td style={{ ...CT.td, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', color: '#8a93a3' }}>{r.note || ''}</td>
                  <td style={CT.td}>
                    <select value={r.status} onChange={e => setStatus(r.id, e.target.value)} style={{ ...input, padding: '4px 6px', fontSize: 11, color: STATUS_COLOR[r.status] || '#cdd3dd' }}>
                      {statuses.map((s: string) => <option key={s} value={s}>{s}</option>)}
                    </select>
                  </td>
                  <td style={CT.td}><button onClick={() => remove(r.id)} style={{ background: 'transparent', border: '1px solid #ff5c6c', color: '#ff5c6c', borderRadius: 6, padding: '3px 8px', fontSize: 11, cursor: 'pointer' }}>Delete</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

const lbl: React.CSSProperties = { display: 'flex', flexDirection: 'column', gap: 4, fontSize: 11, color: '#8a93a3' };

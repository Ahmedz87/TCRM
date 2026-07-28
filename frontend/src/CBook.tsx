import React, { useState, useEffect } from 'react';
import { apiGet } from './api';

// Behavioral Client-Flow C-Book — READ-ONLY analysis tab.
// Surfaces Phase 2 §5 client account financial reconstruction + project status.
// Nothing here modifies any client account, balance, order or transaction.

const money = (n: any) => {
  const v = Number(n || 0);
  const s = v < 0 ? '-' : '';
  const a = Math.abs(v);
  return s + '$' + a.toLocaleString(undefined, { maximumFractionDigits: 2 });
};
const C = { ok: '#3ad29f', warn: '#ffaa00', bad: '#ff5d6c', mut: '#8a93a3', txt: '#e8e8e8' };

function Card({ children, style }: any) {
  return <div style={{ background: 'var(--bg-card,#2c333e)', border: '1px solid var(--border,#4f596b)',
    borderRadius: 12, padding: 16, ...style }}>{children}</div>;
}

function Stat({ label, value, color }: any) {
  return (
    <div style={{ minWidth: 150 }}>
      <div style={{ fontSize: 11, color: C.mut, marginBottom: 3 }}>{label}</div>
      <div style={{ fontSize: 17, fontWeight: 700, color: color || C.txt }}>{value}</div>
    </div>
  );
}

function ReconCard({ d }: any) {
  const brk = d.balance_break;
  const reconciled = brk === null ? null : Math.abs(brk) <= 0.01;
  return (
    <Card style={{ marginTop: 14 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12, flexWrap: 'wrap' }}>
        <div style={{ fontSize: 16, fontWeight: 800, color: C.txt }}>Account #{d.login}</div>
        {d.client && <div style={{ fontSize: 13, color: C.mut }}>{d.client.name} · {d.client.country} · {d.client.platform} · {d.client.status}</div>}
        <div style={{ marginLeft: 'auto', fontSize: 12, color: C.mut }}>{d.currency} · period {d.period}</div>
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 20, marginBottom: 14 }}>
        <Stat label="Net completed deposits" value={money(d.net_completed_deposits)} color={C.ok} />
        <Stat label={`Deposits (count)`} value={d.n_deposits} />
        <Stat label="Net completed withdrawals" value={money(d.net_completed_withdrawals)} color={C.warn} />
        <Stat label="Internal transfers (net)" value={money(d.net_internal_transfers)} />
        <Stat label="Bonus / credit (net)" value={money(d.net_bonus_credit)} />
        <Stat label="Balance fixes (net)" value={money(d.net_balance_fix)} />
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 20, marginBottom: 14 }}>
        <Stat label="Realized gross P&L" value={money(d.realized_gross_pnl)} color={d.realized_gross_pnl >= 0 ? C.ok : C.bad} />
        <Stat label="Commission" value={money(d.commission_total)} />
        <Stat label="Swap" value={money(d.swap_total)} />
        <Stat label="Realized NET P&L" value={money(d.realized_net_pnl)} color={d.realized_net_pnl >= 0 ? C.ok : C.bad} />
        <Stat label="Trades" value={d.n_trades} />
        <Stat label="Volume (lots)" value={Number(d.volume_lots || 0).toFixed(2)} />
      </div>

      {/* Reconciliation strip (§26) */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 20, alignItems: 'center',
        borderTop: '1px solid var(--border,#4f596b)', paddingTop: 12 }}>
        <Stat label="Reconstructed closing balance" value={money(d.reconstructed_closing_balance)} />
        <Stat label="MT-reported balance" value={d.reported_closing_balance === null ? '—' : money(d.reported_closing_balance)} />
        <Stat label="Balance break" value={brk === null ? '—' : money(brk)}
          color={reconciled === null ? C.mut : reconciled ? C.ok : C.bad} />
        {d.unrealized_pnl !== undefined && <Stat label="Unrealized P&L (live)" value={money(d.unrealized_pnl)} color={d.unrealized_pnl >= 0 ? C.ok : C.bad} />}
        {d.closing_equity !== undefined && <Stat label="Closing equity" value={money(d.closing_equity)} />}
        {reconciled !== null && (
          <div style={{ marginLeft: 'auto', fontSize: 12, fontWeight: 700, padding: '5px 12px', borderRadius: 20,
            background: reconciled ? 'rgba(58,210,159,0.14)' : 'rgba(255,93,108,0.14)', color: reconciled ? C.ok : C.bad }}>
            {reconciled ? '✓ Reconciled' : '⚠ Reconciliation break'}
          </div>
        )}
      </div>
      {Number(d.unclassified_amount) !== 0 && (
        <div style={{ marginTop: 10, fontSize: 12, color: C.warn }}>
          ⚠ Unclassified movements: {money(d.unclassified_amount)} — investigate before trusting this row.
        </div>
      )}
    </Card>
  );
}

export default function CBook() {
  const [status, setStatus] = useState<any>(null);
  const [login, setLogin] = useState('');
  const [acct, setAcct] = useState<any>(null);
  const [err, setErr] = useState('');
  const [loading, setLoading] = useState(false);
  const [list, setList] = useState<any>(null);
  const [listLoading, setListLoading] = useState(false);

  useEffect(() => { apiGet('/cbook/status').then(setStatus).catch(() => {}); }, []);

  const lookup = () => {
    const l = login.trim();
    if (!l) return;
    setLoading(true); setErr(''); setAcct(null);
    apiGet(`/cbook/account/${encodeURIComponent(l)}`)
      .then(setAcct).catch((e: any) => setErr(e?.message || 'Not found')).finally(() => setLoading(false));
  };

  const runList = () => {
    setListLoading(true);
    apiGet('/cbook/accounts?limit=50&order=break')
      .then(setList).catch(() => setList({ accounts: [] })).finally(() => setListLoading(false));
  };

  return (
    <div style={{ color: C.txt, maxWidth: 1100 }}>
      {/* Header */}
      <div style={{ marginBottom: 6 }}>
        <span style={{ fontSize: 22, fontWeight: 800 }}>📕 C-Book</span>
        <span style={{ marginLeft: 10, fontSize: 12, fontWeight: 700, color: C.ok,
          background: 'rgba(58,210,159,0.14)', padding: '3px 10px', borderRadius: 20 }}>READ-ONLY · analysis</span>
      </div>
      <div style={{ fontSize: 13, color: C.mut, marginBottom: 16, lineHeight: 1.5 }}>
        Behavioral Client-Flow C-Book — financial reconciliation & behavioral classification research.
        This section never opens, closes, or modifies any client account, balance, order or transaction.
      </div>

      {/* Phase + data availability */}
      {status && (
        <Card style={{ marginBottom: 16 }}>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 14 }}>
            {status.phases?.map((p: any) => {
              const col = p.state === 'in_progress' ? C.ok : p.state === 'spec_loaded' ? C.warn
                : p.state === 'partial' ? C.warn : C.mut;
              return (
                <div key={p.n} style={{ flex: '1 1 200px', border: '1px solid var(--border,#4f596b)', borderRadius: 10, padding: 12 }}>
                  <div style={{ fontSize: 11, color: C.mut }}>Phase {p.n}</div>
                  <div style={{ fontSize: 13, fontWeight: 700, margin: '3px 0 6px' }}>{p.name}</div>
                  <div style={{ fontSize: 11, fontWeight: 700, color: col, textTransform: 'uppercase' }}>{String(p.state).replace('_', ' ')}</div>
                  {p.detail && <div style={{ fontSize: 11, color: C.mut, marginTop: 6, lineHeight: 1.4 }}>{p.detail}</div>}
                </div>
              );
            })}
          </div>
          {status.counts && !status.counts.error && (
            <div style={{ display: 'flex', gap: 24, marginBottom: 12 }}>
              <Stat label="Accounts" value={Number(status.counts.accounts).toLocaleString()} />
              <Stat label="Funded accounts" value={Number(status.counts.funded_accounts).toLocaleString()} color={C.ok} />
            </div>
          )}
          <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap' }}>
            <div style={{ flex: '1 1 320px' }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: C.ok, marginBottom: 6 }}>✓ Buildable now</div>
              <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12, color: C.mut, lineHeight: 1.6 }}>
                {status.buildable?.map((b: string, i: number) => <li key={i}>{b}</li>)}
              </ul>
            </div>
            <div style={{ flex: '1 1 320px' }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: C.bad, marginBottom: 6 }}>⚠ Blocked — missing data</div>
              <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12, color: C.mut, lineHeight: 1.6 }}>
                {status.blocked?.map((b: any, i: number) => <li key={i}><b style={{ color: C.txt }}>{b.item}</b> — {b.reason}</li>)}
              </ul>
            </div>
          </div>
        </Card>
      )}

      {/* §5 account reconstruction lookup */}
      <Card>
        <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 4 }}>§5 · Client Account Financial Reconstruction</div>
        <div style={{ fontSize: 12, color: C.mut, marginBottom: 12 }}>
          Enter an account login to reconstruct its financials from <code>deals</code> and reconcile against the MT-reported balance.
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <input value={login} onChange={e => setLogin(e.target.value)} onKeyDown={e => e.key === 'Enter' && lookup()}
            placeholder="Account login (e.g. 1829)"
            style={{ flex: '0 1 260px', padding: '9px 12px', background: 'var(--bg-input,#373f4d)',
              border: '1px solid var(--border2,#626d80)', borderRadius: 8, color: C.txt, fontSize: 14, outline: 'none' }} />
          <button onClick={lookup} disabled={loading}
            style={{ padding: '9px 20px', background: 'var(--accent,#00e5a0)', border: 'none', borderRadius: 8,
              color: '#0b0e14', fontSize: 13, fontWeight: 700, cursor: 'pointer' }}>
            {loading ? '…' : 'Reconstruct'}
          </button>
        </div>
        {err && <div style={{ color: C.bad, fontSize: 13, marginTop: 10 }}>{err}</div>}
        {acct && <ReconCard d={acct} />}
      </Card>

      {/* Aggregate — biggest reconciliation breaks (heavy; run on demand) */}
      <Card style={{ marginTop: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 4 }}>
          <div style={{ fontSize: 14, fontWeight: 700 }}>Top reconciliation breaks</div>
          <button onClick={runList} disabled={listLoading}
            style={{ marginLeft: 'auto', padding: '7px 16px', background: 'var(--bg-input,#373f4d)',
              border: '1px solid var(--border2,#626d80)', borderRadius: 8, color: C.txt, fontSize: 12, cursor: 'pointer' }}>
            {listLoading ? 'Scanning…' : 'Run scan (top 50)'}
          </button>
        </div>
        <div style={{ fontSize: 12, color: C.mut, marginBottom: 10 }}>
          Aggregates across all accounts (scans <code>deals</code> — may take a moment). Largest reconstructed-vs-reported gap first.
        </div>
        {list && (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
              <thead>
                <tr style={{ color: C.mut, textAlign: 'right' }}>
                  <th style={{ textAlign: 'left', padding: '6px 8px' }}>Login</th>
                  <th style={{ padding: '6px 8px' }}>Net deposits</th>
                  <th style={{ padding: '6px 8px' }}>Net withdrawals</th>
                  <th style={{ padding: '6px 8px' }}>Realized net P&L</th>
                  <th style={{ padding: '6px 8px' }}>Reconstructed</th>
                  <th style={{ padding: '6px 8px' }}>Reported</th>
                  <th style={{ padding: '6px 8px' }}>Break</th>
                </tr>
              </thead>
              <tbody>
                {(list.accounts || []).map((a: any) => {
                  const ok = a.balance_break !== null && Math.abs(a.balance_break) <= 0.01;
                  return (
                    <tr key={a.login} style={{ borderTop: '1px solid var(--border,#4f596b)', textAlign: 'right', cursor: 'pointer' }}
                      onClick={() => { setLogin(String(a.login)); apiGet(`/cbook/account/${a.login}`).then(setAcct).catch(() => {}); }}>
                      <td style={{ textAlign: 'left', padding: '6px 8px', fontWeight: 700 }}>#{a.login}</td>
                      <td style={{ padding: '6px 8px' }}>{money(a.net_completed_deposits)}</td>
                      <td style={{ padding: '6px 8px' }}>{money(a.net_completed_withdrawals)}</td>
                      <td style={{ padding: '6px 8px', color: a.realized_net_pnl >= 0 ? C.ok : C.bad }}>{money(a.realized_net_pnl)}</td>
                      <td style={{ padding: '6px 8px' }}>{money(a.reconstructed_closing_balance)}</td>
                      <td style={{ padding: '6px 8px' }}>{a.reported_closing_balance === null ? '—' : money(a.reported_closing_balance)}</td>
                      <td style={{ padding: '6px 8px', fontWeight: 700, color: a.balance_break === null ? C.mut : ok ? C.ok : C.bad }}>
                        {a.balance_break === null ? '—' : money(a.balance_break)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {(!list.accounts || list.accounts.length === 0) && <div style={{ color: C.mut, fontSize: 13, padding: 12 }}>No rows.</div>}
          </div>
        )}
      </Card>
    </div>
  );
}

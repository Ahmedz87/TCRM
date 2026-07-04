import React, { useState, useEffect } from 'react';
import { apiGet, apiPost } from '../api';

function useIsMobile(bp=760){const [m,setM]=React.useState(()=>typeof window!=='undefined'&&window.innerWidth<=bp);React.useEffect(()=>{const o=()=>setM(window.innerWidth<=bp);window.addEventListener('resize',o);return()=>window.removeEventListener('resize',o);},[bp]);return m;}

const fmt = (n: number) => (n == null ? '—' : n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
const TYPES = ['Standard', 'Zero', 'Cent', 'VIP'];
const LEVERAGES = [50, 100, 200, 400, 500, 1000];

export default function Accounts({ onNewAccount, onNav }: { onNewAccount?: () => void; onNav?: (key: string, login?: number) => void }) {
  const mobile = useIsMobile();
  const [accounts, setAccounts] = useState<any[]>([]);
  const [pending, setPending] = useState(false);
  const [trades, setTrades] = useState<any[]>([]);
  const [reqs, setReqs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);

  const [platform, setPlatform] = useState('MT5');
  const [accType, setAccType] = useState('Standard');
  const [leverage, setLeverage] = useState(500);
  const [islamic, setIslamic] = useState(false);
  const [toast, setToast] = useState('');
  const [busy, setBusy] = useState(false);

  // per-account gear menu + modals (#1)
  const [menuFor, setMenuFor] = useState<number | null>(null);
  const [pwModal, setPwModal] = useState<{ login: number; kind: 'master' | 'investor' } | null>(null);
  const [levModal, setLevModal] = useState<{ login: number; current: number } | null>(null);
  const [pwVal, setPwVal] = useState(''); const [pwVal2, setPwVal2] = useState('');
  const [levVal, setLevVal] = useState(500);
  const [mBusy, setMBusy] = useState(false); const [mMsg, setMMsg] = useState(''); const [mErr, setMErr] = useState('');
  const nav = (k: string, login?: number) => { setMenuFor(null); onNav ? onNav(k, login) : window.dispatchEvent(new CustomEvent('portal-nav', { detail: { key: k, login } })); };

  const submitPassword = async () => {
    if (!pwModal) return;
    setMErr(''); setMMsg('');
    if (pwVal.length < 8) { setMErr('Password must be at least 8 characters.'); return; }
    if (pwVal !== pwVal2) { setMErr('Passwords do not match.'); return; }
    setMBusy(true);
    try {
      const r: any = await apiPost(`/portal/accounts/${pwModal.login}/password`, { password: pwVal, kind: pwModal.kind });
      if (r?.ok) { setMMsg(`${pwModal.kind === 'investor' ? 'Investor' : 'Master'} password changed.`); setPwVal(''); setPwVal2(''); setTimeout(() => setPwModal(null), 1200); }
      else setMErr(r?.error || 'Could not change password.');
    } catch (e: any) { setMErr(e?.message || 'Could not change password.'); }
    finally { setMBusy(false); }
  };
  const submitLeverage = async () => {
    if (!levModal) return;
    setMErr(''); setMMsg(''); setMBusy(true);
    try {
      const r: any = await apiPost(`/portal/accounts/${levModal.login}/leverage`, { leverage: levVal });
      if (r?.ok) { setMMsg(`Leverage changed to 1:${levVal}.`); load(); setTimeout(() => setLevModal(null), 1200); }
      else setMErr(r?.error || 'Could not change leverage.');
    } catch (e: any) { setMErr(e?.message || 'Could not change leverage.'); }
    finally { setMBusy(false); }
  };

  const load = () => {
    Promise.all([apiGet('/portal/accounts'), apiGet('/portal/trades'), apiGet('/portal/accounts/requests')])
      .then(([a, t, r]: any) => { setAccounts(a?.accounts || []); setPending(!!a?.pending); setTrades(t?.trades || []); setReqs(r?.requests || []); })
      .catch(() => {}).finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, []);

  const totalBalance = accounts.reduce((s, a) => s + (a.balance || 0), 0);
  // Active accounts on top; archived (inactive, view-only) shown separately below.
  const activeAccts = accounts.filter(a => !a.archived);
  const archivedAccts = accounts.filter(a => a.archived);

  const submit = async () => {
    setBusy(true); setToast('');
    try {
      const res: any = await apiPost('/portal/accounts/request', { platform, account_type: accType, leverage, islamic });
      if (res?.ok) { setToast(res.message); setShowForm(false); load(); }
      else setToast(res?.detail || 'Request failed.');
    } catch (e: any) { setToast(e?.message || 'Request failed.'); }
    finally { setBusy(false); }
  };

  const bigNum = { fontSize: mobile ? 26 : 34, fontWeight: 900, fontVariantNumeric: 'tabular-nums' as const };
  const segM = mobile ? { minHeight: 44, flex: '1 1 auto' as const } : {};

  return (
    <div style={mobile ? { ...S.page, padding: 16 } : S.page}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: 20 }}>
        <h1 style={S.h1}>Your accounts</h1>
        <button onClick={() => onNewAccount ? onNewAccount() : setShowForm(s => !s)} style={S.newBtn}>{showForm ? 'Close' : '+ New account'}</button>
      </div>

      {showForm && (
        <div style={S.formCard}>
          <div style={S.formTitle}>Open a new trading account</div>

          <label style={S.label}>Platform</label>
          <div style={S.segRow}>
            {['MT5', 'MT4'].map(p => (
              <button key={p} onClick={() => setPlatform(p)} style={{ ...S.seg, ...segM, ...(platform === p ? S.segActive : {}) }}>{p}</button>
            ))}
          </div>

          <label style={{ ...S.label, marginTop: 16 }}>Account type</label>
          <div style={S.segRow}>
            {TYPES.map(t => (
              <button key={t} onClick={() => setAccType(t)} style={{ ...S.seg, ...segM, ...(accType === t ? S.segActive : {}) }}>{t}</button>
            ))}
          </div>

          <label style={{ ...S.label, marginTop: 16 }}>Leverage</label>
          <div style={S.segRow}>
            {LEVERAGES.map(l => (
              <button key={l} onClick={() => setLeverage(l)} style={{ ...S.seg, ...segM, ...(leverage === l ? S.segActive : {}) }}>1:{l}</button>
            ))}
          </div>

          <label style={{ ...S.label, marginTop: 16 }}>Islamic (swap-free)</label>
          <div style={{ display: 'flex', alignItems: 'center' }}>
            <button onClick={() => setIslamic(v => !v)} style={{ ...S.toggle, ...(islamic ? S.toggleOn : {}) }}>
              <span style={{ ...S.toggleKnob, transform: islamic ? 'translateX(20px)' : 'translateX(0)' }} />
            </button>
            <span style={{ fontSize: 12, color: '#8A93A3', marginLeft: 10 }}>{islamic ? 'Swap-free enabled' : 'Standard swaps'}</span>
          </div>

          {toast && <div style={S.toast}>{toast}</div>}

          <button onClick={submit} disabled={busy} style={{ ...S.submitBtn, opacity: busy ? 0.6 : 1 }}>
            {busy ? 'Submitting…' : `Open ${platform} ${accType} account`}
          </button>
          <div style={{ fontSize: 11, color: '#5a6373', marginTop: 10 }}>
            Your request is reviewed by our team and the account is set up shortly after.
          </div>
        </div>
      )}

      <div style={S.summary}>
        <div>
          <div style={S.eyebrow}>Total balance</div>
          <div style={{ ...bigNum, color: '#fff' }}>${fmt(totalBalance)}</div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={S.eyebrow}>Accounts</div>
          <div style={{ ...bigNum, color: '#F8500A' }}>{accounts.length}</div>
        </div>
      </div>

      {reqs.length > 0 && (
        <>
          <div style={S.sectionLabel}>Pending requests</div>
          <div style={S.panel}>
            {reqs.map((r, i) => (
              <div key={r.id} style={{ ...S.row, borderBottom: i < reqs.length - 1 ? '1px solid #1A1F2B' : 'none' }}>
                <span style={{ fontSize: 13, color: '#fff' }}>{r.platform} {r.account_type}{r.islamic ? ' · Islamic' : ''} · 1:{r.leverage}</span>
                <span style={{ fontSize: 10.5, fontWeight: 700, color: '#F8500A', background: 'rgba(232,184,75,0.12)', padding: '4px 10px', borderRadius: 6 }}>In review</span>
              </div>
            ))}
          </div>
        </>
      )}

      {loading ? <div style={S.empty}>Loading…</div> : (
        <>
          <div style={S.sectionLabel}>Active accounts</div>
          <div style={S.panel}>
            {activeAccts.length === 0 ? (
              pending
                ? <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: '#F8500A', fontSize: 13, padding: '6px 2px' }}>
                    <span style={{ display: 'inline-block', width: 15, height: 15, borderRadius: 99, border: '2px solid #F8500A', borderTopColor: 'transparent', animation: 'tnfxspin 0.8s linear infinite' }} />
                    Account pending — waiting for verification. Your trading account is created automatically once your documents are approved.
                    <style>{'@keyframes tnfxspin{to{transform:rotate(360deg)}}'}</style>
                  </div>
                : <div style={{ color: '#8A93A3', fontSize: 13 }}>{archivedAccts.length ? 'No active trading accounts. Open one above.' : 'No trading accounts yet. Open one above.'}</div>
            ) :
              activeAccts.map((a, i) => (
                <div key={i} style={{ ...S.row, borderBottom: i < activeAccts.length - 1 ? '1px solid #1A1F2B' : 'none', position: 'relative', flexWrap: 'wrap', gap: 10 }}>
                  <div style={{ minWidth: 150 }}>
                    <div style={{ fontSize: 14, fontWeight: 700, color: '#fff', display: 'flex', alignItems: 'center', gap: 6 }}>
                      {a.login}
                      <span style={{ fontSize: 9, fontWeight: 800, padding: '1px 6px', borderRadius: 4, background: 'rgba(52,211,153,0.15)', color: '#34D399' }}>LIVE</span>
                    </div>
                    <div style={{ fontSize: 11, color: '#8A93A3' }}>{a.type || a.group || '—'} · {a.platform || 'MT5'}</div>
                  </div>
                  <div style={{ textAlign: 'center', minWidth: 70 }}>
                    <div style={{ fontSize: 14, fontWeight: 700, color: '#F8500A', fontVariantNumeric: 'tabular-nums' }}>{a.balance == null ? '—' : `${fmt(a.balance)}`}</div>
                    <div style={{ fontSize: 10, color: '#8A93A3' }}>USD balance</div>
                  </div>
                  <div style={{ textAlign: 'center', minWidth: 50 }}>
                    <div style={{ fontSize: 13, fontWeight: 700, color: '#fff' }}>1:{a.leverage || '—'}</div>
                    <div style={{ fontSize: 10, color: '#8A93A3' }}>leverage</div>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <button onClick={() => nav('deposit', a.login)} style={S.depBtn}>Deposit</button>
                    <button onClick={() => nav('webtrader', a.login)} style={S.tradeBtn}>Trade</button>
                    <button onClick={() => setMenuFor(menuFor === a.login ? null : a.login)} style={S.gearBtn}>⚙</button>
                  </div>
                  {menuFor === a.login && (
                    <>
                      <div onClick={() => setMenuFor(null)} style={{ position: 'fixed', inset: 0, zIndex: 40 }} />
                      <div style={S.menu}>
                        {[
                          ['🏦 Deposit', () => nav('deposit', a.login)],
                          ['💸 Withdraw', () => nav('withdraw', a.login)],
                          ['🔁 Transfer', () => nav('transfer', a.login)],
                          ['⭐ Master Password', () => { setMenuFor(null); setPwVal(''); setPwVal2(''); setMErr(''); setMMsg(''); setPwModal({ login: a.login, kind: 'master' }); }],
                          ['⭐ Investor Password', () => { setMenuFor(null); setPwVal(''); setPwVal2(''); setMErr(''); setMMsg(''); setPwModal({ login: a.login, kind: 'investor' }); }],
                          ['📊 Change Leverage', () => { setMenuFor(null); setLevVal(a.leverage || 500); setMErr(''); setMMsg(''); setLevModal({ login: a.login, current: a.leverage || 500 }); }],
                          ['📈 Web Trader', () => nav('webtrader', a.login)],
                          ['📁 Open Positions', () => nav('positions', a.login)],
                          ['📜 View Account History', () => nav('history', a.login)],
                          ['📖 Transaction History', () => nav('transactions', a.login)],
                        ].map(([label, fn]: any, j) => (
                          <div key={j} onClick={fn} style={S.menuItem}
                            onMouseEnter={e => (e.currentTarget.style.background = '#1A1F2B')} onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}>{label}</div>
                        ))}
                      </div>
                    </>
                  )}
                </div>
              ))}
          </div>

          {archivedAccts.length > 0 && (
            <>
              <div style={S.sectionLabel}>Archived accounts · {archivedAccts.length}</div>
              <div style={{ fontSize: 11.5, color: '#8A93A3', margin: '-4px 2px 10px', lineHeight: 1.5 }}>
                These accounts are inactive and kept for your records only. You can view their history — deposits,
                withdrawals and internal transfers are disabled.
              </div>
              <div style={S.panel}>
                {archivedAccts.map((a, i) => (
                  <div key={i} style={{ ...S.row, borderBottom: i < archivedAccts.length - 1 ? '1px solid #1A1F2B' : 'none', flexWrap: 'wrap', gap: 10, opacity: 0.82 }}>
                    <div style={{ minWidth: 150 }}>
                      <div style={{ fontSize: 14, fontWeight: 700, color: '#cdd4de', display: 'flex', alignItems: 'center', gap: 6 }}>
                        {a.login}
                        <span title="Archived — view only." style={{ fontSize: 9, fontWeight: 800, padding: '1px 6px', borderRadius: 4, background: 'rgba(138,147,163,0.18)', color: '#8A93A3' }}>ARCHIVED</span>
                      </div>
                      <div style={{ fontSize: 11, color: '#8A93A3' }}>{a.type || a.group || '—'} · {a.platform || 'MT5'}</div>
                    </div>
                    <div style={{ textAlign: 'center', minWidth: 70 }}>
                      <div style={{ fontSize: 14, fontWeight: 700, color: '#8A93A3', fontVariantNumeric: 'tabular-nums' }}>{a.balance == null ? '—' : `${fmt(a.balance)}`}</div>
                      <div style={{ fontSize: 10, color: '#8A93A3' }}>USD balance</div>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <button onClick={() => nav('history', a.login)} style={S.histBtn}>📜 History</button>
                      <button onClick={() => nav('positions', a.login)} style={S.histBtn}>📁 Positions</button>
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}

          <div style={S.sectionLabel}>Recent trades</div>
          <div style={S.panel}>
            {trades.length === 0 ? <div style={{ color: '#8A93A3', fontSize: 13 }}>No recent trades.</div> : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
                  <thead>
                    <tr style={{ color: '#8A93A3', textAlign: 'left' }}>
                      <th style={S.th}>Time</th><th style={S.th}>Symbol</th><th style={S.th}>Side</th>
                      <th style={{ ...S.th, textAlign: 'right' }}>Lots</th>
                      <th style={{ ...S.th, textAlign: 'right' }}>Price</th>
                      <th style={{ ...S.th, textAlign: 'right' }}>P/L</th>
                    </tr>
                  </thead>
                  <tbody>
                    {trades.map((t, i) => (
                      <tr key={i} style={{ borderTop: '1px solid #1A1F2B' }}>
                        <td style={S.td}>{t.time}</td>
                        <td style={{ ...S.td, color: '#fff', fontWeight: 600 }}>{t.symbol}</td>
                        <td style={{ ...S.td, color: t.side === 'Buy' ? '#34D399' : '#F2667A' }}>{t.side}</td>
                        <td style={{ ...S.td, textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{t.lots.toFixed(2)}</td>
                        <td style={{ ...S.td, textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{t.price}</td>
                        <td style={{ ...S.td, textAlign: 'right', fontVariantNumeric: 'tabular-nums', color: t.profit >= 0 ? '#34D399' : '#F2667A', fontWeight: 600 }}>{t.profit >= 0 ? '+' : ''}{t.profit.toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}

      {/* Master / Investor password modal */}
      {pwModal && (
        <div style={S.overlay} onClick={() => setPwModal(null)}>
          <div style={S.modal} onClick={e => e.stopPropagation()}>
            <div style={S.modalTitle}>Change {pwModal.kind === 'investor' ? 'Investor (read-only)' : 'Master'} Password</div>
            <div style={{ fontSize: 12, color: '#8A93A3', marginBottom: 14 }}>Account {pwModal.login} · sets the password on the MT5 server.</div>
            <input type="password" value={pwVal} onChange={e => setPwVal(e.target.value)} placeholder="New password (min 8 chars)" style={S.input} />
            <input type="password" value={pwVal2} onChange={e => setPwVal2(e.target.value)} placeholder="Confirm new password" style={{ ...S.input, marginTop: 10 }} />
            {mErr && <div style={{ fontSize: 12.5, color: '#F2667A', marginTop: 10 }}>{mErr}</div>}
            {mMsg && <div style={{ fontSize: 12.5, color: '#34D399', marginTop: 10 }}>{mMsg}</div>}
            <div style={{ display: 'flex', gap: 10, marginTop: 16 }}>
              <button onClick={() => setPwModal(null)} style={S.cancelBtn}>Cancel</button>
              <button onClick={submitPassword} disabled={mBusy} style={{ ...S.submitBtn, marginTop: 0, opacity: mBusy ? 0.6 : 1 }}>{mBusy ? 'Saving…' : 'Change password'}</button>
            </div>
          </div>
        </div>
      )}

      {/* Change leverage modal */}
      {levModal && (
        <div style={S.overlay} onClick={() => setLevModal(null)}>
          <div style={S.modal} onClick={e => e.stopPropagation()}>
            <div style={S.modalTitle}>Change Leverage</div>
            <div style={{ fontSize: 12, color: '#8A93A3', marginBottom: 14 }}>Account {levModal.login} · current 1:{levModal.current}</div>
            <div style={S.segRow}>
              {LEVERAGES.map(l => (
                <button key={l} onClick={() => setLevVal(l)} style={{ ...S.seg, ...(levVal === l ? S.segActive : {}) }}>1:{l}</button>
              ))}
            </div>
            {mErr && <div style={{ fontSize: 12.5, color: '#F2667A', marginTop: 10 }}>{mErr}</div>}
            {mMsg && <div style={{ fontSize: 12.5, color: '#34D399', marginTop: 10 }}>{mMsg}</div>}
            <div style={{ display: 'flex', gap: 10, marginTop: 16 }}>
              <button onClick={() => setLevModal(null)} style={S.cancelBtn}>Cancel</button>
              <button onClick={submitLeverage} disabled={mBusy} style={{ ...S.submitBtn, marginTop: 0, opacity: mBusy ? 0.6 : 1 }}>{mBusy ? 'Saving…' : `Set 1:${levVal}`}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

const S: any = {
  page: { padding: 28, maxWidth: 920, margin: '0 auto' },
  h1: { fontSize: 24, fontWeight: 800, margin: 0, color: '#fff' },
  newBtn: { padding: '9px 18px', minHeight: 40, borderRadius: 9, background: 'linear-gradient(90deg,#F8500A,#FF7A1A)', color: '#0B0E14', border: 'none', fontSize: 13, fontWeight: 800, cursor: 'pointer' },
  formCard: { background: 'linear-gradient(160deg,#141821,#0d1016)', border: '1px solid rgba(232,184,75,0.25)', borderRadius: 16, padding: 22, marginBottom: 22 },
  formTitle: { fontSize: 16, fontWeight: 800, color: '#fff', marginBottom: 16 },
  label: { fontSize: 10.5, letterSpacing: '0.14em', textTransform: 'uppercase', color: '#8A93A3', fontWeight: 700, display: 'block', marginBottom: 8 },
  segRow: { display: 'flex', gap: 8, flexWrap: 'wrap' },
  seg: { padding: '9px 16px', borderRadius: 9, background: '#0d1016', border: '1px solid #2a3240', color: '#cdd4de', fontSize: 12.5, cursor: 'pointer' },
  segActive: { background: 'rgba(232,184,75,0.12)', border: '1px solid #F8500A', color: '#F8500A', fontWeight: 700 },
  toggle: { display: 'inline-flex', alignItems: 'center', width: 44, height: 24, borderRadius: 99, background: '#2a3240', border: 'none', cursor: 'pointer', padding: 2 },
  toggleOn: { background: '#F8500A' },
  toggleKnob: { width: 20, height: 20, borderRadius: 99, background: '#fff', transition: 'transform .18s', display: 'block' },
  toast: { fontSize: 12.5, color: '#34D399', background: 'rgba(52,211,153,0.10)', border: '1px solid rgba(52,211,153,0.25)', borderRadius: 8, padding: '9px 12px', marginTop: 16 },
  submitBtn: { width: '100%', minHeight: 44, marginTop: 18, padding: '12px', borderRadius: 10, background: 'linear-gradient(90deg,#F8500A,#FF7A1A)', color: '#0B0E14', border: 'none', fontSize: 14, fontWeight: 800, cursor: 'pointer' },
  eyebrow: { fontSize: 10.5, letterSpacing: '0.14em', textTransform: 'uppercase', color: '#8A93A3', fontWeight: 700 },
  summary: { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', background: 'linear-gradient(160deg,#12161F,#0d1016)', border: '1px solid #232a38', borderRadius: 16, padding: 22, marginBottom: 22 },
  sectionLabel: { fontSize: 10.5, letterSpacing: '0.14em', textTransform: 'uppercase', color: '#8A93A3', fontWeight: 700, margin: '6px 0 10px' },
  panel: { background: '#12161F', border: '1px solid #232a38', borderRadius: 14, padding: 16, marginBottom: 20 },
  row: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 4px' },
  empty: { padding: 30, textAlign: 'center', color: '#8A93A3', fontSize: 14, background: '#12161F', border: '1px solid #232a38', borderRadius: 14 },
  th: { padding: '6px 8px', fontSize: 10.5, letterSpacing: '0.06em', textTransform: 'uppercase', fontWeight: 700 },
  td: { padding: '8px', color: '#cdd4de' },
  depBtn: { padding: '8px 16px', minHeight: 38, borderRadius: 8, background: '#34D399', color: '#06251b', border: 'none', fontSize: 12.5, fontWeight: 800, cursor: 'pointer' },
  tradeBtn: { padding: '8px 16px', minHeight: 38, borderRadius: 8, background: '#F8500A', color: '#0B0E14', border: 'none', fontSize: 12.5, fontWeight: 800, cursor: 'pointer' },
  histBtn: { padding: '8px 14px', minHeight: 38, borderRadius: 8, background: '#1A1F2B', color: '#cdd4de', border: '1px solid #2a3240', fontSize: 12, fontWeight: 700, cursor: 'pointer' },
  gearBtn: { padding: '8px 11px', minHeight: 38, borderRadius: 8, background: '#2a3240', color: '#cdd4de', border: '1px solid #2a3240', fontSize: 14, cursor: 'pointer' },
  menu: { position: 'absolute', top: 52, right: 4, zIndex: 50, background: '#12161F', border: '1px solid #2a3240', borderRadius: 12, padding: 6, minWidth: 210, boxShadow: '0 12px 40px rgba(0,0,0,0.5)' },
  menuItem: { padding: '10px 12px', fontSize: 13, color: '#e0e0e0', cursor: 'pointer', borderRadius: 8 },
  overlay: { position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', display: 'grid', placeItems: 'center', zIndex: 100, padding: 16 },
  modal: { background: '#12161F', border: '1px solid #232a38', borderRadius: 16, padding: 22, width: 'min(420px,100%)' },
  modalTitle: { fontSize: 16, fontWeight: 800, color: '#fff', marginBottom: 4 },
  input: { width: '100%', padding: '12px 13px', borderRadius: 10, background: '#0B0E14', border: '1px solid #2a3240', color: '#fff', fontSize: 16, outline: 'none', boxSizing: 'border-box', minHeight: 44 },
  cancelBtn: { flex: '0 0 auto', padding: '12px 18px', borderRadius: 10, background: 'transparent', color: '#8A93A3', border: '1px solid #2a3240', fontSize: 13.5, fontWeight: 700, cursor: 'pointer' },
};

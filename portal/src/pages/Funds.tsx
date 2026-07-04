import React, { useState, useEffect } from 'react';
import { apiGet, apiPost } from '../api';

function useIsMobile(bp=760){const [m,setM]=React.useState(()=>typeof window!=='undefined'&&window.innerWidth<=bp);React.useEffect(()=>{const o=()=>setM(window.innerWidth<=bp);window.addEventListener('resize',o);return()=>window.removeEventListener('resize',o);},[bp]);return m;}

const fmt = (n: number) => (n || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const DEPOSIT_METHODS = ['Qi Card', 'Zain Cash', 'Fastpay', 'Sham Cash', 'Credit/Debit Card', 'Crypto (USDT)', 'Ptop',
  'Ovadot Wallet', 'Ovadot Crypto (USDT)', 'Ovadot Q-Card', 'Bank Wire', 'Local Bank'];
const WITHDRAW_METHODS = ['Bank Wire', 'Crypto (USDT)', 'Local Bank'];
// online payment-gateway methods -> gateway key (only usable when that gateway is enabled server-side)
const GATEWAY_MAP: any = { 'Crypto (USDT)': 'paymaxis', 'Credit/Debit Card': 'bridgerpay', 'Ptop': 'ptop',
  'Ovadot Wallet': 'ovadot_ewallet', 'Ovadot Crypto (USDT)': 'ovadot_crypto', 'Ovadot Q-Card': 'ovadot_qcard' };
const STATUS_C: any = {
  pending_simulation: { c: '#F8500A', label: 'Pending' },
  pending_payment: { c: '#F8500A', label: 'Awaiting payment' },
  pending_admin_review: { c: '#F8500A', label: 'In review' },
  approved: { c: '#34D399', label: 'Approved' }, rejected: { c: '#F2667A', label: 'Rejected' },
  completed: { c: '#34D399', label: 'Completed' }, cancelled: { c: '#8A93A3', label: 'Cancelled' },
};

export default function Funds({ mode }: { mode: 'deposit' | 'withdraw' | 'transfer' | 'transactions' }) {
  const mobile = useIsMobile();
  const [accounts, setAccounts] = useState<any[]>([]);
  const [requests, setRequests] = useState<any[]>([]);
  const [txns, setTxns] = useState<any[]>([]);
  const [totals, setTotals] = useState<any>(null);
  const [amount, setAmount] = useState('');
  const [method, setMethod] = useState('');
  const [login, setLogin] = useState('');
  const [toLogin, setToLogin] = useState('');
  const [toast, setToast] = useState('');
  const [busy, setBusy] = useState(false);
  const [wchk, setWchk] = useState<any>(null);
  // manual deposit (Qi/Zain/Fastpay/Sham) — pay-to card + proof upload
  const [card, setCard] = useState<any>(null);
  const [txid, setTxid] = useState('');
  const [walletId, setWalletId] = useState('');
  const [image, setImage] = useState('');
  const isManual = mode === 'deposit' && /qi|zain|fastpay|sham/i.test(method);
  // online gateways that are switched on server-side (empty until configured)
  const [onlineGw, setOnlineGw] = useState<string[]>([]);
  const [cashier, setCashier] = useState<any>(null);   // BridgerPay cashier widget session
  const gateway = mode === 'deposit' ? GATEWAY_MAP[method] : undefined;
  const isOnline = !!gateway && onlineGw.includes(gateway);

  const load = () => {
    apiGet('/portal/accounts').then((a: any) => {
      const accs = a?.accounts || [];
      setAccounts(accs);
      if (accs[0]) setLogin(String(accs[0].login));
      if (accs[1]) setToLogin(String(accs[1].login));
    }).catch(() => {});
    if (mode !== 'transfer') apiGet('/portal/money-requests').then((r: any) => setRequests(r?.requests || [])).catch(() => {});
    apiGet('/portal/transactions').then((r: any) => { setTxns(r?.transactions || []); setTotals(r?.totals || null); }).catch(() => {});
    if (mode === 'deposit') apiGet('/portal/deposit/online-methods').then((r: any) => setOnlineGw((r?.methods || []).map((m: any) => m.gateway))).catch(() => {});
  };
  useEffect(() => { setAmount(''); setMethod(''); setToast(''); setWchk(null); load(); /* eslint-disable-next-line */ }, [mode]);

  // live withdrawal check — min amount, bonus clawback, and margin-level guard
  useEffect(() => {
    if (mode !== 'withdraw') { setWchk(null); return; }
    const amt = parseFloat(amount) || 0;
    if (amt <= 0) { setWchk(null); return; }
    const t = setTimeout(() => {
      apiPost('/portal/bonus/withdraw-check', { amount: amt }).then(setWchk).catch(() => setWchk(null));
    }, 250);
    return () => clearTimeout(t);
  }, [amount, mode]);

  // manual deposit — fetch the company card that's on-shift right now for the chosen method.
  // Passes the amount so per-transaction / monthly card limits are respected; re-fetches when
  // the amount changes (debounced) so the client always sees an eligible card.
  useEffect(() => {
    if (!isManual) { setCard(null); return; }
    const amt = parseFloat(amount) || 0;
    const t = setTimeout(() => {
      apiGet(`/portal/deposit/card?method=${encodeURIComponent(method)}&amount=${amt}`).then(setCard).catch(() => setCard(null));
    }, 350);
    return () => clearTimeout(t);
  }, [method, isManual, amount]);

  const pickProof = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]; if (!f) return;
    if (f.size > 7 * 1024 * 1024) { setToast('Image is over 7MB — please upload a smaller photo.'); return; }
    const r = new FileReader(); r.onload = () => setImage(String(r.result || '')); r.readAsDataURL(f);
  };

  const title = mode === 'deposit' ? 'Deposit' : mode === 'withdraw' ? 'Withdraw' : 'Transfer';
  // A gateway-backed deposit method (Ovadot/Paymaxis/BridgerPay/Ptop) is shown ONLY when that
  // gateway is enabled server-side; disabled ones stay in admin settings but are hidden here.
  const methods = mode === 'deposit'
    ? DEPOSIT_METHODS.filter(m => !GATEWAY_MAP[m] || onlineGw.includes(GATEWAY_MAP[m]))
    : WITHDRAW_METHODS;
  // Archived accounts are READ-ONLY (history only): never selectable for deposit, internal transfer
  // OR withdrawal. The backend also enforces this (_assert_not_archived) as defense-in-depth.
  const selectable = accounts.filter(a => !a.archived);

  const submit = async () => {
    const amt = parseFloat(amount);
    if (!amt || amt <= 0) { setToast('Enter a valid amount.'); return; }
    if (mode !== 'transfer' && !method) { setToast('Choose a method.'); return; }
    if (mode === 'transfer' && (!login || !toLogin || login === toLogin)) { setToast('Choose two different accounts.'); return; }
    if (isManual) {
      if (!card?.available) { setToast('No company card available right now — please pick another method.'); return; }
      if (!txid.trim()) { setToast('Enter the transaction ID from your receipt.'); return; }
      if (!image) { setToast('Upload your transfer screenshot.'); return; }
    }
    setBusy(true); setToast('');
    try {
      let res: any;
      if (mode === 'transfer') res = await apiPost('/portal/transfer', { from_login: Number(login), to_login: Number(toLogin), amount: amt });
      else if (isManual) res = await apiPost('/portal/deposit/manual', { login: Number(login), amount: amt, method, card_id: card?.card_id, txid: txid.trim(), wallet_id: walletId.trim(), image });
      else if (isOnline) {
        // real online gateway — create a session and send the client to the gateway's payment page
        res = await apiPost('/portal/deposit/online', { login: Number(login), amount: amt, gateway });
        if (res?.ok && res.payment_url) { setToast('Redirecting to secure payment…'); window.location.href = res.payment_url; return; }
        else if (res?.ok && res.crypto) {
          // Ovadot crypto — deposit address returned (no redirect)
          const cr = res.crypto || {};
          const addr = cr.pay_address || cr.address || cr.deposit_address || '';
          setToast(addr ? `Send ${cr.pay_amount || amt} ${(cr.pay_currency || 'USDT').toUpperCase()} to: ${addr}` : 'Crypto deposit created — check Request history.');
          setAmount(''); setMethod(''); load();
        }
        else if (res?.ok && res.cashier) { setToast(''); setCashier(res.cashier); }   // open BridgerPay cashier widget
        else setToast(res?.error || 'Could not start the payment.');
      }
      else res = await apiPost(`/portal/${mode}`, { amount: amt, method, login: login ? Number(login) : null });
      if (res?.ok && !isOnline) { setToast(res.message); setAmount(''); setMethod(''); setTxid(''); setWalletId(''); setImage(''); setCard(null); load(); }
      else if (!isOnline) setToast(res?.message || res?.detail || 'Request failed.');
    } catch (e: any) { setToast(e?.message || 'Request failed.'); }
    finally { setBusy(false); }
  };

  const inputStyle = mobile ? { ...S.input, fontSize: 16 } : S.input;

  // dedicated Transactions tab — ledger only (no deposit/withdraw form)
  if (mode === 'transactions') {
    return (
      <div style={mobile ? { ...S.page, padding: 16 } : S.page}>
        <h1 style={S.h1}>Transactions</h1>
        {totals && (
          <div style={{ display: 'flex', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
            <div style={{ flex: 1, minWidth: 120, background: '#12161F', border: '1px solid #232a38', borderRadius: 12, padding: '12px 14px' }}>
              <div style={{ fontSize: 10.5, color: '#8A93A3', textTransform: 'uppercase', letterSpacing: '0.1em' }}>Total deposits</div>
              <div style={{ fontSize: 19, fontWeight: 800, color: '#34D399' }}>${fmt(totals.deposits)}</div>
            </div>
            <div style={{ flex: 1, minWidth: 120, background: '#12161F', border: '1px solid #232a38', borderRadius: 12, padding: '12px 14px' }}>
              <div style={{ fontSize: 10.5, color: '#8A93A3', textTransform: 'uppercase', letterSpacing: '0.1em' }}>Total withdrawals</div>
              <div style={{ fontSize: 19, fontWeight: 800, color: '#ff6b6b' }}>${fmt(totals.withdrawals)}</div>
            </div>
            <div style={{ flex: 1, minWidth: 120, background: '#12161F', border: '1px solid #232a38', borderRadius: 12, padding: '12px 14px' }}>
              <div style={{ fontSize: 10.5, color: '#8A93A3', textTransform: 'uppercase', letterSpacing: '0.1em' }}>Net deposited</div>
              <div style={{ fontSize: 19, fontWeight: 800, color: '#fff' }}>${fmt(totals.net)}</div>
            </div>
          </div>
        )}
        <div style={S.panel}>
          {txns.length === 0 ? <div style={{ color: '#8A93A3', fontSize: 13 }}>No transactions yet.</div> :
            txns.map((t, i) => {
              const isDep = t.type === 'deposit' || t.type === 'bonus_deposit';
              const isWd = t.type === 'withdrawal' || t.type === 'bonus_withdrawal';
              const col = t.pending ? '#F8500A' : isDep ? '#34D399' : isWd ? '#ff6b6b' : '#9aa3b2';
              const sign = isDep ? '+' : isWd ? '−' : '';
              const label = t.type === 'internal_transfer' ? 'Transfer' : t.type.replace('_', ' ').replace(/\b\w/g, (m: string) => m.toUpperCase());
              return (
                <div key={i} style={{ ...S.reqRow, borderBottom: i < txns.length - 1 ? '1px solid #1A1F2B' : 'none' }}>
                  <div>
                    <div style={{ fontSize: 13.5, fontWeight: 700, color: '#fff' }}>{label}{t.pending ? <span style={{ marginLeft: 8, fontSize: 10, color: '#F8500A', background: 'rgba(232,184,75,0.14)', padding: '2px 7px', borderRadius: 6, fontWeight: 800 }}>PENDING</span> : null}</div>
                    <div style={{ fontSize: 11, color: '#8A93A3' }}>{(t.date || '').slice(0, 16).replace('T', ' ')}{t.method ? ` · ${t.method}` : ''}{t.login ? ` · #${t.login}` : ''}</div>
                  </div>
                  <div style={{ fontSize: 14.5, fontWeight: 800, color: col }}>{sign}${fmt(t.amount)}</div>
                </div>
              );
            })}
        </div>
      </div>
    );
  }

  return (
    <div style={mobile ? { ...S.page, padding: 16 } : S.page}>
      <h1 style={S.h1}>{title}</h1>
      <div style={S.simBanner}>
        ⚙️ Demo mode — {mode === 'transfer' ? 'transfers are' : `${mode}s are`} recorded for review. No real money moves until the live gateway is connected.
      </div>

      <div style={S.panel}>
        <label style={S.label}>{mode === 'transfer' ? 'From account' : 'Account'}</label>
        <select value={login} onChange={e => setLogin(e.target.value)} style={inputStyle}>
          {selectable.length === 0 && <option value="">No active accounts</option>}
          {selectable.map((a, i) => <option key={i} value={a.login}>#{a.login} {a.balance != null ? `· $${fmt(a.balance)}` : ''}</option>)}
        </select>

        {mode === 'transfer' && (
          <>
            <label style={{ ...S.label, marginTop: 16 }}>To account</label>
            <select value={toLogin} onChange={e => setToLogin(e.target.value)} style={inputStyle}>
              {selectable.map((a, i) => <option key={i} value={a.login}>#{a.login} {a.balance != null ? `· $${fmt(a.balance)}` : ''}</option>)}
            </select>
          </>
        )}

        <label style={{ ...S.label, marginTop: 16 }}>Amount (USD)</label>
        <input value={amount} onChange={e => setAmount(e.target.value.replace(/[^0-9.]/g, ''))} placeholder="0.00" inputMode="decimal" style={inputStyle} />

        {mode !== 'transfer' && (
          <>
            <label style={{ ...S.label, marginTop: 16 }}>Method</label>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {methods.map(m => (
                <button key={m} onClick={() => setMethod(m)} style={{ ...S.methodChip, ...(mobile ? { flex: '1 1 45%', minHeight: 44 } : {}), ...(method === m ? S.methodChipActive : {}) }}>{m}</button>
              ))}
            </div>
          </>
        )}

        {/* Manual deposit — pay the on-shift company card, then upload the transfer proof */}
        {isManual && (
          <div style={{ marginTop: 16, background: '#11161f', border: '1px solid #232d3a', borderRadius: 12, padding: 16 }}>
            {card == null ? <div style={{ color: '#8A93A3', fontSize: 13 }}>Loading available card…</div>
              : !card.available ? <div style={{ color: '#F8500A', fontSize: 13 }}>{card.message}</div>
              : (
              <>
                <div style={{ fontSize: 13, fontWeight: 700, color: '#fff', marginBottom: 4 }}>Step 1 — Send {amount ? <span style={{ color: '#34D399' }}>${fmt(parseFloat(amount) || 0)}</span> : 'the amount'} to this {method}:</div>
                {card.on_shift === false && <div style={{ fontSize: 11, color: '#E8B84B', marginBottom: 6 }}>ℹ️ Outside working hours — your deposit may take a little longer to review.</div>}
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: '#0d1117', border: '1px solid #2f3a48', borderRadius: 10, padding: '12px 14px', marginBottom: 6 }}>
                  <div>
                    <div style={{ fontSize: 10, color: '#8A93A3', textTransform: 'uppercase', letterSpacing: 1 }}>{method} number</div>
                    <div style={{ fontFamily: 'monospace', fontSize: 19, fontWeight: 700, color: '#fff', letterSpacing: 1 }}>{card.number}</div>
                    {card.account_number ? <div style={{ fontFamily: 'monospace', fontSize: 12.5, color: '#cfd6e0', marginTop: 2 }}>Account: {card.account_number}</div> : null}
                    {card.card_name ? <div style={{ fontSize: 11.5, color: '#cfd6e0', marginTop: 2 }}>Name on card: <b>{card.card_name}</b></div> : null}
                  </div>
                  <button onClick={() => { try { navigator.clipboard.writeText(card.number); setToast('Card number copied'); } catch {} }}
                    style={{ fontSize: 11.5, fontWeight: 700, color: '#34D399', background: 'rgba(52,211,153,0.12)', border: '1px solid rgba(52,211,153,0.35)', padding: '6px 12px', borderRadius: 7, cursor: 'pointer' }}>Copy</button>
                </div>
                <div style={{ fontSize: 11, color: '#8A93A3', margin: '2px 0 14px' }}>Send the exact amount above, then fill in the details below from your receipt.</div>

                <div style={{ fontSize: 13, fontWeight: 700, color: '#fff', margin: '4px 0 6px' }}>Step 2 — Enter your receipt details</div>
                <label style={S.label}>Transaction ID (from your receipt)</label>
                <input value={txid} onChange={e => setTxid(e.target.value)} placeholder="e.g. 2026062610121420010100166764206475862" style={inputStyle} />

                <label style={{ ...S.label, marginTop: 14 }}>Your wallet ID (sender)</label>
                <input value={walletId} onChange={e => setWalletId(e.target.value)} placeholder="The number you sent FROM" style={inputStyle} />

                <div style={{ fontSize: 13, fontWeight: 700, color: '#fff', margin: '14px 0 6px' }}>Step 3 — Upload your transfer screenshot</div>
                <input type="file" accept="image/*" onChange={pickProof} style={{ ...inputStyle, padding: 8 }} />
                {image && <img src={image} alt="proof" style={{ marginTop: 10, maxWidth: '100%', maxHeight: 200, borderRadius: 8, border: '1px solid #2f3a48' }} />}
                <div style={{ fontSize: 11, color: '#8A93A3', marginTop: 10 }}>Our team reviews and approves every manual deposit. Fake or altered receipts are detected automatically.</div>
              </>
            )}
          </div>
        )}

        {mode === 'withdraw' && wchk && (
          <div style={wchk.ok ? S.infoBox : S.warnBox}>
            {wchk.ok ? (
              <>
                <div>Minimum withdrawal: <b>${fmt(wchk.min_withdraw)}</b> ({wchk.deposited ? 'you have deposited' : 'no deposit yet'}).</div>
                {wchk.clawback > 0 && <div style={{ marginTop: 4 }}>🎁 Withdrawing this will deduct <b>${fmt(wchk.clawback)}</b> of bonus credit proportionally (you have ${fmt(wchk.credit)} bonus).</div>}
                {wchk.margin_level != null && <div style={{ marginTop: 4 }}>Margin level after: <b>{wchk.margin_level}%</b>.</div>}
              </>
            ) : (
              <>
                <div style={{ fontWeight: 700 }}>⚠️ {wchk.reason}</div>
                {wchk.max_withdraw != null && <div style={{ marginTop: 4 }}>You can withdraw up to <b>${fmt(wchk.max_withdraw)}</b>{wchk.max_withdraw > 0 ? '.' : ', or close some open trades first.'}</div>}
              </>
            )}
          </div>
        )}

        {toast && <div style={S.toast}>{toast}</div>}
        <button onClick={submit} disabled={busy || (mode === 'withdraw' && wchk && !wchk.ok)} style={{ ...S.submitBtn, opacity: (busy || (mode === 'withdraw' && wchk && !wchk.ok)) ? 0.6 : 1 }}>
          {busy ? 'Submitting…' : `${title} ${amount ? `$${fmt(parseFloat(amount) || 0)}` : ''}`}
        </button>
      </div>

      {mode !== 'transfer' && (
        <>
          <div style={S.sectionLabel}>Request history</div>
          <div style={S.panel}>
            {requests.filter(r => r.kind === mode).length === 0 ? <div style={{ color: '#8A93A3', fontSize: 13 }}>No {mode} requests yet.</div> :
              requests.filter(r => r.kind === mode).map((r, i, arr) => {
                const st = STATUS_C[r.status] || { c: '#8A93A3', label: r.status };
                return (
                  <div key={r.id} style={{ ...S.reqRow, borderBottom: i < arr.length - 1 ? '1px solid #1A1F2B' : 'none' }}>
                    <div>
                      <div style={{ fontSize: 13.5, fontWeight: 700, color: '#fff' }}>${fmt(r.amount)}</div>
                      <div style={{ fontSize: 11, color: '#8A93A3' }}>{r.method} · {r.date}{r.login ? ` · #${r.login}` : ''}</div>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span style={{ fontSize: 10.5, fontWeight: 700, color: st.c, background: st.c + '1f', padding: '4px 10px', borderRadius: 6 }}>{st.label}</span>
                      {r.cancellable && (
                        <button onClick={async () => {
                          if (!window.confirm('Cancel this pending withdrawal?')) return;
                          try { const res: any = await apiPost(`/portal/money-requests/${r.id}/cancel`, {});
                            if (res?.ok) { setToast('Withdrawal cancelled'); load(); } else setToast(res?.error || 'Could not cancel'); }
                          catch { setToast('Could not cancel'); }
                        }} style={{ fontSize: 10.5, fontWeight: 700, color: '#ff6b6b', background: 'rgba(255,107,107,0.12)', border: '1px solid rgba(255,107,107,0.35)', padding: '4px 10px', borderRadius: 6, cursor: 'pointer' }}>Cancel</button>
                      )}
                    </div>
                  </div>
                );
              })}
          </div>
        </>
      )}

      {/* FULL TRANSACTION HISTORY — all real deposits/withdrawals/transfers + anything pending */}
      <div style={S.sectionLabel}>Transaction history</div>
      {totals && (
        <div style={{ display: 'flex', gap: 10, marginBottom: 12, flexWrap: 'wrap' }}>
          <div style={{ flex: 1, minWidth: 120, background: '#12161F', border: '1px solid #232a38', borderRadius: 12, padding: '12px 14px' }}>
            <div style={{ fontSize: 10.5, color: '#8A93A3', textTransform: 'uppercase', letterSpacing: '0.1em' }}>Total deposits</div>
            <div style={{ fontSize: 19, fontWeight: 800, color: '#34D399' }}>${fmt(totals.deposits)}</div>
          </div>
          <div style={{ flex: 1, minWidth: 120, background: '#12161F', border: '1px solid #232a38', borderRadius: 12, padding: '12px 14px' }}>
            <div style={{ fontSize: 10.5, color: '#8A93A3', textTransform: 'uppercase', letterSpacing: '0.1em' }}>Total withdrawals</div>
            <div style={{ fontSize: 19, fontWeight: 800, color: '#ff6b6b' }}>${fmt(totals.withdrawals)}</div>
          </div>
          <div style={{ flex: 1, minWidth: 120, background: '#12161F', border: '1px solid #232a38', borderRadius: 12, padding: '12px 14px' }}>
            <div style={{ fontSize: 10.5, color: '#8A93A3', textTransform: 'uppercase', letterSpacing: '0.1em' }}>Net deposited</div>
            <div style={{ fontSize: 19, fontWeight: 800, color: '#fff' }}>${fmt(totals.net)}</div>
          </div>
        </div>
      )}
      <div style={S.panel}>
        {txns.length === 0 ? <div style={{ color: '#8A93A3', fontSize: 13 }}>No transactions yet.</div> :
          txns.map((t, i) => {
            const isDep = t.type === 'deposit' || t.type === 'bonus_deposit';
            const isWd = t.type === 'withdrawal' || t.type === 'bonus_withdrawal';
            const col = t.pending ? '#F8500A' : isDep ? '#34D399' : isWd ? '#ff6b6b' : '#9aa3b2';
            const sign = isDep ? '+' : isWd ? '−' : '';
            const label = t.type === 'internal_transfer' ? 'Transfer' : t.type.replace('_', ' ').replace(/\b\w/g, (m: string) => m.toUpperCase());
            return (
              <div key={i} style={{ ...S.reqRow, borderBottom: i < txns.length - 1 ? '1px solid #1A1F2B' : 'none' }}>
                <div>
                  <div style={{ fontSize: 13.5, fontWeight: 700, color: '#fff' }}>{label}{t.pending ? <span style={{ marginLeft: 8, fontSize: 10, color: '#F8500A', background: 'rgba(232,184,75,0.14)', padding: '2px 7px', borderRadius: 6, fontWeight: 800 }}>PENDING</span> : null}</div>
                  <div style={{ fontSize: 11, color: '#8A93A3' }}>{(t.date || '').slice(0, 16).replace('T', ' ')}{t.method ? ` · ${t.method}` : ''}{t.login ? ` · #${t.login}` : ''}</div>
                </div>
                <div style={{ fontSize: 14.5, fontWeight: 800, color: col }}>{sign}${fmt(t.amount)}</div>
              </div>
            );
          })}
      </div>

      {cashier && <BridgerPayCashier cashier={cashier} onClose={() => { setCashier(null); setAmount(''); setMethod(''); load(); }} />}
    </div>
  );
}

// BridgerPay cashier widget — loads the v2 launcher (api_key/cashier_key/cashier_token) into a
// modal. The deposit is credited server-side via the gateway webhook; the postMessage events here
// are only for UX (close on success/cancel). Crediting never depends on the browser.
function BridgerPayCashier({ cashier, onClose }: { cashier: any; onClose: () => void }) {
  React.useEffect(() => {
    const launcher = cashier.launcher || 'https://checkout.bridgerpay.com/v2/launcher';
    const src = `${launcher}/${cashier.api_key}/${cashier.cashier_key}/${cashier.cashier_token}`;
    const s = document.createElement('script');
    s.src = src; s.async = true; s.id = 'bridgerpay-launcher';
    document.body.appendChild(s);
    const onMsg = (e: MessageEvent) => {
      const d: any = e.data || {};
      const t = String(d.type || d.event || d).toLowerCase();
      if (/success|approved|complete|deposit:success/.test(t)) { setTimeout(onClose, 1500); }
      if (/close|cancel|exit/.test(t)) { onClose(); }
    };
    window.addEventListener('message', onMsg);
    return () => {
      window.removeEventListener('message', onMsg);
      document.getElementById('bridgerpay-launcher')?.remove();
      // BridgerPay injects its own container; clean it up so re-open works
      document.querySelectorAll('[id^="bridger"], [class*="bridger"]').forEach(el => { try { el.remove(); } catch {} });
    };
    // eslint-disable-next-line
  }, []);
  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', zIndex: 4000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 12 }}>
      <div style={{ background: '#0d1016', border: '1px solid #2a3240', borderRadius: 14, width: 'min(480px,96vw)', maxHeight: '92vh', overflow: 'auto', position: 'relative' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 16px', borderBottom: '1px solid #232a38' }}>
          <div style={{ fontWeight: 800, color: '#fff', fontSize: 15 }}>Secure card payment</div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#8A93A3', fontSize: 22, cursor: 'pointer', lineHeight: 1 }}>×</button>
        </div>
        {/* BridgerPay renders its cashier into this container */}
        <div id="bridgerpay-cashier" data-cashier-key={cashier.cashier_key} data-cashier-token={cashier.cashier_token} style={{ minHeight: 420, padding: 8 }}>
          <div style={{ color: '#8A93A3', fontSize: 12.5, textAlign: 'center', padding: 40 }}>Loading secure payment form…</div>
        </div>
      </div>
    </div>
  );
}

const S: any = {
  page: { padding: 28, maxWidth: 680, margin: '0 auto' },
  h1: { fontSize: 24, fontWeight: 800, margin: '0 0 16px', color: '#fff' },
  simBanner: { fontSize: 12, color: '#F8500A', background: 'rgba(232,184,75,0.08)', border: '1px solid rgba(232,184,75,0.22)', borderRadius: 10, padding: '10px 14px', marginBottom: 20, lineHeight: 1.5 },
  panel: { background: '#12161F', border: '1px solid #232a38', borderRadius: 14, padding: 20, marginBottom: 20 },
  label: { fontSize: 10.5, letterSpacing: '0.14em', textTransform: 'uppercase', color: '#8A93A3', fontWeight: 700, display: 'block', marginBottom: 7 },
  input: { width: '100%', padding: '11px 13px', borderRadius: 10, background: '#0B0E14', border: '1px solid #2a3240', color: '#fff', fontSize: 14, outline: 'none', boxSizing: 'border-box' },
  methodChip: { padding: '9px 14px', borderRadius: 9, background: '#0d1016', border: '1px solid #2a3240', color: '#cdd4de', fontSize: 12.5, cursor: 'pointer' },
  methodChipActive: { background: 'rgba(232,184,75,0.12)', border: '1px solid #F8500A', color: '#F8500A', fontWeight: 700 },
  toast: { fontSize: 12.5, color: '#34D399', background: 'rgba(52,211,153,0.10)', border: '1px solid rgba(52,211,153,0.25)', borderRadius: 8, padding: '9px 12px', marginTop: 16 },
  infoBox: { fontSize: 12, color: '#cdd4de', background: 'rgba(232,184,75,0.07)', border: '1px solid rgba(232,184,75,0.22)', borderRadius: 8, padding: '10px 12px', marginTop: 16, lineHeight: 1.5 },
  warnBox: { fontSize: 12.5, color: '#F2667A', background: 'rgba(242,102,122,0.08)', border: '1px solid rgba(242,102,122,0.3)', borderRadius: 8, padding: '10px 12px', marginTop: 16, lineHeight: 1.5 },
  submitBtn: { width: '100%', minHeight: 44, marginTop: 18, padding: '12px', borderRadius: 10, background: 'linear-gradient(90deg,#F8500A,#FF7A1A)', color: '#0B0E14', border: 'none', fontSize: 14, fontWeight: 800, cursor: 'pointer' },
  sectionLabel: { fontSize: 10.5, letterSpacing: '0.14em', textTransform: 'uppercase', color: '#8A93A3', fontWeight: 700, margin: '6px 0 10px' },
  reqRow: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 4px' },
};

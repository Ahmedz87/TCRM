import React, { useState, useEffect, useRef } from 'react';
import { apiGet, apiPost } from './api';
import { TH, fmtMoney } from './theme';
import { Wizard, OptionCard, primaryBtn, ghostBtn } from './Wizard';

function useIsMobile(bp=760){const [m,setM]=React.useState(()=>typeof window!=='undefined'&&window.innerWidth<=bp);React.useEffect(()=>{const o=()=>setM(window.innerWidth<=bp);window.addEventListener('resize',o);return()=>window.removeEventListener('resize',o);},[bp]);return m;}

const STEPS = ['Payment & amount', 'Confirm & pay', 'Done'];

// size-aware branded logo per method (used small in the confirm header, large in the square tiles)
function MethodLogo({ logo, size = 38 }: { logo: string; size?: number }) {
  const base: any = { width: size, height: size, borderRadius: Math.round(size * 0.24), display: 'grid', placeItems: 'center', fontSize: Math.round(size * 0.44), fontWeight: 800, flex: '0 0 auto' };
  const txt = Math.round(size * 0.36);
  if (logo === 'card') return <span style={{ ...base, background: 'linear-gradient(135deg,#1a1f71,#2563eb)', color: '#fff' }}>💳</span>;
  if (logo === 'usdt') return <span style={{ ...base, background: '#26a17b', color: '#fff' }}>₮</span>;
  if (logo === 'bank') return <span style={{ ...base, background: '#334155', color: '#fff' }}>🏦</span>;
  if (logo === 'local') return <span style={{ ...base, background: '#7c3aed', color: '#fff' }}>📲</span>;
  if (logo === 'ovadot') return <span style={{ ...base, background: '#0ea5e9', color: '#fff' }}>👛</span>;
  // local Iraqi/Syrian manual methods — branded colour badges
  if (logo === 'qicard') return <span style={{ ...base, background: '#00a651', color: '#fff', fontSize: txt }}>Qi</span>;
  if (logo === 'zaincash') return <span style={{ ...base, background: '#6a1b9a', color: '#fff', fontSize: txt }}>ZC</span>;
  if (logo === 'shamcash') return <span style={{ ...base, background: '#1565c0', color: '#fff', fontSize: txt }}>Sh</span>;
  if (logo === 'fastpay') return <span style={{ ...base, background: '#f57c00', color: '#fff', fontSize: txt }}>FP</span>;
  return <span style={base}>$</span>;
}

const QUICK = [50, 100, 250, 500, 1000];

export default function DepositWizard({ onClose }: { onClose: () => void }) {
  const mobile = useIsMobile();
  const [step, setStep] = useState(0);
  const [accounts, setAccounts] = useState<any[]>([]);
  const [login, setLogin] = useState('');
  const [amount, setAmount] = useState('');
  const [methods, setMethods] = useState<any[]>([]);
  const [method, setMethod] = useState<any>(null);
  const [result, setResult] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [proofName, setProofName] = useState('');
  const [bonus, setBonus] = useState<any>(null);
  // manual company-card flow (Qi / Zain Cash / Fastpay / Sham Cash): show an ACTIVE company card
  // to transfer to, then upload the receipt for AI check + back-office approval.
  const [card, setCard] = useState<any>(null);
  const [txid, setTxid] = useState('');
  const [walletId, setWalletId] = useState('');
  const [proofImg, setProofImg] = useState('');
  const [manualDone, setManualDone] = useState<any>(null);
  const [processing, setProcessing] = useState(false);   // OCR/verification in flight on the final step
  const [myReqs, setMyReqs] = useState<any[]>([]);   // the client's own deposit requests + status
  const [localInput, setLocalInput] = useState('');  // amount typed in LOCAL currency (IQD/SYP)
  const amountRef = useRef<HTMLDivElement>(null);    // auto-scroll target when a method is chosen
  const pickMethod = (m: any) => {
    setMethod(m); setLocalInput(''); setAmount('');
    // scroll the amount box into view so the client goes straight to entering the amount
    setTimeout(() => amountRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 90);
  };
  const isCardMethod = !!method && method.type === 'manual' && /qi|zain|sham|fast\s*pay/i.test(`${method.id} ${method.name}`);
  // local-currency deposit? (Qi/Zain/Fastpay -> IQD, Sham -> SYP). Client enters local, we convert to USD.
  const curr: string = method?.currency || 'USD';
  const isLocal = curr !== 'USD';
  const rate = Number(method?.rate) || 0;   // local units per $1
  // selected account type -> bonus only applies to Standard accounts. Eligibility is
  // decided by the backend from the GROUP (any STD* group = Standard); we trust its
  // is_standard flag and fall back to the label text only if the flag is absent.
  const selAcct = accounts.find(a => String(a.login) === String(login));
  const acctType = (selAcct?.type || '').trim();
  const isStandard = selAcct
    ? (selAcct.is_standard ?? /standard/i.test(acctType))
    : true;

  const loadReqs = () => apiGet('/portal/money-requests').then((r: any) => setMyReqs((r?.requests || []).filter((x: any) => x.kind === 'deposit'))).catch(() => {});
  useEffect(() => {
    apiGet('/portal/accounts').then((a: any) => {
      // archived accounts are view-only — never a deposit target
      const act = (a?.accounts || []).filter((x: any) => !x.archived);
      setAccounts(act); if (act[0]) setLogin(String(act[0].login));
    });
    apiGet('/portal/deposit/methods').then((m: any) => setMethods(m?.methods || []));
    loadReqs();
  }, []);
  // refresh the status list whenever a deposit is submitted (last step shows the result)
  useEffect(() => { if (step === 2) loadReqs(); }, [step]);   // eslint-disable-line

  // client-facing deposit status → colour + label
  const DEP_STATUS: Record<string, { c: string; label: string }> = {
    pending: { c: '#E8B84B', label: 'Pending' }, pending_simulation: { c: '#E8B84B', label: 'Pending' },
    pending_payment: { c: '#E8B84B', label: 'Awaiting payment' }, pending_admin_review: { c: '#E8B84B', label: 'In review' },
    processing: { c: '#4aa3ff', label: 'Processing' }, review: { c: '#E8B84B', label: 'In review' },
    approved: { c: '#34D399', label: 'Approved' }, completed: { c: '#34D399', label: 'Approved' },
    rejected: { c: '#F2667A', label: 'Rejected' },
  };

  // USD amount (canonical, sent to the backend). For local methods it's derived from the local input.
  const amt = isLocal ? (rate ? (parseFloat(localInput) || 0) / rate : 0) : (parseFloat(amount) || 0);
  const localNum = parseFloat(localInput) || 0;

  // live bonus preview — "you will get +$X" before the client commits
  useEffect(() => {
    if (amt <= 0) { setBonus(null); return; }
    const t = setTimeout(() => {
      apiPost('/portal/bonus/preview-deposit', { amount: amt, login: login ? Number(login) : null })
        .then(setBonus).catch(() => setBonus(null));
    }, 250);
    return () => clearTimeout(t);
  }, [amt, login]);
  const bonusAmt = bonus?.bonus || 0;

  const confirm = async () => {
    setBusy(true);
    try {
      const res: any = await apiPost('/portal/deposit/initiate', { login: Number(login), amount: amt, method: method.id });
      setResult(res); setStep(2);
    } catch (e) { /* ignore */ }
    finally { setBusy(false); }
  };

  // fetch ONE active company card for the chosen manual method (rotates by working hours + limits)
  useEffect(() => {
    if (!isCardMethod) { setCard(null); return; }
    const t = setTimeout(() => {
      apiGet(`/portal/deposit/card?method=${encodeURIComponent(method.id)}&amount=${amt}`).then(setCard).catch(() => setCard(null));
    }, 300);
    return () => clearTimeout(t);
  }, [isCardMethod, method, amt]);

  const pickProof = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]; if (!f) return;
    setProofName(f.name);
    if (f.size > 7 * 1024 * 1024) { setProofName('Image over 7MB — use a smaller photo'); return; }
    const r = new FileReader(); r.onload = () => setProofImg(String(r.result || '')); r.readAsDataURL(f);
  };

  const submitManual = async () => {
    // go straight to the last step and show PROCESSING while the receipt is OCR'd + checked
    setBusy(true); setProcessing(true); setManualDone(null); setResult({ mode: 'manual' }); setStep(2);
    try {
      const res: any = await apiPost('/portal/deposit/manual', {
        login: Number(login), amount: amt, method: method.id, card_id: card?.card_id,
        txid: txid.trim(), wallet_id: walletId.trim(), image: proofImg,
        // local-currency context so the back-office can match the receipt (in IQD/SYP) to the USD credit
        currency: curr, local_amount: isLocal ? localNum : undefined, fx_rate: isLocal ? rate : undefined,
      });
      setManualDone(res);
    } catch (e: any) { setManualDone({ ok: false, message: e?.message || 'Submission failed — please try again.' }); }
    finally { setProcessing(false); setBusy(false); }
  };

  return (
    <div style={{ padding: mobile ? '8px 14px' : '8px 0' }}>
      <Wizard
        steps={STEPS} current={step}
        onBack={step === 0 ? onClose : step < 2 ? () => setStep(step - 1) : undefined}
        onNext={
          step === 0 ? (method && amt > 0 && login ? () => setStep(1) : undefined) :
          step === 1 ? (isCardMethod ? submitManual : confirm) : undefined
        }
        nextLabel={step === 1 ? (busy ? 'Processing…' : (isCardMethod ? 'Submit deposit' : 'Confirm deposit')) : 'Continue'}
        nextDisabled={(step === 0 && (!method || !amt || !login))
          || (step === 1 && isCardMethod && (!card?.available || !proofImg)) || busy}
        hideNav={step === 2}
      >
        {step === 0 && (
          <>
            {/* 1 — choose the payment method (square logo tiles) */}
            <div style={LABEL}>Payment method</div>
            <div className="pay-methods" style={{ marginBottom: method ? 22 : 0 }}>
              {methods.map(m => {
                const active = method?.id === m.id;
                return (
                  <button key={m.id} onClick={() => pickMethod(m)} style={{
                    position: 'relative', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 8,
                    aspectRatio: '1 / 1', padding: '10px 6px', borderRadius: 14, cursor: 'pointer', fontFamily: 'inherit', textAlign: 'center', transition: 'all .15s',
                    background: active ? 'rgba(58,210,159,0.12)' : TH.panel,
                    border: `1.5px solid ${active ? TH.accent : TH.border}`, color: TH.text,
                    boxShadow: active ? `0 0 0 3px rgba(58,210,159,0.12)` : 'none',
                  }}>
                    <MethodLogo logo={m.logo} size={mobile ? 40 : 46} />
                    <span style={{ fontSize: 11.5, fontWeight: 700, lineHeight: 1.15, maxWidth: '100%', wordBreak: 'break-word' }}>{m.name}</span>
                    {active && <span style={{ position: 'absolute', top: 6, right: 7, color: TH.accent, fontSize: 14 }}>✓</span>}
                    {m.type === 'api' && <span title="Instant" style={{ position: 'absolute', top: 8, left: 8, width: 7, height: 7, borderRadius: 99, background: TH.accent }} />}
                  </button>
                );
              })}
            </div>

            {/* 2 — account + amount (appear once a method is chosen; auto-scrolled into view) */}
            {method && (
              <div ref={amountRef}>
                <div style={LABEL}>Deposit to account</div>
                <select value={login} onChange={e => setLogin(e.target.value)} style={mobile ? { ...selStyle, fontSize: 16 } : selStyle}>
                  {accounts.map((a, i) => <option key={i} value={a.login}>#{a.login}{a.type ? ` · ${a.type}` : ''}{a.balance != null ? ` · ${fmtMoney(a.balance)}` : ''}</option>)}
                </select>

                <div style={{ ...LABEL, margin: '18px 0 8px' }}>Amount{isLocal ? ` (${curr})` : ' (USD)'}</div>
                <div style={{ display: 'flex', alignItems: 'center', background: TH.panel, border: `1.5px solid ${TH.border}`, borderRadius: TH.radius, padding: '4px 16px' }}>
                  <span style={{ fontSize: isLocal ? 18 : 26, fontWeight: 800, color: TH.muted }}>{isLocal ? curr : '$'}</span>
                  {isLocal
                    ? <input value={localInput ? Number(localInput).toLocaleString('en-US') : ''} onChange={e => setLocalInput(e.target.value.replace(/[^0-9]/g, ''))} placeholder="0" inputMode="numeric" style={mobile ? { ...AMT_INPUT, fontSize: 24 } : AMT_INPUT} />
                    : <input value={amount} onChange={e => setAmount(e.target.value.replace(/[^0-9.]/g, ''))} placeholder="0.00" inputMode="decimal" style={mobile ? { ...AMT_INPUT, fontSize: 26 } : AMT_INPUT} />}
                </div>
                {isLocal && (
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 8, fontSize: 12.5 }}>
                    <span style={{ color: TH.muted }}>Rate: $1 = {rate ? rate.toLocaleString() : '—'} {curr}</span>
                    <span style={{ color: TH.text, fontWeight: 800 }}>≈ {fmtMoney(amt)} USD</span>
                  </div>
                )}
                {!isLocal && (
                  <div style={{ display: 'flex', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
                    {QUICK.map(q => <button key={q} onClick={() => setAmount(String(q))} style={QUICK_BTN}>${q}</button>)}
                  </div>
                )}

                {/* bonus — Standard accounts only */}
                {amt > 0 && (isStandard ? (
                  bonus && !bonus.blocked && bonusAmt > 0 ? (
                    <div style={BONUS_BOX}>
                      <div style={{ fontSize: 13.5, fontWeight: 800, color: TH.gold }}>🎁 You'll receive +{fmtMoney(bonusAmt)} bonus</div>
                      {(bonus.lines || []).map((ln: any, i: number) => (
                        <div key={i} style={{ fontSize: 11.5, color: TH.muted, marginTop: 3 }}>{ln.special ? '✨ ' : '• '}{ln.label} → +{fmtMoney(ln.bonus)}</div>
                      ))}
                      <div style={{ fontSize: 11.5, color: TH.text, marginTop: 6, fontWeight: 700 }}>Total bonus credit: +{fmtMoney(bonusAmt)}</div>
                    </div>
                  ) : bonus && !bonus.blocked ? (
                    <div style={{ marginTop: 14, fontSize: 11.5, color: TH.muted }}>No deposit bonus on this amount (cap reached or not eligible).</div>
                  ) : null
                ) : (
                  <div style={{ marginTop: 16, background: 'rgba(150,160,180,0.08)', border: `1px solid ${TH.border}`, borderRadius: TH.radius, padding: '11px 14px', fontSize: 12, color: TH.muted }}>
                    ℹ️ Deposit bonus is not applied to <b style={{ color: TH.text }}>{selAcct?.base_type || acctType || 'this'}</b> accounts — the bonus is available on <b style={{ color: TH.text }}>Standard</b> accounts only.
                  </div>
                ))}
              </div>
            )}

            {/* recent deposits — shown during method selection only, so it never buries the CTA once
                the client is entering an amount */}
            {!method && myReqs.length > 0 && (
              <div style={{ marginTop: 24 }}>
                <div style={LABEL}>Your recent deposits</div>
                <div style={{ background: TH.panel, border: `1px solid ${TH.border}`, borderRadius: TH.radius, overflow: 'hidden' }}>
                  {myReqs.slice(0, 5).map((r, i) => {
                    const s = DEP_STATUS[(r.status || '').toLowerCase()] || { c: TH.muted, label: r.status };
                    return (
                      <div key={r.id} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 14px', borderBottom: i < Math.min(myReqs.length, 5) - 1 ? `1px solid ${TH.border}` : 'none' }}>
                        <div>
                          <div style={{ fontSize: 13.5, fontWeight: 700, color: TH.text }}>{fmtMoney(r.amount)}</div>
                          <div style={{ fontSize: 11, color: TH.muted }}>{r.method}{r.date ? ` · ${r.date}` : ''}</div>
                        </div>
                        <span style={{ fontSize: 10.5, fontWeight: 700, color: s.c, background: s.c + '1f', padding: '4px 10px', borderRadius: 6 }}>{s.label}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </>
        )}

        {/* CONFIRM — a clearly different (accent) header so it's obvious this is a new step; the
            chosen method is locked here (go Back to change it) */}
        {step === 1 && method && (
          <>
            <div style={{ fontSize: 12, fontWeight: 800, letterSpacing: '0.06em', color: TH.accent, textTransform: 'uppercase', marginBottom: 8 }}>Step 2 · Confirm &amp; send your payment</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '13px 14px', background: 'rgba(58,210,159,0.08)', border: `1.5px solid ${TH.accent}`, borderRadius: TH.radius, marginBottom: 16 }}>
              <MethodLogo logo={method.logo} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 14, fontWeight: 800, color: TH.text }}>{method.name}</div>
                <div style={{ fontSize: 11.5, color: TH.muted }}>Depositing {fmtMoney(amt)}{isLocal ? ` · ${localNum.toLocaleString()} ${curr}` : ''} → account #{login}</div>
              </div>
              <span title="Locked — go Back to change the method" style={{ fontSize: 12, fontWeight: 700, color: TH.accent, background: 'rgba(58,210,159,0.14)', padding: '3px 8px', borderRadius: 6 }}>🔒 Locked</span>
            </div>
          </>
        )}

        {/* MANUAL COMPANY CARD (Qi / Zain / Fastpay / Sham): transfer to an active company card + upload proof */}
        {step === 1 && method && isCardMethod && (
          <div>
            {card == null ? <div style={{ color: TH.muted, fontSize: 13, textAlign: 'center', padding: 20 }}>Finding an available {method.name}…</div>
              : !card.available ? <div style={{ color: TH.gold, fontSize: 13, textAlign: 'center', padding: 20 }}>{card.message}</div>
              : (
              <>
                <div style={{ fontSize: 13, fontWeight: 800, color: TH.text, marginBottom: 8 }}>Step 1 — Transfer <span style={{ color: TH.accent }}>{isLocal ? `${localNum.toLocaleString()} ${curr}` : fmtMoney(amt)}</span> from your {method.name} to:</div>
                {card.on_shift === false && <div style={{ fontSize: 11, color: TH.gold, marginBottom: 8 }}>ℹ️ Outside working hours — review may take a little longer.</div>}
                <div style={{ background: TH.panel, border: `1px solid ${TH.border}`, borderRadius: TH.radius, padding: 16, marginBottom: 14 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                      <div style={{ fontSize: 10, color: TH.muted, textTransform: 'uppercase', letterSpacing: 1 }}>{method.name} account number</div>
                      <div style={{ fontFamily: 'monospace', fontSize: 20, fontWeight: 800, color: TH.text, letterSpacing: 1 }}>{card.account_number || '—'}</div>
                      {card.card_name ? <div style={{ fontSize: 11.5, color: TH.muted, marginTop: 3 }}>Name on card: <b>{card.card_name}</b></div> : null}
                    </div>
                    {card.account_number && <button onClick={() => { try { navigator.clipboard.writeText(card.account_number); } catch {} }} style={{ ...ghostBtn, padding: '6px 12px', fontSize: 12 }}>Copy</button>}
                  </div>
                </div>

                <input value={walletId} onChange={e => setWalletId(e.target.value)} placeholder="Your wallet / card number (sender) — optional" style={{ ...selStyle, marginBottom: 14 }} />

                <div style={{ fontSize: 13, fontWeight: 800, color: TH.text, margin: '6px 0 8px' }}>Step 2 — Upload your transfer screenshot</div>
                <label style={{ display: 'block', border: `1.5px dashed ${proofImg ? TH.accent : TH.border2}`, borderRadius: TH.radius, padding: 22, textAlign: 'center', cursor: 'pointer', background: TH.panel }}>
                  <input type="file" accept="image/*" style={{ display: 'none' }} onChange={pickProof} />
                  <div style={{ fontSize: 24, marginBottom: 6 }}>{proofImg ? '✓' : '📎'}</div>
                  <div style={{ fontSize: 13, color: proofImg ? TH.accent : TH.muted }}>{proofName || 'Tap to upload screenshot / receipt'}</div>
                </label>
                {proofImg && <img src={proofImg} alt="proof" style={{ marginTop: 10, maxWidth: '100%', maxHeight: 180, borderRadius: 8, border: `1px solid ${TH.border}` }} />}
                <div style={{ fontSize: 11, color: TH.muted, marginTop: 10 }}>Our team reviews and approves every manual deposit. Fake or altered receipts are detected automatically.</div>
              </>
            )}
          </div>
        )}

        {step === 1 && method && !isCardMethod && (
          <div>
            <div style={{ background: TH.panel, border: `1px solid ${TH.border}`, borderRadius: TH.radius, padding: 20, marginBottom: 14 }}>
              <div style={{ textAlign: 'center', marginBottom: 16 }}>
                <div style={{ fontSize: 12, color: TH.muted }}>You're depositing</div>
                <div style={{ fontSize: 40, fontWeight: 900, color: TH.text }}>{fmtMoney(amt)}</div>
              </div>
              {([['Account', `#${login}`], ['Method', method.name], ['Fee', method.fee || '0%'],
                 ...(bonusAmt > 0 ? [['🎁 Bonus', `+${fmtMoney(bonusAmt)}`]] : []),
                 ['You receive', fmtMoney(amt + bonusAmt)]] as [string, string][]).map(([k, v], i, arr) => (
                <div key={k} style={{ display: 'flex', justifyContent: 'space-between', padding: '10px 0', borderBottom: i < arr.length - 1 ? `1px solid ${TH.border}` : 'none' }}>
                  <span style={{ fontSize: 13, color: TH.muted }}>{k}</span><span style={{ fontSize: 13, fontWeight: 700 }}>{v}</span>
                </div>
              ))}
            </div>
            <div style={{ fontSize: 11.5, color: TH.muted, textAlign: 'center' }}>By confirming you agree to TNFX's deposit terms.</div>
          </div>
        )}

        {step === 2 && result && (
          <div>
            {result.mode === 'manual' ? (
              processing ? (
                <div style={{ textAlign: 'center', padding: '24px 0' }}>
                  <div style={{ width: 56, height: 56, borderRadius: 99, border: `3px solid ${TH.accent}`, borderTopColor: 'transparent', margin: '0 auto 18px', animation: 'spin 0.8s linear infinite' }} />
                  <div style={{ fontSize: 17, fontWeight: 800, marginBottom: 6 }}>Processing…</div>
                  <div style={{ fontSize: 13, color: TH.muted, lineHeight: 1.6 }}>Reading your receipt and checking the transaction details. This takes a few seconds — please don't close this window.</div>
                </div>
              ) : (() => {
                const msg = manualDone?.message || "We couldn't read this receipt — pop in a clear screenshot.";
                const isDup = manualDone?.case === 'duplicate';
                const isPending = isDup && manualDone?.dup === 'pending';   // your OWN receipt still in review → just wait
                const isDupApproved = isDup && manualDone?.dup === 'approved'; // your OWN receipt already funded you
                const success = manualDone?.ok && !manualDone?.warning;
                const justClose = manualDone?.ok || isPending || isDupApproved;  // success / warning / your-own-duplicate → single button
                // colour + emoji + headline per outcome (short, fun, on-brand)
                const th = success
                  ? { c: '#3ad29f', emoji: '🎉', title: 'Woohoo — receipt looks great!' }
                  : manualDone?.warning
                  ? { c: '#E8B84B', emoji: '🫡', title: 'Submitted — one quick heads-up' }
                  : manualDone?.case === 'fake'
                  ? { c: '#F2667A', emoji: '🕵️', title: "That doesn't look genuine" }
                  : isPending
                  ? { c: '#5a9bff', emoji: '⏳', title: "You're already in the queue!" }
                  : isDupApproved
                  ? { c: '#3ad29f', emoji: '✅', title: 'Already deposited with this receipt!' }
                  : isDup
                  ? { c: '#3ad29f', emoji: '✅', title: 'This receipt was already used' }
                  : { c: '#E8B84B', emoji: '🔍', title: "Couldn't quite read that" };
                const tint = (a: number) => th.c + Math.round(a * 255).toString(16).padStart(2, '0');
                return (
                  <div style={{ padding: '2px 0' }}>
                    <div style={{ textAlign: 'center', marginBottom: 14 }}>
                      <div style={{ width: 72, height: 72, borderRadius: 99, background: tint(0.14), display: 'grid', placeItems: 'center', fontSize: 38, margin: '0 auto 12px', border: `1px solid ${tint(0.4)}`, boxShadow: `0 8px 26px ${tint(0.22)}` }}>{th.emoji}</div>
                      <div style={{ fontSize: 19, fontWeight: 900, color: th.c }}>{th.title}</div>
                    </div>
                    <div style={{ background: tint(0.12), border: `1px solid ${tint(0.4)}`, borderRadius: TH.radius, padding: '13px 16px', fontSize: 13.5, color: TH.text, lineHeight: 1.65, textAlign: 'center', fontWeight: 600 }}>
                      {success
                        ? <>Your <b style={{ color: th.c }}>{fmtMoney(amt)}</b> deposit is with our team — you'll get a ping the moment it's approved. ✨</>
                        : msg}
                    </div>
                    {justClose ? (
                      <button onClick={onClose} style={{ ...primaryBtn, width: '100%', marginTop: 18 }}>{isPending ? "OK, I'll wait 🙌" : success ? 'Sweet — done! 🚀' : 'Got it 👍'}</button>
                    ) : (
                      <>
                        <div style={{ fontSize: 12.5, color: TH.muted, margin: '15px 0 10px', lineHeight: 1.6, textAlign: 'center' }}>Nothing was saved — just upload a <b style={{ color: TH.text }}>clear</b> shot with the <b style={{ color: TH.text }}>Transaction ID + date</b> visible. 📸</div>
                        <label style={{ display: 'block', border: `1.5px dashed ${proofImg ? th.c : TH.border2}`, borderRadius: TH.radius, padding: 22, textAlign: 'center', cursor: 'pointer', background: TH.panel }}>
                          <input type="file" accept="image/*" style={{ display: 'none' }} onChange={pickProof} />
                          <div style={{ fontSize: 24, marginBottom: 6 }}>{proofImg ? '✓' : '📎'}</div>
                          <div style={{ fontSize: 13, color: proofImg ? th.c : TH.muted }}>{proofName || 'Tap to upload a new screenshot'}</div>
                        </label>
                        {proofImg && <img src={proofImg} alt="proof" style={{ marginTop: 10, maxWidth: '100%', maxHeight: 180, borderRadius: 8, border: `1px solid ${TH.border}` }} />}
                        <button onClick={submitManual} disabled={!proofImg || busy} style={{ ...primaryBtn, width: '100%', marginTop: 14, opacity: (!proofImg || busy) ? 0.5 : 1, cursor: (!proofImg || busy) ? 'not-allowed' : 'pointer' }}>{busy ? 'Processing…' : 'Try again 🎯'}</button>
                        <button onClick={onClose} style={{ ...ghostBtn, width: '100%', marginTop: 8 }}>Cancel</button>
                      </>
                    )}
                  </div>
                );
              })()
            ) : result.mode === 'redirect' ? (
              <div style={{ textAlign: 'center' }}>
                <div style={{ width: 56, height: 56, borderRadius: 99, border: `3px solid ${TH.accent}`, borderTopColor: 'transparent', margin: '0 auto 18px', animation: 'spin 0.8s linear infinite' }} />
                <div style={{ fontSize: 16, fontWeight: 800, marginBottom: 6 }}>Redirecting to secure payment…</div>
                <div style={{ fontSize: 13, color: TH.muted, marginBottom: 18 }}>You'll complete your {fmtMoney(amt)} card payment on our payment partner's secure page.</div>
                <a href={result.redirect_url} target="_blank" rel="noreferrer" style={{ ...primaryBtn, display: 'inline-block', textDecoration: 'none' }}>Open payment page →</a>
                <div style={{ fontSize: 11, color: TH.gold, marginTop: 14 }}>Demo: real gateway redirect happens here once API keys are connected.</div>
              </div>
            ) : (
              <div>
                <div style={{ background: 'rgba(58,210,159,0.08)', border: `1px solid rgba(58,210,159,0.25)`, borderRadius: TH.radiusSm, padding: '12px 14px', fontSize: 12.5, color: TH.accent, marginBottom: 16 }}>
                  ✓ Send exactly <b>{fmtMoney(amt)}</b> using the details below, then upload your proof.
                </div>
                <div style={{ background: TH.panel, border: `1px solid ${TH.border}`, borderRadius: TH.radius, padding: 18, marginBottom: 16 }}>
                  <div style={{ fontSize: 11, letterSpacing: '0.1em', textTransform: 'uppercase', color: TH.muted, fontWeight: 700, marginBottom: 12 }}>{method.name} details</div>
                  {Object.entries(method.details || {}).map(([k, v]: any, i, arr) => (
                    <div key={k} style={{ display: 'flex', justifyContent: 'space-between', gap: 12, padding: '9px 0', borderBottom: i < arr.length - 1 ? `1px solid ${TH.border}` : 'none' }}>
                      <span style={{ fontSize: 12, color: TH.muted, flex: '0 0 auto' }}>{k}</span>
                      <span style={{ fontSize: 12.5, fontWeight: 700, fontFamily: 'monospace', textAlign: 'right', wordBreak: 'break-all' }}>{v}</span>
                    </div>
                  ))}
                </div>
                <div style={{ fontSize: 11, letterSpacing: '0.1em', textTransform: 'uppercase', color: TH.muted, fontWeight: 700, marginBottom: 8 }}>Upload payment proof</div>
                <label style={{ display: 'block', border: `1.5px dashed ${proofName ? TH.accent : TH.border2}`, borderRadius: TH.radius, padding: 24, textAlign: 'center', cursor: 'pointer', background: TH.panel }}>
                  <input type="file" accept="image/*,application/pdf" style={{ display: 'none' }} onChange={e => setProofName(e.target.files?.[0]?.name || '')} />
                  <div style={{ fontSize: 26, marginBottom: 6 }}>{proofName ? '✓' : '📎'}</div>
                  <div style={{ fontSize: 13, color: proofName ? TH.accent : TH.muted }}>{proofName || 'Tap to upload screenshot / receipt'}</div>
                </label>
                <button onClick={onClose} disabled={!proofName} style={{ ...primaryBtn, width: '100%', marginTop: 16, opacity: proofName ? 1 : 0.5, cursor: proofName ? 'pointer' : 'not-allowed' }}>Submit deposit</button>
              </div>
            )}
            <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
          </div>
        )}
      </Wizard>
    </div>
  );
}

const selStyle: any = { width: '100%', padding: '13px 14px', borderRadius: TH.radiusSm, background: TH.panel, border: `1px solid ${TH.border2}`, color: TH.text, fontSize: 14, outline: 'none', fontFamily: 'inherit' };
const LABEL: any = { fontSize: 11, letterSpacing: '0.12em', textTransform: 'uppercase', color: TH.muted, fontWeight: 700, marginBottom: 8 };
const AMT_INPUT: any = { flex: 1, minWidth: 0, background: 'transparent', border: 'none', outline: 'none', color: TH.text, fontSize: 28, fontWeight: 800, padding: '12px 8px', fontFamily: 'inherit' };
const QUICK_BTN: any = { padding: '8px 16px', borderRadius: 8, background: TH.panel, border: `1px solid ${TH.border}`, color: TH.text, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' };
const BONUS_BOX: any = { marginTop: 16, background: 'rgba(232,184,75,0.10)', border: '1px solid rgba(232,184,75,0.35)', borderRadius: TH.radius, padding: '12px 14px' };

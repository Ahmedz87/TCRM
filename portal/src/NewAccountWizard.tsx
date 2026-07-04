import React, { useState } from 'react';
import { apiPost } from './api';
import { TH } from './theme';
import { Wizard, OptionCard, primaryBtn, ghostBtn } from './Wizard';

function useIsMobile(bp=760){const [m,setM]=React.useState(()=>typeof window!=='undefined'&&window.innerWidth<=bp);React.useEffect(()=>{const o=()=>setM(window.innerWidth<=bp);window.addEventListener('resize',o);return()=>window.removeEventListener('resize',o);},[bp]);return m;}

const STEPS = ['Choose platform', 'Account model', 'Account type', 'Leverage', 'Your new account'];
const TYPES = [
  { id: 'Standard', sub: 'Balanced spreads, no commission', icon: '◆' },
  { id: 'Zero', sub: 'Raw spreads + low commission', icon: '◇' },
  { id: 'Cent', sub: 'Micro lots, great for beginners', icon: '¢' },
  { id: 'VIP', sub: 'Tightest spreads, priority service', icon: '★' },
];
const LEVERAGES = [50, 100, 200, 400, 500, 1000];

const DOWNLOADS = [
  { label: 'Windows', icon: '🖥️', url: 'https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe' },
  { label: 'macOS', icon: '🍎', url: 'https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/MetaTrader5.dmg' },
  { label: 'iOS', icon: '📱', url: 'https://apps.apple.com/app/metatrader-5/id413251709' },
  { label: 'Android', icon: '🤖', url: 'https://play.google.com/store/apps/details?id=net.metaquotes.metatrader5' },
];

export default function NewAccountWizard({ onClose, onCreated, kycVerified = true, kycStatus = '', onVerifyKyc }:
  { onClose: () => void; onCreated?: () => void; kycVerified?: boolean; kycStatus?: string; onVerifyKyc?: () => void }) {
  const mobile = useIsMobile();
  const [step, setStep] = useState(0);
  const [platform, setPlatform] = useState('MT5');
  const [islamic, setIslamic] = useState<boolean | null>(null);
  const [accType, setAccType] = useState('Standard');
  const [leverage, setLeverage] = useState(500);
  const [result, setResult] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState('');
  const [err, setErr] = useState('');

  const submit = async () => {
    setBusy(true); setErr('');
    try {
      const res: any = await apiPost('/portal/accounts/create', { platform, islamic: !!islamic, account_type: accType, leverage });
      // backend hard-gate (defense-in-depth): if KYC isn't verified it refuses here too
      if (res?.ok === false && res?.error === 'kyc_required') { onClose(); return; }
      if (res?.account) { setResult(res.account); setStep(4); onCreated && onCreated(); }
      else if (res?.ok === false) { setErr(res.message || 'We couldn\'t open the account right now — please try again.'); }
    } catch (e) { setErr('Something went wrong — please try again.'); }
    finally { setBusy(false); }
  };

  const copy = (label: string, val: string) => {
    try { navigator.clipboard.writeText(val); setCopied(label); setTimeout(() => setCopied(''), 1200); } catch {}
  };

  const downloads = platform === 'MT5' ? DOWNLOADS : DOWNLOADS.map(d =>
    d.label === 'Windows' ? { ...d, url: 'https://download.mql5.com/cdn/web/metaquotes.software.corp/mt4/mt4setup.exe' } :
    d.label === 'iOS' ? { ...d, url: 'https://apps.apple.com/app/metatrader-4/id496212596' } :
    d.label === 'Android' ? { ...d, url: 'https://play.google.com/store/apps/details?id=net.metaquotes.metatrader4' } : d);

  // KYC gate: a client must be verified before opening a new trading account. We show a
  // popup-style message immediately (not the steps). Under-review vs not-submitted differ.
  if (!kycVerified) {
    const underReview = ['pending_review', 'in_review', 'submitted', 'under_review'].includes((kycStatus || '').toLowerCase());
    return (
      <div style={{ textAlign: 'center', padding: '12px 4px', maxWidth: 420, margin: '0 auto' }}>
        <div style={{ width: 64, height: 64, borderRadius: 99, background: underReview ? 'rgba(232,184,75,0.14)' : 'rgba(240,85,106,0.12)', display: 'grid', placeItems: 'center', margin: '0 auto 16px', fontSize: 30 }}>{underReview ? '⏳' : '🪪'}</div>
        <div style={{ fontSize: 19, fontWeight: 800, marginBottom: 8, color: TH.text }}>
          {underReview ? 'Your account is under review' : 'Verify your identity first'}
        </div>
        <div style={{ fontSize: 13.5, color: TH.muted, lineHeight: 1.6, marginBottom: 22 }}>
          {underReview
            ? "We're reviewing your documents. You'll be able to open new trading accounts as soon as your account is verified — this usually only takes a few minutes."
            : 'You need to complete your identity verification (KYC) before you can open a new trading account.'}
        </div>
        {!underReview && onVerifyKyc && <button onClick={onVerifyKyc} style={{ ...primaryBtn, width: '100%', marginBottom: 10 }}>Verify now</button>}
        <button onClick={onClose} style={{ ...ghostBtn, width: '100%' }}>Close</button>
      </div>
    );
  }

  return (
    <div style={{ padding: '8px 0' }}>
      <Wizard
        steps={STEPS} current={step}
        onBack={step > 0 && step < 4 ? () => setStep(step - 1) : (step === 0 ? onClose : undefined)}
        onNext={step < 4 ? (
          step === 0 ? () => setStep(1) :
          step === 1 ? (islamic === null ? undefined : () => setStep(2)) :
          step === 2 ? () => setStep(3) :
          step === 3 ? submit : undefined
        ) : undefined}
        nextLabel={step === 0 ? 'Continue' : step === 3 ? (busy ? 'Creating…' : 'Create account') : 'Continue'}
        nextDisabled={(step === 1 && islamic === null) || busy}
        hideNav={step === 4}
      >
        {step === 0 && (
          <>
            <OptionCard active={platform === 'MT5'} onClick={() => setPlatform('MT5')} icon="5" title="MetaTrader 5" sub="Latest platform · more order types, faster" />
            <OptionCard active={platform === 'MT4'} onClick={() => setPlatform('MT4')} icon="4" title="MetaTrader 4" sub="Classic · widely supported, EA-friendly" />
          </>
        )}
        {step === 1 && (
          <>
            <OptionCard active={islamic === false} onClick={() => setIslamic(false)} icon="◷" title="Standard account" sub="Regular swap charges on overnight positions" />
            <OptionCard active={islamic === true} onClick={() => setIslamic(true)} icon="☾" title="Islamic (swap-free)" sub="No overnight swap — Shariah-compliant" />
          </>
        )}
        {step === 2 && (
          <>
            {TYPES.map(t => (
              <OptionCard key={t.id} active={accType === t.id} onClick={() => setAccType(t.id)} icon={t.icon} title={t.id} sub={t.sub} />
            ))}
          </>
        )}
        {step === 3 && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0,1fr))', gap: 10 }}>
            {LEVERAGES.map(l => (
              <button key={l} onClick={() => setLeverage(l)} style={{
                padding: mobile ? '16px 0' : '20px 0', borderRadius: TH.radius, cursor: 'pointer', fontFamily: 'inherit',
                background: leverage === l ? 'rgba(58,210,159,0.10)' : TH.panel,
                border: `1.5px solid ${leverage === l ? TH.accent : TH.border}`,
                color: leverage === l ? TH.accent : TH.text, fontSize: 18, fontWeight: 800,
              }}>1:{l}</button>
            ))}
          </div>
        )}
        {err && step !== 4 && (
          <div style={{ marginTop: 14, fontSize: 12.5, color: TH.neg, background: 'rgba(240,85,106,0.08)', border: '1px solid rgba(240,85,106,0.28)', borderRadius: 8, padding: '9px 12px' }}>{err}</div>
        )}
        {step === 4 && result && (
          <div style={{ textAlign: 'center' }}>
            <div style={{ width: 60, height: 60, borderRadius: 99, background: 'rgba(58,210,159,0.14)', display: 'grid', placeItems: 'center', margin: '0 auto 14px', fontSize: 28 }}>✓</div>
            <div style={{ fontSize: 18, fontWeight: 800, marginBottom: 4 }}>Account ready!</div>
            <div style={{ fontSize: 13, color: TH.muted, marginBottom: 20 }}>{result.platform} · {result.account_type}{result.islamic ? ' · Islamic' : ''} · 1:{result.leverage}</div>

            <div style={{ background: TH.panel, border: `1px solid ${TH.border}`, borderRadius: TH.radius, padding: 18, textAlign: 'left', marginBottom: 16 }}>
              {[['Account number', String(result.login)], ['Password', result.password], ['Server', result.server]].map(([label, val]) => (
                <div key={label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, padding: '10px 0', borderBottom: label !== 'Server' ? `1px solid ${TH.border}` : 'none' }}>
                  <span style={{ fontSize: 12, color: TH.muted, flex: '0 0 auto' }}>{label}</span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
                    <span style={{ fontSize: 14, fontWeight: 700, fontFamily: 'monospace', wordBreak: 'break-all', minWidth: 0 }}>{val}</span>
                    <button onClick={() => copy(label, val)} style={{ fontSize: 11, padding: '3px 8px', borderRadius: 6, background: TH.bg2, border: `1px solid ${TH.border2}`, color: copied === label ? TH.accent : TH.muted, cursor: 'pointer', fontFamily: 'inherit', flex: '0 0 auto' }}>{copied === label ? 'Copied' : 'Copy'}</button>
                  </span>
                </div>
              ))}
            </div>

            <div style={{ background: 'rgba(232,184,75,0.08)', border: '1px solid rgba(232,184,75,0.22)', borderRadius: TH.radiusSm, padding: '10px 14px', fontSize: 12, color: TH.gold, marginBottom: 18, textAlign: 'left' }}>
              ⚠ Save your password now — for your security it won't be shown again.
            </div>

            <div style={{ fontSize: 11, letterSpacing: '0.12em', textTransform: 'uppercase', color: TH.muted, fontWeight: 700, marginBottom: 10, textAlign: 'left' }}>Download {result.platform}</div>
            <div style={{ display: 'grid', gridTemplateColumns: mobile ? 'repeat(2, minmax(0,1fr))' : 'repeat(4, 1fr)', gap: 8, marginBottom: 20 }}>
              {downloads.map(d => (
                <a key={d.label} href={d.url} target="_blank" rel="noreferrer" style={{ textDecoration: 'none', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, padding: '14px 4px', borderRadius: TH.radiusSm, background: TH.panel, border: `1px solid ${TH.border}`, color: TH.text }}>
                  <span style={{ fontSize: 20 }}>{d.icon}</span>
                  <span style={{ fontSize: 11.5, fontWeight: 600 }}>{d.label}</span>
                </a>
              ))}
            </div>

            <button onClick={onClose} style={{ ...primaryBtn, width: '100%' }}>Done</button>
          </div>
        )}
      </Wizard>
    </div>
  );
}

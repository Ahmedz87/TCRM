import React, { useState, useEffect } from 'react';
import { COUNTRIES, byIso, isoFlag, normalizeNational, validNational, e164 } from './countries';

function genPassword(): string {
  const U = 'ABCDEFGHJKLMNPQRSTUVWXYZ', L = 'abcdefghijkmnpqrstuvwxyz', D = '23456789', S = '!@#$%&*?';
  const all = U + L + D + S;
  const pick = (s: string) => s[Math.floor(Math.random() * s.length)];
  let p = pick(U) + pick(L) + pick(D) + pick(S);
  for (let i = 0; i < 8; i++) p += pick(all);
  return p.split('').sort(() => Math.random() - 0.5).join('');
}

// Public client self-registration wizard (TNFX.co "Open an account" -> /register).
// Mobile (country-code split + IP-detect + Turnstile + inline OTP) -> Email+Password
// (domain autocomplete + inline OTP) -> Details (nationality + residence, IP default) ->
// Finance -> Account -> KYC. Single-page: slide transitions are instant.
const API = '/api';
const post = (p: string, b: any) => fetch(`${API}${p}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(b) }).then(r => r.json());
const get = (p: string) => fetch(`${API}${p}`).then(r => r.json());

const EMAIL_DOMAINS = ['gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 'icloud.com', 'live.com', 'protonmail.com'];

const C = { bg: '#0b0e14', card: '#141925', card2: '#1c2231', border: '#2a3142', text: '#e8edf5', sub: '#8a93a3', accent: '#00e5a0', accent2: '#0066ff', red: '#ff5d6c' };
const inp: React.CSSProperties = { width: '100%', padding: '12px 14px', background: C.card2, border: `1px solid ${C.border}`, borderRadius: 10, color: C.text, fontSize: 14, outline: 'none', boxSizing: 'border-box' };
const btn = (bg: string): React.CSSProperties => ({ padding: '13px 18px', borderRadius: 10, border: 'none', background: bg, color: bg === C.accent ? '#06251b' : '#fff', fontSize: 14, fontWeight: 700, cursor: 'pointer' });
const lbl: React.CSSProperties = { fontSize: 12, color: C.sub, marginBottom: 6, display: 'block', fontWeight: 600 };
const STEPS = ['Mobile', 'Email', 'Details', 'Finance', 'Account', 'Verify (KYC)'];
const COUNTRY_NAMES = COUNTRIES.map(c => c.name);

export default function RegisterWizard() {
  // Desktop->mobile KYC hand-off: ?kyc=<regId> boots straight into the upload step on the phone.
  const kycReg = (() => { try { return new URLSearchParams(window.location.search).get('kyc'); } catch { return null; } })();
  const [step, setStep] = useState(kycReg ? 5 : 0);
  const [opts, setOpts] = useState<any>({ countries: [], account_types: [], leverages: [], platforms: [], doc_types: [] });
  const [states, setStates] = useState<string[]>([]);
  const [cities, setCities] = useState<string[]>([]);
  // Capture the ad attribution from the landing URL ONCE (Google Search ads land with
  // ?utm_source=google&gclid=..., Meta with fbclid) so the signup is tagged to its real source.
  const _utm = (() => {
    try {
      const q = new URLSearchParams(window.location.search);
      return {
        utm_source: q.get('utm_source') || '', utm_medium: q.get('utm_medium') || '',
        utm_campaign: q.get('utm_campaign') || '', gclid: q.get('gclid') || '', fbclid: q.get('fbclid') || '',
        ref: q.get('ref') || '',   // IB referral code (belt-and-braces; the /r/ cookie is the robust path)
      };
    } catch { return {}; }
  })();
  const [f, setF] = useState<any>({
    phone: '', dial_iso: 'IQ', phone_national: '',
    email: '', password: '', first_name: '', last_name: '', date_of_birth: '', country: '', state: '', city: '', address: '', nationality: '',
    platform: 'MT5', account_type: 'Standard', leverage: '1:500', islamic: false,
    questionnaire: { experience: '', deposit: '', source: '' },
    ..._utm,
  });
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);
  const [regId, setRegId] = useState<number | null>(kycReg ? Number(kycReg) : null);
  const [clientToken, setClientToken] = useState('');
  const [portalToken, setPortalToken] = useState('');

  useEffect(() => { get('/register/options').then(setOpts).catch(() => {}); }, []);
  // country -> states (governorates). If the country has states, the City list is driven by the State.
  useEffect(() => {
    if (!f.country) { setStates([]); setCities([]); return; }
    get(`/register/states?country=${encodeURIComponent(f.country)}`).then(d => setStates(d.states || [])).catch(() => setStates([]));
    get(`/register/cities?country=${encodeURIComponent(f.country)}`).then(d => setCities(d.cities || [])).catch(() => setCities([]));
  }, [f.country]);
  // state -> cities (countries that have governorates)
  useEffect(() => {
    if (f.country && f.state) get(`/register/cities?country=${encodeURIComponent(f.country)}&state=${encodeURIComponent(f.state)}`).then(d => setCities(d.cities || [])).catch(() => setCities([]));
  }, [f.country, f.state]);

  // detect the visitor's country by IP -> default dial code, residence & nationality
  useEffect(() => {
    fetch('https://ipapi.co/json/').then(r => r.json()).then(d => {
      const iso = d && d.country_code ? String(d.country_code).toUpperCase() : '';
      const c = byIso(iso);
      if (!c) return;
      setF((s: any) => ({ ...s,
        dial_iso: s.phone_national ? s.dial_iso : iso,
        country: s.country || c.name,
        nationality: s.nationality || c.name,
      }));
    }).catch(() => {});
  }, []);

  const up = (k: string, v: any) => setF((s: any) => ({ ...s, [k]: v }));
  const goNext = (n: number) => { setErr(''); setStep(n); };

  return (
    <div style={{ minHeight: '100vh', background: `radial-gradient(120% 70% at 50% 0%, #10182a 0%, ${C.bg} 60%)`, color: C.text, fontFamily: 'system-ui, sans-serif', padding: '28px 16px' }}>
      <div style={{ maxWidth: 540, margin: '0 auto' }}>
        <div style={{ textAlign: 'center', marginBottom: 18 }}>
          <div style={{ fontSize: 24, fontWeight: 800, letterSpacing: 1 }}>TN<span style={{ color: C.accent }}>FX</span></div>
          <div style={{ fontSize: 13, color: C.sub, marginTop: 2 }}>Open your trading account — it only takes a minute</div>
        </div>

        <div style={{ display: 'flex', gap: 6, marginBottom: 20 }}>
          {STEPS.map((s, i) => (
            <div key={s} style={{ flex: 1 }}>
              <div style={{ height: 4, borderRadius: 2, background: i <= step ? C.accent : C.border }} />
              <div style={{ fontSize: 9.5, marginTop: 5, textAlign: 'center', color: i === step ? C.accent : C.sub, fontWeight: i === step ? 700 : 400 }}>{s}</div>
            </div>
          ))}
        </div>

        <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 16, padding: 24 }}>
          {/* Back: lets the user return to fix a wrong phone / email / details (re-verifies on change) */}
          {step > 0 && step <= 4 && (
            <button onClick={() => goNext(step - 1)} style={{ background: 'none', border: 'none', color: C.sub, fontSize: 13, cursor: 'pointer', padding: 0, marginBottom: 12 }}>← Back</button>
          )}
          {err && <div style={{ background: 'rgba(255,93,108,0.12)', color: C.red, padding: '8px 12px', borderRadius: 8, fontSize: 13, marginBottom: 14 }}>{err}</div>}

          {step === 0 && <StepMobile {...{ f, up, busy, setBusy, setErr, onVerified: () => goNext(1) }} />}
          {step === 1 && <StepEmailPassword {...{ f, up, busy, setBusy, setErr, onVerified: () => goNext(2) }} />}
          {step === 2 && <StepDetails {...{ f, up, states, cities, setErr, next: () => goNext(3), goEdit: goNext }} />}
          {step === 3 && <StepFinance {...{ f, up, next: () => goNext(4) }} />}
          {step === 4 && <StepAccount {...{ f, up, opts, busy, setBusy, setErr, onSubmit: async () => {
            setBusy(true); setErr('');
            const r = await post('/register/submit', f);
            setBusy(false);
            if (r.ok) { setRegId(r.registration_id); setClientToken(r.client_token || ''); setPortalToken(r.portal_token || ''); goNext(5); } else setErr(r.error || 'Could not submit');
          } }} />}
          {step === 5 && <StepKyc {...{ regId, opts, portalToken, name: (f.first_name + ' ' + f.last_name).trim() }} />}
        </div>

        <div style={{ textAlign: 'center', marginTop: 16, fontSize: 12, color: C.sub }}>
          Already have an account? <a href="/" style={{ color: C.accent, textDecoration: 'none', fontWeight: 600 }}>Log in</a>
        </div>
      </div>
    </div>
  );
}

function Field({ label: l, children }: any) {
  return <div style={{ marginBottom: 14 }}><label style={lbl}>{l}</label>{children}</div>;
}

// Self-hosted forex captcha — server renders a candlestick image, user taps the asked candle,
// the answer is verified server-side in send-otp. onSolved gives {id, slot} (or null while unsolved).
function ForexCaptcha({ onSolved }: { onSolved: (v: { id: number; slot: number } | null) => void }) {
  const [ch, setCh] = useState<any>(null);
  const [picked, setPicked] = useState<number | null>(null);
  const load = () => { setPicked(null); onSolved(null); setCh(null); get('/register/captcha').then(setCh).catch(() => {}); };
  useEffect(() => { load(); }, []); // eslint-disable-line
  if (!ch) return <div style={{ fontSize: 12, color: C.sub, padding: '8px 0' }}>Loading check…</div>;
  const slots = ch.slots || 4;
  const pick = (e: React.MouseEvent<HTMLImageElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const slot = Math.min(slots - 1, Math.max(0, Math.floor(((e.clientX - r.left) / r.width) * slots)));
    setPicked(slot); onSolved({ id: ch.id, slot });
  };
  return (<div>
    <div style={{ fontSize: 12.5, color: C.text, marginBottom: 6, fontWeight: 600 }}>🤖 {ch.prompt}</div>
    <div style={{ position: 'relative', border: `1px solid ${C.border}`, borderRadius: 10, overflow: 'hidden' }}>
      <img src={ch.image} alt="captcha" onClick={pick} draggable={false} style={{ display: 'block', width: '100%', cursor: 'pointer' }} />
      {picked != null && <div style={{ position: 'absolute', top: 0, bottom: 0, left: `${picked * 100 / slots}%`, width: `${100 / slots}%`, border: `2px solid ${C.accent}`, borderRadius: 8, boxSizing: 'border-box', pointerEvents: 'none' }} />}
    </div>
    <div style={{ fontSize: 11, color: C.sub, marginTop: 6, display: 'flex', justifyContent: 'space-between' }}>
      <span>{picked != null ? 'Selected ✓ (tap to change)' : 'Tap a candle'}</span>
      <button onClick={load} style={{ background: 'none', border: 'none', color: C.accent, fontSize: 11, cursor: 'pointer' }}>↻ New</button>
    </div>
  </div>);
}

function OtpBox({ value, code, setCode, devCode, busy, onVerify, onResend, onChangeContact, contactLabel }: any) {
  return (<>
    <div style={{ fontSize: 13, color: C.sub, marginBottom: 12 }}>Enter the code sent to <b style={{ color: C.text }}>{value}</b>.{devCode && <span style={{ color: C.accent }}> (use {devCode})</span>}</div>
    {/* typo in the number/email? change it right here and we'll re-send */}
    {onChangeContact && <button onClick={onChangeContact} style={{ background: 'none', border: 'none', color: C.accent, fontSize: 12, cursor: 'pointer', padding: 0, marginBottom: 12 }}>✎ Wrong {contactLabel || 'contact'}? Change it</button>}
    <Field label="Verification code"><input style={{ ...inp, letterSpacing: 6, fontSize: 20, textAlign: 'center' }} value={code} onChange={e => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))} placeholder="••••" autoFocus /></Field>
    <button style={{ ...btn(C.accent), width: '100%' }} disabled={busy || code.length < 4} onClick={onVerify}>{busy ? 'Verifying…' : 'Verify →'}</button>
    <button style={{ background: 'none', border: 'none', color: C.sub, fontSize: 12, marginTop: 10, cursor: 'pointer', width: '100%' }} onClick={onResend}>Resend code</button>
  </>);
}

function ExistsBox({ field, onLogin, onNew }: any) {
  return (<div style={{ textAlign: 'center' }}>
    <div style={{ fontSize: 15, marginBottom: 6 }}>You already have an account 👋</div>
    <div style={{ fontSize: 13, color: C.sub, marginBottom: 18 }}>This {field} is already registered.</div>
    <button style={{ ...btn(C.accent), width: '100%', marginBottom: 8 }} onClick={onLogin}>Log in to my account</button>
    <button style={{ ...btn(C.card2), width: '100%', border: `1px solid ${C.border}` }} onClick={onNew}>Use a different {field}</button>
  </div>);
}

function StepMobile({ f, up, busy, setBusy, setErr, onVerified }: any) {
  const [stage, setStage] = useState<'enter' | 'exists' | 'otp'>('enter');
  const [code, setCode] = useState('');
  const [devCode, setDevCode] = useState('');
  const [cap, setCap] = useState<{ id: number; slot: number } | null>(null);
  const [capKey, setCapKey] = useState(0);
  const c = byIso(f.dial_iso) || COUNTRIES[0];
  const valid = validNational(f.phone_national, c);   // a typed leading 0 is ignored
  const fullPhone = e164(c, f.phone_national);

  const send = async () => {
    if (!valid) { setErr(`Enter a valid ${c.name} mobile number`); return; }
    if (!cap) { setErr('Tap the right candle to continue'); return; }
    up('phone', fullPhone);
    setBusy(true); setErr('');
    const r = await post('/register/check-contact', { channel: 'phone', value: fullPhone });
    if (r.exists) { setBusy(false); setStage('exists'); return; }
    const o = await post('/register/send-otp', { channel: 'phone', value: fullPhone, captcha_id: cap.id, captcha_answer: cap.slot });
    setBusy(false);
    if (o.ok) { setDevCode(o.dev_code || ''); setStage('otp'); }
    else { setErr(o.error || 'Could not send code'); setCap(null); setCapKey(k => k + 1); }  // fresh captcha on failure
  };
  const verify = async () => {
    setBusy(true); setErr('');
    const r = await post('/register/verify-otp', { channel: 'phone', value: fullPhone, code });
    setBusy(false);
    if (r.ok) onVerified(); else setErr(r.error || 'Invalid code');
  };

  return (<>
    <h3 style={{ margin: '0 0 16px', fontSize: 17 }}>Your mobile number</h3>
    {stage === 'enter' && (<>
      <Field label="Mobile number">
        <div style={{ display: 'flex', gap: 8 }}>
          <select value={f.dial_iso} onChange={e => { up('dial_iso', e.target.value); up('phone_national', normalizeNational(f.phone_national, byIso(e.target.value))); }}
            style={{ ...inp, width: 132, flex: 'none', paddingLeft: 8, paddingRight: 4 }}>
            {COUNTRIES.map(x => <option key={x.iso} value={x.iso}>{isoFlag(x.iso)} {x.dial}</option>)}
          </select>
          <input style={{ ...inp, flex: 1 }} value={f.phone_national} onChange={e => up('phone_national', normalizeNational(e.target.value, c))}
            inputMode="numeric" placeholder={c.ex || 'phone number'} autoFocus />
        </div>
        {c.pre && <div style={{ fontSize: 11, color: C.sub, marginTop: 6 }}>Common prefixes: <b style={{ color: C.text }}>{c.pre}</b></div>}
        {f.phone_national && !valid && <div style={{ fontSize: 11, color: C.red, marginTop: 4 }}>Enter the full {c.name} number{c.prefix ? ` (starts with ${c.prefix})` : ''}. A leading 0 is fine.</div>}
      </Field>
      <div style={{ marginBottom: 14 }}><ForexCaptcha key={capKey} onSolved={setCap} /></div>
      <button style={{ ...btn(C.accent), width: '100%' }} disabled={busy || !valid || !cap} onClick={send}>{busy ? 'Sending…' : 'Send code →'}</button>
    </>)}
    {stage === 'exists' && <ExistsBox field="number" onLogin={() => (window.location.href = '/')} onNew={() => setStage('enter')} />}
    {stage === 'otp' && <OtpBox value={fullPhone} code={code} setCode={setCode} devCode={devCode} busy={busy} onVerify={verify} onResend={send}
      contactLabel="number" onChangeContact={() => { setStage('enter'); setCode(''); setErr(''); }} />}
  </>);
}

function StepEmailPassword({ f, up, busy, setBusy, setErr, onVerified }: any) {
  const [stage, setStage] = useState<'enter' | 'exists' | 'otp'>('enter');
  const [code, setCode] = useState('');
  const [devCode, setDevCode] = useState('');
  const [showSugg, setShowSugg] = useState(true);
  const [showPw, setShowPw] = useState(false);
  const [confirm, setConfirm] = useState('');

  const suggestions = (): string[] => {
    const v = (f.email || '').trim();
    if (!v || /\s/.test(v)) return [];
    const at = v.indexOf('@');
    const local = at >= 0 ? v.slice(0, at) : v;
    const dom = at >= 0 ? v.slice(at + 1).toLowerCase() : '';
    if (!local) return [];
    return EMAIL_DOMAINS.filter(d => !dom || d.startsWith(dom)).map(d => `${local}@${d}`).filter(s => s !== v).slice(0, 5);
  };

  const send = async () => {
    if (!/.+@.+\..+/.test(f.email || '')) { setErr('Enter a valid email'); return; }
    if ((f.password || '').length < 8) { setErr('Password must be at least 8 characters'); return; }
    if (f.password !== confirm) { setErr('Passwords do not match'); return; }
    setBusy(true); setErr('');
    const r = await post('/register/check-contact', { channel: 'email', value: f.email });
    if (r.exists) { setBusy(false); setStage('exists'); return; }
    const o = await post('/register/send-otp', { channel: 'email', value: f.email });
    setBusy(false);
    if (o.ok) { setDevCode(o.dev_code || ''); setStage('otp'); } else setErr(o.error || 'Could not send code');
  };
  const verify = async () => {
    setBusy(true); setErr('');
    const r = await post('/register/verify-otp', { channel: 'email', value: f.email, code });
    setBusy(false);
    if (r.ok) onVerified(); else setErr(r.error || 'Invalid code');
  };

  const sugg = suggestions();
  return (<>
    <h3 style={{ margin: '0 0 16px', fontSize: 17 }}>Your email & password</h3>
    {stage === 'enter' && (<>
      <Field label="Email address">
        <input style={inp} value={f.email} onChange={e => { up('email', e.target.value); setShowSugg(true); }} placeholder="you@example.com" autoFocus />
        {showSugg && sugg.length > 0 && (
          <div style={{ marginTop: 6, background: C.card2, border: `1px solid ${C.border}`, borderRadius: 10, overflow: 'hidden' }}>
            {sugg.map(s => (
              <div key={s} onClick={() => { up('email', s); setShowSugg(false); }}
                style={{ padding: '9px 12px', fontSize: 13, cursor: 'pointer' }}
                onMouseEnter={e => (e.currentTarget.style.background = C.card)} onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}>{s}</div>
            ))}
          </div>
        )}
      </Field>
      <Field label="Create a password">
        <div style={{ position: 'relative' }}>
          <input type={showPw ? 'text' : 'password'} style={{ ...inp, paddingRight: 60 }} value={f.password} onChange={e => up('password', e.target.value)} placeholder="At least 8 characters" />
          <button onClick={() => setShowPw(s => !s)} style={{ position: 'absolute', right: 10, top: 11, background: 'none', border: 'none', color: C.sub, fontSize: 11, cursor: 'pointer' }}>{showPw ? 'Hide' : 'Show'}</button>
        </div>
        <button onClick={() => { const p = genPassword(); up('password', p); setConfirm(p); setShowPw(true); }} style={{ background: 'none', border: 'none', color: C.accent, fontSize: 12, cursor: 'pointer', marginTop: 8, padding: 0 }}>🔑 Suggest a strong password</button>
      </Field>
      <Field label="Confirm password">
        <input type={showPw ? 'text' : 'password'} style={inp} value={confirm} onChange={e => setConfirm(e.target.value)} placeholder="Re-enter your password" />
        {confirm.length > 0 && confirm !== f.password && <div style={{ fontSize: 11, color: C.red, marginTop: 4 }}>Passwords don't match</div>}
        {confirm.length > 0 && confirm === f.password && (f.password || '').length >= 8 && <div style={{ fontSize: 11, color: C.accent, marginTop: 4 }}>✓ Passwords match</div>}
      </Field>
      <button style={{ ...btn(C.accent), width: '100%' }} disabled={busy} onClick={send}>{busy ? 'Sending…' : 'Save & send code →'}</button>
    </>)}
    {stage === 'exists' && <ExistsBox field="email" onLogin={() => (window.location.href = '/')} onNew={() => setStage('enter')} />}
    {stage === 'otp' && <OtpBox value={f.email} code={code} setCode={setCode} devCode={devCode} busy={busy} onVerify={verify} onResend={send}
      contactLabel="email" onChangeContact={() => { setStage('enter'); setCode(''); setErr(''); }} />}
  </>);
}

function StepDetails({ f, up, states, cities, setErr, next, goEdit }: any) {
  const hasStates = (states || []).length > 0;
  const go = () => {
    if (!f.first_name || !f.last_name) { setErr('Please enter your name'); return; }
    if (!f.nationality) { setErr('Please select your nationality'); return; }
    if (!f.country) { setErr('Please select your country of residence'); return; }
    if (hasStates && !f.state) { setErr('Please select your state / province'); return; }
    setErr(''); next();
  };
  return (<>
    <h3 style={{ margin: '0 0 16px', fontSize: 17 }}>Your details</h3>
    <div style={{ display: 'flex', gap: 10 }}>
      <div style={{ flex: 1 }}><Field label="First name"><input style={inp} value={f.first_name} onChange={e => up('first_name', e.target.value)} /></Field></div>
      <div style={{ flex: 1 }}><Field label="Last name"><input style={inp} value={f.last_name} onChange={e => up('last_name', e.target.value)} /></Field></div>
    </div>
    <Field label="Date of birth"><input type="date" style={inp} value={f.date_of_birth} onChange={e => up('date_of_birth', e.target.value)} max={new Date().toISOString().slice(0, 10)} /></Field>
    <Field label="Nationality"><select style={inp} value={f.nationality} onChange={e => up('nationality', e.target.value)}>
      <option value="">Select nationality…</option>{COUNTRY_NAMES.map(c => <option key={c} value={c}>{c}</option>)}</select></Field>
    <Field label="Country of residence"><select style={inp} value={f.country} onChange={e => { up('country', e.target.value); up('state', ''); up('city', ''); }}>
      <option value="">Select country…</option>{COUNTRY_NAMES.map(c => <option key={c} value={c}>{c}</option>)}</select></Field>
    {hasStates && (
      <Field label="State / Province"><select style={inp} value={f.state} onChange={e => { up('state', e.target.value); up('city', ''); }}>
        <option value="">Select state / province…</option>{states.map((s: string) => <option key={s} value={s}>{s}</option>)}</select></Field>
    )}
    <Field label="City">{(hasStates || cities.length)
      ? <select style={inp} value={f.city} onChange={e => up('city', e.target.value)} disabled={hasStates && !f.state}>
          <option value="">{hasStates && !f.state ? 'Select a state / province first…' : 'Select city…'}</option>{cities.map((c: string) => <option key={c} value={c}>{c}</option>)}</select>
      : <input style={inp} value={f.city} onChange={e => up('city', e.target.value)} placeholder="Your city" />}</Field>
    <Field label="Address"><input style={inp} value={f.address} onChange={e => up('address', e.target.value)} placeholder="Street, area" /></Field>
    <button style={{ ...btn(C.accent), width: '100%', marginTop: 6 }} onClick={go}>Continue →</button>
  </>);
}

function StepFinance({ f, up, next }: any) {
  const q = f.questionnaire;
  const setQ = (k: string, v: string) => up('questionnaire', { ...q, [k]: v });
  const opt = (cur: string, set: (v: string) => void, vals: string[]) => (
    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>{vals.map(v => (
      <button key={v} onClick={() => set(v)} style={{ padding: '9px 14px', borderRadius: 9, fontSize: 13, cursor: 'pointer', border: `1px solid ${cur === v ? C.accent : C.border}`, background: cur === v ? 'rgba(0,229,160,0.12)' : C.card2, color: cur === v ? C.accent : C.text }}>{v}</button>))}</div>
  );
  return (<>
    <h3 style={{ margin: '0 0 16px', fontSize: 17 }}>A few quick questions</h3>
    <Field label="Trading experience">{opt(q.experience, v => setQ('experience', v), ['Beginner', '1–3 years', '3+ years'])}</Field>
    <Field label="Expected first deposit">{opt(q.deposit, v => setQ('deposit', v), ['< $500', '$500–$5k', '$5k–$50k', '$50k+'])}</Field>
    <Field label="Source of funds">{opt(q.source, v => setQ('source', v), ['Salary', 'Business', 'Savings', 'Investments'])}</Field>
    <button style={{ ...btn(C.accent), width: '100%', marginTop: 6 }} onClick={next}>Continue →</button>
  </>);
}

function StepAccount({ f, up, opts, busy, onSubmit }: any) {
  const pill = (cur: any, val: any, set: () => void, txt: string) => (
    <button onClick={set} style={{ flex: 1, padding: '12px', borderRadius: 10, cursor: 'pointer', border: `1px solid ${cur === val ? C.accent : C.border}`, background: cur === val ? 'rgba(0,229,160,0.12)' : C.card2, color: cur === val ? C.accent : C.text, fontSize: 13, fontWeight: 600 }}>{txt}</button>
  );
  return (<>
    <h3 style={{ margin: '0 0 16px', fontSize: 17 }}>Choose your account</h3>
    <Field label="Platform"><div style={{ display: 'flex', gap: 8 }}>{(opts.platforms || ['MT5', 'MT4']).map((p: string) => pill(f.platform, p, () => up('platform', p), p))}</div></Field>
    <Field label="Account model"><div style={{ display: 'flex', gap: 8 }}>{pill(f.islamic, false, () => up('islamic', false), 'Non-Islamic (Swap account)')}{pill(f.islamic, true, () => up('islamic', true), 'Islamic (Swap-free)')}</div></Field>
    <Field label="Account type"><select style={inp} value={f.account_type} onChange={e => up('account_type', e.target.value)}>{(opts.account_types || []).map((t: string) => <option key={t} value={t}>{t}</option>)}</select></Field>
    <Field label="Leverage"><select style={inp} value={f.leverage} onChange={e => up('leverage', e.target.value)}>{(opts.leverages || []).map((l: string) => <option key={l} value={l}>{l}</option>)}</select></Field>
    <button style={{ ...btn(C.accent), width: '100%', marginTop: 6 }} disabled={busy} onClick={onSubmit}>{busy ? 'Creating…' : 'Create my account →'}</button>
  </>);
}

function StepKyc({ regId, opts, portalToken, name }: any) {
  const [docType, setDocType] = useState('');
  const [done, setDone] = useState<Record<string, boolean>>({});
  const sides = (opts.doc_types || []).find((d: any) => d.key === docType)?.sides || [];
  // ID sides + proof of residence FRONT and BACK; only the proof-of-address back is optional.
  const need = docType ? [...sides, 'proof_of_address', 'proof_of_address_back'] : [];

  const upload = async (side: string, file: File) => {
    const isProof = side.startsWith('proof_of_address');
    const fd = new FormData();
    fd.append('registration_id', String(regId));
    fd.append('doc_type', side === 'selfie' ? 'selfie' : isProof ? 'proof_of_address' : docType);
    fd.append('side', side);
    fd.append('file', file);
    const r = await fetch(`${API}/register/kyc-upload`, { method: 'POST', body: fd }).then(x => x.json());
    if (r.ok) setDone(d => ({ ...d, [side]: true }));
  };
  const niceSide = (s: string) => ({ front: 'Front side', back: 'Back side', main: 'Photo page', selfie: 'Selfie (holding your ID)', proof_of_address: 'Proof of residence (front)', proof_of_address_back: 'Proof of residence — back side' } as any)[s] || s;

  const hasUploads = Object.values(done).some(Boolean);
  // uploaded => kick off the AI review (server marks the client "under review"); skipped => just go.
  const finish = (uploaded: boolean) => {
    if (uploaded) { try { fetch(`${API}/register/kyc/process/${regId}`, { method: 'POST' }); } catch {} }
    if (portalToken) { localStorage.setItem('tnfx_portal_token', portalToken); if (name) localStorage.setItem('userName', name); }
    window.location.href = '/portal/';
  };

  const qrUrl = regId ? `${window.location.origin}/register?kyc=${regId}` : '';

  if (!regId) return <div style={{ textAlign: 'center', color: C.accent }}>🎉 Account created!</div>;
  return (<>
    <h3 style={{ margin: '0 0 6px', fontSize: 17 }}>🎉 Account created — verify to activate</h3>
    <div style={{ fontSize: 13, color: C.sub, marginBottom: 16 }}>Upload your documents to get verified and funded. You can also do this later.</div>

    {/* Desktop/PC users: scan to finish on the phone's camera (uploads land on the same account) */}
    {qrUrl && (
      <div style={{ display: 'flex', gap: 12, alignItems: 'center', padding: 12, background: C.card2, border: `1px solid ${C.border}`, borderRadius: 10, marginBottom: 16 }}>
        <img alt="Scan to upload on your phone" width={92} height={92} style={{ borderRadius: 8, background: '#fff', padding: 4, flexShrink: 0 }}
          src={`https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(qrUrl)}`} />
        <div>
          <div style={{ fontSize: 13, fontWeight: 700 }}>📱 On a computer? Use your phone's camera</div>
          <div style={{ fontSize: 11.5, color: C.sub, marginTop: 4, lineHeight: 1.5 }}>Scan this code to open this step on your phone and take photos of your documents directly. When you're done, you can submit from either device.</div>
        </div>
      </div>
    )}

    <Field label="What ID will you use?">
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>{(opts.doc_types || []).map((d: any) =>
        <button key={d.key} onClick={() => setDocType(d.key)} style={{ padding: '10px 14px', borderRadius: 9, fontSize: 13, cursor: 'pointer', border: `1px solid ${docType === d.key ? C.accent : C.border}`, background: docType === d.key ? 'rgba(0,229,160,0.12)' : C.card2, color: docType === d.key ? C.accent : C.text }}>{d.label}</button>)}</div>
    </Field>

    {docType && need.map(side => (
      <div key={side} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '12px 14px', background: C.card2, border: `1px solid ${done[side] ? C.accent : C.border}`, borderRadius: 10, marginBottom: 8 }}>
        <span style={{ flex: 1, fontSize: 13 }}>{niceSide(side)}{side === 'proof_of_address_back' ? ' (optional)' : ''}</span>
        {done[side] ? <span style={{ color: C.accent, fontWeight: 700 }}>✓ Uploaded</span> : (<span style={{ display: 'flex', gap: 6 }}>
          <label style={{ ...btn(C.accent2), padding: '7px 11px', fontSize: 12, cursor: 'pointer' }}>📷 Photo
            <input type="file" accept="image/*" capture={(side === 'selfie' ? 'user' : 'environment') as any} style={{ display: 'none' }} onChange={e => e.target.files && upload(side, e.target.files[0])} />
          </label>
          {side !== 'selfie' && <label style={{ ...btn(C.card2), border: `1px solid ${C.border}`, color: C.text, padding: '7px 11px', fontSize: 12, cursor: 'pointer' }}>📤 Upload
            <input type="file" accept="image/*" style={{ display: 'none' }} onChange={e => e.target.files && upload(side, e.target.files[0])} />
          </label>}
        </span>)}
        {/* Only proof-of-address may have no back; ID/licence back is required (no skip). */}
        {side === 'proof_of_address_back' && !done[side] && <button onClick={() => setDone(d => ({ ...d, [side]: true }))} style={{ background: 'none', border: 'none', color: C.sub, fontSize: 11, cursor: 'pointer' }}>No back side</button>}
      </div>
    ))}

    <button style={{ ...btn(C.accent), width: '100%', marginTop: 10 }} onClick={() => finish(hasUploads)}>Submit & go to dashboard</button>
    <button style={{ background: 'none', border: 'none', color: C.sub, fontSize: 12, marginTop: 12, cursor: 'pointer', width: '100%' }} onClick={() => finish(false)}>Skip for now → dashboard</button>
  </>);
}

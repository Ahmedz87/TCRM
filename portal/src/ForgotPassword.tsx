import React, { useState } from 'react';

// Forgot-password modal (mobile OTP) for the client portal. 3 steps: identifier -> OTP -> new password.
// Hits the shared public backend (/api/auth/pwreset/*) with scope='client'.
async function post(path: string, body: any) {
  const res = await fetch('/api' + path, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  const txt = await res.text();
  let data: any = {}; try { data = txt ? JSON.parse(txt) : {}; } catch {}
  if (!res.ok) throw new Error(data?.detail || 'Request failed');
  return data;
}

export default function ForgotPassword({ onClose, onDone }: { onClose: () => void; onDone?: (id: string) => void }) {
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [ident, setIdent] = useState('');
  const [code, setCode] = useState('');
  const [pw, setPw] = useState('');
  const [pw2, setPw2] = useState('');
  const [maskedTo, setMaskedTo] = useState('');
  const [devCode, setDevCode] = useState('');
  const [resetToken, setResetToken] = useState('');
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);

  const send = async () => {
    if (!ident.trim()) return;
    setErr(''); setBusy(true);
    try {
      const d = await post('/auth/pwreset/send', { identifier: ident.trim(), scope: 'client' });
      setMaskedTo(d.masked_to || '');
      if (d.dev_code) setDevCode(d.dev_code);
      setStep(2);
    } catch (e: any) { setErr(e?.message || 'Could not send the code.'); }
    finally { setBusy(false); }
  };

  const verify = async () => {
    if (!code.trim()) return;
    setErr(''); setBusy(true);
    try {
      const d = await post('/auth/pwreset/verify', { identifier: ident.trim(), scope: 'client', code: code.trim() });
      if (d?.ok && d?.reset_token) { setResetToken(d.reset_token); setStep(3); }
      else setErr(d?.error || 'Incorrect or expired code.');
    } catch (e: any) { setErr(e?.message || 'Incorrect or expired code.'); }
    finally { setBusy(false); }
  };

  const reset = async () => {
    if (pw.length < 8) { setErr('Password must be at least 8 characters.'); return; }
    if (pw !== pw2) { setErr('Passwords do not match.'); return; }
    setErr(''); setBusy(true);
    try {
      await post('/auth/pwreset/reset', { reset_token: resetToken, new_password: pw });
      if (onDone) onDone(ident.trim());
      onClose();
    } catch (e: any) { setErr(e?.message || 'Could not reset the password.'); }
    finally { setBusy(false); }
  };

  return (
    <div style={S.overlay} onClick={onClose}>
      <div style={S.card} onClick={e => e.stopPropagation()}>
        <div style={S.head}>
          <span style={S.title}>Reset password</span>
          <button onClick={onClose} style={S.x}>✕</button>
        </div>
        <div style={S.stepsRow}>
          {[1, 2, 3].map(n => <div key={n} style={{ ...S.dot, background: step >= (n as any) ? '#F8500A' : '#2a3240' }} />)}
        </div>

        {step === 1 && (
          <>
            <div style={S.hint}>Enter your email, phone or trading login. We'll send a verification code to the phone (or email) on your account.</div>
            <input autoFocus value={ident} onChange={e => setIdent(e.target.value)} onKeyDown={e => e.key === 'Enter' && send()}
              placeholder="Email / phone / login" style={S.input} />
            <button onClick={send} disabled={busy || !ident.trim()} style={S.btn}>{busy ? '…' : 'Send code'}</button>
          </>
        )}

        {step === 2 && (
          <>
            <div style={S.hint}>{maskedTo ? <>We sent a 6-digit code to <b style={{ color: '#fff' }}>{maskedTo}</b>.</> : <>If an account exists, a code was sent to its phone on file.</>}</div>
            {devCode && <div style={S.dev}>Dev mode — your code is <b>{devCode}</b> (SMS gateway not live yet)</div>}
            <input autoFocus value={code} onChange={e => setCode(e.target.value.replace(/[^0-9]/g, ''))} onKeyDown={e => e.key === 'Enter' && verify()}
              placeholder="6-digit code" maxLength={6} style={{ ...S.input, letterSpacing: 6, textAlign: 'center', fontSize: 20 }} />
            <button onClick={verify} disabled={busy || !code.trim()} style={S.btn}>{busy ? '…' : 'Verify'}</button>
            <button onClick={send} disabled={busy} style={S.linkBtn}>Resend code</button>
          </>
        )}

        {step === 3 && (
          <>
            <div style={S.hint}>Choose a new password (at least 8 characters).</div>
            <input autoFocus type="password" value={pw} onChange={e => setPw(e.target.value)} placeholder="New password" style={S.input} />
            <input type="password" value={pw2} onChange={e => setPw2(e.target.value)} onKeyDown={e => e.key === 'Enter' && reset()} placeholder="Confirm new password" style={{ ...S.input, marginTop: 10 }} />
            <button onClick={reset} disabled={busy} style={S.btn}>{busy ? '…' : 'Reset password'}</button>
          </>
        )}

        {err && <div style={S.err}>{err}</div>}
      </div>
    </div>
  );
}

const S: any = {
  overlay: { position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.65)', zIndex: 999, display: 'flex', alignItems: 'center', justifyContent: 'center' },
  card: { width: 380, maxWidth: '92vw', background: 'linear-gradient(160deg,#12161F,#0d1016)', border: '1px solid #232a38', borderRadius: 18, padding: 26 },
  head: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 },
  title: { fontSize: 17, fontWeight: 800, color: '#fff' },
  x: { background: 'none', border: 'none', color: '#8A93A3', fontSize: 18, cursor: 'pointer' },
  stepsRow: { display: 'flex', gap: 6, marginBottom: 16 },
  dot: { flex: 1, height: 4, borderRadius: 2 },
  hint: { fontSize: 12.5, color: '#8A93A3', lineHeight: 1.5, marginBottom: 12 },
  dev: { fontSize: 11.5, color: '#F8500A', background: 'rgba(232,184,75,0.08)', border: '1px solid rgba(232,184,75,0.25)', borderRadius: 8, padding: '7px 10px', marginBottom: 10 },
  input: { width: '100%', padding: '12px 14px', borderRadius: 10, background: '#0B0E14', border: '1px solid #2a3240', color: '#fff', fontSize: 14, outline: 'none', boxSizing: 'border-box' },
  btn: { width: '100%', marginTop: 14, padding: 12, borderRadius: 10, background: 'linear-gradient(90deg,#F8500A,#FF7A1A)', color: '#0B0E14', border: 'none', fontSize: 14, fontWeight: 800, cursor: 'pointer' },
  linkBtn: { width: '100%', marginTop: 8, padding: 8, background: 'transparent', border: 'none', color: '#8A93A3', fontSize: 12.5, cursor: 'pointer', textDecoration: 'underline' },
  err: { color: '#F2667A', fontSize: 12.5, marginTop: 12, textAlign: 'center' },
};

import React, { useState } from 'react';
import axios from 'axios';

// Forgot-password modal (mobile OTP) for the staff CRM. 3 steps: identifier -> OTP -> new password.
// scope is 'staff' here; the same backend (/auth/pwreset/*) also serves the client portal ('client').
export default function ForgotPassword({ onClose, onDone, scope = 'staff', isAr = false }:
  { onClose: () => void; onDone?: (identifier: string) => void; scope?: 'staff' | 'client'; isAr?: boolean }) {
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
      const r = await axios.post('/api/auth/pwreset/send', { identifier: ident.trim(), scope });
      const d = r.data || {};
      setMaskedTo(d.masked_to || '');
      if (d.dev_code) setDevCode(d.dev_code);
      // Always advance (anti-enumeration: the server won't say whether the account exists).
      setStep(2);
    } catch (e: any) {
      setErr(e?.response?.data?.detail || 'Could not send the code. Please try again.');
    } finally { setBusy(false); }
  };

  const verify = async () => {
    if (!code.trim()) return;
    setErr(''); setBusy(true);
    try {
      const r = await axios.post('/api/auth/pwreset/verify', { identifier: ident.trim(), scope, code: code.trim() });
      if (r.data?.ok && r.data?.reset_token) { setResetToken(r.data.reset_token); setStep(3); }
      else setErr(r.data?.error || 'Incorrect or expired code.');
    } catch (e: any) {
      setErr(e?.response?.data?.detail || 'Incorrect or expired code.');
    } finally { setBusy(false); }
  };

  const reset = async () => {
    if (pw.length < 8) { setErr('Password must be at least 8 characters.'); return; }
    if (pw !== pw2) { setErr('Passwords do not match.'); return; }
    setErr(''); setBusy(true);
    try {
      await axios.post('/api/auth/pwreset/reset', { reset_token: resetToken, new_password: pw });
      if (onDone) onDone(ident.trim());
      onClose();
    } catch (e: any) {
      setErr(e?.response?.data?.detail || 'Could not reset the password. Please start again.');
    } finally { setBusy(false); }
  };

  return (
    <div style={S.overlay} onClick={onClose}>
      <div style={S.card} onClick={e => e.stopPropagation()}>
        <div style={S.head}>
          <span style={S.title}>{isAr ? 'استعادة كلمة المرور' : 'Reset password'}</span>
          <button onClick={onClose} style={S.x}>✕</button>
        </div>
        <div style={S.stepsRow}>
          {[1, 2, 3].map(n => <div key={n} style={{ ...S.dot, background: step >= (n as any) ? '#00e5a0' : '#4f596b' }} />)}
        </div>

        {step === 1 && (
          <>
            <div style={S.hint}>Enter your {scope === 'staff' ? 'work email or phone' : 'email, phone or login'}. We'll send a verification code to the {scope === 'staff' ? 'email' : 'phone'} on your account.</div>
            <input autoFocus value={ident} onChange={e => setIdent(e.target.value)} onKeyDown={e => e.key === 'Enter' && send()}
              placeholder={scope === 'staff' ? 'name@tnfx.co or phone' : 'email / phone / login'} style={S.input} />
            <button onClick={send} disabled={busy || !ident.trim()} style={S.btn}>{busy ? '…' : 'Send code'}</button>
          </>
        )}

        {step === 2 && (
          <>
            <div style={S.hint}>{maskedTo ? <>We sent a 6-digit code to <b style={{ color: '#cfd6e0' }}>{maskedTo}</b>.</> : <>If an account exists, a code was sent to its phone on file.</>}</div>
            {devCode && <div style={S.dev}>Dev mode — your code is <b>{devCode}</b> (SMS gateway not live yet)</div>}
            <input autoFocus value={code} onChange={e => setCode(e.target.value.replace(/[^0-9]/g, ''))} onKeyDown={e => e.key === 'Enter' && verify()}
              placeholder="6-digit code" maxLength={6} style={{ ...S.input, letterSpacing: 6, textAlign: 'center', fontSize: 20 }} />
            <button onClick={verify} disabled={busy || !code.trim()} style={S.btn}>{busy ? '…' : 'Verify'}</button>
            <button onClick={send} disabled={busy} style={S.link}>Resend code</button>
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
  overlay: { position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', zIndex: 999, display: 'flex', alignItems: 'center', justifyContent: 'center' },
  card: { width: 380, maxWidth: '92vw', background: 'var(--bg-card,#2c333e)', border: '1px solid var(--border,#4f596b)', borderRadius: 16, padding: 26 },
  head: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 },
  title: { fontSize: 17, fontWeight: 800, color: 'var(--text,#fff)' },
  x: { background: 'none', border: 'none', color: 'var(--text2,#888)', fontSize: 18, cursor: 'pointer' },
  stepsRow: { display: 'flex', gap: 6, marginBottom: 16 },
  dot: { flex: 1, height: 4, borderRadius: 2 },
  hint: { fontSize: 12.5, color: 'var(--text2,#9aa3b2)', lineHeight: 1.5, marginBottom: 12 },
  dev: { fontSize: 11.5, color: '#E8B84B', background: 'rgba(232,184,75,0.08)', border: '1px solid rgba(232,184,75,0.25)', borderRadius: 8, padding: '7px 10px', marginBottom: 10 },
  input: { width: '100%', padding: '11px 14px', background: 'var(--bg-input,#373f4d)', border: '1px solid var(--border2,#626d80)', borderRadius: 8, color: 'var(--text,#fff)', fontSize: 14, outline: 'none', boxSizing: 'border-box' },
  btn: { width: '100%', marginTop: 14, padding: 12, background: 'var(--accent,#00e5a0)', border: 'none', borderRadius: 8, color: '#0b0e14', fontSize: 14, fontWeight: 800, cursor: 'pointer' },
  link: { width: '100%', marginTop: 8, padding: 8, background: 'transparent', border: 'none', color: 'var(--text2,#888)', fontSize: 12.5, cursor: 'pointer', textDecoration: 'underline' },
  err: { color: '#ff4d4d', fontSize: 12.5, marginTop: 12, textAlign: 'center' },
};

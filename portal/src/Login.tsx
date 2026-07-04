import React, { useState } from 'react';
import { portalLogin, setToken } from './api';
import ForgotPassword from './ForgotPassword';
import tnfxLogo from './assets/tnfx-logo.png';

export default function Login({ onLogin }: { onLogin: () => void }) {
  const [ident, setIdent] = useState('');
  const [password, setPassword] = useState('');
  const [err, setErr] = useState('');
  const [loading, setLoading] = useState(false);
  const [showForgot, setShowForgot] = useState(false);

  const submit = async () => {
    if (!ident.trim() || !password) return;
    setErr(''); setLoading(true);
    try {
      const res = await portalLogin(ident.trim(), password);
      if (res?.access_token) { setToken(res.access_token); onLogin(); }
      else setErr('Could not log in.');
    } catch (e: any) {
      setErr(e?.message || 'Incorrect login or password.');
    } finally { setLoading(false); }
  };

  return (
    <div style={S.wrap}>
      <div style={S.glowA} />
      <div style={S.glowB} />

      {/* top-right Sign up (always visible) — reuses the full registration wizard on the main site */}
      <button onClick={() => { window.location.href = '/register'; }} style={S.signupTop}>Sign up</button>

      {showForgot && <ForgotPassword onClose={() => setShowForgot(false)} onDone={(id) => { setIdent(id); setErr(''); }} />}

      <div style={S.card}>
        <div style={{ textAlign: 'center', marginBottom: 26 }}>
          <img src={tnfxLogo} alt="TNFX" style={{ height: 46, width: 'auto', display: 'inline-block' }} />
          <div style={S.sub}>Client Portal</div>
        </div>

        <label style={S.label}>Email or login</label>
        <input
          autoFocus
          value={ident}
          onChange={e => setIdent(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') submit(); }}
          placeholder="Email or trading login"
          autoComplete="username"
          style={S.input}
        />

        <label style={{ ...S.label, marginTop: 14 }}>Password</label>
        <input
          type="password"
          value={password}
          onChange={e => setPassword(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') submit(); }}
          placeholder="Your password"
          autoComplete="current-password"
          style={S.input}
        />

        {err && <div style={S.err}>{err}</div>}

        <button onClick={submit} disabled={loading || !ident.trim() || !password} style={{ ...S.btn, opacity: loading || !ident.trim() || !password ? 0.6 : 1 }}>
          {loading ? 'Signing in…' : 'Sign in'}
        </button>

        <div style={{ textAlign: 'center', marginTop: 14 }}>
          <button onClick={() => setShowForgot(true)} style={S.forgot}>Forgot password?</button>
        </div>

        <div style={{ borderTop: '1px solid #232a38', margin: '16px 0 12px' }} />
        <div style={{ textAlign: 'center', fontSize: 12.5, color: '#8A93A3' }}>
          New to TNFX?{' '}
          <button onClick={() => { window.location.href = '/register'; }} style={S.signupInline}>Create an account</button>
        </div>

        <div style={S.foot}>
          By signing in you agree to TNFX's Terms & Privacy Policy.
        </div>
      </div>
    </div>
  );
}

const S: any = {
  wrap: { minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', position: 'relative', overflow: 'hidden', background: 'radial-gradient(120% 90% at 50% -10%, #1a1407 0%, #0B0E14 55%)' },
  glowA: { position: 'absolute', top: '-20%', left: '-10%', width: 480, height: 480, borderRadius: '50%', background: 'radial-gradient(circle, rgba(232,184,75,0.16), transparent 70%)', filter: 'blur(20px)' },
  glowB: { position: 'absolute', bottom: '-25%', right: '-10%', width: 520, height: 520, borderRadius: '50%', background: 'radial-gradient(circle, rgba(111,227,212,0.10), transparent 70%)', filter: 'blur(20px)' },
  card: { position: 'relative', width: 380, maxWidth: '90vw', background: 'linear-gradient(160deg,#12161F,#0d1016)', border: '1px solid #232a38', borderRadius: 20, padding: 30, boxShadow: '0 30px 80px -30px rgba(0,0,0,0.8)' },
  logo: { fontSize: 34, fontWeight: 900, letterSpacing: '-0.02em', color: '#fff' },
  sub: { fontSize: 11, letterSpacing: '0.28em', textTransform: 'uppercase', color: '#8A93A3', marginTop: 4, fontWeight: 700 },
  devBadge: { fontSize: 11, color: '#F8500A', background: 'rgba(232,184,75,0.08)', border: '1px solid rgba(232,184,75,0.22)', borderRadius: 8, padding: '8px 10px', marginBottom: 20, textAlign: 'center' },
  label: { fontSize: 10.5, letterSpacing: '0.14em', textTransform: 'uppercase', color: '#8A93A3', fontWeight: 700, display: 'block', marginBottom: 7 },
  input: { width: '100%', padding: '12px 14px', borderRadius: 10, background: '#0B0E14', border: '1px solid #2a3240', color: '#fff', fontSize: 14, outline: 'none' },
  err: { fontSize: 12.5, color: '#F2667A', background: 'rgba(242,102,122,0.10)', border: '1px solid rgba(242,102,122,0.25)', borderRadius: 8, padding: '8px 12px', marginTop: 12 },
  btn: { width: '100%', marginTop: 18, padding: '12px', borderRadius: 10, background: 'linear-gradient(90deg,#F8500A,#FF7A1A)', color: '#0B0E14', border: 'none', fontSize: 14, fontWeight: 800, cursor: 'pointer' },
  forgot: { background: 'none', border: 'none', color: '#F8500A', fontSize: 12.5, cursor: 'pointer', textDecoration: 'underline' },
  signupTop: { position: 'fixed', top: 18, right: 20, zIndex: 50, padding: '10px 22px', borderRadius: 10, background: 'linear-gradient(90deg,#F8500A,#FF7A1A)', color: '#0B0E14', border: 'none', fontSize: 13.5, fontWeight: 800, cursor: 'pointer', boxShadow: '0 6px 20px rgba(232,184,75,0.3)' },
  signupInline: { background: 'none', border: 'none', color: '#F8500A', fontSize: 12.5, fontWeight: 700, cursor: 'pointer', textDecoration: 'underline' },
  foot: { fontSize: 10.5, color: '#5a6373', textAlign: 'center', marginTop: 20, lineHeight: 1.5 },
};

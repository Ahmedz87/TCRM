import React, { useState, useEffect, Suspense } from 'react';
import axios from 'axios';
import Dashboard from './Dashboard';
import ForgotPassword from './ForgotPassword';
import { lazyWithReload, ChunkErrorBoundary } from './lazyWithReload';
import tnfxLogo from './assets/tnfx-logo.png';

// Lazily loaded: only needed on specific paths (client-portal users / /register),
// so they get their own chunks and stay out of the admin initial bundle.
const ClientDashboard = lazyWithReload(() => import('./ClientDashboard'));
const RegisterWizard = lazyWithReload(() => import('./RegisterWizard'));

axios.defaults.withCredentials = false;

const API = '/api';

const THEMES: any = {
  dark: {
    '--bg':         '#0b0e14',
    '--bg-main':    '#20252f',
    '--bg-card':    '#2c333e',
    '--bg-input':   '#373f4d',
    '--card':       '#0d1016',
    '--card2':      '#0b0e14',
    '--border':     '#4f596b',
    '--border2':    '#626d80',
    '--text':       '#ffffff',
    '--text2':      '#888888',
    '--text3':      '#555555',
    '--accent':     '#00e5a0',
    '--sidebar-bg': '#2c333e',
  },
  light: {
    '--bg':         '#eef1f6',
    '--bg-main':    '#f4f6fa',
    '--bg-card':    '#ffffff',
    '--bg-input':   '#f0f2f5',
    '--card':       '#ffffff',
    '--card2':      '#f4f6fa',
    '--border':     '#e2e6ed',
    '--border2':    '#d0d5de',
    '--text':       '#20252f',
    '--text2':      '#555555',
    '--text3':      '#888888',
    '--accent':     '#00a572',
    '--sidebar-bg': '#ffffff',
  },
};

function applyTheme(name: string) {
  const vars = THEMES[name];
  if (!vars) return;

  const root = document.documentElement;
  Object.entries(vars).forEach(([k, v]) => root.style.setProperty(k, v as string));
  document.body.style.background = vars['--bg-main'];
  document.body.style.color = vars['--text'];

  let style = document.getElementById('crm-theme-style') as HTMLStyleElement;
  if (!style) {
    style = document.createElement('style');
    style.id = 'crm-theme-style';
    document.head.appendChild(style);
  }

  const b  = vars['--bg-main'];
  const c  = vars['--bg-card'];
  const i  = vars['--bg-input'];
  const bo = vars['--border'];
  const b2 = vars['--border2'];
  const t  = vars['--text'];
  const t2 = vars['--text2'];
  const t3 = vars['--text3'];

  style.textContent = `
    *, *::before, *::after { transition: background-color 0.25s ease, color 0.25s ease, border-color 0.25s ease !important; }

    body { background: ${b} !important; color: ${t} !important; }
    #root { background: ${b} !important; }

    /* Main backgrounds */
    div[style*="background: rgb(10, 12, 16)"],
    div[style*="background: #20252f"] { background: ${b} !important; }

    div[style*="background: rgb(17, 19, 24)"],
    div[style*="background: #2c333e"],
    div[style*="background-color: rgb(17, 19, 24)"] { background: ${c} !important; }

    div[style*="background: rgb(26, 29, 36)"],
    div[style*="background: #373f4d"],
    div[style*="background-color: rgb(26, 29, 36)"] { background: ${i} !important; }

    div[style*="background: rgb(20, 23, 32)"],
    div[style*="background: #2c333e"] { background: ${i} !important; }

    div[style*="background: rgb(13, 15, 20)"],
    div[style*="background: #262c36"] { background: ${b} !important; }

    /* Text colors */
    span[style*="color: rgb(136, 136, 136)"],
    div[style*="color: rgb(136, 136, 136)"] { color: ${t2} !important; }

    span[style*="color: rgb(85, 85, 85)"],
    div[style*="color: rgb(85, 85, 85)"] { color: ${t3} !important; }

    span[style*="color: rgb(255, 255, 255)"],
    div[style*="color: rgb(255, 255, 255)"] { color: ${t} !important; }

    /* Borders */
    div[style*="border: 1px solid rgb(34, 34, 34)"],
    div[style*="border-bottom: 1px solid rgb(34, 34, 34)"],
    div[style*="border-right: 1px solid rgb(34, 34, 34)"],
    div[style*="border-top: 1px solid rgb(34, 34, 34)"] { border-color: ${bo} !important; }

    div[style*="border: 1px solid rgb(51, 51, 51)"],
    div[style*="border-bottom: 1px solid rgb(51, 51, 51)"] { border-color: ${b2} !important; }

    /* Inputs */
    input, textarea, select {
      background: ${i} !important;
      color: ${t} !important;
      border-color: ${b2} !important;
    }

    /* Table rows */
    tr[style*="background: transparent"],
    td { color: ${t} !important; }

    /* Table hover */
    tr:hover td { background: ${i} !important; }
  `;
}

function ForcePasswordChange({ currentPassword, onDone, onLogout, isAr }: any) {
  const [np, setNp] = useState('');
  const [cp, setCp] = useState('');
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setErr('');
    if (np.length < 8) { setErr(isAr ? 'كلمة المرور 8 أحرف على الأقل' : 'Password must be at least 8 characters'); return; }
    if (np !== cp)     { setErr(isAr ? 'كلمتا المرور غير متطابقتين' : 'Passwords do not match'); return; }
    setBusy(true);
    try {
      const token = localStorage.getItem('token');
      await axios.post(`${API}/auth/change-password`,
        { current_password: currentPassword, new_password: np },
        { headers: { Authorization: `Bearer ${token}` } });
      onDone();
    } catch (e: any) {
      setErr(e?.response?.data?.detail || 'Could not change password');
    }
    setBusy(false);
  };
  const inp: any = { width:'100%', padding:'10px 14px', background:'var(--bg-input,#373f4d)', border:'1px solid var(--border2,#626d80)', borderRadius:8, color:'var(--text,#fff)', fontSize:14, outline:'none', boxSizing:'border-box' };
  return (
    <div style={{ minHeight:'100vh', background:'var(--bg-main,#20252f)', display:'flex', alignItems:'center', justifyContent:'center', fontFamily:'sans-serif', direction: isAr?'rtl':'ltr' }}>
      <div style={{ background:'var(--bg-card,#2c333e)', border:'1px solid var(--border,#4f596b)', borderRadius:16, padding:40, width:400 }}>
        <div style={{ fontSize:18, fontWeight:700, color:'var(--accent,#00e5a0)', marginBottom:6 }}>{isAr ? 'تعيين كلمة مرور جديدة' : 'Set a new password'}</div>
        <div style={{ fontSize:12, color:'var(--text2,#888)', marginBottom:22 }}>{isAr ? 'لأمانك، يجب تغيير كلمة المرور المؤقتة قبل المتابعة.' : 'For your security, you must change the temporary password before continuing.'}</div>
        <div style={{ marginBottom:16 }}>
          <div style={{ fontSize:11, color:'var(--text2,#888)', marginBottom:6 }}>{isAr ? 'كلمة المرور الجديدة' : 'NEW PASSWORD'}</div>
          <input type="password" value={np} onChange={e => setNp(e.target.value)} placeholder="••••••••" style={inp} />
        </div>
        <div style={{ marginBottom:22 }}>
          <div style={{ fontSize:11, color:'var(--text2,#888)', marginBottom:6 }}>{isAr ? 'تأكيد كلمة المرور' : 'CONFIRM PASSWORD'}</div>
          <input type="password" value={cp} onChange={e => setCp(e.target.value)} onKeyDown={e => e.key==='Enter'&&submit()} placeholder="••••••••" style={inp} />
        </div>
        {err && <div style={{ color:'#ff4d4d', fontSize:13, marginBottom:16, textAlign:'center' }}>{err}</div>}
        <button onClick={submit} disabled={busy} style={{ width:'100%', padding:13, background:'var(--accent,#00e5a0)', border:'none', borderRadius:8, color:'#20252f', fontSize:14, fontWeight:700, cursor:'pointer' }}>
          {busy ? '...' : (isAr ? 'حفظ ومتابعة' : 'Save & continue')}
        </button>
        <button onClick={onLogout} style={{ width:'100%', marginTop:8, padding:10, background:'transparent', border:'1px solid var(--border2,#626d80)', borderRadius:8, color:'var(--text2,#888)', fontSize:12, cursor:'pointer' }}>
          {isAr ? 'تسجيل الخروج' : 'Log out'}
        </button>
      </div>
    </div>
  );
}

export default function App() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [user, setUser] = useState<any>(null);
  const [booting, setBooting] = useState(true);   // restoring session from stored token
  const [showForgot, setShowForgot] = useState(false);
  const [lang, setLang] = useState('en');
  const [theme, setTheme] = useState(() => localStorage.getItem('crm_theme') || 'dark');

  const isAr = lang === 'ar';

  useEffect(() => { applyTheme(theme); localStorage.setItem('crm_theme', theme); }, [theme]);

  // Keep the user logged in across page refreshes: if a token is stored, validate it and restore the session.
  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) { setBooting(false); return; }
    axios.get(`${API}/auth/me`, { headers: { Authorization: `Bearer ${token}` } })
      .then(res => { setUser(res.data); localStorage.setItem('canReassign', res.data?.can_reassign_agent ? '1' : ''); localStorage.setItem('userRole', res.data?.role || ''); })
      .catch(() => { localStorage.removeItem('token'); localStorage.removeItem('userName'); })
      .finally(() => setBooting(false));
  }, []);

  const cycleTheme = () => setTheme(t => t === 'dark' ? 'light' : 'dark');

  const login = async () => {
    setLoading(true); setError('');
    try {
      const form = new URLSearchParams();
      form.append('username', email);
      form.append('password', password);
      const res = await axios.post(`${API}/auth/login`, form);
      localStorage.setItem('token', res.data.access_token);
      localStorage.setItem('userName', res.data.user?.full_name || email);
      localStorage.setItem('canReassign', res.data.user?.can_reassign_agent ? '1' : '');
      localStorage.setItem('userRole', res.data.user?.role || '');
      setUser(res.data.user);
    } catch {
      setError('Invalid email or password');
    }
    setLoading(false);
  };

  // public self-registration (tnfx.co "Register" -> /register) — no login required
  const _p = window.location.pathname.replace(/\/+$/, '');
  if (_p === '/register' || window.location.hash === '#register') return (
    <ChunkErrorBoundary><Suspense fallback={<div style={{minHeight:'100vh',display:'flex',alignItems:'center',justifyContent:'center',background:'var(--bg,#0b0e14)',color:'var(--text2,#888)'}}>Loading…</div>}>
      <RegisterWizard />
    </Suspense></ChunkErrorBoundary>
  );

  if (booting) return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--bg,#0b0e14)', color: 'var(--text2,#888)', fontSize: 14 }}>
      Loading…
    </div>
  );

  if (user && user.must_change_password) return (
    <ForcePasswordChange
      currentPassword={password}
      isAr={isAr}
      onDone={() => setUser({ ...user, must_change_password: false })}
      onLogout={() => { setUser(null); localStorage.removeItem('token'); }}
    />
  );

  // CLIENT portal: same login URL, but a client email lands on their own dashboard
  if (user && (user.user_type === 'client' || user.role === 'client')) {
    const logout = () => { setUser(null); localStorage.removeItem('token'); localStorage.removeItem('userName'); };
    return (
      <div style={{ minHeight: '100vh', background: 'var(--bg-main,#14161d)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 20px', borderBottom: '1px solid var(--border,#353c49)', background: '#1c1f28' }}>
          <img src={tnfxLogo} alt="TNFX" style={{ height: 24, width: 'auto', display: 'block' }} />
          <span style={{ fontSize: 13, color: '#cfd6e0' }}>Client Portal</span>
          <span style={{ marginLeft: 'auto', fontSize: 12, color: '#9aa3b2' }}>{user.full_name} · #{user.login}</span>
          <button onClick={logout} style={{ padding: '6px 14px', background: '#262c36', border: '1px solid var(--border2,#626d80)', borderRadius: 8, color: '#cfd6e0', fontSize: 12, cursor: 'pointer' }}>Log out</button>
        </div>
        <div style={{ padding: 16 }}>
          <ChunkErrorBoundary><Suspense fallback={<div style={{color:'var(--text2,#888)',padding:24}}>Loading…</div>}>
            <ClientDashboard user={user} />
          </Suspense></ChunkErrorBoundary>
        </div>
      </div>
    );
  }

  if (user) return (
    <>

      <Dashboard
        user={user}
        onLogout={() => { setUser(null); localStorage.removeItem('token'); localStorage.removeItem('adminToken'); }}
        lang={lang}
        onLangChange={setLang}
        theme={theme}
        onThemeChange={cycleTheme}
      />
      {user.impersonating && (
        <div style={{ position:'fixed', left:0, right:0, bottom:0, zIndex:99999, display:'flex', alignItems:'center',
                      justifyContent:'center', gap:14, flexWrap:'wrap', padding:'9px 16px',
                      background:'linear-gradient(90deg,#F8500A,#FF7A1A)', color:'#fff', fontSize:13, fontWeight:700,
                      boxShadow:'0 -4px 20px rgba(0,0,0,0.35)' }}>
          <span>👁 Viewing the CRM as <b>{user.full_name}</b> ({(user.role||'').replace('_',' ')}) — read-only preview.</span>
          <button onClick={() => {
            const admin = localStorage.getItem('adminToken');
            if (admin) { localStorage.setItem('token', admin); localStorage.removeItem('adminToken'); }
            window.location.reload();
          }} style={{ padding:'5px 16px', borderRadius:8, border:'1px solid rgba(255,255,255,0.6)',
                      background:'rgba(255,255,255,0.16)', color:'#fff', fontSize:12.5, fontWeight:800, cursor:'pointer' }}>
            ✕ Exit preview
          </button>
        </div>
      )}
    </>
  );

  return (
    <div style={{ minHeight:'100vh', background:'var(--bg-main,#20252f)', display:'flex', alignItems:'center', justifyContent:'center', fontFamily:'sans-serif', direction: isAr?'rtl':'ltr' }}>

      {/* top-right Sign up (always visible) */}
      <button onClick={()=>{ window.location.href='/register'; }}
        style={{ position:'fixed', top:18, right:20, zIndex:50, padding:'10px 20px', background:'var(--accent,#00e5a0)', border:'none', borderRadius:10, color:'#0b0e14', fontSize:13.5, fontWeight:800, cursor:'pointer', boxShadow:'0 6px 20px rgba(0,229,160,0.3)' }}>
        {isAr ? 'إنشاء حساب' : 'Sign up'}
      </button>

      {showForgot && <ForgotPassword scope="staff" isAr={isAr} onClose={()=>setShowForgot(false)} onDone={(id)=>{ setEmail(id); setError(''); }} />}

      <div style={{ background:'var(--bg-card,#2c333e)', border:'1px solid var(--border,#4f596b)', borderRadius:16, padding:40, width:400 }}>
        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:32 }}>
          <div>
            <img src={tnfxLogo} alt="TNFX" style={{ height:38, width:'auto', display:'block' }} />
            <div style={{ fontSize:12, color:'var(--text2,#888)', marginTop:8 }}>Risk Intelligence Platform</div>
          </div>
          <button onClick={() => setLang(isAr?'en':'ar')} style={{ background:'var(--bg-input,#373f4d)', border:'1px solid var(--border2,#626d80)', borderRadius:8, color:'var(--text2,#888)', padding:'6px 12px', cursor:'pointer', fontSize:12 }}>
            {isAr?'EN':'AR'}
          </button>
        </div>
        <div style={{ marginBottom:16 }}>
          <div style={{ fontSize:11, color:'var(--text2,#888)', marginBottom:6 }}>EMAIL</div>
          <input type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="Enter your email"
            style={{ width:'100%', padding:'10px 14px', background:'var(--bg-input,#373f4d)', border:'1px solid var(--border2,#626d80)', borderRadius:8, color:'var(--text,#fff)', fontSize:14, outline:'none', boxSizing:'border-box' as any }} />
        </div>
        <div style={{ marginBottom:24 }}>
          <div style={{ fontSize:11, color:'var(--text2,#888)', marginBottom:6 }}>PASSWORD</div>
          <input type="password" value={password} onChange={e => setPassword(e.target.value)} onKeyDown={e => e.key==='Enter'&&login()} placeholder="Enter your password"
            style={{ width:'100%', padding:'10px 14px', background:'var(--bg-input,#373f4d)', border:'1px solid var(--border2,#626d80)', borderRadius:8, color:'var(--text,#fff)', fontSize:14, outline:'none', boxSizing:'border-box' as any }} />
        </div>
        {error && <div style={{ color:'#ff4d4d', fontSize:13, marginBottom:16, textAlign:'center' }}>{error}</div>}
        <button onClick={login} disabled={loading} style={{ width:'100%', padding:13, background:'var(--brand,#F8500A)', border:'none', borderRadius:8, color:'#fff', fontSize:14, fontWeight:700, cursor:'pointer' }}>
          {loading?'...':isAr?'دخول':'LOGIN'}
        </button>
        <button onClick={login} style={{ width:'100%', marginTop:8, padding:10, background:'transparent', border:'1px solid var(--border2,#626d80)', borderRadius:8, color:'var(--text2,#888)', fontSize:12, cursor:'pointer' }}>
          ⚡ Quick demo access
        </button>
        <div style={{ textAlign:'center', marginTop:12 }}>
          <button onClick={()=>setShowForgot(true)} style={{ background:'none', border:'none', color:'var(--accent,#00e5a0)', fontSize:12.5, cursor:'pointer', textDecoration:'underline' }}>
            {isAr ? 'نسيت كلمة المرور؟' : 'Forgot password?'}
          </button>
        </div>
        <div style={{ borderTop:'1px solid var(--border,#4f596b)', margin:'18px 0 12px' }} />
        <div style={{ textAlign:'center', fontSize:12, color:'var(--text2,#888)', marginBottom:8 }}>{isAr?'ليس لديك حساب بعد؟':"New to TNFX?"}</div>
        <button onClick={()=>{ window.location.href='/register'; }} style={{ width:'100%', padding:13, background:'transparent', border:'1px solid var(--accent,#00e5a0)', borderRadius:8, color:'var(--accent,#00e5a0)', fontSize:14, fontWeight:700, cursor:'pointer' }}>
          {isAr?'افتح حساب تداول جديد ←':'Open a trading account →'}
        </button>
      </div>
    </div>
  );
}

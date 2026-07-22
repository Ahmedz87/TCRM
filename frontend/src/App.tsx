import React, { useState, useEffect, Suspense } from 'react';
import axios from 'axios';
import Dashboard from './Dashboard';
import ForgotPassword from './ForgotPassword';
import { lazyWithReload, ChunkErrorBoundary } from './lazyWithReload';
import { LangContext } from './adminI18n';
import { enableLightEngine, disableLightEngine } from './lightTheme';
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
    '--bg-input':   '#eef1f5',
    '--card':       '#ffffff',
    '--card2':      '#f4f6fa',
    '--border':     '#dfe4ec',
    '--border2':    '#c8cfda',
    '--text':       '#1c2434',
    '--text2':      '#5b6472',
    '--text3':      '#8a94a4',
    '--accent':     '#00a572',
    '--sidebar-bg': '#2c333e',   /* sidebar/topbar stay dark in light mode (.keep-dark) */
  },
};

// ---------------------------------------------------------------------------
// LIGHT-THEME REMAP. Curated dark -> light values for the app's core palette.
// These feed the runtime engine in lightTheme.ts, which rewrites EVERY inline
// style in light mode: exact table hit first, HSL algorithm for anything else
// (rgba, gradients, hover handlers, unknown hexes). Colours NOT listed and not
// caught by the algorithm keep their value (dark text on coloured buttons,
// brand orange, coloured CTAs). Elements inside a `.keep-dark` container
// (sidebar + topbar + dashboard KPI row) are never touched.
// ---------------------------------------------------------------------------
const LIGHT_TEXT: Record<string, string> = {
  // bright / near-white text -> ink
  '#fff':'#1c2434', '#ffffff':'#1c2434', '#eee':'#1c2434', '#e6e9ef':'#1c2434',
  '#e8edf2':'#1c2434', '#e8e8e8':'#1c2434', '#e8ecf2':'#1c2434', '#e7ecf3':'#242e40',
  '#e7eef7':'#242e40', '#e0e0e0':'#242e40', '#e0e5ec':'#242e40', '#dfe3ea':'#242e40',
  '#d5dbe5':'#2c3648', '#eef1f6':'#242e40', '#eafff7':'#067a54',
  // light-grey secondary -> dark grey
  '#cfd6e4':'#3d4757', '#cfd6e0':'#3d4757', '#cdd4de':'#3d4757', '#cdd3dc':'#3d4757',
  '#cdd5e0':'#3d4757', '#c4ccd8':'#434e5f', '#c7ccd6':'#434e5f', '#c0c4cc':'#434e5f',
  '#ccc':'#4a5464', '#bcc3cf':'#4a5464', '#bbb':'#4a5464', '#b8c0cc':'#4a5464',
  '#b9c2cf':'#4a5464', '#ddd':'#4a5464', '#aeb6c2':'#525c6c', '#aeb8c8':'#525c6c',
  '#aab4c4':'#525c6c', '#aab2c0':'#525c6c', '#aaa':'#5b6472', '#9fb0c0':'#5b6472',
  // mid-grey secondary -> medium grey
  '#8a93a5':'#5b6472', '#8a93a3':'#5b6472', '#8b93a1':'#5b6472', '#8a95a7':'#5b6472',
  '#9aa3b3':'#61697a', '#9aa3b2':'#61697a', '#9bb4d4':'#52719c', '#999':'#6a7382',
  '#9aa':'#6a7382', '#aab':'#6a7382', '#888':'#6a7382', '#889':'#6a7382',
  '#88a':'#6a7382', '#8aa':'#6a7382', '#778':'#707a89', '#7c8798':'#707a89',
  '#7a8294':'#707a89', '#7a8392':'#707a89', '#7a8696':'#707a89', '#7d8694':'#707a89',
  '#7e8a99':'#707a89', '#7c8db5':'#5a6a8f',
  // dark muted (tertiary on a dark bg) -> light muted
  '#777':'#848e9e', '#667':'#848e9e', '#666':'#9099a8', '#626d80':'#97a1b1',
  '#5a6373':'#848e9e', '#5d6675':'#848e9e', '#5a6470':'#8b95a5', '#5a6472':'#8b95a5',
  '#5b6679':'#8b95a5', '#566':'#8b95a5', '#555':'#9099a8', '#556':'#9099a8',
  '#4a5261':'#9099a8', '#445':'#9099a8', '#444':'#9099a8',
  // greens
  '#00e5a0':'#008a61', '#3ad29f':'#0e8a68', '#7fe9c0':'#1d9a72', '#7fe0a8':'#1d9a5f',
  '#34d399':'#0c9464', '#37d67a':'#16a34a', '#22c55e':'#16a34a', '#25d366':'#1aa851',
  '#2dd4bf':'#0d9488', '#5eead4':'#0d9488', '#9fb':'#20885f', '#cfe':'#20885f',
  // ambers / oranges / golds
  '#ffaa00':'#b57900', '#ffb454':'#bf7c0a', '#ffd479':'#a97e12', '#ffbf47':'#a97e12',
  '#ffc14d':'#a97e12', '#ffcc66':'#a97e12', '#e8b84b':'#9c7c1e', '#c39a1f':'#96751a',
  '#caa53a':'#96751a', '#ff8c00':'#c26400', '#ff8800':'#c26400', '#ff8c42':'#cf6220',
  '#ff9d76':'#cc5f2e', '#ff8866':'#d4552e', '#ffee00':'#9c8a00',
  // blues
  '#00aaff':'#0077c2', '#0a84ff':'#0a6cd6', '#4d9fff':'#1d6fd8', '#4da8ff':'#1d6fd8',
  '#4ea1ff':'#1d6fd8', '#5b9dff':'#1d6fd8', '#5fb0ff':'#2d6cdf', '#79b8ff':'#2d6cdf',
  '#7fb0ff':'#2d6cdf', '#7fa8ff':'#3b6fd4', '#9ec1ff':'#3b6fd4', '#7fd1ff':'#0077c2',
  '#8fcfe6':'#2b8cb0', '#38bdf8':'#0284c7', '#2f9bd0':'#1d7fb5', '#a5b4fc':'#6473e8',
  // reds / pinks
  '#ff4d4d':'#d92d2d', '#ff4d4f':'#d92d2d', '#ff5d6c':'#d5334a', '#ff5c6c':'#d5334a',
  '#f0556a':'#cc2f47', '#e5484d':'#d33338', '#ff8888':'#d04747', '#ff8a93':'#cf4653',
  '#ff7a7a':'#d04747', '#ff8a8a':'#d04747', '#ff6a6a':'#d04747', '#ff6b6b':'#d04747',
  '#e07a7a':'#c65555', '#ff2d78':'#d61f63', '#ff8ac8':'#d152a0',
  // purples
  '#9966ff':'#7c3aed', '#cc88ff':'#9333ea', '#b794ff':'#8b5cf6', '#b08cff':'#8b5cf6',
  '#c4b5fd':'#7c62d6', '#9b8cff':'#7c5ce8',
  // brand orange: self-mapped so the algorithmic vivid-accent darkening never touches it
  '#f8500a':'#f8500a', '#ff6a1a':'#ff6a1a',
};

const LIGHT_BG: Record<string, string> = {
  // main surfaces
  '#20252f':'#eef1f6', '#2c333e':'#ffffff', '#262c36':'#f2f4f8', '#373f4d':'#eef1f5',
  '#4f596b':'#dfe4ec', '#5a6470':'#d5dbe5', '#626d80':'#d5dbe5',
  // deep panels / wells (incl. legacy pre-restyle values still matched by old rules)
  '#0b0e14':'#f4f6fa', '#0a0c10':'#f4f6fa', '#0a0e14':'#f4f6fa', '#080a0f':'#f4f6fa',
  '#0d1016':'#f7f9fc', '#0d1117':'#f7f9fc', '#0d0f14':'#f4f6fa', '#101319':'#f7f9fc',
  '#0b1220':'#f7f9fc', '#11141a':'#f7f9fc', '#111318':'#ffffff', '#12161f':'#f7f9fc',
  '#141720':'#eef1f5', '#161c24':'#f7f9fc', '#161b25':'#f7f9fc', '#1a1d24':'#eef1f5',
  '#1a1f2b':'#f7f9fc', '#1b212b':'#f7f9fc', '#1c1f28':'#f7f9fc', '#1c2231':'#f7f9fc',
  '#1a2030':'#f4f6fa', '#1b2027':'#f4f6fa', '#1c2027':'#f4f6fa', '#1c2129':'#f4f6fa',
  '#1c2230':'#f4f6fa', '#1e2230':'#f7f9fc', '#1f242c':'#f4f6fa', '#1f242d':'#f4f6fa',
  '#222b38':'#eef1f5', '#222936':'#eef1f5', '#222831':'#eef1f5', '#23282f':'#eef1f5',
  '#23303a':'#eef1f5', '#2a313c':'#eef1f5', '#2a2f3a':'#eef1f5', '#333b49':'#e3e8f0',
  '#3a4250':'#e3e8f0', '#3a4252':'#e3e8f0', '#4a5160':'#e3e8f0',
  // tinted panels (badge / alert backgrounds)
  '#0a1a3a':'#e3edff', '#10233a':'#e3edff', '#1a2440':'#e8eefc', '#0a1a2a':'#e3edf8',
  '#0e3a2a':'#e2f6ec', '#16241d':'#e6f5ec', '#0b2018':'#e6f5ec', '#1c2a22':'#e6f5ec',
  '#1f5c43':'#bfe6d4', '#3a2a0e':'#faf0dc', '#3a0e0e':'#fbe5e5', '#1a0a0a':'#fbe5e5',
  '#3a2530':'#f9e6ec',
};

const LIGHT_BORDER: Record<string, string> = {
  '#4f596b':'#d9dee8', '#626d80':'#c8cfda', '#373f4d':'#dfe4ec', '#2f3a48':'#dde2ea',
  '#232d3a':'#e3e7ee', '#3a434f':'#d9dee8', '#2a3142':'#e0e5ee', '#3a4252':'#d5dbe6',
  '#3a4250':'#d5dbe6', '#3a4350':'#d5dbe6', '#2c333e':'#dfe4ec', '#232a38':'#e3e7ee',
  '#2a3240':'#dee3ec', '#2a3340':'#dee3ec', '#333b46':'#d5dbe6', '#313945':'#d5dbe6',
  '#2a2f3a':'#dee3ec', '#1e2230':'#e3e7ee', '#1a1f2b':'#e3e7ee', '#3a2530':'#f0d5de',
  '#222':'#dfe4ec', '#333':'#d5dbe6', '#20252f':'#e3e7ee', '#262c36':'#e3e7ee',
  '#1f5c43':'#9fd4bc',
  '#00e5a0':'#00a577', '#ff4d4d':'#e05252', '#ffaa00':'#cf8d00', '#00aaff':'#2196d9',
  '#ff8800':'#d97706', '#ff5d6c':'#d5334a',
};


// Excludes the element itself and anything inside a .keep-dark container
// (sidebar / topbar / dashboard KPI row keep the dark look in light mode).
const KD = ':not(.keep-dark):not(.keep-dark *)';

function buildLightCss(vars: any): string {
  const b  = vars['--bg-main'];
  const i  = vars['--bg-input'];
  const b2 = vars['--border2'];
  const t  = vars['--text'];
  const d  = THEMES.dark;

  return `
    *, *::before, *::after { transition: background-color 0.25s ease, color 0.25s ease, border-color 0.25s ease, box-shadow 0.25s ease !important; }

    body { background: ${b} !important; color: ${t} !important; }
    #root { background: ${b} !important; }

    /* KPI numbers render BLACK in the light theme (the dark palette's neon
       green/blue/purple wash out on white). Dark theme keeps them coloured. */
    .kpi-num${KD} { color: #0b0e14 !important; }

    /* Elevation (set by the runtime engine): light themes read depth from
       shadows, not borders. 'card' = converted panels, 'pop' = floating UI. */
    [data-lt="card"] { box-shadow: 0 1px 2px rgba(16,24,40,0.05), 0 8px 24px rgba(16,24,40,0.07); }
    [data-lt="pop"]  { box-shadow: 0 2px 8px rgba(16,24,40,0.08), 0 14px 36px rgba(16,24,40,0.18); }

    /* Inputs */
    input${KD}, textarea${KD}, select${KD} {
      background: ${i} !important;
      color: ${t} !important;
      border-color: ${b2} !important;
    }
    input${KD}:focus, textarea${KD}:focus, select${KD}:focus {
      border-color: #35a983 !important;
      box-shadow: 0 0 0 3px rgba(0,165,114,0.14) !important;
      outline: none !important;
    }
    input${KD}::placeholder, textarea${KD}::placeholder { color: #a5aebc !important; }

    ::selection { background: rgba(0,165,114,0.20); }

    /* Native date/time pickers follow the theme (placeholder + calendar icon visibility) */
    input[type="date"]${KD}, input[type="datetime-local"]${KD}, input[type="time"]${KD}, input[type="month"]${KD}, input[type="week"]${KD} {
      color-scheme: light !important;
    }

    /* Tables */
    td${KD} { color: ${t} !important; }
    tr:hover td${KD} { background: ${i} !important; }

    /* Dark zones float above the light page */
    .kd-side { box-shadow: 0 0 20px rgba(16,24,40,0.22); border-right-color: transparent !important; }
    .kd-top  { box-shadow: 0 2px 12px rgba(16,24,40,0.10); }
    .kd-kpi > div { box-shadow: 0 6px 18px rgba(16,24,40,0.16); }

    /* Light scrollbars (index.css ships the dark ones) */
    *${KD} { scrollbar-color: #c3cad6 transparent; }
    ::-webkit-scrollbar-thumb { background: #c3cad6; border-radius: 6px; border: 2px solid transparent; background-clip: content-box; }
    ::-webkit-scrollbar-thumb:hover { background: #aab3c2; background-clip: content-box; border: 2px solid transparent; }

    /* .keep-dark zones (sidebar + topbar + dashboard KPI row) keep the full dark palette */
    .keep-dark {
      --bg: ${d['--bg']}; --bg-main: ${d['--bg-main']}; --bg-card: ${d['--bg-card']}; --bg-input: ${d['--bg-input']};
      --card: ${d['--card']}; --card2: ${d['--card2']}; --border: ${d['--border']}; --border2: ${d['--border2']};
      --text: ${d['--text']}; --text2: ${d['--text2']}; --text3: ${d['--text3']}; --accent: ${d['--accent']};
      color-scheme: dark;
    }
    .keep-dark, .keep-dark * { scrollbar-color: #4f596b transparent; }
    .keep-dark ::-webkit-scrollbar-thumb { background: #4f596b; border-radius: 6px; border: 2px solid transparent; background-clip: content-box; }
    .keep-dark input, .keep-dark textarea, .keep-dark select {
      background: ${d['--bg-input']} !important; color: ${d['--text']} !important; border-color: ${d['--border2']} !important;
    }
  `;
}

function buildDarkCss(vars: any): string {
  const b  = vars['--bg-main'];
  const c  = vars['--bg-card'];
  const i  = vars['--bg-input'];
  const bo = vars['--border'];
  const b2 = vars['--border2'];
  const t  = vars['--text'];
  const t2 = vars['--text2'];
  const t3 = vars['--text3'];

  return `
    *, *::before, *::after { transition: background-color 0.25s ease, color 0.25s ease, border-color 0.25s ease !important; }

    body { background: ${b} !important; color: ${t} !important; }
    #root { background: ${b} !important; }

    /* Legacy (pre-restyle) hardcoded backgrounds -> current dark palette */
    div[style*="background: rgb(10, 12, 16)"] { background: ${b} !important; }
    div[style*="background: rgb(17, 19, 24)"],
    div[style*="background-color: rgb(17, 19, 24)"] { background: ${c} !important; }
    div[style*="background: rgb(26, 29, 36)"],
    div[style*="background-color: rgb(26, 29, 36)"] { background: ${i} !important; }
    div[style*="background: rgb(20, 23, 32)"] { background: ${i} !important; }
    div[style*="background: rgb(13, 15, 20)"] { background: ${b} !important; }

    /* Legacy borders */
    div[style*="border: 1px solid rgb(34, 34, 34)"],
    div[style*="border-bottom: 1px solid rgb(34, 34, 34)"],
    div[style*="border-right: 1px solid rgb(34, 34, 34)"],
    div[style*="border-top: 1px solid rgb(34, 34, 34)"] { border-color: ${bo} !important; }
    div[style*="border: 1px solid rgb(51, 51, 51)"],
    div[style*="border-bottom: 1px solid rgb(51, 51, 51)"] { border-color: ${b2} !important; }

    /* Text greys stay on the palette */
    span[style*="color: rgb(136, 136, 136)"],
    div[style*="color: rgb(136, 136, 136)"] { color: ${t2} !important; }
    span[style*="color: rgb(85, 85, 85)"],
    div[style*="color: rgb(85, 85, 85)"] { color: ${t3} !important; }
    span[style*="color: rgb(255, 255, 255)"],
    div[style*="color: rgb(255, 255, 255)"] { color: ${t} !important; }

    /* Inputs */
    input, textarea, select {
      background: ${i} !important;
      color: ${t} !important;
      border-color: ${b2} !important;
    }

    /* Native date/time pickers: force the scheme to match the theme so the mm/dd/yyyy placeholder text
       and the calendar icon stay visible on the dark input background (fixes the custom-period date
       filter being invisible on the Transactions / Sales / IB / Finance / Monthly-report pages). */
    input[type="date"], input[type="datetime-local"], input[type="time"], input[type="month"], input[type="week"] {
      color-scheme: dark !important;
    }

    /* Table rows */
    tr[style*="background: transparent"],
    td { color: ${t} !important; }

    /* Table hover */
    tr:hover td { background: ${i} !important; }
  `;
}

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

  style.textContent = name === 'light' ? buildLightCss(vars) : buildDarkCss(vars);

  // Runtime engine: in light mode every inline style (incl. rgba, gradients,
  // JS hover handlers, SVG) is rewritten live via a MutationObserver.
  if (name === 'light') enableLightEngine({ text: LIGHT_TEXT, bg: LIGHT_BG, border: LIGHT_BORDER });
  else disableLightEngine();
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

// partner1.tnfx.co serves this SAME build in PARTNER MODE: the admin app is replaced by the
// standalone IB portal (own login/registration, scope='ib' tokens). One build, two sites.
const IS_PARTNER_SITE = window.location.hostname.toLowerCase().startsWith('partner');
const PartnerGate = React.lazy(() => import('./PartnerGate'));

export default function App() {
  // Partner site: render ONLY the IB portal — before any admin hooks/state.
  if (IS_PARTNER_SITE) {
    return <React.Suspense fallback={<div style={{ color:'#888', padding:40 }}>Loading…</div>}><PartnerGate /></React.Suspense>;
  }
  return <AdminApp />;
}

function AdminApp() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [user, setUser] = useState<any>(null);
  const [booting, setBooting] = useState(true);   // restoring session from stored token
  const [showForgot, setShowForgot] = useState(false);
  const [lang, setLang] = useState(() => localStorage.getItem('crm_lang') || 'en');
  const [theme, setTheme] = useState(() => localStorage.getItem('crm_theme') || 'dark');

  const isAr = lang === 'ar';

  useEffect(() => { applyTheme(theme); localStorage.setItem('crm_theme', theme); }, [theme]);
  // Persist language so the choice sticks across refresh and any widget (e.g. PowerDialer,
  // launched outside the prop tree) can read it via localStorage. Also set the document dir
  // so the whole app flips RTL in Arabic. (i18n rollout — ticket #189 follow-up.)
  useEffect(() => {
    localStorage.setItem('crm_lang', lang);
    document.documentElement.setAttribute('dir', isAr ? 'rtl' : 'ltr');
    document.documentElement.setAttribute('lang', lang);
  }, [lang, isAr]);

  // Keep the user logged in across page refreshes: if a token is stored, validate it and restore the session.
  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) { setBooting(false); return; }
    axios.get(`${API}/auth/me`, { headers: { Authorization: `Bearer ${token}` } })
      .then(res => { setUser(res.data); localStorage.setItem('canReassign', res.data?.can_reassign_agent ? '1' : ''); localStorage.setItem('userRole', res.data?.role || ''); localStorage.setItem('isTeamLead', res.data?.is_team_lead ? '1' : ''); localStorage.setItem('scopeSections', (res.data?.scope_sections || []).join(',')); })
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
    <LangContext.Provider value={lang}>

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
    </LangContext.Provider>
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

import React, { useState, useEffect } from 'react';
import { apiGet } from './api';
import Dashboard from './pages/Dashboard';
import Accounts from './pages/Accounts';
import Funds from './pages/Funds';
import Loyalty from './pages/Loyalty';
import Profile from './pages/Profile';
import Support from './pages/Support';
import NewAccountWizard from './NewAccountWizard';
import DepositWizard from './DepositWizard';
import { KycBanner, KycWizard } from './Kyc';
import TradingViewPage from './pages/TradingViewPage';
import ToolPage from './pages/ToolPage';
import Autochartist from './pages/Autochartist';
import CopyTrading from './pages/CopyTrading';
import BonusPage from './Bonus';
import MyTickets from './Ticket';
import PortalChat from './PortalChat';
import tnfxLogo from './assets/tnfx-logo.png';

// ── Theme (light/dark) ─────────────────────────────────────────────
// The portal's components use hardcoded hex inline styles (no CSS vars), so we
// theme GLOBALLY by injecting a <style> that maps each dark hex to a light one
// via attribute-substring selectors on the rendered inline styles. Dark = the
// current look (no overrides). Accent gold (#e8b84b) stays in both themes.
// Maps every dark surface/border/text hex found across portal/src.
const LIGHT_MAP: [string, string][] = [
  // backgrounds (darkest -> lightest page chrome)
  ['#0B0E14', '#eef1f6'], ['#0b0e14', '#eef1f6'],
  ['#0d1016', '#ffffff'],
  ['#12161f', '#ffffff'], ['#12161d', '#ffffff'],
  ['#141821', '#f5f7fb'], ['#161b24', '#f5f7fb'], ['#161b25', '#f5f7fb'],
  // cards / panels / inputs
  ['#1A1F2B', '#e3e8f0'], ['#1a1f2b', '#e3e8f0'],
  ['#232a38', '#dfe4ec'], ['#222a38', '#dfe4ec'], ['#2f3a48', '#d2d9e4'],
  ['#2a3240', '#d2d9e4'], ['#2f3848', '#d2d9e4'],
  // text
  ['#fff', '#1a1f2b'], ['#ffffff', '#1a1f2b'],
  ['#E7ECF3', '#1f2733'], ['#e7ecf3', '#1f2733'],
  ['#cdd4de', '#3a4250'], ['#cfd6e2', '#3a4250'], ['#e8edf2', '#1f2733'],
  ['#9aa3b3', '#5a6470'], ['#9aa3b2', '#5a6470'], ['#aab2c0', '#5a6470'], ['#aeb7c2', '#5a6470'],
  ['#8A93A3', '#6b7480'], ['#8a93a3', '#6b7480'],
  ['#7b8794', '#6b7480'], ['#5a6373', '#8a93a3'], ['#5a6470', '#8a93a3'],
];

function applyPortalTheme(name: string) {
  let style = document.getElementById('portal-theme-style') as HTMLStyleElement | null;
  if (!style) {
    style = document.createElement('style');
    style.id = 'portal-theme-style';
    document.head.appendChild(style);
  }
  if (name !== 'light') {           // dark = native look, clear overrides
    style.textContent = '';
    document.body.classList.remove('portal-light');
    document.body.style.background = '#0B0E14';
    document.body.style.color = '#E7ECF3';
    return;
  }
  document.body.classList.add('portal-light');
  // Light: rewrite the hardcoded dark hexes to light ones wherever they appear
  // as background / color / border in an inline style attribute.
  const rules: string[] = [
    'html,body,#root{background:#eef1f6 !important;color:#1a1f2b !important;}',
    '::-webkit-scrollbar-track{background:#e3e8f0 !important;}',
    '::-webkit-scrollbar-thumb{background:#c4ccd8 !important;}',
    // generic smooth transition
    '*{transition:background-color .2s ease,color .2s ease,border-color .2s ease;}',
  ];
  for (const [dark, light] of LIGHT_MAP) {
    // background / background-color
    rules.push(`[style*="background: ${dark}"]{background:${light} !important;}`);
    rules.push(`[style*="background:${dark}"]{background:${light} !important;}`);
    rules.push(`[style*="background-color: ${dark}"]{background-color:${light} !important;}`);
    // text color
    rules.push(`[style*="color: ${dark}"]:not([style*="background"]){color:${light} !important;}`);
    rules.push(`[style*="color:${dark}"]:not([style*="background"]){color:${light} !important;}`);
    // borders
    rules.push(`[style*="solid ${dark}"]{border-color:${light} !important;}`);
  }
  // inputs/selects readable on light
  rules.push('input,textarea,select{background:#ffffff !important;color:#1a1f2b !important;border-color:#d2d9e4 !important;}');
  style.textContent = rules.join('\n');
  document.body.style.background = '#eef1f6';
  document.body.style.color = '#1a1f2b';
}

// responsive: true on phones/narrow screens. Drives the off-canvas drawer + bottom nav.
function useIsMobile(bp = 820) {
  const [m, setM] = useState(() => typeof window !== 'undefined' && window.innerWidth <= bp);
  useEffect(() => {
    const on = () => setM(window.innerWidth <= bp);
    window.addEventListener('resize', on);
    return () => window.removeEventListener('resize', on);
  }, [bp]);
  return m;
}

// grouped nav structure
const GROUPS: { label?: string; items: { key: string; label: string; icon: string }[] }[] = [
  { items: [
    { key: 'dashboard', label: 'Dashboard', icon: '🏠' },
    { key: 'accounts', label: 'Accounts', icon: '📊' },
  ] },
  { label: 'Funds', items: [
    { key: 'deposit', label: 'Deposit', icon: '💳' },
    { key: 'withdraw', label: 'Withdraw', icon: '💸' },
    { key: 'transfer', label: 'Transfer', icon: '🔁' },
    { key: 'transactions', label: 'Transactions', icon: '📜' },
    { key: 'bonus', label: 'Bonus', icon: '🎁' },
  ] },
  { label: 'Trading', items: [
    { key: 'copytrading', label: 'Copy Trading', icon: '🤝' },
    { key: 'autochartist', label: 'Autochartist', icon: '📈' },
    { key: 'tradingcentral', label: 'Trading Central', icon: '🎯' },
    { key: 'charts', label: 'Charts', icon: '📉' },
  ] },
  { items: [
    { key: 'loyalty', label: 'Rewards', icon: '🏆' },
    { key: 'mytickets', label: 'My Tickets', icon: '🎫' },
    { key: 'profile', label: 'Profile', icon: '👤' },
    { key: 'support', label: 'Support', icon: '💬' },
  ] },
];

// mobile thumb-reach bottom bar — the 5 most-used destinations
const BOTTOM_NAV = [
  { key: 'dashboard', label: 'Home', icon: '🏠' },
  { key: 'accounts', label: 'Accounts', icon: '📊' },
  { key: 'deposit', label: 'Deposit', icon: '💳' },
  { key: 'copytrading', label: 'Copy', icon: '🤝' },
  { key: 'profile', label: 'Profile', icon: '👤' },
];

export default function Portal({ onLogout }: { onLogout: () => void }) {
  const mobile = useIsMobile();
  const [active, setActive] = useState('dashboard');
  const [theme, setTheme] = useState<string>(() => localStorage.getItem('portal_theme') || 'dark');
  useEffect(() => { applyPortalTheme(theme); localStorage.setItem('portal_theme', theme); }, [theme]);
  const toggleTheme = () => setTheme(t => (t === 'dark' ? 'light' : 'dark'));
  const [me, setMe] = useState<any>(null);
  const [navOpen, setNavOpen] = useState(false);
  const [kyc, setKyc] = useState<any>({ status: 'verified', verified: true });
  const [overlay, setOverlay] = useState<string>('');
  const [acSection, setAcSection] = useState<'live' | 'signals' | 'models' | 'install'>('signals');
  const AC_SUBS = [
    { k: 'signals', i: '📈', l: 'Opportunities' },
    { k: 'live', i: '🛰️', l: 'Live Tool' },
    { k: 'models', i: '📐', l: 'Models' },
    { k: 'install', i: '📥', l: 'Install & Use' },
  ];

  useEffect(() => {
    apiGet('/portal/me').then(setMe).catch(() => {});
    apiGet('/portal/kyc/status').then((k: any) => k && setKyc(k)).catch(() => {});
  }, []);
  // Auto-update the KYC KPI the moment the AI decides — poll while the status is still being
  // processed (reading docs / finalizing the account), stop once it's a final decision. No refresh needed.
  useEffect(() => {
    const inProgress = ['pending_review', 'under_review', 'submitted', 'in_review'].includes(kyc?.status);
    if (!inProgress) return;
    const t = setInterval(() => {
      apiGet('/portal/kyc/status').then((k: any) => k && setKyc(k)).catch(() => {});
    }, 4000);
    return () => clearInterval(t);
  }, [kyc?.status]);
  const go = (k: string) => { setActive(k); setNavOpen(false); };
  const initials = (me?.name || '?').split(' ').slice(0, 2).map((w: string) => w[0]).join('').toUpperCase();

  // ALREADY-HAVE-AN-ACCOUNT: a blocking popup. Closing it (X or "Log in") signs the client out and
  // sends them back to the login page to use their existing account.
  if (kyc?.status === 'exists') {
    const ea = kyc.existing_account || {};
    const to = [ea.email_masked, ea.phone_masked].filter(Boolean).join(' · ');
    return (
      <div style={{ position: 'fixed', inset: 0, background: 'rgba(7,10,18,0.92)', zIndex: 200, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 18 }}>
        <div style={{ width: 'min(460px,94vw)', background: '#10141c', border: '1px solid #2a3340', borderRadius: 16, padding: 26, position: 'relative', textAlign: 'center' }}>
          <button onClick={onLogout} title="Close" style={{ position: 'absolute', top: 12, right: 14, background: 'none', border: 'none', color: '#7a8597', fontSize: 22, cursor: 'pointer' }}>✕</button>
          <div style={{ fontSize: 38, marginBottom: 8 }}>👤</div>
          <div style={{ fontSize: 19, fontWeight: 800, color: '#fff', marginBottom: 8 }}>You already have an account with us</div>
          <div style={{ fontSize: 13.5, color: '#aab3c2', lineHeight: 1.6, marginBottom: 6 }}>
            Our records show this is you. Please log in to your <b style={{ color: '#fff' }}>existing account</b> instead of creating a new one.
          </div>
          {to && <div style={{ fontSize: 13, color: '#cdd5e0', marginBottom: 14 }}>Registered with <b style={{ color: '#34D399' }}>{to}</b></div>}
          <button onClick={onLogout} style={{ width: '100%', padding: '13px', borderRadius: 11, border: 'none', background: 'linear-gradient(90deg,#3a86ff,#5a9bff)', color: '#fff', fontSize: 14.5, fontWeight: 800, cursor: 'pointer' }}>Log in to my existing account</button>
          <div style={{ fontSize: 11.5, color: '#7a8597', marginTop: 14, lineHeight: 1.5 }}>If this isn't you, contact <a href="mailto:support@tnfx.co" style={{ color: '#F8500A' }}>support@tnfx.co</a></div>
        </div>
      </div>
    );
  }

  const impersonating = (() => { try { return sessionStorage.getItem('tnfx_imp') === '1'; } catch { return false; } })();

  return (
    <div style={S.shell}>
      {impersonating && (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 12, flexWrap: 'wrap', padding: '8px 14px', background: 'linear-gradient(90deg,#7a1020,#a3162e)', color: '#fff', fontSize: 12.5, fontWeight: 700, position: 'sticky', top: 0, zIndex: 150 }}>
          <span>👁 Admin preview — viewing as {me?.name || 'this client'} (read-only). Actions are disabled.</span>
          <button onClick={onLogout} style={{ padding: '4px 12px', borderRadius: 7, border: '1px solid rgba(255,255,255,0.5)', background: 'rgba(255,255,255,0.12)', color: '#fff', fontSize: 12, fontWeight: 800, cursor: 'pointer' }}>Exit preview</button>
        </div>
      )}
      <div style={{ ...S.topbar, ...(mobile ? { padding: '0 12px', gap: 8 } : {}) }}>
        {mobile && <button style={S.burger} onClick={() => setNavOpen(o => !o)} aria-label="Menu">☰</button>}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <img src={tnfxLogo} alt="TNFX" style={{ height: mobile ? 24 : 30, width: 'auto', display: 'block' }} />
          {!mobile && <span style={S.brandSub}>Portal</span>}
        </div>
        <div style={{ flex: 1 }} />
        {me && (
          <div style={S.userBox}>
            {!mobile && (
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: '#fff' }}>{me.name}</div>
                <div style={{ fontSize: 10.5, color: '#8A93A3', textTransform: 'capitalize' }}>{me.tier || 'member'} · {Math.round(me.points || 0).toLocaleString()} pts</div>
              </div>
            )}
            <div style={S.avatar}>{initials}</div>
          </div>
        )}
        {!mobile && (
          <button style={S.themeBtn} onClick={toggleTheme} title={theme === 'dark' ? 'Switch to Light' : 'Switch to Dark'}>
            <span style={{ fontSize: 14 }}>{theme === 'dark' ? '🌙' : '☀️'}</span>
            <span>{theme === 'dark' ? 'Dark' : 'Light'}</span>
          </button>
        )}
        {!mobile && <button style={S.logoutBtn} onClick={onLogout}>Sign out</button>}
      </div>

      <div style={S.body}>
        {/* backdrop behind the mobile drawer */}
        {mobile && navOpen && <div style={S.backdrop} onClick={() => setNavOpen(false)} />}
        <div style={{
          ...S.sidebar,
          ...(mobile ? { position: 'fixed', top: 0, bottom: 0, left: 0, zIndex: 50, width: 264, maxWidth: '82vw',
                         transform: navOpen ? 'translateX(0)' : 'translateX(-100%)', transition: 'transform .25s ease',
                         boxShadow: navOpen ? '4px 0 24px rgba(0,0,0,0.5)' : 'none', overflowY: 'auto' } : {}),
        }}>
          {mobile && (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '4px 8px 12px' }}>
              <img src={tnfxLogo} alt="TNFX" style={{ height: 24, width: 'auto', display: 'block' }} />
              <button style={{ ...S.burger, fontSize: 22 }} onClick={() => setNavOpen(false)} aria-label="Close">✕</button>
            </div>
          )}
          {GROUPS.map((g, gi) => (
            <div key={gi} style={{ marginBottom: 6 }}>
              {g.label && <div style={S.groupLabel}>{g.label}</div>}
              {g.items.map(n => (
                <React.Fragment key={n.key}>
                  <button onClick={() => { go(n.key); if (n.key === 'autochartist') setAcSection('signals'); }} style={{ ...S.navItem, ...(mobile ? { padding: '13px 14px', fontSize: 15 } : {}), ...(active === n.key ? S.navItemActive : {}) }}>
                    <span style={{ fontSize: 16, width: 22, textAlign: 'center' }}>{n.icon}</span>
                    <span>{n.label}</span>
                  </button>
                  {n.key === 'autochartist' && active === 'autochartist' && AC_SUBS.map(sub => (
                    <button key={sub.k} onClick={() => { setAcSection(sub.k as any); setNavOpen(false); }}
                      style={{ ...S.subItem, ...(acSection === sub.k ? S.subItemActive : {}) }}>
                      <span style={{ fontSize: 13, width: 18, textAlign: 'center' }}>{sub.i}</span>
                      <span>{sub.l}</span>
                    </button>
                  ))}
                </React.Fragment>
              ))}
            </div>
          ))}
          <div style={{ flex: 1 }} />
          {/* theme + sign-out live in the drawer on mobile (removed from the cramped topbar) */}
          {mobile && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: '8px 4px' }}>
              <button style={{ ...S.themeBtn, marginLeft: 0, justifyContent: 'center', padding: '11px' }} onClick={toggleTheme}>
                <span style={{ fontSize: 14 }}>{theme === 'dark' ? '🌙' : '☀️'}</span>
                <span>{theme === 'dark' ? 'Dark mode' : 'Light mode'}</span>
              </button>
              <button style={{ ...S.logoutBtn, marginLeft: 0, padding: '11px', textAlign: 'center' }} onClick={onLogout}>Sign out</button>
            </div>
          )}
          <div style={S.sideFoot}>TN-Point Program · TNFX © {new Date().getFullYear()}</div>
        </div>

        <div style={{ ...S.content, ...(mobile ? { maxHeight: 'none', paddingBottom: 72 } : {}) }}>
          {active !== 'autochartist' && (
            <div style={{ padding: mobile ? '12px 12px 0' : '20px 28px 0', maxWidth: 1036, margin: '0 auto' }}>
              <KycBanner status={kyc.status} reason={kyc.reason} existingAccount={kyc.existing_account}
                needFamilyId={kyc.need_family_id} poaHolder={kyc.poa_holder} idApproved={kyc.id_approved}
                onStart={() => setOverlay('kyc')} onLogin={onLogout}
                onRefresh={() => apiGet('/portal/kyc/status').then((k: any) => k && setKyc(k))} />
            </div>
          )}

          {overlay === 'newaccount' && <div style={{ padding: mobile ? 12 : 28 }}><NewAccountWizard onClose={() => setOverlay('')} kycVerified={!!kyc.verified} kycStatus={kyc.status} onVerifyKyc={() => setOverlay('kyc')} onCreated={() => apiGet('/portal/kyc/status').then((k: any) => k && setKyc(k))} /></div>}
          {overlay === 'deposit' && <div style={{ padding: mobile ? 12 : 28 }}><DepositWizard onClose={() => setOverlay('')} /></div>}
          {overlay === 'kyc' && <div style={{ padding: mobile ? 12 : 28 }}><KycWizard onClose={() => setOverlay('')} onDone={() => apiGet('/portal/kyc/status').then((k: any) => k && setKyc(k))} /></div>}

          {!overlay && <>
          {active === 'dashboard' && <Dashboard go={(k: string) => { if (k === 'deposit') setOverlay('deposit'); else if (k === 'accounts') { setActive('accounts'); } else go(k); }} onNewAccount={() => setOverlay('newaccount')} onDeposit={() => setOverlay('deposit')} onUploadKyc={() => setOverlay('kyc')} />}
          {active === 'accounts' && <Accounts onNewAccount={() => setOverlay('newaccount')} onNav={(k: string) => {
            if (k === 'deposit') setOverlay('deposit');
            else if (k === 'webtrader' || k === 'positions') go('charts');
            else if (k === 'history' || k === 'transactions') go('transactions');
            else go(k);   // withdraw / transfer / charts
          }} />}
          {active === 'deposit' && <DepositWizard onClose={() => setActive('dashboard')} />}
          {active === 'withdraw' && <Funds mode="withdraw" />}
          {active === 'transfer' && <Funds mode="transfer" />}
          {active === 'transactions' && <Funds mode="transactions" />}
          {active === 'bonus' && <BonusPage onDeposit={() => setOverlay('deposit')} onUploadKyc={() => setOverlay('kyc')} />}
          {active === 'copytrading' && <CopyTrading />}
          {active === 'autochartist' && <Autochartist section={acSection} />}
          {active === 'tradingcentral' && <ToolPage tool="tradingcentral" />}
          {active === 'charts' && <TradingViewPage />}
          {active === 'loyalty' && <Loyalty />}
          {active === 'mytickets' && <MyTickets />}
          {active === 'profile' && <Profile />}
          {active === 'support' && <Support />}
          </>}
        </div>
      </div>

      {/* pinned ticket button removed — manual ticket creation disabled (tickets are created via assistant chat / WhatsApp only) */}
      {/* <TicketButton /> */}

      {/* mobile bottom navigation — thumb-reach access to the key pages */}
      {mobile && (
        <div style={S.bottomNav}>
          {BOTTOM_NAV.map(n => {
            const on = active === n.key || (n.key === 'deposit' && overlay === 'deposit');
            return (
              <button key={n.key} onClick={() => { if (n.key === 'deposit') { setOverlay('deposit'); setNavOpen(false); } else { setOverlay(''); go(n.key); } }}
                style={{ ...S.bnItem, ...(on ? S.bnItemActive : {}) }}>
                <span style={{ fontSize: 19 }}>{n.icon}</span>
                <span style={{ fontSize: 9.5, fontWeight: 700 }}>{n.label}</span>
              </button>
            );
          })}
        </div>
      )}

      {/* AI live chat assistant (floating, on every page) */}
      <PortalChat />
    </div>
  );
}

const S: any = {
  shell: { minHeight: '100vh', display: 'flex', flexDirection: 'column', background: '#0B0E14' },
  topbar: { height: 58, display: 'flex', alignItems: 'center', gap: 14, padding: '0 18px', borderBottom: '1px solid #1A1F2B', background: '#0d1016', position: 'sticky', top: 0, zIndex: 30 },
  burger: { background: 'transparent', border: 'none', color: '#E7ECF3', fontSize: 20, cursor: 'pointer' },
  brand: { fontSize: 20, fontWeight: 900, letterSpacing: '-0.02em', color: '#fff' },
  brandSub: { fontSize: 11, letterSpacing: '0.2em', textTransform: 'uppercase', color: '#8A93A3', fontWeight: 700, marginLeft: 6 },
  userBox: { display: 'flex', alignItems: 'center', gap: 10 },
  avatar: { width: 36, height: 36, borderRadius: 99, background: 'linear-gradient(135deg,#F8500A,#C77B45)', color: '#0B0E14', display: 'grid', placeItems: 'center', fontWeight: 800, fontSize: 13 },
  themeBtn: { marginLeft: 10, display: 'flex', alignItems: 'center', gap: 6, padding: '7px 12px', borderRadius: 8, background: 'transparent', border: '1px solid #2a3240', color: '#E7ECF3', fontSize: 12.5, cursor: 'pointer' },
  logoutBtn: { marginLeft: 14, padding: '7px 14px', borderRadius: 8, background: 'transparent', border: '1px solid #2a3240', color: '#E7ECF3', fontSize: 12.5, cursor: 'pointer' },
  body: { display: 'flex', flex: 1, minHeight: 0 },
  sidebar: { width: 218, flex: '0 0 auto', borderRight: '1px solid #1A1F2B', background: '#0d1016', padding: 12, display: 'flex', flexDirection: 'column' },
  groupLabel: { fontSize: 9.5, letterSpacing: '0.16em', textTransform: 'uppercase', color: '#5a6373', fontWeight: 800, padding: '10px 13px 6px' },
  navItem: { display: 'flex', alignItems: 'center', gap: 11, padding: '10px 13px', borderRadius: 10, background: 'transparent', border: 'none', color: '#9aa3b3', fontSize: 13.5, fontWeight: 600, cursor: 'pointer', textAlign: 'left', width: '100%' },
  navItemActive: { background: 'linear-gradient(90deg, rgba(232,184,75,0.14), rgba(232,184,75,0.04))', color: '#fff', boxShadow: 'inset 2px 0 0 #F8500A' },
  subItem: { display: 'flex', alignItems: 'center', gap: 9, padding: '7px 13px 7px 30px', margin: '1px 0', borderRadius: 8, background: 'transparent', border: 'none', color: '#7b8794', fontSize: 12.5, fontWeight: 600, cursor: 'pointer', textAlign: 'left', width: '100%' },
  subItemActive: { color: '#F8500A', background: 'rgba(232,184,75,0.08)' },
  sideFoot: { fontSize: 10, color: '#5a6373', padding: '12px 8px', lineHeight: 1.6 },
  content: { flex: 1, minWidth: 0, overflowY: 'auto', maxHeight: 'calc(100vh - 58px)' },
  backdrop: { position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 45, backdropFilter: 'blur(1px)' },
  bottomNav: { position: 'fixed', left: 0, right: 0, bottom: 0, height: 60, zIndex: 40, display: 'flex',
    background: 'rgba(13,16,22,0.97)', borderTop: '1px solid #1A1F2B', backdropFilter: 'blur(8px)',
    paddingBottom: 'env(safe-area-inset-bottom)' },
  bnItem: { flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 3,
    background: 'transparent', border: 'none', color: '#7b8794', cursor: 'pointer', padding: '6px 2px' },
  bnItemActive: { color: '#F8500A' },
};

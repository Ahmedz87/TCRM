import { DialerLauncher } from './PowerDialer';
import NetworkBadge from './NetworkBadge';
import OwnDataToggle from './OwnDataToggle';
import React, { useState, useEffect, useCallback, useRef } from 'react';
import { apiGet, apiPost, apiPatch, apiDelete, placeCall, dialNumber, openIbProfile } from './api';
import { AgentCell } from './AgentCell';
import { CT, Pager } from './crmTable';
import { useT } from './adminI18n';
import axios from 'axios';

const API = '/api';

// each staff role maps to ONE fixed department — comments are stamped with it automatically
// (no manual department picker; desk rule Jul 20 2026).
function deptForRole(role: string): string {
  const r = (role || '').toLowerCase();
  if (r.includes('retention')) return 'Retention';
  if (r.includes('sales')) return 'Sales';
  if (r.includes('valid') || r.includes('kyc')) return 'Verification';
  if (r.includes('compl')) return 'Compliance';
  if (r.includes('backoffice') || r.includes('back_office')) return 'Backoffice';
  if (r.includes('finance')) return 'Finance';
  if (r.includes('care') || r.includes('support')) return 'Support';
  if (r.includes('market')) return 'Marketing';
  if (['super_admin', 'admin', 'director'].includes(r)) return 'Management';
  return 'Sales';
}

const networkColors: any = {
  green:  { bg: 'rgba(0,229,160,0.12)', text: '#00e5a0' },
  yellow: { bg: 'rgba(255,200,0,0.12)', text: '#ffc800' },
  orange: { bg: 'rgba(255,140,0,0.12)', text: '#ff8c00' },
  red:    { bg: 'rgba(255,77,77,0.12)', text: '#ff4d4d' },
};
const actionColors: any = { connected_done:'#00e5a0', no_answer:'#ffaa00', call_later:'#0066ff', not_interested:'#ff4d4d', transfer_out:'#cc88ff' };
const actionLabels: any = { connected_done:'Connected & Done', no_answer:'No Answer', call_later:'Call Later', not_interested:'Not Interested', transfer_out:'Transfer out of my data' };

const EMAIL_TEMPLATES = [
  { id: 'deposit',     subject: 'Fund Your Account and Start Trading Today',                     body: `Dear {name},\n\nYour TNFX trading account is ready and waiting for you. Fund your account today and take advantage of current market opportunities in Gold, Forex and Indices.\n\nOur funding methods are fast, secure and available 24/7.\n\nBest regards,\n{agent}\nTNFX` },
  { id: 'dep_bonus',   subject: 'Special Deposit Bonus — Exclusive for You — TNFX',             body: `Dear {name},\n\nWe have an exclusive offer just for you!\n\nMake a deposit this week and receive up to 50% bonus on your deposit amount.\n\nThis is a limited-time offer exclusively for valued TNFX clients. Log in to your portal to claim your bonus before it expires.\n\nBest regards,\n{agent}\nTNFX` },
  { id: 'kyc_pending', subject: 'Action Required: Complete Your KYC Verification — TNFX',        body: `Dear {name},\n\nYour KYC verification is still pending. To ensure uninterrupted access to your trading account and full withdrawal rights, please complete your verification as soon as possible.\n\nPlease submit:\n• Valid passport or national ID\n• Proof of address (utility bill or bank statement issued within 3 months)\n\nLog in to your client portal to upload your documents.\n\nBest regards,\n{agent}\nTNFX Compliance Team` },
  { id: 'kyc_expiry',  subject: 'Important: Your KYC Documents Are Expiring — TNFX',            body: `Dear {name},\n\nOur records show that your identity verification documents are due for renewal.\n\nTo continue trading without interruption and maintain your withdrawal privileges, please upload updated documents within the next 14 days:\n• Valid government-issued ID\n• Recent proof of address (issued within 3 months)\n\nPlease log in to your client portal to upload your documents.\n\nBest regards,\n{agent}\nTNFX Compliance Team` },
  { id: 'inactive',    subject: 'We Miss You — Come Back and Trade with TNFX',                  body: `Dear {name},\n\nWe noticed you have not logged into your trading account recently. The markets are full of opportunities right now, especially in Gold and major forex pairs.\n\nYour account and funds are safe. Log in today and see what you have been missing.\n\nBest regards,\n{agent}\nTNFX` },
  { id: 'margin',      subject: '⚠️ Important: Your Margin Level Requires Attention — TNFX',    body: `Dear {name},\n\nWe would like to inform you that your account margin level requires immediate attention.\n\nPlease log in to your MT5 account and consider:\n• Adding additional funds to your account\n• Reducing your open positions\n• Setting appropriate stop-loss levels\n\nOur support team is available 24/5 if you need assistance.\n\nBest regards,\n{agent}\nTNFX Risk Team` },
  { id: 'withdraw',    subject: 'Your Withdrawal Has Been Processed — TNFX',                    body: `Dear {name},\n\nYour withdrawal request has been processed successfully.\n\nPlease allow 1-3 business days for the funds to appear in your account depending on your payment method.\n\nFor any questions, our support team is available 24/5.\n\nBest regards,\n{agent}\nTNFX Finance Team` },
  { id: 'reactivate',  subject: 'Your TNFX Account — Special Reactivation Offer',               body: `Dear {name},\n\nWe have a special offer to welcome you back to active trading!\n\nReactivate your account this month and enjoy:\n✅ Reduced spreads for your first week\n✅ Dedicated account manager support\n✅ Access to our latest market analysis\n\nLog in now and take advantage of current market conditions.\n\nBest regards,\n{agent}\nTNFX` },
];

const scoreReasons = (c: any, t: (s: string) => string = (x) => x) => {
  const r: { label: string; points: number }[] = [];
  const bal = c.balance || 0, eq = c.equity || 0, ml = c.margin_level || 0, kyc = c.kyc || 'pending', la = c.last_action_type || '';
  if (ml > 0 && ml < 20)          r.push({ label: t('Margin call active'),         points: 40 });
  if (ml > 0 && ml < 80)          r.push({ label: t('Margin below threshold'),     points: 30 });
  if (bal > 0 && eq < bal * 0.7)  r.push({ label: t('Low equity (floating loss)'), points: 20 });
  if (bal >= 500)                  r.push({ label: t('High balance'),               points: 20 });
  if (kyc === 'pending')           r.push({ label: t('KYC pending'),                points: 12 });
  // #290: zero balance ≠ never deposited — check the real deposit signals before claiming it
  const _dep = Number(c.total_deposit ?? c.total_deposits ?? 0) || 0;
  const _depN = Number(c.dep_count ?? c.deposit_count ?? 0) || 0;
  if (bal === 0 && eq === 0 && _dep <= 0 && _depN <= 0 && !c.first_deposit_date)
    r.push({ label: t('Never deposited'), points: 18 });
  else if (bal === 0 && eq === 0 && (_dep > 0 || _depN > 0))
    r.push({ label: t('Deposited before — balance now zero'), points: 18 });
  if (la === 'no_answer')          r.push({ label: t('No answer — escalating'),     points: 10 });
  if (la === 'call_later')         r.push({ label: t('Call later time reached'),    points: 100 });
  if (la === 'connected_done')     r.push({ label: t('Connected & Done (cooldown)'),points: -100 });
  if (c.birthday && c.birthday.in_window && !c.birthday.greeted) r.unshift({ label: t('🎂 Birthday this week'), points: 100 });
  return r;
};

// Birthday 🎂 cake — colour tells the sales agent the state: grey = birthday this week (not yet
// greeted), gold = greeted (successful call done), green = bonus claimed by the client.
const CAKE_COLORS: any = { grey: '#9aa3b3', gold: '#ffbf00', green: '#00e5a0' };
function BirthdayCake({ b }: { b: any }) {
  const t = useT();
  if (!b || !b.in_window) return null;
  const col = CAKE_COLORS[b.cake_color] || '#9aa3b3';
  const tip = b.claimed ? t('Birthday this week — bonus claimed 🎂')
    : b.greeted ? t('Birthday this week — greeted (called) ✓')
    : t('Birthday this week — not yet greeted');
  return <span title={tip} style={{ fontSize: 12, padding: '1px 5px', borderRadius: 99, background: `${col}22`, border: `1px solid ${col}`, filter: b.cake_color === 'grey' ? 'grayscale(0.6)' : 'none', whiteSpace: 'nowrap' }}>🎂</span>;
}

const scoreColor = (s: number) => s >= 60 ? '#ff4d4d' : s >= 30 ? '#ffaa00' : s >= 10 ? '#ffc800' : '#00e5a0';

// ── CLIENT PROFILE PAGE ──────────────────────────────────────────────────
// ── Connection intelligence (shared) ──────────────────────────────────────────
const CONN_REASON_ICON: Record<string,string> = { cid:'📱',mqid:'📱',email:'✉️',similar_email:'📧',phone:'📞',family:'👪',ip:'🌐',payment:'💳',pay_sender:'💳',ib:'🤝',city:'📍' };
function confColor(p:number){ return p>=90?'#ff4d4d':p>=70?'#ffaa00':p>=50?'#ffd400':'#00aaff'; }
const _normName = (s:string)=>(s||'').toLowerCase().replace(/[^a-z؀-ۿ ]/g,'').split(/\s+/).filter(Boolean).slice(0,3).sort().join(' ');
function ConnRow({ c, subjectName, onOpen }:{ c:any; subjectName?:string; onOpen?:(c:any)=>void }){
  const t = useT();
  const col = confColor(c.confidence);
  const [open,setOpen] = useState(false);
  const reasons = c.reasons||[];
  return (
    <div style={{ background:'#2c333e', border:'1px solid '+(open?col+'88':'#4f596b'), borderRadius:10, marginBottom:6 }}>
      <div onClick={()=>setOpen(o=>!o)} style={{ display:'flex', alignItems:'center', gap:10, padding:'8px 10px', cursor:'pointer' }}>
        <div style={{ width:46, textAlign:'center', flexShrink:0 }}>
          <div style={{ fontSize:15, fontWeight:800, color:col }}>{c.confidence}%</div>
          <div style={{ fontSize:9, color:'#667' }}>{c.score10}/10</div>
        </div>
        <div style={{ flex:1, minWidth:0 }}>
          <div style={{ fontSize:12.5, color:'#e6e9ef', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
            {(c.name||'').split(/\s+/).slice(0,2).join(' ')}
            {c.kind==='lead' && <span style={{ fontSize:9, color:'#00aaff', border:'1px solid #00aaff55', borderRadius:4, padding:'0 4px', marginLeft:4 }}>{t('LEAD')}</span>}
          </div>
          <div style={{ fontSize:10, color:'#667', fontFamily:'monospace' }}>{c.login?('#'+c.login):('lead #'+c.id)}{c.city?(' · '+c.city):''}{c.ib_name?(' · '+c.ib_name):''}</div>
        </div>
        <div style={{ display:'flex', gap:4, flexWrap:'wrap', justifyContent:'flex-end', maxWidth:200 }}>
          {reasons.map((r:any,ri:number)=>(
            <span key={ri} title={`${r.label}: ${r.value}`} style={{ fontSize:9.5, padding:'2px 6px', borderRadius:99, background:'#373f4d', color:'#bcc3cf' }}>{CONN_REASON_ICON[r.type]||'·'} {r.type}</span>
          ))}
        </div>
        <div style={{ color:'#667', fontSize:10, marginLeft:2, flexShrink:0 }}>{open?'▲':'▼'}</div>
      </div>
      {open && (
        <div style={{ borderTop:'1px solid #4f596b', padding:'10px 12px', background:'#262c36', borderRadius:'0 0 10px 10px' }}>
          <div style={{ fontSize:10, color:'#8a93a3', marginBottom:8, textTransform:'uppercase', letterSpacing:0.5 }}>{t('What links them — matching details')}</div>
          {reasons.length===0 ? <div style={{ fontSize:11, color:'#667' }}>{t('No shared attributes recorded.')}</div> :
            reasons.map((r:any,ri:number)=>(
              <div key={ri} style={{ display:'flex', alignItems:'flex-start', gap:8, padding:'5px 0', fontSize:11.5, borderBottom: ri<reasons.length-1?'1px solid #313946':'none' }}>
                <span style={{ width:18, textAlign:'center', flexShrink:0 }}>{CONN_REASON_ICON[r.type]||'·'}</span>
                <span style={{ color:'#9aa3b2', width:130, flexShrink:0 }}>{r.label||r.type}</span>
                <span style={{ color:'#e6e9ef', fontFamily:'monospace', wordBreak:'break-all', flex:1 }}>{r.value||'—'}</span>
                <span style={{ fontSize:9, color:'#00e5a0', border:'1px solid #00e5a033', borderRadius:4, padding:'0 5px', flexShrink:0 }}>{t('match')}</span>
              </div>
            ))}
          {onOpen && c.login && (
            <div style={{ marginTop:8 }}>
              <span onClick={(e)=>{ e.stopPropagation(); onOpen(c); }} style={{ fontSize:10.5, color:'#00aaff', cursor:'pointer', textDecoration:'underline' }}>{t('Open')} #{c.login}{t("'s profile →")}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// Robust clipboard copy — navigator.clipboard is undefined in non-secure contexts and
// some in-app webviews, where the old `navigator.clipboard?.writeText` silently no-ops.
// Falls back to a hidden textarea + execCommand so the copy actually happens.
async function copyText(txt: any): Promise<boolean> {
  const s = String(txt ?? '');
  if (!s) return false;
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(s);
      return true;
    }
  } catch {}
  try {
    const ta = document.createElement('textarea');
    ta.value = s;
    ta.style.position = 'fixed'; ta.style.left = '-9999px'; ta.style.opacity = '0';
    document.body.appendChild(ta); ta.focus(); ta.select();
    const ok = document.execCommand('copy');
    document.body.removeChild(ta);
    return ok;
  } catch { return false; }
}
// Copy icon with a brief "✓ Copied" confirmation so it's clearly not just a shape.
function CopyBtn({ value, size = 12, style }: { value: any; size?: number; style?: any }){
  const t = useT();
  const [done, setDone] = useState(false);
  return (
    <span
      onClick={async (e) => { e.stopPropagation(); const ok = await copyText(value); if (ok) { setDone(true); setTimeout(() => setDone(false), 1200); } }}
      title={done ? t('Copied!') : t('Copy')}
      style={{ cursor:'pointer', fontSize:size, color: done ? '#00e5a0' : '#8b93a1', transition:'color 0.15s', userSelect:'none', ...(style||{}) }}>
      {done ? '✓' : '⧉'}
    </span>
  );
}

// ————— Polished profile building blocks —————
function InfoCard({ icon, title, accent='#00e5a0', action, children }: any){
  return (
    <div style={{ background:'linear-gradient(160deg,#2b323c,#242a33)', border:'1px solid #3a434f', borderRadius:16, padding:'14px 18px 10px', boxShadow:'0 4px 16px rgba(0,0,0,0.22)' }}>
      <div style={{ display:'flex', alignItems:'center', gap:9, marginBottom:8 }}>
        <span style={{ width:26, height:26, borderRadius:8, background:accent+'22', color:accent, display:'flex', alignItems:'center', justifyContent:'center', fontSize:13, flexShrink:0 }}>{icon}</span>
        <span style={{ fontSize:11, color:'#aeb6c2', fontWeight:700, textTransform:'uppercase', letterSpacing:0.6 }}>{title}</span>
        {action && <span style={{ marginLeft:'auto' }}>{action}</span>}
      </div>
      {children}
    </div>
  );
}
function Field({ label, value, accent, onClick, mono, last }: any){
  const isEmpty = value===undefined || value===null || value==='' || value==='—';
  return (
    <div style={{ display:'flex', alignItems:'baseline', justifyContent:'space-between', gap:14, padding:'7px 0', borderBottom: last?'none':'1px solid #333b46' }}>
      <span style={{ fontSize:11.5, color:'#8b93a1', flexShrink:0, whiteSpace:'nowrap' }}>{label}</span>
      <span onClick={onClick}
        style={{ fontSize:12.5, fontWeight:600, textAlign:'right', overflowWrap:'anywhere', wordBreak:'break-word', minWidth:0,
          color: onClick ? '#38bdf8' : isEmpty ? '#5a6472' : (accent||'#eef1f6'),
          cursor: onClick?'pointer':'default', fontFamily: mono?'monospace':'inherit',
          textDecoration: onClick?'underline':'none' }}>{isEmpty?'—':value}</span>
    </div>
  );
}
function ClientProfile({ client: clientProp, onBack, lang, setPhoneClient, setEmailClient }: any) {
  const t = useT();
  const isAr = lang === 'ar';
  const [tab, setTab] = useState('overview');
  const [acctView, setAcctView] = useState<'cards'|'table'>('cards');   // #5
  const [selectedAccount, setSelectedAccount] = useState<any>(null);
  const [accountTab, setAccountTab] = useState('open');
  const [histDays, setHistDays] = useState(0);      // trade-history period filter (0 = all time)
  const [client, setClient] = useState<any>(clientProp);
  const [commentText, setCommentText] = useState('');
  // department is FIXED per the logged-in user's role — no manual selection (desk rule Jul 20 2026)
  const commentDept = deptForRole(localStorage.getItem('userRole') || '');
  const [comments, setComments] = useState<any[]>([]);
  const [postingComment, setPostingComment] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);   // comment being edited
  const [editText, setEditText] = useState('');
  const feedRef = useRef<HTMLDivElement>(null);   // comments feed — auto-scroll to bottom
  const [editOpen, setEditOpen] = useState(false);
  const [addAcctOpen, setAddAcctOpen] = useState(false);   // ticket #98: create additional account
  const [conns, setConns] = useState<any>(null);   // ranked network connections
  const isAdmin = ['super_admin','admin','director'].includes(localStorage.getItem('userRole') || '');

  useEffect(() => {
    const lg = clientProp?.login;
    setConns(null);
    if (lg) apiGet(`/network/connections?login=${lg}`).then(setConns).catch(() => {});
  }, [clientProp?.login]);

  useEffect(() => {
    if (clientProp?.id || clientProp?.login) {
      // Prefer fetching by DB id so all trading accounts (MT4+MT5) are returned
      const key = clientProp.id ? `id/${clientProp.id}` : clientProp.login;
      apiGet(`/clients/${key}`)
        .then(data => {
          setClient({ ...clientProp, ...data });
          setComments(data.actions_history || []);
        })
        .catch(() => {
          // Fallback to login if id endpoint not yet available
          if (clientProp.login) {
            apiGet(`/clients/${clientProp.login}`)
              .then(data => { setClient({ ...clientProp, ...data }); setComments(data.actions_history || []); })
              .catch(() => {});
          }
        });
    }
  }, [clientProp?.id, clientProp?.login]);

  const postComment = async () => {
    if (!commentText.trim()) return;
    setPostingComment(true);
    try {
      const userName = localStorage.getItem('userName') || 'Agent';
      const r: any = await apiPost(`/clients/${client.login}/comment`, {
        note: commentText,
        dept: commentDept,
        agent_name: userName,
      });
      // newest goes to the BOTTOM (chat-style) so the last note is in front of you as you type
      setComments(prev => [...prev, {
        id: r?.id,
        action: 'comment',
        note: commentText,
        dept: commentDept,
        agent_name: userName,
        created_at: r?.created_at || new Date().toISOString(),
        can_edit: true,
      }]);
      setCommentText('');
    } catch (e) {
      alert(t('Failed to post comment'));
    }
    setPostingComment(false);
  };
  // A comment is editable/deletable by its author for 60 minutes; then it freezes. (#232, 60m Jul 21)
  const EDIT_MS = 60 * 60 * 1000;
  const canEditComment = (c: any) => !!c?.can_edit && c?.id != null
    && (Date.now() - new Date(c.created_at).getTime()) < EDIT_MS;
  const saveEdit = async (c: any, text: string) => {
    const body = text.trim();
    if (!body) return;
    const r: any = await apiPatch(`/clients/${client.login}/comment/${c.id}`, { note: body });
    if (r && r.detail) { alert(r.detail); return; }
    setComments(prev => prev.map(x => x.id === c.id ? { ...x, note: body } : x));
    setEditingId(null); setEditText('');
  };
  const deleteComment = async (c: any) => {
    if (!window.confirm(t('Delete this comment?'))) return;
    const r: any = await apiDelete(`/clients/${client.login}/comment/${c.id}`);
    if (r && r.detail) { alert(r.detail); return; }
    setComments(prev => prev.filter(x => x.id !== c.id));
  };
  // keep the newest comment in view (scroll the feed to the bottom on load / new post)
  useEffect(() => { if (feedRef.current) feedRef.current.scrollTop = feedRef.current.scrollHeight; }, [comments.length]);
  // oldest -> newest so the latest sits at the bottom, right above the composer
  const orderedComments = [...comments].sort((a, b) =>
    new Date(a.created_at || 0).getTime() - new Date(b.created_at || 0).getTime());

  // open another linked account's profile in place (used by the connections pane)
  const openConn = (cc:any) => {
    if (!cc?.login) return;
    const t = localStorage.getItem('token') || '';
    fetch(`/api/clients/${cc.login}`, { headers:{ Authorization:'Bearer '+t } })
      .then(r=>r.json()).then(d=>{ if(d&&d.login){ setClient(d); setComments(d.actions_history||[]); setTab('overview'); } }).catch(()=>{});
  };

  const tabs = [
    { key: 'overview',   label: t('Overview') },
    { key: 'deposits',   label: t('Deposits') },
    { key: 'withdrawals',label: t('Withdrawals') },
    { key: 'transfers',  label: t('Internal transfers') },
    { key: 'accounts',   label: t('Trading accounts') },
    { key: 'calls',      label: t('Call history') },
    { key: 'network',    label: t('Network') },
  ];

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'var(--bg-main,#20252f)', color: 'var(--text,#fff)', fontFamily: 'sans-serif', zIndex: 500, display:'flex', flexDirection:'column' }}>

      {/* Top bar */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 24px', background: 'linear-gradient(180deg,#333b47,#2a313b)', borderBottom: '1px solid #3a434f', boxShadow:'0 4px 18px rgba(0,0,0,0.25)', flexShrink:0, zIndex: 100, flexWrap:'wrap' }}>
        <button onClick={onBack} style={{ background: 'transparent', border: '1px solid var(--border2,#626d80)', borderRadius: 8, color: 'var(--text2,#888)', padding: '6px 14px', cursor: 'pointer', fontSize: 13, display:'flex', alignItems:'center', gap:6 }}>← {t('Back')}</button>
        <div style={{ width: 40, height: 40, borderRadius: 12, background: 'linear-gradient(135deg,#0066ff,#9966ff)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: 17, flexShrink:0 }}>{client.name?.[0]}</div>
        <div>
          <div style={{ fontSize: 16, fontWeight: 500, color: 'var(--text,#fff)' }}>{client.name}{client.customer_no && <span style={{ marginLeft:8, fontSize:11, fontFamily:'monospace', color:'#9966ff', background:'rgba(153,102,255,0.12)', padding:'2px 7px', borderRadius:6 }}>{client.customer_no}</span>}</div>
          <div style={{ fontSize: 11, color: 'var(--text3,#555)', marginTop:2 }}>#{client.login} · {client.email} {client.phone && <span>· {client.phone}</span>}</div>
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center' }}>
          <button onClick={() => setPhoneClient(client)} style={{ display:'flex', alignItems:'center', gap:5, padding:'7px 14px', borderRadius:8, border:'1px solid rgba(0,229,160,0.3)', background:'rgba(0,229,160,0.08)', color:'#00e5a0', cursor:'pointer', fontSize:12, fontWeight:500 }}>📞 {t('Call')}</button>
          <button onClick={() => { const n=(client.phone||'').replace(/[^0-9]/g,''); window.open('https://wa.me/'+n+'?text=Hello '+client.name,'_blank'); }} style={{ display:'flex', alignItems:'center', gap:5, padding:'7px 14px', borderRadius:8, border:'1px solid rgba(37,211,102,0.3)', background:'rgba(37,211,102,0.08)', color:'#25d366', cursor:'pointer', fontSize:12, fontWeight:500 }}>💬 {t('WhatsApp')}</button>
          <button onClick={() => setEmailClient(client)} style={{ display:'flex', alignItems:'center', gap:5, padding:'7px 14px', borderRadius:8, border:'1px solid rgba(0,102,255,0.3)', background:'rgba(0,102,255,0.08)', color:'#4d9fff', cursor:'pointer', fontSize:12, fontWeight:500 }}>✉️ {t('Email')}</button>
          {client.login > 0 && (
            <button onClick={async () => {
              try {
                const res: any = await apiPost(`/portal/impersonate/${client.login}`, {});
                if (res?.token) window.open(`/portal/?imp=${encodeURIComponent(res.token)}`, '_blank');
                else alert(res?.error || t('No client portal account for this login.'));
              } catch { alert(t('Could not open the client view.')); }
            }} title={t('Open the client portal as this client (read-only preview)')} style={{ display:'flex', alignItems:'center', gap:5, padding:'7px 14px', borderRadius:8, border:'1px solid rgba(232,184,75,0.4)', background:'rgba(232,184,75,0.1)', color:'#E8B84B', cursor:'pointer', fontSize:12, fontWeight:600 }}>👁 {t('View as client')}</button>
          )}
          {isAdmin && (
            <button onClick={() => setAddAcctOpen(true)} title={t('Create an additional MT trading account for this client')} style={{ display:'flex', alignItems:'center', gap:5, padding:'7px 14px', borderRadius:8, border:'1px solid rgba(153,102,255,0.4)', background:'rgba(153,102,255,0.1)', color:'#b08cff', cursor:'pointer', fontSize:12, fontWeight:500 }}>➕ {t('Create additional account')}</button>
          )}
          <div style={{ width:1, height:24, background:'#626d80', margin:'0 4px' }}></div>
          <div style={{ display:'flex', alignItems:'center', justifyContent:'center', width:36, height:36, borderRadius:'50%', border:`2px solid ${scoreColor(client.call_score||0)}`, color:scoreColor(client.call_score||0), fontWeight:700, fontSize:13 }}>{client.call_score||0}</div>
          <span style={{ fontSize:11, padding:'4px 10px', borderRadius:99, background: client.kyc==='verified'?'rgba(0,229,160,0.1)':'rgba(255,170,0,0.1)', color: client.kyc==='verified'?'#00e5a0':'#ffaa00' }}>{client.kyc}</span>
          <span style={{ fontSize:11, padding:'4px 10px', borderRadius:99, background:'rgba(255,77,77,0.1)', color:'#ff4d4d' }}>{client.risk} {t('risk')}</span>
        </div>
      </div>

      {/* Two-pane body: LEFT 70% workspace · RIGHT 30% (connections over comments) */}
      <div style={{ flex:1, minHeight:0, display:'grid', gridTemplateColumns:'minmax(0,7fr) minmax(0,3fr)', gap:16, padding:16, overflow:'hidden' }}>

        {/* LEFT 70% — KPIs + tabs are PINNED; only the content below scrolls */}
        <div style={{ minWidth:0, display:'flex', flexDirection:'column', overflow:'hidden' }}>

      {/* KPI strip (pinned) */}
      <div style={{ flexShrink:0, display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(126px,1fr))', gap: 10, marginBottom: 12 }}>
        {[
          { label: t('Balance'),          value: `$${(client.balance||0).toLocaleString('en-GB')}`,        color: '#5fb0ff',  icon:'💰' },
          { label: t('Equity'),           value: `$${(client.equity||client.balance||0).toLocaleString('en-GB')}`,          color: (client.equity||client.balance) < client.balance ? '#ff6b6b' : '#00e5a0', icon:'📈' },
          { label: t('Margin level'),     value: client.margin_level ? `${client.margin_level.toFixed(0)}%` : '—', color: (client.margin_level||0) < 80 ? '#ff6b6b' : '#00e5a0', icon:'⚖️' },
          { label: t('Total deposits'),   value: `$${(client.total_deposit||0).toLocaleString('en-GB')}`,   color: '#00e5a0', icon:'⬆️' },
          { label: t('Total withdrawals'),value: `$${(client.total_withdraw||0).toLocaleString('en-GB')}`,  color: '#ff9d76', icon:'⬇️' },
          { label: t('Bonus'),            value: `$${client.bonus||0}`,                              color: '#ffc14d', icon:'🎁' },
        ].map((s,i) => (
          <div key={i} style={{ position:'relative', background:'linear-gradient(160deg,#2f3742,#262c35)', border:'1px solid #3a434f', borderRadius:14, padding:'12px 13px', overflow:'hidden' }}>
            <div style={{ position:'absolute', left:0, top:0, bottom:0, width:3, background:s.color, opacity:0.85 }} />
            <div style={{ display:'flex', alignItems:'center', gap:6, marginBottom:8 }}>
              <span style={{ width:22, height:22, borderRadius:7, background:s.color+'22', display:'flex', alignItems:'center', justifyContent:'center', fontSize:11 }}>{s.icon}</span>
              <span style={{ fontSize:9.5, color:'#8b93a1', fontWeight:600, textTransform:'uppercase', letterSpacing:0.4, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{s.label}</span>
            </div>
            <div style={{ fontSize:18, fontWeight:800, color:s.color, letterSpacing:-0.3, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{s.value}</div>
          </div>
        ))}
      </div>

      {/* Tabs (pinned, pill style) */}
      <div style={{ flexShrink:0, display: 'flex', gap: 6, flexWrap:'wrap', paddingBottom: 12, borderBottom:'1px solid #313945' }}>
        {tabs.map(t => (
          <div key={t.key} onClick={() => setTab(t.key)}
            style={{ padding: '7px 15px', cursor: 'pointer', fontSize: 12.5, fontWeight: tab===t.key?700:500, borderRadius: 9, whiteSpace:'nowrap',
              color: tab===t.key?'#0b0f14':'#9aa3b2',
              background: tab===t.key?'linear-gradient(135deg,#00e5a0,#00c48f)':'#262c36',
              border:'1px solid '+(tab===t.key?'transparent':'#353d49'),
              boxShadow: tab===t.key?'0 3px 12px rgba(0,229,160,0.28)':'none',
              transition:'all 0.15s' }}>
            {t.label}
          </div>
        ))}
      </div>

      {/* Content (the only scrolling region on the left) */}
      <div style={{ flex:1, minHeight:0, overflowY:'auto', padding: '16px 2px 24px' }}>

        {/* OVERVIEW — two ordered columns: PROFILE (left) · ACCOUNT & ACTIVITY (right) */}
        {tab === 'overview' && (
          <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit,minmax(340px,1fr))', gap:14, alignItems:'start' }}>

            {/* LEFT COLUMN — Financials FIRST (desk request), then who they are */}
            <div style={{ display:'flex', flexDirection:'column', gap:14, minWidth:0 }}>

            {/* Financials */}
            <InfoCard icon="💵" title={t('Financials')} accent="#00e5a0">
              <Field label={t('Balance')} value={`$${(client.balance||0).toLocaleString('en-GB')}`} accent="#5fb0ff" />
              <Field label={t('Equity')} value={`$${(client.equity||client.balance||0).toLocaleString('en-GB')}`} accent={(client.equity||client.balance) < client.balance ? '#ff6b6b':'#00e5a0'} />
              <Field label={t('Total deposits')} value={`$${(client.total_deposit||0).toLocaleString('en-GB')}`} accent="#00e5a0" />
              <Field label={t('Total withdrawals')} value={`$${(client.total_withdraw||0).toLocaleString('en-GB')}`} accent="#ff9d76" />
              <Field label={t('Net deposit')} value={`$${((client.total_deposit||0)-(client.total_withdraw||0)).toLocaleString('en-GB')}`} />
              <Field label={t('Bonus / credit')} value={`$${(client.bonus||0).toLocaleString('en-GB')}`} accent="#ffc14d" />
              <Field label={t('Deposit count')} value={client.deposit_count ?? client.dep_count ?? '—'} last />
            </InfoCard>

            {/* Personal & contact (Contact + Identity + Location merged) */}
            <InfoCard icon="👤" title={t('Personal & contact')} accent="#38bdf8"
              action={isAdmin ? <button onClick={() => setEditOpen(true)} style={{ fontSize:11, padding:'4px 10px', borderRadius:7, border:'1px solid rgba(56,189,248,0.4)', background:'rgba(56,189,248,0.1)', color:'#38bdf8', cursor:'pointer', fontWeight:600 }}>✏️ {t('Edit')}</button> : undefined}>
              <div style={{ display:'flex', gap:6, flexWrap:'wrap', marginBottom:10 }}>
                <span style={{ fontSize:10.5, fontWeight:700, padding:'4px 9px', borderRadius:99, background: client.email_verified?'rgba(0,229,160,0.14)':'rgba(150,160,180,0.12)', color: client.email_verified?'#00e5a0':'#9aa3b3' }}>{client.email_verified?t('✓ Email'):t('Email ✗')}</span>
                <span style={{ fontSize:10.5, fontWeight:700, padding:'4px 9px', borderRadius:99, background: client.phone_verified?'rgba(0,229,160,0.14)':'rgba(150,160,180,0.12)', color: client.phone_verified?'#00e5a0':'#9aa3b3' }}>{client.phone_verified?t('✓ Phone'):t('Phone ✗')}</span>
                <span style={{ fontSize:10.5, fontWeight:700, padding:'4px 9px', borderRadius:99, background: client.kyc==='verified'?'rgba(0,229,160,0.14)':'rgba(255,170,0,0.14)', color: client.kyc==='verified'?'#00e5a0':'#ffaa00' }}>{client.kyc==='verified'?t('✓ KYC'):t('KYC')+' '+(client.kyc||'pending')}</span>
              </div>
              <Field label={t('Full name')} value={client.name} />
              <Field label={t('Name (English)')} value={client.full_name_en} />
              <Field label={t('Date of birth')} value={client.date_of_birth} />
              <Field label={t('Email')} value={client.email} />
              <Field label={t('Phone')} value={client.phone} />
              <Field label={t('Language')} value={client.language} />
              <Field label={t('Country')} value={client.country} />
              <Field label={t('City')} value={client.city} />
              <Field label={t('IP address')} value={client.ip} mono />
              <Field label={t('CID')} value={client.cid} mono last />
            </InfoCard>

            </div>{/* end LEFT column */}

            {/* RIGHT COLUMN — Activity & score FIRST (desk request) */}
            <div style={{ display:'flex', flexDirection:'column', gap:14, minWidth:0 }}>

            {/* Activity & score (timeline + score reasons merged) */}
            <InfoCard icon="⏱️" title={t('Activity & score')} accent="#fb7185">
              {(() => { const rows=[[t('1st deposit'), client.first_deposit_date, client.first_deposit_amount?('$'+(client.first_deposit_amount||0).toLocaleString('en-GB')):''],[t('Last deposit'),client.last_deposit_date || client.last_deposit_at,''],[t('Last trade'),client.last_trade_date || client.last_trade_at,''],[t('Last withdrawal'),client.last_withdraw_date || client.last_withdraw_at,'']];
                return rows.map(([k,v,extra]:any)=>(
                  <Field key={k} label={k} value={v ? (new Date(v).toLocaleDateString('en-GB') + (extra?` · ${extra}`:'')) : '—'} />
                )); })()}
              <Field label={t('Lead / call score')} value={client.call_score ?? client.score ?? '—'} last={scoreReasons(client).length===0} />
              {scoreReasons(client, t).map((r,i,arr) => (
                <div key={i} style={{ display:'flex', justifyContent:'space-between', alignItems:'center', fontSize:12.5, padding:'7px 0', borderBottom: i===arr.length-1?'none':'1px solid #333b46' }}>
                  <span style={{ color:'#aeb6c2' }}>{r.label}</span>
                  <span style={{ color: r.points > 0 ? '#fbbf24' : '#00e5a0', fontWeight:700, background:(r.points>0?'#fbbf2418':'#00e5a018'), padding:'2px 8px', borderRadius:7 }}>{r.points>0?'+':''}{r.points}</span>
                </div>
              ))}
            </InfoCard>

            {/* Account & assignment (Identity account bits + Assignment + Risk merged) */}
            <InfoCard icon="🤝" title={t('Account & assignment')} accent="#a78bfa">
              <Field label={t('Customer ID')} value={client.customer_no} mono accent="#c4b5fd" />
              <Field label={t('Login #')} value={client.login} mono />
              <Field label={t('Account group')} value={client.group} mono />
              <Field label={t('Platform')} value={client.platform || 'MT5'} />
              <Field label={t('Leverage')} value={client.leverage ? '1:'+client.leverage : '—'} />
              <Field label={t('Accounts')} value={client.account_count || (client.related_accounts||[]).length || '—'} />
              <Field label={t('Sales agent')} value={client.agent_name||client.sales_agent} />
              <Field label={t('IB')} value={(client.ib_display||client.ib) || '—'}
                onClick={(client.ib_display||client.ib) ? ()=>openIbProfile(String(client.ib_display||client.ib||'').replace(/\s*\(.*\)$/,'')) : undefined} />
              <Field label={t('Registered')} value={client.reg_date ? String(client.reg_date).slice(0,10) : '—'} />
              <Field label={t('Risk level')} value={client.risk ? String(client.risk)+' '+t('risk') : '—'} accent={client.risk==='high'?'#ff6b6b':client.risk==='medium'?'#ffaa00':'#00e5a0'} last />
            </InfoCard>

            </div>{/* end RIGHT column */}
          </div>
        )}

        {/* DEPOSITS */}
        {tab === 'deposits' && (() => { const list = client.deposits_list || client.deposits || []; const tot = list.reduce((s:number,d:any)=>s+(d.amount||0),0); return (
          <div>
            {/* totals strip */}
            <div style={{ display:'flex', gap:10, marginBottom:10, flexWrap:'wrap' }}>
              {[[t('Total transactions'), list.length.toLocaleString('en-GB'), '#aeb6c2'],
                [t('Total deposited'), '$'+tot.toLocaleString(undefined,{maximumFractionDigits:2}), '#00e5a0']].map(([l,v,c2]:any)=>(
                <div key={l} style={{ background:'linear-gradient(160deg,#2b323c,#242a33)', border:'1px solid #3a434f', borderRadius:10, padding:'9px 16px' }}>
                  <div style={{ fontSize:10, color:'#8b93a1', textTransform:'uppercase', letterSpacing:0.4 }}>{l}</div>
                  <div style={{ fontSize:16, fontWeight:800, color:c2 }}>{v}</div>
                </div>
              ))}
            </div>
          <div style={{ background: 'linear-gradient(160deg,#2c333e,#262c35)', border: '1px solid #3a434f', borderRadius: 12, overflow: 'hidden' }}>
            <table style={CT.table}>
              <thead>
                <tr style={CT.theadTr}>
                  {['Date','Amount','Trading account','Method','Status','Reference'].map(h => (
                    <th key={h} style={CT.th()}>{t(h)}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {list.map((d: any, i: number) => (
                  <tr key={i} style={CT.row()}>
                    <td style={{ ...CT.td, color: '#888' }}>{(()=>{const v=d.date||d.tx_date; return v? new Date(String(v).replace(' ','T')).toLocaleString('en-GB',{day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit',hour12:false}):'—';})()}</td>
                    <td style={{ ...CT.td, color: '#00e5a0', fontWeight: 500 }}>${(d.amount||0).toLocaleString('en-GB')}</td>
                    <td style={{ ...CT.td, color: '#4d9fff', fontFamily: 'monospace' }}>#{d.account || d.login || '—'}</td>
                    <td style={{ ...CT.td, color: '#888' }}>{d.method || '—'}</td>
                    <td style={CT.td}>
                      <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, background: (d.status||'approved') === 'approved' ? 'rgba(0,229,160,0.1)' : 'rgba(255,170,0,0.1)', color: (d.status||'approved') === 'approved' ? '#00e5a0' : '#ffaa00' }}>{t(d.status||'approved')}</span>
                    </td>
                    <td style={{ ...CT.td, color: '#555', fontFamily: 'monospace', fontSize: 11 }}>{d.deal_id || d.ref || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          </div>
        ); })()}

        {/* WITHDRAWALS */}
        {tab === 'withdrawals' && (() => { const list = client.withdrawals_list || client.withdrawals || []; const tot = list.reduce((s:number,d:any)=>s+(d.amount||0),0); return (
          <div>
            <div style={{ display:'flex', gap:10, marginBottom:10, flexWrap:'wrap' }}>
              {[[t('Total transactions'), list.length.toLocaleString('en-GB'), '#aeb6c2'],
                [t('Total withdrawn'), '$'+tot.toLocaleString(undefined,{maximumFractionDigits:2}), '#ff8888']].map(([l,v,c2]:any)=>(
                <div key={l} style={{ background:'linear-gradient(160deg,#2b323c,#242a33)', border:'1px solid #3a434f', borderRadius:10, padding:'9px 16px' }}>
                  <div style={{ fontSize:10, color:'#8b93a1', textTransform:'uppercase', letterSpacing:0.4 }}>{l}</div>
                  <div style={{ fontSize:16, fontWeight:800, color:c2 }}>{v}</div>
                </div>
              ))}
            </div>
          <div style={{ background: 'linear-gradient(160deg,#2c333e,#262c35)', border: '1px solid #3a434f', borderRadius: 12, overflow: 'hidden' }}>
            <table style={CT.table}>
              <thead>
                <tr style={CT.theadTr}>
                  {['Date','Amount','Trading account','Method','Status','Reference'].map(h => (
                    <th key={h} style={CT.th()}>{t(h)}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {list.map((d: any, i: number) => (
                  <tr key={i} style={CT.row()}>
                    <td style={{ ...CT.td, color: '#888' }}>{(()=>{const v=d.date||d.tx_date; return v? new Date(String(v).replace(' ','T')).toLocaleString('en-GB',{day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit',hour12:false}):'—';})()}</td>
                    <td style={{ ...CT.td, color: '#ff8888', fontWeight: 500 }}>${(d.amount||0).toLocaleString('en-GB')}</td>
                    <td style={{ ...CT.td, color: '#4d9fff', fontFamily: 'monospace' }}>#{d.account || d.login || '—'}</td>
                    <td style={{ ...CT.td, color: '#888' }}>{d.method || '—'}</td>
                    <td style={CT.td}>
                      <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, background: (d.status||'approved') === 'approved' ? 'rgba(0,229,160,0.1)' : 'rgba(255,77,77,0.1)', color: (d.status||'approved') === 'approved' ? '#00e5a0' : '#ff4d4d' }}>{t(d.status||'approved')}</span>
                    </td>
                    <td style={{ ...CT.td, color: '#555', fontFamily: 'monospace', fontSize: 11 }}>{d.deal_id || d.ref || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          </div>
        ); })()}

        {/* INTERNAL TRANSFERS (#87) — money moved between the client's own accounts */}
        {tab === 'transfers' && (
          <div style={{ background: 'linear-gradient(160deg,#2c333e,#262c35)', border: '1px solid #3a434f', borderRadius: 12, overflow: 'hidden' }}>
            <table style={CT.table}>
              <thead>
                <tr style={CT.theadTr}>
                  {['Date','From account','To account','Amount','Reference'].map(h => (
                    <th key={h} style={CT.th()}>{t(h)}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(client.transfers_list || []).length === 0 && (
                  <tr><td colSpan={5} style={{ padding: '18px 14px', color: '#666', textAlign: 'center' }}>{t("No internal transfers between this client's accounts.")}</td></tr>
                )}
                {(client.transfers_list || []).map((d: any, i: number) => (
                  <tr key={i} style={CT.row()}>
                    <td style={{ ...CT.td, color: '#888' }}>{d.date ? new Date(String(d.date).replace(' ','T')).toLocaleString('en-GB',{day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit',hour12:false}) : '—'}</td>
                    <td style={{ ...CT.td, color: '#ff8888', fontFamily: 'monospace' }}>{d.from_account || '—'}</td>
                    <td style={{ ...CT.td, color: '#00e5a0', fontFamily: 'monospace' }}>{d.to_account || '—'}</td>
                    <td style={{ ...CT.td, color: '#ddd', fontWeight: 500 }}>${(d.amount||0).toLocaleString('en-GB')}</td>
                    <td style={{ ...CT.td, color: '#555', fontFamily: 'monospace', fontSize: 11 }}>{d.deal_id || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* TRADING ACCOUNTS — view toggle (#5: cards / table) */}
        {tab === 'accounts' && !selectedAccount && (
          <div style={{ display:'flex', gap:6, marginBottom:10 }}>
            {(['cards','table'] as const).map(v => (
              <button key={v} onClick={()=>setAcctView(v)}
                style={{ padding:'4px 12px', borderRadius:7, fontSize:11, cursor:'pointer', textTransform:'capitalize',
                  border:`1px solid ${acctView===v?'#00e5a0':'#626d80'}`, background:acctView===v?'rgba(0,229,160,0.1)':'transparent', color:acctView===v?'#00e5a0':'#888' }}>{v==='cards'?'▦ '+t('Cards'):'☰ '+t('Table')}</button>
            ))}
          </div>
        )}
        {/* TABLE view */}
        {tab === 'accounts' && !selectedAccount && acctView==='table' && (
          <div style={{ overflowX:'auto', border:'1px solid #4f596b', borderRadius:10 }}>
            <table style={CT.table}>
              <thead><tr style={CT.theadTr}>{['Account #','Platform','Group','Balance','Equity','Status',''].map(h=>(
                <th key={h} style={CT.th()}>{t(h)}</th>))}</tr></thead>
              <tbody>
                {(client.related_accounts || []).map((acc:any,i:number)=>(
                  <tr key={i} style={{ ...CT.row(), cursor:'pointer' }} onClick={()=>setSelectedAccount(acc)}>
                    <td style={{ ...CT.td, fontFamily:'monospace', color:'#00e5a0' }}>#{acc.login}
                      <CopyBtn value={acc.login} style={{ marginLeft:6 }} /></td>
                    <td style={CT.td}>{acc.platform||'MT5'}</td>
                    <td style={{ ...CT.td, color:'#888' }}>{acc.group||acc.group_name||'—'}</td>
                    <td style={CT.td}>${(acc.balance||0).toLocaleString('en-GB')}</td>
                    <td style={CT.td}>${(acc.equity||0).toLocaleString('en-GB')}</td>
                    <td style={CT.td}>{acc.archived?'🗄 '+t('Archived'):(acc.is_active?t('Active'):t('Inactive'))}</td>
                    <td style={{ ...CT.td, color:'#4d9fff' }}>{t('open')} ›</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {/* CARDS view */}
        {tab === 'accounts' && !selectedAccount && acctView==='cards' && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(260px,1fr))', gap: 12 }}>
            {(client.related_accounts || []).map((acc: any, i: number) => (
              <div key={i} onClick={async () => { setSelectedAccount(acc); try { const full = await apiGet(`/trading-accounts/${acc.login}`); setSelectedAccount((prev:any)=> prev && prev.login===acc.login ? {...acc, ...full} : prev); } catch {} }}
                style={{ background: 'linear-gradient(160deg,#2c333e,#262c35)', border: '1px solid #3a434f', borderRadius: 12, padding: 16, cursor: 'pointer' }}
                onMouseEnter={e => (e.currentTarget.style.borderColor = '#00e5a0')}
                onMouseLeave={e => (e.currentTarget.style.borderColor = '#4f596b')}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
                  <div>
                    <div style={{ fontSize: 14, fontWeight: 500, fontFamily: 'monospace', display:'flex', alignItems:'center', gap:6 }}>#{acc.login}
                      <CopyBtn value={acc.login} /></div>
                    <div style={{ fontSize: 11, color: '#555', marginTop: 2 }}>{acc.group || acc.group_name}</div>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4 }}>
                    {acc.archived && <span title={t('Archived from MT4/MT5 — read-only (no deposit/transfer)')} style={{ fontSize: 10, fontWeight: 800, padding: '3px 8px', borderRadius: 99, background: 'rgba(255,170,0,0.15)', color: '#ffaa00', border: '1px solid rgba(255,170,0,0.35)' }}>🗄 {t('ARCHIVED')}</span>}
                    <span style={{ fontSize: 10, padding: '3px 8px', borderRadius: 99, background: acc.is_active ? 'rgba(0,229,160,0.1)' : 'rgba(255,77,77,0.1)', color: acc.is_active ? '#00e5a0' : '#ff4d4d' }}>{acc.is_active ? t('Active') : t('Inactive')}</span>
                    <span style={{ fontSize: 10, padding: '2px 7px', borderRadius: 99, background: acc.platform === 'MT4' ? 'rgba(255,170,0,0.12)' : 'rgba(0,102,255,0.12)', color: acc.platform === 'MT4' ? '#ffaa00' : '#4d9fff', fontWeight: 600 }}>{acc.platform || 'MT5'}</span>
                  </div>
                </div>
                {[[t('Balance'), `$${(acc.balance||0).toLocaleString('en-GB')}`], [t('Equity'), `$${(acc.equity||0).toLocaleString('en-GB')}`], [t('Group'), acc.group || acc.group_name || '—'], [t('Leverage'), acc.leverage ? '1:'+acc.leverage : '—'], [t('Active'), acc.is_active ? t('Yes') : t('No')]].map(([k,v]) => (
                  <div key={k as string} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, padding: '4px 0', borderBottom: '1px solid #373f4d' }}>
                    <span style={{ color: '#555' }}>{k}</span>
                    <span style={{ fontWeight: 500 }}>{v}</span>
                  </div>
                ))}
                <div style={{ marginTop: 10, fontSize: 11, color: '#00e5a0' }}>{t('Click to view trades →')}</div>
              </div>
            ))}
          </div>
        )}

        {/* ACCOUNT DETAIL */}
        {tab === 'accounts' && selectedAccount && (() => {
          const allHist = selectedAccount.trade_history || selectedAccount.history || [];
          // period filter (days) on the trade history — by close time (fallback open time)
          const hist = histDays === 0 ? allHist : allHist.filter((t:any) => {
            const v = t.close_time || t.open_time; if (!v) return true;
            const d = new Date(String(v).replace(' ','T')); if (isNaN(d.getTime())) return true;
            return (Date.now() - d.getTime()) <= histDays*24*3600*1000;
          });
          const pnl   = hist.reduce((s:number,t:any)=>s+(parseFloat(t.profit)||0),0);
          const wins  = hist.reduce((s:number,t:any)=>{const p=parseFloat(t.profit)||0; return p>0?s+p:s;},0);
          const losses= hist.reduce((s:number,t:any)=>{const p=parseFloat(t.profit)||0; return p<0?s+p:s;},0);
          return (
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
              <button onClick={() => setSelectedAccount(null)} style={{ background: '#373f4d', border: '1px solid #626d80', borderRadius: 8, color: '#888', padding: '5px 12px', cursor: 'pointer', fontSize: 12 }}>← {t('Accounts')}</button>
              <div style={{ fontSize: 14, fontWeight: 500 }}>{t('Account')} #{selectedAccount.login}</div>
            </div>
            <div style={{ display: 'flex', gap: 6, marginBottom: 14, flexWrap:'wrap', alignItems:'center' }}>
              {['open', 'history'].map(tb => (
                <button key={tb} onClick={() => setAccountTab(tb)}
                  style={{ padding: '6px 14px', borderRadius: 7, border: `1px solid ${accountTab === tb ? '#00e5a0' : '#626d80'}`, background: accountTab === tb ? 'rgba(0,229,160,0.1)' : 'transparent', color: accountTab === tb ? '#00e5a0' : '#888', cursor: 'pointer', fontSize: 12 }}>
                  {tb === 'open' ? t('Open positions') : t('Trade history')}
                </button>
              ))}
              {accountTab === 'history' && (
                <div style={{ display:'flex', gap:4, marginLeft:'auto' }}>
                  {[[0,t('All time')],[7,t('7 days')],[30,t('30 days')],[90,t('90 days')],[365,t('1 year')]].map(([d,l]:any)=>(
                    <button key={d} onClick={()=>setHistDays(d)}
                      style={{ padding:'4px 10px', borderRadius:6, fontSize:11, cursor:'pointer', border:`1px solid ${histDays===d?'#00e5a0':'#626d80'}`, background:histDays===d?'rgba(0,229,160,0.1)':'transparent', color:histDays===d?'#00e5a0':'#888' }}>{l}</button>
                  ))}
                </div>
              )}
            </div>
            {/* summary strip — closed trades + PnL for the selected period */}
            {accountTab === 'history' && (
              <div style={{ display:'flex', gap:10, marginBottom:12, flexWrap:'wrap' }}>
                {[[t('Closed trades'), hist.length.toLocaleString('en-GB'), '#aeb6c2'],
                  [t('Total PnL'), (pnl<0?'-':'')+'$'+Math.abs(pnl).toLocaleString(undefined,{maximumFractionDigits:2}), pnl>=0?'#00e5a0':'#ff6b6b'],
                  [t('Profit (wins)'), '$'+wins.toLocaleString(undefined,{maximumFractionDigits:2}), '#00e5a0'],
                  [t('Loss'), '-$'+Math.abs(losses).toLocaleString(undefined,{maximumFractionDigits:2}), '#ff8888']].map(([l,v,c2]:any)=>(
                  <div key={l} style={{ background:'linear-gradient(160deg,#2b323c,#242a33)', border:'1px solid #3a434f', borderRadius:10, padding:'9px 16px' }}>
                    <div style={{ fontSize:10, color:'#8b93a1', textTransform:'uppercase', letterSpacing:0.4 }}>{l}</div>
                    <div style={{ fontSize:16, fontWeight:800, color:c2 }}>{v}</div>
                  </div>
                ))}
              </div>
            )}
            <div style={{ background: 'linear-gradient(160deg,#2c333e,#262c35)', border: '1px solid #3a434f', borderRadius: 12, overflow: 'hidden' }}>
              <table style={CT.table}>
                <thead>
                  <tr style={CT.theadTr}>
                    {accountTab === 'open'
                      ? ['Ticket','Symbol','Type','Volume','Open price','Current','Profit','Swap','Open time'].map(h => <th key={h} style={CT.th()}>{t(h)}</th>)
                      : ['Ticket','Symbol','Type','Volume','Open price','Close price','Profit','Open time','Close time'].map(h => <th key={h} style={CT.th()}>{t(h)}</th>)
                    }
                  </tr>
                </thead>
                <tbody>
                  {(accountTab === 'open' ? (selectedAccount.open_positions || selectedAccount.open_trades || []) : hist).map((t: any, i: number) => (
                    <tr key={i} style={CT.row()}>
                      <td style={{ ...CT.td, fontFamily: 'monospace', color: '#888' }}>{t.ticket}</td>
                      <td style={{ ...CT.td, fontWeight: 500 }}>{t.symbol}</td>
                      <td style={CT.td}><span style={{ color: (t.type || t.direction) === 'buy' ? '#00e5a0' : '#ff4d4d', fontWeight: 500 }}>{String(t.type || t.direction || '').toUpperCase()}</span></td>
                      <td style={{ ...CT.td, color: '#888' }}>{t.volume}</td>
                      <td style={{ ...CT.td, color: '#888' }}>{t.open_price}</td>
                      <td style={{ ...CT.td, color: '#888' }}>{t.current_price || t.close_price}</td>
                      <td style={{ ...CT.td, color: t.profit >= 0 ? '#00e5a0' : '#ff4d4d', fontWeight: 500 }}>${t.profit}</td>
                      {accountTab === 'open' && <td style={{ ...CT.td, color: '#888' }}>${t.swap}</td>}
                      <td style={{ ...CT.td, color: '#555', fontSize: 11 }}>{t.open_time}</td>
                      {accountTab === 'history' && <td style={{ ...CT.td, color: '#555', fontSize: 11 }}>{t.close_time}</td>}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          ); })()}

        {tab === 'calls' && (
          <div>
            {(client.actions_history || []).length === 0 ? (
              <div style={{ textAlign:'center', color:'#555', padding:40 }}>{t('No call history yet')}</div>
            ) : (client.actions_history || []).map((a: any, i: number) => (
              <div key={i} style={{ background:'#373f4d', borderRadius:10, padding:14, marginBottom:8, display:'flex', gap:12 }}>
                <div style={{ width:8, height:8, borderRadius:'50%', marginTop:5, flexShrink:0,
                  background: a.action==='connected_done'?'#00e5a0': a.action==='no_answer'?'#ffaa00':'#ff4d4d' }} />
                <div style={{ flex:1 }}>
                  <div style={{ display:'flex', alignItems:'center', gap:8 }}>
                    <span style={{ fontSize:12, fontWeight:500,
                      color: a.action==='connected_done'?'#00e5a0': a.action==='no_answer'?'#ffaa00':'#ff4d4d' }}>
                      {t((actionLabels as any)[a.action] || a.action)}
                    </span>
                    <span style={{ fontSize:11, color:'#555' }}>{a.created_at ? new Date(a.created_at).toLocaleString('en-GB') : ''}</span>
                  </div>
                  {a.note && <div style={{ fontSize:12, color:'#888', marginTop:4 }}>{a.note}</div>}
                </div>
              </div>
            ))}
          </div>
        )}

        {tab === 'network' && (
          <div>
            <div style={{ fontSize:12, color:'#8a93a3', marginBottom:10, lineHeight:1.5 }}>
              {t("Accounts linked to this client, ranked by how certain we are it's the same person/ring (device · email · phone · IB · city · payment · IP). The % and x/10 is our confidence.")}
            </div>
            {!conns ? (
              <div style={{ textAlign:'center', color:'#556', padding:30 }}>{t('Loading connections…')}</div>
            ) : (conns.connections || []).length === 0 ? (
              <div style={{ textAlign:'center', color:'#555', padding:40 }}>{t('No network connections found')}</div>
            ) : (conns.connections || []).map((c: any, i: number) => <ConnRow key={i} c={c} subjectName={conns?.subject?.name} onOpen={openConn} />)}
          </div>
        )}


      </div>
        </div>{/* end LEFT 70% */}

        {/* RIGHT 30% — Connections (top 40%) over Comments centre (bottom 60%) */}
        <div style={{ minWidth:0, display:'grid', gridTemplateRows:'minmax(0,2fr) minmax(0,3fr)', gap:16, overflow:'hidden' }}>

          {/* TOP 40% — Connections */}
          <div style={{ minHeight:0, display:'flex', flexDirection:'column', background:'linear-gradient(160deg,#2c333e,#262c35)', border:'1px solid #3a434f', borderRadius:16, overflow:'hidden', boxShadow:'0 6px 22px rgba(0,0,0,0.28)' }}>
            <div style={{ display:'flex', alignItems:'center', gap:8, padding:'12px 16px', borderBottom:'1px solid #373f4d', flexShrink:0 }}>
              <span style={{ fontSize:13, fontWeight:700 }}>🕸️ {t('Connections')}</span>
              {(conns?.connections?.length>0) && <span style={{ fontSize:10, color:'#8a93a3', background:'#373f4d', padding:'2px 7px', borderRadius:99 }}>{conns.connections.length}</span>}
              {(conns?.connections?.length>0) && <button onClick={()=>setTab('network')} style={{ marginLeft:'auto', background:'none', border:'none', color:'#00e5a0', fontSize:11, cursor:'pointer' }}>{t('See all')} →</button>}
            </div>
            <div style={{ flex:1, overflowY:'auto', padding:'10px 12px' }}>
              <div style={{ fontSize:10.5, color:'#667', marginBottom:8 }}>{t('Linked accounts by shared device · phone · email · IB · IP. Click a row for the matching details.')}</div>
              {!conns ? <div style={{ color:'#556', fontSize:12, padding:8 }}>{t('Loading…')}</div>
                : (conns.connections||[]).length===0 ? <div style={{ color:'#556', fontSize:12, padding:8 }}>{t('No linked accounts found.')}</div>
                : (conns.connections||[]).slice(0,10).map((c:any,i:number)=><ConnRow key={i} c={c} subjectName={conns?.subject?.name} onOpen={openConn} />)}
            </div>
          </div>

          {/* BOTTOM 60% — Comments centre */}
          <div style={{ minHeight:0, display:'flex', flexDirection:'column', background:'linear-gradient(160deg,#2c333e,#262c35)', border:'1px solid #3a434f', borderRadius:16, overflow:'hidden', boxShadow:'0 6px 22px rgba(0,0,0,0.28)' }}>
            <div style={{ display:'flex', alignItems:'center', gap:8, padding:'12px 16px', borderBottom:'1px solid #373f4d', flexShrink:0 }}>
              <span style={{ fontSize:13, fontWeight:700 }}>💬 {t('Comments')}</span>
              {comments.length>0 && <span style={{ fontSize:10, color:'#8a93a3', background:'#373f4d', padding:'2px 7px', borderRadius:99 }}>{comments.length}</span>}
              <span style={{ marginLeft:'auto', fontSize:10, color:'#667' }}>{t('all departments')}</span>
            </div>
            {/* feed — oldest at top, newest at the bottom (chat-style) */}
            <div ref={feedRef} style={{ flex:1, overflowY:'auto', padding:'12px 14px', display:'flex', flexDirection:'column', gap:10 }}>
              {orderedComments.length===0 ? <div style={{ color:'#556', fontSize:12, textAlign:'center', padding:'24px 0' }}>{t('No comments yet.')}<br/>{t('Start the conversation below.')}</div>
                : orderedComments.map((c:any,i:number)=>{
                  const who  = String(c.agent_name || c.agent_id || 'Agent');
                  const hue  = nameHue(who);
                  const dcol = deptColor(c.dept || '');
                  return (
                  <div key={c.id ?? i} style={{ display:'flex', gap:10, alignItems:'flex-start' }}>
                    {/* avatar — stable colour per person */}
                    <div title={who} style={{ width:34, height:34, borderRadius:'50%', flexShrink:0, display:'flex', alignItems:'center', justifyContent:'center', fontSize:12, fontWeight:800, color:'#fff', background:`linear-gradient(135deg, hsl(${hue} 62% 48%), hsl(${(hue+38)%360} 62% 40%))`, boxShadow:`0 2px 8px hsl(${hue} 55% 28% / 0.55)`, border:'1px solid rgba(255,255,255,0.14)', marginTop:1 }}>
                      {initials(who)}
                    </div>
                    {/* bubble — dept-coloured accent, name + dept pill + relative time */}
                    <div style={{ flex:1, minWidth:0, background:'linear-gradient(180deg,#2a313d,#262c36)', border:'1px solid #333b47', borderLeft:`3px solid ${dcol}`, borderRadius:'5px 12px 12px 12px', padding:'9px 12px', boxShadow:'0 1px 3px rgba(0,0,0,0.25)' }}>
                      <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:5 }}>
                        <span style={{ color:'#f2f4f8', fontWeight:700, fontSize:12.5, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{who}</span>
                        {c.agent_title && <span style={{ color:'#8a93a5', fontSize:10, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap', maxWidth:120 }} title={c.agent_title}>{c.agent_title}</span>}
                        {c.dept && <span style={{ fontSize:8.5, fontWeight:800, letterSpacing:.4, textTransform:'uppercase', color:dcol, background:`${dcol}20`, border:`1px solid ${dcol}55`, borderRadius:20, padding:'1px 8px', flexShrink:0 }}>{c.dept}</span>}
                        <span title={c.created_at? new Date(c.created_at).toLocaleString('en-GB'):''} style={{ marginLeft:'auto', color:'#6b7688', fontSize:10.5, flexShrink:0, cursor:'default' }}>{relTime(c.created_at)}</span>
                      </div>
                      {editingId === c.id ? (
                        <div>
                          <textarea value={editText} onChange={e=>setEditText(e.target.value)} rows={2} autoFocus
                            style={{ width:'100%', padding:'8px 10px', background:'#373f4d', border:'1px solid #4f596b', borderRadius:8, color:'#fff', fontSize:12.5, outline:'none', resize:'vertical', boxSizing:'border-box' as any, fontFamily:'inherit' }} />
                          <div style={{ display:'flex', gap:8, marginTop:6 }}>
                            <button onClick={()=>saveEdit(c, editText)} style={{ padding:'5px 12px', background:'#00e5a0', border:'none', borderRadius:7, color:'#20252f', fontWeight:700, fontSize:11.5, cursor:'pointer' }}>{t('Save')}</button>
                            <button onClick={()=>{ setEditingId(null); setEditText(''); }} style={{ padding:'5px 12px', background:'#373f4d', border:'1px solid #4f596b', borderRadius:7, color:'#c7ccd6', fontWeight:600, fontSize:11.5, cursor:'pointer' }}>{t('Cancel')}</button>
                          </div>
                        </div>
                      ) : (
                        <>
                          <div style={{ fontSize:12.5, color:'#ccd2dc', lineHeight:1.55, whiteSpace:'pre-wrap', wordBreak:'break-word' }}>{c.note}</div>
                          {canEditComment(c) && (
                            <div style={{ display:'flex', gap:12, marginTop:7, alignItems:'center' }}>
                              <button onClick={()=>{ setEditingId(c.id); setEditText(c.note); }} style={{ background:'none', border:'none', color:'#7cc4ff', fontSize:11, cursor:'pointer', padding:0 }}>✏️ {t('Edit')}</button>
                              <button onClick={()=>deleteComment(c)} style={{ background:'none', border:'none', color:'#ff7a7a', fontSize:11, cursor:'pointer', padding:0 }}>🗑 {t('Delete')}</button>
                              <span style={{ color:'#5a6472', fontSize:10 }} title={t('You can edit or delete this comment for 60 minutes after posting')}>{t('editable for 60 min')}</span>
                            </div>
                          )}
                        </>
                      )}
                    </div>
                  </div>
                  );
                })}
            </div>
            {/* composer */}
            <div style={{ borderTop:'1px solid #373f4d', padding:'10px 12px', background:'#262c36', flexShrink:0 }}>
              <textarea value={commentText} onChange={e=>setCommentText(e.target.value)} placeholder={t('Write a note about this client… (Enter to save, Shift+Enter = new line)')} rows={2}
                onKeyDown={e=>{ if(e.key==='Enter' && !e.shiftKey && !e.ctrlKey && !e.metaKey){ e.preventDefault(); if(commentText.trim()) postComment(); } }}
                style={{ width:'100%', padding:'8px 10px', background:'#373f4d', border:'1px solid #4f596b', borderRadius:8, color:'#fff', fontSize:12.5, outline:'none', resize:'none', boxSizing:'border-box' as any, fontFamily:'inherit' }} />
              <div style={{ display:'flex', gap:8, marginTop:8, alignItems:'center' }}>
                <span title={t('Your department (fixed by your role)')} style={{ padding:'5px 11px', background:`${deptColor(commentDept)}20`, border:`1px solid ${deptColor(commentDept)}55`, borderRadius:20, color:deptColor(commentDept), fontSize:10.5, fontWeight:800, textTransform:'uppercase', letterSpacing:.3 }}>{commentDept}</span>
                <button onClick={postComment} disabled={postingComment||!commentText.trim()} style={{ marginLeft:'auto', padding:'7px 18px', background:commentText.trim()?'#00e5a0':'#4f596b', border:'none', borderRadius:8, color:commentText.trim()?'#20252f':'#667', fontWeight:700, cursor:commentText.trim()?'pointer':'default', fontSize:12 }}>{postingComment?'…':t('Post')}</button>
              </div>
            </div>
          </div>
        </div>{/* end RIGHT 30% */}

      </div>{/* end two-pane body */}

      {editOpen && (
        <ClientEditModal
          client={client}
          onClose={() => setEditOpen(false)}
          onSaved={(upd: any) => { setClient((prev: any) => ({ ...prev, ...upd })); setEditOpen(false); }}
        />
      )}

      {addAcctOpen && (
        <AddAccountModal client={client} onClose={() => setAddAcctOpen(false)} />
      )}
    </div>
  );
}

// ── CREATE ADDITIONAL ACCOUNT MODAL (admin only — ticket #98, CREATE ONLY, no delete) ──
function AddAccountModal({ client, onClose }: any) {
  const t = useT();
  const [accountType, setAccountType] = useState('Standard');
  const [platform, setPlatform]       = useState('MT5');
  const [islamic, setIslamic]         = useState(false);
  const [leverage, setLeverage]       = useState(500);
  const [credit, setCredit]           = useState(0);
  const [submitting, setSubmitting]   = useState(false);
  const [error, setError]             = useState('');
  const [result, setResult]           = useState<any>(null);   // { login, password, investor_password, group }

  const submit = async () => {
    setSubmitting(true); setError('');
    try {
      const res = await apiPost(`/clients/${client.login}/additional-account`, {
        account_type: accountType, platform, islamic, leverage: Number(leverage),
        initial_credit: Number(credit) || 0,
      });
      // apiPost resolves even on HTTP 4xx/5xx (it doesn't reject); a FastAPI error body
      // is {detail: ...} with no login, so treat anything without ok+login as an error.
      if (res && res.ok && res.login) setResult(res);
      else setError((res && (res.detail || res.error)) || t('Failed to create account'));
    } catch (e: any) {
      setError(e?.message || t('Failed to create account'));
    }
    setSubmitting(false);
  };

  const copy = (txt: string) => { copyText(txt); };

  const inputStyle: any = { width:'100%', padding:'8px 10px', borderRadius:8, border:'1px solid #4f596b', background:'#373f4d', color:'#fff', fontSize:13, boxSizing:'border-box' };
  const labelStyle: any = { fontSize:11, color:'#9aa3b3', marginBottom:4, display:'block' };

  return (
    <div onClick={onClose} style={{ position:'fixed', inset:0, background:'rgba(0,0,0,0.6)', zIndex:900, display:'flex', alignItems:'center', justifyContent:'center' }}>
      <div onClick={e => e.stopPropagation()} style={{ background:'#2c333e', border:'1px solid #4f596b', borderRadius:14, padding:24, width:440, maxWidth:'92vw', maxHeight:'90vh', overflowY:'auto', color:'#fff' }}>
        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:4 }}>
          <div style={{ fontSize:16, fontWeight:600 }}>➕ {t('Create additional account')}</div>
          <button onClick={onClose} style={{ background:'transparent', border:'none', color:'#888', fontSize:20, cursor:'pointer' }}>×</button>
        </div>
        <div style={{ fontSize:12, color:'#9aa3b3', marginBottom:16 }}>{t('For')} {client.name} (#{client.login}) {t('— a NEW real MT account on the live server.')}</div>

        {!result ? (
          <>
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:12, marginBottom:12 }}>
              <div>
                <label style={labelStyle}>{t('Account type')}</label>
                <select value={accountType} onChange={e => setAccountType(e.target.value)} style={inputStyle}>
                  {['Standard','Cent','Zero','VIP','Fix'].map(o => <option key={o} value={o}>{o}</option>)}
                </select>
              </div>
              <div>
                <label style={labelStyle}>{t('Platform')}</label>
                <select value={platform} onChange={e => setPlatform(e.target.value)} style={inputStyle}>
                  <option value="MT5">MT5</option>
                  <option value="MT4">MT4 {t('(not supported yet)')}</option>
                </select>
              </div>
              <div>
                <label style={labelStyle}>{t('Leverage (1:N)')}</label>
                <select value={leverage} onChange={e => setLeverage(Number(e.target.value))} style={inputStyle}>
                  {[50,100,200,300,400,500,1000].map(l => <option key={l} value={l}>1:{l}</option>)}
                </select>
              </div>
              <div>
                <label style={labelStyle}>{t('Initial credit ($, optional)')}</label>
                <input type="number" min={0} value={credit} onChange={e => setCredit(Number(e.target.value))} style={inputStyle} />
              </div>
            </div>
            <label style={{ display:'flex', alignItems:'center', gap:8, fontSize:13, marginBottom:16, cursor:'pointer' }}>
              <input type="checkbox" checked={islamic} onChange={e => setIslamic(e.target.checked)} />
              {t('Islamic (swap-free) account')}
            </label>

            {error && <div style={{ background:'rgba(255,77,77,0.1)', border:'1px solid rgba(255,77,77,0.3)', color:'#ff7a7a', padding:'8px 12px', borderRadius:8, fontSize:12, marginBottom:12 }}>{error}</div>}

            <div style={{ display:'flex', gap:10, justifyContent:'flex-end' }}>
              <button onClick={onClose} style={{ padding:'9px 16px', borderRadius:8, border:'1px solid #4f596b', background:'transparent', color:'#aaa', cursor:'pointer', fontSize:13 }}>{t('Cancel')}</button>
              <button onClick={submit} disabled={submitting || platform !== 'MT5'} style={{ padding:'9px 18px', borderRadius:8, border:'none', background: (submitting||platform!=='MT5') ? '#555' : 'linear-gradient(135deg,#7a4dff,#9966ff)', color:'#fff', cursor:(submitting||platform!=='MT5')?'not-allowed':'pointer', fontSize:13, fontWeight:600 }}>{submitting ? t('Creating…') : t('Create account')}</button>
            </div>
          </>
        ) : (
          <div>
            <div style={{ background:'rgba(0,229,160,0.1)', border:'1px solid rgba(0,229,160,0.3)', borderRadius:10, padding:16, marginBottom:14 }}>
              <div style={{ fontSize:14, fontWeight:600, color:'#00e5a0', marginBottom:10 }}>✓ {t('Account created')}</div>
              {[[t('Login'), result.login],[t('Password'), result.password],[t('Investor password'), result.investor_password],[t('Group'), result.group]].map(([k,v]) => v != null && (
                <div key={k as string} style={{ display:'flex', justifyContent:'space-between', alignItems:'center', padding:'6px 0', borderBottom:'1px solid rgba(255,255,255,0.08)', fontSize:13 }}>
                  <span style={{ color:'#9aa3b3' }}>{k as string}</span>
                  <span style={{ display:'flex', alignItems:'center', gap:8 }}>
                    <code style={{ fontWeight:600 }}>{String(v)}</code>
                    <button onClick={() => copy(String(v))} title={t('Copy')} style={{ background:'transparent', border:'1px solid #4f596b', borderRadius:6, color:'#9aa3b3', cursor:'pointer', fontSize:11, padding:'2px 7px' }}>{t('copy')}</button>
                  </span>
                </div>
              ))}
            </div>
            {result.warning && <div style={{ background:'rgba(255,170,0,0.1)', border:'1px solid rgba(255,170,0,0.3)', color:'#ffcc66', padding:'8px 12px', borderRadius:8, fontSize:12, marginBottom:12 }}>⚠️ {result.warning}</div>}
            <div style={{ fontSize:12, color:'#ffaa00', marginBottom:14 }}>⚠️ {t('Save the password now — it is shown only once.')}</div>
            <div style={{ display:'flex', justifyContent:'flex-end' }}>
              <button onClick={onClose} style={{ padding:'9px 18px', borderRadius:8, border:'none', background:'#00e5a0', color:'#0a0e14', cursor:'pointer', fontSize:13, fontWeight:600 }}>{t('Done')}</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── CLIENT EDIT MODAL (admin: email / phone / password / DOB / English name / verify) ──
function ClientEditModal({ client, onClose, onSaved }: any) {
  const t = useT();
  const [email, setEmail] = useState(client.email || '');
  const [phone, setPhone] = useState(client.phone || '');
  const [password, setPassword] = useState('');
  const [dob, setDob] = useState((client.date_of_birth || '').slice(0, 10));
  const [nameEn, setNameEn] = useState(client.full_name_en || '');
  const [emailVer, setEmailVer] = useState(!!client.email_verified);
  const [phoneVer, setPhoneVer] = useState(!!client.phone_verified);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');

  const suggestion = client.ocr_name_en || '';

  const save = async () => {
    if (!email.trim()) { setErr(t('Email cannot be empty')); return; }
    setSaving(true); setErr('');
    try {
      const r = await apiPatch(`/clients/${client.login}/contact`, {
        email: email.trim(),
        phone: phone.trim(),
        password: password.trim() || undefined,
        date_of_birth: dob.trim() || null,
        full_name_en: nameEn.trim() || null,
        email_verified: emailVer,
        phone_verified: phoneVer,
      });
      onSaved({
        email: r.email, phone: r.phone, date_of_birth: r.date_of_birth,
        full_name_en: r.full_name_en, email_verified: r.email_verified, phone_verified: r.phone_verified,
      });
    } catch (e: any) {
      setErr(e?.message || e?.detail || t('Failed to save'));
      setSaving(false);
    }
  };

  const lbl: React.CSSProperties = { fontSize: 11, color: '#888', marginBottom: 4, display: 'block' };
  const inp: React.CSSProperties = { width: '100%', padding: '9px 11px', background: '#1c2231', border: '1px solid #4f596b', borderRadius: 8, color: '#fff', fontSize: 13, outline: 'none', boxSizing: 'border-box' };

  return (
    <div onClick={onClose} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', zIndex: 700, display: 'flex', alignItems: 'flex-start', justifyContent: 'center', overflowY: 'auto', padding: '5vh 16px' }}>
      <div onClick={e => e.stopPropagation()} style={{ background: '#2c333e', border: '1px solid #4f596b', borderRadius: 14, padding: 22, width: 440, maxWidth: '100%' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <div style={{ fontSize: 15, fontWeight: 700, color: '#fff' }}>{t('Edit contact / credentials')}</div>
          <button onClick={onClose} style={{ background: 'transparent', border: 'none', color: '#888', fontSize: 20, cursor: 'pointer' }}>×</button>
        </div>

        <div style={{ display: 'grid', gap: 12 }}>
          <div>
            <label style={lbl}>{t('Email')}</label>
            <input value={email} onChange={e => setEmail(e.target.value)} style={inp} />
          </div>
          <div>
            <label style={lbl}>{t('Phone')}</label>
            <input value={phone} onChange={e => setPhone(e.target.value)} style={inp} />
          </div>
          <div>
            <label style={lbl}>{t('New portal password')} <span style={{ color: '#555' }}>({t('leave blank to keep')})</span></label>
            <input value={password} onChange={e => setPassword(e.target.value)} type="text" autoComplete="off" placeholder="••••••••" style={inp} />
            <div style={{ fontSize: 10, color: '#666', marginTop: 4 }}>{t("Setting a password logs out the client's existing portal sessions.")}</div>
          </div>
          <div>
            <label style={lbl}>{t('Date of birth')}</label>
            <input value={dob} onChange={e => setDob(e.target.value)} type="date" max={new Date().toISOString().slice(0,10)} style={inp} />
          </div>
          <div>
            <label style={lbl}>{t('Full name (English, 3-part)')}</label>
            <input value={nameEn} onChange={e => setNameEn(e.target.value)} placeholder={t('e.g. Ahmed Ali Hassan')} style={inp} />
            {suggestion && suggestion !== nameEn && (
              <div style={{ fontSize: 10, color: '#00aaff', marginTop: 4, cursor: 'pointer' }} onClick={() => setNameEn(suggestion)}>
                {t('Suggested from KYC:')} {suggestion} {t('— click to use')}
              </div>
            )}
          </div>
          <div style={{ display: 'flex', gap: 16, marginTop: 2 }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 12, color: '#ccc', cursor: 'pointer' }}>
              <input type="checkbox" checked={emailVer} onChange={e => setEmailVer(e.target.checked)} /> {t('Email verified')}
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 12, color: '#ccc', cursor: 'pointer' }}>
              <input type="checkbox" checked={phoneVer} onChange={e => setPhoneVer(e.target.checked)} /> {t('Phone verified')}
            </label>
          </div>
          {err && <div style={{ fontSize: 12, color: '#ff5d6c' }}>{err}</div>}
          <div style={{ display: 'flex', gap: 10, marginTop: 6 }}>
            <button onClick={onClose} style={{ flex: 1, padding: '10px', background: '#373f4d', border: '1px solid #4f596b', borderRadius: 8, color: '#ccc', fontSize: 13, cursor: 'pointer' }}>{t('Cancel')}</button>
            <button onClick={save} disabled={saving} style={{ flex: 2, padding: '10px', background: '#00e5a0', border: 'none', borderRadius: 8, color: '#06251b', fontSize: 13, fontWeight: 700, cursor: 'pointer', opacity: saving ? 0.6 : 1 }}>{saving ? t('Saving…') : t('Save changes')}</button>
          </div>
        </div>
      </div>
    </div>
  );
}

const deptColors: any = { Sales: '#0066ff', Compliance: '#ff4d4d', Finance: '#00e5a0', Support: '#9966ff', Verification: '#ffaa00', Backoffice: '#888', IB: '#ff8c00' };
const deptColor = (d: string) => deptColors[d] || '#888';
const deptBg    = (d: string) => `${deptColors[d] || '#888'}22`;
const deptText  = (d: string) => deptColors[d] || '#888';

// ── Comment-feed helpers: a stable, recognisable avatar colour + initials per poster, and a
//    human relative time. (Comments UI polish.) ──
function nameHue(s: string): number { let h = 0; const v = String(s || ''); for (let i = 0; i < v.length; i++) h = (h * 31 + v.charCodeAt(i)) >>> 0; return h % 360; }
function initials(s: string): string {
  const parts = String(s || '').trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return 'A';
  return (parts[0][0] + (parts.length > 1 ? parts[parts.length - 1][0] : '')).toUpperCase();
}
function relTime(iso: string): string {
  if (!iso) return '';
  const d = new Date(iso).getTime(); if (isNaN(d)) return '';
  const s = Math.floor((Date.now() - d) / 1000);
  if (s < 45) return 'just now';
  const m = Math.floor(s / 60); if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60); if (h < 24) return `${h}h ago`;
  const dy = Math.floor(h / 24); if (dy < 7) return `${dy}d ago`;
  return new Date(iso).toLocaleDateString('en-GB');
}

// ── EMAIL MODAL ──────────────────────────────────────────────────────────
// Click-to-call now goes through the backend Yeastar proxy (see placeCall in api.ts),
// which holds the PBX credentials/token. Falls back to a tel: link automatically.
const yeastarCall = placeCall;

// ── PHONE MODAL ─────────────────────────────────────────────────────────
function PhoneModal({ client, onClose }: any) {
  const t = useT();
  const [calling, setCalling] = useState(false);
  const [called, setCalled] = useState(false);
  const phone = client.phone || '';
  const whatsappNum = phone.replace(/[^0-9]/g,'');

  const handleCall = async () => {
    setCalling(true);
    await yeastarCall(phone);
    setCalling(false);
    setCalled(true);
    setTimeout(onClose, 2000);
  };

  const handleWhatsApp = () => {
    window.open(`https://wa.me/${whatsappNum}?text=Hello ${client.name}, this is ${localStorage.getItem('userName') || 'your broker team'}. How can I assist you today?`, '_blank');
    onClose();
  };

  return (
    <div style={{ position:'fixed', inset:0, background:'rgba(0,0,0,0.75)', zIndex:9999, display:'flex', alignItems:'center', justifyContent:'center' }} onClick={onClose}>
      <div style={{ background:'#2c333e', border:'1px solid #626d80', borderRadius:14, padding:24, width:320 }} onClick={e => e.stopPropagation()}>
        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:20 }}>
          <div style={{ fontSize:14, fontWeight:500 }}>{t('Contact')} {client.name}</div>
          <div onClick={onClose} style={{ cursor:'pointer', color:'#555', fontSize:18 }}>✕</div>
        </div>

        <div style={{ display:'flex', alignItems:'center', gap:10, padding:'10px 14px', background:'#373f4d', borderRadius:10, marginBottom:16 }}>
          <div style={{ width:36, height:36, borderRadius:10, background:'linear-gradient(135deg,#0066ff,#9966ff)', display:'flex', alignItems:'center', justifyContent:'center', fontWeight:700, fontSize:15 }}>{client.name?.[0]}</div>
          <div>
            <div style={{ fontSize:13, fontWeight:500 }}>{client.name}</div>
            <div style={{ fontSize:12, color:'#888', fontFamily:'monospace' }}>{phone || t('No phone number')}</div>
          </div>
        </div>

        {!phone ? (
          <div style={{ textAlign:'center', color:'#555', fontSize:13, padding:'20px 0' }}>{t('No phone number on record')}</div>
        ) : (
          <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
            <button onClick={handleCall} disabled={calling || called}
              style={{ display:'flex', alignItems:'center', gap:12, padding:'14px 16px', background: called ? 'rgba(0,229,160,0.1)' : 'rgba(0,229,160,0.08)', border:`1px solid ${called?'#00e5a0':'rgba(0,229,160,0.3)'}`, borderRadius:10, color: called?'#00e5a0':'#00e5a0', cursor: called?'default':'pointer', fontSize:14, fontWeight:500 }}>
              <div style={{ width:40, height:40, borderRadius:10, background:'rgba(0,229,160,0.15)', display:'flex', alignItems:'center', justifyContent:'center', fontSize:20 }}>
                {called ? '✓' : calling ? '⟳' : '📞'}
              </div>
              <div style={{ textAlign:'left' }}>
                <div style={{ fontSize:13, fontWeight:500 }}>{called ? t('Call initiated!') : calling ? t('Connecting via Yeastar...') : t('Call via Yeastar PBX')}</div>
                <div style={{ fontSize:11, color:'#555', marginTop:2 }}>{called ? t('Check your desk phone') : t('Rings your extension then dials client')}</div>
              </div>
            </button>

            <button onClick={handleWhatsApp}
              style={{ display:'flex', alignItems:'center', gap:12, padding:'14px 16px', background:'rgba(37,211,102,0.08)', border:'1px solid rgba(37,211,102,0.3)', borderRadius:10, color:'#25d366', cursor:'pointer', fontSize:14, fontWeight:500 }}>
              <div style={{ width:40, height:40, borderRadius:10, background:'rgba(37,211,102,0.15)', display:'flex', alignItems:'center', justifyContent:'center', fontSize:20 }}>💬</div>
              <div style={{ textAlign:'left' }}>
                <div style={{ fontSize:13, fontWeight:500 }}>{t('Open WhatsApp')}</div>
                <div style={{ fontSize:11, color:'#555', marginTop:2 }}>{t('Opens chat with greeting pre-filled')}</div>
              </div>
            </button>

            <button onClick={() => { window.location.href = `tel:${dialNumber(phone)}`; onClose(); }}
              style={{ display:'flex', alignItems:'center', gap:12, padding:'14px 16px', background:'rgba(0,102,255,0.08)', border:'1px solid rgba(0,102,255,0.3)', borderRadius:10, color:'#4d9fff', cursor:'pointer', fontSize:14, fontWeight:500 }}>
              <div style={{ width:40, height:40, borderRadius:10, background:'rgba(0,102,255,0.15)', display:'flex', alignItems:'center', justifyContent:'center', fontSize:20 }}>📱</div>
              <div style={{ textAlign:'left' }}>
                <div style={{ fontSize:13, fontWeight:500 }}>{t('Regular call (device)')}</div>
                <div style={{ fontSize:11, color:'#555', marginTop:2 }}>{t('Uses your phone or PC dialer')}</div>
              </div>
            </button>
          </div>
        )}

        <div style={{ marginTop:14, padding:'8px 12px', background:'#373f4d', borderRadius:8, fontSize:11, color:'#555' }}>
          💡 {t('Yeastar PBX connected. Set your agent extension in Settings (defaults to ext 101).')}
        </div>
      </div>
    </div>
  );
}

// ── EMAIL MODAL ─────────────────────────────────────────────────────────
function EmailModal({ client, onClose }: any) {
  const t = useT();
  const CUSTOM_ID = 'custom';
  const allTemplates = [
    { id: CUSTOM_ID, subject: '', body: '', label: '✏️ Custom email' },
    ...EMAIL_TEMPLATES.map(t => ({ ...t, label: t.subject.replace(/🌙|⚠️/g,'').trim() }))
  ];

  const [selectedId, setSelectedId] = useState(CUSTOM_ID);
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [fromName, setFromName] = useState('Your Sales Team');
  const [sent, setSent] = useState(false);
  const [attachments, setAttachments] = useState<any[]>([]);  // {name, media_type, data(b64), size, url}
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');

  const pick = (tpl: any) => {
    setSelectedId(tpl.id);
    if (tpl.id === CUSTOM_ID) { setSubject(''); setBody(''); return; }
    setSubject(tpl.subject);
    setBody(tpl.body.replace(/\{name\}/g, client.name).replace(/\{agent\}/g, fromName));
  };

  // ── Image attachments (#185): client-side gate mirrors the server (images only, ≤5 MB, ≤5) ──
  const ALLOWED = ['image/png', 'image/jpeg', 'image/jpg', 'image/gif'];
  const MAXF = 5 * 1024 * 1024;
  const addFiles = (files: FileList | null) => {
    setError('');
    for (const f of Array.from(files || [])) {
      if (attachments.length >= 5) { setError(t('You can attach up to 5 images.')); break; }
      if (!ALLOWED.includes(f.type)) { setError(t('Only PNG, JPEG or GIF images are allowed.')); continue; }
      if (f.size > MAXF) { setError(`"${f.name}" ${t('is over 5 MB.')}`); continue; }
      const reader = new FileReader();
      reader.onload = () => {
        const dataUrl = String(reader.result || '');
        const b64 = dataUrl.split(',')[1] || '';
        setAttachments(prev => prev.length >= 5 ? prev : [...prev, {
          name: f.name, media_type: f.type === 'image/jpg' ? 'image/jpeg' : f.type, data: b64, size: f.size, url: dataUrl,
        }]);
      };
      reader.readAsDataURL(f);
    }
  };
  const removeAtt = (i: number) => setAttachments(prev => prev.filter((_, idx) => idx !== i));

  const send = async () => {
    if (!subject || !body || sending) return;
    setSending(true); setError('');
    try {
      await apiPost('/client-email/send', {
        to: client.email, subject, body, from_name: fromName,
        attachments: attachments.map(a => ({ name: a.name, media_type: a.media_type, data: a.data })),
      });
      setSent(true); setTimeout(onClose, 1800);
    } catch (e: any) {
      setError(e?.message || t('Could not send the email. Please try again.'));
    } finally {
      setSending(false);
    }
  };

  return (
    <div style={{ position:'fixed', inset:0, background:'rgba(0,0,0,0.75)', zIndex:9999, display:'flex', alignItems:'center', justifyContent:'center' }} onClick={onClose}>
      <div style={{ background:'#2c333e', border:'1px solid #626d80', borderRadius:14, width:760, maxHeight:'90vh', overflow:'auto', display:'flex' }} onClick={e => e.stopPropagation()}>

        {/* Template list */}
        <div style={{ width:230, borderRight:'1px solid #4f596b', padding:14, flexShrink:0, overflowY:'auto' }}>
          <div style={{ fontSize:11, color:'#555', marginBottom:10, textTransform:'uppercase', letterSpacing:1 }}>{t('Templates')}</div>
          {allTemplates.map(tpl => (
            <div key={tpl.id} onClick={() => pick(tpl)}
              style={{ padding:'9px 10px', borderRadius:8, cursor:'pointer', marginBottom:4, background: selectedId===tpl.id?'rgba(0,229,160,0.08)':'transparent', color: selectedId===tpl.id?'#00e5a0':'#888', fontSize:12, borderLeft: selectedId===tpl.id?'2px solid #00e5a0':'2px solid transparent', lineHeight:1.4 }}>
              {tpl.id === CUSTOM_ID ? <span style={{ color: selectedId===CUSTOM_ID?'#00e5a0':'#888', fontWeight:500 }}>✏️ {t('Write custom email')}</span> : tpl.label.substring(0,38) + (tpl.label.length>38?'...':'')}
            </div>
          ))}
        </div>

        {/* Compose */}
        <div style={{ flex:1, padding:20, display:'flex', flexDirection:'column' }}>
          <div style={{ display:'flex', justifyContent:'space-between', marginBottom:16 }}>
            <div style={{ fontSize:14, fontWeight:500 }}>
              {selectedId === CUSTOM_ID ? '✏️ '+t('Compose custom email') : t('Send template email')}
            </div>
            <div onClick={onClose} style={{ cursor:'pointer', color:'#555', fontSize:18 }}>✕</div>
          </div>

          <div style={{ marginBottom:10 }}>
            <div style={{ fontSize:11, color:'#555', marginBottom:4 }}>{t('FROM (your name)')}</div>
            <input value={fromName} onChange={e => setFromName(e.target.value)}
              style={{ width:'100%', padding:'8px 12px', background:'#373f4d', border:'1px solid #626d80', borderRadius:8, color:'#fff', fontSize:13, outline:'none', boxSizing:'border-box' as any }} />
          </div>

          <div style={{ marginBottom:10 }}>
            <div style={{ fontSize:11, color:'#555', marginBottom:4 }}>{t('TO')}</div>
            <input value={client.email} readOnly
              style={{ width:'100%', padding:'8px 12px', background:'#373f4d', border:'1px solid #626d80', borderRadius:8, color:'#888', fontSize:13, outline:'none', boxSizing:'border-box' as any }} />
          </div>

          <div style={{ marginBottom:10 }}>
            <div style={{ fontSize:11, color:'#555', marginBottom:4 }}>{t('SUBJECT')}</div>
            <input value={subject} onChange={e => setSubject(e.target.value)}
              placeholder={t('Enter email subject...')}
              style={{ width:'100%', padding:'8px 12px', background:'#373f4d', border:'1px solid #626d80', borderRadius:8, color:'#fff', fontSize:13, outline:'none', boxSizing:'border-box' as any }} />
          </div>

          <div style={{ marginBottom:14, flex:1 }}>
            <div style={{ fontSize:11, color:'#555', marginBottom:4 }}>{t('MESSAGE')}</div>
            <textarea value={body} onChange={e => setBody(e.target.value)}
              placeholder={selectedId===CUSTOM_ID ? t('Write your custom email here...') : ""}
              rows={selectedId===CUSTOM_ID ? 12 : 10}
              style={{ width:'100%', padding:'10px 12px', background:'#373f4d', border:'1px solid #626d80', borderRadius:8, color:'#fff', fontSize:13, outline:'none', resize:'vertical' as any, boxSizing:'border-box' as any, lineHeight:1.7 }} />
          </div>

          {/* Image attachments (#185) */}
          <div style={{ marginBottom:12 }}>
            <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:6, flexWrap:'wrap' }}>
              <label style={{ fontSize:12, color:'#00e5a0', cursor:'pointer', border:'1px dashed #00e5a0', borderRadius:8, padding:'6px 12px' }}>
                📎 {t('Attach images')}
                <input type="file" accept="image/png,image/jpeg,image/gif" multiple style={{ display:'none' }}
                  onChange={e => { addFiles(e.target.files); (e.target as HTMLInputElement).value = ''; }} />
              </label>
              <span style={{ fontSize:10, color:'#555' }}>{t('PNG, JPEG or GIF — up to 5, max 5 MB each')}</span>
            </div>
            {attachments.length > 0 && (
              <div style={{ display:'flex', flexWrap:'wrap', gap:8 }}>
                {attachments.map((a, i) => (
                  <div key={i} title={a.name} style={{ position:'relative', width:66, height:66, borderRadius:8, overflow:'hidden', border:'1px solid #4f596b' }}>
                    <img src={a.url} alt={a.name} style={{ width:'100%', height:'100%', objectFit:'cover' }} />
                    <div onClick={() => removeAtt(i)} title={t('Remove')}
                      style={{ position:'absolute', top:2, right:2, width:18, height:18, borderRadius:'50%', background:'rgba(0,0,0,0.7)', color:'#fff', fontSize:12, lineHeight:'18px', textAlign:'center', cursor:'pointer' }}>✕</div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {error && <div style={{ marginBottom:8, fontSize:12, color:'#ff6b6b' }}>{error}</div>}

          <div style={{ display:'flex', gap:8 }}>
            <button onClick={onClose} style={{ flex:1, padding:11, background:'transparent', border:'1px solid #626d80', borderRadius:8, color:'#888', cursor:'pointer', fontSize:13 }}>{t('Cancel')}</button>
            <button onClick={send} disabled={!subject || !body || sending}
              style={{ flex:2, padding:11, background: sent?'#00e5a0': (!subject||!body||sending)?'#373f4d':'#0066ff', border:'none', borderRadius:8, color: (!subject||!body||sending)?'#555':'#fff', fontWeight:700, cursor: (!subject||!body||sending)?'default':'pointer', fontSize:13 }}>
              {sent ? '✓ '+t('Sent successfully!') : sending ? t('Sending…') : '✉️ '+t('Send email')}
            </button>
          </div>

          {sent && <div style={{ marginTop:10, fontSize:12, color:'#00e5a0', textAlign:'center' }}>{t('Email sent to')} {client.email}{attachments.length ? ` · ${attachments.length} ${t('image(s)')}` : ''}</div>}
        </div>
      </div>
    </div>
  );
}


function DepositTooltip({ client, x, y, onClose }: any) {
  const t = useT();
  const [deps, setDeps] = React.useState<any[]>([]);
  const [loading, setLoading] = React.useState(true);
  const API = '/api';

  React.useEffect(() => {
    const token = localStorage.getItem('token') || '';
    // A person's deposits can sit on ANY of their accounts (MT4 + MT5 siblings), so query
    // ALL of their logins — not just the representative one (that's why some showed empty).
    const logins = (client.all_logins && client.all_logins.length ? client.all_logins : [client.login]).join(',');
    fetch(`${API}/transactions?logins=${logins}&tx_type=deposit&page_size=50`, {
      headers: { Authorization: `Bearer ${token}` }
    })
      .then(r => r.json())
      .then(d => {
        const txs = d.transactions || d.items || [];
        txs.sort((a:any,b:any) => new Date(b.tx_date).getTime() - new Date(a.tx_date).getTime());
        setDeps(txs.slice(0,10));
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [client.login]);

  // Position tooltip - keep it on screen
  const left = Math.min(x + 10, window.innerWidth - 320);
  const top  = Math.min(y - 10, window.innerHeight - 400);

  return (
    <div
      onMouseLeave={onClose}
      style={{
        position: 'fixed', left, top, zIndex: 99999,
        background: '#2c333e', border: '1px solid #626d80',
        borderRadius: 10, padding: 14, width: 300,
        boxShadow: '0 8px 32px rgba(0,0,0,0.6)',
        pointerEvents: 'none'
      }}>
      <div style={{ display:'flex', justifyContent:'space-between', marginBottom:10 }}>
        <div style={{ fontSize:12, fontWeight:600 }}>{t('Deposits')} — {client.name}</div>
        <div style={{ fontSize:11, color:'#00e5a0' }}>{deps.length} {t('records')}</div>
      </div>
      {loading ? (
        <div style={{ color:'#555', fontSize:12, padding:'10px 0' }}>{t('Loading...')}</div>
      ) : deps.length === 0 ? (
        <div style={{ color:'#555', fontSize:12 }}>{t('No deposits found')}</div>
      ) : (
        <>
          <div style={{ display:'grid', gridTemplateColumns:'1fr 80px 80px', gap:4, marginBottom:6 }}>
            <div style={{ fontSize:10, color:'#555', textTransform:'uppercase' }}>{t('Date')}</div>
            <div style={{ fontSize:10, color:'#555', textTransform:'uppercase', textAlign:'right' }}>{t('Amount')}</div>
            <div style={{ fontSize:10, color:'#555', textTransform:'uppercase' }}>{t('Method')}</div>
          </div>
          {deps.map((d:any, i:number) => (
            <div key={i} style={{ display:'grid', gridTemplateColumns:'1fr 80px 80px', gap:4, padding:'5px 0', borderBottom:'1px solid #373f4d', fontSize:11 }}>
              <div style={{ color:'#888' }}>
                {d.tx_date ? new Date(d.tx_date.replace(' ','T')).toLocaleString('en-GB', {day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit',hour12:false}) : '—'}
              </div>
              <div style={{ color:'#00e5a0', fontWeight:600, textAlign:'right' }}>
                ${(d.amount||0).toLocaleString('en-GB')}
              </div>
              <div style={{ color:'#555', fontSize:10, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
                {d.method || d.payment_method || t('Bank')}
              </div>
            </div>
          ))}
          <div style={{ display:'flex', justifyContent:'space-between', marginTop:8, paddingTop:6, borderTop:'1px solid #626d80', fontSize:12 }}>
            <span style={{ color:'#555' }}>{t('Total')}</span>
            <span style={{ color:'#00e5a0', fontWeight:700 }}>
              ${(client.total_deposit||0).toLocaleString('en-GB')}
            </span>
          </div>
        </>
      )}
    </div>
  );
}


// ── MAIN CLIENTS TABLE ───────────────────────────────────────────────────
const ABUSE_TYPE_LABEL: Record<string, string> = {
  margin_partner: '🔥 Margin-Out', bonus_ring: '🎁 Bonus Ring', bonus_cashout: '🎁 Cash-Out',
  chip_dump: '🔀 Chip Dump', swap_carry: '💱 Swap Carry', toxic_arb: '☢️ Toxic',
};

export default function Clients({ lang }: any) {
  const t = useT();
  const isAr = lang === 'ar';
  const [clients, setClients] = useState<any[]>([]);
  const [abuseFlags, setAbuseFlags] = useState<Record<string, any>>({});
  const [loading, setLoading] = useState(true);
  // #225 item 4: restore the Client page's last filter/sort state so returning from another
  // page lands where you left off. Read once here; each filter below initialises from it (lazy
  // initialisers avoid the mount-overwrite race an effect would cause).
  const _sf = (() => { try { return JSON.parse(sessionStorage.getItem('clients_filters_v1') || '{}') || {}; } catch { return {}; } })();
  const [search, setSearch] = useState<string>(_sf.search || '');
  // debounced: commit to `search` 400ms after typing stops (3 GROUP-BY passes per request)
  const [searchInput, setSearchInput] = useState<string>(_sf.search || '');
  useEffect(() => { const t = setTimeout(() => { setSearch(searchInput); setPage(1); }, 400); return () => clearTimeout(t); }, [searchInput]);
  const [filterCountry, setFilterCountry] = useState<string>(_sf.filterCountry || '');
  const [filterCity, setFilterCity] = useState<string>(_sf.filterCity || '');
  const [filterIB, setFilterIB] = useState<string>(_sf.filterIB || '');
  const [badgeHover, setBadgeHover] = useState<any>(null);
  const [filterAgent, setFilterAgent] = useState<string>(_sf.filterAgent || '');
  const [agentRoster, setAgentRoster] = useState<any[]>([]);   // full staff roster for the agent filter (not just current page)
  const [filterPeriod, setFilterPeriod] = useState('');
  const [filterSources, setFilterSources] = useState<string[]>(Array.isArray(_sf.filterSources) ? _sf.filterSources : []);
  const [filterKyc, setFilterKyc] = useState<string>(_sf.filterKyc || '');
  const [filterRisk, setFilterRisk] = useState<string>(_sf.filterRisk || '');
  const [filterDeposits, setFilterDeposits] = useState<string>(_sf.filterDeposits || '');   // #60 D1/D2/D3/D4/D5+
  const [filterNoDep, setFilterNoDep] = useState<string>(_sf.filterNoDep || '');         // #157 inactive-deposit: '3'/'4'/'6'/'12'/'custom'
  const [noDepCustom, setNoDepCustom] = useState('');         // #157 custom months when preset = 'custom'
  const [filterBirthday, setFilterBirthday] = useState<string>(_sf.filterBirthday || '');   // '' | 'week' | 'unclaimed'
  const [birthdayCount, setBirthdayCount] = useState(0);      // 🎂 clients with a birthday this week
  const [filterDateFrom, setFilterDateFrom] = useState('');   // #62 reg_date from
  const [filterDateTo, setFilterDateTo] = useState('');       // #62 reg_date to
  const [archiveView, setArchiveView] = useState<'active'|'archived'|'all'>('active'); // tabs are PERSON-level: Archived = whole client profile archived by the team / TradeSoft. Account-level archive lives on the Trading Accounts page.
  const [kpiFilter, setKpiFilter] = useState<''|'new_clients'|'active_clients'>('');   // KPI drill-down: click a KPI card -> list shows only that segment
  const [showAdvanced, setShowAdvanced] = useState(false);
  // default MY-data ONLY for team-leaders (who get the toggle); non-team-leaders have no toggle, so
  // own=true stranded them on an empty list (Jul 20 fix).
  const [own, setOwn] = useState(() => localStorage.getItem('isTeamLead') === '1');
  const [connected, setConnected] = useState(false);   // "Connected (7d)" tab — clients contacted this week
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [period, setPeriod] = useState('all_time');
  const [kpis, setKpis] = useState<any>(null);
  const [showKpi, setShowKpi] = useState(() => localStorage.getItem('kpi_hidden') !== '1');  // #4
  const [listStats, setListStats] = useState<any>(null);   // #60 — stats for the filtered subset
  const [total, setTotal] = useState(0);
  const [sort, setSort] = useState<string>(_sf.sort || 'score');
  const [profileClient, setProfileClient] = useState<any>(null);
  const [emailClient, setEmailClient] = useState<any>(null);
  const [depPopup, setDepPopup] = useState<any>(null);
  const [depData, setDepData] = useState<any[]>([]);
  const [depLoading, setDepLoading] = useState(false);
  const [phoneClient, setPhoneClient] = useState<any>(null);
  const [actionMenu, setActionMenu] = useState<any>(null);
  const [actionStep, setActionStep] = useState<'menu'|'form'>('menu');
  const [actionType, setActionType] = useState('');
  const [actionNote, setActionNote] = useState('');
  const [callLaterDays, setCallLaterDays] = useState(0);
  const [callLaterHours, setCallLaterHours] = useState(0);
  const [passToManager, setPassToManager] = useState(false);
  const [saving, setSaving] = useState(false);
  // Ticket #137 — inline "saved" confirmation so logging an outcome doesn't refresh the page
  const [savedToast, setSavedToast] = useState<{ name: string; type: string } | null>(null);
  const toastTimer = useRef<any>(null);
  const [scoreHover, setScoreHover] = useState<any>(null);   // {login,x,y} — fixed-positioned so it clears the KPI/stacking contexts (#224)
  const [scorePin, setScorePin] = useState<number|null>(null);   // #225: click the score to PIN the breakdown open (hover alone was easy to miss / impossible on touch)
  const [networkHover, setNetworkHover] = useState<number|null>(null);
  const [sortCol, setSortCol] = useState<string>('');
  const [sortDir, setSortDir] = useState<'asc'|'desc'>('desc');
  // #225 item 4: snapshot the current filter/sort state so it survives navigating away & back.
  useEffect(() => {
    try {
      sessionStorage.setItem('clients_filters_v1', JSON.stringify({
        search, filterCountry, filterCity, filterIB, filterAgent, filterSources,
        filterKyc, filterRisk, filterDeposits, filterNoDep, filterBirthday, sort,
      }));
    } catch {}
  }, [search, filterCountry, filterCity, filterIB, filterAgent, filterSources, filterKyc, filterRisk, filterDeposits, filterNoDep, filterBirthday, sort]);
  // Multi-select (ticket #38) — selected client logins for bulk actions
  const [selectedLogins, setSelectedLogins] = useState<number[]>([]);
  const [bulkMenuOpen, setBulkMenuOpen] = useState(false);
  const clearSelection = () => { setSelectedLogins([]); setBulkMenuOpen(false); };

  // ── Per-user column customisation (persisted in localStorage). Default hides the money
  // columns (Total dep./Total with./Equity/Margin%) — each user can re-enable what they need.
  const ALL_COLS = ['Client','Accounts','Phone','Country/City','Agent','IB','1st Deposit','Dep#','Last Activity','Total dep.','Total with.','Equity','Margin%','Network','Last Comment','Score','Action'];
  // Fixed per-column widths so the table never scrolls sideways (table-layout:fixed + colgroup).
  const COL_W: Record<string,number> = { 'Client':172,'Accounts':118,'Phone':92,'Country/City':94,'Agent':112,'IB':82,'1st Deposit':84,'Dep#':52,'Last Activity':92,'Total dep.':86,'Total with.':88,'Equity':92,'Margin%':70,'Network':62,'Last Comment':132,'Score':54,'Action':86 };
  const COLS_LOCKED = ['Client','Action'];                       // always visible
  const COLS_HIDE_DEFAULT = ['Total dep.','Total with.','Equity','Margin%'];
  const [visCols, setVisCols] = useState<Record<string,boolean>>(() => {
    try { const s = JSON.parse(localStorage.getItem('clients_cols_v1') || 'null'); if (s && typeof s === 'object') return s; } catch {}
    const d: Record<string,boolean> = {}; ALL_COLS.forEach(c => d[c] = !COLS_HIDE_DEFAULT.includes(c)); return d;
  });
  const V = (h: string) => COLS_LOCKED.includes(h) || visCols[h] !== false;
  const toggleCol = (h: string) => setVisCols(p => {
    const n = { ...p, [h]: !(p[h] !== false) };
    try { localStorage.setItem('clients_cols_v1', JSON.stringify(n)); } catch {}
    return n;
  });
  const [colsOpen, setColsOpen] = useState(false);
  const toggleSelect = (login: number) =>
    setSelectedLogins(prev => prev.includes(login) ? prev.filter(x => x !== login) : [...prev, login]);

  const fetchClients = useCallback(async () => {
    setLoading(true);
    try {
      const _p = new URLSearchParams({ page: String(page), page_size: String(pageSize), sort, search });
      if (filterCountry)           _p.set('country', filterCountry);
      if (filterCity)              _p.set('city', filterCity);
      if (filterIB)                _p.set('ib', filterIB);
      if (filterAgent)             _p.set('agent', filterAgent);
      if (filterKyc)               _p.set('kyc', filterKyc);
      if (filterRisk)              _p.set('risk', filterRisk);
      if (filterSources.length)    _p.set('sources', filterSources.join(','));
      if (filterDeposits)          _p.set('deposits', filterDeposits);
      { const _nd = filterNoDep === 'custom' ? noDepCustom : filterNoDep;
        if (_nd && Number(_nd) > 0)  _p.set('no_deposit_months', String(Number(_nd))); }
      if (filterBirthday)          _p.set('birthday', filterBirthday);
      if (filterDateFrom)          _p.set('date_from', filterDateFrom);
      if (filterDateTo)            _p.set('date_to', filterDateTo);
      if (kpiFilter)               _p.set('kpi', kpiFilter);   // KPI drill-down (new/active clients in period)
      _p.set('archived', archiveView);
      _p.set('period', period);    // scopes the deposit/withdrawal/net KPIs to the selected period
      if (own) _p.set('own', '1');   // team-leader: restrict to the leader's own book
      if (connected) _p.set('connected', '1');   // "Connected (7d)" tab — clients contacted this week
      const data = await apiGet(`/clients?${_p}`);
      setClients(data.clients || []);
      setTotal(data.total || 0);
      setListStats(data.stats || null);   // #60 — filtered-subset statistics
    } catch {
      setClients([]);
      setTotal(0);
      setListStats(null);
    }
    setLoading(false);
  }, [page, pageSize, sort, search, filterCountry, filterCity, filterIB, filterAgent, filterKyc, filterRisk, filterSources, filterDeposits, filterNoDep, noDepCustom, filterBirthday, filterDateFrom, filterDateTo, archiveView, period, kpiFilter, own, connected]);

  // 🎂 count of clients with a birthday this week (refreshes whenever the list reloads)
  useEffect(() => { apiGet('/clients?birthday=week&page_size=1').then((r: any) => setBirthdayCount(r?.total || 0)).catch(() => {}); }, [clients]);
  // Full staff roster for the Sales-agent filter — so you can pick/search ANY agent, not just the ones on this page.
  useEffect(() => { apiGet('/users?page_size=500').then((d: any) => setAgentRoster((d?.users || d || []).filter((u: any) => u?.full_name))).catch(() => {}); }, []);

  // overlay abuse flags for the visible accounts (covers MT4+MT5 logins on each row)
  useEffect(() => {
    const logins = Array.from(new Set(clients.flatMap((c: any) =>
      [c.login, ...((c.related_accounts || []).map((a: any) => a.login))].filter(Boolean))));
    if (!logins.length) { setAbuseFlags({}); return; }
    apiPost('/abuse/flags', { logins }).then((r: any) => setAbuseFlags(r.flags || {})).catch(() => setAbuseFlags({}));
  }, [clients]);

  useEffect(() => { fetchClients(); }, [fetchClients]);

  // Lazily-fetched linked accounts for the Network hover (cached per login).
  const [netConns, setNetConns] = useState<Record<number, any[]>>({});
  const loadNetConns = (login: number) => {
    if (netConns[login] !== undefined) return;
    setNetConns(p => ({ ...p, [login]: [] }));   // mark in-flight so we don't refetch
    apiGet(`/network/connections?login=${login}`)
      .then((d: any) => setNetConns(p => ({ ...p, [login]: d?.connections || [] })))
      .catch(() => {});
  };

  // Drop any selected rows that are no longer in the current result set (page/filter change)
  useEffect(() => {
    const visible = new Set(clients.map((c: any) => c.login));
    setSelectedLogins(prev => prev.filter(l => visible.has(l)));
  }, [clients]);

  useEffect(() => {
    const handler = (e: any) => {
      const { search: s, openProfile } = (e as CustomEvent).detail || {};
      if (s) { setSearch(String(s)); setPage(1); }
      if (openProfile) {
        const token = localStorage.getItem('token') || '';
        fetch(`/api/clients/${openProfile}`, {
          headers: { Authorization: `Bearer ${token}` }
        }).then(r=>r.json()).then(c=>{ if(c && c.login) setProfileClient(c); }).catch(()=>{});
      }
    };
    window.addEventListener('clients_search', handler);
    return () => window.removeEventListener('clients_search', handler);
  }, []);

  // Per-TAB open-profile persistence: remember which client is open in THIS tab (sessionStorage)
  // so a refresh reopens the same profile with a clean my1.tnfx.co URL, and other tabs are
  // unaffected. On mount, reopen whatever this tab had open.
  useEffect(() => {
    try {
      const saved = sessionStorage.getItem('crm_open_client');
      if (saved) {
        const token = localStorage.getItem('token') || '';
        fetch(`/api/clients/${saved}`, { headers: { Authorization: `Bearer ${token}` } })
          .then(r => r.json()).then(c => { if (c && c.login) setProfileClient(c); }).catch(() => {});
      }
    } catch {}
  }, []);
  useEffect(() => {
    try {
      if (profileClient?.login) sessionStorage.setItem('crm_open_client', String(profileClient.login));
      else sessionStorage.removeItem('crm_open_client');
    } catch {}
  }, [profileClient]);

  useEffect(() => {
    // guard against out-of-order responses: switching periods fast can make the SLOW previous
    // response (e.g. all_time) land AFTER the fast current one and overwrite the KPI cards
    // with stale numbers while the list (a separate request) stays correct.
    let live = true;
    apiGet(`/dashboard/kpis?period=${period}`)
      .then((data: any) => { if (live) setKpis(data); }).catch(() => {});
    return () => { live = false; };
  }, [period]);

  const periodStart = (p: string) => {
    const now = new Date();
    if (p === 'today')      return new Date(now.getFullYear(), now.getMonth(), now.getDate());
    if (p === 'this_week')  return new Date(now.setDate(now.getDate() - now.getDay()));
    if (p === 'this_month') return new Date(now.getFullYear(), now.getMonth(), 1);
    if (p === 'last_month') return new Date(now.getFullYear(), now.getMonth()-1, 1);
    if (p === 'this_year')  return new Date(now.getFullYear(), 0, 1);
    if (p === 'last_year')  return new Date(now.getFullYear()-1, 0, 1);
    return null;
  };

  const filtered = clients.filter(c => {
    // Filters applied server-side — only period filter remains client-side
    if (false) return false;
    if (filterPeriod) {
      const start = periodStart(filterPeriod);
      if (start && c.reg_date) {
        const reg = new Date(c.reg_date);
        if (reg < start) return false;
      }
    }
    return true;
  });

  const clearFilters = () => { setFilterCountry(''); setFilterCity(''); setFilterIB(''); setFilterAgent(''); setFilterPeriod(''); setFilterSources([]); setFilterKyc(''); setFilterRisk(''); setFilterDeposits(''); setFilterNoDep(''); setNoDepCustom(''); setFilterBirthday(''); setFilterDateFrom(''); setFilterDateTo(''); setKpiFilter(''); };
  const hasFilters = filterCountry || filterCity || filterIB || filterAgent || filterPeriod || filterSources.length || filterKyc || filterRisk || filterDeposits || filterNoDep || filterBirthday || filterDateFrom || filterDateTo || kpiFilter;

  const uniqueCountries = Array.from(new Set(clients.map(c => c.country).filter(Boolean))).sort();
  const uniqueCities    = Array.from(new Set(clients.map(c => c.city).filter(Boolean))).sort();
  const uniqueIBs       = Array.from(new Set(clients.map(c => c.ib_display).filter(Boolean))).sort();
  const uniqueAgents    = Array.from(new Set(clients.map(c => c.agent_name).filter(Boolean))).sort();

  const SOURCES = ['MQL5','meta','facebook','instagram','google','sales_agent','webinar','affiliate','direct','none','organic','tiktok','youtube','twitter','linkedin','referral','email','whatsapp','other'];
  const SOURCE_LABELS: any = { MQL5:'MQL5 (MetaQuotes)', meta:'Meta (ads)', 'sales_agent':'Sales agent', webinar:'Webinar', affiliate:'Affiliate', direct:'Direct', none:'None/Direct', organic:'Organic', facebook:'Facebook', instagram:'Instagram', tiktok:'TikTok', google:'Google Ads', youtube:'YouTube', twitter:'Twitter/X', linkedin:'LinkedIn', referral:'Referral', email:'Email campaign', whatsapp:'WhatsApp', other:'Other' };
  const SOURCE_COLORS: any = { MQL5:'#0088cc', meta:'#0866ff', 'sales_agent':'#a78bfa', webinar:'#00c2a8', affiliate:'#ffb020', direct:'#8b93a1', facebook:'#1877f2', instagram:'#e1306c', tiktok:'#ff0050', google:'#4285f4', youtube:'#ff0000', twitter:'#1da1f2', linkedin:'#0a66c2', referral:'#00e5a0', email:'#ff8c00', whatsapp:'#25d366', organic:'#888', none:'#555', other:'#888' };
  const PERIODS = [{ key:'today',label:'Today' },{ key:'this_week',label:'This week' },{ key:'this_month',label:'This month' },{ key:'last_month',label:'Last month' },{ key:'this_year',label:'This year' },{ key:'last_year',label:'Last year' }];

  const toggleSort = (col: string) => {
    const backendSortMap: any = {
      '1st Deposit': 'first_dep',   // #225: order by first-deposit DATE (was 'new' = same as Newest)
      'Dep#':        'deposits',
      'Total dep.':  'total_dep',
      'Total with.': 'total_with',
      'Equity':      'equity',
      'Network':     'network',     // #225: order by network score (was 'score' = same as Priority)
    };
    if (backendSortMap[col]) {
      setSort(backendSortMap[col]);
      setPage(1);
    }
    if (sortCol === col) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortCol(col); setSortDir('desc'); }
  };

  const sortedFiltered = filtered; // all sorting done server-side

  const saveAction = async () => {
    if (!actionMenu) return;
    // capture before the modal state is cleared below
    const login = actionMenu.login, name = actionMenu.name, type = actionType, note = actionNote;
    setSaving(true);
    try {
      const token = localStorage.getItem('token');
      if (type === 'transfer_out') {
        // "transfer out of my data" → moves the client up to the manager + opens a reassign request
        const r = await fetch(`${API}/transfer/out`, { method: "POST", headers: { "Authorization": `Bearer ${token}`, "Content-Type": "application/json" }, body: JSON.stringify({
          record_type: 'client', record_key: login, reason: note,
        }) });
        const j = await r.json().catch(() => ({}));
        if (r.ok) alert(j.moved_to_manager ? t('Client moved to your manager for reassignment.') : t('Transfer request recorded.'));
        else alert(j.detail || t('Transfer-out failed.'));
      } else {
        await fetch(`${API}/clients/action`, { method: "POST", headers: { "Authorization": `Bearer ${token}`, "Content-Type": "application/json" }, body: JSON.stringify({
          login, action: type, note,
          call_later_days: callLaterDays, call_later_hours: callLaterHours, pass_to_manager: passToManager,
        }) });
      }
      setActionMenu(null); setActionStep('menu'); setActionNote('');
      setCallLaterDays(0); setCallLaterHours(0);
      // Ticket #137 — outcomes that keep the client on the desk (contacted + note) must NOT reorder
      // or re-page the list out from under the agent. Patch just that row in place and show an inline
      // confirmation instead of a full refetch. Outcomes that legitimately take the client out of the
      // view (not interested → hidden, transferred to manager) still refresh.
      const removesFromView = type === 'not_interested' || type === 'transfer_out';
      if (removesFromView) {
        fetchClients();
      } else {
        setClients(prev => prev.map(c => c.login === login ? {
          ...c,
          last_action_note: note || c.last_action_note,
          last_activity_type: type,
          last_activity_date: new Date().toISOString(),
        } : c));
        setSavedToast({ name, type });
        if (toastTimer.current) clearTimeout(toastTimer.current);
        toastTimer.current = setTimeout(() => setSavedToast(null), 2800);
      }
    } catch {}
    setSaving(false);
  };

  // Archive / unarchive (ticket #57)
  const archiveClient = async (login: number, archived: boolean) => {
    try { await apiPost(`/clients/${login}/archive`, { archived }); fetchClients(); }
    catch { alert(t('Failed to update archive status')); }
  };
  const bulkArchive = async (archived: boolean) => {
    if (!selectedLogins.length) return;
    try {
      await apiPost('/clients/archive', { logins: selectedLogins, archived });
      clearSelection(); fetchClients();
    } catch { alert(t('Failed to archive selection')); }
  };

  // Don't use early return - render profile inside the component so modals appear on top
  if (profileClient) return (
    <>
      <ClientProfile client={profileClient} onBack={() => setProfileClient(null)} lang={lang} setPhoneClient={setPhoneClient} setEmailClient={setEmailClient} />
      {phoneClient && <PhoneModal client={phoneClient} onClose={() => setPhoneClient(null)} />}
      {depPopup && (
        <DepositTooltip
          client={depPopup.client}
          x={depPopup.x}
          y={depPopup.y}
          onClose={()=>setDepPopup(null)}
        />
      )}
      {emailClient && <EmailModal client={emailClient} onClose={() => setEmailClient(null)} />}
    </>
  );

  // KPI calculated from loaded clients
  const totalDeposits    = clients.reduce((s,c) => s + (c.total_deposit||0), 0);
  const totalWithdrawals = clients.reduce((s,c) => s + (c.total_withdraw||0), 0);
  const pendingWith      = clients.filter(c => c.last_action_type === 'withdrawal_pending').length;
  const noDeposit14      = clients.filter(c => !c.last_deposit_date || ((Date.now() - new Date(c.last_deposit_date).getTime()) > 14*86400000)).length;
  const salesComm        = Math.round(totalDeposits * 0.015);
  const ibComm           = Math.round(totalDeposits * 0.009);

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden', minHeight: 0, direction: isAr ? 'rtl' : 'ltr' }}>

      {/* KPI bar + period selector */}
      <div style={{ background: '#262c36', borderBottom: '1px solid #4f596b', flexShrink: 0 }}>
        <div style={{ display: 'flex', gap: 4, padding: '8px 14px 0', overflowX: 'auto' }}>
          {[['all_time',t('All time')],['today',t('Today')],['this_week',t('This week')],['last_week',t('Last week')],['this_month',t('This month')],['last_month',t('Last month')],['this_year',t('This year')],['last_year',t('Last year')]].map(([k,l]) => (
            <button key={k} onClick={() => { setPeriod(k); setFilterPeriod(''); }}
              style={{ padding: '4px 12px', borderRadius: 6, border: `1px solid ${period===k?'#00e5a0':'#626d80'}`, background: period===k?'rgba(0,229,160,0.1)':'transparent', color: period===k?'#00e5a0':'#555', cursor: 'pointer', fontSize: 11, whiteSpace: 'nowrap', fontFamily: 'inherit' }}>
              {l}
            </button>
          ))}
        </div>
        {showKpi && <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,minmax(0,1fr))', gap: 8, padding: '8px 14px 10px' }}>
          {/* #60 — when the list is filtered (deposit count, country, archive, search…) the
               headline stats reflect the FILTERED subset (from data.stats); otherwise the
               global dashboard KPIs for the chosen period. */}
          {(() => { const _filtered = !!(hasFilters || search || archiveView !== 'active') && !!listStats;
                    const _s = _filtered ? listStats : null; return [
            { label: _filtered ? t('Clients (filtered)') : t('Total clients'), value: (_s ? _s.clients : (kpis?.clients || total)).toLocaleString('en-GB'),     color: '#00e5a0' },
            { label: t('Total deposits'),     value: '$'+(((_s ? _s.deposits : kpis?.deposits)||0)/1000).toFixed(1)+'K',                            color: '#00e5a0' },
            { label: t('Total withdrawals'),  value: '$'+(((_s ? _s.withdrawals : kpis?.withdrawals)||0)/1000).toFixed(1)+'K',                      color: '#ff8888' },
            { label: t('Net deposit'),        value: '$'+(((_s ? _s.net_deposit : kpis?.net_deposit)||0)/1000).toFixed(1)+'K',                      color: ((_s ? _s.net_deposit : kpis?.net_deposit)||0) >= 0 ? '#00e5a0' : '#ff4d4d' },
            { label: t('New clients'),        value: (kpis?.new_clients||0).toLocaleString('en-GB'),                                            color: '#00aaff', kpi: 'new_clients', hint: t('People whose FIRST deposit is in the period — click to show only them') },
            { label: t('Active clients'),     value: (kpis?.active_clients_period||0).toLocaleString('en-GB'),                                 color: '#00e5a0', kpi: 'active_clients', hint: t('People with ANY activity in the period (deposit / withdraw / trade / transfer) — click to show only them') },
            { label: t('No deposit 14+ days'),value: (kpis?.no_deposit_14d||0).toString(),                                               color: (kpis?.no_deposit_14d||0) > 0 ? '#ff4d4d' : '#555' },
            { label: t('IB commission'),      value: '$'+((kpis?.ib_comm||0)/1000).toFixed(1)+'K',                                       color: '#ff8c00' },
          ]; })().map((k: any, i) => (
            <div key={i}
              onClick={() => { if (k.kpi) { setKpiFilter(prev => prev === k.kpi ? '' : k.kpi); setPage(1); } }}
              title={k.hint || ''}
              style={{ background: kpiFilter && kpiFilter === k.kpi ? 'rgba(0,229,160,0.10)' : '#2c333e',
                       borderRadius: 10, padding: '10px 14px',
                       border: `1px solid ${kpiFilter && kpiFilter === k.kpi ? '#00e5a0' : '#373f4d'}`,
                       cursor: k.kpi ? 'pointer' : 'default' }}>
              <div style={{ fontSize: 10, color: '#555', marginBottom: 4 }}>{k.label}{k.kpi && kpiFilter === k.kpi ? '  ✕' : ''}</div>
              <div style={{ fontSize: 18, fontWeight: 500, color: k.color }}>{k.value}</div>
            </div>
          ))}
        </div>}
      </div>

      {/* Header */}
      <div style={{ background: 'var(--bg-card,#2c333e)', borderBottom: '1px solid var(--border,#4f596b)', flexShrink: 0 }}>

        {/* Top row */}
        <div style={{ padding: '10px 14px', display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <div>
            <div style={{ fontSize: 15, fontWeight: 500 }}>{t('Clients')}</div>
            <div style={{ fontSize: 11, color: 'var(--text3,#555)' }}>{filtered.length} {t('of')} {total}</div>
          </div>
          <input value={searchInput} onChange={e => setSearchInput(e.target.value)}
            placeholder={t('Search name, email, login, IP, CID...')}
            style={{ flex: 1, maxWidth: 280, padding: '7px 12px', background: 'var(--bg-input,#373f4d)', border: '1px solid var(--border2,#626d80)', borderRadius: 8, color: 'var(--text,#fff)', fontSize: 12, outline: 'none' }} />
          <OwnDataToggle own={own} setOwn={(v) => { setOwn(v); setPage(1); }} section="clients" />
          {/* Connected (last 7d) tab — clients contacted this week, newest action first, comments shown */}
          <button onClick={() => { setConnected(v => !v); setPage(1); }} title={t('Clients you connected with in the last 7 days, sorted by most recent action — so contacted clients that dropped down the list stay easy to follow up')}
            style={{ padding: '7px 12px', borderRadius: 8, border: `1px solid ${connected ? '#4d9fff' : 'var(--border2,#626d80)'}`, background: connected ? 'rgba(77,159,255,0.14)' : 'transparent', color: connected ? '#4d9fff' : 'var(--text2,#8b96a8)', cursor: 'pointer', fontSize: 12, fontWeight: connected ? 700 : 500, whiteSpace: 'nowrap' }}>
            📞 {t('Connected (7d)')}
          </button>
          <button onClick={() => { const n=!showKpi; setShowKpi(n); localStorage.setItem('kpi_hidden', n?'0':'1'); }}
            title={t('Show/hide the KPI cards')} style={{ padding:'7px 12px', borderRadius:8, border:'1px solid var(--border2,#626d80)', background:'transparent', color:'var(--text2,#888)', cursor:'pointer', fontSize:12, whiteSpace:'nowrap' }}>
            {showKpi ? '📊 '+t('Hide KPI') : '📊 '+t('Show KPI')}</button>
          <button onClick={() => setShowAdvanced(v => !v)}
            style={{ padding: '6px 12px', borderRadius: 8, border: `1px solid ${showAdvanced||hasFilters?'#00e5a0':'var(--border2,#626d80)'}`, background: showAdvanced||hasFilters?'rgba(0,229,160,0.1)':'transparent', color: showAdvanced||hasFilters?'#00e5a0':'var(--text2,#888)', cursor: 'pointer', fontSize: 12, display:'flex', alignItems:'center', gap:5 }}>
            ⚙ {t('Filters')} {hasFilters ? `(${[filterCountry,filterCity,filterIB,filterAgent,filterPeriod,filterKyc,filterRisk].filter(Boolean).length + filterSources.length} ${t('active')})` : ''}
          </button>
          {/* 🎂 quick birthday filter — cycles Off → this week → not-yet-claimed → Off */}
          <button onClick={() => { setFilterBirthday(b => b === '' ? 'week' : b === 'week' ? 'unclaimed' : ''); setPage(1); }}
            title={t("Filter clients with a birthday this week (click again for only those who haven't claimed the bonus)")}
            style={{ padding:'6px 12px', borderRadius:8, border:`1px solid ${filterBirthday?'#ff8ac8':'var(--border2,#626d80)'}`, background: filterBirthday?'rgba(255,138,200,0.14)':'transparent', color: filterBirthday?'#ff8ac8':'var(--text2,#888)', cursor:'pointer', fontSize:12, whiteSpace:'nowrap' }}>
            🎂 {filterBirthday === 'unclaimed' ? t('Not claimed') : filterBirthday === 'week' ? t('This week') : t('Birthdays')}{birthdayCount > 0 ? ` (${birthdayCount})` : ''}
          </button>
          {hasFilters && (
            <button onClick={clearFilters}
              style={{ padding:'5px 12px', borderRadius:7, border:'1px solid #ff4d4d', background:'rgba(255,77,77,0.1)', color:'#ff4d4d', cursor:'pointer', fontSize:11, fontFamily:'inherit' }}>
              ✕ {t('Clear all')}
            </button>
          )}
          <div style={{ display: 'flex', gap: 4, marginLeft: 'auto' }}>
            {/* #225 item 1: these quick-sorts are OPTIONAL — click the active chip again to
                deselect it and fall back to the neutral default (balance), no forced selection. */}
            {[{ key: 'new', label: t('Newest') }, { key: 'score', label: t('Priority') }, { key: 'total_dep', label: t('Top depositors') }].map(s => (
              <button key={s.key} onClick={() => { setSort(sort===s.key ? 'balance' : s.key); setPage(1); }}
                style={{ padding: '5px 12px', borderRadius: 7, border: `1px solid ${sort===s.key?'#00e5a0':'var(--border2,#626d80)'}`, background: sort===s.key?'rgba(0,229,160,0.1)':'transparent', color: sort===s.key?'#00e5a0':'var(--text2,#888)', cursor: 'pointer', fontSize: 12 }}>
                {s.label}
              </button>
            ))}
          </div>
          {/* Archive toggle (ticket #57) — ONE button: default = active view; click to see archived, click again to return */}
          <button onClick={() => { setArchiveView(archiveView === 'archived' ? 'active' : 'archived'); setPage(1); }}
            title={t('Show archived clients — click again to return to the active list')}
            style={{ padding: '5px 12px', borderRadius: 7, border: `1px solid ${archiveView==='archived'?'#ffaa00':'var(--border2,#626d80)'}`, background: archiveView==='archived'?'rgba(255,170,0,0.12)':'transparent', color: archiveView==='archived'?'#ffaa00':'var(--text2,#888)', cursor: 'pointer', fontSize: 12, fontWeight: archiveView==='archived'?700:500, whiteSpace:'nowrap' }}>
            🗄 {t('Archived')}
          </button>
          <DialerLauncher
            source="clients"
            fetchAllLogins={async () => {
              const _p = new URLSearchParams({ sort, search });
              if (filterCountry)        _p.set('country', filterCountry);
              if (filterCity)           _p.set('city', filterCity);
              if (filterIB)             _p.set('ib', filterIB);
              if (filterAgent)          _p.set('agent', filterAgent);
              if (filterKyc)            _p.set('kyc', filterKyc);
              if (filterRisk)           _p.set('risk', filterRisk);
              if (filterSources.length) _p.set('sources', filterSources.join(','));
              const token = localStorage.getItem('token') || '';
              const data = await fetch(`/api/clients/logins-only?${_p}`,
                { headers: { Authorization: `Bearer ${token}` } }).then(r => r.json());
              return data.logins || [];
            }}
          />
          {/* Column/settings picker — a compact ⚙ at the very END of the bar (per-user show/hide, persisted) */}
          <div style={{ position:'relative', flexShrink:0 }}>
            <button onClick={() => setColsOpen(v => !v)} title={t('Columns')}
              style={{ width:34, height:34, borderRadius:'50%', display:'flex', alignItems:'center', justifyContent:'center', border:`1px solid ${colsOpen?'#00e5a0':'var(--border2,#626d80)'}`, background: colsOpen?'rgba(0,229,160,0.1)':'transparent', color: colsOpen?'#00e5a0':'var(--text2,#888)', cursor:'pointer', fontSize:15 }}>
              ⚙
            </button>
            {colsOpen && (
              <>
                <div onClick={() => setColsOpen(false)} style={{ position:'fixed', inset:0, zIndex:998 }} />
                <div style={{ position:'absolute', top:'110%', right:0, zIndex:999, background:'#2c333e', border:'1px solid #4f596b', borderRadius:10, padding:10, width:200, boxShadow:'0 8px 24px rgba(0,0,0,0.4)' }}>
                  <div style={{ fontSize:10, color:'#8b93a1', textTransform:'uppercase', letterSpacing:0.5, marginBottom:6 }}>{t('Show columns')}</div>
                  {ALL_COLS.filter(h => !COLS_LOCKED.includes(h)).map(h => (
                    <label key={h} style={{ display:'flex', alignItems:'center', gap:8, padding:'4px 2px', cursor:'pointer', fontSize:12, color:'#cfd6e0' }}>
                      <input type="checkbox" checked={V(h)} onChange={() => toggleCol(h)} style={{ cursor:'pointer' }} />
                      {t(h)}
                    </label>
                  ))}
                  <div style={{ borderTop:'1px solid #373f4d', marginTop:6, paddingTop:6 }}>
                    <span onClick={() => { try { localStorage.removeItem('clients_cols_v1'); } catch {}; const d: Record<string,boolean> = {}; ALL_COLS.forEach(c => d[c] = !COLS_HIDE_DEFAULT.includes(c)); setVisCols(d); }}
                      style={{ fontSize:11, color:'#00aaff', cursor:'pointer', textDecoration:'underline' }}>{t('Reset to default')}</span>
                  </div>
                </div>
              </>
            )}
          </div>
        </div>

        {/* Advanced filters panel */}
        {showAdvanced && (
          <div style={{ padding: '12px 14px', borderTop: '1px solid var(--border,#4f596b)', background: 'var(--bg-input,#373f4d)' }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: 10, marginBottom: 12 }}>

              {/* Period */}
              <div>
                <div style={{ fontSize: 10, color: 'var(--text3,#555)', marginBottom: 5, textTransform:'uppercase', letterSpacing:'.06em' }}>{t('Period')}</div>
                <select value={filterPeriod} onChange={e => { setFilterPeriod(e.target.value); if(e.target.value) setPeriod(e.target.value); }}
                  style={{ width:'100%', padding:'6px 10px', background:'var(--bg-card,#2c333e)', border:'1px solid var(--border2,#626d80)', borderRadius:7, color:'var(--text,#fff)', fontSize:12, outline:'none' }}>
                  <option value="">{t('All time')}</option>
                  {PERIODS.map(p => <option key={p.key} value={p.key}>{t(p.label)}</option>)}
                </select>
              </div>

              {/* Country */}
              <div>
                <div style={{ fontSize: 10, color: 'var(--text3,#555)', marginBottom: 5, textTransform:'uppercase', letterSpacing:'.06em' }}>{t('Country')}</div>
                <select value={filterCountry} onChange={e => { setFilterCountry(e.target.value); setPage(1); }}
                  style={{ width:'100%', padding:'6px 10px', background:'var(--bg-card,#2c333e)', border:'1px solid var(--border2,#626d80)', borderRadius:7, color:'var(--text,#fff)', fontSize:12, outline:'none' }}>
                  <option value="">{t('All countries')}</option>
                  {uniqueCountries.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>

              {/* City */}
              <div>
                <div style={{ fontSize: 10, color: 'var(--text3,#555)', marginBottom: 5, textTransform:'uppercase', letterSpacing:'.06em' }}>{t('City')}</div>
                <select value={filterCity} onChange={e => { setFilterCity(e.target.value); setPage(1); }}
                  style={{ width:'100%', padding:'6px 10px', background:'var(--bg-card,#2c333e)', border:'1px solid var(--border2,#626d80)', borderRadius:7, color:'var(--text,#fff)', fontSize:12, outline:'none' }}>
                  <option value="">{t('All cities')}</option>
                  {uniqueCities.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>

              {/* IB */}
              <div>
                <div style={{ fontSize: 10, color: 'var(--text3,#555)', marginBottom: 5, textTransform:'uppercase', letterSpacing:'.06em' }}>{t('IB')}</div>
                <select value={filterIB} onChange={e => { setFilterIB(e.target.value); setPage(1); }}
                  style={{ width:'100%', padding:'6px 10px', background:'var(--bg-card,#2c333e)', border:'1px solid var(--border2,#626d80)', borderRadius:7, color:'var(--text,#fff)', fontSize:12, outline:'none' }}>
                  <option value="">{t('All IBs')}</option>
                  {uniqueIBs.map(i => <option key={i} value={i}>{i}</option>)}
                </select>
              </div>

              {/* Sales agent (#10) */}
              <div>
                <div style={{ fontSize: 10, color: 'var(--text3,#555)', marginBottom: 5, textTransform:'uppercase', letterSpacing:'.06em' }}>{t('Sales agent')}</div>
                <input list="clients-agent-roster" value={filterAgent} onChange={e => { setFilterAgent(e.target.value); setPage(1); }}
                  placeholder={t('All agents — type to search')}
                  style={{ width:'100%', padding:'6px 10px', background:'var(--bg-card,#2c333e)', border:'1px solid var(--border2,#626d80)', borderRadius:7, color:'var(--text,#fff)', fontSize:12, outline:'none', boxSizing:'border-box' as any }} />
                <datalist id="clients-agent-roster">
                  {(agentRoster.length ? agentRoster.map((a:any)=>a.full_name)
                                       : uniqueAgents).map((a:string) => <option key={a} value={a} />)}
                </datalist>
              </div>

              {/* KYC */}
              <div>
                <div style={{ fontSize: 10, color: 'var(--text3,#555)', marginBottom: 5, textTransform:'uppercase', letterSpacing:'.06em' }}>{t('KYC status')}</div>
                <select value={filterKyc} onChange={e => { setFilterKyc(e.target.value); setPage(1); }}
                  style={{ width:'100%', padding:'6px 10px', background:'var(--bg-card,#2c333e)', border:'1px solid var(--border2,#626d80)', borderRadius:7, color:'var(--text,#fff)', fontSize:12, outline:'none' }}>
                  <option value="">{t('All')}</option>
                  <option value="verified">{t('Verified')}</option>
                  <option value="pending">{t('Pending')}</option>
                </select>
              </div>

              {/* Risk */}
              <div>
                <div style={{ fontSize: 10, color: 'var(--text3,#555)', marginBottom: 5, textTransform:'uppercase', letterSpacing:'.06em' }}>{t('Risk level')}</div>
                <select value={filterRisk} onChange={e => setFilterRisk(e.target.value)}
                  style={{ width:'100%', padding:'6px 10px', background:'var(--bg-card,#2c333e)', border:'1px solid var(--border2,#626d80)', borderRadius:7, color:'var(--text,#fff)', fontSize:12, outline:'none' }}>
                  <option value="">{t('All')}</option>
                  <option value="high">{t('High')}</option>
                  <option value="medium">{t('Medium')}</option>
                  <option value="low">{t('Low')}</option>
                </select>
              </div>

              {/* Number of deposits (ticket #60) */}
              <div>
                <div style={{ fontSize: 10, color: 'var(--text3,#555)', marginBottom: 5, textTransform:'uppercase', letterSpacing:'.06em' }}>{t('# Deposits')}</div>
                <select value={filterDeposits} onChange={e => { setFilterDeposits(e.target.value); setPage(1); }}
                  style={{ width:'100%', padding:'6px 10px', background:'var(--bg-card,#2c333e)', border:'1px solid var(--border2,#626d80)', borderRadius:7, color:'var(--text,#fff)', fontSize:12, outline:'none' }}>
                  <option value="">{t('Any')}</option>
                  <option value="D1">{t('D1 — exactly 1')}</option>
                  <option value="D2">{t('D2 — exactly 2')}</option>
                  <option value="D3">{t('D3 — exactly 3')}</option>
                  <option value="D4">{t('D4 — exactly 4')}</option>
                  <option value="D5+">{t('D5+ — 5 or more')}</option>
                </select>
              </div>

              {/* Inactive deposit period (ticket #157) — depositors gone quiet, for retention */}
              <div>
                <div style={{ fontSize: 10, color: 'var(--text3,#555)', marginBottom: 5, textTransform:'uppercase', letterSpacing:'.06em' }}>{t('Last deposit')}</div>
                <div style={{ display:'flex', gap:6 }}>
                  <select value={filterNoDep} onChange={e => { setFilterNoDep(e.target.value); setPage(1); }}
                    style={{ flex:1, padding:'6px 10px', background:'var(--bg-card,#2c333e)', border:'1px solid var(--border2,#626d80)', borderRadius:7, color:'var(--text,#fff)', fontSize:12, outline:'none' }}>
                    <option value="">{t('Any')}</option>
                    <option value="3">{t('No deposit 3+ months')}</option>
                    <option value="4">{t('No deposit 4+ months')}</option>
                    <option value="6">{t('No deposit 6+ months')}</option>
                    <option value="12">{t('No deposit 12+ months')}</option>
                    <option value="custom">{t('Custom…')}</option>
                  </select>
                  {filterNoDep === 'custom' && (
                    <input type="number" min={1} value={noDepCustom} placeholder={t('months')}
                      onChange={e => { setNoDepCustom(e.target.value); setPage(1); }}
                      style={{ width:70, padding:'6px 8px', background:'var(--bg-card,#2c333e)', border:'1px solid var(--border2,#626d80)', borderRadius:7, color:'var(--text,#fff)', fontSize:12, outline:'none' }} />
                  )}
                </div>
              </div>

              {/* Birthday this week (birthday bonus) */}
              <div>
                <div style={{ fontSize: 10, color: 'var(--text3,#555)', marginBottom: 5, textTransform:'uppercase', letterSpacing:'.06em' }}>🎂 {t('Birthday')}</div>
                <select value={filterBirthday} onChange={e => { setFilterBirthday(e.target.value); setPage(1); }}
                  style={{ width:'100%', padding:'6px 10px', background:'var(--bg-card,#2c333e)', border:'1px solid var(--border2,#626d80)', borderRadius:7, color:'var(--text,#fff)', fontSize:12, outline:'none' }}>
                  <option value="">{t('Any')}</option>
                  <option value="week">{t('Birthday this week')}</option>
                  <option value="unclaimed">{t('This week · not yet claimed')}</option>
                </select>
              </div>

              {/* Reg date from (ticket #62) */}
              <div>
                <div style={{ fontSize: 10, color: 'var(--text3,#555)', marginBottom: 5, textTransform:'uppercase', letterSpacing:'.06em' }}>{t('Registered from')}</div>
                <input type="date" max={new Date(Date.now()+86400000).toISOString().slice(0,10)} value={filterDateFrom} onChange={e => { setFilterDateFrom(e.target.value); setPage(1); }}
                  style={{ width:'100%', padding:'5px 10px', background:'var(--bg-card,#2c333e)', border:'1px solid var(--border2,#626d80)', borderRadius:7, color:'var(--text,#fff)', fontSize:12, outline:'none', colorScheme:'dark' as any, boxSizing:'border-box' as any }} />
              </div>

              {/* Reg date to (ticket #62) */}
              <div>
                <div style={{ fontSize: 10, color: 'var(--text3,#555)', marginBottom: 5, textTransform:'uppercase', letterSpacing:'.06em' }}>{t('Registered to')}</div>
                <input type="date" max={new Date(Date.now()+86400000).toISOString().slice(0,10)} value={filterDateTo} onChange={e => { setFilterDateTo(e.target.value); setPage(1); }}
                  style={{ width:'100%', padding:'5px 10px', background:'var(--bg-card,#2c333e)', border:'1px solid var(--border2,#626d80)', borderRadius:7, color:'var(--text,#fff)', fontSize:12, outline:'none', colorScheme:'dark' as any, boxSizing:'border-box' as any }} />
              </div>

            </div>

            {/* Source multi-select */}
            <div>
              <div style={{ fontSize: 10, color: 'var(--text3,#555)', marginBottom: 6, textTransform:'uppercase', letterSpacing:'.06em' }}>{t('Source (multi-select)')}</div>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {SOURCES.map(s => {
                  const active = filterSources.includes(s);
                  return (
                    <div key={s} onClick={() => setFilterSources(prev => active ? prev.filter(x=>x!==s) : [...prev,s])}
                      style={{ padding:'4px 10px', borderRadius:99, cursor:'pointer', fontSize:11, fontWeight:500, border:`1px solid ${active?SOURCE_COLORS[s]:'var(--border2,#626d80)'}`, background: active?`${SOURCE_COLORS[s]}22`:'transparent', color: active?SOURCE_COLORS[s]:'var(--text2,#888)', transition:'all 0.15s' }}>
                      {t(SOURCE_LABELS[s])}
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Active filter pills + clear */}
            {hasFilters && (
              <div style={{ display:'flex', gap:5, flexWrap:'wrap', alignItems:'center', marginTop:10, paddingTop:10, borderTop:'1px solid var(--border,#4f596b)' }}>
                <span style={{ fontSize:11, color:'var(--text3,#555)', marginRight:4 }}>{t('Active:')}</span>
                {filterPeriod  && <span style={{ fontSize:11, padding:'2px 8px', borderRadius:99, background:'rgba(0,229,160,0.1)', color:'#00e5a0', cursor:'pointer' }} onClick={() => setFilterPeriod('')}>📅 {t(PERIODS.find(p=>p.key===filterPeriod)?.label || '')} ✕</span>}
                {filterCountry && <span style={{ fontSize:11, padding:'2px 8px', borderRadius:99, background:'rgba(0,102,255,0.15)', color:'#4d9fff', cursor:'pointer' }} onClick={() => setFilterCountry('')}>🌍 {filterCountry} ✕</span>}
                {filterCity    && <span style={{ fontSize:11, padding:'2px 8px', borderRadius:99, background:'rgba(0,102,255,0.15)', color:'#4d9fff', cursor:'pointer' }} onClick={() => setFilterCity('')}>🏙 {filterCity} ✕</span>}
                {filterIB      && <span style={{ fontSize:11, padding:'2px 8px', borderRadius:99, background:'rgba(255,140,0,0.15)', color:'#ff8c00', cursor:'pointer' }} onClick={() => setFilterIB('')}>🔗 {filterIB} ✕</span>}
                {filterKyc     && <span style={{ fontSize:11, padding:'2px 8px', borderRadius:99, background:'rgba(0,229,160,0.1)', color:'#00e5a0', cursor:'pointer' }} onClick={() => setFilterKyc('')}>🛡 {t(filterKyc)} ✕</span>}
                {filterRisk    && <span style={{ fontSize:11, padding:'2px 8px', borderRadius:99, background:'rgba(255,77,77,0.1)', color:'#ff4d4d', cursor:'pointer' }} onClick={() => setFilterRisk('')}>⚠ {filterRisk} {t('risk')} ✕</span>}
                {filterDeposits && <span style={{ fontSize:11, padding:'2px 8px', borderRadius:99, background:'rgba(0,229,160,0.1)', color:'#00e5a0', cursor:'pointer' }} onClick={() => setFilterDeposits('')}>💵 {filterDeposits} ✕</span>}
                {filterNoDep && <span style={{ fontSize:11, padding:'2px 8px', borderRadius:99, background:'rgba(255,170,0,0.12)', color:'#ffaa00', cursor:'pointer' }} onClick={() => { setFilterNoDep(''); setNoDepCustom(''); }}>⏳ {t('No deposit')} {(filterNoDep === 'custom' ? noDepCustom : filterNoDep)}m+ ✕</span>}
                {filterBirthday && <span style={{ fontSize:11, padding:'2px 8px', borderRadius:99, background:'rgba(255,138,200,0.15)', color:'#ff8ac8', cursor:'pointer' }} onClick={() => setFilterBirthday('')}>🎂 {filterBirthday === 'unclaimed' ? t('Birthday · not claimed') : t('Birthday this week')} ✕</span>}
                {filterDateFrom && <span style={{ fontSize:11, padding:'2px 8px', borderRadius:99, background:'rgba(0,170,255,0.12)', color:'#4d9fff', cursor:'pointer' }} onClick={() => setFilterDateFrom('')}>📅 {t('from')} {filterDateFrom} ✕</span>}
                {filterDateTo  && <span style={{ fontSize:11, padding:'2px 8px', borderRadius:99, background:'rgba(0,170,255,0.12)', color:'#4d9fff', cursor:'pointer' }} onClick={() => setFilterDateTo('')}>📅 {t('to')} {filterDateTo} ✕</span>}
                {filterSources.map(s => <span key={s} style={{ fontSize:11, padding:'2px 8px', borderRadius:99, background:`${SOURCE_COLORS[s]}22`, color:SOURCE_COLORS[s], cursor:'pointer' }} onClick={() => setFilterSources(prev=>prev.filter(x=>x!==s))}>📣 {t(SOURCE_LABELS[s])} ✕</span>)}
                <span style={{ fontSize:11, color:'#ff4d4d', cursor:'pointer', marginLeft:4 }} onClick={clearFilters}>{t('Clear all')}</span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Bulk-action bar (ticket #38) — appears when ≥1 client is selected */}
      {selectedLogins.length > 0 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '8px 16px', background: 'rgba(0,229,160,0.08)', borderBottom: '1px solid var(--border,#4f596b)', flexShrink: 0, position: 'relative', zIndex: 20 }}>
          <span style={{ fontSize: 13, fontWeight: 600, color: '#00e5a0' }}>{selectedLogins.length} {t('selected')}</span>
          <div style={{ position: 'relative' }}>
            <button onClick={() => setBulkMenuOpen(o => !o)}
              style={{ padding: '5px 14px', borderRadius: 7, border: '1px solid #00e5a0', background: 'rgba(0,229,160,0.12)', color: '#00e5a0', cursor: 'pointer', fontSize: 12, fontWeight: 600 }}>
              {t('Bulk actions')} ▾
            </button>
            {bulkMenuOpen && (
              <div style={{ position: 'absolute', top: '110%', left: 0, background: '#2c333e', border: '1px solid #626d80', borderRadius: 8, padding: 6, minWidth: 200, zIndex: 50, boxShadow: '0 8px 24px rgba(0,0,0,0.5)' }}>
                <div style={{ fontSize: 10, color: '#555', padding: '4px 10px', textTransform: 'uppercase', letterSpacing: .5 }}>{t('Starting point — wire up later')}</div>
                {[
                  { key: 'export', label: '⬇ '+t('Export selected (CSV)') },
                  { key: 'assign', label: '👤 '+t('Assign to agent…') },
                  { key: 'dialer', label: '📞 '+t('Add to Power Dialer') },
                ].map(a => (
                  <div key={a.key}
                    onClick={() => {
                      if (a.key === 'export') {
                        const rows = clients.filter((c:any) => selectedLogins.includes(c.login));
                        const header = ['login','name','email','phone','country','total_deposit','total_withdraw'];
                        const csv = [header.join(','),
                          ...rows.map((c:any) => header.map(h => JSON.stringify((c as any)[h] ?? '')).join(','))].join('\n');
                        const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
                        const link = document.createElement('a');
                        link.href = url; link.download = `clients_selection_${Date.now()}.csv`; link.click();
                        URL.revokeObjectURL(url);
                        setBulkMenuOpen(false);
                      } else {
                        alert(`${t('Bulk')} "${a.label.replace(/^[^ ]+ /,'')}" ${t('for')} ${selectedLogins.length} ${t('clients — coming soon.')}\n${t('Logins:')} ${selectedLogins.join(', ')}`);
                        setBulkMenuOpen(false);
                      }
                    }}
                    style={{ padding: '8px 10px', borderRadius: 6, cursor: 'pointer', fontSize: 12, color: '#ccc' }}
                    onMouseEnter={e => (e.currentTarget.style.background = '#373f4d')}
                    onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}>
                    {a.label}
                  </div>
                ))}
              </div>
            )}
          </div>
          {/* Archive / unarchive selected (ticket #57) */}
          {archiveView !== 'archived' && (
            <button onClick={() => bulkArchive(true)}
              style={{ padding: '5px 12px', borderRadius: 7, border: '1px solid #ffaa00', background: 'rgba(255,170,0,0.12)', color: '#ffaa00', cursor: 'pointer', fontSize: 12, fontWeight: 600 }}>
              🗄 {t('Archive selected')}
            </button>
          )}
          {archiveView !== 'active' && (
            <button onClick={() => bulkArchive(false)}
              style={{ padding: '5px 12px', borderRadius: 7, border: '1px solid #00e5a0', background: 'rgba(0,229,160,0.12)', color: '#00e5a0', cursor: 'pointer', fontSize: 12, fontWeight: 600 }}>
              ♻ {t('Unarchive selected')}
            </button>
          )}
          <button onClick={clearSelection}
            style={{ padding: '5px 12px', borderRadius: 7, border: '1px solid #626d80', background: 'transparent', color: '#888', cursor: 'pointer', fontSize: 12 }}>
            ✕ {t('Clear selection')}
          </button>
        </div>
      )}

      {/* Table */}
      <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
        <div style={{ overflowX: 'auto', overflowY: 'auto', flex: 1, scrollbarWidth: 'thin' }}>
        <style>{`.crm-clients-table td, .crm-clients-table th { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }`}</style>
        <table className="crm-clients-table" style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12, tableLayout: 'fixed' as any }}>
          <colgroup>
            {ALL_COLS.filter(h => V(h)).map(h => <col key={h} style={{ width: COL_W[h] || 90 }} />)}
          </colgroup>
          <thead>
            <tr style={{ background: 'var(--bg-input,#373f4d)', position: 'sticky', top: 0, zIndex: 10 }}>
              {ALL_COLS.filter(h => V(h)).map(h => {
                const sortable = ['Equity','Total dep.','Total with.','Margin%','Network','1st Deposit'].includes(h);
                const active = sortCol === h;
                return (
                  <th key={h} onClick={() => sortable && toggleSort(h)}
                    style={{ padding: '9px 8px', textAlign: 'left', color: active?'var(--accent,#00e5a0)':'#cfd6e0', fontWeight: 600, borderBottom: '1px solid var(--border,#4f596b)', whiteSpace: 'nowrap', fontSize: 11, cursor: sortable?'pointer':'default', userSelect:'none' }}>
                    <span style={{ display:'inline-flex', alignItems:'center', gap:4 }}>
                      {t(h)}
                      {sortable && (
                        <span style={{ display:'inline-flex', flexDirection:'column', lineHeight:1, fontSize:8, opacity: active?1:0.3 }}>
                          <span style={{ color: active && sortDir==='asc' ? 'var(--accent,#00e5a0)' : 'inherit' }}>▲</span>
                          <span style={{ color: active && sortDir==='desc' ? 'var(--accent,#00e5a0)' : 'inherit' }}>▼</span>
                        </span>
                      )}
                    </span>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={19} style={{ padding: 60, textAlign: 'center', color: 'var(--text3,#555)' }}>{t('Loading...')}</td></tr>
            ) : sortedFiltered.length === 0 ? (
              <tr><td colSpan={19} style={{ padding: 60, textAlign: 'center', color: 'var(--text3,#555)' }}>{t('No clients found')}</td></tr>
            ) : sortedFiltered.map((c, i) => (
              <tr key={i} style={{ borderBottom: '1px solid #373f4d', background: selectedLogins.includes(c.login) ? 'rgba(0,229,160,0.06)' : 'transparent' }}
                onMouseEnter={e => (e.currentTarget.style.background = selectedLogins.includes(c.login) ? 'rgba(0,229,160,0.1)' : '#2c333e')}
                onMouseLeave={e => (e.currentTarget.style.background = selectedLogins.includes(c.login) ? 'rgba(0,229,160,0.06)' : 'transparent')}>

                {/* Client — click name → profile page */}
                <td style={{ padding: '9px 8px' }}>
                  <div style={{ display:'flex', alignItems:'center', gap:6 }}>
                    <a href={`?client=${c.login}`} style={{ fontWeight: 500, color: '#00e5a0', cursor: 'pointer', whiteSpace: 'nowrap', textDecoration: 'none' }}
                       onClick={(e) => { if (e.ctrlKey||e.metaKey||e.shiftKey||e.button===1) return; e.preventDefault(); setProfileClient(c); }}
                       title={`${c.name} — ${t('right-click to open in a new tab')}`}>{(c.name || '').trim().split(/\s+/).slice(0, 2).join(' ')}</a>
                    <BirthdayCake b={c.birthday} />
                    {c.is_flagged && <span style={{ fontSize:9, padding:'1px 6px', borderRadius:99, background:'rgba(255,77,77,0.15)', color:'#ff4d4d', border:'1px solid rgba(255,77,77,0.3)', whiteSpace:'nowrap' }}>🚨 {t('FLAGGED')}</span>}
                    {(() => {
                      const f = abuseFlags[c.login] || ((c.related_accounts||[]).map((a:any)=>abuseFlags[a.login]).find(Boolean));
                      if (!f) return null;
                      const col: any = { critical:'#ff4d4d', high:'#ff8800', medium:'#ffaa00' };
                      const cc = col[f.severity] || '#ff4d4d';
                      return <span title={`${t('In')} ${f.n_cases} ${t('open abuse case(s) — click to open Abuse Detection')}`}
                        onClick={(e)=>{ e.stopPropagation(); window.dispatchEvent(new CustomEvent('navigate',{detail:{page:'abuse'}})); }}
                        style={{ fontSize:9, padding:'1px 6px', borderRadius:99, background:`${cc}22`, color:cc, border:`1px solid ${cc}66`, whiteSpace:'nowrap', cursor:'pointer', fontWeight:700 }}>
                        {f.hot ? '🔥 ' : '⛔ '}{t(ABUSE_TYPE_LABEL[f.abuse_type] || 'Abuse')}</span>;
                    })()}
                    {c.lead_badge === 'recapture' && <span onMouseEnter={e=>setBadgeHover({client:c, kind:'recapture', x:e.clientX, y:e.clientY})} onMouseLeave={()=>setBadgeHover(null)} style={{ fontSize:12, padding:'1px 5px', borderRadius:99, background:'rgba(255,77,77,0.15)', border:'1px solid #ff4d4d', whiteSpace:'nowrap', cursor:'help' }}>♻</span>}
                    {c.lead_badge === 'reactivated' && <span title={t('Was archived — came back (re-engaged). +50 score.')} style={{ fontSize:9, fontWeight:700, padding:'2px 6px', borderRadius:99, background:'rgba(248,80,10,0.14)', color:'#FF6A1A', border:'1px solid #F8500A', whiteSpace:'nowrap' }}>📦 {t('Re-captured')}</span>}
                    {c.lead_badge === 'from_lead' && <span onMouseEnter={e=>setBadgeHover({client:c, kind:'from_lead', x:e.clientX, y:e.clientY})} onMouseLeave={()=>setBadgeHover(null)} style={{ fontSize:12, padding:'1px 5px', borderRadius:99, background:'rgba(0,170,255,0.12)', border:'1px solid #00aaff', whiteSpace:'nowrap', cursor:'help' }}>📥</span>}
                    {!c.is_flagged && c.risk==='high' && <span style={{ fontSize:9, padding:'1px 6px', borderRadius:99, background:'rgba(255,170,0,0.15)', color:'#ffaa00', border:'1px solid rgba(255,170,0,0.3)' }}>⚠️</span>}
                    {c.stage && <span title={t('TradeSoft stage')+(c.stage_id?(' (id '+c.stage_id+')'):'')} style={{ fontSize:9, fontWeight:700, padding:'1px 7px', borderRadius:99, background:'rgba(153,102,255,0.15)', color:'#b794ff', border:'1px solid rgba(153,102,255,0.35)', whiteSpace:'nowrap' }}>◇ {String(c.stage)}</span>}
                  </div>
                  <div style={{ display:'flex', alignItems:'center', gap:8, marginTop:1 }}>
                    {/* show the REAL email address (click = compose), not the word "Email" — it read
                        as if the account number was the email. (#212) */}
                    {c.email
                      ? <span style={{ color:'#8a93a3', fontSize:10, cursor:'pointer', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap', maxWidth:190 }} title={`${t('Send email')}: ${c.email}`} onClick={(e) => { e.stopPropagation(); setEmailClient(c); }}>✉️ {c.email}</span>
                      : <span style={{ color:'#556', fontSize:10 }}>✉️ {t('no email')}</span>}
                  </div>
                </td>

                {/* Accounts: count + platform (account group/type removed per request) */}
                {V('Accounts') && (
                <td style={{ padding: '9px 8px', fontSize: 11 }}>
                  <div style={{ display:'flex', flexDirection:'column', gap:3, alignItems:'flex-start' }}>
                    <span title={`${t('Accounts')}: ${(c.all_logins || [c.login]).map((l:any) => '#' + l).join(', ')}`}
                      style={{ background:'rgba(0,170,255,0.12)', color:'#4d9fff', padding:'2px 7px', borderRadius:99, fontWeight:600, cursor:'help' }}>
                      {c.account_count || 1} {(c.account_count||1) > 1 ? t('accts') : t('acct')}
                    </span>
                    <div style={{ display:'flex', gap:3, flexWrap:'wrap' }}>
                      {(c.platforms && c.platforms.length ? c.platforms : ['MT5']).map((p:string) => (
                        <span key={p} style={{ fontSize:9, padding:'1px 5px', borderRadius:4, fontWeight:700,
                          background: p==='MT4' ? 'rgba(255,140,0,0.15)' : 'rgba(0,229,160,0.12)',
                          color: p==='MT4' ? '#ff8c00' : '#00e5a0' }}>{p}</span>
                      ))}
                    </div>
                  </div>
                </td>
                )}

                {/* Phone */}
                {V('Phone') && (
                <td style={{ padding: '9px 8px' }}>
                  {c.phone ? (
                    <div onClick={() => setPhoneClient(c)} title={c.phone} style={{ cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 5, padding: '3px 8px', borderRadius: 6, border: '1px solid #626d80', background: '#373f4d', fontSize: 11, color: '#888', whiteSpace: 'nowrap' }}
                      onMouseEnter={e => (e.currentTarget.style.borderColor='#00e5a0')}
                      onMouseLeave={e => (e.currentTarget.style.borderColor='#626d80')}>
                      📞 ···{c.phone.slice(-4)}
                    </div>
                  ) : <span style={{ color: '#626d80', fontSize: 11 }}>—</span>}
                </td>
                )}

                {/* Country — click to filter */}
                {V('Country/City') && (
                <td style={{ padding: '9px 8px' }}>
                  <div style={{ color: '#888', cursor: 'pointer' }} onClick={() => setFilterCountry(c.country)} title={t('Filter by country')}>{c.country}</div>
                  <div style={{ color: '#555', fontSize: 11, cursor: 'pointer' }} onClick={() => setFilterCity(c.city)} title={t('Filter by city')}>{c.city}</div>
                </td>
                )}

                {/* Agent — click to filter */}
                {V('Agent') && (
                <td style={{ padding: '9px 8px', fontSize: 11 }} onClick={e=>e.stopPropagation()}>
                  <AgentCell entityType="client" entityId={c.login} agentName={c.agent_name}
                    onSortBy={(n)=>setFilterAgent(n)}
                    onChanged={()=> fetchClients()} />
                  {!c.agent_name && c.sales_agent && <div title={t('Sales agent (from TradeSoft)')} style={{ color:'#9966ff', fontSize:10, marginTop:2, whiteSpace:'nowrap', overflow:'hidden', textOverflow:'ellipsis', maxWidth:120 }}>👤 {c.sales_agent}</div>}
                </td>
                )}

                {/* IB — #230: a real linked IB opens IB Admin DIRECTLY on click (same as the client
                    profile). Only when there's no IB record (free-text referrer / #agent) do we fall
                    back to the click-to-filter behaviour — no more "No IB for…" popup on valid IBs. */}
                {V('IB') && (
                <td style={{ padding: '9px 8px', color: c.ib_id ? '#00aaff' : '#8b93a1', fontSize: 11, cursor: c.ib_display ? 'pointer' : 'default' }}
                  title={c.ib_id ? t('Open this IB in IB Admin') : (c.ib_display ? t('Click to filter by this IB') : '')}
                  onClick={() => {
                    if (c.ib_id) { window.dispatchEvent(new CustomEvent('navigate', { detail: { page: 'ib_admin', ibId: c.ib_id } })); }
                    else if (c.ib_display) { setFilterIB(c.ib_display); setPage(1); }
                  }}>
                  {c.ib_display ? c.ib_display.split('(')[0].trim() : (c.ib || '—')}
                </td>
                )}

                {/* 1st deposit — date + amount */}
                {V('1st Deposit') && (
                <td style={{ padding: '9px 8px', fontSize: 11 }}>
                  {c.first_deposit_date ? (
                    <div>
                      <div style={{ color: '#888', fontSize:11 }}>{new Date(c.first_deposit_date).toLocaleDateString('en-GB')}</div>
                      {c.first_deposit_amount > 0 && <div style={{ color: '#00e5a0', fontWeight: 500, fontSize:11 }}>${(c.first_deposit_amount||0).toLocaleString('en-GB')}</div>}
                    </div>
                  ) : <span style={{ color: '#626d80' }}>—</span>}
                </td>
                )}



                {/* Deposit count */}
                {V('Dep#') && (
                <td style={{ padding: '9px 8px', color: '#888', textAlign:'center' }} onClick={e=>e.stopPropagation()}>
                  {(c.dep_count||c.deposit_count||0) > 0
                    ? <span
                        onMouseEnter={e=>{e.stopPropagation();setDepPopup({client:c, x:e.clientX, y:e.clientY});}}
                        onMouseLeave={()=>setDepPopup(null)}
                        style={{ background:'rgba(0,229,160,0.1)', color:'#00e5a0', padding:'2px 8px', borderRadius:99, fontSize:11, cursor:'default' }}>
                        {c.dep_count||c.deposit_count}x
                      </span>
                    : <span style={{color:'#626d80'}}>—</span>}
                </td>
                )}

                {/* Last Activity - client actions */}
                {V('Last Activity') && (
                <td style={{ padding: '9px 8px', fontSize: 11 }}>
                  {c.last_activity_type ? (() => {
                    const actColors: any = { deposit:'#00e5a0', withdrawal:'#ff8888', internal_transfer:'#00aaff', trade:'#ffaa00', bonus_deposit:'#cc88ff', credit:'#cc88ff', adjustment:'#888' };
                    const actLabels: any = { deposit:'Deposit', withdrawal:'Withdraw', internal_transfer:'Transfer', trade:'Trade', bonus_deposit:'Bonus', credit:'Credit', adjustment:'Adjust' };
                    return (
                      <div>
                        <span style={{ fontSize:10, padding:'2px 6px', borderRadius:4, background:`${actColors[c.last_activity_type]||'#888'}22`, color:actColors[c.last_activity_type]||'#888' }}>
                          {t(actLabels[c.last_activity_type] || c.last_activity_type)}
                        </span>
                        {c.last_activity_date && <div style={{ color:'#555', marginTop:2 }}>{new Date(c.last_activity_date).toLocaleDateString('en-GB')}</div>}
                      </div>
                    );
                  })() : <span style={{ color: '#626d80' }}>—</span>}
                </td>
                )}

                {/* Total deposit */}
                {V('Total dep.') && (
                <td style={{ padding: '9px 8px', color: '#00e5a0', fontWeight: 500, whiteSpace: 'nowrap' }}>${(c.total_deposit||0).toLocaleString('en-GB')}</td>
                )}

                {/* Total withdraw */}
                {V('Total with.') && (
                <td style={{ padding: '9px 8px', color: '#ff8888', whiteSpace: 'nowrap' }}>${(c.total_withdraw||0).toLocaleString('en-GB')}</td>
                )}

                {/* Equity */}
                {V('Equity') && (
                <td style={{ padding: '9px 8px', whiteSpace: 'nowrap' }}>
                  <span style={{ color: (c.equity||0) >= (c.balance||0) ? '#00e5a0' : '#ff8888', fontWeight:500 }}>
                    ${(c.equity||0).toLocaleString('en-GB')}
                  </span>
                </td>
                )}

                {/* Margin */}
                {V('Margin%') && (
                <td style={{ padding: '9px 8px' }}>
                  {c.margin_level > 0 ? <span style={{ color: c.margin_level < 80 ? '#ff4d4d' : c.margin_level < 150 ? '#ffaa00' : '#00e5a0', fontWeight: 500 }}>{c.margin_level.toFixed(0)}%</span> : <span style={{ color: '#626d80' }}>—</span>}
                </td>
                )}

                {/* Network — ONE unified badge (canonical 0-10; click for linked accounts) */}
                {V('Network') && (
                <td style={{ padding: '9px 8px' }}>
                  <NetworkBadge score={c.network_score} login={c.login} />
                </td>
                )}

                {/* Last Comment - sales agent actions */}
                {V('Last Comment') && (
                <td style={{ padding: '9px 8px', maxWidth: 140 }}>
                  {c.last_action_note ? (
                    <div>
                      <div style={{ fontSize: 11, color: '#aaa', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 130 }} title={c.last_action_note}>{c.last_action_note}</div>
                      {c.last_action_date && <div style={{ fontSize: 10, color: '#444', marginTop: 2 }}>{new Date(c.last_action_date).toLocaleDateString('en-GB')}</div>}
                    </div>
                  ) : c.last_action_type ? (
                    <div>
                      <span style={{ fontSize: 10, padding: '2px 6px', borderRadius: 4, background: `${(actionColors as any)[c.last_action_type]}22`, color: (actionColors as any)[c.last_action_type] }}>{t((actionLabels as any)[c.last_action_type])}</span>
                      {c.last_action_date && <div style={{ fontSize: 10, color: '#444', marginTop: 2 }}>{new Date(c.last_action_date).toLocaleDateString('en-GB')}</div>}
                    </div>
                  ) : <span style={{ color: '#626d80' }}>—</span>}
                </td>
                )}
                {/* Score */}
                {V('Score') && (
                <td style={{ padding: '9px 8px' }}>
                  <div style={{ display:'inline-block' }}
                    onMouseEnter={e => { const r=(e.currentTarget as HTMLElement).getBoundingClientRect(); setScoreHover({ login:c.login, x:r.left+r.width/2, y:r.bottom+6 }); }}
                    onMouseLeave={() => setScoreHover(null)}>
                    <div onClick={(e)=>{ e.stopPropagation(); const r=(e.currentTarget as HTMLElement).getBoundingClientRect(); setScoreHover({ login:c.login, x:r.left+r.width/2, y:r.bottom+6 }); setScorePin(p => p===c.login ? null : c.login); }}
                      style={{ display:'inline-flex', alignItems:'center', justifyContent:'center', width:36, height:36, borderRadius:'50%', border:`2px solid ${scoreColor(c.call_score||0)}`, color:scoreColor(c.call_score||0), fontWeight:700, fontSize:12, cursor:'pointer' }}
                      title={t('Click for score details')}>
                      {c.call_score||0}
                    </div>
                    {(scoreHover?.login === c.login || scorePin === c.login) && (() => {
                      const reasons = (c.score_breakdown && c.score_breakdown.length) ? c.score_breakdown : scoreReasons(c, t);
                      const pinned = scorePin === c.login;
                      const px = Math.min(Math.max(120, scoreHover?.x ?? window.innerWidth/2), window.innerWidth - 120);
                      const py = Math.min(scoreHover?.y ?? 120, window.innerHeight - 260);
                      return (
                      <div onClick={e=>e.stopPropagation()} style={{ position:'fixed', left:px, top:py, transform:'translateX(-50%)', background:'#373f4d', border:`1px solid ${pinned?'#00aaff':'#626d80'}`, borderRadius:10, padding:12, width:230, zIndex:99999, boxShadow:'0 8px 28px rgba(0,0,0,0.5)', pointerEvents: pinned?'auto':'none' }}>
                        <div style={{ fontSize:12, fontWeight:600, marginBottom:8, display:'flex', justifyContent:'space-between', alignItems:'center' }}>{t('Why this priority score')}{pinned && <span onClick={()=>setScorePin(null)} style={{ cursor:'pointer', color:'#888', fontSize:14 }}>×</span>}</div>
                        {reasons.length === 0 ? <div style={{ fontSize:11, color:'#888' }}>{t('No active triggers — low priority.')}</div>
                          : reasons.map((r:any, ri:number) => (
                            <div key={ri} style={{ display:'flex', justifyContent:'space-between', fontSize:11, marginBottom:4 }}>
                              <span style={{ color:'#aaa' }}>{r.label}</span>
                              <span style={{ color:r.points>0?'#ff8c00':'#00e5a0', fontWeight:600 }}>{r.points>0?'+':''}{r.points}</span>
                            </div>
                          ))}
                        <div style={{ borderTop:'1px solid #626d80', marginTop:8, paddingTop:6, display:'flex', justifyContent:'space-between', fontSize:12 }}>
                          <span style={{ color:'#888' }}>{t('Total')}</span>
                          <span style={{ fontWeight:700 }}>{c.call_score||0}</span>
                        </div>
                      </div>
                      );
                    })()}
                  </div>
                </td>
                )}

                {/* Action */}
                <td style={{ padding: '9px 8px' }} onClick={e=>e.stopPropagation()}>
                  <div style={{ display:'flex', gap:5, alignItems:'center' }}>
                    <button onClick={e => { e.stopPropagation(); setActionMenu(c); setActionStep('menu'); setActionType(''); }}
                      style={{ padding:'5px 12px', background:'#373f4d', border:'1px solid #626d80', borderRadius:6, color:'#888', cursor:'pointer', fontSize:11, whiteSpace:'nowrap' }}>
                      {t('Action')} ▾
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      </div>
      {/* Pagination — shared Pager (page-size + go-to-page dropdown) */}
      <Pager page={page} setPage={setPage} pageSize={pageSize} setPageSize={setPageSize}
        count={clients.length} total={total} label={t('clients')} />

      {/* Phone modal */}
      {phoneClient && <PhoneModal client={phoneClient} onClose={() => setPhoneClient(null)} />}
      {depPopup && (
        <DepositTooltip
          client={depPopup.client}
          x={depPopup.x}
          y={depPopup.y}
          onClose={()=>setDepPopup(null)}
        />
      )}

      {/* Email modal */}
      {emailClient && <EmailModal client={emailClient} onClose={() => setEmailClient(null)} />}

      {/* Ticket #137 — inline "saved" confirmation; the client stays put in the list (no refresh) */}
      {savedToast && (
        <div style={{ position:'fixed', bottom:74, left:'50%', transform:'translateX(-50%)', zIndex:100000,
          display:'flex', alignItems:'center', gap:10, background:'#222833', border:`1px solid ${actionColors[savedToast.type]||'#00e5a0'}66`,
          borderRadius:10, padding:'10px 16px', boxShadow:'0 8px 28px rgba(0,0,0,0.55)' }}>
          <span style={{ width:22, height:22, borderRadius:'50%', background:`${actionColors[savedToast.type]||'#00e5a0'}22`,
            color:actionColors[savedToast.type]||'#00e5a0', display:'flex', alignItems:'center', justifyContent:'center', fontSize:13, fontWeight:700 }}>✓</span>
          <div style={{ fontSize:12.5, color:'#e6e9ef' }}>
            <b style={{ color:actionColors[savedToast.type]||'#00e5a0' }}>{t(actionLabels[savedToast.type] || 'Saved')}</b> · {savedToast.name}
            <span style={{ color:'#8a93a3' }}> {t('— stays in your list')}</span>
          </div>
        </div>
      )}

      {badgeHover && (() => {
        const c = badgeHover.client;
        const when = c.recapture_form_date ? new Date(c.recapture_form_date).toLocaleString('en-GB') : null;
        const left = Math.min(badgeHover.x + 12, window.innerWidth - 290);
        const top  = Math.min(badgeHover.y + 14, window.innerHeight - 150);
        return (
          <div style={{ position:'fixed', left, top, zIndex:99999, background:'#2c333e', border:'1px solid #626d80', borderRadius:10, padding:13, width:270, boxShadow:'0 8px 32px rgba(0,0,0,0.6)', pointerEvents:'none' }}>
            <div style={{ fontSize:12, fontWeight:600, color: badgeHover.kind==='recapture'?'#ff4d4d':'#00aaff', marginBottom:6 }}>
              {badgeHover.kind==='recapture' ? '♻ '+t('Recapture') : '📥 '+t('Came from a Meta lead')}
            </div>
            <div style={{ fontSize:11, color:'#ccc', marginBottom:4 }}>📋 {t('Filled the Meta ad form on:')}</div>
            <div style={{ fontSize:13, fontWeight:600, color:'#00e5a0' }}>{when || t('date not available')}</div>
            <div style={{ fontSize:10, color:'#666', marginTop:7, lineHeight:1.5 }}>
              {badgeHover.kind==='recapture'
                ? t('Was already a client and submitted the ad form again — re-engaged.')
                : t('This client originally came in as a Meta lead.')}
            </div>
          </div>
        );
      })()}

      {/* Action modal */}
      {actionMenu && (
        <div style={{ position: 'fixed', inset: 0, zIndex: 9999, background: 'rgba(0,0,0,0.65)' }} onClick={() => { setActionMenu(null); setActionStep('menu'); }}>
          <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%,-50%)', background: '#2c333e', border: '1px solid #626d80', borderRadius: 14, padding: 22, width: 300 }}
            onClick={e => e.stopPropagation()}>
            {actionStep === 'menu' && (
              <>
                <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 3 }}>{actionMenu.name}</div>
                <div style={{ fontSize: 11, color: '#555', marginBottom: 16 }}>{t('Select outcome')}</div>
                {[
                  { key:'connected_done', icon:'✓', label:t('Connected & Done'),   sub:t('Resurfaces in 14 days'), color:'#00e5a0' },
                  { key:'no_answer',      icon:'✗', label:t('No Answer'),           sub:t('Resurfaces in 2 hours'), color:'#ffaa00' },
                  { key:'call_later',     icon:'⏰', label:t('Call Later'),          sub:t('Set custom follow-up'),  color:'#0066ff' },
                  { key:'not_interested', icon:'⊘', label:t('Not Interested'),      sub:t('Pass to manager / hide'),color:'#ff4d4d' },
                  { key:'transfer_out',   icon:'⇄', label:t('Transfer out of my data'), sub:t('Goes up to your manager'), color:'#cc88ff' },
                ].filter(a => a.key !== 'transfer_out' || localStorage.getItem('canReassign') === '1').map(a => (
                  <div key={a.key} onClick={() => { setActionType(a.key); setActionStep('form'); }}
                    style={{ display:'flex', alignItems:'center', gap:10, padding:'10px 12px', borderRadius:8, cursor:'pointer', marginBottom:6, border:'1px solid #4f596b' }}
                    onMouseEnter={e=>(e.currentTarget.style.background='#373f4d')}
                    onMouseLeave={e=>(e.currentTarget.style.background='transparent')}>
                    <div style={{ width:30, height:30, borderRadius:8, background:`${a.color}22`, color:a.color, display:'flex', alignItems:'center', justifyContent:'center', fontSize:14 }}>{a.icon}</div>
                    <div>
                      <div style={{ fontSize:13, fontWeight:500, color:a.color }}>{a.label}</div>
                      <div style={{ fontSize:11, color:'#555' }}>{a.sub}</div>
                    </div>
                  </div>
                ))}
                {/* ADMIN ONLY — block / delete the whole account */}
                {['super_admin','admin','director'].includes((localStorage.getItem('userRole')||'').toLowerCase()) && (
                  <>
                    <div style={{ borderTop:'1px solid #4f596b', margin:'8px 0 6px' }} />
                    <div onClick={async () => {
                      if (!window.confirm(`${t('Block')} ${actionMenu.name}? ${t("They won't be able to log into the client portal and their trading accounts will be frozen.")}`)) return;
                      try { await apiPost(`/clients/${actionMenu.login}/block`, { blocked: true }); setActionMenu(null); fetchClients(); }
                      catch (e:any) { alert(e?.detail || t('Could not block.')); }
                    }} style={{ display:'flex', alignItems:'center', gap:10, padding:'10px 12px', borderRadius:8, cursor:'pointer', marginBottom:6, border:'1px solid #4f596b' }}
                      onMouseEnter={e=>(e.currentTarget.style.background='#3a2530')} onMouseLeave={e=>(e.currentTarget.style.background='transparent')}>
                      <div style={{ width:30, height:30, borderRadius:8, background:'#ffaa0022', color:'#ffaa00', display:'flex', alignItems:'center', justifyContent:'center', fontSize:14 }}>⛔</div>
                      <div><div style={{ fontSize:13, fontWeight:500, color:'#ffaa00' }}>{t('Block account')}</div><div style={{ fontSize:11, color:'#555' }}>{t('Freeze login & trading (reversible)')}</div></div>
                    </div>
                    <div onClick={async () => {
                      if (!window.confirm(`${t('PERMANENTLY DELETE')} ${actionMenu.name} ${t('and ALL their data (accounts, trades, transactions)? This cannot be undone.')}`)) return;
                      if (!window.confirm(t('Are you absolutely sure? This is irreversible.'))) return;
                      try { await apiDelete(`/clients/${actionMenu.login}`); setActionMenu(null); fetchClients(); }
                      catch (e:any) { alert(e?.detail || t('Could not delete.')); }
                    }} style={{ display:'flex', alignItems:'center', gap:10, padding:'10px 12px', borderRadius:8, cursor:'pointer', marginBottom:6, border:'1px solid #4f596b' }}
                      onMouseEnter={e=>(e.currentTarget.style.background='#3a2530')} onMouseLeave={e=>(e.currentTarget.style.background='transparent')}>
                      <div style={{ width:30, height:30, borderRadius:8, background:'#ff4d4d22', color:'#ff4d4d', display:'flex', alignItems:'center', justifyContent:'center', fontSize:14 }}>🗑</div>
                      <div><div style={{ fontSize:13, fontWeight:500, color:'#ff4d4d' }}>{t('Delete account')}</div><div style={{ fontSize:11, color:'#555' }}>{t('Permanent — removes all data')}</div></div>
                    </div>
                  </>
                )}
              </>
            )}
            {actionStep === 'form' && (
              <>
                <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:16 }}>
                  <div onClick={() => setActionStep('menu')} style={{ cursor:'pointer', color:'#888', fontSize:12 }}>← {t('Back')}</div>
                  <div style={{ fontSize:13, fontWeight:500, color:actionColors[actionType] }}>{t(actionLabels[actionType])}</div>
                </div>
                {actionType === 'call_later' && (
                  <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:8, marginBottom:12 }}>
                    <div>
                      <div style={{ fontSize:11, color:'#555', marginBottom:4 }}>{t('Days')}</div>
                      <input type="number" value={callLaterDays} onChange={e=>setCallLaterDays(parseInt(e.target.value)||0)} min={0}
                        style={{ width:'100%', padding:'8px 10px', background:'#373f4d', border:'1px solid #626d80', borderRadius:8, color:'#fff', fontSize:13, outline:'none', boxSizing:'border-box' as any }} />
                    </div>
                    <div>
                      <div style={{ fontSize:11, color:'#555', marginBottom:4 }}>{t('Hours')}</div>
                      <input type="number" value={callLaterHours} onChange={e=>setCallLaterHours(parseInt(e.target.value)||0)} min={0} max={23}
                        style={{ width:'100%', padding:'8px 10px', background:'#373f4d', border:'1px solid #626d80', borderRadius:8, color:'#fff', fontSize:13, outline:'none', boxSizing:'border-box' as any }} />
                    </div>
                  </div>
                )}
                {actionType === 'not_interested' && (
                  <label style={{ display:'flex', alignItems:'center', gap:8, cursor:'pointer', fontSize:13, color:'#888', marginBottom:12 }}>
                    <input type="checkbox" checked={passToManager} onChange={e=>setPassToManager(e.target.checked)} />
                    {t('Pass to line manager')}
                  </label>
                )}
                {actionType === 'transfer_out' && (
                  <div style={{ fontSize:12, color:'#cc88ff', background:'rgba(204,136,255,0.08)', border:'1px solid rgba(204,136,255,0.25)', borderRadius:8, padding:'9px 11px', marginBottom:12 }}>
                    {t('This removes the client from your list and sends them up to your manager to reassign. Add the reason below.')}
                  </div>
                )}
                <div style={{ marginBottom:14 }}>
                  <div style={{ fontSize:11, color:'#555', marginBottom:4 }}>{t('Note (optional)')}</div>
                  <textarea value={actionNote} onChange={e=>setActionNote(e.target.value)} placeholder={t('Add a note...')} rows={3}
                    style={{ width:'100%', padding:'8px 10px', background:'#373f4d', border:'1px solid #626d80', borderRadius:8, color:'#fff', fontSize:12, outline:'none', resize:'none' as any, boxSizing:'border-box' as any }} />
                </div>
                <button onClick={saveAction} disabled={saving}
                  style={{ width:'100%', padding:11, background:actionColors[actionType], border:'none', borderRadius:8, color:'#fff', fontWeight:700, cursor:'pointer', fontSize:13 }}>
                  {saving ? '...' : t('Save')}
                </button>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}


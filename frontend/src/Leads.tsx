import React, { useState, useEffect, useCallback, useRef } from 'react';
import { apiGet, apiPost, apiPatch, openIbProfile } from './api';
import NetworkBadge from './NetworkBadge';
import { PhoneModal, EmailModal } from './ContactModals';
import KYCPanel from './KYCPanel';
import { DialerLauncher } from './PowerDialer';
import { AgentCell } from './AgentCell';
import { CT, Pager } from './crmTable';
import OwnDataToggle from './OwnDataToggle';
import { useColumnPicker, ColumnGear } from './ColumnPicker';
import { useT } from './adminI18n';

// Leads list columns (fixed order) — shared by the header, the colgroup and the ⚙ column picker.
const LEAD_COLS = ['Lead','Phone','Country','Campaign','Source','Reg date','Last comment','Stage','Training status','Agent','IB','KYC','Network','Score','Actions'];
const LEAD_COL_W: Record<string, number> = { Lead:190, Phone:96, Country:72, Campaign:80, Source:80, 'Reg date':94, 'Last comment':140, Stage:142, 'Training status':116, Agent:112, IB:72, KYC:60, Network:56, Score:52, Actions:76 };
// Training-need levels sales can pick on a lead (drives the Training board).
const TRAIN_LEVELS = [ {v:'', l:'—'}, {v:'beginner', l:'Beginner'}, {v:'needs_improvement', l:'Needs improvement'}, {v:'intermediate', l:'Intermediate'}, {v:'advanced', l:'Advanced'} ];
const TRAIN_STAGE_LABEL: Record<string,string> = { requested:'Requested', under_training:'Under training', training_done:'Training done', first_patch_done:'First patch done', too_beginner:'Too beginner', trader_loses_alot:'Trader (loses a lot)' };
const TRAIN_STAGE_COLOR: Record<string,string> = { requested:'#38bdf8', under_training:'#E8B84B', training_done:'#00e5a0', first_patch_done:'#22c55e', too_beginner:'#ff8800', trader_loses_alot:'#ff4d4d' };

// Meta leads can have very long names — show only the first 3 words in the list.
const firstWords = (name: string, n = 2) =>
  (name || '').trim().split(/\s+/).filter(Boolean).slice(0, n).join(' ');

// STAGES (TradeSoft's pipeline, Jul 2026 — replaces the old status). Meta feedback is
// AUTOMATIC now (meta_auto_feed.py): verified→qualified, deposit→converted, good stage→
// qualified, bad stage→not_qualified, Bad Data→lost; No Answer waits for re-calls.
const STAGES = ['New Lead','Contacted','Demo Trading','Not Interested','No Answer','Ask - Welcome Bonus',
  'Unreachable','Contact Whatsapp','Bad Data','Won','Interested in Training','Under Training',
  'Training Completed','Archived'];
const STAGE_COLORS: Record<string,string> = {
  'New Lead':'#00aaff', 'Contacted':'#ffaa00', 'Demo Trading':'#38bdf8', 'Not Interested':'#ff6b6b',
  'No Answer':'#8b93a1', 'Ask - Welcome Bonus':'#ffc14d', 'Unreachable':'#ff8888',
  'Contact Whatsapp':'#25d366', 'Bad Data':'#ff4d4d', 'Won':'#00e5a0',
  'Interested in Training':'#a78bfa', 'Under Training':'#c4b5fd', 'Training Completed':'#34d399',
  'Archived':'#667',
};
// legacy status -> stage (for rows the backend hasn't migrated yet)
const LEGACY_STAGE: Record<string,string> = { new:'New Lead', contacted:'Contacted', callback:'Contacted',
  converted:'Won', dead:'Not Interested', no_answer:'No Answer', interested:'Interested in Training' };
const stageOf = (l:any) => l.stage || LEGACY_STAGE[l.status] || 'New Lead';
// kept for old references
const STATUS_COLORS: Record<string,string> = {
  new:        '#00aaff',
  contacted:  '#ffaa00',
  callback:   '#cc88ff',
  converted:  '#00e5a0',
  dead:       '#555',
  interested: '#ffee00',
};
const STATUS_LABELS: Record<string,string> = {
  new:'New', contacted:'Contacted', callback:'Callback',
  converted:'Converted', dead:'Dead', interested:'Interested',
};
const SOURCE_ICONS: Record<string,string> = {
  facebook:'📘', instagram:'📸', messenger:'💬', audience_network:'🌐',
  Facebook:'📘', Instagram:'📸', Google:'🔍', WhatsApp:'💬',
  TikTok:'🎵', manual:'✋', Email:'✉️', Referral:'🤝', Other:'🌐',
  mql5:'📈', sales_agent:'🧑‍💼', webinar:'🎥', affiliate:'🤝', direct:'➡️',
};

// Brand logos as inline SVG (real colors)
function SourceLogo({ source, size = 16 }: { source: string, size?: number }) {
  const raw = (source || '').toLowerCase();
  // our Meta lead-form sources are slugs like "meta_syria_form_..." — show the Facebook channel logo
  const s = raw.startsWith('meta') ? 'facebook' : raw;
  const wrap = (children: any) => (
    <span style={{ display:'inline-flex', width:size, height:size, alignItems:'center', justifyContent:'center' }}>{children}</span>
  );
  if (s === 'facebook') return wrap(
    <svg width={size} height={size} viewBox="0 0 24 24"><path fill="#1877F2" d="M24 12.07C24 5.4 18.63 0 12 0S0 5.4 0 12.07C0 18.1 4.39 23.1 10.13 24v-8.44H7.08v-3.49h3.05V9.41c0-3.02 1.79-4.69 4.53-4.69 1.31 0 2.68.24 2.68.24v2.97h-1.51c-1.49 0-1.96.93-1.96 1.89v2.25h3.33l-.53 3.49h-2.8V24C19.61 23.1 24 18.1 24 12.07z"/></svg>
  );
  if (s === 'instagram') return wrap(
    <svg width={size} height={size} viewBox="0 0 24 24"><defs><radialGradient id="ig" cx="0.3" cy="1" r="1"><stop offset="0" stopColor="#fdf497"/><stop offset="0.05" stopColor="#fdf497"/><stop offset="0.45" stopColor="#fd5949"/><stop offset="0.6" stopColor="#d6249f"/><stop offset="0.9" stopColor="#285AEB"/></radialGradient></defs><path fill="url(#ig)" d="M12 2.16c3.2 0 3.58.01 4.85.07 1.17.05 1.8.25 2.23.41.56.22.96.48 1.38.9.42.42.68.82.9 1.38.16.42.36 1.06.41 2.23.06 1.27.07 1.65.07 4.85s-.01 3.58-.07 4.85c-.05 1.17-.25 1.8-.41 2.23-.22.56-.48.96-.9 1.38-.42.42-.82.68-1.38.9-.42.16-1.06.36-2.23.41-1.27.06-1.65.07-4.85.07s-3.58-.01-4.85-.07c-1.17-.05-1.8-.25-2.23-.41a3.7 3.7 0 01-1.38-.9 3.7 3.7 0 01-.9-1.38c-.16-.42-.36-1.06-.41-2.23C2.17 15.58 2.16 15.2 2.16 12s.01-3.58.07-4.85c.05-1.17.25-1.8.41-2.23.22-.56.48-.96.9-1.38.42-.42.82-.68 1.38-.9.42-.16 1.06-.36 2.23-.41C8.42 2.17 8.8 2.16 12 2.16M12 0C8.74 0 8.33.01 7.05.07 5.78.13 4.9.33 4.14.63c-.79.31-1.46.72-2.13 1.38C1.35 2.68.94 3.35.63 4.14.33 4.9.13 5.78.07 7.05.01 8.33 0 8.74 0 12s.01 3.67.07 4.95c.06 1.27.26 2.15.56 2.91.31.79.72 1.46 1.38 2.13.67.66 1.34 1.07 2.13 1.38.76.3 1.64.5 2.91.56C8.33 23.99 8.74 24 12 24s3.67-.01 4.95-.07c1.27-.06 2.15-.26 2.91-.56.79-.31 1.46-.72 2.13-1.38.66-.67 1.07-1.34 1.38-2.13.3-.76.5-1.64.56-2.91.06-1.28.07-1.69.07-4.95s-.01-3.67-.07-4.95c-.06-1.27-.26-2.15-.56-2.91-.31-.79-.72-1.46-1.38-2.13C21.32 1.35 20.65.94 19.86.63 19.1.33 18.22.13 16.95.07 15.67.01 15.26 0 12 0z"/><path fill="url(#ig)" d="M12 5.84A6.16 6.16 0 1018.16 12 6.16 6.16 0 0012 5.84zM12 16a4 4 0 114-4 4 4 0 01-4 4z"/><circle fill="url(#ig)" cx="18.41" cy="5.59" r="1.44"/></svg>
  );
  if (s === 'messenger') return wrap(
    <svg width={size} height={size} viewBox="0 0 24 24"><path fill="#0084FF" d="M12 0C5.24 0 0 4.95 0 11.64c0 3.5 1.44 6.53 3.78 8.62.2.18.32.43.32.7l.07 2.14c.02.68.72 1.13 1.35.86l2.39-1.05c.21-.09.44-.11.66-.05 1.09.3 2.25.46 3.43.46 6.76 0 12-4.95 12-11.64S18.76 0 12 0z"/><path fill="#fff" d="M4.79 15.05l3.53-5.6a1.8 1.8 0 012.6-.48l2.81 2.1c.26.2.62.2.88.01l3.79-2.88c.51-.38 1.17.22.83.76l-3.53 5.6a1.8 1.8 0 01-2.6.48l-2.81-2.1a.66.66 0 00-.88-.01l-3.79 2.88c-.51.38-1.17-.22-.83-.76z"/></svg>
  );
  if (s === 'audience_network') return wrap(
    <svg width={size} height={size} viewBox="0 0 24 24"><path fill="#0081FB" d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8z"/><path fill="#0081FB" d="M12 6a6 6 0 100 12 6 6 0 000-12zm0 10a4 4 0 110-8 4 4 0 010 8z"/></svg>
  );
  if (s === 'google') return wrap(
    <svg width={size} height={size} viewBox="0 0 24 24"><path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"/><path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84A11 11 0 0012 23z"/><path fill="#FBBC05" d="M5.84 14.1a6.6 6.6 0 010-4.22V7.04H2.18a11 11 0 000 9.9l3.66-2.84z"/><path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1a11 11 0 00-9.82 6.04l3.66 2.84C6.71 7.31 9.14 5.38 12 5.38z"/></svg>
  );
  if (s === 'whatsapp') return wrap(
    <svg width={size} height={size} viewBox="0 0 24 24"><path fill="#25D366" d="M.06 24l1.68-6.13A11.86 11.86 0 01.16 11.9C.16 5.34 5.5 0 12.06 0a11.82 11.82 0 018.42 3.49 11.82 11.82 0 013.48 8.42c0 6.56-5.34 11.9-11.9 11.9a11.9 11.9 0 01-5.7-1.45L.06 24zM6.6 20.13l.36.21a9.88 9.88 0 005.04 1.38 9.9 9.9 0 009.9-9.9 9.88 9.88 0 00-2.9-7A9.82 9.82 0 0012.06 2a9.9 9.9 0 00-9.9 9.9c0 1.9.54 3.75 1.56 5.35l.24.38-1 3.64 3.64-1.14z"/><path fill="#fff" d="M9.07 6.92c-.23-.5-.46-.51-.67-.52l-.57-.01c-.2 0-.52.07-.79.37-.27.3-1.04 1.02-1.04 2.48s1.06 2.88 1.21 3.08c.15.2 2.06 3.3 5.09 4.5 2.52 1 3.03.8 3.58.75.55-.05 1.77-.72 2.02-1.42.25-.7.25-1.3.17-1.42-.07-.12-.27-.2-.57-.35-.3-.15-1.77-.87-2.04-.97-.27-.1-.47-.15-.67.15-.2.3-.77.97-.94 1.17-.17.2-.35.22-.64.07-.3-.15-1.26-.46-2.4-1.48-.89-.79-1.49-1.77-1.66-2.07-.17-.3-.02-.46.13-.61.13-.13.3-.35.45-.52.15-.17.2-.3.3-.5.1-.2.05-.37-.02-.52-.07-.15-.66-1.62-.9-2.21z"/></svg>
  );
  // fallback emoji
  return wrap(<span style={{ fontSize: size-2 }}>{SOURCE_ICONS[s] || SOURCE_ICONS[source] || '🌐'}</span>);
}
// Meta CRM feedback stages (sent back to Meta to optimize audience)
const META_STAGES: Record<string,{label:string,color:string}> = {
  qualified:     { label:'Qualified',     color:'#00e5a0' },
  converted:     { label:'Converted',     color:'#00aaff' },
  not_qualified: { label:'Not Qualified', color:'#ff8800' },
  lost:          { label:'Lost',          color:'#ff4d4d' },
};

// ── connection intelligence (shared look with Clients page) ──
const L_REASON_ICON: Record<string,string> = { cid:'📱',mqid:'📱',email:'✉️',phone:'📞',family:'👪',ip:'🌐',payment:'💳',ib:'🤝',city:'📍' };
function lConfColor(p:number){ return p>=90?'#ff4d4d':p>=70?'#ffaa00':p>=50?'#ffd400':'#00aaff'; }
function LConnRow({ c }:{ c:any }){
  const t = useT();
  const col = lConfColor(c.confidence);
  const [open, setOpen] = useState(false);
  const reasons = c.reasons || [];
  return (
    <div style={{ background:'#2c333e', border:'1px solid '+(open?col+'88':'#4f596b'), borderRadius:10, marginBottom:6 }}>
      <div onClick={()=>setOpen(o=>!o)} style={{ display:'flex', alignItems:'center', gap:10, padding:'8px 10px', cursor:'pointer' }}>
        <div style={{ width:46, textAlign:'center', flexShrink:0 }}>
          <div style={{ fontSize:15, fontWeight:800, color:col }}>{c.confidence}%</div>
          <div style={{ fontSize:9, color:'#667' }}>{c.score10}/10</div>
        </div>
        <div style={{ flex:1, minWidth:0 }}>
          <div style={{ fontSize:12.5, color:'#e6e9ef', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
            {(c.name||'').split(/\s+/).slice(0,2).join(' ')} {c.kind==='lead'
              ? <span style={{ fontSize:9, color:'#00aaff', border:'1px solid #00aaff55', borderRadius:4, padding:'0 4px' }}>{t('LEAD')}</span>
              : <span style={{ fontSize:9, color:'#00e5a0', border:'1px solid #00e5a055', borderRadius:4, padding:'0 4px' }}>{t('CLIENT')}</span>}
          </div>
          <div style={{ fontSize:10, color:'#667', fontFamily:'monospace' }}>{c.login?('#'+c.login):('lead #'+c.id)}{c.city?(' · '+c.city):''}{c.ib_name?(' · '+c.ib_name):''}</div>
        </div>
        <div style={{ display:'flex', gap:4, flexWrap:'wrap', justifyContent:'flex-end', maxWidth:220 }}>
          {reasons.map((r:any,ri:number)=>(
            <span key={ri} title={`${r.label}: ${r.value}`} style={{ fontSize:9.5, padding:'2px 6px', borderRadius:99, background:'#373f4d', color:'#bcc3cf' }}>{L_REASON_ICON[r.type]||'·'} {r.type}</span>
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
                <span style={{ width:18, textAlign:'center', flexShrink:0 }}>{L_REASON_ICON[r.type]||'·'}</span>
                <span style={{ color:'#9aa3b2', width:130, flexShrink:0 }}>{r.label||r.type}</span>
                <span style={{ color:'#e6e9ef', fontFamily:'monospace', wordBreak:'break-all', flex:1 }}>{r.value||'—'}</span>
                <span style={{ fontSize:9, color:'#00e5a0', border:'1px solid #00e5a033', borderRadius:4, padding:'0 5px', flexShrink:0 }}>{t('match')}</span>
              </div>
            ))}
          {c.login && (
            <div style={{ marginTop:8 }}>
              <span onClick={(e)=>{ e.stopPropagation();
                  window.dispatchEvent(new CustomEvent('navigate',{detail:{page:'clients', search:String(c.login), openProfile:c.login}})); }}
                style={{ fontSize:10.5, color:'#00aaff', cursor:'pointer', textDecoration:'underline' }}>{t('Open')} #{c.login}{t("'s profile →")}</span>
            </div>
          )}
        </div>
      )}
    </div>
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
function Field({ label, value, accent, onClick, mono, node, last }: any){
  const isEmpty = !node && (value===undefined || value===null || value==='' || value==='—');
  return (
    <div style={{ display:'flex', alignItems:'baseline', justifyContent:'space-between', gap:14, padding:'7px 0', borderBottom: last?'none':'1px solid #333b46' }}>
      <span style={{ fontSize:11.5, color:'#8b93a1', flexShrink:0, whiteSpace:'nowrap' }}>{label}</span>
      {node ? <span style={{ textAlign:'right', minWidth:0 }}>{node}</span> : (
        <span onClick={onClick}
          style={{ fontSize:12.5, fontWeight:600, textAlign:'right', overflowWrap:'anywhere', wordBreak:'break-word', minWidth:0,
            color: onClick ? '#38bdf8' : isEmpty ? '#5a6472' : (accent||'#eef1f6'),
            cursor: onClick?'pointer':'default', fontFamily: mono?'monospace':'inherit' }}>{isEmpty?'—':value}</span>
      )}
    </div>
  );
}

function LeadProfile({ lead: leadProp, onClose, onUpdate, agents }: any) {
  const t = useT();
  const [lead, setLead] = useState<any>(leadProp);
  const [tab, setTab] = useState('details');
  const [verifying, setVerifying] = useState(false);
  const [note, setNote] = useState('');
  const [status, setStatus] = useState(leadProp.status);
  const [saving, setSaving] = useState(false);
  const notesFeedRef = useRef<HTMLDivElement>(null);   // notes feed — auto-scroll to bottom
  const [metaStage, setMetaStage] = useState(leadProp.meta_stage || '');
  const [metaSending, setMetaSending] = useState(false);
  const [metaDetails, setMetaDetails] = useState<any>(null);
  const [conns, setConns] = useState<any>(null);
  const [tradingAccts, setTradingAccts] = useState<any[]|null>(null);  // verified lead's trading account(s)
  const [editContact, setEditContact] = useState(false);   // #90 edit email/phone/password
  // Editing a lead's identity/contact info is ADMIN-TEAM ONLY (boss directive Jul 21, #241 —
  // sales/retention at ANY level request changes from Admin/Nuha). Mirrors backend
  // rbac.may_edit_lead_info; the backend still enforces.
  const canEditLeadInfo = ['super_admin','admin','director']
    .includes((localStorage.getItem('userRole') || '').toLowerCase());
  const [phoneContact, setPhoneContact] = useState<any>(null);   // in-profile call / WhatsApp
  // #242 — edit/delete OWN note lines within 60 min (parity with client comments)
  const [editingNote, setEditingNote] = useState<string|null>(null);   // the original line being edited
  const [editNoteText, setEditNoteText] = useState('');
  const myName = (localStorage.getItem('userName') || '').trim();
  const NOTE_EDIT_MS = 60 * 60 * 1000;
  const parseNoteLine = (ln: string) => {
    const m = ln.match(/^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\]\s*(.+?):\s([\s\S]*)$/);
    return m ? { ts: m[1], author: m[2].trim(), text: m[3] } : null;
  };
  const canEditNote = (ln: string) => {
    const p = parseNoteLine(ln);
    if (!p || !myName || p.author !== myName) return false;
    const t0 = new Date(p.ts.replace(' ', 'T') + ':00Z').getTime();   // stored in UTC
    return !isNaN(t0) && (Date.now() - t0) < NOTE_EDIT_MS;
  };
  const saveNoteEdit = async (original: string, newText: string) => {
    try {
      const r: any = await apiPost(`/leads/${lead.id}/note-edit`, { original, note: newText });
      setLead((prev: any) => ({ ...prev, notes: r.notes }));
      onUpdate && onUpdate({ id: lead.id, notes: r.notes });
      setEditingNote(null); setEditNoteText('');
    } catch (e: any) { alert(e?.message || t('Could not save note — please try again')); }
  };
  const [emailContact, setEmailContact] = useState<any>(null);   // in-profile email templates

  // Recapture identity: for a re-captured lead prefer the VERIFIED name on the existing record.
  const isRecap = String(lead.match_badge||'').startsWith('recapture') && lead.matched_login > 0;
  const displayName = (isRecap && lead.matched_name) ? lead.matched_name : (lead.full_name || 'Unknown');
  const contactCard = { name: displayName, phone: lead.phone, email: lead.email };
  const fmtD = (d:any) => d ? new Date(d).toLocaleDateString('en-GB') : null;

  // Load Meta details (custom questions, source, etc)
  useEffect(() => {
    apiGet(`/meta/lead/${leadProp.id}/details`).then(setMetaDetails).catch(()=>{});
    setConns(null);
    apiGet(`/network/connections?lead_id=${leadProp.id}`).then(setConns).catch(()=>{});
    setTradingAccts(null);
    apiGet(`/leads/${leadProp.id}/trading-accounts`)
      .then((d:any)=>setTradingAccts(d?.trading_accounts || []))
      .catch(()=>setTradingAccts([]));
  }, [leadProp.id]);

  const sendMetaStage = async (stage: string) => {
    setMetaSending(true);
    setMetaStage(stage);
    try {
      const res = await apiPost(`/meta/lead/${lead.id}/stage`, { status: stage });
      setLead({...lead, status: stage, meta_stage: res.meta_event});
    } catch(e) { alert(t('Failed to send to Meta')); }
    setMetaSending(false);
  };

  const save = async (updates: any) => {
    setSaving(true);
    try {
      // apiPatch REJECTS on 4xx/5xx — so we only reflect the change AFTER the backend confirms.
      await apiPatch(`/leads/${lead.id}`, updates);
      setLead({...lead, ...updates});
      if (updates.stage !== undefined) setStatus(updates.stage);
      // push the confirmed change to the OUTER leads table immediately (no need to close first)
      if (onUpdate) onUpdate(lead.id, updates);
    } catch(e:any) {
      alert(t('Could not save — ') + (e?.message || t('please try again')));
    }
    setSaving(false);
  };

  const logCall = async () => {
    if (!note.trim()) return;
    setSaving(true);
    try {
      const r:any = await apiPost(`/leads/${lead.id}/call`, { note });
      if (r && r.detail) { alert(t('Could not save note: ') + r.detail); }
      else {
        // reflect the saved note (formatted with timestamp + agent) so a reload matches
        const saved = (r && r.note) ? r.note : note;
        const nAtt = (lead.call_attempts||0)+1;
        setLead({...lead, call_attempts: nAtt, notes: (lead.notes? lead.notes+'\n' : '')+saved });
        // keep the list row's call count fresh without a full list reload (#171)
        if (onUpdate) onUpdate(lead.id, { call_attempts: nAtt });
        setNote('');
      }
    } catch(e:any) { alert(t('Could not save note — please try again') + (e?.message? ': '+e.message : '')); }
    setSaving(false);
  };
  // #293: newest note is now at the TOP — keep it in view by scrolling the feed to the top
  useEffect(() => {
    if (notesFeedRef.current) notesFeedRef.current.scrollTop = 0;
  }, [lead.notes]);

  return (
    <div style={{ position:'fixed', inset:0, zIndex:500, background:'var(--bg-main,#20252f)', color:'#e6e9ef', display:'flex', flexDirection:'column' }}>
      {/* Header */}
      <div style={{ display:'flex', alignItems:'center', gap:12, padding:'14px 20px', borderBottom:'1px solid #3a434f', background:'linear-gradient(180deg,#333b47,#2a313b)', boxShadow:'0 4px 18px rgba(0,0,0,0.25)', flexShrink:0, zIndex:10 }}>
        <button onClick={onClose} style={{ background:'none', border:'1px solid #626d80', borderRadius:7, color:'#888', cursor:'pointer', padding:'5px 12px', fontSize:12 }}>← {t('Back')}</button>
        <div style={{ width:42, height:42, borderRadius:12, background: lead.is_verified?'linear-gradient(135deg,#00e5a0,#00b37e)':'linear-gradient(135deg,#5b6cff,#9966ff)', display:'flex', alignItems:'center', justifyContent:'center', fontWeight:800, fontSize:18, color:'#0b0f14', flexShrink:0 }}>{(displayName||'?')[0]?.toUpperCase()}</div>
        <div style={{ flex:1, minWidth:0 }}>
          <div style={{ fontSize:16, fontWeight:700, display:'flex', alignItems:'center', gap:8, flexWrap:'wrap' }}>
            <span>{displayName}</span>
            {lead.is_verified && <span title={t('Verified account')} style={{ fontSize:11 }}>✅</span>}
            {lead.customer_no && <span style={{ fontSize:11, fontFamily:'monospace', color:'#9966ff', background:'rgba(153,102,255,0.12)', padding:'2px 7px', borderRadius:6 }}>{lead.customer_no}</span>}
            {isRecap && <span style={{ fontSize:9.5, fontWeight:700, padding:'2px 7px', borderRadius:99, background:'rgba(248,80,10,0.14)', color:'#FF6A1A', border:'1px solid #F8500A' }}>♻ {t('Re-captured')}</span>}
          </div>
          <div style={{ fontSize:11, color:'#8b93a1', display:'flex', alignItems:'center', gap:5, flexWrap:'wrap' }}>
            <span>{lead.phone} · {lead.country} {lead.city} ·</span>
            <SourceLogo source={lead.source} size={14} />
            <span>{lead.source}</span>
          </div>
        </div>
        {/* Quick contact actions — call / WhatsApp / email straight from the profile */}
        {lead.phone && <button onClick={()=>setPhoneContact(contactCard)} title={t('Call / WhatsApp')} style={{ display:'flex', alignItems:'center', gap:5, padding:'6px 12px', borderRadius:8, border:'1px solid rgba(0,229,160,0.4)', background:'rgba(0,229,160,0.1)', color:'#00e5a0', cursor:'pointer', fontSize:12, fontWeight:600 }}>📞 {t('Call')}</button>}
        {lead.email && <button onClick={()=>setEmailContact(contactCard)} title={t('Send email')} style={{ display:'flex', alignItems:'center', gap:5, padding:'6px 12px', borderRadius:8, border:'1px solid rgba(77,159,255,0.4)', background:'rgba(77,159,255,0.1)', color:'#4d9fff', cursor:'pointer', fontSize:12, fontWeight:600 }}>✉️ {t('Email')}</button>}
        {/* #294: send an email-verification request straight from the new CRM (no more old CRM) */}
        {lead.email && <button onClick={async()=>{ try { const r:any = await apiPost(`/leads/${lead.id}/send-verification-email`, {}); alert(r?.ok ? (t('Verification email sent to ')+(r.sent_to||lead.email)) : (r?.error || t('Could not send the email.'))); } catch { alert(t('Could not send the email.')); } }} title={t('Send an email-verification request to this lead')} style={{ display:'flex', alignItems:'center', gap:5, padding:'6px 12px', borderRadius:8, border:'1px solid rgba(232,184,75,0.45)', background:'rgba(232,184,75,0.12)', color:'#E8B84B', cursor:'pointer', fontSize:12, fontWeight:600 }}>🔐 {t('Verify email')}</button>}
        {(lead.converted_login > 0 || lead.matched_login > 0) && (
          <button onClick={async () => {
            const lg = lead.converted_login || lead.matched_login;
            try {
              const res: any = await apiPost(`/portal/impersonate/${lg}`, {});
              if (res?.token) window.open(`/portal/?imp=${encodeURIComponent(res.token)}`, '_blank');
              else alert(res?.error || t('No client portal account for this lead.'));
            } catch { alert(t('Could not open the client view.')); }
          }} title={t("Open the client portal as this lead's account (read-only preview)")} style={{ display:'flex', alignItems:'center', gap:5, padding:'6px 12px', borderRadius:8, border:'1px solid rgba(232,184,75,0.4)', background:'rgba(232,184,75,0.1)', color:'#E8B84B', cursor:'pointer', fontSize:12, fontWeight:600 }}>👁 {t('View as client')}</button>
        )}
        <span style={{ fontSize:11, padding:'3px 10px', borderRadius:99, background:(STAGE_COLORS[stageOf(lead)]||'#555')+'22', color:STAGE_COLORS[stageOf(lead)]||'#888', fontWeight:700 }}>
          {t(stageOf(lead))}
        </span>
      </div>

      {/* Re-capture summary — prominent + highlighted so the desk instantly sees this person
          already exists, with first registration and last re-capture dates. */}
      {isRecap && (
        <div style={{ flexShrink:0, margin:'12px 20px 0', padding:'12px 16px', borderRadius:12, background:'linear-gradient(135deg, rgba(248,80,10,0.16), rgba(255,106,26,0.05))', border:'1px solid rgba(248,80,10,0.45)', display:'flex', alignItems:'center', gap:18, flexWrap:'wrap' }}>
          <div style={{ display:'flex', alignItems:'center', gap:10 }}>
            <span style={{ fontSize:22, lineHeight:1 }}>♻</span>
            <div>
              <div style={{ fontSize:13, fontWeight:800, color:'#FF6A1A' }}>{t('Re-captured lead')}</div>
              <div style={{ fontSize:10.5, color:'#9aa3b2' }}>{t('This person already exists in our system')}</div>
            </div>
          </div>
          <div style={{ display:'flex', gap:12, flexWrap:'wrap', marginLeft:'auto' }}>
            <div style={{ background:'rgba(0,229,160,0.08)', border:'1px solid rgba(0,229,160,0.25)', borderRadius:10, padding:'7px 14px', minWidth:118 }}>
              <div style={{ fontSize:9, color:'#8792a6', textTransform:'uppercase', letterSpacing:.6, fontWeight:700, marginBottom:2 }}>{t('First registration')}</div>
              <div style={{ fontSize:15, fontWeight:800, color:'#00e5a0' }}>{fmtD(lead.matched_reg_date) || '—'}</div>
            </div>
            <div style={{ background:'rgba(255,209,102,0.08)', border:'1px solid rgba(255,209,102,0.28)', borderRadius:10, padding:'7px 14px', minWidth:118 }}>
              <div style={{ fontSize:9, color:'#8792a6', textTransform:'uppercase', letterSpacing:.6, fontWeight:700, marginBottom:2 }}>{t('Last re-capture')}</div>
              <div style={{ fontSize:15, fontWeight:800, color:'#ffd166' }}>{fmtD(lead.meta_created||lead.created_at) || '—'}</div>
            </div>
            {lead.full_name && lead.matched_name && lead.full_name!==lead.matched_name && (
              <div style={{ background:'rgba(196,181,253,0.08)', border:'1px solid rgba(196,181,253,0.28)', borderRadius:10, padding:'7px 14px', minWidth:118 }}>
                <div style={{ fontSize:9, color:'#8792a6', textTransform:'uppercase', letterSpacing:.6, fontWeight:700, marginBottom:2 }}>{t('Name on new ad')}</div>
                <div style={{ fontSize:13, fontWeight:700, color:'#c4b5fd', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap', maxWidth:160 }}>{firstWords(lead.full_name)}</div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Tabs (pill style) */}
      <div style={{ display:'flex', gap:6, padding:'10px 20px', borderBottom:'1px solid #313945', background:'#2c333e', flexShrink:0 }}>
        {['details','verification'].map(tb => (
          <button key={tb} onClick={() => setTab(tb)}
            style={{ padding:'7px 16px', borderRadius:9, fontWeight:tab===tb?700:500, textTransform:'capitalize', cursor:'pointer', fontSize:12.5, fontFamily:'inherit',
              color: tab===tb?'#0b0f14':'#9aa3b2',
              background: tab===tb?'linear-gradient(135deg,#00e5a0,#00c48f)':'#262c36',
              border:'1px solid '+(tab===tb?'transparent':'#353d49'),
              boxShadow: tab===tb?'0 3px 12px rgba(0,229,160,0.28)':'none', transition:'all 0.15s' }}>
            {t(tb)}
          </button>
        ))}
      </div>

      {/* Two-pane body: LEFT 70% workspace · RIGHT 30% (connections over notes) */}
      <div style={{ flex:1, minHeight:0, display:'grid', gridTemplateColumns:'minmax(0,7fr) minmax(0,3fr)', gap:16, padding:16, overflow:'hidden' }}>

        {/* LEFT 70% */}
        <div style={{ minWidth:0, overflowY:'auto', paddingRight:4 }}>
        {tab === 'details' && (
          <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit,minmax(320px,1fr))', gap:14, alignItems:'start' }}>

            {/* LEFT COLUMN */}
            <div style={{ display:'flex', flexDirection:'column', gap:14, minWidth:0 }}>
            {/* Lead details (personal + status merged) */}
            <InfoCard icon="👤" title={t('Lead details')} accent="#38bdf8"
              action={canEditLeadInfo ? <button onClick={()=>setEditContact(true)} style={{ padding:'4px 10px', background:'rgba(56,189,248,0.1)', border:'1px solid rgba(56,189,248,0.4)', borderRadius:7, color:'#38bdf8', cursor:'pointer', fontSize:11, fontFamily:'inherit', fontWeight:600 }}>✎ {t('Edit')}</button> : undefined}>
              <Field label={t('Customer ID')} value={lead.customer_no} mono accent="#c4b5fd" />
              <Field label={t('Name')} value={displayName} accent={isRecap && lead.matched_name ? '#00e5a0' : undefined} />
              {isRecap && lead.full_name && lead.matched_name && lead.full_name!==lead.matched_name && <Field label={t('Ad-form name')} value={lead.full_name} accent="#c4b5fd" />}
              <Field label={t('Phone')} value={lead.phone} />
              <Field label={t('Email')} value={lead.email} />
              <Field label={t('Date of birth')} value={lead.date_of_birth} />
              <Field label={t('Country')} value={lead.country} />
              <Field label={t('City')} value={lead.city} />
              <Field label={t('Language')} value={lead.language} />
              <Field label={t('Portal password')} value={lead.has_password ? t('•••••• (set)') : t('— (not set)')} accent={lead.has_password?'#00e5a0':undefined} last />

              {/* Status & assignment merged in */}
              <div style={{ marginTop:12, paddingTop:12, borderTop:'1px solid #333b46' }}>
                <div style={{ fontSize:11, color:'#8b93a1', margin:'0 0 6px' }}>{t('Stage')}</div>
                <select value={STAGES.includes(status) ? status : stageOf(lead)} disabled={saving} onChange={e => save({stage: e.target.value})}
                  style={{ width:'100%', padding:'9px', background:'#373f4d', border:'1px solid #4f596b', borderRadius:8, color:'#e0e0e0', fontSize:13, marginBottom:12, fontFamily:'inherit', opacity:saving?0.6:1 }}>
                  {STAGES.map(s => <option key={s} value={s}>{t(s)}</option>)}
                </select>
                <div style={{ fontSize:11, color:'#8b93a1', marginBottom:6 }}>{t('Assigned agent')}</div>
                {/* Only admins & Rahaf may change the sales agent; everyone else sees it read-only. */}
                {localStorage.getItem('canReassign') === '1' ? (
                <select value={lead.assigned_agent_id||''} onChange={e => save({assigned_agent_id: e.target.value || null})}
                  style={{ width:'100%', padding:'9px', background:'#373f4d', border:'1px solid #4f596b', borderRadius:8, color:'#e0e0e0', fontSize:13, fontFamily:'inherit' }}>
                  <option value="">{t('Unassigned')}</option>
                  {agents.map((a:any) => <option key={a.id} value={a.id}>{a.full_name}</option>)}
                </select>
                ) : (
                  <div style={{ width:'100%', padding:'9px', background:'#2a303a', border:'1px solid #4f596b', borderRadius:8, color:'#9fb0c0', fontSize:13 }}>
                    {lead.agent_name || t('Unassigned')}
                  </div>
                )}

                {/* Training needs — sales pick a level; this sends the lead to the Training team's board */}
                <div style={{ fontSize:11, color:'#8b93a1', margin:'12px 0 6px', display:'flex', alignItems:'center', gap:6 }}>🎓 {t('Training needs')}</div>
                <select value={lead.training_need||''} onChange={e => save({training_need: e.target.value})} disabled={saving}
                  style={{ width:'100%', padding:'9px', background: lead.training_need?'rgba(232,184,75,0.10)':'#373f4d', border:`1px solid ${lead.training_need?'#E8B84B':'#4f596b'}`, borderRadius:8, color: lead.training_need?'#E8B84B':'#e0e0e0', fontSize:13, fontFamily:'inherit' }}>
                  {TRAIN_LEVELS.map(x=><option key={x.v} value={x.v} style={{background:'#373f4d',color:'#e0e0e0'}}>{t(x.l)}</option>)}
                </select>
                {lead.training_stage && <div style={{ fontSize:11, color:'#8792a6', marginTop:6 }}>{t('On the training board')}: <b style={{color:TRAIN_STAGE_COLOR[lead.training_stage]||'#aaa'}}>{t(TRAIN_STAGE_LABEL[lead.training_stage]||lead.training_stage)}</b></div>}
              </div>
            </InfoCard>

            {/* Trading accounts — verified/matched leads own trading login(s) */}
            <InfoCard icon="💹" title={t('Trading accounts')} accent="#00e5a0">
              {tradingAccts === null ? (
                <div style={{ fontSize:12, color:'#5a6472', textAlign:'center', padding:'12px 0' }}>{t('Loading…')}</div>
              ) : tradingAccts.length === 0 ? (
                <div style={{ fontSize:12, color:'#5a6472', textAlign:'center', padding:'12px 0' }}>{t('No trading accounts yet')}</div>
              ) : (
                <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
                  {tradingAccts.map((a:any, i:number) => (
                    <div key={a.login ?? i}
                      onClick={()=>window.dispatchEvent(new CustomEvent('navigate',{detail:{page:'clients', search:String(a.login), openProfile:a.login}}))}
                      title={t("Open this account's profile")}
                      style={{ display:'flex', alignItems:'center', justifyContent:'space-between', gap:10, padding:'9px 11px', background:'var(--bg-input,#373f4d)', border:'1px solid var(--border,#3a434f)', borderRadius:10, cursor:'pointer' }}>
                      <div style={{ minWidth:0 }}>
                        <div style={{ fontSize:14, fontWeight:800, fontFamily:'monospace', color:'var(--accent,#00e5a0)' }}>#{a.login}</div>
                        <div style={{ fontSize:10.5, color:'#8b93a1', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
                          <span style={{ fontWeight:600 }}>{a.platform || 'MT5'}</span>{a.group_name ? ' · '+a.group_name : ''}
                        </div>
                      </div>
                      <div style={{ fontSize:13, fontWeight:700, color:'var(--text,#e6e9ef)', flexShrink:0, fontFamily:'monospace' }}>
                        ${Number(a.balance||0).toLocaleString('en-GB',{minimumFractionDigits:2, maximumFractionDigits:2})}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </InfoCard>
            </div>{/* end LEFT column */}

            {/* RIGHT COLUMN */}
            <div style={{ display:'flex', flexDirection:'column', gap:14, minWidth:0 }}>
            {/* Source & campaign */}
            <InfoCard icon={<SourceLogo source={lead.meta_platform||lead.source} size={15} />} title={t('Source & campaign')} accent="#fbbf24">
              <Field label={t('Source')} node={<span style={{ display:'flex', alignItems:'center', gap:6, color:'#eef1f6', fontWeight:600, fontSize:12.5, justifyContent:'flex-end' }}><SourceLogo source={lead.meta_platform||lead.source} size={14} />{metaDetails?.meta_platform || lead.meta_platform || lead.source || '—'}</span>} />
              <Field label={t('Publisher')} value={metaDetails?.meta_publisher_platform} />
              <Field label={t('Placement')} value={metaDetails?.meta_platform_position} />
              <Field label={t('Campaign')} value={metaDetails?.campaign_name || lead.campaign_name} />
              <Field label={t('Ad set')} value={metaDetails?.adset_name} />
              <Field label={t('Ad')} value={metaDetails?.ad_name || lead.ad_name} />
              <Field label={t('Created')} value={lead.created_at ? new Date(lead.created_at).toLocaleString('en-GB') : '—'} />
              <Field label={t('Meta lead ID')} value={metaDetails?.meta_lead_id || lead.meta_lead_id} mono />
            </InfoCard>

            {/* Form answers */}
            <InfoCard icon="📝" title={`${t('Form answers')}${metaDetails?.custom_questions?.length ? ` (${metaDetails.custom_questions.length})` : ''}`} accent="#00e5a0">
              {metaDetails?.custom_questions?.length ? (
                metaDetails.custom_questions.map((qa:any, i:number) => (
                  <div key={i} style={{ padding:'8px 0', borderBottom:'1px solid #333b46' }}>
                    <div style={{ fontSize:11, color:'#8b93a1', marginBottom:4, direction:'auto' as any }}>{qa.q}</div>
                    <div style={{ fontSize:13, color:'#00e5a0', fontWeight:600, direction:'auto' as any }}>{qa.a || '—'}</div>
                  </div>
                ))
              ) : (
                <div style={{ fontSize:12, color:'#5a6472', textAlign:'center', padding:'16px 0' }}>
                  {t('No custom questions for this lead')}
                </div>
              )}
            </InfoCard>
            </div>{/* end RIGHT column */}
          </div>
        )}
        {tab === 'verification' && <KYCPanel leadId={lead.id} />}
        </div>{/* end LEFT 70% */}

        {/* RIGHT 30% — Connections (top 40%) over Notes / call log (bottom 60%) */}
        <div style={{ minWidth:0, display:'grid', gridTemplateRows:'minmax(0,2fr) minmax(0,3fr)', gap:16, overflow:'hidden' }}>

          {/* TOP 40% — Connections */}
          <div style={{ minHeight:0, display:'flex', flexDirection:'column', background:'linear-gradient(160deg,#2c333e,#262c35)', border:'1px solid #3a434f', borderRadius:16, overflow:'hidden', boxShadow:'0 6px 22px rgba(0,0,0,0.28)' }}>
            <div style={{ display:'flex', alignItems:'center', gap:8, padding:'12px 16px', borderBottom:'1px solid #373f4d', flexShrink:0 }}>
              <span style={{ fontSize:13, fontWeight:700 }}>🕸️ {t('Connections')}</span>
              {(conns?.connections?.length>0) && <span style={{ fontSize:10, color:'#8a93a3', background:'#373f4d', padding:'2px 7px', borderRadius:99 }}>{conns.connections.length}</span>}
            </div>
            <div style={{ flex:1, overflowY:'auto', padding:'10px 12px' }}>
              <div style={{ fontSize:10.5, color:'#667', marginBottom:8, lineHeight:1.5 }}>{t('Existing clients/leads this person is linked to — by phone, email, city or payment. The % / x-of-10 is our confidence.')}</div>
              {!conns ? <div style={{ textAlign:'center', color:'#556', padding:20, fontSize:12 }}>{t('Loading connections…')}</div>
                : (conns.connections||[]).length === 0
                  ? <div style={{ textAlign:'center', color:'#556', padding:20, fontSize:12 }}>{t('No connections found — a fresh, unlinked lead.')}</div>
                  : (conns.connections||[]).map((c:any,i:number) => <LConnRow key={i} c={c} />)}
            </div>
          </div>

          {/* BOTTOM 60% — Notes / call log centre */}
          <div style={{ minHeight:0, display:'flex', flexDirection:'column', background:'linear-gradient(160deg,#2c333e,#262c35)', border:'1px solid #3a434f', borderRadius:16, overflow:'hidden', boxShadow:'0 6px 22px rgba(0,0,0,0.28)' }}>
            <div style={{ display:'flex', alignItems:'center', gap:8, padding:'12px 16px', borderBottom:'1px solid #373f4d', flexShrink:0 }}>
              <span style={{ fontSize:13, fontWeight:700 }}>📞 {t('Notes & call log')}</span>
              {(lead.call_attempts>0) && <span style={{ fontSize:10, color:'#8a93a3', background:'#373f4d', padding:'2px 7px', borderRadius:99 }}>{lead.call_attempts} {lead.call_attempts>1?t('calls'):t('call')}</span>}
            </div>
            {/* feed — #293: NEWEST at the top, oldest below */}
            <div ref={notesFeedRef} style={{ flex:1, overflowY:'auto', padding:'12px 14px', display:'flex', flexDirection:'column', gap:8 }}>
              {(() => {
                const entries = String(lead.notes||'').split('\n').map(s=>s.trim()).filter(Boolean).reverse();
                return entries.length===0
                  ? <div style={{ color:'#556', fontSize:12, textAlign:'center', padding:'24px 0' }}>{t('No notes yet.')}<br/>{t('Log the first call below.')}</div>
                  : entries.map((n:string,i:number)=>(
                    <div key={i} style={{ background:'#262c36', border:'1px solid #373f4d', borderRadius:10, padding:'9px 12px', fontSize:12.5, color:'#c7ccd6', lineHeight:1.5, whiteSpace:'pre-wrap', wordBreak:'break-word' }}>
                      {editingNote === n ? (
                        <div>
                          <textarea value={editNoteText} onChange={e=>setEditNoteText(e.target.value)} rows={2} autoFocus
                            style={{ width:'100%', padding:'8px 10px', background:'#373f4d', border:'1px solid #4f596b', borderRadius:8, color:'#fff', fontSize:12.5, outline:'none', resize:'vertical', boxSizing:'border-box' as any, fontFamily:'inherit' }} />
                          <div style={{ display:'flex', gap:8, marginTop:6 }}>
                            <button onClick={()=>saveNoteEdit(n, editNoteText)} disabled={!editNoteText.trim()} style={{ padding:'5px 12px', background:'#00e5a0', border:'none', borderRadius:7, color:'#20252f', fontWeight:700, fontSize:11.5, cursor:'pointer' }}>{t('Save')}</button>
                            <button onClick={()=>{ setEditingNote(null); setEditNoteText(''); }} style={{ padding:'5px 12px', background:'#373f4d', border:'1px solid #4f596b', borderRadius:7, color:'#c7ccd6', fontWeight:600, fontSize:11.5, cursor:'pointer' }}>{t('Cancel')}</button>
                          </div>
                        </div>
                      ) : (
                        <>
                          {n}
                          {canEditNote(n) && (
                            <div style={{ display:'flex', gap:12, marginTop:6, alignItems:'center' }}>
                              <button onClick={()=>{ setEditingNote(n); setEditNoteText(parseNoteLine(n)?.text || ''); }} style={{ background:'none', border:'none', color:'#7cc4ff', fontSize:11, cursor:'pointer', padding:0 }}>✏️ {t('Edit')}</button>
                              <button onClick={()=>{ if (window.confirm(t('Delete this note?'))) saveNoteEdit(n, ''); }} style={{ background:'none', border:'none', color:'#ff7a7a', fontSize:11, cursor:'pointer', padding:0 }}>🗑 {t('Delete')}</button>
                              <span style={{ color:'#5a6472', fontSize:10 }}>{t('editable for 60 min')}</span>
                            </div>
                          )}
                        </>
                      )}
                    </div>
                  ));
              })()}
            </div>
            {/* composer */}
            <div style={{ borderTop:'1px solid #373f4d', padding:'10px 12px', background:'#262c36', flexShrink:0 }}>
              <textarea value={note} onChange={e => setNote(e.target.value)} placeholder={t('Log a call or add a note… (Enter to save, Shift+Enter = new line)')} rows={2}
                onKeyDown={e=>{ if(e.key==='Enter' && !e.shiftKey && !e.ctrlKey && !e.metaKey){ e.preventDefault(); if(note.trim()&&!saving) logCall(); } }}
                style={{ width:'100%', padding:'8px 10px', background:'#373f4d', border:'1px solid #4f596b', borderRadius:8, color:'#e0e0e0', fontSize:12.5, outline:'none', resize:'none', fontFamily:'inherit', boxSizing:'border-box' as any }} />
              <button onClick={logCall} disabled={saving || !note.trim()}
                style={{ marginTop:8, width:'100%', padding:'8px 18px', background:note.trim()?'#00e5a0':'#4f596b', border:'none', borderRadius:8, color:note.trim()?'#000':'#667', fontWeight:700, cursor:note.trim()?'pointer':'default', fontSize:12, fontFamily:'inherit' }}>
                {saving ? '…' : t('Log call / note')}
              </button>
            </div>
          </div>
        </div>{/* end RIGHT 30% */}

      </div>{/* end two-pane body */}

      {editContact && (
        <EditContactModal
          lead={lead}
          onClose={()=>setEditContact(false)}
          onSaved={(u:any)=>{ setLead({...lead, ...u}); setEditContact(false); }}
        />
      )}
      {phoneContact && <PhoneModal contact={phoneContact} onClose={()=>setPhoneContact(null)} />}
      {emailContact && <EmailModal contact={emailContact} type="lead" onClose={()=>setEmailContact(null)} />}
    </div>
  );
}

// #90 (Nuha) — edit a lead's Email, Phone and Portal password.
function EditContactModal({ lead, onClose, onSaved }: any) {
  const t = useT();
  const [email, setEmail]       = useState(lead.email || '');
  const [phone, setPhone]       = useState(lead.phone || '');
  const [dob, setDob]           = useState(lead.date_of_birth || '');  // YYYY-MM-DD (#90)
  const [password, setPassword] = useState('');
  const [showPw, setShowPw]     = useState(false);
  const [saving, setSaving]     = useState(false);
  const [err, setErr]           = useState('');

  const emailValid = !email || /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email);
  const phoneValid = !phone || phone.replace(/\D/g,'').length >= 6;
  const dobValid   = !dob || /^\d{4}-\d{2}-\d{2}$/.test(dob);
  const pwValid    = !password || password.length >= 6;
  const canSave    = emailValid && phoneValid && dobValid && pwValid && !saving;

  const save = async () => {
    setErr('');
    if (!canSave) return;
    setSaving(true);
    try {
      const body: any = { email: email.trim(), phone: phone.trim(), date_of_birth: dob.trim() };
      if (password) body.password = password;
      const res = await apiPatch(`/leads/${lead.id}/contact`, body);
      if (res?.error) { setErr(res.error); setSaving(false); return; }
      onSaved({
        email: email.trim(),
        phone: phone.trim(),
        date_of_birth: dob.trim(),
        has_password: lead.has_password || !!password,
      });
    } catch(e) { setErr(t('Failed to save')); }
    setSaving(false);
  };

  const fieldStyle: any = (ok:boolean) => ({
    width:'100%', padding:'9px 11px', background:'#373f4d',
    border:`1px solid ${ok?'#626d80':'#ff4d4d'}`, borderRadius:8, color:'#e0e0e0',
    fontSize:13, outline:'none', boxSizing:'border-box', fontFamily:'inherit',
  });

  return (
    <div style={{ position:'fixed', inset:0, zIndex:9999, background:'rgba(0,0,0,0.7)', display:'flex', alignItems:'center', justifyContent:'center' }} onClick={onClose}>
      <div style={{ background:'#2c333e', borderRadius:14, padding:24, width:420, border:'1px solid #626d80' }} onClick={e=>e.stopPropagation()}>
        <div style={{ fontSize:15, fontWeight:700, marginBottom:4 }}>{t('Edit contact')}</div>
        <div style={{ fontSize:11, color:'#666', marginBottom:16 }}>{lead.full_name || `${t('Lead')} #${lead.id}`}</div>

        <div style={{ fontSize:11, color:'#888', marginBottom:5 }}>{t('Email')}</div>
        <input value={email} onChange={e=>setEmail(e.target.value)} type="email" placeholder="name@example.com" style={fieldStyle(emailValid)} />
        {!emailValid && <div style={{ fontSize:10, color:'#ff4d4d', marginTop:3 }}>{t('Enter a valid email (or leave blank to clear)')}</div>}

        <div style={{ fontSize:11, color:'#888', margin:'14px 0 5px' }}>{t('Phone')}</div>
        <input value={phone} onChange={e=>setPhone(e.target.value)} type="tel" placeholder="+9715xxxxxxx" style={fieldStyle(phoneValid)} />
        {!phoneValid && <div style={{ fontSize:10, color:'#ff4d4d', marginTop:3 }}>{t('Phone looks too short')}</div>}

        <div style={{ fontSize:11, color:'#888', margin:'14px 0 5px' }}>{t('Date of birth')}</div>
        <input value={dob} onChange={e=>setDob(e.target.value)} type="date" max={new Date().toISOString().slice(0,10)} style={fieldStyle(dobValid)} />
        {!dobValid && <div style={{ fontSize:10, color:'#ff4d4d', marginTop:3 }}>{t('Use the date picker (YYYY-MM-DD)')}</div>}

        <div style={{ fontSize:11, color:'#888', margin:'14px 0 5px', display:'flex', justifyContent:'space-between' }}>
          <span>{t('Portal password')} {lead.has_password ? t('(set — leave blank to keep)') : t('(optional)')}</span>
          <span onClick={()=>setShowPw(s=>!s)} style={{ cursor:'pointer', color:'#00aaff' }}>{showPw?t('Hide'):t('Show')}</span>
        </div>
        <input value={password} onChange={e=>setPassword(e.target.value)} type={showPw?'text':'password'} placeholder={t('Leave blank to keep current')} style={fieldStyle(pwValid)} autoComplete="new-password" />
        {!pwValid && <div style={{ fontSize:10, color:'#ff4d4d', marginTop:3 }}>{t('Password must be at least 6 characters')}</div>}

        {err && <div style={{ fontSize:11, color:'#ff4d4d', marginTop:12 }}>{err}</div>}

        <div style={{ display:'flex', gap:8, justifyContent:'flex-end', marginTop:20 }}>
          <button onClick={onClose} style={{ padding:'8px 16px', background:'#373f4d', border:'1px solid #626d80', borderRadius:8, color:'#888', cursor:'pointer', fontSize:13, fontFamily:'inherit' }}>{t('Cancel')}</button>
          <button onClick={save} disabled={!canSave}
            style={{ padding:'8px 20px', background:canSave?'#00e5a0':'#4f596b', border:'none', borderRadius:8, color:canSave?'#000':'#666', fontWeight:700, cursor:canSave?'pointer':'default', fontSize:13, fontFamily:'inherit' }}>
            {saving ? t('Saving...') : t('Save changes')}
          </button>
        </div>
      </div>
    </div>
  );
}


const actionColors: any = { connected_done:'#00e5a0', no_answer:'#ffaa00', call_later:'#0066ff', not_interested:'#ff4d4d' };
const actionLabels: any = { connected_done:'Connected & Done', no_answer:'No Answer', call_later:'Call Later', not_interested:'Not Interested' };
const API_BASE = '/api';

function LeadActions({ lead, onUpdate, onView, showView=true }: any) {
  const t = useT();
  const [open, setOpen]           = React.useState(false);
  const [step, setStep]           = React.useState<'menu'|'form'>('menu');
  const [actionType, setActionType] = React.useState('');
  const [actionNote, setActionNote] = React.useState('');
  const [callLaterDays, setCallLaterDays] = React.useState(0);
  const [callLaterHours, setCallLaterHours] = React.useState(2);
  const [passToManager, setPassToManager] = React.useState(false);
  const [saving, setSaving]       = React.useState(false);

  const close = () => { setOpen(false); setStep('menu'); setActionNote(''); setActionType(''); };

  const saveAction = async () => {
    setSaving(true);
    try {
      const token = localStorage.getItem('token');
      // Map the call outcome to a STAGE. Meta feeding is automatic from the stage:
      //  Not Interested -> stage 'Not Interested' -> auto-fed to Meta as not_qualified;
      //  No Answer -> stage 'No Answer' -> NOT fed (waits for re-calls);
      //  Connected & Done -> 'Contacted' -> auto-fed qualified.
      const stageMap: any = { connected_done:'Contacted', no_answer:'No Answer', not_interested:'Not Interested' };
      const legacyMap: any = { connected_done:'contacted', no_answer:'no_answer', call_later:'callback', not_interested:'dead' };

      // Save action + note via call endpoint
      await fetch(`${API_BASE}/leads/${lead.id}/call`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          note: `[${actionLabels[actionType]}] ${actionNote}`,
          call_later_days: callLaterDays,
          call_later_hours: callLaterHours,
        })
      });
      // Update stage (+legacy status for old filters); call_later keeps the current stage.
      const body: any = { status: legacyMap[actionType] || 'contacted' };
      if (stageMap[actionType]) body.stage = stageMap[actionType];
      await fetch(`${API_BASE}/leads/${lead.id}`, {
        method: 'PATCH',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      close();
      onUpdate();
    } catch(e) {}
    setSaving(false);
  };

  return (
    <>
      <div style={{ display:'flex', gap:4 }}>
        {showView && (
          <button onClick={onView}
            style={{ padding:'3px 8px', background:'rgba(0,229,160,0.1)', border:'1px solid rgba(0,229,160,0.3)', borderRadius:5, color:'#00e5a0', cursor:'pointer', fontSize:10 }}>
            {t('View')}
          </button>
        )}
        <button onClick={()=>setOpen(true)}
          style={{ padding:'3px 8px', background:'#373f4d', border:'1px solid #626d80', borderRadius:5, color:'#888', cursor:'pointer', fontSize:10 }}>
          {t('Action')} ▾
        </button>
      </div>

      {open && (
        <div style={{ position:'fixed', inset:0, zIndex:9999, background:'rgba(0,0,0,0.65)' }} onClick={close}>
          <div style={{ position:'absolute', top:'50%', left:'50%', transform:'translate(-50%,-50%)', background:'#2c333e', border:'1px solid #626d80', borderRadius:14, padding:22, width:300 }}
            onClick={e=>e.stopPropagation()}>
            {step === 'menu' && (
              <>
                <div style={{ fontSize:13, fontWeight:500, marginBottom:3 }}>{lead.full_name}</div>
                <div style={{ fontSize:11, color:'#555', marginBottom:16 }}>{t('Select outcome')}</div>
                {[
                  { key:'connected_done', icon:'✓', label:t('Connected & Done'),   sub:t('Resurfaces in 14 days'), color:'#00e5a0' },
                  { key:'no_answer',      icon:'✗', label:t('No Answer'),           sub:t('Resurfaces in 2 hours'), color:'#ffaa00' },
                  { key:'call_later',     icon:'⏰', label:t('Call Later'),          sub:t('Set custom follow-up'),  color:'#0066ff' },
                  { key:'not_interested', icon:'⊘', label:t('Not Interested'),      sub:t('Pass to manager / hide'),color:'#ff4d4d' },
                ].map(a => (
                  <div key={a.key} onClick={()=>{ setActionType(a.key); setStep('form'); }}
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
              </>
            )}
            {step === 'form' && (
              <>
                <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:16 }}>
                  <div onClick={()=>setStep('menu')} style={{ cursor:'pointer', color:'#888', fontSize:12 }}>← {t('Back')}</div>
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
    </>
  );
}

export default function Leads() {
  const t = useT();
  const [view, setView]             = useState<'leads'|'verified'>('leads');  // #95 sub-view
  const [leads, setLeads]           = useState<any[]>([]);
  const [total, setTotal]           = useState(0);
  const [kpis, setKpis]             = useState<any>({});
  const [page, setPage]             = useState(1);
  const [pageSize, setPageSize]     = useState(20);   // #58 selectable
  const [archiveView, setArchiveView] = useState<'active'|'archived'|'all'>('active'); // #57
  const [dateFrom, setDateFrom]     = useState('');   // #62
  const [dateTo, setDateTo]         = useState('');   // #62
  const [search, setSearch]         = useState('');
  const [showKpi, setShowKpi]       = useState(() => localStorage.getItem('kpi_hidden') !== '1');  // #4
  const [sort, setSort]             = useState('created_at');
  const [loading, setLoading]       = useState(false);
  const [networkHover, setNetworkHover] = useState<number|null>(null);
  const [verifiedOnly, setVerifiedOnly] = useState(false);   // #6 Verified-leads filter
  const [scoreHover, setScoreHover] = useState<any>(null);   // {lead, x, y} — fixed-positioned so it clears the KPI cards (#158)
  const [badgeHover, setBadgeHover] = useState<any>(null);
  const [selected, setSelected]     = useState<any>(null);
  // #286 — remember the list's scroll position while a profile is open (the profile REPLACES the
  // list, unmounting it) and restore it on return, so closing a lead lands you where you were.
  const listScrollRef = useRef<HTMLDivElement>(null);
  const savedScrollTop = useRef(0);
  const openLead = (l: any) => { savedScrollTop.current = listScrollRef.current?.scrollTop || 0; setSelected(l); };
  useEffect(() => {
    if (!selected) requestAnimationFrame(() => {
      if (listScrollRef.current) listScrollRef.current.scrollTop = savedScrollTop.current;
    });
  }, [selected]);
  const [showAdd, setShowAdd]       = useState(false);
  const [phoneContact, setPhoneContact] = useState<any>(null);
  const [emailContact, setEmailContact] = useState<any>(null);
  const [agents, setAgents]         = useState<any[]>([]);
  const [showFilters, setShowFilters] = useState(false);
  // Multi-select (ticket #39) — selected lead ids for bulk actions
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [bulkMenuOpen, setBulkMenuOpen] = useState(false);
  const clearSelection = () => { setSelectedIds([]); setBulkMenuOpen(false); };

  // jump-to-search from the global search page (navigate event → leads_search)
  useEffect(() => {
    const h = (e: any) => { const s = e.detail?.search; if (s != null) { setSearch(String(s)); setPage(1); } };
    window.addEventListener('leads_search', h);
    return () => window.removeEventListener('leads_search', h);
  }, []);
  // deep-link: ?lead=<id> → open that lead's profile directly (right-click open-in-tab)
  useEffect(() => {
    const h = (e: any) => {
      const id = e.detail?.id; if (!id) return;
      apiGet(`/leads?lead_id=${id}`).then((r: any) => {
        const l = (r?.leads || [])[0]; if (l) setSelected(l);
      }).catch(() => {});
    };
    window.addEventListener('leads_open', h);
    return () => window.removeEventListener('leads_open', h);
  }, []);
  // Per-TAB open-profile persistence: reopen this tab's lead on mount (so a refresh returns to the
  // same lead with a clean my1.tnfx.co URL), and keep sessionStorage in sync as it opens/closes.
  useEffect(() => {
    try {
      const saved = sessionStorage.getItem('crm_open_lead');
      if (saved) apiGet(`/leads?lead_id=${saved}`).then((r: any) => {
        const l = (r?.leads || [])[0]; if (l) setSelected(l);
      }).catch(() => {});
    } catch {}
  }, []);
  useEffect(() => {
    try {
      if (selected?.id) sessionStorage.setItem('crm_open_lead', String(selected.id));
      else sessionStorage.removeItem('crm_open_lead');
    } catch {}
  }, [selected]);
  const toggleSelect = (id: number) =>
    setSelectedIds(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);

  // Filters
  const [filterStatus,   setFilterStatus]   = useState('');
  const [filterSource,   setFilterSource]   = useState('');
  const [filterCountry,  setFilterCountry]  = useState('');
  const [filterCity,     setFilterCity]     = useState('');
  const [filterAgent,    setFilterAgent]    = useState('');
  const [filterIB,       setFilterIB]       = useState('');
  const [filterPlatform, setFilterPlatform] = useState('');
  const [filterVerified, setFilterVerified] = useState('');
  const [filterBadge,    setFilterBadge]    = useState('');
  const [period,         setPeriod]         = useState('all_time');
  const [showCustom,     setShowCustom]     = useState(false);   // reveal the custom date-range inputs
  // default to MY-data ONLY for team-leaders (who get the toggle to expand); everyone else (admins,
  // agents) has NO toggle, so defaulting own=true stranded them on an empty list (Jul 20 fix).
  const [own,            setOwn]            = useState(() => localStorage.getItem('isTeamLead') === '1');
  const colPick = useColumnPicker(LEAD_COLS, 'leads_cols_v2', { locked: ['Lead','Actions'], hideDefault: ['Training status'] });
  // hide de-selected columns by their (1-based) position — no change to the row markup.
  // #277: COLLAPSE hidden cells to zero-width IN PLACE (keep them in the grid) rather than
  // display:none. display:none removed the <th>/<td> from the table's column model while its
  // <col> stayed in the colgroup, so under table-layout:fixed the fixed widths landed on the
  // wrong columns and the visible headers overlapped. Zero-width-in-place keeps col↔cell 1:1.
  const _hiddenCss = LEAD_COLS.map((h,i)=>({h,n:i+1})).filter(x=>!colPick.V(x.h))
    .map(x=>`.leads-cols th:nth-child(${x.n}),.leads-cols td:nth-child(${x.n}){width:0 !important;max-width:0 !important;min-width:0 !important;padding-left:0 !important;padding-right:0 !important;border:0 !important;overflow:hidden !important;white-space:nowrap !important}.leads-cols th:nth-child(${x.n})>*,.leads-cols td:nth-child(${x.n})>*{display:none !important}.leads-cols col:nth-child(${x.n}){width:0 !important}`).join('');
  const [connected,      setConnected]      = useState(false);   // "Connected (7d)" tab — leads contacted this week

  const hasFilters = !![filterStatus,filterSource,filterCountry,filterCity,filterAgent,filterPlatform,filterVerified,filterBadge,filterIB,dateFrom,dateTo].filter(Boolean).length || period !== 'all_time';

  const clearFilters = () => { setFilterStatus(''); setFilterSource(''); setFilterCountry(''); setFilterCity(''); setFilterAgent(''); setFilterPlatform(''); setFilterVerified(''); setFilterBadge(''); setFilterIB(''); setDateFrom(''); setDateTo(''); setPeriod('all_time'); setPage(1); };

  // Archive / unarchive (ticket #57)
  const archiveLead = async (id: number, archived: boolean) => {
    try { await apiPost(`/leads/${id}/archive`, { archived }); load(); }
    catch { alert(t('Failed to update archive status')); }
  };
  const bulkArchive = async (archived: boolean) => {
    if (!selectedIds.length) return;
    try { await apiPost('/leads/archive', { ids: selectedIds, archived }); clearSelection(); load(); }
    catch { alert(t('Failed to archive selection')); }
  };
  // #63 — one-click: move every still-active "not interested" (dead) lead to the archive.
  const archiveNotInterested = async () => {
    if (!window.confirm(t('Archive all leads marked "Not interested"? They move to the Archived list and leave the main list clean.'))) return;
    try { const r:any = await apiPost('/leads/archive-not-interested', {}); alert(`${t('Archived')} ${r.count||0} ${t('"not interested" lead(s).')}`); load(); }
    catch { alert(t('Failed to archive not-interested leads')); }
  };

  useEffect(() => {
    // #276: use /assign/agents (sales + RETENTION + managers) instead of role=sales_agent, so
    // retention employees appear in the assign dropdown. Normalise name -> full_name for the UI.
    apiGet('/assign/agents')
      .then((d:any) => setAgents((d.agents || d.users || d || []).map((a:any) => ({ ...a, full_name: a.full_name || a.name }))))
      .catch(() => {});
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const p = new URLSearchParams({ page:String(page), page_size:String(pageSize), search, sort, period });
      if (filterStatus)   p.set('status',   filterStatus);
      if (filterSource)   p.set('source',   filterSource);
      if (filterCountry)  p.set('country',  filterCountry);
      if (filterCity)     p.set('city',     filterCity);
      if (filterAgent)    p.set('agent',    filterAgent);
      if (filterIB)       p.set('ib',       filterIB);
      if (filterPlatform) p.set('platform', filterPlatform);
      if (filterVerified) p.set('verified', filterVerified);
      if (filterBadge)    p.set('badge',    filterBadge);
      if (dateFrom)       p.set('date_from', dateFrom);
      if (dateTo)         p.set('date_to',   dateTo);
      if (verifiedOnly)   p.set('kyc', 'verified');
      p.set('archived', archiveView);
      if (own) p.set('own', '1');
      if (connected) p.set('connected', '1');
      const data = await apiGet(`/leads?${p}`);
      setLeads(data.leads || []);
      setTotal(data.total || 0);
      setKpis(data.kpis || {});
    } catch(e) { setLeads([]); }
    setLoading(false);
  }, [page, pageSize, search, sort, period, filterStatus, filterSource, filterCountry, filterCity, filterAgent, filterIB, filterPlatform, filterVerified, filterBadge, dateFrom, dateTo, archiveView, verifiedOnly, own, connected]);

  useEffect(() => { load(); }, [load]);

  // Drop any selected leads no longer in the current result set (page/filter change)
  useEffect(() => {
    const visible = new Set(leads.map((l: any) => l.id));
    setSelectedIds(prev => prev.filter(id => visible.has(id)));
  }, [leads]);

  const uniqueCountries = Array.from(new Set(leads.map((l:any) => l.country).filter(Boolean))).sort();
  const uniqueCities    = Array.from(new Set(leads.map((l:any) => l.city).filter(Boolean))).sort();
  const uniqueAgents    = Array.from(new Set(leads.map((l:any) => l.agent_name).filter(Boolean))).sort();

  if (selected) return <LeadProfile lead={selected}
    // #171: don't re-query the whole (166k-row) leads list on close — switching between leads was
    // slow because each "back" reloaded the list. The changed row is already updated in place via
    // onUpdate, so closing is now instant.
    onClose={() => { setSelected(null); }}
    onUpdate={(id:number, upd:any) => { setLeads(prev => prev.map((l:any) => l.id===id ? {...l, ...upd} : l)); setSelected((s:any)=> s && s.id===id ? {...s, ...upd} : s); }}
    agents={agents} />;

  if (view === 'verified') return <VerifiedAccounts view={view} setView={setView} />;

  return (
    <div style={{ height:'100%', display:'flex', flexDirection:'column', overflow:'hidden', minHeight:0 }}>

      {/* KPI bar */}
      <div style={{ background:'#262c36', borderBottom:'1px solid #373f4d', flexShrink:0 }}>
        {/* Period selector + custom date range (one row) */}
        <div style={{ display:'flex', alignItems:'center', gap:4, padding:'8px 14px 0', overflowX:'auto' }}>
          {[['all_time','All time'],['today','Today'],['yesterday','Yesterday'],['this_week','This week'],['last_week','Last week'],['this_month','This month'],['last_month','Last month'],['this_year','This year'],['last_year','Last year']].map(([k,l])=>{
            // a custom range OVERRIDES the preset — deselect the period buttons while it's active
            const sel = period===k && !(dateFrom||dateTo);
            return (
            <button key={k} onClick={()=>{ setPeriod(k); setDateFrom(''); setDateTo(''); setShowCustom(false); setPage(1); }}
              style={{ padding:'4px 12px', borderRadius:6, border:`1px solid ${sel?'#00e5a0':'var(--border2,#626d80)'}`, background:sel?'rgba(0,229,160,0.1)':'transparent', color:sel?'#00e5a0':'var(--text3,#555)', cursor:'pointer', fontSize:11, whiteSpace:'nowrap', fontFamily:'inherit' }}>
              {t(l)}
            </button>
          );})}
          {/* Custom range — reveals from/to date inputs that win over the preset */}
          {(() => { const custActive = showCustom || !!(dateFrom||dateTo); return (
            <button onClick={()=>setShowCustom(s=>!s)}
              style={{ padding:'4px 12px', borderRadius:6, border:`1px solid ${custActive?'#00e5a0':'var(--border2,#626d80)'}`, background:custActive?'rgba(0,229,160,0.1)':'transparent', color:custActive?'#00e5a0':'var(--text3,#555)', cursor:'pointer', fontSize:11, whiteSpace:'nowrap', fontFamily:'inherit' }}>
              {t('Custom')}
            </button>
          ); })()}
          {(showCustom || dateFrom || dateTo) && (<>
            <span style={{ width:1, height:18, background:'var(--border,#4f596b)', margin:'0 6px', flexShrink:0 }} />
            <input type="date" title={t('Custom range — from')} max={new Date(Date.now()+86400000).toISOString().slice(0,10)} value={dateFrom} onChange={e=>{ setDateFrom(e.target.value); setPage(1); }}
              style={{ padding:'4px 8px', background:'var(--bg-input,#373f4d)', border:'1px solid var(--border2,#626d80)', borderRadius:6, color:'var(--text,#e0e0e0)', fontSize:11, width:125, flexShrink:0, fontFamily:'inherit', colorScheme:'dark' as any }} />
            <span style={{ color:'var(--text3,#555)', flexShrink:0 }}>—</span>
            <input type="date" title={t('Custom range — to')} max={new Date(Date.now()+86400000).toISOString().slice(0,10)} value={dateTo} onChange={e=>{ setDateTo(e.target.value); setPage(1); }}
              style={{ padding:'4px 8px', background:'var(--bg-input,#373f4d)', border:'1px solid var(--border2,#626d80)', borderRadius:6, color:'var(--text,#e0e0e0)', fontSize:11, width:125, flexShrink:0, fontFamily:'inherit', colorScheme:'dark' as any }} />
            {(dateFrom || dateTo) && (
              <button onClick={()=>{ setDateFrom(''); setDateTo(''); setPage(1); }} title={t('Clear the custom date range')}
                style={{ padding:'4px 8px', borderRadius:6, border:'1px solid var(--border2,#626d80)', background:'transparent', color:'var(--text3,#888)', cursor:'pointer', fontSize:11, flexShrink:0, fontFamily:'inherit' }}>✕</button>
            )}
          </>)}
          <button onClick={() => { const n=!showKpi; setShowKpi(n); localStorage.setItem('kpi_hidden', n?'0':'1'); }}
            title={t('Show/hide the KPI cards')} style={{ marginLeft:'auto', padding:'4px 12px', borderRadius:6, border:'1px solid #626d80', background:'transparent', color:'#888', cursor:'pointer', fontSize:11, whiteSpace:'nowrap' }}>
            {showKpi ? `📊 ${t('Hide KPI')}` : `📊 ${t('Show KPI')}`}</button>
        </div>
        {/* KPI cards */}
        {showKpi && <div style={{ display:'grid', gridTemplateColumns:'repeat(5,1fr)', gap:6, padding:'8px 14px 10px' }}>
          {[
            { label:t('Total leads'),   value:(kpis.total||0).toLocaleString('en-GB'),     color:'#e0e0e0' },
            { label:`🔵 ${t('New')}`,        value:(kpis.new||0).toLocaleString('en-GB'),        color:'#00aaff' },
            { label:`🟠 ${t('Contacted')}`,  value:(kpis.contacted||0).toLocaleString('en-GB'), color:'#ffaa00' },
            { label:`🟣 ${t('Callback')}`,   value:(kpis.callback||0).toLocaleString('en-GB'),  color:'#cc88ff' },
            { label:`✅ ${t('Converted')}`,  value:(kpis.converted||0).toLocaleString('en-GB'), color:'#00e5a0' },
            { label:`💀 ${t('Dead')}`,       value:(kpis.dead||0).toLocaleString('en-GB'),      color:'#555' },
            { label:`📘 ${t('Facebook')}`,   value:(kpis.from_facebook||0).toLocaleString('en-GB'), color:'#1877f2' },
            { label:`📸 ${t('Instagram')}`,  value:(kpis.from_instagram||0).toLocaleString('en-GB'), color:'#e1306c' },
            { label:`🔍 ${t('Google')}`,     value:(kpis.from_google||0).toLocaleString('en-GB'),   color:'#ea4335' },
          ].map((k,i)=>(
            <div key={i} style={{ background:'#2c333e', border:'1px solid #373f4d', borderRadius:8, padding:'8px 12px' }}>
              <div style={{ fontSize:9, color:'#555', textTransform:'uppercase', letterSpacing:.5, marginBottom:3 }}>{k.label}</div>
              <div style={{ fontSize:18, fontWeight:700, color:k.color }}>{k.value}</div>
            </div>
          ))}
        </div>}
      </div>

      {/* Search + filters bar — ONE line (no wrap); scrolls sideways only if the window is very narrow.
          The ⚙ column picker is the last item so it always sits at the end of this single row.
          The scoped rule keeps every control at its natural width (only the search input flexes),
          so the row scrolls instead of squashing/wrapping the buttons. */}
      <style>{`.leads-toolbar > * { flex-shrink: 0; } .leads-toolbar > input { flex-shrink: 1; }`}</style>
      <div className="leads-toolbar" style={{ display:'flex', alignItems:'center', gap:8, padding:'8px 14px', background:'#2c333e', borderBottom:'1px solid #373f4d', flexShrink:0, flexWrap:'nowrap', overflowX:'auto' }}>
        <div style={{ fontWeight:600, fontSize:13, whiteSpace:'nowrap' }}>{t('Leads')}</div>
        <div style={{ fontSize:11, color:'#555' }}>{total.toLocaleString('en-GB')} {t('leads')}</div>
        <OwnDataToggle own={own} setOwn={(v:boolean)=>{ setOwn(v); setPage(1); }} section="leads" />
        <input value={search} onChange={e=>{ setSearch(e.target.value); setPage(1); }} placeholder={t('Search name, phone, email, country...')}
          style={{ flex:'1 1 140px', minWidth:120, padding:'6px 10px', background:'#373f4d', border:'1px solid #626d80', borderRadius:7, color:'#e0e0e0', fontSize:12, outline:'none' }} />
        {[{key:'created_at',label:'Newest'},{key:'score',label:'Priority'},{key:'network',label:'Network'},{key:'last_login',label:'Last login'}].map(s=>(
          <button key={s.key} onClick={()=>{setSort(s.key);setPage(1);}}
            style={{padding:'5px 10px',borderRadius:6,border:`1px solid ${sort===s.key?'#00e5a0':'#626d80'}`,background:sort===s.key?'rgba(0,229,160,0.1)':'transparent',color:sort===s.key?'#00e5a0':'#888',cursor:'pointer',fontSize:11,fontFamily:'inherit'}}>
            {t(s.label)}
          </button>
        ))}
        {/* Verified leads filter (#6) — beside Priority / Network */}
        <button onClick={()=>{ setVerifiedOnly(v=>!v); setPage(1); }}
          style={{padding:'5px 10px',borderRadius:6,border:`1px solid ${verifiedOnly?'#00e5a0':'#626d80'}`,background:verifiedOnly?'rgba(0,229,160,0.1)':'transparent',color:verifiedOnly?'#00e5a0':'#888',cursor:'pointer',fontSize:11,fontFamily:'inherit'}}>
          ✅ {t('Verified leads')}
        </button>
        {/* Connected (last 7d) tab — leads YOU contacted this week, newest contact first, with the comments */}
        <button onClick={()=>{ setConnected(v=>!v); setPage(1); }} title={t('Leads you connected with in the last 7 days, sorted by most recent — so contacted leads that dropped down the priority list stay easy to follow up')}
          style={{padding:'5px 10px',borderRadius:6,border:`1px solid ${connected?'#4d9fff':'#626d80'}`,background:connected?'rgba(77,159,255,0.14)':'transparent',color:connected?'#4d9fff':'#888',cursor:'pointer',fontSize:11,fontFamily:'inherit',fontWeight:connected?700:400}}>
          📞 {t('Connected (7d)')}
        </button>
        {/* Archive toggle — ONE button: default active; click to see archived, click again to return */}
        <button onClick={()=>{ setArchiveView(archiveView==='archived'?'active':'archived'); setPage(1); }} title={t('Show archived leads — click again to return to the active list')}
          style={{padding:'5px 10px',borderRadius:6,border:`1px solid ${archiveView==='archived'?'#ffaa00':'#626d80'}`,background:archiveView==='archived'?'rgba(255,170,0,0.12)':'transparent',color:archiveView==='archived'?'#ffaa00':'#888',cursor:'pointer',fontSize:11,fontFamily:'inherit',fontWeight:archiveView==='archived'?700:400}}>
          🗄 {t('Archived')}
        </button>
        <button onClick={()=>setShowFilters(!showFilters)}
          style={{ padding:'6px 12px', borderRadius:7, border:`1px solid ${showFilters||hasFilters?'#00e5a0':'#626d80'}`, background:showFilters||hasFilters?'rgba(0,229,160,0.08)':'transparent', color:showFilters||hasFilters?'#00e5a0':'#888', cursor:'pointer', fontSize:12, fontFamily:'inherit' }}>
          ⚙ {t('Filters')} {hasFilters?`(${[filterStatus,filterSource,filterCountry,filterCity,filterAgent,filterPlatform].filter(Boolean).length} ${t('active')})`:''}
        </button>
        {filterIB && (
          <span onClick={()=>{ setFilterIB(''); setPage(1); }} title={t('Remove IB filter')}
            style={{ padding:'5px 10px', borderRadius:99, border:'1px solid #00aaff', background:'rgba(0,170,255,0.12)', color:'#00aaff', cursor:'pointer', fontSize:11.5, whiteSpace:'nowrap' }}>
            🔗 {t('IB:')} {filterIB} ✕
          </span>
        )}
        {hasFilters && (
          <button onClick={clearFilters}
            style={{ padding:'6px 12px', borderRadius:7, border:'1px solid #ff4d4d', background:'rgba(255,77,77,0.1)', color:'#ff4d4d', cursor:'pointer', fontSize:12, fontFamily:'inherit' }}>
            ✕ {t('Clear filter')}
          </button>
        )}
        <DialerLauncher
          source="leads"
          fetchAllLogins={async () => {
            const _p = new URLSearchParams({ search, sort });
            const token = localStorage.getItem('token') || '';
            const data = await fetch(`/api/leads/logins-only?${_p}`,
              { headers: { Authorization: `Bearer ${token}` } }).then(r => r.json());
            return data.logins || [];
          }}
        />
        <button onClick={()=>setShowAdd(true)}
          style={{ padding:'6px 14px', borderRadius:7, border:'none', background:'#00e5a0', color:'#000', fontWeight:700, cursor:'pointer', fontSize:12, fontFamily:'inherit' }}>
          + {t('Add lead')}
        </button>
        {/* ⚙ column picker — sits right next to Add lead on the same row */}
        <ColumnGear picker={colPick} t={t} />
      </div>

      {/* Filter panel */}
      {showFilters && (
        <div style={{ padding:'10px 14px', background:'#262c36', borderBottom:'1px solid #373f4d', flexShrink:0, display:'flex', gap:8, flexWrap:'wrap', alignItems:'flex-end' }}>
          {[
            ['Stage', filterStatus, setFilterStatus, ['', ...STAGES], ['All', ...STAGES]],
            ['Source', filterSource, setFilterSource, ['','meta','facebook','instagram','google','MQL5','sales_agent','webinar','messenger','audience_network','WhatsApp','TikTok','manual','Email','Referral'], ['All','Meta (ads)','Facebook','Instagram','Google','MQL5','Sales agent','Webinar','Messenger','Meta Audience','WhatsApp','TikTok','Manual','Email','Referral']],
            ['Platform', filterPlatform, setFilterPlatform, ['','meta','google','manual'], ['All','Meta','Google','Manual']],
            ['Badge', filterBadge, setFilterBadge, ['','recapture','registered_no_deposit'], ['All','♻ Recapture','🔥 No Deposit']],
          ].map(([label, val, setter, opts, labels]: any) => (
            <div key={label}>
              <div style={{ fontSize:10, color:'#555', marginBottom:4, textTransform:'uppercase' }}>{t(label)}</div>
              <select value={val} onChange={e=>{ setter(e.target.value); setPage(1); }}
                style={{ padding:'5px 8px', background:'#373f4d', border:'1px solid #626d80', borderRadius:6, color:'#e0e0e0', fontSize:11 }}>
                {opts.map((o:string, i:number) => <option key={o} value={o}>{t(labels[i])}</option>)}
              </select>
            </div>
          ))}
          <div>
            <div style={{ fontSize:10, color:'#555', marginBottom:4, textTransform:'uppercase' }}>{t('Country')}</div>
            <select value={filterCountry} onChange={e=>{ setFilterCountry(e.target.value); setPage(1); }}
              style={{ padding:'5px 8px', background:'#373f4d', border:'1px solid #626d80', borderRadius:6, color:'#e0e0e0', fontSize:11 }}>
              <option value="">{t('All countries')}</option>
              {uniqueCountries.map((c:any) => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div>
            <div style={{ fontSize:10, color:'#555', marginBottom:4, textTransform:'uppercase' }}>{t('Agent')}</div>
            <select value={filterAgent} onChange={e=>{ setFilterAgent(e.target.value); setPage(1); }}
              style={{ padding:'5px 8px', background:'#373f4d', border:'1px solid #626d80', borderRadius:6, color:'#e0e0e0', fontSize:11 }}>
              <option value="">{t('All agents')}</option>
              {uniqueAgents.map((a:any) => <option key={a} value={a}>{a}</option>)}
            </select>
          </div>
          <div>
            <div style={{ fontSize:10, color:'#555', marginBottom:4, textTransform:'uppercase' }}>{t('Verification')}</div>
            <select value={filterVerified} onChange={e=>{ setFilterVerified(e.target.value); setPage(1); }}
              style={{ padding:'5px 8px', background:'#373f4d', border:'1px solid #626d80', borderRadius:6, color:'#e0e0e0', fontSize:11 }}>
              <option value="">{t('All')}</option>
              <option value="verified">✅ {t('Fully verified')}</option>
              <option value="phone_only">📞 {t('Phone verified')}</option>
              <option value="email_only">✉️ {t('Email verified')}</option>
              <option value="unverified">❌ {t('Unverified')}</option>
              <option value="repeated_ip">🌐 {t('Repeated IP')}</option>
              <option value="repeated_cid">📱 {t('Repeated CID')}</option>
              <option value="kyc_id">🪪 {t('ID uploaded')}</option>
              <option value="kyc_address">📄 {t('Address uploaded')}</option>
            </select>
          </div>
          {/* Date range on created_at (ticket #62) */}
          <div>
            <div style={{ fontSize:10, color:'#555', marginBottom:4, textTransform:'uppercase' }}>{t('Created from')}</div>
            <input type="date" max={new Date(Date.now()+86400000).toISOString().slice(0,10)} value={dateFrom} onChange={e=>{ setDateFrom(e.target.value); setPage(1); }}
              style={{ padding:'4px 8px', background:'#373f4d', border:'1px solid #626d80', borderRadius:6, color:'#e0e0e0', fontSize:11, colorScheme:'dark' as any }} />
          </div>
          <div>
            <div style={{ fontSize:10, color:'#555', marginBottom:4, textTransform:'uppercase' }}>{t('Created to')}</div>
            <input type="date" max={new Date(Date.now()+86400000).toISOString().slice(0,10)} value={dateTo} onChange={e=>{ setDateTo(e.target.value); setPage(1); }}
              style={{ padding:'4px 8px', background:'#373f4d', border:'1px solid #626d80', borderRadius:6, color:'#e0e0e0', fontSize:11, colorScheme:'dark' as any }} />
          </div>
        </div>
      )}

      {/* Bulk-action bar (ticket #39) — appears when ≥1 lead is selected */}
      {selectedIds.length > 0 && (
        <div style={{ display:'flex', alignItems:'center', gap:12, padding:'8px 14px', background:'rgba(0,229,160,0.08)', borderBottom:'1px solid #373f4d', flexShrink:0, position:'relative', zIndex:20 }}>
          <span style={{ fontSize:13, fontWeight:600, color:'#00e5a0' }}>{selectedIds.length} {t('selected')}</span>
          <div style={{ position:'relative' }}>
            <button onClick={()=>setBulkMenuOpen(o=>!o)}
              style={{ padding:'5px 14px', borderRadius:7, border:'1px solid #00e5a0', background:'rgba(0,229,160,0.12)', color:'#00e5a0', cursor:'pointer', fontSize:12, fontWeight:600, fontFamily:'inherit' }}>
              {t('Bulk actions')} ▾
            </button>
            {bulkMenuOpen && (
              <div style={{ position:'absolute', top:'110%', left:0, background:'#2c333e', border:'1px solid #626d80', borderRadius:8, padding:6, minWidth:210, zIndex:50, boxShadow:'0 8px 24px rgba(0,0,0,0.5)' }}>
                <div style={{ fontSize:10, color:'#555', padding:'4px 10px', textTransform:'uppercase', letterSpacing:.5 }}>{t('Starting point — wire up later')}</div>
                {[
                  { key:'export', label:`⬇ ${t('Export selected (CSV)')}` },
                  { key:'assign', label:`👤 ${t('Assign to agent…')}` },
                  { key:'status', label:`🏷 ${t('Set status…')}` },
                ].map(a => (
                  <div key={a.key}
                    onClick={() => {
                      if (a.key === 'export') {
                        const rows = leads.filter((l:any) => selectedIds.includes(l.id));
                        const header = ['id','full_name','phone','email','country','city','source','status'];
                        const csv = [header.join(','),
                          ...rows.map((l:any) => header.map(h => JSON.stringify((l as any)[h] ?? '')).join(','))].join('\n');
                        const url = URL.createObjectURL(new Blob([csv], { type:'text/csv' }));
                        const link = document.createElement('a');
                        link.href = url; link.download = `leads_selection_${Date.now()}.csv`; link.click();
                        URL.revokeObjectURL(url);
                        setBulkMenuOpen(false);
                      } else {
                        alert(`${t('Bulk')} "${a.label.replace(/^[^ ]+ /,'')}" ${t('for')} ${selectedIds.length} ${t('leads — coming soon.')}\n${t('Lead IDs:')} ${selectedIds.join(', ')}`);
                        setBulkMenuOpen(false);
                      }
                    }}
                    style={{ padding:'8px 10px', borderRadius:6, cursor:'pointer', fontSize:12, color:'#ccc' }}
                    onMouseEnter={e=>(e.currentTarget.style.background='#373f4d')}
                    onMouseLeave={e=>(e.currentTarget.style.background='transparent')}>
                    {a.label}
                  </div>
                ))}
              </div>
            )}
          </div>
          {/* (bulk archive buttons removed — each lead row has its own archive action) */}
          <button onClick={clearSelection}
            style={{ padding:'5px 12px', borderRadius:7, border:'1px solid #626d80', background:'transparent', color:'#888', cursor:'pointer', fontSize:12, fontFamily:'inherit' }}>
            ✕ {t('Clear selection')}
          </button>
        </div>
      )}

      {/* Table */}
      <div ref={listScrollRef} style={CT.scroll}>
        {_hiddenCss && <style>{_hiddenCss}</style>}
        <table className="leads-cols" style={{ ...CT.table, tableLayout:'fixed' as any }}>
          <colgroup>
            {LEAD_COLS.map((h)=><col key={h} style={{ width:LEAD_COL_W[h] }} />)}
          </colgroup>
          <thead>
            <tr style={CT.theadTr}>
              {LEAD_COLS.map(h=>(
                <th key={h} style={CT.th(false, (h==='Network'||h==='Score') ? 'right' : 'left')}>{t(h)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={16} style={{ padding:40, textAlign:'center', color:'#555' }}>{t('Loading...')}</td></tr>
            ) : leads.length === 0 ? (
              <tr><td colSpan={16} style={{ padding:40, textAlign:'center', color:'#555' }}>{t('No leads found')}</td></tr>
            ) : leads.map((l:any) => (
              <tr key={l.id} onClick={()=>openLead(l)} style={{ ...CT.row(selectedIds.includes(l.id)), cursor:'pointer' }}
                onMouseEnter={e=>(e.currentTarget.style.background = selectedIds.includes(l.id) ? 'rgba(0,229,160,0.1)' : '#2c333e')}
                onMouseLeave={e=>(e.currentTarget.style.background = selectedIds.includes(l.id) ? 'rgba(0,229,160,0.06)' : 'transparent')}>
                <td style={CT.td}>
                  <div style={{ fontSize:10, color:'#667', fontFamily:'monospace', marginBottom:2 }}>{l.customer_no || `Lead #${l.id}`}</div>
                  <a href={`?lead=${l.id}`} title={`${l.full_name || ''}${t(' — right-click to open in a new tab')}`}
                     onClick={(e)=>{ if (e.ctrlKey||e.metaKey||e.shiftKey||(e as any).button===1) { e.stopPropagation(); return; } e.preventDefault(); }}
                     style={{ fontWeight:600, color: l.is_verified ? '#00e5a0' : '#e0e0e0', fontSize:12, display:'flex', alignItems:'center', gap:4, textDecoration:'none' }}>
                    {firstWords((String(l.match_badge||'').startsWith('recapture') && l.matched_name) ? l.matched_name : l.full_name) || t('Unknown')}
                    {l.is_verified && (
                      <span title={t('Fully verified — click to filter')} onClick={e=>{e.stopPropagation();setFilterVerified('verified');setPage(1);}}
                        style={{ color:'#00e5a0', fontSize:11, cursor:'pointer' }}>✅</span>
                    )}
                    {l.match_badge === 'recapture' && (
                      <span onMouseEnter={e=>setBadgeHover({lead:l, kind:'recapture', x:e.clientX, y:e.clientY})} onMouseLeave={()=>setBadgeHover(null)}
                        style={{ fontSize:12, padding:'1px 5px', borderRadius:99, background:'rgba(255,77,77,0.15)', border:'1px solid #ff4d4d', whiteSpace:'nowrap', cursor:'help' }}>♻</span>
                    )}
                    {l.match_badge === 'registered_no_deposit' && (
                      <span onMouseEnter={e=>setBadgeHover({lead:l, kind:'no_deposit', x:e.clientX, y:e.clientY})} onMouseLeave={()=>setBadgeHover(null)}
                        style={{ fontSize:11, padding:'1px 5px', borderRadius:99, background:'#ff880022', border:'1px solid #ff8800', whiteSpace:'nowrap', cursor:'help' }}>🔥</span>
                    )}
                    {l.match_badge === 'reactivated' && (
                      <span title={t('Re-captured from archive (re-engaged) — +50 score')}
                        style={{ fontSize:9, fontWeight:700, padding:'2px 6px', borderRadius:99, background:'rgba(248,80,10,0.14)', color:'#FF6A1A', border:'1px solid #F8500A', whiteSpace:'nowrap' }}>📦 {t('Re-captured')}</span>
                    )}
                    {l.match_badge === 'recapture_archive' && (
                      <span onMouseEnter={e=>setBadgeHover({lead:l, kind:'recapture', x:e.clientX, y:e.clientY})} onMouseLeave={()=>setBadgeHover(null)}
                        style={{ fontSize:9, fontWeight:700, padding:'2px 6px', borderRadius:99, background:'rgba(248,80,10,0.14)', color:'#FF6A1A', border:'1px solid #F8500A', whiteSpace:'nowrap', cursor:'help' }}>📦 {t('Re-captured')}</span>
                    )}
                    {l.is_archived && (
                      <span style={{ fontSize:9, fontWeight:700, padding:'1px 6px', borderRadius:99, background:'rgba(255,170,0,0.12)', color:'#ffaa00', border:'1px solid rgba(255,170,0,0.3)', whiteSpace:'nowrap' }}>🗄 {t('Archived')}</span>
                    )}
                  </a>
                  <div style={{ fontSize:10, color:'#555', marginTop:2, display:'flex', alignItems:'center', gap:4 }}>{l.email ? <><span onClick={e=>{e.stopPropagation();setEmailContact({name:l.full_name,email:l.email});}} title={l.email} style={{ cursor:'pointer', color:'#8a93a3' }}>✉️ {t('Email')}</span>{l.email_verified && <span title={t('Email verified — click to filter')} onClick={e=>{e.stopPropagation();setFilterVerified('email_only');setPage(1);}} style={{ color:'#00e5a0', cursor:'pointer' }}>✓</span>}</> : <span style={{ color:'#445' }}>—</span>}</div>
                </td>
                <td style={CT.td}>
                  {l.phone ? (
                    <div style={{ display:'inline-flex', alignItems:'center', gap:4 }}>
                      <div onClick={e=>{e.stopPropagation();setPhoneContact({name:l.full_name,phone:l.phone});}} title={l.phone} style={{ display:'inline-flex', alignItems:'center', gap:4, padding:'2px 7px', borderRadius:5, border:`1px solid ${l.phone_verified?'#00e5a0':'#626d80'}`, background:'#373f4d', fontSize:11, color:'#888', cursor:'pointer' }}>
                        📞 ···{(l.phone||'').slice(-4)}
                      </div>
                      {l.phone_verified && <span title={t('Phone verified — click to filter')} onClick={e=>{e.stopPropagation();setFilterVerified('phone_only');setPage(1);}}
                        style={{ color:'#00e5a0', fontSize:12, cursor:'pointer' }}>✓</span>}
                    </div>
                  ) : '—'}
                </td>
                <td style={{ ...CT.td, color:'#888', fontSize:11 }}>
                  <div onClick={e=>{e.stopPropagation();l.country&&setFilterCountry(l.country);setPage(1);}} style={{ cursor:'pointer', color:'#888' }} title={t('Filter by country')}>{l.country || '—'}</div>
                  {l.city && <div onClick={e=>{e.stopPropagation();setFilterCity(l.city);setPage(1);}} style={{ color:'#555', cursor:'pointer' }} title={t('Filter by city')}>{l.city}</div>}
                </td>
                <td style={{ ...CT.td, color:'#888', fontSize:11, width:90, maxWidth:90, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }} title={l.campaign_name || ''}>
                  {l.campaign_name || '—'}
                </td>
                <td style={CT.td} onClick={e=>{e.stopPropagation();l.source&&setFilterSource(l.source);setPage(1);}}>
                  <div style={{ display:'flex', alignItems:'center', gap:6, fontSize:11, color:'#888', cursor:'pointer', textTransform:'capitalize' }} title={l.source}>
                    <SourceLogo source={l.source} size={16} />
                    <span>{l.source ? l.source.replace(/_/g,' ') : '—'}</span>
                  </div>
                </td>
                <td style={{ ...CT.td, color:'#888', fontSize:11 }}>
                  <div title={t('Registration date')}>{(l.meta_created || l.created_at) ? new Date(l.meta_created || l.created_at).toLocaleDateString('en-GB') : '—'}</div>
                  <div onClick={e=>{ e.stopPropagation(); setSort('last_login'); setPage(1); }} title={t('Last login — click to sort by most recent login')}
                    style={{ fontSize:10, color: l.last_login ? '#7fb0ff' : '#556', cursor:'pointer', marginTop:2, whiteSpace:'nowrap' }}>
                    🕑 {l.last_login ? new Date(l.last_login).toLocaleDateString('en-GB') : '—'}
                  </div>
                </td>
                {/* Last comment — the most recent communication (latest note line + call outcome). #194 */}
                <td style={CT.td}>
                  {(() => {
                    // last comment = last non-empty line of the running notes log ("[time] agent: text")
                    const lastLine = String(l.notes||'').split('\n').map((s:string)=>s.trim()).filter(Boolean).pop() || '';
                    const txt = lastLine.replace(/^\[[^\]]*\]\s*[^:]*:\s*/, '');
                    const m:any = { no_answer:[t('No answer'),'#9aa3b2'], off:[t('Off'),'#888'], rejected:[t('Rejected'),'#ff5d6c'], connected:[t('Connected'),'#00e5a0'], done:[t('Connected'),'#00e5a0'], call_later:[t('Callback'),'#ffaa00'] };
                    const oc = l.last_call_outcome ? (m[l.last_call_outcome] || [l.last_call_outcome,'#888']) : null;
                    if (!txt && !oc) return <span style={{ color:'#445' }}>—</span>;
                    return (
                      <div style={{ maxWidth:200 }}>
                        {txt && <div title={txt} style={{ fontSize:11, color:'#c7ccd6', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>💬 {txt}</div>}
                        {(oc || l.last_call_at || l.call_attempts>0) && (
                          <div style={{ display:'flex', alignItems:'center', gap:6, marginTop:txt?2:0 }}>
                            {oc && <span style={{ color:oc[1], fontWeight:600, fontSize:10 }}>{oc[0]}</span>}
                            {l.last_call_at && <span style={{ fontSize:9, color:'#667' }}>{new Date(l.last_call_at).toLocaleDateString('en-GB')}</span>}
                            {/* #273: times this number was called — so agents avoid over-calling */}
                            {l.call_attempts>0 && <span title={t('Times this number was called')} style={{ fontSize:9, color:'#8a93a3', background:'#2a2f3a', padding:'1px 6px', borderRadius:99, whiteSpace:'nowrap' }}>📞 {l.call_attempts}</span>}
                          </div>
                        )}
                      </div>
                    );
                  })()}
                </td>
                {/* Stage (TradeSoft pipeline). Meta quality is fed AUTOMATICALLY from stage/
                    verification/deposits — the manual rating column is gone. */}
                <td style={CT.td} onClick={e=>e.stopPropagation()}>
                  <select value={stageOf(l)} onChange={async e=>{
                    e.stopPropagation();
                    await apiPatch(`/leads/${l.id}`,{stage:e.target.value});
                    load();
                  }} style={{ padding:'3px 8px', background:(STAGE_COLORS[stageOf(l)]||'#555')+'22', border:`1px solid ${STAGE_COLORS[stageOf(l)]||'#555'}`, borderRadius:99, color:STAGE_COLORS[stageOf(l)]||'#888', cursor:'pointer', fontSize:10, fontWeight:600, outline:'none', fontFamily:'inherit', maxWidth:130 }}>
                    {STAGES.map(s=><option key={s} value={s} style={{background:'#373f4d',color:'#e0e0e0'}}>{t(s)}</option>)}
                  </select>
                  {l.meta_quality && <div title={t('Quality auto-fed to Meta')} style={{ fontSize:9, color:'#667', marginTop:2 }}>→ {t('Meta:')} {l.meta_quality}</div>}
                </td>
                {/* Training status — set by the training team on the Training board (hidden by default) */}
                <td style={{ ...CT.td, fontSize:11 }}>
                  {l.training_stage
                    ? <span style={{ fontSize:9.5, fontWeight:700, padding:'2px 7px', borderRadius:99, whiteSpace:'nowrap', background:(TRAIN_STAGE_COLOR[l.training_stage]||'#888')+'22', color:TRAIN_STAGE_COLOR[l.training_stage]||'#aaa', border:`1px solid ${TRAIN_STAGE_COLOR[l.training_stage]||'#888'}` }}>{t(TRAIN_STAGE_LABEL[l.training_stage]||l.training_stage)}</span>
                    : <span style={{ color:'#556' }}>—</span>}
                </td>

                <td style={{ ...CT.td, fontSize:11 }} onClick={e=>e.stopPropagation()}>
                  <AgentCell entityType="lead" entityId={l.id} agentName={l.agent_name}
                    onSortBy={(n)=>{ setFilterAgent(n); setPage(1); }}
                    onChanged={()=> load()} />
                  {!l.agent_name && l.legacy_sales_agent && l.legacy_sales_agent!=='-' &&
                    <div onClick={e=>{ e.stopPropagation(); setFilterAgent(l.legacy_sales_agent); setPage(1); }}
                      title={t('TradeSoft sales agent — click to filter leads by this agent')}
                      style={{ color:'#b08cff', fontSize:10, marginTop:2, whiteSpace:'nowrap', overflow:'hidden', textOverflow:'ellipsis', maxWidth:120, cursor:'pointer', textDecoration:'underline' }}>👤 {l.legacy_sales_agent}</div>}
                </td>
                <td style={{ ...CT.td, fontSize:11, width:80, maxWidth:80 }} onClick={e=>e.stopPropagation()}>
                  {l.ib_name
                    ? <span onClick={e=>{ e.stopPropagation(); if(filterIB===l.ib_name){ openIbProfile(l.ib_name); } else { setFilterIB(l.ib_name); setPage(1); } }}
                        title={l.ib_name + (filterIB===l.ib_name?t(' — open IB page'):t(' — filter by this IB (click again to open IB page)'))}
                        style={{ color:'#00aaff', cursor:'pointer', display:'block', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{l.ib_name}</span>
                    : <span style={{ color:'#555' }}>—</span>}
                </td>

                {/* KYC */}
                <td style={{ ...CT.td, padding:'9px 6px' }} onClick={e=>e.stopPropagation()}>
                  <div style={{ display:'flex', flexDirection:'column', gap:2 }}>
                    <span title={t('Identity document — click to filter')} onClick={e=>{e.stopPropagation();setFilterVerified('kyc_id');setPage(1);}}
                      style={{ fontSize:10, color: l.kyc_id_verified?'#00e5a0':l.kyc_id_uploaded?'#ffaa00':'#555', cursor:'pointer' }}>
                      🪪 {l.kyc_id_verified?'✓':l.kyc_id_uploaded?'⏳':'—'}
                    </span>
                    <span title={t('Address proof — click to filter')} onClick={e=>{e.stopPropagation();setFilterVerified('kyc_address');setPage(1);}}
                      style={{ fontSize:10, color: l.kyc_address_verified?'#00e5a0':l.kyc_address_uploaded?'#ffaa00':'#555', cursor:'pointer' }}>
                      📄 {l.kyc_address_verified?'✓':l.kyc_address_uploaded?'⏳':'—'}
                    </span>
                    {/* trading account (#2): show the account once KYC-verified, else "not yet verified" */}
                    {(l.kyc_status==='verified' && l.converted_login)
                      ? <span style={{ fontSize:10, color:'#00e5a0', fontWeight:700 }}>💼 {l.converted_login}</span>
                      : <span style={{ fontSize:9.5, color:'#777' }}>{t('not yet verified')}</span>}
                  </div>
                </td>
                {/* Network — ONE unified badge (canonical 0-10; click for linked accounts) */}
                <td style={{ ...CT.td, textAlign:'right' }} onClick={e=>e.stopPropagation()}>
                  <NetworkBadge score={l.network_score} leadId={l.id} />
                </td>
                <td style={{ ...CT.td, textAlign:'right' }}>
                  <div style={{ display:'inline-block' }}
                    onMouseEnter={e=>{ const r=(e.currentTarget as HTMLElement).getBoundingClientRect(); setScoreHover({ lead:l, x:r.right, y:r.top }); }}
                    onMouseLeave={()=>setScoreHover(null)}>
                    <div style={{ display:'inline-flex', alignItems:'center', justifyContent:'center', width:32, height:32, borderRadius:'50%', border:`2px solid ${(l.score||0)>=50?'#ff4d4d':(l.score||0)>=25?'#ff8800':'#555'}`, color:(l.score||0)>=50?'#ff4d4d':(l.score||0)>=25?'#ff8800':'#888', fontWeight:700, fontSize:12, cursor:'help' }}>
                      {l.score||0}
                    </div>
                  </div>
                </td>
                <td style={CT.td} onClick={e=>e.stopPropagation()}>
                  <div style={{ display:'flex', alignItems:'center', gap:4 }}>
                    <LeadActions lead={l} onUpdate={load} onView={()=>openLead(l)} showView={false} />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

      </div>

      {/* Pagination + page-size selector (ticket #58) */}
      <Pager page={page} setPage={setPage} pageSize={pageSize} setPageSize={setPageSize}
        count={leads.length} total={total} label={t('leads')} />

      {phoneContact && <PhoneModal contact={phoneContact} onClose={()=>setPhoneContact(null)} />}
      {emailContact && <EmailModal contact={emailContact} type="lead" onClose={()=>setEmailContact(null)} />}

      {/* Score-breakdown tooltip — position:fixed at top level so it ALWAYS clears the KPI cards
          (it used to render behind them for the first rows — ticket #158). */}
      {scoreHover && (() => {
        const l = scoreHover.lead;
        const matched = l.match_badge==='recapture'||l.match_badge==='registered_no_deposit';
        const mb = matched ? 50 : 0;
        const pv = l.phone_verified ? 15 : 0;
        const ev = l.email_verified ? 15 : 0;
        const both = (l.phone && l.email) ? 10 : 0;
        const recency = Math.max(0, (l.score||0) - mb - pv - ev - both); // backend uses real lead date
        const rows:any[] = [
          [l.match_badge==='recapture'?t('♻ Recapture (was a depositor)'):l.match_badge==='registered_no_deposit'?t('🔥 Registered, no deposit'):t('Matched a client'), mb, matched],
          [t('📞 Phone verified'), pv, !!pv],
          [t('✉️ Email verified'), ev, !!ev],
          [t('Phone + email on file'), both, !!both],
          [t('🕑 Recency (lead age)'), recency, recency>0],
        ];
        const width = 230;
        const left = Math.min(Math.max(8, scoreHover.x - width), window.innerWidth - width - 8);
        const top  = Math.max(8, scoreHover.y - 185);   // above the score circle, clamped on-screen
        return (
          <div style={{ position:'fixed', left, top, width, zIndex:99999, background:'#373f4d', border:'1px solid #626d80', borderRadius:10, padding:12, boxShadow:'0 8px 32px rgba(0,0,0,0.6)', pointerEvents:'none', textAlign:'left' }}>
            <div style={{ fontSize:12, fontWeight:600, marginBottom:8 }}>{t('Why score =')} {l.score||0}</div>
            {rows.map(([label,val,active]:any)=>(
              <div key={label} style={{ display:'flex', justifyContent:'space-between', fontSize:10, padding:'3px 0', borderBottom:'1px solid #4f596b', color: active?'#e0e0e0':'#555' }}>
                <span>{label}</span>
                <span style={{ color: active?'#00e5a0':'#555' }}>{active?`+${val}`:'—'}</span>
              </div>
            ))}
            <div style={{ display:'flex', justifyContent:'space-between', fontSize:11, fontWeight:700, paddingTop:6 }}>
              <span>{t('Total')}</span><span style={{ color:'#fff' }}>{l.score||0}/100</span>
            </div>
          </div>
        );
      })()}

      {badgeHover && (() => {
        const l = badgeHover.lead;
        const when = l.meta_created ? new Date(l.meta_created).toLocaleString('en-GB') : (l.created_at ? new Date(l.created_at).toLocaleString('en-GB') : null);
        const isRe = badgeHover.kind==='recapture';
        const origReg = l.matched_reg_date ? new Date(l.matched_reg_date).toLocaleDateString('en-GB') : null;
        const hasOld = isRe && l.matched_login > 0;
        const left = Math.min(badgeHover.x + 12, window.innerWidth - 316);
        const top  = Math.min(badgeHover.y + 14, window.innerHeight - (hasOld?250:150));
        return (
          <div style={{ position:'fixed', left, top, zIndex:99999, background:'#2c333e', border:`1px solid ${isRe?'#ff6a1a':'#626d80'}`, borderRadius:10, padding:13, width:296, boxShadow:'0 8px 32px rgba(0,0,0,0.6)', pointerEvents:'none' }}>
            <div style={{ fontSize:12.5, fontWeight:700, color: isRe?'#ff6a1a':'#ff8800', marginBottom:8 }}>
              {isRe ? t('♻ Recapture — already in our system') : t('🔥 Registered, no deposit')}
            </div>
            {hasOld ? (<>
              {/* THE OLD RECORD — clearly shown so the desk knows who this really is */}
              <div style={{ background:'rgba(255,106,26,0.10)', border:'1px solid rgba(255,106,26,0.35)', borderRadius:8, padding:'9px 11px', marginBottom:9 }}>
                <div style={{ fontSize:9.5, color:'#ffb488', fontWeight:700, textTransform:'uppercase', letterSpacing:'.05em', marginBottom:4 }}>📇 {t('Existing record')}</div>
                <div style={{ fontSize:13, fontWeight:700, color:'#fff' }}>{l.matched_name || l.full_name || '—'} <span style={{ color:'#9aa6b8', fontWeight:500 }}>· #{l.matched_login}</span></div>
                <div style={{ display:'flex', justifyContent:'space-between', marginTop:6, fontSize:11 }}>
                  <span style={{ color:'#9aa6b8' }}>{t('Registered')}</span>
                  <span style={{ color:'#00e5a0', fontWeight:700 }}>{origReg || '—'}</span>
                </div>
                <div style={{ display:'flex', justifyContent:'space-between', marginTop:3, fontSize:11 }}>
                  <span style={{ color:'#9aa6b8' }}>{t('Deposited')}</span>
                  <span style={{ color:(l.matched_deposits>0)?'#00e5a0':'#888', fontWeight:700 }}>{(l.matched_deposits>0)?('$'+Number(l.matched_deposits).toLocaleString('en-GB')):t('never')}</span>
                </div>
              </div>
              <div style={{ display:'flex', justifyContent:'space-between', fontSize:11 }}>
                <span style={{ color:'#9aa6b8' }}>♻ {t('Re-filled the form')}</span>
                <span style={{ color:'#ffd166', fontWeight:700 }}>{when || '—'}</span>
              </div>
              <div style={{ fontSize:9.5, color:'#8792a6', marginTop:8, lineHeight:1.5 }}>{t('Same person came back through a new ad. Their original registration date and history are kept — this is an update of the old record, not a new client.')}</div>
            </>) : (<>
              <div style={{ fontSize:11, color:'#ccc', marginBottom:4 }}>📋 {t('Filled the Meta ad form on:')}</div>
              <div style={{ fontSize:13, fontWeight:600, color:'#00e5a0' }}>{when || t('date not available')}</div>
              <div style={{ fontSize:10, color:'#8792a6', marginTop:7, lineHeight:1.5 }}>
                {isRe
                  ? t('Re-submitted our ad form — was already in our system (older archived lead reactivated).')
                  : `${t('Opened account')} #${l.matched_login} ${t('from this lead but never deposited.')}`}
              </div>
            </>)}
          </div>
        );
      })()}

      {/* Add lead modal */}
      {showAdd && (
        <div style={{ position:'fixed', inset:0, background:'rgba(0,0,0,0.7)', zIndex:1000, display:'flex', alignItems:'center', justifyContent:'center' }}>
          <div style={{ background:'#2c333e', borderRadius:12, padding:24, width:480, border:'1px solid #626d80' }}>
            <div style={{ fontSize:15, fontWeight:700, marginBottom:16 }}>{t('Add new lead')}</div>
            <AddLeadForm onClose={()=>setShowAdd(false)} onSaved={()=>{ setShowAdd(false); load(); }} agents={agents} />
          </div>
        </div>
      )}
    </div>
  );
}

// #95 (Nuha) — Verified Accounts: KYC-approved accounts that have a trading-account
// number (login), regardless of deposit. (Replaced the old "Approved & funded" tab —
// accounts that deposit move to the Clients list automatically.)
function VerifiedAccounts({ view, setView }: any) {
  const t = useT();
  const [rows, setRows]   = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [kpis, setKpis]   = useState<any>({});
  const [loading, setLoading] = useState(false);
  const [search, setSearch]   = useState('');
  const [country, setCountry] = useState('');
  const [sort, setSort]   = useState('date');
  const [page, setPage]   = useState(1);
  const pageSize = 50;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const p = new URLSearchParams({ page:String(page), page_size:String(pageSize), sort });
      if (search)  p.set('search', search);
      if (country) p.set('country', country);
      const data = await apiGet(`/leads/verified?${p}`);
      setRows(data.accounts || []);
      setTotal(data.total || 0);
      setKpis(data.kpis || {});
    } catch(e) { setRows([]); }
    setLoading(false);
  }, [page, sort, search, country]);

  useEffect(() => { load(); }, [load]);

  const countries = Array.from(new Set(rows.map((r:any)=>r.country).filter(Boolean))).sort();

  return (
    <div style={{ height:'100%', display:'flex', flexDirection:'column', overflow:'hidden', minHeight:0 }}>
      {/* Sub-view tabs */}
      <div style={{ display:'flex', gap:4, padding:'8px 14px 0', background:'#2c333e', flexShrink:0 }}>
        {([['leads','📋 All leads'],['verified','✅ Verified Accounts']] as const).map(([k,l])=>(
          <button key={k} onClick={()=>setView(k)}
            style={{ padding:'6px 16px', borderRadius:'8px 8px 0 0', border:`1px solid ${view===k?'#00e5a0':'#626d80'}`, borderBottom:'none', background:view===k?'rgba(0,229,160,0.1)':'transparent', color:view===k?'#00e5a0':'#888', cursor:'pointer', fontSize:12, fontWeight:600, fontFamily:'inherit' }}>
            {t(l)}
          </button>
        ))}
      </div>

      {/* KPI bar */}
      <div style={{ display:'grid', gridTemplateColumns:'repeat(1,minmax(0,300px))', gap:8, padding:'10px 14px', background:'#262c36', borderBottom:'1px solid #373f4d', flexShrink:0 }}>
        {[
          { label:t('Verified accounts (KYC-approved + has trading account)'), value:(kpis.accounts||0).toLocaleString('en-GB'), color:'#00e5a0' },
        ].map((k,i)=>(
          <div key={i} style={{ background:'#2c333e', border:'1px solid #373f4d', borderRadius:8, padding:'8px 14px' }}>
            <div style={{ fontSize:9, color:'#555', textTransform:'uppercase', letterSpacing:.5, marginBottom:3 }}>{k.label}</div>
            <div style={{ fontSize:18, fontWeight:700, color:k.color }}>{k.value}</div>
          </div>
        ))}
      </div>

      {/* Controls */}
      <div style={{ display:'flex', alignItems:'center', gap:8, padding:'8px 14px', background:'#2c333e', borderBottom:'1px solid #373f4d', flexShrink:0, flexWrap:'wrap' }}>
        <div style={{ fontWeight:600, fontSize:13 }}>{t('Verified Accounts')}</div>
        <div style={{ fontSize:11, color:'#555' }}>{total.toLocaleString('en-GB')} {t('accounts')}</div>
        <input value={search} onChange={e=>{ setSearch(e.target.value); setPage(1); }} placeholder={t('Search name, login, email, phone...')}
          style={{ flex:1, minWidth:200, padding:'6px 10px', background:'#373f4d', border:'1px solid #626d80', borderRadius:7, color:'#e0e0e0', fontSize:12, outline:'none' }} />
        <select value={country} onChange={e=>{ setCountry(e.target.value); setPage(1); }}
          style={{ padding:'6px 8px', background:'#373f4d', border:'1px solid #626d80', borderRadius:7, color:'#e0e0e0', fontSize:11 }}>
          <option value="">{t('All countries')}</option>
          {countries.map((c:any)=><option key={c} value={c}>{c}</option>)}
        </select>
        {[{key:'date',label:'Newest'},{key:'name',label:'Name'},{key:'login',label:'Login'}].map(s=>(
          <button key={s.key} onClick={()=>{ setSort(s.key); setPage(1); }}
            style={{ padding:'5px 10px', borderRadius:6, border:`1px solid ${sort===s.key?'#00e5a0':'#626d80'}`, background:sort===s.key?'rgba(0,229,160,0.1)':'transparent', color:sort===s.key?'#00e5a0':'#888', cursor:'pointer', fontSize:11, fontFamily:'inherit' }}>
            {t(s.label)}
          </button>
        ))}
      </div>

      {/* Table */}
      <div style={{ flex:1, overflow:'auto', minHeight:0 }}>
        <table style={{ width:'100%', borderCollapse:'collapse', fontSize:12 }}>
          <thead>
            <tr style={{ background:'#262c36', position:'sticky', top:0, zIndex:5 }}>
              {['Name','Account / Login','Platform','Country','KYC / Approval','Registered','Deposited?','From lead'].map(h=>(
                <th key={h} style={{ padding:'8px 10px', textAlign:'left', color:'#cfd6e0', fontWeight:600, fontSize:10, borderBottom:'1px solid #373f4d', whiteSpace:'nowrap', textTransform:'uppercase', letterSpacing:.5 }}>{t(h)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={8} style={{ padding:40, textAlign:'center', color:'#555' }}>{t('Loading...')}</td></tr>
            ) : rows.length === 0 ? (
              <tr><td colSpan={8} style={{ padding:40, textAlign:'center', color:'#555' }}>{t('No verified accounts found')}</td></tr>
            ) : rows.map((r:any) => (
              <tr key={r.login} style={{ borderBottom:'1px solid #262c36' }}
                onMouseEnter={e=>(e.currentTarget.style.background='#2c333e')}
                onMouseLeave={e=>(e.currentTarget.style.background='transparent')}>
                <td style={{ padding:'8px 10px', fontWeight:600, color:'#e0e0e0' }} title={r.name}>{firstWords(r.name,3) || '—'}</td>
                <td style={{ padding:'8px 10px', fontFamily:'monospace', color:'#00aaff' }}>#{r.login}</td>
                <td style={{ padding:'8px 10px', color:'#888' }}>{r.platform}</td>
                <td style={{ padding:'8px 10px', color:'#888' }}>{r.country || '—'}</td>
                <td style={{ padding:'8px 10px' }}>
                  <span style={{ fontSize:10, padding:'2px 8px', borderRadius:99,
                    background: r.kyc_status==='verified' ? 'rgba(0,229,160,0.12)' : 'rgba(255,170,0,0.12)',
                    color: r.kyc_status==='verified' ? '#00e5a0' : '#ffaa00',
                    border:`1px solid ${r.kyc_status==='verified' ? '#00e5a0' : '#ffaa00'}` }}>
                    {r.kyc_status==='verified' ? `✓ ${t('Approved')}` : (r.kyc_status || t('pending'))}
                  </span>
                </td>
                <td style={{ padding:'8px 10px', color:'#888', whiteSpace:'nowrap' }}>{r.reg_date ? new Date(r.reg_date).toLocaleDateString('en-GB') : '—'}</td>
                <td style={{ padding:'8px 10px', textAlign:'center' }}>
                  {r.has_deposit
                    ? <span style={{ fontSize:10, color:'#00e5a0' }} title={t('Has at least one deposit')}>✓</span>
                    : <span style={{ fontSize:10, color:'#556' }} title={t('No deposit yet')}>—</span>}
                </td>
                <td style={{ padding:'8px 10px', fontSize:11, color:'#888' }}>
                  {r.lead_id
                    ? <span title={`${t('From lead')} #${r.lead_id}`}>
                        🎯 {firstWords(r.lead_name,2) || `#${r.lead_id}`}
                        {r.match_badge==='recapture' && <span style={{ marginLeft:4, color:'#ff4d4d' }}>♻</span>}
                      </span>
                    : <span style={{ color:'#445' }}>—</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {/* Pagination */}
        <div style={{ display:'flex', justifyContent:'center', alignItems:'center', gap:8, padding:'12px' }}>
          <button onClick={()=>setPage(p=>Math.max(1,p-1))} disabled={page===1}
            style={{ padding:'5px 14px', background:'#373f4d', border:'1px solid #626d80', borderRadius:6, color:page===1?'#626d80':'#888', cursor:page===1?'default':'pointer', fontSize:12 }}>← {t('Prev')}</button>
          <span style={{ color:'#555', fontSize:12 }}>{t('Page')} {page} {t('of')} {Math.max(1, Math.ceil(total/pageSize))}</span>
          <button onClick={()=>setPage(p=>p+1)} disabled={rows.length<pageSize}
            style={{ padding:'5px 14px', background:'#373f4d', border:'1px solid #626d80', borderRadius:6, color:rows.length<pageSize?'#626d80':'#00e5a0', cursor:rows.length<pageSize?'default':'pointer', fontSize:12, borderColor:rows.length<pageSize?'#626d80':'#00e5a0' }}>{t('Next')} →</button>
        </div>
      </div>
    </div>
  );
}

function AddLeadForm({ onClose, onSaved, agents }: any) {
  const t = useT();
  // a SALES AGENT can only create leads for themselves — the agent box is locked to their name
  const isSalesAgent = (localStorage.getItem('userRole') || '') === 'sales_agent';
  const myName = localStorage.getItem('userName') || '';
  const [form, setForm] = useState({ full_name:'', phone:'', email:'', country:'', city:'', source:'manual', status:'new', assigned_agent_id:'', notes:'' });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');

  const submit = async () => {
    setErr('');
    if (!form.phone.trim() && !form.email.trim()) { setErr(t('At least a phone number or an email is required')); return; }
    setSaving(true);
    try {
      const res: any = await apiPost('/leads', form);
      if (res && res.id) onSaved();
      else setErr(res?.detail || t('Failed to create the lead'));
    } catch(e) { setErr(t('Failed to create the lead')); }
    setSaving(false);
  };

  const inp = (field: string, placeholder: string, type='text') => (
    <input value={(form as any)[field]} onChange={e=>setForm({...form,[field]:e.target.value})}
      placeholder={placeholder} type={type}
      style={{ width:'100%', padding:'8px 10px', background:'#373f4d', border:'1px solid #626d80', borderRadius:7, color:'#e0e0e0', fontSize:13, outline:'none', boxSizing:'border-box' as any, fontFamily:'inherit' }} />
  );

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:8 }}>
        {inp('full_name',t('Full name'))}
        {inp('phone',t('Phone number'),'tel')}
        {inp('email',t('Email'),'email')}
        {inp('country',t('Country'))}
        {inp('city',t('City'))}
        <select value={form.source} onChange={e=>setForm({...form,source:e.target.value})}
          style={{ padding:'8px 10px', background:'#373f4d', border:'1px solid #626d80', borderRadius:7, color:'#e0e0e0', fontSize:13 }}>
          {['manual','facebook','instagram','messenger','audience_network','Google','WhatsApp','TikTok','Email','Referral','Other'].map(s=><option key={s} value={s}>{s}</option>)}
        </select>
        {isSalesAgent ? (
          <input value={myName} disabled title={t('Sales agents can only create leads for themselves')}
            style={{ padding:'8px 10px', background:'#2c333e', border:'1px solid #626d80', borderRadius:7, color:'#8b93a1', fontSize:13, boxSizing:'border-box' as any, fontFamily:'inherit' }} />
        ) : (
          <select value={form.assigned_agent_id} onChange={e=>setForm({...form,assigned_agent_id:e.target.value})}
            style={{ padding:'8px 10px', background:'#373f4d', border:'1px solid #626d80', borderRadius:7, color:'#e0e0e0', fontSize:13 }}>
            <option value="">{t('Unassigned')}</option>
            {agents.map((a:any)=><option key={a.id} value={a.id}>{a.full_name}</option>)}
          </select>
        )}
      </div>
      <textarea value={form.notes} onChange={e=>setForm({...form,notes:e.target.value})} placeholder={t('Notes...')} rows={2}
        style={{ width:'100%', padding:'8px 10px', background:'#373f4d', border:'1px solid #626d80', borderRadius:7, color:'#e0e0e0', fontSize:13, outline:'none', resize:'none', fontFamily:'inherit', boxSizing:'border-box' as any }} />
      {err && <div style={{ fontSize:12, color:'#ff6b6b', background:'rgba(255,77,77,0.08)', border:'1px solid rgba(255,77,77,0.3)', borderRadius:7, padding:'8px 10px' }}>{err}</div>}
      <div style={{ display:'flex', gap:8, justifyContent:'flex-end', marginTop:4 }}>
        <button onClick={onClose} style={{ padding:'7px 16px', background:'#373f4d', border:'1px solid #626d80', borderRadius:7, color:'#888', cursor:'pointer', fontSize:13 }}>{t('Cancel')}</button>
        <button onClick={submit} disabled={saving}
          style={{ padding:'7px 20px', background:'#00e5a0', border:'none', borderRadius:7, color:'#000', fontWeight:700, cursor:'pointer', fontSize:13, fontFamily:'inherit' }}>
          {saving ? t('Saving...') : t('Add lead')}
        </button>
      </div>
    </div>
  );
}

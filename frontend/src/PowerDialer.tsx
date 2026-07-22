import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useT } from './adminI18n';

const API = '/api';

function apiGet(path: string) {
  const token = localStorage.getItem('token') || '';
  return fetch(`${API}${path}`, { headers: { Authorization: `Bearer ${token}` } }).then(r => r.json());
}
function apiPost(path: string, body: any) {
  const token = localStorage.getItem('token') || '';
  return fetch(`${API}${path}`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  }).then(r => r.json());
}

async function yeastarCall(phone: string): Promise<any> {
  const extension = localStorage.getItem('yeastarExtension') || '';
  try {
    const res = await apiPost('/dialer/call', { phone, extension });
    return res || { ok: false, errmsg: 'No response from server' };
  } catch {
    return { ok: false, errmsg: 'Network error reaching the server' };
  }
}

// Short attention ring — played when a contact answers, so the agent looks up.
function playAnswerRing() {
  try {
    const Ctx = (window as any).AudioContext || (window as any).webkitAudioContext;
    if (!Ctx) return;
    const ctx = new Ctx();
    [0, 0.18, 0.36].forEach((t) => {
      const o = ctx.createOscillator(); const g = ctx.createGain();
      o.type = 'sine'; o.frequency.value = 880;
      o.connect(g); g.connect(ctx.destination);
      const s = ctx.currentTime + t;
      g.gain.setValueAtTime(0.0001, s);
      g.gain.exponentialRampToValueAtTime(0.25, s + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, s + 0.14);
      o.start(s); o.stop(s + 0.15);
    });
    setTimeout(() => { try { ctx.close(); } catch {} }, 800);
  } catch {}
}

function fmtUSD(n: number) { return '$' + (n || 0).toLocaleString(undefined, { maximumFractionDigits: 0 }); }
function fmtTime(s: number) { return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`; }

interface Client {
  queue_id: number;
  login: number;
  lead_id?: number;
  source?: string;
  name: string;
  phone: string;
  country: string;
  city: string;
  balance: number;
  equity: number;
  total_deposits: number;
  last_deposit: string;
  attempt: number;
  campaign?: string;
  channel?: string;
  reg_date?: string;
  last_comment?: string;
}

// channel/platform colour for the badge
const CHANNEL_COLORS: Record<string,string> = {
  facebook:'#1877f2', instagram:'#e1306c', tiktok:'#ff0050', snapchat:'#f0c040',
  google:'#4285f4', youtube:'#ff0000', whatsapp:'#25d366', direct:'#888',
};
function fmtDateTime(s?: string) {
  if (!s) return '';
  const d = new Date(s.includes('T') || s.includes('-') ? s : Number(s));
  if (isNaN(d.getTime())) return s;
  return d.toLocaleString(undefined, { day:'2-digit', month:'short', year:'numeric', hour:'2-digit', minute:'2-digit' });
}
// local "YYYY-MM-DDTHH:MM:00" from a Date (no timezone suffix — matches backend naive compare)
function toLocalIso(d: Date) {
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:00`;
}

// ── BIG ANSWERED POPUP ──────────────────────────────────────────────────────
// #256 — the CURRENT contact's previous comments, auto-switching as the dialer advances,
// so the agent sees who they're about to talk to (and past context) without leaving the widget.
function ContactComments({ contact }: any) {
  const t = useT();
  const [items, setItems] = useState<any[]|null>(null);
  useEffect(() => {
    let dead = false;
    setItems(null);
    if (!contact) return;
    (async () => {
      try {
        if (contact.lead_id && (contact.source === 'leads' || !contact.login)) {
          const d: any = await apiGet(`/leads?lead_id=${contact.lead_id}`);
          const l = (d.leads || [])[0];
          const lines = String(l?.notes || '').split('\n').map((s: string) => s.trim()).filter(Boolean).slice(-3).reverse();
          if (!dead) setItems(lines.map((x: string) => ({ text: x })));
        } else if (contact.login) {
          const d: any = await apiGet(`/clients/${contact.login}`);
          const cs = (d.actions_history || []).filter((a: any) => a.note).slice(0, 3);
          if (!dead) setItems(cs.map((a: any) => ({
            text: a.note, who: a.agent_name || '',
            when: a.created_at ? new Date(a.created_at).toLocaleDateString('en-GB') : '',
          })));
        } else if (!dead) setItems([]);
      } catch { if (!dead) setItems([]); }
    })();
    return () => { dead = true; };
  }, [contact?.lead_id, contact?.login]);
  if (!contact) return null;
  return (
    <div style={{ padding:'8px 12px', borderTop:'1px solid #1e2230', maxHeight:150, overflowY:'auto' }}>
      <div style={{ fontSize:9.5, color:'#667', textTransform:'uppercase', letterSpacing:.6, fontWeight:700, marginBottom:5 }}>
        💬 {t('Previous comments')}
      </div>
      {items === null ? (
        <div style={{ fontSize:11, color:'#556' }}>{t('Loading…')}</div>
      ) : items.length === 0 ? (
        <div style={{ fontSize:11, color:'#556' }}>{t('No previous comments')}</div>
      ) : items.map((c, i) => (
        <div key={i} style={{ fontSize:11, color:'#aab3c0', lineHeight:1.45, padding:'4px 0', borderBottom: i < items.length-1 ? '1px solid #2a313d' : 'none', wordBreak:'break-word' }}>
          {(c.who || c.when) && <span style={{ color:'#667', fontSize:9.5 }}>{c.who}{c.when ? ` · ${c.when}` : ''} — </span>}
          {c.text}
        </div>
      ))}
    </div>
  );
}


function AnsweredPopup({ client, sessionId, onDone, onCallLater }: any) {
  const t = useT();
  const [comment, setComment]           = useState('');
  const [showCallLater, setShowCallLater] = useState(false);
  const [offDays, setOffDays]   = useState('');
  const [offHours, setOffHours] = useState('');
  const [offMins, setOffMins]   = useState('');
  const [duration, setDuration]           = useState(0);

  useEffect(() => {
    const t = setInterval(() => setDuration(d => d + 1), 1000);
    return () => clearInterval(t);
  }, []);

  const offsetMs = ((+offDays || 0) * 86400 + (+offHours || 0) * 3600 + (+offMins || 0) * 60) * 1000;
  const callbackDate = offsetMs > 0 ? new Date(Date.now() + offsetMs) : null;
  const setQuick = (d: number, h: number, m: number) => {
    setOffDays(d ? String(d) : ''); setOffHours(h ? String(h) : ''); setOffMins(m ? String(m) : '');
  };

  const submitOutcome = async (outcome: string) => {
    const call_later_at = outcome === 'call_later' && callbackDate ? toLocalIso(callbackDate) : undefined;
    await apiPost('/dialer/call/result', {
      queue_id: client.queue_id, session_id: sessionId,
      login: client.login, lead_id: client.lead_id,
      outcome, comment, call_later_at,
    });
    if (outcome === 'call_later') onCallLater();
    else onDone();
  };

  return (
    <div style={{ position:'fixed', inset:0, background:'rgba(0,0,0,0.85)', zIndex:999999,
      display:'flex', alignItems:'center', justifyContent:'center' }}>
      <div style={{ background:'#262c36', border:'1px solid rgba(0,229,160,0.3)', borderRadius:20,
        padding:32, width:480, maxHeight:'85vh', overflowY:'auto',
        boxShadow:'0 0 60px rgba(0,229,160,0.15)' }}>

        {/* Header */}
        <div style={{ display:'flex', alignItems:'center', gap:12, marginBottom:24 }}>
          <div style={{ width:52, height:52, borderRadius:14, background:'linear-gradient(135deg,#003d99,#0066ff)',
            display:'flex', alignItems:'center', justifyContent:'center', fontSize:22, fontWeight:700, color:'#fff' }}>
            {client.name?.[0]?.toUpperCase()}
          </div>
          <div>
            <div style={{ fontSize:20, fontWeight:700, color:'#fff' }}>{client.name}</div>
            <div style={{ fontSize:13, color:'#00e5a0', fontFamily:'monospace' }}>{client.phone}</div>
          </div>
          <div style={{ marginLeft:'auto', textAlign:'right' }}>
            <div style={{ fontSize:24, fontWeight:700, color:'#00e5a0', fontFamily:'monospace' }}>{fmtTime(duration)}</div>
            <div style={{ fontSize:11, color:'#555' }}>{t('On call')}</div>
          </div>
          <button onClick={() => submitOutcome('done')} title={t('Close & finish call')}
            style={{ marginLeft:14, alignSelf:'flex-start', background:'none', border:'none',
              color:'#667', cursor:'pointer', fontSize:24, lineHeight:1, padding:0 }}>✕</button>
        </div>

        {/* Client stats */}
        <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr 1fr', gap:10, marginBottom:20 }}>
          {[
            { label:'Balance',    value: fmtUSD(client.balance),        color:'#00e5a0' },
            { label:'Total Dep.', value: fmtUSD(client.total_deposits),  color:'#4d9fff' },
            { label:'Country',    value: client.country || '—',          color:'#e0e0e0' },
            { label:'City',       value: client.city || '—',             color:'#888' },
            { label:'Equity',     value: fmtUSD(client.equity),          color:'#ffaa00' },
            { label:'Attempt',    value: `#${(client.attempt||0)+1}`,    color:'#ff8800' },
          ].map(s => (
            <div key={s.label} style={{ background:'#2c333e', borderRadius:10, padding:'10px 12px', textAlign:'center' }}>
              <div style={{ fontSize:15, fontWeight:600, color:s.color }}>{s.value}</div>
              <div style={{ fontSize:10, color:'#555', marginTop:2 }}>{t(s.label)}</div>
            </div>
          ))}
        </div>

        {/* Lead details: campaign · channel · registered · last comment */}
        <div style={{ background:'#2c333e', borderRadius:12, padding:'12px 14px', marginBottom:16,
          display:'flex', flexDirection:'column', gap:10 }}>
          <div style={{ display:'flex', alignItems:'center', gap:8 }}>
            <span style={{ fontSize:11, color:'#667', width:78, flexShrink:0 }}>📣 {t('Campaign')}</span>
            <span style={{ fontSize:13, color:'#e0e0e0', fontWeight:500, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
              {client.campaign || '—'}
            </span>
            {client.channel && (
              <span style={{ marginLeft:'auto', fontSize:10, fontWeight:600, padding:'2px 9px', borderRadius:99,
                textTransform:'capitalize',
                background:`${CHANNEL_COLORS[client.channel.toLowerCase()] || '#888'}22`,
                color: CHANNEL_COLORS[client.channel.toLowerCase()] || '#aaa' }}>
                {client.channel}
              </span>
            )}
          </div>
          <div style={{ display:'flex', alignItems:'center', gap:8 }}>
            <span style={{ fontSize:11, color:'#667', width:78, flexShrink:0 }}>🗓 {t('Registered')}</span>
            <span style={{ fontSize:13, color:'#e0e0e0' }}>{fmtDateTime(client.reg_date) || '—'}</span>
          </div>
          {client.last_comment ? (
            <div style={{ display:'flex', gap:8 }}>
              <span style={{ fontSize:11, color:'#667', width:78, flexShrink:0, paddingTop:2 }}>💬 {t('Last note')}</span>
              <span style={{ fontSize:12, color:'#c0c4cc', lineHeight:1.5, whiteSpace:'pre-wrap',
                maxHeight:60, overflowY:'auto' }}>{client.last_comment}</span>
            </div>
          ) : (
            <div style={{ display:'flex', gap:8 }}>
              <span style={{ fontSize:11, color:'#667', width:78, flexShrink:0 }}>💬 {t('Last note')}</span>
              <span style={{ fontSize:12, color:'#555', fontStyle:'italic' }}>{t('No previous notes')}</span>
            </div>
          )}
        </div>

        {/* Notes */}
        <div style={{ marginBottom:16 }}>
          <div style={{ fontSize:11, color:'#555', marginBottom:6 }}>{t('Call notes')}</div>
          <textarea value={comment} onChange={e => setComment(e.target.value)}
            placeholder={t('What did you discuss? Any follow-up needed?')}
            style={{ width:'100%', background:'#2c333e', border:'1px solid #1e2230', borderRadius:10,
              color:'#e0e0e0', fontSize:13, padding:'12px', resize:'none', outline:'none',
              height:80, fontFamily:'inherit', boxSizing:'border-box' }} />
        </div>

        {/* Actions */}
        <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
          <button onClick={() => submitOutcome('done')}
            style={{ padding:'13px', background:'linear-gradient(135deg,#00c87a,#00e5a0)',
              border:'none', borderRadius:12, color:'#262c36', fontSize:14, fontWeight:700, cursor:'pointer' }}>
            ✓ {t('Connected & Done')}
          </button>
          <button onClick={() => setShowCallLater(!showCallLater)}
            style={{ padding:'11px', background:'rgba(255,170,0,0.1)', border:'1px solid rgba(255,170,0,0.3)',
              borderRadius:12, color:'#ffaa00', cursor:'pointer', fontSize:13, fontWeight:500 }}>
            🕐 {t('Schedule Callback')}
          </button>
          {showCallLater && (
            <div style={{ background:'#2c333e', border:'1px solid #1e2230', borderRadius:12, padding:14, marginTop:2 }}>
              <div style={{ fontSize:11, color:'#667', marginBottom:10 }}>{t('Call back in…')}</div>
              {/* Day / Hours / Minutes digit boxes */}
              <div style={{ display:'flex', gap:10, marginBottom:12 }}>
                {[
                  { lbl:'Days',    val:offDays,  set:setOffDays,  max:30 },
                  { lbl:'Hours',   val:offHours, set:setOffHours, max:23 },
                  { lbl:'Minutes', val:offMins,  set:setOffMins,  max:59 },
                ].map(f => (
                  <div key={f.lbl} style={{ flex:1, textAlign:'center' }}>
                    <input type="number" min={0} max={f.max} value={f.val} placeholder="0"
                      onChange={e => f.set(e.target.value.replace(/[^0-9]/g,''))}
                      style={{ width:'100%', background:'#373f4d', border:'1px solid #626d80', borderRadius:10,
                        color:'#fff', fontSize:24, fontWeight:700, padding:'10px 0', textAlign:'center',
                        outline:'none', boxSizing:'border-box', MozAppearance:'textfield' as any }} />
                    <div style={{ fontSize:10, color:'#667', marginTop:4, textTransform:'uppercase', letterSpacing:.5 }}>{t(f.lbl)}</div>
                  </div>
                ))}
              </div>
              {/* Quick shortcuts */}
              <div style={{ display:'flex', gap:6, flexWrap:'wrap', marginBottom:12 }}>
                {[
                  { lbl:'+30 min',    d:0, h:0, m:30 },
                  { lbl:'+1 hour',    d:0, h:1, m:0 },
                  { lbl:'+2 hours',   d:0, h:2, m:0 },
                  { lbl:'+3 hours',   d:0, h:3, m:0 },
                  { lbl:'Tomorrow',   d:1, h:0, m:0 },
                  { lbl:'In 2 days',  d:2, h:0, m:0 },
                ].map(q => (
                  <button key={q.lbl} onClick={() => setQuick(q.d, q.h, q.m)}
                    style={{ padding:'6px 12px', background:'#373f4d', border:'1px solid #2a3142',
                      borderRadius:99, color:'#9fb0c0', fontSize:11, fontWeight:500, cursor:'pointer' }}>
                    {t(q.lbl)}
                  </button>
                ))}
              </div>
              {/* Preview + Set */}
              <div style={{ display:'flex', alignItems:'center', gap:10 }}>
                <div style={{ flex:1, fontSize:12, color: callbackDate ? '#ffaa00' : '#555' }}>
                  {callbackDate ? `📞 ${fmtDateTime(callbackDate.toISOString())}` : t('Enter a time or pick a shortcut')}
                </div>
                <button onClick={() => submitOutcome('call_later')} disabled={!callbackDate}
                  style={{ padding:'10px 20px', background: callbackDate ? '#ffaa00' : '#2a2a2a',
                    border:'none', borderRadius:8, color: callbackDate ? '#262c36' : '#666',
                    fontWeight:700, cursor: callbackDate ? 'pointer' : 'default', fontSize:13 }}>
                  {t('Set callback')}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}


// ── QUEUE PREVIEW PANEL ─────────────────────────────────────────────────────
function QueuePanel({ sessionId, onStart, onClose }: { sessionId: number, onStart: () => void, onClose: () => void }) {
  const t = useT();
  const [queue, setQueue] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Fetch the queue list
    const token = localStorage.getItem("token") || "";
    fetch(`${API}/dialer/session/${sessionId}/queue`, {
      headers: { Authorization: `Bearer ${token}` }
    }).then(r => r.json()).then(d => {
      setQueue(d.items || []);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, [sessionId]);

  return (
    <div style={{
      position: "fixed", top: 0, right: 0, bottom: 0, width: 340, zIndex: 99998,
      background: "#262c36", borderLeft: "1px solid #1e2230",
      display: "flex", flexDirection: "column",
      boxShadow: "-8px 0 40px rgba(0,0,0,0.6)"
    }}>
      {/* Header */}
      <div style={{ padding: "16px 20px", borderBottom: "1px solid #1e2230",
        display: "flex", alignItems: "center", justifyContent: "space-between", flexShrink: 0 }}>
        <div>
          <div style={{ fontSize: 15, fontWeight: 700, color: "#e0e0e0" }}>📞 {t('Power Dialer Queue')}</div>
          <div style={{ fontSize: 11, color: "#555", marginTop: 2 }}>{queue.length} {t('contacts to call')}</div>
        </div>
        <button onClick={onClose}
          style={{ background: "none", border: "none", color: "#555", cursor: "pointer", fontSize: 20 }}>✕</button>
      </div>

      {/* Queue list */}
      <div style={{ flex: 1, overflowY: "auto", padding: "8px 0" }}>
        {loading ? (
          <div style={{ padding: 20, textAlign: "center", color: "#555" }}>{t('Loading queue...')}</div>
        ) : queue.map((item: any, i: number) => (
          <div key={item.queue_id || i} style={{
            display: "flex", alignItems: "center", gap: 10, padding: "10px 20px",
            borderBottom: "1px solid #262c36", transition: "background .15s"
          }}>
            <div style={{ width: 24, height: 24, borderRadius: 6, background: "#373f4d",
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 11, color: "#555", fontWeight: 600, flexShrink: 0 }}>{i + 1}</div>
            <div style={{ width: 32, height: 32, borderRadius: 8,
              background: "linear-gradient(135deg,#003d9922,#0066ff22)",
              border: "1px solid #0066ff33",
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 13, fontWeight: 700, color: "#4d9fff", flexShrink: 0 }}>
              {item.name?.[0]?.toUpperCase() || "?"}
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: "#e0e0e0",
                overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{item.name || t("Unknown")}</div>
              <div style={{ fontSize: 11, color: "#555", fontFamily: "monospace" }}>{item.phone || "—"}</div>
            </div>
            <div style={{ textAlign: "right", flexShrink: 0 }}>
              <div style={{ fontSize: 11, color: "#00e5a0", fontWeight: 500 }}>${(item.balance || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}</div>
              <div style={{ fontSize: 10, color: "#555" }}>{item.country || ""}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Start button */}
      <div style={{ padding: "16px 20px", borderTop: "1px solid #1e2230", flexShrink: 0 }}>
        <button onClick={onStart}
          style={{ width: "100%", padding: "14px", background: "linear-gradient(135deg,#00c87a,#00e5a0)",
            border: "none", borderRadius: 12, color: "#262c36", fontSize: 15, fontWeight: 700,
            cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", gap: 8 }}>
          ▶ {t('Start Power Dialer')}
        </button>
        <div style={{ textAlign: "center", fontSize: 11, color: "#555", marginTop: 8 }}>
          {t('Will auto-call each contact in order')}
        </div>
      </div>
    </div>
  );
}

// ── MAIN DIALER WIDGET ──────────────────────────────────────────────────────
export function PowerDialerWidget({ sessionId, onClose }: { sessionId: number, onClose: () => void }) {
  const t = useT();
  const [current, setCurrent]     = useState<Client | null>(null);
  const [stats, setStats]         = useState({ pending:0, done:0, exhausted:0, total:0 });
  const [phase, setPhase]         = useState<'calling'|'answered'|'paused'|'done'>('calling');
  const [minimized, setMinimized] = useState(false);
  const [callingName, setCallingName] = useState('');
  const [dialResult, setDialResult] = useState<any>(null);
  const countdownRef = useRef<any>(null);
  const noAnswerRef  = useRef<any>(null);
  const runningRef   = useRef(true);

  const loadStats = useCallback(() => {
    apiGet(`/dialer/session/${sessionId}/stats`).then(setStats).catch(() => {});
  }, [sessionId]);

  // ── CALL NEXT — auto-dials the next contact server-side (auto-answer on the agent leg) ──
  // The backend picks the next contact, places the PBX call, and records it as this agent's
  // active call. The polling effect below then watches its live status: on a real ANSWER it
  // pops the card; on no-answer/off/rejected the worker auto-logs + reschedules and we advance.
  const callNext = useCallback(async () => {
    if (!runningRef.current) return;
    clearTimeout(noAnswerRef.current);
    await new Promise(r => setTimeout(r, 300));   // let reschedule writes settle
    const data = await apiPost(`/dialer/session/${sessionId}/auto-next`, {});
    if (data?.error === 'no_extension') {
      setDialResult({ ok: false, errmsg: data.errmsg || t('Set your PBX extension in Settings.') });
      runningRef.current = false; setPhase('paused'); return;
    }
    if (data?.done) { setPhase('done'); return; }
    setCurrent(data);
    setCallingName(data.name);
    setPhase('calling');
    // Dial is placed asynchronously server-side; show "dialing" optimistically. If it fails to
    // place, the /active-call poll returns 'dial_failed' and pauses with a message.
    setDialResult({ ok: true, caller: '' });
    loadStats();
  }, [sessionId, loadStats]);

  // Auto-start on mount
  useEffect(() => {
    runningRef.current = true;
    callNext();
    return () => {
      runningRef.current = false;
      clearTimeout(noAnswerRef.current);
      clearInterval(countdownRef.current);
    };
  }, [callNext]);

  // ── MANUAL OUTCOMES (while ringing) ────────────────────────────────────
  const manualOutcome = useCallback(async (outcome: 'no_answer'|'rejected'|'off') => {
    clearTimeout(noAnswerRef.current);
    if (!current) return;
    await apiPost('/dialer/call/result', {
      queue_id: current.queue_id, session_id: sessionId,
      login: current.login, lead_id: current.lead_id,
      outcome, comment: '',
    });
    loadStats();
    callNext(); // immediate — no delay
  }, [current, sessionId, loadStats, callNext]);

  // ── ANSWERED ────────────────────────────────────────────────────────────
  const handleAnswered = useCallback(() => {
    clearTimeout(noAnswerRef.current);
    playAnswerRing();   // ring so the agent knows the contact picked up
    setPhase('answered');
  }, []);

  // ── AFTER DONE / CALLBACK — go straight to the next call (no waiting) ────
  const handleDone = useCallback(() => {
    loadStats();
    callNext();
  }, [callNext, loadStats]);

  // ── AUTO-ADVANCE — poll the live call status while a call is ringing ──────
  // The event worker (dialer_events.py) updates the call's status from real PBX events:
  //   answered            -> pop the customer card + ring the agent
  //   no_answer/off/reject -> it already auto-logged + rescheduled; we just move to the next.
  // If the worker is down, status stays 'ringing' and the agent uses the manual buttons below
  // (graceful fallback — nothing breaks, it just isn't automatic).
  useEffect(() => {
    if (phase !== 'calling') return;
    const iv = setInterval(async () => {
      if (!runningRef.current) return;
      let st: any;
      try { st = await apiGet('/dialer/active-call'); } catch { return; }
      if (!st || !st.status) return;
      if (st.status === 'answered') {
        handleAnswered();
      } else if (st.status === 'no_answer' || st.status === 'rejected' || st.status === 'off') {
        loadStats();
        callNext();
      } else if (st.status === 'agent_no_answer' || st.status === 'dial_failed') {
        // The AGENT's own phone didn't take the call (auto-answer off / busy / declined) — the
        // customer was never dialed. Don't advance (that would burn the queue); pause and tell
        // the agent to fix their phone, then Resume retries.
        runningRef.current = false;
        setDialResult({ ok: false, errmsg: t("Your phone didn't pick up the call. Turn on auto-answer in Linkus (or accept the call on your phone), then press Resume.") });
        setPhase('paused');
      }
    }, 1500);
    return () => clearInterval(iv);
  }, [phase, handleAnswered, callNext, loadStats]);

  const stopDialer = async () => {
    runningRef.current = false;
    clearTimeout(noAnswerRef.current);
    clearInterval(countdownRef.current);
    await apiPost(`/dialer/session/${sessionId}/stop`, {});
    onClose();
  };

  const progress = stats.total > 0
    ? Math.round(((stats.done + stats.exhausted) / stats.total) * 100) : 0;

  // shared style for the small secondary outcome buttons
  const secBtn = (c: string): React.CSSProperties => ({
    padding: '9px 4px', background: `${c}14`, border: `1px solid ${c}33`, borderRadius: 9,
    color: c, cursor: 'pointer', fontSize: 11, fontWeight: 600, fontFamily: 'inherit',
    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4, whiteSpace: 'nowrap',
  });

  // ── MINIMIZED ───────────────────────────────────────────────────────────
  if (minimized) return (
    <div onClick={() => setMinimized(false)} style={{ position:'fixed', top:70, right:20, zIndex:99999,
      background:'#2c333e', border:'1px solid #00e5a0', borderRadius:12, padding:'10px 18px',
      cursor:'pointer', display:'flex', alignItems:'center', gap:10,
      boxShadow:'0 4px 20px rgba(0,229,160,0.2)' }}>
      <div style={{ width:8, height:8, borderRadius:99,
        background: phase==='calling'?'#ffaa00':phase==='answered'?'#00e5a0':'#555',
        animation: phase==='calling'||phase==='answered' ? 'pulse 1s infinite' : '' }} />
      <span style={{ fontSize:12, color:'#e0e0e0' }}>
        {phase==='calling'   ? `📞 ${t('Calling')} ${callingName}...` :
         phase==='answered'  ? `🟢 ${t('On call with')} ${callingName}` :
         phase==='paused'    ? '⏸ ' + t('Dialer paused') : '✓ ' + t('Done')}
      </span>
      <span style={{ fontSize:10, color:'#555' }}>{stats.done}/{stats.total}</span>
    </div>
  );

  return (
    <>
      {/* Answered big popup */}
      {phase === 'answered' && current && (
        <AnsweredPopup
          client={current}
          sessionId={sessionId}
          onDone={handleDone}
          onCallLater={handleDone}
        />
      )}

      {/* Floating dialer widget */}
      <div style={{ position:'fixed', top:70, right:20, zIndex:99998, width:320,
        background:'#262c36', border:'1px solid #1e2230', borderRadius:16,
        boxShadow:'0 8px 40px rgba(0,0,0,0.7)', overflow:'hidden' }}>

        {/* Header */}
        <div style={{ background:'linear-gradient(135deg,#0a1628,#111827)', padding:'10px 14px',
          borderBottom:'1px solid #1e2230', display:'flex', alignItems:'center', justifyContent:'space-between' }}>
          <div style={{ display:'flex', alignItems:'center', gap:8 }}>
            <div style={{ width:8, height:8, borderRadius:99,
              background: phase==='calling'?'#ffaa00':phase==='answered'?'#00e5a0':'#555',
              boxShadow: phase==='calling'?'0 0 6px #ffaa00':phase==='answered'?'0 0 6px #00e5a0':'' }} />
            <span style={{ fontSize:13, fontWeight:600, color:'#e0e0e0' }}>{t('Power Dialer')}</span>
          </div>
          <div style={{ display:'flex', gap:4 }}>
            {phase === 'calling' && (
              <button onClick={() => { runningRef.current = false; clearTimeout(noAnswerRef.current); setPhase('paused'); }}
                style={{ background:'none', border:'none', color:'#555', cursor:'pointer', fontSize:13, padding:'0 6px' }}>⏸</button>
            )}
            <button onClick={() => setMinimized(true)}
              style={{ background:'none', border:'none', color:'#555', cursor:'pointer', fontSize:16, padding:'0 4px' }}>−</button>
            <button onClick={stopDialer}
              style={{ background:'none', border:'none', color:'#555', cursor:'pointer', fontSize:16, padding:'0 4px' }}>✕</button>
          </div>
        </div>

        {/* Progress bar */}
        <div style={{ height:3, background:'#373f4d' }}>
          <div style={{ height:'100%', background:'#00e5a0', width:`${progress}%`, transition:'width .5s' }} />
        </div>

        {/* Stats */}
        <div style={{ display:'flex', padding:'10px 6px', borderBottom:'1px solid #373f4d' }}>
          {([['Done', stats.done, '#00e5a0'], ['Pending', stats.pending, '#9aa3b2'],
             ['No ans.', stats.exhausted, '#ff5d6c'], ['Progress', `${progress}%`, '#4d9fff']] as [string, any, string][])
            .map(([l,v,c],i)=>(
            <div key={i} style={{ flex:1, textAlign:'center', borderRight: i<3 ? '1px solid #16181e' : 'none' }}>
              <div style={{ fontSize:16, fontWeight:700, color:c }}>{v}</div>
              <div style={{ fontSize:9, color:'#667', textTransform:'uppercase', letterSpacing:.4, marginTop:2 }}>{t(l)}</div>
            </div>
          ))}
        </div>

        {/* Current client mini card */}
        {current && (
          <div style={{ padding:'10px 14px', borderBottom:'1px solid #373f4d' }}>
            <div style={{ display:'flex', alignItems:'center', gap:8 }}>
              <div style={{ width:32, height:32, borderRadius:8, background:'linear-gradient(135deg,#003d9922,#0066ff22)',
                border:'1px solid #0066ff33', display:'flex', alignItems:'center', justifyContent:'center',
                fontSize:14, fontWeight:700, color:'#4d9fff' }}>
                {current.name?.[0]?.toUpperCase()}
              </div>
              <div style={{ flex:1, minWidth:0 }}>
                <div style={{ fontSize:12, fontWeight:600, color:'#e0e0e0', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{current.name}</div>
                <div style={{ fontSize:11, color:'#555', fontFamily:'monospace' }}>{current.phone}</div>
              </div>
              {(current.attempt||0) > 0 && (
                <span style={{ fontSize:10, padding:'2px 6px', borderRadius:99, background:'rgba(255,170,0,0.1)', color:'#ffaa00' }}>
                  {t('Att.')}{(current.attempt||0)+1}
                </span>
              )}
            </div>
          </div>
        )}

        {/* CALLING phase */}
        {phase === 'calling' && (
          <div style={{ padding:'12px 14px 14px' }}>
            <div style={{ textAlign:'center', color:'#ffaa00', fontSize:12, marginBottom:8,
              animation:'pulse 1.5s infinite' }}>
              🔔 {t('Ringing')} {current?.name?.split(' ')[0]}…
            </div>
            {/* PBX result so the agent knows the call really went out */}
            {dialResult && (dialResult.ok
              ? <div style={{ textAlign:'center', fontSize:11, color:'#00e5a0', marginBottom:12 }}>
                  📞 {t('Auto-dialing — your headset connects automatically. Waiting for answer…')}
                </div>
              : <div style={{ textAlign:'center', fontSize:11, color:'#ff5d6c', marginBottom:12,
                  background:'rgba(255,93,108,0.1)', border:'1px solid rgba(255,93,108,0.3)', borderRadius:8, padding:'6px 8px' }}>
                  ⚠ {t('Call not placed:')} {dialResult.errmsg || t('PBX rejected')}
                </div>
            )}
            <div style={{ textAlign:'center', fontSize:10, color:'#667', marginBottom:8 }}>
              {t("Advances automatically on the outcome. Use the buttons only if it doesn't.")}
            </div>
            <button onClick={handleAnswered}
              style={{ width:'100%', padding:'13px', background:'linear-gradient(135deg,#00c87a,#00e5a0)',
                border:'none', borderRadius:12, color:'#262c36', fontSize:14, fontWeight:700,
                cursor:'pointer', marginBottom:8, fontFamily:'inherit' }}>
              ✓ {t('Answered')}
            </button>
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr 1fr', gap:6 }}>
              <button onClick={() => manualOutcome('no_answer')} style={secBtn('#9aa3b2')}>✗ {t('No answer')}</button>
              <button onClick={() => manualOutcome('rejected')} style={secBtn('#ff5d6c')}>🚫 {t('Rejected')}</button>
              <button onClick={() => manualOutcome('off')} style={secBtn('#888')}>📵 {t('Off')}</button>
            </div>
            {/* #256 — previous comments for the CURRENT contact, switching automatically */}
            <ContactComments contact={current} />
          </div>
        )}

        {/* PAUSED phase */}
        {phase === 'paused' && (
          <div style={{ padding:'14px', textAlign:'center' }}>
            <div style={{ color:'#9aa3b2', fontSize:12, marginBottom:12 }}>⏸ {t('Dialer paused')}</div>
            {dialResult && !dialResult.ok && dialResult.errmsg && (
              <div style={{ fontSize:11, color:'#ff5d6c', marginBottom:12, lineHeight:1.5,
                background:'rgba(255,93,108,0.1)', border:'1px solid rgba(255,93,108,0.3)', borderRadius:8, padding:'8px 10px' }}>
                ⚠ {dialResult.errmsg}
              </div>
            )}
            <button onClick={() => { runningRef.current = true; callNext(); }}
              style={{ width:'100%', padding:'13px', background:'linear-gradient(135deg,#00c87a,#00e5a0)',
                border:'none', borderRadius:12, color:'#262c36', cursor:'pointer', fontSize:14, fontWeight:700, fontFamily:'inherit' }}>
              ▶ {t('Resume dialing')}
            </button>
          </div>
        )}

        {/* DONE phase */}
        {phase === 'done' && (
          <div style={{ padding:'20px 14px 16px', textAlign:'center' }}>
            <div style={{ fontSize:28, marginBottom:6 }}>🎉</div>
            <div style={{ fontSize:15, fontWeight:700, color:'#00e5a0', marginBottom:4 }}>{t('Batch complete')}</div>
            <div style={{ fontSize:11, color:'#667', marginBottom:8 }}>
              {stats.done} {t('connected')} · {stats.exhausted} {t('unreachable')}
            </div>
            <div style={{ fontSize:11, color:'#9aa3b2', marginBottom:14 }}>
              {t('Close and press')} <b>{t('Power Dial')}</b> {t('again for the next 20.')}
            </div>
            <button onClick={onClose}
              style={{ width:'100%', padding:'11px', background:'#373f4d', border:'1px solid #2a2f3a',
                borderRadius:10, color:'#9aa3b2', cursor:'pointer', fontSize:13, fontWeight:600, fontFamily:'inherit' }}>
              {t('Close')}
            </button>
          </div>
        )}

        <style>{`@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }`}</style>
      </div>
    </>
  );
}

// ── LAUNCHER ────────────────────────────────────────────────────────────────
// ── MAINTENANCE GATE ─────────────────────────────────────────────────────────
// Power Dialer is temporarily disabled everywhere (user request, Jul 20 2026).
// Flip to false to re-enable — the button then works exactly as before.
const DIALER_MAINTENANCE = true;

export function DialerLauncher({ fetchAllLogins, source = 'clients' }:
  { fetchAllLogins: () => Promise<number[]>, source?: string }) {
  const t = useT();
  const [sessionId, setSessionId]       = useState<number | null>(null);
  const [showQueue, setShowQueue]       = useState(false);
  const [dialerActive, setDialerActive] = useState(false);
  const [loading, setLoading]           = useState(false);
  const [count, setCount]               = useState<number|null>(null);
  const [showMaint, setShowMaint]       = useState(false);

  const openQueue = async () => {
    if (DIALER_MAINTENANCE) { setShowMaint(true); return; }
    setLoading(true);
    try {
      const ids = await fetchAllLogins();
      if (!ids.length) { setLoading(false); return; }
      setCount(ids.length);
      const body = source === 'leads'
        ? { lead_ids: ids, source: 'leads' }
        : { logins: ids, source: 'clients' };
      const data = await apiPost('/dialer/session/start', body);
      if (data.session_id) {
        setSessionId(data.session_id);
        setDialerActive(true);   // dial straight away — no preview/confirm step
      }
    } catch (e) { console.error(e); }
    setLoading(false);
  };

  // Step 2: sales clicks Start → hide queue, show dialer
  const startDialer = () => {
    setShowQueue(false);
    setDialerActive(true);
  };

  const closeAll = async () => {
    if (sessionId) await apiPost(`/dialer/session/${sessionId}/stop`, {});
    setShowQueue(false);
    setDialerActive(false);
    setSessionId(null);
  };

  return (
    <>
      <button onClick={openQueue} disabled={loading || showQueue || dialerActive}
        style={{ display:'flex', alignItems:'center', gap:6, padding:'7px 14px',
          background: 'linear-gradient(135deg,#00c87a,#00e5a0)',
          border:'none', borderRadius:10,
          color: '#262c36',
          cursor: loading ? 'not-allowed' : 'pointer',
          fontSize:12, fontWeight:700, transition:'all .2s' }}>
        {loading ? '⟳' : '📞'} {loading ? t('Loading all...') : count ? `${t('Power Dial')} (${count})` : t('Power Dial')}
      </button>

      {/* Queue preview panel */}
      {showQueue && sessionId && (
        <QueuePanel
          sessionId={sessionId}
          onStart={startDialer}
          onClose={closeAll}
        />
      )}

      {/* Active dialer widget */}
      {dialerActive && sessionId && (
        <PowerDialerWidget sessionId={sessionId} onClose={closeAll} />
      )}

      {/* Maintenance popup */}
      {showMaint && (
        <div onClick={() => setShowMaint(false)}
          style={{ position: 'fixed', inset: 0, background: 'rgba(2,6,23,.6)', zIndex: 2000,
                   display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div onClick={e => e.stopPropagation()}
            style={{ background: 'var(--bg-card,#2c333e)', color: 'var(--text,#e6e9ef)',
                     border: '1px solid var(--border,#4f596b)', borderRadius: 16,
                     padding: '28px 34px', maxWidth: 380, textAlign: 'center',
                     boxShadow: '0 20px 60px rgba(0,0,0,.5)' }}>
            <div style={{ fontSize: 42, marginBottom: 10 }}>🛠️</div>
            <div style={{ fontSize: 17, fontWeight: 800, marginBottom: 6 }}>{t('Power Dialer — Under Maintenance')}</div>
            <div style={{ fontSize: 13, color: 'var(--text2,#8a93a3)', lineHeight: 1.7, marginBottom: 4 }}>
              {t('This feature is temporarily unavailable while we work on it.')}
            </div>
            <div style={{ fontSize: 13, color: 'var(--text2,#8a93a3)', lineHeight: 1.7, direction: 'rtl' }}>
              هذه الميزة قيد الصيانة مؤقتاً — ستعود قريباً.
            </div>
            <button onClick={() => setShowMaint(false)}
              style={{ marginTop: 16, border: 'none', background: 'linear-gradient(135deg,#2563eb,#7c3aed)',
                       color: '#fff', borderRadius: 10, padding: '9px 26px', cursor: 'pointer',
                       fontSize: 13.5, fontWeight: 700 }}>
              {t('OK')}
            </button>
          </div>
        </div>
      )}
    </>
  );
}

export default PowerDialerWidget;

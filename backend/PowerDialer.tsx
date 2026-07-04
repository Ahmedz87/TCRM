import React, { useState, useEffect, useRef, useCallback } from 'react';

const API = 'http://127.0.0.1:8000';

function getYeastar() {
  return {
    url:   localStorage.getItem('yeastarUrl')   || 'http://YOUR_YEASTAR_IP:8088',
    token: localStorage.getItem('yeastarToken') || 'TOKEN',
    ext:   localStorage.getItem('yeastarExtension') || '100',
  };
}

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

async function yeastarCall(phone: string) {
  const clean = phone.replace(/[^0-9+]/g, '');
  const { url, token, ext } = getYeastar();
  try {
    const res = await fetch(`${url}/api/v1.1.0/call/dial?token=${token}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ caller: ext, callee: clean })
    });
    return res.ok;
  } catch {
    window.open(`tel:${clean}`);
    return true;
  }
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
}

// ── BIG ANSWERED POPUP ──────────────────────────────────────────────────────
function AnsweredPopup({ client, sessionId, onDone, onCallLater }: any) {
  const [comment, setComment]           = useState('');
  const [showCallLater, setShowCallLater] = useState(false);
  const [callLaterDate, setCallLaterDate] = useState('');
  const [callLaterTime, setCallLaterTime] = useState('');
  const [duration, setDuration]           = useState(0);

  useEffect(() => {
    const t = setInterval(() => setDuration(d => d + 1), 1000);
    return () => clearInterval(t);
  }, []);

  const submitOutcome = async (outcome: string) => {
    const call_later_at = outcome === 'call_later' && callLaterDate && callLaterTime
      ? `${callLaterDate}T${callLaterTime}:00` : undefined;
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
      <div style={{ background:'#0d0f14', border:'1px solid rgba(0,229,160,0.3)', borderRadius:20,
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
            <div style={{ fontSize:11, color:'#555' }}>On call</div>
          </div>
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
            <div key={s.label} style={{ background:'#111318', borderRadius:10, padding:'10px 12px', textAlign:'center' }}>
              <div style={{ fontSize:15, fontWeight:600, color:s.color }}>{s.value}</div>
              <div style={{ fontSize:10, color:'#555', marginTop:2 }}>{s.label}</div>
            </div>
          ))}
        </div>

        {/* Notes */}
        <div style={{ marginBottom:16 }}>
          <div style={{ fontSize:11, color:'#555', marginBottom:6 }}>Call notes</div>
          <textarea value={comment} onChange={e => setComment(e.target.value)}
            placeholder="What did you discuss? Any follow-up needed?"
            style={{ width:'100%', background:'#111318', border:'1px solid #1e2230', borderRadius:10,
              color:'#e0e0e0', fontSize:13, padding:'12px', resize:'none', outline:'none',
              height:80, fontFamily:'inherit', boxSizing:'border-box' }} />
        </div>

        {/* Actions */}
        <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
          <button onClick={() => submitOutcome('done')}
            style={{ padding:'13px', background:'linear-gradient(135deg,#00c87a,#00e5a0)',
              border:'none', borderRadius:12, color:'#0d0f14', fontSize:14, fontWeight:700, cursor:'pointer' }}>
            ✓ Connected & Done — Next call in 9s
          </button>
          <button onClick={() => setShowCallLater(!showCallLater)}
            style={{ padding:'11px', background:'rgba(255,170,0,0.1)', border:'1px solid rgba(255,170,0,0.3)',
              borderRadius:12, color:'#ffaa00', cursor:'pointer', fontSize:13, fontWeight:500 }}>
            🕐 Schedule Callback
          </button>
          {showCallLater && (
            <div style={{ display:'flex', gap:8, alignItems:'center' }}>
              <input type="date" value={callLaterDate} onChange={e => setCallLaterDate(e.target.value)}
                style={{ flex:1, background:'#1a1d24', border:'1px solid #333', borderRadius:8,
                  color:'#e0e0e0', fontSize:12, padding:'8px', outline:'none' }} />
              <input type="time" value={callLaterTime} onChange={e => setCallLaterTime(e.target.value)}
                style={{ flex:1, background:'#1a1d24', border:'1px solid #333', borderRadius:8,
                  color:'#e0e0e0', fontSize:12, padding:'8px', outline:'none' }} />
              <button onClick={() => submitOutcome('call_later')}
                style={{ padding:'8px 14px', background:'#ffaa00', border:'none', borderRadius:8,
                  color:'#0d0f14', fontWeight:700, cursor:'pointer', fontSize:12 }}>
                Set
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}


// ── QUEUE PREVIEW PANEL ─────────────────────────────────────────────────────
function QueuePanel({ sessionId, onStart, onClose }: { sessionId: number, onStart: () => void, onClose: () => void }) {
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
      background: "#0d0f14", borderLeft: "1px solid #1e2230",
      display: "flex", flexDirection: "column",
      boxShadow: "-8px 0 40px rgba(0,0,0,0.6)"
    }}>
      {/* Header */}
      <div style={{ padding: "16px 20px", borderBottom: "1px solid #1e2230",
        display: "flex", alignItems: "center", justifyContent: "space-between", flexShrink: 0 }}>
        <div>
          <div style={{ fontSize: 15, fontWeight: 700, color: "#e0e0e0" }}>📞 Power Dialer Queue</div>
          <div style={{ fontSize: 11, color: "#555", marginTop: 2 }}>{queue.length} contacts to call</div>
        </div>
        <button onClick={onClose}
          style={{ background: "none", border: "none", color: "#555", cursor: "pointer", fontSize: 20 }}>✕</button>
      </div>

      {/* Queue list */}
      <div style={{ flex: 1, overflowY: "auto", padding: "8px 0" }}>
        {loading ? (
          <div style={{ padding: 20, textAlign: "center", color: "#555" }}>Loading queue...</div>
        ) : queue.map((item: any, i: number) => (
          <div key={item.queue_id || i} style={{
            display: "flex", alignItems: "center", gap: 10, padding: "10px 20px",
            borderBottom: "1px solid #0f1117", transition: "background .15s"
          }}>
            <div style={{ width: 24, height: 24, borderRadius: 6, background: "#1a1d24",
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
                overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{item.name || "Unknown"}</div>
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
            border: "none", borderRadius: 12, color: "#0d0f14", fontSize: 15, fontWeight: 700,
            cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", gap: 8 }}>
          ▶ Start Power Dialer
        </button>
        <div style={{ textAlign: "center", fontSize: 11, color: "#555", marginTop: 8 }}>
          Will auto-call each contact in order
        </div>
      </div>
    </div>
  );
}

// ── MAIN DIALER WIDGET ──────────────────────────────────────────────────────
export function PowerDialerWidget({ sessionId, onClose }: { sessionId: number, onClose: () => void }) {
  const [current, setCurrent]     = useState<Client | null>(null);
  const [stats, setStats]         = useState({ pending:0, done:0, exhausted:0, total:0 });
  const [phase, setPhase]         = useState<'calling'|'answered'|'countdown'|'paused'|'done'>('calling');
  const [countdown, setCountdown] = useState(9);
  const [minimized, setMinimized] = useState(false);
  const [callingName, setCallingName] = useState('');
  const countdownRef = useRef<any>(null);
  const noAnswerRef  = useRef<any>(null);
  const runningRef   = useRef(true);

  const loadStats = useCallback(() => {
    apiGet(`/dialer/session/${sessionId}/stats`).then(setStats).catch(() => {});
  }, [sessionId]);

  // ── CALL NEXT — always re-queries so rescheduled/high-score clients jump to top ──
  const callNext = useCallback(async () => {
    if (!runningRef.current) return;
    clearTimeout(noAnswerRef.current);
    // Small pause to let DB update (reschedule writes) settle
    await new Promise(r => setTimeout(r, 300));
    const data = await apiGet(`/dialer/session/${sessionId}/next`);
    if (data.done) { setPhase('done'); return; }
    setCurrent(data);
    setCallingName(data.name);
    setPhase('calling');
    loadStats();
    await yeastarCall(data.phone);

    // Auto no-answer after 30 seconds
    noAnswerRef.current = setTimeout(async () => {
      if (!runningRef.current) return;
      await apiPost('/dialer/call/result', {
        queue_id: data.queue_id, session_id: sessionId,
        login: data.login, lead_id: data.lead_id,
        outcome: 'no_answer', comment: '',
      });
      loadStats();
      callNext();
    }, 30000);
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
    setPhase('answered');
  }, []);

  // ── AFTER DONE (with comment) ───────────────────────────────────────────
  const handleDone = useCallback(() => {
    loadStats();
    setPhase('countdown');
    setCountdown(9);
    countdownRef.current = setInterval(() => {
      setCountdown(prev => {
        if (prev <= 1) {
          clearInterval(countdownRef.current);
          callNext();
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
  }, [callNext, loadStats]);

  const skipCountdown = useCallback(() => {
    clearInterval(countdownRef.current);
    callNext();
  }, [callNext]);

  const stopDialer = async () => {
    runningRef.current = false;
    clearTimeout(noAnswerRef.current);
    clearInterval(countdownRef.current);
    await apiPost(`/dialer/session/${sessionId}/stop`, {});
    onClose();
  };

  const progress = stats.total > 0
    ? Math.round(((stats.done + stats.exhausted) / stats.total) * 100) : 0;

  // ── MINIMIZED ───────────────────────────────────────────────────────────
  if (minimized) return (
    <div onClick={() => setMinimized(false)} style={{ position:'fixed', bottom:20, right:20, zIndex:99999,
      background:'#111318', border:'1px solid #00e5a0', borderRadius:12, padding:'10px 18px',
      cursor:'pointer', display:'flex', alignItems:'center', gap:10,
      boxShadow:'0 4px 20px rgba(0,229,160,0.2)' }}>
      <div style={{ width:8, height:8, borderRadius:99,
        background: phase==='calling'?'#ffaa00':phase==='answered'?'#00e5a0':phase==='countdown'?'#4d9fff':'#555',
        animation: phase==='calling'||phase==='answered' ? 'pulse 1s infinite' : '' }} />
      <span style={{ fontSize:12, color:'#e0e0e0' }}>
        {phase==='calling'   ? `📞 Calling ${callingName}...` :
         phase==='answered'  ? `🟢 On call with ${callingName}` :
         phase==='countdown' ? `⏱ Next call in ${countdown}s` :
         phase==='paused'    ? '⏸ Dialer paused' : '✓ Done'}
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
      <div style={{ position:'fixed', bottom:20, right:20, zIndex:99998, width:320,
        background:'#0d0f14', border:'1px solid #1e2230', borderRadius:16,
        boxShadow:'0 8px 40px rgba(0,0,0,0.7)', overflow:'hidden' }}>

        {/* Header */}
        <div style={{ background:'linear-gradient(135deg,#0a1628,#111827)', padding:'10px 14px',
          borderBottom:'1px solid #1e2230', display:'flex', alignItems:'center', justifyContent:'space-between' }}>
          <div style={{ display:'flex', alignItems:'center', gap:8 }}>
            <div style={{ width:8, height:8, borderRadius:99,
              background: phase==='calling'?'#ffaa00':phase==='answered'?'#00e5a0':phase==='countdown'?'#4d9fff':'#555',
              boxShadow: phase==='calling'?'0 0 6px #ffaa00':phase==='answered'?'0 0 6px #00e5a0':'' }} />
            <span style={{ fontSize:13, fontWeight:600, color:'#e0e0e0' }}>Power Dialer</span>
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
        <div style={{ height:3, background:'#1a1d24' }}>
          <div style={{ height:'100%', background:'#00e5a0', width:`${progress}%`, transition:'width .5s' }} />
        </div>

        {/* Stats */}
        <div style={{ display:'flex', justifyContent:'space-between', padding:'8px 14px', borderBottom:'1px solid #1a1d24' }}>
          {[['Done', stats.done, '#00e5a0'], ['Pending', stats.pending, '#888'], ['No ans.', stats.exhausted, '#ff4d4d'], [`${progress}%`, 0, '#555']].map(([l,v,c],i)=>(
            <div key={i} style={{ textAlign:'center' }}>
              <div style={{ fontSize:15, fontWeight:600, color:c as string }}>{i<3?v:''}{i===3?l:''}</div>
              <div style={{ fontSize:10, color:'#555' }}>{i<3?l:'Progress'}</div>
            </div>
          ))}
        </div>

        {/* Current client mini card */}
        {current && (
          <div style={{ padding:'10px 14px', borderBottom:'1px solid #1a1d24' }}>
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
                  Att.{(current.attempt||0)+1}
                </span>
              )}
            </div>
          </div>
        )}

        {/* CALLING phase */}
        {phase === 'calling' && (
          <div style={{ padding:'12px 14px' }}>
            <div style={{ textAlign:'center', color:'#ffaa00', fontSize:12, marginBottom:10,
              animation:'pulse 1.5s infinite' }}>
              🔔 Ringing {current?.name?.split(' ')[0]}...
            </div>
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:6, marginBottom:6 }}>
              <button onClick={handleAnswered}
                style={{ padding:'10px', background:'rgba(0,229,160,0.12)', border:'1px solid rgba(0,229,160,0.3)',
                  borderRadius:10, color:'#00e5a0', cursor:'pointer', fontSize:12, fontWeight:600 }}>
                ✓ Answered
              </button>
              <button onClick={() => manualOutcome('no_answer')}
                style={{ padding:'10px', background:'rgba(100,100,100,0.1)', border:'1px solid #333',
                  borderRadius:10, color:'#888', cursor:'pointer', fontSize:12 }}>
                ✗ No answer
              </button>
            </div>
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:6 }}>
              <button onClick={() => manualOutcome('rejected')}
                style={{ padding:'8px', background:'rgba(255,77,77,0.08)', border:'1px solid rgba(255,77,77,0.2)',
                  borderRadius:10, color:'#ff4d4d', cursor:'pointer', fontSize:11 }}>
                🚫 Rejected
              </button>
              <button onClick={() => manualOutcome('off')}
                style={{ padding:'8px', background:'rgba(100,100,100,0.08)', border:'1px solid #2a2a2a',
                  borderRadius:10, color:'#666', cursor:'pointer', fontSize:11 }}>
                📵 Phone off
              </button>
            </div>
          </div>
        )}

        {/* COUNTDOWN phase */}
        {phase === 'countdown' && (
          <div style={{ padding:'16px 14px', textAlign:'center' }}>
            <div style={{ fontSize:11, color:'#555', marginBottom:6 }}>Next call in</div>
            <div style={{ fontSize:40, fontWeight:700, color:'#00e5a0', fontFamily:'monospace',
              textShadow:'0 0 20px rgba(0,229,160,0.4)', lineHeight:1 }}>{countdown}</div>
            <button onClick={skipCountdown}
              style={{ marginTop:10, padding:'7px 20px', background:'#1a1d24', border:'1px solid #333',
                borderRadius:8, color:'#888', cursor:'pointer', fontSize:12 }}>
              Skip →
            </button>
          </div>
        )}

        {/* PAUSED phase */}
        {phase === 'paused' && (
          <div style={{ padding:'14px', textAlign:'center' }}>
            <div style={{ color:'#888', fontSize:12, marginBottom:10 }}>Dialer paused</div>
            <button onClick={() => { runningRef.current = true; callNext(); }}
              style={{ padding:'10px 24px', background:'rgba(0,229,160,0.1)', border:'1px solid rgba(0,229,160,0.3)',
                borderRadius:10, color:'#00e5a0', cursor:'pointer', fontSize:13, fontWeight:600 }}>
              ▶ Resume
            </button>
          </div>
        )}

        {/* DONE phase */}
        {phase === 'done' && (
          <div style={{ padding:'20px 14px', textAlign:'center' }}>
            <div style={{ fontSize:26, marginBottom:6 }}>🎉</div>
            <div style={{ fontSize:14, fontWeight:600, color:'#00e5a0', marginBottom:4 }}>Session Complete!</div>
            <div style={{ fontSize:11, color:'#555', marginBottom:14 }}>
              {stats.done} connected · {stats.exhausted} unreachable
            </div>
            <button onClick={onClose}
              style={{ padding:'8px 22px', background:'#1a1d24', border:'1px solid #333',
                borderRadius:8, color:'#888', cursor:'pointer', fontSize:12 }}>
              Close
            </button>
          </div>
        )}

        <style>{`@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }`}</style>
      </div>
    </>
  );
}

// ── LAUNCHER ────────────────────────────────────────────────────────────────
export function DialerLauncher({ fetchAllLogins, source = 'clients' }:
  { fetchAllLogins: () => Promise<number[]>, source?: string }) {
  const [sessionId, setSessionId]       = useState<number | null>(null);
  const [showQueue, setShowQueue]       = useState(false);
  const [dialerActive, setDialerActive] = useState(false);
  const [loading, setLoading]           = useState(false);
  const [count, setCount]               = useState<number|null>(null);

  const openQueue = async () => {
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
        setShowQueue(true);
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
          color: '#0d0f14',
          cursor: loading ? 'not-allowed' : 'pointer',
          fontSize:12, fontWeight:700, transition:'all .2s' }}>
        {loading ? '⟳' : '📞'} {loading ? 'Loading all...' : count ? `Power Dial (${count})` : 'Power Dial'}
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
    </>
  );
}

export default PowerDialerWidget;

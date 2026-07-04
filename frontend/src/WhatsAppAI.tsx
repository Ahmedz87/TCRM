import React, { useState, useEffect, useCallback } from 'react';
import { apiGet, apiPost, apiPatch, apiDelete } from './api';

// ── WhatsApp AI assistant (Wati) ────────────────────────────────────────────
// Dry-run/preview: a live Simulator that resolves the sender's identity, generates the AI
// reply, and shows the CRM auto-actions it WOULD take. Sends nothing until Wati is connected
// & the LIVE switch is on.

const card: React.CSSProperties = { background: 'var(--bg-card,#2c333e)', border: '1px solid var(--border,#4f596b)', borderRadius: 12, padding: 18 };
const cap: React.CSSProperties = { fontSize: 11, color: '#8a93a5', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 12, fontWeight: 700 };
const input: React.CSSProperties = { padding: '9px 11px', background: '#1c2231', border: '1px solid #3a4252', borderRadius: 8, color: '#e6e9ef', fontSize: 13 };
const btn = (bg: string, fg = '#06251b'): React.CSSProperties => ({ padding: '9px 14px', background: bg, border: 'none', borderRadius: 8, color: fg, fontSize: 13, fontWeight: 700, cursor: 'pointer' });

const ACTION_LABEL: any = {
  phone_verified: '📞 Phone verified', ai_owned: '🤖 AI owns lead (no human dials)',
  source_whatsapp: '🏷️ Source = WhatsApp', qualified: '🎯 Profile captured',
  lead_created: '✨ New lead created', escalated_to_human: '🙋 Handed to human', opt_out: '🚫 Opted out',
};

export default function WhatsAppAI() {
  const [status, setStatus] = useState<any>(null);
  const [tab, setTab] = useState<'simulator' | 'conversations' | 'training' | 'settings'>('simulator');

  const load = useCallback(() => { apiGet('/wati/status').then(setStatus).catch(() => {}); }, []);
  useEffect(() => { load(); }, [load]);
  const cfg = status?.config || {};

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      {/* status strip */}
      <div style={{ ...card, display: 'flex', gap: 18, flexWrap: 'wrap', alignItems: 'center' }}>
        <Badge ok={status?.ai_configured} on="AI brain ready" off="AI not configured" />
        <Badge ok={status?.connected} on="Wati connected" off="Wati not connected" />
        <Badge ok={cfg.enabled} on="LIVE — sending on" off="Preview — not sending" warnOff />
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 16, fontSize: 12, color: '#8a93a5' }}>
          <span>💬 {status?.stats?.conversations ?? 0} chats</span>
          <span>🤖 {status?.stats?.ai_replies ?? 0} AI replies</span>
          <span>🏷️ {status?.stats?.wa_leads ?? 0} WA leads</span>
          <span>🙋 {status?.stats?.escalated ?? 0} escalated</span>
        </div>
      </div>

      <div style={{ display: 'flex', gap: 8 }}>
        {(['simulator', 'conversations', 'training', 'settings'] as const).map(t => (
          <button key={t} onClick={() => setTab(t)} style={{ ...btn(tab === t ? '#00e5a022' : '#2c333e', tab === t ? '#00e5a0' : '#9aa3b3'), border: '1px solid ' + (tab === t ? '#00e5a055' : '#3a4252'), textTransform: 'capitalize' }}>{t === 'training' ? '🎓 Train' : t}</button>
        ))}
      </div>

      {tab === 'simulator' && <Simulator aiOk={status?.ai_configured} />}
      {tab === 'conversations' && <Conversations />}
      {tab === 'training' && <Training />}
      {tab === 'settings' && <Settings cfg={cfg} onSaved={load} />}
    </div>
  );
}

function Badge({ ok, on, off, warnOff }: { ok: boolean; on: string; off: string; warnOff?: boolean }) {
  const c = ok ? '#00e5a0' : warnOff ? '#ffaa00' : '#9aa3b3';
  return <span style={{ fontSize: 12, fontWeight: 700, color: c, padding: '4px 10px', borderRadius: 99, background: c + '1a' }}>{ok ? '●' : '○'} {ok ? on : off}</span>;
}

// ── Simulator (the star) ──
const PRESETS = [
  { label: 'Returning client (Arabic)', phone: '+9647721512437', message: 'مرحبا' },
  { label: 'New lead from ad', phone: '+9647701112233', message: "Hi, I saw your ad. I'm new to trading, how do I start?" },
  { label: 'Ready to deposit', phone: '+9647702223344', message: 'How much do I need to open an account?' },
  { label: 'Withdrawal (escalates)', phone: '+9647705556677', message: 'I want to withdraw my money now' },
];

function Simulator({ aiOk }: { aiOk: boolean }) {
  const [phone, setPhone] = useState('+9647721512437');
  const [message, setMessage] = useState('مرحبا');
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<any>(null);

  const run = async () => {
    if (!phone || !message) return;
    setBusy(true); setRes(null);
    try { setRes(await apiPost('/wati/simulate', { phone, message })); } catch { setRes({ error: 'failed' }); }
    setBusy(false);
  };

  const idn = res?.identity || {};
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, alignItems: 'start' }}>
      <div style={{ display: 'grid', gap: 12 }}>
        <div style={card}>
          <div style={cap}>Simulate an inbound WhatsApp</div>
          <div style={{ fontSize: 12, color: '#8a93a5', marginBottom: 10 }}>Type any number + message. This previews exactly what the AI would reply and which CRM actions it would take — <b>nothing is sent or saved</b>.</div>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 10 }}>
            {PRESETS.map(p => <span key={p.label} onClick={() => { setPhone(p.phone); setMessage(p.message); }} style={{ cursor: 'pointer', fontSize: 11, padding: '4px 9px', borderRadius: 7, background: '#1c2231', color: '#cfd6e4', border: '1px solid #3a4252' }}>{p.label}</span>)}
          </div>
          <input value={phone} onChange={e => setPhone(e.target.value)} placeholder="Sender phone (+964...)" style={{ ...input, width: '100%', boxSizing: 'border-box', marginBottom: 8, fontFamily: 'monospace' }} />
          <textarea value={message} onChange={e => setMessage(e.target.value)} rows={3} placeholder="Their WhatsApp message…" dir="auto" style={{ ...input, width: '100%', boxSizing: 'border-box', resize: 'vertical', marginBottom: 10 }} />
          <button onClick={run} disabled={busy || !aiOk} style={{ ...btn(aiOk ? '#25D366' : '#3a4252', aiOk ? '#06251b' : '#8a93a5'), width: '100%' }}>{busy ? 'AI is replying…' : '▶ Run simulation'}</button>
          {!aiOk && <div style={{ fontSize: 11, color: '#ffaa00', marginTop: 6 }}>AI brain not configured — set the Claude key in ai_config.py.</div>}
        </div>
      </div>

      <div style={{ display: 'grid', gap: 12 }}>
        {res?.error && <div style={{ ...card, color: '#ff5d6c' }}>Error: {res.error}</div>}
        {res && !res.error && (<>
          <div style={card}>
            <div style={cap}>Who is this?</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <span style={{ fontSize: 22 }}>{idn.kind === 'client' ? '👤' : idn.kind === 'lead' ? '🎯' : '🆕'}</span>
              <div>
                <div style={{ fontWeight: 700, color: '#e6e9ef' }}>{idn.name || (idn.kind === 'new' ? 'Brand-new contact' : '—')}</div>
                <div style={{ fontSize: 12, color: '#8a93a5' }}>
                  {idn.kind === 'client' ? `Existing client · login ${idn.login} · ${idn.segment || ''}${idn.deposits != null ? ` · ${idn.deposits} deposits` : ''}` :
                   idn.kind === 'lead' ? `Known lead · ${idn.country || ''} ${idn.badge ? '· ' + idn.badge : ''}` : 'Not in the CRM yet'}
                </div>
              </div>
            </div>
          </div>
          <div style={{ ...card, background: '#0b2018', border: '1px solid #1f5c43' }}>
            <div style={{ ...cap, color: '#7fe9c0' }}>🤖 AI reply {res.escalate && <span style={{ color: '#ffaa00' }}>· escalating to human</span>}{res.opted_out && <span style={{ color: '#ff8866' }}>· opt-out</span>}</div>
            <div dir="auto" style={{ background: '#075E54', color: '#fff', padding: '10px 12px', borderRadius: '10px 10px 10px 2px', fontSize: 14, lineHeight: 1.5, whiteSpace: 'pre-wrap' }}>{res.reply}</div>
          </div>
          {res.qualification && Object.values(res.qualification).some(Boolean) && (
            <div style={card}>
              <div style={cap}>🎯 Captured profile</div>
              <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', fontSize: 13, color: '#cfd6e4' }}>
                {res.qualification.experience_level && res.qualification.experience_level !== 'unknown' && <span>Level: <b>{res.qualification.experience_level}</b></span>}
                {res.qualification.interest && res.qualification.interest !== 'unknown' && <span>Interest: <b>{res.qualification.interest}</b></span>}
                {res.qualification.goal && <span>Goal: <b>{res.qualification.goal}</b></span>}
                {res.qualification.intent && <span>Intent: <b>{res.qualification.intent}</b></span>}
                {res.qualification.ready_to_register && <span style={{ color: '#00e5a0' }}>✅ ready to register</span>}
              </div>
            </div>
          )}
          <div style={card}>
            <div style={cap}>CRM actions it would take</div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {(res.actions || []).length ? res.actions.map((a: string) => (
                <span key={a} style={{ fontSize: 12, fontWeight: 600, color: '#00e5a0', background: '#00e5a01a', border: '1px solid #00e5a044', borderRadius: 7, padding: '4px 9px' }}>{ACTION_LABEL[a] || a}</span>
              )) : <span style={{ color: '#8a93a5', fontSize: 12 }}>No CRM changes</span>}
            </div>
            <div style={{ fontSize: 11, color: '#8a93a5', marginTop: 8 }}>Preview only — these are written to the CRM only when a real message arrives with the channel enabled.</div>
          </div>
        </>)}
        {!res && <div style={{ ...card, color: '#8a93a5', fontSize: 13 }}>Run a simulation to see the identity match, the AI's reply, and the CRM actions.</div>}
      </div>
    </div>
  );
}

// ── Conversations ──
function Conversations() {
  const [rows, setRows] = useState<any[]>([]);
  const [thread, setThread] = useState<any>(null);
  useEffect(() => { apiGet('/wati/conversations').then(r => setRows(r.conversations || [])).catch(() => {}); }, []);
  const open = (phone: string) => apiGet(`/wati/conversations/${encodeURIComponent(phone)}/messages`).then(setThread).catch(() => {});
  if (!rows.length) return <div style={{ ...card, color: '#8a93a5', fontSize: 13 }}>No conversations yet. They appear here once real WhatsApp messages start arriving (or after the channel goes live).</div>;
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, alignItems: 'start' }}>
      <div style={card}>
        <div style={cap}>Recent chats</div>
        {rows.map(r => (
          <div key={r.phone} onClick={() => open(r.phone)} style={{ display: 'flex', justifyContent: 'space-between', padding: '9px 0', borderBottom: '1px solid #373f4d', cursor: 'pointer' }}>
            <div><div style={{ color: '#e6e9ef', fontSize: 13 }}>{r.name || r.phone}</div><div style={{ fontSize: 11, color: '#8a93a5' }}>{r.kind} · {r.phone}</div></div>
            <span style={{ fontSize: 11, color: r.status === 'escalated' ? '#ffaa00' : '#8a93a5' }}>{r.status}</span>
          </div>
        ))}
      </div>
      <div style={card}>
        <div style={cap}>Thread</div>
        {!thread ? <div style={{ color: '#8a93a5', fontSize: 13 }}>Pick a chat.</div> :
          thread.messages.map((m: any, i: number) => (
            <div key={i} style={{ display: 'flex', justifyContent: m.direction === 'out' ? 'flex-end' : 'flex-start', marginBottom: 6 }}>
              <div dir="auto" style={{ maxWidth: '80%', background: m.direction === 'out' ? '#075E54' : '#2c333e', color: m.direction === 'out' ? '#fff' : '#cfd6e4', padding: '7px 10px', borderRadius: 8, fontSize: 13 }}>{m.body}</div>
            </div>
          ))}
      </div>
    </div>
  );
}

// ── Training (teach the bot) ──
function Training() {
  const [data, setData] = useState<any>({ teachings: [], staff_phones: [] });
  const [note, setNote] = useState('');
  const [phone, setPhone] = useState('');
  const load = () => apiGet('/wati/teachings').then(setData).catch(() => {});
  useEffect(() => { load(); }, []);
  const addNote = async () => { if (!note.trim()) return; await apiPost('/wati/teachings', { note }).catch(() => {}); setNote(''); load(); };
  const toggle = async (t: any) => { await apiPatch(`/wati/teachings/${t.id}`, { active: !t.active }).catch(() => {}); load(); };
  const del = async (t: any) => { await apiDelete(`/wati/teachings/${t.id}`).catch(() => {}); load(); };
  const addStaff = async () => { if (!phone.trim()) return; await apiPost('/wati/staff-phones', { phone }).catch(() => {}); setPhone(''); load(); };
  const delStaff = async (p: string) => { await apiDelete(`/wati/staff-phones?phone=${encodeURIComponent(p)}`).catch(() => {}); load(); };
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr', gap: 16, alignItems: 'start' }}>
      <div style={card}>
        <div style={cap}>🎓 What the bot has been taught</div>
        <div style={{ fontSize: 12, color: '#8a93a5', marginBottom: 10 }}>
          Staff can teach the bot from WhatsApp by starting a message with <b style={{ color: '#00e5a0' }}>#</b> (e.g. “# deposits are instant via ZainCash”). Lessons are applied above the bot’s defaults. Add or edit them here too.
        </div>
        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
          <input value={note} onChange={e => setNote(e.target.value)} placeholder="Teach the bot a rule…" dir="auto" style={{ ...input, flex: 1 }} />
          <button onClick={addNote} style={btn('#00e5a0')}>Add</button>
        </div>
        {(data.teachings || []).length === 0 ? <div style={{ color: '#8a93a5', fontSize: 13 }}>No lessons yet.</div> :
          (data.teachings || []).map((t: any) => (
            <div key={t.id} style={{ display: 'flex', gap: 10, alignItems: 'flex-start', padding: '9px 0', borderBottom: '1px solid #373f4d', opacity: t.active ? 1 : 0.5 }}>
              <input type="checkbox" checked={t.active} onChange={() => toggle(t)} style={{ marginTop: 3 }} />
              <div style={{ flex: 1, fontSize: 13, color: '#e6e9ef' }} dir="auto">{t.note}
                <div style={{ fontSize: 10, color: '#8a93a5' }}>{t.author_phone} · {t.created_at}</div>
              </div>
              <span onClick={() => del(t)} style={{ cursor: 'pointer', color: '#ff5d6c', fontSize: 12 }}>delete</span>
            </div>
          ))}
      </div>
      <div style={card}>
        <div style={cap}>👮 Staff phones (can teach via #)</div>
        <div style={{ fontSize: 12, color: '#8a93a5', marginBottom: 10 }}>Only these numbers can train the bot with #. Everyone else’s # message is treated as a normal chat.</div>
        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
          <input value={phone} onChange={e => setPhone(e.target.value)} placeholder="+9647…" style={{ ...input, flex: 1, fontFamily: 'monospace' }} />
          <button onClick={addStaff} style={btn('#00e5a0')}>Add</button>
        </div>
        {(data.staff_phones || []).length === 0 ? <div style={{ color: '#8a93a5', fontSize: 13 }}>None yet.</div> :
          (data.staff_phones || []).map((s: any, i: number) => (
            <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '7px 0', borderBottom: '1px solid #373f4d', fontSize: 13, color: '#cfd6e4' }}>
              <span style={{ fontFamily: 'monospace' }}>{s.phone} {s.label ? <span style={{ color: '#8a93a5' }}>· {s.label}</span> : null}</span>
              <span onClick={() => delStaff(s.phone)} style={{ cursor: 'pointer', color: '#ff5d6c', fontSize: 12 }}>remove</span>
            </div>
          ))}
      </div>
    </div>
  );
}

// ── Settings ──
function Settings({ cfg, onSaved }: { cfg: any; onSaved: () => void }) {
  const [local, setLocal] = useState<any>({ ...cfg });
  const [msg, setMsg] = useState('');
  useEffect(() => { setLocal({ ...cfg }); }, [cfg]);
  const save = async () => {
    await apiPost('/wati/config', local).catch(() => {});
    setMsg('Saved'); setTimeout(() => setMsg(''), 2500); onSaved();
  };
  const Toggle = ({ k, label, desc, warn }: any) => (
    <label style={{ display: 'flex', gap: 10, alignItems: 'flex-start', padding: '8px 0', cursor: 'pointer' }}>
      <input type="checkbox" checked={!!local[k]} onChange={e => setLocal({ ...local, [k]: e.target.checked })} style={{ marginTop: 3 }} />
      <div><div style={{ color: warn && local[k] ? '#ffaa00' : '#e6e9ef', fontSize: 13, fontWeight: 600 }}>{label}</div><div style={{ fontSize: 11, color: '#8a93a5' }}>{desc}</div></div>
    </label>
  );
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, alignItems: 'start' }}>
      <div style={card}>
        <div style={cap}>Behaviour</div>
        <Toggle k="enabled" label="LIVE — actually send via Wati" desc="OFF = preview only. Turn on only after the Wati token is set and you've tested." warn />
        <Toggle k="auto_reply" label="Auto-reply" desc="AI replies automatically. Off = suggest mode (logs the draft for a human to send)." />
        <Toggle k="ai_owns_leads" label="AI owns WhatsApp leads" desc="WhatsApp leads are AI-managed — the routing rules & Power Dialer skip them (no human dials)." />
        <div style={{ marginTop: 8 }}>
          <button onClick={save} style={btn('#00e5a0')}>Save</button>
          {msg && <span style={{ marginLeft: 10, color: '#00e5a0', fontSize: 12 }}>{msg}</span>}
        </div>
      </div>
      <div style={card}>
        <div style={cap}>Wati connection & offer</div>
        <div style={{ fontSize: 12, color: '#cfd6e4', marginBottom: 4 }}>Current offer (AI features this)</div>
        <input value={local.current_offer || ''} onChange={e => setLocal({ ...local, current_offer: e.target.value })} placeholder="e.g. 30% deposit bonus this week" style={{ ...input, width: '100%', boxSizing: 'border-box', marginBottom: 12 }} />
        <div style={{ fontSize: 12, color: '#cfd6e4', marginBottom: 4 }}>Wati API endpoint</div>
        <input value={local.api_endpoint || ''} onChange={e => setLocal({ ...local, api_endpoint: e.target.value })} placeholder="https://live-server-xxxx.wati.io" style={{ ...input, width: '100%', boxSizing: 'border-box', marginBottom: 12, fontFamily: 'monospace' }} />
        <div style={{ fontSize: 12, color: '#cfd6e4', marginBottom: 4 }}>Wati access token {cfg.api_token_set && <span style={{ color: '#00e5a0' }}>· set</span>}</div>
        <input value={local.api_token || ''} onChange={e => setLocal({ ...local, api_token: e.target.value })} placeholder={cfg.api_token_set ? '•••••••• (leave blank to keep)' : 'Bearer eyJ…'} style={{ ...input, width: '100%', boxSizing: 'border-box', fontFamily: 'monospace' }} />
        <div style={{ fontSize: 11, color: '#8a93a5', marginTop: 8 }}>Point Wati's incoming-message webhook to <b>https://my1.tnfx.co/api/wati/webhook</b>.</div>
      </div>
    </div>
  );
}

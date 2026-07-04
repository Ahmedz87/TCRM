import React, { useState, useEffect, useCallback } from 'react';
import { apiGet, apiPost, apiPatch, apiDelete } from './api';

const card: React.CSSProperties = { background: 'var(--bg-card,#2c333e)', border: '1px solid var(--border,#4f596b)', borderRadius: 12, padding: 18 };
const cap: React.CSSProperties = { fontSize: 11, color: '#8a93a5', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 12, fontWeight: 700 };
const input: React.CSSProperties = { padding: '8px 10px', background: '#1c2231', border: '1px solid #3a4252', borderRadius: 8, color: '#e6e9ef', fontSize: 13 };
const btn = (bg: string, fg = '#06251b'): React.CSSProperties => ({ padding: '9px 14px', background: bg, border: 'none', borderRadius: 8, color: fg, fontSize: 13, fontWeight: 700, cursor: 'pointer' });
const fmt = (n: number) => (n || 0).toLocaleString();

export default function DripJourneys() {
  const [journeys, setJourneys] = useState<any[]>([]);
  const [segments, setSegments] = useState<any[]>([]);
  const [creating, setCreating] = useState(false);
  const [runMsg, setRunMsg] = useState('');

  const load = useCallback(() => {
    apiGet('/drip/journeys').then(r => setJourneys(r.journeys || [])).catch(() => {});
    apiGet('/marketing/segments').then(r => setSegments(r.segments || [])).catch(() => {});
  }, []);
  useEffect(() => { load(); }, [load]);

  const toggle = async (j: any) => { await apiPatch(`/drip/journeys/${j.id}`, { is_active: !j.is_active }).catch(() => {}); load(); };
  const del = async (j: any) => { if (!window.confirm(`Delete "${j.name}"?`)) return; await apiDelete(`/drip/journeys/${j.id}`).catch(() => {}); load(); };
  const enroll = async (j: any) => {
    const pv = await apiPost(`/drip/journeys/${j.id}/enroll`, { dry_run: true }).catch(() => null);
    if (!pv) return;
    if (!window.confirm(`Enroll ${fmt(pv.would_enroll)} members of "${j.segment_key}" into "${j.name}"?`)) return;
    const r = await apiPost(`/drip/journeys/${j.id}/enroll`, {}).catch(() => null);
    setRunMsg(`Enrolled ${r?.enrolled ?? 0} members.`); load();
  };
  const runNow = async () => {
    const r = await apiPost('/drip/run', {}).catch(() => null);
    setRunMsg(r ? `Processed ${r.processed} due steps — ${r.sent} sent, ${r.simulated} simulated (channels gated).` : 'Run failed');
    load();
  };

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ fontSize: 13, color: '#8a93a5' }}>Automated multi-step sequences across email / WhatsApp. Sends are <b>simulated</b> until the channel is live.</div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button onClick={runNow} style={btn('#3a4252', '#cfd6e4')}>▶ Run due steps</button>
          <button onClick={() => setCreating(true)} style={btn('#00e5a0')}>+ New journey</button>
        </div>
      </div>
      {runMsg && <div style={{ background: '#00e5a022', color: '#00e5a0', padding: '8px 12px', borderRadius: 8, fontSize: 13 }}>{runMsg}</div>}

      {journeys.length === 0 && <div style={{ ...card, color: '#8a93a5', fontSize: 13 }}>No journeys yet. Create one — e.g. a 3-step no-deposit nurture.</div>}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(330px, 1fr))', gap: 12 }}>
        {journeys.map(j => (
          <div key={j.id} style={{ ...card, opacity: j.is_active ? 1 : 0.7 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ fontSize: 15, fontWeight: 700, color: '#e6e9ef' }}>{j.name}</div>
              <span style={{ fontSize: 11, fontWeight: 700, padding: '3px 9px', borderRadius: 99, background: j.is_active ? '#00e5a022' : '#3a4252', color: j.is_active ? '#00e5a0' : '#9aa3b3' }}>{j.is_active ? 'Active' : 'Paused'}</span>
            </div>
            <div style={{ fontSize: 12, color: '#8a93a5', margin: '6px 0' }}>
              {j.channel === 'whatsapp' ? '💬' : '✉️'} {j.channel} · 🎯 {j.segment_key} · {j.steps} steps
            </div>
            <div style={{ display: 'flex', gap: 14, fontSize: 12, color: '#cfd6e4', marginBottom: 10 }}>
              <span>Enrolled <b>{fmt(j.enrolled)}</b></span><span>Active <b>{fmt(j.active)}</b></span><span>Sends <b>{fmt(j.sends)}</b></span>
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <button onClick={() => enroll(j)} style={{ ...btn('#00e5a022', '#00e5a0'), padding: '6px 10px', fontSize: 12 }}>Enroll segment</button>
              <button onClick={() => toggle(j)} style={{ ...btn('#3a4252', '#cfd6e4'), padding: '6px 10px', fontSize: 12 }}>{j.is_active ? 'Pause' : 'Activate'}</button>
              <button onClick={() => del(j)} style={{ ...btn('#ff5d6c22', '#ff5d6c'), padding: '6px 10px', fontSize: 12 }}>Delete</button>
            </div>
          </div>
        ))}
      </div>
      {creating && <JourneyEditor segments={segments} onClose={() => setCreating(false)} onSaved={() => { setCreating(false); load(); }} />}
    </div>
  );
}

function JourneyEditor({ segments, onClose, onSaved }: { segments: any[]; onClose: () => void; onSaved: () => void }) {
  const [name, setName] = useState('');
  const [segment, setSegment] = useState('clients_never_deposited');
  const [channel, setChannel] = useState('email');
  const [steps, setSteps] = useState<any[]>([{ delay_hours: 0, subject: '', body: '' }]);
  const [err, setErr] = useState('');

  const setStep = (i: number, patch: any) => setSteps(steps.map((s, j) => j === i ? { ...s, ...patch } : s));
  const save = async () => {
    if (!name.trim()) { setErr('Name required'); return; }
    if (steps.some(s => !s.body.trim())) { setErr('Every step needs a message'); return; }
    const r = await apiPost('/drip/journeys', { name, segment_key: segment, channel, steps }).catch(() => null);
    if (r?.ok) onSaved(); else setErr('Save failed');
  };

  return (
    <div onClick={onClose} style={{ position: 'fixed', inset: 0, background: '#0009', zIndex: 100, display: 'flex', justifyContent: 'center', alignItems: 'flex-start', padding: '40px 16px', overflowY: 'auto' }}>
      <div onClick={e => e.stopPropagation()} style={{ ...card, width: 620, maxWidth: '100%' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 14 }}>
          <h3 style={{ color: '#e6e9ef', margin: 0 }}>New journey</h3><span onClick={onClose} style={{ cursor: 'pointer', color: '#8a93a5' }}>✕</span>
        </div>
        <div style={{ display: 'flex', gap: 10, marginBottom: 12 }}>
          <input value={name} onChange={e => setName(e.target.value)} placeholder="Journey name" style={{ ...input, flex: 1 }} />
          <select value={channel} onChange={e => setChannel(e.target.value)} style={input}><option value="email">✉️ Email</option><option value="whatsapp">💬 WhatsApp</option></select>
        </div>
        <div style={{ fontSize: 12, color: '#cfd6e4', marginBottom: 4 }}>Target segment</div>
        <select value={segment} onChange={e => setSegment(e.target.value)} style={{ ...input, width: '100%', boxSizing: 'border-box', marginBottom: 14 }}>
          {segments.map(s => <option key={s.key} value={s.key}>{s.label} ({fmt(s.total)})</option>)}
        </select>
        <div style={cap}>Steps</div>
        {steps.map((s, i) => (
          <div key={i} style={{ border: '1px solid #3a4252', borderRadius: 8, padding: 10, marginBottom: 8 }}>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 6 }}>
              <span style={{ fontSize: 12, color: '#8a93a5' }}>Step {i + 1} · wait</span>
              <input type="number" value={s.delay_hours} onChange={e => setStep(i, { delay_hours: parseInt(e.target.value) || 0 })} style={{ ...input, width: 70 }} />
              <span style={{ fontSize: 12, color: '#8a93a5' }}>hours</span>
              {steps.length > 1 && <span onClick={() => setSteps(steps.filter((_, j) => j !== i))} style={{ marginLeft: 'auto', cursor: 'pointer', color: '#ff5d6c', fontSize: 12 }}>remove</span>}
            </div>
            {channel === 'email' && <input value={s.subject} onChange={e => setStep(i, { subject: e.target.value })} placeholder="Subject" style={{ ...input, width: '100%', boxSizing: 'border-box', marginBottom: 6 }} />}
            <textarea value={s.body} onChange={e => setStep(i, { body: e.target.value })} placeholder="Message…" rows={2} dir="auto" style={{ ...input, width: '100%', boxSizing: 'border-box', resize: 'vertical' }} />
          </div>
        ))}
        <button onClick={() => setSteps([...steps, { delay_hours: 72, subject: '', body: '' }])} style={{ ...btn('#3a4252', '#cfd6e4'), fontSize: 12, padding: '6px 10px' }}>+ Add step</button>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 16, alignItems: 'center' }}>
          {err && <span style={{ color: '#ff5d6c', fontSize: 12 }}>{err}</span>}
          <button onClick={onClose} style={btn('#3a4252', '#cfd6e4')}>Cancel</button>
          <button onClick={save} style={btn('#00e5a0')}>Create journey</button>
        </div>
      </div>
    </div>
  );
}

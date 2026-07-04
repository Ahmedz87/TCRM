import React, { useState, useEffect } from 'react';
import { apiGet, apiPost } from './api';
import { TH } from './theme';

// Portal ticketing: a pinned red button (top-center, all pages) to report an issue /
// leave a note, and an "AI note" mode used from the live chat to tell the bot how to answer.

const SECTIONS = ['Dashboard', 'Accounts', 'Deposit', 'Withdraw', 'Transfer', 'Bonus',
  'Copy Trading', 'Charts', 'Rewards', 'Profile', 'KYC', 'AI assistant', 'Other'];
const CRITS = [
  { v: 'low', label: 'Low', c: '#8a93a3' },
  { v: 'medium', label: 'Medium', c: '#F8500A' },
  { v: 'high', label: 'High', c: '#ff8c42' },
  { v: 'critical', label: 'Critical', c: '#f0556a' },
];
// creator must choose how to handle — no default; review listed first
const ROUTES = [
  { v: 'review', label: '📤 Send to Admin for review', c: '#3b82f6' },
  { v: 'fix', label: '🔧 Fix directly', c: '#3ad29f' },
];

function scaleToDataUrl(file: Blob, maxDim = 1280, quality = 0.7): Promise<string> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    const url = URL.createObjectURL(file);
    img.onload = () => {
      let { width, height } = img;
      if (width > maxDim || height > maxDim) { const s = Math.min(maxDim / width, maxDim / height); width = Math.round(width * s); height = Math.round(height * s); }
      const c = document.createElement('canvas'); c.width = width; c.height = height;
      c.getContext('2d')!.drawImage(img, 0, 0, width, height);
      URL.revokeObjectURL(url); resolve(c.toDataURL('image/jpeg', quality));
    };
    img.onerror = reject; img.src = url;
  });
}

export function TicketModal({ onClose, aiMode, defaultSection }: { onClose: () => void; aiMode?: boolean; defaultSection?: string }) {
  const [section, setSection] = useState(defaultSection || (aiMode ? 'AI assistant' : 'Dashboard'));
  const [note, setNote] = useState('');
  const [critical, setCritical] = useState('medium');
  const [route, setRoute] = useState('');   // blank — must choose
  const [shot, setShot] = useState('');
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [err, setErr] = useState('');

  const onFile = async (f?: File) => { if (f) setShot(await scaleToDataUrl(f)); };
  const onPaste = async (e: React.ClipboardEvent) => {
    const item = Array.from(e.clipboardData.items).find(i => i.type.startsWith('image/'));
    if (item) { const f = item.getAsFile(); if (f) setShot(await scaleToDataUrl(f)); }
  };

  const submit = async () => {
    if (!aiMode && !route) { setErr('Please choose how to handle this ticket.'); return; }
    if (!note.trim()) { setErr('Please write your note.'); return; }
    setBusy(true); setErr('');
    try {
      await apiPost('/portal/tickets', { section, note, critical, route: route || null, screenshot: shot || null, for_ai: !!aiMode, page_url: window.location.href });
      setDone(true); setTimeout(onClose, 1400);
    } catch (e: any) { setErr(e?.message || 'Could not submit.'); }
    finally { setBusy(false); }
  };

  return (
    <div style={S.overlay} onClick={onClose}>
      <div style={S.modal} onClick={e => e.stopPropagation()} onPaste={onPaste}>
        <div style={S.head}>
          <span style={{ fontSize: 16, fontWeight: 800 }}>{aiMode ? '🤖 Tell the assistant how to answer' : '🎫 New ticket'}</span>
          <button style={S.x} onClick={onClose}>✕</button>
        </div>

        {done ? (
          <div style={{ textAlign: 'center', padding: '24px 0' }}>
            <div style={{ fontSize: 38 }}>✓</div>
            <div style={{ fontSize: 15, fontWeight: 700, color: TH.accent, marginTop: 8 }}>{aiMode ? 'Sent to the assistant.' : 'Ticket submitted — thank you!'}</div>
          </div>
        ) : (
          <>
            {aiMode ? (
              <div style={{ fontSize: 12, color: TH.muted, marginBottom: 12 }}>Your note is sent to our AI assistant as guidance on how it should respond. Staff can review it too.</div>
            ) : (
              <>
                <label style={S.lbl}>How should we handle this? <span style={{ color: '#ff8c42' }}>*</span></label>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 4 }}>
                  {ROUTES.map(r => (
                    <button key={r.v} onClick={() => setRoute(r.v)} style={{
                      padding: '11px 14px', borderRadius: 8, cursor: 'pointer', fontSize: 13, fontWeight: 700, textAlign: 'left',
                      background: route === r.v ? r.c + '22' : TH.panel2, color: route === r.v ? r.c : '#cdd4de',
                      border: `1px solid ${route === r.v ? r.c : TH.border2}`,
                    }}>{route === r.v ? '● ' : '○ '}{r.label}</button>
                  ))}
                </div>
                <label style={{ ...S.lbl, marginTop: 14 }}>Which section?</label>
                <select value={section} onChange={e => setSection(e.target.value)} style={S.input}>
                  {SECTIONS.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
                <label style={{ ...S.lbl, marginTop: 14 }}>Critical level</label>
                <div style={{ display: 'flex', gap: 8 }}>
                  {CRITS.map(c => (
                    <button key={c.v} onClick={() => setCritical(c.v)} style={{
                      flex: 1, padding: '8px', borderRadius: 8, cursor: 'pointer', fontSize: 12.5, fontWeight: 700,
                      background: critical === c.v ? c.c : TH.panel2, color: critical === c.v ? '#0b0e14' : '#cdd4de',
                      border: `1px solid ${critical === c.v ? c.c : TH.border2}`,
                    }}>{c.label}</button>
                  ))}
                </div>
              </>
            )}

            <label style={{ ...S.lbl, marginTop: 14 }}>{aiMode ? 'Your instruction' : 'Your note'}</label>
            <textarea value={note} onChange={e => setNote(e.target.value)} rows={4}
              placeholder={aiMode ? 'e.g. "Always greet in Arabic and mention the current deposit bonus."' : 'Describe the issue. You can paste a screenshot here (Ctrl+V).'}
              style={{ ...S.input, resize: 'vertical', fontFamily: 'inherit' }} />

            {!aiMode && (
              <>
                <label style={{ ...S.lbl, marginTop: 14 }}>Screenshot (paste or upload)</label>
                {shot ? (
                  <div style={{ position: 'relative' }}>
                    <img src={shot} alt="screenshot" style={{ width: '100%', borderRadius: 8, border: `1px solid ${TH.border2}` }} />
                    <button onClick={() => setShot('')} style={{ ...S.x, position: 'absolute', top: 6, right: 6, background: '#000a' }}>✕</button>
                  </div>
                ) : (
                  <label style={S.upload}>
                    <input type="file" accept="image/*" style={{ display: 'none' }} onChange={e => onFile(e.target.files?.[0])} />
                    📎 Click to upload — or paste a screenshot in this box
                  </label>
                )}
              </>
            )}

            {err && <div style={{ color: '#ff7a7a', fontSize: 12.5, marginTop: 10 }}>{err}</div>}
            <button onClick={submit} disabled={busy} style={S.submit}>{busy ? 'Submitting…' : (aiMode ? 'Send to assistant' : 'Submit ticket')}</button>
          </>
        )}
      </div>
    </div>
  );
}

export function TicketButton() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button onClick={() => setOpen(true)} style={S.pinned} title="Report an issue / add a note">🎫 Add Ticket</button>
      {open && <TicketModal onClose={() => setOpen(false)} />}
    </>
  );
}

const TSTAT: any = {
  under_review: { label: 'Under review', c: '#F8500A' },
  proceed: { label: 'In progress', c: '#3b82f6' },
  answered: { label: 'Answered — your turn', c: '#a855f7' },
  done: { label: 'Closed', c: '#3ad29f' },
};

// The maker's view: their tickets + the conversation, where they reply or close.
export default function MyTicketsPage() {
  const [tickets, setTickets] = useState<any[]>([]);
  const [detail, setDetail] = useState<any>(null);
  const [reply, setReply] = useState('');
  const [busy, setBusy] = useState(false);

  const load = () => apiGet('/portal/tickets').then((d: any) => setTickets(d?.tickets || [])).catch(() => {});
  useEffect(() => { load(); }, []);
  const open = (id: number) => { setReply(''); apiGet(`/portal/tickets/${id}`).then(setDetail).catch(() => {}); };

  const send = async (close: boolean) => {
    if (!close && !reply.trim()) return;
    setBusy(true);
    try {
      const r: any = await apiPost(`/portal/tickets/${detail.id}/reply`, { body: reply, close });
      if (r && r.detail && !r.ok) { window.alert(r.detail); }
      else { setReply(''); if (close) setDetail(null); else open(detail.id); load(); }
    } finally { setBusy(false); }
  };

  return (
    <div style={{ padding: 28, maxWidth: 760, margin: '0 auto', color: TH.text }}>
      <h1 style={{ fontSize: 24, fontWeight: 800, margin: '0 0 16px' }}>My tickets</h1>
      {tickets.length === 0 && <div style={{ color: TH.muted, fontSize: 14, background: TH.panel, border: `1px solid ${TH.border}`, borderRadius: 14, padding: 30, textAlign: 'center' }}>You haven't raised any tickets yet. Reach out through the live chat assistant and our team will follow up here.</div>}
      {tickets.map(t => {
        const st = TSTAT[t.status] || { label: t.status, c: TH.muted };
        return (
          <div key={t.id} onClick={() => open(t.id)} style={{ background: TH.panel, border: `1px solid ${t.status === 'answered' ? '#a855f7' : TH.border}`, borderRadius: 12, padding: 14, marginBottom: 10, cursor: 'pointer' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
              <span style={{ fontSize: 12, color: TH.muted }}>#{t.id} · {t.section} · {t.created_at}</span>
              <span style={{ fontSize: 10.5, fontWeight: 700, color: st.c, background: st.c + '22', borderRadius: 6, padding: '3px 9px' }}>{st.label}</span>
            </div>
            <div style={{ fontSize: 13.5, color: TH.text, marginTop: 6, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{t.note}</div>
            {t.replies > 0 && <div style={{ fontSize: 11, color: '#a855f7', marginTop: 4 }}>💬 {t.replies} repl{t.replies === 1 ? 'y' : 'ies'}</div>}
          </div>
        );
      })}

      {detail && (
        <div style={S.overlay} onClick={() => setDetail(null)}>
          <div style={S.modal} onClick={e => e.stopPropagation()}>
            <div style={S.head}>
              <span style={{ fontSize: 16, fontWeight: 800 }}>Ticket #{detail.id}</span>
              <button style={S.x} onClick={() => setDetail(null)}>✕</button>
            </div>
            <div style={{ fontSize: 12, color: TH.muted, marginBottom: 8 }}>{detail.section} · {detail.created_at}</div>
            <div style={{ fontSize: 14, color: TH.text, whiteSpace: 'pre-wrap', lineHeight: 1.5, marginBottom: 12 }}>{detail.note}</div>
            {detail.screenshot && <img src={detail.screenshot} alt="screenshot" style={{ width: '100%', borderRadius: 8, border: `1px solid ${TH.border2}`, marginBottom: 12 }} />}

            {detail.replies?.length > 0 && (
              <div style={{ borderTop: `1px solid ${TH.border}`, paddingTop: 12 }}>
                {detail.replies.map((rp: any, i: number) => (
                  <div key={i} style={{ marginBottom: 10, paddingLeft: 10, borderLeft: `2px solid ${rp.author_type === 'client' ? TH.accent : '#a855f7'}` }}>
                    <div style={{ fontSize: 11, color: rp.author_type === 'client' ? TH.accent : '#a855f7', fontWeight: 700 }}>
                      {rp.author_type === 'client' ? '🙋 You' : '🛠 Support'} · {rp.at}
                    </div>
                    <div style={{ fontSize: 13, color: TH.text, whiteSpace: 'pre-wrap', lineHeight: 1.5, marginTop: 2 }}>{rp.body}</div>
                  </div>
                ))}
              </div>
            )}

            {detail.status === 'done' ? (
              <div style={{ fontSize: 12.5, color: TH.accent, marginTop: 12, fontWeight: 700 }}>✓ This ticket is closed.</div>
            ) : (
              <>
                <textarea value={reply} onChange={e => setReply(e.target.value)} rows={3}
                  placeholder="Reply to support…" style={{ ...S.input, resize: 'vertical', fontFamily: 'inherit', marginTop: 12 }} />
                <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
                  <button onClick={() => send(false)} disabled={busy || !reply.trim()} style={{ ...S.submit, marginTop: 0, flex: 1, opacity: (busy || !reply.trim()) ? 0.5 : 1, background: 'linear-gradient(90deg,#a855f7,#7c3aed)' }}>Send reply</button>
                  <button onClick={() => send(true)} disabled={busy} style={{ padding: '12px 18px', borderRadius: 9, background: 'transparent', border: `1px solid ${TH.accent}`, color: TH.accent, fontWeight: 800, fontSize: 13, cursor: 'pointer' }}>✓ Close ticket</button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

const S: any = {
  pinned: { position: 'fixed', top: 10, left: '50%', transform: 'translateX(-50%)', zIndex: 4000,
    padding: '8px 18px', borderRadius: 999, background: 'linear-gradient(90deg,#f0556a,#d83a50)', color: '#fff',
    border: 'none', fontSize: 13, fontWeight: 800, cursor: 'pointer', boxShadow: '0 6px 22px rgba(240,85,106,0.5)', fontFamily: 'inherit' },
  overlay: { position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', zIndex: 5000, display: 'flex', alignItems: 'flex-start', justifyContent: 'center', padding: '60px 16px', overflowY: 'auto' },
  modal: { background: TH.panel, border: `1px solid ${TH.border2}`, borderRadius: 14, padding: 20, width: '100%', maxWidth: 460, color: TH.text },
  head: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 },
  x: { background: 'transparent', border: 'none', color: TH.muted, fontSize: 16, cursor: 'pointer' },
  lbl: { fontSize: 11.5, color: TH.muted, fontWeight: 600, display: 'block', marginBottom: 6 },
  input: { width: '100%', padding: '10px 12px', borderRadius: 8, background: TH.panel2, border: `1px solid ${TH.border2}`, color: TH.text, fontSize: 13.5, outline: 'none', boxSizing: 'border-box' },
  upload: { display: 'block', border: `1.5px dashed ${TH.border2}`, borderRadius: 8, padding: 18, textAlign: 'center', cursor: 'pointer', color: TH.muted, fontSize: 12.5 },
  submit: { width: '100%', marginTop: 16, padding: '12px', borderRadius: 9, background: 'linear-gradient(90deg,#f0556a,#d83a50)', color: '#fff', border: 'none', fontWeight: 800, fontSize: 14, cursor: 'pointer' },
};

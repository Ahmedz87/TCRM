import React, { useState, useEffect, useRef } from 'react';
import { apiGet, apiPost, apiPatch, apiDelete } from './api';

// ── Ticket Centre ──────────────────────────────────────────────────────────────
// Every staff user can open a ticket, pick a priority and submit it to the developer.
// A user sees ONLY their own tickets and tracks the status + replies. Admins see and
// answer all tickets; their replies always appear to the maker as "Developer".
// (No AI chat — removed Jul 2026 at the desk's request.)

const SECTIONS = [
  'Dashboard', 'Leads', 'Clients', 'Trading accounts', 'Transactions', 'IB system',
  'Sales agents', 'Network', 'Abuse detection', 'Bonus', 'Copy trading', 'Loyalty',
  'Payments / deposits', 'Withdrawals', 'KYC / verification', 'Reports', 'Settings',
  'Client portal', 'Other',
];

// Priority — matches backend VALID_CRIT (normal | medium | urgent | critical)
const CRITS = [
  { v: 'normal',   label: 'Normal',   c: '#8a93a3' },
  { v: 'medium',   label: 'Medium',   c: '#E8B84B' },
  { v: 'urgent',   label: 'Urgent',   c: '#ff8c42' },
  { v: 'critical', label: 'Critical', c: '#ff4d4f' },
];
const critMeta = (v: string) => CRITS.find(c => c.v === v) || CRITS[0];

// Maker-facing status labels (the raw DB values stay the same on the backend).
const STATUSES: any = {
  under_review: { label: 'Submitted',   c: '#E8B84B' },   // waiting on the developer
  proceed:      { label: 'In progress', c: '#22c55e' },
  answered:     { label: 'Replied',     c: '#a855f7' },   // developer replied
  done:         { label: 'Done',        c: '#00e5a0' },
  rejected:     { label: 'Closed',      c: '#ff4d4f' },
};
const statusMeta = (v: string) => STATUSES[v] || STATUSES.under_review;

// Auto-subject: a short one-line title from the note (works for Arabic & English).
function makeSubject(note: string): string {
  const oneLine = (note || '').replace(/\s+/g, ' ').trim();
  if (!oneLine) return 'Ticket';
  const stop = oneLine.search(/[.!?؟\n]/);
  let s = stop > 8 && stop <= 70 ? oneLine.slice(0, stop) : oneLine;
  if (s.length > 70) s = s.slice(0, 70).trim() + '…';
  return s;
}

// downscale any image blob to a small JPEG data URL (stay under nginx body limit)
function scaleToDataUrl(file: Blob, maxDim = 1280, quality = 0.7): Promise<string> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    const url = URL.createObjectURL(file);
    img.onload = () => {
      let { width, height } = img;
      if (width > maxDim || height > maxDim) {
        const s = Math.min(maxDim / width, maxDim / height);
        width = Math.round(width * s); height = Math.round(height * s);
      }
      const c = document.createElement('canvas'); c.width = width; c.height = height;
      c.getContext('2d')!.drawImage(img, 0, 0, width, height);
      URL.revokeObjectURL(url);
      resolve(c.toDataURL('image/jpeg', quality));
    };
    img.onerror = reject; img.src = url;
  });
}

// ── New-ticket modal (fill -> review -> submit) ─────────────────────────────────
function NewTicketModal({ onClose, onCreated }: any) {
  const [section, setSection] = useState('');
  const [note, setNote] = useState('');
  const [critical, setCritical] = useState('normal');
  const [shot, setShot] = useState('');
  const [review, setReview] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const onFile = async (f?: File | null) => { if (f) setShot(await scaleToDataUrl(f)); };
  const onPaste = async (e: React.ClipboardEvent) => {
    const item = Array.from(e.clipboardData.items).find(i => i.type.startsWith('image/'));
    if (item) { const f = item.getAsFile(); if (f) setShot(await scaleToDataUrl(f)); }
  };
  const goReview = () => {
    if (!note.trim()) { setErr('Please describe the issue or request.'); return; }
    if (!section) { setErr('Please choose a section.'); return; }
    setErr(''); setReview(true);
  };
  const submit = async () => {
    setBusy(true); setErr('');
    const r = await apiPost('/tickets', {
      section, note: note.trim(), critical,
      screenshot: shot || null, page_url: window.location.href,
    });
    setBusy(false);
    if (r && r.detail && !r.id) { setErr(r.detail); return; }
    onCreated && onCreated();
    onClose();
  };

  return (
    <div style={S.overlay} onClick={onClose}>
      <div style={S.modal} onClick={e => e.stopPropagation()}>
        <div style={S.modalHead}>
          <span style={{ fontSize: 16, fontWeight: 800 }}>{review ? '🔎 Review your ticket' : '🎫 New ticket'}</span>
          <button onClick={onClose} style={S.x}>✕</button>
        </div>

        {review ? (
          <div>
            <div style={{ ...S.reviewCard }}>
              <div style={{ display: 'flex', gap: 8, marginBottom: 8, flexWrap: 'wrap' }}>
                <span style={{ ...S.pill, background: critMeta(critical).c + '22', color: critMeta(critical).c }}>{critMeta(critical).label}</span>
                {section && <span style={S.metaPill}>{section}</span>}
              </div>
              <div dir="auto" style={{ fontWeight: 700, marginBottom: 6, textAlign: 'start' }}>{makeSubject(note)}</div>
              <div dir="auto" style={{ whiteSpace: 'pre-wrap', fontSize: 13, color: '#cdd4de', textAlign: 'start' }}>{note}</div>
              {shot && <img src={shot} alt="" style={{ maxWidth: '100%', borderRadius: 8, marginTop: 10, border: '1px solid #4f596b' }} />}
            </div>
            {err && <div style={S.err}>{err}</div>}
            <div style={{ display: 'flex', gap: 10, marginTop: 14 }}>
              <button onClick={() => setReview(false)} disabled={busy} style={S.secondary}>← Edit</button>
              <button onClick={submit} disabled={busy} style={{ ...S.submit, marginTop: 0, flex: 1 }}>
                {busy ? 'Submitting…' : 'Submit to developer'}
              </button>
            </div>
          </div>
        ) : (
          <div onPaste={onPaste}>
            <label style={S.lbl}>Section</label>
            <select value={section} onChange={e => setSection(e.target.value)} style={S.input}>
              <option value="">— choose a section —</option>
              {SECTIONS.map(s => <option key={s} value={s}>{s}</option>)}
            </select>

            <label style={{ ...S.lbl, marginTop: 14 }}>Priority</label>
            <div style={{ display: 'flex', gap: 8 }}>
              {CRITS.map(c => (
                <button key={c.v} onClick={() => setCritical(c.v)}
                  style={{
                    flex: 1, padding: '9px 4px', borderRadius: 8, fontWeight: 700, fontSize: 12.5, cursor: 'pointer',
                    background: critical === c.v ? c.c + '22' : '#373f4d',
                    border: `1.5px solid ${critical === c.v ? c.c : '#4f596b'}`,
                    color: critical === c.v ? c.c : '#cdd4de',
                  }}>{c.label}</button>
              ))}
            </div>

            <label style={{ ...S.lbl, marginTop: 14 }}>Describe the issue or request</label>
            <textarea value={note} onChange={e => setNote(e.target.value)} rows={5} dir="auto"
              placeholder="What happened / what do you need? You can paste a screenshot too."
              style={{ ...S.input, resize: 'vertical', textAlign: 'start' }} />

            <label style={{ ...S.lbl, marginTop: 14 }}>Screenshot (optional)</label>
            {shot ? (
              <div style={{ position: 'relative' }}>
                <img src={shot} alt="" style={{ maxWidth: '100%', borderRadius: 8, border: '1px solid #4f596b' }} />
                <button onClick={() => setShot('')} style={{ ...S.x, position: 'absolute', top: 6, right: 6, background: 'rgba(0,0,0,0.6)', borderRadius: 6, padding: '2px 8px' }}>remove</button>
              </div>
            ) : (
              <label style={S.upload}>
                Click to upload or paste an image
                <input type="file" accept="image/*" hidden onChange={e => onFile(e.target.files?.[0])} />
              </label>
            )}

            {err && <div style={S.err}>{err}</div>}
            <button onClick={goReview} style={S.submit}>Review →</button>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Ticket detail drawer ────────────────────────────────────────────────────────
function TicketDetail({ id, onClose, onChanged }: any) {
  const [d, setDetail] = useState<any>(null);
  const [reply, setReply] = useState('');
  const [replyImg, setReplyImg] = useState('');
  const [busy, setBusy] = useState(false);
  const convRef = useRef<HTMLDivElement>(null);

  const load = () => apiGet(`/tickets/${id}`).then(setDetail).catch(() => {});
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [id]);
  useEffect(() => { if (d && convRef.current) convRef.current.scrollTop = convRef.current.scrollHeight; }, [d]);

  const onReplyFile = async (f?: File | null) => { if (f) setReplyImg(await scaleToDataUrl(f)); };
  const onPaste = async (e: React.ClipboardEvent) => {
    const item = Array.from(e.clipboardData.items).find(i => i.type.startsWith('image/'));
    if (item) { const f = item.getAsFile(); if (f) setReplyImg(await scaleToDataUrl(f)); }
  };
  const sendReply = async () => {
    if (!reply.trim() && !replyImg) return;
    setBusy(true);
    const r = await apiPost(`/tickets/${id}/reply`, { body: reply.trim(), image: replyImg || null });
    setBusy(false);
    if (r && r.detail && !r.ok) { window.alert(r.detail); return; }
    setReply(''); setReplyImg(''); load(); onChanged && onChanged();
  };
  const setStatus = async (s: string) => {
    const r = await apiPatch(`/tickets/${id}/status`, { status: s });
    if (r && r.detail && !r.ok) { window.alert(r.detail); return; }
    load(); onChanged && onChanged();
  };
  const remove = async () => {
    if (!window.confirm('Delete this ticket?')) return;
    await apiDelete(`/tickets/${id}`); onClose(); onChanged && onChanged();
  };
  const awardPoints = async (pts: number) => {
    const r = await apiPatch(`/tickets/${id}/points`, { points: pts });
    if (r && r.detail && !r.ok) { window.alert(r.detail); return; }
    load(); onChanged && onChanged();
  };

  if (!d) return null;
  const sm = statusMeta(d.status);
  const cm = critMeta(d.critical);
  const isAdmin = !!d.is_admin;
  const isMine = !!d.is_mine;

  return (
    <div style={S.overlay} onClick={onClose}>
      <div style={S.detailModal} onClick={e => e.stopPropagation()}>
        <div style={S.detailHead}>
          <div style={{ minWidth: 0 }}>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 6, flexWrap: 'wrap' }}>
              <span style={{ color: '#8a93a3', fontSize: 12 }}>#{d.id}</span>
              <span style={{ ...S.pill, background: cm.c + '22', color: cm.c }}>{cm.label}</span>
              <span style={{ ...S.pill, background: sm.c + '22', color: sm.c }}>{sm.label}</span>
              {d.section && <span style={S.metaPill}>{d.section}</span>}
              {d.award_points > 0 && <span style={{ ...S.pill, background: '#f5c51a22', color: '#f5c51a', fontWeight: 800 }}>🏆 {d.award_points} pts</span>}
            </div>
            <div dir="auto" style={{ fontWeight: 700, fontSize: 15, textAlign: 'start' }}>{makeSubject(d.note)}</div>
          </div>
          <button onClick={onClose} style={S.x}>✕</button>
        </div>

        <div ref={convRef} style={S.convScroll}>
          {/* original request */}
          <div style={{ ...S.bubble, ...S.bubbleMine }}>
            <div style={S.bubbleWho}>{d.creator || 'You'}</div>
            <div dir="auto" style={{ whiteSpace: 'pre-wrap', textAlign: 'start' }}>{d.note}</div>
            {d.screenshot && <img src={d.screenshot} alt="" style={S.bubbleImg} />}
            {d.created_at && <div style={S.bubbleAt}>{d.created_at}</div>}
          </div>
          {/* thread */}
          {(d.replies || []).map((r: any, i: number) => {
            const dev = r.author_type === 'dev';
            return (
              <div key={i} style={{ ...S.bubble, ...(dev ? S.bubbleDev : S.bubbleMine) }}>
                <div style={{ ...S.bubbleWho, color: dev ? '#7cc4ff' : '#9aa4b2' }}>
                  {dev ? '🛠 Developer' : (r.author || 'You')}
                </div>
                {r.body && <div dir="auto" style={{ whiteSpace: 'pre-wrap', textAlign: 'start' }}>{r.body}</div>}
                {r.image && <img src={r.image} alt="" style={S.bubbleImg} />}
                {r.at && <div style={S.bubbleAt}>{r.at}</div>}
              </div>
            );
          })}
        </div>

        <div style={S.detailFoot} onPaste={onPaste}>
          {replyImg && (
            <div style={{ position: 'relative', marginBottom: 8, display: 'inline-block' }}>
              <img src={replyImg} alt="" style={{ maxHeight: 90, borderRadius: 6, border: '1px solid #4f596b' }} />
              <button onClick={() => setReplyImg('')} style={{ ...S.x, position: 'absolute', top: 2, right: 2, background: 'rgba(0,0,0,0.6)', borderRadius: 6, padding: '0 6px' }}>✕</button>
            </div>
          )}
          <div style={{ display: 'flex', gap: 8 }}>
            <textarea value={reply} onChange={e => setReply(e.target.value)} rows={2}
              placeholder={isAdmin ? 'Reply to the maker (shows as “Developer”)…' : 'Add a message…'}
              style={{ ...S.input, resize: 'none' }} />
            <label style={{ ...S.secondary, display: 'flex', alignItems: 'center', padding: '0 12px', cursor: 'pointer' }}>
              📎<input type="file" accept="image/*" hidden onChange={e => onReplyFile(e.target.files?.[0])} />
            </label>
            <button onClick={sendReply} disabled={busy} style={{ ...S.submit, marginTop: 0, width: 'auto', padding: '0 18px' }}>Send</button>
          </div>

          {/* actions */}
          <div style={{ display: 'flex', gap: 8, marginTop: 10, flexWrap: 'wrap', alignItems: 'center' }}>
            {isAdmin && (
              <>
                <span style={{ fontSize: 11, color: '#8a93a3' }}>Set status:</span>
                <select value={d.status} onChange={e => setStatus(e.target.value)} style={S.statusSel}>
                  <option value="under_review">Submitted</option>
                  <option value="proceed">In progress</option>
                  <option value="answered">Replied</option>
                  <option value="done">Done</option>
                  <option value="rejected">Closed</option>
                </select>
                <span style={{ fontSize: 11, color: '#8a93a3', marginLeft: 4 }}>🏆 Points:</span>
                <input type="number" min={0} defaultValue={d.award_points || 0} key={`pts-${d.id}-${d.award_points}`}
                  onBlur={e => { const v = parseInt(e.target.value || '0', 10); if (v !== (d.award_points || 0)) awardPoints(v); }}
                  style={{ ...S.statusSel, width: 64 }} title="Award points to the maker, then click away to save" />
                <button onClick={remove} style={{ ...S.secondary, color: '#ff7a7a', borderColor: '#5a3a3a' }}>Delete</button>
              </>
            )}
            {!isAdmin && isMine && d.status !== 'done' && (
              <button onClick={() => setStatus('done')} style={{ ...S.secondary, color: '#00e5a0', borderColor: '#2f5a4a' }}>
                ✓ Mark as done
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Main page ───────────────────────────────────────────────────────────────────
export default function TicketsPage() {
  const [tickets, setTickets] = useState<any[]>([]);
  const [isAdmin, setIsAdmin] = useState(false);
  const [tab, setTab] = useState<'mine' | 'all' | 'chatbot'>('mine');   // admin tabs
  const [fStatus, setFStatus] = useState('');
  const [fCrit, setFCrit] = useState('');
  const [openId, setOpenId] = useState<number | null>(null);
  const [showNew, setShowNew] = useState(false);
  const [myPoints, setMyPoints] = useState(0);   // caller's running contributor score

  const load = () => {
    const qs = new URLSearchParams();
    if (fStatus) qs.set('status', fStatus);
    if (fCrit) qs.set('critical', fCrit);
    if (tab === 'mine') qs.set('mine', '1');
    if (tab === 'chatbot') qs.set('source', 'chat');   // separate live-chat / bot tickets
    apiGet(`/tickets?${qs.toString()}`).then((r: any) => {
      setTickets(r?.tickets || []);
      setIsAdmin(!!r?.is_admin);
      setMyPoints(r?.my_points || 0);
    }).catch(() => {});
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [fStatus, fCrit, tab]);

  const counts = {
    open: tickets.filter(t => t.status === 'under_review').length,
    progress: tickets.filter(t => t.status === 'proceed' || t.status === 'answered').length,
    done: tickets.filter(t => t.status === 'done').length,
    total: tickets.length,
  };

  // Sort by ticket number (#). Click the # header to flip newest/oldest first.
  const [numDesc, setNumDesc] = useState(true);
  const sorted = [...tickets].sort((a, b) => numDesc ? b.id - a.id : a.id - b.id);

  return (
    <div style={S.page}>
      <div style={S.pageHead}>
        <div>
          <div style={{ fontSize: 22, fontWeight: 800 }}>🎫 Ticket Centre</div>
          <div style={{ color: '#8a93a3', fontSize: 13, marginTop: 4 }}>
            Report an issue or request a change — submit it to the developer and track the reply here.
          </div>
        </div>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
          <div style={S.scoreBadge} title="Points you've earned for helpful bug reports & ideas">
            🏆 <b style={{ fontSize: 17 }}>{myPoints}</b> pts
          </div>
          <button onClick={() => setShowNew(true)} style={S.newBtn}>＋ New ticket</button>
        </div>
      </div>

      <div style={S.kpis}>
        <Kpi label="Submitted" value={counts.open} c="#E8B84B" />
        <Kpi label="In progress" value={counts.progress} c="#22c55e" />
        <Kpi label="Done" value={counts.done} c="#00e5a0" />
        <Kpi label={tab === 'chatbot' ? '🤖 Chatbot tickets' : (isAdmin && tab === 'all' ? 'All tickets' : 'My tickets')} value={counts.total} c="#e8edf2" />
      </div>

      <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end', marginBottom: 12, flexWrap: 'wrap' }}>
        {isAdmin && (
          <div style={S.tabs}>
            {(['mine', 'all', 'chatbot'] as const).map(k => (
              <button key={k} onClick={() => setTab(k)}
                style={{ ...S.tab, ...(tab === k ? S.tabOn : {}) }}>
                {k === 'mine' ? '👤 My queue' : k === 'all' ? '🗂 All tickets' : '🤖 Chatbot'}
              </button>
            ))}
          </div>
        )}
        <Filter label="Status" value={fStatus} set={setFStatus}
          opts={[['', 'All statuses'], ...Object.entries(STATUSES).map(([v, m]: any) => [v, m.label])]} />
        <Filter label="Priority" value={fCrit} set={setFCrit}
          opts={[['', 'All priorities'], ...CRITS.map(c => [c.v, c.label])]} />
      </div>

      <div style={S.table}>
        <div style={{ ...S.row, ...S.headRow }}>
          <div style={{ width: 92, cursor: 'pointer', userSelect: 'none' }} onClick={() => setNumDesc(d => !d)}>
            {tab === 'chatbot' ? 'Ref' : '#'} {numDesc ? '▼' : '▲'}
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>Subject</div>
          <div style={{ width: 140 }}>Made by</div>
          <div style={{ width: 120 }}>Section</div>
          <div style={{ width: 84 }}>Priority</div>
          <div style={{ width: 104 }}>Status</div>
          <div style={{ width: 70, textAlign: 'center' }}>Points</div>
          <div style={{ width: 54, textAlign: 'center' }}>Replies</div>
          <div style={{ width: 104 }}>Created</div>
        </div>
        {sorted.length === 0 && (
          <div style={{ padding: 40, textAlign: 'center', color: '#8a93a3', fontSize: 13 }}>
            No tickets yet. Click “＋ New ticket” to submit one.
          </div>
        )}
        {sorted.map(t => {
          const sm = statusMeta(t.status), cm = critMeta(t.critical);
          return (
            <div key={t.id} style={S.row} onClick={() => setOpenId(t.id)}>
              <div style={{ width: 92, color: t.series ? '#a855f7' : '#8a93a3', fontWeight: t.series ? 700 : 400, fontSize: t.series ? 11 : 13, whiteSpace: 'nowrap' }}>
                {t.series ? `🤖 ${t.series}` : `#${t.id}`}
              </div>
              <div style={{ flex: 1, minWidth: 0, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6 }}>
                {t.unread && isAdmin && <span title="new activity" style={{ width: 8, height: 8, borderRadius: 999, background: '#ff4d4f', flexShrink: 0 }} />}
                <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={makeSubject(t.note)}>{makeSubject(t.note)}</span>
              </div>
              <div style={{ width: 140, color: '#cdd4de', fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{t.creator || '—'}</div>
              <div style={{ width: 120, color: '#cdd4de', fontSize: 12 }}>{t.section || '—'}</div>
              <div style={{ width: 84 }}><span style={{ ...S.pill, background: cm.c + '22', color: cm.c }}>{cm.label}</span></div>
              <div style={{ width: 104 }}><span style={{ ...S.pill, background: sm.c + '22', color: sm.c }}>{sm.label}</span></div>
              <div style={{ width: 70, textAlign: 'center' }}>
                {t.award_points > 0
                  ? <span style={{ ...S.pill, background: '#f5c51a22', color: '#f5c51a' }}>🏆 {t.award_points}</span>
                  : <span style={{ color: '#5a6472' }}>—</span>}
              </div>
              <div style={{ width: 54, textAlign: 'center', color: '#8a93a3' }}>{t.replies || 0}</div>
              <div style={{ width: 104, color: '#8a93a3', fontSize: 11.5 }}>{t.created_at}</div>
            </div>
          );
        })}
      </div>

      {showNew && <NewTicketModal onClose={() => setShowNew(false)} onCreated={load} />}
      {openId != null && <TicketDetail id={openId} onClose={() => setOpenId(null)} onChanged={load} />}
    </div>
  );
}

const Kpi = ({ label, value, c }: any) => (
  <div style={S.kpi}><div style={{ fontSize: 11, color: '#8a93a3', fontWeight: 600 }}>{label}</div><div style={{ fontSize: 24, fontWeight: 800, color: c, marginTop: 4 }}>{value}</div></div>
);
const Filter = ({ label, value, set, opts }: any) => (
  <div><div style={{ fontSize: 10.5, color: '#8a93a3', fontWeight: 600, marginBottom: 4 }}>{label}</div>
    <select value={value} onChange={e => set(e.target.value)} style={{ ...S.input, width: 'auto', padding: '7px 10px' }}>
      {opts.map(([v, l]: any) => <option key={v} value={v}>{l}</option>)}
    </select></div>
);

const S: any = {
  page: { padding: 24, maxWidth: 1180, margin: '0 auto', color: '#e8edf2' },
  pageHead: { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 18, gap: 12 },
  newBtn: { padding: '10px 18px', borderRadius: 9, background: 'linear-gradient(90deg,#ff4d4f,#e5484d)', color: '#fff', border: 'none', fontWeight: 800, fontSize: 13, cursor: 'pointer', whiteSpace: 'nowrap', boxShadow: '0 6px 18px rgba(229,72,77,0.35)' },
  scoreBadge: { display: 'flex', alignItems: 'center', gap: 6, padding: '7px 14px', borderRadius: 999, background: 'rgba(245,197,26,0.12)', border: '1px solid rgba(245,197,26,0.4)', color: '#f5c51a', fontWeight: 700, fontSize: 13, whiteSpace: 'nowrap' },
  kpis: { display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 10, marginBottom: 16 },
  kpi: { background: '#2c333e', border: '1px solid #4f596b', borderRadius: 10, padding: '12px 14px' },
  tabs: { display: 'flex', gap: 4, background: '#2c333e', border: '1px solid #4f596b', borderRadius: 9, padding: 3 },
  tab: { padding: '7px 14px', borderRadius: 7, background: 'transparent', border: 'none', color: '#8a93a3', fontWeight: 700, fontSize: 12.5, cursor: 'pointer' },
  tabOn: { background: '#373f4d', color: '#e8edf2' },
  table: { background: '#2c333e', border: '1px solid #4f596b', borderRadius: 12, overflow: 'hidden' },
  row: { display: 'flex', alignItems: 'center', gap: 10, padding: '11px 14px', borderBottom: '1px solid #3a4250', cursor: 'pointer', fontSize: 13 },
  headRow: { background: '#262c36', color: '#8a93a3', fontSize: 11, fontWeight: 700, textTransform: 'uppercase', cursor: 'default' },
  pill: { fontSize: 10.5, fontWeight: 700, padding: '3px 9px', borderRadius: 6, display: 'inline-block' },
  metaPill: { fontSize: 11, color: '#cdd4de', background: '#373f4d', borderRadius: 6, padding: '3px 9px' },
  statusSel: { padding: '6px 8px', borderRadius: 7, background: '#373f4d', border: '1px solid #4f596b', color: '#e8edf2', fontSize: 12 },
  overlay: { position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', zIndex: 5000, display: 'flex', alignItems: 'flex-start', justifyContent: 'center', padding: '60px 16px', overflowY: 'auto' },
  modal: { background: '#262c36', border: '1px solid #4f596b', borderRadius: 14, padding: 20, width: '100%', maxWidth: 480, color: '#e8edf2' },
  reviewCard: { background: '#2c333e', border: '1px solid #4f596b', borderRadius: 10, padding: 14 },
  detailModal: { background: '#262c36', border: '1px solid #4f596b', borderRadius: 14, width: '100%', maxWidth: 620, color: '#e8edf2', display: 'flex', flexDirection: 'column', maxHeight: 'calc(100vh - 96px)', overflow: 'hidden' },
  detailHead: { display: 'flex', justifyContent: 'space-between', gap: 10, padding: '16px 20px', borderBottom: '1px solid #3a4250', flexShrink: 0 },
  convScroll: { flex: 1, overflowY: 'auto', padding: '14px 20px', minHeight: 160, display: 'flex', flexDirection: 'column', gap: 10 },
  bubble: { maxWidth: '85%', padding: '10px 12px', borderRadius: 10, fontSize: 13, lineHeight: 1.5 },
  bubbleMine: { alignSelf: 'flex-end', background: '#33608a22', border: '1px solid #33608a55' },
  bubbleDev: { alignSelf: 'flex-start', background: '#2c333e', border: '1px solid #4f596b' },
  bubbleWho: { fontSize: 11, fontWeight: 700, marginBottom: 4, color: '#9aa4b2' },
  bubbleAt: { fontSize: 10, color: '#6b7482', marginTop: 6 },
  bubbleImg: { maxWidth: '100%', borderRadius: 8, marginTop: 8, border: '1px solid #4f596b' },
  detailFoot: { padding: '12px 20px 16px', borderTop: '1px solid #3a4250', flexShrink: 0, background: '#2a313c' },
  modalHead: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 },
  x: { background: 'transparent', border: 'none', color: '#8a93a3', fontSize: 16, cursor: 'pointer' },
  lbl: { fontSize: 11.5, color: '#8a93a3', fontWeight: 600, display: 'block', marginBottom: 6 },
  input: { width: '100%', padding: '10px 12px', borderRadius: 8, background: '#373f4d', border: '1px solid #4f596b', color: '#e8edf2', fontSize: 13.5, outline: 'none', boxSizing: 'border-box' },
  upload: { display: 'block', border: '1.5px dashed #4f596b', borderRadius: 8, padding: 18, textAlign: 'center', cursor: 'pointer', color: '#8a93a3', fontSize: 12.5 },
  err: { color: '#ff7a7a', fontSize: 12.5, marginTop: 10 },
  submit: { width: '100%', marginTop: 16, padding: '12px', borderRadius: 9, background: 'linear-gradient(90deg,#ff4d4f,#e5484d)', color: '#fff', border: 'none', fontWeight: 800, fontSize: 14, cursor: 'pointer' },
  secondary: { padding: '10px 16px', borderRadius: 9, background: '#373f4d', border: '1px solid #4f596b', color: '#e8edf2', fontWeight: 700, fontSize: 13, cursor: 'pointer' },
};

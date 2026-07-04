import React, { useState, useEffect, useRef } from 'react';
import { apiGet, apiPost, apiPatch, apiDelete } from './api';

// CRM ticketing: a pinned red "Add ticket" button (top-center, all pages) + create modal,
// and a Tickets page listing every ticket with a status workflow.

const SECTIONS = [
  'Dashboard', 'Leads', 'Clients', 'Trading accounts', 'Transactions', 'IB system',
  'Sales agents', 'Network', 'Abuse detection', 'Bonus', 'Copy trading', 'Loyalty',
  'Payments / deposits', 'Withdrawals', 'KYC / verification', 'Settings', 'Client portal',
  'AI assistant', 'Other',
];
const CRITS = [
  { v: 'low', label: 'Low', c: '#8a93a3' },
  { v: 'medium', label: 'Medium', c: '#E8B84B' },
  { v: 'high', label: 'High', c: '#ff8c42' },
  { v: 'critical', label: 'Critical', c: '#ff4d4f' },
];
const STATUSES: any = {
  under_review: { label: 'Under review', c: '#E8B84B' },
  proceed: { label: '✅ Approved · in progress', c: '#22c55e' },
  answered: { label: 'Answered · awaiting maker', c: '#a855f7' },
  done: { label: 'Done', c: '#00e5a0' },
  rejected: { label: 'Rejected', c: '#ff4d4f' },
};
// how the ticket should be handled — creator must choose (no default). Review listed first.
const ROUTES = [
  { v: 'review', label: '📤 Send to Admin for review', c: '#3b82f6' },
  { v: 'fix', label: '🔧 Fix directly', c: '#00e5a0' },
];
const routeMeta = (v: string) => ROUTES.find(r => r.v === v);
const critC = (v: string) => (CRITS.find(c => c.v === v) || CRITS[1]).c;

// Auto-subject from the ticket body (ticket #13): a short one-line title derived from the
// note's content — first sentence / clause, trimmed. Works for Arabic & English.
function makeSubject(note: string): string {
  const oneLine = (note || '').replace(/\s+/g, ' ').trim();
  if (!oneLine) return 'Ticket';
  // prefer the first sentence boundary if it gives a sensible-length title
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

// ─────────────── shared create modal (also reused with onPaste) ───────────────
export function TicketModal({ onClose, onCreated, defaultSection }: any) {
  const [section, setSection] = useState(defaultSection || 'Dashboard');
  const [note, setNote] = useState('');
  const [critical, setCritical] = useState('medium');
  const [route, setRoute] = useState('');   // blank on purpose — creator must choose
  const [shot, setShot] = useState<string>('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [review, setReview] = useState(false);   // review/edit step before submit (ticket #5)

  const onFile = async (f?: File) => { if (f) setShot(await scaleToDataUrl(f)); };
  const onPaste = async (e: React.ClipboardEvent) => {
    const item = Array.from(e.clipboardData.items).find(i => i.type.startsWith('image/'));
    if (item) { const f = item.getAsFile(); if (f) setShot(await scaleToDataUrl(f)); }
  };

  const goReview = () => {
    if (!route) { setErr('Please choose how to handle this ticket.'); return; }
    if (!note.trim()) { setErr('Please write your note.'); return; }
    setErr(''); setReview(true);
  };
  const submit = async () => {
    if (!route) { setErr('Please choose how to handle this ticket.'); return; }
    if (!note.trim()) { setErr('Please write your note.'); return; }
    setBusy(true); setErr('');
    try {
      await apiPost('/tickets', { section, note, critical, route, screenshot: shot || null, page_url: window.location.href });
      onCreated && onCreated();
      onClose();
    } catch (e: any) { setErr(e?.message || 'Could not submit.'); }
    finally { setBusy(false); }
  };

  return (
    <div style={S.overlay} onClick={onClose}>
      <div style={S.modal} onClick={e => e.stopPropagation()} onPaste={onPaste}>
        <div style={S.modalHead}>
          <span style={{ fontSize: 16, fontWeight: 800 }}>{review ? '🔎 Review your ticket' : '🎫 New ticket'}</span>
          <button style={S.x} onClick={onClose}>✕</button>
        </div>

        {review ? (
          <>
            <div style={{ fontSize: 12.5, color: '#8a93a3', marginBottom: 12 }}>Check everything below, then submit — or go back to edit.</div>
            {[['Handling', routeMeta(route)?.label], ['Section', section], ['Critical', critical], ['Note', note]].map(([k, v]: any) => (
              <div key={k} style={{ marginBottom: 10 }}>
                <div style={{ fontSize: 10.5, color: '#8a93a3', fontWeight: 700, textTransform: 'uppercase' }}>{k}</div>
                <div style={{ fontSize: 13.5, color: '#e8edf2', whiteSpace: 'pre-wrap', marginTop: 2 }}>{v}</div>
              </div>
            ))}
            {shot && <img src={shot} alt="screenshot" style={{ width: '100%', borderRadius: 8, border: '1px solid #4f596b', marginTop: 4 }} />}
            {err && <div style={S.err}>{err}</div>}
            <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
              <button onClick={() => setReview(false)} disabled={busy} style={{ flex: '0 0 auto', padding: '12px 18px', borderRadius: 9, background: '#373f4d', border: '1px solid #4f596b', color: '#e8edf2', fontWeight: 700, fontSize: 13.5, cursor: 'pointer' }}>← Edit</button>
              <button onClick={submit} disabled={busy} style={{ ...S.submit, marginTop: 0, flex: 1 }}>{busy ? 'Submitting…' : '✓ Submit ticket'}</button>
            </div>
          </>
        ) : (
        <>
        <label style={S.lbl}>How should we handle this? <span style={{ color: '#ff8c42' }}>*</span></label>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {ROUTES.map(r => (
            <button key={r.v} onClick={() => setRoute(r.v)} style={{
              padding: '11px 14px', borderRadius: 8, cursor: 'pointer', fontSize: 13, fontWeight: 700, textAlign: 'left',
              background: route === r.v ? r.c + '22' : '#373f4d', color: route === r.v ? r.c : '#cdd4de',
              border: `1px solid ${route === r.v ? r.c : '#4f596b'}`,
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
              background: critical === c.v ? c.c : '#373f4d', color: critical === c.v ? '#0b0e14' : '#cdd4de',
              border: `1px solid ${critical === c.v ? c.c : '#4f596b'}`,
            }}>{c.label}</button>
          ))}
        </div>

        <label style={{ ...S.lbl, marginTop: 14 }}>Your note</label>
        <textarea value={note} onChange={e => setNote(e.target.value)} rows={4}
          placeholder="Describe the issue / your note. You can paste a screenshot here (Ctrl+V)."
          style={{ ...S.input, resize: 'vertical', fontFamily: 'inherit' }} />

        <label style={{ ...S.lbl, marginTop: 14 }}>Screenshot (paste above, or upload)</label>
        {shot ? (
          <div style={{ position: 'relative' }}>
            <img src={shot} alt="screenshot" style={{ width: '100%', borderRadius: 8, border: '1px solid #4f596b' }} />
            <button onClick={() => setShot('')} style={{ ...S.x, position: 'absolute', top: 6, right: 6, background: '#000a' }}>✕</button>
          </div>
        ) : (
          <label style={S.upload}>
            <input type="file" accept="image/*" style={{ display: 'none' }} onChange={e => onFile(e.target.files?.[0])} />
            📎 Click to upload — or paste a screenshot anywhere in this box
          </label>
        )}

        {err && <div style={S.err}>{err}</div>}
        <button onClick={goReview} style={S.submit}>Review →</button>
        </>
        )}
      </div>
    </div>
  );
}

// ─────────────── pinned red button (rendered on every page) ───────────────
export function TicketButton() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button onClick={() => setOpen(true)} style={S.pinned} title="Report an issue / add a note">
        🎫 Add Ticket
      </button>
      {open && <TicketModal onClose={() => setOpen(false)} />}
    </>
  );
}

// ─────────────── Tickets admin page ───────────────
export default function TicketsPage() {
  const [tickets, setTickets] = useState<any[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [fStatus, setFStatus] = useState('');
  const [fCrit, setFCrit] = useState('');
  const [detail, setDetail] = useState<any>(null);
  const [adding, setAdding] = useState(false);
  const [reply, setReply] = useState('');
  const [replyImg, setReplyImg] = useState<string>('');   // optional photo on a staff reply
  const [tab, setTab] = useState<'mine' | 'all'>('mine');   // default: My tickets
  const [isAdmin, setIsAdmin] = useState(false);
  const [canCreate, setCanCreate] = useState(false);   // allowlisted staff may create tickets manually
  const [editNote, setEditNote] = useState<string | null>(null);   // admin "edit it myself" mode
  const [members, setMembers] = useState<any[]>([]);   // staff for the transfer picker
  const [transferTo, setTransferTo] = useState('');    // selected member id
  const convRef = useRef<HTMLDivElement>(null);

  useEffect(() => { apiGet('/tickets/members').then((d: any) => setMembers(d?.members || [])).catch(() => {}); }, []);
  useEffect(() => { apiGet('/tickets/can-create').then((d: any) => setCanCreate(!!d?.can_create)).catch(() => {}); }, []);

  // when a ticket opens (or its thread reloads), auto-scroll the conversation to the BOTTOM
  // so the newest messages + the reply box are in view.
  useEffect(() => {
    if (detail && convRef.current) {
      const el = convRef.current;
      requestAnimationFrame(() => { el.scrollTop = el.scrollHeight; });
    }
  }, [detail]);

  const load = () => {
    const qs = new URLSearchParams();
    if (fStatus) qs.set('status', fStatus);
    if (fCrit) qs.set('critical', fCrit);
    if (tab === 'mine') qs.set('mine', '1');
    apiGet('/tickets?' + qs.toString()).then((d: any) => { setTickets(d?.tickets || []); setIsAdmin(!!d?.is_admin); }).catch(() => {});
    apiGet('/tickets/stats').then(setStats).catch(() => {});
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [fStatus, fCrit, tab]);

  const decide = async (t: any, action: string, comment?: string) => {
    const r = await apiPost(`/tickets/${t.id}/decision`, { action, comment: comment || '' });
    if (r && r.detail && !r.ok) { window.alert(r.detail); return; }
    setReply(''); apiGet(`/tickets/${t.id}`).then(setDetail).catch(() => {}); load();
  };
  const saveEdit = async (t: any) => {
    if (!editNote || !editNote.trim()) { setEditNote(null); return; }
    const r = await apiPatch(`/tickets/${t.id}`, { note: editNote });
    if (r && r.detail && !r.ok) { window.alert(r.detail); return; }
    setEditNote(null); apiGet(`/tickets/${t.id}`).then(setDetail).catch(() => {}); load();
  };
  const transfer = async (t: any) => {
    if (!transferTo) { window.alert('Pick a member to transfer this ticket to.'); return; }
    const r = await apiPost(`/tickets/${t.id}/transfer`, { to_user_id: Number(transferTo), comment: reply });
    if (r && r.detail && !r.ok) { window.alert(r.detail); return; }
    setTransferTo(''); setReply(''); apiGet(`/tickets/${t.id}`).then(setDetail).catch(() => {}); load();
  };

  const setStatus = async (t: any, s: string) => {
    const r = await apiPatch(`/tickets/${t.id}/status`, { status: s });
    if (r && r.detail) { window.alert(r.detail); load(); return; }   // e.g. 403 "only the maker closes"
    load(); if (detail?.id === t.id) setDetail({ ...detail, status: s });
  };
  const remove = async (t: any) => { if (!window.confirm('Delete this ticket?')) return; await apiDelete(`/tickets/${t.id}`); setDetail(null); load(); };
  const openDetail = (id: number) => { setReply(''); setReplyImg(''); setEditNote(null); apiGet(`/tickets/${id}`).then((d: any) => { setDetail(d); setTimeout(load, 400); }).catch(() => {}); };
  const onReplyFile = async (f?: File) => { if (f) setReplyImg(await scaleToDataUrl(f)); };
  const onReplyPaste = async (e: React.ClipboardEvent) => {
    const item = Array.from(e.clipboardData.items).find(i => i.type.startsWith('image/'));
    if (item) { const f = item.getAsFile(); if (f) setReplyImg(await scaleToDataUrl(f)); }
  };
  const sendReply = async (t: any) => {
    if (!reply.trim() && !replyImg) return;
    const r = await apiPost(`/tickets/${t.id}/reply`, { body: reply, image: replyImg || null });
    if (r && r.detail && !r.ok) { window.alert(r.detail); return; }
    setReply(''); setReplyImg(''); apiGet(`/tickets/${t.id}`).then(setDetail).catch(() => {}); load();
  };
  const escalate = async (t: any) => {
    const r = await apiPost(`/tickets/${t.id}/escalate`, { body: reply });
    if (r && r.detail && !r.ok) { window.alert(r.detail); return; }
    setReply(''); apiGet(`/tickets/${t.id}`).then(setDetail).catch(() => {}); load();
  };

  return (
    <div style={S.page}>
      <div style={S.pageHead}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 800, margin: 0, display: 'flex', alignItems: 'center', gap: 10 }}>
            🎫 Tickets
            {tickets.filter(t => t.unread).length > 0 && <span style={{ fontSize: 12, fontWeight: 800, color: '#fff', background: '#ff3b30', borderRadius: 99, padding: '2px 9px' }}>{tickets.filter(t => t.unread).length} new</span>}
            {tickets.filter(t => t.needs_approval && !t.approved).length > 0 && <span style={{ fontSize: 12, fontWeight: 800, color: '#fff', background: '#6366f1', borderRadius: 99, padding: '2px 9px' }}>🛡 {tickets.filter(t => t.needs_approval && !t.approved).length} need approval</span>}
          </h1>
          <div style={{ fontSize: 13, color: '#8a93a3', marginTop: 4 }}>Your tickets &amp; ones sent to you are in <b style={{ color: '#c4b5fd' }}>My tickets</b>; everything is under <b style={{ color: '#c4b5fd' }}>All</b>. Admins can approve / reject / send back / edit, and transfer a ticket to another member. A red dot = something new to read.</div>
        </div>
        {/* Manual ticket creation is disabled except for allowlisted staff (e.g. abbask@tnfx.co). */}
        {canCreate && (
          <button onClick={() => setAdding(true)}
            style={{ padding: '10px 18px', borderRadius: 9, background: '#6366f1', border: 'none',
              color: '#fff', fontWeight: 800, fontSize: 13.5, cursor: 'pointer', whiteSpace: 'nowrap' }}>
            + New ticket
          </button>
        )}
      </div>
      {adding && <TicketModal onClose={() => setAdding(false)} onCreated={() => { setAdding(false); load(); }} />}

      {stats && (
        <div style={S.kpis}>
          <Kpi label="Under review" value={stats.under_review} c="#E8B84B" />
          <Kpi label="Proceed" value={stats.proceed} c="#3b82f6" />
          <Kpi label="Done" value={stats.done} c="#00e5a0" />
          <Kpi label="Urgent open" value={stats.urgent_open} c="#ff4d4f" />
        </div>
      )}

      <div style={{ display: 'flex', gap: 14, marginBottom: 14, flexWrap: 'wrap', alignItems: 'flex-end' }}>
        {/* segmented My tickets / All tabs — sits beside the Status & Critical filters */}
        <div>
          <div style={{ fontSize: 10.5, color: '#8a93a3', fontWeight: 600, marginBottom: 4 }}>View</div>
          <div style={{ display: 'inline-flex', background: '#222831', borderRadius: 9, padding: 3, border: '1px solid #4f596b' }}>
            {([['mine', isAdmin ? '👤 My tickets & reviews' : '👤 My tickets'], ['all', '🗂 All']] as const).map(([k, lbl]) => (
              <button key={k} onClick={() => setTab(k as any)} style={{
                padding: '7px 14px', borderRadius: 7, cursor: 'pointer', fontSize: 12.5, fontWeight: 700, fontFamily: 'inherit',
                background: tab === k ? 'linear-gradient(90deg,#a855f7,#7c3aed)' : 'transparent',
                color: tab === k ? '#fff' : '#9aa3b3', border: 'none', transition: 'all .12s',
              }}>{lbl}</button>
            ))}
          </div>
        </div>
        <Filter label="Status" value={fStatus} set={setFStatus} opts={[['', 'All'], ['under_review', 'Under review'], ['proceed', 'Approved · in progress'], ['answered', 'Answered'], ['rejected', 'Rejected'], ['done', 'Done']]} />
        <Filter label="Critical" value={fCrit} set={setFCrit} opts={[['', 'All'], ...CRITS.map(c => [c.v, c.label] as [string, string])]} />
      </div>

      <div style={S.table}>
        <div style={{ ...S.row, ...S.headRow }}>
          <div style={{ width: 44 }}>#</div>
          <div style={{ width: 130 }}>When</div>
          <div style={{ flex: 1 }}>Who / source</div>
          <div style={{ width: 130 }}>Section</div>
          <div style={{ width: 80 }}>Critical</div>
          <div style={{ flex: 1.4 }}>Note</div>
          <div style={{ width: 120 }}>Status</div>
          <div style={{ width: 150 }}>Action</div>
        </div>
        {tickets.length === 0 && <div style={{ padding: 24, color: '#8a93a3', fontSize: 13 }}>No tickets.</div>}
        {tickets.map(t => (
          <div key={t.id} style={{ ...S.row, ...(t.unread ? { background: 'rgba(229,72,77,0.06)' } : {}), ...(t.needs_approval && !t.approved ? { background: 'rgba(99,102,241,0.10)', boxShadow: 'inset 3px 0 0 #6366f1' } : {}) }} onClick={() => openDetail(t.id)}>
            <div style={{ width: 44, color: '#8a93a3', display: 'flex', alignItems: 'center', gap: 6 }}>
              {t.unread && <span title="New reply — click to read" style={{ width: 9, height: 9, borderRadius: '50%', background: '#ff3b30', flexShrink: 0, boxShadow: '0 0 6px rgba(255,59,48,0.8)' }} />}
              #{t.id}
            </div>
            <div style={{ width: 130, fontSize: 12, color: '#cdd4de' }}>{t.created_at}</div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontWeight: 700, fontSize: 13 }}>{t.creator}</div>
              <div style={{ fontSize: 11, color: '#8a93a3' }}>
                {t.source}{t.for_ai ? ' · AI note' : ''}{t.has_screenshot ? ' · 📷' : ''}{t.replies > 0 ? ` · 💬 ${t.replies}` : ''}
                {t.route && <span style={{ color: routeMeta(t.route)?.c, fontWeight: 700 }}>{' · '}{t.route === 'fix' ? '🔧 Fix directly' : '📤 For review'}</span>}
              </div>
              {t.needs_approval && !t.approved && <span style={S.approvalTag}>🛡 NEEDS APPROVAL</span>}
              {t.approved && <span style={{ ...S.approvalTag, background: 'rgba(34,197,94,0.15)', color: '#22c55e', border: '1px solid #22c55e55' }}>✓ Approved</span>}
              {t.assigned_to_me && <span style={{ ...S.approvalTag, background: 'rgba(20,184,166,0.18)', color: '#2dd4bf', border: '1px solid #14b8a655' }}>🔀 Transferred to you</span>}
              {t.assigned_to && !t.assigned_to_me && <span style={{ ...S.approvalTag, background: 'rgba(20,184,166,0.10)', color: '#5eead4', border: '1px solid #14b8a644' }}>🔀 → {t.assigned_to_name}</span>}
            </div>
            <div style={{ width: 130, fontSize: 12 }}>{t.section}</div>
            <div style={{ width: 80 }}><span style={{ ...S.pill, background: critC(t.critical) + '22', color: critC(t.critical), border: `1px solid ${critC(t.critical)}55` }}>{t.critical}</span></div>
            <div style={{ flex: 1.4, fontSize: 12, color: '#cdd4de', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{t.note}</div>
            <div style={{ width: 120 }}><span style={{ ...S.pill, background: STATUSES[t.status].c + '22', color: STATUSES[t.status].c, border: `1px solid ${STATUSES[t.status].c}55` }}>{STATUSES[t.status].label}</span></div>
            <div style={{ width: 150 }} onClick={e => e.stopPropagation()}>
              <select value={t.status === 'done' ? 'done' : t.status} onChange={e => setStatus(t, e.target.value)} style={S.statusSel}>
                <option value="under_review">Under review</option>
                <option value="proceed">Proceed</option>
                <option value="answered">Answered</option>
                {t.status === 'done' && <option value="done">Done</option>}
              </select>
            </div>
          </div>
        ))}
      </div>

      {detail && (
        <div style={S.overlay} onClick={() => setDetail(null)}>
          <div style={S.detailModal} onClick={e => e.stopPropagation()}>
            {/* ── PINNED HEADER: subject stays visible while the conversation scrolls ── */}
            <div style={S.detailHead}>
              <div style={{ minWidth: 0, flex: 1 }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: '#8a93a3', letterSpacing: '0.03em' }}>TICKET #{detail.id}</div>
                <div style={{ fontSize: 16.5, fontWeight: 800, color: '#fff', lineHeight: 1.3, marginTop: 2 }}>{makeSubject(detail.note)}</div>
                <div style={{ fontSize: 12, color: '#8a93a3', marginTop: 4 }}>Created by {detail.creator} · {detail.created_at}</div>
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 8 }}>
                  <span style={{ ...S.pill, background: critC(detail.critical) + '22', color: critC(detail.critical), border: `1px solid ${critC(detail.critical)}55` }}>{detail.critical}</span>
                  <span style={{ ...S.pill, background: STATUSES[detail.status].c + '22', color: STATUSES[detail.status].c }}>{STATUSES[detail.status].label}</span>
                  {detail.route && <span style={{ ...S.pill, background: routeMeta(detail.route)?.c + '22', color: routeMeta(detail.route)?.c, border: `1px solid ${routeMeta(detail.route)?.c}55` }}>{routeMeta(detail.route)?.label}</span>}
                  <span style={S.metaPill}>{detail.section}</span>
                  {detail.needs_approval && !detail.approved && <span style={S.approvalTag}>🛡 APPROVAL NEEDED</span>}
                  {detail.approved && <span style={{ ...S.approvalTag, background: 'rgba(34,197,94,0.15)', color: '#22c55e', border: '1px solid #22c55e55' }}>✓ Approved</span>}
                  {detail.assigned_to_name && <span style={{ ...S.approvalTag, background: 'rgba(20,184,166,0.18)', color: '#2dd4bf', border: '1px solid #14b8a655' }}>🔀 {detail.assigned_to_me ? 'Transferred to you' : `Transferred to ${detail.assigned_to_name}`}</span>}
                </div>
              </div>
              <button style={S.x} onClick={() => setDetail(null)}>✕</button>
            </div>

            {/* ── SCROLLABLE CONVERSATION: oldest at top, newest at the bottom ── */}
            <div ref={convRef} style={S.convScroll}>
              {(() => {
                const original = {
                  author_type: detail.creator_type === 'client' ? 'client' : 'staff',
                  author: detail.creator, body: detail.note, at: detail.created_at, isOriginal: true,
                };
                const thread = [original, ...(detail.replies || [])];   // chronological
                return thread.map((rp: any, i: number) => {
                  const ai = rp.author_type === 'ai';
                  const client = rp.author_type === 'client';
                  const c = ai ? '#a855f7' : (client ? '#3b82f6' : '#00b3a4');
                  return (
                    <div key={i} style={{ marginBottom: 10, display: 'flex', justifyContent: client ? 'flex-start' : 'flex-end' }}>
                      <div style={{ maxWidth: '88%', background: c + '14', border: `1px solid ${c}44`, borderLeft: `3px solid ${c}`, borderRadius: 10, padding: '8px 11px' }}>
                        <div style={{ fontSize: 11, color: c, fontWeight: 700, marginBottom: 3 }}>
                          {ai ? '🤖 ' : (client ? '👤 ' : '🛠 ')}{rp.author} · {rp.at}
                          {rp.isOriginal && <span style={{ marginLeft: 6, fontSize: 9.5, fontWeight: 800, color: '#8a93a3', background: '#373f4d', borderRadius: 5, padding: '1px 6px' }}>ORIGINAL</span>}
                        </div>
                        {rp.body && <div style={{ fontSize: 13, color: '#e8edf2', whiteSpace: 'pre-wrap', lineHeight: 1.5 }}>{rp.body}</div>}
                        {rp.image && <a href={rp.image} target="_blank" rel="noreferrer"><img src={rp.image} alt="reply attachment" style={{ width: '100%', borderRadius: 8, border: '1px solid #4f596b', marginTop: 6 }} /></a>}
                        {rp.isOriginal && detail.page_url && <div style={{ fontSize: 11, color: '#8a93a3', marginTop: 8, wordBreak: 'break-all' }}>📍 {detail.page_url}</div>}
                        {rp.isOriginal && detail.screenshot && <img src={detail.screenshot} alt="screenshot" style={{ width: '100%', borderRadius: 8, border: '1px solid #4f596b', marginTop: 8 }} />}
                      </div>
                    </div>
                  );
                });
              })()}
            </div>

            {/* ── PINNED FOOTER ── */}
            <div style={S.detailFoot}>
              {/* ADMIN DECISION — shown when the request was sent for review AND you're an admin
                  OR a designated handler for this ticket's client (e.g. bakera on baker's tickets) */}
              {detail.needs_approval && (detail.can_handle ?? detail.is_admin) && editNote === null && (
                <div style={{ background: 'rgba(99,102,241,0.10)', border: '1px solid #6366f155', borderRadius: 10, padding: '10px 12px', marginBottom: 10 }}>
                  <div style={{ fontSize: 11.5, fontWeight: 800, color: '#a5b4fc', marginBottom: 6 }}>🛡 ADMIN DECISION — this request was sent to you for review</div>
                  <div style={{ fontSize: 11, color: '#8a93a3', marginBottom: 8 }}>For Reject / Send back, type your reason or comments in the reply box below first.</div>
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                    <button onClick={() => decide(detail, 'approve', reply)}
                      style={{ padding: '9px 14px', borderRadius: 8, cursor: 'pointer', border: 'none', color: '#fff', fontWeight: 800, fontSize: 12.5, background: 'linear-gradient(90deg,#10b981,#059669)' }}>✅ Approve</button>
                    <button onClick={() => { if (!reply.trim()) { window.alert('Type the reason for rejection in the box below.'); return; } decide(detail, 'reject', reply); }}
                      style={{ padding: '9px 14px', borderRadius: 8, cursor: 'pointer', border: 'none', color: '#fff', fontWeight: 800, fontSize: 12.5, background: 'linear-gradient(90deg,#ef4444,#dc2626)' }}>❌ Reject</button>
                    <button onClick={() => { if (!reply.trim()) { window.alert('Type the comments for the creator in the box below.'); return; } decide(detail, 'send_back', reply); }}
                      style={{ padding: '9px 14px', borderRadius: 8, cursor: 'pointer', border: 'none', color: '#fff', fontWeight: 800, fontSize: 12.5, background: 'linear-gradient(90deg,#f59e0b,#d97706)' }}>↩️ Send back to creator</button>
                    <button onClick={() => setEditNote(detail.note || '')}
                      style={{ padding: '9px 14px', borderRadius: 8, cursor: 'pointer', border: 'none', color: '#fff', fontWeight: 800, fontSize: 12.5, background: 'linear-gradient(90deg,#3b82f6,#2563eb)' }}>✏️ Edit it myself</button>
                  </div>
                  {/* Transfer to another member */}
                  <div style={{ display: 'flex', gap: 8, marginTop: 10, alignItems: 'center', flexWrap: 'wrap' }}>
                    <span style={{ fontSize: 11.5, color: '#8a93a3', fontWeight: 700 }}>🔀 Transfer to:</span>
                    <select value={transferTo} onChange={e => setTransferTo(e.target.value)}
                      style={{ ...S.input, width: 'auto', minWidth: 180, padding: '7px 10px', flex: 1 }}>
                      <option value="">Choose a member…</option>
                      {members.map(m => <option key={m.id} value={m.id}>{m.name}{m.role ? ` · ${m.role}` : ''}</option>)}
                    </select>
                    <button onClick={() => transfer(detail)} disabled={!transferTo}
                      style={{ padding: '8px 14px', borderRadius: 8, cursor: transferTo ? 'pointer' : 'default', opacity: transferTo ? 1 : 0.5, border: 'none', color: '#fff', fontWeight: 800, fontSize: 12.5, background: 'linear-gradient(90deg,#14b8a6,#0d9488)' }}>Transfer</button>
                  </div>
                </div>
              )}

              {editNote !== null ? (
                /* Admin "edit it myself" mode */
                <div>
                  <div style={{ fontSize: 11.5, fontWeight: 800, color: '#8fcfe6', marginBottom: 6 }}>✏️ Editing the request text</div>
                  <textarea value={editNote} onChange={e => setEditNote(e.target.value)} rows={4}
                    style={{ ...S.input, resize: 'vertical', fontFamily: 'inherit' }} />
                  <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                    <button onClick={() => saveEdit(detail)}
                      style={{ flex: 1, padding: '11px', borderRadius: 9, border: 'none', color: '#fff', fontWeight: 800, fontSize: 13, cursor: 'pointer', background: 'linear-gradient(90deg,#10b981,#059669)' }}>✓ Save edit</button>
                    <button onClick={() => setEditNote(null)}
                      style={{ flex: '0 0 auto', padding: '11px 16px', borderRadius: 9, cursor: 'pointer', background: 'transparent', border: '1px solid #4f596b', color: '#cdd4de', fontWeight: 700, fontSize: 13 }}>Cancel</button>
                  </div>
                </div>
              ) : (
                <>
                  <textarea value={reply} onChange={e => setReply(e.target.value)} onPaste={onReplyPaste} rows={2}
                    placeholder="Type your reply… (you can also attach or paste a photo)"
                    style={{ ...S.input, resize: 'vertical', fontFamily: 'inherit' }} />
                  {replyImg ? (
                    <div style={{ position: 'relative', marginTop: 8 }}>
                      <img src={replyImg} alt="reply attachment" style={{ maxHeight: 140, borderRadius: 8, border: '1px solid #4f596b' }} />
                      <button onClick={() => setReplyImg('')} title="Remove photo"
                        style={{ position: 'absolute', top: 4, left: 4, width: 22, height: 22, borderRadius: '50%', border: 'none', background: 'rgba(0,0,0,0.65)', color: '#fff', fontWeight: 800, cursor: 'pointer' }}>✕</button>
                    </div>
                  ) : (
                    <label style={{ display: 'inline-block', marginTop: 8, fontSize: 12, color: '#8a93a3', cursor: 'pointer', border: '1px dashed #4f596b', borderRadius: 8, padding: '6px 10px' }}>
                      <input type="file" accept="image/*" style={{ display: 'none' }} onChange={e => onReplyFile(e.target.files?.[0])} />
                      📎 Attach a photo
                    </label>
                  )}
                  <div style={{ display: 'flex', gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
                    <button onClick={() => sendReply(detail)} disabled={!reply.trim() && !replyImg}
                      style={{ flex: 1, minWidth: 150, padding: '11px 14px', borderRadius: 9, border: 'none', color: '#fff', fontWeight: 800, fontSize: 13, cursor: (reply.trim() || replyImg) ? 'pointer' : 'default', opacity: (reply.trim() || replyImg) ? 1 : 0.5, background: 'linear-gradient(90deg,#a855f7,#7c3aed)' }}>💬 Reply &amp; mark Answered</button>
                    <button onClick={() => escalate(detail)}
                      style={{ flex: 1, minWidth: 150, padding: '11px 14px', borderRadius: 9, border: 'none', color: '#fff', fontWeight: 800, fontSize: 13, cursor: 'pointer', background: 'linear-gradient(90deg,#3b82f6,#2563eb)' }}>📤 Send to Admin for Review</button>
                    {detail.status !== 'done' &&
                      <button onClick={() => setStatus(detail, 'done')} title="Closes the ticket"
                        style={{ flex: '0 0 auto', padding: '11px 16px', borderRadius: 9, cursor: 'pointer', background: 'transparent', border: '1px solid #00e5a055', color: '#00e5a0', fontWeight: 800, fontSize: 13 }}>✓ Done / Close</button>}
                  </div>
                  {(detail.can_handle ?? detail.is_admin) && !detail.needs_approval && (
                    <div style={{ display: 'flex', gap: 8, marginTop: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                      <span style={{ fontSize: 11, color: '#8a93a3', fontWeight: 700 }}>🔀 Transfer to:</span>
                      <select value={transferTo} onChange={e => setTransferTo(e.target.value)}
                        style={{ ...S.input, width: 'auto', minWidth: 170, padding: '6px 9px', flex: 1, fontSize: 12 }}>
                        <option value="">Choose a member…</option>
                        {members.map(m => <option key={m.id} value={m.id}>{m.name}{m.role ? ` · ${m.role}` : ''}</option>)}
                      </select>
                      <button onClick={() => transfer(detail)} disabled={!transferTo}
                        style={{ padding: '7px 13px', borderRadius: 8, cursor: transferTo ? 'pointer' : 'default', opacity: transferTo ? 1 : 0.5, border: 'none', color: '#fff', fontWeight: 800, fontSize: 12, background: 'linear-gradient(90deg,#14b8a6,#0d9488)' }}>Transfer</button>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {adding && <TicketModal onClose={() => setAdding(false)} onCreated={load} />}
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
  pinned: { position: 'fixed', top: 10, left: '50%', transform: 'translateX(-50%)', zIndex: 4000,
    padding: '8px 18px', borderRadius: 999, background: 'linear-gradient(90deg,#ff4d4f,#e5484d)', color: '#fff',
    border: 'none', fontSize: 13, fontWeight: 800, cursor: 'pointer', boxShadow: '0 6px 22px rgba(229,72,77,0.5)', fontFamily: 'inherit' },
  page: { padding: 24, maxWidth: 1180, margin: '0 auto', color: '#e8edf2' },
  pageHead: { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 18 },
  addBtn: { padding: '9px 16px', borderRadius: 8, background: '#373f4d', border: '1px solid #ff4d4f', color: '#ff4d4f', fontWeight: 700, fontSize: 12.5, cursor: 'pointer' },
  kpis: { display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 10, marginBottom: 16 },
  kpi: { background: '#2c333e', border: '1px solid #4f596b', borderRadius: 10, padding: '12px 14px' },
  table: { background: '#2c333e', border: '1px solid #4f596b', borderRadius: 12, overflow: 'hidden' },
  row: { display: 'flex', alignItems: 'center', gap: 10, padding: '11px 14px', borderBottom: '1px solid #3a4250', cursor: 'pointer', fontSize: 13 },
  headRow: { background: '#262c36', color: '#8a93a3', fontSize: 11, fontWeight: 700, textTransform: 'uppercase', cursor: 'default' },
  pill: { fontSize: 10.5, fontWeight: 700, padding: '3px 9px', borderRadius: 6, textTransform: 'capitalize', display: 'inline-block' },
  approvalTag: { display: 'inline-block', marginTop: 4, fontSize: 10, fontWeight: 800, letterSpacing: '0.04em', color: '#fff', background: 'linear-gradient(90deg,#6366f1,#7c3aed)', borderRadius: 6, padding: '3px 9px', boxShadow: '0 0 10px rgba(99,102,241,0.5)' },
  metaPill: { fontSize: 11, color: '#cdd4de', background: '#373f4d', borderRadius: 6, padding: '3px 9px' },
  statusSel: { width: '100%', padding: '6px 8px', borderRadius: 7, background: '#373f4d', border: '1px solid #4f596b', color: '#e8edf2', fontSize: 12 },
  overlay: { position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', zIndex: 5000, display: 'flex', alignItems: 'flex-start', justifyContent: 'center', padding: '60px 16px', overflowY: 'auto' },
  modal: { background: '#262c36', border: '1px solid #4f596b', borderRadius: 14, padding: 20, width: '100%', maxWidth: 460, color: '#e8edf2' },
  detailModal: { background: '#262c36', border: '1px solid #4f596b', borderRadius: 14, width: '100%', maxWidth: 620, color: '#e8edf2', display: 'flex', flexDirection: 'column', maxHeight: 'calc(100vh - 96px)', overflow: 'hidden' },
  detailHead: { display: 'flex', justifyContent: 'space-between', gap: 10, padding: '16px 20px', borderBottom: '1px solid #3a4250', flexShrink: 0, background: '#262c36' },
  convScroll: { flex: 1, overflowY: 'auto', padding: '14px 20px', minHeight: 140 },
  detailFoot: { padding: '12px 20px 16px', borderTop: '1px solid #3a4250', flexShrink: 0, background: '#2a313c' },
  modalHead: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 },
  x: { background: 'transparent', border: 'none', color: '#8a93a3', fontSize: 16, cursor: 'pointer' },
  lbl: { fontSize: 11.5, color: '#8a93a3', fontWeight: 600, display: 'block', marginBottom: 6 },
  input: { width: '100%', padding: '10px 12px', borderRadius: 8, background: '#373f4d', border: '1px solid #4f596b', color: '#e8edf2', fontSize: 13.5, outline: 'none', boxSizing: 'border-box' },
  upload: { display: 'block', border: '1.5px dashed #4f596b', borderRadius: 8, padding: 18, textAlign: 'center', cursor: 'pointer', color: '#8a93a3', fontSize: 12.5 },
  err: { color: '#ff7a7a', fontSize: 12.5, marginTop: 10 },
  submit: { width: '100%', marginTop: 16, padding: '12px', borderRadius: 9, background: 'linear-gradient(90deg,#ff4d4f,#e5484d)', color: '#fff', border: 'none', fontWeight: 800, fontSize: 14, cursor: 'pointer' },
};

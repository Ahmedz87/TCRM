import React, { useState, useEffect } from 'react';
import { apiGet } from './api';

// Loads a proof image with the staff bearer token (a bare <img> can't send the auth header).
function AuthImg({ proofId, style }: { proofId: number; style?: any }) {
  const [src, setSrc] = useState('');
  useEffect(() => {
    let url = ''; const tok = localStorage.getItem('token') || '';
    fetch(`/api/payments/manual-deposits/${proofId}/image`, { headers: { Authorization: 'Bearer ' + tok } })
      .then(r => r.ok ? r.blob() : Promise.reject()).then(b => { url = URL.createObjectURL(b); setSrc(url); }).catch(() => {});
    return () => { if (url) URL.revokeObjectURL(url); };
  }, [proofId]);
  if (!src) return <div style={{ ...style, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#566', fontSize: 11 }}>no image</div>;
  return <img src={src} alt="proof" style={style} />;
}

const inp: any = { width: '100%', padding: '8px 10px', borderRadius: 8, background: '#262c36', border: '1px solid #2f3a48', color: '#e8edf2', fontSize: 13, outline: 'none', boxSizing: 'border-box' };

// Shared "case-file" popup for reviewing a portal deposit / withdrawal request.
// Fetches the full detail (payment + optional receipt/OCR + client + recent deposit/withdraw comments)
// by the money-request id (rid). For a PENDING request it exposes Approve / Reject (Reject asks for a
// reason). The parent supplies onApprove/onReject so it owns the action endpoint.
export default function DepositCaseModal({ rid, reasons, canAct, onClose, onApprove, onReject }: {
  rid: number; reasons: string[]; canAct: boolean;
  onClose: () => void; onApprove: () => void; onReject: (reason: string) => void;
}) {
  const [d, setD] = useState<any>(null);
  const [zoom, setZoom] = useState(false);
  const [rejMode, setRejMode] = useState(false);
  const [rejReason, setRejReason] = useState('');
  const [rejCustom, setRejCustom] = useState('');
  useEffect(() => { apiGet(`/transactions/requests/${rid}/detail`).then(setD).catch(() => setD({ _err: true })); }, [rid]);

  const shell = (body: any) => (
    <div onClick={onClose} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.75)', zIndex: 100000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}>
      <div onClick={e => e.stopPropagation()} style={{ background: '#12161f', border: '1px solid #232d3a', borderRadius: 14, width: 'min(920px,96vw)', maxHeight: '92vh', overflow: 'auto' }}>{body}</div>
    </div>
  );
  if (!d) return shell(<div style={{ padding: 40, color: '#8A93A3', fontSize: 13 }}>Loading…</div>);
  if (d._err) return shell(<div style={{ padding: 40, color: '#f0556a', fontSize: 13 }}>Could not load this request (back-office access required).</div>);

  const st = (d.status || '').toLowerCase();
  const rejected = st === 'rejected';
  const done = ['approved', 'completed', 'confirmed', 'done', 'cancelled'].includes(st);
  const pending = !rejected && !done;   // anything not finalised is actionable (pending / pending_payment / review …)
  const hdrCol = rejected ? '#f0556a' : pending ? '#E8B84B' : '#3ad29f';
  const hdrTxt = rejected ? '✕ Rejected' : pending ? '● Pending' : '✓ Approved';
  const kindL = (d.kind || 'deposit') === 'withdraw' ? 'withdrawal' : 'deposit';
  const isDep = kindL === 'deposit';
  const vc = d.verdict === 'reject' ? '#f0556a' : d.verdict === 'approve' ? '#3ad29f' : '#E8B84B';
  const row = (k: string, v: any, hl?: string) => <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, padding: '7px 0', borderBottom: '1px solid #232d3a', fontSize: 12.5 }}><span style={{ color: '#8A93A3' }}>{k}</span><span style={{ fontWeight: 600, color: hl || '#e8edf2', textAlign: 'right', wordBreak: 'break-all', fontFamily: /card|wallet|txn|Transaction|Account/i.test(k) ? 'monospace' : 'inherit' }}>{v || '—'}</span></div>;

  return shell(
    <>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '14px 18px', borderBottom: `1px solid ${hdrCol}55` }}>
        <div style={{ fontSize: 15, fontWeight: 800, color: hdrCol }}>{hdrTxt} {kindL} — review</div>
        <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#8A93A3', fontSize: 22, cursor: 'pointer' }}>×</button>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr' }}>
        <div style={{ padding: 18, borderRight: '1px solid #232d3a' }}>
          <div style={{ fontSize: 11, letterSpacing: 1, textTransform: 'uppercase', color: '#8A93A3', fontWeight: 700, marginBottom: 8 }}>Payment details</div>
          {row('Type', kindL, isDep ? '#3ad29f' : '#ff6b6b')}
          {row('Amount', `$${(d.amount || 0).toLocaleString('en-GB')}`)}
          {d.ocr_amount != null && Math.abs(d.ocr_amount - d.amount) > 0.5 && row('OCR amount', `$${d.ocr_amount.toLocaleString('en-GB')}`, '#f0556a')}
          {row('Method', d.method)}
          {row('Requested', d.date)}
          {isDep && (d.company_card || d.company_card_name || d.company_account) && <>
            <div style={{ fontSize: 11, color: '#8A93A3', margin: '12px 0 4px', fontWeight: 700 }}>RECEIVER — company card</div>
            {row('Card name', d.company_card_name)}
            {row('Card number', d.company_card)}
            {row('Account', d.company_account)}
          </>}
          {isDep && (d.ocr_wallet_id || d.entered_wallet_id || d.ocr_txid || d.entered_txid || d.ocr_date) && <>
            <div style={{ fontSize: 11, color: '#8A93A3', margin: '12px 0 4px', fontWeight: 700 }}>SENDER — from OCR</div>
            {row('Sender wallet', d.ocr_wallet_id || d.entered_wallet_id)}
            {row('Transaction ID', d.ocr_txid || d.entered_txid)}
            {row('Receipt date', d.ocr_date)}
          </>}
          {isDep && d.verdict && <div style={{ marginTop: 12, padding: '8px 10px', borderRadius: 8, background: 'rgba(232,184,75,0.06)', border: '1px solid #2f3a48' }}>
            <div style={{ fontSize: 11, color: '#8A93A3', fontWeight: 700 }}>AI VERDICT</div>
            <div style={{ color: vc, fontWeight: 700, textTransform: 'capitalize' }}>{d.verdict === 'approve' ? 'approved' : d.verdict === 'reject' ? 'rejected' : 'review'}</div>
            {d.reasons && <div style={{ fontSize: 11, color: '#cfd6e0', marginTop: 4 }}>{d.reasons}</div>}
          </div>}
        </div>
        <div style={{ padding: 18 }}>
          <div style={{ fontSize: 11, letterSpacing: 1, textTransform: 'uppercase', color: '#8A93A3', fontWeight: 700, marginBottom: 8 }}>Client</div>
          {row('Name', d.name)}{row('Login', `#${d.login}`)}{row('Phone', d.phone)}{row('Email', d.email)}
          {isDep && <>
            <div style={{ fontSize: 11, color: '#8A93A3', margin: '12px 0 6px', fontWeight: 700 }}>RECEIPT</div>
            {d.has_image && d.proof_id ? <div onClick={() => setZoom(true)} style={{ cursor: 'zoom-in' }}><AuthImg proofId={d.proof_id} style={{ width: '100%', maxHeight: 230, objectFit: 'contain', borderRadius: 8, border: '1px solid #2f3a48', background: '#0d1117' }} /></div> : <div style={{ color: '#566', fontSize: 12 }}>No receipt uploaded</div>}
          </>}
          <div style={{ fontSize: 11, color: '#8A93A3', margin: '14px 0 6px', fontWeight: 700 }}>RECENT DEPOSIT / WITHDRAW COMMENTS</div>
          {(d.comments || []).length === 0 ? <div style={{ color: '#566', fontSize: 11.5 }}>No comments yet.</div> :
            (d.comments || []).map((cm: any, i: number) => (
              <div key={i} style={{ fontSize: 11.5, padding: '6px 0', borderBottom: '1px solid #232d3a' }}>
                <div style={{ color: '#cfd6e0' }}>{cm.note || cm.action}</div>
                <div style={{ color: '#667', fontSize: 10 }}>{cm.date}{cm.by ? ` · ${cm.by}` : ''}</div>
              </div>
            ))}
        </div>
      </div>
      {pending && canAct && (
        <div style={{ padding: '14px 18px', borderTop: '1px solid #232d3a' }}>
          {!rejMode ? (
            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
              <button onClick={() => setRejMode(true)} style={{ color: '#f0556a', background: 'none', border: '1px solid #3a2530', borderRadius: 8, padding: '9px 18px', fontWeight: 700, cursor: 'pointer' }}>Reject</button>
              <button onClick={() => { if (window.confirm(`Approve this ${kindL} and record it?`)) onApprove(); }} style={{ color: '#06231a', background: '#3ad29f', border: 'none', borderRadius: 8, padding: '9px 22px', fontWeight: 800, cursor: 'pointer' }}>Approve</button>
            </div>
          ) : (
            <div>
              <div style={{ fontSize: 12, color: '#f0556a', fontWeight: 700, marginBottom: 8 }}>Reject — choose a reason (posted to the client's comments):</div>
              <select value={rejReason} onChange={e => setRejReason(e.target.value)} style={{ ...inp, marginBottom: 8 }}>
                <option value="">— select a reason —</option>{reasons.map(r => <option key={r} value={r}>{r}</option>)}
              </select>
              {rejReason === 'Other' && <input value={rejCustom} onChange={e => setRejCustom(e.target.value)} placeholder="Write the reason…" style={{ ...inp, marginBottom: 8 }} />}
              <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
                <button onClick={() => setRejMode(false)} style={{ color: '#8A93A3', background: 'none', border: '1px solid #2f3a48', borderRadius: 8, padding: '9px 16px', cursor: 'pointer' }}>Cancel</button>
                <button disabled={!rejReason || (rejReason === 'Other' && !rejCustom.trim())} onClick={() => onReject(rejReason === 'Other' ? rejCustom.trim() : rejReason)} style={{ color: '#fff', background: '#f0556a', border: 'none', borderRadius: 8, padding: '9px 20px', fontWeight: 800, cursor: 'pointer', opacity: (!rejReason || (rejReason === 'Other' && !rejCustom.trim())) ? 0.5 : 1 }}>Confirm reject</button>
              </div>
            </div>
          )}
        </div>
      )}
      {zoom && d.proof_id && <div onClick={() => setZoom(false)} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.85)', zIndex: 100001, display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'zoom-out' }}><AuthImg proofId={d.proof_id} style={{ maxWidth: '92vw', maxHeight: '92vh', borderRadius: 10 }} /></div>}
    </>
  );
}

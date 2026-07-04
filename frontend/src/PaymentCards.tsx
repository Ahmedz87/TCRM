import React, { useState, useEffect } from 'react';
import { apiGet, apiPost, apiPut, apiDelete } from './api';

const TYPES = [
  { v: 'qcard', l: 'Qi Card' }, { v: 'zaincash', l: 'Zain Cash' },
  { v: 'fastpay', l: 'Fastpay' }, { v: 'shamcash', l: 'Sham Cash' },
];

// loads a proof image with the staff bearer token (a bare <img> can't send the auth header)
function AuthImg({ id, style }: { id: number; style?: any }) {
  const [src, setSrc] = useState('');
  useEffect(() => {
    let url = ''; const tok = localStorage.getItem('token') || '';
    fetch(`/api/payments/manual-deposits/${id}/image`, { headers: { Authorization: 'Bearer ' + tok } })
      .then(r => r.ok ? r.blob() : Promise.reject()).then(b => { url = URL.createObjectURL(b); setSrc(url); }).catch(() => {});
    return () => { if (url) URL.revokeObjectURL(url); };
  }, [id]);
  if (!src) return <div style={{ ...style, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#566', fontSize: 11 }}>no image</div>;
  return <img src={src} alt="proof" style={style} />;
}

// Company manual-payment cards distributed to back-office members with active hours + the
// transaction-ID series trainer (the AI uses it to spot fake Q-card receipts).
// working hours are stored as MINUTES-since-midnight; convert to/from an <input type=time> value.
const minToHHMM = (m: number) => `${String(Math.floor((m || 0) / 60) % 24).padStart(2, '0')}:${String((m || 0) % 60).padStart(2, '0')}`;
const hhmmToMin = (s: string) => { const [h, mi] = (s || '00:00').split(':').map(Number); return (h || 0) * 60 + (mi || 0); };
const BLANK = { card_type: 'qcard', number: '', account_number: '', card_name: '', holder_name: '', holder_user_id: '', active_from: 0, active_to: 1440, is_active: true, daily_limit: 0, monthly_limit: 0 };

export default function PaymentCards() {
  const [cards, setCards] = useState<any[]>([]);
  const [holders, setHolders] = useState<any[]>([]);
  const [form, setForm] = useState<any>({ ...BLANK });
  const [editId, setEditId] = useState<number | null>(null);
  const [msg, setMsg] = useState('');
  const [series, setSeries] = useState({ method: 'qcard', samples: '' });
  const [deposits, setDeposits] = useState<any[]>([]);
  const [zoom, setZoom] = useState<number | null>(null);
  const [gateways, setGateways] = useState<any[]>([]);
  const [reasons, setReasons] = useState<string[]>([]);
  const [caseD, setCaseD] = useState<any>(null);          // open case-file (deposit detail)
  const [rejMode, setRejMode] = useState(false);
  const [rejReason, setRejReason] = useState('');
  const [rejCustom, setRejCustom] = useState('');
  const [rateForm, setRateForm] = useState<any>({ IQD: '', SYP: '' });
  const [ratesSaved, setRatesSaved] = useState('');

  const loadRates = () => apiGet('/payments/fx-rates').then((d: any) => setRateForm({ IQD: d?.rates?.IQD ?? '', SYP: d?.rates?.SYP ?? '' })).catch(() => {});
  const saveRates = async () => {
    try {
      const d: any = await apiPost('/payments/fx-rates', { IQD: Number(rateForm.IQD) || undefined, SYP: Number(rateForm.SYP) || undefined });
      setRateForm({ IQD: d?.rates?.IQD ?? '', SYP: d?.rates?.SYP ?? '' });
      setRatesSaved('Rates saved'); setTimeout(() => setRatesSaved(''), 2000);
    } catch { setRatesSaved('Save failed'); }
  };

  const load = () => apiGet('/payments/cards').then((d: any) => setCards(d?.cards || [])).catch(() => {});
  const loadDeposits = () => apiGet('/payments/manual-deposits').then((d: any) => { setDeposits(d?.deposits || []); setReasons(d?.reject_reasons || []); }).catch(() => {});
  const openCase = (id: number) => { setRejMode(false); setRejReason(''); setRejCustom(''); apiGet(`/payments/manual-deposits/${id}/detail`).then(setCaseD).catch(() => {}); };
  useEffect(() => { load(); loadDeposits(); loadRates(); apiGet('/payments/holders').then((d: any) => setHolders(d?.holders || [])).catch(() => {});
    apiGet('/payments/gateways/status').then((d: any) => setGateways(d?.gateways || [])).catch(() => {}); }, []);

  const actDeposit = async (id: number, action: 'approve' | 'reject', reason?: string) => {
    try { await apiPost(`/payments/manual-deposits/${id}/action`, { action, reason: reason || '' }); setMsg(`Deposit ${action}d`); setCaseD(null); loadDeposits(); }
    catch { setMsg('Action failed'); }
  };
  const imgUrl = (id: number) => `/api/payments/manual-deposits/${id}/image`;

  const save = async () => {
    if (!form.number) { setMsg('Card/number required'); return; }
    try {
      if (editId) await apiPut(`/payments/cards/${editId}`, form);
      else await apiPost('/payments/cards', form);
      setForm({ ...BLANK }); setEditId(null); setMsg('Saved'); load();
    } catch { setMsg('Save failed'); }
  };
  const del = async (id: number) => { if (window.confirm('Delete this card?')) { await apiDelete(`/payments/cards/${id}`); load(); } };
  const edit = (c: any) => { setForm({ ...c, holder_user_id: c.holder_user_id || '' }); setEditId(c.id); };
  const trainSeries = async () => {
    const r: any = await apiPost('/payments/txid-series', { method: series.method, samples: series.samples });
    setMsg(`Series learned for ${series.method}: prefix "${r?.learned?.common_prefix || ''}", len ${(r?.learned?.len || []).join('-')} (${r?.count} samples)`);
  };

  const inp: any = { width: '100%', padding: '8px 10px', borderRadius: 8, background: '#262c36', border: '1px solid #2f3a48', color: '#e8edf2', fontSize: 13, outline: 'none', boxSizing: 'border-box' };
  return (
    <div style={{ padding: 24, maxWidth: 1240, margin: '0 auto' }}>
      <div style={{ fontSize: 18, fontWeight: 700, marginBottom: 4 }}>💳 Payment Cards</div>
      <div style={{ fontSize: 12, color: '#8A93A3', marginBottom: 18 }}>Company Qi / Zain Cash / Fastpay / Sham Cash numbers held by back-office members. Clients are shown an <b>active</b> card based on the holder's working hours.</div>
      {msg && <div style={{ background: 'rgba(58,210,159,0.1)', border: '1px solid #2bb88a55', color: '#3ad29f', borderRadius: 8, padding: '8px 12px', fontSize: 12.5, marginBottom: 14 }}>{msg}</div>}

      {/* FX rates — local-currency deposits convert to USD at these (back-office editable) */}
      <div style={{ background: '#161c24', border: '1px solid #2f3a48', borderRadius: 12, padding: 16, marginBottom: 20 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
          <div style={{ fontSize: 13, fontWeight: 700 }}>💱 Exchange rates</div>
          {ratesSaved && <span style={{ fontSize: 11.5, color: ratesSaved.includes('fail') ? '#F2667A' : '#3ad29f' }}>{ratesSaved}</span>}
        </div>
        <div style={{ fontSize: 11.5, color: '#8A93A3', marginBottom: 12 }}>Clients depositing with a local method enter the amount in local currency; the portal converts it to USD at these rates. Update whenever the market moves.</div>
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <div>
            <div style={{ fontSize: 11, color: '#8A93A3', marginBottom: 4 }}>Iraqi Dinar (IQD) — Qi Card / Zain Cash / Fastpay</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 13, color: '#8A93A3' }}>$1 =</span>
              <input value={rateForm.IQD} onChange={e => setRateForm({ ...rateForm, IQD: e.target.value.replace(/[^0-9.]/g, '') })} style={{ ...inp, width: 130 }} placeholder="1550" />
              <span style={{ fontSize: 13, color: '#8A93A3' }}>IQD</span>
            </div>
          </div>
          <div>
            <div style={{ fontSize: 11, color: '#8A93A3', marginBottom: 4 }}>Syrian Pound (SYP) — Sham Cash</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 13, color: '#8A93A3' }}>$1 =</span>
              <input value={rateForm.SYP} onChange={e => setRateForm({ ...rateForm, SYP: e.target.value.replace(/[^0-9.]/g, '') })} style={{ ...inp, width: 130 }} placeholder="15000" />
              <span style={{ fontSize: 13, color: '#8A93A3' }}>SYP</span>
            </div>
          </div>
          <button onClick={saveRates} style={{ padding: '8px 20px', background: '#3ad29f', border: 'none', borderRadius: 8, color: '#0a0c10', fontWeight: 700, fontSize: 13, cursor: 'pointer' }}>Save rates</button>
        </div>
      </div>

      {/* Add / edit */}
      <div style={{ background: '#161c24', border: '1px solid #232d3a', borderRadius: 12, padding: 16, marginBottom: 20 }}>
        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12 }}>{editId ? 'Edit card' : 'Add a card'}</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 12 }}>
          <div><div style={{ fontSize: 11, color: '#8A93A3', marginBottom: 4 }}>Type</div>
            <select value={form.card_type} onChange={e => setForm({ ...form, card_type: e.target.value })} style={inp}>{TYPES.map(t => <option key={t.v} value={t.v}>{t.l}</option>)}</select></div>
          <div><div style={{ fontSize: 11, color: '#8A93A3', marginBottom: 4 }}>Card number</div>
            <input value={form.number} onChange={e => setForm({ ...form, number: e.target.value })} style={inp} placeholder="e.g. 4177630212450228" /></div>
          <div><div style={{ fontSize: 11, color: '#8A93A3', marginBottom: 4 }}>Card name (name printed on the card)</div>
            <input value={form.card_name || ''} onChange={e => setForm({ ...form, card_name: e.target.value })} style={inp} placeholder="e.g. Nasreen Fayyad" /></div>
          <div><div style={{ fontSize: 11, color: '#8A93A3', marginBottom: 4 }}>Account number</div>
            <input value={form.account_number || ''} onChange={e => setForm({ ...form, account_number: e.target.value })} style={inp} placeholder="e.g. 4710711542" /></div>
          <div><div style={{ fontSize: 11, color: '#8A93A3', marginBottom: 4 }}>Holder (back-office team)</div>
            <select value={form.holder_user_id} onChange={e => { const a = holders.find((x: any) => String(x.id) === e.target.value); setForm({ ...form, holder_user_id: e.target.value, holder_name: a?.name || '' }); }} style={inp}>
              <option value="">— select —</option>{holders.map((a: any) => <option key={a.id} value={a.id}>{a.name}</option>)}</select></div>
          <div><div style={{ fontSize: 11, color: '#8A93A3', marginBottom: 4 }}>Active from (HH:MM)</div>
            <input type="time" value={minToHHMM(form.active_from)} onChange={e => setForm({ ...form, active_from: hhmmToMin(e.target.value) })} style={inp} /></div>
          <div><div style={{ fontSize: 11, color: '#8A93A3', marginBottom: 4 }}>Active to (HH:MM)</div>
            <input type="time" value={minToHHMM(form.active_to)} onChange={e => setForm({ ...form, active_to: hhmmToMin(e.target.value) })} style={inp} /></div>
          <div><div style={{ fontSize: 11, color: '#8A93A3', marginBottom: 4 }}>Daily limit ($, 0 = no limit)</div>
            <input type="number" min={0} value={form.daily_limit ?? 0} onChange={e => setForm({ ...form, daily_limit: +e.target.value })} style={inp} /></div>
          <div><div style={{ fontSize: 11, color: '#8A93A3', marginBottom: 4 }}>Monthly limit ($, 0 = no limit)</div>
            <input type="number" min={0} value={form.monthly_limit ?? 0} onChange={e => setForm({ ...form, monthly_limit: +e.target.value })} style={inp} /></div>
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: 8 }}>
            <label style={{ fontSize: 12, color: '#e8edf2', display: 'flex', alignItems: 'center', gap: 6 }}><input type="checkbox" checked={form.is_active} onChange={e => setForm({ ...form, is_active: e.target.checked })} /> Active</label>
            <button onClick={save} style={{ padding: '8px 18px', borderRadius: 8, background: '#3ad29f', color: '#06231a', border: 'none', fontWeight: 700, cursor: 'pointer' }}>{editId ? 'Update' : 'Add'}</button>
            {editId && <button onClick={() => { setEditId(null); setForm({ ...BLANK }); }} style={{ padding: '8px 14px', borderRadius: 8, background: 'transparent', border: '1px solid #2f3a48', color: '#8A93A3', cursor: 'pointer' }}>Cancel</button>}
          </div>
        </div>
      </div>

      {/* List */}
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
        <thead><tr>{['Type', 'Card number', 'Card name', 'Account #', 'Holder', 'Active hours', 'Daily', 'Monthly', 'Status', 'Now', ''].map(h => <th key={h} style={{ padding: '8px 10px', textAlign: 'left', color: '#cfd6e0', fontWeight: 600, borderBottom: '1px solid #2f3a48' }}>{h}</th>)}</tr></thead>
        <tbody>
          {cards.length === 0 ? <tr><td colSpan={11} style={{ padding: 24, color: '#8A93A3', textAlign: 'center' }}>No cards yet — add your Qi / Zain Cash / Fastpay / Sham Cash numbers above.</td></tr> :
            cards.map(c => (
              <tr key={c.id} style={{ borderBottom: '1px solid #232d3a' }}>
                <td style={{ padding: '8px 10px', textTransform: 'capitalize' }}>{TYPES.find(t => t.v === c.card_type)?.l || c.card_type}</td>
                <td style={{ padding: '8px 10px', fontFamily: 'monospace' }}>{c.number || '—'}</td>
                <td style={{ padding: '8px 10px' }}>{c.card_name || '—'}</td>
                <td style={{ padding: '8px 10px', fontFamily: 'monospace' }}>{c.account_number || '—'}</td>
                <td style={{ padding: '8px 10px' }}>{c.holder_name || <span style={{ color: '#f0556a' }}>— unassigned</span>}</td>
                <td style={{ padding: '8px 10px' }}>{minToHHMM(c.active_from)}–{minToHHMM(c.active_to)}</td>
                <td style={{ padding: '8px 10px' }}>{c.daily_limit ? <span title={`used today $${(c.day_used || 0).toLocaleString()}`}>${c.daily_limit.toLocaleString()}</span> : '—'}</td>
                <td style={{ padding: '8px 10px' }}>{c.monthly_limit ? <span title={`used this month $${(c.month_used || 0).toLocaleString()}`}>${c.monthly_limit.toLocaleString()}</span> : '—'}</td>
                <td style={{ padding: '8px 10px' }}><span style={{ color: c.is_active ? '#3ad29f' : '#f0556a' }}>{c.is_active ? 'On' : 'Off'}</span></td>
                <td style={{ padding: '8px 10px' }}>{c.available_now ? <span style={{ color: '#3ad29f', fontWeight: 700 }}>● live</span> : <span style={{ color: '#566' }}>—</span>}</td>
                <td style={{ padding: '8px 10px' }}><button onClick={() => edit(c)} style={{ marginRight: 6, color: '#9bb4d4', background: 'none', border: '1px solid #2f3a48', borderRadius: 6, padding: '3px 10px', cursor: 'pointer' }}>Edit</button><button onClick={() => del(c.id)} style={{ color: '#f0556a', background: 'none', border: '1px solid #3a2530', borderRadius: 6, padding: '3px 10px', cursor: 'pointer' }}>Delete</button></td>
              </tr>
            ))}
        </tbody>
      </table>

      {/* Manual deposit review — AI flags fakes, a human approves */}
      <div style={{ background: '#161c24', border: '1px solid #232d3a', borderRadius: 12, padding: 16, marginTop: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
          <div style={{ fontSize: 13, fontWeight: 600 }}>🧾 Manual deposit review</div>
          <button onClick={loadDeposits} style={{ fontSize: 11.5, color: '#9bb4d4', background: 'none', border: '1px solid #2f3a48', borderRadius: 6, padding: '4px 10px', cursor: 'pointer' }}>Refresh</button>
        </div>
        <div style={{ fontSize: 11.5, color: '#8A93A3', marginBottom: 12 }}>Client-uploaded transfer proofs. The AI OCRs the receipt and <b>only flags / rejects</b> fakes — a back-office member always makes the final approval.</div>
        {deposits.length === 0 ? <div style={{ color: '#8A93A3', fontSize: 12.5, padding: 8 }}>No manual deposits submitted yet.</div> : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
            <thead><tr>{['When', 'Client', 'Method', 'Amount', 'AI verdict', 'Status', ''].map(h => <th key={h} style={{ padding: '7px 8px', textAlign: 'left', color: '#cfd6e0', fontWeight: 600, borderBottom: '1px solid #2f3a48' }}>{h}</th>)}</tr></thead>
            <tbody>
              {deposits.map(d => {
                const pending = d.status === 'pending_admin_review';
                const vc = d.verdict === 'reject' ? '#f0556a' : d.verdict === 'approve' ? '#3ad29f' : '#E8B84B';
                return (
                  <tr key={d.id} style={{ borderBottom: '1px solid #232d3a',
                    background: pending ? 'rgba(232,184,75,0.07)' : 'transparent', opacity: pending ? 1 : 0.7 }}>
                    <td style={{ padding: '7px 8px', whiteSpace: 'nowrap' }}>{d.date}</td>
                    <td style={{ padding: '7px 8px' }}>{d.name || '—'}<div style={{ color: '#8A93A3', fontSize: 10.5 }}>#{d.login}</div></td>
                    <td style={{ padding: '7px 8px', textTransform: 'capitalize' }}>{d.method}</td>
                    <td style={{ padding: '7px 8px', fontWeight: 700 }}>${(d.amount || 0).toLocaleString()}{d.ocr_amount != null && Math.abs(d.ocr_amount - d.amount) > 0.5 && <div style={{ color: '#f0556a', fontSize: 10 }}>OCR ${d.ocr_amount}</div>}</td>
                    <td style={{ padding: '7px 8px' }}><span style={{ color: vc, fontWeight: 700, textTransform: 'capitalize' }}>{d.verdict === 'approve' ? 'approved' : d.verdict === 'reject' ? 'rejected' : 'review'}</span></td>
                    <td style={{ padding: '7px 8px' }}>{pending ? <span style={{ color: '#E8B84B', fontWeight: 700 }}>● Pending</span> : <span style={{ color: d.status === 'approved' ? '#3ad29f' : '#f0556a', fontWeight: 700 }}>{d.status === 'approved' ? '✓ Approved' : '✕ Rejected'}</span>}</td>
                    <td style={{ padding: '7px 8px' }}>
                      <button onClick={() => openCase(d.id)} style={{ color: pending ? '#E8B84B' : '#9bb4d4', background: 'none', border: `1px solid ${pending ? '#E8B84B55' : '#2f3a48'}`, borderRadius: 6, padding: '4px 12px', cursor: 'pointer', fontWeight: 600 }}>Details</button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {zoom != null && (
        <div onClick={() => setZoom(null)} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.8)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1200, cursor: 'zoom-out' }}>
          <AuthImg id={zoom} style={{ maxWidth: '90vw', maxHeight: '90vh', borderRadius: 10 }} />
        </div>
      )}

      {/* Case-file popup: payment details | client + receipt + comments; approve/reject for pending */}
      {caseD && (() => {
        const d = caseD; const pending = d.status === 'pending_admin_review';
        const vc = d.verdict === 'reject' ? '#f0556a' : d.verdict === 'approve' ? '#3ad29f' : '#E8B84B';
        const row = (k: string, v: any, hl?: string) => <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, padding: '7px 0', borderBottom: '1px solid #232d3a', fontSize: 12.5 }}><span style={{ color: '#8A93A3' }}>{k}</span><span style={{ fontWeight: 600, color: hl || '#e8edf2', textAlign: 'right', wordBreak: 'break-all', fontFamily: /card|wallet|txn|Transaction|Account/i.test(k) ? 'monospace' : 'inherit' }}>{v || '—'}</span></div>;
        return (
          <div onClick={() => setCaseD(null)} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.75)', zIndex: 1100, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}>
            <div onClick={e => e.stopPropagation()} style={{ background: '#12161f', border: `1px solid ${pending ? '#E8B84B55' : '#232d3a'}`, borderRadius: 14, width: 'min(920px,96vw)', maxHeight: '92vh', overflow: 'auto' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '14px 18px', borderBottom: '1px solid #232d3a' }}>
                <div style={{ fontSize: 15, fontWeight: 800, color: pending ? '#E8B84B' : '#e8edf2' }}>{pending ? '● Pending deposit — review' : (d.status === 'approved' ? '✓ Approved deposit' : '✕ Rejected deposit')}</div>
                <button onClick={() => setCaseD(null)} style={{ background: 'none', border: 'none', color: '#8A93A3', fontSize: 22, cursor: 'pointer' }}>×</button>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr' }}>
                <div style={{ padding: 18, borderRight: '1px solid #232d3a' }}>
                  <div style={{ fontSize: 11, letterSpacing: 1, textTransform: 'uppercase', color: '#8A93A3', fontWeight: 700, marginBottom: 8 }}>Payment details</div>
                  {row('Amount', `$${(d.amount || 0).toLocaleString()}`)}
                  {d.ocr_amount != null && Math.abs(d.ocr_amount - d.amount) > 0.5 && row('OCR amount', `$${d.ocr_amount.toLocaleString()}`, '#f0556a')}
                  {row('Method', d.method)}
                  <div style={{ fontSize: 11, color: '#8A93A3', margin: '12px 0 4px', fontWeight: 700 }}>RECEIVER — company card</div>
                  {row('Card name', d.company_card_name)}
                  {row('Card number', d.company_card)}
                  {row('Account', d.company_account)}
                  <div style={{ fontSize: 11, color: '#8A93A3', margin: '12px 0 4px', fontWeight: 700 }}>SENDER — from OCR</div>
                  {row('Sender wallet', d.ocr_wallet_id || d.entered_wallet_id)}
                  {row('Transaction ID', d.ocr_txid || d.entered_txid)}
                  {row('Receipt date', d.ocr_date)}
                  <div style={{ marginTop: 12, padding: '8px 10px', borderRadius: 8, background: 'rgba(232,184,75,0.06)', border: '1px solid #2f3a48' }}>
                    <div style={{ fontSize: 11, color: '#8A93A3', fontWeight: 700 }}>AI VERDICT</div>
                    <div style={{ color: vc, fontWeight: 700, textTransform: 'capitalize' }}>{d.verdict === 'approve' ? 'approved' : d.verdict === 'reject' ? 'rejected' : 'review'}</div>
                    {d.reasons && <div style={{ fontSize: 11, color: '#cfd6e0', marginTop: 4 }}>{d.reasons}</div>}
                  </div>
                </div>
                <div style={{ padding: 18 }}>
                  <div style={{ fontSize: 11, letterSpacing: 1, textTransform: 'uppercase', color: '#8A93A3', fontWeight: 700, marginBottom: 8 }}>Client</div>
                  {row('Name', d.name)}{row('Login', `#${d.login}`)}{row('Phone', d.phone)}{row('Email', d.email)}
                  <div style={{ fontSize: 11, color: '#8A93A3', margin: '12px 0 6px', fontWeight: 700 }}>RECEIPT</div>
                  {d.has_image ? <div onClick={() => setZoom(d.id)} style={{ cursor: 'zoom-in' }}><AuthImg id={d.id} style={{ width: '100%', maxHeight: 230, objectFit: 'contain', borderRadius: 8, border: '1px solid #2f3a48', background: '#0d1117' }} /></div> : <div style={{ color: '#566', fontSize: 12 }}>No receipt uploaded</div>}
                  <div style={{ fontSize: 11, color: '#8A93A3', margin: '14px 0 6px', fontWeight: 700 }}>RECENT COMMENTS</div>
                  {(d.comments || []).length === 0 ? <div style={{ color: '#566', fontSize: 11.5 }}>No comments yet.</div> :
                    (d.comments || []).map((cm: any, i: number) => (
                      <div key={i} style={{ fontSize: 11.5, padding: '6px 0', borderBottom: '1px solid #232d3a' }}>
                        <div style={{ color: '#cfd6e0' }}>{cm.note || cm.action}</div>
                        <div style={{ color: '#667', fontSize: 10 }}>{cm.date}{cm.by ? ` · ${cm.by}` : ''}</div>
                      </div>
                    ))}
                </div>
              </div>
              {pending && (
                <div style={{ padding: '14px 18px', borderTop: '1px solid #232d3a' }}>
                  {!rejMode ? (
                    <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
                      <button onClick={() => setRejMode(true)} style={{ color: '#f0556a', background: 'none', border: '1px solid #3a2530', borderRadius: 8, padding: '9px 18px', fontWeight: 700, cursor: 'pointer' }}>Reject</button>
                      <button onClick={() => { if (window.confirm('Approve this deposit and credit it?')) actDeposit(d.id, 'approve'); }} style={{ color: '#06231a', background: '#3ad29f', border: 'none', borderRadius: 8, padding: '9px 22px', fontWeight: 800, cursor: 'pointer' }}>Approve</button>
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
                        <button disabled={!rejReason || (rejReason === 'Other' && !rejCustom.trim())} onClick={() => actDeposit(d.id, 'reject', rejReason === 'Other' ? rejCustom.trim() : rejReason)} style={{ color: '#fff', background: '#f0556a', border: 'none', borderRadius: 8, padding: '9px 20px', fontWeight: 800, cursor: 'pointer', opacity: (!rejReason || (rejReason === 'Other' && !rejCustom.trim())) ? 0.5 : 1 }}>Confirm reject</button>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        );
      })()}

      {/* Online payment gateways — enabled ones show in the client portal */}
      <div style={{ background: '#161c24', border: '1px solid #232d3a', borderRadius: 12, padding: 16, marginTop: 24 }}>
        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>🌐 Online payment gateways</div>
        <div style={{ fontSize: 11.5, color: '#8A93A3', marginBottom: 12 }}>Configured in <code>backend/gateway_config.py</code>. Only <b>enabled</b> gateways appear in the client portal; disabled ones stay here for reference. (Flip a gateway on/off in that file, then restart the backend.)</div>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
          <thead><tr>{['Gateway', 'Currency', 'Credentials', 'Mode', 'In client portal'].map(h => <th key={h} style={{ padding: '7px 9px', textAlign: 'left', color: '#cfd6e0', fontWeight: 600, borderBottom: '1px solid #2f3a48' }}>{h}</th>)}</tr></thead>
          <tbody>
            {gateways.length === 0 ? <tr><td colSpan={5} style={{ padding: 16, color: '#8A93A3' }}>No gateways configured.</td></tr> :
              gateways.map((g: any) => (
                <tr key={g.gateway} style={{ borderBottom: '1px solid #232d3a' }}>
                  <td style={{ padding: '7px 9px', fontWeight: 600 }}>{g.label}<div style={{ color: '#566', fontSize: 10, fontFamily: 'monospace' }}>{g.gateway}</div></td>
                  <td style={{ padding: '7px 9px' }}>{g.currency}</td>
                  <td style={{ padding: '7px 9px' }}><span style={{ color: g.has_credentials ? '#3ad29f' : '#f0556a' }}>{g.has_credentials ? '✓ set' : '— missing'}</span></td>
                  <td style={{ padding: '7px 9px' }}>{g.sandbox ? <span style={{ color: '#E8B84B' }}>sandbox</span> : <span style={{ color: '#9bb4d4' }}>live</span>}</td>
                  <td style={{ padding: '7px 9px' }}><span style={{ fontWeight: 700, color: g.enabled ? '#3ad29f' : '#8A93A3' }}>{g.enabled ? '● Shown (enabled)' : '○ Hidden (disabled)'}</span></td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>

      {/* Train the txid series */}
      <div style={{ background: '#161c24', border: '1px solid #232d3a', borderRadius: 12, padding: 16, marginTop: 24 }}>
        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>🤖 Train transaction-ID series (anti-fraud)</div>
        <div style={{ fontSize: 11.5, color: '#8A93A3', marginBottom: 10 }}>Paste the last ~50 real transaction IDs for a method (one per line). The AI learns the fixed series so it can reject fakes that don't match.</div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
          <select value={series.method} onChange={e => setSeries({ ...series, method: e.target.value })} style={{ ...inp, width: 160 }}>{TYPES.map(t => <option key={t.v} value={t.v}>{t.l}</option>)}</select>
          <textarea value={series.samples} onChange={e => setSeries({ ...series, samples: e.target.value })} rows={5} style={{ ...inp, flex: 1, fontFamily: 'monospace' }} placeholder={'2026062610121420010100166764206475862\n2026062610121420010100166523406679999\n…'} />
          <button onClick={trainSeries} style={{ padding: '8px 18px', borderRadius: 8, background: '#3ad29f', color: '#06231a', border: 'none', fontWeight: 700, cursor: 'pointer' }}>Learn</button>
        </div>
      </div>
    </div>
  );
}

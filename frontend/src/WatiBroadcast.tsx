import React, { useState, useEffect } from 'react';
import { apiGet, apiPost } from './api';
import { CT } from './crmTable';

// WhatsApp broadcast via Wati — pick a segment + an approved template, test on one number,
// then send to the whole segment (with a confirm gate). Broadcasts must use an approved template.

const card: React.CSSProperties = { background: 'var(--bg-card,#2c333e)', border: '1px solid var(--border,#4f596b)', borderRadius: 12, padding: 18 };
const cap: React.CSSProperties = { fontSize: 11, color: '#8a93a5', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 12, fontWeight: 700 };
const input: React.CSSProperties = { padding: '9px 11px', background: '#1c2231', border: '1px solid #3a4252', borderRadius: 8, color: '#e6e9ef', fontSize: 13 };
const btn = (bg: string, fg = '#06251b'): React.CSSProperties => ({ padding: '9px 14px', background: bg, border: 'none', borderRadius: 8, color: fg, fontSize: 13, fontWeight: 700, cursor: 'pointer' });
const fmt = (n: number) => (n || 0).toLocaleString('en-GB');

export default function WatiBroadcast() {
  const [segments, setSegments] = useState<any[]>([]);
  const [templates, setTemplates] = useState<any[]>([]);
  const [tplErr, setTplErr] = useState('');
  const [segKey, setSegKey] = useState('');
  const [tplName, setTplName] = useState('');
  const [params, setParams] = useState<string[]>([]);
  const [preview, setPreview] = useState<any>(null);
  const [testNum, setTestNum] = useState('');
  const [msg, setMsg] = useState('');
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState<any>(null);   // { reachable }
  const [broadcasts, setBroadcasts] = useState<any[]>([]);
  const [syncAttrs, setSyncAttrs] = useState(true);
  const [attrPrev, setAttrPrev] = useState<any>(null);
  const [attrStatus, setAttrStatus] = useState<any>(null);

  useEffect(() => { apiGet('/marketing/segments').then(r => setSegments(r.segments || [])).catch(() => {}); }, []);
  useEffect(() => {
    apiGet('/wati/templates').then(r => { setTemplates(r.templates || []); if (r.error) setTplErr(r.error); }).catch(() => setTplErr('Could not load templates'));
    loadLog();
  }, []);
  const loadLog = () => apiGet('/wati/broadcasts').then(r => setBroadcasts(r.broadcasts || [])).catch(() => {});

  const tpl = templates.find(t => t.name === tplName);
  const seg = segments.find(s => s.key === segKey);

  useEffect(() => { setParams(tpl ? Array(tpl.param_count).fill('') : []); }, [tplName]); // eslint-disable-line

  const doPreview = () => {
    if (!segKey) return;
    apiPost('/wati/broadcast/preview', { segment_key: segKey }).then(setPreview).catch(() => {});
    apiGet(`/wati/attributes/preview?segment_key=${segKey}`).then(setAttrPrev).catch(() => setAttrPrev(null));
  };
  useEffect(() => { setPreview(null); setAttrPrev(null); if (segKey) doPreview(); }, [segKey]); // eslint-disable-line

  // poll attribute-sync progress while a sync is running
  const pollAttr = () => apiGet('/wati/attributes/status').then(setAttrStatus).catch(() => {});
  useEffect(() => {
    pollAttr();
    const id = setInterval(() => { if (attrStatus?.running) pollAttr(); }, 3000);
    return () => clearInterval(id);
  }, [attrStatus?.running]); // eslint-disable-line
  const syncNow = async () => {
    if (!segKey) { setMsg('Pick an audience first'); return; }
    const r = await apiPost('/wati/attributes/sync', { segment_key: segKey }).catch(() => null);
    setMsg(r?.ok ? '⏳ Attribute sync started (runs in background)' : (r?.message || r?.error || 'Could not start sync'));
    setTimeout(pollAttr, 800);
  };

  const sendTest = async () => {
    if (!tplName || !testNum.trim()) { setMsg('Pick a template and enter a test number'); return; }
    setBusy(true); setMsg('');
    const r = await apiPost('/wati/broadcast/test', { template_name: tplName, test_number: testNum.trim(), params }).catch(() => null);
    setBusy(false);
    setMsg(r?.ok ? `✓ Test sent to ${r.to}` : `Test failed: ${r?.detail || r?.error || 'error'}`);
  };

  const startSend = async () => {
    if (!segKey || !tplName) { setMsg('Pick an audience and a template'); return; }
    setBusy(true); setMsg('');
    const r = await apiPost('/wati/broadcast/send', { segment_key: segKey, template_name: tplName, params, sync_attrs: syncAttrs }).catch(() => null);
    setBusy(false);
    if (r?.needs_confirm) setConfirm({ reachable: r.reachable });
    else setMsg(r?.error || 'Unexpected response');
  };
  const confirmSend = async () => {
    setBusy(true); setConfirm(null); setMsg('Sending…');
    const r = await apiPost('/wati/broadcast/send', { segment_key: segKey, template_name: tplName, params, sync_attrs: syncAttrs, confirm: true }).catch(() => null);
    setBusy(false);
    setMsg(r?.ok ? `✅ Broadcast sent — ${fmt(r.sent)} delivered${r.failed ? `, ${fmt(r.failed)} failed` : ''}.` : `Failed: ${r?.detail || r?.error || 'error'}`);
    loadLog();
  };

  return (
    <div style={{ display: 'grid', gap: 16, maxWidth: 900 }}>
      <div style={{ background: '#16241d', border: '1px solid #1f5c43', color: '#7fe9c0', borderRadius: 8, padding: '8px 12px', fontSize: 12 }}>
        💬 Broadcasts send an <b>approved WhatsApp template</b> to everyone in a segment. Always send a <b>test to yourself first</b>. Real messages go out and are billed by Wati per message.
      </div>

      {/* 1 · audience */}
      <div style={card}>
        <div style={cap}>1 · Audience</div>
        <select value={segKey} onChange={e => setSegKey(e.target.value)} style={{ ...input, width: '100%' }}>
          <option value="">Choose a segment…</option>
          {segments.map(s => <option key={s.key} value={s.key}>{s.label} — {fmt(s.reach_phone ?? s.reach_whatsapp)} on WhatsApp</option>)}
        </select>
        {preview && <div style={{ fontSize: 13, color: '#cfd6e4', marginTop: 8 }}>Reachable: <b style={{ color: '#00e5a0' }}>{fmt(preview.reachable)}</b> contacts {preview.sample?.length ? <span style={{ color: '#8a93a5' }}>· e.g. {preview.sample.join(', ')}</span> : null}</div>}
      </div>

      {/* 2 · template */}
      <div style={card}>
        <div style={cap}>2 · Template {tplErr && <span style={{ color: '#ff8888', textTransform: 'none' }}>· {tplErr}</span>}</div>
        <select value={tplName} onChange={e => setTplName(e.target.value)} style={{ ...input, width: '100%' }}>
          <option value="">Choose an approved template…</option>
          {templates.map(t => <option key={t.name} value={t.name}>{t.name} ({t.category}{t.has_media ? ' · media' : ''}{t.param_count ? ` · ${t.param_count} var` : ''})</option>)}
        </select>
        {tpl && (
          <div style={{ marginTop: 10 }}>
            <div style={{ background: '#0d1016', border: '1px solid #232a38', borderRadius: 10, padding: 12, fontSize: 13, color: '#e6e9ef', whiteSpace: 'pre-wrap', lineHeight: 1.5 }} dir="auto">
              {tpl.has_media && <div style={{ fontSize: 11, color: '#8a93a5', marginBottom: 6 }}>🖼 {tpl.media_type} header (uses the template's approved media)</div>}
              {tpl.body}
              {tpl.footer && <div style={{ fontSize: 11, color: '#8a93a5', marginTop: 8 }}>{tpl.footer}</div>}
            </div>
            {tpl.param_count > 0 && (
              <div style={{ marginTop: 10 }}>
                <div style={{ fontSize: 11, color: '#8a93a5', marginBottom: 6 }}>Fill the template variables ({'{{1}}'}…):</div>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  {params.map((v, i) => (
                    <input key={i} value={v} onChange={e => { const p = [...params]; p[i] = e.target.value; setParams(p); }}
                      placeholder={`{{${i + 1}}}`} style={{ ...input, width: 160 }} />
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* attributes: ACD (agent) + contact fields */}
      <div style={card}>
        <div style={cap}>Contact attributes in Wati (ACD = current agent)</div>
        <div style={{ fontSize: 12, color: '#8a93a5', marginBottom: 10 }}>
          Keeps each Wati contact's <b style={{ color: '#cfd6e4' }}>acd</b> = the client's current owning agent
          (flips sales→retention on deposit), plus <b style={{ color: '#cfd6e4' }}>sales_agent, agent_team, country, city, deposits, lead_stage</b>.
          New numbers you message get <b style={{ color: '#cfd6e4' }}>created with all attributes filled</b>.
        </div>
        {attrPrev?.sample?.length > 0 && (
          <div style={{ background: '#0d1016', border: '1px solid #232a38', borderRadius: 8, padding: 10, fontSize: 12, color: '#cfd6e4', marginBottom: 10 }}>
            Example — <b>{attrPrev.sample[0].name}</b>: acd=<b style={{ color: '#25D366' }}>{attrPrev.sample[0].attrs.acd || '—'}</b>
            {attrPrev.sample[0].attrs.agent_team ? <> · team={attrPrev.sample[0].attrs.agent_team}</> : null}
            {attrPrev.sample[0].attrs.country ? <> · {attrPrev.sample[0].attrs.country}</> : null}
            {attrPrev.sample[0].attrs.total_deposit_amount ? <> · dep ${attrPrev.sample[0].attrs.total_deposit_amount}</> : null}
          </div>
        )}
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          <button onClick={syncNow} disabled={!segKey || attrStatus?.running} style={btn('#79b8ff', '#06192e')}>
            {attrStatus?.running ? 'Syncing…' : '⟳ Sync attributes now'}
          </button>
          {attrStatus?.running && (
            <span style={{ fontSize: 12, color: '#79b8ff' }}>
              {fmt(attrStatus.done)} / {fmt(attrStatus.total)} contacts · {fmt(attrStatus.ok)} ok{attrStatus.failed ? ` · ${fmt(attrStatus.failed)} failed` : ''}
            </span>
          )}
          {!attrStatus?.running && attrStatus?.finished && (
            <span style={{ fontSize: 12, color: '#8a93a5' }}>Last sync: {fmt(attrStatus.ok)} updated{attrStatus.failed ? `, ${fmt(attrStatus.failed)} failed` : ''} ({attrStatus.finished})</span>
          )}
        </div>
      </div>

      {/* 3 · test + send */}
      <div style={card}>
        <div style={cap}>3 · Test, then broadcast</div>
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: '#cfd6e4', marginBottom: 12, cursor: 'pointer' }}>
          <input type="checkbox" checked={syncAttrs} onChange={e => setSyncAttrs(e.target.checked)} />
          Update ACD / agent + fill new contacts in Wati when I broadcast (runs in the background)
        </label>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 12 }}>
          <input value={testNum} onChange={e => setTestNum(e.target.value)} placeholder="Your number (e.g. 9647…) for a test" style={{ ...input, width: 260 }} />
          <button onClick={sendTest} disabled={busy || !tplName} style={btn('#3a4252', '#cfd6e4')}>Send test to me</button>
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          <button onClick={startSend} disabled={busy || !segKey || !tplName} style={btn('#25D366', '#06251b')}>
            📣 Broadcast to {seg ? fmt(preview?.reachable ?? (seg.reach_phone ?? seg.reach_whatsapp)) : '…'} contacts
          </button>
          {msg && <span style={{ fontSize: 13, color: msg.startsWith('✓') || msg.startsWith('✅') ? '#00e5a0' : (msg.startsWith('Sending') ? '#79b8ff' : '#ffaa00') }}>{msg}</span>}
        </div>
      </div>

      {/* recent */}
      {broadcasts.length > 0 && (
        <div style={card}>
          <div style={cap}>Recent broadcasts</div>
          <div style={CT.scroll}>
            <table style={CT.table}>
              <thead><tr style={CT.theadTr}>{['Template', 'Segment', 'Recipients', 'Sent', 'Failed', 'Status', 'By', 'When'].map(h => <th key={h} style={CT.th(false, ['Recipients', 'Sent', 'Failed'].includes(h) ? 'right' : 'left')}>{h}</th>)}</tr></thead>
              <tbody>{broadcasts.map(b => (
                <tr key={b.id} style={CT.row()}>
                  <td style={CT.td}>{b.template}</td>
                  <td style={{ ...CT.td, color: '#8a93a5' }}>{b.segment_key}</td>
                  <td style={{ ...CT.td, textAlign: 'right' }}>{fmt(b.recipients)}</td>
                  <td style={{ ...CT.td, textAlign: 'right', color: '#00e5a0' }}>{fmt(b.sent)}</td>
                  <td style={{ ...CT.td, textAlign: 'right', color: b.failed ? '#ff8888' : '#8a93a5' }}>{fmt(b.failed)}</td>
                  <td style={CT.td}><span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 99, background: b.status === 'sent' ? '#00e5a022' : b.status === 'partial' ? '#5c451f44' : '#5c1f1f44', color: b.status === 'sent' ? '#00e5a0' : b.status === 'partial' ? '#e9c97f' : '#ff8888' }}>{b.status}</span></td>
                  <td style={{ ...CT.td, color: '#8a93a5' }}>{b.created_by}</td>
                  <td style={{ ...CT.td, color: '#8a93a5' }}>{(b.created_at || '').toString().slice(0, 16).replace('T', ' ')}</td>
                </tr>))}</tbody>
            </table>
          </div>
        </div>
      )}

      {/* confirm dialog */}
      {confirm && (
        <div onClick={() => setConfirm(null)} style={{ position: 'fixed', inset: 0, background: '#0009', zIndex: 200, display: 'flex', justifyContent: 'center', alignItems: 'center', padding: 16 }}>
          <div onClick={e => e.stopPropagation()} style={{ ...card, width: 440, maxWidth: '100%' }}>
            <div style={{ fontSize: 16, fontWeight: 700, color: '#e6e9ef', marginBottom: 10 }}>Send this broadcast?</div>
            <div style={{ fontSize: 13, color: '#cfd6e4', lineHeight: 1.6, marginBottom: 16 }}>
              Template <b style={{ color: '#25D366' }}>{tplName}</b> will be sent to <b style={{ color: '#00e5a0' }}>{fmt(confirm.reachable)}</b> contacts in <b>{seg?.label}</b>.<br />
              <span style={{ color: '#ffaa00' }}>This sends real WhatsApp messages and is billed by Wati.</span> Did you send yourself a test first?
            </div>
            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
              <button onClick={() => setConfirm(null)} style={btn('#3a4252', '#cfd6e4')}>Cancel</button>
              <button onClick={confirmSend} style={btn('#25D366', '#06251b')}>Yes, send to {fmt(confirm.reachable)}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

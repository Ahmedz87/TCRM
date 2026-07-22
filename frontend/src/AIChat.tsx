import React, { useState, useEffect } from 'react';
import { apiGet, apiPost } from './api';
import { CT } from './crmTable';

// ── AI Assistant chat (Ticketing center) ────────────────────────────────────────
// Back-and-forth Claude chat for staff: ask questions, attach photos/PDFs, request
// any report (rendered inline with Excel export — auto-scoped to the user's own
// department), and file change requests (the AI creates tickets via create_ticket).

const card: React.CSSProperties = {
  background: 'var(--bg-card,#2c333e)', border: '1px solid var(--border,#373f4d)', borderRadius: 12, padding: 16,
};
const input: React.CSSProperties = {
  background: 'var(--bg-card,#2c333e)', color: '#e6e9ef',
  border: '1px solid var(--border,#373f4d)', borderRadius: 8, padding: '7px 10px', fontSize: 13,
};
const td: React.CSSProperties = { ...CT.td, textAlign: 'right' };
const tdL: React.CSSProperties = { ...CT.td, textAlign: 'left', fontWeight: 600 };

const fmtCell = (type: string, v: any) => {
  if (v === null || v === undefined) return '';
  if (type === 'money') return (v < 0 ? '-$' : '$') + Math.abs(Math.round(v || 0)).toLocaleString();
  if (type === 'float') return (v || 0).toLocaleString(undefined, { maximumFractionDigits: 1 });
  if (type === 'int') return (v || 0).toLocaleString();
  return String(v);
};

function ResultTable({ result }: { result: any }) {
  const cols = result?.columns || [];
  const nd = result?.n_dims || 1;
  if (!result) return null;
  if (!result.rows?.length) return <div style={{ color: '#8a93a3' }}>No data for that request.</div>;
  return (
    <div style={{ ...CT.scroll, maxHeight: '45vh' }}>
      <table style={{ ...CT.table, minWidth: 500 }}>
        <thead><tr style={CT.theadTr}>{cols.map((c: any, i: number) => <th key={c.key} style={CT.th(false, i < nd ? 'left' : 'right')}>{c.label}</th>)}</tr></thead>
        <tbody>
          {result.rows.map((row: any[], ri: number) => (
            <tr key={ri} style={CT.row()}>{cols.map((c: any, ci: number) => <td key={c.key} style={ci < nd ? tdL : td}>{fmtCell(c.type, row[ci])}</td>)}</tr>
          ))}
          {result.total_row && (
            <tr style={{ ...CT.row(), background: 'rgba(91,157,255,0.10)', fontWeight: 700 }}>
              {cols.map((c: any, ci: number) => <td key={c.key} style={{ ...(ci < nd ? tdL : td), fontWeight: 700, borderTop: '2px solid var(--border,#373f4d)' }}>{fmtCell(c.type, result.total_row[ci])}</td>)}
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function MdText({ text }: { text: string }) {
  const lines = (text || '').split('\n');
  return (
    <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.5 }}>
      {lines.map((ln, i) => {
        const parts = ln.split(/\*\*(.+?)\*\*/g);
        return (
          <div key={i} style={{ paddingLeft: /^\s*[-•]/.test(ln) ? 8 : 0 }}>
            {parts.map((p, j) => (j % 2 === 1 ? <b key={j}>{p}</b> : <span key={j}>{p}</span>))}
          </div>
        );
      })}
    </div>
  );
}

async function exportSpecXlsx(s: any) {
  if (!s) return;
  const token = localStorage.getItem('token') || '';
  const res = await fetch('/api/monthly-report/run/export', {
    method: 'POST', headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' },
    body: JSON.stringify({ category: s.category, group_by: s.group_by, period: s.period, start: s.start, end: s.end, filters: s.filters }),
  });
  if (res.ok) { const b = await res.blob(); const u = URL.createObjectURL(b); const a = document.createElement('a'); a.href = u; a.download = (s.category || 'report') + '_report.xlsx'; a.click(); URL.revokeObjectURL(u); }
}

export default function AIChat({ onTicketCreated, fullPage }: { onTicketCreated?: () => void; fullPage?: boolean }) {
  const [msgs, setMsgs] = useState<any[]>([]);
  const [q, setQ] = useState('');
  const [files, setFiles] = useState<{ name: string; media_type: string; data: string; preview?: string }[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState('');
  const endRef = React.useRef<HTMLDivElement>(null);
  const fileRef = React.useRef<HTMLInputElement>(null);

  useEffect(() => { apiGet('/monthly-report/chat/history').then((d) => setMsgs(d.messages || [])).catch(() => {}); }, []);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [msgs, loading]);

  const addFiles = (list: FileList | null) => {
    if (!list) return;
    Array.from(list).slice(0, 4 - files.length).forEach((f) => {
      if (!/^image\/|application\/pdf/.test(f.type)) { setErr(`${f.name}: only images or PDF`); return; }
      if (f.size > 4.5 * 1024 * 1024) { setErr(`${f.name} is too large (max 4.5MB)`); return; }
      const rd = new FileReader();
      rd.onload = () => {
        const b64 = String(rd.result).split(',')[1] || '';
        setFiles((prev) => [...prev, { name: f.name, media_type: f.type, data: b64,
          preview: f.type.startsWith('image/') ? String(rd.result) : undefined }]);
      };
      rd.readAsDataURL(f);
    });
    if (fileRef.current) fileRef.current.value = '';
  };

  const send = () => {
    const text = q.trim();
    if ((!text && !files.length) || loading) return;
    setErr('');
    const mine = { role: 'user', content: text, attachments: files.map((f) => ({ name: f.name, media_type: f.media_type })), reports: [] };
    setMsgs((m) => [...m, mine]);
    setQ(''); const sendFiles = files; setFiles([]);
    setLoading(true);
    apiPost('/monthly-report/chat', { message: text, attachments: sendFiles.map(({ name, media_type, data }) => ({ name, media_type, data })) })
      .then((d) => {
        setLoading(false);
        if (d.error) { setErr(d.error); return; }
        setMsgs((m) => [...m, { role: 'assistant', content: d.reply, attachments: [], reports: d.reports || [] }]);
        if ((d.reply || '').includes('🎫') && onTicketCreated) onTicketCreated();
      })
      .catch((e) => { setLoading(false); setErr(String(e)); });
  };

  const clearChat = () => {
    if (!window.confirm('Clear the whole conversation?')) return;
    apiPost('/monthly-report/chat/clear', {}).then(() => setMsgs([])).catch(() => {});
  };

  const examples = ['my deposits this month by method', 'top sales agents last month', 'please add a print button to the Clients page', 'analyse the attached chart'];

  return (
    <div style={{ ...card, border: '1px solid #1f6feb66', display: 'flex', flexDirection: 'column',
                  ...(fullPage ? { flex: 1, minHeight: 0, marginBottom: 0 } : { marginBottom: 16 }) }}>
      {!fullPage && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8, flexWrap: 'wrap' }}>
          <span style={{ fontSize: 16 }}>🤖</span><b>AI Assistant</b>
          <span style={{ color: '#8a93a3', fontSize: 12 }}>chat directly — reports (your department), attachments, change requests → tickets</span>
          <div style={{ flex: 1 }} />
          {msgs.length > 0 && <button onClick={clearChat} style={{ ...input, cursor: 'pointer', fontSize: 11, color: '#ff8a93' }}>🗑 Clear chat</button>}
        </div>
      )}
      {fullPage && msgs.length > 0 && (
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 4 }}>
          <button onClick={clearChat} style={{ ...input, cursor: 'pointer', fontSize: 11, color: '#ff8a93' }}>🗑 Clear chat</button>
        </div>
      )}

      <div style={{ ...(fullPage ? { flex: 1, minHeight: 0 } : { maxHeight: '48vh' }), overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 10, padding: '6px 2px' }}>
        {msgs.length === 0 && !loading && (
          <div style={{ color: '#8a93a3', fontSize: 12, padding: 8 }}>
            Talk to the assistant — for example:
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 8 }}>
              {examples.map((s) => <button key={s} onClick={() => setQ(s)} style={{ ...input, cursor: 'pointer', fontSize: 11, padding: '4px 8px', color: '#8a93a3' }}>{s}</button>)}
            </div>
          </div>
        )}
        {msgs.map((m, i) => (
          <div key={i} style={{ alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start', maxWidth: '92%', minWidth: m.reports?.length ? '80%' : undefined }}>
            <div style={{
              background: m.role === 'user' ? 'rgba(248,80,10,0.14)' : 'var(--bg-input,#373f4d)',
              border: '1px solid ' + (m.role === 'user' ? 'rgba(248,80,10,0.35)' : 'var(--border,#4f596b)'),
              borderRadius: m.role === 'user' ? '12px 12px 3px 12px' : '12px 12px 12px 3px',
              padding: '9px 12px', fontSize: 13, color: '#e6e9ef',
            }}>
              {m.attachments?.length > 0 && (
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: m.content ? 6 : 0 }}>
                  {m.attachments.map((a: any, j: number) => (
                    <span key={j} style={{ fontSize: 11, background: 'rgba(0,0,0,0.25)', borderRadius: 6, padding: '2px 8px' }}>
                      {a.media_type?.startsWith('image/') ? '🖼' : '📄'} {a.name}
                    </span>
                  ))}
                </div>
              )}
              {m.content && <MdText text={m.content} />}
              {(m.reports || []).map((rp: any, j: number) => (
                <div key={j} style={{ marginTop: 10, background: 'var(--bg-card,#2c333e)', border: '1px solid var(--border,#4f596b)', borderRadius: 8, padding: 10 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6, flexWrap: 'wrap' }}>
                    <b style={{ fontSize: 12 }}>{rp.title}</b>
                    <span style={{ color: '#8a93a3', fontSize: 11 }}>{rp.result?.rows?.length || 0} row(s)</span>
                    <div style={{ flex: 1 }} />
                    <button onClick={() => exportSpecXlsx(rp.spec)} style={{ ...input, cursor: 'pointer', background: '#1f8a4c', borderColor: '#1f8a4c', color: '#fff', fontWeight: 600, fontSize: 11, padding: '4px 10px' }}>⬇ Excel</button>
                  </div>
                  <ResultTable result={rp.result} />
                </div>
              ))}
            </div>
          </div>
        ))}
        {loading && <div style={{ color: '#8a93a3', fontSize: 12, padding: '4px 8px' }}>⏳ assistant is thinking…</div>}
        <div ref={endRef} />
      </div>

      {err && <div style={{ color: '#ff5c6c', marginTop: 6, fontSize: 12 }}>{err}</div>}

      {files.length > 0 && (
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 8 }}>
          {files.map((f, i) => (
            <span key={i} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, background: 'var(--bg-input,#373f4d)', border: '1px solid var(--border,#4f596b)', borderRadius: 8, padding: '4px 8px' }}>
              {f.preview ? <img src={f.preview} alt="" style={{ width: 26, height: 26, objectFit: 'cover', borderRadius: 4 }} /> : '📄'}
              {f.name}
              <span onClick={() => setFiles(files.filter((_, j) => j !== i))} style={{ cursor: 'pointer', color: '#ff8a93' }}>✕</span>
            </span>
          ))}
        </div>
      )}

      <div style={{ display: 'flex', gap: 8, marginTop: 10, alignItems: 'flex-end' }}>
        <input ref={fileRef} type="file" multiple accept="image/*,application/pdf" style={{ display: 'none' }}
          onChange={(e) => addFiles(e.target.files)} />
        <button onClick={() => fileRef.current?.click()} title="Attach photos / PDF"
          style={{ ...input, cursor: 'pointer', fontSize: 16, padding: '8px 12px' }}>📎</button>
        <textarea value={q} onChange={(e) => setQ(e.target.value)} rows={q.includes('\n') ? 3 : 1}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } }}
          placeholder="Message the assistant… (Enter to send, Shift+Enter for a new line)"
          style={{ ...input, flex: 1, resize: 'none', minHeight: 38 }} />
        <button onClick={send} disabled={loading}
          style={{ ...input, cursor: 'pointer', background: '#1f6feb', borderColor: '#1f6feb', color: '#fff', fontWeight: 600, padding: '8px 20px' }}>
          {loading ? '…' : 'Send ➤'}
        </button>
      </div>
    </div>
  );
}

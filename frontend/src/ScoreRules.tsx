import React, { useState, useEffect, useCallback, useRef } from 'react';
import { apiGet, apiPost, apiPatch, apiDelete } from './api';

/* Admin scoring rule-builder. Each rule ADDS points to a lead/client score when its field matches.
   Value fields are MULTI-SELECT (pick many, e.g. country ∈ {Iraq, Syria}). Rules can be
   activated/deactivated (seasonal) and given an expiry (or never). Backend: /score-rules. */

const cell: React.CSSProperties = { padding: '7px 9px', background: '#11141a', border: '1px solid #2a3142', borderRadius: 7, color: '#e6e9ef', fontSize: 12.5, outline: 'none' };

// searchable multi-select: chips for the picked values + a filterable checkbox dropdown
function MultiSelect({ options, selected, onChange, width = 240 }: { options: string[]; selected: string[]; onChange: (v: string[]) => void; width?: number }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState('');
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const h = (e: any) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', h); return () => document.removeEventListener('mousedown', h);
  }, []);
  const filtered = options.filter(o => o.toLowerCase().includes(q.toLowerCase())).slice(0, 300);
  const toggle = (o: string) => onChange(selected.includes(o) ? selected.filter(x => x !== o) : [...selected, o]);
  return (
    <div ref={ref} style={{ position: 'relative', minWidth: width }}>
      <div onClick={() => setOpen(o => !o)} style={{ ...cell, display: 'flex', flexWrap: 'wrap', gap: 4, cursor: 'pointer', minHeight: 34, alignItems: 'center' }}>
        {selected.length === 0 ? <span style={{ color: '#667' }}>choose one or more…</span> :
          selected.map(s => (
            <span key={s} onClick={e => { e.stopPropagation(); toggle(s); }}
              style={{ fontSize: 11, padding: '2px 6px', borderRadius: 6, background: 'rgba(28,100,242,0.22)', color: '#9ec1ff', cursor: 'pointer' }}>{s} ✕</span>
          ))}
      </div>
      {open && (
        <div style={{ position: 'absolute', top: '100%', left: 0, minWidth: '100%', zIndex: 60, marginTop: 4, background: '#11141a', border: '1px solid #2a3142', borderRadius: 8, maxHeight: 260, overflowY: 'auto', boxShadow: '0 10px 30px rgba(0,0,0,0.55)' }}>
          <input autoFocus value={q} onChange={e => setQ(e.target.value)} placeholder="search…" onClick={e => e.stopPropagation()}
            style={{ ...cell, width: '100%', borderRadius: 0, border: 'none', borderBottom: '1px solid #2a3142', boxSizing: 'border-box' }} />
          {filtered.map(o => (
            <div key={o} onClick={() => toggle(o)} style={{ padding: '7px 10px', fontSize: 12.5, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8, whiteSpace: 'nowrap', color: selected.includes(o) ? '#00e5a0' : '#cdd4de' }}>
              <input type="checkbox" checked={selected.includes(o)} readOnly style={{ pointerEvents: 'none' }} /> {o}
            </div>
          ))}
          {filtered.length === 0 && <div style={{ padding: 10, color: '#667', fontSize: 12 }}>No matches</div>}
        </div>
      )}
    </div>
  );
}

export default function ScoreRules() {
  const [opts, setOpts] = useState<any>({ fields: { lead: [], client: [] }, field_meta: { lead: {}, client: {} } });
  const [rules, setRules] = useState<any[]>([]);
  const [msg, setMsg] = useState('');
  const [applying, setApplying] = useState(false);

  // new-rule draft
  const [scope, setScope] = useState('client');
  const [field, setField] = useState('country');
  const [selected, setSelected] = useState<string[]>([]);   // multi-value picks
  const [numVal, setNumVal] = useState('');                 // int fields (no_deposit_days)
  const [points, setPoints] = useState('10');
  const [never, setNever] = useState(true);
  const [expiry, setExpiry] = useState('');

  const loadRules = useCallback(() => { apiGet('/score-rules').then((d: any) => setRules(d.rules || [])).catch(() => {}); }, []);
  useEffect(() => { apiGet('/score-rules/options').then(setOpts).catch(() => {}); loadRules(); }, [loadRules]);

  const fields: string[] = opts.fields?.[scope] || [];
  const meta = (f: string) => opts.field_meta?.[scope]?.[f] || { label: f, type: 'multi', options: [] };
  const fType = meta(field).type as 'multi' | 'int' | 'none';
  useEffect(() => { if (fields.length && !fields.includes(field)) { setField(fields[0]); setSelected([]); setNumVal(''); } /* eslint-disable-next-line */ }, [scope]);

  const valueCell = () => {
    if (fType === 'none') return <input value="(matches all)" disabled style={{ ...cell, width: 150, opacity: .5 }} />;
    if (fType === 'int') return <input value={numVal} onChange={e => setNumVal(e.target.value.replace(/[^0-9]/g, ''))} placeholder="days, e.g. 30" style={{ ...cell, width: 150 }} />;
    return <MultiSelect options={meta(field).options || []} selected={selected} onChange={setSelected} />;
  };

  const addRule = async () => {
    let value = '';
    if (fType === 'multi') { if (!selected.length) { setMsg('Pick at least one value.'); return; } value = selected.join(','); }
    else if (fType === 'int') { if (!numVal.trim()) { setMsg('Enter a number.'); return; } value = numVal.trim(); }
    if (!Number(points)) { setMsg('Set the points.'); return; }
    const r: any = await apiPost('/score-rules', { scope, field, value, points: Number(points), expires_at: never ? '' : expiry });
    if (r?.ok) { setMsg(''); setSelected([]); setNumVal(''); loadRules(); } else setMsg(r?.detail || 'Could not add rule.');
  };

  const toggle = async (rule: any) => { await apiPatch(`/score-rules/${rule.id}`, { active: !rule.active }); loadRules(); };
  const setRulePoints = async (rule: any, p: number) => { await apiPatch(`/score-rules/${rule.id}`, { points: p }); loadRules(); };
  const del = async (rule: any) => { if (!window.confirm('Delete this rule?')) return; await apiDelete(`/score-rules/${rule.id}`); loadRules(); };
  const applyNow = async () => { setApplying(true); setMsg(''); const r: any = await apiPost('/score-rules/apply', {}); setMsg(r?.message || 'Recalculating…'); setApplying(false); };

  const ruleText = (r: any) => {
    const m = opts.field_meta?.[r.scope]?.[r.field];
    const label = m?.label || r.field;
    if (m?.type === 'none') return label;
    if (r.field === 'no_deposit_days') return `no deposit for ≥ ${r.value} days`;
    const vals = String(r.value || '').split(',').filter(Boolean);
    return <span>{label} <span style={{ color: '#8a93a3' }}>∈</span> {vals.map((v: string, i: number) => (
      <span key={i} style={{ fontSize: 11, padding: '1px 6px', borderRadius: 6, background: '#1a2030', color: '#9ec1ff', marginRight: 4, display: 'inline-block' }}>{v}</span>
    ))}</span>;
  };

  return (
    <div style={{ background: '#2c333e', border: '1px solid #4f596b', borderRadius: 12, padding: 16, marginBottom: 16, maxWidth: 980 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
        <span style={{ fontSize: 15, fontWeight: 700, color: '#e6e9ef' }}>🎯 Custom scoring rules</span>
        <div style={{ flex: 1 }} />
        <button onClick={applyNow} disabled={applying} style={{ padding: '7px 16px', background: '#00e5a0', border: 'none', borderRadius: 8, color: '#0a0c10', fontWeight: 700, fontSize: 12.5, cursor: 'pointer' }}>{applying ? '…' : '↻ Apply now (recalculate)'}</button>
      </div>
      <div style={{ fontSize: 11.5, color: '#8a93a3', marginBottom: 14 }}>Build a rule — pick a scope, a field and one OR MORE values. Matching leads/clients get the points added. Toggle to activate/deactivate by season and set an expiry or never.</div>

      {/* builder bar */}
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', background: '#262c36', border: '1px dashed #3a4150', borderRadius: 9, padding: 10, marginBottom: 14 }}>
        <select value={scope} onChange={e => { setScope(e.target.value); setSelected([]); setNumVal(''); }} style={{ ...cell, width: 100 }}><option value="client">Client</option><option value="lead">Lead</option></select>
        <span style={{ color: '#667', fontSize: 12 }}>where</span>
        <select value={field} onChange={e => { setField(e.target.value); setSelected([]); setNumVal(''); }} style={{ ...cell, width: 180 }}>{fields.map((f: string) => <option key={f} value={f}>{meta(f).label}</option>)}</select>
        {valueCell()}
        <span style={{ color: '#667', fontSize: 12 }}>→ give</span>
        <input value={points} onChange={e => setPoints(e.target.value.replace(/[^0-9-]/g, ''))} style={{ ...cell, width: 64 }} /><span style={{ color: '#667', fontSize: 12 }}>pts</span>
        <label style={{ display: 'flex', gap: 5, alignItems: 'center', fontSize: 12, color: '#9aa3b2', cursor: 'pointer' }}><input type="checkbox" checked={never} onChange={e => setNever(e.target.checked)} />never expires</label>
        {!never && <input type="date" value={expiry} onChange={e => setExpiry(e.target.value)} style={{ ...cell, width: 140 }} />}
        <button onClick={addRule} style={{ padding: '7px 16px', background: '#1c64f2', border: 'none', borderRadius: 8, color: '#fff', fontWeight: 700, fontSize: 12.5, cursor: 'pointer' }}>+ Add rule</button>
      </div>
      {msg && <div style={{ fontSize: 12, color: msg.includes('recalc') || msg.includes('background') ? '#00e5a0' : '#ff8a8a', marginBottom: 10 }}>{msg}</div>}

      {/* rules list */}
      {rules.length === 0 ? <div style={{ color: '#667', fontSize: 12.5, padding: '8px 2px' }}>No custom rules yet.</div> : (
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
          <thead><tr style={{ color: '#8a93a3', textAlign: 'left' }}>
            {['Scope', 'Condition', 'Points', 'Expires', 'Active', ''].map(h => <th key={h} style={{ padding: '6px 6px', fontWeight: 600, fontSize: 10.5, textTransform: 'uppercase' }}>{h}</th>)}
          </tr></thead>
          <tbody>
            {rules.map(r => (
              <tr key={r.id} style={{ borderTop: '1px solid #373f4d', opacity: r.active ? 1 : .5 }}>
                <td style={{ padding: '7px 6px' }}><span style={{ fontSize: 10.5, padding: '2px 7px', borderRadius: 99, background: r.scope === 'client' ? 'rgba(0,170,255,0.15)' : 'rgba(204,136,255,0.15)', color: r.scope === 'client' ? '#00aaff' : '#cc88ff' }}>{r.scope}</span></td>
                <td style={{ padding: '7px 6px', color: '#cdd4de' }}>{ruleText(r)}</td>
                <td style={{ padding: '7px 6px' }}><input defaultValue={r.points} onBlur={e => { const p = Number(e.target.value); if (p !== r.points) setRulePoints(r, p); }} style={{ ...cell, width: 56, padding: '4px 7px' }} /></td>
                <td style={{ padding: '7px 6px', color: '#8a93a3' }}>{r.expires_at || 'never'}</td>
                <td style={{ padding: '7px 6px' }}>
                  <button onClick={() => toggle(r)} style={{ width: 38, height: 20, borderRadius: 99, border: 'none', cursor: 'pointer', background: r.active ? '#00e5a0' : '#4f596b', position: 'relative' }}>
                    <span style={{ position: 'absolute', top: 2, left: r.active ? 20 : 2, width: 16, height: 16, borderRadius: '50%', background: '#fff', transition: 'left .15s' }} />
                  </button>
                </td>
                <td style={{ padding: '7px 6px' }}><button onClick={() => del(r)} style={{ background: 'none', border: 'none', color: '#ff6a6a', cursor: 'pointer', fontSize: 14 }}>🗑</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

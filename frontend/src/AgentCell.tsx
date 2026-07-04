import React, { useState, useEffect, useRef } from 'react';

const API = '/api';
const tok = () => localStorage.getItem('token') || '';
// show only the first two words of a name
export const twoWords = (n?: string | null) =>
  (n || '').trim().split(/\s+/).filter(Boolean).slice(0, 2).join(' ');

// agents list cached at module level (fetched once)
let _cache: any[] | null = null;
let _promise: Promise<any[]> | null = null;
function loadAgents(): Promise<any[]> {
  if (_cache) return Promise.resolve(_cache);
  if (!_promise) {
    _promise = fetch(`${API}/assign/agents`, { headers: { Authorization: `Bearer ${tok()}` } })
      .then(r => r.json()).then(d => { _cache = d.agents || []; return _cache!; })
      .catch(() => { _promise = null; return []; });
  }
  return _promise;
}

const item: React.CSSProperties = { padding: '7px 9px', fontSize: 12, color: '#cdd3dc', borderRadius: 6, cursor: 'pointer', whiteSpace: 'nowrap' };

export function AgentCell({ entityType, entityId, agentName, onSortBy, onChanged }: {
  entityType: 'lead' | 'client';
  entityId: number;
  agentName?: string | null;
  onSortBy?: (name: string) => void;
  onChanged?: (newName: string | null) => void;
}) {
  const canReassign = localStorage.getItem('canReassign') === '1';
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<'menu' | 'pick'>('menu');
  const [agents, setAgents] = useState<any[]>([]);
  const [q, setQ] = useState('');
  const [last, setLast] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [pos, setPos] = useState<{ left: number; top: number; flip: boolean }>({ left: 0, top: 0, flip: false });
  const ref = useRef<HTMLSpanElement>(null);
  const has = !!agentName;

  useEffect(() => {
    if (!open) return;
    loadAgents().then(setAgents);
    fetch(`${API}/assign/log?entity_type=${entityType}&entity_ref=${entityId}&limit=1`, { headers: { Authorization: `Bearer ${tok()}` } })
      .then(r => r.json()).then(d => setLast((d.log || [])[0] || null)).catch(() => {});
    const h = (e: any) => { if (ref.current && !ref.current.contains(e.target)) { setOpen(false); setMode('menu'); setQ(''); } };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, [open, entityType, entityId]);

  const assign = async (agent_id: number | null, name: string | null) => {
    setBusy(true);
    try {
      await fetch(`${API}/assign/${entityType}/${entityId}`, {
        method: 'POST', headers: { Authorization: `Bearer ${tok()}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ agent_id }),
      });
      onChanged && onChanged(name);
    } catch {}
    setBusy(false); setOpen(false); setMode('menu'); setQ('');
  };

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!has && !canReassign) return;        // nothing to do
    if (!open) {
      const r = ref.current?.getBoundingClientRect();
      if (r) {
        const flip = r.bottom + 300 > window.innerHeight;
        setPos({ left: Math.min(r.left, window.innerWidth - 252), top: flip ? r.top : r.bottom + 4, flip });
      }
      setMode(!has && canReassign ? 'pick' : 'menu');
      setOpen(true);
    } else { setOpen(false); setMode('menu'); }
  };

  const filtered = agents.filter(a =>
    twoWords(a.name).toLowerCase().includes(q.toLowerCase()) || (a.name || '').toLowerCase().includes(q.toLowerCase()));

  const clickable = has || canReassign;

  return (
    <span ref={ref} style={{ position: 'relative' }}>
      <span onClick={handleClick}
        title={clickable ? 'Click for options' : ''}
        style={{ color: has ? '#9fb0c0' : '#626d80', cursor: clickable ? 'pointer' : 'default',
          borderBottom: clickable ? '1px dotted #4f596b' : 'none' }}>
        {has ? twoWords(agentName) : '—'}
      </span>

      {open && (
        <div onClick={e => e.stopPropagation()} style={{ position: 'fixed', left: pos.left,
          ...(pos.flip ? { bottom: window.innerHeight - pos.top + 4 } : { top: pos.top }), zIndex: 99999,
          width: 240, background: '#1c1f28', border: '1px solid #434b5a', borderRadius: 10,
          boxShadow: '0 10px 34px rgba(0,0,0,0.6)', padding: 8 }}>
          {mode === 'menu' ? (
            <>
              {has && onSortBy && (
                <div onClick={() => { onSortBy(agentName!); setOpen(false); }} style={item}>🔎 Sort by {twoWords(agentName)}</div>
              )}
              {canReassign && (
                <div onClick={() => setMode('pick')} style={item}>✏️ Change sales agent</div>
              )}
              {canReassign && has && (
                <div onClick={() => assign(null, null)} style={{ ...item, color: '#ff6b6b' }}>✖ Unassign</div>
              )}
              {!has && !canReassign && <div style={{ ...item, color: '#667', cursor: 'default' }}>No sales agent</div>}
              {last && (
                <div style={{ fontSize: 9.5, color: '#667', padding: '7px 8px 2px', borderTop: '1px solid #2a3142', marginTop: 4, whiteSpace: 'normal', lineHeight: 1.5 }}>
                  Last change: <span style={{ color: '#9fb0c0' }}>{twoWords(last.from)}→{twoWords(last.to)}</span><br />
                  by {twoWords(last.by)} · {new Date(last.at).toLocaleString()}
                </div>
              )}
            </>
          ) : (
            <>
              <input autoFocus value={q} onChange={e => setQ(e.target.value)} placeholder="Search sales agent…"
                style={{ width: '100%', boxSizing: 'border-box', padding: '7px 9px', background: '#11141a',
                  border: '1px solid #2a3142', borderRadius: 7, color: '#e0e0e0', fontSize: 12, outline: 'none', marginBottom: 6 }} />
              <div style={{ maxHeight: 210, overflowY: 'auto' }}>
                {busy && <div style={{ ...item, color: '#667' }}>Saving…</div>}
                {!busy && filtered.map(a => (
                  <div key={a.id} onClick={() => assign(a.id, a.name)} style={item}>
                    {twoWords(a.name)}
                    {a.role === 'sales_manager' && <span style={{ color: '#667', fontSize: 9 }}> · mgr</span>}
                    {a.role === 'director' && <span style={{ color: '#667', fontSize: 9 }}> · dir</span>}
                  </div>
                ))}
                {!busy && !filtered.length && <div style={{ ...item, color: '#667', cursor: 'default' }}>No match</div>}
              </div>
            </>
          )}
        </div>
      )}
    </span>
  );
}

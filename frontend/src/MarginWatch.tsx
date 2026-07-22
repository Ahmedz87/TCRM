import React, { useState, useEffect, useRef } from 'react';
import { apiGet } from './api';

/**
 * MarginWatch (#210) — a small floating, DRAGGABLE icon that sticks on every page.
 * Drag it anywhere (position is remembered); click it to see the list of accounts whose margin
 * level is below the threshold (default 110%). Shows a "data as of" stamp so the desk knows how
 * fresh the equity/margin feed is. Data comes from GET /trading-accounts/margin-watch.
 */
export default function MarginWatch() {
  const [pos, setPos] = useState<{ x: number; y: number }>(() => {
    try { const s = JSON.parse(localStorage.getItem('marginwatch_pos') || 'null'); if (s && typeof s.x === 'number') return s; } catch {}
    return { x: (window.innerWidth || 1200) - 78, y: (window.innerHeight || 800) - 140 };
  });
  const posRef = useRef(pos);
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [threshold, setThreshold] = useState<number>(110);
  const drag = useRef<{ sx: number; sy: number; ox: number; oy: number; moved: boolean } | null>(null);

  const load = async (th: number) => {
    setLoading(true);
    try { const d = await apiGet(`/trading-accounts/margin-watch?threshold=${th}`); setData(d); } catch {}
    setLoading(false);
  };
  // poll the count every 2 min so the badge stays current even when closed
  useEffect(() => { load(threshold); const t = setInterval(() => load(threshold), 120000); return () => clearInterval(t); }, [threshold]);

  const onDown = (e: React.PointerEvent) => {
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    drag.current = { sx: e.clientX, sy: e.clientY, ox: posRef.current.x, oy: posRef.current.y, moved: false };
  };
  const onMove = (e: React.PointerEvent) => {
    if (!drag.current) return;
    const dx = e.clientX - drag.current.sx, dy = e.clientY - drag.current.sy;
    if (Math.abs(dx) > 4 || Math.abs(dy) > 4) drag.current.moved = true;
    const nx = Math.max(8, Math.min((window.innerWidth || 1200) - 56, drag.current.ox + dx));
    const ny = Math.max(8, Math.min((window.innerHeight || 800) - 56, drag.current.oy + dy));
    posRef.current = { x: nx, y: ny }; setPos(posRef.current);
  };
  const onUp = () => {
    if (drag.current) {
      if (drag.current.moved) { try { localStorage.setItem('marginwatch_pos', JSON.stringify(posRef.current)); } catch {} }
      else { setOpen(o => !o); if (!open) load(threshold); }   // a click (not a drag) toggles the panel
    }
    drag.current = null;
  };

  const count = data?.count || 0;
  const asOf = data?.data_as_of ? new Date(data.data_as_of) : null;
  const stale = asOf ? (Date.now() - asOf.getTime()) > 2 * 3600 * 1000 : false;
  const mlColor = (m: number) => m < 60 ? '#ff4d4d' : m < 100 ? '#ff8c00' : '#ffd23f';
  // open ONLY that client's profile (not a filtered list) — Clients handles openProfile directly
  const goTo = (login: number) => { window.dispatchEvent(new CustomEvent('navigate', { detail: { page: 'clients', search: String(login), openProfile: login } })); setOpen(false); };

  // panel opens toward the side of the screen with more room
  const panelLeft = pos.x < (window.innerWidth || 1200) / 2 ? pos.x : Math.max(8, pos.x - 320);
  const panelTop = Math.max(8, Math.min(pos.y - 10, (window.innerHeight || 800) - 420));

  return (
    <>
      {/* the draggable icon */}
      <div onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp}
        title="Margin watch — drag to move, click to open"
        style={{ position: 'fixed', left: pos.x, top: pos.y, zIndex: 2147483000, width: 46, height: 46,
          borderRadius: '50%', background: count > 0 ? 'linear-gradient(135deg,#F8500A,#ff8c00)' : '#2c333e',
          border: '2px solid ' + (count > 0 ? '#ffb020' : '#4f596b'), boxShadow: '0 6px 20px rgba(0,0,0,0.45)',
          cursor: 'grab', display: 'flex', alignItems: 'center', justifyContent: 'center', touchAction: 'none', userSelect: 'none' }}>
        <span style={{ fontSize: 20 }}>⚠️</span>
        {count > 0 && (
          <span style={{ position: 'absolute', top: -4, right: -4, minWidth: 18, height: 18, padding: '0 4px',
            borderRadius: 9, background: '#ff4d4d', color: '#fff', fontSize: 11, fontWeight: 700,
            display: 'flex', alignItems: 'center', justifyContent: 'center', border: '1px solid #20252f' }}>{count}</span>
        )}
      </div>

      {/* the list panel */}
      {open && (
        <>
          <div onClick={() => setOpen(false)} style={{ position: 'fixed', inset: 0, zIndex: 2147483001 }} />
          <div style={{ position: 'fixed', left: panelLeft, top: panelTop, width: 320, maxHeight: 420, overflowY: 'auto',
            background: '#20252f', border: '1px solid #4f596b', borderRadius: 12, zIndex: 2147483002,
            boxShadow: '0 10px 34px rgba(0,0,0,0.6)', color: '#fff' }}>
            <div style={{ padding: '12px 14px', borderBottom: '1px solid #3a4250', position: 'sticky', top: 0, background: '#20252f', borderRadius: '12px 12px 0 0' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ fontSize: 14, fontWeight: 700 }}>⚠️ Margin watch</div>
                <span onClick={() => setOpen(false)} style={{ cursor: 'pointer', color: '#8a93a5', fontSize: 16 }}>×</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 8 }}>
                <span style={{ fontSize: 11, color: '#8a93a5' }}>Below</span>
                {[100, 110, 150].map(th => (
                  <button key={th} onClick={() => setThreshold(th)}
                    style={{ padding: '2px 8px', borderRadius: 6, fontSize: 11, cursor: 'pointer',
                      border: '1px solid ' + (threshold === th ? '#F8500A' : '#4f596b'),
                      background: threshold === th ? 'rgba(248,80,10,0.15)' : 'transparent',
                      color: threshold === th ? '#FF6A1A' : '#8a93a5' }}>{th}%</button>
                ))}
                <span style={{ marginLeft: 'auto', fontSize: 12, fontWeight: 700, color: count > 0 ? '#ff8c00' : '#00e5a0' }}>{count}</span>
              </div>
              {asOf && (
                <div style={{ fontSize: 10, marginTop: 6, color: stale ? '#ff8c00' : '#6b7686' }}>
                  {stale ? '⚠ ' : ''}data as of {asOf.toLocaleString('en-GB')}{stale ? ' — live feed is behind' : ''}
                </div>
              )}
            </div>
            <div>
              {loading ? <div style={{ padding: 16, color: '#8a93a5', fontSize: 12 }}>Loading…</div>
                : count === 0 ? <div style={{ padding: 16, color: '#8a93a5', fontSize: 12 }}>No accounts below {threshold}%. 🎉</div>
                : (data.accounts || []).map((a: any) => (
                  <div key={a.login} onClick={() => goTo(a.login)}
                    style={{ padding: '8px 14px', borderBottom: '1px solid #2c333e', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8 }}
                    onMouseEnter={e => (e.currentTarget.style.background = '#2c333e')}
                    onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 12, fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{a.name || a.login}</div>
                      <div style={{ fontSize: 10, color: '#8a93a5' }}>#{a.login}{a.agent_name ? ' · ' + a.agent_name : ''}</div>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      <div style={{ fontSize: 13, fontWeight: 700, color: mlColor(a.margin_level) }}>{a.margin_level.toFixed(1)}%</div>
                      <div style={{ fontSize: 10, color: '#8a93a5' }}>${(a.equity || 0).toLocaleString('en-GB', { maximumFractionDigits: 0 })}</div>
                    </div>
                  </div>
                ))}
            </div>
          </div>
        </>
      )}
    </>
  );
}

import React, { useState, useRef } from 'react';
import ReactDOM from 'react-dom';
import { apiGet } from './api';

// ── ONE network-risk badge, used on EVERY page (Clients, Leads, IB, Transactions, Neg-balance). ──
// The score is the SINGLE canonical 0-10 value from the backend (build_network_scores.py); this file
// is the ONLY place that turns it into a colour and shows the detail popup, so the x/10 looks and
// behaves identically everywhere. Previous design restored: coloured PILL + details on HOVER.

// colour ladder (green → amber → red), same look the pages had before unification. CID scores 10 → red.
export function netColor(score: number): string {
  const s = Math.round(score || 0);
  if (s >= 7) return '#ff4d4d';   // red — device / CID, or multi-signal
  if (s >= 4) return '#ffaa00';   // amber — same payment sender / similar email
  if (s >= 1) return '#00e5a0';   // green — shared IP only / weak
  return '#5a6472';               // none
}
export function netLabel(score: number): string {
  const s = Math.round(score || 0);
  if (s >= 8) return 'Critical';
  if (s >= 5) return 'High';
  if (s >= 3) return 'Medium';
  if (s >= 1) return 'Low';
  return 'None';
}

const REASON_COLOR: Record<string, string> = {
  cid: '#ff4d4d', mqid: '#ff4d4d', pay_sender: '#ff8c00', similar_email: '#ffd166',
  ib: '#cc88ff', city: '#00aaff', payment: '#8a93a3', ip: '#8a93a3',
};

// simple per-key cache so re-hovering the same subject doesn't refetch
const _cache: Record<string, any> = {};

export default function NetworkBadge({
  score, login, leadId,
}: { score: number; login?: number | null; leadId?: number | null }) {
  const s = Math.max(0, Math.min(10, Math.round(score || 0)));
  const col = netColor(s);
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [pos, setPos] = useState<{ x: number; y: number; up?: boolean; maxH?: number }>({ x: 0, y: 0 });
  const ref = useRef<HTMLSpanElement>(null);
  const closeTimer = useRef<any>(null);

  const key = login ? `l${login}` : leadId ? `d${leadId}` : '';

  const load = () => {
    if (!key || _cache[key]) { if (_cache[key]) setData(_cache[key]); return; }
    setLoading(true);
    const qs = login ? `login=${login}` : `lead_id=${leadId}`;
    apiGet(`/network/connections?${qs}`)
      .then((d: any) => { _cache[key] = d; setData(d); })
      .catch(() => setData({ connections: [], error: true }))
      .finally(() => setLoading(false));
  };

  const enter = () => {
    if (closeTimer.current) { clearTimeout(closeTimer.current); closeTimer.current = null; }
    if (!key || s === 0) return;
    const r = ref.current?.getBoundingClientRect();
    if (r) {
      const POPUP_H = 420;   // matches maxHeight below
      const x = Math.min(r.left, window.innerWidth - 360);
      // #229/#284: keep the popup ATTACHED to its badge. Plenty of room below -> open downward.
      // Near the bottom of the screen -> FLIP UPWARD, anchored just above the badge (bottom-
      // anchored so it works whatever the popup's actual height) — the old clamp teleported it
      // to the top of the screen, detached from the row, which read as another lead's data.
      if (window.innerHeight - r.bottom >= POPUP_H + 14) {
        setPos({ x, y: r.bottom + 6, up: false, maxH: POPUP_H });
      } else {
        setPos({ x, y: window.innerHeight - r.top + 6, up: true,
                 maxH: Math.min(POPUP_H, Math.max(180, r.top - 16)) });
      }
    }
    setOpen(true); load();
  };
  const leave = () => { closeTimer.current = setTimeout(() => setOpen(false), 250); };

  const conns = data?.connections || [];

  return (
    <span style={{ position: 'relative', display: 'inline-block' }} onMouseEnter={enter} onMouseLeave={leave}>
      <span ref={ref}
        style={{
          display: 'inline-flex', alignItems: 'center', gap: 4, padding: '3px 9px', borderRadius: 99,
          border: `1px solid ${s ? col : '#2a3142'}`, background: s ? col + '18' : 'transparent',
          color: s ? col : '#5a6472', fontSize: 11, fontWeight: 600,
          cursor: s && key ? 'help' : 'default', whiteSpace: 'nowrap',
        }}>
        {s}/10
      </span>

      {open && ReactDOM.createPortal(
        <div onMouseEnter={enter} onMouseLeave={leave}
          style={{
            position: 'fixed', left: pos.x, width: 350, maxHeight: pos.maxH ?? 420, overflowY: 'auto',
            ...(pos.up ? { bottom: pos.y } : { top: pos.y }),
            background: '#20252f', border: `1px solid ${col}`, borderRadius: 10, zIndex: 100000,
            boxShadow: '0 12px 40px rgba(0,0,0,0.6)', padding: 12, textAlign: 'left',
          }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <span style={{ fontSize: 15, fontWeight: 800, color: col }}>{s}/10</span>
            <span style={{ fontSize: 11, fontWeight: 700, color: col, textTransform: 'uppercase', letterSpacing: .5 }}>{netLabel(s)}</span>
            {data?.reason && <span style={{ fontSize: 10, color: '#8a93a3' }}>· {data.reason}</span>}
            <span style={{ marginLeft: 'auto', fontSize: 10, color: '#667' }}>{conns.length} linked</span>
          </div>
          {loading ? <div style={{ color: '#667', fontSize: 12, padding: 12, textAlign: 'center' }}>Loading…</div>
            : conns.length === 0
              ? <div style={{ color: '#667', fontSize: 12, padding: 12, textAlign: 'center' }}>
                  {data?.error ? 'Could not load connections.' : 'No linked accounts — not connected to anyone.'}</div>
              : conns.map((c: any, i: number) => (
                <div key={i}
                  onClick={() => { if (c.login) window.dispatchEvent(new CustomEvent('navigate', { detail: { page: 'clients', login: c.login } })); }}
                  style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 6px', borderTop: '1px solid #2a3142', cursor: c.login ? 'pointer' : 'default' }}>
                  <span style={{ minWidth: 28, textAlign: 'center', fontSize: 11, fontWeight: 700, fontFamily: 'monospace',
                    color: netColor(c.score10 || 0) }}>{c.score10 || 0}</span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 12, color: '#e6e9ef', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {c.name || (c.kind === 'lead' ? `Lead #${c.id}` : `#${c.login}`)}</div>
                    <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginTop: 2 }}>
                      {(c.reasons || []).slice(0, 3).map((rr: any, j: number) => (
                        <span key={j} style={{ fontSize: 9, padding: '1px 5px', borderRadius: 4,
                          background: (REASON_COLOR[rr.type] || '#667') + '22', color: REASON_COLOR[rr.type] || '#889' }}>
                          {rr.label}</span>
                      ))}
                    </div>
                  </div>
                  {c.country && <span style={{ fontSize: 10, color: '#667' }}>{c.country}</span>}
                </div>
              ))}
        </div>,
        document.body,
      )}
    </span>
  );
}

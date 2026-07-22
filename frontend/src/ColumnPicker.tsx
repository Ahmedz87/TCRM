import React, { useState, useRef } from 'react';
import ReactDOM from 'react-dom';

/**
 * Reusable per-user column show/hide picker — the same ⚙ control the Clients page has, so every
 * list page (Leads, Transactions, IB Admin, …) can offer it with one hook + one button.
 *
 *   const cols = useColumnPicker(COLS, 'leads_cols_v1', { locked: ['Lead','Actions'] });
 *   ...toolbar:  <ColumnGear picker={cols} t={t} />
 *   ...header:   COLS.filter(h => cols.V(h)).map(h => <th>…</th>)
 *   ...colgroup: COLS.filter(h => cols.V(h)).map(h => <col style={{width: W[h]}}/>)
 *   ...row:      {cols.V('Phone') && <td>…</td>}   // locked columns render unconditionally
 *
 * Choice persists in localStorage under `storageKey` (versioned per page).
 */
export type ColumnPicker = {
  cols: string[];
  locked: string[];
  V: (h: string) => boolean;
  toggle: (h: string) => void;
  reset: () => void;
};

export function useColumnPicker(
  cols: string[],
  storageKey: string,
  opts?: { locked?: string[]; hideDefault?: string[] }
): ColumnPicker {
  const locked = opts?.locked || [];
  const hideDefault = opts?.hideDefault || [];
  const seed = (): Record<string, boolean> => {
    const d: Record<string, boolean> = {};
    cols.forEach(c => (d[c] = !hideDefault.includes(c)));
    return d;
  };
  const [vis, setVis] = useState<Record<string, boolean>>(() => {
    try {
      const s = JSON.parse(localStorage.getItem(storageKey) || 'null');
      if (s && typeof s === 'object') return { ...seed(), ...s };
    } catch {}
    return seed();
  });
  const V = (h: string) => locked.includes(h) || vis[h] !== false;
  const toggle = (h: string) =>
    setVis(p => {
      const n = { ...p, [h]: !(locked.includes(h) || p[h] !== false) };
      try { localStorage.setItem(storageKey, JSON.stringify(n)); } catch {}
      return n;
    });
  const reset = () => {
    try { localStorage.removeItem(storageKey); } catch {}
    setVis(seed());
  };
  return { cols, locked, V, toggle, reset };
}

export function ColumnGear({ picker, t = (x: string) => x }: { picker: ColumnPicker; t?: (s: string) => string }) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number }>({ top: 0, left: 0 });
  const btnRef = useRef<HTMLButtonElement>(null);
  const { cols, locked, V, toggle, reset } = picker;
  const MENU_W = 210;
  const openMenu = () => {
    const r = btnRef.current?.getBoundingClientRect();
    if (r) {
      // anchor the menu under the button, right-aligned, clamped to the viewport
      const left = Math.max(8, Math.min(r.right - MENU_W, window.innerWidth - MENU_W - 8));
      setPos({ top: Math.min(r.bottom + 6, window.innerHeight - 120), left });
    }
    setOpen(v => !v);
  };
  return (
    <div style={{ position: 'relative', flexShrink: 0 }}>
      <button ref={btnRef} onClick={openMenu} title={t('Columns')}
        style={{ width: 34, height: 34, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center',
          border: `1px solid ${open ? '#00e5a0' : 'var(--border2,#626d80)'}`, background: open ? 'rgba(0,229,160,0.1)' : 'transparent',
          color: open ? '#00e5a0' : 'var(--text2,#888)', cursor: 'pointer', fontSize: 15 }}>
        ⚙
      </button>
      {open && ReactDOM.createPortal(
        <>
          {/* click-away backdrop */}
          <div onClick={() => setOpen(false)} style={{ position: 'fixed', inset: 0, zIndex: 2147483646 }} />
          {/* the menu is rendered to <body> via a portal + position:fixed so no toolbar overflow can clip it */}
          <div style={{ position: 'fixed', top: pos.top, left: pos.left, zIndex: 2147483647, background: '#2c333e', border: '1px solid #4f596b',
            borderRadius: 10, padding: 10, width: MENU_W, maxHeight: '60vh', overflowY: 'auto', boxShadow: '0 8px 24px rgba(0,0,0,0.5)' }}>
            <div style={{ fontSize: 10, color: '#8b93a1', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 6 }}>{t('Show columns')}</div>
            {cols.filter(h => !locked.includes(h)).map(h => (
              <label key={h} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 2px', cursor: 'pointer', fontSize: 12, color: '#cfd6e0' }}>
                <input type="checkbox" checked={V(h)} onChange={() => toggle(h)} style={{ cursor: 'pointer' }} />
                {t(h)}
              </label>
            ))}
            <div style={{ borderTop: '1px solid #373f4d', marginTop: 6, paddingTop: 6 }}>
              <span onClick={reset} style={{ fontSize: 11, color: '#00aaff', cursor: 'pointer', textDecoration: 'underline' }}>{t('Reset to default')}</span>
            </div>
          </div>
        </>,
        document.body
      )}
    </div>
  );
}

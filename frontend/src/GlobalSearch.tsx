import React, { useEffect, useRef, useState, useCallback } from 'react';
import { apiGet } from './api';

// One box, everything. Staff-only global search over clients / leads / IBs / trading accounts /
// trades / transactions / deposits. Backed by GET /search?q= (search_router.py). Theme-aware via
// CSS vars (dark source of truth; light engine remaps) — no light-only palette.

type Item = {
  type: string; title: string; subtitle: string; meta?: string;
  nav?: { page: string; search?: string; openProfile?: number; login?: number; ibId?: number };
};
type Group = { category: string; label: string; icon: string; count: number; items: Item[] };
type Result = { query: string; total: number; groups: Group[] };

const TYPE_C: Record<string, string> = {
  client: '#00aaff', lead: '#9966ff', ib: '#ffaa00', account: '#4d9fff',
  trade: '#00e5a0', transaction: '#ff8ac8', deposit: '#22c9a0',
};

function go(nav?: Item['nav']) {
  if (!nav) return;
  window.dispatchEvent(new CustomEvent('navigate', { detail: nav }));
}

export default function GlobalSearch({ initial = '' }: { initial?: string }) {
  const [q, setQ] = useState(initial);
  const [res, setRes] = useState<Result | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);
  const seq = useRef(0);

  useEffect(() => { inputRef.current?.focus(); }, []);

  const run = useCallback((query: string) => {
    const term = query.trim();
    if (term.length < 2) { setRes(null); setLoading(false); setErr(''); return; }
    const my = ++seq.current;
    setLoading(true); setErr('');
    apiGet('/search?q=' + encodeURIComponent(term))
      .then((d: Result) => { if (my === seq.current) { setRes(d); setLoading(false); } })
      .catch(() => { if (my === seq.current) { setErr('Search failed — try again.'); setLoading(false); } });
  }, []);

  // debounce as you type
  useEffect(() => {
    const t = setTimeout(() => run(q), 280);
    return () => clearTimeout(t);
  }, [q, run]);

  return (
    <div style={{ maxWidth: 960, margin: '0 auto', width: '100%', display: 'flex', flexDirection: 'column', gap: 16, padding: '8px 4px 40px' }}>
      <div>
        <div style={{ fontSize: 20, fontWeight: 800, color: 'var(--text,#e8ecf3)', marginBottom: 4 }}>Global search</div>
        <div style={{ fontSize: 12.5, color: 'var(--text2,#8a93a3)' }}>
          Search anything — a login, phone, email, name, customer #, IB code, trade ID, transaction ref or deposit/sender ID.
        </div>
      </div>

      {/* search box */}
      <div style={{ position: 'relative' }}>
        <span style={{ position: 'absolute', left: 16, top: '50%', transform: 'translateY(-50%)', fontSize: 18, opacity: 0.7 }}>🔍</span>
        <input
          ref={inputRef}
          value={q}
          onChange={e => setQ(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') run(q); }}
          placeholder="e.g. 55577788, name@email.com, +9647…, IB code, trade #…"
          style={{
            width: '100%', boxSizing: 'border-box', padding: '15px 16px 15px 46px', fontSize: 15,
            borderRadius: 14, border: '1px solid var(--border2,#626d80)', background: 'var(--bg-input,#373f4d)',
            color: 'var(--text,#e8ecf3)', outline: 'none',
          }}
        />
        {loading && <span style={{ position: 'absolute', right: 16, top: '50%', transform: 'translateY(-50%)', fontSize: 12, color: 'var(--text2,#8a93a3)' }}>searching…</span>}
      </div>

      {err && <div style={{ color: '#ff8080', fontSize: 13 }}>{err}</div>}

      {res && res.total === 0 && !loading && (
        <div style={{ textAlign: 'center', padding: 50, color: 'var(--text2,#8a93a3)', fontSize: 14 }}>
          No matches for <b style={{ color: 'var(--text,#e8ecf3)' }}>“{res.query}”</b>.
        </div>
      )}

      {res && res.total > 0 && (
        <div style={{ fontSize: 12, color: 'var(--text2,#8a93a3)' }}>
          {res.total} result{res.total === 1 ? '' : 's'} for <b style={{ color: 'var(--text,#e8ecf3)' }}>“{res.query}”</b>
        </div>
      )}

      {res?.groups.map(g => (
        <div key={g.category} style={{ background: 'var(--bg-card,#2c333e)', border: '1px solid var(--border,#4f596b)', borderRadius: 14, overflow: 'hidden' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '11px 16px', borderBottom: '1px solid var(--border,#4f596b)', background: 'var(--bg-input,#31384420)' }}>
            <span style={{ fontSize: 16 }}>{g.icon}</span>
            <span style={{ fontSize: 13, fontWeight: 800, color: 'var(--text,#e8ecf3)', textTransform: 'uppercase', letterSpacing: 0.5 }}>{g.label}</span>
            <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--text2,#8a93a3)', background: 'var(--bg-input,#373f4d)', borderRadius: 99, padding: '1px 8px' }}>{g.count}</span>
          </div>
          {g.items.map((it, i) => (
            <div
              key={i}
              onClick={() => go(it.nav)}
              style={{
                display: 'flex', alignItems: 'center', gap: 12, padding: '11px 16px', cursor: 'pointer',
                borderBottom: i < g.items.length - 1 ? '1px solid var(--border,#3a424f)' : 'none',
              }}
              onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-hover,rgba(255,255,255,0.03))')}
              onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
            >
              <span style={{
                flexShrink: 0, fontSize: 9.5, fontWeight: 800, textTransform: 'uppercase', letterSpacing: 0.5,
                color: TYPE_C[it.type] || '#8a93a3', border: `1px solid ${(TYPE_C[it.type] || '#8a93a3')}55`,
                borderRadius: 6, padding: '3px 7px', minWidth: 74, textAlign: 'center',
              }}>{it.type}</span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13.5, fontWeight: 700, color: 'var(--text,#e8ecf3)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{it.title}</div>
                <div style={{ fontSize: 11.5, color: 'var(--text2,#8a93a3)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{it.subtitle}</div>
              </div>
              {it.meta && (
                <span style={{ flexShrink: 0, fontSize: 11, fontWeight: 700, color: 'var(--text2,#98a2b3)' }}>{it.meta}</span>
              )}
              <span style={{ flexShrink: 0, color: 'var(--text2,#8a93a3)', fontSize: 16 }}>›</span>
            </div>
          ))}
        </div>
      ))}

      {!res && !loading && (
        <div style={{ textAlign: 'center', padding: 40, color: 'var(--text2,#8a93a3)', fontSize: 13 }}>
          Start typing to search across the whole CRM.
        </div>
      )}
    </div>
  );
}

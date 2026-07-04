import React, { useEffect, useState, useCallback } from 'react';
import { apiGet, apiPost } from '../api';

function useIsMobile(bp = 760) { const [m, setM] = useState(() => typeof window !== 'undefined' && window.innerWidth <= bp); useEffect(() => { const o = () => setM(window.innerWidth <= bp); window.addEventListener('resize', o); return () => window.removeEventListener('resize', o); }, [bp]); return m; }

// ───────────────────────── helpers ─────────────────────────
const fmt = (n: number, d = 0) => (n ?? 0).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d });
const pos = (n: number) => (n >= 0 ? '#34D399' : '#F2667A');
const riskColor = (r: number) => (r <= 3 ? '#34D399' : r <= 6 ? '#F8500A' : '#F2667A');
const riskLabel = (r: number) => (r <= 3 ? 'Low' : r <= 6 ? 'Medium' : 'High');

// inline SVG equity/return curve
function Curve({ points, color = '#34D399', h = 44, w = 150, fill = true }: any) {
  if (!points || points.length < 2) return <div style={{ height: h }} />;
  const ys = points as number[];
  const min = Math.min(...ys), max = Math.max(...ys), span = max - min || 1;
  const step = w / (ys.length - 1);
  const pts = ys.map((y, i) => `${(i * step).toFixed(1)},${(h - ((y - min) / span) * (h - 4) - 2).toFixed(1)}`);
  const line = 'M' + pts.join(' L');
  const area = `${line} L${w},${h} L0,${h} Z`;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" width="100%" height={h} style={{ display: 'block', maxWidth: '100%' }}>
      {fill && <path d={area} fill={color} opacity={0.12} />}
      <path d={line} fill="none" stroke={color} strokeWidth={1.8} />
    </svg>
  );
}

function Stat({ label, value, color }: any) {
  return (
    <div style={{ textAlign: 'center', flex: 1 }}>
      <div style={{ fontSize: 14.5, fontWeight: 800, color: color || '#E7ECF3' }}>{value}</div>
      <div style={{ fontSize: 9.5, color: '#8A93A3', textTransform: 'uppercase', letterSpacing: '0.06em', marginTop: 2 }}>{label}</div>
    </div>
  );
}

// ───────────────────────── provider card ─────────────────────────
function ProviderCard({ p, onOpen, onFollow }: any) {
  return (
    <div style={{ ...C.card, ...(p.active === false ? { opacity: 0.6 } : {}) }} onClick={() => onOpen(p.id)}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 11 }}>
        <div style={C.avatar}>{p.avatar || '📈'}</div>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <div style={{ fontSize: 14, fontWeight: 800, color: '#fff', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.name}</div>
            {p.is_real && <span title="Real verified track record" style={C.realBadge}>REAL</span>}
            {p.active === false && <span title={`Inactive — last trade ${p.last_trade_at}`} style={C.inactiveBadge}>INACTIVE</span>}
            {p.verified && p.active !== false && <span title="Verified" style={{ color: '#4DA8FF', fontSize: 12 }}>✔</span>}
            {p.featured && <span style={C.featBadge}>★</span>}
          </div>
          <div style={{ fontSize: 11, color: '#8A93A3' }}>{p.strategy} · {p.markets}</div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: 18, fontWeight: 900, color: pos(p.return_pct) }}>{p.return_pct >= 0 ? '+' : ''}{fmt(p.return_pct, 1)}%</div>
          <div style={{ fontSize: 9.5, color: '#8A93A3' }}>{p.days_active}d return</div>
        </div>
      </div>

      <div style={{ margin: '10px 0 8px' }}>
        <Curve points={genCurve(p.return_pct, p.days_active)} color={pos(p.return_pct)} w={300} h={40} />
      </div>

      <div style={{ display: 'flex', borderTop: '1px solid #1A1F2B', paddingTop: 9 }}>
        <Stat label="Win" value={`${fmt(p.win_rate, 0)}%`} />
        <Stat label="Max DD" value={`${fmt(p.max_drawdown, 1)}%`} color="#F2667A" />
        <Stat label="Risk" value={riskLabel(p.risk_level)} color={riskColor(p.risk_level)} />
        <Stat label="Copiers" value={fmt(p.followers)} />
      </div>

      <button
        style={{ ...C.followBtn, ...(p.following ? C.followingBtn : {}) }}
        onClick={(e) => { e.stopPropagation(); onFollow(p); }}
      >
        {p.following ? '✓ Copying' : 'Copy'}
      </button>
    </div>
  );
}

// fabricate a plausible curve shape from the headline return (cards don't fetch full history)
function genCurve(ret: number, days: number) {
  const n = Math.max(8, Math.min(40, days));
  const out: number[] = [];
  let v = 0;
  for (let i = 0; i < n; i++) {
    const drift = (ret / n);
    v += drift + Math.sin(i * 1.7) * Math.abs(ret) * 0.04 + (i % 3 === 0 ? -Math.abs(ret) * 0.03 : 0);
    out.push(v);
  }
  out[out.length - 1] = ret;
  return out;
}

// ───────────────────────── detail + follow modal ─────────────────────────
function DetailModal({ id, onClose, onChanged }: any) {
  const mobile = useIsMobile();
  const [d, setD] = useState<any>(null);
  const [tab, setTab] = useState<'trades' | 'open' | 'copiers'>('trades');
  const [showFollow, setShowFollow] = useState(false);
  const [alloc, setAlloc] = useState('');
  const [mult, setMult] = useState('1');
  const [mode, setMode] = useState('proportional');
  const [copyExisting, setCopyExisting] = useState('all');
  const [maxLot, setMaxLot] = useState('');
  const [stopPct, setStopPct] = useState('');
  const [isDemo, setIsDemo] = useState(false);
  const [agree, setAgree] = useState(false);
  const [accepted, setAccepted] = useState(true);   // assume accepted; fetch corrects
  const [openPos, setOpenPos] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('');

  const load = useCallback(() => { apiGet(`/portal/copy/providers/${id}`).then(setD).catch(() => {}); }, [id]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { apiGet(`/portal/copy/providers/${id}/open-positions`).then(setOpenPos).catch(() => setOpenPos({ positions: [] })); }, [id]);
  useEffect(() => { apiGet('/portal/copy/disclaimer').then((r: any) => setAccepted(!!r?.accepted)).catch(() => {}); }, []);

  if (!d) return (
    <div style={C.overlay} onClick={onClose}><div style={C.modal} onClick={e => e.stopPropagation()}><div style={{ padding: 40, textAlign: 'center', color: '#8A93A3' }}>Loading…</div></div></div>
  );

  const eq = (d.equity_curve || []).map((x: any) => x.equity);
  const submitFollow = async () => {
    const a = parseFloat(alloc);
    if (!a || a < d.min_investment) { setMsg(`Minimum is $${fmt(d.min_investment)}`); return; }
    if (!accepted && !isDemo && !agree) { setMsg('Please accept the risk disclosure to continue.'); return; }
    setBusy(true); setMsg('');
    try {
      if (!accepted && !isDemo && agree) { await apiPost('/portal/copy/disclaimer/accept', {}); setAccepted(true); }
      const r: any = await apiPost('/portal/copy/follow', { provider_id: d.id, allocation: a, multiplier: parseFloat(mult) || 1, copy_mode: mode, copy_existing: copyExisting, max_lot: maxLot ? parseFloat(maxLot) : null, stop_equity_pct: stopPct ? parseFloat(stopPct) : null, is_demo: isDemo });
      setMsg(r?.message || 'Copying started'); setShowFollow(false); load(); onChanged && onChanged();
    } catch (e: any) {
      const m = e?.message === 'disclaimer_required' ? 'Please accept the risk disclosure first.' : (e?.message || 'Could not start copying');
      setMsg(m);
    }
    finally { setBusy(false); }
  };
  const stop = async () => {
    setBusy(true);
    try { await apiPost('/portal/copy/unfollow', { provider_id: d.id }); load(); onChanged && onChanged(); }
    finally { setBusy(false); }
  };

  return (
    <div style={C.overlay} onClick={onClose}>
      <div style={{ ...C.modal, ...(mobile ? { padding: 16 } : {}) }} onClick={e => e.stopPropagation()}>
        <button style={C.close} onClick={onClose}>✕</button>

        {/* header */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 16 }}>
          <div style={{ ...C.avatar, width: 54, height: 54, fontSize: 26 }}>{d.avatar || '📈'}</div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 19, fontWeight: 900, color: '#fff' }}>{d.name} {d.verified && <span style={{ color: '#4DA8FF', fontSize: 14 }}>✔</span>}</div>
            <div style={{ fontSize: 12.5, color: '#8A93A3' }}>{d.strategy} · {d.markets} · {d.country}</div>
          </div>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: mobile ? 21 : 26, fontWeight: 900, color: pos(d.return_pct) }}>{d.return_pct >= 0 ? '+' : ''}{fmt(d.return_pct, 1)}%</div>
            <div style={{ fontSize: 10.5, color: '#8A93A3' }}>{d.days_active}-day return</div>
          </div>
        </div>

        {/* equity curve */}
        <div style={{ background: '#0B0E14', borderRadius: 12, padding: '14px 16px', border: '1px solid #1A1F2B', marginBottom: 14 }}>
          <div style={{ fontSize: 11, color: '#8A93A3', marginBottom: 6 }}>Equity curve · start ${fmt(10000)}</div>
          <Curve points={eq} color={pos(d.return_pct)} w={620} h={120} />
        </div>

        {/* stats grid */}
        <div style={{ display: 'flex', gap: 8, marginBottom: 8, flexWrap: 'wrap' }}>
          {[['Win rate', `${fmt(d.win_rate, 0)}%`, '#E7ECF3'],
            ['Max DD', `${fmt(d.max_drawdown, 1)}%`, '#F2667A'],
            ['Profit factor', fmt(d.profit_factor, 2), '#E7ECF3'],
            ['Trades', fmt(d.total_trades), '#E7ECF3'],
            ['Avg hold', `${fmt(d.avg_hold_min)}m`, '#E7ECF3'],
            ['Risk', riskLabel(d.risk_level), riskColor(d.risk_level)],
            ['Copiers', fmt(d.followers), '#E7ECF3'],
            ['Fee', `${fmt(d.fee_pct)}%`, '#F8500A']].map(([l, v, c]: any) => (
            <div key={l} style={C.statBox}><div style={{ fontSize: 15, fontWeight: 800, color: c }}>{v}</div><div style={C.statLbl}>{l}</div></div>
          ))}
        </div>
        {d.bio && <div style={{ fontSize: 12.5, color: '#aab2c0', lineHeight: 1.5, margin: '6px 2px 14px' }}>{d.bio}</div>}

        {/* current copy status */}
        {d.i_follow && (
          <div style={C.followingNote}>
            <div>You're copying with <b style={{ color: '#fff' }}>${fmt(d.i_follow.allocation)}</b> · {d.i_follow.copy_mode} ×{d.i_follow.multiplier} · since {d.i_follow.since}
              <span style={{ color: pos(d.i_follow.pnl), marginLeft: 8 }}>P/L {d.i_follow.pnl >= 0 ? '+' : ''}${fmt(d.i_follow.pnl, 2)}</span>
            </div>
            <button style={C.stopBtn} disabled={busy} onClick={stop}>Stop copying</button>
          </div>
        )}

        {/* follow CTA / form */}
        {!d.i_follow && !showFollow && (
          <button style={C.bigFollow} onClick={() => { setShowFollow(true); setAlloc(String(d.min_investment)); }}>Copy this trader</button>
        )}
        {showFollow && (
          <div style={C.followForm}>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              <div style={{ flex: 1, minWidth: 150 }}>
                <label style={C.lbl}>Allocation (USD) — your copy capital</label>
                <input value={alloc} onChange={e => setAlloc(e.target.value)} placeholder={`min $${fmt(d.min_investment)}`} style={C.input} />
              </div>
              <div style={{ width: 110 }}>
                <label style={C.lbl}>Multiplier</label>
                <select value={mult} onChange={e => setMult(e.target.value)} style={C.input}>
                  {['0.5', '1', '1.5', '2', '3'].map(m => <option key={m} value={m}>×{m}</option>)}
                </select>
              </div>
              <div style={{ width: 150 }}>
                <label style={C.lbl}>Copy mode</label>
                <select value={mode} onChange={e => setMode(e.target.value)} style={C.input}>
                  <option value="proportional">Proportional</option>
                  <option value="fixed">Fixed lot</option>
                  <option value="mirror">Mirror</option>
                </select>
              </div>
            </div>

            {/* their currently-open positions handling */}
            <div style={{ marginTop: 12 }}>
              <label style={C.lbl}>Their open positions ({openPos?.positions?.length || 0})</label>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {[['all', 'Copy all open (incl. losing)'], ['skip_losing', 'Copy open, skip losing'], ['new', 'Only new trades']].map(([v, l]: any) => (
                  <button key={v} type="button" onClick={() => setCopyExisting(v)}
                    style={{ ...C.optBtn, ...(copyExisting === v ? C.optBtnActive : {}) }}>{l}</button>
                ))}
              </div>
            </div>

            {/* risk controls */}
            <div style={{ display: 'flex', gap: 10, marginTop: 12, flexWrap: 'wrap' }}>
              <div style={{ flex: 1, minWidth: 130 }}>
                <label style={C.lbl}>Max lot / trade (optional)</label>
                <input value={maxLot} onChange={e => setMaxLot(e.target.value)} placeholder="e.g. 0.50" style={C.input} />
              </div>
              <div style={{ flex: 1, minWidth: 130 }}>
                <label style={C.lbl}>Stop copy if loss ≥ % (optional)</label>
                <input value={stopPct} onChange={e => setStopPct(e.target.value)} placeholder="e.g. 20" style={C.input} />
              </div>
            </div>

            {/* demo toggle + low-allocation guardrail */}
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 12, cursor: 'pointer', fontSize: 12.5, color: '#aab2c0' }}>
              <input type="checkbox" checked={isDemo} onChange={e => setIsDemo(e.target.checked)} />
              Copy on <b style={{ color: '#fff' }}>demo</b> (paper trade — no risk, try before going live)
            </label>
            {alloc && parseFloat(alloc) > 0 && parseFloat(alloc) < d.min_investment * 2 && (
              <div style={{ fontSize: 11, color: '#F8500A', marginTop: 8 }}>⚠ Low allocation can round up to the minimum lot size and over-leverage. Consider at least ${fmt(d.min_investment * 2)}.</div>
            )}

            <div style={{ fontSize: 11, color: '#8A93A3', margin: '10px 2px' }}>
              ⓘ Allocation is your own capital assigned to this trader (not a fee). The provider charges a {fmt(d.fee_pct)}% performance fee on profits. {d.is_real ? '' : 'Automatic execution activates in an upcoming release — no live orders are placed yet.'}
            </div>

            {/* risk disclosure (first time only) */}
            {!accepted && !isDemo && (
              <label style={{ display: 'flex', alignItems: 'flex-start', gap: 8, background: 'rgba(242,102,122,0.07)', border: '1px solid rgba(242,102,122,0.2)', borderRadius: 10, padding: 11, margin: '4px 0 10px', cursor: 'pointer', fontSize: 11.5, color: '#aab2c0', lineHeight: 1.5 }}>
                <input type="checkbox" checked={agree} onChange={e => setAgree(e.target.checked)} style={{ marginTop: 2 }} />
                <span>I understand that copy trading carries risk: <b style={{ color: '#fff' }}>past performance does not guarantee future results</b>, and I may lose part or all of my allocated capital. I'm copying at my own discretion.</span>
              </label>
            )}

            <div style={{ display: 'flex', gap: 8 }}>
              <button style={C.bigFollow} disabled={busy} onClick={submitFollow}>{busy ? 'Saving…' : (isDemo ? 'Start demo copy' : 'Confirm & copy')}</button>
              <button style={C.ghostBtn} onClick={() => setShowFollow(false)}>Cancel</button>
            </div>
          </div>
        )}
        {msg && <div style={{ fontSize: 12, color: '#F8500A', marginTop: 8 }}>{msg}</div>}

        {/* tabs: trades / open / copiers */}
        <div style={{ display: 'flex', gap: 6, margin: '18px 0 10px', flexWrap: 'wrap' }}>
          <button style={{ ...C.tab, ...(tab === 'trades' ? C.tabActive : {}) }} onClick={() => setTab('trades')}>Recent trades</button>
          <button style={{ ...C.tab, ...(tab === 'open' ? C.tabActive : {}) }} onClick={() => setTab('open')}>Open positions{openPos?.positions?.length ? ` (${openPos.positions.length})` : ''}</button>
          <button style={{ ...C.tab, ...(tab === 'copiers' ? C.tabActive : {}) }} onClick={() => setTab('copiers')}>Copiers</button>
        </div>
        {tab === 'open' && (
          <div style={{ maxHeight: 240, overflowY: 'auto', overflowX: 'auto' }}>
            {openPos?.source === 'recent' && <div style={{ fontSize: 11, color: '#8A93A3', padding: '4px 2px 8px' }}>Recent activity (live positions sync on next bridge update).</div>}
            {(openPos?.positions || []).length === 0 ? <div style={{ color: '#8A93A3', padding: 14, fontSize: 12.5 }}>No open positions right now.</div> :
              (openPos.positions).map((t: any, i: number) => (
                <div key={i} style={C.tradeRow}>
                  <span style={{ width: 70, fontWeight: 700, color: '#E7ECF3' }}>{t.symbol}</span>
                  <span style={{ width: 44, color: t.side === 'Buy' ? '#34D399' : '#F2667A' }}>{t.side}</span>
                  <span style={{ width: 54, color: '#8A93A3' }}>{t.lots} lot</span>
                  <span style={{ flex: 1, color: '#8A93A3', fontSize: 11 }}>{t.open_price ? `@ ${t.open_price}` : (t.open_time || '')}</span>
                  <span style={{ width: 80, textAlign: 'right', fontWeight: 800, color: pos(t.profit) }}>{t.profit >= 0 ? '+' : ''}${fmt(t.profit, 2)}</span>
                </div>
              ))}
          </div>
        )}
        {tab === 'trades' && (
          <div style={{ maxHeight: 240, overflowY: 'auto', overflowX: 'auto' }}>
            {(d.recent_trades || []).map((t: any, i: number) => (
              <div key={i} style={C.tradeRow}>
                <span style={{ width: 70, fontWeight: 700, color: '#E7ECF3' }}>{t.symbol}</span>
                <span style={{ width: 44, color: t.side === 'Buy' ? '#34D399' : '#F2667A' }}>{t.side}</span>
                <span style={{ width: 54, color: '#8A93A3' }}>{t.lots} lot</span>
                <span style={{ flex: 1, color: '#8A93A3', fontSize: 11 }}>{t.close_time} · {t.hold_min}m</span>
                <span style={{ width: 80, textAlign: 'right', fontWeight: 800, color: pos(t.pnl) }}>{t.pnl >= 0 ? '+' : ''}${fmt(t.pnl, 2)}</span>
              </div>
            ))}
          </div>
        )}
        {tab === 'copiers' && (
          <div style={{ maxHeight: 240, overflowY: 'auto', overflowX: 'auto' }}>
            {(d.recent_followers || []).map((f: any, i: number) => (
              <div key={i} style={C.tradeRow}>
                <span style={{ flex: 1, color: '#E7ECF3' }}>{f.name}</span>
                <span style={{ width: 90, color: '#8A93A3' }}>${fmt(f.allocation)}</span>
                <span style={{ width: 70, color: '#8A93A3', fontSize: 11 }}>{f.since}</span>
                <span style={{ width: 80, textAlign: 'right', color: pos(f.pnl) }}>{f.pnl >= 0 ? '+' : ''}${fmt(f.pnl, 2)}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ───────────────────────── become-provider tab ─────────────────────────
function BecomeProvider() {
  const [app, setApp] = useState<any>(undefined);
  const [pd, setPd] = useState<any>(null);
  const [elig, setElig] = useState<any>(null);
  const [form, setForm] = useState({ strategy: 'Intraday', markets: 'FX Majors', risk_level: 5, fee_pct: 20, min_investment: 250, bio: '' });
  const [busy, setBusy] = useState(false); const [msg, setMsg] = useState('');
  useEffect(() => {
    apiGet('/portal/copy/my-provider').then((r: any) => setApp(r?.application || null)).catch(() => setApp(null));
    apiGet('/portal/copy/provider-dashboard').then((r: any) => setPd(r?.provider || null)).catch(() => {});
    apiGet('/portal/copy/eligibility').then(setElig).catch(() => {});
  }, []);
  const submit = async () => {
    setBusy(true); setMsg('');
    try { const r: any = await apiPost('/portal/copy/apply', form); setMsg(r?.message || 'Submitted'); apiGet('/portal/copy/my-provider').then((x: any) => setApp(x?.application || null)); }
    catch (e: any) { setMsg(e?.message || 'Could not submit'); } finally { setBusy(false); }
  };
  if (app === undefined) return <div style={{ color: '#8A93A3', padding: 30 }}>Loading…</div>;
  if (app) return (
    <div style={C.panel}>
      <div style={{ fontSize: 16, fontWeight: 800, color: '#fff', marginBottom: 6 }}>Your provider profile</div>
      <div style={{ display: 'inline-block', padding: '4px 12px', borderRadius: 99, fontSize: 12, fontWeight: 700,
        background: app.status === 'approved' ? 'rgba(52,211,153,0.12)' : app.status === 'pending' ? 'rgba(232,184,75,0.12)' : 'rgba(242,102,122,0.12)',
        color: app.status === 'approved' ? '#34D399' : app.status === 'pending' ? '#F8500A' : '#F2667A', textTransform: 'capitalize' }}>{app.status}</div>
      <div style={{ fontSize: 13, color: '#aab2c0', marginTop: 12 }}>{app.strategy} · {app.markets} · risk {app.risk_level}/10 · {app.fee_pct}% performance fee · min ${fmt(app.min_investment)}</div>
      {app.status === 'pending' && <div style={{ fontSize: 12.5, color: '#8A93A3', marginTop: 10 }}>Our team is reviewing your trading history. You'll appear on the leaderboard once approved.</div>}
      {app.status === 'approved' && <>
        <div style={{ fontSize: 12.5, color: '#34D399', marginTop: 10 }}>You're live on the leaderboard with {app.followers} copiers.</div>
        {app.earnings && (
          <div style={{ marginTop: 16 }}>
            <div style={C.lbl}>Your earnings</div>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginTop: 6 }}>
              <div style={C.earnBox}><div style={C.earnV}>${fmt(app.earnings.total)}</div><div style={C.earnL}>Total earned</div></div>
              <div style={C.earnBox}><div style={C.earnV}>${fmt(app.earnings.perf_fee)}</div><div style={C.earnL}>Performance fee ({app.earnings.fee_pct}%)</div></div>
              <div style={C.earnBox}><div style={C.earnV}>${fmt(app.earnings.commission)}</div><div style={C.earnL}>Volume commission</div></div>
            </div>
            <div style={{ fontSize: 11, color: '#8A93A3', marginTop: 8 }}>You earn a {app.earnings.fee_pct}% performance fee on profits you make your copiers (high-water mark) plus a per-lot rebate on their copied volume.</div>
          </div>
        )}
        {pd && pd.copiers && pd.copiers.length > 0 && (
          <div style={{ marginTop: 18 }}>
            <div style={C.lbl}>Your copiers ({pd.followers})</div>
            <div style={{ ...C.tableWrap, marginTop: 6 }}>
              <table style={C.table}>
                <thead><tr>{['Copier', 'Allocated', 'P/L', 'Since', 'Status'].map(h => <th key={h} style={C.th}>{h}</th>)}</tr></thead>
                <tbody>
                  {pd.copiers.slice(0, 15).map((c: any, i: number) => (
                    <tr key={i} style={C.tr}>
                      <td style={C.tdc}>{c.name}</td>
                      <td style={C.tdc}>${fmt(c.allocation)}</td>
                      <td style={{ ...C.tdc, color: pos(c.pnl), fontWeight: 700 }}>{c.pnl >= 0 ? '+' : ''}${fmt(c.pnl, 2)}</td>
                      <td style={{ ...C.tdc, color: '#8A93A3' }}>{c.since}</td>
                      <td style={C.tdc}>{c.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {pd.payouts && pd.payouts.length > 0 && (
              <div style={{ fontSize: 11.5, color: '#8A93A3', marginTop: 10 }}>
                Payouts: {pd.payouts.filter((p: any) => p.status === 'paid').length} paid, {pd.payouts.filter((p: any) => p.status === 'pending').length} pending — settled by the desk into your IB account.
              </div>
            )}
          </div>
        )}
      </>}
    </div>
  );
  return (
    <div style={C.panel}>
      <div style={{ fontSize: 17, fontWeight: 800, color: '#fff', marginBottom: 4 }}>Become a signal provider</div>
      <div style={{ fontSize: 12.5, color: '#8A93A3', marginBottom: 16 }}>Let others copy your trades and earn a performance fee on their profits.</div>
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        <div style={{ flex: 1, minWidth: 160 }}><label style={C.lbl}>Strategy</label>
          <select value={form.strategy} onChange={e => setForm({ ...form, strategy: e.target.value })} style={C.input}>
            {['Scalping', 'Intraday', 'Swing', 'News', 'Grid', 'Conservative'].map(s => <option key={s}>{s}</option>)}
          </select></div>
        <div style={{ flex: 1, minWidth: 160 }}><label style={C.lbl}>Markets</label>
          <input value={form.markets} onChange={e => setForm({ ...form, markets: e.target.value })} style={C.input} placeholder="e.g. XAUUSD, FX Majors" /></div>
      </div>
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 10 }}>
        <div style={{ width: 130 }}><label style={C.lbl}>Risk (1–10)</label><input type="number" min={1} max={10} value={form.risk_level} onChange={e => setForm({ ...form, risk_level: +e.target.value })} style={C.input} /></div>
        <div style={{ width: 130 }}><label style={C.lbl}>Fee %</label><input type="number" value={form.fee_pct} onChange={e => setForm({ ...form, fee_pct: +e.target.value })} style={C.input} /></div>
        <div style={{ width: 150 }}><label style={C.lbl}>Min investment $</label><input type="number" value={form.min_investment} onChange={e => setForm({ ...form, min_investment: +e.target.value })} style={C.input} /></div>
      </div>
      <div style={{ marginTop: 10 }}><label style={C.lbl}>Bio</label>
        <textarea value={form.bio} onChange={e => setForm({ ...form, bio: e.target.value })} style={{ ...C.input, height: 70, resize: 'vertical' }} placeholder="Describe your trading style and edge…" /></div>
      {elig && (
        <div style={{ fontSize: 12, marginTop: 12, padding: '9px 12px', borderRadius: 9,
          background: elig.eligible ? 'rgba(52,211,153,0.08)' : 'rgba(232,184,75,0.08)',
          border: `1px solid ${elig.eligible ? 'rgba(52,211,153,0.25)' : 'rgba(232,184,75,0.25)'}`,
          color: elig.eligible ? '#34D399' : '#F8500A' }}>
          {elig.eligible ? '✓ ' : '⚠ '}{elig.reason}
        </div>
      )}
      <button style={{ ...C.bigFollow, marginTop: 14, maxWidth: 220, opacity: elig && !elig.eligible ? 0.6 : 1 }} disabled={busy || (elig && !elig.eligible)} onClick={submit}>{busy ? 'Submitting…' : 'Submit application'}</button>
      {msg && <div style={{ fontSize: 12.5, color: '#F8500A', marginTop: 10 }}>{msg}</div>}
    </div>
  );
}

// ───────────────────────── notifications bell ─────────────────────────
function NotifBell() {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<any>({ notifications: [], unread: 0 });
  const load = useCallback(() => { apiGet('/portal/copy/notifications').then(setData).catch(() => {}); }, []);
  useEffect(() => { load(); }, [load]);
  const toggle = async () => {
    const next = !open; setOpen(next);
    if (next && data.unread) { await apiPost('/portal/copy/notifications/read', {}); load(); }
  };
  const icon = (t: string) => t === 'stop_loss' ? '🛑' : t === 'provider_flagged' ? '⚠️' : t === 'provider_inactive' ? '💤' : '✅';
  return (
    <div style={{ position: 'relative' }}>
      <button onClick={toggle} style={C.bell}>🔔{data.unread ? <span style={C.bellBadge}>{data.unread}</span> : null}</button>
      {open && (
        <div style={C.bellPanel}>
          <div style={{ fontSize: 13, fontWeight: 800, color: '#fff', padding: '4px 6px 10px' }}>Notifications</div>
          {(data.notifications || []).length === 0 ? <div style={{ color: '#8A93A3', fontSize: 12.5, padding: 10 }}>Nothing yet.</div> :
            (data.notifications).map((n: any) => (
              <div key={n.id} style={{ display: 'flex', gap: 9, padding: '9px 6px', borderTop: '1px solid #12161d' }}>
                <span>{icon(n.type)}</span>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 12.5, fontWeight: 700, color: '#E7ECF3' }}>{n.title}</div>
                  {n.body && <div style={{ fontSize: 11.5, color: '#8A93A3', lineHeight: 1.4 }}>{n.body}</div>}
                  <div style={{ fontSize: 10, color: '#5a6373', marginTop: 2 }}>{n.at}</div>
                </div>
              </div>
            ))}
        </div>
      )}
    </div>
  );
}

// ───────────────────────── my copies (providers + open trades) ─────────────────────────
function MyCopies({ following, onChanged, openProvider, goDiscover }: any) {
  const [sub, setSub] = useState<'providers' | 'open'>('providers');
  const [ot, setOt] = useState<any>({ trades: [], providers: [], symbols: [], total_pnl: 0 });
  const [fProv, setFProv] = useState(''); const [fSym, setFSym] = useState('');
  const [sortK, setSortK] = useState<{ k: string; dir: 1 | -1 }>({ k: 'pnl', dir: 1 });
  const [disc, setDisc] = useState<any>(null);

  const loadOpen = useCallback(() => {
    const q = new URLSearchParams({ ...(fProv ? { provider_id: fProv } : {}), ...(fSym ? { symbol: fSym } : {}) }).toString();
    apiGet(`/portal/copy/my-open-trades?${q}`).then(setOt).catch(() => {});
  }, [fProv, fSym]);
  useEffect(() => { loadOpen(); }, [loadOpen]);

  const closeOne = async (id: number) => { await apiPost(`/portal/copy/positions/${id}/close`, {}); loadOpen(); onChanged && onChanged(); };
  const doDisconnect = async (close: boolean) => {
    await apiPost('/portal/copy/unfollow', { provider_id: disc.provider_id, close_positions: close });
    setDisc(null); loadOpen(); onChanged && onChanged();
  };
  const setSort = (k: string) => setSortK(s => ({ k, dir: s.k === k ? (s.dir === 1 ? -1 : 1) : 1 }));
  const trades = [...(ot.trades || [])].sort((a, b) => {
    const av = a[sortK.k], bv = b[sortK.k];
    if (typeof av === 'string') return sortK.dir * String(av).localeCompare(String(bv));
    return sortK.dir * ((av || 0) - (bv || 0));
  });

  const list = following.following || [];
  return (
    <div>
      <div style={{ display: 'flex', gap: 10, marginBottom: 14, flexWrap: 'wrap' }}>
        <div style={C.kpi}><div style={C.kpiV}>{following.totals?.count || 0}</div><div style={C.kpiL}>Active copies</div></div>
        <div style={C.kpi}><div style={C.kpiV}>${fmt(following.totals?.allocated || 0)}</div><div style={C.kpiL}>Allocated</div></div>
        <div style={C.kpi}><div style={C.kpiV}>{ot.trades?.length || 0}</div><div style={C.kpiL}>Open copied trades</div></div>
        <div style={C.kpi}><div style={{ ...C.kpiV, color: pos(ot.total_pnl || 0) }}>{(ot.total_pnl || 0) >= 0 ? '+' : ''}${fmt(ot.total_pnl || 0, 2)}</div><div style={C.kpiL}>Open P/L</div></div>
      </div>

      <div style={{ display: 'flex', gap: 6, marginBottom: 12, flexWrap: 'wrap' }}>
        <button style={{ ...C.tab, ...(sub === 'providers' ? C.tabActive : {}) }} onClick={() => setSub('providers')}>Providers ({list.length})</button>
        <button style={{ ...C.tab, ...(sub === 'open' ? C.tabActive : {}) }} onClick={() => setSub('open')}>Open trades ({ot.trades?.length || 0})</button>
      </div>

      {sub === 'providers' && (list.length === 0 ? (
        <div style={{ ...C.panel, textAlign: 'center', color: '#8A93A3' }}>You're not copying anyone yet. Go to <b style={{ color: '#F8500A', cursor: 'pointer' }} onClick={goDiscover}>Discover</b>.</div>
      ) : (
        <div style={C.tableWrap}>
          <table style={C.table}>
            <thead><tr>{['Copied from', 'Strategy', 'Return', 'Allocated', 'My P/L', 'Fee owed', 'Open', ''].map((h, i) => <th key={i} style={C.th}>{h}</th>)}</tr></thead>
            <tbody>
              {list.map((f: any) => (
                <tr key={f.provider_id} style={C.tr}>
                  <td style={C.tdc}><span style={{ marginRight: 7 }}>{f.avatar || '📈'}</span><b style={{ cursor: 'pointer' }} onClick={() => openProvider(f.provider_id)}>{f.name}</b></td>
                  <td style={{ ...C.tdc, color: '#8A93A3' }}>{f.strategy}</td>
                  <td style={{ ...C.tdc, color: pos(f.return_pct), fontWeight: 700 }}>{f.return_pct >= 0 ? '+' : ''}{fmt(f.return_pct, 1)}%</td>
                  <td style={C.tdc}>${fmt(f.allocation)}</td>
                  <td style={{ ...C.tdc, color: pos(f.pnl), fontWeight: 700 }}>{f.pnl >= 0 ? '+' : ''}${fmt(f.pnl, 2)}</td>
                  <td style={{ ...C.tdc, color: '#F8500A' }} title="Performance fee owed to the provider (high-water mark)">${fmt(f.fee_owed || 0, 2)}</td>
                  <td style={C.tdc}>{f.open_trades || 0}</td>
                  <td style={{ ...C.tdc, textAlign: 'right' }}><button style={C.discBtn} onClick={() => setDisc(f)}>Disconnect</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}

      {sub === 'open' && (
        <div>
          <div style={{ display: 'flex', gap: 8, marginBottom: 12, flexWrap: 'wrap' }}>
            <select value={fProv} onChange={e => setFProv(e.target.value)} style={{ ...C.input, width: 'min(200px, 100%)' }}>
              <option value="">All providers</option>
              {(ot.providers || []).map((p: any) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
            <select value={fSym} onChange={e => setFSym(e.target.value)} style={{ ...C.input, width: 'min(150px, 100%)' }}>
              <option value="">All symbols</option>
              {(ot.symbols || []).map((s: string) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          {trades.length === 0 ? <div style={{ ...C.panel, textAlign: 'center', color: '#8A93A3' }}>No open copied trades.</div> : (
            <div style={C.tableWrap}>
              <table style={C.table}>
                <thead><tr>
                  {[['provider', 'Copied from'], ['symbol', 'Symbol'], ['side', 'Side'], ['lots', 'Lots'], ['pnl', 'P/L']].map(([k, l]) => (
                    <th key={k} style={{ ...C.th, cursor: 'pointer' }} onClick={() => setSort(k)}>{l}{sortK.k === k ? (sortK.dir === 1 ? ' ▲' : ' ▼') : ''}</th>
                  ))}
                  <th style={C.th}></th>
                </tr></thead>
                <tbody>
                  {trades.map((t: any) => (
                    <tr key={t.id} style={C.tr}>
                      <td style={C.tdc}><span style={{ marginRight: 6 }}>{t.avatar || '📈'}</span>{t.provider}</td>
                      <td style={{ ...C.tdc, fontWeight: 700 }}>{t.symbol}</td>
                      <td style={{ ...C.tdc, color: t.side === 'Buy' ? '#34D399' : '#F2667A' }}>{t.side}</td>
                      <td style={C.tdc}>{t.lots}</td>
                      <td style={{ ...C.tdc, color: pos(t.pnl), fontWeight: 700 }}>{t.pnl >= 0 ? '+' : ''}${fmt(t.pnl, 2)}</td>
                      <td style={{ ...C.tdc, textAlign: 'right' }}><button style={C.closeTradeBtn} onClick={() => closeOne(t.id)}>Close</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div style={{ fontSize: 11, color: '#8A93A3', marginTop: 10 }}>ⓘ Copied positions are recorded in simulation — live execution activates in an upcoming release.</div>
        </div>
      )}

      {disc && (
        <div style={C.overlay} onClick={() => setDisc(null)}>
          <div style={{ ...C.modal, width: 'min(420px, 94vw)' }} onClick={e => e.stopPropagation()}>
            <div style={{ fontSize: 16, fontWeight: 800, color: '#fff', marginBottom: 8 }}>Disconnect {disc.name}?</div>
            <div style={{ fontSize: 13, color: '#aab2c0', marginBottom: 18 }}>You have <b>{disc.open_trades || 0}</b> open copied trade(s) from this provider. What should we do with them?</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <button style={C.bigFollow} onClick={() => doDisconnect(false)}>Disconnect & keep trades open</button>
              <button style={{ ...C.ghostBtn, border: '1px solid #F2667A', color: '#F2667A' }} onClick={() => doDisconnect(true)}>Disconnect & close all trades</button>
              <button style={C.ghostBtn} onClick={() => setDisc(null)}>Cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ───────────────────────── main page ─────────────────────────
export default function CopyTrading() {
  const mobile = useIsMobile();
  const [view, setView] = useState<'discover' | 'following' | 'provider'>('discover');
  const [providers, setProviders] = useState<any[]>([]);
  const [strategies, setStrategies] = useState<string[]>([]);
  const [sort, setSort] = useState('return');
  const [strat, setStrat] = useState('');
  const [realOnly, setRealOnly] = useState(false);
  const [activeOnly, setActiveOnly] = useState(true);
  const [search, setSearch] = useState('');
  const [openId, setOpenId] = useState<number | null>(null);
  const [following, setFollowing] = useState<any>({ following: [], totals: {} });
  const [loading, setLoading] = useState(true);

  const loadBoard = useCallback(() => {
    setLoading(true);
    const q = new URLSearchParams({ sort, ...(strat ? { strategy: strat } : {}), ...(search ? { search } : {}), ...(realOnly ? { real_only: '1' } : {}), ...(activeOnly ? { active_only: '1' } : {}) }).toString();
    apiGet(`/portal/copy/providers?${q}`).then((r: any) => { setProviders(r?.providers || []); setStrategies(r?.strategies || []); }).catch(() => {}).finally(() => setLoading(false));
  }, [sort, strat, search, realOnly, activeOnly]);
  const loadFollowing = useCallback(() => { apiGet('/portal/copy/my-following').then(setFollowing).catch(() => {}); }, []);
  useEffect(() => { loadBoard(); }, [loadBoard]);
  useEffect(() => { loadFollowing(); }, [loadFollowing]);

  const quickFollow = async (p: any) => {
    if (p.following) { setOpenId(p.id); return; }
    setOpenId(p.id); // open modal to choose allocation
  };
  const refresh = () => { loadBoard(); loadFollowing(); };

  return (
    <div style={{ padding: mobile ? '14px 14px 80px' : '18px 28px 60px', maxWidth: 1036, margin: '0 auto' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 16, flexWrap: 'wrap' }}>
        <div>
          <div style={{ fontSize: mobile ? 19 : 22, fontWeight: 900, color: '#fff' }}>Copy Trading</div>
          <div style={{ fontSize: 12.5, color: '#8A93A3' }}>Follow top traders — mirror their strategy into your account.</div>
        </div>
        <div style={{ flex: 1 }} />
        <NotifBell />
        <div style={{ display: 'flex', gap: 6, background: '#0d1016', padding: 4, borderRadius: 12, border: '1px solid #1A1F2B', maxWidth: '100%', overflowX: 'auto', flex: mobile ? '1 1 100%' : undefined }}>
          {[['discover', 'Discover'], ['following', `My Copies${following.totals?.count ? ` (${following.totals.count})` : ''}`], ['provider', 'Become a Provider']].map(([k, l]: any) => (
            <button key={k} onClick={() => setView(k)} style={{ ...C.viewTab, ...(view === k ? C.viewTabActive : {}) }}>{l}</button>
          ))}
        </div>
      </div>

      {view === 'discover' && <>
        <div style={{ display: 'flex', gap: 8, marginBottom: 14, flexWrap: 'wrap', alignItems: 'center' }}>
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search trader…" style={{ ...C.input, width: 'min(180px, 100%)', flex: mobile ? '1 1 100%' : undefined }} />
          <select value={sort} onChange={e => setSort(e.target.value)} style={{ ...C.input, width: 'min(160px, 100%)' }}>
            <option value="return">Top return</option>
            <option value="winrate">Best win rate</option>
            <option value="followers">Most copied</option>
            <option value="drawdown">Lowest drawdown</option>
            <option value="risk">Lowest risk</option>
            <option value="new">Newest</option>
          </select>
          <button style={{ ...C.chip, ...(realOnly ? C.realChipActive : {}) }} onClick={() => setRealOnly(v => !v)}>✓ Real traders</button>
          <button style={{ ...C.chip, ...(activeOnly ? C.realChipActive : {}) }} onClick={() => setActiveOnly(v => !v)}>{activeOnly ? '🟢 Active only' : 'Show inactive'}</button>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            <button style={{ ...C.chip, ...(strat === '' ? C.chipActive : {}) }} onClick={() => setStrat('')}>All</button>
            {strategies.map(s => <button key={s} style={{ ...C.chip, ...(strat === s ? C.chipActive : {}) }} onClick={() => setStrat(s)}>{s}</button>)}
          </div>
        </div>
        {loading ? <div style={{ color: '#8A93A3', padding: 30 }}>Loading providers…</div> :
          <div style={C.grid}>
            {providers.map(p => <ProviderCard key={p.id} p={p} onOpen={setOpenId} onFollow={quickFollow} />)}
          </div>}
      </>}

      {view === 'following' && <MyCopies following={following} onChanged={refresh} openProvider={setOpenId} goDiscover={() => setView('discover')} />}

      {view === 'provider' && <BecomeProvider />}

      {openId && <DetailModal id={openId} onClose={() => setOpenId(null)} onChanged={refresh} />}
    </div>
  );
}

const C: any = {
  grid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 14 },
  card: { background: '#0d1016', border: '1px solid #1A1F2B', borderRadius: 16, padding: 16, cursor: 'pointer', transition: 'border .15s' },
  avatar: { width: 42, height: 42, borderRadius: 12, background: 'linear-gradient(135deg,#1c2330,#11151d)', border: '1px solid #2a3240', display: 'grid', placeItems: 'center', fontSize: 20, flex: '0 0 auto' },
  featBadge: { color: '#F8500A', fontSize: 11 },
  realBadge: { fontSize: 8.5, fontWeight: 900, letterSpacing: '0.04em', color: '#0B0E14', background: '#34D399', borderRadius: 4, padding: '2px 5px' },
  inactiveBadge: { fontSize: 8.5, fontWeight: 900, letterSpacing: '0.04em', color: '#0B0E14', background: '#8A93A3', borderRadius: 4, padding: '2px 5px' },
  realChipActive: { background: 'rgba(52,211,153,0.16)', borderColor: 'rgba(52,211,153,0.45)', color: '#34D399' },
  followBtn: { width: '100%', marginTop: 12, padding: '9px', borderRadius: 10, background: 'linear-gradient(90deg,#F8500A,#FF7A1A)', color: '#0B0E14', border: 'none', fontWeight: 800, fontSize: 13, cursor: 'pointer' },
  followingBtn: { background: 'transparent', border: '1px solid #34D399', color: '#34D399' },
  // modal
  overlay: { position: 'fixed', inset: 0, background: 'rgba(5,7,11,0.72)', backdropFilter: 'blur(3px)', zIndex: 100, display: 'flex', alignItems: 'flex-start', justifyContent: 'center', overflowY: 'auto', padding: '40px 16px' },
  modal: { position: 'relative', width: 'min(680px, 94vw)', maxWidth: '100%', background: '#0d1016', border: '1px solid #232a38', borderRadius: 20, padding: 24, boxShadow: '0 40px 100px -30px #000' },
  close: { position: 'absolute', top: 14, right: 14, width: 30, height: 30, borderRadius: 8, background: '#161b25', border: '1px solid #2a3240', color: '#E7ECF3', cursor: 'pointer', fontSize: 13 },
  statBox: { flex: '1 0 70px', background: '#0B0E14', border: '1px solid #1A1F2B', borderRadius: 10, padding: '9px 6px', textAlign: 'center' },
  statLbl: { fontSize: 9, color: '#8A93A3', textTransform: 'uppercase', letterSpacing: '0.05em', marginTop: 2 },
  followingNote: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, background: 'rgba(52,211,153,0.08)', border: '1px solid rgba(52,211,153,0.25)', borderRadius: 12, padding: '11px 14px', fontSize: 12.5, color: '#aab2c0', flexWrap: 'wrap' },
  stopBtn: { padding: '7px 13px', borderRadius: 8, background: 'transparent', border: '1px solid #F2667A', color: '#F2667A', cursor: 'pointer', fontSize: 12, fontWeight: 700 },
  bigFollow: { padding: '12px 22px', borderRadius: 11, background: 'linear-gradient(90deg,#F8500A,#FF7A1A)', color: '#0B0E14', border: 'none', fontWeight: 800, fontSize: 14, cursor: 'pointer' },
  ghostBtn: { padding: '12px 18px', borderRadius: 11, background: 'transparent', border: '1px solid #2a3240', color: '#E7ECF3', cursor: 'pointer', fontSize: 13 },
  followForm: { background: '#0B0E14', border: '1px solid #1A1F2B', borderRadius: 12, padding: 14, marginTop: 4 },
  optBtn: { padding: '8px 12px', borderRadius: 8, background: '#0d1016', border: '1px solid #2a3240', color: '#9aa3b3', fontSize: 12, fontWeight: 600, cursor: 'pointer' },
  optBtnActive: { background: 'rgba(232,184,75,0.14)', borderColor: 'rgba(232,184,75,0.45)', color: '#F8500A' },
  lbl: { fontSize: 10.5, color: '#8A93A3', textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 700, display: 'block', marginBottom: 5 },
  input: { width: '100%', padding: '10px 12px', borderRadius: 9, background: '#0d1016', border: '1px solid #2a3240', color: '#fff', fontSize: 13.5, outline: 'none', boxSizing: 'border-box' },
  tab: { padding: '7px 14px', borderRadius: 8, background: 'transparent', border: '1px solid #1A1F2B', color: '#9aa3b3', fontSize: 12.5, fontWeight: 600, cursor: 'pointer' },
  tabActive: { background: '#161b25', color: '#fff', borderColor: '#2a3240' },
  tradeRow: { display: 'flex', alignItems: 'center', gap: 8, padding: '9px 4px', borderBottom: '1px solid #12161d', fontSize: 12.5, minWidth: 280 },
  viewTab: { padding: '8px 15px', borderRadius: 9, background: 'transparent', border: 'none', color: '#9aa3b3', fontSize: 12.5, fontWeight: 700, cursor: 'pointer' },
  viewTabActive: { background: 'linear-gradient(90deg, rgba(232,184,75,0.16), rgba(232,184,75,0.05))', color: '#fff' },
  chip: { padding: '7px 12px', borderRadius: 99, background: '#0d1016', border: '1px solid #1A1F2B', color: '#9aa3b3', fontSize: 12, cursor: 'pointer' },
  chipActive: { background: 'rgba(232,184,75,0.14)', borderColor: 'rgba(232,184,75,0.4)', color: '#F8500A' },
  panel: { background: '#0d1016', border: '1px solid #1A1F2B', borderRadius: 16, padding: 22, maxWidth: 640 },
  earnBox: { flex: 1, minWidth: 130, background: '#0B0E14', border: '1px solid #1A1F2B', borderRadius: 10, padding: '12px 14px' },
  earnV: { fontSize: 18, fontWeight: 900, color: '#34D399' },
  earnL: { fontSize: 10.5, color: '#8A93A3', marginTop: 2 },
  kpi: { flex: 1, minWidth: 140, background: '#0d1016', border: '1px solid #1A1F2B', borderRadius: 14, padding: '14px 16px' },
  kpiV: { fontSize: 20, fontWeight: 900, color: '#fff' },
  kpiL: { fontSize: 11, color: '#8A93A3', marginTop: 2 },
  followRow: { display: 'flex', alignItems: 'center', gap: 14, background: '#0d1016', border: '1px solid #1A1F2B', borderRadius: 14, padding: '12px 16px', marginBottom: 10, cursor: 'pointer' },
  tableWrap: { background: '#0d1016', border: '1px solid #1A1F2B', borderRadius: 14, overflowX: 'auto' },
  table: { width: '100%', minWidth: 560, borderCollapse: 'collapse', fontSize: 13 },
  th: { textAlign: 'left', padding: '11px 13px', fontSize: 10.5, textTransform: 'uppercase', letterSpacing: '0.05em', color: '#8A93A3', background: '#0B0E14', userSelect: 'none' },
  tr: { borderTop: '1px solid #12161d' },
  tdc: { padding: '11px 13px', color: '#E7ECF3', verticalAlign: 'middle' },
  discBtn: { padding: '6px 12px', borderRadius: 8, background: 'transparent', border: '1px solid #2a3240', color: '#9aa3b3', cursor: 'pointer', fontSize: 12, fontWeight: 700 },
  closeTradeBtn: { padding: '5px 12px', borderRadius: 7, background: 'rgba(242,102,122,0.1)', border: '1px solid rgba(242,102,122,0.4)', color: '#F2667A', cursor: 'pointer', fontSize: 12, fontWeight: 700 },
  bell: { position: 'relative', background: '#0d1016', border: '1px solid #1A1F2B', borderRadius: 10, padding: '8px 11px', fontSize: 15, cursor: 'pointer' },
  bellBadge: { position: 'absolute', top: -5, right: -5, background: '#F2667A', color: '#fff', borderRadius: 99, fontSize: 9.5, fontWeight: 900, padding: '1px 5px' },
  bellPanel: { position: 'absolute', top: 44, right: 0, width: 'min(320px, 86vw)', maxHeight: 400, overflowY: 'auto', background: '#0d1016', border: '1px solid #232a38', borderRadius: 14, padding: 10, zIndex: 60, boxShadow: '0 20px 50px -20px #000' },
};

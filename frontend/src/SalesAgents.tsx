import React, { useState, useEffect, useCallback, useRef } from 'react';
import { createPortal } from 'react-dom';
import { apiGet, apiPost } from './api';
import TransferModal from './TransferModal';
import { CT } from './crmTable';

const fmtUSD = (n: number) => '$' + Math.round(n || 0).toLocaleString('en-GB');
const fmtNum = (n: number) => (n || 0).toLocaleString('en-GB');

const PERIODS: [string, string][] = [
  ['today', 'Today'], ['yesterday', 'Yesterday'], ['this_week', 'This week'], ['last_week', 'Last week'],
  ['last_7_days', 'Last 7 days'], ['this_month', 'This month'], ['last_month', 'Last month'],
  ['last_30_days', 'Last 30 days'], ['this_year', 'This year'], ['last_year', 'Last year'], ['all_time', 'All time'],
];
const GROUPS: [string, string][] = [
  ['', 'All'], ['retention', 'Retention'], ['sales', 'Sales'], ['team_leader', 'Team leaders'],
];

const th: React.CSSProperties = {
  padding: '9px 11px', textAlign: 'left', color: '#667', fontWeight: 600, fontSize: 10,
  textTransform: 'uppercase', letterSpacing: .4, borderBottom: '1px solid #373f4d',
  whiteSpace: 'nowrap', cursor: 'pointer', position: 'sticky', top: 0, background: '#262c36', userSelect: 'none',
};
const td: React.CSSProperties = { padding: '9px 11px', borderBottom: '1px solid #2c333e', fontSize: 12, whiteSpace: 'nowrap' };

function Kpi({ label, value, c, hint }: any) {
  return (
    <div style={{ background: '#2c333e', border: '1px solid #373f4d', borderRadius: 10, padding: '9px 13px' }}>
      <div style={{ fontSize: 9, color: '#556', textTransform: 'uppercase', letterSpacing: .5, marginBottom: 3 }}>{label}</div>
      <div style={{ fontSize: 18, fontWeight: 700, color: c }}>{value}</div>
      {hint && <div style={{ fontSize: 9, color: '#667', marginTop: 2 }}>{hint}</div>}
    </div>
  );
}

const ROLE_COLOR: Record<string, string> = { 'Team Leader': '#cc88ff', 'Sales Manager': '#ffaa00', 'Sales Agent': '#00aaff' };

// Everyone sees full numbers now (blur removed). Only MANAGEMENT may EDIT the rate/target.
const MGMT_ROLES = ['super_admin', 'admin', 'director', 'sales_manager'];
const isMgmt = () => MGMT_ROLES.includes(localStorage.getItem('userRole') || '');
// Only admins & Rahaf may move records between agents (bulk transfer / resolve requests) — Jul 2026.
const canReassignAgent = () => localStorage.getItem('canReassign') === '1';

const UIFONT = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif';
// (i) info bubble — the popover is PORTALED to <body> with fixed positioning so it never gets
// clipped by the drawer's overflow or hidden behind the sidebar.
function Info({ text }: { text: string }) {
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null);
  const ref = useRef<HTMLSpanElement>(null);
  const show = () => { const r = ref.current?.getBoundingClientRect(); if (r) setPos({ x: r.left + r.width / 2, y: r.top }); };
  return (
    <span ref={ref} style={{ display: 'inline-flex', verticalAlign: 'middle' }}
      onMouseEnter={show} onMouseLeave={() => setPos(null)}>
      <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 15, height: 15,
        borderRadius: '50%', background: pos ? '#00e5a0' : '#3a4150', color: pos ? '#0a0c10' : '#c3cad6',
        fontSize: 10, fontWeight: 700, fontStyle: 'italic', fontFamily: 'Georgia, serif', cursor: 'help', marginLeft: 5, transition: 'all .12s' }}>i</span>
      {pos && createPortal(
        <span style={{ position: 'fixed', left: pos.x, top: pos.y - 10, transform: 'translate(-50%,-100%)', zIndex: 2147483647,
          width: 280, maxWidth: '90vw', background: 'linear-gradient(180deg,#242b36,#1b212b)', border: '1px solid #3f4a5a', borderRadius: 10,
          padding: '11px 13px', fontFamily: UIFONT, fontSize: 12, lineHeight: 1.55, color: '#dce3ec', fontWeight: 400,
          letterSpacing: .1, boxShadow: '0 10px 30px rgba(0,0,0,0.55)', whiteSpace: 'normal', textTransform: 'none', pointerEvents: 'none' }}>
          {text}
          <span style={{ position: 'absolute', top: '100%', left: '50%', transform: 'translateX(-50%)', width: 0, height: 0,
            borderLeft: '6px solid transparent', borderRight: '6px solid transparent', borderTop: '6px solid #1b212b' }} />
        </span>, document.body)}
    </span>
  );
}

// Score pill (0-100 performance) coloured by band
function ScorePill({ pct, demo }: { pct: number; demo?: boolean }) {
  const c = pct >= 85 ? '#00e5a0' : pct >= 70 ? '#ffd166' : pct >= 50 ? '#ffaa00' : '#ff5d6c';
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
      <span style={{ color: c, fontWeight: 800 }}>{Math.round(pct)}%</span>
      {demo && <span style={{ fontSize: 8, color: '#ffaa00', border: '1px solid #ffaa0055', borderRadius: 4, padding: '0 3px' }}>DEMO</span>}
    </span>
  );
}
const MARKUP_INFO = 'Company markup for a RETENTION agent counts the profit their clients’ trades made — but only trades they’re entitled to: for their OWN clients and their OWN IBs, from the first trade (D1); for clients transferred from sales, only from the 2nd deposit (D2). If D2 happened but no call was logged, it counts only from the 3rd deposit (D3). Credit trades are excluded.';
const IBCOMM_INFO = 'IB commission we count = commission paid to IBs on ANY trading account under an IB — regardless of whether that IB belongs to this agent — over the period. Credit trades are excluded. It is deducted from the company markup to get the net.';
const PERF_INFO = 'Monthly performance score (0-100%). Weighted: own new clients brought (target 5) 30%, active IBs (target 3) 30%, successful calls ≥80s (target 1000) 30%, Call-QA score 10%. Eligible commission = commission × this score. THIS MONTH is a demo value (70-85%) — goes live next month.';

// ── FTD / NDA drill-down: which customers, and WHY a first-deposit is not an NDA ──────────
function FTDModal({ agent, period, cFrom, cTo, onClose }: any) {
  const [d, setD] = useState<any>(null);
  useEffect(() => {
    const extra = period === 'custom' && cFrom && cTo ? `&date_from=${cFrom}&date_to=${cTo}` : '';
    apiGet(`/agents/${agent.id}/ftd-detail?period=${period}${extra}`).then(setD).catch(() => setD({ ftds: [] }));
  }, [agent.id, period, cFrom, cTo]);
  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', zIndex: 9600, display: 'flex', justifyContent: 'center', alignItems: 'flex-start', overflow: 'auto', padding: '30px 12px' }} onClick={onClose}>
      <div onClick={e => e.stopPropagation()} style={{ width: 860, maxWidth: '96vw', background: '#20252f', border: '1px solid #373f4d', borderRadius: 14, padding: 20 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
          <div style={{ fontSize: 16, fontWeight: 800, color: '#e6e9ef' }}>💧 First-time deposits — {agent.name}</div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#889', fontSize: 20, cursor: 'pointer' }}>✕</button>
        </div>
        {!d ? <div style={{ color: '#667', padding: 24 }}>Loading…</div> : (
          <>
            <div style={{ fontSize: 11, color: '#889', marginBottom: 12 }}>
              {d.period?.from} → {d.period?.to} · <b style={{ color: '#00aaff' }}>{d.ftd} FTD</b> · <b style={{ color: '#ffd166' }}>{d.nda} new clients</b> (these pay the unit bonus) · <b style={{ color: '#ff8c00' }}>{(d.ftd || 0) - (d.nda || 0)} related</b> — the relation that disqualified each is shown below
            </div>
            {(d.ftds || []).length === 0 && <div style={{ color: '#667', padding: 16 }}>No first-time deposits in this period.</div>}
            {(d.ftds || []).map((x: any, i: number) => (
              <div key={i} style={{ border: '1px solid #373f4d', borderRadius: 10, padding: '10px 13px', marginBottom: 8, background: x.is_nda ? 'rgba(0,229,160,0.05)' : 'rgba(255,140,0,0.05)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                  <span style={{ fontWeight: 700, color: '#e6e9ef' }}>{x.name || `#${x.login}`}</span>
                  <span style={{ fontSize: 11, color: '#889' }}>login {x.login}</span>
                  <span style={{ fontSize: 11, color: '#889' }}>{x.ftd_date}</span>
                  <span style={{ fontSize: 12, color: '#00e5a0', fontWeight: 600 }}>${Math.round(x.ftd_amount).toLocaleString('en-GB')}</span>
                  <span style={{ marginLeft: 'auto', fontSize: 11, fontWeight: 800, padding: '2px 10px', borderRadius: 99,
                    background: x.is_nda ? 'rgba(0,229,160,0.15)' : 'rgba(255,140,0,0.15)', color: x.is_nda ? '#00e5a0' : '#ff8c00' }}>
                    {x.is_nda ? '🟢 New Client' : '🔴 Related — not counted'}
                  </span>
                </div>
                {!x.is_nda && (
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 8 }}>
                    {(x.reasons || []).length === 0 && <span style={{ fontSize: 11, color: '#889' }}>related via an indirect/older signal (no direct match found now)</span>}
                    {(x.reasons || []).map((r: any, j: number) => (
                      <span key={j} title={r.value || ''} style={{ fontSize: 11, padding: '3px 9px', borderRadius: 99, background: '#2c333e', border: '1px solid #3a4150', color: '#ffaa66' }}>
                        {r.type}{r.other_name ? <> → <b style={{ color: '#e6e9ef' }}>{r.other_name}</b> <span style={{ color: '#667' }}>({r.other_login})</span></> : (r.value ? ` ${r.value}` : '')}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  );
}

// ── Per-agent detail drawer ──────────────────────────────────────────────────
function AgentDetail({ agentId, period, onClose, startWide, hideCollapse }: { agentId: number; period: string; onClose: () => void; startWide?: boolean; hideCollapse?: boolean }) {
  const mgmt = isMgmt();
  const [d, setD] = useState<any>(null);
  const [tgt, setTgt] = useState('');
  const [pct, setPct] = useState('');
  const [saving, setSaving] = useState(false);
  const [wide, setWide] = useState(!!startWide);   // "More details" → full-page view
  const [lp, setLp] = useState(period);            // the full-page view gets its own period
  const [calcAgent, setCalcAgent] = useState<any>(null);     // markup calculator modal
  const [funnelAgent, setFunnelAgent] = useState<any>(null); // sales leads funnel modal
  const [rulesAgent, setRulesAgent] = useState(false);       // individual scoring editor

  const load = useCallback(() => {
    apiGet(`/agents/${agentId}?period=${lp}`).then((x: any) => {
      setD(x); setTgt(String(x.sales_target || 0)); setPct(String(x.commission_pct || 10));
    }).catch(() => setD((d: any) => d || { error: true }));
  }, [agentId, lp]);
  useEffect(() => { load(); }, [load]);

  const save = async () => {
    setSaving(true);
    try {
      await apiPost(`/agents/${agentId}/settings`, { commission_pct: parseFloat(pct) || 0, sales_target: parseFloat(tgt) || 0 });
      await load();
    } catch (e: any) {
      alert('Save failed: ' + (e?.message || 'error'));
    } finally { setSaving(false); }
  };

  const k = d?.kpis || {};
  const tile = (label: string, value: any, c = '#e6e9ef', hint = '') => (
    <div style={{ background: '#262c36', border: '1px solid #373f4d', borderRadius: 9, padding: '10px 12px' }}>
      <div style={{ fontSize: 9, color: '#667', textTransform: 'uppercase', letterSpacing: .4, marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 17, fontWeight: 700, color: c }}>{value}</div>
      {hint && <div style={{ fontSize: 9, color: '#667', marginTop: 2 }}>{hint}</div>}
    </div>
  );
  const tileInfo = (label: string, value: any, c: string, info: string, hint = '') => (
    <div style={{ background: '#262c36', border: '1px solid #373f4d', borderRadius: 9, padding: '10px 12px' }}>
      <div style={{ fontSize: 9, color: '#667', textTransform: 'uppercase', letterSpacing: .4, marginBottom: 4, display: 'flex', alignItems: 'center' }}>{label}<Info text={info} /></div>
      <div style={{ fontSize: 17, fontWeight: 700, color: c }}>{value}</div>
      {hint && <div style={{ fontSize: 9, color: '#667', marginTop: 2 }}>{hint}</div>}
    </div>
  );
  const drillBtn: React.CSSProperties = { background: '#2c333e', border: '1px solid #3a4150', color: '#00e5a0', borderRadius: 7, padding: '5px 11px', fontSize: 11, fontWeight: 600, cursor: 'pointer', whiteSpace: 'nowrap' };

  // "More details" (wide) renders CONTAINED inside the page content box (absolute over the
  // SalesAgents root, which is position:relative) so it never covers the sidebar/top bar.
  // The narrow drawer stays a fixed slide-in from the right.
  const outer: React.CSSProperties = wide
    ? { position: 'absolute', inset: 0, background: '#20252f', zIndex: 40, overflowY: 'auto' }
    : { position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', zIndex: 9000 };
  return (
    <div style={outer} onClick={wide ? undefined : onClose}>
      <div onClick={e => e.stopPropagation()} style={wide
        ? { minHeight: '100%', background: '#20252f', padding: '20px 30px' }
        : { position: 'absolute', top: 0, right: 0, bottom: 0, left: 'auto', width: 600, maxWidth: '94vw',
            background: '#20252f', borderLeft: '1px solid #373f4d', boxShadow: '-10px 0 40px rgba(0,0,0,0.6)', overflowY: 'auto', padding: 20 }}>
        {!d ? <div style={{ color: '#667', padding: 30 }}>Loading…</div> : (
          <>
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 4 }}>
              <div>
                <div style={{ fontSize: 19, fontWeight: 700, color: '#e6e9ef' }}>{d.name}</div>
                <div style={{ fontSize: 11, color: ROLE_COLOR[d.role] || '#889' }}>{d.role}{d.team_type ? ` · ${d.team_type}` : ''}{d.extension ? ` · ext ${d.extension}` : ''}</div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                {!hideCollapse && <button onClick={() => setWide(w => !w)} title="Full sales-agent page"
                  style={{ background: '#2c333e', border: '1px solid #373f4d', color: '#9aa3b2', fontSize: 11, fontWeight: 600, padding: '5px 11px', borderRadius: 7, cursor: 'pointer', whiteSpace: 'nowrap' }}>
                  {wide ? '⤡ Collapse' : '⤢ More details'}
                </button>}
                {!hideCollapse && <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#889', fontSize: 22, cursor: 'pointer' }}>✕</button>}
              </div>
            </div>
            {wide && (
              <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap', margin: '12px 0 4px' }}>
                {PERIODS.map(([v, l]) => (
                  <button key={v} onClick={() => setLp(v)}
                    style={{ padding: '4px 11px', borderRadius: 6, fontSize: 11, cursor: 'pointer', fontFamily: 'inherit',
                      border: `1px solid ${lp === v ? '#00e5a0' : '#2a2f3a'}`, background: lp === v ? 'rgba(0,229,160,0.1)' : 'transparent', color: lp === v ? '#00e5a0' : '#889' }}>{l}</button>
                ))}
              </div>
            )}
            <div style={{ marginBottom: 12 }} />

            {/* Commission summary — TWO MODULES: sales = per-unit funnel, retention/TL = markup.
                Everyone sees the numbers. Score & Eligible commission on the right. */}
            <div style={{ fontSize: 11, color: '#889', fontWeight: 600, textTransform: 'uppercase', letterSpacing: .5, marginBottom: 8 }}>💰 Commission (this period)</div>
            {d.team_type === 'sales' ? (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7,1fr)', gap: 8, marginBottom: 12 }}>
                {tile('Leads', fmtNum(k.own_leads), '#cc88ff', 'assigned to him')}
                {tile('Own leads', fmtNum(k.own_added), '#cc88ff', 'added by himself')}
                {tile('Verified', fmtNum(k.verified_leads), '#00e5a0', 'KYC verified')}
                {tile('Converted', fmtNum(k.converted), '#00aaff', 'deposited (D1)')}
                {tile('New clients', fmtNum(k.unit_nda), '#ffd166', `× $${k.unit_rate ?? 10}`)}
                {tile('Commission', fmtUSD(k.sales_commission), '#cc88ff', `${k.unit_nda ?? 0} new clients × $${k.unit_rate ?? 10}`)}
                {tileInfo('Eligible', fmtUSD(k.eligible_commission), '#00e5a0', PERF_INFO, `commission × ${Math.round(k.performance || 0)}%`)}
              </div>
            ) : (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5,1fr)', gap: 8, marginBottom: 12 }}>
                {tileInfo('Company markup', fmtUSD(k.markup), '#00e5a0', MARKUP_INFO, 'entitled trades only')}
                {tileInfo('Paid to IBs', fmtUSD(k.ib_commission), '#ff8c00', IBCOMM_INFO, 'trading under IBs')}
                {tile('Net (markup − IB)', fmtUSD(k.net_commission), '#00aaff')}
                {tile(`Commission (${d.commission_pct}%)`, fmtUSD(k.sales_commission), '#cc88ff', 'of net markup')}
                {tileInfo('Eligible', fmtUSD(k.eligible_commission), '#00e5a0', PERF_INFO, `commission × ${Math.round(k.performance || 0)}%`)}
              </div>
            )}

            {/* Performance + (retention → Unit rate $10 · sales → Commission target) in ONE row */}
            <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr', gap: 12, marginBottom: 16 }}>
              {/* left: performance */}
              <div style={{ background: '#262c36', border: '1px solid #373f4d', borderRadius: 10, padding: '10px 14px', display: 'flex', flexDirection: 'column', gap: 8 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: '#e6e9ef', display: 'flex', alignItems: 'center' }}>Performance <Info text={PERF_INFO} /></div>
                  <ScorePill pct={k.performance || 0} demo={k.perf_demo} />
                  <div style={{ marginLeft: 'auto', display: 'flex', gap: 6 }}>
                    {mgmt && <button onClick={() => setRulesAgent(true)} style={drillBtn}>⚙ Scoring</button>}
                    {d.team_type === 'sales'
                      ? <button onClick={() => setFunnelAgent({ id: d.id, name: d.name })} style={drillBtn}>📋 Funnel</button>
                      : <button onClick={() => setCalcAgent({ id: d.id, name: d.name })} style={drillBtn}>📊 Markup</button>}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', fontSize: 10 }}>
                  {(k.perf_breakdown || []).map((b: any, i: number) => (
                    <span key={i} title={`${b.actual} / ${b.target} — ${b.points} of ${b.weight} pts`}
                      style={{ padding: '2px 7px', borderRadius: 99, background: '#1a1f28', border: '1px solid #333b48', color: '#9aa3b2' }}>
                      {b.label}: <b style={{ color: '#e6e9ef' }}>{b.actual}</b>/{b.target}
                    </span>
                  ))}
                </div>
              </div>
              {/* right: retention/lead → Unit rate; sales → commission target editor */}
              <div style={{ background: '#262c36', border: '1px solid #373f4d', borderRadius: 10, padding: '10px 14px' }}>
                {d.team_type !== 'sales' ? (
                  <div style={{ display: 'flex', flexDirection: 'column', height: '100%', justifyContent: 'center' }}>
                    <div style={{ fontSize: 11, color: '#889', marginBottom: 4 }}>Unit rate</div>
                    <div style={{ fontSize: 22, fontWeight: 800, color: '#ffd166' }}>${k.unit_rate ?? 10}</div>
                  </div>
                ) : (
                  <>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                      <div style={{ fontSize: 12, fontWeight: 600, color: '#e6e9ef' }}>🎯 Commission target</div>
                      {mgmt && <button onClick={save} disabled={saving} style={{ padding: '4px 10px', background: '#00e5a0', border: 'none', borderRadius: 6, color: '#0a0c10', fontWeight: 700, fontSize: 11, cursor: 'pointer' }}>{saving ? '…' : 'Save'}</button>}
                    </div>
                    {mgmt && (
                      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
                        <span style={{ fontSize: 10, color: '#667' }}>Rate %</span>
                        <input value={pct} onChange={e => setPct(e.target.value.replace(/[^0-9.]/g, ''))} style={{ width: 46, padding: '4px 6px', background: '#11141a', border: '1px solid #2a3142', borderRadius: 6, color: '#e0e0e0', fontSize: 12 }} />
                        <span style={{ fontSize: 10, color: '#667' }}>Target $</span>
                        <input value={tgt} onChange={e => setTgt(e.target.value.replace(/[^0-9.]/g, ''))} style={{ width: 72, padding: '4px 6px', background: '#11141a', border: '1px solid #2a3142', borderRadius: 6, color: '#e0e0e0', fontSize: 12 }} />
                      </div>
                    )}
                    {k.target > 0 ? (
                      <>
                        <div style={{ height: 8, background: '#11141a', borderRadius: 4, overflow: 'hidden', marginBottom: 6 }}>
                          <div style={{ height: '100%', width: `${Math.min(100, k.target_pct)}%`, background: k.target_pct >= 100 ? '#00e5a0' : '#00aaff', borderRadius: 4 }} />
                        </div>
                        <div style={{ fontSize: 10.5, color: '#9aa3b2' }}><span style={{ color: '#00e5a0', fontWeight: 700 }}>{fmtUSD(k.target_done)}</span> / {fmtUSD(k.target)} ({k.target_pct}%)</div>
                      </>
                    ) : <div style={{ fontSize: 11, color: '#667' }}>No target set.</div>}
                  </>
                )}
              </div>
            </div>

            {/* Activity KPIs */}
            <div style={{ fontSize: 11, color: '#889', fontWeight: 600, textTransform: 'uppercase', letterSpacing: .5, marginBottom: 8 }}>📊 Activity</div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 8, marginBottom: 16 }}>
              {tile('Calls', fmtNum(k.calls), '#00aaff')}
              {tile('Active traders', fmtNum(k.active_traders), '#00e5a0', 'made a deposit')}
              {tile('Clients', fmtNum(k.clients), '#00aaff')}
              {tile('Own clients', fmtNum(k.own_clients), '#cc88ff', 'from his leads')}
              {tile('Leads', fmtNum(k.leads), '#cc88ff')}
              {tile('Verified leads', fmtNum(k.verified_leads), '#9aa3b2')}
              {tile('Own leads', fmtNum(k.own_leads), '#cc88ff', 'assigned to him')}
              {tile('IBs', fmtNum(k.ibs), '#ffaa00', `${fmtNum(k.active_ibs)} active`)}
              {tile('Deposits', fmtUSD(k.deposits), '#00e5a0')}
              {tile('Withdrawals', fmtUSD(k.withdrawals), '#ff5d6c')}
              {tile('Net deposit', fmtUSD(k.net_deposit), k.net_deposit >= 0 ? '#00e5a0' : '#ff5d6c')}
              {tile('Volume', fmtNum(Math.round(k.lots)) + ' lots', '#cc88ff')}
            </div>

            {/* Top clients by company profit */}
            <div style={{ fontSize: 11, color: '#889', fontWeight: 600, textTransform: 'uppercase', letterSpacing: .5, marginBottom: 8 }}>🏆 Top clients by company markup</div>
            <div style={{ background: '#0a0c10', border: '1px solid #373f4d', borderRadius: 10, overflow: 'hidden' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11.5, background: '#0a0c10' }}>
                <thead><tr>{['Client', 'Lots', 'Trades', 'Company markup'].map(h => <th key={h} style={{ ...th, position: 'static' }}>{h}</th>)}</tr></thead>
                <tbody>
                  {(d.top_clients || []).length === 0 ? <tr><td colSpan={4} style={{ padding: 20, textAlign: 'center', color: '#556', background: '#0a0c10' }}>No trades in period</td></tr>
                    : d.top_clients.map((c: any, i: number) => (
                      <tr key={i} style={{ background: '#0a0c10' }}>
                        <td style={{ ...td, borderColor: '#1c2129' }}><span style={{ fontFamily: 'monospace', color: '#00aaff' }}>#{c.login}</span> <span style={{ color: '#cfd6e0' }}>{c.name}</span></td>
                        <td style={{ ...td, color: '#9aa3b2', borderColor: '#1c2129' }}>{fmtNum(Math.round(c.lots))}</td>
                        <td style={{ ...td, color: '#9aa3b2', borderColor: '#1c2129' }}>{fmtNum(c.trades)}</td>
                        <td style={{ ...td, color: '#00e5a0', fontWeight: 600, borderColor: '#1c2129' }}>{fmtUSD(c.markup)}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
      {calcAgent && <MarkupCalcModal agent={calcAgent} period={lp} onClose={() => setCalcAgent(null)} />}
      {funnelAgent && <FunnelModal agent={funnelAgent} period={lp} onClose={() => setFunnelAgent(null)} />}
      {rulesAgent && d && <AgentScoringModal agentId={d.id} name={d.name} onClose={() => setRulesAgent(false)} onSaved={load} />}
    </div>
  );
}

// ── Individual per-agent scoring override (wins over the team general rule) ───────────────────
function AgentScoringModal({ agentId, name, onClose, onSaved }: any) {
  const [d, setD] = useState<any>(null);
  const [vals, setVals] = useState<any>({});
  const [saving, setSaving] = useState(false);
  useEffect(() => { apiGet(`/agents/${agentId}/scoring-rules`).then((x: any) => { setD(x); setVals(x.overrides || {}); }).catch(() => setD({})); }, [agentId]);
  const FIELDS: [string, string][] = [['perf_w_nda', 'New-client weight %'], ['perf_t_nda', 'New-client target'], ['perf_w_ib', 'IB weight %'], ['perf_t_ib', 'IB target'], ['perf_w_calls', 'Calls weight %'], ['perf_t_calls', 'Calls target'], ['perf_w_qa', 'QA weight %']];
  const inp: React.CSSProperties = { width: 70, padding: '5px 7px', background: '#11141a', border: '1px solid #2a3142', borderRadius: 6, color: '#e0e0e0', fontSize: 12, outline: 'none' };
  const save = async () => {
    setSaving(true);
    try { await apiPost(`/agents/${agentId}/scoring-rules`, vals); onSaved && onSaved(); onClose(); }
    catch (e: any) { alert('Save failed: ' + (e?.message || 'error')); } finally { setSaving(false); }
  };
  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', zIndex: 9800, display: 'flex', justifyContent: 'center', alignItems: 'flex-start', overflow: 'auto', padding: '50px 12px' }} onClick={onClose}>
      <div onClick={e => e.stopPropagation()} style={{ width: 480, maxWidth: '96vw', background: '#20252f', border: '1px solid #373f4d', borderRadius: 14, padding: 20, fontFamily: UIFONT }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
          <div style={{ fontSize: 15, fontWeight: 800, color: '#e6e9ef' }}>⚙️ Individual scoring — {name}</div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#889', fontSize: 20, cursor: 'pointer' }}>✕</button>
        </div>
        <div style={{ fontSize: 11, color: '#889', marginBottom: 14 }}>Overrides WIN over the {d?.team} team rule. Leave a field blank to use the team default (shown as placeholder).</div>
        {!d ? <div style={{ color: '#667' }}>Loading…</div> : (
          <>
            {FIELDS.map(([k, label]) => (
              <div key={k} style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 9 }}>
                <div style={{ width: 130, fontSize: 12, color: '#cfd6e0' }}>{label}</div>
                <input value={vals[k] ?? ''} placeholder={`team: ${d.team_general?.[k] ?? ''}`}
                  onChange={e => setVals((p: any) => ({ ...p, [k]: e.target.value.replace(/[^0-9.]/g, '') }))} style={inp} />
                {d.overrides?.[k] != null && <span style={{ fontSize: 10, color: '#00e5a0' }}>override</span>}
              </div>
            ))}
            <button onClick={save} disabled={saving} style={{ marginTop: 12, padding: '8px 18px', background: '#00e5a0', border: 'none', borderRadius: 8, color: '#0a0c10', fontWeight: 700, fontSize: 12, cursor: 'pointer' }}>{saving ? 'Saving…' : 'Save individual rules'}</button>
          </>
        )}
      </div>
    </div>
  );
}

// ── Markup calculator (retention) — per-client / per-trade with D1(red)/entitled(green) ──────
function MarkupCalcModal({ agent, period, onClose }: any) {
  const [d, setD] = useState<any>(null);
  const [group, setGroup] = useState('clients');       // clients|trades|daily|weekly|monthly
  const [country, setCountry] = useState('');
  const [ib, setIb] = useState('all');                 // all|yes|no
  const [expand, setExpand] = useState<number | null>(null);
  useEffect(() => {
    const q = `period=${period}&group=${group}&ib=${ib}${country ? `&country=${encodeURIComponent(country)}` : ''}`;
    apiGet(`/agents/${agent.id}/markup-calculator?${q}`).then(setD).catch(() => setD({ rows: [], totals: {} }));
  }, [agent.id, period, group, ib, country]);
  const t = d?.totals || {};
  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', zIndex: 9700, display: 'flex', justifyContent: 'center', alignItems: 'flex-start', overflow: 'auto', padding: '24px 12px' }} onClick={onClose}>
      <div onClick={e => e.stopPropagation()} style={{ width: 1040, maxWidth: '97vw', background: '#20252f', border: '1px solid #373f4d', borderRadius: 14, padding: 18 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
          <div style={{ fontSize: 16, fontWeight: 800, color: '#e6e9ef', display: 'flex', alignItems: 'center' }}>📊 Markup calculator — {agent.name}<Info text={MARKUP_INFO} /></div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#889', fontSize: 20, cursor: 'pointer' }}>✕</button>
        </div>
        {/* filters */}
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', marginBottom: 10 }}>
          <div style={{ display: 'flex', gap: 4 }}>
            {['clients', 'trades', 'daily', 'weekly', 'monthly'].map(g => (
              <button key={g} onClick={() => setGroup(g)} style={{ padding: '4px 10px', borderRadius: 6, fontSize: 11, cursor: 'pointer',
                border: `1px solid ${group === g ? '#00e5a0' : '#2a2f3a'}`, background: group === g ? 'rgba(0,229,160,0.1)' : 'transparent', color: group === g ? '#00e5a0' : '#889', textTransform: 'capitalize' }}>{g}</button>
            ))}
          </div>
          <select value={ib} onChange={e => setIb(e.target.value)} style={{ padding: '5px 8px', background: '#11141a', border: '1px solid #2a3142', borderRadius: 6, color: '#cfd6e0', fontSize: 11 }}>
            <option value="all">All clients</option><option value="yes">Under an IB</option><option value="no">No IB</option>
          </select>
          <input value={country} onChange={e => setCountry(e.target.value)} placeholder="Country…" style={{ padding: '5px 8px', width: 130, background: '#11141a', border: '1px solid #2a3142', borderRadius: 6, color: '#e0e0e0', fontSize: 11 }} />
        </div>
        {/* summary strip */}
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', fontSize: 11, color: '#9aa3b2', marginBottom: 10, padding: '8px 12px', background: '#1a1f28', borderRadius: 8 }}>
          {t.clients != null && <span>Clients <b style={{ color: '#00aaff' }}>{fmtNum(t.clients)}</b></span>}
          {t.lots != null && <span>Lots <b style={{ color: '#cc88ff' }}>{fmtNum(Math.round(t.lots))}</b></span>}
          <span>Entitled markup <b style={{ color: '#00e5a0' }}>{fmtUSD(t.markup || t.entitled_markup || 0)}</b></span>
          {t.d1_markup != null && <span>Excluded (pre-D2) <b style={{ color: '#ff5d6c' }}>{fmtUSD(t.d1_markup)}</b></span>}
          {t.ib_comm != null && <span>IB comm <b style={{ color: '#ff8c00' }}>{fmtUSD(t.ib_comm)}</b></span>}
          {t.net != null && <span>Net profit <b style={{ color: '#00e5a0' }}>{fmtUSD(t.net)}</b></span>}
        </div>
        {!d ? <div style={{ color: '#667', padding: 20 }}>Loading…</div> : (
          <div style={{ maxHeight: '60vh', overflow: 'auto', border: '1px solid #2c333e', borderRadius: 8 }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11.5 }}>
              {group === 'clients' && <>
                <thead><tr>{['Client', 'Country/City', 'IB', 'Earns from', 'Lots', 'Markup', 'Pre-D2 (D1)', 'IB comm', 'Net'].map(h => <th key={h} style={{ ...th, position: 'sticky', top: 0 }}>{h}</th>)}</tr></thead>
                <tbody>
                  {(d.rows || []).map((r: any, i: number) => (
                    <React.Fragment key={i}>
                      <tr onClick={() => setExpand(expand === r.login ? null : r.login)} style={{ cursor: 'pointer' }}>
                        <td style={td}><span style={{ fontFamily: 'monospace', color: '#00aaff' }}>#{r.login}</span> {r.name}</td>
                        <td style={{ ...td, color: '#9aa3b2' }}>{r.country}{r.city ? ` · ${r.city}` : ''}</td>
                        <td style={{ ...td }}>{r.under_ib ? <span style={{ color: '#ffaa00' }}>IB</span> : <span style={{ color: '#556' }}>—</span>}{r.own_or_ib && <span style={{ color: '#00e5a0', fontSize: 9, marginLeft: 4 }}>own</span>}</td>
                        <td style={{ ...td, color: r.earns_from.startsWith('D3') ? '#ff8c00' : r.earns_from.startsWith('first') ? '#00e5a0' : '#9aa3b2', fontSize: 10 }}>{r.earns_from}{!r.had_call && !r.own_or_ib && <span style={{ color: '#ff5d6c', marginLeft: 4 }}>no call</span>}</td>
                        <td style={{ ...td, textAlign: 'right', color: '#9aa3b2' }}>{fmtNum(Math.round(r.lots))}</td>
                        <td style={{ ...td, textAlign: 'right', color: '#00e5a0', fontWeight: 600 }}>{fmtUSD(r.markup)}</td>
                        <td style={{ ...td, textAlign: 'right', color: r.d1_markup ? '#ff5d6c' : '#556' }}>{fmtUSD(r.d1_markup)}</td>
                        <td style={{ ...td, textAlign: 'right', color: '#ff8c00' }}>{fmtUSD(r.ib_comm)}</td>
                        <td style={{ ...td, textAlign: 'right', color: '#00e5a0', fontWeight: 700 }}>{fmtUSD(r.net)}</td>
                      </tr>
                      {expand === r.login && <tr><td colSpan={9} style={{ padding: 0 }}><ClientTrades agentId={agent.id} period={period} login={r.login} /></td></tr>}
                    </React.Fragment>
                  ))}
                </tbody>
              </>}
              {group === 'trades' && <>
                <thead><tr>{['Client', 'Date', 'Lots', 'Markup', 'Status'].map(h => <th key={h} style={{ ...th, position: 'sticky', top: 0 }}>{h}</th>)}</tr></thead>
                <tbody>{(d.rows || []).slice(0, 500).map((r: any, i: number) => (
                  <tr key={i} style={{ background: r.entitled ? 'transparent' : 'rgba(255,93,108,0.06)' }}>
                    <td style={td}>#{r.login} {r.name}</td>
                    <td style={{ ...td, color: '#9aa3b2' }}>{r.date}</td>
                    <td style={{ ...td, textAlign: 'right', color: '#9aa3b2' }}>{r.lots}</td>
                    <td style={{ ...td, textAlign: 'right', color: r.entitled ? '#00e5a0' : '#ff5d6c', fontWeight: 600 }}>{fmtUSD(r.markup)}</td>
                    <td style={{ ...td }}><span style={{ color: r.entitled ? '#00e5a0' : '#ff5d6c', fontWeight: 700 }}>{r.entitled ? 'counted' : 'D1'}</span></td>
                  </tr>))}
                </tbody>
              </>}
              {['daily', 'weekly', 'monthly'].includes(group) && <>
                <thead><tr>{['Period', 'Trades', 'Lots', 'Entitled markup', 'Pre-D2 (D1)'].map(h => <th key={h} style={{ ...th, position: 'sticky', top: 0 }}>{h}</th>)}</tr></thead>
                <tbody>{(d.rows || []).map((r: any, i: number) => (
                  <tr key={i}>
                    <td style={td}>{r.bucket}</td>
                    <td style={{ ...td, textAlign: 'right', color: '#9aa3b2' }}>{fmtNum(r.trades)}</td>
                    <td style={{ ...td, textAlign: 'right', color: '#9aa3b2' }}>{fmtNum(Math.round(r.lots))}</td>
                    <td style={{ ...td, textAlign: 'right', color: '#00e5a0', fontWeight: 600 }}>{fmtUSD(r.markup)}</td>
                    <td style={{ ...td, textAlign: 'right', color: r.d1_markup ? '#ff5d6c' : '#556' }}>{fmtUSD(r.d1_markup)}</td>
                  </tr>))}
                </tbody>
              </>}
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function ClientTrades({ agentId, period, login }: any) {
  const [rows, setRows] = useState<any[]>([]);
  useEffect(() => {
    apiGet(`/agents/${agentId}/markup-calculator?period=${period}&group=trades&client=${login}`).then((d: any) => setRows(d.rows || [])).catch(() => setRows([]));
  }, [agentId, period, login]);
  return (
    <div style={{ maxHeight: 220, overflow: 'auto', background: '#171b22', padding: 8 }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
        <tbody>{rows.slice(0, 300).map((r: any, i: number) => (
          <tr key={i} style={{ background: r.entitled ? 'transparent' : 'rgba(255,93,108,0.08)' }}>
            <td style={{ padding: '3px 8px', color: '#9aa3b2' }}>{r.date}</td>
            <td style={{ padding: '3px 8px', textAlign: 'right', color: '#9aa3b2' }}>{r.lots} lots</td>
            <td style={{ padding: '3px 8px', textAlign: 'right', color: r.entitled ? '#00e5a0' : '#ff5d6c', fontWeight: 600 }}>{fmtUSD(r.markup)}</td>
            <td style={{ padding: '3px 8px', color: r.entitled ? '#00e5a0' : '#ff5d6c', fontWeight: 700 }}>{r.entitled ? 'counted' : 'D1'}</td>
          </tr>))}
          {rows.length === 0 && <tr><td style={{ padding: 8, color: '#667' }}>No trades.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

// ── Sales leads funnel — leads that deposited, calls before converting, lost/no-call ─────────
function FunnelModal({ agent, period, onClose }: any) {
  const [d, setD] = useState<any>(null);
  const [status, setStatus] = useState('');            // ''|won|verified|lost
  const [country, setCountry] = useState('');
  const [source, setSource] = useState('');
  useEffect(() => {
    const q = `period=${period}${status ? `&status=${status}` : ''}${country ? `&country=${encodeURIComponent(country)}` : ''}${source ? `&source=${encodeURIComponent(source)}` : ''}`;
    apiGet(`/agents/${agent.id}/sales-funnel?${q}`).then(setD).catch(() => setD({ rows: [] }));
  }, [agent.id, period, status, country, source]);
  const scolor = (s: string) => s === 'won' ? '#00e5a0' : s === 'lost' ? '#ff5d6c' : s === 'verified' ? '#00aaff' : '#9aa3b2';
  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', zIndex: 9700, display: 'flex', justifyContent: 'center', alignItems: 'flex-start', overflow: 'auto', padding: '24px 12px' }} onClick={onClose}>
      <div onClick={e => e.stopPropagation()} style={{ width: 960, maxWidth: '97vw', background: '#20252f', border: '1px solid #373f4d', borderRadius: 14, padding: 18 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
          <div style={{ fontSize: 16, fontWeight: 800, color: '#e6e9ef' }}>📋 Leads funnel — {agent.name}</div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#889', fontSize: 20, cursor: 'pointer' }}>✕</button>
        </div>
        <div style={{ fontSize: 11, color: '#889', marginBottom: 10 }}>
          <b style={{ color: '#00e5a0' }}>{d?.won ?? 0} won</b> (deposited + called) · <b style={{ color: '#ff5d6c' }}>{d?.lost ?? 0} lost</b> (deposited, NO call — not a win) · <b style={{ color: '#00aaff' }}>{d?.verified ?? 0} verified</b>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 10 }}>
          <select value={status} onChange={e => setStatus(e.target.value)} style={{ padding: '5px 8px', background: '#11141a', border: '1px solid #2a3142', borderRadius: 6, color: '#cfd6e0', fontSize: 11 }}>
            <option value="">All</option><option value="won">Won</option><option value="lost">Lost (no call)</option><option value="verified">Verified</option>
          </select>
          <input value={country} onChange={e => setCountry(e.target.value)} placeholder="Country…" style={{ padding: '5px 8px', width: 120, background: '#11141a', border: '1px solid #2a3142', borderRadius: 6, color: '#e0e0e0', fontSize: 11 }} />
          <input value={source} onChange={e => setSource(e.target.value)} placeholder="Source/campaign…" style={{ padding: '5px 8px', width: 150, background: '#11141a', border: '1px solid #2a3142', borderRadius: 6, color: '#e0e0e0', fontSize: 11 }} />
        </div>
        {!d ? <div style={{ color: '#667', padding: 20 }}>Loading…</div> : (
          <div style={{ maxHeight: '60vh', overflow: 'auto', border: '1px solid #2c333e', borderRadius: 8 }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11.5 }}>
              <thead><tr>{['Lead', 'Country/City', 'Source', 'Registered', 'FTD date', 'Calls', 'Status'].map(h => <th key={h} style={{ ...th, position: 'sticky', top: 0 }}>{h}</th>)}</tr></thead>
              <tbody>{(d.rows || []).slice(0, 800).map((r: any, i: number) => (
                <tr key={i} style={{ background: r.status === 'lost' ? 'rgba(255,93,108,0.06)' : 'transparent' }}>
                  <td style={td}>{r.name}{r.verified && <span style={{ color: '#00aaff', fontSize: 9, marginLeft: 5 }}>✓KYC</span>}</td>
                  <td style={{ ...td, color: '#9aa3b2' }}>{r.country}{r.city ? ` · ${r.city}` : ''}</td>
                  <td style={{ ...td, color: '#9aa3b2' }}>{r.source}{r.campaign ? ` · ${r.campaign}` : ''}</td>
                  <td style={{ ...td, color: '#9aa3b2' }}>{r.reg_date || '—'}</td>
                  <td style={{ ...td, color: '#9aa3b2' }}>{r.ftd_date || '—'}</td>
                  <td style={{ ...td, textAlign: 'center', color: r.calls ? '#00e5a0' : '#ff5d6c', fontWeight: 700 }}>{r.calls}</td>
                  <td style={{ ...td }}><span style={{ color: scolor(r.status), fontWeight: 700 }}>{r.status === 'lost' ? 'lost · no call' : r.status}</span></td>
                </tr>))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Editable performance scoring rules (weights + targets) — management ──────────────────────
function ScoringRulesModal({ onClose }: any) {
  const [s, setS] = useState<any>(null);
  const [team, setTeam] = useState('retention');   // sales | retention (leads/managers use retention)
  const [saving, setSaving] = useState(false);
  useEffect(() => { setS(null); apiGet(`/agents/scoring-settings?team=${team}`).then(setS).catch(() => setS({})); }, [team]);
  const set = (k: string, v: string) => setS((p: any) => ({ ...p, [k]: v.replace(/[^0-9.]/g, '') }));
  const save = async () => {
    setSaving(true);
    const body: any = { team }; Object.entries(s).forEach(([k, v]) => { if (k !== 'team') body[k] = parseFloat(v as string) || 0; });
    try { await apiPost('/agents/scoring-settings', body); onClose(); }
    catch (e: any) { alert('Save failed: ' + (e?.message || 'error')); } finally { setSaving(false); }
  };
  const wsum = s ? ['perf_w_nda', 'perf_w_ib', 'perf_w_calls', 'perf_w_qa'].reduce((t, k) => t + (parseFloat(s[k]) || 0), 0) : 0;
  const row = (label: string, wk: string, tk: string | null, unit: string) => (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
      <div style={{ width: 150, fontSize: 12, color: '#cfd6e0' }}>{label}</div>
      <span style={{ fontSize: 10, color: '#667' }}>weight %</span>
      <input value={s[wk] ?? ''} onChange={e => set(wk, e.target.value)} style={inp} />
      {tk && <><span style={{ fontSize: 10, color: '#667' }}>target</span>
        <input value={s[tk] ?? ''} onChange={e => set(tk, e.target.value)} style={inp} /><span style={{ fontSize: 10, color: '#667' }}>{unit}</span></>}
    </div>
  );
  const inp: React.CSSProperties = { width: 64, padding: '5px 7px', background: '#11141a', border: '1px solid #2a3142', borderRadius: 6, color: '#e0e0e0', fontSize: 12, outline: 'none' };
  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', zIndex: 9700, display: 'flex', justifyContent: 'center', alignItems: 'flex-start', overflow: 'auto', padding: '40px 12px' }} onClick={onClose}>
      <div onClick={e => e.stopPropagation()} style={{ width: 520, maxWidth: '96vw', background: '#20252f', border: '1px solid #373f4d', borderRadius: 14, padding: 20, fontFamily: UIFONT }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
          <div style={{ fontSize: 16, fontWeight: 800, color: '#e6e9ef' }}>⚙️ Performance scoring rules</div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#889', fontSize: 20, cursor: 'pointer' }}>✕</button>
        </div>
        <div style={{ display: 'flex', gap: 6, marginBottom: 12 }}>
          {[['retention', 'Retention (+ team leaders)'], ['sales', 'Sales']].map(([v, l]) => (
            <button key={v} onClick={() => setTeam(v)} style={{ padding: '5px 12px', borderRadius: 6, fontSize: 12, cursor: 'pointer',
              border: `1px solid ${team === v ? '#00e5a0' : '#2a2f3a'}`, background: team === v ? 'rgba(0,229,160,0.1)' : 'transparent', color: team === v ? '#00e5a0' : '#889' }}>{l}</button>
          ))}
        </div>
        <div style={{ fontSize: 11, color: '#889', marginBottom: 14 }}>General rule for the <b style={{ color: '#cfd6e0' }}>{team}</b> team. Each metric scores min(1, actual/target) × weight. Score drives eligible commission (commission × score%). Per-agent overrides (in each agent's page) win over this.</div>
        {!s ? <div style={{ color: '#667' }}>Loading…</div> : (
          <>
            {row('Own new clients', 'perf_w_nda', 'perf_t_nda', 'per month')}
            {row('Active IBs', 'perf_w_ib', 'perf_t_ib', 'per month')}
            {row('Calls ≥80s', 'perf_w_calls', 'perf_t_calls', 'per month')}
            {row('Call-QA score', 'perf_w_qa', null, '')}
            <div style={{ fontSize: 11, color: wsum === 100 ? '#00e5a0' : '#ffaa00', marginTop: 6 }}>weights total: {wsum}%{wsum !== 100 ? ' (recommended 100)' : ' ✓'}</div>
            <button onClick={save} disabled={saving} style={{ marginTop: 14, padding: '8px 18px', background: '#00e5a0', border: 'none', borderRadius: 8, color: '#0a0c10', fontWeight: 700, fontSize: 12, cursor: 'pointer' }}>{saving ? 'Saving…' : 'Save rules'}</button>
          </>
        )}
      </div>
    </div>
  );
}

export default function SalesAgents({ focusAgentId }: { focusAgentId?: number }) {
  const [agents, setAgents] = useState<any[]>([]);
  const [kpis, setKpis] = useState<any>({});
  const [sort, setSort] = useState('commission');
  const [sortDir, setSortDir] = useState('desc');
  const [search, setSearch] = useState('');
  const [period, setPeriod] = useState('this_month');
  const [group, setGroup] = useState('');
  const [loading, setLoading] = useState(true);
  const [openAgent, setOpenAgent] = useState<number | null>(null);
  const [autoWide, setAutoWide] = useState(false);
  // a plain sales/retention agent (not management, not a team leader) sees ONLY their own page —
  // auto-open their own detail in the wide view on load.
  const plainAgent = !isMgmt() && localStorage.getItem('isTeamLead') !== '1';
  const [team, setTeam] = useState(0);              // filter by team leader
  const [teams, setTeams] = useState<any[]>([]);
  const [cFrom, setCFrom] = useState('');           // custom period from/to
  const [cTo, setCTo] = useState('');
  const [xferSource, setXferSource] = useState<any>(null);   // bulk-transfer modal source agent
  const [ftdView, setFtdView] = useState<any>(null);         // FTD/NDA drill-down modal {id,name}
  const [calcView, setCalcView] = useState<any>(null);       // markup calculator (from a row)
  const [funnelView, setFunnelView] = useState<any>(null);   // leads funnel (from a row)
  const [showRules, setShowRules] = useState(false);         // scoring-rules editor
  const [capAgents, setCapAgents] = useState<any[]>([]);     // agents w/ caps for the transfer UI
  const loadCaps = useCallback(() => { apiGet('/transfer/agents').then((d: any) => setCapAgents(d.agents || [])).catch(() => {}); }, []);
  useEffect(() => { loadCaps(); }, [loadCaps]);
  const [showReqs, setShowReqs] = useState(false);
  const [reqs, setReqs] = useState<any[]>([]);
  const [reqPick, setReqPick] = useState<Record<number, number>>({});
  const loadReqs = useCallback(() => { apiGet('/transfer/requests').then((d: any) => setReqs(d.requests || [])).catch(() => {}); }, []);
  useEffect(() => { loadReqs(); }, [loadReqs]);
  const resolveReq = async (id: number, action: string) => {
    await apiPost(`/transfer/requests/${id}/resolve`, { action, to_agent_id: reqPick[id] || 0, reason: 'transfer-out resolved' });
    loadReqs(); load(); loadCaps();
  };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const p = new URLSearchParams({ sort, sort_dir: sortDir, period });
      // search filters client-side below - the server recompute costs ~9s on deals
      if (group) p.set('group', group);
      if (team) p.set('team', String(team));
      if (period === 'custom' && cFrom && cTo) { p.set('date_from', cFrom); p.set('date_to', cTo); }
      const d = await apiGet(`/agents?${p}`);
      setAgents(d.agents || []); setKpis(d.kpis || {}); setTeams(d.teams || []);
    } catch { setAgents([]); }
    setLoading(false);
  }, [sort, sortDir, period, group, team, cFrom, cTo]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { if (focusAgentId) setOpenAgent(focusAgentId); }, [focusAgentId]);
  useEffect(() => {
    if (plainAgent && agents.length === 1 && openAgent == null) { setAutoWide(true); setOpenAgent(agents[0].id); }
  }, [plainAgent, agents, openAgent]);

  const mgmt = isMgmt();   // non-management: money blurred, no rate editing (pending board)

  // TWO MODULES — columns: [header, sortKey, period-scoped?]
  // SALES tab   = per-unit funnel: leads → own → verified → converted → NDA×$unit = commission.
  // RETENTION   = markup-based (no unit section at all).
  // All / TLs   = the full combined table.
  const COLS: [string, string, boolean][] = group === 'sales' ? [
    ['Sales agent', 'name', false], ['Leads', 'leads', false], ['Own leads', 'own_leads', false],
    ['Verified', 'verified', false], ['Converted', 'converted', true], ['New Clients', 'nda', true],
    ['Unit bonus', 'unit_bonus', true], ['Commission', 'sales_commission', true],
    ['Score', 'performance', true], ['Eligible', 'eligible_commission', true],
  ] : group === 'retention' ? [
    ['Sales agent', 'name', false], ['Clients', 'clients', false],
    ['FTD', 'ftd', true], ['New Clients', 'nda', true],
    ['Leads', 'leads', false], ['IBs', 'ibs', false],
    ['Deposits', 'deposits', true], ['Withdrawals', 'withdrawals', true],
    ['Markup', 'commission', true], ['IB comm', 'ib_commission', true], ['Net', 'net_commission', true],
    ['Commission', 'sales_commission', true],
    ['Score', 'performance', true], ['Eligible', 'eligible_commission', true],
  ] : [
    ['Sales agent', 'name', false], ['Clients', 'clients', false],
    ['FTD', 'ftd', true], ['New Clients', 'nda', true],
    ['Leads', 'leads', false], ['IBs', 'ibs', false],
    ['Deposits', 'deposits', true], ['Withdrawals', 'withdrawals', true],
    ['Markup', 'commission', true], ['IB comm', 'ib_commission', true], ['Net', 'net_commission', true],
    ['Unit bonus', 'unit_bonus', true], ['Commission', 'sales_commission', true],
    ['Score', 'performance', true], ['Eligible', 'eligible_commission', true],
  ];

  // totals row (sums every numeric column over the visible agents)
  const tot = agents.reduce((a, x) => ({
    clients: a.clients + (x.clients || 0), new_clients: a.new_clients + (x.new_clients || 0),
    ftd: a.ftd + (x.ftd || 0), nda: a.nda + (x.nda || 0),
    leads: a.leads + (x.leads || 0), ibs: a.ibs + (x.ibs || 0),
    verified: a.verified + (x.verified_leads || 0),
    own_leads: a.own_leads + (x.own_leads || 0), converted: a.converted + (x.converted || 0),
    deposits: a.deposits + (x.deposits || 0), withdrawals: a.withdrawals + (x.withdrawals || 0),
    commission: a.commission + (x.commission || 0), ib_commission: a.ib_commission + (x.ib_commission || 0),
    net_commission: a.net_commission + (x.net_commission || 0), sales_commission: a.sales_commission + (x.sales_commission || 0),
    unit_bonus: a.unit_bonus + (x.unit_bonus || 0), unit_nda: a.unit_nda + (x.unit_nda || 0),
    eligible_commission: a.eligible_commission + (x.eligible_commission || 0),
  }), { clients: 0, new_clients: 0, ftd: 0, nda: 0, leads: 0, ibs: 0, verified: 0, own_leads: 0, converted: 0, deposits: 0, withdrawals: 0, commission: 0, ib_commission: 0, net_commission: 0, sales_commission: 0, unit_bonus: 0, unit_nda: 0, eligible_commission: 0 });

  // per-column cell renderers (so each module can pick its columns)
  const CELL: Record<string, (a: any) => React.ReactNode> = {
    clients:    a => <td key="clients" style={{ ...CT.td, textAlign: 'right', color: '#00aaff', fontWeight: 600 }}>{fmtNum(a.clients)}</td>,
    new_clients:a => <td key="new" style={{ ...CT.td, textAlign: 'right', color: a.new_clients ? '#00e5a0' : '#445' }}>{fmtNum(a.new_clients)}</td>,
    ftd:        a => <td key="ftd" onClick={e => { if (a.ftd) { e.stopPropagation(); setFtdView({ id: a.id, name: a.name }); } }}
                      style={{ ...CT.td, textAlign: 'right', color: a.ftd ? '#00aaff' : '#445', cursor: a.ftd ? 'pointer' : 'default', textDecoration: a.ftd ? 'underline dotted' : 'none' }}
                      title="First-Time-Deposits (unique customers) in the period — click to see who">{fmtNum(a.ftd)}</td>,
    nda:        a => <td key="nda" onClick={e => { if (a.ftd) { e.stopPropagation(); setFtdView({ id: a.id, name: a.name }); } }}
                      style={{ ...CT.td, textAlign: 'right', cursor: a.ftd ? 'pointer' : 'default' }}
                      title={`Genuinely new deposit accounts. ${a.nda_pct}% of this agent's FTDs — click to see who, and why the others are related`}>
                      <span style={{ color: a.nda ? '#ffd166' : '#445', fontWeight: 700, textDecoration: a.ftd ? 'underline dotted' : 'none' }}>{fmtNum(a.nda)}</span>
                      {a.ftd > 0 && <span style={{ fontSize: 10, color: a.nda_pct >= 70 ? '#00e5a0' : a.nda_pct >= 50 ? '#ffaa00' : '#ff5d6c', marginLeft: 4 }}>{a.nda_pct}%</span>}
                    </td>,
    leads:      a => <td key="leads" style={{ ...CT.td, textAlign: 'right', color: '#cc88ff' }}>{fmtNum(a.leads)}</td>,
    own_leads:  a => <td key="own" style={{ ...CT.td, textAlign: 'right', color: a.own_leads ? '#cc88ff' : '#445' }} title="Leads the agent added themselves (not campaign-distributed)">{fmtNum(a.own_leads)}</td>,
    verified:   a => <td key="ver" style={{ ...CT.td, textAlign: 'right', color: a.verified_leads ? '#00e5a0' : '#445' }} title="KYC-verified leads">{fmtNum(a.verified_leads)}</td>,
    converted:  a => <td key="conv" onClick={e => { e.stopPropagation(); setFunnelView({ id: a.id, name: a.name }); }}
                      style={{ ...CT.td, textAlign: 'right', color: a.converted ? '#00aaff' : '#445', fontWeight: 600, cursor: 'pointer' }}
                      title="Click to open the leads funnel (who deposited, calls, won/lost-no-call)"><span style={{ textDecoration: 'underline dotted' }}>{fmtNum(a.converted)}</span></td>,
    ibs:        a => <td key="ibs" style={{ ...CT.td, textAlign: 'right', color: '#ffaa00', fontWeight: 600 }}>{fmtNum(a.ibs)}</td>,
    deposits:   a => <td key="dep" style={{ ...CT.td, textAlign: 'right', color: '#00e5a0' }}>{fmtUSD(a.deposits)}</td>,
    withdrawals:a => <td key="wd" style={{ ...CT.td, textAlign: 'right', color: '#ff5d6c' }}>{fmtUSD(a.withdrawals)}</td>,
    commission: a => <td key="mk" onClick={e => { if (a.team !== 'sales') { e.stopPropagation(); setCalcView({ id: a.id, name: a.name }); } }}
                      style={{ ...CT.td, textAlign: 'right', cursor: a.team !== 'sales' ? 'pointer' : 'default' }}
                      title={a.team !== 'sales' ? 'Click to open the markup calculator (per-client / per-trade)' : 'Company markup (entitled trades)'}>
                      <span style={{ color: '#00e5a0', fontWeight: 600, textDecoration: a.team !== 'sales' ? 'underline dotted' : 'none' }}>{fmtUSD(a.commission)}</span></td>,
    ib_commission: a => <td key="ibc" style={{ ...CT.td, textAlign: 'right' }}><span style={{ color: '#ff8c00' }}>{fmtUSD(a.ib_commission)}</span></td>,
    net_commission:a => <td key="net" style={{ ...CT.td, textAlign: 'right' }}><span style={{ color: '#00aaff', fontWeight: 600 }}>{fmtUSD(a.net_commission)}</span></td>,
    unit_bonus: a => <td key="ub" style={{ ...CT.td, textAlign: 'right' }} title={`$${a.unit_rate || 10} × ${a.unit_nda || 0} new-client conversions acquired`}>
                      <span>
                        <span style={{ color: a.unit_bonus ? '#ffd166' : '#445', fontWeight: 700 }}>{fmtUSD(a.unit_bonus)}</span>
                        {a.unit_nda > 0 && <span style={{ fontSize: 10, color: '#889', marginLeft: 4 }}>{a.unit_nda}×</span>}
                      </span>
                    </td>,
    sales_commission: a => <td key="sc" style={{ ...CT.td, textAlign: 'right' }} title="Sales = $unit × new-client conversions · Retention = markup% after D2 · TL = markup%"><span style={{ color: '#cc88ff', fontWeight: 700 }}>{fmtUSD(a.sales_commission)}</span></td>,
    performance: a => <td key="perf" style={{ ...CT.td, textAlign: 'right' }} title="Monthly performance score (demo this month)"><ScorePill pct={a.performance || 0} demo={a.perf_demo} /></td>,
    eligible_commission: a => <td key="elig" style={{ ...CT.td, textAlign: 'right' }} title="commission × performance%"><span style={{ color: '#00e5a0', fontWeight: 700 }}>{fmtUSD(a.eligible_commission)}</span></td>,
  };
  const TCELL: Record<string, React.ReactNode> = {
    clients:    <td key="clients" style={{ ...CT.td, textAlign: 'right', color: '#00aaff', fontWeight: 700 }}>{fmtNum(tot.clients)}</td>,
    new_clients:<td key="new" style={{ ...CT.td, textAlign: 'right', color: '#00e5a0', fontWeight: 700 }}>{fmtNum(tot.new_clients)}</td>,
    ftd:        <td key="ftd" style={{ ...CT.td, textAlign: 'right', color: '#00aaff', fontWeight: 700 }}>{fmtNum(tot.ftd)}</td>,
    nda:        <td key="nda" style={{ ...CT.td, textAlign: 'right', color: '#ffd166', fontWeight: 800 }}>{fmtNum(tot.nda)}{tot.ftd > 0 && <span style={{ fontSize: 10, color: '#889', marginLeft: 4 }}>{Math.round(100 * tot.nda / tot.ftd)}%</span>}</td>,
    leads:      <td key="leads" style={{ ...CT.td, textAlign: 'right', color: '#cc88ff', fontWeight: 700 }}>{fmtNum(tot.leads)}</td>,
    own_leads:  <td key="own" style={{ ...CT.td, textAlign: 'right', color: '#cc88ff', fontWeight: 700 }}>{fmtNum(tot.own_leads)}</td>,
    verified:   <td key="ver" style={{ ...CT.td, textAlign: 'right', color: '#00e5a0', fontWeight: 700 }}>{fmtNum(tot.verified)}</td>,
    converted:  <td key="conv" style={{ ...CT.td, textAlign: 'right', color: '#00aaff', fontWeight: 700 }}>{fmtNum(tot.converted)}</td>,
    ibs:        <td key="ibs" style={{ ...CT.td, textAlign: 'right', color: '#ffaa00', fontWeight: 700 }}>{fmtNum(tot.ibs)}</td>,
    deposits:   <td key="dep" style={{ ...CT.td, textAlign: 'right', color: '#00e5a0', fontWeight: 700 }}>{fmtUSD(tot.deposits)}</td>,
    withdrawals:<td key="wd" style={{ ...CT.td, textAlign: 'right', color: '#ff5d6c', fontWeight: 700 }}>{fmtUSD(tot.withdrawals)}</td>,
    commission: <td key="mk" style={{ ...CT.td, textAlign: 'right' }}><span style={{ color: '#00e5a0', fontWeight: 700 }}>{fmtUSD(tot.commission)}</span></td>,
    ib_commission: <td key="ibc" style={{ ...CT.td, textAlign: 'right' }}><span style={{ color: '#ff8c00', fontWeight: 700 }}>{fmtUSD(tot.ib_commission)}</span></td>,
    net_commission:<td key="net" style={{ ...CT.td, textAlign: 'right' }}><span style={{ color: '#00aaff', fontWeight: 700 }}>{fmtUSD(tot.net_commission)}</span></td>,
    unit_bonus: <td key="ub" style={{ ...CT.td, textAlign: 'right' }}><span style={{ color: '#ffd166', fontWeight: 800 }}>{fmtUSD(tot.unit_bonus)}{tot.unit_nda > 0 && <span style={{ fontSize: 10, color: '#889', marginLeft: 4 }}>{tot.unit_nda}×</span>}</span></td>,
    sales_commission: <td key="sc" style={{ ...CT.td, textAlign: 'right' }}><span style={{ color: '#cc88ff', fontWeight: 800 }}>{fmtUSD(tot.sales_commission)}</span></td>,
    performance: <td key="perf" style={{ ...CT.td, textAlign: 'right', color: '#889', fontSize: 11 }}>{kpis.avg_performance ? `${kpis.avg_performance}% avg` : '—'}</td>,
    eligible_commission: <td key="elig" style={{ ...CT.td, textAlign: 'right' }}><span style={{ color: '#00e5a0', fontWeight: 800 }}>{fmtUSD(tot.eligible_commission)}</span></td>,
  };

  const saveUnit = async (v: string) => {
    const n = parseFloat(v);
    if (isNaN(n) || n < 0) return;
    await apiPost('/agents/commission-settings', { sales_unit_usd: n });
    load();
  };

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden', minHeight: 0, background: '#20252f', position: 'relative' }}>
      <div style={{ padding: '12px 16px 10px', borderBottom: '1px solid #373f4d', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 10 }}>
          <div style={{ fontSize: 16, fontWeight: 700, color: '#e6e9ef' }}>🧑‍💼 Sales Agents</div>
          <select value={group} onChange={e => setGroup(e.target.value)}
            style={{ padding: '6px 10px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 8, color: '#cfd6e0', fontSize: 12, outline: 'none' }}>
            {GROUPS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          <select value={team} onChange={e => setTeam(Number(e.target.value))} title="Filter by team"
            style={{ padding: '6px 10px', background: '#373f4d', border: `1px solid ${team ? '#00e5a0' : '#626d80'}`, borderRadius: 8, color: team ? '#00e5a0' : '#cfd6e0', fontSize: 12, outline: 'none' }}>
            <option value={0}>All teams</option>
            {teams.map((t: any) => <option key={t.id} value={t.id}>{t.name}'s team</option>)}
          </select>
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search agent…"
            style={{ marginLeft: 'auto', padding: '7px 12px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 8, color: '#e0e0e0', fontSize: 12, width: 200, outline: 'none' }} />
          {canReassignAgent() && (
          <button onClick={() => { setShowReqs(true); loadReqs(); }} title="Transfer-out requests"
            style={{ padding: '7px 12px', background: reqs.length ? 'rgba(204,136,255,0.14)' : '#373f4d', border: `1px solid ${reqs.length ? '#cc88ff' : '#626d80'}`, borderRadius: 8, color: reqs.length ? '#cc88ff' : '#9aa3b2', fontSize: 12, cursor: 'pointer', whiteSpace: 'nowrap' }}>
            📥 Requests{reqs.length ? ` (${reqs.length})` : ''}
          </button>
          )}
          {isMgmt() && (
            <button onClick={() => setShowRules(true)} title="Edit performance scoring rules"
              style={{ padding: '7px 12px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 8, color: '#9aa3b2', fontSize: 12, cursor: 'pointer', whiteSpace: 'nowrap' }}>
              ⚙ Scoring rules
            </button>
          )}
        </div>
        <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap', marginBottom: 10, alignItems: 'center' }}>
          {PERIODS.map(([v, l]) => (
            <button key={v} onClick={() => setPeriod(v)}
              style={{ padding: '4px 11px', borderRadius: 6, fontSize: 11, cursor: 'pointer', fontFamily: 'inherit',
                border: `1px solid ${period === v ? '#00e5a0' : '#2a2f3a'}`, background: period === v ? 'rgba(0,229,160,0.1)' : 'transparent', color: period === v ? '#00e5a0' : '#889' }}>
              {l}
            </button>
          ))}
          <button onClick={() => setPeriod('custom')}
            style={{ padding: '4px 11px', borderRadius: 6, fontSize: 11, cursor: 'pointer', fontFamily: 'inherit',
              border: `1px solid ${period === 'custom' ? '#00e5a0' : '#2a2f3a'}`, background: period === 'custom' ? 'rgba(0,229,160,0.1)' : 'transparent', color: period === 'custom' ? '#00e5a0' : '#889' }}>
            Custom
          </button>
          {period === 'custom' && (
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
              <input type="date" max={new Date(Date.now()+86400000).toISOString().slice(0,10)} value={cFrom} onChange={e => setCFrom(e.target.value)}
                style={{ padding: '3px 7px', background: '#11141a', border: '1px solid #2a3142', borderRadius: 6, color: '#e0e0e0', fontSize: 11, outline: 'none' }} />
              <span style={{ color: '#667', fontSize: 11 }}>→</span>
              <input type="date" max={new Date(Date.now()+86400000).toISOString().slice(0,10)} value={cTo} onChange={e => setCTo(e.target.value)}
                style={{ padding: '3px 7px', background: '#11141a', border: '1px solid #2a3142', borderRadius: 6, color: '#e0e0e0', fontSize: 11, outline: 'none' }} />
            </span>
          )}
        </div>
        {/* editable sales unit-bonus rate (management only; sales module only — retention is markup-based) */}
        {mgmt && group !== 'retention' && (
          <div style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: 6, marginBottom: 6, fontSize: 11, color: '#889' }}>
            <span title="Sales are paid per unit: this $ for every new-client conversion they acquire">⚙ Sales unit rate: $</span>
            <input key={kpis.unit_rate} type="number" defaultValue={kpis.unit_rate ?? 10} min={0} step={1}
              onKeyDown={e => { if (e.key === 'Enter') saveUnit((e.target as HTMLInputElement).value); }}
              onBlur={e => saveUnit(e.target.value)}
              style={{ width: 60, padding: '2px 6px', background: '#11141a', border: '1px solid #2a3142', borderRadius: 6, color: '#e0e0e0', fontSize: 11, outline: 'none' }} />
            <span>per new-client conversion · Enter to save</span>
          </div>
        )}
        {kpis.perf_demo && (
          <div style={{ background: 'rgba(255,209,102,0.08)', border: '1px solid rgba(255,209,102,0.35)', borderRadius: 8, padding: '6px 12px', marginBottom: 8, fontSize: 11, color: '#ffd166' }}>
            ⓘ Performance scores this month are a <b>DEMO</b> (70-85%) so you can see how eligible commission works — real scoring goes live next month.
          </div>
        )}
        {/* commission KPIs (the headline ones) + operational */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 8, marginBottom: 8 }}>
          <Kpi label="Company markup" value={fmtUSD(kpis.total_commission)} c="#00e5a0" hint="entitled trades only" />
          <Kpi label="Paid to IBs" value={fmtUSD(kpis.total_ib_commission)} c="#ff8c00" hint="trading accounts under IBs" />
          <Kpi label="Net (markup − IB)" value={fmtUSD(kpis.total_net_commission)} c="#00aaff" />
          <Kpi label="Commission" value={fmtUSD(kpis.total_sales_commission)} c="#cc88ff" hint="sales = $/new client · retention = markup%" />
          <Kpi label="Eligible" value={fmtUSD(kpis.total_eligible_commission)} c="#00e5a0" hint={`commission × performance (avg ${kpis.avg_performance || 0}%)`} />
          <Kpi label={`Unit bonus ($${kpis.unit_rate ?? 10}/new client)`} value={fmtUSD(kpis.total_unit_bonus)} c="#ffd166" hint={`${fmtNum(kpis.total_unit_nda || 0)} new clients × $${kpis.unit_rate ?? 10}`} />
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: 8 }}>
          <Kpi label="Agents" value={fmtNum(kpis.total_agents)} c="#e6e9ef" />
          <Kpi label="Total clients" value={fmtNum(kpis.unique_clients || kpis.total_clients)} c="#00aaff"
            hint={kpis.unique_clients && kpis.total_clients > kpis.unique_clients ? `unique people — ${fmtNum(kpis.total_clients - kpis.unique_clients)} more per-agent slots (a person under 2 agents counts for each)` : 'unique people (same universe as the Clients page)'} />
          <Kpi label="FTD (period)" value={fmtNum(kpis.total_ftd)} c="#00aaff" hint="first-time deposits — unique customers whose FIRST deposit is in the period" />
          <Kpi label="New Clients" value={`${fmtNum(kpis.total_nda)}${kpis.total_ftd ? ` · ${Math.round(100 * kpis.total_nda / kpis.total_ftd)}%` : ''}`} c="#ffd166" hint="genuinely new — no relation to existing clients" />
          <Kpi label="IBs" value={fmtNum(kpis.total_ibs)} c="#ffaa00" />
          <Kpi label="Deposits" value={fmtUSD(kpis.total_deposits)} c="#00e5a0" />
        </div>
      </div>

      <div style={CT.scroll}>
        <table style={CT.table}>
          <thead>
            <tr style={CT.theadTr}>{COLS.map(([h, s, per]) => {
              const align: 'left' | 'right' = s === 'name' ? 'left' : 'right';
              return (
                <th key={h} style={{ ...CT.th(sort === s, align), cursor: 'pointer' }} title={per ? 'For the selected period · click to sort' : 'Lifetime · click to sort'}
                  onClick={() => { if (sort === s) setSortDir(d => d === 'asc' ? 'desc' : 'asc'); else { setSort(s); setSortDir('desc'); } }}>
                  {h}{per ? ' •' : ''}{sort === s ? (sortDir === 'asc' ? ' ↑' : ' ↓') : ' ⇅'}
                </th>
              );
            })}</tr>
          </thead>
          <tbody>
            {loading ? <tr><td colSpan={COLS.length} style={{ padding: 40, textAlign: 'center', color: '#556' }}>Loading…</td></tr>
              : agents.length === 0 ? <tr><td colSpan={COLS.length} style={{ padding: 40, textAlign: 'center', color: '#556' }}>No agents found</td></tr>
              : agents.filter(a => !search || (a.name || '').toLowerCase().includes(search.toLowerCase())).map((a, i) => {
                const focus = openAgent && a.id === openAgent;
                const rc = ROLE_COLOR[a.role] || '#889';
                return (
                  <tr key={i} style={{ ...CT.row(!!focus), background: focus ? 'rgba(0,229,160,0.08)' : 'transparent', cursor: 'pointer' }}
                    onClick={() => setOpenAgent(a.id)}
                    onMouseEnter={e => (e.currentTarget.style.background = '#101319')}
                    onMouseLeave={e => (e.currentTarget.style.background = focus ? 'rgba(0,229,160,0.08)' : 'transparent')}>
                    <td style={{ ...CT.td, borderLeft: focus ? '3px solid #00e5a0' : '3px solid transparent' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <div style={{ flex: 1 }}>
                          <div style={{ fontWeight: 600, color: '#e6e9ef' }}>{a.name}</div>
                          <div style={{ fontSize: 10, color: rc }}>{a.role}{!a.is_active && <span style={{ color: '#ff5d6c' }}> · inactive</span>}</div>
                        </div>
                        {canReassignAgent() && (
                        <button onClick={(e) => { e.stopPropagation(); setXferSource(capAgents.find(x => x.id === a.id) || { ...a, clients: a.clients }); }}
                          title="Bulk transfer this agent's clients / leads"
                          style={{ background: '#2c333e', border: '1px solid #3a4150', color: '#00aaff', borderRadius: 6, padding: '3px 8px', fontSize: 12, cursor: 'pointer' }}>⇄</button>
                        )}
                      </div>
                    </td>
                    {COLS.slice(1).map(([, s]) => CELL[s]?.(a))}
                  </tr>
                );
              })}
            {!loading && agents.length > 0 && (
              <tr style={{ ...CT.row(), background: '#262c36', position: 'sticky', bottom: 0 }}>
                <td style={{ ...CT.td, color: '#e6e9ef', fontWeight: 800 }}>TOTAL · {agents.length} agents</td>
                {COLS.slice(1).map(([, s]) => TCELL[s])}
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <div style={{ padding: '6px 16px', borderTop: '1px solid #373f4d', fontSize: 10, color: '#556', flexShrink: 0 }}>
        Markup = company profit from the agent's clients' trades · IB comm = paid to those clients' IBs · Net = markup − IB · SALES are paid $unit × new-client conversions only · RETENTION is paid Net × % (own/IB clients from start, transferred clients after D2). Click a row for full details &amp; target.
      </div>
      {openAgent && <AgentDetail agentId={openAgent} period={period} startWide={autoWide} hideCollapse={plainAgent} onClose={() => { setOpenAgent(null); setAutoWide(false); }} />}
      {ftdView && <FTDModal agent={ftdView} period={period} cFrom={cFrom} cTo={cTo} onClose={() => setFtdView(null)} />}
      {calcView && <MarkupCalcModal agent={calcView} period={period} onClose={() => setCalcView(null)} />}
      {funnelView && <FunnelModal agent={funnelView} period={period} onClose={() => setFunnelView(null)} />}
      {showRules && <ScoringRulesModal onClose={() => setShowRules(false)} />}
      {xferSource && <TransferModal source={xferSource} agents={capAgents}
        onClose={() => setXferSource(null)}
        onDone={() => { load(); loadCaps(); }} />}
      {showReqs && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', zIndex: 9500, display: 'flex', justifyContent: 'center', alignItems: 'flex-start', overflow: 'auto', padding: '30px 12px' }} onClick={() => setShowReqs(false)}>
          <div onClick={e => e.stopPropagation()} style={{ width: 640, maxWidth: '96vw', background: '#20252f', border: '1px solid #373f4d', borderRadius: 14, padding: 20 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
              <div style={{ fontSize: 16, fontWeight: 800, color: '#e6e9ef' }}>📥 Transfer-out requests</div>
              <button onClick={() => setShowReqs(false)} style={{ background: 'none', border: 'none', color: '#889', fontSize: 22, cursor: 'pointer' }}>✕</button>
            </div>
            {reqs.length === 0 ? <div style={{ color: '#667', fontSize: 13, padding: 20, textAlign: 'center' }}>No pending requests.</div>
              : reqs.map(r => (
                <div key={r.id} style={{ background: '#262c36', border: '1px solid #373f4d', borderRadius: 10, padding: 12, marginBottom: 10 }}>
                  <div style={{ fontSize: 13, color: '#e6e9ef', fontWeight: 600 }}>{r.record_type === 'client' ? '👤' : '🎯'} {r.record_name || `#${r.record_key}`} <span style={{ color: '#667', fontSize: 11, fontWeight: 400 }}>· from {r.requested_by} · {r.at}</span></div>
                  {r.reason && <div style={{ fontSize: 11.5, color: '#9aa3b2', margin: '4px 0 8px' }}>“{r.reason}”</div>}
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <select value={reqPick[r.id] || 0} onChange={e => setReqPick(p => ({ ...p, [r.id]: Number(e.target.value) }))}
                      style={{ flex: 1, padding: '6px 9px', background: '#11141a', border: '1px solid #2a3142', borderRadius: 7, color: '#e6e9ef', fontSize: 12, outline: 'none' }}>
                      <option value={0}>Assign to…</option>
                      {capAgents.filter(a => !a.at_cap).map(a => <option key={a.id} value={a.id}>{a.name} ({a.team_type}{a.remaining != null ? `, ${a.remaining} left` : ''})</option>)}
                    </select>
                    <button onClick={() => resolveReq(r.id, 'assign')} disabled={!reqPick[r.id]}
                      style={{ padding: '6px 14px', background: '#00e5a0', border: 'none', borderRadius: 7, color: '#0a0c10', fontWeight: 700, fontSize: 12, cursor: reqPick[r.id] ? 'pointer' : 'not-allowed', opacity: reqPick[r.id] ? 1 : 0.5 }}>Assign</button>
                    <button onClick={() => resolveReq(r.id, 'reject')} style={{ padding: '6px 12px', background: '#373f4d', border: '1px solid #4f596b', borderRadius: 7, color: '#ff8a8a', fontSize: 12, cursor: 'pointer' }}>Dismiss</button>
                  </div>
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}

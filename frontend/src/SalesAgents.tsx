import React, { useState, useEffect, useCallback } from 'react';
import { apiGet, apiPost } from './api';
import TransferModal from './TransferModal';
import { CT } from './crmTable';

const fmtUSD = (n: number) => '$' + Math.round(n || 0).toLocaleString();
const fmtNum = (n: number) => (n || 0).toLocaleString();

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

// ── Per-agent detail drawer ──────────────────────────────────────────────────
function AgentDetail({ agentId, period, onClose, startWide }: { agentId: number; period: string; onClose: () => void; startWide?: boolean }) {
  const [d, setD] = useState<any>(null);
  const [tgt, setTgt] = useState('');
  const [pct, setPct] = useState('');
  const [saving, setSaving] = useState(false);
  const [wide, setWide] = useState(!!startWide);   // "More details" → full-page view
  const [lp, setLp] = useState(period);            // the full-page view gets its own period

  const load = useCallback(() => {
    apiGet(`/agents/${agentId}?period=${lp}`).then((x: any) => {
      setD(x); setTgt(String(x.sales_target || 0)); setPct(String(x.commission_pct || 10));
    });
  }, [agentId, lp]);
  useEffect(() => { load(); }, [load]);

  const save = async () => {
    setSaving(true);
    await apiPost(`/agents/${agentId}/settings`, { commission_pct: parseFloat(pct) || 0, sales_target: parseFloat(tgt) || 0 });
    await load(); setSaving(false);
  };

  const k = d?.kpis || {};
  const tile = (label: string, value: any, c = '#e6e9ef', hint = '') => (
    <div style={{ background: '#262c36', border: '1px solid #373f4d', borderRadius: 9, padding: '10px 12px' }}>
      <div style={{ fontSize: 9, color: '#667', textTransform: 'uppercase', letterSpacing: .4, marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 17, fontWeight: 700, color: c }}>{value}</div>
      {hint && <div style={{ fontSize: 9, color: '#667', marginTop: 2 }}>{hint}</div>}
    </div>
  );

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', zIndex: 9000 }} onClick={onClose}>
      <div onClick={e => e.stopPropagation()} style={{ position: 'absolute', top: 0, right: 0, bottom: 0,
        left: wide ? 0 : 'auto', width: wide ? '100%' : 600, maxWidth: wide ? '100%' : '94vw',
        background: '#20252f', borderLeft: '1px solid #373f4d', boxShadow: '-10px 0 40px rgba(0,0,0,0.6)', overflowY: 'auto', padding: wide ? '20px 36px' : 20 }}>
        {!d ? <div style={{ color: '#667', padding: 30 }}>Loading…</div> : (
          <>
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 4 }}>
              <div>
                <div style={{ fontSize: 19, fontWeight: 700, color: '#e6e9ef' }}>{d.name}</div>
                <div style={{ fontSize: 11, color: ROLE_COLOR[d.role] || '#889' }}>{d.role}{d.team_type ? ` · ${d.team_type}` : ''}{d.extension ? ` · ext ${d.extension}` : ''}</div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <button onClick={() => setWide(w => !w)} title="Full sales-agent page"
                  style={{ background: '#2c333e', border: '1px solid #373f4d', color: '#9aa3b2', fontSize: 11, fontWeight: 600, padding: '5px 11px', borderRadius: 7, cursor: 'pointer', whiteSpace: 'nowrap' }}>
                  {wide ? '⤡ Collapse' : '⤢ More details'}
                </button>
                <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#889', fontSize: 22, cursor: 'pointer' }}>✕</button>
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
            <div style={{ fontSize: 11, color: '#667', marginBottom: 14 }}>Period: {d.period?.from} → {d.period?.to}</div>

            {/* Commission summary */}
            <div style={{ fontSize: 11, color: '#889', fontWeight: 600, textTransform: 'uppercase', letterSpacing: .5, marginBottom: 8 }}>💰 Commission (this period)</div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 8, marginBottom: 16 }}>
              {tile('Company markup', fmtUSD(k.markup), '#00e5a0', 'from his clients')}
              {tile('Paid to IBs', fmtUSD(k.ib_commission), '#ff8c00', 'his clients’ IBs')}
              {tile('Net (markup − IB)', fmtUSD(k.net_commission), '#00aaff')}
              {tile(`Sales comm (${d.commission_pct}%)`, fmtUSD(k.sales_commission), '#cc88ff', 'what we pay him')}
            </div>

            {/* Target */}
            <div style={{ background: '#262c36', border: '1px solid #373f4d', borderRadius: 10, padding: 14, marginBottom: 16 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: '#e6e9ef' }}>🎯 Commission target</div>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <span style={{ fontSize: 10, color: '#667' }}>Rate %</span>
                  <input value={pct} onChange={e => setPct(e.target.value.replace(/[^0-9.]/g, ''))} style={{ width: 50, padding: '5px 7px', background: '#11141a', border: '1px solid #2a3142', borderRadius: 6, color: '#e0e0e0', fontSize: 12, outline: 'none' }} />
                  <span style={{ fontSize: 10, color: '#667' }}>Target $</span>
                  <input value={tgt} onChange={e => setTgt(e.target.value.replace(/[^0-9.]/g, ''))} style={{ width: 80, padding: '5px 7px', background: '#11141a', border: '1px solid #2a3142', borderRadius: 6, color: '#e0e0e0', fontSize: 12, outline: 'none' }} />
                  <button onClick={save} disabled={saving} style={{ padding: '5px 12px', background: '#00e5a0', border: 'none', borderRadius: 6, color: '#0a0c10', fontWeight: 700, fontSize: 11, cursor: 'pointer' }}>{saving ? '…' : 'Save'}</button>
                </div>
              </div>
              {k.target > 0 ? (
                <>
                  <div style={{ height: 8, background: '#11141a', borderRadius: 4, overflow: 'hidden', marginBottom: 6 }}>
                    <div style={{ height: '100%', width: `${Math.min(100, k.target_pct)}%`, background: k.target_pct >= 100 ? '#00e5a0' : '#00aaff', borderRadius: 4 }} />
                  </div>
                  <div style={{ fontSize: 11, color: '#9aa3b2' }}>
                    <span style={{ color: '#00e5a0', fontWeight: 700 }}>{fmtUSD(k.target_done)}</span> done · <span style={{ color: '#ffaa00' }}>{fmtUSD(k.target_left)}</span> left · {k.target_pct}% of {fmtUSD(k.target)}
                  </div>
                </>
              ) : <div style={{ fontSize: 11, color: '#667' }}>No target set — enter a Target $ above to track progress.</div>}
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
            <div style={{ background: '#262c36', border: '1px solid #373f4d', borderRadius: 10, overflow: 'hidden' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11.5 }}>
                <thead><tr>{['Client', 'Lots', 'Trades', 'Company markup'].map(h => <th key={h} style={{ ...th, position: 'static' }}>{h}</th>)}</tr></thead>
                <tbody>
                  {(d.top_clients || []).length === 0 ? <tr><td colSpan={4} style={{ padding: 20, textAlign: 'center', color: '#556' }}>No trades in period</td></tr>
                    : d.top_clients.map((c: any, i: number) => (
                      <tr key={i}>
                        <td style={td}><span style={{ fontFamily: 'monospace', color: '#00aaff' }}>#{c.login}</span> <span style={{ color: '#cfd6e0' }}>{c.name}</span></td>
                        <td style={{ ...td, color: '#9aa3b2' }}>{fmtNum(Math.round(c.lots))}</td>
                        <td style={{ ...td, color: '#9aa3b2' }}>{fmtNum(c.trades)}</td>
                        <td style={{ ...td, color: '#00e5a0', fontWeight: 600 }}>{fmtUSD(c.markup)}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
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
  const [team, setTeam] = useState(0);              // filter by team leader
  const [teams, setTeams] = useState<any[]>([]);
  const [cFrom, setCFrom] = useState('');           // custom period from/to
  const [cTo, setCTo] = useState('');
  const [xferSource, setXferSource] = useState<any>(null);   // bulk-transfer modal source agent
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
      if (search) p.set('search', search);
      if (group) p.set('group', group);
      if (team) p.set('team', String(team));
      if (period === 'custom' && cFrom && cTo) { p.set('date_from', cFrom); p.set('date_to', cTo); }
      const d = await apiGet(`/agents?${p}`);
      setAgents(d.agents || []); setKpis(d.kpis || {}); setTeams(d.teams || []);
    } catch { setAgents([]); }
    setLoading(false);
  }, [sort, sortDir, period, search, group, team, cFrom, cTo]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { if (focusAgentId) setOpenAgent(focusAgentId); }, [focusAgentId]);

  // columns: [header, sortKey, period-scoped?]
  const COLS: [string, string, boolean][] = [
    ['Sales agent', 'name', false], ['Clients', 'clients', false], ['New', 'new_clients', true],
    ['Leads', 'leads', false], ['IBs', 'ibs', false],
    ['Deposits', 'deposits', true], ['Withdrawals', 'withdrawals', true],
    ['Markup', 'commission', true], ['IB comm', 'ib_commission', true], ['Net', 'net_commission', true], ['Sales 10%', 'sales_commission', true],
  ];

  // totals row (sums every numeric column over the visible agents)
  const tot = agents.reduce((a, x) => ({
    clients: a.clients + (x.clients || 0), new_clients: a.new_clients + (x.new_clients || 0),
    leads: a.leads + (x.leads || 0), ibs: a.ibs + (x.ibs || 0),
    deposits: a.deposits + (x.deposits || 0), withdrawals: a.withdrawals + (x.withdrawals || 0),
    commission: a.commission + (x.commission || 0), ib_commission: a.ib_commission + (x.ib_commission || 0),
    net_commission: a.net_commission + (x.net_commission || 0), sales_commission: a.sales_commission + (x.sales_commission || 0),
  }), { clients: 0, new_clients: 0, leads: 0, ibs: 0, deposits: 0, withdrawals: 0, commission: 0, ib_commission: 0, net_commission: 0, sales_commission: 0 });

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden', minHeight: 0, background: '#20252f' }}>
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
          <button onClick={() => { setShowReqs(true); loadReqs(); }} title="Transfer-out requests"
            style={{ padding: '7px 12px', background: reqs.length ? 'rgba(204,136,255,0.14)' : '#373f4d', border: `1px solid ${reqs.length ? '#cc88ff' : '#626d80'}`, borderRadius: 8, color: reqs.length ? '#cc88ff' : '#9aa3b2', fontSize: 12, cursor: 'pointer', whiteSpace: 'nowrap' }}>
            📥 Requests{reqs.length ? ` (${reqs.length})` : ''}
          </button>
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
              <input type="date" value={cFrom} onChange={e => setCFrom(e.target.value)}
                style={{ padding: '3px 7px', background: '#11141a', border: '1px solid #2a3142', borderRadius: 6, color: '#e0e0e0', fontSize: 11, outline: 'none' }} />
              <span style={{ color: '#667', fontSize: 11 }}>→</span>
              <input type="date" value={cTo} onChange={e => setCTo(e.target.value)}
                style={{ padding: '3px 7px', background: '#11141a', border: '1px solid #2a3142', borderRadius: 6, color: '#e0e0e0', fontSize: 11, outline: 'none' }} />
            </span>
          )}
        </div>
        {/* commission KPIs (the headline ones) + operational */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8, marginBottom: 8 }}>
          <Kpi label="Company markup" value={fmtUSD(kpis.total_commission)} c="#00e5a0" hint="profit from all their clients" />
          <Kpi label="Paid to IBs" value={fmtUSD(kpis.total_ib_commission)} c="#ff8c00" hint="their clients' IB commission" />
          <Kpi label="Net (markup − IB)" value={fmtUSD(kpis.total_net_commission)} c="#00aaff" />
          <Kpi label="Sales commission (10%)" value={fmtUSD(kpis.total_sales_commission)} c="#cc88ff" hint="total we pay the sales team" />
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 8 }}>
          <Kpi label="Agents" value={fmtNum(kpis.total_agents)} c="#e6e9ef" />
          <Kpi label="Total clients" value={fmtNum(kpis.total_clients)} c="#00aaff" />
          <Kpi label="New clients" value={fmtNum(kpis.new_clients)} c="#00e5a0" />
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
              : agents.map((a, i) => {
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
                        <button onClick={(e) => { e.stopPropagation(); setXferSource(capAgents.find(x => x.id === a.id) || { ...a, clients: a.clients }); }}
                          title="Bulk transfer this agent's clients / leads"
                          style={{ background: '#2c333e', border: '1px solid #3a4150', color: '#00aaff', borderRadius: 6, padding: '3px 8px', fontSize: 12, cursor: 'pointer' }}>⇄</button>
                      </div>
                    </td>
                    <td style={{ ...CT.td, textAlign: 'right', color: '#00aaff', fontWeight: 600 }}>{fmtNum(a.clients)}</td>
                    <td style={{ ...CT.td, textAlign: 'right', color: a.new_clients ? '#00e5a0' : '#445' }}>{fmtNum(a.new_clients)}</td>
                    <td style={{ ...CT.td, textAlign: 'right', color: '#cc88ff' }}>{fmtNum(a.leads)}</td>
                    <td style={{ ...CT.td, textAlign: 'right', color: '#ffaa00', fontWeight: 600 }}>{fmtNum(a.ibs)}</td>
                    <td style={{ ...CT.td, textAlign: 'right', color: '#00e5a0' }}>{fmtUSD(a.deposits)}</td>
                    <td style={{ ...CT.td, textAlign: 'right', color: '#ff5d6c' }}>{fmtUSD(a.withdrawals)}</td>
                    <td style={{ ...CT.td, textAlign: 'right', color: '#00e5a0', fontWeight: 600 }}>{fmtUSD(a.commission)}</td>
                    <td style={{ ...CT.td, textAlign: 'right', color: '#ff8c00' }}>{fmtUSD(a.ib_commission)}</td>
                    <td style={{ ...CT.td, textAlign: 'right', color: '#00aaff', fontWeight: 600 }}>{fmtUSD(a.net_commission)}</td>
                    <td style={{ ...CT.td, textAlign: 'right', color: '#cc88ff', fontWeight: 700 }}>{fmtUSD(a.sales_commission)}</td>
                  </tr>
                );
              })}
            {!loading && agents.length > 0 && (
              <tr style={{ ...CT.row(), background: '#262c36', position: 'sticky', bottom: 0 }}>
                <td style={{ ...CT.td, color: '#e6e9ef', fontWeight: 800 }}>TOTAL · {agents.length} agents</td>
                <td style={{ ...CT.td, textAlign: 'right', color: '#00aaff', fontWeight: 700 }}>{fmtNum(tot.clients)}</td>
                <td style={{ ...CT.td, textAlign: 'right', color: '#00e5a0', fontWeight: 700 }}>{fmtNum(tot.new_clients)}</td>
                <td style={{ ...CT.td, textAlign: 'right', color: '#cc88ff', fontWeight: 700 }}>{fmtNum(tot.leads)}</td>
                <td style={{ ...CT.td, textAlign: 'right', color: '#ffaa00', fontWeight: 700 }}>{fmtNum(tot.ibs)}</td>
                <td style={{ ...CT.td, textAlign: 'right', color: '#00e5a0', fontWeight: 700 }}>{fmtUSD(tot.deposits)}</td>
                <td style={{ ...CT.td, textAlign: 'right', color: '#ff5d6c', fontWeight: 700 }}>{fmtUSD(tot.withdrawals)}</td>
                <td style={{ ...CT.td, textAlign: 'right', color: '#00e5a0', fontWeight: 700 }}>{fmtUSD(tot.commission)}</td>
                <td style={{ ...CT.td, textAlign: 'right', color: '#ff8c00', fontWeight: 700 }}>{fmtUSD(tot.ib_commission)}</td>
                <td style={{ ...CT.td, textAlign: 'right', color: '#00aaff', fontWeight: 700 }}>{fmtUSD(tot.net_commission)}</td>
                <td style={{ ...CT.td, textAlign: 'right', color: '#cc88ff', fontWeight: 800 }}>{fmtUSD(tot.sales_commission)}</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <div style={{ padding: '6px 16px', borderTop: '1px solid #373f4d', fontSize: 10, color: '#556', flexShrink: 0 }}>
        Markup = company profit from the agent's clients' trades · IB comm = paid to those clients' IBs · Net = markup − IB · Sales = Net × the agent's % (default 10%). Click a row for full details &amp; target.
      </div>
      {openAgent && <AgentDetail agentId={openAgent} period={period} onClose={() => setOpenAgent(null)} />}
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

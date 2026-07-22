import React, { useState, useMemo, useEffect } from 'react';
import { apiGet, apiPost } from './api';

/* Bulk transfer / auto-distribute of a sales agent's clients or leads to other agents.
   Backend: /transfer/preview, /transfer/bulk, /transfer/auto-distribute. Caps (TL 300 /
   retention 1000) are enforced server-side; we surface remaining capacity per target. */

const lbl: React.CSSProperties = { fontSize: 10.5, color: '#8a93a3', textTransform: 'uppercase', letterSpacing: .4, fontWeight: 700, marginBottom: 5, display: 'block' };
const inp: React.CSSProperties = { width: '100%', padding: '8px 10px', background: '#11141a', border: '1px solid #2a3142', borderRadius: 7, color: '#e6e9ef', fontSize: 12.5, outline: 'none', boxSizing: 'border-box' };
const card: React.CSSProperties = { background: '#262c36', border: '1px solid #373f4d', borderRadius: 10, padding: 14, marginBottom: 12 };

export default function TransferModal({ source, agents, onClose, onDone }:
  { source: any; agents: any[]; onClose: () => void; onDone: () => void }) {
  const [rtype, setRtype] = useState<'client' | 'lead'>('client');
  const [count, setCount] = useState('100');
  const [order, setOrder] = useState('newest');           // newest|oldest|no_deposit
  const [noDepDays, setNoDepDays] = useState('');
  const [country, setCountry] = useState('');
  const [city, setCity] = useState('');
  const [ib, setIb] = useState('');                        // ''|yes|no
  const [lastActDays, setLastActDays] = useState('');
  const [exOwnClient, setExOwnClient] = useState(false);
  const [exOwnLeads, setExOwnLeads] = useState(false);
  const [exOwnIb, setExOwnIb] = useState(false);

  const [mode, setMode] = useState<'pick' | 'auto'>('pick');
  const [scope, setScope] = useState('internal');         // internal|external|all
  const [allocBy, setAllocBy] = useState<'count' | 'pct'>('pct');
  const [picked, setPicked] = useState<Record<number, string>>({});   // agentId -> count/pct value
  const [targetScope, setTargetScope] = useState('all');  // which agents to list: internal|external|all
  const [search, setSearch] = useState('');
  const [reason, setReason] = useState('');

  const [preview, setPreview] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('');
  const [book, setBook] = useState<any>({ total: 0, countries: [], cities: [] });   // agent's full book + dropdown options
  const [matched, setMatched] = useState<number | null>(null);                      // live filtered count

  const filters = () => {
    const f: any = { count: Number(count) || 0, order };
    if (noDepDays) f.no_deposit_days = Number(noDepDays);
    if (country) f.country = country.trim();
    if (city) f.city = city.trim();
    if (rtype === 'client' && ib) f.ib = ib;
    if (lastActDays) f.last_activity_days = Number(lastActDays);
    f.exclude_own_client = exOwnClient; f.exclude_own_leads = exOwnLeads; f.exclude_own_ib = exOwnIb;
    return f;
  };

  // the team-leader that defines the source's team (TL → itself; otherwise its manager)
  const tlId = (source.team_type === 'lead' || (source.role || '').toLowerCase() === 'sales_manager') ? source.id : source.manager_id;

  // full book + country/city options when the record type changes
  useEffect(() => {
    setMatched(null); setCountry(''); setCity('');
    apiGet(`/transfer/book?agent_id=${source.id}&record_type=${rtype}`).then(setBook).catch(() => setBook({ total: 0, countries: [], cities: [] }));
  }, [rtype, source.id]);

  // live filtered count (debounced) as the filters change
  useEffect(() => {
    const t = setTimeout(() => {
      apiPost('/transfer/preview', { from_agent_id: source.id, record_type: rtype, filters: { ...filters(), count: 0 } })
        .then((r: any) => setMatched(r.matched)).catch(() => setMatched(null));
    }, 400);
    return () => clearTimeout(t);
    // eslint-disable-next-line
  }, [rtype, order, noDepDays, country, city, ib, lastActDays, source.id]);

  // target agent list: exclude source; restrict to same-team / other-team (defined by the team leader);
  // and by record type (leads → sales agents, clients → retention + team leaders).
  const targetAgents = useMemo(() => {
    let list = agents.filter(a => a.id !== source.id);
    list = list.filter(a => rtype === 'lead' ? a.team_type === 'sales' : (a.team_type === 'retention' || a.team_type === 'lead'));
    const inTeam = (a: any) => a.manager_id === tlId || a.id === tlId;
    if (targetScope === 'internal') list = list.filter(inTeam);
    else if (targetScope === 'external') list = list.filter(a => !inTeam(a));
    if (search) list = list.filter(a => (a.name || '').toLowerCase().includes(search.toLowerCase()));
    return list;
  }, [agents, source, targetScope, search, rtype, tlId]);

  const pickedTargets = () => Object.entries(picked)
    .filter(([, v]) => Number(v) > 0)
    .map(([id, v]) => allocBy === 'pct' ? { agent_id: Number(id), pct: Number(v) } : { agent_id: Number(id), count: Number(v) });

  const pctTotal = allocBy === 'pct' ? Object.values(picked).reduce((s, v) => s + (Number(v) || 0), 0) : 0;

  const doPreview = async () => {
    setBusy(true); setMsg('');
    try {
      const body: any = { from_agent_id: source.id, record_type: rtype, filters: filters() };
      if (mode === 'pick') body.targets = pickedTargets();
      const r = await apiPost('/transfer/preview', body);
      setPreview(r);
    } catch (e: any) { setMsg(e?.message || 'Preview failed'); }
    setBusy(false);
  };

  const execute = async () => {
    if (!reason.trim()) { setMsg('Please add a reason for the transfer.'); return; }
    if (mode === 'pick' && pickedTargets().length === 0) { setMsg('Pick at least one target agent with an amount.'); return; }
    if (!window.confirm(`Transfer ${rtype}s from ${source.name}? This reassigns real records and comments each one.`)) return;
    setBusy(true); setMsg('');
    try {
      if (mode === 'pick') {
        const r = await apiPost('/transfer/bulk', { from_agent_id: source.id, record_type: rtype, filters: filters(), targets: pickedTargets(), reason });
        setMsg(`✓ Transferred. ${(r.targets || []).map((t: any) => `${t.agent}: ${t.assigned}${t.skipped_over_cap ? ` (${t.skipped_over_cap} skipped — at cap)` : ''}`).join(' · ')}`);
      } else {
        const r = await apiPost('/transfer/auto-distribute', { from_agent_id: source.id, record_type: rtype, scope, filters: filters(), reason });
        setMsg(`✓ Auto-distributed ${r.matched} to ${(r.targets || []).length} agents (${scope}).`);
      }
      onDone();
    } catch (e: any) { setMsg(e?.message || 'Transfer failed'); }
    setBusy(false);
  };

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', zIndex: 9500, display: 'flex', justifyContent: 'center', alignItems: 'flex-start', overflow: 'auto', padding: '24px 12px' }} onClick={onClose}>
      <div onClick={e => e.stopPropagation()} style={{ width: 760, maxWidth: '96vw', background: '#20252f', border: '1px solid #373f4d', borderRadius: 14, padding: 20 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
          <div style={{ fontSize: 17, fontWeight: 800, color: '#e6e9ef' }}>⇄ Transfer from {source.name}</div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#889', fontSize: 22, cursor: 'pointer' }}>✕</button>
        </div>
        <div style={{ fontSize: 11, color: '#667', marginBottom: 14 }}>
          {source.team_type} · {source.clients} clients{source.cap ? ` (cap ${source.cap})` : ''}
        </div>

        {/* what + how much */}
        <div style={card}>
          <div style={{ fontSize: 12, color: '#9aa3b2', marginBottom: 10 }}>
            Book: <b style={{ color: '#00aaff' }}>{(book.total || 0).toLocaleString('en-GB')}</b> {rtype === 'client' ? 'clients' : 'leads'}
            {matched != null && <> · matching filters: <b style={{ color: '#00e5a0' }}>{matched.toLocaleString('en-GB')}</b></>}
          </div>
          <div style={{ display: 'flex', gap: 16, alignItems: 'flex-end', flexWrap: 'wrap' }}>
            <div>
              <span style={lbl}>Move</span>
              <div style={{ display: 'flex', gap: 6 }}>
                {(['client', 'lead'] as const).map(t => (
                  <button key={t} onClick={() => setRtype(t)} style={{ padding: '7px 14px', borderRadius: 7, fontSize: 12, cursor: 'pointer', fontWeight: 700,
                    border: `1px solid ${rtype === t ? '#00e5a0' : '#3a4150'}`, background: rtype === t ? 'rgba(0,229,160,0.12)' : '#11141a', color: rtype === t ? '#00e5a0' : '#9aa3b2' }}>{t === 'client' ? 'Clients' : 'Leads'}</button>
                ))}
              </div>
            </div>
            <div style={{ width: 110 }}><span style={lbl}>How many</span><input value={count} onChange={e => setCount(e.target.value.replace(/[^0-9]/g, ''))} style={inp} placeholder="100" /></div>
            <div style={{ width: 170 }}><span style={lbl}>Pick</span>
              <select value={order} onChange={e => setOrder(e.target.value)} style={inp}>
                <option value="all">All (ignore count)</option>
                <option value="newest">Newest first</option>
                <option value="oldest">Oldest first</option>
                {rtype === 'client' && <option value="no_deposit">No deposit</option>}
              </select>
            </div>
            {rtype === 'client' && <div style={{ width: 150 }}><span style={lbl}>No deposit for ≥ (days)</span><input value={noDepDays} onChange={e => setNoDepDays(e.target.value.replace(/[^0-9]/g, ''))} style={inp} placeholder="e.g. 30" /></div>}
            <div style={{ width: 150 }}><span style={lbl}>No activity for ≥ (days)</span><input value={lastActDays} onChange={e => setLastActDays(e.target.value.replace(/[^0-9]/g, ''))} style={inp} placeholder="e.g. 14" /></div>
          </div>
          <div style={{ display: 'flex', gap: 16, alignItems: 'flex-end', flexWrap: 'wrap', marginTop: 12 }}>
            <div style={{ width: 160 }}><span style={lbl}>Country ({book.countries?.length || 0})</span>
              <input value={country} onChange={e => setCountry(e.target.value)} style={inp} placeholder="search / any" list="xfer-countries" />
              <datalist id="xfer-countries">{(book.countries || []).map((c: string) => <option key={c} value={c} />)}</datalist>
            </div>
            <div style={{ width: 160 }}><span style={lbl}>City ({book.cities?.length || 0})</span>
              <input value={city} onChange={e => setCity(e.target.value)} style={inp} placeholder="search / any" list="xfer-cities" />
              <datalist id="xfer-cities">{(book.cities || []).map((c: string) => <option key={c} value={c} />)}</datalist>
            </div>
            {rtype === 'client' && <div style={{ width: 160 }}><span style={lbl}>Under an IB?</span>
              <select value={ib} onChange={e => setIb(e.target.value)} style={inp}>
                <option value="">Any</option><option value="yes">Under an IB</option><option value="no">Not under an IB</option>
              </select>
            </div>}
            <div style={{ display: 'flex', gap: 14, alignItems: 'center', fontSize: 11.5, color: '#9aa3b2', paddingBottom: 8 }}>
              <label style={{ display: 'flex', gap: 5, alignItems: 'center', cursor: 'pointer' }}><input type="checkbox" checked={exOwnIb} onChange={e => setExOwnIb(e.target.checked)} />Keep own-IB data <span title="own-IB mapping coming soon" style={{ color: '#667' }}>ⓘ</span></label>
              <label style={{ display: 'flex', gap: 5, alignItems: 'center', cursor: 'pointer' }}><input type="checkbox" checked={exOwnClient} onChange={e => setExOwnClient(e.target.checked)} />Keep own clients</label>
              <label style={{ display: 'flex', gap: 5, alignItems: 'center', cursor: 'pointer' }}><input type="checkbox" checked={exOwnLeads} onChange={e => setExOwnLeads(e.target.checked)} />Keep own leads</label>
            </div>
          </div>
        </div>

        {/* where to */}
        <div style={card}>
          <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
            {(['pick', 'auto'] as const).map(m => (
              <button key={m} onClick={() => setMode(m)} style={{ flex: 1, padding: '8px', borderRadius: 7, fontSize: 12, fontWeight: 700, cursor: 'pointer',
                border: `1px solid ${mode === m ? '#00aaff' : '#3a4150'}`, background: mode === m ? 'rgba(0,170,255,0.12)' : '#11141a', color: mode === m ? '#00aaff' : '#9aa3b2' }}>
                {m === 'pick' ? 'Selected agents (count / %)' : 'Auto-distribute evenly'}</button>
            ))}
          </div>

          {mode === 'auto' ? (
            <div>
              <span style={lbl}>Distribute across</span>
              <div style={{ display: 'flex', gap: 6 }}>
                {[['internal', 'Internal team'], ['external', 'External teams'], ['all', 'All company agents']].map(([v, l]) => (
                  <button key={v} onClick={() => setScope(v)} style={{ padding: '7px 12px', borderRadius: 7, fontSize: 12, cursor: 'pointer', fontWeight: 700,
                    border: `1px solid ${scope === v ? '#00e5a0' : '#3a4150'}`, background: scope === v ? 'rgba(0,229,160,0.12)' : '#11141a', color: scope === v ? '#00e5a0' : '#9aa3b2' }}>{l}</button>
                ))}
              </div>
              <div style={{ fontSize: 11, color: '#667', marginTop: 8 }}>Evenly round-robins the matched records across every agent in scope, skipping anyone at their client cap.</div>
            </div>
          ) : (
            <>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
                <select value={targetScope} onChange={e => setTargetScope(e.target.value)} style={{ ...inp, width: 150 }}>
                  <option value="all">All company</option><option value="internal">Internal team</option><option value="external">External teams</option>
                </select>
                <select value={allocBy} onChange={e => setAllocBy(e.target.value as any)} style={{ ...inp, width: 130 }}>
                  <option value="pct">By %</option><option value="count">By count</option>
                </select>
                <input value={search} onChange={e => setSearch(e.target.value)} placeholder="search agent…" style={{ ...inp, flex: 1 }} />
                {allocBy === 'pct' && <span style={{ fontSize: 11, color: pctTotal === 100 ? '#00e5a0' : '#ffaa00', whiteSpace: 'nowrap' }}>Σ {pctTotal}%</span>}
              </div>
              <div style={{ maxHeight: 200, overflow: 'auto', border: '1px solid #2a3142', borderRadius: 8 }}>
                {targetAgents.map(a => (
                  <div key={a.id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 10px', borderBottom: '1px solid #222831' }}>
                    <div style={{ flex: 1, fontSize: 12 }}>
                      <span style={{ color: '#e6e9ef' }}>{a.name}</span>
                      <span style={{ color: '#667', fontSize: 10 }}> · {a.team_type} · {a.clients}{a.cap ? `/${a.cap}` : ''}{a.at_cap ? ' ⛔ at cap' : a.remaining != null ? ` (${a.remaining} left)` : ''}</span>
                    </div>
                    <input value={picked[a.id] || ''} onChange={e => setPicked(p => ({ ...p, [a.id]: e.target.value.replace(/[^0-9]/g, '') }))}
                      placeholder={allocBy === 'pct' ? '%' : 'n'} style={{ ...inp, width: 70, padding: '5px 8px' }} />
                  </div>
                ))}
              </div>
            </>
          )}
        </div>

        <div style={card}>
          <span style={lbl}>Reason (added as a comment on every transferred record) *</span>
          <input value={reason} onChange={e => setReason(e.target.value)} style={inp} placeholder="e.g. rebalancing workload / agent left / campaign follow-up" />
        </div>

        {preview && (
          <div style={{ ...card, background: '#11141a' }}>
            <div style={{ fontSize: 12, color: '#9aa3b2', marginBottom: 6 }}>Preview — <b style={{ color: '#00e5a0' }}>{preview.matched}</b> {rtype}s match.</div>
            {(preview.targets || []).map((t: any, i: number) => (
              <div key={i} style={{ fontSize: 11.5, color: '#cdd4de' }}>→ {t.agent}: <b>{t.assigned}</b>{t.skipped_over_cap ? <span style={{ color: '#ffaa00' }}> ({t.skipped_over_cap} skipped — at cap)</span> : ''}</div>
            ))}
          </div>
        )}
        {msg && <div style={{ fontSize: 12, color: msg.startsWith('✓') ? '#00e5a0' : '#ff8a8a', marginBottom: 10 }}>{msg}</div>}

        <div style={{ display: 'flex', gap: 8 }}>
          <button onClick={doPreview} disabled={busy} style={{ flex: '0 0 auto', padding: '11px 18px', borderRadius: 9, background: '#373f4d', border: '1px solid #4f596b', color: '#e6e9ef', fontWeight: 700, fontSize: 13, cursor: 'pointer' }}>{busy ? '…' : '👁 Preview'}</button>
          <button onClick={execute} disabled={busy} style={{ flex: 1, padding: '11px 18px', borderRadius: 9, background: '#00e5a0', border: 'none', color: '#0a0c10', fontWeight: 800, fontSize: 13, cursor: 'pointer' }}>{busy ? '…' : 'Go ahead — transfer'}</button>
        </div>
      </div>
    </div>
  );
}

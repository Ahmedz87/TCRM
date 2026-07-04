import React, { useState, useEffect, useCallback } from 'react';
import { apiGet, apiPost, apiPatch, apiDelete } from './api';

// ── Leads Settings: rule-based lead assignment ──────────────────────────────
// Desk builds ordered rules (higher priority wins). Each rule routes leads matching
// its criteria (country/city/campaign/source/IB/timing) to a set of sales agents
// (round-robin). If no rule matches, an IB lead falls back to the IB's managing agent.

type Agent = { id: number; name: string; role?: string };
type Ib = { id: number; name: string };
type Options = { countries: string[]; cities: string[]; campaigns: string[]; sources: string[]; ibs: Ib[]; agents: Agent[] };
type Timing = { days?: number[]; from?: string; to?: string };
type Criteria = { countries?: string[]; cities?: string[]; campaigns?: string[]; sources?: string[]; ib_ids?: number[]; timing?: Timing };
type Rule = { id: number; name: string; priority: number; is_active: boolean; criteria: Criteria; agent_ids: number[]; agents?: Agent[] };
type Config = { auto_assign_enabled: boolean; ib_default_enabled: boolean; fallback_agent_id: number | null; tz_offset: number };

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

const card: React.CSSProperties = { background: '#2c333e', border: '1px solid #4f596b', borderRadius: 12, padding: 18, marginBottom: 16 };
const cap: React.CSSProperties = { fontSize: 11, color: '#8a93a5', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 12, fontWeight: 700 };
const input: React.CSSProperties = { padding: '8px 10px', background: '#1c2231', border: '1px solid #3a4252', borderRadius: 8, color: '#e6e9ef', fontSize: 13 };
const btn = (bg: string, fg = '#06251b'): React.CSSProperties => ({ padding: '9px 14px', background: bg, border: 'none', borderRadius: 8, color: fg, fontSize: 13, fontWeight: 700, cursor: 'pointer' });

// ── reusable searchable multi-select (chips) ──
function MultiSelect({ options, value, onChange, placeholder, render }:
  { options: { v: string; label: string }[]; value: string[]; onChange: (v: string[]) => void; placeholder: string; render?: (v: string) => string }) {
  const [q, setQ] = useState('');
  const [open, setOpen] = useState(false);
  const sel = new Set(value);
  const filtered = options.filter(o => !sel.has(o.v) && o.label.toLowerCase().includes(q.toLowerCase())).slice(0, 40);
  return (
    <div style={{ position: 'relative' }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 6 }}>
        {value.map(v => (
          <span key={v} style={{ background: '#00e5a022', border: '1px solid #00e5a055', color: '#00e5a0', borderRadius: 6, padding: '3px 8px', fontSize: 12, display: 'flex', gap: 6, alignItems: 'center' }}>
            {render ? render(v) : v}
            <span onClick={() => onChange(value.filter(x => x !== v))} style={{ cursor: 'pointer', color: '#9aa3b3' }}>✕</span>
          </span>
        ))}
      </div>
      <input value={q} placeholder={placeholder} onChange={e => { setQ(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)} onBlur={() => setTimeout(() => setOpen(false), 150)}
        style={{ ...input, width: '100%', boxSizing: 'border-box' }} />
      {open && filtered.length > 0 && (
        <div style={{ position: 'absolute', zIndex: 30, top: '100%', left: 0, right: 0, background: '#222936', border: '1px solid #3a4252', borderRadius: 8, marginTop: 4, maxHeight: 220, overflowY: 'auto', boxShadow: '0 8px 24px #0008' }}>
          {filtered.map(o => (
            <div key={o.v} onMouseDown={() => { onChange([...value, o.v]); setQ(''); }}
              style={{ padding: '8px 10px', fontSize: 13, color: '#cfd6e4', cursor: 'pointer', borderBottom: '1px solid #2c333e' }}
              onMouseEnter={e => (e.currentTarget.style.background = '#2c333e')}
              onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}>{o.label}</div>
          ))}
        </div>
      )}
    </div>
  );
}

function criteriaSummary(c: Criteria, opts: Options | null): string {
  const parts: string[] = [];
  if (c.countries?.length) parts.push(`Country: ${c.countries.join(', ')}`);
  if (c.cities?.length) parts.push(`City: ${c.cities.join(', ')}`);
  if (c.sources?.length) parts.push(`Source: ${c.sources.join(', ')}`);
  if (c.campaigns?.length) parts.push(`Campaign: ${c.campaigns.length} selected`);
  if (c.ib_ids?.length) {
    const names = c.ib_ids.map(id => opts?.ibs.find(i => i.id === id)?.name || `#${id}`);
    parts.push(`IB: ${names.slice(0, 2).join(', ')}${names.length > 2 ? '…' : ''}`);
  }
  if (c.timing && (c.timing.days?.length || c.timing.from)) {
    const d = c.timing.days?.length ? c.timing.days.map(i => DAYS[i]).join('/') : 'any day';
    const t = c.timing.from ? `${c.timing.from}–${c.timing.to || '24:00'}` : '';
    parts.push(`Timing: ${d} ${t}`.trim());
  }
  return parts.length ? parts.join('  ·  ') : 'Any lead (no filters)';
}

export default function LeadsSettings() {
  const [opts, setOpts] = useState<Options | null>(null);
  const [rules, setRules] = useState<Rule[]>([]);
  const [config, setConfig] = useState<Config | null>(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<Rule | null>(null);
  const [applyResult, setApplyResult] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('');

  const load = useCallback(() => {
    setLoading(true);
    Promise.all([
      apiGet('/settings/leads/options'),
      apiGet('/settings/leads/rules'),
      apiGet('/settings/leads/config'),
    ]).then(([o, r, c]) => {
      setOpts(o); setRules(r.rules || []); setConfig(c);
    }).catch(() => setMsg('Failed to load')).finally(() => setLoading(false));
  }, []);
  useEffect(() => { load(); }, [load]);

  const flash = (m: string) => { setMsg(m); setTimeout(() => setMsg(''), 3000); };

  const saveConfig = async (patch: Partial<Config>) => {
    const next = { ...(config as Config), ...patch };
    setConfig(next);
    await apiPost('/settings/leads/config', next).catch(() => {});
  };

  const toggleActive = async (r: Rule) => {
    await apiPatch(`/settings/leads/rules/${r.id}`, { is_active: !r.is_active }).catch(() => {});
    load();
  };
  const removeRule = async (r: Rule) => {
    if (!window.confirm(`Delete rule "${r.name}"?`)) return;
    await apiDelete(`/settings/leads/rules/${r.id}`).catch(() => {});
    load();
  };

  const applyToExisting = async (dry: boolean) => {
    setBusy(true); setApplyResult(null);
    try {
      const r = await apiPost('/settings/leads/apply', { only_unassigned: true, dry_run: dry });
      setApplyResult({ ...r, dry });
      if (!dry) { flash('Applied to existing leads'); load(); }
    } catch { flash('Apply failed'); }
    setBusy(false);
  };

  if (loading) return <div style={{ color: '#888', padding: 40, textAlign: 'center' }}>Loading leads settings…</div>;

  return (
    <div style={{ maxWidth: 1000 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <h2 style={{ color: '#e6e9ef', margin: 0, fontSize: 22 }}>🎯 Leads Settings — assignment rules</h2>
        <button onClick={() => setEditing({ id: 0, name: '', priority: 100, is_active: true, criteria: {}, agent_ids: [] })} style={btn('#00e5a0')}>+ New rule</button>
      </div>
      <p style={{ color: '#8a93a5', fontSize: 13, marginTop: 0, marginBottom: 16 }}>
        Leads are routed to sales agents by these rules, evaluated <b>highest priority first</b> — the first matching rule wins.
        A rule assigns to its agents in round-robin. If no rule matches, an IB lead goes to its IB's managing agent.
      </p>
      {msg && <div style={{ background: '#00e5a022', color: '#00e5a0', padding: '8px 12px', borderRadius: 8, marginBottom: 12, fontSize: 13 }}>{msg}</div>}

      {/* config */}
      <div style={card}>
        <div style={cap}>⚙️ Routing configuration</div>
        <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', alignItems: 'center' }}>
          <label style={{ display: 'flex', gap: 8, alignItems: 'center', color: '#cfd6e4', fontSize: 13, cursor: 'pointer' }}>
            <input type="checkbox" checked={config?.auto_assign_enabled} onChange={e => saveConfig({ auto_assign_enabled: e.target.checked })} />
            Auto-assign new leads on arrival
          </label>
          <label style={{ display: 'flex', gap: 8, alignItems: 'center', color: '#cfd6e4', fontSize: 13, cursor: 'pointer' }}>
            <input type="checkbox" checked={config?.ib_default_enabled} onChange={e => saveConfig({ ib_default_enabled: e.target.checked })} />
            IB default (IB leads → the IB's managing agent when no rule matches)
          </label>
          <label style={{ display: 'flex', gap: 8, alignItems: 'center', color: '#cfd6e4', fontSize: 13 }}>
            Timing timezone UTC
            <input type="number" value={config?.tz_offset ?? 3} onChange={e => saveConfig({ tz_offset: parseInt(e.target.value) || 0 })} style={{ ...input, width: 56 }} />
          </label>
          <label style={{ display: 'flex', gap: 8, alignItems: 'center', color: '#cfd6e4', fontSize: 13 }}>
            Fallback agent
            <select value={config?.fallback_agent_id ?? ''} onChange={e => saveConfig({ fallback_agent_id: e.target.value ? parseInt(e.target.value) : null })} style={{ ...input }}>
              <option value="">— none —</option>
              {opts?.agents.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
          </label>
        </div>
        <div style={{ marginTop: 14, display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          <button onClick={() => applyToExisting(true)} disabled={busy} style={btn('#3a4252', '#cfd6e4')}>Preview apply to existing</button>
          <button onClick={() => applyToExisting(false)} disabled={busy} style={btn('#ffaa00')}>Apply to existing unassigned leads</button>
          {applyResult && (
            <span style={{ color: '#cfd6e4', fontSize: 13 }}>
              {applyResult.dry ? 'Would assign' : 'Assigned'} <b style={{ color: '#00e5a0' }}>{applyResult.assigned}</b> of {applyResult.scanned}
              &nbsp;(by rule {applyResult.by_rule}, by IB {applyResult.by_ib}, unmatched {applyResult.unassigned})
            </span>
          )}
        </div>
      </div>

      {/* rules list */}
      <div style={card}>
        <div style={cap}>📋 Rules ({rules.length}) — priority order</div>
        {rules.length === 0 && <div style={{ color: '#8a93a5', fontSize: 13 }}>No rules yet. Create one to start routing leads.</div>}
        {rules.map(r => (
          <div key={r.id} style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '12px 0', borderBottom: '1px solid #373f4d', opacity: r.is_active ? 1 : 0.5 }}>
            <div style={{ width: 44, textAlign: 'center' }}>
              <div style={{ fontSize: 18, fontWeight: 800, color: '#00e5a0' }}>{r.priority}</div>
              <div style={{ fontSize: 9, color: '#8a93a5', textTransform: 'uppercase' }}>priority</div>
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 14, fontWeight: 700, color: '#e6e9ef' }}>{r.name}</div>
              <div style={{ fontSize: 12, color: '#8a93a5', marginTop: 2 }}>{criteriaSummary(r.criteria, opts)}</div>
              <div style={{ fontSize: 12, color: '#79b8ff', marginTop: 4 }}>
                → {(r.agents || []).map(a => a.name).join(', ') || '—'}
              </div>
            </div>
            <button onClick={() => toggleActive(r)} style={{ ...btn(r.is_active ? '#00e5a022' : '#3a4252', r.is_active ? '#00e5a0' : '#9aa3b3'), padding: '5px 10px', fontSize: 12 }}>{r.is_active ? 'Active' : 'Off'}</button>
            <button onClick={() => setEditing(r)} style={{ ...btn('#3a4252', '#cfd6e4'), padding: '5px 10px', fontSize: 12 }}>Edit</button>
            <button onClick={() => removeRule(r)} style={{ ...btn('#ff5d6c22', '#ff5d6c'), padding: '5px 10px', fontSize: 12 }}>Delete</button>
          </div>
        ))}
      </div>

      {editing && opts && (
        <RuleEditor rule={editing} opts={opts} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load(); flash('Rule saved'); }} />
      )}
    </div>
  );
}

// ── rule create/edit modal ──
function RuleEditor({ rule, opts, onClose, onSaved }: { rule: Rule; opts: Options; onClose: () => void; onSaved: () => void }) {
  const [name, setName] = useState(rule.name);
  const [priority, setPriority] = useState(rule.priority);
  const [crit, setCrit] = useState<Criteria>(rule.criteria || {});
  const [agentIds, setAgentIds] = useState<number[]>(rule.agent_ids || []);
  const [preview, setPreview] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');

  const setC = (patch: Partial<Criteria>) => setCrit(c => ({ ...c, ...patch }));
  const timing = crit.timing || {};
  const setTiming = (patch: Partial<Timing>) => setC({ timing: { ...timing, ...patch } });

  // live preview count (debounced)
  useEffect(() => {
    const h = setTimeout(() => {
      apiPost('/settings/leads/preview', { criteria: crit }).then(r => setPreview(r.matches)).catch(() => setPreview(null));
    }, 400);
    return () => clearTimeout(h);
  }, [crit]);

  const save = async () => {
    if (!name.trim()) { setErr('Give the rule a name'); return; }
    if (agentIds.length === 0) { setErr('Pick at least one sales agent'); return; }
    setSaving(true); setErr('');
    const body = { name, priority, criteria: crit, agent_ids: agentIds, is_active: rule.is_active };
    try {
      if (rule.id) await apiPatch(`/settings/leads/rules/${rule.id}`, body);
      else await apiPost('/settings/leads/rules', body);
      onSaved();
    } catch (e: any) { setErr(e?.message || 'Save failed'); setSaving(false); }
  };

  const toStr = (a: string[]) => a;

  return (
    <div onClick={onClose} style={{ position: 'fixed', inset: 0, background: '#0009', zIndex: 100, display: 'flex', justifyContent: 'center', alignItems: 'flex-start', overflowY: 'auto', padding: '40px 16px' }}>
      <div onClick={e => e.stopPropagation()} style={{ background: '#222936', border: '1px solid #4f596b', borderRadius: 14, padding: 24, width: 640, maxWidth: '100%' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <h3 style={{ color: '#e6e9ef', margin: 0 }}>{rule.id ? 'Edit rule' : 'New rule'}</h3>
          <span onClick={onClose} style={{ cursor: 'pointer', color: '#8a93a5', fontSize: 22 }}>✕</span>
        </div>

        <div style={{ display: 'flex', gap: 12, marginBottom: 16 }}>
          <div style={{ flex: 1 }}>
            <div style={cap}>Rule name</div>
            <input value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Iraqi Facebook leads" style={{ ...input, width: '100%', boxSizing: 'border-box' }} />
          </div>
          <div style={{ width: 120 }}>
            <div style={cap}>Priority</div>
            <input type="number" value={priority} onChange={e => setPriority(parseInt(e.target.value) || 0)} style={{ ...input, width: '100%', boxSizing: 'border-box' }} />
          </div>
        </div>

        <div style={cap}>Match leads where… <span style={{ textTransform: 'none', color: '#8a93a5', letterSpacing: 0 }}>(leave a filter empty = any)</span></div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginBottom: 12 }}>
          <Field label="Country">
            <MultiSelect placeholder="Add country…" value={crit.countries || []} onChange={v => setC({ countries: toStr(v) })}
              options={opts.countries.map(c => ({ v: c, label: c }))} />
          </Field>
          <Field label="City">
            <MultiSelect placeholder="Add city…" value={crit.cities || []} onChange={v => setC({ cities: toStr(v) })}
              options={opts.cities.map(c => ({ v: c, label: c }))} />
          </Field>
          <Field label="Source">
            <MultiSelect placeholder="Add source…" value={crit.sources || []} onChange={v => setC({ sources: toStr(v) })}
              options={opts.sources.map(s => ({ v: s, label: s.charAt(0).toUpperCase() + s.slice(1) }))} />
          </Field>
          <Field label="Specific IB">
            <MultiSelect placeholder="Add IB…" value={(crit.ib_ids || []).map(String)} onChange={v => setC({ ib_ids: v.map(Number) })}
              render={v => opts.ibs.find(i => i.id === Number(v))?.name || `#${v}`}
              options={opts.ibs.map(i => ({ v: String(i.id), label: i.name }))} />
          </Field>
        </div>
        <Field label="Campaign (form)">
          <MultiSelect placeholder="Add campaign…" value={crit.campaigns || []} onChange={v => setC({ campaigns: toStr(v) })}
            options={opts.campaigns.map(c => ({ v: c, label: c }))} />
        </Field>

        {/* timing */}
        <div style={{ marginTop: 12 }}>
          <div style={cap}>Timing (lead arrival)</div>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 8 }}>
            {DAYS.map((d, i) => {
              const on = (timing.days || []).includes(i);
              return <span key={d} onClick={() => setTiming({ days: on ? (timing.days || []).filter(x => x !== i) : [...(timing.days || []), i] })}
                style={{ cursor: 'pointer', padding: '5px 10px', borderRadius: 7, fontSize: 12, fontWeight: 600, background: on ? '#00e5a022' : '#1c2231', color: on ? '#00e5a0' : '#8a93a5', border: `1px solid ${on ? '#00e5a055' : '#3a4252'}` }}>{d}</span>;
            })}
          </div>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center', color: '#8a93a5', fontSize: 13 }}>
            From <input type="time" value={timing.from || ''} onChange={e => setTiming({ from: e.target.value })} style={input} />
            to <input type="time" value={timing.to || ''} onChange={e => setTiming({ to: e.target.value })} style={input} />
            <span style={{ fontSize: 11 }}>(leave blank for any time)</span>
          </div>
        </div>

        {/* assign to */}
        <div style={{ marginTop: 16 }}>
          <div style={cap}>Assign to sales agents <span style={{ textTransform: 'none', color: '#8a93a5', letterSpacing: 0 }}>(round-robin across the selected agents)</span></div>
          <MultiSelect placeholder="Add agent…" value={agentIds.map(String)} onChange={v => setAgentIds(v.map(Number))}
            render={v => opts.agents.find(a => a.id === Number(v))?.name || `#${v}`}
            options={opts.agents.map(a => ({ v: String(a.id), label: a.name }))} />
        </div>

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 20 }}>
          <span style={{ color: '#8a93a5', fontSize: 13 }}>
            {preview != null ? <>Matches <b style={{ color: '#00e5a0' }}>{preview.toLocaleString()}</b> existing leads</> : '…'}
          </span>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            {err && <span style={{ color: '#ff5d6c', fontSize: 12 }}>{err}</span>}
            <button onClick={onClose} style={btn('#3a4252', '#cfd6e4')}>Cancel</button>
            <button onClick={save} disabled={saving} style={btn('#00e5a0')}>{saving ? 'Saving…' : 'Save rule'}</button>
          </div>
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div style={{ fontSize: 12, color: '#cfd6e4', marginBottom: 6, fontWeight: 600 }}>{label}</div>
      {children}
    </div>
  );
}

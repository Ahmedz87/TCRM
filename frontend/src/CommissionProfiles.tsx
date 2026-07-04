import React, { useEffect, useState, useCallback } from 'react';
import { apiGet, apiPost, apiPut, apiDelete } from './api';

// IB commission "Profile Configurations" — mirrors the broker's MT5 screen.
// A profile (name, ib_level, platform) holds a flat list of rules; on a closed trade the
// LOWEST-priority matching rule wins; commission = lots × value × point-value (or lots × value
// for USD-per-lot). Lets you Add / Edit / Delete profiles and rules + live-preview a symbol.

type Profile = { id: number; name: string; ib_level: number | null; platform: string; rule_count: number };
type Rule = { serial?: number; id: number; name: string; priority: number; symbols: string; distribution: string; value: number };

const DIST = [['pips', 'Pips'], ['usd_per_lot', 'USD Per Lot']];
const blankRule = (): Rule => ({ id: 0, name: '', priority: 20, symbols: '*', distribution: 'pips', value: 0 });

export default function CommissionProfiles() {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [pid, setPid] = useState<number | null>(null);
  const [rules, setRules] = useState<Rule[]>([]);
  const [profileName, setProfileName] = useState('');
  const [edit, setEdit] = useState<Rule | null>(null);     // rule being edited in the drawer
  const [msg, setMsg] = useState('');
  // preview
  const [pvSym, setPvSym] = useState('EURUSD');
  const [pvLots, setPvLots] = useState('1');
  const [pv, setPv] = useState<any>(null);

  const flash = (t: string) => { setMsg(t); setTimeout(() => setMsg(''), 2500); };

  const loadProfiles = useCallback(async () => {
    const d = await apiGet('/commission/profiles');
    setProfiles(d.profiles || []);
    if (d.profiles?.length && pid == null) setPid(d.profiles[0].id);
  }, [pid]);

  const loadRules = useCallback(async (id: number) => {
    const d = await apiGet(`/commission/profiles/${id}`);
    setRules(d.rules || []);
    setProfileName(d.name || '');
  }, []);

  useEffect(() => { loadProfiles(); }, [loadProfiles]);
  useEffect(() => { if (pid != null) loadRules(pid); }, [pid, loadRules]);

  // ── profile actions ──
  const addProfile = async () => {
    const name = prompt('Profile name (e.g. "0.5 pips Markup")', '');
    if (!name) return;
    const lvl = prompt('IB level (5-10)', '5'); if (!lvl) return;
    const d = await apiPost('/commission/profiles', { name, ib_level: Number(lvl), platform: 'MT5' });
    await loadProfiles(); if (d.id) setPid(d.id); flash('Profile created');
  };
  const renameProfile = async () => {
    if (pid == null) return;
    const name = prompt('Rename profile', profileName); if (!name) return;
    const p = profiles.find(x => x.id === pid);
    await apiPut(`/commission/profiles/${pid}`, { name, ib_level: p?.ib_level, platform: p?.platform || 'MT5' });
    await loadProfiles(); await loadRules(pid); flash('Saved');
  };
  const deleteProfile = async () => {
    if (pid == null) return;
    if (!window.confirm(`Delete profile "${profileName}" and ALL its rules?`)) return;
    await apiDelete(`/commission/profiles/${pid}`);
    setPid(null); setRules([]); await loadProfiles(); flash('Profile deleted');
  };

  // ── rule actions ──
  const saveRule = async () => {
    if (!edit || pid == null) return;
    const body = { name: edit.name, priority: Number(edit.priority), symbols: edit.symbols,
                   distribution: edit.distribution, value: Number(edit.value) };
    if (edit.id) await apiPut(`/commission/rules/${edit.id}`, body);
    else await apiPost(`/commission/profiles/${pid}/rules`, body);
    setEdit(null); await loadRules(pid); await loadProfiles(); flash('Rule saved');
  };
  const deleteRule = async (r: Rule) => {
    if (!window.confirm(`Delete rule "${r.name}" (priority ${r.priority})?`)) return;
    await apiDelete(`/commission/rules/${r.id}`); if (pid != null) await loadRules(pid); await loadProfiles();
    flash('Rule deleted');
  };

  const runPreview = async () => {
    const d = await apiPost('/commission/preview', { symbol: pvSym.trim(), lots: Number(pvLots) || 1, profile_id: pid });
    setPv(d);
  };

  const rowBg = (r: Rule) => (r.priority === 15 ? 'rgba(255,200,0,0.13)' : 'transparent');  // Zero = pending IB-mgr confirm

  const sorted = [...rules].sort((a, b) => a.priority - b.priority);
  const inp: React.CSSProperties = { width: '100%', padding: '9px 12px', borderRadius: 8, background: '#373f4d', border: '1px solid #2a2f3a', color: '#e8e8e8', fontSize: 13, boxSizing: 'border-box' };
  const lbl: React.CSSProperties = { fontSize: 11, color: '#8a93a3', marginBottom: 5, display: 'block', marginTop: 12 };

  return (
    <div style={{ color: '#e8e8e8', padding: 16, height: '100%', overflow: 'auto' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginBottom: 14 }}>
        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 600 }}>💰 Profile Configurations</h2>
        <span style={{ fontSize: 12, color: '#888' }}>IB commission rules · lowest priority wins · commission = lots × value × point-value</span>
        {msg && <span style={{ marginLeft: 'auto', fontSize: 12, color: '#00e5a0', background: 'rgba(0,229,160,0.1)', padding: '4px 10px', borderRadius: 6 }}>{msg}</span>}
      </div>

      <div style={{ fontSize: 11, color: '#caa53a', marginBottom: 10 }}>
        <span style={{ background: 'rgba(255,200,0,0.13)', padding: '2px 8px', borderRadius: 6 }}>🟡 Priority 15 (Zero)</span>
        &nbsp;highlighted = pending confirmation with the IB manager.
      </div>

      {/* Profile selector + actions */}
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 14, flexWrap: 'wrap' }}>
        <select value={pid ?? ''} onChange={e => setPid(Number(e.target.value))}
          style={{ ...inp, width: 'auto', minWidth: 260 }}>
          {profiles.map(p => <option key={p.id} value={p.id}>{p.name}{p.ib_level ? ` — IB-${p.ib_level}` : ' — tier'} · {p.platform} ({p.rule_count})</option>)}
        </select>
        <button onClick={addProfile} style={btn('#00e5a0')}>+ Add Profile</button>
        <button onClick={renameProfile} style={btn('#4d9fff')} disabled={pid == null}>✎ Rename</button>
        <button onClick={deleteProfile} style={btn('#ff5d6c')} disabled={pid == null}>🗑 Delete</button>
        <button onClick={() => setEdit(blankRule())} style={{ ...btn('#ffaa00'), marginLeft: 'auto' }} disabled={pid == null}>+ Add Rule</button>
      </div>

      {/* Rules table */}
      <div style={{ background: '#2c333e', border: '1px solid #4f596b', borderRadius: 10, overflow: 'hidden' }}>
        <div style={{ display: 'grid', gridTemplateColumns: '50px 70px 1fr 2fr 120px 80px 56px', gap: 8, padding: '10px 14px', fontSize: 10, color: '#667', textTransform: 'uppercase', borderBottom: '1px solid #4f596b' }}>
          <span>ID</span><span>Priority</span><span>Name</span><span>Symbols</span><span>Distribution</span><span style={{ textAlign: 'right' }}>Value</span><span></span>
        </div>
        {sorted.map(r => (
          <div key={r.id} onClick={() => setEdit({ ...r })}
            style={{ display: 'grid', gridTemplateColumns: '50px 70px 1fr 2fr 120px 80px 56px', gap: 8, padding: '11px 14px', fontSize: 12.5, borderBottom: '1px solid #373f4d', cursor: 'pointer', alignItems: 'center', background: rowBg(r) }}
            onMouseEnter={e => (e.currentTarget.style.background = r.priority === 15 ? 'rgba(255,200,0,0.22)' : '#161922')} onMouseLeave={e => (e.currentTarget.style.background = rowBg(r))}>
            <span style={{ color: '#7d8694', fontWeight: 600 }}>{r.serial ?? '—'}</span>
            <span><span style={{ background: 'rgba(77,159,255,0.12)', color: '#4d9fff', borderRadius: 6, padding: '2px 8px', fontWeight: 700 }}>{r.priority}</span></span>
            <span style={{ fontWeight: 600 }}>{r.name}</span>
            <span style={{ color: '#9aa3b3', fontFamily: 'monospace', fontSize: 11, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={r.symbols}>{r.symbols}</span>
            <span style={{ color: r.distribution === 'pips' ? '#00e5a0' : '#ffaa00' }}>{r.distribution === 'pips' ? 'Pips' : 'USD Per Lot'}</span>
            <span style={{ textAlign: 'right', fontWeight: 600 }}>{r.value}</span>
            <span style={{ textAlign: 'right' }}>
              <button onClick={e => { e.stopPropagation(); deleteRule(r); }} style={{ background: 'none', border: 'none', color: '#ff5d6c', cursor: 'pointer', fontSize: 14 }}>🗑</button>
            </span>
          </div>
        ))}
        {sorted.length === 0 && <div style={{ padding: 20, color: '#666', fontSize: 13 }}>No rules. Click “+ Add Rule”.</div>}
      </div>

      {/* Preview tester */}
      <div style={{ marginTop: 16, background: '#2c333e', border: '1px solid #4f596b', borderRadius: 10, padding: 14 }}>
        <div style={{ fontSize: 11, color: '#8a93a3', textTransform: 'uppercase', marginBottom: 8 }}>🧪 Commission preview</div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <input value={pvSym} onChange={e => setPvSym(e.target.value)} placeholder="symbol e.g. EURUSD.c" style={{ ...inp, width: 200 }} />
          <input value={pvLots} onChange={e => setPvLots(e.target.value)} placeholder="lots" style={{ ...inp, width: 90 }} />
          <button onClick={runPreview} style={btn('#4d9fff')}>Preview</button>
          {pv && (pv.matched
            ? <span style={{ fontSize: 13 }}>→ <b style={{ color: '#4d9fff' }}>{pv.rule}</b> (p{pv.priority}, {pv.distribution === 'pips' ? 'Pips' : 'USD/lot'} {pv.value}{pv.pip_usd != null ? `, point $${pv.pip_usd}` : ''}) = <b style={{ color: '#00e5a0' }}>{pv.commission_usd == null ? 'n/a (no symbol spec)' : `$${Number(pv.commission_usd).toFixed(4)}`}</b></span>
            : <span style={{ color: '#ff5d6c', fontSize: 13 }}>no matching rule</span>)}
        </div>
      </div>

      {/* Manage Profile Cog drawer */}
      {edit && (
        <div onClick={() => setEdit(null)} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', zIndex: 100, display: 'flex', justifyContent: 'flex-end' }}>
          <div onClick={e => e.stopPropagation()} style={{ width: 460, maxWidth: '95vw', height: '100%', overflowY: 'auto', background: '#262c36', borderLeft: '1px solid #4f596b', padding: 24 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
              <div style={{ fontSize: 18, fontWeight: 600 }}>Manage Profile Cog</div>
              <button onClick={() => setEdit(null)} style={{ background: 'none', border: 'none', color: '#888', fontSize: 22, cursor: 'pointer' }}>×</button>
            </div>
            <label style={lbl}>Name</label>
            <input style={inp} value={edit.name} onChange={e => setEdit({ ...edit, name: e.target.value })} />
            <label style={lbl}>Priority <span style={{ color: '#667' }}>(lowest number wins)</span></label>
            <input style={inp} type="number" value={edit.priority} onChange={e => setEdit({ ...edit, priority: Number(e.target.value) })} />
            <label style={lbl}>Profile Type</label>
            <input style={{ ...inp, color: '#888' }} value="Commission Trade Lot - CTL" disabled />
            <label style={lbl}>Symbols <span style={{ color: '#667' }}>(comma list; * = all, *.c/*.x/*.v/*. = account suffix)</span></label>
            <textarea style={{ ...inp, height: 90, resize: 'vertical', fontFamily: 'monospace' }} value={edit.symbols} onChange={e => setEdit({ ...edit, symbols: e.target.value })} />
            <label style={lbl}>Distribution</label>
            <select style={inp} value={edit.distribution} onChange={e => setEdit({ ...edit, distribution: e.target.value })}>
              {DIST.map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
            <label style={lbl}>{edit.distribution === 'pips' ? 'Pips (value)' : 'USD Per Lot (value)'}</label>
            <input style={inp} type="number" step="any" value={edit.value} onChange={e => setEdit({ ...edit, value: Number(e.target.value) })} />
            <button onClick={saveRule} style={{ ...btn('#00e5a0'), width: '100%', padding: '12px', marginTop: 20, fontSize: 14 }}>Save</button>
          </div>
        </div>
      )}
    </div>
  );
}

function btn(color: string): React.CSSProperties {
  return { padding: '8px 14px', borderRadius: 8, fontSize: 12.5, fontWeight: 600, cursor: 'pointer',
    background: `${color}1a`, border: `1px solid ${color}55`, color };
}

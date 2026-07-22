import React, { useState, useEffect } from 'react';
import { apiGet, apiPut } from './api';
import { CT } from './crmTable';

/* ── Challenge & career-path settings (staff only) ──────────────────────────
   ONE shared editor used by BOTH admin surfaces — my1 Dashboard (IB System →
   IB Challenges) and the partner1 admin workspace. It reads/writes the same
   /ib-portal/admin/challenge-defs endpoint (ibp_challenge_defs table), which
   every IB portal reads live — so a change made on either site applies to both
   and to what IBs see, immediately. */
const METRICS = [
  { v: 'ftd',      label: 'Funded clients (FTD)' },
  { v: 'lots',     label: 'Lots traded' },
  { v: 'deposits', label: 'Deposits $' },
  { v: 'regs',     label: 'New registrations' },
  { v: 'clicks',   label: 'Unique referral clicks' },
];
const inD: React.CSSProperties = { padding:'7px 9px', background:'#2a3140', border:'1px solid #3a4356',
  borderRadius:7, color:'#fff', fontSize:12.5, outline:'none', boxSizing:'border-box', width:'100%' };

export default function ChallengeSettings() {
  const [defs, setDefs] = useState<any>(null);
  const [tiers, setTiers] = useState<any[]>([]);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState('');
  useEffect(() => {
    apiGet('/ib-portal/admin/challenge-defs').then(setDefs).catch(() => setMsg('Failed to load'));
    apiGet('/ib-portal/admin/tier-reqs').then((d:any) => setTiers(d.tiers || [])).catch(() => {});
  }, []);
  if (!defs) return <div style={{ padding:26, color:'#98a2b3' }}>{msg || 'Loading…'}</div>;
  const upT = (i: number, f: string, v: any) => { const t = [...tiers]; t[i] = { ...t[i], [f]: v }; setTiers(t); };

  const upC  = (i: number, f: string, v: any) => { const c = [...defs.career]; c[i] = { ...c[i], [f]: v }; setDefs({ ...defs, career: c }); };
  const upCT = (i: number, k: string, v: any) => { const c = [...defs.career]; c[i] = { ...c[i], target: { ...(c[i].target || {}), [k]: v } }; setDefs({ ...defs, career: c }); };
  const upW  = (i: number, f: string, v: any) => { const w = [...defs.weekly]; w[i] = { ...w[i], [f]: v }; setDefs({ ...defs, weekly: w }); };
  const del  = (kind: 'career'|'weekly', i: number) => setDefs({ ...defs, [kind]: defs[kind].filter((_: any, j: number) => j !== i) });
  const move = (kind: 'career'|'weekly', i: number, d: number) => {
    const a = [...defs[kind]]; const j = i + d;
    if (j < 0 || j >= a.length) return;
    [a[i], a[j]] = [a[j], a[i]]; setDefs({ ...defs, [kind]: a });
  };
  const save = async () => {
    setSaving(true); setMsg('');
    try {
      await apiPut('/ib-portal/admin/challenge-defs', { career: defs.career, weekly: defs.weekly });
      if (tiers.length) await apiPut('/ib-portal/admin/tier-reqs', { tiers });
      setMsg('Saved ✓ — changes are live for all IBs immediately');
    } catch { setMsg('Save failed — check the values'); }
    setSaving(false);
  };

  return (
    <div style={{ padding:'20px 24px 60px', maxWidth:1150 }}>
      <div style={{ display:'flex', alignItems:'center', gap:14, marginBottom:6 }}>
        <div style={{ fontSize:19, fontWeight:800 }}>🏆 IB grades, challenges &amp; career path</div>
        <button onClick={save} disabled={saving}
          style={{ marginLeft:'auto', padding:'9px 22px', borderRadius:9, border:'none', cursor:'pointer',
                   background:'#00b57f', color:'#fff', fontWeight:800, fontSize:13 }}>{saving ? 'Saving…' : 'Save all changes'}</button>
      </div>
      <div style={{ fontSize:12, color:'#98a2b3', marginBottom:14 }}>
        What every IB sees in their portal. Career stages are one-time (accept → deadline → reward);
        weekly challenges auto-reset every Sunday. Untick “On” to hide one without deleting it.
        {msg && <span style={{ marginLeft:12, color: msg.startsWith('Saved') ? '#00e5a0' : '#ff6b6b', fontWeight:700 }}>{msg}</span>}
      </div>

      {tiers.length > 0 && (<>
        <div style={{ fontSize:14, fontWeight:800, margin:'14px 0 8px', color:'#7ee2a8' }}>IB grades — promotion requirements</div>
        <div style={{ fontSize:11.5, color:'#98a2b3', marginBottom:8 }}>
          What an IB must bring to REACH each grade — counted from their last promotion/demotion date.
          The $/lot column is what the IB sees as their rate; actual trade pricing follows the commission profiles.
        </div>
        <div style={{ background:'#242b38', border:'1px solid #3a4356', borderRadius:12, overflow:'auto' }}>
          <table style={{ ...CT.table, minWidth:820 }}>
            <thead><tr style={CT.theadTr}>
              <th style={CT.th()}>Level</th><th style={{ ...CT.th(), minWidth:130 }}>Grade</th>
              <th style={CT.th()}>Commission $/lot</th><th style={CT.th()}>Min. deposits $</th>
              <th style={CT.th()}>Lots (monthly average)</th><th style={CT.th()}>Min. NDA (new accounts)</th>
            </tr></thead>
            <tbody>
              {tiers.map((t: any, i: number) => (
                <tr key={t.level} style={CT.row()}>
                  <td style={{ ...CT.td, color:'#98a2b3' }}>IB-{t.level}</td>
                  <td style={CT.td}><input style={inD} value={t.name || ''} onChange={e => upT(i, 'name', e.target.value)} /></td>
                  <td style={CT.td}><input style={{ ...inD, width:80 }} value={t.comm_per_lot ?? ''} onChange={e => upT(i, 'comm_per_lot', e.target.value)} /></td>
                  <td style={CT.td}><input style={{ ...inD, width:110 }} value={t.min_deposit ?? ''} onChange={e => upT(i, 'min_deposit', e.target.value)}
                    placeholder={t.level === 5 ? 'no condition' : ''} /></td>
                  <td style={CT.td}><input style={{ ...inD, width:90 }} value={t.min_lots_avg ?? ''} onChange={e => upT(i, 'min_lots_avg', e.target.value)} /></td>
                  <td style={CT.td}><input style={{ ...inD, width:90 }} value={t.min_accounts ?? ''} onChange={e => upT(i, 'min_accounts', e.target.value)} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </>)}

      <div style={{ fontSize:14, fontWeight:800, margin:'24px 0 8px', color:'#ffd479' }}>Career path (stages in order)</div>
      <div style={{ background:'#242b38', border:'1px solid #3a4356', borderRadius:12, overflow:'auto' }}>
        <table style={{ ...CT.table, minWidth:980 }}>
          <thead><tr style={CT.theadTr}>
            <th style={CT.th()}>#</th><th style={CT.th()}>On</th><th style={{ ...CT.th(), minWidth:150 }}>Name</th>
            <th style={{ ...CT.th(), minWidth:240 }}>Description (shown to the IB)</th>
            <th style={CT.th()}>Reward $</th><th style={CT.th()}>Days</th>
            <th style={CT.th()}>New clients</th><th style={CT.th()}>FTDs</th><th style={CT.th()}>Lots</th><th style={CT.th()}></th>
          </tr></thead>
          <tbody>
            {defs.career.map((c: any, i: number) => (
              <tr key={c.key || i} style={{ ...CT.row(), opacity: c.enabled === false ? 0.45 : 1 }}>
                <td style={{ ...CT.td, color:'#98a2b3' }}>
                  {i + 1}
                  <button onClick={() => move('career', i, -1)} title="Move up"   style={{ marginLeft:6, background:'none', border:'none', color:'#667085', cursor:'pointer' }}>↑</button>
                  <button onClick={() => move('career', i, 1)}  title="Move down" style={{ background:'none', border:'none', color:'#667085', cursor:'pointer' }}>↓</button>
                </td>
                <td style={CT.td}><input type="checkbox" checked={c.enabled !== false} onChange={e => upC(i, 'enabled', e.target.checked)} /></td>
                <td style={CT.td}><input style={inD} value={c.name || ''} onChange={e => upC(i, 'name', e.target.value)} /></td>
                <td style={CT.td}><input style={inD} value={c.desc || ''} onChange={e => upC(i, 'desc', e.target.value)} /></td>
                <td style={CT.td}><input style={{ ...inD, width:80 }}  value={c.reward ?? ''} onChange={e => upC(i, 'reward', e.target.value)} /></td>
                <td style={CT.td}><input style={{ ...inD, width:60 }}  value={c.days ?? ''}   onChange={e => upC(i, 'days', e.target.value)} /></td>
                <td style={CT.td}><input style={{ ...inD, width:70 }}  value={c.target?.clients ?? ''} placeholder="—" onChange={e => upCT(i, 'clients', e.target.value)} /></td>
                <td style={CT.td}><input style={{ ...inD, width:70 }}  value={c.target?.ftd ?? ''}     placeholder="—" onChange={e => upCT(i, 'ftd', e.target.value)} /></td>
                <td style={CT.td}><input style={{ ...inD, width:80 }}  value={c.target?.lots ?? ''}    placeholder="—" onChange={e => upCT(i, 'lots', e.target.value)} /></td>
                <td style={CT.td}><button onClick={() => del('career', i)} title="Remove stage"
                  style={{ background:'none', border:'none', color:'#ff6b6b', cursor:'pointer', fontSize:15 }}>✕</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <button onClick={() => setDefs({ ...defs, career: [...defs.career, { key:'', name:'New stage', desc:'', reward:100, days:30, target:{ clients:'' }, enabled:true }] })}
        style={{ marginTop:8, padding:'7px 16px', borderRadius:8, border:'1px dashed #3a4356', background:'transparent', color:'#98a2b3', cursor:'pointer', fontSize:12.5 }}>+ Add career stage</button>

      <div style={{ fontSize:14, fontWeight:800, margin:'24px 0 8px', color:'#7fd4ff' }}>Weekly challenges (reset every Sunday)</div>
      <div style={{ background:'#242b38', border:'1px solid #3a4356', borderRadius:12, overflow:'auto' }}>
        <table style={{ ...CT.table, minWidth:900 }}>
          <thead><tr style={CT.theadTr}>
            <th style={CT.th()}>#</th><th style={CT.th()}>On</th><th style={CT.th()}>Emoji</th>
            <th style={{ ...CT.th(), minWidth:140 }}>Name</th><th style={{ ...CT.th(), minWidth:220 }}>Description</th>
            <th style={{ ...CT.th(), minWidth:160 }}>Counts</th><th style={CT.th()}>Target</th><th style={CT.th()}>Reward $</th><th style={CT.th()}></th>
          </tr></thead>
          <tbody>
            {defs.weekly.map((w: any, i: number) => (
              <tr key={w.key || i} style={{ ...CT.row(), opacity: w.enabled === false ? 0.45 : 1 }}>
                <td style={{ ...CT.td, color:'#98a2b3' }}>
                  {i + 1}
                  <button onClick={() => move('weekly', i, -1)} style={{ marginLeft:6, background:'none', border:'none', color:'#667085', cursor:'pointer' }}>↑</button>
                  <button onClick={() => move('weekly', i, 1)}  style={{ background:'none', border:'none', color:'#667085', cursor:'pointer' }}>↓</button>
                </td>
                <td style={CT.td}><input type="checkbox" checked={w.enabled !== false} onChange={e => upW(i, 'enabled', e.target.checked)} /></td>
                <td style={CT.td}><input style={{ ...inD, width:52, textAlign:'center' }} value={w.emoji || ''} onChange={e => upW(i, 'emoji', e.target.value)} /></td>
                <td style={CT.td}><input style={inD} value={w.name || ''} onChange={e => upW(i, 'name', e.target.value)} /></td>
                <td style={CT.td}><input style={inD} value={w.desc || ''} onChange={e => upW(i, 'desc', e.target.value)} /></td>
                <td style={CT.td}>
                  <select value={w.metric || 'ftd'} onChange={e => upW(i, 'metric', e.target.value)} style={{ ...inD, width:170 }}>
                    {METRICS.map(m => <option key={m.v} value={m.v}>{m.label}</option>)}
                  </select></td>
                <td style={CT.td}><input style={{ ...inD, width:80 }} value={w.target ?? ''} onChange={e => upW(i, 'target', e.target.value)} /></td>
                <td style={CT.td}><input style={{ ...inD, width:80 }} value={w.reward ?? ''} onChange={e => upW(i, 'reward', e.target.value)} /></td>
                <td style={CT.td}><button onClick={() => del('weekly', i)}
                  style={{ background:'none', border:'none', color:'#ff6b6b', cursor:'pointer', fontSize:15 }}>✕</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <button onClick={() => setDefs({ ...defs, weekly: [...defs.weekly, { key:'', emoji:'🏅', name:'New challenge', desc:'', metric:'ftd', target:1, reward:20, enabled:true }] })}
        style={{ marginTop:8, padding:'7px 16px', borderRadius:8, border:'1px dashed #3a4356', background:'transparent', color:'#98a2b3', cursor:'pointer', fontSize:12.5 }}>+ Add weekly challenge</button>
    </div>
  );
}

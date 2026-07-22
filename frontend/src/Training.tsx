import React, { useState, useEffect, useCallback } from 'react';
import { apiGet, apiPost, apiPatch, apiDelete } from './api';
import { useT } from './adminI18n';
import { CT } from './crmTable';

// Training department board — leads/clients that sales flagged as needing training. The training
// team (role='training') + admins move them through the stages and manage the material library.
const STAGE_COLORS: Record<string, string> = {
  requested: '#38bdf8', under_training: '#E8B84B', training_done: '#00e5a0',
  first_patch_done: '#22c55e', too_beginner: '#ff8800', trader_loses_alot: '#ff4d4d',
};

export default function Training() {
  const t = useT();
  const [data, setData] = useState<any>({ requests: [], counts: {}, can_manage: false });
  const [stages, setStages] = useState<any[]>([]);
  const [filter, setFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<'board' | 'materials'>('board');
  const [mats, setMats] = useState<any>({ materials: [], can_manage: false });
  const [showAddMat, setShowAddMat] = useState(false);
  const [matForm, setMatForm] = useState<any>({ title: '', category: '', url: '', description: '' });

  const load = useCallback(async () => {
    setLoading(true);
    try { setData(await apiGet('/training' + (filter ? `?stage=${filter}` : ''))); } catch {}
    setLoading(false);
  }, [filter]);
  useEffect(() => { apiGet('/training/meta').then((m: any) => setStages(m.stages || [])).catch(() => {}); }, []);
  useEffect(() => { load(); }, [load]);
  const loadMats = () => apiGet('/training/materials').then(setMats).catch(() => {});
  useEffect(() => { loadMats(); }, []);

  const canManage = data.can_manage;
  const setStage = async (id: number, stage: string) => { try { await apiPatch(`/training/${id}`, { stage }); load(); } catch (e: any) { alert(e?.message || 'Failed'); } };
  const claim = async (id: number) => { try { await apiPatch(`/training/${id}`, { claim: true }); load(); } catch {} };
  const remove = async (id: number) => { if (!window.confirm(t('Remove this training case?'))) return; try { await apiDelete(`/training/${id}`); load(); } catch {} };

  const addMat = async () => {
    if (!matForm.title.trim()) return;
    try { await apiPost('/training/materials', matForm); setShowAddMat(false); setMatForm({ title: '', category: '', url: '', description: '' }); loadMats(); } catch (e: any) { alert(e?.message || 'Failed'); }
  };

  const chip = (key: string, label: string, n: number) => (
    <button key={key} onClick={() => setFilter(filter === key ? '' : key)}
      style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '6px 12px', borderRadius: 8, cursor: 'pointer', fontSize: 12, fontWeight: 600,
        border: `1px solid ${filter === key ? (STAGE_COLORS[key] || '#00e5a0') : 'var(--border2,#626d80)'}`,
        background: filter === key ? (STAGE_COLORS[key] || '#00e5a0') + '22' : 'transparent',
        color: filter === key ? (STAGE_COLORS[key] || '#00e5a0') : 'var(--text2,#9aa3b2)' }}>
      {label} <span style={{ background: (STAGE_COLORS[key] || '#888') + '33', color: STAGE_COLORS[key] || '#aaa', borderRadius: 99, padding: '1px 7px', fontSize: 11 }}>{n}</span>
    </button>
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', color: 'var(--text,#e6e9ef)' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '14px 20px', borderBottom: '1px solid var(--border,#3a434f)', flexWrap: 'wrap' }}>
        <div style={{ fontSize: 18, fontWeight: 700 }}>🎓 {t('Training')}</div>
        <div style={{ display: 'flex', gap: 6, marginLeft: 8 }}>
          {(['board', 'materials'] as const).map(k => (
            <button key={k} onClick={() => setTab(k)}
              style={{ padding: '6px 14px', borderRadius: 8, fontSize: 12.5, fontWeight: tab === k ? 700 : 500, cursor: 'pointer',
                color: tab === k ? '#0b0f14' : 'var(--text2,#9aa3b2)', border: '1px solid ' + (tab === k ? 'transparent' : 'var(--border2,#353d49)'),
                background: tab === k ? 'linear-gradient(135deg,#E8B84B,#d9a72f)' : 'transparent' }}>
              {k === 'board' ? '📋 ' + t('Training board') : '📚 ' + t('Materials')}
            </button>
          ))}
        </div>
      </div>

      {tab === 'board' ? (
        <>
          {/* Stage filter chips */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '12px 20px', flexWrap: 'wrap', borderBottom: '1px solid var(--border,#313945)' }}>
            {chip('', t('All'), Object.values(data.counts || {}).reduce((a: any, b: any) => a + b, 0) as number)}
            {stages.map((s: any) => chip(s.key, t(s.label), (data.counts || {})[s.key] || 0))}
          </div>
          <div style={{ ...CT.scroll, padding: '0 8px' }}>
            <table style={{ ...CT.table }}>
              <thead><tr style={CT.theadTr}>
                {['Name', 'Phone', 'Country', 'From', 'Sent by', 'Note', 'Stage', 'Trainer'].map(h =>
                  <th key={h} style={CT.th()}>{t(h)}</th>)}
                {canManage && <th style={CT.th()}></th>}
              </tr></thead>
              <tbody>
                {loading ? (
                  <tr><td colSpan={9} style={{ padding: 40, textAlign: 'center', color: '#667' }}>{t('Loading...')}</td></tr>
                ) : (data.requests || []).length === 0 ? (
                  <tr><td colSpan={9} style={{ padding: 40, textAlign: 'center', color: '#667' }}>{t('No training cases yet — flag a lead with the 🎓 Training button.')}</td></tr>
                ) : data.requests.map((r: any) => (
                  <tr key={r.id} style={CT.row()}>
                    <td style={CT.td}>
                      <div style={{ fontWeight: 600 }}>{r.name}</div>
                      {r.customer_no && <div style={{ fontSize: 10, color: '#8792a6', fontFamily: 'monospace' }}>{r.customer_no}</div>}
                    </td>
                    <td style={{ ...CT.td, fontFamily: 'monospace', fontSize: 11 }}>{r.phone || '—'}</td>
                    <td style={{ ...CT.td, fontSize: 11, color: '#9aa3b2' }}>{r.country || '—'}</td>
                    <td style={{ ...CT.td, fontSize: 11 }}>{r.source === 'lead' ? '🎯 ' + t('Lead') : '👤 ' + t('Client')}</td>
                    <td style={{ ...CT.td, fontSize: 11, color: '#9aa3b2' }}>
                      {r.requested_by}
                      <div style={{ fontSize: 9.5, color: '#667' }}>{r.requested_at ? new Date(r.requested_at).toLocaleDateString('en-GB') : ''}</div>
                    </td>
                    <td style={{ ...CT.td, maxWidth: 240, whiteSpace: 'normal', fontSize: 11.5, color: '#c7ccd6' }}>{r.note || <span style={{ color: '#556' }}>—</span>}</td>
                    <td style={CT.td}>
                      {canManage ? (
                        <select value={r.stage} onChange={e => setStage(r.id, e.target.value)}
                          style={{ padding: '4px 8px', borderRadius: 99, fontSize: 11, fontWeight: 700, cursor: 'pointer', outline: 'none', fontFamily: 'inherit',
                            background: (STAGE_COLORS[r.stage] || '#888') + '22', border: `1px solid ${STAGE_COLORS[r.stage] || '#888'}`, color: STAGE_COLORS[r.stage] || '#aaa' }}>
                          {stages.map((s: any) => <option key={s.key} value={s.key} style={{ background: '#2c333e', color: '#e0e0e0' }}>{t(s.label)}</option>)}
                        </select>
                      ) : (
                        <span style={{ padding: '3px 10px', borderRadius: 99, fontSize: 11, fontWeight: 700, background: (STAGE_COLORS[r.stage] || '#888') + '22', color: STAGE_COLORS[r.stage] || '#aaa', border: `1px solid ${STAGE_COLORS[r.stage] || '#888'}` }}>{r.stage_label}</span>
                      )}
                    </td>
                    <td style={{ ...CT.td, fontSize: 11 }}>
                      {r.trainer || (canManage ? <span onClick={() => claim(r.id)} style={{ color: '#38bdf8', cursor: 'pointer', textDecoration: 'underline' }}>{t('Claim')}</span> : '—')}
                    </td>
                    {canManage && <td style={CT.td}><span onClick={() => remove(r.id)} title={t('Remove')} style={{ cursor: 'pointer', color: '#ff6b6b', fontSize: 13 }}>✕</span></td>}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : (
        /* Materials tab */
        <div style={{ padding: 20, overflowY: 'auto' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
            <div style={{ fontSize: 13, color: '#9aa3b2' }}>{t('Training material for the team — guides, videos, scripts.')}</div>
            {mats.can_manage && <button onClick={() => setShowAddMat(v => !v)} style={{ padding: '7px 14px', borderRadius: 8, border: '1px solid #E8B84B', background: 'rgba(232,184,75,0.12)', color: '#E8B84B', cursor: 'pointer', fontSize: 12, fontWeight: 600 }}>＋ {t('Add material')}</button>}
          </div>
          {showAddMat && (
            <div style={{ background: 'var(--bg-card,#2c333e)', border: '1px solid var(--border2,#4f596b)', borderRadius: 12, padding: 16, marginBottom: 16, display: 'grid', gap: 10, maxWidth: 560 }}>
              <input placeholder={t('Title')} value={matForm.title} onChange={e => setMatForm({ ...matForm, title: e.target.value })} style={inp} />
              <div style={{ display: 'flex', gap: 10 }}>
                <input placeholder={t('Category (e.g. Beginner, Risk)')} value={matForm.category} onChange={e => setMatForm({ ...matForm, category: e.target.value })} style={{ ...inp, flex: 1 }} />
                <input placeholder={t('Link (URL)')} value={matForm.url} onChange={e => setMatForm({ ...matForm, url: e.target.value })} style={{ ...inp, flex: 2 }} />
              </div>
              <textarea placeholder={t('Description')} value={matForm.description} onChange={e => setMatForm({ ...matForm, description: e.target.value })} style={{ ...inp, minHeight: 60, resize: 'vertical' as any }} />
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
                <button onClick={() => setShowAddMat(false)} style={{ padding: '7px 14px', background: 'transparent', border: '1px solid #626d80', borderRadius: 8, color: '#888', cursor: 'pointer' }}>{t('Cancel')}</button>
                <button onClick={addMat} style={{ padding: '7px 18px', background: '#E8B84B', border: 'none', borderRadius: 8, color: '#0b0f14', fontWeight: 700, cursor: 'pointer' }}>{t('Save')}</button>
              </div>
            </div>
          )}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(280px,1fr))', gap: 12 }}>
            {(mats.materials || []).length === 0 && <div style={{ color: '#667', fontSize: 13 }}>{t('No materials yet.')}</div>}
            {(mats.materials || []).map((m: any) => (
              <div key={m.id} style={{ background: 'var(--bg-card,#2c333e)', border: '1px solid var(--border2,#4f596b)', borderRadius: 12, padding: 14 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', gap: 8 }}>
                  <div style={{ fontWeight: 700, fontSize: 14 }}>{m.title}</div>
                  {mats.can_manage && <span onClick={async () => { if (window.confirm(t('Delete?'))) { await apiDelete(`/training/materials/${m.id}`); loadMats(); } }} style={{ cursor: 'pointer', color: '#ff6b6b', fontSize: 13 }}>✕</span>}
                </div>
                {m.category && <span style={{ display: 'inline-block', marginTop: 4, fontSize: 10, padding: '2px 8px', borderRadius: 99, background: 'rgba(56,189,248,0.14)', color: '#38bdf8' }}>{m.category}</span>}
                {m.description && <div style={{ fontSize: 12, color: '#9aa3b2', marginTop: 8, lineHeight: 1.5 }}>{m.description}</div>}
                {m.url && <a href={m.url} target="_blank" rel="noreferrer" style={{ display: 'inline-block', marginTop: 10, fontSize: 12, color: '#E8B84B', fontWeight: 600, textDecoration: 'none' }}>🔗 {t('Open material')}</a>}
                <div style={{ fontSize: 9.5, color: '#667', marginTop: 8 }}>{m.created_by}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

const inp: React.CSSProperties = { width: '100%', padding: '9px 11px', background: 'var(--bg-input,#373f4d)', border: '1px solid var(--border2,#626d80)', borderRadius: 8, color: 'var(--text,#e6e9ef)', fontSize: 13, outline: 'none', boxSizing: 'border-box' as any, fontFamily: 'inherit' };

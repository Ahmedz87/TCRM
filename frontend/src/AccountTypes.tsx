import React, { useState, useEffect } from 'react';
import { apiGet, apiPost, apiDelete } from './api';

export default function AccountTypes() {
  const [types, setTypes] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<any | null>(null);
  const [adding, setAdding] = useState(false);
  const [msg, setMsg] = useState('');

  const load = () => {
    setLoading(true);
    apiGet('/admin/payments/account-types').then((d: any) => setTypes(d?.account_types || [])).catch(() => {}).finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, []);

  const remove = async (t: any) => {
    if (!window.confirm(`Delete account type "${t.name}"?`)) return;
    await apiDelete(`/admin/payments/account-types/${t.id}`);
    setMsg(`Deleted ${t.name}`); load();
  };

  if (editing || adding) {
    return <TypeEditor
      initial={editing || { first_deposit_min: 100, default_leverage: 500, leverages: [50, 100, 200, 400, 500, 1000], swap_free_available: true, platforms: ['MT5', 'MT4'], is_active: true, sort_order: 100 }}
      onClose={() => { setEditing(null); setAdding(false); }}
      onSaved={() => { setEditing(null); setAdding(false); setMsg('Saved'); load(); }}
    />;
  }

  return (
    <div style={S.wrap}>
      <div style={S.head}>
        <div>
          <h1 style={S.h1}>Account types</h1>
          <div style={S.sub}>Specs for each trading account type — first-deposit minimum, leverages, swap-free, MT group mapping.</div>
        </div>
        <button style={S.addBtn} onClick={() => setAdding(true)}>+ Add type</button>
      </div>

      {msg && <div style={S.toast}>{msg}</div>}

      {loading ? <div style={S.empty}>Loading…</div> : (
        <div style={S.list}>
          {types.map(t => (
            <div key={t.id} style={S.row}>
              <div style={{ flex: 1 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontWeight: 700, fontSize: 15 }}>{t.name}</span>
                  {!t.is_active && <span style={S.tagOff}>DISABLED</span>}
                  {t.swap_free_available && <span style={S.tagSwap}>swap-free ✓</span>}
                </div>
                <div style={S.rowSub}>{t.description}</div>
                <div style={S.specs}>
                  <span>First deposit: <b style={{ color: '#3ad29f' }}>${Number(t.first_deposit_min).toLocaleString()}</b></span>
                  <span>Default leverage: <b>1:{t.default_leverage}</b></span>
                  <span>Leverages: {(t.leverages || []).map((l: number) => `1:${l}`).join(', ')}</span>
                </div>
                <div style={S.groups}>MT5: <code>{t.mt5_group || '—'}</code> · MT4: <code>{t.mt4_group || '—'}</code></div>
              </div>
              <button style={S.editBtn} onClick={() => setEditing(t)}>Edit</button>
              <button style={S.delBtn} onClick={() => remove(t)}>✕</button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function TypeEditor({ initial, onClose, onSaved }: any) {
  const [t, setT] = useState<any>({ ...initial });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const isNew = !initial.id;
  const set = (k: string, v: any) => setT({ ...t, [k]: v });

  const save = async () => {
    setErr(''); setBusy(true);
    try {
      const body = { ...t };
      if (isNew && !body.code) body.code = (body.name || '').toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '');
      let res: any;
      if (isNew) res = await apiPost('/admin/payments/account-types', body);
      else {
        const token = localStorage.getItem('token') || '';
        const r = await fetch(`/api/admin/payments/account-types/${t.id}`, {
          method: 'PUT', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }, body: JSON.stringify(body),
        });
        res = await r.json();
      }
      if (res?.ok) onSaved();
      else setErr(res?.detail || 'Save failed');
    } catch (e: any) { setErr(e?.message || 'Save failed'); }
    finally { setBusy(false); }
  };

  const csvNum = (arr: any[]) => (arr || []).join(', ');
  const parseNums = (s: string) => s.split(',').map(x => parseInt(x.trim(), 10)).filter(n => !isNaN(n));

  return (
    <div style={S.wrap}>
      <button style={S.backLink} onClick={onClose}>← Back to account types</button>
      <h1 style={S.h1}>{isNew ? 'New account type' : `Edit ${t.name}`}</h1>
      {err && <div style={S.errBox}>{err}</div>}

      <div style={S.editGrid}>
        <Field label="Name"><input style={S.input} value={t.name || ''} onChange={e => set('name', e.target.value)} /></Field>
        {isNew && <Field label="Code (unique)"><input style={S.input} value={t.code || ''} onChange={e => set('code', e.target.value)} placeholder="auto from name" /></Field>}
        <Field label="Description"><input style={S.input} value={t.description || ''} onChange={e => set('description', e.target.value)} /></Field>
        <Field label="First deposit minimum ($)"><input style={S.input} type="number" value={t.first_deposit_min ?? ''} onChange={e => set('first_deposit_min', e.target.value)} /></Field>
        <Field label="Default leverage (1:X)"><input style={S.input} type="number" value={t.default_leverage ?? ''} onChange={e => set('default_leverage', e.target.value)} /></Field>
        <Field label="Sort order"><input style={S.input} type="number" value={t.sort_order ?? 100} onChange={e => set('sort_order', e.target.value)} /></Field>
      </div>

      <Field label="Available leverages (comma-separated, e.g. 50, 100, 500)">
        <input style={S.input} value={csvNum(t.leverages)} onChange={e => set('leverages', parseNums(e.target.value))} />
      </Field>

      <div style={S.section}>MT group mapping (for provisioning)</div>
      <div style={S.editGrid}>
        <Field label="MT5 group"><input style={S.input} value={t.mt5_group || ''} onChange={e => set('mt5_group', e.target.value)} placeholder="real\\STD-USD" /></Field>
        <Field label="MT4 group"><input style={S.input} value={t.mt4_group || ''} onChange={e => set('mt4_group', e.target.value)} placeholder="STD\\2-STD-IS" /></Field>
      </div>

      <div style={{ display: 'flex', gap: 20, marginTop: 16 }}>
        <label style={S.check}><input type="checkbox" checked={!!t.swap_free_available} onChange={e => set('swap_free_available', e.target.checked)} /> Islamic / swap-free available</label>
        <label style={S.check}><input type="checkbox" checked={!!t.is_active} onChange={e => set('is_active', e.target.checked)} /> Active</label>
      </div>

      <div style={{ display: 'flex', gap: 10, marginTop: 24 }}>
        <button style={S.saveBtn} disabled={busy} onClick={save}>{busy ? 'Saving…' : 'Save type'}</button>
        <button style={S.ghostBtn} onClick={onClose}>Cancel</button>
      </div>
    </div>
  );
}

function Field({ label, children }: any) {
  return <div style={{ marginBottom: 14 }}><label style={S.label}>{label}</label>{children}</div>;
}

const S: any = {
  wrap: { padding: 28, maxWidth: 860, margin: '0 auto', color: '#e8edf2' },
  head: { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 20 },
  h1: { fontSize: 22, fontWeight: 800, margin: 0 },
  sub: { fontSize: 13, color: '#8A93A3', marginTop: 4, maxWidth: 560 },
  addBtn: { padding: '10px 18px', borderRadius: 9, background: 'linear-gradient(90deg,#3ad29f,#2bb88a)', color: '#06231a', border: 'none', fontWeight: 800, fontSize: 13, cursor: 'pointer', flex: '0 0 auto' },
  toast: { background: 'rgba(58,210,159,0.1)', border: '1px solid rgba(58,210,159,0.3)', color: '#3ad29f', borderRadius: 8, padding: '8px 14px', fontSize: 13, marginBottom: 14 },
  list: { display: 'flex', flexDirection: 'column', gap: 10 },
  row: { display: 'flex', alignItems: 'flex-start', gap: 14, background: '#161c24', border: '1px solid #232d3a', borderRadius: 12, padding: '16px 18px' },
  rowSub: { fontSize: 12.5, color: '#8A93A3', marginTop: 3 },
  specs: { display: 'flex', gap: 18, flexWrap: 'wrap', fontSize: 12, color: '#cdd4de', marginTop: 8 },
  groups: { fontSize: 11, color: '#5a6470', marginTop: 6 },
  tagOff: { fontSize: 9.5, fontWeight: 800, color: '#f0556a', background: 'rgba(240,85,106,0.12)', padding: '2px 7px', borderRadius: 5 },
  tagSwap: { fontSize: 9.5, fontWeight: 800, color: '#3ad29f', background: 'rgba(58,210,159,0.12)', padding: '2px 7px', borderRadius: 5 },
  editBtn: { padding: '7px 14px', borderRadius: 8, background: 'transparent', border: '1px solid #2f3a48', color: '#e8edf2', fontSize: 12.5, fontWeight: 600, cursor: 'pointer', flex: '0 0 auto' },
  delBtn: { width: 30, height: 30, borderRadius: 8, background: 'transparent', border: '1px solid #3a2530', color: '#f0556a', cursor: 'pointer', flex: '0 0 auto' },
  empty: { padding: 40, textAlign: 'center', color: '#8A93A3' },
  backLink: { background: 'none', border: 'none', color: '#3ad29f', cursor: 'pointer', fontSize: 13, marginBottom: 12, padding: 0 },
  editGrid: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 },
  section: { fontSize: 11, letterSpacing: '0.12em', textTransform: 'uppercase', color: '#8A93A3', fontWeight: 700, margin: '22px 0 12px', borderBottom: '1px solid #232d3a', paddingBottom: 6 },
  label: { fontSize: 11.5, color: '#8A93A3', fontWeight: 600, display: 'block', marginBottom: 6 },
  input: { width: '100%', padding: '10px 12px', borderRadius: 8, background: '#262c36', border: '1px solid #2f3a48', color: '#e8edf2', fontSize: 13.5, outline: 'none', boxSizing: 'border-box' },
  check: { fontSize: 13, color: '#cdd4de', display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' },
  saveBtn: { padding: '12px 24px', borderRadius: 9, background: 'linear-gradient(90deg,#3ad29f,#2bb88a)', color: '#06231a', border: 'none', fontWeight: 800, fontSize: 14, cursor: 'pointer' },
  ghostBtn: { padding: '12px 24px', borderRadius: 9, background: 'transparent', border: '1px solid #2f3a48', color: '#e8edf2', fontWeight: 600, fontSize: 14, cursor: 'pointer' },
  errBox: { background: 'rgba(240,85,106,0.1)', border: '1px solid rgba(240,85,106,0.3)', color: '#f0556a', borderRadius: 8, padding: '8px 14px', fontSize: 13, marginBottom: 14 },
};

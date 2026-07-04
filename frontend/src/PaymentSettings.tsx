import React, { useState, useEffect } from 'react';
import { apiGet, apiPost, apiPatch, apiDelete } from './api';

type Method = any;

const LOGOS: any = {
  card: '💳', usdt: '₮', ovadot: '👛', bank: '🏦', local: '📲', generic: '$',
  qicard: 'Qi', zaincash: 'ZC', shamcash: 'Sh', fastpay: 'FP',
};
const LOGO_OPTS = ['qicard', 'zaincash', 'shamcash', 'fastpay', 'card', 'usdt', 'ovadot', 'bank', 'local', 'generic'];

export default function PaymentSettings() {
  const [methods, setMethods] = useState<Method[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<Method | null>(null);
  const [adding, setAdding] = useState(false);
  const [addKind, setAddKind] = useState<'manual' | 'auto' | null>(null);
  const [msg, setMsg] = useState('');

  const load = () => {
    setLoading(true);
    apiGet('/admin/payments/methods').then((d: any) => setMethods(d?.methods || [])).catch(() => {}).finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, []);

  const toggle = async (m: Method, field: string) => {
    await apiPatch(`/admin/payments/methods/${m.id}/toggle`, { field });
    load();
  };

  const remove = async (m: Method) => {
    if (!window.confirm(`Delete "${m.name}"? This cannot be undone.`)) return;
    await apiDelete(`/admin/payments/methods/${m.id}`);
    setMsg(`Deleted ${m.name}`); load();
  };

  if (editing || (adding && addKind)) {
    return <MethodEditor
      initial={editing || { kind: addKind, is_active: true, deposit_enabled: true, withdraw_enabled: true, min_deposit: 10, min_withdraw: 50, max_withdraw: 100000, allow_countries: [], block_countries: [], manual_details: {}, env_keys: [], api_config: {}, fee: '0%', sort_order: 100, logo: 'generic' }}
      onClose={() => { setEditing(null); setAdding(false); setAddKind(null); }}
      onSaved={() => { setEditing(null); setAdding(false); setAddKind(null); setMsg('Saved'); load(); }}
    />;
  }

  return (
    <div style={S.wrap}>
      <div style={S.head}>
        <div>
          <h1 style={S.h1}>Payment methods</h1>
          <div style={S.sub}>Enable, configure, and add deposit / withdrawal methods.</div>
        </div>
        <button style={S.addBtn} onClick={() => { setAdding(true); setAddKind(null); }}>+ Add method</button>
      </div>

      {msg && <div style={S.toast}>{msg}</div>}

      {adding && !addKind && (
        <div style={S.kindCard}>
          <div style={{ fontWeight: 700, marginBottom: 12, fontSize: 15 }}>What kind of method?</div>
          <div style={{ display: 'flex', gap: 12 }}>
            <button style={S.kindBtn} onClick={() => setAddKind('manual')}>
              <div style={{ fontSize: 26 }}>🧾</div>
              <div style={{ fontWeight: 700, marginTop: 6 }}>Manual</div>
              <div style={S.kindSub}>Show payment details, client uploads proof</div>
            </button>
            <button style={S.kindBtn} onClick={() => setAddKind('auto')}>
              <div style={{ fontSize: 26 }}>⚡</div>
              <div style={{ fontWeight: 700, marginTop: 6 }}>Automatic (API)</div>
              <div style={S.kindSub}>Connects to a payment API / gateway</div>
            </button>
          </div>
          <button style={S.cancelLink} onClick={() => setAdding(false)}>Cancel</button>
        </div>
      )}

      {loading ? <div style={S.empty}>Loading…</div> : (
        <div style={S.list}>
          {methods.map(m => (
            <div key={m.id} style={S.row}>
              <div style={S.logo}>{LOGOS[m.logo] || LOGOS.generic}</div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontWeight: 700, fontSize: 14.5 }}>{m.name}</span>
                  <span style={m.kind === 'auto' ? S.tagAuto : S.tagManual}>{m.kind === 'auto' ? 'API' : 'MANUAL'}</span>
                  {!m.is_active && <span style={S.tagOff}>DISABLED</span>}
                </div>
                <div style={S.rowSub}>{m.blurb || m.code} · min dep ${fmt(m.min_deposit)} · {m.max_deposit ? `max $${fmt(m.max_deposit)}` : 'no max'}{(m.allow_countries?.length || m.block_countries?.length) ? ' · region rules' : ''}</div>
              </div>
              <div style={S.toggles}>
                <Toggle label="Active" on={m.is_active} onClick={() => toggle(m, 'is_active')} />
                <Toggle label="Deposit" on={m.deposit_enabled} onClick={() => toggle(m, 'deposit_enabled')} />
                <Toggle label="Withdraw" on={m.withdraw_enabled} onClick={() => toggle(m, 'withdraw_enabled')} />
              </div>
              <button style={S.editBtn} onClick={() => setEditing(m)}>Edit</button>
              <button style={S.delBtn} onClick={() => remove(m)} title="Delete">✕</button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Toggle({ label, on, onClick }: any) {
  return (
    <button onClick={onClick} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4, background: 'none', border: 'none', cursor: 'pointer' }}>
      <div style={{ width: 38, height: 21, borderRadius: 99, background: on ? '#3ad29f' : '#3a4252', padding: 2, transition: 'background .15s', display: 'flex', justifyContent: on ? 'flex-end' : 'flex-start' }}>
        <div style={{ width: 17, height: 17, borderRadius: 99, background: '#fff' }} />
      </div>
      <span style={{ fontSize: 10, color: '#8A93A3', fontWeight: 600 }}>{label}</span>
    </button>
  );
}

// ---------------- editor ----------------
function MethodEditor({ initial, onClose, onSaved }: any) {
  const [m, setM] = useState<any>({ ...initial });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const isNew = !initial.id;
  const set = (k: string, v: any) => setM({ ...m, [k]: v });

  // manual details as editable rows
  const detailRows = Object.entries(m.manual_details || {});
  const setDetail = (k: string, v: string, oldK?: string) => {
    const d = { ...(m.manual_details || {}) };
    if (oldK && oldK !== k) delete d[oldK];
    d[k] = v; set('manual_details', d);
  };
  const addDetail = () => set('manual_details', { ...(m.manual_details || {}), '': '' });
  const delDetail = (k: string) => { const d = { ...(m.manual_details || {}) }; delete d[k]; set('manual_details', d); };

  const save = async () => {
    setErr(''); setBusy(true);
    try {
      const body = { ...m };
      if (isNew && !body.code) body.code = (body.name || '').toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '');
      const token = localStorage.getItem('token') || '';
      const url = isNew
        ? '/api/admin/payments/methods'
        : `/api/admin/payments/methods/${m.id}`;
      const r = await fetch(url, {
        method: isNew ? 'POST' : 'PUT',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify(body),
      });
      const res = await r.json().catch(() => ({}));
      if (r.ok && res && res.ok) onSaved();
      else setErr((res && res.detail) || `Save failed (HTTP ${r.status})`);
    } catch (e: any) { setErr(e?.message || 'Save failed'); }
    finally { setBusy(false); }
  };

  const csv = (arr: any[]) => (arr || []).join(', ');
  const parseCsv = (s: string) => s.split(',').map(x => x.trim()).filter(Boolean);

  return (
    <div style={S.wrap}>
      <button style={S.backLink} onClick={onClose}>← Back to methods</button>
      <h1 style={S.h1}>{isNew ? `New ${m.kind === 'auto' ? 'API' : 'manual'} method` : `Edit ${m.name}`}</h1>
      {err && <div style={S.errBox}>{err}</div>}

      <div style={S.editGrid}>
        <Field label="Display name"><input style={S.input} value={m.name || ''} onChange={e => set('name', e.target.value)} /></Field>
        {isNew && <Field label="Code (unique, no spaces)"><input style={S.input} value={m.code || ''} onChange={e => set('code', e.target.value)} placeholder="auto from name if blank" /></Field>}
        <Field label="Logo"><select style={S.input} value={m.logo} onChange={e => set('logo', e.target.value)}>{LOGO_OPTS.map(l => <option key={l} value={l}>{LOGOS[l]} {l}</option>)}</select></Field>
        <Field label="Provider (for API methods)"><input style={S.input} value={m.provider || ''} onChange={e => set('provider', e.target.value)} placeholder="ovadot / usdt / card …" /></Field>
        <Field label="Short description"><input style={S.input} value={m.blurb || ''} onChange={e => set('blurb', e.target.value)} /></Field>
        <Field label="Fee label"><input style={S.input} value={m.fee || ''} onChange={e => set('fee', e.target.value)} placeholder="0%" /></Field>
        <Field label="Processing time"><input style={S.input} value={m.processing_time || ''} onChange={e => set('processing_time', e.target.value)} placeholder="Instant / 1-3 days" /></Field>
        <Field label="Sort order"><input style={S.input} type="number" value={m.sort_order ?? 100} onChange={e => set('sort_order', e.target.value)} /></Field>
      </div>

      <div style={S.section}>Limits</div>
      <div style={S.editGrid}>
        <Field label="Min deposit ($)"><input style={S.input} type="number" value={m.min_deposit ?? ''} onChange={e => set('min_deposit', e.target.value)} /></Field>
        <Field label="Max deposit ($, blank = none)"><input style={S.input} type="number" value={m.max_deposit ?? ''} onChange={e => set('max_deposit', e.target.value === '' ? null : e.target.value)} /></Field>
        <Field label="Min withdraw ($)"><input style={S.input} type="number" value={m.min_withdraw ?? ''} onChange={e => set('min_withdraw', e.target.value)} /></Field>
        <Field label="Max withdraw ($)"><input style={S.input} type="number" value={m.max_withdraw ?? ''} onChange={e => set('max_withdraw', e.target.value)} /></Field>
      </div>

      <div style={S.section}>Region rules</div>
      <div style={S.editGrid}>
        <Field label="Show ONLY in (allowlist, comma-separated countries; blank = everywhere)">
          <input style={S.input} value={csv(m.allow_countries)} onChange={e => set('allow_countries', parseCsv(e.target.value))} placeholder="e.g. Iraq, UAE" />
        </Field>
        <Field label="Hide in (blocklist, comma-separated countries)">
          <input style={S.input} value={csv(m.block_countries)} onChange={e => set('block_countries', parseCsv(e.target.value))} placeholder="e.g. USA, Iran" />
        </Field>
      </div>

      {m.kind === 'manual' ? (
        <>
          <div style={S.section}>Manual payment details (shown to client)</div>
          {detailRows.map(([k, v]: any, i) => (
            <div key={i} style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
              <input style={{ ...S.input, flex: '0 0 38%' }} value={k} placeholder="Label (e.g. IBAN)" onChange={e => setDetail(e.target.value, v as string, k)} />
              <input style={{ ...S.input, flex: 1 }} value={v as string} placeholder="Value" onChange={e => setDetail(k, e.target.value)} />
              <button style={S.delBtn} onClick={() => delDetail(k)}>✕</button>
            </div>
          ))}
          <button style={S.smallBtn} onClick={addDetail}>+ Add detail</button>
        </>
      ) : (
        <>
          <div style={S.section}>API configuration</div>
          <div style={S.envNote}>🔒 For security, secret keys live in the server's <b>.env</b> file. Here you only list the env-variable <i>names</i> this method uses.</div>
          <Field label="Env key names (comma-separated)">
            <input style={S.input} value={csv(m.env_keys)} onChange={e => set('env_keys', parseCsv(e.target.value))} placeholder="OVADOT_API_KEY, OVADOT_MERCHANT_ID" />
          </Field>
          <Field label="API base URL (non-secret)">
            <input style={S.input} value={m.api_config?.base_url || ''} onChange={e => set('api_config', { ...(m.api_config || {}), base_url: e.target.value })} placeholder="https://api.provider.com" />
          </Field>
          <Field label="Flow type">
            <select style={S.input} value={m.api_config?.flow || 'redirect'} onChange={e => set('api_config', { ...(m.api_config || {}), flow: e.target.value })}>
              <option value="redirect">Redirect / hosted checkout</option>
              <option value="ewallet">E-wallet</option>
              <option value="crypto_address">Crypto address (auto-confirm)</option>
            </select>
          </Field>
        </>
      )}

      <div style={{ display: 'flex', gap: 10, marginTop: 24 }}>
        <button style={S.saveBtn} disabled={busy} onClick={save}>{busy ? 'Saving…' : 'Save method'}</button>
        <button style={S.ghostBtn} onClick={onClose}>Cancel</button>
      </div>
    </div>
  );
}

function Field({ label, children }: any) {
  return <div style={{ marginBottom: 14 }}><label style={S.label}>{label}</label>{children}</div>;
}

const fmt = (n: any) => (n == null ? '0' : Number(n).toLocaleString());

const S: any = {
  wrap: { padding: 28, maxWidth: 900, margin: '0 auto', color: '#e8edf2' },
  head: { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 20 },
  h1: { fontSize: 22, fontWeight: 800, margin: 0 },
  sub: { fontSize: 13, color: '#8A93A3', marginTop: 4 },
  addBtn: { padding: '10px 18px', borderRadius: 9, background: 'linear-gradient(90deg,#3ad29f,#2bb88a)', color: '#06231a', border: 'none', fontWeight: 800, fontSize: 13, cursor: 'pointer' },
  toast: { background: 'rgba(58,210,159,0.1)', border: '1px solid rgba(58,210,159,0.3)', color: '#3ad29f', borderRadius: 8, padding: '8px 14px', fontSize: 13, marginBottom: 14 },
  list: { display: 'flex', flexDirection: 'column', gap: 10 },
  row: { display: 'flex', alignItems: 'center', gap: 14, background: '#161c24', border: '1px solid #232d3a', borderRadius: 12, padding: '14px 16px' },
  logo: { width: 42, height: 42, borderRadius: 10, background: '#262c36', display: 'grid', placeItems: 'center', fontSize: 18, flex: '0 0 auto' },
  rowSub: { fontSize: 11.5, color: '#8A93A3', marginTop: 3, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' },
  toggles: { display: 'flex', gap: 14, flex: '0 0 auto' },
  tagAuto: { fontSize: 9.5, fontWeight: 800, color: '#3ad29f', background: 'rgba(58,210,159,0.12)', padding: '2px 7px', borderRadius: 5 },
  tagManual: { fontSize: 9.5, fontWeight: 800, color: '#8A93A3', background: '#222b38', padding: '2px 7px', borderRadius: 5 },
  tagOff: { fontSize: 9.5, fontWeight: 800, color: '#f0556a', background: 'rgba(240,85,106,0.12)', padding: '2px 7px', borderRadius: 5 },
  editBtn: { padding: '7px 14px', borderRadius: 8, background: 'transparent', border: '1px solid #2f3a48', color: '#e8edf2', fontSize: 12.5, fontWeight: 600, cursor: 'pointer', flex: '0 0 auto' },
  delBtn: { width: 30, height: 30, borderRadius: 8, background: 'transparent', border: '1px solid #3a2530', color: '#f0556a', cursor: 'pointer', flex: '0 0 auto' },
  empty: { padding: 40, textAlign: 'center', color: '#8A93A3' },
  kindCard: { background: '#161c24', border: '1px solid #232d3a', borderRadius: 12, padding: 20, marginBottom: 18 },
  kindBtn: { flex: 1, background: '#262c36', border: '1px solid #2f3a48', borderRadius: 10, padding: 18, cursor: 'pointer', color: '#e8edf2', textAlign: 'center' },
  kindSub: { fontSize: 11.5, color: '#8A93A3', marginTop: 4 },
  cancelLink: { marginTop: 14, background: 'none', border: 'none', color: '#8A93A3', cursor: 'pointer', fontSize: 13 },
  backLink: { background: 'none', border: 'none', color: '#3ad29f', cursor: 'pointer', fontSize: 13, marginBottom: 12, padding: 0 },
  editGrid: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 },
  section: { fontSize: 11, letterSpacing: '0.12em', textTransform: 'uppercase', color: '#8A93A3', fontWeight: 700, margin: '22px 0 12px', borderBottom: '1px solid #232d3a', paddingBottom: 6 },
  label: { fontSize: 11.5, color: '#8A93A3', fontWeight: 600, display: 'block', marginBottom: 6 },
  input: { width: '100%', padding: '10px 12px', borderRadius: 8, background: '#262c36', border: '1px solid #2f3a48', color: '#e8edf2', fontSize: 13.5, outline: 'none', boxSizing: 'border-box' },
  envNote: { fontSize: 12, color: '#E8B84B', background: 'rgba(232,184,75,0.08)', border: '1px solid rgba(232,184,75,0.22)', borderRadius: 8, padding: '10px 12px', marginBottom: 14, lineHeight: 1.5 },
  saveBtn: { padding: '12px 24px', borderRadius: 9, background: 'linear-gradient(90deg,#3ad29f,#2bb88a)', color: '#06231a', border: 'none', fontWeight: 800, fontSize: 14, cursor: 'pointer' },
  ghostBtn: { padding: '12px 24px', borderRadius: 9, background: 'transparent', border: '1px solid #2f3a48', color: '#e8edf2', fontWeight: 600, fontSize: 14, cursor: 'pointer' },
  smallBtn: { padding: '7px 14px', borderRadius: 8, background: '#222b38', border: '1px solid #2f3a48', color: '#e8edf2', fontSize: 12, cursor: 'pointer', marginTop: 4 },
  errBox: { background: 'rgba(240,85,106,0.1)', border: '1px solid rgba(240,85,106,0.3)', color: '#f0556a', borderRadius: 8, padding: '8px 14px', fontSize: 13, marginBottom: 14 },
};

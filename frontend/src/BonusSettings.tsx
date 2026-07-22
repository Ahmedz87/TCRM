import React, { useState, useEffect } from 'react';
import { apiGet, apiPut, apiPost, apiPatch, apiDelete } from './api';
import { CT } from './crmTable';

// Bonus settings: global config (welcome / deposit tiers / withdraw mins / margin floor /
// blocked countries) + special-offer CRUD (percent, cap, min deposit, countries, deadline).
const csv = (arr: any[]) => (arr || []).join(', ');
const parseCsv = (s: string) => s.split(',').map(x => x.trim()).filter(Boolean);

export default function BonusSettings() {
  const [cfg, setCfg] = useState<any>(null);
  const [offers, setOffers] = useState<any[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [reviews, setReviews] = useState<any[]>([]);
  const [editing, setEditing] = useState<any>(null);
  const [adding, setAdding] = useState(false);
  const [msg, setMsg] = useState('');

  const load = () => {
    apiGet('/admin/bonus/config').then((d: any) => setCfg(d?.config || null)).catch(() => {});
    apiGet('/admin/bonus/offers').then((d: any) => setOffers(d?.offers || [])).catch(() => {});
    apiGet('/admin/bonus/stats').then((d: any) => setStats(d || null)).catch(() => {});
    apiGet('/admin/bonus/reviews?status=pending').then((d: any) => setReviews(d?.reviews || [])).catch(() => {});
  };
  useEffect(() => { load(); }, []);

  const decideReview = async (id: number, decision: 'approve' | 'reject') => {
    const res: any = await apiPost(`/admin/bonus/reviews/${id}/decision`, { decision });
    if (res?.ok) {
      setMsg(decision === 'approve'
        ? `Approved — $${res.granted || 50} welcome bonus credited.`
        : 'Rejected — welcome bonus blocked for this client.');
      setTimeout(() => setMsg(''), 3000);
    }
    load();
  };

  const num = (k: string, v: string) => setCfg((c: any) => ({ ...c, [k]: parseFloat(v) || 0 }));
  const saveCfg = async () => {
    await apiPut('/admin/bonus/config', cfg);
    setMsg('Configuration saved'); setTimeout(() => setMsg(''), 2500); load();
  };

  const toggleOffer = async (o: any) => { await apiPatch(`/admin/bonus/offers/${o.id}/toggle`, {}); load(); };
  const delOffer = async (o: any) => {
    if (!window.confirm(`Delete offer "${o.name}"?`)) return;
    await apiDelete(`/admin/bonus/offers/${o.id}`); load();
  };

  if (!cfg) return <div style={{ padding: 28, color: '#8A93A3' }}>Loading bonus settings…</div>;

  if (editing || adding) {
    return <OfferEditor
      initial={editing || { name: '', percent: 100, cap: 500, min_deposit: 0, countries: [], starts_at: '', ends_at: '', active: true }}
      onClose={() => { setEditing(null); setAdding(false); }}
      onSaved={() => { setEditing(null); setAdding(false); setMsg('Offer saved'); setTimeout(() => setMsg(''), 2500); load(); }}
    />;
  }

  return (
    <div style={S.wrap}>
      <div style={S.head}>
        <div>
          <h1 style={S.h1}>🎁 Bonus settings</h1>
          <div style={S.sub}>Welcome bonus, tiered deposit bonus, blocked countries, and time-limited special offers.</div>
        </div>
        <button style={S.saveBtn} onClick={saveCfg}>Save configuration</button>
      </div>
      {msg && <div style={S.toast}>✅ {msg}</div>}

      {stats && (
        <div style={S.kpis}>
          <Kpi label="Welcome paid" value={`$${stats.welcome_total.toLocaleString('en-GB')}`} />
          <Kpi label="Deposit bonus paid" value={`$${stats.deposit_total.toLocaleString('en-GB')}`} />
          <Kpi label="Special offers paid" value={`$${stats.special_total.toLocaleString('en-GB')}`} />
          <Kpi label="Clawed back" value={`$${stats.clawed_back.toLocaleString('en-GB')}`} color="#e0b341" />
          <Kpi label="Clients with bonus" value={stats.clients} />
        </div>
      )}

      {/* WELCOME-BONUS REVIEW QUEUE */}
      <div style={S.card}>
        <div style={S.rowBetween}>
          <div>
            <div style={{ fontSize: 15, fontWeight: 800, color: '#e6e9ef' }}>
              👪 Welcome-bonus reviews {reviews.length > 0 && <span style={{ color: '#E8B84B' }}>({reviews.length} pending)</span>}
            </div>
            <div style={{ fontSize: 12, color: '#8A93A3', marginTop: 3 }}>
              Cases where 2 of (IB / City / Family / IP) matched another account that already got the bonus. Approve credits $50; reject blocks it.
            </div>
          </div>
        </div>
        {reviews.length === 0 ? (
          <div style={{ fontSize: 13, color: '#8A93A3', marginTop: 14, padding: '10px 0' }}>No pending reviews — nothing to action. ✅</div>
        ) : (
          <div style={{ marginTop: 14, ...CT.scroll }}>
            <table style={CT.table}>
              <thead>
                <tr style={CT.theadTr}>
                  {['Client', 'Contact', 'Login', 'Location', 'Matched signals', 'Actions'].map(h => (
                    <th key={h} style={CT.th()}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {reviews.map(r => (
                  <tr key={r.id} style={CT.row()}>
                    <td style={{ ...CT.td, color: '#e6e9ef', fontWeight: 600 }}>{r.name || '—'}</td>
                    <td style={{ ...CT.td, color: '#9aa3b2' }}>{r.email || r.phone || '—'}</td>
                    <td style={{ ...CT.td, color: '#9aa3b2' }}>{r.login || '—'}</td>
                    <td style={{ ...CT.td, color: '#9aa3b2' }}>{[r.city, r.country].filter(Boolean).join(', ') || '—'}</td>
                    <td style={{ ...CT.td, whiteSpace: 'normal' }}>
                      {(r.matched || '').split(',').filter(Boolean).map((m: string, i: number) => (
                        <span key={i} style={{ display: 'inline-block', margin: '2px 4px 2px 0', padding: '2px 8px', borderRadius: 6, fontSize: 11, fontWeight: 700, color: '#E8B84B', background: 'rgba(232,184,75,0.12)', border: '1px solid rgba(232,184,75,0.35)' }}>{m.trim()}</span>
                      ))}
                    </td>
                    <td style={CT.td}>
                      <button onClick={() => decideReview(r.id, 'approve')} style={{ marginRight: 8, padding: '6px 14px', borderRadius: 7, border: 'none', background: 'linear-gradient(90deg,#3ad29f,#2bb88a)', color: '#06231a', fontWeight: 800, fontSize: 12, cursor: 'pointer' }}>Approve</button>
                      <button onClick={() => decideReview(r.id, 'reject')} style={{ padding: '6px 14px', borderRadius: 7, border: '1px solid #f0556a', background: 'transparent', color: '#f0556a', fontWeight: 800, fontSize: 12, cursor: 'pointer' }}>Reject</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* GLOBAL TOGGLE */}
      <div style={S.card}>
        <div style={S.rowBetween}>
          <div>
            <div style={S.cardTitle}>Bonus program</div>
            <div style={S.hint}>Master switch. When off, no welcome/deposit/special bonus is offered or credited.</div>
          </div>
          <Switch on={!!cfg.bonuses_enabled} onClick={() => setCfg({ ...cfg, bonuses_enabled: !cfg.bonuses_enabled })} />
        </div>
      </div>

      {/* WELCOME BONUS */}
      <div style={S.card}>
        <div style={S.cardTitle}>Welcome bonus</div>
        <div style={S.grid3}>
          <Field label="Welcome amount ($)"><input style={S.input} value={cfg.welcome_amount} onChange={e => num('welcome_amount', e.target.value)} /></Field>
          <Field label="Min withdrawal — no deposit ($)"><input style={S.input} value={cfg.welcome_withdraw_min_nodep} onChange={e => num('welcome_withdraw_min_nodep', e.target.value)} /></Field>
          <Field label="Min withdrawal — has deposit ($)"><input style={S.input} value={cfg.welcome_withdraw_min_dep} onChange={e => num('welcome_withdraw_min_dep', e.target.value)} /></Field>
        </div>
        <div style={S.hint}>Given to a newly-verified client on a brand-new device with no network link (checked via CID).</div>
      </div>

      {/* DEPOSIT BONUS TIERS */}
      <div style={S.card}>
        <div style={S.cardTitle}>Deposit bonus (standard)</div>
        <div style={S.grid3}>
          <Field label="Tier-1 %"><input style={S.input} value={cfg.dep_tier1_pct} onChange={e => num('dep_tier1_pct', e.target.value)} /></Field>
          <Field label="Tier-1 applies to first ($ deposit)"><input style={S.input} value={cfg.dep_tier1_cap} onChange={e => num('dep_tier1_cap', e.target.value)} /></Field>
          <Field label="Tier-2 % (above tier-1)"><input style={S.input} value={cfg.dep_tier2_pct} onChange={e => num('dep_tier2_pct', e.target.value)} /></Field>
        </div>
        <div style={S.grid3}>
          <Field label="Total lifetime bonus cap ($)"><input style={S.input} value={cfg.dep_total_cap} onChange={e => num('dep_total_cap', e.target.value)} /></Field>
          <Field label="Withdrawal margin floor (%)"><input style={S.input} value={cfg.margin_floor_pct} onChange={e => num('margin_floor_pct', e.target.value)} /></Field>
          <div />
        </div>
        <div style={S.hint}>
          e.g. {cfg.dep_tier1_pct}% on the first ${Number(cfg.dep_tier1_cap).toLocaleString('en-GB')} of deposits, then {cfg.dep_tier2_pct}% above —
          capped at ${Number(cfg.dep_total_cap).toLocaleString('en-GB')} total. A deposit of $2,000 → ${(cfg.dep_tier1_cap * cfg.dep_tier1_pct / 100).toLocaleString('en-GB')} + ${((2000 - cfg.dep_tier1_cap) * cfg.dep_tier2_pct / 100).toLocaleString('en-GB')}.
          Withdrawals are blocked if they would drop margin level below {cfg.margin_floor_pct}%.
        </div>
      </div>

      {/* BIRTHDAY BONUS */}
      <div style={S.card}>
        <div style={S.rowBetween}>
          <div style={S.cardTitle}>🎂 Birthday bonus</div>
          <Switch on={cfg.birthday_enabled !== false} onClick={() => setCfg({ ...cfg, birthday_enabled: cfg.birthday_enabled === false })} />
        </div>
        <div style={S.grid3}>
          <Field label="Gift amount ($)"><input style={S.input} value={cfg.birthday_amount ?? 100} onChange={e => num('birthday_amount', e.target.value)} /></Field>
          <Field label="Claim opens (days before birthday)"><input style={S.input} value={cfg.birthday_before_days ?? 5} onChange={e => num('birthday_before_days', e.target.value)} /></Field>
          <Field label="Claim closes (days after birthday)"><input style={S.input} value={cfg.birthday_after_days ?? 2} onChange={e => num('birthday_after_days', e.target.value)} /></Field>
        </div>
        <div style={S.grid3}>
          <Field label="Must have deposited within (days)"><input style={S.input} value={cfg.birthday_deposit_window_days ?? 365} onChange={e => num('birthday_deposit_window_days', e.target.value)} /></Field>
          <div /><div />
        </div>
        <div style={S.hint}>
          A client can claim a ${Number(cfg.birthday_amount ?? 100).toLocaleString('en-GB')} gift from {cfg.birthday_before_days ?? 5} days before to {cfg.birthday_after_days ?? 2} days after their
          birthday, IF they deposited within the last {cfg.birthday_deposit_window_days ?? 365} days. In that window the client is boosted +100 on the
          Clients page with a 🎂; a successful call clears the boost (cake turns gold), and a claim turns it green.
        </div>
      </div>

      {/* BLOCKED COUNTRIES */}
      <div style={S.card}>
        <div style={S.cardTitle}>Blocked countries (no bonuses)</div>
        <input style={S.input} value={csv(cfg.blocked_countries)} onChange={e => setCfg({ ...cfg, blocked_countries: parseCsv(e.target.value) })} placeholder="India, Pakistan, Egypt" />
        <div style={S.hint}>Comma-separated. Clients in these countries get no welcome / deposit / special bonus. ISO codes (IN, PK, EG) also match.</div>
      </div>

      {/* SPECIAL OFFERS */}
      <div style={S.card}>
        <div style={S.rowBetween}>
          <div style={S.cardTitle}>Special offers (limited-time)</div>
          <button style={S.addBtn} onClick={() => setAdding(true)}>+ New offer</button>
        </div>
        {offers.length === 0 && <div style={S.hint}>No special offers. Add one (e.g. “100% up to $500”) with a deadline; it shows in the client portal and the AI bot reads it.</div>}
        {offers.map(o => (
          <div key={o.id} style={S.offerRow}>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 700, fontSize: 14 }}>
                {o.name} {!o.active && <span style={S.pill}>off</span>}
              </div>
              <div style={S.hint}>
                {o.percent}% up to ${o.cap.toLocaleString('en-GB')} · min deposit ${o.min_deposit.toLocaleString('en-GB')}
                {o.ends_at ? ` · ends ${o.ends_at.slice(0, 16)}` : ' · no deadline'}
                {o.countries?.length ? ` · ${o.countries.join(', ')}` : ' · all countries'}
              </div>
            </div>
            <Switch on={!!o.active} onClick={() => toggleOffer(o)} small />
            <button style={S.linkBtn} onClick={() => setEditing(o)}>Edit</button>
            <button style={{ ...S.linkBtn, color: '#e07a7a' }} onClick={() => delOffer(o)}>Delete</button>
          </div>
        ))}
      </div>
    </div>
  );
}

function OfferEditor({ initial, onClose, onSaved }: any) {
  const [o, setO] = useState<any>({ ...initial });
  const [saving, setSaving] = useState(false);
  const set = (k: string, v: any) => setO((p: any) => ({ ...p, [k]: v }));
  // datetime-local wants "YYYY-MM-DDTHH:mm"
  const toLocal = (s: string) => (s ? String(s).replace(' ', 'T').slice(0, 16) : '');

  const save = async () => {
    if (!o.name.trim()) { window.alert('Name is required'); return; }
    setSaving(true);
    const body = {
      ...o, percent: parseFloat(o.percent) || 0, cap: parseFloat(o.cap) || 0,
      min_deposit: parseFloat(o.min_deposit) || 0,
      starts_at: o.starts_at ? o.starts_at.replace('T', ' ') : '',
      ends_at: o.ends_at ? o.ends_at.replace('T', ' ') : '',
    };
    if (o.id) await apiPut(`/admin/bonus/offers/${o.id}`, body);
    else await apiPost('/admin/bonus/offers', body);
    setSaving(false); onSaved();
  };

  return (
    <div style={S.wrap}>
      <div style={S.head}>
        <h1 style={S.h1}>{o.id ? 'Edit' : 'New'} special offer</h1>
        <button style={S.linkBtn} onClick={onClose}>← Back</button>
      </div>
      <div style={S.card}>
        <Field label="Offer name (shown to client)"><input style={S.input} value={o.name} onChange={e => set('name', e.target.value)} placeholder="e.g. 100% Welcome Boost" /></Field>
        <div style={S.grid3}>
          <Field label="Percent (%)"><input style={S.input} value={o.percent} onChange={e => set('percent', e.target.value)} /></Field>
          <Field label="Max bonus cap ($, 0 = none)"><input style={S.input} value={o.cap} onChange={e => set('cap', e.target.value)} /></Field>
          <Field label="Min deposit ($)"><input style={S.input} value={o.min_deposit} onChange={e => set('min_deposit', e.target.value)} /></Field>
        </div>
        <div style={S.grid2}>
          <Field label="Starts (optional)"><input type="datetime-local" style={S.input} value={toLocal(o.starts_at)} onChange={e => set('starts_at', e.target.value)} /></Field>
          <Field label="Deadline / ends"><input type="datetime-local" style={S.input} value={toLocal(o.ends_at)} onChange={e => set('ends_at', e.target.value)} /></Field>
        </div>
        <Field label="Countries (comma-separated, empty = all except blocked)">
          <input style={S.input} value={csv(o.countries)} onChange={e => set('countries', parseCsv(e.target.value))} placeholder="Iraq, UAE, Jordan" />
        </Field>
        <div style={{ ...S.rowBetween, marginTop: 12 }}>
          <label style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 13 }}>
            <Switch on={!!o.active} onClick={() => set('active', !o.active)} small /> Active
          </label>
          <button style={S.saveBtn} disabled={saving} onClick={save}>{saving ? 'Saving…' : 'Save offer'}</button>
        </div>
      </div>
    </div>
  );
}

const Field = ({ label, children }: any) => (
  <div style={{ marginBottom: 12 }}><label style={S.label}>{label}</label>{children}</div>
);
const Kpi = ({ label, value, color }: any) => (
  <div style={S.kpi}><div style={S.kpiLabel}>{label}</div><div style={{ ...S.kpiVal, color: color || '#e8edf2' }}>{value}</div></div>
);
const Switch = ({ on, onClick, small }: any) => (
  <div onClick={onClick} style={{
    width: small ? 38 : 46, height: small ? 22 : 26, borderRadius: 20, cursor: 'pointer',
    background: on ? '#3ad29f' : '#3a4250', position: 'relative', transition: 'all .15s', flexShrink: 0,
  }}>
    <div style={{
      position: 'absolute', top: 3, left: on ? (small ? 19 : 23) : 3,
      width: small ? 16 : 20, height: small ? 16 : 20, borderRadius: '50%', background: '#fff', transition: 'all .15s',
    }} />
  </div>
);

const S: any = {
  wrap: { padding: 28, maxWidth: 920, margin: '0 auto', color: '#e8edf2' },
  head: { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 20 },
  h1: { fontSize: 22, fontWeight: 800, margin: 0 },
  sub: { fontSize: 13, color: '#8A93A3', marginTop: 4 },
  toast: { background: 'rgba(58,210,159,0.1)', border: '1px solid rgba(58,210,159,0.3)', color: '#3ad29f', borderRadius: 8, padding: '8px 14px', fontSize: 13, marginBottom: 14 },
  kpis: { display: 'grid', gridTemplateColumns: 'repeat(5,1fr)', gap: 10, marginBottom: 18 },
  kpi: { background: '#1b212b', border: '1px solid #2f3a48', borderRadius: 10, padding: '12px 14px' },
  kpiLabel: { fontSize: 11, color: '#8A93A3', fontWeight: 600 },
  kpiVal: { fontSize: 19, fontWeight: 800, marginTop: 4 },
  card: { background: '#1b212b', border: '1px solid #2f3a48', borderRadius: 12, padding: 18, marginBottom: 16 },
  cardTitle: { fontSize: 15, fontWeight: 800, marginBottom: 10 },
  rowBetween: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12 },
  grid3: { display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 12 },
  grid2: { display: 'grid', gridTemplateColumns: 'repeat(2,1fr)', gap: 12 },
  hint: { fontSize: 12, color: '#8A93A3', marginTop: 8, lineHeight: 1.5 },
  label: { fontSize: 11.5, color: '#8A93A3', fontWeight: 600, display: 'block', marginBottom: 6 },
  input: { width: '100%', padding: '10px 12px', borderRadius: 8, background: '#262c36', border: '1px solid #2f3a48', color: '#e8edf2', fontSize: 13.5, outline: 'none', boxSizing: 'border-box' },
  addBtn: { padding: '8px 14px', borderRadius: 8, background: '#262c36', border: '1px solid #3ad29f', color: '#3ad29f', fontWeight: 700, fontSize: 12.5, cursor: 'pointer' },
  saveBtn: { padding: '12px 24px', borderRadius: 9, background: 'linear-gradient(90deg,#3ad29f,#2bb88a)', color: '#06231a', border: 'none', fontWeight: 800, fontSize: 14, cursor: 'pointer' },
  linkBtn: { padding: '6px 10px', borderRadius: 7, background: 'transparent', border: 'none', color: '#7fa8ff', fontWeight: 700, fontSize: 12.5, cursor: 'pointer' },
  offerRow: { display: 'flex', alignItems: 'center', gap: 12, padding: '12px 0', borderTop: '1px solid #2f3a48' },
  pill: { fontSize: 10, background: '#3a4250', color: '#b9c2cf', borderRadius: 5, padding: '2px 6px', marginLeft: 6, fontWeight: 700 },
};

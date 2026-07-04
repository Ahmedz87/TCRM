import React, { useState, useEffect } from 'react';
import { apiGet, apiPost, setToken } from '../api';

function useIsMobile(bp=760){const [m,setM]=React.useState(()=>typeof window!=='undefined'&&window.innerWidth<=bp);React.useEffect(()=>{const o=()=>setM(window.innerWidth<=bp);window.addEventListener('resize',o);return()=>window.removeEventListener('resize',o);},[bp]);return m;}

function ChangePassword() {
  const mobile = useIsMobile();
  const [cur, setCur] = useState(''); const [nw, setNw] = useState(''); const [nw2, setNw2] = useState('');
  const [busy, setBusy] = useState(false); const [msg, setMsg] = useState(''); const [err, setErr] = useState('');
  const submit = async () => {
    setErr(''); setMsg('');
    if (nw.length < 8) { setErr('New password must be at least 8 characters.'); return; }
    if (nw !== nw2) { setErr('Passwords do not match.'); return; }
    setBusy(true);
    try {
      const r: any = await apiPost('/portal/auth/change-password', { current_password: cur, new_password: nw });
      if (r?.access_token) setToken(r.access_token);   // stay logged in
      setMsg('Password changed successfully.'); setCur(''); setNw(''); setNw2('');
    } catch (e: any) { setErr(e?.message || 'Could not change password.'); }
    finally { setBusy(false); }
  };
  return (
    <div style={P.panel}>
      <div style={{ fontSize: 15, fontWeight: 800, color: '#fff', marginBottom: 12 }}>Change password</div>
      <input type="password" value={cur} onChange={e => setCur(e.target.value)} placeholder="Current password" autoComplete="current-password" style={P.input} />
      <input type="password" value={nw} onChange={e => setNw(e.target.value)} placeholder="New password (min 8 chars)" autoComplete="new-password" style={{ ...P.input, marginTop: 10 }} />
      <input type="password" value={nw2} onChange={e => setNw2(e.target.value)} placeholder="Confirm new password" autoComplete="new-password" style={{ ...P.input, marginTop: 10 }} />
      {err && <div style={{ fontSize: 12.5, color: '#F2667A', marginTop: 10 }}>{err}</div>}
      {msg && <div style={{ fontSize: 12.5, color: '#34D399', marginTop: 10 }}>{msg}</div>}
      <button onClick={submit} disabled={busy || !cur || !nw} style={{ ...P.btn, width: mobile ? '100%' : undefined, opacity: busy || !cur || !nw ? 0.6 : 1 }}>{busy ? 'Saving…' : 'Update password'}</button>
    </div>
  );
}

const P: any = {
  panel: { background: '#12161F', border: '1px solid #232a38', borderRadius: 14, padding: 18, marginBottom: 16 },
  input: { width: '100%', padding: '12px 13px', borderRadius: 10, background: '#0B0E14', border: '1px solid #2a3240', color: '#fff', fontSize: 16, outline: 'none', boxSizing: 'border-box', minHeight: 44 },
  btn: { marginTop: 14, padding: '12px 20px', borderRadius: 10, background: 'linear-gradient(90deg,#F8500A,#FF7A1A)', color: '#0B0E14', border: 'none', fontSize: 14, fontWeight: 800, cursor: 'pointer', minHeight: 44 },
};

function KycDocuments({ me }: any) {
  const [data, setData] = useState<any>(null);
  useEffect(() => { apiGet('/portal/kyc/documents').then(setData).catch(() => setData({ documents: [] })); }, []);
  if (!data) return null;
  const docs = data.documents || [];
  const approved = data.overall === 'approved';
  if (!docs.length && !approved) return null;   // nothing uploaded yet -> the dashboard "verify" banner covers it
  const reason = data.reason || '';
  const rejected = docs.some((d: any) => d.status === 'rejected');
  const docsNeeded = data.overall === 'docs_needed';
  // when approved, the verified identity fields each get a green check
  const verifiedRows: [string, any][] = [['Mobile', me?.phone], ['Email', me?.email], ['KYC ID', data.id_number], ['Address', data.address]];
  const badge = (status: string) => {
    const map: any = {
      approved:     { t: 'Approved',    c: '#34D399', bg: 'rgba(52,211,153,0.12)', b: 'rgba(52,211,153,0.30)' },
      under_review: { t: 'Under Review', c: '#F8500A', bg: 'rgba(232,184,75,0.12)', b: 'rgba(232,184,75,0.30)' },
      rejected:     { t: 'Rejected',    c: '#F2667A', bg: 'rgba(240,85,106,0.12)', b: 'rgba(240,85,106,0.30)' },
      not_submitted:{ t: 'Not submitted', c: '#8A93A3', bg: 'rgba(138,147,163,0.12)', b: 'rgba(138,147,163,0.30)' },
    };
    const s = map[status] || map.under_review;
    // hover on a rejected badge reveals WHY (native tooltip)
    return <span title={status === 'rejected' ? (reason || 'Rejected — please re-upload') : undefined}
      style={{ fontSize: 11, fontWeight: 800, color: s.c, background: s.bg, border: `1px solid ${s.b}`, borderRadius: 99, padding: '3px 10px', cursor: status === 'rejected' ? 'help' : 'default' }}>
      {status === 'under_review' ? '⏳ ' : status === 'approved' ? '✓ ' : status === 'rejected' ? '⚠ ' : ''}{s.t}</span>;
  };
  return (
    <div style={P.panel}>
      <div style={{ fontSize: 15, fontWeight: 800, color: '#fff', marginBottom: 4 }}>Verification documents</div>
      <div style={{ fontSize: 12, color: '#8A93A3', marginBottom: 12 }}>The documents you uploaded and their review status.</div>
      {(rejected || docsNeeded) && reason && (
        <div style={{ fontSize: 12, color: docsNeeded ? '#F8500A' : '#F2667A', background: docsNeeded ? 'rgba(232,184,75,0.08)' : 'rgba(240,85,106,0.08)', border: `1px solid ${docsNeeded ? 'rgba(232,184,75,0.28)' : 'rgba(240,85,106,0.25)'}`, borderRadius: 8, padding: '9px 12px', marginBottom: 12, lineHeight: 1.5 }}>
          {docsNeeded ? '📄' : '⚠'} {reason}
        </div>
      )}
      {approved && (
        <div style={{ marginBottom: 14 }}>
          {verifiedRows.filter(([, v]) => v).map(([label, val], i) => (
            <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '9px 0', borderBottom: '1px solid #1A1F2B' }}>
              <span style={{ fontSize: 12.5, color: '#8A93A3' }}>{label}</span>
              <span style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: '#fff', fontWeight: 600 }}>
                {val}<span style={{ color: '#34D399', fontWeight: 800 }}>✓</span>
              </span>
            </div>
          ))}
        </div>
      )}
      {docs.map((d: any, i: number) => (
        <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '11px 0', borderBottom: i < docs.length - 1 ? '1px solid #1A1F2B' : 'none' }}>
          <div>
            <div style={{ fontSize: 13.5, color: '#fff', fontWeight: 600 }}>📄 {d.label || d.side}</div>
            {d.status === 'approved' && d.expiry_date && <div style={{ fontSize: 11, color: '#8A93A3', marginTop: 2 }}>Expires: {d.expiry_date}</div>}
          </div>
          {badge(d.status)}
        </div>
      ))}
    </div>
  );
}

export default function Profile() {
  const mobile = useIsMobile();
  const [me, setMe] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => { apiGet('/portal/me').then(setMe).catch(() => {}).finally(() => setLoading(false)); }, []);

  if (loading) return <div style={S.page}><div style={S.empty}>Loading…</div></div>;
  if (!me) return <div style={S.page}><div style={S.empty}>Could not load profile.</div></div>;

  const rows = [
    { label: 'Full name', value: me.name },
    { label: 'Email', value: me.email || '—' },
    { label: 'Phone', value: me.phone || '—' },
    { label: 'City', value: me.city || '—' },
    { label: 'Country', value: me.country || '—' },
    { label: 'Client ID', value: `#${me.client_id}` },
    { label: 'Loyalty tier', value: me.tier ? me.tier.charAt(0).toUpperCase() + me.tier.slice(1) : '—' },
  ];

  return (
    <div style={S.page}>
      <h1 style={S.h1}>Profile</h1>
      <div style={S.headCard}>
        <div style={S.avatar}>{(me.name || '?').split(' ').slice(0, 2).map((w: string) => w[0]).join('').toUpperCase()}</div>
        <div>
          <div style={{ fontSize: 20, fontWeight: 800, color: '#fff' }}>{me.name}</div>
          <div style={{ fontSize: 12.5, color: '#8A93A3', textTransform: 'capitalize' }}>{me.tier || 'member'} · {Math.round(me.points || 0).toLocaleString()} points</div>
        </div>
      </div>

      <div style={S.panel}>
        {rows.map((r, i) => (
          <div key={i} style={{ ...S.row, flexDirection: mobile ? 'column' : 'row', alignItems: mobile ? 'flex-start' : 'center', gap: mobile ? 3 : 12, borderBottom: i < rows.length - 1 ? '1px solid #1A1F2B' : 'none' }}>
            <span style={S.rowLabel}>{r.label}</span>
            <span style={{ ...S.rowValue, textAlign: mobile ? 'left' : 'right', wordBreak: 'break-word', maxWidth: '100%' }}>{r.value}</span>
          </div>
        ))}
      </div>

      <KycDocuments me={me} />

      <ChangePassword />

      <div style={S.note}>
        To update your personal details, please contact support — profile editing will be available soon.
      </div>
    </div>
  );
}

const S: any = {
  page: { padding: 'clamp(16px, 5vw, 28px)', maxWidth: 640, margin: '0 auto' },
  h1: { fontSize: 24, fontWeight: 800, margin: '0 0 20px', color: '#fff' },
  headCard: { display: 'flex', alignItems: 'center', gap: 16, background: 'linear-gradient(160deg,#12161F,#0d1016)', border: '1px solid #232a38', borderRadius: 16, padding: 22, marginBottom: 20 },
  avatar: { width: 60, height: 60, borderRadius: 99, background: 'linear-gradient(135deg,#F8500A,#C77B45)', color: '#0B0E14', display: 'grid', placeItems: 'center', fontWeight: 800, fontSize: 22 },
  panel: { background: '#12161F', border: '1px solid #232a38', borderRadius: 14, padding: '4px 18px', marginBottom: 16 },
  row: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '14px 0' },
  rowLabel: { fontSize: 12.5, color: '#8A93A3' },
  rowValue: { fontSize: 13.5, color: '#fff', fontWeight: 600 },
  empty: { padding: 30, textAlign: 'center', color: '#8A93A3', fontSize: 14, background: '#12161F', border: '1px solid #232a38', borderRadius: 14 },
  note: { fontSize: 12, color: '#8A93A3', lineHeight: 1.5, padding: '0 4px' },
};

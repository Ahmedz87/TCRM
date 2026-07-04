import React, { useEffect, useState } from 'react';
import { apiGet, apiPost } from './api';

// KYC results for a lead: Claude-extracted ID fields + local face-match score + auto-verify
// verdict + network/family cross-check. Shown on the lead's Verification tab.
const VS: any = {
  verified: { c: '#00e5a0', label: '✓ Verified' },
  review:   { c: '#ffaa00', label: '⚠ Needs review' },
  rejected: { c: '#ff5d6c', label: '✗ Rejected' },
  pending:  { c: '#9aa3b3', label: '… Pending' },
};
const FACE: any = {
  match:    { c: '#00e5a0', label: '✓ Face match' },
  review:   { c: '#ffaa00', label: '⚠ Face uncertain' },
  mismatch: { c: '#ff5d6c', label: '✗ Face mismatch' },
  no_face:  { c: '#9aa3b3', label: 'No face detected' },
  no_selfie:{ c: '#9aa3b3', label: 'No selfie' },
};
const FIELD_LABELS: [string, string][] = [
  ['full_name', 'Full name'], ['full_name_ar', 'Name (Arabic)'], ['id_number', 'ID number'],
  ['date_of_birth', 'Date of birth'], ['expiry_date', 'Expiry'], ['issue_date', 'Issued'],
  ['mother_name', 'Mother name'], ['mother_father_name', "Mother's father"],
  ['father_name', 'Father name'], ['grandfather_name', 'Grandfather'], ['surname', 'Surname'],
  ['family_code', 'Family code'], ['city', 'City'], ['place_of_birth', 'Place of birth'],
  ['gender', 'Gender'], ['nationality', 'Nationality'],
];

export default function KYCPanel({ leadId }: { leadId: number }) {
  const [d, setD] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [act, setAct] = useState<any>(null);
  const [activating, setActivating] = useState(false);
  const [credit, setCredit] = useState('0');

  useEffect(() => {
    setLoading(true);
    apiGet(`/register/kyc/by-lead/${leadId}`).then(setD).catch(() => setD(null)).finally(() => setLoading(false));
  }, [leadId]);

  const activate = async () => {
    if (!d?.registration_id) return;
    setActivating(true); setAct(null);
    try {
      const r = await apiPost(`/register/activate/${d.registration_id}`, { credit: parseFloat(credit) || 0 });
      setAct(r);
      if (r?.ok) apiGet(`/register/kyc/by-lead/${leadId}`).then(setD).catch(() => {});
    } catch { setAct({ ok: false, error: 'request failed' }); }
    setActivating(false);
  };

  const card: React.CSSProperties = { background: '#2c333e', borderRadius: 12, padding: 18, border: '1px solid #373f4d' };
  const cap: React.CSSProperties = { fontSize: 11, color: '#666', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 14, fontWeight: 600 };

  if (loading) return <div style={{ color: '#888', fontSize: 13 }}>Loading KYC…</div>;
  if (!d || !d.found) return (
    <div style={{ ...card, color: '#9aa3b3', fontSize: 13 }}>
      No KYC submission for this lead yet. KYC results appear here after the client uploads documents in the registration wizard.
    </div>
  );

  // Never present a SIMULATED/placeholder OCR payload as if it were read from the document.
  // Real Claude OCR (kyc_ai) never sets these flags; a demo/fallback generator does. If flagged,
  // blank the fields so a fabricated id_number (etc.) is never shown to the desk. (Ticket #25.)
  const rawF = d.fields || {};
  const simulated = !!(rawF._simulated || rawF._status === 'simulated' || rawF._status === 'placeholder');
  const f = simulated ? { _status: rawF._status || 'simulated' } : rawF;
  const pending = !f.full_name || f._status === 'pending_no_key' || simulated;
  const vs = VS[d.verify_status] || VS.pending;
  const face = FACE[d.face_verdict] || null;
  const net = d.network || {};

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, alignItems: 'start' }}>
      {/* LEFT: verdict + extracted fields */}
      <div style={{ display: 'grid', gap: 16 }}>
        <div style={card}>
          <div style={cap}>🛡️ Verification</div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center', marginBottom: 6 }}>
            <span style={{ fontSize: 14, fontWeight: 800, color: vs.c, padding: '4px 12px', borderRadius: 8, background: vs.c + '1a' }}>{vs.label}</span>
            {d.name_match != null && <Chip ok={d.name_match} t={d.name_match ? 'Name matches' : 'Name mismatch'} />}
            {d.doc_expired != null && <Chip ok={!d.doc_expired} t={d.doc_expired ? 'Expired' : 'Not expired'} />}
          </div>
          {d.processed_at && <div style={{ fontSize: 11, color: '#666' }}>Checked {d.processed_at.replace('T', ' ').slice(0, 16)}</div>}
        </div>

        {/* Verify & activate — create the real MT account */}
        <div style={card}>
          <div style={cap}>🚀 Trading account</div>
          {d.activated ? (
            <div style={{ fontSize: 13, color: '#00e5a0', fontWeight: 700 }}>✓ Active — MT login {d.mt_login}</div>
          ) : act?.ok ? (
            <div>
              <div style={{ fontSize: 13, color: '#00e5a0', fontWeight: 800, marginBottom: 8 }}>✓ Account created — login {act.login}</div>
              <div style={{ fontSize: 11, color: '#ffaa00', marginBottom: 8 }}>Give these to the client — shown once:</div>
              {[['MT login', act.login], ['Master password', act.master_password], ['Investor password', act.investor_password], ['Group', act.group]].map(([k, v]: any) => (
                <div key={k} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid #373f4d', fontSize: 12 }}>
                  <span style={{ color: '#666' }}>{k}</span>
                  <span style={{ color: '#e0e0e0', fontFamily: 'monospace', fontWeight: 600 }}>{v}</span>
                </div>
              ))}
            </div>
          ) : (
            <div>
              <div style={{ fontSize: 12, color: '#9aa3b3', marginBottom: 10 }}>
                Creates the real {d.account?.platform || 'MT5'} account ({d.account?.type}{d.account?.islamic ? ' · Islamic' : ''}, {d.account?.leverage}) and maps the client to it.
                {d.verify_status !== 'verified' && <span style={{ color: '#ffaa00' }}> ⚠ KYC not fully verified yet.</span>}
              </div>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 10 }}>
                <span style={{ fontSize: 12, color: '#666' }}>Welcome credit&nbsp;$</span>
                <input value={credit} onChange={e => setCredit(e.target.value.replace(/[^0-9.]/g, ''))} style={{ width: 80, padding: '6px 8px', background: '#1c2231', border: '1px solid #373f4d', borderRadius: 7, color: '#e0e0e0', fontSize: 12 }} />
              </div>
              <button onClick={activate} disabled={activating} style={{ width: '100%', padding: '10px', background: '#00e5a0', border: 'none', borderRadius: 8, color: '#06251b', fontSize: 13, fontWeight: 700, cursor: 'pointer', opacity: activating ? 0.6 : 1 }}>{activating ? 'Creating account…' : '🚀 Verify & activate — create MT account'}</button>
              {act && !act.ok && <div style={{ fontSize: 12, color: '#ff5d6c', marginTop: 8 }}>{act.error}</div>}
            </div>
          )}
        </div>

        <div style={card}>
          <div style={cap}>🪪 Document fields {pending && <span style={{ color: '#ffaa00', textTransform: 'none', letterSpacing: 0 }}>· reading pending (add AI key)</span>}</div>
          {pending && !Object.keys(f).filter(k => !k.startsWith('_')).length ? (
            <div style={{ color: '#9aa3b3', fontSize: 12 }}>Document uploaded — fields will fill once the AI key is configured.</div>
          ) : FIELD_LABELS.map(([k, lbl]) => {
            const val = (f[k] != null && String(f[k]).trim() !== '') ? String(f[k]) : '';
            return (
              <div key={k} style={{ display: 'flex', justifyContent: 'space-between', padding: '7px 0', borderBottom: '1px solid #373f4d', fontSize: 12 }}>
                <span style={{ color: '#666' }}>{lbl}</span>
                <span style={{ color: val ? '#e0e0e0' : '#5a6172', fontWeight: 500, textAlign: 'right', maxWidth: '60%', wordBreak: 'break-word' }}>{val || '—'}</span>
              </div>
            );
          })}
          {/* surface any extra OCR keys not in the known label list (never a fabricated value) */}
          {Object.keys(f).filter(k => !k.startsWith('_') && !FIELD_LABELS.some(([lk]) => lk === k) && String(f[k] ?? '').trim() !== '').map(k => (
            <div key={k} style={{ display: 'flex', justifyContent: 'space-between', padding: '7px 0', borderBottom: '1px solid #373f4d', fontSize: 12 }}>
              <span style={{ color: '#666' }}>{k.replace(/_/g, ' ')}</span>
              <span style={{ color: '#e0e0e0', fontWeight: 500, textAlign: 'right', maxWidth: '60%', wordBreak: 'break-word' }}>{String(f[k])}</span>
            </div>
          ))}
        </div>
      </div>

      {/* RIGHT: face match + network */}
      <div style={{ display: 'grid', gap: 16 }}>
        <div style={card}>
          <div style={cap}>🤳 Face match (selfie ↔ ID)</div>
          {face ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <span style={{ fontSize: 14, fontWeight: 800, color: face.c, padding: '4px 12px', borderRadius: 8, background: face.c + '1a' }}>{face.label}</span>
              {d.face_score != null && <span style={{ fontSize: 13, color: '#9aa3b3' }}>score {(d.face_score * 100).toFixed(0)}%</span>}
            </div>
          ) : <div style={{ color: '#9aa3b3', fontSize: 12 }}>No selfie / ID to compare yet.</div>}
          <div style={{ fontSize: 11, color: '#555', marginTop: 8 }}>Runs locally on the server — biometric data never leaves the box.</div>
        </div>

        <div style={card}>
          <div style={cap}>🕸️ Network & family cross-check</div>
          <div style={{ marginBottom: 8 }}>
            <span style={{ fontSize: 13, fontWeight: 700, color: net.level === 'strong' ? '#ff8800' : '#00e5a0' }}>
              {net.level === 'strong' ? '⚠ Linked to existing records' : '✓ No links found'}
            </span>
          </div>
          {[['Same phone on file', net.dup_phone], ['Same email on file', net.dup_email],
            ['ID number reused', net.id_number_reused]].map(([lbl, v]: any) => (
            <div key={lbl} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid #373f4d', fontSize: 12 }}>
              <span style={{ color: '#666' }}>{lbl}</span>
              <span style={{ color: v ? '#ff8800' : '#9aa3b3', fontWeight: 600 }}>{v || 0}</span>
            </div>
          ))}
          {net.family_code && (
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', fontSize: 12 }}>
              <span style={{ color: '#666' }}>Official family ID</span>
              <span style={{ color: '#e0e0e0', fontWeight: 600 }}>{net.family_code}</span>
            </div>
          )}
          {net.family && (net.family.family_code || net.family.count > 0) && (
            <div style={{ padding: '6px 0', fontSize: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: '#666' }}>Internal family code</span>
                <span style={{ color: net.family.color === 'green' ? '#00e5a0' : '#E8B84B', fontWeight: 700 }}>
                  {net.family.family_code || '—'} {net.family.count ? `· ${net.family.count} ${net.family.color === 'green' ? 'family' : 'probable'}` : ''}
                </span>
              </div>
              {(net.family.members || []).length > 0 && (
                <div style={{ color: '#9aa3b3', marginTop: 4 }}>
                  {net.family.members.map((m: any, i: number) => (
                    <span key={i}>{m.name} <span style={{ color: m.color === 'green' ? '#00e5a0' : '#E8B84B' }}>({m.link})</span>{i < net.family.members.length - 1 ? ', ' : ''}</span>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Chip({ ok, t }: { ok: boolean; t: string }) {
  const c = ok ? '#00e5a0' : '#ff5d6c';
  return <span style={{ fontSize: 11, fontWeight: 700, color: c, padding: '3px 9px', borderRadius: 7, background: c + '1a' }}>{ok ? '✓' : '✗'} {t}</span>;
}

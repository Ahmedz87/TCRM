import React, { useEffect, useState } from 'react';
import { apiGet, apiPost } from './api';

// Staff KYC review console (sidebar "KYC"). Lists every registration that uploaded documents,
// shows the AI verdict + reason + the document images, and lets the verification team
// Approve / Reject (with a comment). Backed by /kyc-admin/*.

const STATUS_META: Record<string, { label: string; c: string; bg: string }> = {
  approved:     { label: 'Approved',              c: '#00e5a0', bg: 'rgba(0,229,160,0.12)' },
  under_review: { label: 'Under Review',          c: '#E8B84B', bg: 'rgba(232,184,75,0.12)' },
  admin_review: { label: 'Admin review required', c: '#ff9f43', bg: 'rgba(255,159,67,0.12)' },
  rejected:     { label: 'Rejected',              c: '#ff5d6c', bg: 'rgba(255,93,108,0.12)' },
  duplicate:    { label: 'Duplicate',             c: '#3a86ff', bg: 'rgba(58,134,255,0.12)' },
  pending:      { label: 'Pending',               c: '#8a93a5', bg: 'rgba(138,147,165,0.12)' },
};

function Badge({ status }: { status: string }) {
  const s = STATUS_META[status] || STATUS_META.under_review;
  return <span style={{ fontSize: 11, fontWeight: 700, color: s.c, background: s.bg, border: `1px solid ${s.c}55`, borderRadius: 99, padding: '3px 10px', whiteSpace: 'nowrap' }}>{s.label}</span>;
}

const CHIPS = [
  { key: 'all', label: 'All' },
  { key: 'under_review', label: 'Under Review' },
  { key: 'admin_review', label: 'Admin review' },
  { key: 'duplicate', label: 'Duplicate' },
  { key: 'rejected', label: 'Rejected' },
  { key: 'approved', label: 'Approved' },
  { key: 'pending', label: 'Pending' },
];

function DocImage({ rid, doc, onDecide }: { rid: number; doc: any; onDecide?: (docId: number, decision: 'approve' | 'reject') => void }) {
  const [url, setUrl] = useState('');
  useEffect(() => {
    let dead = false; let obj = '';
    const token = localStorage.getItem('token') || '';
    fetch(`/api/kyc-admin/${rid}/doc/${doc.id}`, { headers: { Authorization: 'Bearer ' + token } })
      .then(r => (r.ok ? r.blob() : Promise.reject()))
      .then(b => { obj = URL.createObjectURL(b); if (!dead) setUrl(obj); })
      .catch(() => {});
    return () => { dead = true; if (obj) URL.revokeObjectURL(obj); };
  }, [rid, doc.id]);
  const label = ({ front: 'ID front', back: 'ID back', main: 'Passport', selfie: 'Selfie', proof_of_address: 'Proof of address', proof_of_address_back: 'Proof — back' } as any)[doc.side] || doc.side;
  const sc: any = { approved: '#00e5a0', rejected: '#ff5d6c' };
  const ds = (doc.status || '').toLowerCase();
  return (
    <div style={{ width: 150 }}>
      <div style={{ fontSize: 11, color: '#8a93a5', marginBottom: 4, display: 'flex', justifyContent: 'space-between' }}>
        <span>{label}</span>
        {sc[ds] && <span style={{ color: sc[ds], fontWeight: 700 }}>{ds === 'approved' ? '✓' : '✗'}</span>}
      </div>
      {url
        ? <a href={url} target="_blank" rel="noreferrer"><img src={url} alt={label} style={{ width: 150, height: 100, objectFit: 'cover', borderRadius: 8, border: `1px solid ${sc[ds] || 'var(--border,#4f596b)'}` }} /></a>
        : <div style={{ width: 150, height: 100, borderRadius: 8, border: '1px solid var(--border,#4f596b)', display: 'grid', placeItems: 'center', color: '#5b6679', fontSize: 11 }}>…</div>}
      {onDecide && (
        <div style={{ display: 'flex', gap: 6, marginTop: 6 }}>
          <button onClick={() => onDecide(doc.id, 'approve')} style={{ flex: 1, padding: '5px', borderRadius: 6, border: 'none', background: 'rgba(0,229,160,0.15)', color: '#00e5a0', fontSize: 11, fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit' }}>✓ OK</button>
          <button onClick={() => onDecide(doc.id, 'reject')} style={{ flex: 1, padding: '5px', borderRadius: 6, border: '1px solid #ff5d6c', background: 'transparent', color: '#ff5d6c', fontSize: 11, fontWeight: 700, cursor: 'pointer', fontFamily: 'inherit' }}>✗ No</button>
        </div>
      )}
    </div>
  );
}

export default function KycReview() {
  const [status, setStatus] = useState('all');
  const [items, setItems] = useState<any[]>([]);
  const [counts, setCounts] = useState<any>({});
  const [search, setSearch] = useState('');
  const [sel, setSel] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [comment, setComment] = useState('');
  const [sortKey, setSortKey] = useState('processed_at');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');

  const sorted = React.useMemo(() => {
    const arr = [...items];
    arr.sort((a, b) => {
      let av = a[sortKey], bv = b[sortKey];
      if (sortKey === 'location') { av = [a.country, a.city].filter(Boolean).join(' '); bv = [b.country, b.city].filter(Boolean).join(' '); }
      av = (av ?? '').toString().toLowerCase(); bv = (bv ?? '').toString().toLowerCase();
      if (av < bv) return sortDir === 'asc' ? -1 : 1;
      if (av > bv) return sortDir === 'asc' ? 1 : -1;
      return 0;
    });
    return arr;
  }, [items, sortKey, sortDir]);
  const toggleSort = (k: string) => { if (sortKey === k) setSortDir(d => (d === 'asc' ? 'desc' : 'asc')); else { setSortKey(k); setSortDir('asc'); } };

  const load = () => {
    apiGet(`/kyc-admin/list?status=${status}&search=${encodeURIComponent(search)}`).then(d => setItems(d.items || [])).catch(() => setItems([]));
    apiGet('/kyc-admin/counts').then(setCounts).catch(() => {});
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [status]);

  const openDetail = (rid: number) => {
    setSel({ loading: true }); setRejecting(false); setComment('');
    apiGet(`/kyc-admin/${rid}`).then(setSel).catch(() => setSel(null));
  };

  const decideDoc = async (docId: number, decision: 'approve' | 'reject') => {
    if (!sel) return;
    try {
      await apiPost(`/kyc-admin/${sel.registration_id}/doc/${docId}/decision`, { decision });
      openDetail(sel.registration_id); load();
    } catch (e) { /* ignore */ }
  };

  const decide = async (decision: 'approve' | 'reject') => {
    if (!sel) return;
    if (decision === 'reject' && !rejecting) { setRejecting(true); return; }
    setBusy(true);
    try {
      await apiPost(`/kyc-admin/${sel.registration_id}/decision`, { decision, comment });
      setSel(null); load();
    } catch (e) { /* ignore */ }
    finally { setBusy(false); }
  };

  const card = { background: 'var(--bg-card,#2c333e)', border: '1px solid var(--border,#4f596b)', borderRadius: 10 };

  return (
    <div style={{ display: 'flex', gap: 16, height: '100%', minHeight: 0 }}>
      {/* LEFT: queue */}
      <div style={{ flex: sel ? '0 0 34%' : '1', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
        <h2 style={{ margin: '0 0 4px', fontSize: 22, color: 'var(--text,#e6e9ef)' }}>🪪 KYC Verification</h2>
        <p style={{ margin: '0 0 14px', fontSize: 13, color: '#8a93a5' }}>Review documents uploaded by registrants and approve or reject.</p>

        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 12 }}>
          {CHIPS.map(c => (
            <button key={c.key} onClick={() => setStatus(c.key)}
              style={{ padding: '6px 12px', borderRadius: 7, cursor: 'pointer', fontSize: 12, fontFamily: 'inherit',
                border: `1px solid ${status === c.key ? '#00e5a0' : '#626d80'}`, background: status === c.key ? 'rgba(0,229,160,0.1)' : 'transparent', color: status === c.key ? '#00e5a0' : '#8a93a5' }}>
              {c.label}{counts[c.key] != null ? ` (${counts[c.key]})` : ''}
            </button>
          ))}
        </div>

        <input value={search} onChange={e => setSearch(e.target.value)} onKeyDown={e => e.key === 'Enter' && load()}
          placeholder="Search name / email / phone — press Enter"
          style={{ ...card, padding: '9px 12px', color: 'var(--text,#e6e9ef)', fontSize: 13, marginBottom: 12, outline: 'none' }} />

        <div style={{ ...card, flex: 1, overflow: 'auto', minHeight: 0 }}>
          {items.length === 0
            ? <div style={{ padding: 24, textAlign: 'center', color: '#8a93a5', fontSize: 13 }}>No submissions in this view.</div>
            : (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
              <thead>
                <tr style={{ position: 'sticky', top: 0, background: 'var(--bg-card,#2c333e)', zIndex: 1 }}>
                  {([['name', 'Name'], ['contact', 'Contact'], ['location', 'Location'], ...(sel ? [] : [['n_docs', 'Docs'], ['processed_at', 'Reviewed']] as any), ['status', 'Status']] as any[]).map(([k, label]) => (
                    <th key={k} onClick={() => toggleSort(k === 'contact' ? 'email' : k)}
                      style={{ textAlign: 'left', padding: '9px 12px', color: '#8a93a5', fontWeight: 600, cursor: 'pointer', borderBottom: '1px solid var(--border,#4f596b)', whiteSpace: 'nowrap' }}>
                      {label}{(sortKey === k || (k === 'contact' && sortKey === 'email')) ? (sortDir === 'asc' ? ' ▲' : ' ▼') : ''}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {sorted.map(it => (
                  <tr key={it.registration_id} onClick={() => openDetail(it.registration_id)}
                    style={{ cursor: 'pointer', borderBottom: '1px solid var(--border,#3a4250)', background: sel?.registration_id === it.registration_id ? 'rgba(0,229,160,0.06)' : 'transparent' }}>
                    <td style={{ padding: '10px 12px', color: 'var(--text,#e6e9ef)', fontWeight: 600 }}>{it.name}</td>
                    <td style={{ padding: '10px 12px', color: '#8a93a5', maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{it.email || it.phone || '—'}</td>
                    <td style={{ padding: '10px 12px', color: '#8a93a5', whiteSpace: 'nowrap' }}>{[it.city, it.country].filter(Boolean).join(', ') || '—'}</td>
                    {!sel && <td style={{ padding: '10px 12px', color: '#8a93a5', textAlign: 'center' }}>{it.n_docs}</td>}
                    {!sel && <td style={{ padding: '10px 12px', color: '#8a93a5', whiteSpace: 'nowrap' }}>{(it.processed_at || it.created_at || '').slice(0, 16).replace('T', ' ') || '—'}</td>}
                    <td style={{ padding: '10px 12px' }}>
                      <Badge status={it.status} />
                      {it.poa_review && <span title={`Address proof in another name${it.poa_holder ? ' (' + it.poa_holder + ')' : ''} — confirm family via Family ID`}
                        style={{ marginLeft: 6, display: 'inline-block', padding: '2px 7px', borderRadius: 6, fontSize: 10.5, fontWeight: 800, color: '#E8B84B', background: 'rgba(232,184,75,0.14)', border: '1px solid rgba(232,184,75,0.4)' }}>👪 Family POA</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* RIGHT: detail */}
      {sel && (
        <div style={{ ...card, flex: 1, overflow: 'auto', minHeight: 0, padding: 18 }}>
          {sel.loading ? <div style={{ color: '#8a93a5' }}>Loading…</div> : (<>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
              <div>
                <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--text,#e6e9ef)' }}>{sel.name || '—'}</div>
                <div style={{ fontSize: 12, color: '#8a93a5', marginTop: 2 }}>{sel.email || '—'} · {sel.phone || '—'}</div>
              </div>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <Badge status={sel.status} />
                <button onClick={() => setSel(null)} style={{ background: 'none', border: 'none', color: '#8a93a5', fontSize: 18, cursor: 'pointer' }}>✕</button>
              </div>
            </div>

            {sel.reason && <div style={{ fontSize: 12.5, color: '#cdd5e0', background: 'var(--bg,#1b2129)', border: '1px solid var(--border,#4f596b)', borderRadius: 8, padding: '9px 12px', marginBottom: 14 }}>📝 {sel.reason}</div>}

            {sel.poa?.verdict === 'household_ok' && sel.poa?.note && (
              <div style={{ fontSize: 12, color: '#34D399', background: 'rgba(52,211,153,0.10)', border: '1px solid rgba(52,211,153,0.32)', borderRadius: 8, padding: '10px 12px', marginBottom: 14, lineHeight: 1.55 }}>
                <b>👪 Proof of address accepted (family).</b><br />
                {sel.poa.note}
              </div>
            )}

            {(sel.poa?.verdict === 'need_family_id' || sel.poa?.manual_review) && (
              <div style={{ fontSize: 12, color: '#E8B84B', background: 'rgba(232,184,75,0.10)', border: '1px solid rgba(232,184,75,0.35)', borderRadius: 8, padding: '10px 12px', marginBottom: 14, lineHeight: 1.55 }}>
                <b>👪 Proof of address in another name — manual review.</b><br />
                The address proof is in the name of <b style={{ color: '#fff' }}>{sel.poa?.holder_name || 'another person'}</b>, not the applicant.
                {sel.poa?.relationship && <> Name-chain analysis suggests this is the applicant's <b style={{ color: '#fff' }}>{sel.poa.relationship}</b>.</>}
                {sel.poa?.family_id_provided
                  ? <> A family member's ID was supplied (<b style={{ color: '#fff' }}>{sel.poa?.family_member_name || '—'}</b>) but the Family ID {sel.poa?.family_id_match ? 'matches' : <b style={{ color: '#fff' }}>does NOT match</b>} the applicant's{sel.poa?.applicant_family_code || sel.poa?.family_member_family_code ? ` (applicant ${sel.poa?.applicant_family_code || '?'} vs family ${sel.poa?.family_member_family_code || '?'})` : ''}.</>
                  : <> We've asked the client to upload that person's ID to confirm the household via the shared Family ID. Sales may call to assist.</>}
                {sel.poa?.address_match && <> Address on the bill matches the applicant's address ✓.</>}
              </div>
            )}

            {/* matched existing account (duplicate ID) — the account we already have */}
            {sel.network?.existing_account && (
              <div style={{ background: 'rgba(58,134,255,0.08)', border: '1px solid rgba(58,134,255,0.30)', borderRadius: 8, padding: '11px 13px', marginBottom: 14 }}>
                <div style={{ fontSize: 12, fontWeight: 700, color: '#3a86ff', marginBottom: 6 }}>👤 Matches an existing account (same ID)</div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2,1fr)', gap: 6, fontSize: 12 }}>
                  {[['Name', sel.network.existing_account.name], ['Email', sel.network.existing_account.email], ['Phone', sel.network.existing_account.phone], ['Login', sel.network.existing_account.login], ['Registered', (sel.network.existing_account.created_at || '').slice(0, 10)], ['Reg #', sel.network.existing_account.registration_id]].map(([k, v]: any, i: number) => (
                    <div key={i}><span style={{ color: '#8a93a5' }}>{k}: </span><span style={{ color: 'var(--text,#e6e9ef)', fontWeight: 600 }}>{v || '—'}</span></div>
                  ))}
                </div>
              </div>
            )}

            {/* family group (same family code / same address) — OK to approve, not a duplicate */}
            {sel.network?.family && (sel.network.family.count > 0 || sel.network.family.family_code) && (() => {
              const fam = sel.network.family; const green = fam.color === 'green';
              const col = green ? '#00e5a0' : '#E8B84B';
              const bg = green ? 'rgba(0,229,160,0.08)' : 'rgba(232,184,75,0.10)';
              return (
                <div style={{ background: bg, border: `1px solid ${col}55`, borderRadius: 8, padding: '11px 13px', marginBottom: 14 }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: col, marginBottom: 4 }}>
                    👨‍👩‍👧 {green ? 'Confirmed family (approve)' : (fam.count ? 'Probable family — review' : 'Family group')}
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2,1fr)', gap: 4, fontSize: 11.5, marginBottom: fam.count ? 6 : 0 }}>
                    <div><span style={{ color: '#8a93a5' }}>Internal family code: </span><span style={{ color: 'var(--text,#e6e9ef)', fontWeight: 600 }}>{fam.family_code || '—'}</span></div>
                    <div><span style={{ color: '#8a93a5' }}>Official family ID: </span><span style={{ color: 'var(--text,#e6e9ef)', fontWeight: 600 }}>{fam.official_family_id || '—'}</span></div>
                  </div>
                  {fam.count > 0 && <div style={{ fontSize: 12 }}>
                    {(fam.members || []).map((m: any, i: number) => (
                      <span key={i} style={{ color: 'var(--text,#e6e9ef)' }}>{m.name || ('Reg #' + m.registration_id)} <span style={{ color: m.color === 'green' ? '#00e5a0' : '#E8B84B' }}>({m.link})</span>{i < fam.members.length - 1 ? ' · ' : ''}</span>
                    ))}
                  </div>}
                </div>
              );
            })()}

            {/* key ID details — DOB + Family ID (from the back) + mother & her father in one line */}
            {sel.ocr_fields && (sel.ocr_fields.date_of_birth || sel.ocr_fields.family_code || sel.ocr_fields.mother_name) && (
              <div style={{ background: 'var(--bg,#1b2129)', border: '1px solid var(--border,#3a4250)', borderRadius: 8, padding: '10px 13px', marginBottom: 14 }}>
                <div style={{ fontSize: 11, color: '#8a93a5', textTransform: 'uppercase', letterSpacing: '.5px', marginBottom: 6 }}>Key ID details</div>
                <div style={{ display: 'grid', gap: 5, fontSize: 12.5 }}>
                  <div><span style={{ color: '#8a93a5' }}>Date of birth: </span><span style={{ color: 'var(--text,#e6e9ef)', fontWeight: 600 }}>{sel.ocr_fields.date_of_birth || '—'}</span></div>
                  <div><span style={{ color: '#8a93a5' }}>Family ID: </span><span style={{ color: 'var(--text,#e6e9ef)', fontWeight: 600 }}>{sel.ocr_fields.family_code || '—'}</span></div>
                  <div><span style={{ color: '#8a93a5' }}>Mother (and her father): </span><span style={{ color: 'var(--text,#e6e9ef)', fontWeight: 600 }}>{[sel.ocr_fields.mother_name, sel.ocr_fields.mother_father_name].filter(Boolean).join(' — ') || '—'}</span></div>
                </div>
              </div>
            )}

            {/* documents */}
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 16 }}>
              {(sel.documents || []).map((d: any) => <DocImage key={d.id} rid={sel.registration_id} doc={d} onDecide={decideDoc} />)}
            </div>

            {/* AI signals */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2,1fr)', gap: 8, marginBottom: 16 }}>
              {[
                ['Face match', sel.face_verdict || '—'],
                ['Name match', sel.name_match === true ? '✓ yes' : sel.name_match === false ? '✗ no' : 'n/a (different script?)'],
                ['Document expired', sel.doc_expired === true ? '⚠ yes' : sel.doc_expired === false ? 'no' : 'unknown'],
                ['ID number', sel.id_number || '—'],
                ['Duplicate phone', (sel.network?.dup_phone || 0)],
                ['Duplicate email', (sel.network?.dup_email || 0)],
                ['ID reused', (sel.network?.id_number_reused || 0)],
                ['Family-code links', (sel.network?.family_code_matches || []).length],
              ].map(([k, v]: any, i: number) => (
                <div key={i} style={{ background: 'var(--bg,#1b2129)', border: '1px solid var(--border,#3a4250)', borderRadius: 8, padding: '8px 10px' }}>
                  <div style={{ fontSize: 10.5, color: '#8a93a5' }}>{k}</div>
                  <div style={{ fontSize: 13, color: 'var(--text,#e6e9ef)', fontWeight: 600 }}>{String(v)}</div>
                </div>
              ))}
            </div>

            {/* OCR fields */}
            {sel.ocr_fields && Object.keys(sel.ocr_fields).filter(k => !k.startsWith('_') && sel.ocr_fields[k]).length > 0 && (
              <div style={{ marginBottom: 16 }}>
                <div style={{ fontSize: 12, color: '#8a93a5', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '.5px' }}>Read from the document</div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2,1fr)', gap: 6 }}>
                  {Object.entries(sel.ocr_fields).filter(([k, v]: any) => !k.startsWith('_') && v).map(([k, v]: any) => (
                    <div key={k} style={{ fontSize: 12 }}><span style={{ color: '#8a93a5' }}>{k.replace(/_/g, ' ')}: </span><span style={{ color: 'var(--text,#e6e9ef)' }}>{String(v)}</span></div>
                  ))}
                </div>
              </div>
            )}

            {/* actions */}
            {rejecting && (
              <textarea value={comment} onChange={e => setComment(e.target.value)} placeholder="Reason for rejection (shown to the client)…" rows={2}
                style={{ width: '100%', boxSizing: 'border-box', background: 'var(--bg,#1b2129)', border: '1px solid var(--border,#4f596b)', borderRadius: 8, color: 'var(--text,#e6e9ef)', padding: '9px 12px', fontSize: 13, marginBottom: 10, outline: 'none', fontFamily: 'inherit' }} />
            )}
            <div style={{ display: 'flex', gap: 10 }}>
              <button disabled={busy} onClick={() => decide('approve')} style={{ flex: 1, padding: '11px', borderRadius: 9, border: 'none', background: '#00e5a0', color: '#06251b', fontWeight: 700, fontSize: 13.5, cursor: 'pointer', fontFamily: 'inherit' }}>✓ Approve</button>
              <button disabled={busy} onClick={() => decide('reject')} style={{ flex: 1, padding: '11px', borderRadius: 9, border: '1px solid #ff5d6c', background: rejecting ? '#ff5d6c' : 'transparent', color: rejecting ? '#fff' : '#ff5d6c', fontWeight: 700, fontSize: 13.5, cursor: 'pointer', fontFamily: 'inherit' }}>{rejecting ? 'Confirm reject' : '✗ Reject'}</button>
            </div>
          </>)}
        </div>
      )}
    </div>
  );
}

import React, { useState, useEffect, useCallback } from 'react';
import { apiGet, apiPost } from './api';

// AML / Sanctions compliance review (P0-16). Reads /aml/* (aml_router.py): the onboarding sanctions
// match queue + ad-hoc screening + list stats + threshold tuning. Compliance roles only (backend-gated).
// Uses theme CSS vars (dark source-of-truth) so it remaps correctly in light mode.

type Hit = {
  id: number; subject_type: string; subject_id: number; source: string;
  matched_name: string; entity_type: string; programs: string; score: number;
  status: string; reviewed_by: string | null; reviewed_at: string | null; note: string | null;
  created_at: string; name_screened: string; subj_dob: string | null;
  primary_name: string | null; entity_dob: string | null; nationality: string | null;
};
type Stats = {
  list_entities: Record<string, number>; name_variants: number; lists_updated: string | null;
  screenings_run: number; hits_by_status: Record<string, number>;
  match_threshold: number; block_threshold: number;
};

const C = {
  bg: 'var(--bg-main)', card: 'var(--bg-card)', input: 'var(--bg-input)',
  border: 'var(--border)', text: 'var(--text)', muted: 'var(--text2)',
  brand: 'var(--brand)', green: 'var(--accent)', red: '#ff5c6c', amber: '#ffb020',
};

function scoreColor(s: number) { return s >= 0.95 ? C.red : s >= 0.9 ? C.amber : C.muted; }
function statusColor(s: string) {
  return s === 'confirmed' ? C.red : s === 'cleared' ? C.green : C.amber;
}

const Card: React.FC<{ children: React.ReactNode; style?: React.CSSProperties }> = ({ children, style }) => (
  <div style={{ background: C.card, border: `1px solid ${C.border}`, borderRadius: 12, padding: 16, ...style }}>{children}</div>
);

export default function AMLReview() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [tab, setTab] = useState<'pending' | 'cleared' | 'confirmed' | 'all'>('pending');
  const [hits, setHits] = useState<Hit[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState<number | null>(null);
  const [role, setRole] = useState<string>('');

  // ad-hoc screen
  const [q, setQ] = useState('');
  const [qRes, setQRes] = useState<Hit[] | null>(null);
  const [qLoading, setQLoading] = useState(false);

  useEffect(() => {
    setRole((localStorage.getItem('userRole') || '').toLowerCase());
  }, []);
  const isMgmt = ['super_admin', 'admin', 'director'].includes(role);

  const loadStats = useCallback(() => { apiGet('/aml/stats').then(setStats).catch(e => setErr(String(e.message || e))); }, []);
  const loadHits = useCallback(() => {
    setLoading(true); setErr('');
    apiGet(`/aml/hits?status=${tab}&limit=500`)
      .then(r => setHits(r.hits || []))
      .catch(e => setErr(String(e.message || e)))
      .finally(() => setLoading(false));
  }, [tab]);

  useEffect(() => { loadStats(); }, [loadStats]);
  useEffect(() => { loadHits(); }, [loadHits]);

  const resolve = (h: Hit, action: 'clear' | 'confirm') => {
    const verb = action === 'clear' ? 'CLEAR (false positive / different person)' : 'CONFIRM as a real sanctions match';
    const note = window.prompt(`${verb}\n\n${h.name_screened}  ↔  ${h.matched_name} [${h.source}]\nReason / note (optional):`, '');
    if (note === null) return;   // cancelled
    setBusy(h.id);
    apiPost(`/aml/hits/${h.id}/${action}`, { note })
      .then(() => { loadHits(); loadStats(); })
      .catch(e => setErr(String(e.message || e)))
      .finally(() => setBusy(null));
  };

  const screenNow = () => {
    if (q.trim().length < 3) return;
    setQLoading(true); setQRes(null);
    apiPost('/aml/screen', { name: q.trim() })
      .then(r => setQRes(r.matches || []))
      .catch(e => setErr(String(e.message || e)))
      .finally(() => setQLoading(false));
  };

  const refreshLists = () => {
    setBusy(-1);
    apiPost('/aml/refresh', {}).then(() => setTimeout(loadStats, 12000)).catch(e => setErr(String(e.message || e))).finally(() => setTimeout(() => setBusy(null), 12000));
  };

  const pending = stats?.hits_by_status?.pending || 0;

  return (
    <div style={{ padding: 20, color: C.text, maxWidth: 1280, margin: '0 auto' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 4 }}>
        <span style={{ fontSize: 22 }}>⚖️</span>
        <h2 style={{ margin: 0, fontSize: 20 }}>AML / Sanctions Screening</h2>
        {pending > 0 && <span style={{ background: C.amber, color: '#1a1300', fontWeight: 700, fontSize: 12, padding: '2px 9px', borderRadius: 20 }}>{pending} to review</span>}
        <div style={{ flex: 1 }} />
        {isMgmt && <button onClick={refreshLists} disabled={busy === -1} style={btn(C.border)}>{busy === -1 ? 'Refreshing…' : '↻ Refresh lists'}</button>}
      </div>
      <div style={{ color: C.muted, fontSize: 12, marginBottom: 16 }}>
        New registrations are screened against OFAC + UN sanctions lists before a real account is provisioned. A block-level match holds onboarding here for your review.
      </div>

      {err && <div style={{ background: 'rgba(255,92,108,0.12)', border: `1px solid ${C.red}`, color: C.red, padding: '8px 12px', borderRadius: 8, marginBottom: 12, fontSize: 13 }}>{err}</div>}

      {/* KPI tiles */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: 12, marginBottom: 16 }}>
        {kpi('OFAC entities', stats?.list_entities?.ofac)}
        {kpi('UN entities', stats?.list_entities?.un)}
        {kpi('Name variants', stats?.name_variants)}
        {kpi('Screenings run', stats?.screenings_run)}
        {kpi('Pending review', pending, pending > 0 ? C.amber : undefined)}
        {kpi('Lists updated', stats?.lists_updated ? stats.lists_updated.slice(0, 10) : '—')}
      </div>

      {/* Ad-hoc screen */}
      <Card style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>Screen a name</div>
        <div style={{ display: 'flex', gap: 8 }}>
          <input value={q} onChange={e => setQ(e.target.value)} onKeyDown={e => e.key === 'Enter' && screenNow()}
            placeholder="e.g. full name to check against the lists"
            style={{ flex: 1, background: C.input, border: `1px solid ${C.border}`, color: C.text, borderRadius: 8, padding: '9px 12px', fontSize: 13 }} />
          <button onClick={screenNow} disabled={qLoading || q.trim().length < 3} style={btn(C.brand, true)}>{qLoading ? 'Screening…' : 'Screen'}</button>
        </div>
        {qRes !== null && (
          <div style={{ marginTop: 10, fontSize: 13 }}>
            {qRes.length === 0
              ? <span style={{ color: C.green }}>✓ No sanctions match.</span>
              : <>
                <span style={{ color: C.amber }}>{qRes.length} potential match{qRes.length > 1 ? 'es' : ''}:</span>
                <div style={{ marginTop: 6, display: 'flex', flexDirection: 'column', gap: 4 }}>
                  {qRes.slice(0, 8).map((m, i) => (
                    <div key={i} style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
                      <b style={{ color: scoreColor(m.score) }}>{(m.score * 100).toFixed(0)}%</b>
                      <span>{m.primary_name || m.matched_name}</span>
                      <span style={pill}>{m.source?.toUpperCase()}</span>
                      <span style={pill}>{m.entity_type}</span>
                      {m.entity_dob && <span style={{ color: C.muted }}>DOB {m.entity_dob}</span>}
                      {m.nationality && <span style={{ color: C.muted }}>· {m.nationality}</span>}
                      {m.programs && <span style={{ color: C.muted }}>· {m.programs}</span>}
                    </div>
                  ))}
                </div>
              </>}
          </div>
        )}
      </Card>

      {/* Review queue */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 10 }}>
        {(['pending', 'cleared', 'confirmed', 'all'] as const).map(t => (
          <button key={t} onClick={() => setTab(t)} style={{
            ...btn(tab === t ? C.brand : C.border, tab === t),
            textTransform: 'capitalize',
          }}>{t}{t === 'pending' && pending ? ` (${pending})` : ''}</button>
        ))}
        <div style={{ flex: 1 }} />
        <button onClick={loadHits} style={btn(C.border)}>↻</button>
      </div>

      <Card style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
            <thead>
              <tr style={{ color: C.muted, textAlign: 'left', borderBottom: `1px solid ${C.border}` }}>
                {['Registrant', 'Matched sanctioned entity', 'List', 'Score', 'Status', 'Actions'].map(h => (
                  <th key={h} style={{ padding: '10px 12px', fontWeight: 600, whiteSpace: 'nowrap' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading && <tr><td colSpan={6} style={{ padding: 24, color: C.muted, textAlign: 'center' }}>Loading…</td></tr>}
              {!loading && hits.length === 0 && <tr><td colSpan={6} style={{ padding: 24, color: C.muted, textAlign: 'center' }}>No {tab === 'all' ? '' : tab} hits.</td></tr>}
              {!loading && hits.map(h => (
                <tr key={h.id} style={{ borderBottom: `1px solid ${C.border}` }}>
                  <td style={td}>
                    <div style={{ fontWeight: 600 }}>{h.name_screened || '—'}</div>
                    <div style={{ color: C.muted, fontSize: 11 }}>
                      reg #{h.subject_id}{h.subj_dob ? ` · DOB ${h.subj_dob}` : ''} · {String(h.created_at).slice(0, 10)}
                    </div>
                  </td>
                  <td style={td}>
                    <div>{h.primary_name || h.matched_name}</div>
                    <div style={{ color: C.muted, fontSize: 11 }}>
                      {h.entity_type}{h.entity_dob ? ` · DOB ${h.entity_dob}` : ''}{h.nationality ? ` · ${h.nationality}` : ''}{h.programs ? ` · ${h.programs}` : ''}
                    </div>
                  </td>
                  <td style={td}><span style={pill}>{h.source?.toUpperCase()}</span></td>
                  <td style={{ ...td, fontWeight: 700, color: scoreColor(h.score) }}>{(h.score * 100).toFixed(0)}%</td>
                  <td style={td}>
                    <span style={{ color: statusColor(h.status), fontWeight: 600, textTransform: 'capitalize' }}>{h.status}</span>
                    {h.reviewed_by && <div style={{ color: C.muted, fontSize: 11 }}>{h.reviewed_by}{h.note ? ` · ${h.note}` : ''}</div>}
                  </td>
                  <td style={td}>
                    {h.status === 'pending' ? (
                      <div style={{ display: 'flex', gap: 6 }}>
                        <button disabled={busy === h.id} onClick={() => resolve(h, 'clear')} style={btn(C.green)}>Clear</button>
                        <button disabled={busy === h.id} onClick={() => resolve(h, 'confirm')} style={btn(C.red)}>Confirm</button>
                      </div>
                    ) : <span style={{ color: C.muted }}>—</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {stats && (
        <div style={{ color: C.muted, fontSize: 11.5, marginTop: 12 }}>
          Queue threshold {(stats.match_threshold * 100).toFixed(0)}% · block-onboarding threshold {(stats.block_threshold * 100).toFixed(0)}%
          {isMgmt && ' (tune via /aml/settings)'}. Name screening over-refers by design — DOB & nationality help confirm whether it is the same person.
        </div>
      )}
    </div>
  );

  function kpi(label: string, val: any, color?: string) {
    return (
      <Card style={{ padding: 12 }}>
        <div style={{ color: C.muted, fontSize: 11, marginBottom: 4 }}>{label}</div>
        <div style={{ fontSize: 20, fontWeight: 700, color: color || C.text }}>
          {val === undefined || val === null ? '—' : typeof val === 'number' ? val.toLocaleString() : val}
        </div>
      </Card>
    );
  }
}

const td: React.CSSProperties = { padding: '10px 12px', verticalAlign: 'top' };
const pill: React.CSSProperties = { background: 'var(--bg-input)', border: '1px solid var(--border)', borderRadius: 6, padding: '1px 7px', fontSize: 11 };
function btn(color: string, filled = false): React.CSSProperties {
  return {
    background: filled ? color : 'transparent', color: filled ? '#0b0e14' : color,
    border: `1px solid ${color}`, borderRadius: 8, padding: '7px 12px', fontSize: 12.5,
    fontWeight: 600, cursor: 'pointer', whiteSpace: 'nowrap',
  };
}

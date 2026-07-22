/**
 * CallQA.tsx — Call QA command center (backend call_qa_engine.py).
 *
 * Design language: dark-first "mission control" — stat tiles up top, an inbox-style
 * grid list (priority rail, mini score rings, unread accents), and a premium report
 * drawer: animated score gauge, glass sections, a 3-step coaching timeline and a
 * chat-styled transcript. Everything sits on the shared CRM theme variables
 * (--bg-main/--bg-card/--text/--border) so it renders correctly in BOTH themes.
 * Functionality preserved: filters, sorting, RBAC scope + OwnDataToggle,
 * read/understood workflow, per-customer call history with old transcripts.
 */
import React, { useEffect, useMemo, useState } from 'react';
import { apiGet, apiPost } from './api';
import OwnDataToggle from './OwnDataToggle';

type Coaching = { opening?: string; middle?: string; closing?: string } | null;
type Report = {
  id: number; recording_id: number; call_time: string;
  agent_ext: string; agent_name: string; customer_number: string;
  direction: string; duration: number;
  client_login: number | null; client_name: string | null;
  contact_type: string | null;
  summary: string; analysis?: string | null; outcome: string;
  score: number | null; priority: string;
  strengths: string[]; weaknesses: string[]; recommendation: string; flags: string[];
  coaching?: Coaching;
  read_at?: string | null; read_by?: string | null;
  prev_calls?: number;
  transcript_text?: string;
  history?: HistItem[];
};
type HistItem = {
  id: number; call_time: string; agent_name: string; direction: string;
  duration: number; score: number | null; priority: string; outcome: string; summary: string;
};

/* ---------------------------------------------------------------- theme */

const PAGE = 'var(--bg-main,#20252f)';
const CARD = 'var(--bg-card,#2c333e)';
const HEAD = 'var(--bg-input,#373f4d)';
const BORD = 'var(--border,#4f596b)';
const TXT  = 'var(--text,#e6e9ef)';
const TXT2 = 'var(--text2,#8a93a3)';

const PRIO: Record<string, { label: string; c: string; glass: string; line: string }> = {
  critical: { label: 'Critical', c: '#f87171', glass: 'rgba(248,113,113,.14)', line: '#ef4444' },
  urgent:   { label: 'Urgent',   c: '#fbbf24', glass: 'rgba(251,191,36,.14)',  line: '#f59e0b' },
  medium:   { label: 'Medium',   c: '#38bdf8', glass: 'rgba(56,189,248,.14)',  line: '#0ea5e9' },
  normal:   { label: 'Normal',   c: '#34d399', glass: 'rgba(52,211,153,.14)',  line: '#10b981' },
};
const CTYPE: Record<string, { label: string; c: string; glass: string }> = {
  client: { label: 'Client', c: '#60a5fa', glass: 'rgba(96,165,250,.15)' },
  ib:     { label: 'IB',     c: '#facc15', glass: 'rgba(250,204,21,.15)' },
  lead:   { label: 'Lead',   c: '#c084fc', glass: 'rgba(192,132,252,.15)' },
  unknown:{ label: '—',      c: '#94a3b8', glass: 'rgba(148,163,184,.12)' },
};
const OUTCOME: Record<string, string> = {
  interested: 'Interested', follow_up: 'Follow up', not_interested: 'Not interested',
  callback: 'Callback', complaint: 'Complaint', no_conversation: 'No answer', other: 'Other',
};
const PRIO_RANK: Record<string, number> = { critical: 0, urgent: 1, medium: 2, normal: 3 };
const PHASES: Array<{ key: 'opening' | 'middle' | 'closing'; en: string; icon: string }> = [
  { key: 'opening', en: 'Opening', icon: '👋' },
  { key: 'middle',  en: 'Middle',  icon: '💬' },
  { key: 'closing', en: 'Closing', icon: '🤝' },
];

function fmtDur(s: number) { return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`; }
function fmtTime(t: string) {
  const d = new Date(t);
  return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short' }) + ' ' +
         d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
}
function scoreColor(v: number | null) {
  if (v == null) return '#64748b';
  if (v >= 7.5) return '#34d399';
  if (v >= 5) return '#fbbf24';
  return '#f87171';
}

/* -------------------------------------------------------- score gauge */

function Ring({ v, size = 40, stroke = 3.5, font = 13 }:
  { v: number | null; size?: number; stroke?: number; font?: number }) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const pct = v == null ? 0 : Math.max(0.02, Math.min(1, v / 10));
  const col = scoreColor(v);
  return (
    <div style={{ position: 'relative', width: size, height: size, flex: 'none' }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)', display: 'block' }}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(148,163,184,.18)" strokeWidth={stroke} />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={col} strokeWidth={stroke}
          strokeDasharray={`${c * pct} ${c}`} strokeLinecap="round"
          style={{ transition: 'stroke-dasharray .6s ease' }} />
      </svg>
      <span style={{
        position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontWeight: 800, fontSize: font, color: col,
      }}>{v ?? '–'}</span>
    </div>
  );
}

/* ------------------------------------------------------------ chips */

const chip = (c: string, glass: string, fs = 10.5): React.CSSProperties => ({
  color: c, background: glass, border: `1px solid ${c}33`,
  padding: '2px 9px', borderRadius: 999, fontWeight: 700, fontSize: fs,
  whiteSpace: 'nowrap', display: 'inline-block',
});
const clip: React.CSSProperties = { overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' };
const rtl: React.CSSProperties = { direction: 'rtl', textAlign: 'right' };
const inputStyle: React.CSSProperties = {
  padding: '8px 12px', borderRadius: 10, border: `1px solid ${BORD}`,
  fontSize: 12.5, background: HEAD, color: TXT, outline: 'none',
};
const section = (accent?: string): React.CSSProperties => ({
  background: CARD, border: `1px solid ${accent ? accent + '44' : BORD}`,
  borderRadius: 14, padding: '13px 15px', marginBottom: 10,
});

/* the inbox grid — one template shared by header + rows so columns always align
   and always fill 100% (only Customer + Summary flex) */
const GRID = '22px 86px 148px minmax(120px,1fr) 60px 74px 44px 44px minmax(210px,2.1fr) 92px';

type SortKey = 'time' | 'agent' | 'score' | 'priority' | 'type';

export default function CallQA() {
  const today = new Date().toISOString().slice(0, 10);
  const monthStart = today.slice(0, 8) + '01';
  const [reports, setReports] = useState<Report[]>([]);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [unreadTotal, setUnreadTotal] = useState(0);
  const [agents, setAgents] = useState<any[]>([]);
  const [agent, setAgent] = useState('');
  const [priority, setPriority] = useState('');
  const [onlyUnread, setOnlyUnread] = useState(false);
  const [dateFrom, setDateFrom] = useState(monthStart);
  const [dateTo, setDateTo] = useState(today);
  const [search, setSearch] = useState('');        // debounced value sent to the API
  const [searchRaw, setSearchRaw] = useState('');   // what the user is typing
  // #283: Call QA defaults to the TEAM view for everyone. A team leader reviews their team's
  // calls — defaulting to "my own data" showed only the leader's OWN extension (usually zero
  // calls) and the page opened as "Nothing here yet". The My-team toggle still narrows on demand.
  const [own, setOwn] = useState(false);
  const [sortKey, setSortKey] = useState<SortKey>('priority');
  const [sortDir, setSortDir] = useState<1 | -1>(1);
  const [sel, setSel] = useState<Report | null>(null);
  const [histSel, setHistSel] = useState<Report | null>(null);
  const [showTranscript, setShowTranscript] = useState(false);
  const [loading, setLoading] = useState(false);
  const [marking, setMarking] = useState(false);

  const load = () => {
    setLoading(true);
    const q = new URLSearchParams({ agent, priority, date_from: dateFrom, date_to: dateTo, search, limit: '400' });
    if (own) q.set('own', '1');
    apiGet('/call-qa/reports?' + q.toString())
      .then(r => { setReports(r.reports || []); setCounts(r.counts || {}); setUnreadTotal(r.unread || 0); })
      .finally(() => setLoading(false));
  };
  useEffect(load, [agent, priority, dateFrom, dateTo, search, own]);
  useEffect(() => {                                 // debounce: deep search hits clients+leads
    const t = setTimeout(() => setSearch(searchRaw.trim()), 400);
    return () => clearTimeout(t);
  }, [searchRaw]);
  useEffect(() => { apiGet('/call-qa/agents' + (own ? '?own=1' : '')).then(a => setAgents(Array.isArray(a) ? a : [])); }, [own]);

  const total = useMemo(() => Object.values(counts).reduce((a, b) => a + b, 0), [counts]);
  const avgScore = useMemo(() => {
    const s = reports.filter(r => r.score != null);
    return s.length ? Math.round(s.reduce((a, r) => a + (r.score as number), 0) / s.length * 10) / 10 : null;
  }, [reports]);

  const sorted = useMemo(() => {
    let arr = [...reports];
    if (onlyUnread) arr = arr.filter(r => !r.read_at);
    arr.sort((a, b) => {
      let v = 0;
      if (sortKey === 'time') v = new Date(a.call_time).getTime() - new Date(b.call_time).getTime();
      else if (sortKey === 'agent') v = (a.agent_name || '').localeCompare(b.agent_name || '');
      else if (sortKey === 'score') v = (a.score ?? -1) - (b.score ?? -1);
      else if (sortKey === 'type') v = (a.contact_type || 'zz').localeCompare(b.contact_type || 'zz');
      else v = (PRIO_RANK[a.priority] ?? 9) - (PRIO_RANK[b.priority] ?? 9)
            || new Date(b.call_time).getTime() - new Date(a.call_time).getTime();
      return v * sortDir;
    });
    return arr;
  }, [reports, sortKey, sortDir, onlyUnread]);

  const clickSort = (k: SortKey) => {
    if (sortKey === k) setSortDir(d => (d === 1 ? -1 : 1));
    else { setSortKey(k); setSortDir(k === 'time' ? -1 : 1); }
  };
  const arrow = (k: SortKey) => sortKey === k ? (sortDir === 1 ? ' ▲' : ' ▼') : '';

  const openReport = (r: Report) => {
    setSel(r); setHistSel(null); setShowTranscript(false);
    apiGet(`/call-qa/reports/${r.id}`).then(full => setSel(s => (s && s.id === r.id ? { ...s, ...full } : s)));
  };
  const openHistory = (h: HistItem) => {
    setHistSel({ ...(h as any), strengths: [], weaknesses: [], flags: [] });
    apiGet(`/call-qa/reports/${h.id}`).then(full => setHistSel(full));
  };
  const markRead = () => {
    if (!sel || sel.read_at) return;
    setMarking(true);
    apiPost(`/call-qa/reports/${sel.id}/read`, {}).then(res => {
      setSel(s => (s ? { ...s, read_at: res.read_at, read_by: res.read_by } : s));
      setReports(rs => rs.map(r => (r.id === sel.id ? { ...r, read_at: res.read_at, read_by: res.read_by } : r)));
      setUnreadTotal(n => Math.max(0, n - 1));
    }).finally(() => setMarking(false));
  };

  const active = histSel || sel;
  const ap = active ? (PRIO[active.priority] || PRIO.normal) : PRIO.normal;

  /* transcript → chat-style lines */
  const transcriptLines = useMemo(() => {
    const t = active?.transcript_text || '';
    return t.split('\n').map(l => {
      const m = l.match(/^\[(\d+)s\]\s*(.*)$/);
      return m ? { t: +m[1], text: m[2] } : { t: null as number | null, text: l };
    }).filter(l => l.text.trim());
  }, [active?.transcript_text]);

  /* stat tiles: [icon, label, value, accent, onClick, active?] */
  const tiles: Array<{ icon: string; label: string; value: React.ReactNode; c: string; on?: () => void; on_?: boolean }> = [
    { icon: '🎧', label: 'Calls scored', value: total, c: '#818cf8' },
    { icon: '⭐', label: 'Avg score', value: avgScore ?? '–', c: scoreColor(avgScore) },
    { icon: '🚨', label: 'Critical', value: counts.critical || 0, c: PRIO.critical.c, on: () => setPriority(priority === 'critical' ? '' : 'critical'), on_: priority === 'critical' },
    { icon: '⚡', label: 'Urgent', value: counts.urgent || 0, c: PRIO.urgent.c, on: () => setPriority(priority === 'urgent' ? '' : 'urgent'), on_: priority === 'urgent' },
    { icon: '📬', label: 'Unread', value: unreadTotal, c: '#60a5fa', on: () => setOnlyUnread(v => !v), on_: onlyUnread },
  ];

  return (
    <div style={{ padding: '14px 18px', height: '100%', display: 'flex', flexDirection: 'column', minHeight: 0, background: PAGE, color: TXT }}>
      <style>{`
        @keyframes qaSlide { from { transform: translateX(48px); opacity: 0 } to { transform: none; opacity: 1 } }
        @keyframes qaFade  { from { opacity: 0 } to { opacity: 1 } }
        .qa-row:hover { background: ${HEAD} !important; }
        .qa-tile:hover { transform: translateY(-2px); }
        .qa-hist:hover { border-color: #60a5fa88 !important; }
      `}</style>

      {/* ── hero: title + stat tiles ─────────────────────────────────── */}
      <div style={{ display: 'flex', alignItems: 'stretch', gap: 10, marginBottom: 12, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, paddingRight: 10 }}>
          <div style={{
            width: 46, height: 46, borderRadius: 14, display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 22, background: 'linear-gradient(135deg,#4f46e5,#7c3aed)', boxShadow: '0 4px 14px rgba(99,102,241,.35)',
          }}>🎧</div>
          <div>
            <div style={{ fontSize: 19, fontWeight: 800, letterSpacing: .2 }}>Call QA</div>
            <div style={{ color: TXT2, fontSize: 11.5 }}>AI coaching card for every sales call</div>
          </div>
        </div>
        <div style={{ flex: 1 }} />
        {tiles.map(tl => (
          <div key={tl.label} className="qa-tile" onClick={tl.on}
            style={{
              minWidth: 108, padding: '9px 14px', borderRadius: 14, background: CARD,
              border: tl.on_ ? `1.5px solid ${tl.c}` : `1px solid ${BORD}`,
              cursor: tl.on ? 'pointer' : 'default', transition: 'transform .12s, border-color .12s',
              position: 'relative', overflow: 'hidden',
            }}>
            <div style={{ position: 'absolute', inset: 0, background: `linear-gradient(135deg, ${tl.c}22, transparent 55%)` }} />
            <div style={{ position: 'relative' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: TXT2, fontSize: 10.5, fontWeight: 700, textTransform: 'uppercase', letterSpacing: .5 }}>
                <span style={{ fontSize: 12 }}>{tl.icon}</span>{tl.label}
              </div>
              <div style={{ fontSize: 22, fontWeight: 850, color: tl.c, lineHeight: 1.25 }}>{tl.value}</div>
            </div>
          </div>
        ))}
      </div>

      {/* ── filter bar ───────────────────────────────────────────────── */}
      <div style={{
        display: 'flex', gap: 8, marginBottom: 10, flexWrap: 'wrap', alignItems: 'center',
        background: CARD, border: `1px solid ${BORD}`, borderRadius: 14, padding: '9px 12px',
      }}>
        <select value={agent} onChange={e => setAgent(e.target.value)} style={inputStyle}>
          <option value="">All agents</option>
          {agents.map(a => (
            <option key={a.agent_ext} value={a.agent_ext}>
              {a.agent_name} · {a.calls} calls · avg {a.avg_score ?? '-'}
            </option>
          ))}
        </select>
        <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} style={inputStyle} />
        <span style={{ color: TXT2 }}>→</span>
        <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} style={inputStyle} />
        <input placeholder="🔍  Name, email, phone, account #, summary…" value={searchRaw} onChange={e => setSearchRaw(e.target.value)}
          style={{ ...inputStyle, flex: 1, minWidth: 200 }} />
        {(['medium', 'normal'] as const).map(p => (
          <button key={p} onClick={() => setPriority(priority === p ? '' : p)}
            style={{ ...chip(PRIO[p].c, priority === p ? PRIO[p].glass : 'transparent', 11), border: `1px solid ${priority === p ? PRIO[p].c : BORD}`, cursor: 'pointer', padding: '5px 12px' }}>
            {PRIO[p].label} {counts[p] || 0}
          </button>
        ))}
        <OwnDataToggle own={own} setOwn={setOwn} section="calls" />
        {loading && <span style={{ color: TXT2, fontSize: 12 }}>⟳ loading…</span>}
      </div>

      {/* ── inbox list ───────────────────────────────────────────────── */}
      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', overflowX: 'hidden', background: CARD, border: `1px solid ${BORD}`, borderRadius: 14 }}>
        {/* header */}
        <div style={{
          display: 'grid', gridTemplateColumns: GRID, gap: 8, alignItems: 'center',
          padding: '9px 12px 8px', position: 'sticky', top: 0, zIndex: 2, background: HEAD,
          borderBottom: `1px solid ${BORD}`, fontSize: 10, fontWeight: 800, color: TXT2,
          textTransform: 'uppercase', letterSpacing: .7,
        }}>
          <span />
          <span style={{ cursor: 'pointer' }} onClick={() => clickSort('time')}>Date{arrow('time')}</span>
          <span style={{ cursor: 'pointer' }} onClick={() => clickSort('agent')}>Agent{arrow('agent')}</span>
          <span>Customer</span>
          <span style={{ textAlign: 'center', cursor: 'pointer' }} onClick={() => clickSort('type')}>Type{arrow('type')}</span>
          <span style={{ textAlign: 'center', cursor: 'pointer' }} onClick={() => clickSort('priority')}>Priority{arrow('priority')}</span>
          <span style={{ textAlign: 'center', cursor: 'pointer' }} onClick={() => clickSort('score')}>Score{arrow('score')}</span>
          <span style={{ textAlign: 'center' }}>Dur</span>
          <span style={{ textAlign: 'right' }}>Summary</span>
          <span>Outcome</span>
        </div>
        {/* rows */}
        {sorted.map(r => {
          const p = PRIO[r.priority] || PRIO.normal;
          const ct = CTYPE[r.contact_type || 'unknown'] || CTYPE.unknown;
          const unread = !r.read_at;
          return (
            <div key={r.id} className="qa-row" onClick={() => openReport(r)}
              style={{
                display: 'grid', gridTemplateColumns: GRID, gap: 8, alignItems: 'center',
                padding: '7px 12px', cursor: 'pointer', borderBottom: `1px solid ${BORD}22`,
                boxShadow: `inset 3px 0 0 ${p.line}`,
                opacity: unread ? 1 : 0.55, transition: 'background .1s',
              }}>
              <span style={{ textAlign: 'center' }}>
                {unread
                  ? <span title="Unread" style={{ display: 'inline-block', width: 8, height: 8, borderRadius: 4, background: '#60a5fa', boxShadow: '0 0 6px #60a5fa' }} />
                  : <span title={`Read by ${r.read_by || ''}`} style={{ color: TXT2, fontSize: 10 }}>✓</span>}
              </span>
              <span style={{ ...clip, color: TXT2, fontSize: 11 }}>{fmtTime(r.call_time)}</span>
              <span style={{ ...clip, fontSize: 12.5, fontWeight: unread ? 700 : 500 }} title={r.agent_name}>{r.agent_name || r.agent_ext}</span>
              <span style={{ ...clip, fontSize: 12.5 }} title={`${r.client_name || ''} ${r.customer_number}${(r.prev_calls || 0) > 0 ? ` · ${(r.prev_calls || 0) + 1} calls total` : ''}`}>
                {(r.prev_calls || 0) > 0 && (
                  <span style={{ ...chip('#818cf8', 'rgba(129,140,248,.15)', 9.5), padding: '0 5px', marginRight: 5 }}>×{(r.prev_calls || 0) + 1}</span>
                )}
                {r.client_name || <span style={{ color: TXT2 }}>{r.customer_number}</span>}
              </span>
              <span style={{ textAlign: 'center' }}><span style={chip(ct.c, ct.glass)}>{ct.label}</span></span>
              <span style={{ textAlign: 'center' }}><span style={chip(p.c, p.glass)}>{p.label}</span></span>
              <span style={{ display: 'flex', justifyContent: 'center' }}><Ring v={r.score} size={30} stroke={3} font={10.5} /></span>
              <span style={{ textAlign: 'center', color: TXT2, fontSize: 11 }}>{fmtDur(r.duration)}</span>
              <span style={{ ...clip, ...rtl, fontSize: 12, color: TXT }} title={r.summary}>{r.summary}</span>
              <span style={{ ...clip, color: TXT2, fontSize: 11 }}>{OUTCOME[r.outcome] || r.outcome}</span>
            </div>
          );
        })}
        {!sorted.length && !loading && (
          <div style={{ padding: 60, textAlign: 'center', color: TXT2 }}>
            <div style={{ fontSize: 40, marginBottom: 10 }}>🎧</div>
            <div style={{ fontWeight: 700, marginBottom: 4, color: TXT }}>Nothing here yet</div>
            No scored calls for this filter — the July archive is filling up progressively.
          </div>
        )}
      </div>

      {/* ── report drawer ────────────────────────────────────────────── */}
      {sel && (
        <div onClick={() => { setSel(null); setHistSel(null); }}
          style={{ position: 'fixed', inset: 0, background: 'rgba(2,6,23,.6)', zIndex: 100, display: 'flex', justifyContent: 'flex-end', animation: 'qaFade .15s ease' }}>
          <div onClick={e => e.stopPropagation()}
            style={{
              width: 620, maxWidth: '96vw', background: PAGE, color: TXT, height: '100%',
              display: 'flex', flexDirection: 'column', boxShadow: '-12px 0 40px rgba(0,0,0,.55)',
              animation: 'qaSlide .22s cubic-bezier(.2,.8,.25,1)',
            }}>
            {active && <>
              {/* hero */}
              <div style={{
                padding: '18px 22px 16px', borderBottom: `1px solid ${BORD}`,
                background: `linear-gradient(150deg, ${ap.glass}, transparent 60%), ${CARD}`,
              }}>
                {histSel && (
                  <button onClick={() => { setHistSel(null); setShowTranscript(false); }}
                    style={{ border: `1px solid ${BORD}`, background: HEAD, color: TXT, borderRadius: 8, padding: '4px 12px', cursor: 'pointer', fontSize: 12, marginBottom: 12, fontWeight: 600 }}>
                    ← Back to current call
                  </button>
                )}
                <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                  <Ring v={active.score} size={64} stroke={5.5} font={20} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                      <span style={chip(ap.c, ap.glass, 12)}>{ap.label}</span>
                      {(() => { const ct = CTYPE[(active as any).contact_type || 'unknown'] || CTYPE.unknown; return <span style={chip(ct.c, ct.glass, 12)}>{ct.label}</span>; })()}
                      {histSel && <span style={chip('#94a3b8', 'rgba(148,163,184,.15)', 12)}>Previous call</span>}
                      {!histSel && sel.read_at && <span style={chip('#34d399', 'rgba(52,211,153,.15)', 12)}>✓ Read</span>}
                    </div>
                    <div style={{ fontSize: 16, fontWeight: 800, marginTop: 7, ...clip }}>
                      {active.agent_name} <span style={{ color: TXT2, fontWeight: 500 }}>→</span> {(active as any).client_name || (active as any).customer_number}
                    </div>
                    <div style={{ color: TXT2, fontSize: 12, marginTop: 3 }}>
                      📅 {fmtTime(active.call_time)} &nbsp;·&nbsp; ⏱ {fmtDur(active.duration)} &nbsp;·&nbsp; {OUTCOME[active.outcome] || active.outcome}
                    </div>
                  </div>
                  <button onClick={() => { setSel(null); setHistSel(null); }}
                    style={{ border: 'none', background: HEAD, color: TXT2, fontSize: 16, cursor: 'pointer', width: 32, height: 32, borderRadius: 16, flex: 'none' }}>✕</button>
                </div>
              </div>

              {/* body */}
              <div style={{ padding: '14px 22px', flex: 1, overflowY: 'auto' }}>
                <div style={{ ...section(), ...rtl, fontSize: 14, fontWeight: 700, lineHeight: 1.7 }}>{active.summary}</div>

                {active.analysis && (
                  <div style={section()}>
                    <div style={{ fontSize: 12, fontWeight: 800, color: '#818cf8', marginBottom: 6 }}>📋 ANALYSIS</div>
                    <div style={{ ...rtl, fontSize: 13, lineHeight: 1.8, color: TXT }}>{active.analysis}</div>
                  </div>
                )}

                {!!(active.flags || []).length && (
                  <div style={section('#f87171')}>
                    <div style={{ fontSize: 12, fontWeight: 800, color: '#f87171', marginBottom: 6 }}>🚩 FLAGS</div>
                    <ul style={{ ...rtl, margin: 0, paddingRight: 18 }}>
                      {(active.flags || []).map((f, i) => <li key={i} style={{ marginBottom: 5, fontSize: 12.5, lineHeight: 1.7 }}>{f}</li>)}
                    </ul>
                  </div>
                )}

                <div style={{ display: 'flex', gap: 10 }}>
                  <div style={{ ...section('#34d399'), flex: 1 }}>
                    <div style={{ fontSize: 12, fontWeight: 800, color: '#34d399', marginBottom: 6 }}>✅ STRENGTHS</div>
                    <ul style={{ ...rtl, margin: 0, paddingRight: 16 }}>
                      {(active.strengths || []).map((s, i) => <li key={i} style={{ marginBottom: 5, fontSize: 12, lineHeight: 1.7 }}>{s}</li>)}
                      {!(active.strengths || []).length && <li style={{ color: TXT2, fontSize: 12 }}>—</li>}
                    </ul>
                  </div>
                  <div style={{ ...section('#f87171'), flex: 1 }}>
                    <div style={{ fontSize: 12, fontWeight: 800, color: '#f87171', marginBottom: 6 }}>⚠️ WEAKNESSES</div>
                    <ul style={{ ...rtl, margin: 0, paddingRight: 16 }}>
                      {(active.weaknesses || []).map((s, i) => <li key={i} style={{ marginBottom: 5, fontSize: 12, lineHeight: 1.7 }}>{s}</li>)}
                      {!(active.weaknesses || []).length && <li style={{ color: TXT2, fontSize: 12 }}>—</li>}
                    </ul>
                  </div>
                </div>

                <div style={section('#60a5fa')}>
                  <div style={{ fontSize: 12, fontWeight: 800, color: '#60a5fa', marginBottom: 6 }}>💡 RECOMMENDATION</div>
                  <div style={{ ...rtl, fontSize: 13, lineHeight: 1.8, fontWeight: 600 }}>{active.recommendation}</div>
                </div>

                {/* coaching timeline */}
                {!!(active.coaching && (active.coaching.opening || active.coaching.middle || active.coaching.closing)) && (
                  <div style={section('#fbbf24')}>
                    <div style={{ fontSize: 12, fontWeight: 800, color: '#fbbf24', marginBottom: 10 }}>🎓 COACHING — HOW TO RUN THIS CALL</div>
                    {PHASES.map((ph, idx) => active.coaching?.[ph.key] && (
                      <div key={ph.key} style={{ display: 'flex', gap: 12, position: 'relative', paddingBottom: idx < 2 ? 16 : 0 }}>
                        {/* timeline rail */}
                        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', flex: 'none' }}>
                          <div style={{
                            width: 28, height: 28, borderRadius: 14, background: 'rgba(251,191,36,.16)',
                            border: '1.5px solid #fbbf24', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13,
                          }}>{ph.icon}</div>
                          {idx < 2 && <div style={{ width: 2, flex: 1, background: 'linear-gradient(#fbbf2466, #fbbf2411)', marginTop: 2 }} />}
                        </div>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ fontSize: 11, fontWeight: 800, color: '#fbbf24', textTransform: 'uppercase', letterSpacing: .6, marginBottom: 4 }}>
                            {idx + 1} · {ph.en}
                          </div>
                          <div style={{ ...rtl, fontSize: 13, lineHeight: 1.85 }}>{active.coaching[ph.key]}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {/* transcript */}
                <button onClick={() => setShowTranscript(v => !v)}
                  style={{
                    border: `1px solid ${BORD}`, background: HEAD, color: TXT, borderRadius: 10,
                    padding: '8px 16px', cursor: 'pointer', fontSize: 12.5, fontWeight: 700, marginBottom: 10,
                  }}>
                  {showTranscript ? '▲ Hide transcript' : '▼ Full transcript'}
                </button>
                {showTranscript && (
                  <div style={{ ...section(), maxHeight: 380, overflowY: 'auto' }}>
                    {transcriptLines.length ? transcriptLines.map((l, i) => (
                      <div key={i} style={{ display: 'flex', gap: 10, padding: '5px 0', borderBottom: i < transcriptLines.length - 1 ? `1px solid ${BORD}33` : 'none' }}>
                        {l.t != null && (
                          <span style={{ color: TXT2, fontSize: 10, fontWeight: 700, flex: 'none', width: 38, textAlign: 'left', paddingTop: 3 }}>
                            {fmtDur(l.t)}
                          </span>
                        )}
                        <span style={{ ...rtl, flex: 1, fontSize: 12.5, lineHeight: 1.75 }}>{l.text}</span>
                      </div>
                    )) : <div style={{ color: TXT2, fontSize: 12 }}>Loading…</div>}
                  </div>
                )}

                {/* history */}
                {!histSel && !!(sel.history || []).length && (
                  <div style={{ marginTop: 14 }}>
                    <div style={{ fontWeight: 800, fontSize: 12, marginBottom: 8, color: TXT2, textTransform: 'uppercase', letterSpacing: .6 }}>
                      ☎ Previous calls with this number ({(sel.history || []).length})
                    </div>
                    {(sel.history || []).map(h => {
                      const hp = PRIO[h.priority] || PRIO.normal;
                      return (
                        <div key={h.id} className="qa-hist" onClick={() => { openHistory(h); setShowTranscript(false); }}
                          style={{
                            display: 'flex', gap: 12, alignItems: 'center', background: CARD,
                            border: `1px solid ${BORD}`, borderRadius: 12, padding: '9px 12px',
                            marginBottom: 6, cursor: 'pointer', transition: 'border-color .12s',
                            boxShadow: `inset 3px 0 0 ${hp.line}`,
                          }}>
                          <Ring v={h.score} size={34} stroke={3} font={11} />
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 11, color: TXT2, flexWrap: 'wrap' }}>
                              <span style={chip(hp.c, hp.glass, 9.5)}>{hp.label}</span>
                              <b style={{ color: TXT }}>{h.agent_name}</b>
                              <span>{fmtTime(h.call_time)}</span>
                              <span>{fmtDur(h.duration)}</span>
                              <span>{OUTCOME[h.outcome] || h.outcome}</span>
                            </div>
                            <div style={{ ...rtl, ...clip, fontSize: 12, marginTop: 3, color: TXT }}>{h.summary}</div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* sticky footer: read / understood */}
              {!histSel && (
                <div style={{ padding: '13px 22px 16px', borderTop: `1px solid ${BORD}`, background: CARD }}>
                  {sel.read_at ? (
                    <div style={{ textAlign: 'center', color: '#34d399', fontWeight: 700, fontSize: 12.5 }}>
                      ✓ Read & understood {sel.read_by ? `by ${sel.read_by}` : ''} · {fmtTime(sel.read_at)}
                    </div>
                  ) : (
                    <button onClick={markRead} disabled={marking}
                      style={{
                        width: '100%', border: 'none',
                        background: marking ? '#475569' : 'linear-gradient(135deg,#2563eb,#7c3aed)',
                        color: '#fff', borderRadius: 12, padding: '13px 0', cursor: 'pointer',
                        fontSize: 14.5, fontWeight: 800, letterSpacing: .3,
                        boxShadow: '0 4px 18px rgba(79,70,229,.4)',
                      }}>
                      {marking ? 'Saving…' : '✓  Read / Understood'}
                    </button>
                  )}
                </div>
              )}
            </>}
          </div>
        </div>
      )}
    </div>
  );
}

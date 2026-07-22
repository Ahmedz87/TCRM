import React, { useState, useEffect, useCallback } from 'react';
import { apiGet, apiPost, apiDelete } from './api';
import { CT } from './crmTable';
import WhatsAppAI from './WhatsAppAI';
import MarketingPerformance from './MarketingPerformance';
import DripJourneys from './DripJourneys';
import SocialAds from './SocialAds';
import WatiBroadcast from './WatiBroadcast';

// ── Marketing Command Center ────────────────────────────────────────────────
// READ-ONLY / PREVIEW-ONLY: builds smart audiences, drafts copy with AI, and previews
// who would receive what. It SENDS NOTHING and SPENDS NOTHING — every channel shows a
// disabled "send" until it's connected & explicitly enabled.

type View = 'hub' | 'overview' | 'audiences' | 'email' | 'whatsapp' | 'wa_broadcast' | 'whatsapp_ai' | 'performance' | 'journeys' | 'ads' | 'channels' | 'drafts';

const card: React.CSSProperties = { background: 'var(--bg-card,#2c333e)', border: '1px solid var(--border,#4f596b)', borderRadius: 12, padding: 18 };
const cap: React.CSSProperties = { fontSize: 11, color: '#8a93a5', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 12, fontWeight: 700 };
const input: React.CSSProperties = { padding: '9px 11px', background: '#1c2231', border: '1px solid #3a4252', borderRadius: 8, color: '#e6e9ef', fontSize: 13 };
const btn = (bg: string, fg = '#06251b'): React.CSSProperties => ({ padding: '9px 14px', background: bg, border: 'none', borderRadius: 8, color: fg, fontSize: 13, fontWeight: 700, cursor: 'pointer' });
const fmt = (n: number) => (n || 0).toLocaleString('en-GB');

const HUB_CARDS: { key: View; icon: string; title: string; desc: string }[] = [
  { key: 'overview',  icon: '📊', title: 'Overview',        desc: 'Reachability & funnel at a glance' },
  { key: 'performance', icon: '🏆', title: 'Performance (ROI)', desc: 'Which campaigns produce depositors & revenue + Meta CAPI' },
  { key: 'audiences', icon: '🎯', title: 'Audiences',       desc: 'Smart segments — who to target, with live counts' },
  { key: 'journeys',  icon: '🔁', title: 'Drip journeys',   desc: 'Automated email/WhatsApp nurture sequences' },
  { key: 'email',     icon: '✉️', title: 'Email marketing', desc: 'Pick an audience + occasion, AI-draft the email (preview)' },
  { key: 'wa_broadcast', icon: '📣', title: 'WhatsApp broadcast', desc: 'Send an approved Wati template to a segment (test first, then send)' },
  { key: 'whatsapp',  icon: '💬', title: 'WhatsApp (Wati)', desc: 'AI-draft a WhatsApp message + how to leverage Wati' },
  { key: 'whatsapp_ai', icon: '🤖', title: 'WhatsApp AI assistant', desc: 'AI replies, qualifies & sells on inbound WhatsApp — try the simulator' },
  { key: 'ads',       icon: '📣', title: 'Ads & audiences',  desc: 'Connect TikTok · Snap · Meta — build Custom Audiences from segments' },
  { key: 'drafts',    icon: '🗂', title: 'Saved drafts',    desc: 'Campaigns you saved (nothing is sent)' },
  { key: 'channels',  icon: '🔌', title: 'Channels',        desc: 'Connection status of every channel' },
];

export default function Marketing() {
  const [view, setView] = useState<View>('hub');
  const [overview, setOverview] = useState<any>(null);
  const [segments, setSegments] = useState<any[]>([]);
  const [countries, setCountries] = useState<any[]>([]);
  const [channels, setChannels] = useState<any[]>([]);
  const [aiOn, setAiOn] = useState(false);
  const [composer, setComposer] = useState<{ channel: 'email' | 'whatsapp'; segment?: string; occasion?: string } | null>(null);

  const load = useCallback(() => {
    apiGet('/marketing/overview').then(setOverview).catch(() => {});
    apiGet('/marketing/segments').then(r => { setSegments(r.segments || []); setCountries(r.countries || []); }).catch(() => {});
    apiGet('/marketing/channels').then(r => { setChannels(r.channels || []); setAiOn(!!r.ai_drafting); }).catch(() => {});
  }, []);
  useEffect(() => { load(); }, [load]);

  const openComposer = (channel: 'email' | 'whatsapp', segment?: string, occasion?: string) => {
    setComposer({ channel, segment, occasion });
    setView(channel);
  };

  return (
    <div style={{ maxWidth: 1080 }}>
      {/* header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 6 }}>
        {view !== 'hub' && <span onClick={() => setView('hub')} style={{ cursor: 'pointer', color: '#00e5a0', fontSize: 13 }}>‹ Marketing</span>}
        <h2 style={{ color: 'var(--text,#e6e9ef)', margin: 0, fontSize: 22 }}>📣 Marketing{view !== 'hub' ? ` — ${HUB_CARDS.find(c => c.key === view)?.title || ''}` : ''}</h2>
      </div>
      <div style={{ background: '#1c2a22', border: '1px solid #1f5c43', color: '#7fe9c0', borderRadius: 8, padding: '8px 12px', fontSize: 12, marginBottom: 18 }}>
        🔒 Preview mode — this builds audiences and drafts copy. Nothing is sent and no budget is spent until a channel is connected & enabled.
      </div>

      {view === 'hub' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(250px, 1fr))', gap: 14 }}>
          {HUB_CARDS.map(c => (
            <div key={c.key} onClick={() => setView(c.key)} style={{ ...card, cursor: 'pointer', transition: 'border-color .15s, transform .15s' }}
              onMouseEnter={e => { e.currentTarget.style.borderColor = '#00e5a0'; e.currentTarget.style.transform = 'translateY(-2px)'; }}
              onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--border,#4f596b)'; e.currentTarget.style.transform = 'none'; }}>
              <div style={{ fontSize: 26, marginBottom: 10 }}>{c.icon}</div>
              <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text,#e6e9ef)', marginBottom: 4 }}>{c.title}</div>
              <div style={{ fontSize: 12, color: '#8a93a5', lineHeight: 1.4 }}>{c.desc}</div>
            </div>
          ))}
        </div>
      )}

      {view === 'overview' && <Overview overview={overview} />}
      {view === 'audiences' && <Audiences segments={segments} countries={countries} onUse={openComposer} />}
      {view === 'email' && <Composer channel="email" preset={composer} segments={segments} aiOn={aiOn} onSaved={load} />}
      {view === 'whatsapp' && <Composer channel="whatsapp" preset={composer} segments={segments} aiOn={aiOn} onSaved={load} wati />}
      {view === 'wa_broadcast' && <WatiBroadcast />}
      {view === 'whatsapp_ai' && <WhatsAppAI />}
      {view === 'performance' && <MarketingPerformance />}
      {view === 'journeys' && <DripJourneys />}
      {view === 'ads' && <SocialAds />}
      {view === 'channels' && <Channels channels={channels} aiOn={aiOn} />}
      {view === 'drafts' && <Drafts />}
    </div>
  );
}

// ── Overview ──
function Overview({ overview }: { overview: any }) {
  if (!overview) return <div style={{ color: '#888' }}>Loading…</div>;
  const r = overview.reach, f = overview.funnel;
  const Tile = ({ label, value, sub, color = '#00e5a0' }: any) => (
    <div style={{ ...card, minWidth: 150 }}>
      <div style={{ fontSize: 26, fontWeight: 800, color }}>{fmt(value)}</div>
      <div style={{ fontSize: 12, color: '#cfd6e4', marginTop: 2 }}>{label}</div>
      {sub && <div style={{ fontSize: 11, color: '#8a93a5', marginTop: 2 }}>{sub}</div>}
    </div>
  );
  return (
    <div style={{ display: 'grid', gap: 18 }}>
      <div>
        <div style={cap}>Reachable audience</div>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <Tile label="Reachable by email" value={r.total_email} sub={`${fmt(r.leads_email)} leads · ${fmt(r.clients_email)} clients`} />
          <Tile label="Reachable on WhatsApp" value={r.total_whatsapp} sub={`${fmt(r.leads_whatsapp)} leads · ${fmt(r.clients_whatsapp)} clients`} color="#25D366" />
          <Tile label="Total leads" value={r.leads} color="#79b8ff" />
          <Tile label="Total clients" value={r.clients} color="#79b8ff" />
        </div>
      </div>
      <div>
        <div style={cap}>Conversion funnel</div>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <Tile label="Leads" value={f.leads} color="#79b8ff" />
          <Tile label="Clients" value={f.clients} color="#79b8ff" />
          <Tile label="Depositors" value={f.depositors} />
          <Tile label="Never deposited" value={f.never_deposited} color="#ffaa00" sub="biggest conversion pool" />
          <Tile label="Lapsed 90d+" value={f.lapsed_90} color="#ff8866" sub="reactivation target" />
        </div>
      </div>
    </div>
  );
}

// ── Audiences ──
function Audiences({ segments, countries, onUse }: { segments: any[]; countries: any[]; onUse: (ch: 'email' | 'whatsapp', seg: string) => void }) {
  const [sample, setSample] = useState<any>(null);
  const groups: { [k: string]: any[] } = { leads: [], clients: [], ibs: [] };
  segments.forEach(s => (groups[s.audience] || (groups[s.audience] = [])).push(s));
  const titleFor: any = { leads: '🎯 Leads (prospects)', clients: '👥 Clients', ibs: '🤝 Partners' };

  const showSample = (key: string) => apiGet(`/marketing/segments/${key}/sample`).then(setSample).catch(() => {});

  return (
    <div style={{ display: 'grid', gap: 18 }}>
      {Object.keys(groups).filter(g => groups[g].length).map(g => (
        <div key={g}>
          <div style={cap}>{titleFor[g] || g}</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 12 }}>
            {groups[g].map(s => (
              <div key={s.key} style={card}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                  <div style={{ fontSize: 14, fontWeight: 700, color: '#e6e9ef' }}>{s.label}</div>
                  <div style={{ fontSize: 18, fontWeight: 800, color: '#00e5a0' }}>{fmt(s.total)}</div>
                </div>
                <div style={{ fontSize: 12, color: '#8a93a5', margin: '4px 0 10px', lineHeight: 1.4 }}>{s.desc}</div>
                <div style={{ display: 'flex', gap: 14, fontSize: 11, color: '#cfd6e4', marginBottom: 10 }}>
                  <span>✉️ {fmt(s.reach_email)} email</span>
                  <span>💬 {fmt(s.reach_whatsapp)} WhatsApp</span>
                </div>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  <button onClick={() => showSample(s.key)} style={{ ...btn('#3a4252', '#cfd6e4'), padding: '6px 10px', fontSize: 12 }}>Preview</button>
                  <button onClick={() => onUse('email', s.key)} style={{ ...btn('#00e5a022', '#00e5a0'), padding: '6px 10px', fontSize: 12 }}>✉️ Email</button>
                  <button onClick={() => onUse('whatsapp', s.key)} style={{ ...btn('#25D36622', '#25D366'), padding: '6px 10px', fontSize: 12 }}>💬 WhatsApp</button>
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
      {!!countries.length && (
        <div>
          <div style={cap}>🌍 Leads by country</div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {countries.map(c => (
              <span key={c.country} style={{ background: '#1c2231', border: '1px solid #3a4252', borderRadius: 8, padding: '6px 10px', fontSize: 12, color: '#cfd6e4' }}>
                {c.country} <b style={{ color: '#00e5a0' }}>{fmt(c.leads)}</b>
              </span>
            ))}
          </div>
        </div>
      )}
      {sample && (
        <div onClick={() => setSample(null)} style={{ position: 'fixed', inset: 0, background: '#0009', zIndex: 100, display: 'flex', justifyContent: 'center', alignItems: 'flex-start', padding: '60px 16px', overflowY: 'auto' }}>
          <div onClick={e => e.stopPropagation()} style={{ ...card, width: 560, maxWidth: '100%' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
              <div style={{ fontWeight: 700, color: '#e6e9ef' }}>{sample.label} — sample recipients</div>
              <span onClick={() => setSample(null)} style={{ cursor: 'pointer', color: '#8a93a5' }}>✕</span>
            </div>
            <div style={{ fontSize: 11, color: '#8a93a5', marginBottom: 8 }}>Contacts are masked. This is a preview — no message is sent.</div>
            <div style={CT.scroll}>
              <table style={CT.table}>
                <thead><tr style={CT.theadTr}><th style={CT.th()}>Name</th><th style={CT.th()}>Email</th><th style={CT.th()}>Phone</th><th style={CT.th()}>Country</th></tr></thead>
                <tbody>{sample.sample.map((x: any, i: number) => (
                  <tr key={i} style={CT.row()}>
                    <td style={CT.td}>{x.name}</td><td style={CT.td}>{x.email}</td><td style={CT.td}>{x.phone}</td><td style={CT.td}>{x.country}</td>
                  </tr>))}</tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Composer (email + whatsapp share this) ──
function Composer({ channel, preset, segments, aiOn, onSaved, wati }: { channel: 'email' | 'whatsapp'; preset: any; segments: any[]; aiOn: boolean; onSaved: () => void; wati?: boolean }) {
  const [segment, setSegment] = useState(preset?.segment || '');
  const [occasion, setOccasion] = useState(preset?.occasion || '');
  const [offer, setOffer] = useState('');
  const [language, setLanguage] = useState('Arabic');
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [busy, setBusy] = useState(false);
  const [occasions, setOccasions] = useState<any[]>([]);
  const [savedMsg, setSavedMsg] = useState('');
  useEffect(() => { apiGet('/marketing/occasions').then(r => setOccasions(r.occasions || [])).catch(() => {}); }, []);

  const seg = segments.find(s => s.key === segment);
  const recipients = seg ? (channel === 'email' ? seg.reach_email : seg.reach_whatsapp) : 0;

  const generate = async () => {
    if (!segment) { setSavedMsg('Pick an audience first'); return; }
    setBusy(true); setSavedMsg('');
    try {
      const r = await apiPost('/marketing/draft', { segment, channel, occasion, offer, language });
      if (r.ok) { setSubject(r.subject || ''); setBody(r.body || ''); }
      else setSavedMsg(r.message || 'AI draft unavailable');
    } catch { setSavedMsg('Draft failed'); }
    setBusy(false);
  };
  const save = async () => {
    if (!body.trim()) { setSavedMsg('Nothing to save yet'); return; }
    const r = await apiPost('/marketing/campaigns', { name: occasion || seg?.label || 'Campaign', channel, segment_key: segment, occasion, subject, body, language }).catch(() => null);
    setSavedMsg(r?.ok ? '✓ Saved as draft (not sent)' : 'Save failed');
    onSaved();
  };

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, alignItems: 'start' }}>
      {/* left: targeting */}
      <div style={{ display: 'grid', gap: 14 }}>
        {wati && <WatiPanel />}
        <div style={card}>
          <div style={cap}>1 · Who</div>
          <select value={segment} onChange={e => setSegment(e.target.value)} style={{ ...input, width: '100%' }}>
            <option value="">Choose an audience…</option>
            {segments.map(s => <option key={s.key} value={s.key}>{s.label} ({fmt(channel === 'email' ? s.reach_email : s.reach_whatsapp)})</option>)}
          </select>
          {seg && <div style={{ fontSize: 12, color: '#8a93a5', marginTop: 8 }}>{seg.desc} · <b style={{ color: '#00e5a0' }}>{fmt(recipients)}</b> reachable on {channel === 'email' ? 'email' : 'WhatsApp'}.</div>}
        </div>
        <div style={card}>
          <div style={cap}>2 · Occasion / offer</div>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 10 }}>
            {occasions.map(o => (
              <span key={o.id} onClick={() => { setOccasion(o.name); if (!segment) setSegment(o.audience); }}
                title={o.angle} style={{ cursor: 'pointer', fontSize: 11, padding: '4px 9px', borderRadius: 7, background: occasion === o.name ? '#00e5a022' : '#1c2231', color: occasion === o.name ? '#00e5a0' : '#cfd6e4', border: '1px solid #3a4252' }}>
                {o.type === 'holiday' ? '🎉' : o.type === 'offer' ? '🎁' : o.type === 'market' ? '📈' : '•'} {o.name}
              </span>
            ))}
          </div>
          <input value={occasion} onChange={e => setOccasion(e.target.value)} placeholder="Occasion / theme (e.g. Eid offer)" style={{ ...input, width: '100%', boxSizing: 'border-box', marginBottom: 8 }} />
          <input value={offer} onChange={e => setOffer(e.target.value)} placeholder="Offer to feature (e.g. 30% deposit bonus) — optional" style={{ ...input, width: '100%', boxSizing: 'border-box', marginBottom: 8 }} />
          <select value={language} onChange={e => setLanguage(e.target.value)} style={{ ...input, width: '100%' }}>
            {['Arabic', 'English', 'Arabic + English', 'Turkish'].map(l => <option key={l}>{l}</option>)}
          </select>
        </div>
        <button onClick={generate} disabled={busy || !aiOn} title={aiOn ? '' : 'Add backend/ai_key.txt to enable AI drafting'}
          style={{ ...btn(aiOn ? '#9966ff' : '#3a4252', aiOn ? '#fff' : '#8a93a5'), opacity: busy ? 0.6 : 1 }}>
          {busy ? 'Writing…' : `✨ Generate ${channel === 'email' ? 'email' : 'message'} with AI`}
        </button>
        {!aiOn && <div style={{ fontSize: 11, color: '#8a93a5' }}>AI drafting is off (no AI key configured).</div>}
      </div>

      {/* right: draft preview */}
      <div style={{ display: 'grid', gap: 14 }}>
        <div style={card}>
          <div style={cap}>3 · Draft {channel === 'email' ? 'email' : 'WhatsApp message'} (editable)</div>
          {channel === 'email' && (
            <input value={subject} onChange={e => setSubject(e.target.value)} placeholder="Subject line" style={{ ...input, width: '100%', boxSizing: 'border-box', marginBottom: 8, fontWeight: 600 }} />
          )}
          <textarea value={body} onChange={e => setBody(e.target.value)} placeholder="Message body — generate with AI or write your own…" rows={channel === 'email' ? 12 : 6}
            style={{ ...input, width: '100%', boxSizing: 'border-box', resize: 'vertical', lineHeight: 1.5 }} dir="auto" />
        </div>
        <div style={card}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ fontSize: 13, color: '#cfd6e4' }}>{seg ? <>Would reach <b style={{ color: '#00e5a0' }}>{fmt(recipients)}</b></> : 'Pick an audience'}</div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              {savedMsg && <span style={{ fontSize: 12, color: savedMsg.startsWith('✓') ? '#00e5a0' : '#ffaa00' }}>{savedMsg}</span>}
              <button onClick={save} style={btn('#3a4252', '#cfd6e4')}>Save draft</button>
              <button disabled title="Sending is disabled until the channel is connected & enabled" style={{ ...btn('#2a2f3a', '#5a6172'), cursor: 'not-allowed' }}>🔒 Send (disabled)</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function WatiPanel() {
  return (
    <div style={{ ...card, background: '#16241d', border: '1px solid #1f5c43' }}>
      <div style={{ ...cap, color: '#7fe9c0' }}>💬 Getting the most from Wati</div>
      <ul style={{ margin: 0, paddingLeft: 18, color: '#cfd6e4', fontSize: 12, lineHeight: 1.7 }}>
        <li><b>Broadcasts</b> — send approved WhatsApp templates to a segment (e.g. lapsed depositors) in one go.</li>
        <li><b>Drip sequences</b> — auto follow-ups for no-deposit leads (Day 1 welcome → Day 3 how-to-fund → Day 7 offer).</li>
        <li><b>Click-to-WhatsApp ads</b> — point Meta/TikTok ads straight into a Wati chat to qualify leads instantly.</li>
        <li><b>Chatbot</b> — auto-answer FAQs & pre-qualify, hand hot leads to sales.</li>
        <li><b>Two-way + team inbox</b> — sales reply from one shared inbox; log outcomes back here.</li>
      </ul>
      <div style={{ fontSize: 11, color: '#8a93a5', marginTop: 10 }}>To connect: paste your <b>Wati API endpoint + access token</b> and approve message templates. Until then this is preview-only.</div>
    </div>
  );
}

// ── Channels / Ads status ──
function Channels({ channels, aiOn, onlyAds }: { channels: any[]; aiOn?: boolean; onlyAds?: boolean }) {
  const adKeys = ['meta', 'google', 'tiktok', 'snap'];
  const list = onlyAds ? channels.filter(c => adKeys.includes(c.key)) : channels;
  const icon: any = { email: '✉️', wati: '💬', meta: '📘', google: '🔍', tiktok: '🎵', snap: '👻' };
  return (
    <div style={{ display: 'grid', gap: 14 }}>
      {onlyAds && <div style={{ fontSize: 13, color: '#8a93a5' }}>Each ad platform has a Marketing API I can drive from here once it's credentialed. Status below.</div>}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 12 }}>
        {list.map(c => (
          <div key={c.key} style={card}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
              <div style={{ fontSize: 14, fontWeight: 700, color: '#e6e9ef' }}>{icon[c.key] || '🔌'} {c.name}</div>
              <span style={{ fontSize: 11, fontWeight: 700, padding: '3px 9px', borderRadius: 99, background: c.connected ? '#00e5a022' : '#3a4252', color: c.connected ? '#00e5a0' : '#9aa3b3' }}>
                {c.connected ? 'Connected' : 'Not connected'}
              </span>
            </div>
            <div style={{ fontSize: 12, color: '#8a93a5', lineHeight: 1.5 }}>Needs: {c.needs}</div>
            <div style={{ fontSize: 11, color: c.can_send ? '#00e5a0' : '#ffaa00', marginTop: 8 }}>{c.can_send ? 'Sending enabled' : '🔒 Sending/spend disabled'}</div>
          </div>
        ))}
      </div>
      {!onlyAds && <div style={{ fontSize: 12, color: '#8a93a5' }}>AI drafting: {aiOn ? <b style={{ color: '#00e5a0' }}>on</b> : <b style={{ color: '#ffaa00' }}>off (add backend/ai_key.txt)</b>}</div>}
    </div>
  );
}

// ── Saved drafts ──
function Drafts() {
  const [rows, setRows] = useState<any[]>([]);
  const load = () => apiGet('/marketing/campaigns').then(r => setRows(r.campaigns || [])).catch(() => {});
  useEffect(() => { load(); }, []);
  const del = async (id: number) => { await apiDelete(`/marketing/campaigns/${id}`).catch(() => {}); load(); };
  if (!rows.length) return <div style={{ ...card, color: '#8a93a5', fontSize: 13 }}>No saved drafts yet. Build one in Email or WhatsApp.</div>;
  return (
    <div style={card}>
      <div style={CT.scroll}>
        <table style={CT.table}>
          <thead><tr style={CT.theadTr}>
            {['Name', 'Channel', 'Audience', 'Recipients', 'Status', ''].map(h => <th key={h} style={CT.th(false, h === 'Recipients' ? 'right' : 'left')}>{h}</th>)}
          </tr></thead>
          <tbody>{rows.map(r => (
            <tr key={r.id} style={CT.row()}>
              <td style={{ ...CT.td, whiteSpace: 'normal' }}>{r.name}{r.subject ? <div style={{ fontSize: 11, color: '#8a93a5' }}>{r.subject}</div> : null}</td>
              <td style={CT.td}>{r.channel === 'whatsapp' ? '💬 WhatsApp' : '✉️ Email'}</td>
              <td style={CT.td}>{r.segment_key}</td>
              <td style={{ ...CT.td, textAlign: 'right' }}>{fmt(r.recipient_count)}</td>
              <td style={CT.td}><span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 99, background: '#3a4252', color: '#cfd6e4' }}>{r.status}</span></td>
              <td style={CT.td}><span onClick={() => del(r.id)} style={{ cursor: 'pointer', color: '#ff5d6c' }}>Delete</span></td>
            </tr>))}</tbody>
        </table>
      </div>
    </div>
  );
}

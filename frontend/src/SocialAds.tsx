import React, { useState, useEffect, useCallback } from 'react';
import { apiGet, apiPost } from './api';

// Social Ads console — connect TikTok / Snap / Meta, build hashed Custom Audiences from the
// CRM's smart segments, and draft campaigns. Everything is GATED server-side: audience sync only
// uploads once the platform is connected AND SOCIAL_LIVE_ENABLED=1 — otherwise it's a dry-run.

const card: React.CSSProperties = { background: 'var(--bg-card,#2c333e)', border: '1px solid var(--border,#4f596b)', borderRadius: 12, padding: 18 };
const cap: React.CSSProperties = { fontSize: 11, color: '#8a93a5', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 12, fontWeight: 700 };
const input: React.CSSProperties = { padding: '9px 11px', background: '#1c2231', border: '1px solid #3a4252', borderRadius: 8, color: '#e6e9ef', fontSize: 13 };
const btn = (bg: string, fg = '#06251b'): React.CSSProperties => ({ padding: '9px 14px', background: bg, border: 'none', borderRadius: 8, color: fg, fontSize: 13, fontWeight: 700, cursor: 'pointer' });
const fmt = (n: number) => (n || 0).toLocaleString();

const PLAT: Record<string, { icon: string; name: string; accent: string }> = {
  tiktok: { icon: '🎵', name: 'TikTok', accent: '#ff0050' },
  snap: { icon: '👻', name: 'Snapchat', accent: '#FFFC00' },
  meta: { icon: '📘', name: 'Meta (FB/IG)', accent: '#1877f2' },
};
// the fields each platform's /config accepts (besides OAuth-minted tokens)
const FIELDS: Record<string, { k: string; label: string; ph: string }[]> = {
  tiktok: [
    { k: 'client_id', label: 'App ID', ph: 'TikTok for Business app id' },
    { k: 'client_secret', label: 'App Secret', ph: 'app secret' },
    { k: 'advertiser_id', label: 'Advertiser ID', ph: 'your ad account / advertiser id' },
  ],
  snap: [
    { k: 'client_id', label: 'OAuth Client ID', ph: 'Snap app client id' },
    { k: 'client_secret', label: 'OAuth Client Secret', ph: 'client secret' },
    { k: 'ad_account_id', label: 'Ad Account ID', ph: 'snap ad account id' },
    { k: 'org_id', label: 'Organization ID', ph: 'snap business org id' },
  ],
  meta: [
    { k: 'access_token', label: 'Access Token', ph: 'long-lived system-user token' },
    { k: 'ad_account_id', label: 'Ad Account ID', ph: 'act_XXXXXXXX' },
  ],
};

export default function SocialAds() {
  const [status, setStatus] = useState<any>(null);
  const [platform, setPlatform] = useState<string>('tiktok');
  const [segments, setSegments] = useState<any[]>([]);
  const [audiences, setAudiences] = useState<any[]>([]);

  const load = useCallback(() => {
    apiGet('/social/status').then(setStatus).catch(() => {});
    apiGet('/social/audiences').then(r => setAudiences(r.audiences || [])).catch(() => {});
  }, []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { apiGet('/social/segments').then(r => setSegments(r.segments || [])).catch(() => {}); }, []);

  const ps = status?.platforms?.[platform];

  return (
    <div style={{ display: 'grid', gap: 16 }}>
      <div style={{ background: status?.live_enabled ? '#16241d' : '#241c16', border: `1px solid ${status?.live_enabled ? '#1f5c43' : '#5c451f'}`, color: status?.live_enabled ? '#7fe9c0' : '#e9c97f', borderRadius: 8, padding: '8px 12px', fontSize: 12 }}>
        {status?.live_enabled
          ? '🟢 Live mode ON — connected platforms will receive real audience uploads.'
          : '🔒 Gated — audiences build & hash here but upload nothing until a platform is connected and the live flag is on. Safe to explore.'}
      </div>

      {/* platform tabs */}
      <div style={{ display: 'flex', gap: 8 }}>
        {Object.keys(PLAT).map(p => {
          const r = status?.platforms?.[p]?.ready;
          return (
            <button key={p} onClick={() => setPlatform(p)} style={{
              ...btn(platform === p ? PLAT[p].accent + '22' : 'transparent', platform === p ? '#e6e9ef' : '#8a93a5'),
              border: `1px solid ${platform === p ? PLAT[p].accent : '#3a4252'}`,
            }}>
              {PLAT[p].icon} {PLAT[p].name} {r ? '✓' : ''}
            </button>
          );
        })}
      </div>

      <ConnectionCard platform={platform} ps={ps} onSaved={load} />
      <AudienceBuilder platform={platform} segments={segments} ready={!!ps?.ready} live={!!status?.live_enabled} onSynced={load} />
      <AudienceList audiences={audiences} />
    </div>
  );
}

function ConnectionCard({ platform, ps, onSaved }: { platform: string; ps: any; onSaved: () => void }) {
  const [vals, setVals] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => { setVals({}); setMsg(''); }, [platform]);

  const save = async () => {
    const payload: any = {};
    Object.entries(vals).forEach(([k, v]) => { if (v?.trim()) payload[k] = v.trim(); });
    if (!Object.keys(payload).length) { setMsg('Nothing to save'); return; }
    setBusy(true);
    await apiPost(`/social/${platform}/config`, payload).catch(() => {});
    setBusy(false); setMsg('✓ Saved'); setVals({}); onSaved();
  };
  const connect = async () => {
    const r: any = await apiGet(`/social/${platform}/oauth/start`).catch(() => null);
    if (r?.auth_url) window.open(r.auth_url, '_blank');
    else setMsg(r?.error || 'Could not start OAuth');
  };

  return (
    <div style={card}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <div style={cap}>Connect {PLAT[platform].name}</div>
        <span style={{ fontSize: 11, fontWeight: 700, padding: '3px 10px', borderRadius: 99, background: ps?.ready ? '#00e5a022' : '#3a4252', color: ps?.ready ? '#00e5a0' : '#9aa3b3' }}>
          {ps?.ready ? 'Ready' : 'Not connected'}
        </span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(220px,1fr))', gap: 10, marginBottom: 12 }}>
        {(FIELDS[platform] || []).map(f => (
          <div key={f.k}>
            <div style={{ fontSize: 11, color: '#8a93a5', marginBottom: 4 }}>
              {f.label} {(ps && ((f.k === 'access_token' && ps.token_set) || (f.k === 'client_id' && ps.client_id_set) || (f.k === 'client_secret' && ps.secret_set) || (f.k === 'advertiser_id' && ps.advertiser_id) || (f.k === 'ad_account_id' && ps.ad_account_id))) ? <span style={{ color: '#00e5a0' }}>· set</span> : null}
            </div>
            <input value={vals[f.k] || ''} onChange={e => setVals({ ...vals, [f.k]: e.target.value })} placeholder={f.ph} style={{ ...input, width: '100%', boxSizing: 'border-box' }} />
          </div>
        ))}
      </div>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
        <button onClick={save} disabled={busy} style={btn('#3a4252', '#cfd6e4')}>{busy ? 'Saving…' : 'Save credentials'}</button>
        {platform !== 'meta' && <button onClick={connect} style={btn(PLAT[platform].accent, platform === 'snap' ? '#222' : '#fff')}>↗ Connect (authorize)</button>}
        {msg && <span style={{ fontSize: 12, color: msg.startsWith('✓') ? '#00e5a0' : '#ffaa00' }}>{msg}</span>}
        {ps?.redirect_uri && platform !== 'meta' && <span style={{ fontSize: 11, color: '#8a93a5' }}>Redirect URI to register: <code style={{ color: '#cfd6e4' }}>{ps.redirect_uri}</code></span>}
      </div>
    </div>
  );
}

function AudienceBuilder({ platform, segments, ready, live, onSynced }: { platform: string; segments: any[]; ready: boolean; live: boolean; onSynced: () => void }) {
  const [seg, setSeg] = useState('');
  const [name, setName] = useState('');
  const [preview, setPreview] = useState<any>(null);
  const [result, setResult] = useState<any>(null);
  const [busy, setBusy] = useState(false);

  const segObj = segments.find(s => s.key === seg);
  const doPreview = async () => {
    if (!seg) return;
    setBusy(true); setResult(null);
    const r = await apiPost('/social/audiences/preview', { segment_key: seg }).catch(() => null);
    setPreview(r); setBusy(false);
  };
  const doSync = async () => {
    if (!seg) return;
    setBusy(true);
    const r = await apiPost('/social/audiences/sync', { platform, segment_key: seg, name: name || undefined }).catch(() => null);
    setResult(r); setBusy(false); onSynced();
  };

  return (
    <div style={card}>
      <div style={cap}>Build a Custom Audience → {PLAT[platform].name}</div>
      <div style={{ fontSize: 12, color: '#8a93a5', marginBottom: 12 }}>
        Pick a CRM segment. Emails &amp; phones are <b style={{ color: '#cfd6e4' }}>SHA-256 hashed</b> before anything leaves the server — raw contacts never go to the ad platform. Use it for direct targeting or as a <b style={{ color: '#cfd6e4' }}>lookalike</b> seed.
      </div>
      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'flex-end', marginBottom: 12 }}>
        <div style={{ flex: 1, minWidth: 240 }}>
          <div style={{ fontSize: 11, color: '#8a93a5', marginBottom: 4 }}>Segment</div>
          <select value={seg} onChange={e => { setSeg(e.target.value); setPreview(null); setResult(null); }} style={{ ...input, width: '100%' }}>
            <option value="">Choose a segment…</option>
            {segments.map(s => <option key={s.key} value={s.key}>{s.label} ({fmt(s.total)})</option>)}
          </select>
        </div>
        <div style={{ flex: 1, minWidth: 200 }}>
          <div style={{ fontSize: 11, color: '#8a93a5', marginBottom: 4 }}>Audience name (optional)</div>
          <input value={name} onChange={e => setName(e.target.value)} placeholder={segObj ? `TNFX · ${segObj.label}` : 'Audience name'} style={{ ...input, width: '100%', boxSizing: 'border-box' }} />
        </div>
        <button onClick={doPreview} disabled={!seg || busy} style={btn('#3a4252', '#cfd6e4')}>Preview match</button>
        <button onClick={doSync} disabled={!seg || busy} style={btn(ready && live ? '#00e5a0' : '#9966ff', ready && live ? '#06251b' : '#fff')}>
          {ready && live ? '↗ Sync audience' : '🔒 Sync (dry-run)'}
        </button>
      </div>

      {preview && !preview.error && (
        <div style={{ background: '#1c2231', borderRadius: 8, padding: 12, fontSize: 13, color: '#cfd6e4', marginBottom: result ? 10 : 0 }}>
          <b style={{ color: '#00e5a0' }}>{fmt(preview.matched)}</b> contacts match · {fmt(preview.with_email)} email · {fmt(preview.with_phone)} phone (hashed).
          <div style={{ fontSize: 11, color: '#8a93a5', marginTop: 4 }}>{preview.note}</div>
        </div>
      )}
      {result && (
        <div style={{ background: result.dry_run ? '#241c16' : '#16241d', border: `1px solid ${result.dry_run ? '#5c451f' : '#1f5c43'}`, borderRadius: 8, padding: 12, fontSize: 13, color: result.dry_run ? '#e9c97f' : '#7fe9c0' }}>
          {result.dry_run ? '🔒 ' : '✅ '}{result.message || (result.ok ? 'Synced' : 'Failed')}
        </div>
      )}
    </div>
  );
}

function AudienceList({ audiences }: { audiences: any[] }) {
  if (!audiences.length) return null;
  return (
    <div style={card}>
      <div style={cap}>Audiences</div>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
        <thead><tr style={{ color: '#8a93a5', textAlign: 'left' }}>
          {['Platform', 'Name', 'Segment', 'Size', 'Status', 'When'].map(h => <th key={h} style={{ padding: 7 }}>{h}</th>)}
        </tr></thead>
        <tbody>{audiences.map(a => (
          <tr key={a.id} style={{ borderTop: '1px solid #373f4d', color: '#cfd6e4' }}>
            <td style={{ padding: 7 }}>{PLAT[a.platform]?.icon} {PLAT[a.platform]?.name || a.platform}</td>
            <td style={{ padding: 7 }}>{a.name}</td>
            <td style={{ padding: 7, color: '#8a93a5' }}>{a.segment_key}</td>
            <td style={{ padding: 7 }}>{fmt(a.size)}</td>
            <td style={{ padding: 7 }}>
              <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 99, background: a.dry_run ? '#5c451f44' : (a.status === 'synced' ? '#00e5a022' : '#5c1f1f44'), color: a.dry_run ? '#e9c97f' : (a.status === 'synced' ? '#00e5a0' : '#ff8888') }}>
                {a.dry_run ? 'dry-run' : a.status}
              </span>
            </td>
            <td style={{ padding: 7, color: '#8a93a5' }}>{(a.last_synced_at || a.created_at || '').toString().slice(0, 16).replace('T', ' ')}</td>
          </tr>))}</tbody>
      </table>
    </div>
  );
}

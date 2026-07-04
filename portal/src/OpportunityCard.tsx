import React from 'react';

export type Opportunity = {
  instrument: string; timeframe: string; type: string; title: string;
  direction: string; entry: number; stop: number; target: number;
  target_period: string; age: string; identified_at: string; expiry: string;
  probability?: number | null; description: string; chart_url?: string | null;
};

const GOLD = '#F8500A';

export default function OpportunityCard({ o, onTrade, compact }: { o: Opportunity; onTrade?: () => void; compact?: boolean }) {
  const bear = (o.direction || '').toLowerCase().includes('bear');
  const dirColor = bear ? '#F2667A' : '#34D399';
  const dirArrow = bear ? '▼' : '▲';

  // levels track: position stop / entry / target between min & max
  const lv = [o.stop, o.entry, o.target].filter((x) => typeof x === 'number') as number[];
  const lo = Math.min(...lv), hi = Math.max(...lv);
  const pct = (v: number) => (hi === lo ? 50 : ((v - lo) / (hi - lo)) * 100);

  return (
    <div style={S.card}>
      {/* header */}
      <div style={S.head}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 15, fontWeight: 800, color: '#fff' }}>{o.instrument}</span>
          <span style={S.tf}>{o.timeframe}m</span>
          <span style={{ ...S.dirBadge, color: dirColor, borderColor: dirColor + '55', background: dirColor + '14' }}>
            {dirArrow} {bear ? 'Bearish' : 'Bullish'}
          </span>
        </div>
        <button onClick={onTrade} style={S.trade}>⇄ Trade Now</button>
      </div>

      <div style={{ fontSize: 12.5, color: '#cfd6e2', fontWeight: 700, marginBottom: 2 }}>
        {o.title} <span style={{ color: '#7b8794', fontWeight: 500 }}>· {o.age}</span>
      </div>

      {/* levels */}
      <div style={S.levels}>
        <Lvl label="Entry" val={o.entry} c="#fff" />
        <Lvl label="Target" val={o.target} c="#34D399" />
        <Lvl label="Stop-Loss" val={o.stop} c="#F2667A" />
        <Lvl label="Target period" val={o.target_period} c="#cfd6e2" raw />
      </div>

      {/* levels track */}
      {lv.length === 3 && (
        <div style={S.track}>
          <Marker pos={pct(o.stop)} c="#F2667A" tip="Stop" />
          <Marker pos={pct(o.entry)} c={GOLD} tip="Entry" />
          <Marker pos={pct(o.target)} c="#34D399" tip="Target" />
        </div>
      )}

      {!compact && (
        <div style={{ fontSize: 11.5, color: '#9aa3b3', lineHeight: 1.55, margin: '10px 0 0' }}>{o.description}</div>
      )}
      {o.chart_url && (
        <img src={o.chart_url} alt={o.instrument} style={{ width: '100%', borderRadius: 10, marginTop: 10 }} />
      )}

      <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 10, fontSize: 10.5, color: '#5a6373' }}>
        <span>Identified: {o.identified_at}</span>
        <span>Expiry: {o.expiry}</span>
      </div>
    </div>
  );
}

function Lvl({ label, val, c, raw }: { label: string; val: any; c: string; raw?: boolean }) {
  return (
    <div>
      <div style={{ fontSize: 9.5, letterSpacing: '0.1em', textTransform: 'uppercase', color: '#7b8794', fontWeight: 700 }}>{label}</div>
      <div style={{ fontSize: 14, fontWeight: 800, color: c, marginTop: 2, fontVariantNumeric: 'tabular-nums' }}>
        {raw ? (val || '—') : (typeof val === 'number' ? val : '—')}
      </div>
    </div>
  );
}

function Marker({ pos, c, tip }: { pos: number; c: string; tip: string }) {
  return (
    <div style={{ position: 'absolute', left: `${pos}%`, top: 0, transform: 'translateX(-50%)', textAlign: 'center' }} title={tip}>
      <div style={{ width: 2, height: 14, background: c, margin: '0 auto' }} />
      <div style={{ width: 9, height: 9, borderRadius: '50%', background: c, margin: '0 auto' }} />
    </div>
  );
}

const S: any = {
  card: { background: '#12161F', border: '1px solid #232a38', borderRadius: 14, padding: 16 },
  head: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8, gap: 8, flexWrap: 'wrap' },
  tf: { fontSize: 10.5, color: '#8A93A3', background: '#1b2230', padding: '2px 7px', borderRadius: 6, fontWeight: 700 },
  dirBadge: { fontSize: 10.5, fontWeight: 800, padding: '2px 8px', borderRadius: 99, border: '1px solid' },
  trade: { background: '#E8772E', border: 'none', color: '#fff', fontSize: 11.5, fontWeight: 800, padding: '7px 13px', borderRadius: 8, cursor: 'pointer' },
  levels: { display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '8px 14px', margin: '12px 0 4px' },
  track: { position: 'relative', height: 24, marginTop: 14, borderTop: '1px dashed #2a3240' },
};

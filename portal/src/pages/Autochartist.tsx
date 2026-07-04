import React, { useState, useEffect } from 'react';
import { AUTOCHARTIST_SRC } from '../autochartist';
import { apiGet } from '../api';
import OpportunityCard from '../OpportunityCard';

const GOLD = '#F8500A';

const MODELS: { icon: string; title: string; desc: string }[] = [
  { icon: '📐', title: 'Chart Patterns', desc: 'Triangles, channels, wedges, flags & pennants, head & shoulders, double tops/bottoms — emerging & completed, each with a quality score.' },
  { icon: '🔱', title: 'Fibonacci Patterns', desc: 'Harmonic patterns — Gartley, Butterfly, Bat, Crab, ABCD — with entry and target zones.' },
  { icon: '📊', title: 'Key Levels', desc: 'Live support & resistance plus Fibonacci retracement/extension levels, updated continuously.' },
  { icon: '🌊', title: 'Volatility Analysis', desc: 'Forecasts the expected price range and suggests data-driven stop-loss & take-profit distances.' },
  { icon: '📈', title: 'Trend & Breakout', desc: 'Identifies the prevailing trend and the likely breakout direction on each instrument.' },
  { icon: '🧮', title: 'Power Stats', desc: 'Historical price-movement & volatility statistics so you can size and time trades sensibly.' },
  { icon: '🗞️', title: 'Market Reports', desc: 'Scheduled daily & weekly opportunity reports delivered automatically.' },
  { icon: '🗓️', title: 'News Volatility', desc: 'Highlights the instruments most likely to move around upcoming economic events.' },
  { icon: '🔔', title: 'Real-time Alerts', desc: 'Get pinged the moment a new setup forms on your watched symbols.' },
];
const MT4_STEPS = [
  'Download the TNFX Autochartist plugin/installer (ask your account manager).',
  'Fully close MetaTrader 4.',
  'Run the installer — it auto-detects your MT4 terminal. Click through and finish.',
  'Re-open MT4. In the “Navigator” panel, open “Expert Advisors”.',
  'Drag “Autochartist” onto any open chart.',
  'Tick “Allow DLL imports” / “Allow live trading”, then press OK.',
  'The Autochartist panel docks into MT4 — pick your symbols and you’re ready.',
];
const MT5_STEPS = [
  'Download the TNFX Autochartist plugin/installer.',
  'Fully close MetaTrader 5.',
  'Run the installer — it auto-detects your MT5 terminal. Finish the setup.',
  'Re-open MT5. In the “Navigator” panel, open “Expert Advisors”.',
  'Drag “Autochartist” onto a chart and allow algorithmic trading.',
  'The Autochartist panel appears — select your instruments to start.',
];
const USE_STEPS = [
  'Open the Autochartist panel (here in the portal, or inside MT4/MT5).',
  'Choose the symbols you care about.',
  'Browse detected opportunities — each shows a quality/probability score.',
  'Click one to see the pattern, suggested direction, and key levels.',
  'Use Volatility Analysis to set sensible stop-loss / take-profit distances.',
  'Turn on alerts so you’re notified the moment a new setup forms.',
];

export default function Autochartist({ section = 'live' }: { section?: 'live' | 'signals' | 'models' | 'install' }) {
  const [ops, setOps] = useState<any[]>([]);
  useEffect(() => {
    if (section === 'signals') apiGet('/autochartist/opportunities?limit=12').then((r: any) => setOps(r?.opportunities || [])).catch(() => {});
  }, [section]);

  if (section === 'signals') {
    return (
      <div style={S.infoPage}>
        <div style={S.sectionTitle}>Live Opportunities <span style={S.freePill2}>🎁 FREE</span></div>
        {ops.length === 0 ? (
          <div style={{ color: '#8A93A3', fontSize: 13, padding: 24 }}>Loading opportunities…</div>
        ) : (
          <div style={S.cardsGrid}>
            {ops.map((o, i) => <OpportunityCard key={i} o={o} />)}
          </div>
        )}
      </div>
    );
  }
  if (section === 'models') {
    return (
      <div style={S.infoPage}>
        <div style={S.sectionTitle}>What Autochartist gives you</div>
        <div style={S.grid}>
          {MODELS.map((m, i) => (
            <div key={i} style={S.featCard}>
              <div style={{ fontSize: 22, marginBottom: 8 }}>{m.icon}</div>
              <div style={{ fontSize: 13.5, fontWeight: 700, color: '#fff', marginBottom: 5 }}>{m.title}</div>
              <div style={{ fontSize: 12, color: '#9aa3b3', lineHeight: 1.55 }}>{m.desc}</div>
            </div>
          ))}
        </div>
      </div>
    );
  }
  if (section === 'install') {
    return (
      <div style={S.infoPage}>
        <div style={S.sectionTitle}>Install & use Autochartist</div>
        <div style={S.guideGrid}>
          <Guide title="📥 Install on MT4" steps={MT4_STEPS} />
          <Guide title="📥 Install on MT5" steps={MT5_STEPS} />
          <Guide title="🚀 How to use it" steps={USE_STEPS} />
        </div>
        <div style={{ fontSize: 11, color: '#5a6373', textAlign: 'center', marginTop: 18, lineHeight: 1.6 }}>
          Autochartist signals are trading ideas to confirm with your own judgement — not guaranteed
          outcomes. Trading carries risk. Need the installer? Ask your account manager. 🤝
        </div>
      </div>
    );
  }

  // section === 'live' — tool first, full width & tall
  return (
    <div style={S.livePage}>
      <div style={S.bar}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 20 }}>📈</span>
          <span style={{ fontSize: 17, fontWeight: 800, color: '#fff' }}>Autochartist</span>
          <span style={S.freePill}>🎁 FREE for TNFX clients</span>
        </div>
        <span style={{ fontSize: 11.5, color: '#8A93A3' }}>Live automated market analysis</span>
      </div>
      {AUTOCHARTIST_SRC ? (
        <iframe title="Autochartist" src={AUTOCHARTIST_SRC} style={S.frame} allow="fullscreen" />
      ) : (
        <div style={S.placeholder}>Autochartist embed not connected.</div>
      )}
    </div>
  );
}

function Guide({ title, steps }: { title: string; steps: string[] }) {
  return (
    <div style={S.guideCard}>
      <div style={S.guideHead}>{title}</div>
      <ol style={{ margin: 0, paddingLeft: 18 }}>
        {steps.map((s, i) => (
          <li key={i} style={{ fontSize: 12.5, color: '#cfd6e2', lineHeight: 1.6, marginBottom: 7 }}>{s}</li>
        ))}
      </ol>
    </div>
  );
}

const S: any = {
  livePage: { padding: '14px 16px', width: '100%', boxSizing: 'border-box', display: 'flex', flexDirection: 'column', height: 'calc(100vh - 86px)' },
  bar: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10, flexWrap: 'wrap', gap: 8 },
  freePill: { fontSize: 11, fontWeight: 800, color: '#0B0E14', background: 'linear-gradient(90deg,#F8500A,#FF7A1A)', padding: '4px 12px', borderRadius: 99 },
  frame: { flex: 1, width: '100%', minHeight: 480, border: '1px solid #232a38', borderRadius: 14, background: '#fff' },
  placeholder: { flex: 1, display: 'grid', placeItems: 'center', color: '#8A93A3', border: '1px dashed #2a3240', borderRadius: 14, background: '#12161F' },
  infoPage: { padding: 28, maxWidth: 1040, margin: '0 auto' },
  sectionTitle: { fontSize: 18, fontWeight: 800, color: '#fff', margin: '4px 4px 14px' },
  grid: { display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 },
  cardsGrid: { display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 14 },
  freePill2: { fontSize: 10.5, fontWeight: 800, color: '#0B0E14', background: 'linear-gradient(90deg,#F8500A,#FF7A1A)', padding: '3px 10px', borderRadius: 99, marginLeft: 8, verticalAlign: 'middle' },
  featCard: { background: '#12161F', border: '1px solid #232a38', borderRadius: 14, padding: 16 },
  guideGrid: { display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 },
  guideCard: { background: '#12161F', border: '1px solid #232a38', borderRadius: 14, padding: 18 },
  guideHead: { fontSize: 14, fontWeight: 800, color: GOLD, marginBottom: 12 },
};

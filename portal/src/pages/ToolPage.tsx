import React from 'react';

type Feature = { icon: string; title: string; desc: string };

const CONFIG: any = {
  copytrading: {
    icon: '🔁', title: 'Copy Trading',
    blurb: 'Follow top-performing traders and automatically mirror their trades in your own account.',
    features: [
      { icon: '🏆', title: 'Top traders leaderboard', desc: 'Browse verified strategies ranked by return, risk, and consistency.' },
      { icon: '⚙️', title: 'One-click copy', desc: 'Allocate funds and copy a trader — positions mirror automatically.' },
      { icon: '🛡️', title: 'Risk controls', desc: 'Set copy ratio, max drawdown, and stop-copy rules to stay in control.' },
    ],
    cta: 'Join the waitlist',
  },
  autochartist: {
    icon: '📈', title: 'Autochartist',
    blurb: 'Automated technical analysis — chart patterns, key levels, and volatility insights scanned across markets in real time.',
    features: [
      { icon: '🔍', title: 'Pattern recognition', desc: 'Emerging and completed chart patterns detected automatically.' },
      { icon: '📊', title: 'Key levels', desc: 'Support/resistance and Fibonacci levels updated continuously.' },
      { icon: '🔔', title: 'Trade alerts', desc: 'Get notified the moment a setup forms on your watched symbols.' },
    ],
    cta: 'Enable Autochartist',
  },
  tradingcentral: {
    icon: '🎯', title: 'Trading Central',
    blurb: 'Award-winning research and actionable analyst insights to sharpen your trading decisions.',
    features: [
      { icon: '🧭', title: 'Analyst views', desc: 'Daily directional bias and technical commentary per instrument.' },
      { icon: '📰', title: 'Market buzz', desc: 'News sentiment and social signals distilled into a clear read.' },
      { icon: '📐', title: 'Strategy builder', desc: 'Entry, target, and stop suggestions backed by quant models.' },
    ],
    cta: 'Open Trading Central',
  },
};

export default function ToolPage({ tool }: { tool: 'copytrading' | 'autochartist' | 'tradingcentral' }) {
  const c = CONFIG[tool];
  return (
    <div style={S.page}>
      <div style={S.hero}>
        <div style={{ fontSize: 44 }}>{c.icon}</div>
        <h1 style={S.h1}>{c.title}</h1>
        <p style={S.blurb}>{c.blurb}</p>
        <span style={S.badge}>Coming soon</span>
      </div>

      <div style={S.featGrid}>
        {c.features.map((f: Feature, i: number) => (
          <div key={i} style={S.featCard}>
            <div style={{ fontSize: 24, marginBottom: 10 }}>{f.icon}</div>
            <div style={{ fontSize: 14, fontWeight: 700, color: '#fff', marginBottom: 6 }}>{f.title}</div>
            <div style={{ fontSize: 12, color: '#9aa3b3', lineHeight: 1.55 }}>{f.desc}</div>
          </div>
        ))}
      </div>

      <div style={S.ctaWrap}>
        <button style={S.cta}>{c.cta}</button>
        <div style={{ fontSize: 11, color: '#5a6373', marginTop: 10 }}>
          This feature is being set up. You'll be notified the moment it goes live.
        </div>
      </div>
    </div>
  );
}

const S: any = {
  page: { padding: 28, maxWidth: 880, margin: '0 auto' },
  hero: { textAlign: 'center', background: 'linear-gradient(160deg,#141821,#0d1016)', border: '1px solid #232a38', borderRadius: 18, padding: '38px 28px', marginBottom: 18 },
  h1: { fontSize: 26, fontWeight: 800, margin: '12px 0 8px', color: '#fff' },
  blurb: { fontSize: 13.5, color: '#9aa3b3', maxWidth: 520, margin: '0 auto', lineHeight: 1.6 },
  badge: { display: 'inline-block', marginTop: 16, fontSize: 10.5, fontWeight: 800, letterSpacing: '0.1em', color: '#F8500A', background: 'rgba(232,184,75,0.1)', border: '1px solid rgba(232,184,75,0.25)', padding: '5px 14px', borderRadius: 99 },
  featGrid: { display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginBottom: 20 },
  featCard: { background: '#12161F', border: '1px solid #232a38', borderRadius: 14, padding: 18 },
  ctaWrap: { textAlign: 'center' },
  cta: { padding: '12px 28px', borderRadius: 10, background: 'linear-gradient(90deg,#F8500A,#FF7A1A)', color: '#0B0E14', border: 'none', fontSize: 14, fontWeight: 800, cursor: 'pointer' },
};

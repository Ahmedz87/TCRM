import React, { useState } from 'react';

const FAQ = [
  { q: 'How do I earn TN-Points?', a: 'You earn points on every closed trade in FX majors, minors, and Gold (XAUUSD). Points are based on your lot size and your current tier: Bronze 4, Silver 5, Gold 6, Platinum 7 points per standard lot.' },
  { q: 'How do I move up a tier?', a: 'Keep a daily trading streak. Trade at least once every market day for 30 days in a row to advance from Bronze to Silver, and Silver to Gold. Reaching Platinum takes a 40-day streak. Weekends do not break your streak.' },
  { q: 'What can I redeem points for?', a: 'Trading bonuses, cashback (points ÷ 12), and premium rewards like the latest iPhone, a Dubai trip, or a luxury car. Visit the Rewards page to see everything you can claim.' },
  { q: 'How does Invite Friends work?', a: 'Share your referral code from the Rewards page. When your friend registers, completes verification, and funds their account, you earn 100 points after a quick review.' },
  { q: 'How long do deposits and withdrawals take?', a: 'Deposits are usually instant once the payment gateway confirms. Withdrawals are reviewed by our team and processed according to your chosen method.' },
];

export default function Support() {
  const [open, setOpen] = useState<number | null>(0);
  const [sent, setSent] = useState(false);
  const [msg, setMsg] = useState('');

  return (
    <div style={S.page}>
      <h1 style={S.h1}>Support</h1>

      <div style={S.contactGrid}>
        <a href="mailto:support@tnfx.co" style={S.contactCard}>
          <div style={{ fontSize: 26 }}>✉️</div>
          <div>
            <div style={{ fontSize: 13.5, fontWeight: 700, color: '#fff' }}>Email us</div>
            <div style={{ fontSize: 11.5, color: '#8A93A3' }}>support@tnfx.co</div>
          </div>
        </a>
        <div style={S.contactCard}>
          <div style={{ fontSize: 26 }}>💬</div>
          <div>
            <div style={{ fontSize: 13.5, fontWeight: 700, color: '#fff' }}>Live chat</div>
            <div style={{ fontSize: 11.5, color: '#8A93A3' }}>Available 24/5</div>
          </div>
        </div>
      </div>

      <div style={S.sectionLabel}>Send us a message</div>
      <div style={S.panel}>
        {sent ? (
          <div style={{ color: '#34D399', fontSize: 13.5 }}>✓ Thanks — your message has been sent. Our team will get back to you shortly.</div>
        ) : (
          <>
            <textarea value={msg} onChange={e => setMsg(e.target.value)} placeholder="How can we help?" rows={4} style={S.textarea} />
            <button onClick={() => { if (msg.trim()) { setSent(true); } }} style={S.btn}>Send message</button>
          </>
        )}
      </div>

      <div style={S.sectionLabel}>Frequently asked</div>
      <div style={S.panel}>
        {FAQ.map((f, i) => (
          <div key={i} style={{ borderBottom: i < FAQ.length - 1 ? '1px solid #1A1F2B' : 'none' }}>
            <button onClick={() => setOpen(open === i ? null : i)} style={S.faqQ}>
              <span>{f.q}</span>
              <span style={{ color: '#8A93A3', transform: open === i ? 'rotate(180deg)' : 'none', transition: 'transform .2s' }}>▾</span>
            </button>
            {open === i && <div style={S.faqA}>{f.a}</div>}
          </div>
        ))}
      </div>
    </div>
  );
}

const S: any = {
  page: { padding: 28, maxWidth: 720, margin: '0 auto' },
  h1: { fontSize: 24, fontWeight: 800, margin: '0 0 20px', color: '#fff' },
  contactGrid: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 22 },
  contactCard: { display: 'flex', alignItems: 'center', gap: 14, background: '#12161F', border: '1px solid #232a38', borderRadius: 14, padding: 18, textDecoration: 'none', cursor: 'pointer' },
  sectionLabel: { fontSize: 10.5, letterSpacing: '0.14em', textTransform: 'uppercase', color: '#8A93A3', fontWeight: 700, margin: '6px 0 10px' },
  panel: { background: '#12161F', border: '1px solid #232a38', borderRadius: 14, padding: 18, marginBottom: 20 },
  textarea: { width: '100%', padding: '11px 13px', borderRadius: 10, background: '#0B0E14', border: '1px solid #2a3240', color: '#fff', fontSize: 13.5, outline: 'none', resize: 'vertical', boxSizing: 'border-box' },
  btn: { marginTop: 12, padding: '10px 20px', borderRadius: 9, background: 'linear-gradient(90deg,#F8500A,#FF7A1A)', color: '#0B0E14', border: 'none', fontSize: 13, fontWeight: 800, cursor: 'pointer' },
  faqQ: { width: '100%', display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '14px 0', background: 'transparent', border: 'none', color: '#fff', fontSize: 13.5, fontWeight: 600, cursor: 'pointer', textAlign: 'left' },
  faqA: { fontSize: 12.5, color: '#9aa3b3', lineHeight: 1.6, padding: '0 0 14px' },
};

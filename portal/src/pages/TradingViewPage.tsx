import React, { useEffect, useRef, useState } from 'react';

const SYMBOLS = [
  { label: 'EUR/USD', tv: 'FX:EURUSD' },
  { label: 'GBP/USD', tv: 'FX:GBPUSD' },
  { label: 'USD/JPY', tv: 'FX:USDJPY' },
  { label: 'Gold', tv: 'OANDA:XAUUSD' },
  { label: 'BTC/USD', tv: 'BITSTAMP:BTCUSD' },
];

export default function TradingViewPage() {
  const [sym, setSym] = useState(SYMBOLS[0].tv);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    ref.current.innerHTML = '';
    const container = document.createElement('div');
    container.className = 'tradingview-widget-container__widget';
    container.style.height = '100%';
    ref.current.appendChild(container);

    const script = document.createElement('script');
    script.src = 'https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js';
    script.async = true;
    script.innerHTML = JSON.stringify({
      autosize: true, symbol: sym, interval: '60', timezone: 'Etc/UTC',
      theme: 'dark', style: '1', locale: 'en',
      enable_publishing: false, hide_side_toolbar: false, allow_symbol_change: true,
      backgroundColor: 'rgba(11,14,20,1)', gridColor: 'rgba(35,42,56,0.5)',
    });
    ref.current.appendChild(script);
  }, [sym]);

  return (
    <div style={S.page}>
      <div style={S.head}>
        <h1 style={S.h1}>Charts · TradingView</h1>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {SYMBOLS.map(s => (
            <button key={s.tv} onClick={() => setSym(s.tv)}
              style={{ ...S.chip, ...(sym === s.tv ? S.chipActive : {}) }}>{s.label}</button>
          ))}
        </div>
      </div>
      <div style={S.chartWrap}>
        <div ref={ref} style={{ height: '100%', width: '100%' }} />
      </div>
    </div>
  );
}

const S: any = {
  page: { padding: 28, maxWidth: 1100, margin: '0 auto', height: 'calc(100vh - 58px)', display: 'flex', flexDirection: 'column', boxSizing: 'border-box' },
  head: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12, marginBottom: 16 },
  h1: { fontSize: 24, fontWeight: 800, margin: 0, color: '#fff' },
  chip: { padding: '7px 14px', borderRadius: 8, background: '#12161F', border: '1px solid #2a3240', color: '#cdd4de', fontSize: 12.5, cursor: 'pointer' },
  chipActive: { background: 'rgba(232,184,75,0.12)', border: '1px solid #F8500A', color: '#F8500A', fontWeight: 700 },
  chartWrap: { flex: 1, minHeight: 420, borderRadius: 14, overflow: 'hidden', border: '1px solid #232a38', background: '#0B0E14' },
};

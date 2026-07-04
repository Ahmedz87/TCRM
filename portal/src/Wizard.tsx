import React from 'react';
import { TH } from './theme';

// A reusable stepped wizard shell: progress dots, title, slide area, back/next.
export function Wizard({ steps, current, children, onBack, onNext, nextLabel, nextDisabled, hideNav }: {
  steps: string[]; current: number; children: React.ReactNode;
  onBack?: () => void; onNext?: () => void; nextLabel?: string; nextDisabled?: boolean; hideNav?: boolean;
}) {
  return (
    <div style={{ maxWidth: 560, margin: '0 auto' }}>
      {/* progress */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 24 }}>
        {steps.map((s, i) => (
          <React.Fragment key={i}>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, flex: '0 0 auto' }}>
              <div style={{
                width: 26, height: 26, borderRadius: 99, display: 'grid', placeItems: 'center',
                fontSize: 12, fontWeight: 800,
                background: i < current ? TH.accent : i === current ? TH.accent : TH.panel,
                color: i <= current ? '#06231a' : TH.dim,
                border: `1px solid ${i <= current ? TH.accent : TH.border}`,
              }}>{i < current ? '✓' : i + 1}</div>
            </div>
            {i < steps.length - 1 && <div style={{ flex: 1, height: 2, background: i < current ? TH.accent : TH.border, borderRadius: 2 }} />}
          </React.Fragment>
        ))}
      </div>
      <div style={{ fontSize: 11, letterSpacing: '0.14em', textTransform: 'uppercase', color: TH.muted, fontWeight: 700, textAlign: 'center', marginBottom: 4 }}>
        Step {current + 1} of {steps.length}
      </div>
      <h2 style={{ fontSize: 22, fontWeight: 800, textAlign: 'center', margin: '0 0 22px', color: TH.text }}>{steps[current]}</h2>

      <div style={{ minHeight: 180 }}>{children}</div>

      {!hideNav && (
        <div style={{ display: 'flex', gap: 10, marginTop: 24 }}>
          {onBack && <button onClick={onBack} style={ghostBtn}>← Back</button>}
          {onNext && <button onClick={onNext} disabled={nextDisabled} style={{ ...primaryBtn, flex: 1, opacity: nextDisabled ? 0.5 : 1, cursor: nextDisabled ? 'not-allowed' : 'pointer' }}>{nextLabel || 'Continue'}</button>}
        </div>
      )}
    </div>
  );
}

// a selectable option card (big tap target for wizard choices)
export function OptionCard({ active, onClick, icon, title, sub, right }: any) {
  return (
    <button onClick={onClick} style={{
      width: '100%', display: 'flex', alignItems: 'center', gap: 14, padding: '16px 18px',
      borderRadius: TH.radius, marginBottom: 10, cursor: 'pointer', textAlign: 'left',
      background: active ? 'rgba(58,210,159,0.10)' : TH.panel,
      border: `1.5px solid ${active ? TH.accent : TH.border}`,
      color: TH.text, transition: 'all .12s', fontFamily: 'inherit',
    }}>
      {icon && <span style={{ fontSize: 24, width: 30, textAlign: 'center', flex: '0 0 auto' }}>{icon}</span>}
      <span style={{ flex: 1 }}>
        <span style={{ display: 'block', fontSize: 15, fontWeight: 700 }}>{title}</span>
        {sub && <span style={{ display: 'block', fontSize: 12, color: TH.muted, marginTop: 2 }}>{sub}</span>}
      </span>
      {right && <span style={{ fontSize: 13, fontWeight: 700, color: active ? TH.accent : TH.muted }}>{right}</span>}
      <span style={{ width: 20, height: 20, borderRadius: 99, border: `2px solid ${active ? TH.accent : TH.border2}`, background: active ? TH.accent : 'transparent', display: 'grid', placeItems: 'center', flex: '0 0 auto' }}>
        {active && <span style={{ width: 8, height: 8, borderRadius: 99, background: '#06231a' }} />}
      </span>
    </button>
  );
}

export const primaryBtn: any = { padding: '13px 20px', borderRadius: TH.radiusSm, background: TH.accentGrad, color: '#fff', border: 'none', fontSize: 14, fontWeight: 800, cursor: 'pointer', fontFamily: 'inherit' };
export const ghostBtn: any = { padding: '13px 20px', borderRadius: TH.radiusSm, background: 'transparent', border: `1px solid ${TH.border2}`, color: TH.text, fontSize: 14, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' };

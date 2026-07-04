import React, { useState, useEffect } from 'react';
import { apiGet, apiPost } from './api';
import ScoreRules from './ScoreRules';

const DEFAULTS: Record<string, number> = {
  no_contact_14d:        30,
  no_contact_7d:         15,
  call_later_reached:    25,
  no_deposit_ever:       25,
  no_deposit_21d:        20,
  payment_rejected:      35,
  first_dep_7d:          20,
  withdrawal_pending:    15,
  margin_below_50:       40,
  margin_below_100:      25,
  no_trade_30d:          15,
  has_balance:           10,
  min_days_between_calls:14,
  max_days_without_call: 14,
};

const SECTIONS = [
  {
    title: '📞 Overdue contact', badge: 'Urgent', badgeColor: '#ff4d4d',
    items: [
      { key: 'no_contact_14d',     label: 'No contact in 14+ days',         desc: 'Client overdue — must be called immediately',            unit: 'pts' },
      { key: 'no_contact_7d',      label: 'No contact in 7–13 days',        desc: 'Getting overdue — call soon',                           unit: 'pts' },
      { key: 'call_later_reached', label: 'Call later date reached',         desc: 'Sales promised a callback — that date has arrived',      unit: 'pts' },
    ]
  },
  {
    title: '💰 Deposit triggers', badge: 'High priority', badgeColor: '#ffaa00',
    items: [
      { key: 'no_deposit_ever',    label: 'Logged in but never deposited',   desc: 'Active account with no deposit — hot lead',             unit: 'pts' },
      { key: 'no_deposit_21d',     label: 'No deposit in 21+ days',          desc: 'Previously active client has gone cold',                unit: 'pts' },
      { key: 'payment_rejected',   label: 'Payment rejected recently',       desc: 'Tried to deposit but payment failed — needs help',      unit: 'pts' },
      { key: 'first_dep_7d',       label: 'First deposit in last 7 days',    desc: 'New depositor — nurture while engaged',                 unit: 'pts' },
      { key: 'withdrawal_pending', label: 'Withdrawal pending or recent',    desc: 'Retention risk — call before funds leave',              unit: 'pts' },
    ]
  },
  {
    title: '⚠️ Account health', badge: 'Risk', badgeColor: '#ff4d4d',
    items: [
      { key: 'margin_below_50',    label: 'Margin level below 50%',          desc: 'Urgent — account almost at margin call',                unit: 'pts' },
      { key: 'margin_below_100',   label: 'Margin level 50%–100%',           desc: 'Low margin — warn client',                             unit: 'pts' },
      { key: 'no_trade_30d',       label: 'No trade in 30+ days (has balance)',desc: 'Funded but inactive — re-engage before withdrawal',  unit: 'pts' },
      { key: 'has_balance',        label: 'Has positive balance',             desc: 'Active funded client — always worth checking in',      unit: 'pts' },
    ]
  },
  {
    title: '🔄 Call cycle', badge: '', badgeColor: '',
    items: [
      { key: 'min_days_between_calls', label: 'Minimum days between calls',   desc: 'After a call, client won\'t appear as priority for this many days', unit: 'days' },
      { key: 'max_days_without_call',  label: 'Maximum days without a call',  desc: 'Every client is guaranteed to be called within this period',        unit: 'days' },
    ]
  },
];

const PREVIEW_TRIGGERS = ['no_contact_14d', 'has_balance', 'margin_below_50'];
const PREVIEW_LABELS: Record<string, string> = {
  no_contact_14d: 'No contact 14+ days',
  has_balance:    'Has positive balance',
  margin_below_50:'Margin below 50%',
};

export default function ScoreSettings() {
  const [values, setValues]   = useState<Record<string, number>>({ ...DEFAULTS });
  const [saved, setSaved]     = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiGet('/settings/score').then(data => {
      if (data && typeof data === 'object') {
        setValues(prev => ({ ...prev, ...data }));
      }
    }).catch(() => {}).finally(() => setLoading(false));
  }, []);

  const previewScore = Math.min(100, PREVIEW_TRIGGERS.reduce((sum, k) => sum + (values[k] || 0), 0));
  const scoreColor   = (s: number) => s >= 60 ? '#ff4d4d' : s >= 30 ? '#ffaa00' : '#00e5a0';

  const handleSave = async () => {
    try {
      await apiPost('/settings/score', values);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (e) { alert('Failed to save settings'); }
  };

  const handleReset = () => setValues({ ...DEFAULTS });

  if (loading) return <div style={{ color: '#555', padding: 40, textAlign: 'center' }}>Loading settings...</div>;

  const cardStyle: React.CSSProperties = {
    background: '#2c333e', border: '1px solid #4f596b', borderRadius: 12, padding: 16, marginBottom: 12,
  };
  const rowStyle: React.CSSProperties = {
    display: 'flex', alignItems: 'center', padding: '10px 0', borderBottom: '1px solid #373f4d',
  };

  return (
    <div style={{ maxWidth: 920 }}>
      <ScoreRules />
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20, flexWrap: 'wrap', gap: 12 }}>
        <div>
          <div style={{ fontSize: 18, fontWeight: 600 }}>Priority score settings</div>
          <div style={{ fontSize: 12, color: '#555', marginTop: 4 }}>Changes apply immediately — all client scores recalculate on save</div>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button onClick={handleReset}
            style={{ padding: '7px 16px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 8, color: '#888', fontSize: 12, cursor: 'pointer' }}>
            Reset defaults
          </button>
          <button onClick={handleSave}
            style={{ padding: '7px 20px', background: '#00e5a0', border: 'none', borderRadius: 8, color: '#000', fontSize: 13, fontWeight: 600, cursor: 'pointer' }}>
            Save changes
          </button>
        </div>
      </div>

      {/* Saved toast */}
      {saved && (
        <div style={{ background: '#0e3a2a', border: '1px solid #00e5a022', borderRadius: 8, padding: '10px 16px', marginBottom: 12, fontSize: 12, color: '#00e5a0', fontWeight: 500 }}>
          ✅ Settings saved — client scores are recalculating now
        </div>
      )}

      {/* Sections */}
      {SECTIONS.map(section => (
        <div key={section.title} style={cardStyle}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12, paddingBottom: 10, borderBottom: '1px solid #373f4d' }}>
            <span style={{ fontSize: 13, fontWeight: 600 }}>{section.title}</span>
            {section.badge && (
              <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, background: `${section.badgeColor}22`, color: section.badgeColor, fontWeight: 500 }}>
                {section.badge}
              </span>
            )}
          </div>
          {section.items.map((item, i) => (
            <div key={item.key} style={{ ...rowStyle, borderBottom: i < section.items.length - 1 ? '1px solid #373f4d' : 'none', paddingBottom: i === section.items.length - 1 ? 0 : 10 }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 12, color: '#e0e0e0', fontWeight: 500 }}>{item.label}</div>
                <div style={{ fontSize: 11, color: '#555', marginTop: 3 }}>{item.desc}</div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <input
                  type="number" min={0} max={item.unit === 'days' ? 90 : 100}
                  value={values[item.key] ?? DEFAULTS[item.key]}
                  onChange={e => setValues(prev => ({ ...prev, [item.key]: Math.max(0, parseInt(e.target.value) || 0) }))}
                  style={{ width: 64, padding: '5px 8px', textAlign: 'center', fontSize: 14, fontWeight: 600, border: '1px solid #626d80', borderRadius: 8, background: '#373f4d', color: '#e0e0e0', outline: 'none' }}
                />
                <span style={{ fontSize: 11, color: '#555', minWidth: 28 }}>{item.unit}</span>
              </div>
            </div>
          ))}
        </div>
      ))}

      {/* Live preview */}
      <div style={cardStyle}>
        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12, paddingBottom: 10, borderBottom: '1px solid #373f4d' }}>🧮 Score preview</div>
        <div style={{ fontSize: 11, color: '#555', marginBottom: 10 }}>Example: client with balance, no contact in 14 days, margin below 50%</div>
        {PREVIEW_TRIGGERS.map(k => (
          <div key={k} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, padding: '4px 0' }}>
            <span style={{ color: '#888' }}>{PREVIEW_LABELS[k]}</span>
            <span style={{ color: '#ff4d4d', fontWeight: 600 }}>+{values[k] || 0}</span>
          </div>
        ))}
        <div style={{ borderTop: '1px solid #373f4d', marginTop: 10, paddingTop: 10, display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
          <span style={{ color: '#555' }}>Example total</span>
          <span style={{ fontWeight: 700, color: scoreColor(previewScore) }}>{previewScore} / 100</span>
        </div>
      </div>

      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 4 }}>
        <button onClick={handleReset}
          style={{ padding: '7px 16px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 8, color: '#888', fontSize: 12, cursor: 'pointer' }}>
          Reset defaults
        </button>
        <button onClick={handleSave}
          style={{ padding: '7px 20px', background: '#00e5a0', border: 'none', borderRadius: 8, color: '#000', fontSize: 13, fontWeight: 600, cursor: 'pointer' }}>
          Save changes
        </button>
      </div>
    </div>
  );
}

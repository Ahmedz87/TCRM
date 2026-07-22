import React from 'react';

/**
 * "My team" toggle — shown ONLY to team leaders / managers (localStorage.isTeamLead).
 * ONE clickable chip. DEFAULT (off) = the leader sees only their OWN data (page sends `&own=1`).
 * Click it ON = expand to their whole team's data (no `own` param). Click again = back to own.
 * (The page state seed must default to own=true so the first load shows own data.)
 *
 * `section` (optional) hides the toggle if the leader is restricted from that page anyway.
 */
export function useIsTeamLead(section?: string): boolean {
  const isLead = (typeof localStorage !== 'undefined' && localStorage.getItem('isTeamLead') === '1');
  if (!isLead) return false;
  if (section) {
    const secs = (localStorage.getItem('scopeSections') || '').split(',').filter(Boolean);
    if (secs.length && !secs.includes(section)) return false;  // not allowed here at all
  }
  return true;
}

export default function OwnDataToggle({ own, setOwn, section }:
  { own: boolean; setOwn: (v: boolean) => void; section?: string }) {
  if (!useIsTeamLead(section)) return null;
  const teamOn = !own;   // team view is ON when NOT restricted to own; default (own=true) = OFF
  return (
    <button
      onClick={() => setOwn(!own)}
      title={teamOn ? "Showing your whole team — tap to see only your own data"
                    : "Showing only your data — tap to view your whole team"}
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 6, padding: '7px 14px', fontSize: 12.5,
        fontWeight: 700, cursor: 'pointer', borderRadius: 9, whiteSpace: 'nowrap', transition: 'all .12s',
        border: `1px solid ${teamOn ? '#2f6bff' : 'rgba(120,130,150,0.35)'}`,
        background: teamOn ? '#2f6bff' : 'transparent',
        color: teamOn ? '#fff' : '#8b96a8',
      }}>
      👥 My team{teamOn ? ' ✓' : ''}
    </button>
  );
}

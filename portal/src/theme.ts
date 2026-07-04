// Clean Modern theme tokens (Portal 1)
export const TH = {
  bg: '#0f1419', bg2: '#0a0d12', panel: '#161c24', panel2: '#1a2129',
  border: '#232d3a', border2: '#2f3a48',
  text: '#e8edf2', muted: '#7b8794', dim: '#5a6470',
  accent: '#3ad29f', accent2: '#2bb88a', accentGrad: 'linear-gradient(135deg,#3ad29f,#2563eb)',
  pos: '#3ad29f', neg: '#f0556a', gold: '#F8500A',
  radius: 14, radiusSm: 10,
};
export const fmtMoney = (n: number) => '$' + (n || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
export const fmtNum = (n: number) => (n || 0).toLocaleString();

// Country dial codes + per-country mobile validation for the registration wizard.
//   len    = national mobile digit count (WITHOUT the leading trunk 0)
//   prefix = required leading digit of the national mobile number (optional)
//   ex     = placeholder/example shown in the input
//   pre    = common 2-3 digit mobile prefixes shown as a hint
export interface Country { iso: string; name: string; dial: string; len?: number; prefix?: string; ex?: string; pre?: string; }

export const COUNTRIES: Country[] = [
  { iso: 'IQ', name: 'Iraq', dial: '+964', len: 10, prefix: '7', ex: '770 123 4567', pre: '770 · 771 · 780 · 781 · 750' },
  { iso: 'SA', name: 'Saudi Arabia', dial: '+966', len: 9, prefix: '5', ex: '50 123 4567', pre: '50 · 53 · 54 · 55 · 56 · 59' },
  { iso: 'AE', name: 'United Arab Emirates', dial: '+971', len: 9, prefix: '5', ex: '55 123 4567', pre: '50 · 52 · 54 · 55 · 56 · 58' },
  { iso: 'KW', name: 'Kuwait', dial: '+965', len: 8, ex: '5012 3456', pre: '5 · 6 · 9' },
  { iso: 'QA', name: 'Qatar', dial: '+974', len: 8, ex: '3312 3456', pre: '3 · 5 · 6 · 7' },
  { iso: 'BH', name: 'Bahrain', dial: '+973', len: 8, ex: '3612 3456', pre: '3 · 6' },
  { iso: 'OM', name: 'Oman', dial: '+968', len: 8, ex: '9212 3456', pre: '7 · 9' },
  { iso: 'JO', name: 'Jordan', dial: '+962', len: 9, prefix: '7', ex: '79 012 3456', pre: '77 · 78 · 79' },
  { iso: 'LB', name: 'Lebanon', dial: '+961', len: 8, ex: '71 123 456', pre: '3 · 70 · 71 · 76 · 78 · 81' },
  { iso: 'SY', name: 'Syria', dial: '+963', len: 9, prefix: '9', ex: '944 567 890', pre: '93 · 94 · 95 · 96 · 98 · 99' },
  { iso: 'PS', name: 'Palestine', dial: '+970', len: 9, prefix: '5', ex: '59 123 4567', pre: '56 · 59' },
  { iso: 'YE', name: 'Yemen', dial: '+967', len: 9, ex: '712 345 678', pre: '70 · 71 · 73 · 77 · 78' },
  { iso: 'EG', name: 'Egypt', dial: '+20', len: 10, prefix: '1', ex: '10 1234 5678', pre: '10 · 11 · 12 · 15' },
  { iso: 'TR', name: 'Turkey', dial: '+90', len: 10, prefix: '5', ex: '532 123 4567', pre: '50 · 53 · 54 · 55' },
  { iso: 'IR', name: 'Iran', dial: '+98', len: 10, prefix: '9', ex: '912 345 6789', pre: '90 · 91 · 92 · 93' },
  { iso: 'US', name: 'United States', dial: '+1', len: 10, ex: '201 555 0123' },
  { iso: 'GB', name: 'United Kingdom', dial: '+44', len: 10, ex: '7400 123456', pre: '74 · 75 · 77 · 78 · 79' },
  { iso: 'CA', name: 'Canada', dial: '+1', len: 10, ex: '204 555 0123' },
  { iso: 'DE', name: 'Germany', dial: '+49', ex: '151 2345678', pre: '15 · 16 · 17' },
  { iso: 'FR', name: 'France', dial: '+33', len: 9, prefix: '6', ex: '6 12 34 56 78', pre: '6 · 7' },
  { iso: 'NL', name: 'Netherlands', dial: '+31', len: 9, prefix: '6', ex: '6 1234 5678', pre: '6' },
  { iso: 'SE', name: 'Sweden', dial: '+46', ex: '70 123 4567', pre: '70 · 72 · 73 · 76' },
  { iso: 'IN', name: 'India', dial: '+91', len: 10, ex: '98765 43210', pre: '6 · 7 · 8 · 9' },
  { iso: 'PK', name: 'Pakistan', dial: '+92', len: 10, prefix: '3', ex: '301 2345678', pre: '30 · 31 · 32 · 33 · 34' },
  { iso: 'BD', name: 'Bangladesh', dial: '+880', len: 10, prefix: '1', ex: '1812 345678', pre: '13 · 14 · 15 · 16 · 17 · 18 · 19' },
  { iso: 'AU', name: 'Australia', dial: '+61', len: 9, prefix: '4', ex: '412 345 678', pre: '4' },
  { iso: 'MY', name: 'Malaysia', dial: '+60', ex: '12 345 6789', pre: '1' },
  { iso: 'ID', name: 'Indonesia', dial: '+62', ex: '812 3456 789', pre: '8' },
  { iso: 'NG', name: 'Nigeria', dial: '+234', len: 10, ex: '802 123 4567', pre: '70 · 80 · 81 · 90 · 91' },
  { iso: 'MA', name: 'Morocco', dial: '+212', len: 9, prefix: '6', ex: '6 12 34 56 78', pre: '6 · 7' },
  { iso: 'DZ', name: 'Algeria', dial: '+213', len: 9, ex: '5 51 23 45 67', pre: '5 · 6 · 7' },
  { iso: 'TN', name: 'Tunisia', dial: '+216', len: 8, ex: '20 123 456', pre: '2 · 4 · 5 · 9' },
];

export const isoFlag = (iso: string) =>
  (iso || '').toUpperCase().replace(/[^A-Z]/g, '').replace(/./g, c => String.fromCodePoint(127397 + c.charCodeAt(0)));

export const byIso = (iso: string): Country | undefined =>
  COUNTRIES.find(c => c.iso === (iso || '').toUpperCase());

// strip a leading trunk 0 (e.g. Iraqi 0770… -> 770…)
export const stripTrunk = (d: string) => (d || '').startsWith('0') ? d.slice(1) : d;

// For DISPLAY: digits only, allow a typed leading 0, cap length (len, or len+1 when a 0 is typed).
export function normalizeNational(raw: string, c?: Country): string {
  const d = (raw || '').replace(/\D/g, '');
  const max = c?.len ? (d.startsWith('0') ? c.len + 1 : c.len) : 15;
  return d.slice(0, max);
}

// Valid? (the typed value may include a leading 0 — we ignore it)
export function validNational(typed: string, c?: Country): boolean {
  const d = stripTrunk((typed || '').replace(/\D/g, ''));
  if (!c) return d.length >= 6;
  if (c.len && d.length !== c.len) return false;
  if (!c.len && d.length < 6) return false;
  if (c.prefix && !d.startsWith(c.prefix)) return false;
  return true;
}

// Full E.164-style number (dial code + national, leading 0 dropped)
export const e164 = (c: Country | undefined, typed: string) =>
  (c?.dial || '') + stripTrunk((typed || '').replace(/\D/g, ''));

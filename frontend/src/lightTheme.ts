// ---------------------------------------------------------------------------
// Runtime light-theme engine.
//
// The CRM hardcodes dark-theme colours in inline styles everywhere — hex,
// rgb()/rgba(), gradients, JS hover handlers (onMouseEnter sets
// el.style.background), SVG fills. Static CSS attribute-selector overrides can
// never cover all of that, so in light mode a MutationObserver rewrites every
// inline style through a colour-mapping pipeline:
//
//   1. exact curated tables (the app's core dark palette -> hand-picked light
//      values), passed in from App.tsx;
//   2. an HSL-based algorithmic fallback for anything not in the tables:
//      dark neutral surfaces -> light surfaces, light text -> ink (keeping the
//      grey hierarchy), bright accents -> readable deep accents, dark tinted
//      panels -> pastel tints. Coloured button/badge backgrounds are kept.
//
// White text on a background that STAYS coloured (solid buttons, gradients) is
// preserved via a nearest-inline-background context check. `.keep-dark`
// subtrees (sidebar / topbar / dashboard KPI row) are skipped entirely.
// Originals are stashed in data-dk* attributes so dark mode restores cleanly.
//
// Idempotency (critical — we observe our own writes): every colour the engine
// emits is remembered in per-role output sets; a token that is already an
// output is never re-mapped, so transform(transform(x)) === transform(x) and
// the observer can never loop.
// ---------------------------------------------------------------------------

type RGBA = { r: number; g: number; b: number; a: number };
type Role = 'text' | 'bg' | 'border';
export type ColorTables = { text: Record<string, string>; bg: Record<string, string>; border: Record<string, string> };

const COLOR_RE = /#[0-9a-fA-F]{3,8}\b|rgba?\(\s*[\d.]+[^)]*\)/g;

function parseColor(tok: string): RGBA | null {
  tok = tok.trim();
  if (tok[0] === '#') {
    let h = tok.slice(1);
    if (h.length === 3 || h.length === 4) h = h.split('').map(c => c + c).join('');
    if (h.length !== 6 && h.length !== 8) return null;
    const n = parseInt(h.slice(0, 6), 16);
    if (isNaN(n)) return null;
    const a = h.length === 8 ? parseInt(h.slice(6, 8), 16) / 255 : 1;
    return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255, a };
  }
  const m = tok.match(/rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*(?:,\s*([\d.]+)\s*)?\)/);
  if (!m) return null;
  return { r: +m[1], g: +m[2], b: +m[3], a: m[4] === undefined ? 1 : +m[4] };
}

function toHsl(c: RGBA): { h: number; s: number; l: number } {
  const r = c.r / 255, g = c.g / 255, b = c.b / 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  const l = (max + min) / 2;
  if (max === min) return { h: 0, s: 0, l };
  const d = max - min;
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
  let h: number;
  if (max === r) h = ((g - b) / d + (g < b ? 6 : 0)) * 60;
  else if (max === g) h = ((b - r) / d + 2) * 60;
  else h = ((r - g) / d + 4) * 60;
  return { h, s, l };
}

function hslToRgbStr(h: number, s: number, l: number, a: number): string {
  h = ((h % 360) + 360) % 360 / 360;
  let r: number, g: number, b: number;
  if (s === 0) { r = g = b = l; }
  else {
    const hue2rgb = (p: number, q: number, t: number) => {
      if (t < 0) t += 1;
      if (t > 1) t -= 1;
      if (t < 1 / 6) return p + (q - p) * 6 * t;
      if (t < 1 / 2) return q;
      if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6;
      return p;
    };
    const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
    const p = 2 * l - q;
    r = hue2rgb(p, q, h + 1 / 3); g = hue2rgb(p, q, h); b = hue2rgb(p, q, h - 1 / 3);
  }
  const R = Math.round(r * 255), G = Math.round(g * 255), B = Math.round(b * 255);
  return a >= 0.999 ? `rgb(${R}, ${G}, ${B})` : `rgba(${R}, ${G}, ${B}, ${+a.toFixed(3)})`;
}

const ckey = (c: RGBA) => `${Math.round(c.r)},${Math.round(c.g)},${Math.round(c.b)},${+c.a.toFixed(3)}`;

// Exact input lookups (normalized) + everything the engine has ever emitted, per role.
const EX: Record<Role, Map<string, string>> = { text: new Map(), bg: new Map(), border: new Map() };
const OUT: Record<Role, Set<string>> = { text: new Set(), bg: new Set(), border: new Set() };
let seeded = false;

function seed(tables: ColorTables) {
  if (seeded) return;
  seeded = true;
  (Object.keys(tables) as Role[]).forEach(role => {
    Object.entries(tables[role]).forEach(([from, to]) => {
      const f = parseColor(from);
      if (f) EX[role].set(ckey(f), to);
      const t = parseColor(to);
      if (t) OUT[role].add(ckey(t));
    });
  });
}

function remember(role: Role, out: string): string {
  const c = parseColor(out);
  if (c) OUT[role].add(ckey(c));
  return out;
}

function mapToken(role: Role, tok: string, coloredCtx: boolean): string | null {
  const c = parseColor(tok);
  if (!c) return null;
  const k = ckey(c);
  if (OUT[role].has(k)) return null;                       // already a light colour we emitted
  const { h, s, l } = toHsl(c);

  if (role === 'text') {
    // white/near-white on a background that stays coloured (button, badge, gradient) stays white
    if (coloredCtx && l >= 0.78 && c.a >= 0.5) return null;
    if (c.a >= 0.999) {
      const exact = EX.text.get(k);
      if (exact) return remember(role, exact);
    }
    if (c.a < 0.999) {
      // translucent white-ish text (rgba(255,255,255,.7) etc.) -> ink with the same alpha
      if (s < 0.3 && l > 0.7) return remember(role, `rgba(28, 36, 52, ${+c.a.toFixed(3)})`);
      return null;
    }
    if (s < 0.28) {                                        // grayscale text hierarchy
      if (l >= 0.82) return remember(role, 'rgb(28, 36, 52)');    // white -> ink
      if (l >= 0.68) return remember(role, 'rgb(61, 71, 87)');
      if (l >= 0.52) return remember(role, 'rgb(91, 100, 114)');
      if (l >= 0.40) return remember(role, 'rgb(106, 115, 130)');
      if (l >= 0.18) return remember(role, 'rgb(144, 153, 168)'); // muted-on-dark -> muted-on-light
      return null;                                                // near-black: deliberate, keep
    }
    if (l > 0.72) return remember(role, hslToRgbStr(h, Math.min(s, 0.9), 0.33, 1));  // pale accent -> deep accent
    if (l > 0.55) return remember(role, hslToRgbStr(h, Math.min(s, 0.8), 0.40, 1));  // bright accent -> readable accent
    if (l > 0.45 && s > 0.55) return remember(role, hslToRgbStr(h, Math.min(s, 0.8), 0.40, 1)); // vivid mid (ambers, greens)
    return null;                                                                     // already deep enough
  }

  if (role === 'bg') {
    if (c.a < 0.95) {
      // translucent white hover tints (built for dark surfaces) -> subtle dark tint;
      // dark/coloured overlays (modal backdrops, rgba badge tints) keep
      if (s < 0.3 && l > 0.7) return remember(role, `rgba(16, 24, 40, ${+Math.min(0.35, c.a * 0.6).toFixed(3)})`);
      return null;
    }
    if (c.a >= 0.999) {
      const exact = EX.bg.get(k);
      if (exact) return remember(role, exact);
    }
    if (s < 0.3) {                                         // neutral dark surfaces -> light surfaces
      if (l >= 0.55) return null;                          // already light
      if (l < 0.09) return remember(role, 'rgb(244, 246, 250)');
      if (l < 0.145) return remember(role, 'rgb(247, 249, 252)');
      if (l < 0.20) return remember(role, 'rgb(255, 255, 255)'); // card level -> white
      if (l < 0.28) return remember(role, 'rgb(242, 244, 248)');
      if (l < 0.38) return remember(role, 'rgb(233, 237, 243)');
      return remember(role, 'rgb(223, 228, 236)');
    }
    if (l < 0.30) return remember(role, hslToRgbStr(h, Math.min(s, 0.55), 0.93, 1)); // dark tinted panel -> pastel
    return null;                                           // coloured buttons/badges keep
  }

  // border
  if (c.a >= 0.999) {
    const exact = EX.border.get(k);
    if (exact) return remember(role, exact);
  }
  if (s < 0.3) {
    if (l >= 0.55) return null;
    if (l < 0.16) return remember(role, 'rgb(227, 231, 238)');
    if (l < 0.30) return remember(role, 'rgb(217, 222, 232)');
    return remember(role, 'rgb(200, 207, 218)');
  }
  if (l > 0.80) return null;
  if (l > 0.62) return remember(role, hslToRgbStr(h, s, 0.45, 1));                   // pale accent border -> deep
  if (l < 0.30) return remember(role, hslToRgbStr(h, Math.min(s, 0.5), 0.78, 1));    // dark tinted border -> pastel
  return null;
}

function roleFor(prop: string): Role | null {
  if (prop === 'color' || prop === 'caret-color' || prop === '-webkit-text-fill-color') return 'text';
  if (prop.startsWith('background')) return 'bg';
  if (prop.includes('border') || prop.startsWith('outline')) return 'border';
  return null;                                             // box-shadow, filter, etc.: keep
}

// Does this background value stay coloured after the transform (so white text
// on it must stay white)? True for saturated mid-lightness solids and for
// gradients with at least one saturated non-dark stop.
function bgStaysColored(bgVal: string): boolean {
  if (!bgVal) return false;
  if (bgVal.includes('gradient')) {
    const toks = bgVal.match(COLOR_RE) || [];
    return toks.some(t => {
      const c = parseColor(t);
      if (!c) return false;
      const { s, l } = toHsl(c);
      return s >= 0.3 && l >= 0.2 && l <= 0.78;
    });
  }
  const m = bgVal.match(COLOR_RE);
  if (!m) return false;
  const c = parseColor(m[0]);
  if (!c || c.a < 0.4) return false;
  const { s, l } = toHsl(c);
  return s >= 0.3 && l >= 0.2 && l <= 0.78;
}

function coloredCtxFor(el: Element): boolean {
  let e: Element | null = el;
  for (let i = 0; e && i < 4; i++) {
    const st = (e as HTMLElement).style;
    if (st) {
      const bg = st.background || st.backgroundColor || st.backgroundImage;
      if (bg) return bgStaysColored(bg);
    }
    e = e.parentElement;
  }
  return false;
}

// A KPI/stat number = big + bold text. In light mode the desk wants EVERY KPI number
// rendered BLACK (not the darkened accent), so detect the signature on the whole style
// block and force near-black for its text colour. Threshold is high enough (>=20px, >=500
// weight) that ordinary 11-14px body text and table cells are never caught.
function isBigBoldNumber(css: string): boolean {
  const fs = css.match(/font-size:\s*(\d+(?:\.\d+)?)px/);
  if (!fs || +fs[1] < 15) return false;             // KPI/stat numbers are 15-34px; body text is 11-14px
  const fw = css.match(/font-weight:\s*(\d+|bold)/);
  if (!fw) return false;
  return fw[1] === 'bold' || +fw[1] >= 500;
}
const INK = 'rgb(11, 14, 20)';

function transformCss(cssText: string, coloredCtx: boolean): string {
  const kpi = isBigBoldNumber(cssText);
  return cssText.split(';').map(decl => {
    const idx = decl.indexOf(':');
    if (idx < 0) return decl;
    const prop = decl.slice(0, idx).trim().toLowerCase();
    const role = roleFor(prop);
    if (!role) return decl;
    const val = decl.slice(idx + 1);
    // KPI numbers: force black (unless the number sits on a coloured surface, where it stays legible via the normal path)
    if (role === 'text' && kpi && !coloredCtx) {
      return decl.slice(0, idx + 1) + val.replace(COLOR_RE, tok => {
        const c = parseColor(tok);
        return c && c.a >= 0.5 ? INK : tok;   // keep translucent underlays; blacken the number itself
      });
    }
    if (role === 'bg' && val.includes('gradient')) {
      // only remap SURFACE gradients (every stop dark); brand/coloured gradients keep
      const toks = val.match(COLOR_RE) || [];
      const allDark = toks.length > 0 && toks.every(t => {
        const c = parseColor(t);
        return !c || toHsl(c).l < 0.35;
      });
      if (!allDark) return decl;
    }
    return decl.slice(0, idx + 1) + val.replace(COLOR_RE, tok => mapToken(role, tok, coloredCtx) ?? tok);
  }).join(';');
}

// SVG fill/stroke presentation attributes (charts, network graphs): only fix
// the invisible case — near-white grayscale drawn for a dark background.
function mapSvgAttr(v: string): string | null {
  const c = parseColor(v);
  if (!c) return null;
  const { s, l } = toHsl(c);
  if (s < 0.15 && l > 0.8) return 'rgb(61, 71, 87)';
  return null;
}

// ---------------------------------------------------------------------------
// Elevation classifier — polish layer. Dark themes separate surfaces with
// borders; light themes need soft shadows. When the engine converts a dark
// panel to a light surface it tags the element so buildLightCss can give it
// depth: 'pop' = floating UI (dropdowns, modals, popovers), 'card' = panels.
// ---------------------------------------------------------------------------
const LIGHT_SURFACE_RE = /background(?:-color)?:\s*(?:rgb\(255, 255, 255\)|#fff\b|#ffffff|#f7f9fc|#f4f6fa|#f2f4f8|rgb\(247, 249, 252\)|rgb\(244, 246, 250\)|rgb\(242, 244, 248\))/i;

function classifyElevation(css: string): 'pop' | 'card' | null {
  if (!LIGHT_SURFACE_RE.test(css)) return null;
  const floating = /position:\s*(fixed|absolute)/.test(css);
  const zm = css.match(/z-index:\s*(\d+)/);
  const rm = css.match(/border-radius:\s*(\d+(?:\.\d+)?)px/);
  const radius = rm ? +rm[1] : 0;
  if (floating && ((zm && +zm[1] >= 5) || radius >= 8)) return 'pop';
  if (radius >= 10 && radius <= 28) return 'card';
  return null;
}

let mo: MutationObserver | null = null;
const xformCache = new Map<string, string>();
const lastOut = new WeakMap<Element, string>();

function processEl(el: Element) {
  if (el.nodeType !== 1 || !el.closest || el.closest('.keep-dark')) return;

  const cur = el.getAttribute('style');
  if (cur) {
    if (lastOut.get(el) !== cur) {
      const ctx = coloredCtxFor(el);
      const cacheKey = (ctx ? '1|' : '0|') + cur;
      let out = xformCache.get(cacheKey);
      if (out === undefined) {
        out = transformCss(cur, ctx);
        if (xformCache.size > 8000) xformCache.clear();
        xformCache.set(cacheKey, out);
      }
      if (out !== cur) {
        if (!el.getAttribute('data-dk')) el.setAttribute('data-dk', cur);
        el.setAttribute('style', out);
        const kind = classifyElevation(out);
        if (kind) el.setAttribute('data-lt', kind);
        else if (el.hasAttribute('data-lt')) el.removeAttribute('data-lt');
      }
      lastOut.set(el, out);
    }
  }

  if (el instanceof SVGElement) {
    for (const attr of ['fill', 'stroke']) {
      const v = el.getAttribute(attr);
      if (v && v !== 'none' && v !== 'currentColor' && !v.startsWith('url')) {
        const mapped = mapSvgAttr(v);
        if (mapped && mapped !== v) {
          if (!el.getAttribute('data-dk-' + attr)) el.setAttribute('data-dk-' + attr, v);
          el.setAttribute(attr, mapped);
        }
      }
    }
  }
}

function walk(root: Element) {
  processEl(root);
  root.querySelectorAll('[style],[fill],[stroke]').forEach(processEl);
}

export function enableLightEngine(tables: ColorTables) {
  seed(tables);
  disableLightEngine(false);
  walk(document.body);
  mo = new MutationObserver(muts => {
    for (const m of muts) {
      if (m.type === 'attributes') processEl(m.target as Element);
      else m.addedNodes.forEach(n => { if (n.nodeType === 1) walk(n as Element); });
    }
  });
  mo.observe(document.body, { subtree: true, childList: true, attributes: true, attributeFilter: ['style', 'fill', 'stroke'] });
}

export function disableLightEngine(restore = true) {
  if (mo) { mo.disconnect(); mo = null; }
  if (!restore) return;
  document.querySelectorAll('[data-dk]').forEach(el => {
    el.setAttribute('style', el.getAttribute('data-dk')!);
    el.removeAttribute('data-dk');
    lastOut.delete(el);
  });
  document.querySelectorAll('[data-lt]').forEach(el => el.removeAttribute('data-lt'));
  ['fill', 'stroke'].forEach(attr => {
    document.querySelectorAll(`[data-dk-${attr}]`).forEach(el => {
      el.setAttribute(attr, el.getAttribute(`data-dk-${attr}`)!);
      el.removeAttribute(`data-dk-${attr}`);
    });
  });
  xformCache.clear();
}

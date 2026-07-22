import React, { useState, useEffect, useMemo } from 'react';
import tnfxLogo from './assets/tnfx-logo.png';
import tnfxMark from './assets/tnfx-mark.png';
import { TNFX_LOGO_DATAURI, TNFX_MARK_DATAURI } from './assets/tnfxBrand';
import { apiGet, apiPost } from './api';
import { qrSVG } from './qrcode';
import { ibT, IB_LANGS, isRTL, Lang, langsForCountry } from './ibI18n';

// compact flag-only language picker — shows the current flag, opens a small menu
function LangPicker({ value, options, onPick }:{ value:Lang; options:any[]; onPick:(l:Lang)=>void }) {
  const [open, setOpen] = useState(false);
  const cur = options.find(o=>o.k===value) || options[0];
  const Flag = ({ f, size=18 }:{ f:string; size?:number }) => f.startsWith('data:')
    ? <img src={f} alt="" style={{ width:size+3, height:(size+3)*0.71, borderRadius:2, display:'block' }} />
    : <span style={{ fontSize:size }}>{f}</span>;
  return (
    <div style={{ position:'relative' }}>
      <button onClick={()=>setOpen(v=>!v)} title="Language" style={{ background:'rgba(255,255,255,0.05)', border:'1px solid rgba(255,255,255,0.16)', borderRadius:9, height:36, width:44, display:'flex', alignItems:'center', justifyContent:'center', cursor:'pointer' }}>
        <Flag f={cur.flag} />
      </button>
      {open && (<>
        <div onClick={()=>setOpen(false)} style={{ position:'fixed', inset:0, zIndex:190 }} />
        <div style={{ position:'absolute', right:0, top:42, background:C.card, border:`1px solid ${C.border}`, borderRadius:11, boxShadow:'0 12px 36px rgba(16,24,40,0.18)', zIndex:200, overflow:'hidden', minWidth:150 }}>
          {options.map(o=>(
            <div key={o.k} onClick={()=>{ onPick(o.k); setOpen(false); }} style={{ display:'flex', alignItems:'center', gap:9, padding:'9px 13px', cursor:'pointer', background:o.k===value?C.blueBg:'transparent' }}
              onMouseEnter={e=>(e.currentTarget.style.background=C.soft||C.card2)} onMouseLeave={e=>(e.currentTarget.style.background=o.k===value?C.blueBg:'transparent')}>
              <Flag f={o.flag} size={16} /><span style={{ fontSize:12.5, color:C.text, fontWeight:o.k===value?700:500 }}>{o.label}</span>
            </div>
          ))}
        </div>
      </>)}
    </div>
  );
}

// live countdown — ticks each second from a seconds value, shows "Xd Yh Zm Ws"
function Countdown({ seconds, color }:{ seconds:number; color:string }) {
  const [s, setS] = useState(seconds);
  useEffect(() => { setS(seconds); }, [seconds]);
  useEffect(() => {
    if (s <= 0) return;
    const t = setInterval(() => setS(x => Math.max(0, x - 1)), 1000);
    return () => clearInterval(t);
  }, [s]);
  const d = Math.floor(s/86400), h = Math.floor((s%86400)/3600), m = Math.floor((s%3600)/60), sec = s%60;
  return <span style={{ color, fontWeight:700, fontVariantNumeric:'tabular-nums' }}>
    {s<=0 ? 'expired' : `${d>0?d+'d ':''}${h}h ${m}m ${String(sec).padStart(2,'0')}s`}</span>;
}

// ── formatters ──────────────────────────────────────────────────────────────
const usd  = (n:number) => '$' + Math.round(n||0).toLocaleString('en-GB');
const GOLD_RATE: any = { 5: '$5', 6: '$6', 7: '$7', 8: '$8', 9: '$9', 10: '$10' };  // XAUUSD/major $ per lot BY LEVEL — ladder linearised Jul 9 2026 (was L6=$7/L7=$7.50); keep in sync with commission_rules
const usdK = (n:number) => Math.abs(n||0) >= 1000 ? '$' + ((n||0)/1000).toFixed((Math.abs(n||0)>=100000)?0:1) + 'K' : '$' + Math.round(n||0).toLocaleString('en-GB');
const num  = (n:number) => Math.round(n||0).toLocaleString('en-GB');
const initialsOf = (s:string) => (s||'').split(/\s+/).filter(Boolean).slice(0,2).map(x=>x[0]||'').join('').toUpperCase() || '—';

// ── light theme ─────────────────────────────────────────────────────────────
const C = {
  bg:'#f4f6fa', card:'#ffffff', card2:'#f7f9fc', soft:'#fbfcfe',
  border:'#e7ebf2', borderH:'#dde3ec',
  text:'#101828', text2:'#5a6b85', text3:'#8c99ad',
  blue:'#2f6bff',   blueBg:'#eef3ff',
  green:'#0fae7a',  greenBg:'#e6f8f1',
  red:'#e5484d',    redBg:'#fdecec',
  amber:'#d98a00',  amberBg:'#fcf3e0',
  purple:'#6d5cff', purpleBg:'#eeecff',
};
const SANS = "'Inter','Plus Jakarta Sans',-apple-system,'Segoe UI',sans-serif";

// tier ladder — matches backend TIER_NAMES (5..10). `req` = what's needed to REACH that tier.
// req = the desk sheet (Jul 13 2026): deposit $, lots MONTHLY AVERAGE, funded accounts.
// These are only the FALLBACK — the live values come from ib_tier_requirements via R.tier_next.
const BTIERS = [
  { level:5,  name:'Bronze',    color:'#b06f33', bg:'#f6ece1', icon:'🥉', req:{ ftd:0,   lots:0,    deposit:0 } },
  { level:6,  name:'Silver',    color:'#7a8696', bg:'#eef1f5', icon:'🥈', req:{ ftd:5,   lots:20,   deposit:1500 } },
  { level:7,  name:'Golden',    color:'#c39a1f', bg:'#fbf2d6', icon:'🥇', req:{ ftd:15,  lots:50,   deposit:10000 } },
  { level:8,  name:'Diamond',   color:'#2f9bd0', bg:'#e6f4fb', icon:'💎', req:{ ftd:40,  lots:200,  deposit:100000 } },
  { level:9,  name:'Legendary', color:'#6d5cff', bg:'#eeecff', icon:'⭐', req:{ ftd:100, lots:1000, deposit:300000 } },
  { level:10, name:'Prime IB',  color:'#e5484d', bg:'#fdecec', icon:'👑', req:{ ftd:200, lots:2500, deposit:500000 } },
];
const bt     = (l:number) => BTIERS.find(t=>t.level===l) || BTIERS[0];
const btNext = (l:number) => BTIERS.find(t=>t.level===l+1);

const PLATFORM_COLORS:any = { facebook:'#1877f2', instagram:'#e1306c', tiktok:'#111', snapchat:'#caa800', google:'#4285f4', whatsapp:'#25d366', direct:'#5a6b85', '':'#5a6b85' };

// ── shared styles ───────────────────────────────────────────────────────────
const S:any = {
  page:   { padding:'20px 22px', maxWidth:1360, margin:'0 auto' },
  card:   { background:C.card, border:`1px solid ${C.border}`, borderRadius:14, boxShadow:'0 1px 2px rgba(16,24,40,0.05)' },
  th:     { padding:'11px 14px', textAlign:'left', fontWeight:600, fontSize:11, textTransform:'uppercase', letterSpacing:'.04em', borderBottom:`1px solid ${C.border}`, whiteSpace:'nowrap', background:C.card2, position:'sticky' as any, top:0 },
  td:     { padding:'11px 14px', borderBottom:`1px solid ${C.border}`, fontSize:13, whiteSpace:'nowrap' as any },
  input:  { padding:'9px 12px', borderRadius:9, fontSize:13, outline:'none', fontFamily:SANS },
  secLbl: { fontSize:14, fontWeight:700, color:C.text, marginBottom:13 },
  btnPri: { padding:'9px 16px', background:C.blue, color:'#fff', border:'none', borderRadius:9, fontSize:12.5, fontWeight:600, cursor:'pointer' },
  btnGhost:{ padding:'9px 14px', background:C.card, color:C.blue, border:`1px solid ${C.borderH}`, borderRadius:9, fontSize:12.5, fontWeight:600, cursor:'pointer' },
};
const badge = (bg:string, col:string):React.CSSProperties => ({ fontSize:11, padding:'3px 9px', borderRadius:99, fontWeight:600, background:bg, color:col, display:'inline-block', whiteSpace:'nowrap' });

// ── marketing banners (Banners tab) ──────────────────────────────────────────
// REAL TNFX creative language (taken from the actual TNFX social banners, Jul 2026):
//   · deep charcoal cinematic background with a soft radial glow — never flat, never white
//   · GOLD light-rays / particles sweeping the frame (the luxury signature)
//   · Arabic-first bold headline in ORANGE, second line in WHITE (EN variant available)
//   · logo lockup top-left · parallelogram CTA in the hot orange gradient
//   · compliance strip at the bottom: مرخصة من قبل FSA ◆ إن التداول ينطوي على مخاطر
//   · thin orange gradient bar along the very bottom edge of every banner
const TNFX_O1 = '#ff4700', TNFX_O2 = '#ff9100', TNFX_ORANGE = '#ff6a00';
const TNFX_G1 = '#8a6420', TNFX_G2 = '#e8b84b', TNFX_G3 = '#f6dfa0';   // brand golds (trophy/globe)
const BTHEMES: any = {
  dark:   { label:'Dark',   accent:'url(#og)', accentFlat:TNFX_ORANGE, sub:'#c9ced8', text:'#ffffff',
            ctaText:'#111111', ctaFill:'url(#og)', logoF:'', markF:'url(#fg)', markOp:0.05, chip:'#17181d', rays:0.5 },
  // light studio look — BLACK type on white (desk rule Jul 15), orange kept only for the CTA + accents
  white:  { label:'White',  accent:'#141414', accentFlat:TNFX_ORANGE, sub:'#3a3d42', text:'#141414',
            ctaText:'#ffffff', ctaFill:'url(#og)', logoF:'', markF:'', markOp:0.08, chip:'#ececec', rays:0.3 },
  // orange colourway uses BLACK type (desk rule Jul 14)
  orange: { label:'Orange', accent:'#141414', accentFlat:'#141414', sub:'#4d2000', text:'#141414',
            ctaText:'#ffffff', ctaFill:'#141414', logoF:'url(#fb)', markF:'url(#fb)', markOp:0.08, chip:TNFX_ORANGE, rays:0 },
};
// Arabic-FIRST campaigns (the real ads are Arabic); each also carries the EN variant.
// arT = orange headline line · arS = white second line (and vice-versa for EN).
// hero = the GIANT centre value (the real ads' $1000 / 100% signature) · heroSub/arHS = line under it
const BANNERS = [
  { key:'zero',     kicker:'ZERO ACCOUNT',    title:'ZERO SPREAD',      sub:'Spreads from 0.0 pips on majors',
    arK:'حساب زيرو', arT:'سبريد صفر', arS:'فروقات من 0.0 نقطة على الأزواج الرئيسية',
    hero:'0.0', heroSub:'PIPS SPREAD', arHS:'نقطة سبريد' },
  { key:'ultra',    kicker:'ULTRA ACCOUNT',   title:'MAXIMUM LEVERAGE', sub:'Maximum buying power',
    arK:'حساب ألترا', arT:'أعلى رافعة مالية', arS:'أقصى قوة شرائية لصفقاتك',
    hero:'1:3000', heroSub:'ULTRA ACCOUNT LEVERAGE', arHS:'رافعة حساب ألترا' },
  { key:'bonus',    kicker:'NEW CLIENTS',     title:'WELCOME BONUS',    sub:'Start trading with bonus funds',
    arK:'للعملاء الجدد', arT:'بونص ترحيبي', arS:'ابدأ التداول برصيد إضافي',
    hero:'100%', heroSub:'DEPOSIT BONUS', arHS:'بونص على الإيداع' },
  { key:'autoch',   kicker:'PRO SIGNALS',     title:'AUTOCHARTIST',     sub:'Pro signals & market scanner',
    arK:'إشارات احترافية', arT:'أوتوشارتست', arS:'إشارات وتحليلات احترافية للسوق',
    hero:'FREE', heroSub:'FOR ALL TNFX CLIENTS', arHS:'مجاناً لعملاء TNFX' },
  { key:'ib10',     kicker:'PARTNER PROGRAM', title:'BECOME A PARTNER', sub:'Grow your income as a TNFX IB',
    arK:'برنامج الشركاء', arT:'كن شريك TNFX', arS:'نمِّ دخلك كوسيط معرف معنا',
    hero:'$10', heroSub:'COMMISSION PER LOT', arHS:'عمولة عن كل لوت' },
  { key:'instr',    kicker:'ONE ACCOUNT',     title:'ALL THE MARKETS',  sub:'FX · metals · indices · stocks · crypto',
    arK:'حساب واحد', arT:'كل الأسواق', arS:'عملات · معادن · مؤشرات · أسهم · كريبتو',
    hero:'1000+', heroSub:'TRADING INSTRUMENTS', arHS:'أداة تداول' },
  { key:'gold',     kicker:'XAU/USD',         title:'TRADE GOLD',       sub:'Deep liquidity · fast execution',
    arK:'الذهب XAU/USD', arT:'تداول الذهب', arS:'سيولة عميقة وتنفيذ فوري',
    hero:'GOLD', heroSub:'XAU/USD · 24/5', arHS:'الذهب على مدار الساعة', gold:true },
  { key:'equities', kicker:'GLOBAL STOCKS',   title:'TRADE EQUITIES',   sub:'Apple · Tesla · Nvidia · Amazon',
    arK:'أسهم عالمية', arT:'تداول الأسهم', arS:'آبل · تسلا · نفيديا · أمازون',
    hero:'STOCKS', heroSub:'AAPL · TSLA · NVDA · AMZN', arHS:'أشهر الأسهم العالمية' },
  { key:'oil',      kicker:'ENERGY CFDs',     title:'TRADE OIL',        sub:'WTI & Brent · long or short',
    arK:'عقود الطاقة', arT:'تداول النفط', arS:'برنت و WTI · شراءً أو بيعاً',
    hero:'OIL', heroSub:'WTI & BRENT', arHS:'برنت و WTI' },
  { key:'copytr',   kicker:'COPY TRADING',    title:'COPY THE PROS',    sub:'Follow verified top traders',
    arK:'كوبي تريدنق', arT:'انسخ المحترفين', arS:'تابع أفضل المتداولين الموثقين',
    hero:'COPY', heroSub:'TOP VERIFIED TRADERS', arHS:'أفضل المتداولين الموثقين' },
  { key:'fastpay',  kicker:'FUNDING',         title:'INSTANT DEPOSITS', sub:'Local payment methods · fast withdrawals',
    arK:'الإيداع والسحب', arT:'إيداع فوري', arS:'وسائل دفع محلية وسحب سريع',
    hero:'INSTANT', heroSub:'DEPOSITS & WITHDRAWALS', arHS:'إيداع وسحب فوري' },
  { key:'mt45',     kicker:'PLATFORMS',       title:'TRADE ANYWHERE',   sub:'Desktop · web · mobile',
    arK:'منصات التداول', arT:'تداول أينما كنت', arS:'كمبيوتر · ويب · موبايل',
    hero:'MT4·MT5', heroSub:'ALL PLATFORMS', arHS:'جميع المنصات' },
];
// the 20 standard placements (IAB display + social)
const BSIZES = [
  { w:728,  h:90,   label:'Leaderboard',       cat:'horizontal' },
  { w:970,  h:90,   label:'Large leaderboard', cat:'horizontal' },
  { w:970,  h:250,  label:'Billboard',         cat:'horizontal' },
  { w:468,  h:60,   label:'Banner',            cat:'horizontal' },
  { w:320,  h:50,   label:'Mobile banner',     cat:'horizontal' },
  { w:320,  h:100,  label:'Large mobile',      cat:'horizontal' },
  { w:234,  h:60,   label:'Half banner',       cat:'horizontal' },
  { w:120,  h:600,  label:'Skyscraper',        cat:'vertical' },
  { w:160,  h:600,  label:'Wide skyscraper',   cat:'vertical' },
  { w:300,  h:600,  label:'Half page',         cat:'vertical' },
  { w:300,  h:1050, label:'Portrait',          cat:'vertical' },
  { w:120,  h:240,  label:'Vertical banner',   cat:'vertical' },
  { w:300,  h:250,  label:'Medium rectangle',  cat:'square' },
  { w:336,  h:280,  label:'Large rectangle',   cat:'square' },
  { w:250,  h:250,  label:'Square',            cat:'square' },
  { w:200,  h:200,  label:'Small square',      cat:'square' },
  { w:125,  h:125,  label:'Button',            cat:'square' },
  { w:1080, h:1080, label:'Social post',       cat:'social' },
  { w:1200, h:628,  label:'Social landscape',  cat:'social' },
  { w:1080, h:1920, label:'Story',             cat:'social' },
];

// ── text measurement: size every text element to ACTUALLY FIT (no overflow / no cutoff).
// A shared offscreen canvas measures real glyph widths (incl. Arabic ligatures) so we never
// guess with a fixed glyph-factor again. Font size scales linearly with width, so the exact
// fitting size = capFont clamped by (maxWidth / widthAtRef * refSize).
const _measCanvas: HTMLCanvasElement | null =
  typeof document !== 'undefined' ? document.createElement('canvas') : null;
const _measCtx: CanvasRenderingContext2D | null = _measCanvas ? _measCanvas.getContext('2d') : null;
function textWidth(txt:string, px:number, family:string, weight:string|number='400', italic=false):number {
  if (_measCtx) { _measCtx.font = `${italic?'italic ':''}${weight} ${px}px ${family}`; return _measCtx.measureText(String(txt)).width; }
  return String(txt).length * px * 0.55;   // SSR fallback only
}
function fitFont(txt:string, family:string, weight:string|number, italic:boolean, maxW:number, cap:number, floor=6):number {
  const ref = textWidth(txt, 100, family, weight, italic);
  return ref <= 0 ? cap : Math.max(floor, Math.min(cap, 100 * maxW / ref));
}
// balanced word-wrap into up to maxLines lines, each fitting maxW; picks the line count that
// yields the LARGEST uniform font (fewer lines preferred on ties). Returns {lines, fs}.
function fitLines(txt:string, family:string, weight:string|number, italic:boolean, maxW:number, cap:number, maxLines:number) {
  const words = String(txt).split(/\s+/).filter(Boolean);
  if (words.length <= 1) return { lines:[txt], fs: fitFont(txt, family, weight, italic, maxW, cap) };
  let best:{lines:string[],fs:number} | null = null;
  for (let L=1; L<=Math.min(maxLines, words.length); L++) {
    // greedy near-equal split by character length
    const target = Math.ceil(words.join(' ').length / L);
    const lines:string[] = []; let cur = '';
    for (const wd of words) {
      if (cur && (cur.length + 1 + wd.length) > target && lines.length < L-1) { lines.push(cur); cur = wd; }
      else cur = cur ? cur+' '+wd : wd;
    }
    if (cur) lines.push(cur);
    const fs = Math.min(cap, ...lines.map(ln => fitFont(ln, family, weight, italic, maxW, cap*4)));
    if (!best || fs > best.fs + 0.6) best = { lines, fs };
  }
  return best!;
}

// bannerSVG — TNFX premium banner generator (redesigned Jul 2026). Self-contained SVG per IB
// (referral code baked in). Design system: deep navy-charcoal gradient · directional warm glow ·
// bold ghosted bull watermark · upward market line-chart ribbon (not scattered particles) ·
// GOLD hero value as the focal point · ORANGE reserved for the CTA pill (arrow) · gold divider /
// corner bracket accents. Four adaptive layouts: wide billboard (2-column), short bar, vertical
// skyscraper, and centred card/social — each measured-to-fit so nothing overflows at any size.
function bannerSVG(c:any, themeKey:string, w:number, h:number, code:string,
                   logoUri=TNFX_LOGO_DATAURI, markUri=TNFX_MARK_DATAURI, lang='ar') {
  const ar = lang === 'ar';
  const esc = (s:string) => String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;');
  const m = Math.min(w,h), ratio = w/h;
  const clamp = (v:number, lo:number, hi:number) => Math.max(lo, Math.min(hi, v));
  const dark = themeKey==='dark', white = themeKey==='white', orange = themeKey==='orange';
  // Arabic must NOT be Arial Black (breaks shaping); no quotes in font-family (breaks XML).
  const HEAD = ar ? 'Tahoma, Segoe UI, Arial, sans-serif' : 'Arial Black, Arial Narrow, sans-serif';
  const BODY = ar ? 'Tahoma, Segoe UI, Arial, sans-serif' : 'Arial, Helvetica, sans-serif';
  const NUM  = 'Arial Black, Arial, sans-serif';

  const T:any = dark ? { text:'#ffffff', sub:'#9aa6ba', kick:'#ff9130', hero:'#ffffff', ctaText:'#111', ctaFill:'url(#og)',
        foot:'#8b94a5', markF:'', markOp:0.06, bg:'url(#bgD)', line:'#ff7a1a', logoF:'' }
    : white ? { text:'#131722', sub:'#5b6472', kick:'#e06a00', hero:'#131722', ctaText:'#fff', ctaFill:'url(#og)',
        foot:'#8791a0', markF:'url(#fdk)', markOp:0.05, bg:'url(#bgW)', line:'#e06a00', logoF:'' }
    : { text:'#141414', sub:'#5a2600', kick:'#141414', hero:'#141414', ctaText:'#fff', ctaFill:'#141414',
        foot:'#5a2600', markF:'url(#fdk)', markOp:0.10, bg:'url(#bgO)', line:'#141414', logoF:'url(#fdk)' };

  const kicker = ar ? c.arK : c.kicker, title = ar ? c.arT : c.title, sub = ar ? c.arS : c.sub;
  const heroSub = ar ? (c.arHS||'') : (c.heroSub||'');
  const ctaTxt = ar ? 'افتح حسابك الآن' : 'OPEN ACCOUNT';
  const site = 'TNFX.co';
  const P:string[] = [];
  const LOGO_AR = 4.473;

  const logo = (x:number, y:number, lh:number) =>
    `<image href="${logoUri}" x="${x}" y="${y}" height="${lh}" width="${lh*LOGO_AR}" preserveAspectRatio="xMinYMid meet"${T.logoF?` filter="${T.logoF}"`:''}/>`;
  const T2 = (txt:string, x:number, y:number, fs:number, anchor:string, fill:string, fam:string, weight:number) =>
    `<text x="${x}" y="${y}" text-anchor="${anchor}" font-family="${fam}" font-weight="${weight}" font-size="${fs}" fill="${fill}">${esc(txt)}</text>`;
  const KTRACK = 0.14;   // kicker letter-spacing (EN only)
  // size the kicker so it FITS INCLUDING letter-spacing (else long EN kickers overflow/overlap)
  const fitKick = (maxW:number, cap:number) => {
    const t = String(kicker).toUpperCase();
    if (ar) return fitFont(t, BODY, 800, false, maxW, cap);
    const w100 = textWidth(t, 100, BODY, 800) + Math.max(0, t.length-1)*100*KTRACK;
    return Math.max(6, Math.min(cap, w100>0 ? 100*maxW/w100 : cap));
  };
  const kickerEl = (x:number, y:number, fs:number, anchor:string) => {
    const tr = ar ? '' : ` letter-spacing="${(fs*KTRACK).toFixed(2)}"`;
    return `<text x="${x}" y="${y}" text-anchor="${anchor}" font-family="${BODY}" font-weight="800" font-size="${fs}"${tr} fill="${T.kick}">${esc(String(kicker).toUpperCase())}</text>`;
  };
  const ctaW = (fs:number) => { const tw = textWidth(ctaTxt, fs, HEAD, 900, false); return tw + fs*1.05*2 + fs*0.5 + fs*0.9; };
  const ctaEl = (x:number, y:number, fs:number, anchor:string) => {
    const tw = textWidth(ctaTxt, fs, HEAD, 900, false), padX = fs*1.05, arrow = fs*0.9, gap = fs*0.5;
    const bw = tw+padX*2+gap+arrow, bh = fs*2.05, r = bh*0.5;
    const bx = anchor==='middle' ? x-bw/2 : anchor==='end' ? x-bw : x;
    const arX = ar ? bx+padX : bx+bw-padX-arrow;
    const txX = ar ? bx+bw-padX : bx+padX;
    const ap = ar
      ? `M ${arX+arrow} ${y+bh*0.32} L ${arX} ${y+bh*0.5} L ${arX+arrow} ${y+bh*0.68} M ${arX} ${y+bh*0.5} L ${arX+arrow} ${y+bh*0.5}`
      : `M ${arX} ${y+bh*0.32} L ${arX+arrow} ${y+bh*0.5} L ${arX} ${y+bh*0.68} M ${arX} ${y+bh*0.5} L ${arX+arrow} ${y+bh*0.5}`;
    return `<rect x="${bx}" y="${y}" width="${bw}" height="${bh}" rx="${r}" fill="${T.ctaFill}"/>`
      + `<rect x="${bx}" y="${y}" width="${bw}" height="${bh*0.5}" rx="${r}" fill="#ffffff" opacity="0.14"/>`
      + `<text x="${txX}" y="${y+bh*0.68}" text-anchor="${ar?'end':'start'}" font-family="${HEAD}" font-weight="900" font-size="${fs}" fill="${T.ctaText}">${esc(ctaTxt)}</text>`
      + `<path d="${ap}" stroke="${T.ctaText}" stroke-width="${fs*0.16}" fill="none" stroke-linecap="round" stroke-linejoin="round"/>`;
  };
  const heroEl = (cx:number, baseY:number, maxW:number, cap:number, anchor='middle') => {
    if (!c.hero) return null;
    const hf = fitFont(String(c.hero), NUM, 900, false, maxW, cap);
    const hw = textWidth(String(c.hero), hf, NUM, 900);
    let o = `<ellipse cx="${cx}" cy="${baseY-hf*0.34}" rx="${Math.min(maxW*0.7, hw*0.72)}" ry="${hf*0.7}" fill="url(#glow)"/>`;
    o += `<text x="${cx}" y="${baseY}" text-anchor="${anchor}" font-family="${NUM}" font-weight="900" font-size="${hf}" fill="${T.hero}">${esc(c.hero)}</text>`;
    if (heroSub) { const sf = clamp(hf*0.17, 9, m*0.04);
      o += `<text x="${cx}" y="${baseY+hf*0.30}" text-anchor="${anchor}" font-family="${BODY}" font-weight="700" font-size="${sf}"${ar?'':' letter-spacing="1.5"'} fill="${T.sub}">${esc(heroSub)}</text>`; }
    return { svg:o, w:hw, fs:hf };
  };
  const chartRibbon = () => {
    if (orange) return '';
    const n = 10, pad = w*0.02, top = h*0.52, bot = h*0.99;
    const seed = (i:number) => (((i+2)*2654435761)>>>0)%1000/1000;
    const pts:number[][] = [];
    for (let i=0;i<=n;i++){ const x = pad+(w-2*pad)*i/n; const up = i/n; const jit = (seed(i)-0.5)*0.16;
      const y = bot-(bot-top)*(0.15+up*0.8+jit); pts.push([x, Math.max(top, Math.min(bot, y))]); }
    const line = pts.map((p,i)=>(i?'L':'M')+p[0].toFixed(1)+' '+p[1].toFixed(1)).join(' ');
    const area = line+` L ${w-pad} ${h} L ${pad} ${h} Z`;
    const col = white ? '#e06a00' : '#ff7a1a', op = white ? 0.13 : 0.16;
    return `<path d="${area}" fill="url(#chart)" opacity="${white?0.5:0.6}"/><path d="${line}" fill="none" stroke="${col}" stroke-width="${Math.max(1.2, m*0.006)}" opacity="${op*1.6}" stroke-linejoin="round"/>`;
  };
  const bullMark = (x:number, y:number, size:number) =>
    `<image href="${markUri}" x="${x}" y="${y}" width="${size}" height="${size}" opacity="${T.markOp}" filter="${T.markF}"/>`;
  const bracket = (x:number, y:number, len:number, sw:number) =>
    orange ? '' : `<path d="M ${x} ${y+len} L ${x} ${y} L ${x+len} ${y}" stroke="${T.line}" stroke-width="${sw}" fill="none" opacity="0.9"/>`;

  P.push(`<defs>
    <linearGradient id="bgD" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#0e1420"/><stop offset="0.5" stop-color="#141c2b"/><stop offset="1" stop-color="#090d15"/></linearGradient>
    <linearGradient id="bgW" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#ffffff"/><stop offset="0.55" stop-color="#f4f6f9"/><stop offset="1" stop-color="#e7ebf1"/></linearGradient>
    <linearGradient id="bgO" x1="0" y1="0" x2="0.9" y2="1"><stop offset="0" stop-color="#ff6a00"/><stop offset="1" stop-color="#ff9200"/></linearGradient>
    <linearGradient id="og" x1="0" y1="0" x2="1" y2="0.4"><stop offset="0" stop-color="${TNFX_O1}"/><stop offset="1" stop-color="${TNFX_O2}"/></linearGradient>
    <linearGradient id="gg" x1="0" y1="1" x2="0.3" y2="0"><stop offset="0" stop-color="${TNFX_G1}"/><stop offset="0.45" stop-color="${TNFX_G2}"/><stop offset="1" stop-color="${TNFX_G3}"/></linearGradient>
    <radialGradient id="glow" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stop-color="#ff8a2a" stop-opacity="0.30"/><stop offset="1" stop-color="#ff8a2a" stop-opacity="0"/></radialGradient>
    <radialGradient id="glowBig" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stop-color="#ff7a00" stop-opacity="${dark?0.32:0.12}"/><stop offset="0.6" stop-color="#ff9500" stop-opacity="${dark?0.1:0.05}"/><stop offset="1" stop-color="#000" stop-opacity="0"/></radialGradient>
    <linearGradient id="chart" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${white?'#e06a00':'#ff7a1a'}" stop-opacity="0.20"/><stop offset="1" stop-color="${white?'#e06a00':'#ff7a1a'}" stop-opacity="0"/></linearGradient>
    <radialGradient id="vig" cx="0.5" cy="0.42" r="0.75"><stop offset="0.55" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity="0.34"/></radialGradient>
    <filter id="fmk"><feColorMatrix type="matrix" values="0 0 0 0 0.91  0 0 0 0 0.72  0 0 0 0 0.29  0 0 0 1 0"/></filter>
    <filter id="fdk"><feColorMatrix type="matrix" values="0 0 0 0 0.07  0 0 0 0 0.07  0 0 0 0 0.08  0 0 0 1 0"/></filter>
  </defs>`);
  P.push(`<rect width="${w}" height="${h}" fill="${T.bg}"/>`);
  const glowX = ar ? w*0.22 : w*0.8;
  P.push(`<ellipse cx="${glowX}" cy="${h*0.26}" rx="${w*0.6}" ry="${h*0.7}" fill="url(#glowBig)"/>`);
  P.push(chartRibbon());
  if (dark) P.push(`<rect width="${w}" height="${h}" fill="url(#vig)"/>`);
  if (white) P.push(`<rect x="0.5" y="0.5" width="${w-1}" height="${h-1}" fill="none" stroke="#00000014"/>`);

  if (ratio>=1.9 && h>=140) {
    // ── WIDE BILLBOARD ── text column (reading side) + giant gold hero (far side) + divider
    const pad = clamp(h*0.15,16,56), lh = clamp(h*0.17,24,60), lw = lh*LOGO_AR;
    const heroW = w*0.34, gap = pad*0.8;
    const heroCx = ar ? pad+heroW/2 : w-pad-heroW/2;
    const divX = ar ? pad+heroW+gap : w-pad-heroW-gap;
    const tx0 = ar ? divX+gap : pad, tx1 = ar ? w-pad : divX-gap, tW = Math.max(30, tx1-tx0);
    const anchor = ar ? 'end' : 'start', tx = ar ? tx1 : tx0;
    P.push(bullMark(ar ? -h*0.28 : w-h*0.98, h*0.02, h*1.08));
    P.push(logo(ar ? tx1-lw : tx0, pad, lh));
    P.push(`<line x1="${divX}" y1="${h*0.26}" x2="${divX}" y2="${h*0.74}" stroke="#ff7a1a" stroke-width="${Math.max(1.4,w*0.0015)}" opacity="0.55"/>`);
    const tTop = pad+lh+clamp(h*0.05,8,42), tBot = h-pad*1.55;
    const buildW = (s:number) => {
      const it:{h:number;fn:(y:number)=>string}[] = [];
      const kf = fitKick(tW, clamp(h*0.075,10,17)*s);
      it.push({h:kf*2.0, fn:(y)=>kickerEl(tx, y+kf*0.8, kf, anchor)});
      const hb = fitLines(String(title), HEAD, 900, !ar, tW, clamp(h*0.2,18,54)*s, 2);
      hb.lines.forEach((ln:string)=>it.push({h:hb.fs*1.18, fn:(y)=>T2(ln, tx, y+hb.fs*0.9, hb.fs, anchor, T.text, HEAD, 900)}));
      if (sub) { const sf = fitFont(String(sub), BODY, 600, false, tW, clamp(h*0.07,10,17)*s);
        it.push({h:sf*2.1, fn:(y)=>T2(String(sub), tx, y+sf*0.9, sf, anchor, T.sub, BODY, 600)}); }
      const cf = clamp(h*0.088,11,22)*s; it.push({h:cf*2.05*1.55, fn:(y)=>ctaEl(tx, y+cf*2.05*0.3, cf, anchor)});
      return { items:it, total:it.reduce((a,x)=>a+x.h,0) };
    };
    let st = buildW(1); if (st.total>(tBot-tTop)) st = buildW((tBot-tTop)/st.total);
    let y = tTop+Math.max(0,((tBot-tTop)-st.total))/2;
    st.items.forEach(it=>{ P.push(it.fn(y)); y += it.h; });
    const he = heroEl(heroCx, h*0.545, heroW*0.94, clamp(h*0.46,44,152)); if (he) P.push(he.svg);
    const footTxt = site;
    P.push(T2(footTxt, ar?w-pad:pad, h-pad*0.5, fitFont(footTxt, BODY, 700, false, w*0.42, clamp(h*0.05,9,14)), ar?'end':'start', T.foot, BODY, 700));
    P.push(T2(ar?'مرخّصة من FSA · التداول ينطوي على مخاطر':'Licensed by FSA · Trading involves risk', ar?pad:w-pad, h-pad*0.5, clamp(h*0.042,8,12), ar?'start':'end', T.foot, BODY, 400));
    P.push(`<rect x="0" y="${h-Math.max(3,h*0.016)}" width="${w}" height="${Math.max(3,h*0.016)}" fill="url(#og)"/>`);

  } else if (ratio>=2.6 && h<220) {
    // ── HORIZONTAL BAR ── [logo] · [kicker+headline] · [hero] · [CTA]
    const pad = clamp(h*0.28,10,34), lh = clamp(h*0.4,16,54), lw = lh*LOGO_AR;
    const wantCta = w>=470, wantHero = !!c.hero && w>=440 && ratio<9;
    const ctaF = wantCta ? clamp(h*0.2,9,20) : 0, ctaBw = wantCta ? ctaW(ctaF) : 0;
    P.push(bullMark(ar ? -h*0.35 : w-h*0.72, h*0.16, h*1.0));
    const logoX = ar ? w-pad-lw : pad;
    const ctaX  = ar ? pad : w-pad;
    const heroBudget = wantHero ? clamp(w*0.16,60,150) : 0;
    const textStart = ar ? (wantCta?ctaX+ctaBw+pad:pad) + (wantHero?heroBudget+pad:0) : logoX+lw+pad;
    const heroCx = ar ? textStart-heroBudget/2 : (wantCta? w-pad-ctaBw : w-pad)-heroBudget/2;
    const tW = Math.max(20, ar ? (logoX-pad)-textStart : (wantHero? heroCx-heroBudget/2-pad : (wantCta? w-pad-ctaBw-pad : w-pad))-textStart);
    P.push(logo(logoX, h*0.5-lh/2, lh));
    const anchor = ar ? 'end' : 'start', tx = ar ? (logoX-pad) : textStart;
    const kf = fitKick(tW, clamp(h*0.16,8,13));
    const hf = fitFont(String(title), HEAD, 900, !ar, tW, clamp(h*0.36,12,30));
    P.push(kickerEl(tx, h*0.5-hf*0.28, kf, anchor));
    P.push(T2(String(title), tx, h*0.5+hf*0.62, hf, anchor, T.text, HEAD, 900));
    if (wantHero) { const he = heroEl(heroCx, h*0.62, heroBudget, clamp(h*0.6,18,44)); if (he) P.push(he.svg); }
    if (wantCta) P.push(ctaEl(ctaX, h*0.5-ctaF*2.05/2, ctaF, ar?'start':'end'));
    P.push(`<rect x="0" y="${h-Math.max(2,h*0.03)}" width="${w}" height="${Math.max(2,h*0.03)}" fill="url(#og)"/>`);

  } else if (h/w>=1.7) {
    // ── VERTICAL / SKYSCRAPER ── stacked centred
    const p = clamp(w*0.11,10,44), cx = w/2, iw = w-2*p, tiny = w<150;
    const lh = clamp(iw/LOGO_AR,10,h*0.075);
    P.push(logo(cx-lh*LOGO_AR/2, p, lh));
    P.push(bullMark(cx-w*0.55, h-w*0.9, w*1.1));
    P.push(bracket(p, p+lh+p*0.4, clamp(w*0.14,10,26), Math.max(1.5,w*0.012)));
    const footTxt = site;
    const ff = clamp(w*0.058,8.5,13);
    P.push(T2(footTxt, cx, h-(h>=420?h*0.05:h*0.028), fitFont(footTxt, BODY, 700, false, iw, ff), 'middle', T.text, BODY, 700));
    if (h>=440) P.push(T2(ar?'مرخّصة من FSA · التداول ينطوي على مخاطر':'Licensed by FSA · Trading involves risk', cx, h-h*0.022, clamp(w*0.045,7,10), 'middle', T.foot, BODY, 400));
    const vTop = p+lh+clamp(h*0.045,10,64), vBot = h-(h>=420?h*0.1:h*0.06), vAvail = vBot-vTop;
    const build = (s:number) => {
      const it:{h:number;fn:(y:number)=>string}[] = [];
      if (!tiny) { const kf = fitKick(iw, clamp(w*0.058,9,15)*s);
        it.push({h:kf*2.1, fn:(y)=>kickerEl(cx, y+kf*0.8, kf, 'middle')}); }
      const hb = fitLines(String(title), HEAD, 900, !ar, iw, clamp(w*0.17,12,50)*s, 2);
      hb.lines.forEach((ln:string)=>it.push({h:hb.fs*1.24, fn:(y)=>T2(ln, cx, y+hb.fs*0.92, hb.fs, 'middle', T.text, HEAD, 900)}));
      if (!tiny && sub) { const sf = fitFont(String(sub), BODY, 600, false, iw, clamp(w*0.058,8,13)*s);
        it.push({h:sf*2.2, fn:(y)=>T2(String(sub), cx, y+sf*0.9, sf, 'middle', T.sub, BODY, 600)}); }
      if (!tiny && c.hero && h>340) { const he0 = heroEl(cx, 0, iw, clamp(w*0.34,20,140)*s); const hf = he0?he0.fs:0;
        it.push({h:hf*1.7, fn:(y)=>{ const he = heroEl(cx, y+hf*0.92, iw, clamp(w*0.34,20,140)*s); return he?he.svg:''; }}); }
      if (!tiny) { let cf = clamp(w*0.066,9,17)*s; if (ctaW(cf)>iw) cf = cf*iw/ctaW(cf);
        it.push({h:cf*2.05*1.7, fn:(y)=>ctaEl(cx, y+cf*2.05*0.35, cf, 'middle')}); }
      return { items:it, total:it.reduce((a,x)=>a+x.h,0) };
    };
    let vs = build(1);
    if (vs.total>vAvail) vs = build(vAvail/vs.total);
    else if (vs.total < vAvail*0.66) vs = build(Math.min(1.6, vAvail*0.78/vs.total));
    let vy = vTop+Math.max(0,(vAvail-vs.total))/2;
    vs.items.forEach(it=>{ P.push(it.fn(vy)); vy += it.h; });
    P.push(`<rect x="0" y="${h-Math.max(3,w*0.02)}" width="${w}" height="${Math.max(3,w*0.02)}" fill="url(#og)"/>`);

  } else {
    // ── CARD / SQUARE / SOCIAL ── centred post
    const p = m*0.085, cx = w/2, iw = w-2*p, big = m>=210;
    P.push(bullMark(ar ? -m*0.16 : w-m*0.58, h-m*0.62, m*0.66));
    const lh = clamp(m*0.085,14,84);
    P.push(logo(p, p, lh));
    P.push(bracket(p, p+lh+m*0.03, clamp(m*0.11,12,40), Math.max(1.6,m*0.007)));
    if (big) {
      const footTxt = site;
      const top = p+lh+m*0.055, bottom = h-p*1.5, avail = bottom-top;
      const build = (s:number) => {
        const it:{h:number;fn:(y:number)=>string}[] = [];
        const kf = fitKick(iw, m*0.036*s);
        it.push({h:kf*2.0, fn:(y)=>kickerEl(cx, y+kf*0.8, kf, 'middle')});
        const hb = fitLines(String(title), HEAD, 900, !ar, iw, m*0.1*s, 2);
        hb.lines.forEach((ln:string)=>it.push({h:hb.fs*1.2, fn:(y)=>T2(ln, cx, y+hb.fs*0.9, hb.fs, 'middle', T.text, HEAD, 900)}));
        if (sub) { const sf = fitFont(String(sub), BODY, 600, false, iw, m*0.04*s); it.push({h:sf*2.2, fn:(y)=>T2(String(sub), cx, y+sf*0.9, sf, 'middle', T.sub, BODY, 600)}); }
        if (c.hero) { const he0 = heroEl(cx, 0, iw*0.92, m*0.22*s); const hf = he0?he0.fs:0;
          it.push({h:hf*1.6, fn:(y)=>{ const he = heroEl(cx, y+hf*0.9, iw*0.92, m*0.22*s); return he?he.svg:''; }}); }
        const cf = m*0.042*s; it.push({h:cf*2.05*1.6, fn:(y)=>ctaEl(cx, y+cf*2.05*0.3, cf, 'middle')});
        const stf = clamp(m*0.032*s,10,18); it.push({h:stf*2.0, fn:(y)=>T2(footTxt, cx, y+stf*0.8, fitFont(footTxt, BODY, 700, false, iw, stf), 'middle', T.foot, BODY, 700)});
        return { items:it, total:it.reduce((a,x)=>a+x.h,0) };
      };
      let st = build(1); if (st.total>avail) st = build(avail/st.total);
      let y = top+Math.max(0,(avail-st.total))/2;
      st.items.forEach(it=>{ P.push(it.fn(y)); y += it.h; });
      P.push(T2(ar?'مرخّصة من FSA · إن التداول ينطوي على مخاطر':'Licensed by FSA · Trading involves risk', ar?w-p:p, h-p*0.5, m*0.026, ar?'end':'start', T.foot, BODY, 400));
    } else {
      let y = h*0.46;
      const hb = fitLines(String(title), HEAD, 900, !ar, iw, m*0.16, 2);
      hb.lines.forEach((ln:string)=>{ P.push(T2(ln, cx, y, hb.fs, 'middle', T.text, HEAD, 900)); y += hb.fs*1.12; });
      const stf = fitFont(site, BODY, 700, false, iw, m*0.085);
      P.push(T2(site, cx, h-p*0.9, stf, 'middle', T.sub, BODY, 700));
    }
    P.push(`<rect x="0" y="${h-Math.max(3,m*0.012)}" width="${w}" height="${Math.max(3,m*0.012)}" fill="url(#og)"/>`);
  }
  return `<?xml version="1.0" encoding="UTF-8"?><svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}">${P.join('')}</svg>`;
}

// ── small components ─────────────────────────────────────────────────────────
function Kpi({ label, value, sub, accent, icon, onInfo }:any) {
  return (
    <div style={{ ...S.card, padding:'15px 17px' }}>
      <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:9 }}>
        <span style={{ fontSize:11.5, color:C.text2, fontWeight:600, textTransform:'uppercase', letterSpacing:'.03em' }}>{label}</span>
        <span style={{ display:'flex', alignItems:'center', gap:6 }}>
          {onInfo && <button onClick={onInfo} title="What's this?" style={{ width:16, height:16, lineHeight:'14px', textAlign:'center', borderRadius:99, border:`1px solid ${C.borderH}`, background:'#fff', color:C.text2, fontSize:10.5, fontWeight:900, fontStyle:'italic', cursor:'pointer', padding:0, flexShrink:0 }}>i</button>}
          {icon && <span style={{ fontSize:14, opacity:.85 }}>{icon}</span>}
        </span>
      </div>
      <div style={{ fontSize:25, fontWeight:700, color:C.text, letterSpacing:'-0.5px', lineHeight:1.05 }}>{value}</div>
      {sub && <div style={{ fontSize:12, color:accent||C.text3, marginTop:7 }}>{sub}</div>}
    </div>
  );
}
function MiniStat({ label, value, sub, accent }:any) {
  return (
    <div style={{ ...S.card, padding:'13px 14px' }}>
      <div style={{ fontSize:10.5, color:C.text2, fontWeight:600, textTransform:'uppercase', letterSpacing:'.03em', marginBottom:6 }}>{label}</div>
      <div style={{ fontSize:19, fontWeight:700, color:accent||C.text }}>{value}</div>
      {sub && <div style={{ fontSize:10.5, color:C.text3, marginTop:4 }}>{sub}</div>}
    </div>
  );
}
function EmptyRow({ cols, loading }:{ cols:number; loading:boolean }) {
  return <tr><td colSpan={cols} style={{ ...S.td, textAlign:'center', color:C.text3, padding:34 }}>{loading ? 'Loading…' : 'Nothing to show'}</td></tr>;
}
function Bar({ pct, color }:{ pct:number; color:string }) {
  return <div style={{ height:7, borderRadius:99, background:C.card2, overflow:'hidden' }}>
    <div style={{ height:'100%', borderRadius:99, width:`${Math.max(2,Math.min(100,pct))}%`, background:color }} /></div>;
}

/* ═══════════ GO-LIVE ANALYTICS KIT (Jul 2026) — pure-SVG, zero deps ═══════════ */
const sumBy = (a:any[], k:string) => a.reduce((s,d)=>s+(+d?.[k]||0), 0);
function timeAgo(ts?:string) {
  if (!ts) return '';
  const t = Date.parse(String(ts).replace(' ','T')); if (isNaN(t)) return '';
  const s = Math.max(0, (Date.now()-t)/1000);
  if (s < 90) return 'just now';
  if (s < 3600) return `${Math.round(s/60)}m ago`;
  if (s < 86400) return `${Math.round(s/3600)}h ago`;
  return `${Math.round(s/86400)}d ago`;
}
// animated count-up for hero numbers (eases out over ~1s, re-runs when target changes)
function useCountUp(target:number) {
  const [v, setV] = useState(0);
  useEffect(() => {
    let raf = 0; const t0 = performance.now(); const from = 0; const dur = 950;
    const step = (now:number) => {
      const p = Math.min(1, (now-t0)/dur); const e = 1-Math.pow(1-p, 3);
      setV(from + (target-from)*e);
      if (p < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [target]);
  return v;
}
function AnimatedUsd({ v }:{ v:number }) { const a = useCountUp(v||0); return <>{usd(a)}</>; }
function DeltaChip({ pct }:{ pct:number|null }) {
  if (pct === null || !isFinite(pct)) return null;
  const up = pct >= 0;
  return <span style={{ display:'inline-flex', alignItems:'center', gap:4, padding:'3px 9px', borderRadius:99, fontSize:11.5, fontWeight:800,
    background: up?'rgba(19,168,88,0.18)':'rgba(224,49,71,0.18)', color: up?'#3ddc8f':'#ff7285' }}>
    {up?'▲':'▼'} {Math.abs(pct)}% <span style={{ fontWeight:600, opacity:.75 }}>vs prev 30d</span></span>;
}
// mini sparkline (gradient area) — hero + KPI accents
function Spark({ vals, color, w=190, h=52, id }:{ vals:number[]; color:string; w?:number; h?:number; id:string }) {
  if (!vals.length) return null;
  const mx = Math.max(...vals, 1), n = vals.length;
  const x = (i:number) => n<=1 ? w/2 : (i/(n-1))*w;
  const y = (v:number) => h-3-(h-8)*(v/mx);
  const pts = vals.map((v,i)=>`${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{ display:'block', overflow:'visible' }}>
      <defs><linearGradient id={`sp-${id}`} x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stopColor={color} stopOpacity="0.45" /><stop offset="100%" stopColor={color} stopOpacity="0.02" />
      </linearGradient></defs>
      <polygon points={`0,${h} ${pts} ${w},${h}`} fill={`url(#sp-${id})`} />
      <polyline points={pts} fill="none" stroke={color} strokeWidth="2.2" strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={x(n-1)} cy={y(vals[n-1])} r="3.4" fill={color} stroke="#fff" strokeWidth="1.4" />
    </svg>
  );
}
// circular progress ring — the "game" progress element for the Challenge Arena
function Ring({ pct, size=56, stroke=6, color, track, children }:{ pct:number; size?:number; stroke?:number; color:string; track?:string; children?:React.ReactNode }) {
  const r = (size-stroke)/2, c = 2*Math.PI*r, p = Math.max(0, Math.min(100, pct||0));
  return (
    <div style={{ position:'relative', width:size, height:size, flexShrink:0 }}>
      <svg width={size} height={size} style={{ transform:'rotate(-90deg)', display:'block' }}>
        <circle cx={size/2} cy={size/2} r={r} stroke={track||C.card2} strokeWidth={stroke} fill="none" />
        <circle cx={size/2} cy={size/2} r={r} stroke={color} strokeWidth={stroke} fill="none" strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={c*(1-p/100)} style={{ transition:'stroke-dashoffset .9s cubic-bezier(.22,1,.36,1)' }} />
      </svg>
      <div style={{ position:'absolute', inset:0, display:'flex', alignItems:'center', justifyContent:'center' }}>{children}</div>
    </div>
  );
}
// arena ranks — pure fun, computed from how many challenges the IB has completed
const ARENA_RANKS = [
  { n:'Rookie',    icon:'🥉', at:0  }, { n:'Fighter',  icon:'🥊', at:2  },
  { n:'Gladiator', icon:'🛡️', at:5  }, { n:'Champion', icon:'🏆', at:9  },
  { n:'Legend',    icon:'👑', at:14 },
];


/* ── arena list helpers (light theme) ── */
// full-width meter with the count centred ON the bar — spreads quest info across the card
function MeterBar({ pct, label, c1='#5a9bff', c2='#2f6bff', h=15 }:{ pct:number; label?:string; c1?:string; c2?:string; h?:number }) {
  const p = Math.max(0, Math.min(100, pct||0));
  return (
    <div style={{ position:'relative', height:h, borderRadius:h/2, background:'#eef1f7', border:'1px solid #dfe5ef', overflow:'hidden' }}>
      <div className="ibp-bar-fill" style={{ position:'absolute', top:0, left:0, bottom:0, width:`${p}%`, borderRadius:h/2, background:`linear-gradient(90deg, ${c1}, ${c2})` }} />
      {p>0 && p<100 && <div className="ibp-shimmer" style={{ position:'absolute', top:0, left:0, bottom:0, width:`${p}%`, borderRadius:h/2 }} />}
      {label && <div style={{ position:'absolute', inset:0, display:'flex', alignItems:'center', justifyContent:'center', fontSize:h>=14?10:9.5, fontWeight:800, color:'#17202f', textShadow:'0 0 4px #fff, 0 0 4px #fff, 0 0 6px #fff' }}>{label}</div>}
    </div>
  );
}
// soft gold reward pill
function RewardPill({ amount }:{ amount:number }) {
  return <span style={{ flexShrink:0, padding:'5px 12px', borderRadius:99, fontSize:12, fontWeight:900,
    background:'linear-gradient(92deg,#fff3d6,#ffe3a1)', border:'1px solid #f0c96b', color:'#8a6508' }}>🪙 +{usd(amount)}</span>;
}
// full interactive trend chart — hover crosshair + tooltip, day buckets
function TrendChart({ data, metric, color, fmt }:{ data:any[]; metric:string; color:string; fmt:(n:number)=>string }) {
  const [hi, setHi] = useState<number|null>(null);
  const W = 760, H = 210, PL = 44, PR = 12, PT = 14, PB = 26;
  const vals = data.map(d => +d?.[metric]||0);
  const n = vals.length;
  if (!n) return <div style={{ height:H, display:'flex', alignItems:'center', justifyContent:'center', color:C.text3, fontSize:13 }}>
    📉 No activity in this range yet — share your referral link to get the chart moving!</div>;
  const mx = Math.max(...vals, 1);
  const x = (i:number) => PL + (n<=1 ? (W-PL-PR)/2 : (i/(n-1))*(W-PL-PR));
  const y = (v:number) => PT + (H-PT-PB) * (1 - v/mx);
  const pts = vals.map((v,i)=>`${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
  const grid = [0.25, 0.5, 0.75, 1];
  const onMove = (e:React.MouseEvent<SVGSVGElement>) => {
    const r = (e.currentTarget as any).getBoundingClientRect();
    const px = (e.clientX - r.left) / r.width * W;
    const i = Math.round((px-PL) / Math.max(1,(W-PL-PR)) * (n-1));
    setHi(Math.max(0, Math.min(n-1, i)));
  };
  const hd = hi!==null ? data[hi] : null;
  return (
    <div style={{ position:'relative' }}>
      {hd && (
        <div style={{ position:'absolute', top:2, right:8, background:'#0b1220', color:'#fff', borderRadius:9, padding:'6px 12px', fontSize:11.5, fontWeight:700, pointerEvents:'none', boxShadow:'0 6px 18px rgba(11,18,32,0.25)', zIndex:2 }}>
          {String(hd.bucket).slice(0,10).split('-').reverse().join('/')} · <span style={{ color }}>{fmt(+hd[metric]||0)}</span>
        </div>
      )}
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width:'100%', height:'auto', display:'block', cursor:'crosshair' }}
           onMouseMove={onMove} onMouseLeave={()=>setHi(null)}>
        <defs><linearGradient id={`tc-${metric}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.32" /><stop offset="100%" stopColor={color} stopOpacity="0.02" />
        </linearGradient></defs>
        {grid.map((g,i)=>(
          <g key={i}>
            <line x1={PL} x2={W-PR} y1={y(mx*g)} y2={y(mx*g)} stroke={C.border} strokeDasharray="3 5" strokeWidth="1" />
            <text x={PL-7} y={y(mx*g)+3.5} textAnchor="end" fontSize="9.5" fill={C.text3} fontFamily={SANS}>{fmt(mx*g)}</text>
          </g>
        ))}
        <polygon points={`${x(0)},${y(0)} ${pts} ${x(n-1)},${y(0)}`} fill={`url(#tc-${metric})`} />
        <polyline points={pts} fill="none" stroke={color} strokeWidth="2.4" strokeLinejoin="round" strokeLinecap="round" />
        {/* x labels — ~6 evenly spaced */}
        {vals.map((_,i)=> (n<=7 || i%Math.ceil(n/6)===0 || i===n-1) ? (
          <text key={i} x={x(i)} y={H-8} textAnchor="middle" fontSize="9.5" fill={C.text3} fontFamily={SANS}>
            {String(data[i].bucket).slice(5,10).split('-').reverse().join('/')}</text>
        ) : null)}
        {hi!==null && (<g>
          <line x1={x(hi)} x2={x(hi)} y1={PT} y2={H-PB} stroke={color} strokeOpacity="0.45" strokeWidth="1.2" />
          <circle cx={x(hi)} cy={y(vals[hi])} r="4.6" fill={color} stroke="#fff" strokeWidth="2" />
        </g>)}
      </svg>
    </div>
  );
}

const TRADE_PERIODS:[string,string][] = [
  ['today','Today'],['yesterday','Yesterday'],['this_week','This week'],['last_week','Last week'],
  ['last_7_days','Last 7 days'],['this_month','This month'],['last_month','Last month'],
  ['this_year','This year'],['last_year','Last year'],['all_time','All time'],['custom','Custom'],
];
// Light trades table (the dark IBTradesTab stays for the admin profile view). Shows ONLY
// eligible (commission-paid) trades, with a period selector and country/city/client filters.
function LightTrades({ ibId, preview }:{ ibId?:number; preview:boolean }) {
  // Client P&L is shown to STAFF only. The IB partner site (partner1.tnfx.co) must never show
  // whether clients win or lose money — the backend also strips profit for IB callers.
  const showPL = !window.location.hostname.toLowerCase().startsWith('partner');
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState('this_month');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [country, setCountry] = useState('');
  const [city, setCity] = useState('');
  const [q, setQ] = useState('');           // search: client name / login / symbol
  const qLogin = /^\d{3,}$/.test(q.trim()) ? q.trim() : '';   // numeric → server-side login filter
  const [campaign, setCampaign] = useState('');
  const [groupBy, setGroupBy] = useState('list');   // list | day | week | month | year
  const inp:React.CSSProperties = { padding:'7px 10px', borderRadius:8, fontSize:12, outline:'none', background:'#fff', color:C.text, border:`1px solid ${C.borderH}` };
  useEffect(() => {
    setLoading(true);
    const ep = preview ? `/ibs/${ibId}/trades` : '/portal/ib-trades';
    const p = new URLSearchParams({ period, view:'eligible', page:'1', page_size:'100' });
    if (period==='custom') { if (dateFrom) p.set('date_from',dateFrom); if (dateTo) p.set('date_to',dateTo); }
    if (country) p.set('country',country);
    if (city) p.set('city',city);
    if (qLogin) p.set('client_login',qLogin);
    if (campaign) p.set('campaign',campaign);
    if (groupBy!=='list') p.set('group_by',groupBy);
    apiGet(`${ep}?${p}`).then(d=>setData(d)).catch(()=>setData(null)).finally(()=>setLoading(false));
  }, [ibId, preview, period, dateFrom, dateTo, country, city, qLogin, campaign, groupBy]);
  const t = data?.totals || { trades:0, lots:0, commission:0 };
  const qq = q.trim().toLowerCase();
  const rows = (data?.trades || []).filter((r:any) => !qq || /^\d{3,}$/.test(qq) ||
    [r.client, r.login, r.symbol].some((v:any) => String(v||'').toLowerCase().includes(qq)));
  const groups = data?.groups || null;
  const opts = data?.filters || { countries:[], cities:[], campaigns:[] };
  const grouped = groupBy!=='list';
  return (
    <div style={{ ...S.card, overflow:'hidden' }}>
      {/* ONE filter row — search + period + country + cities + campaign + display */}
      <div className="ibp-filters" style={{ display:'flex', gap:8, padding:'12px 14px', borderBottom:`1px solid ${C.border}`, alignItems:'center' }}>
        <input value={q} onChange={e=>setQ(e.target.value)} placeholder="🔍 Search client, login, symbol…" style={{ ...inp, width:210 }} />
        <select value={period} onChange={e=>setPeriod(e.target.value)} title="Period" style={inp}>
          {TRADE_PERIODS.map(([k,l])=><option key={k} value={k}>{l}</option>)}
        </select>
        {period==='custom' && (<>
          <input type="date" max={new Date(Date.now()+86400000).toISOString().slice(0,10)} value={dateFrom} onChange={e=>setDateFrom(e.target.value)} style={inp} />
          <input type="date" max={new Date(Date.now()+86400000).toISOString().slice(0,10)} value={dateTo} onChange={e=>setDateTo(e.target.value)} style={inp} />
        </>)}
        <select value={country} onChange={e=>setCountry(e.target.value)} style={inp}>
          <option value="">All countries</option>{(opts.countries||[]).map((x:string)=><option key={x} value={x}>{x}</option>)}
        </select>
        <select value={city} onChange={e=>setCity(e.target.value)} style={inp}>
          <option value="">All cities</option>{(opts.cities||[]).map((x:string)=><option key={x} value={x}>{x}</option>)}
        </select>
        <select value={campaign} onChange={e=>setCampaign(e.target.value)} style={inp}>
          <option value="">All campaigns</option>{(opts.campaigns||[]).map((x:string)=><option key={x} value={x}>{x}</option>)}
        </select>
        <select value={groupBy} onChange={e=>setGroupBy(e.target.value)} title="Display" style={inp}>
          {[['list','Per trade'],['day','Daily'],['week','Weekly'],['month','Monthly'],['year','Yearly']].map(([k,l])=><option key={k} value={k}>{l}</option>)}
        </select>
        {(country||city||q||campaign) && <button onClick={()=>{setCountry('');setCity('');setQ('');setCampaign('');}} style={{ ...inp, color:C.red, cursor:'pointer', flexShrink:0 }}>✕</button>}
      </div>
      <div style={{ padding:'8px 14px', borderBottom:`1px solid ${C.border}`, fontSize:12.5, color:C.text2 }}>
        {num(t.trades)} eligible · {num(t.lots)} lots · <b style={{ color:C.green }}>{usd(t.commission)} commission</b>
      </div>
      <div style={{ overflowX:'auto', maxHeight:560 }}>
        {grouped ? (
          <table style={{ width:'100%', borderCollapse:'collapse' }}>
            {/* Client P&L (Profit) is shown to STAFF only (preview). IBs must not see whether
                their clients win or lose money — the column is omitted in the IB portal. */}
            <thead><tr>{['Period','Trades','Lots','Commission',...(showPL?['Profit']:[])].map(h=><th key={h} style={S.th}>{h}</th>)}</tr></thead>
            <tbody>
              {(groups||[]).map((g:any,i:number)=>(
                <tr key={i} className="ibp-row">
                  <td style={{ ...S.td, fontWeight:600 }}>{g.bucket}</td>
                  <td style={S.td}>{num(g.trades)}</td>
                  <td className="cp" style={S.td}>{num(g.lots)} lots</td>
                  <td className="cg" style={{ ...S.td, fontWeight:600 }}>{usd(g.commission)}</td>
                  {showPL && <td className={g.profit>=0?'cg':'cr'} style={S.td}>{g.profit>=0?'+':''}{usd(g.profit)}</td>}
                </tr>
              ))}
              {(!groups || groups.length===0) && <EmptyRow cols={showPL?5:4} loading={loading} />}
            </tbody>
          </table>
        ) : (
        <table style={{ width:'100%', borderCollapse:'collapse' }}>
          <thead><tr>{['Trade #','Account','Open','Symbol','Side','Lots',...(showPL?['Profit']:[]),'Commission','Closed'].map(h=>
            <th key={h} className={['Open','Closed'].includes(h)?'hm':''} style={S.th}>{h}</th>)}</tr></thead>
          <tbody>
            {rows.map((r:any,i:number) => {
              const buy = String(r.direction||'').toLowerCase().startsWith('b');
              return (
                <tr key={i} className="ibp-row">
                  <td style={{ ...S.td, fontFamily:'monospace', color:C.text3 }}>{r.deal_id ?? '—'}</td>
                  <td className="cb" style={{ ...S.td, fontFamily:'monospace', fontWeight:600 }}>#{r.login}</td>
                  <td className="cm hm" style={S.td}>{r.open_time ? String(r.open_time).slice(0,16).replace('T',' ') : '—'}</td>
                  <td style={S.td}>{r.symbol}</td>
                  <td style={S.td}><span style={badge(buy?C.greenBg:C.redBg, buy?C.green:C.red)}>{buy?'BUY':'SELL'}</span></td>
                  <td style={S.td}>{(r.lots||0).toFixed(2)}</td>
                  {/* Client P&L shown to STAFF only — IBs must not see client win/loss. */}
                  {showPL && <td className={(r.profit||0)>=0?'cg':'cr'} style={{ ...S.td, fontWeight:600 }}>{(r.profit||0)>=0?'+':''}{usd(r.profit)}</td>}
                  {/* per-trade commission is often cents (e.g. 0.30 lots × $0.80/lot = $0.24) — show 2
                      decimals so small real commissions don't round down to a misleading "$0" */}
                  <td className="cg" style={{ ...S.td, fontWeight:600 }}>{'$' + (r.commission||0).toFixed(2)}</td>
                  <td className="cm hm" style={S.td}>{r.close_time ? String(r.close_time).slice(0,16).replace('T',' ') : '—'}</td>
                </tr>
              );
            })}
            {rows.length===0 && <EmptyRow cols={showPL?9:8} loading={loading} />}
          </tbody>
        </table>
        )}
      </div>
    </div>
  );
}

// ── demo (standalone nav) sample data ────────────────────────────────────────
const MOCK_CLIENTS = [
  { login:10021, name:'Ahmed Al-Rashid',  country:'UAE',          balance:24500, dep:30000, wd:5500,  volume:125, kyc:'verified', reg:'2026-01-20', campaign:'Facebook-Iraq' },
  { login:10028, name:'Mohammed Hassan',  country:'Egypt',        balance:8200,  dep:10000, wd:1800,  volume:42,  kyc:'pending',  reg:'2026-02-14', campaign:'Instagram' },
  { login:10077, name:'Fatima Nasser',    country:'Saudi Arabia', balance:3100,  dep:0,     wd:0,     volume:0,   kyc:'pending',  reg:'2026-03-01', campaign:'TikTok' },
  { login:10112, name:'Omar Khalil',      country:'Turkey',       balance:51800, dep:60000, wd:8200,  volume:445, kyc:'verified', reg:'2025-11-10', campaign:'Facebook-Jordan' },
  { login:10134, name:'Sara Ibrahim',     country:'Jordan',       balance:5200,  dep:8000,  wd:1000,  volume:22,  kyc:'verified', reg:'2026-04-05', campaign:'Instagram' },
  { login:10156, name:'Khalid Mansour',   country:'Kuwait',       balance:12400, dep:0,     wd:0,     volume:0,   kyc:'pending',  reg:'2026-02-28', campaign:'Direct' },
];
const MOCK_MANAGER = { name:'Sara Abdullah', title:'Senior IB Manager', email:'sara@tnfx.co', phone:'+971 55 244 1596', department:'Partnerships' };
const MOCK_COMMISSIONS = [
  { client_login:10112, client_name:'Omar Khalil',    lots:445, pts_per_lot:8, commission_usd:2980, status:'unpaid' },
  { client_login:10021, client_name:'Ahmed Al-Rashid',lots:125, pts_per_lot:8, commission_usd:840,  status:'unpaid' },
  { client_login:10028, client_name:'Mohammed Hassan',lots:42,  pts_per_lot:8, commission_usd:280,  status:'paid' },
];

// ── challenges sample (gamification) ─────────────────────────────────────────
const CH1 = [   // career path (sequential)
  { id:1, stage:1, name:'Getting Started', desc:'Onboard your first 5 clients',         reward:50,   status:'completed' },
  { id:2, stage:2, name:'First Blood',     desc:'Bring your first funded client (FTD)', reward:100,  status:'completed' },
  { id:3, stage:3, name:'Momentum',        desc:'10 funded clients + 100 lots traded',  reward:250,  status:'active', progress:62 },
  { id:4, stage:4, name:'Rising Star',     desc:'25 funded clients + 500 lots',         reward:600,  status:'locked' },
  { id:5, stage:5, name:'Power Partner',   desc:'50 funded clients + 2,000 lots',       reward:1500, status:'locked' },
  { id:6, stage:6, name:'Legend',          desc:'100 funded clients + 6,000 lots',      reward:4000, status:'locked' },
];
const CH2 = [   // weekly challenges
  { id:1, emoji:'🩸', name:'First Blood',    desc:'Bring 1 FTD this week',          target:1,     progress:1,     reward:15  },
  { id:2, emoji:'⚔️', name:'Double Down',    desc:'Bring 2 FTDs this week',         target:2,     progress:2,     reward:30  },
  { id:3, emoji:'🎯', name:'Hat Trick',      desc:'Bring 3 FTDs this week',         target:3,     progress:2,     reward:60  },
  { id:4, emoji:'📊', name:'Volume Hunter',  desc:'Clients trade 50 lots',          target:50,    progress:32,    reward:120 },
  { id:5, emoji:'💵', name:'Cash Flow',      desc:'Clients deposit $5,000',         target:5000,  progress:3200,  reward:30  },
  { id:6, emoji:'🔗', name:'Link Builder',   desc:'10 referral registrations',      target:10,    progress:7,     reward:20  },
  { id:7, emoji:'🐋', name:'Whale Hunter',   desc:'Clients deposit $50,000',        target:50000, progress:12000, reward:400 },
  { id:8, emoji:'🌍', name:'Gulf Dominator', desc:'3 FTDs from UAE / KSA / Kuwait', target:3,     progress:1,     reward:100 },
];

// ══════════════════════════════════════════════════════════════════════════════
// Add-a-channel config for the Profile page (mirrors the signup wizard; kept local to avoid a
// circular import with PartnerGate). prefix = domain shown as a chip · username = @handle · url = full.
const SOCIALS:any[] = [
  { k:'facebook',  label:'Facebook',  mode:'prefix',   prefix:'facebook.com/', ph:'yourpage' },
  { k:'youtube',   label:'YouTube',   mode:'prefix',   prefix:'youtube.com/',  ph:'@yourchannel' },
  { k:'telegram',  label:'Telegram',  mode:'prefix',   prefix:'t.me/',         ph:'yourchannel' },
  { k:'instagram', label:'Instagram', mode:'username', tmpl:(u:string)=>`instagram.com/${u}`,    ph:'username' },
  { k:'tiktok',    label:'TikTok',    mode:'username', tmpl:(u:string)=>`tiktok.com/@${u}`,       ph:'username' },
  { k:'snapchat',  label:'Snapchat',  mode:'username', tmpl:(u:string)=>`snapchat.com/add/${u}`, ph:'username' },
  { k:'x',         label:'X',         mode:'username', tmpl:(u:string)=>`x.com/${u}`,             ph:'username' },
  { k:'whatsapp',  label:'WhatsApp',  mode:'prefix',   prefix:'wa.me/',        ph:'9647…' },
  { k:'website',   label:'Website',   mode:'url', ph:'https://yoursite.com' },
];
const buildSocUrl = (c:any, raw:string):string => {
  const v = (raw||'').trim(); if (!c || !v) return '';
  if (c.mode==='url') return v;
  if (c.mode==='username') return c.tmpl(v.replace(/^@+/,'').replace(/\s+/g,''));
  let h = v.replace(/^https?:\/\//i,'').replace(new RegExp('^'+c.prefix.replace(/\./g,'\\.'),'i'),'');
  return c.prefix + h.replace(/^\/+/,'');
};

export default function IBPortal({ lang, ibId, onBack, owner, pending, onLogout, onInstall }:any) {
  const [uiLang, setUiLang] = useState<Lang>((localStorage.getItem('ib_lang') as Lang) || (lang as Lang) || 'en');
  const t = ibT(uiLang);
  const rtl = isRTL(uiLang);
  const setLang = (l:Lang) => { setUiLang(l); localStorage.setItem('ib_lang', l); };
  const [tab, setTab] = useState('dashboard');
  const [showUserMenu, setShowUserMenu] = useState<boolean>(false);
  const [cliSearch, setCliSearch] = useState('');
  const [cliCountry, setCliCountry] = useState('');
  const [cliCity, setCliCity] = useState('');
  const [cliPeriod, setCliPeriod] = useState('all');   // filter by acquisition (first-deposit) period
  const [cliStatus, setCliStatus] = useState('');      // '' | nda | ftd | review | additional
  const [cliSort, setCliSort] = useState<{col:string;dir:'asc'|'desc'}>({ col:'volume', dir:'desc' });
  const [leadSearch, setLeadSearch] = useState('');
  const [leadCountry, setLeadCountry] = useState('');
  const [leadCity, setLeadCity] = useState('');
  const [leadCampaign, setLeadCampaign] = useState('');
  const [leadVer, setLeadVer] = useState('');          // '' | 'ver' | 'unver'
  const [myCampaigns, setMyCampaigns] = useState<any[]>([]);
  const [campModal, setCampModal] = useState(false);
  const [campForm, setCampForm] = useState<any>({ name:'', platform:'', website:'' });
  const [copied, setCopied] = useState('');
  const [refLinks, setRefLinks] = useState<any[]>([]);   // existing (Plugit) referral links
  const [refData, setRefData] = useState<any>(null);     // the primary standalone /r/<code> link + stats
  const [showQR, setShowQR] = useState(false);
  const [notifs, setNotifs] = useState<any>({ unread:0, items:[] });
  const [showBell, setShowBell] = useState(false);
  const [subIbs, setSubIbs] = useState<any>(null);
  const [profileForm, setProfileForm] = useState<any>(null);
  const [addSoc, setAddSoc] = useState<any>({ platform:'', handle:'', busy:false, ok:false, msg:'' });
  const submitSocial = async () => {
    const cat = SOCIALS.find(x=>x.k===addSoc.platform); if (!cat || !ibId) return;
    const url = buildSocUrl(cat, addSoc.handle);
    if (!url) { setAddSoc((a:any)=>({ ...a, msg:'Enter your handle first.' })); return; }
    setAddSoc((a:any)=>({ ...a, busy:true, msg:'' }));
    try {
      const r:any = await apiPost(`/ibs/${ibId}/social/add`, { platform:cat.k, label:cat.label, url, name:(addSoc.handle||'').replace(/^@+/,'') });
      apiGet(`/ibs/${ibId}?period=all_time`).then(setR).catch(()=>{});
      setAddSoc({ platform:'', handle:'', busy:false, ok:true, msg:r?.message || 'Added ✓' });
    } catch (e:any) {
      setAddSoc((a:any)=>({ ...a, busy:false, ok:false, msg:e?.message || 'Could not add — check it and try again.' }));
    }
  };
  const [board, setBoard] = useState<any>(null);
  const [autoWd, setAutoWd] = useState<any>(null);
  const [calcInputs, setCalcInputs] = useState({ clients:10, lots:5 });
  const [anns, setAnns] = useState<any[]>([]);
  const [drill, setDrill] = useState<any>(null);   // client drill-down modal data
  const [statusInfo, setStatusInfo] = useState<any>(null);   // NDA status detail popup (yellow/red)
  const [infoPop, setInfoPop] = useState<any>(null);         // KPI "i" definition popup {title, body}
  const [analytics, setAnalytics] = useState<any>(null);
  const loadAnns = () => { if (ibId) apiGet(`/ibs/${ibId}/announcements`).then((d:any)=>setAnns(d.items||[])).catch(()=>{}); };
  const openDrill = (login:number) => { if (ibId) { setDrill({ loading:true }); apiGet(`/ibs/${ibId}/client/${login}`).then(setDrill).catch(()=>setDrill(null)); } };
  const loadBoard = () => { if (ibId) apiGet(`/ibs/${ibId}/leaderboard?period=this_month`).then(setBoard).catch(()=>{}); };
  const loadAutoWd = () => { if (ibId) apiGet(`/ibs/${ibId}/auto-withdraw`).then(setAutoWd).catch(()=>{}); };
  const loadNotifs = () => { if (ibId) apiGet(`/ibs/${ibId}/notifications`).then(setNotifs).catch(()=>{}); };
  const loadSubIbs = () => { if (ibId) apiGet(`/ibs/${ibId}/sub-ibs`).then(setSubIbs).catch(()=>{}); };
  const downloadStatement = async (period='all_time') => {
    if (!ibId) return;
    try {
      const r = await fetch(`/api/ibs/${ibId}/statement.csv?period=${period}`,
        { headers: { Authorization: `Bearer ${localStorage.getItem('token')||''}` } });
      const blob = await r.blob();
      const a = document.createElement('a'); a.href = URL.createObjectURL(blob);
      a.download = `tnfx-statement-${ibId}-${period}.csv`; a.click();
      setTimeout(()=>URL.revokeObjectURL(a.href), 4000);
    } catch { alert('Could not download the statement'); }
  };
  const [ibOps, setIbOps] = useState<any>(null);          // payout operations
  const [ibPromos, setIbPromos] = useState<any>(null);    // level-promotion history
  const [payModal, setPayModal] = useState<string | null>(null);   // 'withdraw' | 'transfer'
  const [payForm, setPayForm] = useState<any>({ amount:'', to_account:'' });
  const [chData, setChData] = useState<any>(null);   // real challenge data (preview)
  const [chAt, setChAt] = useState(0);               // when chData was fetched — anchors countdown drift
  const preview = !!ibId;

  const [R, setR] = useState<any>(null);
  // language choices for THIS IB: English + their country's language(s). If the saved language
  // isn't offered for their country, fall back to the first allowed one.
  const langOptions = useMemo(() => {
    const allowed = langsForCountry(R?.country);
    return IB_LANGS.filter(l => allowed.includes(l.k));
  }, [R]);
  useEffect(() => {
    if (langOptions.length && !langOptions.some(l => l.k === uiLang)) setLang(langOptions[0].k);
    /* eslint-disable-next-line */
  }, [langOptions]);
  useEffect(() => {
    if (!ibId) { setR(null); return; }
    setR(null);
    apiGet(`/ibs/${ibId}?period=all_time`).then(setR).catch(()=>{});
  }, [ibId]);

  // ── first-login onboarding + agreement gate ──────────────────────────────────────────────
  // `owner` = the REAL IB is viewing their own portal (PartnerGate). Staff "view as IB" / admin
  // preview never see this. Shows the intro slideshow + agreement whenever the IB has not accepted
  // the CURRENT agreement version — so every existing IB is onboarded to the new engine once.
  const [agreement, setAgreement] = useState<any>(null);
  const [onboard, setOnboard] = useState(false);
  const [obStep, setObStep] = useState(0);
  const [obAgree, setObAgree] = useState(false);
  const [obSaving, setObSaving] = useState(false);
  useEffect(() => { apiGet('/ib-agreement').then(setAgreement).catch(()=>{}); }, []);
  useEffect(() => {
    // require agreement.sections so this degrades gracefully if the backend hasn't deployed the v2
    // agreement yet (old backend returns no sections + no accept endpoint) — never show a popup we
    // can't complete. `agreement_version` on R is also only present on the new backend.
    if (owner && R && agreement?.sections?.length && R.agreement_version !== agreement.version) {
      setObStep(0); setObAgree(false); setOnboard(true);
    }
  }, [owner, R, agreement]);
  const acceptAgreement = async () => {
    if (!ibId || obSaving) return;
    setObSaving(true);
    try {
      await apiPost(`/ibs/${ibId}/agreement/accept`, {});
      setR((prev:any) => prev ? { ...prev, agreement_version: agreement?.version } : prev);
      setOnboard(false);
    } catch { alert('Could not save — please try again.'); }
    finally { setObSaving(false); }
  };

  // campaigns (E) + challenges (F) — real data when previewing a specific IB
  const loadCampaigns = () => {
    if (!ibId) return;
    apiGet(`/ibs/${ibId}/campaigns`).then((d:any)=>setMyCampaigns(d.campaigns||[])).catch(()=>{});
    apiGet(`/ibs/${ibId}/referral-links`).then((d:any)=>setRefLinks(d.links||[])).catch(()=>{});
    apiGet(`/ibs/${ibId}/ref`).then((d:any)=>setRefData(d)).catch(()=>{});
  };
  const loadCh = () => { if (ibId) apiGet(`/ibs/${ibId}/challenges`).then((d:any)=>{ setChData(d); setChAt(Date.now()); }).catch(()=>{}); };
  const loadOps = () => { if (ibId) apiGet(`/ibs/${ibId}/operations`).then(setIbOps).catch(()=>{}); };
  const loadPromos = () => { if (ibId) apiGet(`/ibs/${ibId}/promotions`).then(setIbPromos).catch(()=>{}); };
  useEffect(() => { loadCampaigns(); loadCh(); loadOps(); loadPromos(); loadNotifs(); loadAnns(); /* eslint-disable-next-line */ }, [ibId]);
  // real-time-ish: refresh the live figures + notifications every 60s while the tab is open
  useEffect(() => {
    if (!ibId) return;
    const iv = setInterval(() => {
      apiGet(`/ibs/${ibId}?period=all_time`).then(setR).catch(()=>{});
      loadNotifs();
    }, 60000);
    return () => clearInterval(iv);
    /* eslint-disable-next-line */
  }, [ibId]);
  useEffect(() => { if (tab==='campaigns' && ibId) apiGet(`/ibs/${ibId}/campaign-analytics`).then(setAnalytics).catch(()=>{}); /* eslint-disable-next-line */ }, [tab, ibId]);
  useEffect(() => { if (tab==='subibs') loadSubIbs(); if (tab==='leaderboard') loadBoard(); if (tab==='earnings') loadAutoWd(); if (tab==='profile' && R) setProfileForm({ phone:R.phone||'', country:R.country||'', city:R.city||'', bio:R.bio||'' }); /* eslint-disable-next-line */ }, [tab, R]);

  // ── GO-LIVE ANALYTICS: 90-day daily commission series + latest commission activity ──
  const [series, setSeries] = useState<any[]>([]);       // [{bucket, trades, lots, commission}] oldest→newest
  const [recent, setRecent] = useState<any[]>([]);       // latest eligible trades (commission view, no P&L)
  const loadSeries = () => {
    if (!ibId) {
      // mock mode (staff demo without an IB): synthesize a lively series
      const t = Date.now();
      setSeries(Array.from({ length: 90 }, (_, i) => {
        const wave = 1 + 0.5*Math.sin(i/6) + 0.3*Math.sin(i/2.3);
        return { bucket: new Date(t-(89-i)*864e5).toISOString().slice(0,10),
                 trades: Math.round(4+wave*9), lots: +(2+wave*7).toFixed(1), commission: Math.round(35+wave*180) };
      }));
      setRecent([]);
      return;
    }
    const d2 = new Date(), d1 = new Date(Date.now() - 89*864e5);
    const p = new URLSearchParams({ period:'custom', date_from:d1.toISOString().slice(0,10), date_to:d2.toISOString().slice(0,10),
                                    view:'eligible', group_by:'day', page:'1', page_size:'9' });
    apiGet(`/ibs/${ibId}/trades?${p}`).then((d:any) => {
      setSeries((d?.groups || []).slice().reverse());     // backend returns newest-first
      setRecent((d?.trades || []).slice(0, 9));            // same call → latest 9 commission rows
    }).catch(()=>{});
  };
  useEffect(() => { loadSeries(); /* eslint-disable-next-line */ }, [ibId]);
  // silent auto-refresh every 2 min so the portal feels LIVE (no spinners, no flicker)
  useEffect(() => {
    if (!ibId) return;
    const iv = setInterval(() => {
      apiGet(`/ibs/${ibId}?period=all_time`).then(setR).catch(()=>{});
      loadSeries(); loadOps(); loadCh();
    }, 120000);
    return () => clearInterval(iv);
    // eslint-disable-next-line
  }, [ibId]);
  // fill missing days with zeros so charts read time-true (a quiet week shows as a dip, not a skip)
  const daySeries = useMemo(() => {
    if (!series.length) return series;
    const m:any = {}; series.forEach((d:any) => { m[String(d.bucket).slice(0,10)] = d; });
    const out:any[] = [];
    for (let i = 89; i >= 0; i--) {
      const key = new Date(Date.now()-i*864e5).toISOString().slice(0,10);
      out.push(m[key] || { bucket:key, trades:0, lots:0, commission:0 });
    }
    return out;
  }, [series]);
  const last30 = useMemo(() => daySeries.slice(-30), [daySeries]);
  const prev30 = useMemo(() => daySeries.slice(-60, -30), [daySeries]);
  const c30 = sumBy(last30, 'commission'), cPrev30 = sumBy(prev30, 'commission');
  const commDelta = cPrev30 > 0 ? Math.round((c30-cPrev30)/cPrev30*100) : null;
  const bestDay = useMemo(() => daySeries.reduce((b:any,d:any)=> (+d.commission||0) > (+b?.commission||0) ? d : b, null), [daySeries]);
  // hero + analytics-card UI state (top-level: hooks can't live inside the tab conditional)
  const [chMetric, setChMetric] = useState<'commission'|'lots'|'trades'>('commission');
  const [chRange, setChRange]   = useState<30|90>(30);
  // Challenge Arena: celebration burst when a reward is claimed (🎉 +$X overlay, ~1.6s)
  const [celebrate, setCelebrate] = useState<number|null>(null);
  const celebrateT = React.useRef<any>(null);
  const fireCelebrate = (amount:number) => {
    if (celebrateT.current) clearTimeout(celebrateT.current);
    setCelebrate(amount);
    celebrateT.current = setTimeout(()=>setCelebrate(null), 1700);
  };
  // RoK-style quest hub — which quest list dialog is open (null = hub view with the mission core)
  const [questPanel, setQuestPanel] = useState<null|'career'|'weekly'|'season'|'daily'>(null);
  // countdowns tick from FETCH time — a dialog opened minutes later must not restart stale values
  const adjSec = (v:any) => v==null ? null : (!chAt ? +v : Math.max(0, Math.floor(+v - (Date.now()-chAt)/1000)));
  const copyRef = () => {
    const done = () => { setCopied('ref'); setTimeout(()=>setCopied(''), 1800); };
    try { if (navigator.clipboard?.writeText) { navigator.clipboard.writeText(refUrl).then(done); return; } } catch {}
    const ta = document.createElement('textarea'); ta.value = refUrl; document.body.appendChild(ta); ta.select();
    try { document.execCommand('copy'); done(); } catch {} document.body.removeChild(ta);
  };
  // available to request = pending commission balance (earned − paid − approved payouts) minus
  // requests still awaiting approval, so stacked pending requests can't exceed the balance
  const payPending = (ibOps?.operations || []).filter((o:any) => o.status === 'Pending')
    .reduce((s:number, o:any) => s + (o.amount || 0), 0);
  const payAvailable = Math.max(0, (R?.unpaid_commission || 0) - payPending);
  const MIN_PAYOUT = 50;
  const submitPayout = async () => {
    const amt = parseFloat(payForm.amount);
    if (!ibId || !(amt > 0)) return;
    if (amt < MIN_PAYOUT) { alert(`Minimum withdrawal / internal transfer is $${MIN_PAYOUT}.`); return; }
    if (amt > payAvailable) { alert(`Amount exceeds your available commission balance ($${payAvailable.toFixed(2)} available).`); return; }
    if (payModal === 'transfer' && !payForm.to_account) { alert('Choose the trading account to transfer to.'); return; }
    if (payModal === 'withdraw' && !(payForm.wallet || '').trim()) { alert('Enter your Ovadot wallet number.'); return; }
    try {
      // NOTE: apiPost resolves even on HTTP 4xx — check the body for ok/detail
      const res: any = await apiPost(`/ibs/${ibId}/operations`, {
        kind: payModal, amount: amt,
        payment_type: payModal === 'withdraw' ? 'Ovadot Wallet' : 'Transfer',
        to_account: payModal === 'withdraw' ? (payForm.wallet || '').trim() : payForm.to_account,
      });
      if (!res?.ok) { alert(res?.detail || 'Could not submit request'); return; }
      setPayModal(null); setPayForm({ amount:'', to_account:'' }); loadOps();
      alert('Request submitted — it will show in the admin Withdrawals page for approval.');
    } catch { alert('Could not submit request'); }
  };
  const createCampaign = async () => {
    if (!ibId || !campForm.name.trim()) return;
    try { await apiPost(`/ibs/${ibId}/campaigns`, campForm); setCampModal(false); setCampForm({ name:'', platform:'', website:'' }); loadCampaigns(); }
    catch { alert('Could not create campaign'); }
  };
  const chAction = async (path:string, key:string): Promise<boolean> => {
    if (!ibId) return false;
    try {
      const d:any = await apiPost(`/ibs/${ibId}/challenges/${path}`, { key });
      // apiPost resolves even on HTTP 4xx — only a real state payload may replace chData;
      // a {detail:...} error body would wipe the whole arena (false 'all conquered' state).
      if (d && Array.isArray(d.career)) { setChData(d); setChAt(Date.now()); return true; }
      alert((d && (d.detail || d.error)) || 'Action failed — please try again.');
      return false;
    } catch (e:any) { alert(e?.message || 'Action failed'); return false; }
  };
  // Banners tab state: theme + language (Arabic-first, like the real ads) + filters
  const [bTheme, setBTheme] = useState('dark');
  const [bLang, setBLang] = useState<'ar'|'en'>('ar');
  const [bCamp, setBCamp] = useState('all');
  const [bCat, setBCat] = useState('all');
  const [copiedB, setCopiedB] = useState('');
  // the IB's REAL referral link: Plugit custom_link first, then a CRM campaign ref_link,
  // then a ref-code link — NEVER the bare site (the WhatsApp share was sending my1.tnfx.co).
  const _refCode = (preview ? (R?.ib_code || '') : 'IB-001');   // ibCode is declared further down
  const refUrl =
    (refLinks.find((l:any) => String(l.custom_link || '').startsWith('http')) as any)?.custom_link ||
    (myCampaigns[0] && (myCampaigns[0] as any).ref_link) ||
    (_refCode ? `https://my1.tnfx.co/register?ref=${encodeURIComponent(_refCode)}` : 'https://my1.tnfx.co');
  // the REAL logo + bull mark as data-URIs, embedded into every generated banner.
  // Inlined constants (not an async fetch) so the real logo is ALWAYS present — never the
  // text fallback — in both the live preview and the downloaded PNG.
  const logoUri = TNFX_LOGO_DATAURI, markUri = TNFX_MARK_DATAURI;

  // download as PNG (render the brand SVG offscreen onto a canvas)
  const dlBanner = (c:any, s:any) => {
    const svg = bannerSVG(c, bTheme, s.w, s.h, ibCode || '', logoUri, markUri, bLang);
    const url = URL.createObjectURL(new Blob([svg], { type:'image/svg+xml;charset=utf-8' }));
    const img = new Image();
    img.onload = () => {
      const cv = document.createElement('canvas'); cv.width = s.w; cv.height = s.h;
      cv.getContext('2d')!.drawImage(img, 0, 0, s.w, s.h);
      URL.revokeObjectURL(url);
      cv.toBlob(bl => {
        if (!bl) return;
        const a = document.createElement('a');
        a.href = URL.createObjectURL(bl);
        a.download = `tnfx-${c.key}-${bLang}-${bTheme}-${s.w}x${s.h}.png`;
        a.click();
        setTimeout(() => URL.revokeObjectURL(a.href), 4000);
      }, 'image/png');
    };
    img.src = url;
  };
  // copy the WEBSITE EMBED CODE: <a href=referral><img …self-contained banner…></a>
  const copyEmbed = (c:any, s:any) => {
    const svg = bannerSVG(c, bTheme, s.w, s.h, ibCode || '', logoUri, markUri, bLang);
    const html = `<a href="${refUrl}" target="_blank" rel="noopener"><img width="${s.w}" height="${s.h}" style="border:0" alt="TNFX — ${bLang==='ar' ? c.arT : c.title}" src="data:image/svg+xml;utf8,${encodeURIComponent(svg)}"/></a>`;
    const key = `${c.key}-${s.w}x${s.h}`;
    const done = () => { setCopiedB(key); setTimeout(() => setCopiedB(''), 1600); };
    try {
      if (navigator.clipboard?.writeText) { navigator.clipboard.writeText(html).then(done); return; }
    } catch {}
    const ta = document.createElement('textarea');
    ta.value = html; document.body.appendChild(ta); ta.select();
    try { document.execCommand('copy'); done(); } catch {}
    document.body.removeChild(ta);
  };

  // NDA dispute: "this is a new client, why only FTD?" → opens a desk review case
  const [revReq, setRevReq] = useState<Record<number,string>>({});
  const reqNdaReview = async (login:number) => {
    if (!ibId) return;
    if (!window.confirm('Ask our team to re-check this client?\nYou will see the result here: 🟡 NDA (under review) → 🟢 NDA (counts) or 🔴 NDA (related).')) return;
    try {
      const r:any = await apiPost(`/ibs/${ibId}/nda-review`, { login });
      setRevReq(m => ({ ...m, [login]: r?.status || 'pending' }));
    } catch { alert('Could not submit the review request'); }
  };

  // identity
  const level    = preview ? (R?.ib_level || 5) : 8;
  const T        = bt(level);
  const NT       = btNext(level);
  const ibName   = preview ? (R?.name || `IB #${ibId}`) : 'Ahmad Zaman';
  const ibCode   = preview ? (R?.ib_code || '') : 'IB-001';
  const tierName = preview ? (R?.tier || T.name) : T.name;
  const manager  = preview ? R?.manager : MOCK_MANAGER;

  // per-trading-account rows
  const accounts = useMemo(() => {
    if (preview) return (R?.clients || []).map((c:any) => ({
      login:c.login, cus:c.customer_no || `#${c.login}`, name:c.name, country:c.country, city:c.city, balance:c.balance,
      dep:c.total_dep, wd:c.total_with, volume:c.volume, commission:c.commission||0, kyc:c.kyc,
      reg:c.reg_date, campaign:c.campaign || 'Direct', first_trade:c.first_trade,
      email:c.email, phone:c.phone, first_deposit:c.first_deposit,
      email_v:!!c.email_verified, phone_v:!!c.phone_verified,
      account_number:c.account_number || c.login, is_nda:!!c.is_nda, nda_review:c.nda_review || '',
      nda_pending:!!c.nda_pending, nda_lots: c.nda_lots || 0, relation_reason: c.relation_reason || '',
      ftd_here: c.ftd_here !== undefined ? !!c.ftd_here : (c.total_dep||0) > 0,
      is_archived: !!c.is_archived, is_self: !!c.is_self,
      self_related: c.self_related || (c.is_self ? 'self' : null), self_related_reason: c.self_related_reason || '',
      group: c.group_name || '', platform: c.platform || 'MT5',
      kyc_real: c.kyc_real || '', phone_v_real: !!c.phone_verified_real, email_v_real: !!c.email_verified_real,
    }));
    return MOCK_CLIENTS.map((c:any,i:number) => ({ ...c, cus:`CUS${100000+i}`, commission:Math.round((c.volume||0)*7), city:c.city||'', email:`${(c.name||'').split(' ')[0].toLowerCase()}@example.com`, phone:'+9647xxxxxxxx', first_deposit:c.reg, first_trade:c.reg, email_v:false, phone_v:false }));
  }, [R, preview]);

  // CLIENTS = one row per person (customer_no), summing all their trading accounts
  const clients = useMemo(() => {
    const m:any = {};
    accounts.forEach((a:any) => {
      const key = a.cus;
      if (!m[key]) m[key] = { ...a, accounts:0, dep:0, wd:0, volume:0, commission:0, balance:0, kyc:'pending', email_v:false, phone_v:false, first_deposit:null, reg:a.reg };
      const g = m[key];
      g.accounts++; g.dep += (a.dep||0); g.wd += (a.wd||0); g.volume += (a.volume||0);
      g.commission += (a.commission||0); g.balance += (a.balance||0);
      if (a.kyc==='verified') g.kyc = 'verified';
      g.email_v = g.email_v || a.email_v; g.phone_v = g.phone_v || a.phone_v;
      g.is_nda = g.is_nda || a.is_nda;
      g.nda_pending = g.nda_pending || a.nda_pending;
      g.nda_lots = Math.max(g.nda_lots || 0, a.nda_lots || 0);   // customer's total Gold+FX lots
      if (!g.relation_reason && a.relation_reason) g.relation_reason = a.relation_reason;
      g.ftd_here = g.ftd_here || a.ftd_here;
      if (!g.nda_review && a.nda_review) g.nda_review = a.nda_review;
      if (a.first_deposit && (!g.first_deposit || a.first_deposit < g.first_deposit)) g.first_deposit = a.first_deposit;
      if (a.reg && (!g.reg || a.reg < g.reg)) g.reg = a.reg;
    });
    return Object.values(m);
  }, [accounts]);

  const k = preview ? {
    clients:R?.total_clients||0, active:R?.period?.active_clients||R?.active_clients||0,
    ftd:R?.period?.ftd??R?.funnel?.ftd??0, nda:R?.period?.nda??R?.funnel?.nda??0,
    leads:R?.funnel?.leads||0, verified:R?.funnel?.verified_leads||0, subIbs:R?.funnel?.sub_ibs||0,
    // paid = everything the IB already took out (Operation-Log payoff + any staff payments);
    // unpaid/pending = earned − paid (the backend trigger keeps unpaid_commission on this rule)
    commission:R?.total_commission||0, unpaid:R?.unpaid_commission||0, paid:(R?.total_payoff||0)+(R?.paid_commission||0),
    volume:R?.total_volume||0, deposits:R?.period?.deposits||0, withdrawals:R?.period?.withdrawals||0, balance:R?.balance||0,
  } : {
    clients:145, active:89, ftd:34, nda:21, leads:223, verified:120, subIbs:4,
    commission:24800, unpaid:3200, paid:21600, volume:8420, deposits:248000, withdrawals:42000, balance:3200,
  };

  // DESK RULE (Jul 2026): a registered person with NO deposit is still a LEAD (a verified one);
  // CLIENT means at least ONE deposit. Everything below (KPIs, tabs, funnel) uses this split.
  const leadsList  = useMemo(() => clients.filter((c:any) => (c.dep||0) <= 0), [clients]);
  const fundedList = useMemo(() => clients.filter((c:any) => (c.dep||0) >  0), [clients]);
  // FTD = the customer's FIRST-EVER deposit was made under THIS IB (they were brought in by him);
  // deposited customers whose first deposit was elsewhere = ADDITIONAL accounts, not his FTDs.
  const ftdList  = useMemo(() => fundedList.filter((c:any) => c.ftd_here !== false), [fundedList]);
  const addlList = useMemo(() => fundedList.filter((c:any) => c.ftd_here === false), [fundedList]);
  // Trading accounts tab = EVERY account of a deposited person, one row each (name repeats);
  // person-level lists above keep the KPIs/funnel person-true.
  const tradingAccounts = useMemo(() => {
    const funded = new Set(fundedList.map((c:any) => c.cus));
    return accounts.filter((a:any) => funded.has(a.cus));
  }, [accounts, fundedList]);
  const topClients = useMemo(() => [...fundedList].sort((a:any,b:any)=>(b.volume||0)-(a.volume||0)).slice(0,8), [fundedList]);
  const campaigns = useMemo(() => {
    const m:any = {};
    clients.forEach((c:any) => {
      const key = c.campaign || 'Direct';
      if (!m[key]) m[key] = { name:key, leads:0, ftds:0, deposits:0, volume:0 };
      m[key].leads++; m[key].volume += (c.volume||0);
      if ((c.dep||0) > 0) { m[key].ftds++; m[key].deposits += (c.dep||0); }
    });
    return Object.values(m).sort((a:any,b:any)=>b.deposits-a.deposits);
  }, [clients]);
  const commissions = preview ? (R?.commissions || []) : MOCK_COMMISSIONS;

  // tier progression: gap to next level — criteria RESET at the IB's last promotion/demotion,
  // so progress counts from that date (backend tier_progress); IBs never promoted count all-time.
  const TP:any = (preview && R?.tier_progress) || null;
  const REQ:any = (preview && R?.tier_next) || null;   // desk-editable requirements for the next grade
  const tierGaps = NT ? [
    { l:'Deposits',               cur: TP ? TP.deposits : k.deposits, tgt: REQ ? REQ.min_deposit  : NT.req.deposit, fmt:usdK },
    { l:'Lots · monthly average', cur: TP ? TP.lots_avg : 0,          tgt: REQ ? REQ.min_lots_avg : NT.req.lots,    fmt:num  },
    { l:'New clients',            cur: TP ? TP.nda      : k.nda,      tgt: REQ ? REQ.min_accounts : NT.req.ftd,     fmt:num  },
  ] : [];

  const tabs = [
    { key:'dashboard', label:t('nav.dashboard') }, { key:'clients', label:t('nav.clients') },
    { key:'leads', label:t('nav.leads') }, { key:'trades', label:t('nav.trades') },
    { key:'campaigns', label:t('nav.campaigns') }, { key:'challenges', label:t('nav.challenges') },
    { key:'subibs', label:t('nav.subibs') },
    { key:'marketing', label:t('nav.marketing') },
    { key:'earnings', label:t('nav.earnings') }, { key:'profile', label:t('nav.profile') },
  // Challenge Arena is HIDDEN from real IBs for now (still being finished) — visible ONLY when an
  // admin/staff views the portal. `owner` is set ONLY for the real IB (PartnerGate); staff "view as
  // IB" / admin preview leave it falsy, so they still see it.
  ].filter((tb:any) => tb.key !== 'challenges' || !owner);

  // option lists for filters (from the real account rows)
  const countryOpts = useMemo(() => (Array.from(new Set(accounts.map((a:any)=>a.country).filter(Boolean))) as string[]).sort(), [accounts]);
  const cityOpts = useMemo(() => (Array.from(new Set(accounts.map((a:any)=>a.city).filter(Boolean))) as string[]).sort(), [accounts]);
  const campaignOpts = useMemo(() => (Array.from(new Set(accounts.map((a:any)=>a.campaign).filter(Boolean))) as string[]).sort(), [accounts]);

  const periodCutoff = (p:string) => {
    if (p==='all') return null;
    const d = new Date(); d.setHours(0,0,0,0);
    if (p==='today') return d;
    if (p==='this_week') { d.setDate(d.getDate() - ((d.getDay()+6)%7)); return d; }
    if (p==='this_month') { d.setDate(1); return d; }
    if (p==='this_year') { d.setMonth(0,1); return d; }
    if (p==='last_30') { d.setDate(d.getDate()-30); return d; }
    if (p==='last_90') { d.setDate(d.getDate()-90); return d; }
    return null;
  };
  // account TYPE from the MT group (STD / Zero / VIP / Cent / ECN)
  const acctTypeOf = (g:string) => {
    const u = String(g || '').toUpperCase();
    if (!u) return '—';
    if (u.includes('CENT')) return 'Cent';
    if (u.includes('ZERO')) return 'Zero';
    if (u.includes('VIP'))  return 'VIP';
    if (u.includes('ECN'))  return 'ECN';
    if (u.includes('IB'))   return 'IB';
    return 'STD';
  };
  // FTD/NDA are per-CUSTOMER events: only the account that received the customer's FIRST deposit
  // is the FTD (the one the dashboard KPI counts, deduped by customer_no). A customer's OTHER
  // accounts under this IB are additional accounts, not new FTDs — so tag exactly ONE FTD account
  // per customer. This makes the list's FTD/NDA counts equal the dashboard KPI.
  const ftdPrimary = useMemo(() => {
    const byCus:any = {};
    accounts.forEach((a:any) => {
      if (a.ftd_here === false) return;                            // their first deposit was elsewhere
      const p = byCus[a.cus];
      if (!p || (a.first_deposit||'9999') < (p.first_deposit||'9999')) byCus[a.cus] = a;
    });
    const s = new Set<any>(); Object.values(byCus).forEach((a:any)=>s.add(a.login)); return s;
  }, [accounts]);
  // one place decides a row's status — the badge AND the status filter both use it
  const statusOf = (c:any) => (c.ftd_here === false || !ftdPrimary.has(c.login)) ? 'additional'
    : (c.is_nda || c.nda_review === 'approved') ? 'nda'
    : c.nda_pending ? 'nda_pending'          // yellow: unique FTD, still under the 1.0 Gold+FX lot floor
    : c.nda_review === 'pending' ? 'review' : 'ftd';
  const filteredClients = useMemo(() => {
    const cut = periodCutoff(cliPeriod);
    let list = tradingAccounts.filter((c:any) =>
      (!cliSearch || `${c.name||''} ${c.login} ${c.account_number||''} ${c.cus} ${c.country||''}`.toLowerCase().includes(cliSearch.toLowerCase()))
      && (!cliCountry || c.country===cliCountry)
      && (!cliCity || c.city===cliCity)
      && (!cliStatus || statusOf(c)===cliStatus)
      && (!cut || (c.first_deposit && new Date(c.first_deposit) >= cut)));
    const dir = cliSort.dir==='asc' ? 1 : -1;
    list = [...list].sort((a:any,b:any)=>((a[cliSort.col]||0)-(b[cliSort.col]||0))*dir);
    return list;
  }, [tradingAccounts, cliSearch, cliCountry, cliCity, cliStatus, cliPeriod, cliSort]);
  // all-time NDA count exactly as it appears in THIS list (per-customer) — the dashboard KPI uses it
  // so the headline number and the "NDA" status filter always agree.
  const ndaCount = useMemo(() => tradingAccounts.filter((a:any)=>statusOf(a)==='nda').length, [tradingAccounts, ftdPrimary]);
  const toggleSort = (col:string) => setCliSort(s => s.col===col ? { col, dir:s.dir==='asc'?'desc':'asc' } : { col, dir:'desc' });

  // LEADS = account-holders with no deposit (REAL verification, not the clients-page rule)
  // + PURE leads registered under the IB with no trading account yet (from the leads table).
  // The IB sees the actual phone/email so he can call and follow up (desk rule Jul 15).
  const allLeads = useMemo(() => {
    const acc = leadsList.map((c:any) => ({
      name: c.name || '—', phone: c.phone || '', email: c.email || '',
      phone_v: !!c.phone_v_real, email_v: !!c.email_v_real, kyc: c.kyc_real || '',
      acct: c.account_number || c.login, reg: c.reg, country: c.country || '', city: c.city || '',
      campaign: c.campaign || 'Direct',
    }));
    const pure = ((preview && R?.lead_rows) || []).map((l:any) => ({
      name: l.name || '—', phone: l.phone || '', email: l.email || '',
      phone_v: !!l.phone_verified, email_v: !!l.email_verified, kyc: l.kyc || '',
      acct: null, reg: l.reg || '', country: l.country || '', city: l.city || '',
      campaign: l.stage || 'No account yet',
    }));
    return [...acc, ...pure];
  }, [leadsList, R, preview]);
  const filteredLeads = useMemo(() => allLeads.filter((c:any) => {
    const isVer = c.phone_v || c.email_v || c.kyc === 'verified';
    return (!leadSearch || `${c.name} ${c.phone} ${c.email} ${c.acct||''}`.toLowerCase().includes(leadSearch.toLowerCase()))
      && (!leadCountry || c.country===leadCountry)
      && (!leadCity || c.city===leadCity)
      && (!leadCampaign || c.campaign===leadCampaign)
      && (!leadVer || (leadVer==='ver' ? isVer : !isVer));
  // newest registrations first; leads with no known date sink to the bottom
  }).sort((a:any,b:any)=> String(b.reg||'').localeCompare(String(a.reg||''))),
  [allLeads, leadSearch, leadCountry, leadCity, leadCampaign, leadVer]);

  const loadingPreview = preview && !R;

  // Challenge view: a REAL IB (preview) renders ONLY live chData — never the sample missions
  // (tapping a mock CLAIM would post fake keys + celebrate money that doesn't exist). While the
  // first fetch is in flight the arena shows a loading screen instead.
  const chLoading = preview && !chData;
  const cv:any = preview ? (chData || { career:[], weekly:[], seconds_to_reset:0 }) : {
    career: CH1.map((c:any) => ({ key:'c'+c.id, stage:c.stage, name:c.name, desc:c.desc, reward:c.reward, target:{},
      status: c.status==='completed' ? 'claimed' : c.status==='active' ? 'active' : 'available',
      progress:{}, pct:c.progress||0, seconds_left: c.status==='active' ? 26*86400 : null })),
    weekly: CH2.map((c:any) => ({ key:'w'+c.id, emoji:c.emoji, name:c.name, desc:c.desc, target:c.target, reward:c.reward,
      progress:c.progress, pct:Math.min(100,Math.round(c.progress/c.target*100)), ready:c.progress>=c.target, claimed:false })),
    seconds_to_reset: 4*86400,
  };
  // ready to claim = weekly READY rewards + completed (unclaimed) CAREER rewards
  const ch2ToClaim = (cv.weekly||[]).filter((w:any)=>w.ready && !w.claimed).reduce((s:number,w:any)=>s+(w.reward||0),0)
                   + (cv.career||[]).filter((c:any)=>c.status==='completed').reduce((s:number,c:any)=>s+(c.reward||0),0);

  return (
    <div className="ibp" dir={rtl?'rtl':'ltr'} style={{ height:'100%', overflowY:'auto', background:C.bg, color:C.text, fontFamily:SANS, direction:rtl?'rtl':'ltr' }}>

      {/* ── UNDER-REVIEW bar (pending application) ─────────────────────────────────── */}
      {pending && (
        <div style={{ position:'sticky', top:0, zIndex:60, display:'flex', alignItems:'center', gap:10, flexWrap:'wrap',
          padding:'10px 18px', background:'linear-gradient(90deg,#fff4d6,#ffe7a6)', color:'#7a5b00',
          borderBottom:'1px solid #f0d48a', fontSize:12.5, fontWeight:700 }}>
          <span style={{ fontSize:15 }}>🟡</span>
          <span>{uiLang==='ar'
            ? 'طلب انضمامك كشريك قيد المراجعة. يمكنك استكشاف بوابتك — تظهر عملاؤك وعمولتك ورابط الإحالة بمجرد اعتماد فريقنا لك.'
            : <>Your partner application is <b>under review</b>. Explore your portal — your clients, commission and referral link switch on once our desk approves you.</>}</span>
        </div>
      )}

      {/* ── FIRST-LOGIN ONBOARDING + AGREEMENT (real IB only) ─────────────────────── */}
      {onboard && agreement && (() => {
        const AR = uiLang === 'ar';
        const slides:any[] = [
          { icon:'🎉', title: AR?'مرحباً بك في بوابة الشريك':'Welcome to your Partner Portal',
            desc: AR?'هذه لوحة القيادة الخاصة بك كوسيط مُعرِّف لدى TNFX. جولة سريعة ثم تكون جاهزاً.':'This is your command center as a TNFX Introducing Broker. A quick tour, then you\'re ready to grow.' },
          { icon:'📊', title: AR?'لوحة المعلومات':'Your Dashboard',
            desc: AR?'مؤشرات الأداء المباشرة، رابط الإحالة الخاص بك، وتقدّمك نحو المستوى التالي — بنظرة واحدة.':'Live KPIs, your referral link, and progress toward your next IB level — all at a glance.' },
          { icon:'👥', title: AR?'حسابات التداول':'Trading Accounts',
            desc: AR?'كل عميل تُعرّفه مع حالته: 🟢 عميل جديد يُحتسب، 🟡 قيد التفعيل، 🔴 غير محتسب. فقط العملاء الجدد الفعليون يُحتسبون لترقيتك.':'Every client you introduce, colour-coded: 🟢 New Client counts, 🟡 warming up, 🔴 not counted. Only genuine new clients count toward your promotion.' },
          { icon:'🌱', title: AR?'العملاء المحتملون':'Leads',
            desc: AR?'أشخاص مُسجّلون تحتك ولم يودعوا بعد. اتصل بهم وتابعهم — إيداع واحد يحوّلهم إلى عملائك.':'People registered under you who haven\'t deposited yet. Call and follow up — one deposit makes them your client.' },
          { icon:'📈', title: AR?'الصفقات والعمولات':'Trades & Commission',
            desc: AR?'تابع تداولات عملائك والعمولة التي تكسبها لكل عقد (لوت) — محدّثة مباشرة.':'Track your clients\' trading and the commission you earn per lot — updated live.' },
          { icon:'🎨', title: AR?'الحملات واللافتات':'Campaigns & Banners',
            desc: AR?'أنشئ حملات إحالة وولّد لافتات TNFX احترافية بلغتك لتنمية شبكتك.':'Create referral campaigns and generate branded TNFX banners in your language to grow your network.' },
          { icon:'💰', title: AR?'الأرباح والسحب':'Earnings & Withdrawals',
            desc: AR?'اطلب السحب والتحويل من محفظة عمولاتك. يُفتح السحب عند المستوى 6 — استمر بجلب عملاء حقيقيين لترقيتك.':'Request withdrawals & transfers from your commission wallet. Withdrawals unlock at Level 6 — keep introducing genuine clients to get promoted.' },
          { icon:'📜', agreement:true, title: AR?'اتفاقية الوسيط المُعرِّف':'IB Agreement' },
        ];
        const last = slides.length - 1;
        const s = slides[Math.min(obStep, last)];
        const onLast = obStep >= last;
        return (
          <div className="ibp-sheet-back" style={{ position:'fixed', inset:0, zIndex:90, background:'rgba(9,12,22,0.78)', display:'flex', alignItems:'center', justifyContent:'center', padding:16 }}>
            <div className="ibp-sheet" onClick={e=>e.stopPropagation()} dir={rtl?'rtl':'ltr'}
              style={{ width:'100%', maxWidth:520, maxHeight:'90vh', display:'flex', flexDirection:'column', borderRadius:18, overflow:'hidden', background:C.bg, border:'1px solid #2c3444', boxShadow:'0 30px 80px rgba(0,0,0,0.55)' }}>
              <div style={{ padding:'13px 16px', background:'linear-gradient(118deg,#12151d,#1b2130 60%,#0d1016)', color:'#fff', display:'flex', alignItems:'center', gap:10 }}>
                <img src={tnfxLogo} alt="TNFX" style={{ height:20 }} />
                <div style={{ flex:1, fontSize:12.5, fontWeight:800, color:'#c9b78a' }}>{AR?'جولة تعريفية':'Getting started'}</div>
                <div style={{ fontSize:11, color:'rgba(255,255,255,0.6)' }}>{obStep+1}/{slides.length}</div>
              </div>
              <div style={{ display:'flex', gap:5, padding:'10px 16px 0' }}>
                {slides.map((sl:any,i:number)=><div key={i} style={{ flex:1, height:4, borderRadius:9, background: i<=obStep ? (sl.hot?TNFX_ORANGE:C.blue) : C.border }} />)}
              </div>
              <div style={{ flex:1, overflowY:'auto', padding:'22px 22px 8px' }}>
                {!s.agreement ? (
                  <div style={{ textAlign:'center', padding:'8px 0 14px' }}>
                    <div style={{ width:84, height:84, borderRadius:'50%', margin:'4px auto 16px', display:'flex', alignItems:'center', justifyContent:'center', fontSize:40,
                       background: s.hot ? 'linear-gradient(135deg,#ff6a00,#ff9500)' : C.blueBg, boxShadow: s.hot?'0 10px 30px rgba(255,120,0,0.35)':'none' }}>{s.icon}</div>
                    {s.hot && <div style={{ fontSize:11, fontWeight:900, letterSpacing:'.08em', color:TNFX_ORANGE, marginBottom:6 }}>{AR?'⭐ لا تفوّتها':'⭐ DON\'T MISS THIS'}</div>}
                    <div style={{ fontSize:21, fontWeight:900, color:C.text, marginBottom:10 }}>{s.title}</div>
                    <div style={{ fontSize:13.5, color:C.text2, lineHeight:1.7, maxWidth:400, margin:'0 auto' }}>{s.desc}</div>
                  </div>
                ) : (
                  <div>
                    <div style={{ textAlign:'center', marginBottom:14 }}>
                      <div style={{ fontSize:34 }}>📜</div>
                      <div style={{ fontSize:19, fontWeight:900, color:C.text, marginTop:6 }}>{s.title}</div>
                      <div style={{ fontSize:11.5, color:C.text3, marginTop:3 }}>{AR?'النسخة':'Version'} {agreement.version}</div>
                    </div>
                    <div style={{ maxHeight:230, overflowY:'auto', border:`1px solid ${C.border}`, borderRadius:12, padding:'12px 14px', background:C.card, textAlign: rtl?'right':'left' }}>
                      {(agreement.sections||[]).map((sec:any,i:number)=>(
                        <div key={i} style={{ marginBottom:12 }}>
                          <div style={{ fontSize:12.5, fontWeight:800, color:C.text, marginBottom:4 }}>{sec.h}</div>
                          <div style={{ fontSize:11.5, color:C.text2, lineHeight:1.65, whiteSpace:'pre-line' }}>{sec.b}</div>
                        </div>
                      ))}
                      {agreement.url && <a href={agreement.url} target="_blank" rel="noreferrer" style={{ fontSize:11.5, color:C.blue, fontWeight:700 }}>{AR?'اقرأ الاتفاقية الكاملة ←':'Read the full agreement →'}</a>}
                    </div>
                    <label style={{ display:'flex', alignItems:'flex-start', gap:9, marginTop:14, cursor:'pointer' }}>
                      <input type="checkbox" checked={obAgree} onChange={e=>setObAgree(e.target.checked)} style={{ marginTop:2, width:17, height:17, flexShrink:0 }} />
                      <span style={{ fontSize:12.5, color:C.text, lineHeight:1.5 }}>{AR?'لقد قرأت وأوافق على اتفاقية الوسيط المُعرِّف لدى TNFX، بما في ذلك تعريف NDA وقاعدة عمولة الحسابات الذاتية/المرتبطة وقفل السحب للمستوى 5 وحق TNFX في الإيقاف أو خفض المستوى في أي وقت.':'I have read and I agree to the TNFX Introducing Broker Agreement, including the NDA definition, the self/related-account commission rule, the Level-5 withdrawal lock, and TNFX\'s right to suspend or demote at any time.'}</span>
                    </label>
                  </div>
                )}
              </div>
              <div style={{ display:'flex', gap:10, padding:'12px 16px 16px', borderTop:`1px solid ${C.border}` }}>
                {obStep>0 && <button onClick={()=>setObStep((x:number)=>x-1)} style={{ ...S.btnGhost, padding:'11px 16px' }}>{AR?'رجوع':'Back'}</button>}
                <div style={{ flex:1 }} />
                {!onLast
                  ? <button onClick={()=>setObStep((x:number)=>x+1)} style={{ ...S.btnPri, padding:'11px 22px', ...(s.hot?{background:TNFX_ORANGE}:{}) }}>{AR?'التالي':'Next'} →</button>
                  : <button onClick={acceptAgreement} disabled={!obAgree||obSaving}
                      style={{ ...S.btnPri, padding:'11px 22px', background:(!obAgree||obSaving)?C.text3:C.green, cursor:(!obAgree||obSaving)?'not-allowed':'pointer' }}>
                      {obSaving?(AR?'جارٍ الحفظ…':'Saving…'):(AR?'أوافق وأبدأ':'Agree & Get Started')}</button>}
              </div>
            </div>
          </div>
        );
      })()}

      {/* ── Header — dark navy bar (matches the old partner top bar it replaced) ── */}
      <div style={{ background:'#101828', borderBottom:'1px solid #1c2b47', position:'sticky', top:0, zIndex:20 }}>
        <div className="ibp-head" style={{ maxWidth:1360, margin:'0 auto', padding:'13px 22px', display:'flex', alignItems:'center', justifyContent:'space-between', gap:10, flexWrap:'wrap' }}>
          <div style={{ display:'flex', alignItems:'center', gap:13, minWidth:0 }}>
            {preview && onBack && <button onClick={onBack} style={{ ...S.btnGhost, padding:'7px 12px' }} title="Back to IB Admin">← Back</button>}
            <div style={{ background:'#0b1220', borderRadius:9, padding:'7px 10px', display:'flex', alignItems:'center' }}>
              <img src={tnfxLogo} alt="TNFX" style={{ height:22, width:'auto', display:'block' }} />
            </div>
            <div className="ibp-hide-sm">
              <div style={{ fontSize:15, fontWeight:700, color:'#fff', letterSpacing:'-.2px' }}>Partner Portal</div>
              <div style={{ fontSize:11, color:'#98a2b3' }}>TNFX Introducing Broker</div>
            </div>
            {/* badge + back only when opened from INSIDE the admin app (onBack given);
                a real IB (or the exact-view new tab) sees the portal with no admin traces */}
            {preview && onBack && <span className="ibp-hide-sm" style={{ ...badge(C.amberBg, C.amber), marginLeft:4 }}>👁 Admin preview</span>}
          </div>
          <div style={{ display:'flex', alignItems:'center', gap:9, flexShrink:0, marginLeft:'auto' }}>
            {/* compact flag-only language picker — options limited to English + the IB's country language(s) */}
            <LangPicker value={uiLang} options={langOptions} onPick={setLang} />
            {/* notification bell */}
            <div style={{ position:'relative' }}>
              <button onClick={()=>{ setShowBell(v=>!v); if(!showBell && notifs.unread>0){ apiPost(`/ibs/${ibId}/notifications/read`,{}).then(()=>loadNotifs()); } }}
                title="Notifications" style={{ position:'relative', background:'none', border:'1px solid rgba(255,255,255,0.16)', borderRadius:9, width:36, height:36, cursor:'pointer', fontSize:16 }}>🔔
                {notifs.unread>0 && <span style={{ position:'absolute', top:-5, right:-5, minWidth:16, height:16, padding:'0 3px', borderRadius:99, background:C.red, color:'#fff', fontSize:10, fontWeight:800, display:'flex', alignItems:'center', justifyContent:'center' }}>{notifs.unread>9?'9+':notifs.unread}</span>}
              </button>
              {showBell && (
                <div className="ibp-bell-menu" style={{ position:'absolute', right:0, top:44, width:320, maxWidth:'92vw', background:C.card, border:`1px solid ${C.border}`, borderRadius:12, boxShadow:'0 12px 40px rgba(16,24,40,0.18)', zIndex:200, overflow:'hidden' }}>
                  <div style={{ padding:'11px 14px', borderBottom:`1px solid ${C.border}`, fontWeight:700, fontSize:13, color:C.text }}>Notifications</div>
                  <div style={{ maxHeight:360, overflowY:'auto' }}>
                    {(notifs.items||[]).length===0 && <div style={{ padding:20, textAlign:'center', color:C.text3, fontSize:12.5 }}>Nothing yet.</div>}
                    {(notifs.items||[]).map((n:any)=>(
                      <div key={n.id} style={{ padding:'11px 14px', borderBottom:`1px solid ${C.border}`, background: n.read?'transparent':C.blueBg }}>
                        <div style={{ fontSize:12.5, fontWeight:700, color:C.text }}>{n.title}</div>
                        {n.body && <div style={{ fontSize:11.5, color:C.text2, marginTop:2 }}>{n.body}</div>}
                        <div style={{ fontSize:10.5, color:C.text3, marginTop:3 }}>{n.at ? String(n.at).replace('T',' ').slice(0,16) : ''}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
            <div className="ibp-idblock" style={{ textAlign:'right' }}>
              {/* desktop: full name · mobile: first name only */}
              <div style={{ fontSize:13, fontWeight:700, color:'#fff' }}>
                <span className="ibp-hide-sm">{ibName}</span>
                <span className="ibp-only-sm">{String(ibName||'').trim().split(/\s+/)[0]}</span>
              </div>
              {/* tier + IB code — folds away on phones (ibp-idsub) */}
              <div className="ibp-idsub" style={{ fontSize:11.5, color:'#98a2b3' }}>
                <span style={{ ...badge(T.bg, T.color), padding:'2px 8px' }}>{T.icon} {tierName} · L{level}</span>
                <span style={{ color:'#8fa3c8', marginLeft:6 }}>IB code: <b style={{ color:'#cdd8ea' }}>{R?.ext_ib_id ?? ibCode ?? '—'}</b></span>
              </div>
              {/* available balance — stays on mobile (lifetime part folds) */}
              <div onClick={()=>setTab('earnings')} title="Available to withdraw — open Earnings"
                style={{ fontSize:13, fontWeight:800, color:'#3ddc8f', marginTop:3, cursor:'pointer' }}>
                {usd(payAvailable)} <span style={{ fontSize:10, fontWeight:600 }}>available</span>
                <span className="ibp-idsub" style={{ color:'#8fa3c8', fontWeight:500, fontSize:9.5, marginLeft:7 }}>lifetime {usd(k.commission)}</span>
              </div>
            </div>
            {/* avatar → account menu (sign-out lives here now that the top partner bar is gone) */}
            <div style={{ position:'relative' }}>
              <div onClick={()=>setShowUserMenu(v=>!v)} title={ibName}
                style={{ width:38, height:38, borderRadius:'50%', background:C.blueBg, color:C.blue, display:'flex', alignItems:'center', justifyContent:'center', fontSize:13, fontWeight:700, cursor:'pointer', userSelect:'none' }}>{initialsOf(ibName)}</div>
              {showUserMenu && (<>
                <div onClick={()=>setShowUserMenu(false)} style={{ position:'fixed', inset:0, zIndex:190 }} />
                <div style={{ position:'absolute', right:0, top:46, width:230, background:C.card, border:`1px solid ${C.border}`, borderRadius:12, boxShadow:'0 12px 40px rgba(16,24,40,0.18)', zIndex:200, overflow:'hidden' }}>
                  <div style={{ padding:'12px 14px', borderBottom:`1px solid ${C.border}` }}>
                    <div style={{ fontSize:13, fontWeight:700, color:C.text, whiteSpace:'nowrap', overflow:'hidden', textOverflow:'ellipsis' }}>{ibName}</div>
                    <div style={{ fontSize:11, color:C.text3, marginTop:2 }}>IB code: {R?.ext_ib_id ?? ibCode ?? '—'}</div>
                  </div>
                  <div onClick={()=>{ setShowUserMenu(false); setTab('profile'); }} style={{ padding:'11px 14px', fontSize:13, color:C.text2, cursor:'pointer' }}
                    onMouseEnter={e=>e.currentTarget.style.background=C.blueBg} onMouseLeave={e=>e.currentTarget.style.background='transparent'}>👤 Profile</div>
                  {onInstall && <div onClick={()=>{ setShowUserMenu(false); onInstall(); }} style={{ padding:'11px 14px', fontSize:13, color:C.text2, cursor:'pointer' }}
                    onMouseEnter={e=>e.currentTarget.style.background=C.blueBg} onMouseLeave={e=>e.currentTarget.style.background='transparent'}>📲 Install app</div>}
                  {onLogout && <div onClick={()=>{ setShowUserMenu(false); onLogout(); }} style={{ padding:'11px 14px', fontSize:13, fontWeight:700, color:C.red, cursor:'pointer', borderTop:`1px solid ${C.border}` }}
                    onMouseEnter={e=>e.currentTarget.style.background=C.redBg} onMouseLeave={e=>e.currentTarget.style.background='transparent'}>⏻ Sign out</div>}
                </div>
              </>)}
            </div>
          </div>
        </div>
        <div className="ibp-tabs" style={{ maxWidth:1360, margin:'0 auto', padding:'0 22px', display:'flex', gap:2, overflowX:'auto' }}>
          {tabs.map(t => {
            const on = tab===t.key;
            return <div key={t.key} className="ibp-tab" onClick={()=>setTab(t.key)}
              style={{ padding:'12px 15px', fontSize:13, fontWeight:on?700:500, cursor:'pointer', whiteSpace:'nowrap', color:on?'#fff':'#98a2b3', borderBottom:`2.5px solid ${on?'#ff8b3d':'transparent'}` }}>{t.label}</div>;
          })}
        </div>
        {/* ── Client drill-down modal (privacy-safe account activity) ── */}
        {drill && (
          <div onClick={()=>setDrill(null)} style={{ position:'fixed', inset:0, zIndex:150, background:'rgba(16,24,40,0.5)', display:'flex', alignItems:'center', justifyContent:'center', padding:16 }}>
            <div onClick={e=>e.stopPropagation()} dir="ltr" style={{ ...S.card, width:520, maxWidth:'96vw', maxHeight:'88vh', overflowY:'auto', padding:20 }}>
              {drill.loading ? <div style={{ padding:30, textAlign:'center', color:C.text3 }}>Loading…</div> : (<>
                <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:14 }}>
                  <div>
                    <div style={{ fontSize:16, fontWeight:800, color:C.text }}>Account #{drill.login}</div>
                    <div style={{ fontSize:12, color:C.text3 }}>{drill.country||''} · {drill.platform} · {drill.is_nda?'🟢 NDA':'first-deposit client'}</div>
                  </div>
                  <button onClick={()=>setDrill(null)} style={{ ...S.btnGhost, padding:'5px 12px' }}>✕</button>
                </div>
                <div className="ibp-g3" style={{ display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:10, marginBottom:14 }}>
                  <MiniStat label="Deposits" value={usd(drill.deposits)} accent={C.green} />
                  <MiniStat label="Withdrawals" value={usd(drill.withdrawals)} accent={C.amber} />
                  <MiniStat label="Total lots" value={`${num(drill.total_lots)}`} accent={C.purple} />
                </div>
                <div style={{ fontSize:12.5, fontWeight:700, color:C.text, marginBottom:8 }}>Recent trades <span style={{ fontWeight:400, color:C.text3 }}>· first deposit {drill.first_deposit||'—'}</span></div>
                <div style={{ ...S.card, overflow:'hidden' }}>
                  <table style={{ width:'100%', borderCollapse:'collapse' }}>
                    <thead><tr>{['Date','Symbol','Side','Lots'].map(h=><th key={h} style={{ ...S.th, fontSize:10.5 }}>{h}</th>)}</tr></thead>
                    <tbody>
                      {(drill.trades||[]).map((tr:any,i:number)=>(
                        <tr key={i} className="ibp-row">
                          <td className="cm" style={{ ...S.td, fontSize:12 }}>{tr.date}</td>
                          <td style={{ ...S.td, fontSize:12 }}>{tr.symbol}</td>
                          <td style={{ ...S.td, fontSize:12 }}><span style={badge(tr.side==='BUY'?C.greenBg:C.redBg, tr.side==='BUY'?C.green:C.red)}>{tr.side}</span></td>
                          <td style={{ ...S.td, fontSize:12 }}>{tr.lots}</td>
                        </tr>
                      ))}
                      {(drill.trades||[]).length===0 && <tr><td colSpan={4} style={{ ...S.td, textAlign:'center', color:C.text3, padding:18 }}>No trades yet</td></tr>}
                    </tbody>
                  </table>
                </div>
              </>)}
            </div>
          </div>
        )}
      </div>

      {/* ══ DASHBOARD ══ */}
      {tab==='dashboard' && (
        <div className="ibp-page" style={S.page}>
          {/* ── Announcements from the desk ── */}
          {anns.map((a:any)=>{
            const tn = a.tone==='promo' ? { bg:C.greenBg, ac:C.green } : a.tone==='warn' ? { bg:C.amberBg, ac:C.amber } : { bg:C.blueBg, ac:C.blue };
            return (
              <div key={a.id} style={{ ...S.card, padding:'13px 16px', marginBottom:12, borderLeft:`3px solid ${tn.ac}`, background:tn.bg }}>
                <div style={{ fontSize:13, fontWeight:800, color:C.text }}>📣 {a.title}</div>
                {a.body && <div style={{ fontSize:12, color:C.text2, marginTop:3, lineHeight:1.5 }}>{a.body}</div>}
              </div>
            );
          })}
          {/* ── HERO: lifetime earnings + live 30d pulse + one-tap actions ── */}
          <div className="ibp-hero" style={{ position:'relative', overflow:'hidden', borderRadius:14, marginBottom:16,
            background:'linear-gradient(118deg,#0b1220 0%,#101d38 48%,#0d2b26 100%)', border:'1px solid #1c2b47',
            boxShadow:'0 14px 40px rgba(11,18,32,0.35)', padding:'22px 26px', color:'#eef2f9' }}>
            {/* ambient glows */}
            <div style={{ position:'absolute', top:-70, right:-40, width:260, height:260, borderRadius:'50%', background:'radial-gradient(circle, rgba(61,220,143,0.16), transparent 65%)', pointerEvents:'none' }} />
            <div style={{ position:'absolute', bottom:-90, left:'34%', width:300, height:300, borderRadius:'50%', background:'radial-gradient(circle, rgba(47,107,255,0.14), transparent 65%)', pointerEvents:'none' }} />
            <div className="ibp-hero-in" style={{ position:'relative', display:'flex', justifyContent:'space-between', alignItems:'center', gap:22, flexWrap:'wrap' }}>
              <div style={{ minWidth:230 }}>
                {/* HIGHLIGHT = ready to withdraw (the money the IB can take now); lifetime earned moves below */}
                <div style={{ fontSize:11, fontWeight:800, letterSpacing:'.14em', textTransform:'uppercase', color:'#8fa3c8', marginBottom:7 }}>💰 Ready to withdraw</div>
                <div style={{ fontSize:'clamp(30px,4.4vw,44px)', fontWeight:800, letterSpacing:'-1px', lineHeight:1, background:'linear-gradient(92deg,#ffffff,#9fe8c6 70%,#3ddc8f)', WebkitBackgroundClip:'text', WebkitTextFillColor:'transparent' }}>
                  <AnimatedUsd v={payAvailable} />
                </div>
                <div style={{ display:'flex', alignItems:'center', gap:8, marginTop:11, flexWrap:'wrap' }}>
                  <span style={{ padding:'3px 9px', borderRadius:99, fontSize:11.5, fontWeight:800, background:'rgba(255,255,255,0.08)', color:'#cdd8ea' }}>💎 {usd(k.commission)} lifetime earned</span>
                  <DeltaChip pct={commDelta} />
                </div>
              </div>
              <div className="ibp-hero-spark" style={{ textAlign:'right' }}>
                <Spark vals={last30.map((d:any)=>+d.commission||0)} color="#3ddc8f" w={210} h={58} id="hero" />
                <div style={{ fontSize:10.5, color:'#8fa3c8', fontWeight:700, marginTop:5, letterSpacing:'.05em' }}>
                  LAST 30 DAYS · {usd(c30)}{bestDay && (+bestDay.commission||0) > 0 ? <span style={{ color:'#3ddc8f' }}> · best day {usd(+bestDay.commission)}</span> : ''}
                </div>
              </div>
            </div>
            {/* one-tap actions */}
            <div className="ibp-qa" style={{ position:'relative', display:'flex', gap:9, marginTop:18, flexWrap:'wrap' }}>
              {(() => { const qa:React.CSSProperties = { padding:'9px 15px', borderRadius:10, fontSize:12.5, fontWeight:700, cursor:'pointer', border:'1px solid #27395e', background:'rgba(255,255,255,0.05)', color:'#dfe7f5' };
                return (<>
                  <button onClick={copyRef} style={{ ...qa, background: copied==='ref' ? 'rgba(19,168,88,0.25)' : 'linear-gradient(92deg,#2f6bff,#2fa4ff)', border:'none', color:'#fff' }}>
                    {copied==='ref' ? '✓ Link copied!' : '🔗 Copy referral link'}</button>
                  <a href={`https://wa.me/?text=${encodeURIComponent(`Trade with TNFX — open your account here: ${refUrl}`)}`} target="_blank" rel="noreferrer" style={{ ...qa, textDecoration:'none', background:'rgba(37,211,102,0.14)', border:'1px solid rgba(37,211,102,0.4)', color:'#4be084' }}>💬 Share on WhatsApp</a>
                  <button onClick={()=>setTab('earnings')} style={{ ...qa, background:'rgba(19,168,88,0.18)', border:'1px solid rgba(19,168,88,0.5)', color:'#5fe39a' }}>
                    {(R?.ib_level || 5) >= 6 ? `💸 Withdraw ${usd(payAvailable)}` : '🔒 Withdraw · Level 6'}</button>
                  <button onClick={()=>setTab('marketing')} style={qa}>🎨 Get banners</button>
                </>); })()}
            </div>
          </div>

          {/* main KPIs full width */}
          {(() => { const archivedN = accounts.filter((a:any)=>a.is_archived).length; return (
          <div className="ibp-g4" style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:13, marginBottom:16 }}>
            <Kpi label={t('kpi.leads')} value={loadingPreview?'…':num(leadsList.length)} sub={t('kpi.leads_sub')} accent={C.purple} icon="🌱" />
            {/* NDA = counted / total : xx of the yy first-deposit clients are genuinely new (count for promotion) */}
            <Kpi label="NDA" icon="⭐" accent={C.green}
              onInfo={()=>setInfoPop({ title:t('kpi.nda_info_title'),
                body:t('kpi.nda_info_body').replace('{total}', String(num(ftdList.length))).replace('{new}', String(num(ndaCount))) })}
              value={loadingPreview?'…':<span><span style={{ color:C.green }}>{num(ndaCount)}</span><span style={{ color:C.text3, fontWeight:600 }}> / {num(ftdList.length)}</span></span>}
              sub={t('kpi.nda_sub')} />
            {/* total trading accounts the IB introduced, INCLUDING archived (tagged) */}
            <Kpi label={t('nav.clients')} icon="💼" accent={C.blue}
              value={loadingPreview?'…':num(accounts.length)}
              sub={<>{num(accounts.length - archivedN)} {t('kpi.active')}{archivedN>0 && <> · <span style={{ ...badge(C.card2, C.text3), fontSize:10 }}>{num(archivedN)} {t('kpi.archived')}</span></>}</>} />
            <Kpi label={t('kpi.available')} value={loadingPreview?'…':usd(payAvailable)} sub={`${t('kpi.earned_pre')} ${usd(k.commission)}`} accent={C.green} icon="💰" />
          </div>
          ); })()}

          {/* ── ACTIVE CHALLENGE status — appears once a career mission is underway (or ready to claim).
                 Hidden from real IBs while the Challenge Arena is being finished (owner only). ── */}
          {(() => {
            if (owner) return null;   // Challenge Arena hidden from real IBs for now (admin view only)
            const aq = (cv.career||[]).find((c:any)=>c.status==='active') || (cv.career||[]).find((c:any)=>c.status==='completed');
            if (!aq) return null;
            const ready = aq.status==='completed';
            const tgt = aq.target||{}, prog = aq.progress||{};
            const label = (k:string) => k==='nda'?'new clients' : k==='ftd'?'FTDs' : k==='clients'?'clients' : k==='lots'?'lots' : k;
            const parts = Object.keys(tgt).map(k=>`${num(prog[k]||0)} / ${num(tgt[k])} ${label(k)}`);
            return (
              <div style={{ ...S.card, padding:'15px 17px', marginBottom:16, display:'flex', alignItems:'center', gap:17, flexWrap:'wrap',
                border:`1.5px solid ${ready?C.green:TNFX_ORANGE}66`, background:`linear-gradient(120deg, ${ready?C.greenBg:'#fff3ea'}, ${C.card} 62%)` }}>
                <Ring pct={ready?100:aq.pct||0} size={64} stroke={6.5} color={ready?C.green:TNFX_ORANGE}>
                  <span style={{ fontSize:14, fontWeight:900, color:ready?C.green:TNFX_ORANGE }}>{ready?'✓':`${aq.pct||0}%`}</span>
                </Ring>
                <div style={{ flex:'1 1 200px', minWidth:0 }}>
                  <div style={{ fontSize:10.5, fontWeight:800, letterSpacing:'.09em', color:ready?C.green:TNFX_ORANGE }}>
                    {ready?'🎉 MISSION COMPLETE':'⚔️ MISSION IN PROGRESS'}</div>
                  <div style={{ fontSize:15.5, fontWeight:800, color:C.text, margin:'2px 0 5px' }}>{aq.name}</div>
                  {parts.length>0 && <div style={{ fontSize:12, color:C.text2 }}>{parts.join('  ·  ')}</div>}
                  {!ready && aq.seconds_left!=null && <div style={{ fontSize:11.5, color:C.amber, fontWeight:800, marginTop:4 }}>⏱ <Countdown seconds={adjSec(aq.seconds_left)||0} color={C.amber}/> left</div>}
                </div>
                <div style={{ display:'flex', flexDirection:'column', gap:8, alignItems:'flex-end' }}>
                  <RewardPill amount={aq.reward} />
                  <button onClick={()=>setTab('challenges')} className="ibp-cta" style={{ padding:'9px 16px', borderRadius:10, fontSize:12.5, fontWeight:800, cursor:'pointer', border:'none', color:'#fff', minHeight:38,
                    background: ready?'linear-gradient(92deg,#13a858,#3ddc8f)':'linear-gradient(92deg,#ff6a00,#ff9500)' }}>{ready?'🎉 Claim reward':'View challenge →'}</button>
                </div>
              </div>
            );
          })()}

          <div className="ibp-cols" style={{ display:'grid', gridTemplateColumns:'minmax(0,1.75fr) minmax(0,1fr)', gap:16, alignItems:'start' }}>
            {/* LEFT: tier + top clients */}
            <div style={{ display:'flex', flexDirection:'column', gap:16 }}>
              {/* ── performance analytics — interactive daily chart (commission / lots / trades) ── */}
              <div style={{ ...S.card, overflow:'hidden' }}>
                <div style={{ padding:'14px 16px 10px', borderBottom:`1px solid ${C.border}`, display:'flex', justifyContent:'space-between', alignItems:'center', gap:10, flexWrap:'wrap' }}>
                  <span style={{ fontSize:13.5, fontWeight:700 }}>📈 Performance analytics</span>
                  <div style={{ display:'flex', gap:6, flexWrap:'wrap' }}>
                    {([['commission','Commission $'],['lots','Lots'],['trades','Trades']] as [typeof chMetric,string][]).map(([m,l]) => (
                      <button key={m} onClick={()=>setChMetric(m)} style={{ padding:'5px 11px', borderRadius:99, fontSize:11.5, fontWeight:700, cursor:'pointer',
                        border:`1px solid ${chMetric===m?C.blue:C.borderH}`, background:chMetric===m?C.blueBg:'#fff', color:chMetric===m?C.blue:C.text2 }}>{l}</button>
                    ))}
                    <span style={{ width:1, background:C.border, margin:'0 3px' }} />
                    {([30,90] as (30|90)[]).map(r => (
                      <button key={r} onClick={()=>setChRange(r)} style={{ padding:'5px 11px', borderRadius:99, fontSize:11.5, fontWeight:700, cursor:'pointer',
                        border:`1px solid ${chRange===r?C.green:C.borderH}`, background:chRange===r?C.greenBg:'#fff', color:chRange===r?C.green:C.text2 }}>{r}D</button>
                    ))}
                  </div>
                </div>
                <div style={{ padding:'14px 14px 8px' }}>
                  <TrendChart data={daySeries.slice(-chRange)} metric={chMetric}
                    color={chMetric==='commission'?C.green:chMetric==='lots'?C.purple:C.blue}
                    fmt={chMetric==='commission'?usdK:num} />
                </div>
                {/* quick stats strip under the chart */}
                {(() => { const rng = daySeries.slice(-chRange);
                  const tot = sumBy(rng, chMetric), avg = rng.length ? tot/rng.length : 0;
                  const activeDays = rng.filter((d:any)=>+d[chMetric]>0).length;
                  const f = chMetric==='commission' ? usd : num;
                  return (
                    <div style={{ display:'flex', borderTop:`1px solid ${C.border}` }}>
                      {[['Total', f(tot)], ['Daily average', f(avg)], ['Active days', `${activeDays}/${rng.length}`]].map(([l,v],i)=>(
                        <div key={i} style={{ flex:1, padding:'11px 16px', borderLeft:i?`1px solid ${C.border}`:'none' }}>
                          <div style={{ fontSize:10, color:C.text3, fontWeight:700, textTransform:'uppercase', letterSpacing:'.05em' }}>{l}</div>
                          <div style={{ fontSize:16, fontWeight:800, color:C.text, marginTop:3 }}>{v}</div>
                        </div>
                      ))}
                    </div>
                  ); })()}
              </div>

              {/* tier card — live / gamified */}
              {(() => {
                const overall = NT ? Math.round(tierGaps.reduce((s,g)=>s+(g.tgt?Math.min(100,g.cur/g.tgt*100):100),0)/Math.max(1,tierGaps.length)) : 100;
                const remainingMet = NT ? tierGaps.filter(g=>g.cur>=g.tgt).length : 3;
                return (
                /* the WHOLE card lives in the next grade's colour family — strong at the top,
                   very light for the rest — so it reads as ONE section */
                <div style={{ ...S.card, overflow:'hidden',
                  border:`1px solid ${NT ? NT.color+'44' : C.border}`,
                  background: NT ? `linear-gradient(180deg, ${NT.color}0a, ${NT.color}05 55%, #ffffff)` : C.card }}>
                  {/* hero — BIG: Diamond → Legendary on one line, live gradient + shimmer bar */}
                  <div style={{ position:'relative', overflow:'hidden', padding:'22px 24px',
                    background:`linear-gradient(115deg, ${T.color}22, ${NT?NT.color:T.color}30 60%, ${NT?NT.color:T.color}18)` }}>
                    <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', gap:12, flexWrap:'wrap' }}>
                      <div className="ibp-hero-title" style={{ display:'flex', alignItems:'center', gap:9, minWidth:0, overflow:'hidden',
                        fontSize:'clamp(15px, 2.2vw, 21px)', fontWeight:800, color:C.text, whiteSpace:'nowrap' }}>
                        <span className="ibp-float" style={{ fontSize:'1.55em', lineHeight:1 }}>{T.icon}</span> {tierName}
                        {NT && <span style={{ color:C.text3, fontWeight:500 }}>→</span>}
                        {NT && <><span className="ibp-float" style={{ fontSize:'1.55em', lineHeight:1 }}>{NT.icon}</span><span style={{ color:NT.color }}>{NT.name}</span></>}
                      </div>
                      {NT && (
                        <div style={{ textAlign:'right', flexShrink:0, marginLeft:'auto' }}>
                          <div style={{ fontSize:26, fontWeight:800, color:NT.color, lineHeight:1 }}>{overall}%</div>
                          <div style={{ fontSize:11, color:C.text2, fontWeight:600, marginTop:3 }}>on the way 🚀</div>
                        </div>
                      )}
                    </div>
                    {NT && (
                      <div style={{ position:'relative', height:11, borderRadius:99, background:'#ffffffcc', border:`1px solid ${NT.color}33`, overflow:'hidden', marginTop:14 }}>
                        <div className="ibp-bar-fill" style={{ height:'100%', width:`${overall}%`, borderRadius:99, background:`linear-gradient(90deg, ${T.color}, ${NT.color})` }} />
                        <div className="ibp-shimmer" style={{ position:'absolute', inset:0, width:`${overall}%`, borderRadius:99 }} />
                      </div>
                    )}
                  </div>

                  <div style={{ padding:'16px 20px 20px' }}>
                    {/* roadmap with pulsing current node */}
                    <div style={{ display:'flex', alignItems:'center', padding:'0 2px', marginBottom:NT?18:0 }}>
                      {BTIERS.map((t,i) => {
                        const here = t.level===level, passed = t.level < level;
                        return (
                          <React.Fragment key={t.level}>
                            <div style={{ textAlign:'center', minWidth:50 }}>
                              <div className={here?'ibp-pulse':''} style={{ width:here?44:34, height:here?44:34, borderRadius:'50%', margin:'0 auto 5px', display:'flex', alignItems:'center', justifyContent:'center', fontSize:here?19:14,
                                background:(here||passed)?t.bg:C.card2, border:`${here?2.5:1.5}px solid ${(here||passed)?t.color:C.borderH}` }}>{t.icon}</div>
                              <div style={{ fontSize:here?11:9.5, color:(here||passed)?t.color:C.text3, fontWeight:here?700:500 }}>{t.name}</div>
                              {here && <div style={{ fontSize:9, color:C.blue, fontWeight:700 }}>You</div>}
                            </div>
                            {i<BTIERS.length-1 && <div style={{ flex:1, height:3, borderRadius:2, background: passed?`linear-gradient(90deg,${BTIERS[i].color},${BTIERS[i+1].color})`:C.border }} />}
                          </React.Fragment>
                        );
                      })}
                    </div>
                    {/* what's missing for next level */}
                    {NT ? (
                      /* three LIVE meter rows — same colour family as the header, shimmer + a mood
                         emoji per row (🚀 → 💪 → 🔥 → 🎉 as the IB gets closer) */
                      <div style={{ borderTop:`1px solid ${NT.color}26`, paddingTop:14 }}>
                        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'baseline', marginBottom:12 }}>
                          <span style={{ fontSize:13, fontWeight:800, color:NT.color }}>To unlock {NT.icon} {NT.name}</span>
                          {TP?.since && <span style={{ fontSize:11, color:C.text3 }}>counting since {String(TP.since).slice(0,10).split('-').reverse().join('/')}</span>}
                        </div>
                        {tierGaps.map((g,i) => {
                          const pct = g.tgt ? Math.min(100, g.cur/g.tgt*100) : 100;
                          const done = g.cur >= g.tgt;
                          const mood = done ? '🎉' : pct >= 75 ? '🔥' : pct >= 40 ? '💪' : '🚀';
                          return (
                            <div key={i} style={{ marginBottom: i < tierGaps.length-1 ? 14 : 0 }}>
                              <div style={{ display:'flex', justifyContent:'space-between', alignItems:'baseline', marginBottom:5 }}>
                                <span style={{ fontSize:12.5, color:C.text2, fontWeight:600 }}>{mood} {g.l}</span>
                                <span style={{ fontSize:12.5, color:C.text3 }}>
                                  <b style={{ color:C.text }}>{g.fmt(g.cur)}</b> / {g.fmt(g.tgt)}
                                  <span style={{ marginLeft:8, fontWeight:800, color:done?C.green:NT.color }}>{done?'✓ done':`${Math.round(pct)}%`}</span>
                                </span>
                              </div>
                              <div style={{ position:'relative', height:8, borderRadius:99, background:'#ffffff', border:`1px solid ${NT.color}26`, overflow:'hidden' }}>
                                <div className="ibp-bar-fill" style={{ height:'100%', width:`${pct}%`, borderRadius:99,
                                  background: done ? C.green : `linear-gradient(90deg, ${NT.color}99, ${NT.color})` }} />
                                {!done && <div className="ibp-shimmer" style={{ position:'absolute', inset:0, width:`${pct}%`, borderRadius:99 }} />}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    ) : (
                      <div style={{ borderTop:`1px solid ${C.border}`, paddingTop:16, textAlign:'center', fontSize:13, fontWeight:700, color:C.amber }}>👑 You've reached the top grade — Prime IB. Maximum commission rate unlocked!</div>
                    )}
                  </div>
                </div>
                );
              })()}

              {/* top clients */}
              <div style={{ ...S.card, overflow:'hidden' }}>
                <div style={{ padding:'14px 16px', borderBottom:`1px solid ${C.border}`, display:'flex', justifyContent:'space-between', alignItems:'center' }}>
                  <span style={{ fontSize:13.5, fontWeight:700 }}>Top clients by volume</span>
                  <span onClick={()=>setTab('clients')} style={{ fontSize:12, color:C.blue, cursor:'pointer', fontWeight:600 }}>View all →</span>
                </div>
                <table style={{ width:'100%', borderCollapse:'collapse' }}>
                  <thead><tr>{['Account','Country','City','Volume','Status'].map(h=><th key={h} style={S.th}>{h}</th>)}</tr></thead>
                  <tbody>
                    {topClients.map((c:any,i:number)=>(
                      <tr key={i} className="ibp-row">
                        <td className="cb" style={{ ...S.td, fontFamily:'monospace', fontWeight:600 }}>#{c.account_number || c.login}<div style={{ fontSize:11, color:C.text3 }}>{c.cus}</div></td>
                        <td className="cm" style={S.td}>{c.country||'—'}</td>
                        <td className="cm" style={S.td}>{c.city||'—'}</td>
                        <td className="cp" style={{ ...S.td, fontWeight:600 }}>{num(c.volume)} lots</td>
                        <td style={S.td}>{c.ftd_here === false
                          ? <span style={badge(C.card2, C.purple)}>Additional account</span>
                          : c.is_nda
                          ? <span style={badge(C.greenBg, C.green)}>🟢 NDA</span>
                          : c.nda_pending
                          ? <span title={`Traded ${(c.nda_lots||0).toFixed(2)} / 1.0 lot`} style={badge(C.amberBg, C.amber)}>🟡 NDA</span>
                          : <span title={c.relation_reason?`Linked to an existing client — ${c.relation_reason}`:'Linked to an existing client'} style={badge(C.redBg, C.red)}>🔴 NDA</span>}</td>
                      </tr>
                    ))}
                    {topClients.length===0 && <EmptyRow cols={5} loading={loadingPreview} />}
                  </tbody>
                </table>
              </div>
            </div>

            {/* RIGHT: manager + funnel + mini stats */}
            <div style={{ display:'flex', flexDirection:'column', gap:16 }}>
              {/* manager */}
              <div style={{ ...S.card, padding:18 }}>
                <div style={{ fontSize:11, color:C.text3, fontWeight:700, textTransform:'uppercase', letterSpacing:'.06em', marginBottom:13 }}>Your account manager</div>
                <div style={{ display:'flex', alignItems:'center', gap:13, marginBottom:15 }}>
                  <div style={{ width:50, height:50, borderRadius:'50%', background:C.blueBg, color:C.blue, display:'flex', alignItems:'center', justifyContent:'center', fontSize:16, fontWeight:700, overflow:'hidden', flexShrink:0 }}>
                    {manager?.avatar_url ? <img src={manager.avatar_url} alt="" style={{ width:'100%', height:'100%', objectFit:'cover' }} /> : (manager?.name ? initialsOf(manager.name) : '—')}
                  </div>
                  <div style={{ minWidth:0 }}>
                    <div style={{ fontSize:14.5, fontWeight:700, color:C.text }}>{manager?.name || 'Unassigned'}</div>
                    <div style={{ fontSize:12, color:C.text2 }}>{manager?.title || (manager?'Account Manager':'—')}</div>
                  </div>
                </div>
                {manager ? (<>
                  {[{ic:'✉',l:'Email',v:manager.email||'—'},{ic:'📱',l:'Phone',v:manager.phone||'—'},...(manager.department?[{ic:'🏢',l:'Team',v:manager.department}]:[])].map((r:any,i:number)=>(
                    <div key={i} style={{ display:'flex', alignItems:'center', gap:10, padding:'9px 0', borderTop:`1px solid ${C.border}` }}>
                      <span style={{ width:26, height:26, borderRadius:7, background:C.card2, display:'flex', alignItems:'center', justifyContent:'center', fontSize:12 }}>{r.ic}</span>
                      <div style={{ minWidth:0 }}>
                        <div style={{ fontSize:9.5, color:C.text3, textTransform:'uppercase', letterSpacing:'.05em' }}>{r.l}</div>
                        <div style={{ fontSize:12.5, color:C.text, overflow:'hidden', textOverflow:'ellipsis' }}>{r.v}</div>
                      </div>
                    </div>
                  ))}
                  <div style={{ display:'flex', gap:8, marginTop:13 }}>
                    <a href={manager.email?`mailto:${manager.email}`:undefined} style={{ ...S.btnPri, flex:1, textAlign:'center', textDecoration:'none' }}>✉ Email</a>
                    <a href={manager.phone?`tel:${manager.phone}`:undefined} style={{ ...S.btnGhost, flex:1, textAlign:'center', textDecoration:'none' }}>📞 Call</a>
                  </div>
                </>) : <div style={{ fontSize:12.5, color:C.text3, padding:'8px 0' }}>No manager assigned yet.</div>}
              </div>

              {/* funnel */}
              <div style={{ ...S.card, padding:18 }}>
                <div style={{ fontSize:11, color:C.text3, fontWeight:700, textTransform:'uppercase', letterSpacing:'.06em', marginBottom:14 }}>Client funnel</div>
                {(() => {
                  const lead=clients.length, ftd=ftdList.length, nda=ndaCount, mx=Math.max(lead,1);
                  const steps=[{l:'Registered (leads + clients)',v:lead,c:C.purple},{l:'Clients · first deposit with you',v:ftd,c:C.blue},{l:'New clients · genuine & active',v:nda,c:C.green}];
                  return (<>
                    {steps.map((s,i)=>(
                      <div key={i} style={{ marginBottom:13 }}>
                        <div style={{ display:'flex', justifyContent:'space-between', marginBottom:5 }}>
                          <span style={{ fontSize:12, color:C.text2 }}>{s.l}</span>
                          <span style={{ fontSize:14, fontWeight:700, color:s.c }}>{num(s.v)}</span>
                        </div>
                        <Bar pct={s.v/mx*100} color={s.c} />
                      </div>
                    ))}
                    <div style={{ display:'flex', justifyContent:'space-between', marginTop:14, paddingTop:12, borderTop:`1px solid ${C.border}` }}>
                      <span style={{ fontSize:12, color:C.text2 }}>Conversion</span>
                      <span style={{ fontSize:15, fontWeight:700, color:C.green }}>{lead?Math.round(ftd/lead*100):0}%</span>
                    </div>
                    {addlList.length>0 && <div style={{ fontSize:11, color:C.text3, marginTop:8 }}>
                      + {num(addlList.length)} existing customer{addlList.length>1?'s':''} opened additional accounts under you</div>}
                  </>);
                })()}
              </div>

              {/* ── live commission activity (latest eligible trades — commission only, no P&L) ── */}
              <div style={{ ...S.card, overflow:'hidden' }}>
                <div style={{ padding:'14px 16px', borderBottom:`1px solid ${C.border}`, display:'flex', justifyContent:'space-between', alignItems:'center' }}>
                  <span style={{ fontSize:13.5, fontWeight:700 }}>⚡ Live commission feed</span>
                  <span onClick={()=>setTab('trades')} style={{ fontSize:12, color:C.blue, cursor:'pointer', fontWeight:600 }}>All trades →</span>
                </div>
                <div>
                  {recent.map((r:any,i:number) => {
                    const buy = String(r.direction||'').toLowerCase().startsWith('b');
                    return (
                      <div key={i} style={{ display:'flex', alignItems:'center', gap:10, padding:'10px 16px', borderBottom: i<recent.length-1?`1px solid ${C.border}`:'none' }}>
                        <span style={{ width:30, height:30, borderRadius:8, flexShrink:0, display:'flex', alignItems:'center', justifyContent:'center', fontSize:10, fontWeight:800,
                          background: buy?C.greenBg:C.redBg, color: buy?C.green:C.red }}>{buy?'BUY':'SELL'}</span>
                        <div style={{ flex:1, minWidth:0 }}>
                          <div style={{ fontSize:12.5, fontWeight:700, color:C.text }}>{r.symbol} · {(+r.lots||0).toFixed(2)} lots</div>
                          <div style={{ fontSize:10.5, color:C.text3 }}>#{r.login} · {timeAgo(r.close_time) || String(r.close_time||'').slice(0,16).replace('T',' ')}</div>
                        </div>
                        <span style={{ fontSize:13, fontWeight:800, color:C.green, flexShrink:0 }}>+${(+r.commission||0).toFixed(2)}</span>
                      </div>
                    );
                  })}
                  {recent.length===0 && <div style={{ padding:'22px 16px', textAlign:'center', fontSize:12.5, color:C.text3 }}>
                    No commission activity yet — it appears here the moment your clients trade. 🚀</div>}
                </div>
              </div>

              {/* ── where your clients are — country share ── */}
              {(() => {
                const m:any = {};
                fundedList.forEach((c:any) => { const key = c.country || 'Other';
                  m[key] = m[key] || { name:key, clients:0, volume:0 }; m[key].clients++; m[key].volume += (c.volume||0); });
                const rowsC:any[] = (Object.values(m) as any[]).sort((a,b)=>b.clients-a.clients).slice(0,6);
                const mxC = Math.max(...rowsC.map(r=>r.clients), 1);
                const PALETTE = [C.blue, C.green, C.purple, C.amber, '#e0317f', '#17a2b8'];
                return rowsC.length ? (
                  <div style={{ ...S.card, padding:18 }}>
                    <div style={{ fontSize:11, color:C.text3, fontWeight:700, textTransform:'uppercase', letterSpacing:'.06em', marginBottom:13 }}>🌍 Your clients by country</div>
                    {rowsC.map((r,i)=>(
                      <div key={i} style={{ marginBottom: i<rowsC.length-1?12:0 }}>
                        <div style={{ display:'flex', justifyContent:'space-between', marginBottom:4 }}>
                          <span style={{ fontSize:12.5, color:C.text, fontWeight:600 }}>{r.name}</span>
                          <span style={{ fontSize:11.5, color:C.text3 }}><b style={{ color:PALETTE[i%PALETTE.length] }}>{num(r.clients)}</b> clients · {num(r.volume)} lots</span>
                        </div>
                        <Bar pct={r.clients/mxC*100} color={PALETTE[i%PALETTE.length]} />
                      </div>
                    ))}
                  </div>
                ) : null;
              })()}

              {/* mini stats */}
              <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:12 }}>
                <MiniStat label="Active traders" value={num(k.active)} sub="traded this period" accent={C.green} />
                <MiniStat label="Sub-IBs" value={num(k.subIbs)} sub="in your network" accent={C.blue} />
                <MiniStat label="Paid out" value={usd(k.paid)} sub="commission paid" accent={C.text} />
                <MiniStat label="Own balance" value={usd(k.balance)} sub="IB account" accent={C.text} />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ══ CLIENTS ══ */}
      {tab==='clients' && (
        <div className="ibp-page" style={S.page}>
          <div className="ibp-filters" style={{ display:'flex', gap:9, marginBottom:13, alignItems:'center' }}>
            <input placeholder="🔍 Search name, account #, customer ID…" value={cliSearch} onChange={e=>setCliSearch(e.target.value)}
              style={{ ...S.input, width:250, background:C.card, color:C.text, border:`1px solid ${C.borderH}` }} />
            <select value={cliStatus} onChange={e=>setCliStatus(e.target.value)} title="Filter by status" style={{ ...S.input, background:'#fff', color:C.text, border:`1px solid ${C.borderH}` }}>
              <option value="">All statuses</option>
              <option value="nda">🟢 NDA — new, counts</option>
              <option value="nda_pending">🟡 NDA — pending (needs 1.0 lot)</option>
              <option value="review">🟡 NDA — under review</option>
              <option value="ftd">🔴 NDA — related, not counted</option>
              <option value="additional">Additional account</option>
            </select>
            <select value={cliCountry} onChange={e=>setCliCountry(e.target.value)} style={{ ...S.input, background:'#fff', color:C.text, border:`1px solid ${C.borderH}` }}>
              <option value="">All countries</option>{countryOpts.map((x:string)=><option key={x} value={x}>{x}</option>)}
            </select>
            <select value={cliCity} onChange={e=>setCliCity(e.target.value)} style={{ ...S.input, background:'#fff', color:C.text, border:`1px solid ${C.borderH}` }}>
              <option value="">All cities</option>{cityOpts.map((x:string)=><option key={x} value={x}>{x}</option>)}
            </select>
            <select value={cliPeriod} onChange={e=>setCliPeriod(e.target.value)} title="Filter by first-deposit date" style={{ ...S.input, background:'#fff', color:C.text, border:`1px solid ${C.borderH}` }}>
              {[['all','All time'],['today','Today'],['this_week','This week'],['this_month','This month'],['last_30','Last 30 days'],['last_90','Last 90 days'],['this_year','This year']].map(([k,l])=><option key={k} value={k}>{l}</option>)}
            </select>
            <span style={{ fontSize:12.5, color:C.text3, marginLeft:'auto' }}>{filteredClients.length} trading account(s)</span>
          </div>
          <div style={{ ...S.card, overflow:'hidden' }}>
            <div style={{ overflowX:'auto', maxHeight:640 }}>
              <table style={{ width:'100%', borderCollapse:'collapse' }}>
                <thead><tr>
                  {['Account','Type','Platform','Country','City','Volume','Commission','First deposit','Reg date','Status'].map(h => {
                    const sortable = h==='Volume'||h==='Commission';
                    const col = h==='Volume'?'volume':'commission';
                    const active = sortable && cliSort.col===col;
                    const hideM = ['Platform','Country','City','First deposit','Reg date'].includes(h);
                    return <th key={h} className={hideM?'hm':''} style={{ ...S.th, cursor:sortable?'pointer':'default', color:active?C.blue:C.text3 }}
                      onClick={()=>sortable&&toggleSort(col)}>{h}{active?(cliSort.dir==='asc'?' ▲':' ▼'):(sortable?' ↕':'')}</th>;
                  })}
                </tr></thead>
                <tbody>
                  {filteredClients.map((c:any,i:number)=>{
                    const rev = revReq[c.login] || c.nda_review || '';
                    const st = statusOf(c);
                    return (
                    <tr key={i} className="ibp-row" style={c.is_archived ? { opacity:0.6 } : undefined}>
                      <td className="cb" style={{ ...S.td, fontFamily:'monospace', fontSize:11.5 }}>
                        <span onClick={()=>openDrill(c.login)} title="View activity" style={{ color:C.blue, cursor:'pointer', fontWeight:700 }}>#{c.account_number || c.login}</span>
                        {(c.self_related || c.is_self) && (() => {
                          const zero = (R?.ib_level || 5) < 7;   // self/related earns nothing at Level 5/6
                          const isSelf = c.self_related === 'self' || !!c.is_self;
                          return <span title={`${isSelf ? 'Your OWN trading account' : 'Account 100% related to you (10/10 connection)'}${c.self_related_reason ? ' — ' + c.self_related_reason : ''}. ${zero ? 'No commission is paid on it at your level — it unlocks at Level 7.' : 'It earns commission at your level (7+).'}`}
                            style={{ ...badge(zero ? C.redBg : C.card2, zero ? C.red : C.text3), marginLeft:6, fontSize:9.5, fontWeight:800 }}>
                            {zero ? (isSelf ? 'Self · $0' : 'Related · $0') : (isSelf ? 'Self' : 'Related')}</span>;
                        })()}
                        {c.is_archived && <span title="This account is archived (closed/inactive) — its deposits and history still count in your New-Client numbers" style={{ ...badge(C.card2, C.text3), marginLeft:6, fontSize:9.5 }}>Archived</span>}</td>
                      <td style={S.td}><span style={badge(C.blueBg, C.blue)}>{acctTypeOf(c.group)}</span></td>
                      <td className="cm hm" style={S.td}>{c.platform || 'MT5'}</td>
                      <td className="cm hm" style={S.td}>{c.country||'—'}</td>
                      <td className="cm hm" style={S.td}>{c.city||'—'}</td>
                      <td className="cp" style={{ ...S.td, fontWeight:600 }}>{num(c.volume)} lots</td>
                      <td className="cg" style={{ ...S.td, fontWeight:600 }}>{c.commission>0?usd(c.commission):'—'}</td>
                      <td className="cm hm" style={S.td}>{c.first_deposit ? String(c.first_deposit).slice(0,10) : '—'}</td>
                      <td className="cm hm" style={S.td}>{c.reg ? String(c.reg).slice(0,10) : '—'}</td>
                      <td style={{ ...S.td, whiteSpace:'nowrap' }}>
                        {/* status is always "NDA"; the COLOUR is the outcome (🟢 counts · 🟡 pending · 🔴 related).
                            Additional accounts aren't NDA candidates. The ⓘ on yellow/red opens the details. */}
                        {(() => {
                          const iBtn = (kind:string) => (
                            <button onClick={()=>setStatusInfo({ kind, c })} title="Why? — tap for details"
                              style={{ marginLeft:5, width:16, height:16, lineHeight:'14px', textAlign:'center', borderRadius:99, border:`1px solid ${C.borderH}`, background:'#fff', color:C.text2, fontSize:10.5, fontWeight:900, fontStyle:'italic', cursor:'pointer', padding:0, flexShrink:0 }}>i</button>);
                          if (st === 'additional') return <span title={c.ftd_here === false
                              ? "Existing TNFX client — first deposit made before joining you; an ADDITIONAL account"
                              : "This client's first-deposit account is already yours — an additional account"} style={badge(C.card2, C.purple)}>Additional account</span>;
                          if (st === 'nda') return <span style={badge(C.greenBg, C.green)}>🟢 NDA</span>;
                          if (st === 'nda_pending') return <span style={{ display:'inline-flex', alignItems:'center' }}><span style={badge(C.amberBg, C.amber)}>🟡 NDA · {(c.nda_lots||0).toFixed(2)}/1.0 lot</span>{iBtn('pending')}</span>;
                          if (st === 'review') return <span style={{ display:'inline-flex', alignItems:'center' }}><span style={badge(C.amberBg, C.amber)}>🟡 NDA</span>{iBtn('review')}</span>;
                          // DECISIVE ties (same device / same payment sender) are a 100% match — no dispute
                          // possible, so no "Review?" button. Soft ties (email / IP / city) keep it.
                          const decisive = /same device|same payment/i.test(c.relation_reason||'');
                          return <span style={{ display:'inline-flex', alignItems:'center' }}>
                            <span style={badge(C.redBg, C.red)}>🔴 NDA</span>{iBtn('related')}
                            {rev !== 'rejected' && !decisive && <button onClick={()=>reqNdaReview(c.login)} title="Disagree? Ask our team to re-check"
                              style={{ marginLeft:5, padding:'2px 8px', borderRadius:99, border:`1px solid ${C.borderH}`, background:'transparent', color:C.text2, fontSize:10.5, cursor:'pointer' }}>Review?</button>}
                          </span>;
                        })()}
                      </td>
                    </tr>
                  );})}
                  {filteredClients.length===0 && <EmptyRow cols={10} loading={loadingPreview} />}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* KPI definition popup — opens from the ⓘ on a KPI card */}
      {infoPop && (
        <div onClick={()=>setInfoPop(null)} style={{ position:'fixed', inset:0, background:'rgba(16,24,40,0.5)', zIndex:130, display:'flex', alignItems:'center', justifyContent:'center', padding:16 }}>
          <div onClick={e=>e.stopPropagation()} style={{ ...S.card, width:420, maxWidth:'95vw', padding:20 }}>
            <div style={{ fontSize:15, fontWeight:800, color:C.text, marginBottom:10 }}>{infoPop.title}</div>
            <div style={{ fontSize:13, color:C.text2, lineHeight:1.65 }}>{infoPop.body}</div>
            <button onClick={()=>setInfoPop(null)} style={{ ...S.btnGhost, marginTop:16, width:'100%' }}>Got it</button>
          </div>
        </div>
      )}

      {/* NDA status detail popup — opens from the ⓘ on a yellow/red badge */}
      {statusInfo && (() => {
        const c = statusInfo.c || {}; const k = statusInfo.kind;
        const meta:any = ({
          pending: { icon:'🟡', ttl:'NDA · pending', col:C.amber, bg:C.amberBg,
            body:`This client is genuinely new, but hasn't traded enough yet. They become a counted NDA once they trade 1.0 lot on Gold or FX — summed across all their accounts. So far ${(c.nda_lots||0).toFixed(2)} / 1.0 lot.` },
          review: { icon:'🟡', ttl:'NDA · under review', col:C.amber, bg:C.amberBg,
            body:'Our team is re-checking this client. Once done it becomes 🟢 NDA (counts) or 🔴 NDA (related) — you will see the result here.' },
          related: { icon:'🔴', ttl:'NDA · related', col:C.red, bg:C.redBg,
            body:`This client's first deposit was made with you, but they are LINKED to an existing TNFX client${c.relation_reason?` — ${c.relation_reason}`:''}. Because they are the same person / network as an existing client, they don't count as a new NDA.` },
        } as any)[k] || { icon:'', ttl:'Details', col:C.text, bg:C.card2, body:'' };
        return (
          <div onClick={()=>setStatusInfo(null)} style={{ position:'fixed', inset:0, background:'rgba(16,24,40,0.5)', zIndex:130, display:'flex', alignItems:'center', justifyContent:'center', padding:16 }}>
            <div onClick={e=>e.stopPropagation()} style={{ ...S.card, width:400, maxWidth:'95vw', padding:20 }}>
              <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:12 }}>
                <span style={{ fontSize:22 }}>{meta.icon}</span>
                <div style={{ fontSize:15, fontWeight:800, color:C.text, flex:1, minWidth:0, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{c.name || `#${c.login}`}</div>
                <span style={badge(meta.bg, meta.col)}>{meta.ttl}</span>
              </div>
              <div style={{ fontSize:13, color:C.text2, lineHeight:1.65 }}>{meta.body}</div>
              {k==='pending' && <div style={{ marginTop:12, height:9, background:C.card2, borderRadius:99, overflow:'hidden' }}>
                <div style={{ height:'100%', width:`${Math.min(100,(c.nda_lots||0)*100)}%`, background:'linear-gradient(90deg,#ffb37a,#ff6a00)', borderRadius:99 }} /></div>}
              <button onClick={()=>setStatusInfo(null)} style={{ ...S.btnGhost, marginTop:16, width:'100%' }}>Close</button>
            </div>
          </div>
        );
      })()}

      {/* ══ LEADS ══ */}
      {tab==='leads' && (() => {
        const kycBadge = (kyc:string) => kyc === 'verified'
          ? <span title="KYC verified" style={badge(C.greenBg, C.green)}>✓ verified</span>
          : (kyc && kyc !== 'none')
          ? <span title="Documents uploaded — waiting for verification" style={badge(C.amberBg, C.amber)}>◐ uploaded</span>
          : <span title="No KYC documents uploaded yet" style={badge(C.card2, C.text3)}>✗ none</span>;
        return (
        <div className="ibp-page" style={S.page}>
          <div style={{ fontSize:12.5, color:C.text2, marginBottom:11 }}>
            Your leads — registered under you but no deposit yet. Call them and follow up: one deposit turns them into your clients.
            <span style={{ color:C.text3 }}> ({filteredLeads.length})</span></div>
          <div className="ibp-filters" style={{ display:'flex', gap:9, marginBottom:13, alignItems:'center' }}>
            <input placeholder="🔍 Search name, phone, email…" value={leadSearch} onChange={e=>setLeadSearch(e.target.value)}
              style={{ ...S.input, width:230, background:'#fff', color:C.text, border:`1px solid ${C.borderH}` }} />
            <select value={leadVer} onChange={e=>setLeadVer(e.target.value)} title="Filter by verification" style={{ ...S.input, background:'#fff', color:C.text, border:`1px solid ${C.borderH}` }}>
              <option value="">All leads</option>
              <option value="ver">✓ Verified</option>
              <option value="unver">Not verified yet</option>
            </select>
            <select value={leadCountry} onChange={e=>setLeadCountry(e.target.value)} style={{ ...S.input, background:'#fff', color:C.text, border:`1px solid ${C.borderH}` }}>
              <option value="">All countries</option>{countryOpts.map((x:string)=><option key={x} value={x}>{x}</option>)}
            </select>
            <select value={leadCity} onChange={e=>setLeadCity(e.target.value)} style={{ ...S.input, background:'#fff', color:C.text, border:`1px solid ${C.borderH}` }}>
              <option value="">All cities</option>{cityOpts.map((x:string)=><option key={x} value={x}>{x}</option>)}
            </select>
          </div>
          <div style={{ ...S.card, overflow:'hidden' }}>
            <div style={{ overflowX:'auto', maxHeight:640 }}>
              <table style={{ width:'100%', borderCollapse:'collapse' }}>
                <thead><tr>{['Name','Phone','Verified','KYC','Email','Account','Country','Reg date'].map(h=>
                  <th key={h} className={['Email','Account','Country','Reg date'].includes(h)?'hm':''} style={S.th}>{h}</th>)}</tr></thead>
                <tbody>
                  {filteredLeads.map((c:any,i:number)=>{
                    const isVer = c.phone_v || c.email_v || c.kyc === 'verified';
                    return (
                    <tr key={i} className="ibp-row">
                      <td style={{ ...S.td, fontWeight:600 }}>{String(c.name).trim().split(/\s+/).slice(0,2).join(' ')}</td>
                      <td style={{ ...S.td, fontFamily:'monospace' }}>
                        {c.phone ? <a href={`tel:${c.phone}`} style={{ color:C.blue, textDecoration:'none', fontWeight:600 }}>{c.phone}</a> : <span style={{ color:C.text3 }}>—</span>}
                      </td>
                      <td style={S.td}>{isVer
                        ? <span title="Email or phone verified" style={badge(C.greenBg, C.green)}>✓</span>
                        : <span title="Not verified yet — follow up!" style={badge(C.card2, C.text3)}>✗</span>}</td>
                      <td style={S.td}>{kycBadge(c.kyc)}</td>
                      <td className="cm hm" style={S.td}>{c.email || '—'}</td>
                      <td className="hm" style={S.td}>{c.acct
                        ? <span className="cb" style={{ fontFamily:'monospace', fontWeight:600 }}>#{c.acct}</span>
                        : <span style={badge(C.amberBg, C.amber)}>no account yet</span>}</td>
                      <td className="cm hm" style={S.td}>{c.country||'—'}</td>
                      <td className="cm hm" style={S.td}>{c.reg ? String(c.reg).slice(0,10) : '—'}</td>
                    </tr>
                  );})}
                  {filteredLeads.length===0 && <EmptyRow cols={8} loading={loadingPreview} />}
                </tbody>
              </table>
            </div>
          </div>
        </div>
        );
      })()}

      {/* ══ TRADES ══ */}
      {tab==='trades' && <div className="ibp-page" style={S.page}><LightTrades ibId={ibId} preview={preview} /></div>}

      {/* ══ CAMPAIGNS ══ */}
      {tab==='campaigns' && (
        <div className="ibp-page" style={S.page}>
          {/* ── THE primary referral link (solid standalone /r/<code>) + QR + stats ── */}
          {pending ? (
            <div style={{ ...S.card, padding:'26px 24px', marginBottom:18, textAlign:'center' }}>
              <div style={{ fontSize:34 }}>🔗</div>
              <div style={{ fontSize:16, fontWeight:800, color:C.text, marginTop:6 }}>{uiLang==='ar'?'يُفتح رابط الإحالة بعد الاعتماد':'Your referral link unlocks after approval'}</div>
              <div style={{ fontSize:13, color:C.text2, maxWidth:430, margin:'6px auto 0', lineHeight:1.6 }}>{uiLang==='ar'?'بمجرد اعتماد فريقنا لطلبك، يظهر هنا رابط الإحالة الخاص بك وأدوات الحملات — وكل تسجيل عبره يُنسب إليك تلقائياً.':'Once our desk approves your application, your personal referral link and campaign tools appear here — every signup through it is credited to you automatically.'}</div>
            </div>
          ) : refData && (
            <div style={{ ...S.card, overflow:'hidden', marginBottom:18, background:`linear-gradient(115deg, ${C.blueBg}, ${C.card})` }}>
              <div className="ibp-cols" style={{ display:'grid', gridTemplateColumns:'minmax(0,1.6fr) minmax(0,1fr)', gap:0, alignItems:'stretch' }}>
                <div style={{ padding:'20px 22px' }}>
                  <div style={{ fontSize:11, color:C.text3, fontWeight:700, textTransform:'uppercase', letterSpacing:'.08em' }}>Your referral link</div>
                  <div style={{ fontSize:13, color:C.text2, margin:'3px 0 12px' }}>Share this everywhere — every signup through it is credited to you automatically (30-day tracking).</div>
                  <div style={{ display:'flex', gap:8, alignItems:'center', flexWrap:'wrap' }}>
                    <div style={{ flex:1, minWidth:200, fontFamily:'monospace', fontSize:14, fontWeight:700, color:C.blue,
                      background:'#fff', border:`1px solid ${C.borderH}`, borderRadius:9, padding:'11px 13px', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{refData.link}</div>
                    <button onClick={()=>{ const t=refData.link; try{navigator.clipboard?.writeText(t);}catch{} setCopied('mainref'); setTimeout(()=>setCopied(''),1500); }}
                      style={{ ...S.btnPri, whiteSpace:'nowrap' }}>{copied==='mainref'?'✓ Copied':'🔗 Copy'}</button>
                  </div>
                  <div style={{ display:'flex', gap:8, marginTop:11, flexWrap:'wrap' }}>
                    <a href={`https://wa.me/?text=${encodeURIComponent(`Trade with TNFX — open your account: ${refData.link}`)}`} target="_blank" rel="noreferrer"
                      style={{ ...S.btnGhost, textDecoration:'none', background:'rgba(37,211,102,0.12)', border:'1px solid rgba(37,211,102,0.4)', color:'#1a9b52' }}>💬 WhatsApp</a>
                    <button onClick={()=>setShowQR(true)} style={S.btnGhost}>▦ QR code</button>
                  </div>
                  <div style={{ display:'flex', gap:22, marginTop:16, flexWrap:'wrap' }}>
                    <div><div style={{ fontSize:20, fontWeight:800, color:C.text }}>{num(refData.unique_clicks||0)}</div><div style={{ fontSize:11, color:C.text3 }}>unique clicks</div></div>
                    <div><div style={{ fontSize:20, fontWeight:800, color:C.text }}>{num(refData.clicks||0)}</div><div style={{ fontSize:11, color:C.text3 }}>total clicks</div></div>
                    <div><div style={{ fontSize:20, fontWeight:800, color:C.green }}>{num(refData.signups||0)}</div><div style={{ fontSize:11, color:C.text3 }}>signups</div></div>
                    {(refData.by_source||[]).slice(0,3).map((s:any)=>(
                      <div key={s.src}><div style={{ fontSize:20, fontWeight:800, color:C.text }}>{num(s.clicks)}</div><div style={{ fontSize:11, color:C.text3, textTransform:'capitalize' }}>{s.src}</div></div>
                    ))}
                  </div>
                </div>
                <div style={{ display:'flex', alignItems:'center', justifyContent:'center', padding:16, borderLeft:`1px solid ${C.border}`, background:'#fff' }}>
                  <div style={{ textAlign:'center' }}>
                    <div dangerouslySetInnerHTML={{ __html: qrSVG(refData.link, 150, '#0b1220', '#ffffff') }} />
                    <div style={{ fontSize:11, color:C.text3, marginTop:6 }}>Scan to open your link</div>
                  </div>
                </div>
              </div>
            </div>
          )}
          {showQR && refData && (
            <div onClick={()=>setShowQR(false)} style={{ position:'fixed', inset:0, background:'rgba(16,24,40,0.55)', zIndex:120, display:'flex', alignItems:'center', justifyContent:'center', padding:16 }}>
              <div onClick={e=>e.stopPropagation()} style={{ ...S.card, padding:24, textAlign:'center', background:'#fff' }}>
                <div dangerouslySetInnerHTML={{ __html: qrSVG(refData.link, 300, '#0b1220', '#ffffff') }} />
                <div style={{ fontFamily:'monospace', fontSize:12.5, color:C.blue, marginTop:12 }}>{refData.link}</div>
                <div style={{ fontSize:12, color:C.text3, marginTop:6 }}>Right-click → Save image, or screenshot to share</div>
                <button onClick={()=>setShowQR(false)} style={{ ...S.btnGhost, marginTop:14 }}>Close</button>
              </div>
            </div>
          )}
          {/* ── Marketing analytics: funnel + best sources ── */}
          {analytics && (analytics.funnel?.clicks > 0 || (analytics.by_source||[]).length > 0) && (
            <div style={{ ...S.card, padding:16, marginBottom:18 }}>
              <div style={{ ...S.secLbl, marginBottom:12 }}>📊 Link performance</div>
              <div style={{ display:'flex', gap:10, marginBottom:14, flexWrap:'wrap' }}>
                {[['Clicks', analytics.funnel.clicks, C.blue],['Unique', analytics.funnel.unique, C.purple],['Signups', analytics.funnel.signups, C.green]].map(([l,v,ac]:any,i:number)=>(
                  <div key={i} style={{ flex:'1 1 100px', textAlign:'center', background:C.card2, borderRadius:10, padding:'12px 10px' }}>
                    <div style={{ fontSize:22, fontWeight:900, color:ac }}>{num(v)}</div>
                    <div style={{ fontSize:11, color:C.text3 }}>{l}</div>
                  </div>
                ))}
                <div style={{ flex:'1 1 100px', textAlign:'center', background:C.greenBg, borderRadius:10, padding:'12px 10px' }}>
                  <div style={{ fontSize:22, fontWeight:900, color:C.green }}>{analytics.funnel.clicks ? Math.round(100*analytics.funnel.signups/analytics.funnel.clicks) : 0}%</div>
                  <div style={{ fontSize:11, color:C.text3 }}>conversion</div>
                </div>
              </div>
              {(analytics.by_source||[]).length > 0 && (
                <div>
                  <div style={{ fontSize:12, fontWeight:700, color:C.text2, marginBottom:8 }}>By channel</div>
                  {analytics.by_source.map((s:any,i:number)=>{
                    const max = Math.max(...analytics.by_source.map((x:any)=>x.clicks), 1);
                    return (
                      <div key={i} style={{ display:'flex', alignItems:'center', gap:10, marginBottom:7 }}>
                        <span style={{ width:80, fontSize:12, color:C.text2, textTransform:'capitalize', flexShrink:0 }}>{s.src}</span>
                        <div style={{ flex:1, height:16, background:C.card2, borderRadius:99, overflow:'hidden' }}>
                          <div style={{ height:'100%', width:`${Math.max(4,100*s.clicks/max)}%`, background:`linear-gradient(90deg,${C.blue},${C.purple})`, borderRadius:99 }} />
                        </div>
                        <span style={{ fontSize:11.5, color:C.text3, width:110, textAlign:'right', flexShrink:0 }}>{num(s.clicks)} clicks · {num(s.signups)} joined</span>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}
          {/* My campaigns + create (E) */}
          <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:13 }}>
            <div style={S.secLbl}>Campaign links <span style={{ fontSize:11, fontWeight:500, color:C.text3 }}>· separate link per channel to compare performance</span></div>
            {preview && !pending && <button onClick={()=>setCampModal(true)} style={S.btnPri}>+ Create campaign</button>}
          </div>
          <div style={{ ...S.card, overflow:'hidden', marginBottom:18 }}>
            <table style={{ width:'100%', borderCollapse:'collapse' }}>
              <thead><tr>{['Campaign','Platform','Website','Referral link','Clicks'].map(h=><th key={h} style={S.th}>{h}</th>)}</tr></thead>
              <tbody>
                {myCampaigns.map((c:any)=>(
                  <tr key={c.id} className="ibp-row">
                    <td style={{ ...S.td, fontWeight:600 }}>{c.name}</td>
                    <td style={S.td}>{c.platform ? <span style={badge(`${PLATFORM_COLORS[c.platform.toLowerCase()]||C.text2}1a`, PLATFORM_COLORS[c.platform.toLowerCase()]||C.text2)}>{c.platform}</span> : '—'}</td>
                    <td className="cm" style={S.td}>{c.website ? <a href={c.website} target="_blank" rel="noreferrer" style={{ color:C.blue }}>{c.website.replace(/^https?:\/\//,'').slice(0,28)}</a> : '—'}</td>
                    <td style={S.td}>
                      <span style={{ fontFamily:'monospace', fontSize:11.5, color:C.blue }}>{c.ref_link}</span>
                      <button onClick={()=>{ navigator.clipboard?.writeText(c.ref_link); setCopied(c.ref_code); setTimeout(()=>setCopied(''),1500); }}
                        style={{ ...S.btnGhost, padding:'3px 8px', marginLeft:8, fontSize:11 }}>{copied===c.ref_code?'✓ Copied':'Copy'}</button>
                    </td>
                    <td className="cp" style={S.td}>{num(c.clicks)}</td>
                  </tr>
                ))}
                {myCampaigns.length===0 && <tr><td colSpan={5} style={{ ...S.td, textAlign:'center', color:C.text3, padding:26 }}>No campaigns yet — create one to get a referral link.</td></tr>}
              </tbody>
            </table>
          </div>

          {campModal && (
            <div onClick={()=>setCampModal(false)} style={{ position:'fixed', inset:0, background:'rgba(16,24,40,0.45)', zIndex:100, display:'flex', alignItems:'center', justifyContent:'center', padding:16 }}>
              <div onClick={e=>e.stopPropagation()} style={{ ...S.card, width:420, maxWidth:'95vw', padding:22 }}>
                <div style={{ fontSize:16, fontWeight:800, color:C.text, marginBottom:14 }}>Create campaign</div>
                {[['name','Campaign name *','e.g. Instagram Iraq'],['platform','Platform','facebook / instagram / tiktok / website…'],['website','Website / landing URL','https://…']].map(([k,label,ph]:any)=>(
                  <div key={k} style={{ marginBottom:12 }}>
                    <label style={{ fontSize:11.5, color:C.text2, fontWeight:600, display:'block', marginBottom:5 }}>{label}</label>
                    <input value={campForm[k]} onChange={e=>setCampForm((f:any)=>({...f,[k]:e.target.value}))} placeholder={ph}
                      style={{ width:'100%', padding:'9px 11px', borderRadius:9, border:`1px solid ${C.borderH}`, background:'#fff', color:C.text, fontSize:13, outline:'none', boxSizing:'border-box' }} />
                  </div>
                ))}
                <div style={{ fontSize:11.5, color:C.text3, marginBottom:14 }}>A unique referral link will be generated for this campaign.</div>
                <div style={{ display:'flex', gap:8, justifyContent:'flex-end' }}>
                  <button onClick={()=>setCampModal(false)} style={S.btnGhost}>Cancel</button>
                  <button onClick={createCampaign} disabled={!campForm.name.trim()} style={{ ...S.btnPri, opacity:campForm.name.trim()?1:0.5 }}>Create</button>
                </div>
              </div>
            </div>
          )}

          {/* Existing (Plugit) referral links — kept working */}
          {refLinks.length > 0 && (
            <div style={{ marginBottom:18 }}>
              <div style={{ ...S.secLbl, display:'flex', alignItems:'center', gap:8 }}>🔗 Your existing referral links <span style={{ fontSize:11, fontWeight:500, color:C.text3 }}>· still active — keep using them</span></div>
              <div style={{ ...S.card, overflow:'hidden' }}>
                <table style={{ width:'100%', borderCollapse:'collapse' }}>
                  <thead><tr>{['Campaign code','Referrer ID','Referral link','Clicks'].map(h=><th key={h} style={S.th}>{h}</th>)}</tr></thead>
                  <tbody>
                    {refLinks.map((l:any,i:number)=>(
                      <tr key={i} className="ibp-row">
                        <td className="cb" style={{ ...S.td, fontFamily:'monospace' }}>{l.campaign_code||'—'}</td>
                        <td className="cm" style={S.td}>{l.referrer_id||'—'}</td>
                        <td style={S.td}>
                          <span style={{ fontFamily:'monospace', fontSize:11, color:C.blue }}>{(l.custom_link||'').slice(0,52)}{(l.custom_link||'').length>52?'…':''}</span>
                          <button onClick={()=>{ navigator.clipboard?.writeText(l.custom_link); setCopied(l.custom_link); setTimeout(()=>setCopied(''),1500); }}
                            style={{ ...S.btnGhost, padding:'3px 8px', marginLeft:8, fontSize:11 }}>{copied===l.custom_link?'✓ Copied':'Copy'}</button>
                        </td>
                        <td className="cp" style={S.td}>{num(l.clicks)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          <div style={{ fontSize:12.5, color:C.text2, marginBottom:13 }}>Performance grouped by the campaign each client came from.</div>
          <div style={{ ...S.card, overflow:'hidden' }}>
            <table style={{ width:'100%', borderCollapse:'collapse' }}>
              <thead><tr>{['Campaign','Clients','Funded','Conversion','Deposits','Volume'].map(h=><th key={h} style={S.th}>{h}</th>)}</tr></thead>
              <tbody>
                {campaigns.map((c:any,i:number)=>{
                  const plat = (c.name||'').split(/[-_ ]/)[0].toLowerCase();
                  const col = PLATFORM_COLORS[plat] || C.text2;
                  return (
                    <tr key={i} className="ibp-row">
                      <td style={S.td}><span style={badge(`${col}1a`, col)}>{c.name}</span></td>
                      <td style={{ ...S.td, fontWeight:600 }}>{num(c.leads)}</td>
                      <td className="cg" style={S.td}>{num(c.ftds)}</td>
                      <td className="cm" style={S.td}>{c.leads?Math.round(c.ftds/c.leads*100):0}%</td>
                      <td className="cg" style={{ ...S.td, fontWeight:600 }}>{usd(c.deposits)}</td>
                      <td className="cp" style={S.td}>{num(c.volume)} lots</td>
                    </tr>
                  );
                })}
                {campaigns.length===0 && <EmptyRow cols={6} loading={loadingPreview} />}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ══ CHALLENGES (gamification: CH1 career + CH2 weekly) ══ */}
      {tab==='challenges' && !owner && (() => {
        const career:any[] = cv.career||[], weekly:any[] = cv.weekly||[];
        const claimedN = career.filter((c:any)=>c.status==='claimed').length + weekly.filter((w:any)=>w.claimed).length;
        const earned = career.filter((c:any)=>c.status==='claimed').reduce((s:number,c:any)=>s+(c.reward||0),0)
                     + weekly.filter((w:any)=>w.claimed).reduce((s:number,w:any)=>s+(w.reward||0),0);
        const rank = [...ARENA_RANKS].reverse().find(r=>claimedN>=r.at) || ARENA_RANKS[0];
        const nextRank = ARENA_RANKS[ARENA_RANKS.indexOf(rank)+1];
        const rankPct = nextRank ? Math.min(100, Math.round((claimedN-rank.at)/(nextRank.at-rank.at)*100)) : 100;
        const activeQ = career.find((c:any)=>c.status==='active');
        const readyCareerN = career.filter((c:any)=>c.status==='completed').length;
        const expiredN = career.filter((c:any)=>c.status==='expired').length;
        const nextAvail = career.find((c:any)=>c.status==='available');
        const careerDoneN = career.filter((c:any)=>c.status==='claimed').length;
        const careerDot = readyCareerN + expiredN + ((!activeQ && !readyCareerN && nextAvail) ? 1 : 0);
        const readyWeeklyN = weekly.filter((w:any)=>w.ready && !w.claimed).length;
        const readyN = readyWeeklyN + readyCareerN;
        const careerRingPct = activeQ ? (activeQ.pct||0) : (career.length ? Math.round(careerDoneN/career.length*100) : 0);
        const weeklyDonePct = weekly.length ? Math.round(weekly.filter((w:any)=>w.claimed||w.ready).length/weekly.length*100) : 0;
        const resetSec = adjSec(cv.seconds_to_reset)||0;
        const scrollToSec = (id:string) => { try { document.getElementById(id)?.scrollIntoView({ behavior:'smooth', block:'start' }); } catch {} };
        const CTA = (bg:string, glow:string):React.CSSProperties => ({ padding:'10px 20px', borderRadius:10, fontSize:12.5, fontWeight:800, cursor:'pointer', border:'none', color:'#fff', background:bg, boxShadow:`0 6px 16px ${glow}`, minHeight:40 });
        // per-target meters — full-width bars, count centred ON the bar
        const Meters = ({ q }:{ q:any }) => (
          <div>
            {q.progress && Object.keys(q.target||{}).length>0
              ? Object.entries(q.target).map(([tk,tv]:any,j:number) => {
                  const cur = +(q.progress?.[tk]||0), p = tv?Math.min(100,cur/tv*100):100;
                  return (
                    <div key={j} style={{ marginBottom:8 }}>
                      <div style={{ fontSize:10.5, color:C.text2, fontWeight:700, textTransform:'capitalize', marginBottom:3 }}>{(tk==='nda'?'new clients':tk.replace(/_/g,' '))} {p>=100 && <span style={{ color:C.green }}>✓</span>}</div>
                      <MeterBar pct={p} label={`${num(cur)} / ${num(tv)}`} c1={p>=100?'#3ddc8f':'#ffb37a'} c2={p>=100?'#13a858':'#ff6a00'} />
                    </div>
                  );
                })
              : <MeterBar pct={q.pct||0} label={`${q.pct||0}%`} c1={q.pct>=100?'#3ddc8f':'#ffb37a'} c2={q.pct>=100?'#13a858':'#ff6a00'} />}
          </div>
        );
        // the four quest programmes — premium status cards (tap = scroll / open teaser)
        const HUBS:any[] = [
          { key:'career', icon:'🗺️', name:'Career Quest', g1:'#ff6a00', g2:'#ff9d4d', dot:careerDot, bar:careerRingPct,
            sub: activeQ ? `mission live · ${activeQ.pct||0}%` : readyCareerN>0 ? 'reward ready to claim!' : `${careerDoneN}/${career.length} conquered`,
            go: () => scrollToSec('arena-career') },
          { key:'weekly', icon:'🏟️', name:'Weekly Quests', g1:'#13a858', g2:'#3ddc8f', dot:readyWeeklyN, bar:weeklyDonePct, timer:true,
            sub: readyWeeklyN>0 ? `${readyWeeklyN} ready to claim!` : `${weekly.length} missions live`,
            go: () => scrollToSec('arena-weekly') },
          { key:'season', icon:'🌟', name:'Season Quest', g1:'#c99a2e', g2:'#e8b84b', dot:0, locked:true, sub:'Season 1 · soon',
            go: () => setQuestPanel('season') },
          { key:'daily',  icon:'⚡', name:'Daily Challenge', g1:'#f0a500', g2:'#ffd166', dot:0, locked:true, sub:'coming soon',
            go: () => setQuestPanel('daily') },
        ];
        // ── one career stage row (rail node + quest card) ──
        const CareerRow = (ch:any, i:number) => {
          const st = ch.status;
          const isDone = st==='claimed', isReady = st==='completed', isLive = st==='active', isDead = st==='expired', isLocked = st==='locked';
          const col = isDone||isReady?C.green : isLive?TNFX_ORANGE : isDead?C.red : isLocked?'#9aa4b5' : '#94a3bd';
          const last = i===career.length-1;
          return (
            <div key={ch.key} style={{ display:'flex', gap:12 }}>
              <div className="ibp-rail" style={{ display:'flex', flexDirection:'column', alignItems:'center', width:48, flexShrink:0 }}>
                {isLive
                  ? <Ring pct={ch.pct||0} size={46} stroke={4.5} color={TNFX_ORANGE}><span style={{ fontSize:11, fontWeight:900, color:TNFX_ORANGE }}>{ch.pct||0}%</span></Ring>
                  : <div className={isReady?'ibp-glow':''} style={{ width:42, height:42, borderRadius:'50%', display:'flex', alignItems:'center', justifyContent:'center', fontSize:isDone||isReady?18:15, fontWeight:900,
                      background:isDone?C.greenBg:isReady?C.green:isDead?C.redBg:'#f1f4f9', border:`2.5px solid ${col}`, color:isReady?'#fff':col }}>
                      {isDone?'✓':isReady?'🎁':isDead?'⏰':isLocked?'🔒':(ch.stage||i+1)}</div>}
                {!last && <div style={{ width:3, flex:1, minHeight:16, margin:'4px 0', borderRadius:2,
                  background: isDone ? `linear-gradient(180deg, ${C.green}, ${C.green}55)` : C.border }} />}
              </div>
              <div className="ibp-quest" style={{ flex:1, marginBottom:last?0:12, borderRadius:13, padding:'13px 15px',
                border:`1.5px solid ${isLive?TNFX_ORANGE+'66':isReady?C.green:isDead?C.red+'55':C.border}`,
                background: isLive?`linear-gradient(135deg, ${'#fff3ea'}, #ffffff 70%)`
                          : isReady?`linear-gradient(135deg, ${C.greenBg}, #ffffff 70%)`
                          : isDead?`linear-gradient(135deg, ${C.redBg}, #ffffff 70%)` : '#fff',
                opacity: isLocked ? 0.62 : (st==='available' && career.some((x:any)=>x.status==='active'))?.72:1 }}>
                <div style={{ display:'flex', alignItems:'flex-start', gap:10, flexWrap:'wrap' }}>
                  <div style={{ minWidth:0, flex:'1 1 150px' }}>
                    <div style={{ fontSize:14, fontWeight:800, color:C.text }}>{ch.name}
                      {isLive && <span style={{ ...badge('#fff3ea', TNFX_ORANGE), marginLeft:8, verticalAlign:'2px' }}>LIVE</span>}
                    </div>
                    <div style={{ fontSize:11.5, color:C.text2, marginTop:3 }}>{ch.desc}</div>
                    {ch.days && (st==='available'||isLocked||isDead) && (
                      <div style={{ marginTop:6, display:'inline-flex', alignItems:'center', gap:5, fontSize:10.5, fontWeight:700, color:C.text3, padding:'3px 9px', borderRadius:99, background:'#f1f4f9', border:`1px solid ${C.border}` }}>🕒 {ch.days}-day challenge</div>
                    )}
                  </div>
                  <span style={{ marginLeft:'auto' }}><RewardPill amount={ch.reward} /></span>
                </div>
                {isLive && (
                  <div style={{ marginTop:11 }}>
                    <Meters q={ch} />
                    <div style={{ display:'flex', justifyContent:'flex-end', marginTop:8 }}>
                      <span style={{ padding:'4px 11px', borderRadius:99, fontSize:11, fontWeight:800, background:C.amberBg, color:C.amber }}>
                        ⏱ {ch.seconds_left!=null ? <Countdown seconds={adjSec(ch.seconds_left)||0} color={C.amber} /> : '—'} left</span>
                    </div>
                  </div>
                )}
                {st==='available' && <button onClick={()=>preview && chAction('accept', ch.key)} className="ibp-cta" style={{ ...CTA('linear-gradient(92deg,#ff6a00,#ff9500)','rgba(255,106,0,0.35)'), marginTop:11 }}>⚔️ Accept mission</button>}
                {isLocked && <div style={{ marginTop:11, fontSize:11.5, fontWeight:700, color:C.text3, display:'flex', alignItems:'center', gap:7 }}>🔒 Claim the previous stage to unlock this mission</div>}
                {isReady && <button onClick={async()=>{ if(!preview) return; if (await chAction('claim', ch.key)) fireCelebrate(ch.reward); }} className="ibp-cta ibp-glow" style={{ ...CTA('linear-gradient(92deg,#13a858,#3ddc8f)','rgba(19,168,88,0.45)'), marginTop:11, fontWeight:900 }}>🎉 CLAIM {usd(ch.reward)}</button>}
                {isDone && <div style={{ marginTop:9, fontSize:11.5, color:C.green, fontWeight:800 }}>✓ Conquered — {usd(ch.reward)} credited to your balance</div>}
                {isDead && (
                  <div style={{ marginTop:11, display:'flex', alignItems:'center', gap:10, flexWrap:'wrap' }}>
                    <span style={{ fontSize:11.5, color:C.red, fontWeight:800 }}>⏰ Time's up — but legends get rematches</span>
                    <button onClick={()=>preview && chAction('rechallenge', ch.key)} className="ibp-cta" style={{ padding:'9px 16px', borderRadius:10, fontSize:12.5, fontWeight:800, cursor:'pointer', border:`1.5px solid ${C.red}`, background:'#fff', color:C.red, minHeight:38 }}>↻ Re-challenge</button>
                  </div>
                )}
              </div>
            </div>
          );
        };
        // ── one weekly mission row: icon | name+desc | reward | action, meter full width below ──
        const WeeklyRow = (ch:any) => {
          const ready = ch.ready && !ch.claimed;
          const tint = ready?C.green:ch.claimed?'#c9a227':TNFX_ORANGE;
          return (
            <div key={ch.key} className={`ibp-qrow ${ready?'ibp-glow':''}`}
              style={{ display:'flex', alignItems:'center', flexWrap:'wrap', gap:12, padding:'13px 14px', borderRadius:14, marginBottom:10, position:'relative', overflow:'hidden',
                border:`1.5px solid ${ch.claimed?'#e8cf7a':ready?C.green:C.border}`,
                background: ch.claimed?'linear-gradient(135deg,#fdf8e7,#ffffff 70%)':ready?`linear-gradient(135deg,${C.greenBg},#ffffff 70%)`:'#fff',
                opacity: ch.claimed?.75:1 }}>
              {ch.claimed && <div style={{ position:'absolute', top:10, right:-27, transform:'rotate(38deg)', background:'linear-gradient(92deg,#f7b733,#f0a500)', color:'#3d2b00', fontSize:9.5, fontWeight:900, padding:'3px 30px', letterSpacing:'.08em' }}>CLAIMED</div>}
              <div style={{ width:46, height:46, flexShrink:0, borderRadius:12, display:'flex', alignItems:'center', justifyContent:'center', fontSize:23,
                background:`radial-gradient(circle at 30% 30%, ${tint}2e, ${tint}12)`, border:`1.5px solid ${tint}44` }}>{ch.emoji}</div>
              <div style={{ flex:1, minWidth:0 }}>
                <div style={{ fontSize:13.5, fontWeight:800, color:C.text }}>{ch.name}</div>
                <div style={{ fontSize:11, color:C.text2, marginTop:2 }}>{ch.desc}</div>
              </div>
              <RewardPill amount={ch.reward} />
              <div className="ibp-qact" style={{ width:104, flexShrink:0, textAlign:'center' }}>
                {ch.claimed
                  ? <span style={{ fontSize:11.5, fontWeight:900, color:'#c9a227' }}>✓ Claimed</span>
                  : ready
                  ? <button onClick={async()=>{ if(!preview) return; if (await chAction('claim-weekly', ch.key)) fireCelebrate(ch.reward); }} className="ibp-cta"
                      style={{ ...CTA('linear-gradient(92deg,#13a858,#3ddc8f)','rgba(19,168,88,0.4)'), width:'100%', padding:'10px 6px', fontSize:12, fontWeight:900 }}>🎉 CLAIM</button>
                  : <span style={{ display:'inline-block', padding:'6px 13px', borderRadius:99, fontSize:11, fontWeight:800, background:'#f1f4f9', border:`1px solid ${C.border}`, color:C.text3 }}>{ch.pct||0}%</span>}
              </div>
              <div style={{ flexBasis:'100%', marginTop:2 }}>
                <MeterBar pct={ch.claimed?100:ch.pct||0} label={`${num(ch.progress)} / ${num(ch.target)}`}
                  c1={ready||ch.claimed?'#3ddc8f':'#ffb37a'} c2={ready||ch.claimed?'#13a858':'#ff6a00'} />
              </div>
            </div>
          );
        };
        return (
        <div className="ibp-page" style={S.page}>
          {/* 🎉 claim celebration burst */}
          {celebrate!==null && (
            <div style={{ position:'fixed', inset:0, zIndex:80, display:'flex', alignItems:'center', justifyContent:'center', pointerEvents:'none' }}>
              <div className="ibp-pop" style={{ textAlign:'center' }}>
                <div style={{ fontSize:64, lineHeight:1 }}>🎉</div>
                <div style={{ fontSize:40, fontWeight:900, color:C.green, textShadow:'0 4px 22px rgba(19,168,88,0.5)' }}>+{usd(celebrate)}</div>
                <div style={{ fontSize:14, fontWeight:800, color:C.text, marginTop:2 }}>Reward claimed!</div>
              </div>
              {['🪙','⭐','🎊','💰','🏅','✨'].map((e,i)=>(
                <span key={i} className="ibp-confetti" style={{ position:'absolute', fontSize:26, animationDelay:`${i*0.09}s`, left:`${34+i*6}%`, top:'46%' }}>{e}</span>
              ))}
            </div>
          )}

          {/* ══ ARENA HERO — claim + rank (weekly countdown lives in the Weekly box below) ══ */}
          <div className="ibp-hero" style={{ position:'relative', overflow:'hidden', borderRadius:14, marginBottom:16,
            background:'linear-gradient(120deg,#12151d 0%,#1b2130 46%,#0d1016 100%)', border:'1px solid #2c3444',
            boxShadow:'0 14px 40px rgba(0,0,0,0.45)', padding:'22px 26px', color:'#f0e9d8' }}>
            <div style={{ position:'absolute', top:-90, left:-40, width:300, height:300, borderRadius:'50%', background:'radial-gradient(circle, rgba(232,184,75,0.22), transparent 65%)', pointerEvents:'none' }} />
            <div style={{ position:'absolute', bottom:-110, right:-30, width:320, height:320, borderRadius:'50%', background:'radial-gradient(circle, rgba(255,106,0,0.18), transparent 65%)', pointerEvents:'none' }} />
            <div style={{ position:'absolute', inset:0, backgroundImage:'repeating-linear-gradient(115deg, rgba(232,184,75,0.04) 0 2px, transparent 2px 22px)', pointerEvents:'none' }} />
            <div className="ibp-hero-in" style={{ position:'relative', display:'flex', justifyContent:'space-between', alignItems:'center', gap:20, flexWrap:'wrap' }}>
              <div style={{ minWidth:250 }}>
                <div style={{ fontSize:'clamp(20px,3vw,27px)', fontWeight:900, letterSpacing:'-.4px' }}>⚔️ Challenge Arena</div>
                <div style={{ fontSize:12.5, color:'#c9b78a', marginTop:4, maxWidth:430 }}>Accept missions, hit the targets, claim <b style={{ color:'#3ddc8f' }}>real cash</b> — every mission's counters start the moment you accept it.</div>
                <div style={{ display:'flex', alignItems:'center', gap:12, marginTop:14, background:'rgba(255,255,255,0.06)', border:'1px solid rgba(232,184,75,0.35)', borderRadius:12, padding:'10px 14px', maxWidth:430 }}>
                  <span className="ibp-float" style={{ fontSize:30, lineHeight:1 }}>{rank.icon}</span>
                  <div style={{ flex:1, minWidth:0 }}>
                    <div style={{ display:'flex', justifyContent:'space-between', alignItems:'baseline' }}>
                      <span style={{ fontSize:14, fontWeight:800 }}>{rank.n}</span>
                      <span style={{ fontSize:10.5, color:'#c9b78a', fontWeight:700 }}>{claimedN} completed{nextRank?` · ${nextRank.at-claimedN} to ${nextRank.icon} ${nextRank.n}`:' · MAX RANK'}</span>
                    </div>
                    <div style={{ position:'relative', height:8, borderRadius:99, background:'rgba(255,255,255,0.12)', overflow:'hidden', marginTop:6 }}>
                      <div className="ibp-bar-fill" style={{ height:'100%', width:`${rankPct}%`, borderRadius:99, background:'linear-gradient(90deg,#e8b84b,#3ddc8f)' }} />
                      <div className="ibp-shimmer" style={{ position:'absolute', inset:0, width:`${rankPct}%`, borderRadius:99 }} />
                    </div>
                  </div>
                </div>
              </div>
              <div className="ibp-ar-claim" style={{ textAlign:'right' }}>
                <div style={{ fontSize:10.5, fontWeight:800, letterSpacing:'.14em', textTransform:'uppercase', color:'#c9b78a' }}>💰 Ready to claim</div>
                <div style={{ fontSize:'clamp(28px,4vw,40px)', fontWeight:900, lineHeight:1.05,
                  background:'linear-gradient(92deg,#ffffff,#ffe6ad 55%,#f6dfa0)', WebkitBackgroundClip:'text', WebkitTextFillColor:'transparent' }}>
                  <AnimatedUsd v={ch2ToClaim} /></div>
                {readyN>0 && <div style={{ fontSize:11.5, color:'#3ddc8f', fontWeight:800, marginTop:3 }}>🎉 {readyN} reward{readyN>1?'s':''} waiting for you!</div>}
                <div style={{ display:'flex', gap:7, marginTop:10, justifyContent:'flex-end', flexWrap:'wrap' }}>
                  <span style={{ padding:'5px 12px', borderRadius:99, fontSize:11, fontWeight:800, background:'rgba(255,255,255,0.07)', border:'1px solid rgba(255,255,255,0.14)', color:'#e8ddc4' }}>🏅 {usd(earned)} earned</span>
                  <span style={{ padding:'5px 12px', borderRadius:99, fontSize:11, fontWeight:800, background:'rgba(255,255,255,0.07)', border:'1px solid rgba(255,255,255,0.14)', color:'#e8ddc4' }}>🎯 {claimedN} missions</span>
                </div>
              </div>
            </div>
          </div>

          {chLoading ? (
            <div style={{ ...S.card, padding:'60px 20px', textAlign:'center' }}>
              <div className="ibp-spin-med" style={{ width:54, height:54, margin:'0 auto 16px', borderRadius:'50%', border:'3px solid #e3e8f2', borderTopColor:TNFX_ORANGE }} />
              <div style={{ fontSize:15, fontWeight:800, color:C.text }}>Loading your missions…</div>
            </div>
          ) : (<>
            {/* ══ QUEST PROGRAMMES — premium status strip (tap → jump to the list) ══ */}
            <div className="ibp-hub-grid" style={{ display:'grid', gridTemplateColumns:'repeat(4, minmax(0,1fr))', gap:12, marginBottom:16 }}>
              {HUBS.map((h:any) => (
                <div key={h.key} className="ibp-hub" onClick={h.go}
                  style={{ position:'relative', cursor:'pointer', borderRadius:15, padding:'13px 13px 13px 16px', display:'flex', alignItems:'center', gap:11, overflow:'hidden',
                    background:'#fff', border:`1px solid ${h.locked?C.border:h.g1+'3d'}`, boxShadow:'0 4px 16px rgba(23,32,48,.07)' }}>
                  <div style={{ position:'absolute', left:0, top:0, bottom:0, width:4, background:`linear-gradient(180deg,${h.g1},${h.g2})`, opacity:h.locked?.35:1 }} />
                  <div style={{ width:46, height:46, borderRadius:14, flexShrink:0, display:'flex', alignItems:'center', justifyContent:'center', fontSize:23, position:'relative', overflow:'hidden',
                    background:`linear-gradient(150deg,${h.g1}${h.locked?'26':'e6'},${h.g2}${h.locked?'1a':'cc'})`, boxShadow:h.locked?'none':`0 5px 12px ${h.g1}4d`, filter:h.locked?'grayscale(.5)':'none' }}>
                    <div style={{ position:'absolute', top:0, left:0, right:0, height:'48%', background:'linear-gradient(180deg,rgba(255,255,255,.38),rgba(255,255,255,0))' }} />
                    <span style={{ filter:'drop-shadow(0 2px 2px rgba(0,0,0,.25))' }}>{h.icon}</span>
                  </div>
                  <div style={{ flex:1, minWidth:0 }}>
                    <div style={{ fontSize:12.5, fontWeight:900, color:h.locked?C.text3:C.text, display:'flex', alignItems:'center', gap:5 }}>
                      <span style={{ overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{h.name}</span>{h.locked && <span style={{ fontSize:11 }}>🔒</span>}
                    </div>
                    <div style={{ fontSize:10.5, color:h.dot>0?h.g1:C.text3, fontWeight:h.dot>0?800:700, marginTop:2, whiteSpace:'nowrap', overflow:'hidden', textOverflow:'ellipsis' }}>{h.sub}</div>
                    {h.timer
                      ? <div style={{ fontSize:10, fontWeight:800, color:C.amber, marginTop:4 }}>⏳ resets in <Countdown seconds={resetSec} color={C.amber} /></div>
                      : h.bar!=null && !h.locked
                      ? <div style={{ marginTop:5, maxWidth:150 }}><MeterBar pct={h.bar} h={6} c1={h.g1} c2={h.g2} /></div>
                      : null}
                  </div>
                  {!h.locked && <span style={{ color:C.text3, fontSize:15, fontWeight:800, flexShrink:0 }}>›</span>}
                  {h.dot>0 && <span className="ibp-reddot" style={{ position:'absolute', top:8, right:8, minWidth:21, height:21, borderRadius:99,
                    background:'linear-gradient(140deg,#ff5d6c,#e03147)', color:'#fff', fontSize:11, fontWeight:900, display:'flex',
                    alignItems:'center', justifyContent:'center', padding:'0 6px', border:'2px solid #fff' }}>{h.dot}</span>}
                </div>
              ))}
            </div>

            {/* ══ MISSION CORE — the running quest at a glance ══ */}
            <div style={{ ...S.card, overflow:'hidden', marginBottom:16 }}>
              <div style={{ padding:'11px 16px', borderBottom:`1px solid ${C.border}`, display:'flex', alignItems:'center', justifyContent:'space-between', gap:8 }}>
                <span style={{ fontSize:11.5, fontWeight:900, letterSpacing:'.1em', color:activeQ?TNFX_ORANGE:C.text3 }}>
                  {activeQ ? '⚙️ MISSION RUNNING' : '⚙️ MISSION CONTROL'}
                </span>
                <button onClick={()=>scrollToSec('arena-career')} style={{ ...S.btnGhost, padding:'8px 14px', fontSize:11.5, fontWeight:800, minHeight:36 }}>View quest map ↓</button>
              </div>
              {activeQ ? (
                <div className="ibp-core-row" style={{ display:'flex', gap:24, padding:'18px 22px', alignItems:'center' }}>
                  <div style={{ position:'relative', width:148, height:148, flexShrink:0 }}>
                    <svg className="ibp-spin-slow" width="148" height="148" viewBox="0 0 148 148" style={{ position:'absolute', inset:0 }}>
                      <circle cx="74" cy="74" r="70" fill="none" stroke={TNFX_ORANGE+'40'} strokeWidth="1.6" strokeDasharray="3 9" />
                    </svg>
                    <svg className="ibp-spin-rev" width="148" height="148" viewBox="0 0 148 148" style={{ position:'absolute', inset:0 }}>
                      <circle cx="74" cy="74" r="62" fill="none" stroke={TNFX_ORANGE} strokeOpacity="0.55" strokeWidth="3" strokeLinecap="round" strokeDasharray="34 356" />
                      <circle cx="74" cy="74" r="62" fill="none" stroke="#3ddc8f" strokeOpacity="0.65" strokeWidth="3" strokeLinecap="round" strokeDasharray="18 372" strokeDashoffset="170" />
                    </svg>
                    <div className="ibp-spin-med" style={{ position:'absolute', inset:9 }}>
                      <span style={{ position:'absolute', top:-4, left:'50%', marginLeft:-4, width:8, height:8, borderRadius:99, background:'#3ddc8f', boxShadow:'0 0 11px 3px rgba(61,220,143,0.75)' }} />
                    </div>
                    <div style={{ position:'absolute', inset:22 }}>
                      <Ring pct={activeQ.pct||0} size={104} stroke={9} color={TNFX_ORANGE}>
                        <div style={{ textAlign:'center' }}>
                          <div style={{ fontSize:24, fontWeight:900, color:TNFX_ORANGE, lineHeight:1 }}>{activeQ.pct||0}%</div>
                          <div className="ibp-breathe" style={{ fontSize:8.5, fontWeight:900, letterSpacing:'.14em', color:C.text3, marginTop:3 }}>SYNCING</div>
                        </div>
                      </Ring>
                    </div>
                  </div>
                  <div style={{ flex:1, minWidth:0 }}>
                    <div style={{ display:'flex', alignItems:'center', gap:9, flexWrap:'wrap' }}>
                      <span style={{ fontSize:15.5, fontWeight:900, color:C.text }}>{activeQ.name}</span>
                      <span style={badge('#fff3ea', TNFX_ORANGE)}>LIVE</span>
                      <span style={{ marginLeft:'auto' }}><RewardPill amount={activeQ.reward} /></span>
                    </div>
                    <div style={{ fontSize:12, color:C.text2, margin:'4px 0 12px' }}>{activeQ.desc}</div>
                    <Meters q={activeQ} />
                    <div style={{ display:'flex', justifyContent:'flex-end', marginTop:9 }}>
                      <span style={{ padding:'4px 11px', borderRadius:99, fontSize:11, fontWeight:800, background:C.amberBg, color:C.amber }}>
                        ⏱ {activeQ.seconds_left!=null ? <Countdown seconds={adjSec(activeQ.seconds_left)||0} color={C.amber} /> : '—'} left</span>
                    </div>
                  </div>
                </div>
              ) : readyCareerN>0 ? (
                <div style={{ padding:'24px 20px', textAlign:'center' }}>
                  <div className="ibp-float" style={{ fontSize:40 }}>🎁</div>
                  <div style={{ fontSize:15, fontWeight:900, color:C.text, marginTop:6 }}>Mission accomplished — your reward is waiting!</div>
                  <button onClick={()=>scrollToSec('arena-career')} className="ibp-cta ibp-glow" style={{ ...CTA('linear-gradient(92deg,#13a858,#3ddc8f)','rgba(19,168,88,0.45)'), marginTop:12, padding:'11px 26px', fontSize:13.5 }}>🎉 Claim below ↓</button>
                </div>
              ) : expiredN>0 ? (
                <div style={{ padding:'24px 20px', textAlign:'center' }}>
                  <div style={{ fontSize:38 }}>⏰</div>
                  <div style={{ fontSize:14.5, fontWeight:900, color:C.text, marginTop:6 }}>A mission timed out — legends get rematches.</div>
                  <button onClick={()=>scrollToSec('arena-career')} className="ibp-cta" style={{ marginTop:12, padding:'10px 24px', borderRadius:10, fontSize:13, fontWeight:800, cursor:'pointer', border:`1.5px solid ${C.red}`, background:'#fff', color:C.red, minHeight:40 }}>↻ Re-challenge below ↓</button>
                </div>
              ) : nextAvail ? (
                <div style={{ padding:'24px 20px', textAlign:'center' }}>
                  <div className="ibp-float" style={{ fontSize:40 }}>⚔️</div>
                  <div style={{ fontSize:15, fontWeight:900, color:C.text, marginTop:6 }}>No mission running</div>
                  <div style={{ fontSize:12, color:C.text2, marginTop:3 }}>Next up: <b>{nextAvail.name}</b> · 🪙 +{usd(nextAvail.reward)}</div>
                  <button onClick={()=>scrollToSec('arena-career')} className="ibp-cta" style={{ ...CTA('linear-gradient(92deg,#ff6a00,#ff9500)','rgba(255,106,0,0.35)'), marginTop:12, padding:'11px 26px', fontSize:13.5 }}>⚔️ Accept your next mission ↓</button>
                </div>
              ) : career.length===0 ? (
                <div style={{ padding:'26px 20px', textAlign:'center' }}>
                  <div style={{ fontSize:36 }}>🛠️</div>
                  <div style={{ fontSize:13.5, fontWeight:800, color:C.text2, marginTop:7 }}>Missions are being prepared — check back soon!</div>
                </div>
              ) : (
                <div style={{ padding:'26px 20px', textAlign:'center' }}>
                  <div style={{ fontSize:40 }}>👑</div>
                  <div style={{ fontSize:15, fontWeight:900, color:C.amber, marginTop:6 }}>Every career mission conquered — you are a Legend!</div>
                </div>
              )}
            </div>

            {/* ══ THE QUEST LISTS — side by side, both visible by scrolling ══ */}
            <div className="ibp-cols" style={{ display:'grid', gridTemplateColumns:'minmax(0,1fr) minmax(0,1.05fr)', gap:16, alignItems:'start' }}>
              {/* career */}
              <div id="arena-career" style={{ ...S.card, padding:'16px 16px 18px', scrollMarginTop:96 }}>
                <div style={{ display:'flex', justifyContent:'space-between', alignItems:'baseline', gap:8, marginBottom:15, flexWrap:'wrap' }}>
                  <span style={{ fontSize:14, fontWeight:900 }}>🗺️ Career Quest</span>
                  <span style={{ fontSize:10.5, color:C.text3, fontWeight:700 }}>{careerDoneN}/{career.length} conquered · one epic path</span>
                </div>
                {career.length ? career.map(CareerRow)
                  : <div style={{ padding:'26px 12px', textAlign:'center', color:C.text3, fontSize:12.5, fontWeight:700 }}>🛠️ Missions are being prepared — check back soon!</div>}
              </div>
              {/* weekly */}
              <div id="arena-weekly" style={{ ...S.card, padding:'16px 16px 12px', scrollMarginTop:96 }}>
                <div style={{ display:'flex', justifyContent:'space-between', alignItems:'baseline', gap:8, marginBottom:15, flexWrap:'wrap' }}>
                  <span style={{ fontSize:14, fontWeight:900 }}>🏟️ Weekly Quests</span>
                  <span style={{ padding:'4px 11px', borderRadius:99, fontSize:10.5, fontWeight:800, background:C.amberBg, color:C.amber }}>⏳ resets in <Countdown seconds={resetSec} color={C.amber} /></span>
                </div>
                {weekly.length ? weekly.map(WeeklyRow)
                  : <div style={{ padding:'26px 12px', textAlign:'center', color:C.text3, fontSize:12.5, fontWeight:700 }}>New missions drop at the weekly reset — check back soon! 🎮</div>}
              </div>
            </div>
          </>)}

          {/* ══ SEASON / DAILY teaser dialog ══ */}
          {(questPanel==='season'||questPanel==='daily') && (() => {
            const meta:any = {
              season:{ icon:'🌟', title:'Season Quest', sub:'Season 1 · multi-week epics' },
              daily:{ icon:'⚡', title:'Daily Challenge', sub:'quick daily wins' },
            }[questPanel];
            return (
              <div className="ibp-sheet-back" onClick={()=>setQuestPanel(null)}
                style={{ position:'fixed', inset:0, zIndex:70, background:'rgba(9,12,22,0.72)', display:'flex', alignItems:'center', justifyContent:'center', padding:16 }}>
                <div className="ibp-sheet" onClick={e=>e.stopPropagation()}
                  style={{ width:'100%', maxWidth:480, maxHeight:'86vh', overflowY:'auto', overscrollBehavior:'contain', borderRadius:18,
                    background:C.bg, border:'1px solid #2c3444', boxShadow:'0 30px 80px rgba(0,0,0,0.5)' }}>
                  <div style={{ position:'sticky', top:0, zIndex:3, display:'flex', alignItems:'center', gap:11, padding:'12px 14px',
                    background:'linear-gradient(118deg,#12151d,#1b2130 60%,#0d1016)', color:'#fff' }}>
                    <span style={{ fontSize:23 }}>{meta.icon}</span>
                    <div style={{ flex:1, minWidth:0 }}>
                      <div style={{ fontSize:15, fontWeight:900 }}>{meta.title}</div>
                      <div style={{ fontSize:10.5, color:'#c9b78a', fontWeight:700 }}>{meta.sub}</div>
                    </div>
                    <button onClick={()=>setQuestPanel(null)} style={{ width:44, height:44, borderRadius:99, border:'1px solid rgba(255,255,255,0.25)', background:'rgba(255,255,255,0.08)', color:'#fff', fontSize:16, fontWeight:800, cursor:'pointer', flexShrink:0 }}>✕</button>
                  </div>
                  <div style={{ textAlign:'center', padding:'30px 18px 34px' }}>
                    <div className="ibp-float" style={{ fontSize:52 }}>{meta.icon}</div>
                    <div style={{ fontSize:17, fontWeight:900, color:C.text, marginTop:10 }}>{questPanel==='season'?'Season 1 is coming':'Daily missions are coming'}</div>
                    <div style={{ fontSize:12.5, color:C.text2, lineHeight:1.6, maxWidth:360, margin:'8px auto 0' }}>
                      {questPanel==='season'
                        ? 'Multi-week epic missions with mega rewards and a season leaderboard. Stay ready — it drops soon!'
                        : 'Quick one-day wins with instant rewards, refreshed every morning. Warm up your referral link!'}
                    </div>
                    <span style={{ display:'inline-block', marginTop:14, padding:'7px 16px', borderRadius:99, fontSize:11.5, fontWeight:900, background:C.amberBg, color:C.amber }}>🔒 Unlocks soon</span>
                  </div>
                </div>
              </div>
            );
          })()}
        </div>
        );
      })()}

      {/* ══ BANNERS ══ */}
      {tab==='marketing' && (() => {
        const sizes = BSIZES.filter(s => bCat === 'all' || s.cat === bCat);
        const camps = BANNERS.filter(c => bCamp === 'all' || c.key === bCamp);
        const combos = camps.flatMap(c => sizes.map(s => ({ c, s })));
        return (
        <div className="ibp-page" style={S.page}>
          <div style={{ ...S.secLbl, display:'flex', alignItems:'baseline', gap:10, flexWrap:'wrap' }}>Brand banners
            <span style={{ fontSize:11.5, fontWeight:500, color:C.text3 }}>Real TNFX identity — dark & gold, عربي/EN · 20 standard sizes. ⬇ PNG for social — ⧉ Copy code pastes a ready banner (with YOUR referral link) into any website.</span></div>
          {/* filters: campaign + format + language + theme */}
          <div className="ibp-filters" style={{ display:'flex', gap:9, marginBottom:14, alignItems:'center', flexWrap:'wrap' }}>
            <select value={bCamp} onChange={e=>setBCamp(e.target.value)} style={{ ...S.input, background:'#fff', color:C.text, border:`1px solid ${C.borderH}` }}>
              <option value="all">All banners</option>
              {BANNERS.map((c:any)=><option key={c.key} value={c.key}>{bLang==='ar' ? c.arT : c.title}</option>)}
            </select>
            <select value={bCat} onChange={e=>setBCat(e.target.value)} style={{ ...S.input, background:'#fff', color:C.text, border:`1px solid ${C.borderH}` }}>
              {[['all','All formats'],['horizontal','Narrow horizontal'],['vertical','Narrow vertical'],['square','Square / rectangle'],['social','Social media']].map(([k,l])=><option key={k} value={k}>{l}</option>)}
            </select>
            <div style={{ display:'flex', gap:5, alignItems:'center' }}>
              {(['ar','en'] as const).map(l=>(
                <button key={l} onClick={()=>setBLang(l)}
                  style={{ padding:'6px 13px', borderRadius:99, cursor:'pointer', fontSize:11.5, fontWeight:700,
                           border: bLang===l ? `2px solid ${TNFX_ORANGE}` : `1px solid ${C.borderH}`,
                           background: bLang===l ? '#fff4ec' : '#fff', color:'#111' }}>{l==='ar' ? 'العربية' : 'English'}</button>
              ))}
            </div>
            <div style={{ display:'flex', gap:5, alignItems:'center' }}>
              {Object.entries(BTHEMES).map(([k,t]:any)=>(
                <button key={k} onClick={()=>setBTheme(k)} title={`${t.label} theme`}
                  style={{ padding:'6px 13px', borderRadius:99, cursor:'pointer', fontSize:11.5, fontWeight:700,
                           border: bTheme===k ? `2px solid ${TNFX_ORANGE}` : `1px solid ${C.borderH}`,
                           background:t.chip, color: k==='gold' ? '#111' : '#fff' }}>{t.label}</button>
              ))}
            </div>
            <span style={{ fontSize:12, color:C.text3, marginLeft:'auto' }}>{combos.length} banner(s)</span>
          </div>
          <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill,minmax(280px,1fr))', gap:13 }}>
            {combos.map(({ c, s }:any) => {
              const key = `${c.key}-${s.w}x${s.h}`;
              const uri = `data:image/svg+xml;utf8,${encodeURIComponent(bannerSVG(c, bTheme, s.w, s.h, ibCode || '', logoUri, markUri, bLang))}`;
              return (
                <div key={key} style={{ ...S.card, overflow:'hidden' }}>
                  <div style={{ height:168, display:'flex', alignItems:'center', justifyContent:'center', background:'#e9edf3', overflow:'hidden', padding:8 }}>
                    <img alt={`${c.title} ${s.w}×${s.h}`} src={uri} style={{ maxWidth:'100%', maxHeight:'100%' }} />
                  </div>
                  <div style={{ padding:'9px 12px 11px' }}>
                    <div style={{ display:'flex', justifyContent:'space-between', alignItems:'baseline', gap:8 }}>
                      <span style={{ fontSize:12.5, fontWeight:700, color:C.text, whiteSpace:'nowrap', overflow:'hidden', textOverflow:'ellipsis' }}>{bLang==='ar' ? c.arT : c.title}</span>
                      <span style={{ fontSize:10.5, color:C.text3, flexShrink:0 }}>{s.label} · {s.w}×{s.h}</span>
                    </div>
                    <div style={{ display:'flex', gap:7, marginTop:8 }}>
                      <button onClick={()=>dlBanner(c,s)} style={{ ...S.btnGhost, flex:1, padding:'7px 0', fontSize:11.5 }}>⬇ PNG</button>
                      <button onClick={()=>copyEmbed(c,s)} style={{ ...S.btnGhost, flex:1, padding:'7px 0', fontSize:11.5, color: copiedB===key ? C.green : C.blue }}>
                        {copiedB===key ? '✓ Copied' : '⧉ Copy code'}</button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
        );
      })()}

      {/* ══ EARNINGS ══ */}
      {/* ══ LEADERBOARD ══ */}
      {tab==='leaderboard' && (
        <div className="ibp-page" style={S.page}>
          <div style={{ ...S.secLbl, display:'flex', alignItems:'baseline', gap:10, flexWrap:'wrap' }}>🏅 Partner leaderboard
            <span style={{ fontSize:11.5, fontWeight:500, color:C.text3 }}>· this month · ranked by new clients &amp; deposits — not raw volume</span></div>
          {board?.me && (
            <div style={{ ...S.card, padding:'16px 18px', marginBottom:14, background:`linear-gradient(115deg, ${C.blueBg}, ${C.card})`, display:'flex', alignItems:'center', gap:16, flexWrap:'wrap' }}>
              <div style={{ fontSize:34, fontWeight:900, color:C.blue }}>#{board.my_rank}</div>
              <div style={{ flex:1, minWidth:160 }}>
                <div style={{ fontSize:13, fontWeight:800, color:C.text }}>Your rank this month</div>
                <div style={{ fontSize:12, color:C.text2 }}>out of {num(board.total)} active partners</div>
              </div>
              <div style={{ display:'flex', gap:18 }}>
                <div><div style={{ fontSize:18, fontWeight:800, color:C.green }}>{num(board.me.nda)}</div><div style={{ fontSize:10.5, color:C.text3 }}>new clients</div></div>
                <div><div style={{ fontSize:18, fontWeight:800, color:C.amber }}>{usdK(board.me.deposits)}</div><div style={{ fontSize:10.5, color:C.text3 }}>deposits</div></div>
                <div><div style={{ fontSize:18, fontWeight:800, color:C.purple }}>{num(board.me.lots)}</div><div style={{ fontSize:10.5, color:C.text3 }}>lots</div></div>
              </div>
            </div>
          )}
          <div style={{ ...S.card, overflow:'hidden' }}>
            <table style={{ width:'100%', borderCollapse:'collapse' }}>
              <thead><tr>{['#','Partner','New clients','Deposits','Lots'].map(h=>
                <th key={h} className={h==='Lots'?'hm':''} style={S.th}>{h}</th>)}</tr></thead>
              <tbody>
                {(board?.board||[]).map((r:any)=>(
                  <tr key={r.rank} className="ibp-row" style={r.me?{ background:C.blueBg }:undefined}>
                    <td style={{ ...S.td, fontWeight:800, color: r.rank<=3?C.amber:C.text2 }}>{r.rank<=3?['🥇','🥈','🥉'][r.rank-1]:r.rank}</td>
                    <td style={{ ...S.td, fontWeight: r.me?800:600, color: r.me?C.blue:C.text }}>{r.name}{r.me?' (you)':''}</td>
                    <td className="cg" style={{ ...S.td, fontWeight:700 }}>{num(r.nda)}</td>
                    <td className="ca" style={S.td}>{usd(r.deposits)}</td>
                    <td className="cp hm" style={S.td}>{num(r.lots)} lots</td>
                  </tr>
                ))}
                {(!board || (board.board||[]).length===0) && <tr><td colSpan={5} style={{ ...S.td, textAlign:'center', color:C.text3, padding:26 }}>Leaderboard builds as partners bring clients this month.</td></tr>}
              </tbody>
            </table>
          </div>
          <div style={{ fontSize:11.5, color:C.text3, marginTop:12 }}>Other partners are shown anonymously. Bring genuine new clients to climb — deposits count too, raw volume barely moves your rank.</div>
        </div>
      )}

      {/* ══ SUB-IBs ══ */}
      {tab==='subibs' && (
        <div className="ibp-page" style={S.page}>
          <div style={{ ...S.secLbl, display:'flex', alignItems:'baseline', gap:10, flexWrap:'wrap' }}>Your sub-partners
            <span style={{ fontSize:11.5, fontWeight:500, color:C.text3 }}>· you earn {subIbs?.override_pct||10}% override on every sub-partner's commission</span></div>
          {subIbs && (
            <div className="ibp-g3" style={{ display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:12, marginBottom:14 }}>
              <Kpi label="Sub-partners" value={num(subIbs.count||0)} accent={C.blue} icon="🤝" />
              <Kpi label="Their commission" value={usd((subIbs.sub_ibs||[]).reduce((s:number,x:any)=>s+(x.their_commission||0),0))} accent={C.amber} icon="📊" />
              <Kpi label="Your override" value={usd(subIbs.override_total||0)} sub={`${subIbs.override_pct||10}% total`} accent={C.green} icon="💰" />
            </div>
          )}
          <div style={{ ...S.card, overflow:'hidden' }}>
            <div style={{ overflowX:'auto', maxHeight:560 }}>
              <table style={{ width:'100%', borderCollapse:'collapse' }}>
                <thead><tr>{['Sub-partner','Code','Level','Clients','Volume','Their commission','Your 10% override'].map(h=>
                  <th key={h} className={['Code','Level','Clients','Volume'].includes(h)?'hm':''} style={S.th}>{h}</th>)}</tr></thead>
                <tbody>
                  {(subIbs?.sub_ibs||[]).map((s:any,i:number)=>(
                    <tr key={i} className="ibp-row">
                      <td style={{ ...S.td, fontWeight:600 }}>{String(s.name||'—').trim().split(/\s+/).slice(0,2).join(' ')}</td>
                      <td className="cb hm" style={{ ...S.td, fontFamily:'monospace' }}>{s.ib_code||'—'}</td>
                      <td className="hm" style={S.td}><span style={badge(C.blueBg,C.blue)}>L{s.ib_level}</span></td>
                      <td className="cm hm" style={S.td}>{num(s.clients)}</td>
                      <td className="cp hm" style={S.td}>{num(s.volume)} lots</td>
                      <td className="ca" style={{ ...S.td, fontWeight:600 }}>{usd(s.their_commission)}</td>
                      <td className="cg" style={{ ...S.td, fontWeight:700 }}>{usd(s.your_override)}</td>
                    </tr>
                  ))}
                  {(!subIbs || (subIbs.sub_ibs||[]).length===0) && <tr><td colSpan={7} style={{ ...S.td, textAlign:'center', color:C.text3, padding:26 }}>No sub-partners yet. Share your referral link with people who want to become IBs — you earn 10% of everything they make.</td></tr>}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* ══ PROFILE ══ */}
      {tab==='profile' && profileForm && (
        <div className="ibp-page" style={S.page}>
          <div style={{ ...S.card, padding:22, maxWidth:640 }}>
            <div style={{ display:'flex', alignItems:'center', gap:16, marginBottom:20 }}>
              <div style={{ width:74, height:74, borderRadius:'50%', overflow:'hidden', background:C.blueBg, color:C.blue, display:'flex', alignItems:'center', justifyContent:'center', fontSize:26, fontWeight:800, flexShrink:0 }}>
                {R?.photo_url ? <img src={R.photo_url} alt="" style={{ width:'100%', height:'100%', objectFit:'cover' }} /> : initialsOf(ibName)}</div>
              <div>
                <div style={{ fontSize:18, fontWeight:800, color:C.text }}>{ibName}</div>
                <div style={{ fontSize:12, color:C.text3 }}>IB code {R?.ext_ib_id ?? ibCode} · {tierName}</div>
                <label style={{ ...S.btnGhost, display:'inline-block', marginTop:8, cursor:'pointer', fontSize:12 }}>
                  📷 Upload photo
                  <input type="file" accept="image/*" style={{ display:'none' }} onChange={async e=>{
                    const f=e.target.files?.[0]; if(!f||!ibId) return;
                    const fd=new FormData(); fd.append('file', f);
                    try { const r=await fetch(`/api/ibs/${ibId}/photo`, { method:'POST', headers:{ Authorization:`Bearer ${localStorage.getItem('token')||''}` }, body:fd }); const j=await r.json(); if(j.photo_url){ apiGet(`/ibs/${ibId}?period=all_time`).then(setR); } } catch { alert('Upload failed'); }
                  }} />
                </label>
              </div>
            </div>
            {[['phone','Phone'],['country','Country'],['city','City']].map(([k,lbl]:any)=>(
              <div key={k} style={{ marginBottom:12 }}>
                <label style={{ fontSize:11.5, color:C.text2, fontWeight:600, display:'block', marginBottom:5 }}>{lbl}</label>
                <input value={profileForm[k]||''} onChange={e=>setProfileForm((f:any)=>({...f,[k]:e.target.value}))}
                  style={{ width:'100%', padding:'10px 12px', borderRadius:9, border:`1px solid ${C.borderH}`, background:'#fff', color:C.text, fontSize:13.5, outline:'none', boxSizing:'border-box' }} />
              </div>
            ))}
            <div style={{ marginBottom:14 }}>
              <label style={{ fontSize:11.5, color:C.text2, fontWeight:600, display:'block', marginBottom:5 }}>About you (optional)</label>
              <textarea value={profileForm.bio||''} onChange={e=>setProfileForm((f:any)=>({...f,bio:e.target.value}))} rows={3}
                style={{ width:'100%', padding:'10px 12px', borderRadius:9, border:`1px solid ${C.borderH}`, background:'#fff', color:C.text, fontSize:13.5, outline:'none', boxSizing:'border-box', resize:'vertical' }} />
            </div>
            <button onClick={async()=>{ try{ await apiPost(`/ibs/${ibId}/profile`, profileForm); apiGet(`/ibs/${ibId}?period=all_time`).then(setR); alert('Profile saved'); }catch{ alert('Save failed'); } }} style={S.btnPri}>Save profile</button>

            {/* ── Social channels — read-only; the IB can ADD, only the desk can edit/remove ── */}
            <div style={{ marginTop:24, paddingTop:18, borderTop:`1px solid ${C.border}` }}>
              <div style={{ ...S.secLbl, marginBottom:3 }}>Your channels</div>
              <div style={{ fontSize:11.5, color:C.text3, marginBottom:12 }}>Add more anytime. To change or remove a channel, contact the desk.</div>
              {(R?.social_links||[]).length>0 ? (R.social_links||[]).map((s:any,i:number)=>(
                <div key={i} style={{ display:'flex', alignItems:'center', gap:10, padding:'9px 11px', border:`1px solid ${C.border}`, borderRadius:9, marginBottom:8, background:C.card2 }}>
                  <span style={{ fontSize:12, fontWeight:700, color:C.text, width:82, flexShrink:0, textTransform:'capitalize' }}>{s.label||s.platform}</span>
                  <a href={(s.url||'').startsWith('http')?s.url:`https://${s.url}`} target="_blank" rel="noreferrer" style={{ flex:1, minWidth:0, fontSize:12, color:C.blue, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{(s.url||'').replace(/^https?:\/\//,'')}</a>
                  <span title="Verified" style={{ fontSize:12, color:C.green, fontWeight:800, flexShrink:0 }}>✓</span>
                </div>
              )) : <div style={{ fontSize:12, color:C.text3, marginBottom:8 }}>No channels added yet.</div>}
              <div style={{ display:'flex', gap:8, marginTop:12, flexWrap:'wrap', alignItems:'stretch' }}>
                <select value={addSoc.platform} onChange={e=>setAddSoc((a:any)=>({ ...a, platform:e.target.value, handle:'', msg:'' }))}
                  style={{ padding:'0 10px', height:40, borderRadius:9, border:`1px solid ${C.borderH}`, background:'#fff', color:C.text, fontSize:13 }}>
                  <option value="">+ Add a channel…</option>
                  {SOCIALS.map((s:any)=><option key={s.k} value={s.k}>{s.label}</option>)}
                </select>
                {addSoc.platform && (() => {
                  const cat = SOCIALS.find((x:any)=>x.k===addSoc.platform);
                  return <div style={{ flex:1, minWidth:190, display:'flex', border:`1px solid ${C.borderH}`, borderRadius:9, overflow:'hidden', background:'#fff' }}>
                    {cat?.mode==='prefix' && <span style={{ padding:'0 9px', display:'flex', alignItems:'center', fontSize:12.5, color:C.text3, background:C.card2, whiteSpace:'nowrap' }}>{cat.prefix}</span>}
                    {cat?.mode==='username' && <span style={{ padding:'0 11px', display:'flex', alignItems:'center', fontSize:15, fontWeight:700, color:C.text3, background:C.card2 }}>@</span>}
                    <input value={addSoc.handle} onChange={e=>setAddSoc((a:any)=>({ ...a, handle:e.target.value, msg:'' }))} onKeyDown={e=>{ if(e.key==='Enter'){ e.preventDefault(); submitSocial(); } }}
                      placeholder={cat?.ph||'…'} autoCapitalize="none" spellCheck={false}
                      style={{ flex:1, minWidth:0, height:40, padding:'0 11px', border:'none', outline:'none', color:C.text, fontSize:13, background:'transparent' }} />
                  </div>;
                })()}
                {addSoc.platform && <button disabled={addSoc.busy || !addSoc.handle.trim()} onClick={submitSocial}
                  style={{ ...S.btnPri, opacity:(addSoc.busy||!addSoc.handle.trim())?0.5:1 }}>{addSoc.busy?'…':'Add'}</button>}
              </div>
              {addSoc.msg && <div style={{ fontSize:12, marginTop:8, color: addSoc.ok?C.green:C.red }}>{addSoc.msg}</div>}
            </div>
          </div>
        </div>
      )}

      {tab==='earnings' && (
        <div className="ibp-page" style={S.page}>
          <div className="ibp-g4" style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:12, marginBottom:14 }}>
            <Kpi label="Commissions"  value={usd(payAvailable)} sub="available to withdraw now" accent={C.green} icon="💰" />
            <Kpi label="Paid out"     value={usd(k.paid)}       accent={C.text}  icon="✔" />
            <Kpi label="Total earned" value={usd(k.commission)} sub="lifetime"   accent={C.amber} icon="📈" />
            <Kpi label="Rate"         value={`${level} pts/lot`} sub={tierName}  accent={C.purple} icon="🏅" />
          </div>
          {/* Withdraw / internal transfer + payout history */}
          <div style={{ ...S.card, padding:16, marginBottom:16 }}>
            <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:12, flexWrap:'wrap' }}>
              <div style={S.secLbl}>Payouts</div>
              <div style={{ marginLeft:'auto', display:'flex', gap:8, flexWrap:'wrap', alignItems:'center' }}>
                {(R?.ib_level || 5) >= 6 ? (<>
                  <button onClick={()=>{ setPayForm({ amount:'', to_account:'' }); setPayModal('withdraw'); }} style={S.btnPri}>💸 Withdraw</button>
                  <button onClick={()=>{ setPayForm({ amount:'', to_account:(R?.accounts?.[0]?.account||'') }); setPayModal('transfer'); }} style={S.btnGhost}>🔁 Internal transfer</button>
                </>) : (
                  <span title="Withdrawals and transfers unlock at Level 6. Keep introducing genuine new clients to get promoted." style={{ ...badge(C.amberBg, C.amber), fontSize:11.5, fontWeight:800, padding:'7px 12px' }}>🔒 Unlocks at Level 6</span>
                )}
                {ibId && <button onClick={()=>downloadStatement('all_time')} style={S.btnGhost}>⬇ Statement</button>}
                {ibId && <button onClick={()=>downloadStatement('this_year')} style={S.btnGhost}>📅 This year</button>}
              </div>
            </div>
            {(R?.ib_level || 5) < 6 && (
              <div style={{ background:C.amberBg, color:C.amber, border:`1px solid ${C.amber}44`, borderRadius:10, padding:'10px 12px', fontSize:12, fontWeight:600, marginBottom:12, lineHeight:1.55 }}>
                🔒 As a Level 5 IB, withdrawals and internal transfers are locked. Keep bringing genuine new
                clients — once you're promoted to Level 6, this unlocks automatically.
              </div>
            )}
            {ibOps?.summary && (
              <div className="ibp-g3" style={{ display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:10, marginBottom:12 }}>
                <MiniStat label="Total paid out" value={usd(ibOps.summary.paid_out)} accent={C.red} />
                <MiniStat label="Withdrawn" value={usd(ibOps.summary.withdrawn)} accent={C.amber} />
                <MiniStat label="Transferred" value={usd(ibOps.summary.transferred)} accent={C.blue} />
              </div>
            )}
            <div style={{ overflowX:'auto', maxHeight:280 }}>
              <table style={{ width:'100%', borderCollapse:'collapse' }}>
                <thead><tr>{['Date','Type','Amount','Method','To','Status'].map(h=>
                  <th key={h} className={['Method','To'].includes(h)?'hm':''} style={S.th}>{h}</th>)}</tr></thead>
                <tbody>
                  {(ibOps?.operations||[]).slice(0,50).map((o:any,i:number)=>{
                    const st = o.status==='Approved'?C.green:o.status==='Declined'?C.red:C.amber;
                    return (
                      <tr key={i} className="ibp-row">
                        <td className="cm" style={S.td}>{o.op_date?String(o.op_date).slice(0,10):'—'}</td>
                        <td style={S.td}>{o.request_type?.replace(' Wallet','')}</td>
                        <td style={{ ...S.td, fontWeight:600 }}>{usd(o.amount)}</td>
                        <td className="cm hm" style={S.td}>{o.payment_type||'—'}</td>
                        <td className="cm hm" style={S.td}>{o.to_account||'—'}</td>
                        <td style={S.td}><span style={badge(`${st}22`, st)}>{o.status}</span></td>
                      </tr>
                    );
                  })}
                  {(!ibOps || (ibOps.operations||[]).length===0) && <tr><td colSpan={6} style={{ ...S.td, textAlign:'center', color:C.text3, padding:20 }}>No payouts yet</td></tr>}
                </tbody>
              </table>
            </div>
          </div>

          {/* Level promotion history */}
          {(ibPromos?.promotions?.length > 0) && (
            <div style={{ ...S.card, padding:16, marginBottom:16 }}>
              <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:12 }}>
                <div style={S.secLbl}>🎖 Your level history</div>
                <div style={{ marginLeft:'auto', fontSize:11.5, color:C.text3 }}>current: <b style={{ color:C.purple }}>{level} pts/lot ({tierName})</b></div>
              </div>
              <div style={{ position:'relative', paddingLeft:20 }}>
                <div style={{ position:'absolute', left:5, top:4, bottom:4, width:2, background:C.border }} />
                {(ibPromos.promotions||[]).map((p:any,i:number)=>{
                  const demo = p.direction === 'demotion';
                  const col = demo ? C.red : C.green;
                  return (
                  <div key={i} style={{ position:'relative', marginBottom:14 }}>
                    <div style={{ position:'absolute', left:-20, top:2, width:11, height:11, borderRadius:99, background:col, border:`2px solid ${C.card||'#fff'}` }} />
                    <div style={{ display:'flex', alignItems:'center', gap:8, flexWrap:'wrap' }}>
                      <span className="cm" style={{ fontSize:12, color:C.text2 }}>{p.date}</span>
                      <span style={badge('#8892a022', C.text2)}>Level {p.from_level}</span>
                      <span style={{ color:col, fontWeight:700 }}>{demo ? '↓' : '→'}</span>
                      <span style={badge(`${col}22`, col)}>Level {p.to_level}</span>
                      <span style={{ fontSize:11, color:col }}>{demo ? 'Demoted' : 'Promoted! 🎉'}</span>
                    </div>
                  </div>
                  );})}
              </div>
            </div>
          )}

          {/* Auto-withdraw (Ovadot) + annual statement */}
          {autoWd && (
            <div style={{ ...S.card, padding:16, marginBottom:16 }}>
              <div style={{ display:'flex', alignItems:'center', gap:10, marginBottom:12, flexWrap:'wrap' }}>
                <div style={S.secLbl}>⚙️ Auto-withdraw</div>
                <label style={{ marginLeft:'auto', display:'flex', alignItems:'center', gap:7, cursor:'pointer', fontSize:12.5, color:C.text2 }}>
                  <input type="checkbox" checked={autoWd.enabled} onChange={e=>setAutoWd({...autoWd, enabled:e.target.checked})} />
                  Pay me automatically to my Ovadot wallet
                </label>
              </div>
              <div style={{ display:'flex', gap:10, flexWrap:'wrap', alignItems:'flex-end' }}>
                <div style={{ flex:'1 1 140px' }}>
                  <label style={{ fontSize:11, color:C.text3, display:'block', marginBottom:4 }}>When my balance reaches</label>
                  <input type="number" value={autoWd.threshold||''} onChange={e=>setAutoWd({...autoWd, threshold:+e.target.value})} placeholder="e.g. 500"
                    style={{ width:'100%', padding:'9px 11px', borderRadius:9, border:`1px solid ${C.borderH}`, background:'#fff', color:C.text, fontSize:13, outline:'none', boxSizing:'border-box' }} />
                </div>
                <div style={{ flex:'2 1 200px' }}>
                  <label style={{ fontSize:11, color:C.text3, display:'block', marginBottom:4 }}>Ovadot wallet</label>
                  <input value={autoWd.wallet||''} onChange={e=>setAutoWd({...autoWd, wallet:e.target.value})} placeholder="Your Ovadot wallet number"
                    style={{ width:'100%', padding:'9px 11px', borderRadius:9, border:`1px solid ${C.borderH}`, background:'#fff', color:C.text, fontSize:13, outline:'none', boxSizing:'border-box' }} />
                </div>
                <button onClick={async()=>{ try{ const r:any=await apiPost(`/ibs/${ibId}/auto-withdraw`, autoWd); if(r?.ok){ alert('Auto-withdraw saved'); } else alert(r?.detail||'Could not save'); }catch(e:any){ alert(e?.message||'Could not save'); } }} style={S.btnPri}>Save</button>
              </div>
              <div style={{ fontSize:11, color:C.text3, marginTop:9 }}>When on, we auto-create a withdrawal to your Ovadot wallet each time your available balance passes the threshold (min $50). You'll be notified.</div>
            </div>
          )}

          {/* Commission projection calculator */}
          {(() => {
            const rate = level;   // pts/lot ≈ $/lot on gold & majors
            const clients = calcInputs.clients, lotsPer = calcInputs.lots;
            const monthly = clients * lotsPer * rate;
            return (
              <div style={{ ...S.card, padding:16, marginBottom:16 }}>
                <div style={S.secLbl}>🧮 Earnings calculator</div>
                <div style={{ display:'flex', gap:12, flexWrap:'wrap', alignItems:'flex-end' }}>
                  <div style={{ flex:'1 1 130px' }}>
                    <label style={{ fontSize:11, color:C.text3, display:'block', marginBottom:4 }}>Active clients</label>
                    <input type="number" value={calcInputs.clients} onChange={e=>setCalcInputs({...calcInputs, clients:Math.max(0,+e.target.value)})}
                      style={{ width:'100%', padding:'9px 11px', borderRadius:9, border:`1px solid ${C.borderH}`, background:'#fff', color:C.text, fontSize:13, outline:'none', boxSizing:'border-box' }} />
                  </div>
                  <div style={{ flex:'1 1 130px' }}>
                    <label style={{ fontSize:11, color:C.text3, display:'block', marginBottom:4 }}>Lots each / month</label>
                    <input type="number" value={calcInputs.lots} onChange={e=>setCalcInputs({...calcInputs, lots:Math.max(0,+e.target.value)})}
                      style={{ width:'100%', padding:'9px 11px', borderRadius:9, border:`1px solid ${C.borderH}`, background:'#fff', color:C.text, fontSize:13, outline:'none', boxSizing:'border-box' }} />
                  </div>
                  <div style={{ flex:'1 1 160px', textAlign:'center', background:C.greenBg, borderRadius:11, padding:'10px 12px' }}>
                    <div style={{ fontSize:22, fontWeight:900, color:C.green }}>{usd(monthly)}</div>
                    <div style={{ fontSize:10.5, color:C.text3 }}>/ month at {rate} pts/lot ({tierName})</div>
                    <div style={{ fontSize:11, color:C.text2, marginTop:3 }}>{usd(monthly*12)} / year</div>
                  </div>
                </div>
                <div style={{ fontSize:11, color:C.text3, marginTop:9 }}>Reach {tierName==='Prime IB'?'the top grade':'a higher grade'} and the same book pays more — every grade adds $1/lot.</div>
              </div>
            );
          })()}

          {payModal && (
            <div onClick={()=>setPayModal(null)} style={{ position:'fixed', inset:0, background:'rgba(16,24,40,0.45)', zIndex:100, display:'flex', alignItems:'center', justifyContent:'center', padding:16 }}>
              <div onClick={e=>e.stopPropagation()} style={{ ...S.card, width:400, maxWidth:'95vw', padding:22 }}>
                <div style={{ fontSize:16, fontWeight:800, color:C.text, marginBottom:8 }}>{payModal==='withdraw'?'💸 Request withdrawal':'🔁 Internal transfer'}</div>
                <div style={{ fontSize:12, marginBottom:12, padding:'8px 10px', borderRadius:8, background:C.greenBg, color:C.green, fontWeight:600 }}>
                  Available: ${payAvailable.toFixed(2)} <span style={{ color:C.text3, fontWeight:400 }}>· minimum ${MIN_PAYOUT}{payPending>0?` · $${payPending.toFixed(2)} pending approval`:''}</span>
                </div>
                <label style={{ fontSize:11.5, color:C.text2, fontWeight:600, display:'block', marginBottom:5 }}>Amount (USD)</label>
                <input type="number" min={MIN_PAYOUT} max={payAvailable} value={payForm.amount} onChange={e=>setPayForm((f:any)=>({...f,amount:e.target.value}))} placeholder="0.00"
                  style={{ width:'100%', padding:'9px 11px', borderRadius:9, border:`1px solid ${C.borderH}`, background:'#fff', color:C.text, fontSize:13, outline:'none', boxSizing:'border-box', marginBottom:12 }} />
                {payModal==='withdraw' && (<>
                  <label style={{ fontSize:11.5, color:C.text2, fontWeight:600, display:'block', marginBottom:5 }}>Withdrawal method</label>
                  <select value="ovadot" onChange={()=>{}}
                    style={{ width:'100%', padding:'9px 11px', borderRadius:9, border:`1px solid ${C.borderH}`, background:'#fff', color:C.text, fontSize:13, outline:'none', boxSizing:'border-box', marginBottom:8 }}>
                    <option value="ovadot">Ovadot Wallet</option>
                  </select>
                  <label style={{ fontSize:11.5, color:C.text2, fontWeight:600, display:'block', marginBottom:5 }}>Your Ovadot wallet number</label>
                  <input value={payForm.wallet || ''} onChange={e=>setPayForm((f:any)=>({...f,wallet:e.target.value}))}
                    placeholder="e.g. OV-12345678 / wallet email or phone"
                    style={{ width:'100%', padding:'9px 11px', borderRadius:9, border:`1px solid ${C.borderH}`, background:'#fff', color:C.text, fontSize:13, outline:'none', boxSizing:'border-box', marginBottom:6 }} />
                  <div style={{ fontSize:11.5, marginBottom:12 }}>
                    <a href="https://ovadot.com" target="_blank" rel="noreferrer" style={{ color:C.blue, fontWeight:600, textDecoration:'none' }}>
                      Don't have a wallet? Open your free Ovadot account →</a>
                  </div>
                </>)}
                {payModal==='transfer' && (<>
                  <label style={{ fontSize:11.5, color:C.text2, fontWeight:600, display:'block', marginBottom:5 }}>To trading account</label>
                  <select value={payForm.to_account} onChange={e=>setPayForm((f:any)=>({...f,to_account:e.target.value}))}
                    style={{ width:'100%', padding:'9px 11px', borderRadius:9, border:`1px solid ${C.borderH}`, background:'#fff', color:C.text, fontSize:13, outline:'none', boxSizing:'border-box', marginBottom:12 }}>
                    {(R?.accounts||[]).map((a:any,i:number)=><option key={i} value={a.account}>{a.platform} · #{a.account}</option>)}
                    {(!R?.accounts || R.accounts.length===0) && <option value="">No trading accounts</option>}
                  </select>
                </>)}
                <div style={{ fontSize:11.5, color:C.text3, marginBottom:14 }}>{payModal==='transfer'?'Moves commission to your selected trading account. Needs admin approval.':'Withdrawal request — needs admin approval.'}</div>
                <div style={{ display:'flex', gap:8, justifyContent:'flex-end' }}>
                  <button onClick={()=>setPayModal(null)} style={S.btnGhost}>Cancel</button>
                  <button onClick={submitPayout}
                    disabled={!(parseFloat(payForm.amount) >= MIN_PAYOUT && parseFloat(payForm.amount) <= payAvailable)}
                    style={{ ...S.btnPri, opacity: (parseFloat(payForm.amount) >= MIN_PAYOUT && parseFloat(payForm.amount) <= payAvailable) ? 1 : 0.5 }}>Submit request</button>
                </div>
              </div>
            </div>
          )}

          <div style={S.secLbl}>Commission by client</div>
          <div style={{ ...S.card, overflow:'hidden' }}>
            <div style={{ overflowX:'auto', maxHeight:560 }}>
              <table style={{ width:'100%', borderCollapse:'collapse' }}>
                <thead><tr>{['Client','Login','Lots','Pts/lot','Commission','Status'].map(h=><th key={h} style={S.th}>{h}</th>)}</tr></thead>
                <tbody>
                  {commissions.map((t:any,i:number)=>(
                    <tr key={i} className="ibp-row">
                      <td style={{ ...S.td, fontWeight:500 }}>{t.client_name}</td>
                      <td className="cb" style={{ ...S.td, fontFamily:'monospace' }}>#{t.client_login}</td>
                      <td className="cp" style={S.td}>{num(t.lots)}</td>
                      <td className="cm" style={S.td}>{t.pts_per_lot}</td>
                      <td className="ca" style={{ ...S.td, fontWeight:700 }}>{usd(t.commission_usd)}</td>
                      <td style={S.td}><span style={badge(t.status==='paid'?C.greenBg:C.amberBg, t.status==='paid'?C.green:C.amber)}>{t.status}</span></td>
                    </tr>
                  ))}
                  {commissions.length===0 && <EmptyRow cols={6} loading={loadingPreview} />}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* Scoped overrides — the admin app injects global dark rules (td/input/hover);
          beat them with higher-specificity !important so the light portal stays light. */}
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
        .ibp *::-webkit-scrollbar{width:10px;height:10px}
        .ibp *::-webkit-scrollbar-thumb{background:#cfd6e2;border-radius:99px}
        .ibp *::-webkit-scrollbar-thumb:hover{background:#b6c0d0}
        .ibp *::-webkit-scrollbar-track{background:transparent}
        .ibp-tab:hover{color:${C.blue} !important}
        .ibp td{color:${C.text} !important}
        .ibp th{color:${C.text3} !important}
        .ibp td.cg{color:${C.green} !important}
        .ibp td.cr{color:${C.red} !important}
        .ibp td.cb{color:${C.blue} !important}
        .ibp td.cp{color:${C.purple} !important}
        .ibp td.ca{color:${C.amber} !important}
        .ibp td.cm{color:${C.text2} !important}
        .ibp tr:hover td{background:transparent !important}
        .ibp-row:hover td{background:${C.soft} !important}
        .ibp-only-sm{display:none}
        .ibp input, .ibp select, .ibp textarea{background:#ffffff !important; color:${C.text} !important; border-color:${C.borderH} !important}
        .ibp input::placeholder{color:#9aa6b8}
        /* shine travels LEFT → RIGHT (with 200% background-size, higher background-position %
           shifts the gradient leftwards — so animate from +160% down to -160%) */
        @keyframes ibpShimmer{0%{background-position:160% 0}100%{background-position:-160% 0}}
        @keyframes ibpPulse{0%,100%{box-shadow:0 0 0 0 rgba(47,107,255,0.45)}50%{box-shadow:0 0 0 7px rgba(47,107,255,0)}}
        @keyframes ibpFloat{0%,100%{transform:translateY(0)}50%{transform:translateY(-3px)}}
        .ibp-shimmer{background:linear-gradient(100deg, rgba(255,255,255,0) 20%, rgba(255,255,255,0.55) 50%, rgba(255,255,255,0) 80%);background-size:200% 100%;animation:ibpShimmer 1.8s linear infinite}
        .ibp-pulse{animation:ibpPulse 2s ease-out infinite}
        .ibp-float{animation:ibpFloat 2.8s ease-in-out infinite}
        .ibp-bar-fill{transition:width .9s cubic-bezier(.22,1,.36,1)}
        /* RTL languages: the PAGE flips, but the MAIN NAV BAR, TABLES + FILTER ROWS stay
           left-to-right and keep their English numbers/headers (desk rule Jul 15 2026). */
        .ibp[dir="rtl"] table, .ibp[dir="rtl"] .ibp-filters, .ibp[dir="rtl"] .ibp-tabs,
        .ibp[dir="rtl"] .ibp-head { direction:ltr !important; }
        .ibp[dir="rtl"] th, .ibp[dir="rtl"] td { text-align:left !important; }
        /* the notification dropdown must never spill off a phone screen */
        @media (max-width: 560px){
          .ibp-bell-menu{ position:fixed !important; top:58px !important; right:8px !important; left:8px !important; width:auto !important; max-width:none !important; }
        }
        /* ── Challenge Arena FX ── */
        @keyframes ibpGlow{0%,100%{box-shadow:0 0 0 0 rgba(19,168,88,0.38)}50%{box-shadow:0 0 0 8px rgba(19,168,88,0)}}
        .ibp-glow{animation:ibpGlow 1.9s ease-out infinite}
        @keyframes ibpPop{0%{transform:scale(.3);opacity:0}35%{transform:scale(1.15);opacity:1}55%{transform:scale(1)}82%{transform:scale(1);opacity:1}100%{transform:scale(.96) translateY(-14px);opacity:0}}
        .ibp-pop{animation:ibpPop 1.65s cubic-bezier(.22,1,.36,1) forwards}
        @keyframes ibpConfetti{0%{transform:translateY(0) rotate(0deg);opacity:0}18%{opacity:1}100%{transform:translateY(-150px) rotate(340deg);opacity:0}}
        .ibp-confetti{animation:ibpConfetti 1.55s ease-out forwards}
        .ibp-quest{transition:transform .22s ease, box-shadow .22s ease}
        .ibp-quest:hover{transform:translateY(-3px);box-shadow:0 10px 28px rgba(23,32,48,0.12)}
        .ibp-cta{transition:transform .15s ease, filter .15s ease}
        .ibp-cta:hover{transform:translateY(-1.5px);filter:brightness(1.07)}
        .ibp-cta:active{transform:translateY(0) scale(.98)}
        /* ── Quest hub / mission core FX (RoK-style) ── */
        @keyframes ibpSpinK{to{transform:rotate(360deg)}}
        @keyframes ibpSpinRevK{to{transform:rotate(-360deg)}}
        .ibp-spin-slow{animation:ibpSpinK 11s linear infinite;transform-origin:center}
        .ibp-spin-med{animation:ibpSpinK 2.8s linear infinite;transform-origin:center}
        .ibp-spin-rev{animation:ibpSpinRevK 6s linear infinite;transform-origin:center}
        @keyframes ibpBreatheK{0%,100%{opacity:.4}50%{opacity:1}}
        .ibp-breathe{animation:ibpBreatheK 1.7s ease-in-out infinite}
        @keyframes ibpRedDotK{0%,100%{box-shadow:0 0 0 0 rgba(224,49,71,0.55)}50%{box-shadow:0 0 0 6px rgba(224,49,71,0)}}
        .ibp-reddot{animation:ibpRedDotK 1.5s ease-out infinite}
        .ibp-hub{transition:transform .18s ease, box-shadow .18s ease}
        .ibp-hub:hover{transform:translateY(-3px)}
        .ibp-hub:active{transform:scale(.96)}
        @keyframes ibpSheetK{from{transform:translateY(30px) scale(.985);opacity:0}to{transform:none;opacity:1}}
        .ibp-sheet{animation:ibpSheetK .3s cubic-bezier(.22,1,.36,1)}
        @keyframes ibpFadeK{from{opacity:0}to{opacity:1}}
        .ibp-sheet-back{animation:ibpFadeK .22s ease}
        .ibp-ticker::-webkit-scrollbar{height:6px}
        /* ── MOBILE FIRST for IBs (they browse on phones). Class hooks (ibp-page/-head/
           -tabs/-cols/-g3/-g4/-g5) beat the inline styles with !important. */
        @media (max-width: 1020px){
          .ibp-cols{grid-template-columns:1fr !important}            /* two-column layouts stack */
        }
        @media (max-width: 760px){
          .ibp-page{padding:12px 10px !important}
          .ibp-head{padding:10px 12px !important}
          .ibp-tabs{padding:0 6px !important}
          .ibp-tabs > div{padding:11px 11px !important; font-size:12.5px !important}
          .ibp-g5,.ibp-g4{grid-template-columns:repeat(2,1fr) !important; gap:9px !important}
          .ibp-g3{grid-template-columns:1fr !important}
          .ibp input, .ibp select{max-width:100% !important; width:100% !important}
          .ibp table{font-size:12px; table-layout:auto; width:100% !important}
          .ibp td, .ibp th{padding:9px 7px !important; white-space:normal !important; word-break:break-word}
          .ibp-hide-sm{display:none !important}
          /* header fits on phones: it WRAPS (no overlap). Mobile shows FIRST NAME + available
             balance only; tier badge, IB code and the lifetime figure fold away (.ibp-idsub). */
          .ibp-idblock{ text-align:left !important; }
          .ibp-idblock .ibp-idsub{ display:none !important; }
          .ibp-only-sm{ display:inline !important; }
          /* NO sideways scrolling on phones: secondary table columns hide (.hm), the rest fits */
          .ibp .hm{display:none !important}
          /* filters FIT the screen: search takes its own line, dropdowns share lines below */
          .ibp-filters{flex-wrap:wrap !important; overflow-x:visible !important}
          .ibp-filters input{flex:1 1 100% !important; width:100% !important; min-width:0 !important}
          .ibp-filters select{flex:1 1 30% !important; width:auto !important; min-width:0 !important; max-width:none !important}
          .ibp-filters button, .ibp-filters span{flex:0 0 auto !important}
          /* the 3 promotion meters stay SIDE BY SIDE on phones (one compact box, not a long list) */
          .ibp-req{grid-template-columns:repeat(3,1fr) !important; gap:8px !important}
          /* hero stacks: number on top, sparkline below-left, actions full width */
          .ibp-hero{padding:17px 15px !important}
          .ibp-hero-in{flex-direction:column !important; align-items:flex-start !important; gap:13px !important}
          .ibp-hero-spark{text-align:left !important}
          .ibp-qa{gap:7px !important}
          .ibp-qa button, .ibp-qa a{flex:1 1 46% !important; text-align:center !important; padding:10px 8px !important}
          /* weekly arena cards go single column on phones */
          .ibp-wk{grid-template-columns:1fr !important}
          /* ── Challenge Arena on phones: compact, thumb-friendly ── */
          .ibp-ar-claim{text-align:left !important; width:100% !important; border-top:1px solid rgba(255,255,255,0.12); padding-top:13px !important}
          .ibp-hub-grid{grid-template-columns:repeat(2,1fr) !important}   /* quest icons 2×2 */
          .ibp-rail{width:46px !important}
          .ibp-quest{padding:12px 12px !important}
          .ibp-qrow{gap:9px !important; padding:11px 10px !important}
          .ibp-qact{margin-left:auto}                 /* CLAIM hugs the right when the row wraps */
          .ibp-core-row{flex-direction:column !important; gap:16px !important; padding:16px 14px !important}
          .ibp-core-row > div:last-child{width:100%}
          /* dialog = bottom sheet; 84vh (visible-viewport-safe), 90dvh where supported below */
          .ibp-sheet-back{align-items:flex-end !important; padding:0 !important}
          .ibp-sheet{max-width:100% !important; max-height:84vh !important; border-radius:18px 18px 0 0 !important}
        }
        @supports (height: 1dvh){
          @media (max-width: 760px){ .ibp-sheet{max-height:90dvh !important} }
        }
        /* desktop: search + all filters in ONE row */
        .ibp-filters{flex-wrap:nowrap; overflow-x:auto; -webkit-overflow-scrolling:touch; scrollbar-width:thin}
        .ibp-filters > *{flex:0 0 auto}
        @media (max-width: 420px){
          .ibp-g5,.ibp-g4{grid-template-columns:1fr 1fr !important}
        }
      `}</style>
    </div>
  );
}

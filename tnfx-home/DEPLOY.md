# TNFX.co homepage rebuild — deploy notes

Built 2026-07-21, restyled 2026-07-22 by Claude Fable 5. Standalone static homepage — no
WordPress, no build step, no external requests (all CSS/JS inline, logos AND brand fonts
embedded as data-URIs).

**LIVE PREVIEW: https://my1.tnfx.co/newhome/** (static copy in `frontend/build/newhome/` —
note: the next frontend `npm run build` wipes it; re-copy from this folder after rebuilds).

**Brand system (v5 — current): the WORDMARK's identity, clean.** Archivo Black display
(web twin of the banners' Arial Black), skewed uppercase two-line hero (orange + white — the
ad-banner formula), hot orange `#FF4700→#FF9100` as the only accent on flat charcoal
`#0B0C0F`/`#121317`, Arial body (no font embed), GE Dinar One for Arabic. Ornament stripped.

**Superseded (v3 — "dark & premium, market-first")**:
- Canvas: TNFX navy deepened to near-black (`#040B18`/`#0A1526` cards, periwinkle-tinted
  hairlines), orange `#F8500A→#FF9A3D` CTAs (navy text for contrast), gold `#E8B84B` accents
  + the gold-rays motif from TNFX's social banners (hero, partner cards, final band).
- Fonts (all embedded as woff2 data URIs, zero requests): **Montserrat 700–900** display
  (matches the heavy angular TNFX wordmark; also loaded by the live site), **Work Sans** body,
  **GE Dinar One Medium** for Arabic (from tnfx.co's own uploads).
- Market-first: broker KPI strip under the hero (0.0 pips* / 1:500† / $100 / 1,000+ / 24/6),
  gold XAUUSD terminal, price ticker with INDICATIVE label + pause, trend sparklines in the
  markets table. Mobile-first CSS (base = phone; ≥720px / ≥1024px enhance).
- v1 (dark, system fonts) and v2 (light Boing, mirroring the WP site) were both rejected by
  the user; v2's light palette/Boing files remain available in the scratchpad history if the
  direction ever flips back.

## What's in this folder

| File | Purpose |
|---|---|
| `index.html` | The complete homepage (EN). ~145 KB single file, self-contained. |
| `img/og-home.png` | 1200×630 Open Graph / social share card (generated from `og-card.html`). |
| `og-card.html` | Source for the OG card — re-render with headless Edge if copy changes. Not deployed. |
| `img/tnfx-logo.png`, `img/tnfx-mark.png` | Brand lockup + bull mark (referenced by JSON-LD/manifest). |
| `img/logo192.png`, `img/logo512.png` | PWA / apple-touch icons. |
| `favicon.ico` | Favicon (multi-size). |
| `robots.txt`, `sitemap.xml`, `site.webmanifest` | SEO/PWA support files. |

## How to deploy

The page expects to live at the **site root** (`https://tnfx.co/`). Upload the folder contents
(minus `og-card.html` and this file) to the web root, or serve via nginx:

```nginx
server {
    listen 443 ssl;
    server_name tnfx.co www.tnfx.co;
    root /var/www/tnfx-home;
    index index.html;
    location / { try_files $uri $uri/ /index.html; }
}
```

Keep 301s: `http→https`, `www→apex`, `/index.html→/`.

## ⚠️ Verify before/at launch

1. **X (Twitter) handle** — the current WP footer links `x.com/TNFX_official`, but the indexed
   live account is `x.com/TNFXofficial`. The new page uses `TNFXofficial`. Open both in a
   browser and correct the footer + JSON-LD `sameAs` if needed.
2. **Partner link** — the page links `https://partner1.tnfx.co/` (the new IB portal). The old WP
   site links `partner.tnfx.co` (legacy Azure SPA). Confirm which one marketing wants public.
3. **hreflang cluster** — the page declares `ar/ku/tr/zh-hans/es` alternates pointing at the
   existing WordPress language homepages (`tnfx.co/ar/` …). Those pages already point back to
   `tnfx.co/` as their `en` alternate, so the cluster stays valid — but if the WP language pages
   are ever removed, strip the corresponding `<link rel="alternate">` tags and sitemap entries.
4. **Payment methods shown**: ZainCash, Qi Card, Visa, Mastercard, Bank Transfer, Sticpay,
   Payeer, WebMoney, UPI, PayRetailers. Confirm with finance this is the list to advertise
   (the old page showed KoraPay/Ozow instead of ZainCash/Qi).
5. **Live prices** — the page streams LIVE reference prices over a keyless public WebSocket
   (Binance miniTicker: PAXGUSDT as gold reference, EURUSDT, BTCUSDT, ETHUSDT). Badges flip
   from INDICATIVE to "LIVE · REF" automatically; if the feed is unreachable the page falls
   back to labeled demo values. Footnote ‡ covers both states. Optional upgrade: replace the
   feed with TNFX's own MT5 bridge quotes (bridge.py) via a tiny `/quotes` endpoint for true
   tradable prices on GBP/JPY/US30/USOIL too.

## 🔴 Issues found on the CURRENT live WordPress site (report to whoever runs it)

Found during research on 2026-07-21 — these hurt SEO today and are fixed by this rebuild,
but the WP install itself needs attention:

1. **Casino-spam injection**: the live homepage HTML contains a hidden paragraph linking to
   `tnfx.co/Pokies-in-australian-online-casinos` ("Greetings Australian gambling fans…").
   This is a classic SEO spam compromise — the WordPress install should be audited
   (plugins, users, file integrity) even after the new homepage replaces it.
2. **JSON-LD Organization name is "Admin_M"** (the WP author leaked into the Organization
   node) — Google currently thinks the site's entity is named Admin_M.
3. `https://tnfx.co/en/` 301-redirects to the FSA licence page instead of the homepage.
4. Stray `<title>Document</title>` fragment embedded mid-page.
5. English nav "Video Tutorials" links to the Arabic URL.

## Next SEO steps (beyond the homepage)

- Arabic homepage mirror (`/ar/`) in this same design — highest-value follow-up
  (Iraqi query pattern is Arabic-first: "شركات التداول المرخصة في العراق").
- Dedicated landing pages: Islamic/swap-free account, gold trading, copy trading,
  ZainCash/Qi deposits, IB program (reuse the partner-seo generator pattern).
- Submit `sitemap.xml` in Search Console after launch; watch CTR on Iraq geo.

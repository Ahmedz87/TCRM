# -*- coding: utf-8 -*-
"""Generate the TNFX partner SEO sub-pages: 9 topics x 11 languages = 99 static HTML pages,
served by nginx under partner1.tnfx.co/partners/<slug> (EN) and /<lang>/partners/<slug>.
ARTICLE/BLOG layout: readable content column + sticky sidebar (portal CTAs, table of contents,
key facts, related). Self-contained HTML: SEO head + hreflang + JSON-LD + IP-geo lang switcher + RTL."""
import json, os, html
from flags import FLAGS, LANG_FLAG, COUNTRY_LANGS, COUNTRY_AR_FLAG

HERE = os.path.dirname(__file__)
OUT = r"C:\Broker-crm\frontend\public"
IMG = "/partners/img"
SITE = "https://partner1.tnfx.co"
APP_JOIN = SITE + "/?join=1"          # IB portal signup
APP_LOGIN = SITE + "/?login=1"        # IB portal login
CLIENT = "https://my1.tnfx.co/portal/"  # client / trading-account portal

fixed = json.load(open(HERE + "/i18n/en.json", encoding="utf-8"))
TIERS, PAYMENTS, CAREER, WEEKLY_N, LANGS = (fixed["TIERS"], fixed["PAYMENTS"],
                                            fixed["CAREER"], fixed["WEEKLY"], fixed["LANGS"])
META_KEYWORDS = fixed.get("META_KEYWORDS", {})
TOPIC_ORDER = list(fixed["TOPICS"].keys())
LANG_ORDER = list(LANGS.keys())

def esc(x): return html.escape(str(x), quote=True)

def load_lang(code):
    path = HERE + ("/i18n/_src_flat.json" if code == "en" else f"/i18n/{code}.json")
    return json.load(open(path, encoding="utf-8"))

# ---------- CSS ----------
CSS = r"""
:root{--bg:#13151C;--p1:#1B1E27;--p2:#20242F;--p3:#262B37;--line:rgba(255,255,255,.09);
--line2:rgba(255,255,255,.16);--ink:#F3F2EF;--ink2:#B4B8C2;--ink3:#818693;
--acc:#FF7A1A;--acc2:#FF9F45;--grad:linear-gradient(135deg,#ff5412,#ff9a3d);--good:#35C98A;
--sans:system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,"Noto Sans",sans-serif;
--serif:Georgia,"Times New Roman","Noto Serif",serif;}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);line-height:1.6;
-webkit-font-smoothing:antialiased;font-variant-numeric:tabular-nums;overflow-x:hidden}
.wrap{max-width:1200px;margin:0 auto;padding:0 22px}
a{color:inherit;text-decoration:none}
.num{font-variant-numeric:tabular-nums;direction:ltr;unicode-bidi:isolate}
.eyebrow{font-size:12px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--ink3);
display:inline-flex;align-items:center;gap:9px}
.eyebrow::before{content:"";width:18px;height:1px;background:var(--grad)}
.cta{background:var(--grad);color:#fff;border:none;font-weight:600;cursor:pointer;border-radius:10px;
display:inline-flex;align-items:center;justify-content:center;gap:7px;transition:transform .15s,filter .15s}
.cta:hover{transform:translateY(-1px);filter:brightness(1.08)}
.ghost{background:transparent;color:var(--ink);border:1px solid var(--line2);font-weight:600;cursor:pointer;
border-radius:10px;display:inline-flex;align-items:center;justify-content:center}
.ghost:hover{border-color:rgba(255,255,255,.32);background:rgba(255,255,255,.04)}
/* top bar */
.top{position:sticky;top:0;z-index:60;background:rgba(19,21,28,.86);backdrop-filter:blur(12px);
-webkit-backdrop-filter:blur(12px);border-bottom:1px solid var(--line)}
@supports not (backdrop-filter:blur(12px)){.top{background:rgba(19,21,28,.98)}}
.top .wrap{height:60px;display:flex;align-items:center;gap:13px}
.top img.logo{height:24px;flex-shrink:0}
.brandtag{font-size:11px;font-weight:700;letter-spacing:.17em;color:var(--ink3)}
.tnav{display:flex;gap:20px;margin-inline:auto}
.tnav a{font-size:13.5px;color:var(--ink2)}.tnav a:hover{color:var(--ink)}
.topr{margin-inline-start:auto;display:flex;gap:8px;align-items:center;flex-shrink:0}
.top .cta,.top .ghost{height:35px;padding:0 14px;font-size:13.5px;white-space:nowrap}
/* lang switch */
.lang{position:relative}
.langbtn{display:inline-flex;align-items:center;gap:7px;height:35px;padding:0 10px;border:1px solid var(--line2);
border-radius:9px;background:transparent;color:var(--ink);cursor:pointer;font-size:13px;font-family:var(--sans)}
.langbtn:hover{background:rgba(255,255,255,.05)}
.langmenu{position:absolute;top:43px;inset-inline-end:0;background:var(--p1);border:1px solid var(--line2);
border-radius:11px;padding:5px;min-width:170px;box-shadow:0 16px 40px rgba(0,0,0,.45);display:none;z-index:80}
.langmenu.open{display:block}
.langmenu a{display:flex;align-items:center;gap:9px;padding:8px 11px;border-radius:7px;font-size:13.5px;color:var(--ink2)}
.langmenu a:hover{background:var(--p2);color:var(--ink)}
.langmenu a.cur{color:var(--ink);font-weight:600}
.langmenu a.cur::after{content:"✓";margin-inline-start:auto;color:var(--acc)}
/* geo suggest */
.suggest{position:fixed;inset-block-end:16px;inset-inline:16px;max-width:420px;margin-inline:auto;
background:var(--p1);border:1px solid var(--line2);border-radius:13px;padding:13px 15px;display:none;
align-items:center;gap:12px;z-index:90;box-shadow:0 18px 50px rgba(0,0,0,.5)}
.suggest.show{display:flex}.suggest .t{font-size:13.5px;color:var(--ink);flex:1}
.suggest .cta{height:34px;padding:0 15px;font-size:13px}
.suggest .x{background:none;border:none;color:var(--ink3);cursor:pointer;font-size:13px;padding:6px}
/* article header */
.ahead{border-bottom:1px solid var(--line);background:
radial-gradient(900px 300px at 20% -40%,rgba(255,84,18,.09),transparent 60%)}
.ahead .wrap{padding:40px 22px 30px;max-width:1200px}
.ahead .cat{margin-bottom:16px}
.ahead h1{font-size:clamp(30px,4.6vw,50px);line-height:1.08;letter-spacing:-.022em;font-weight:800;
max-width:20ch;margin:0}
.ahead .dek{font-size:18px;color:var(--ink2);max-width:64ch;margin:16px 0 20px;line-height:1.6}
.byline{display:flex;align-items:center;gap:12px;flex-wrap:wrap;font-size:13px;color:var(--ink3)}
.byline .av{width:26px;height:26px;border-radius:7px;background:var(--grad);display:inline-flex;
align-items:center;justify-content:center;color:#fff;font-weight:800;font-size:12px}
.byline .dot{width:3px;height:3px;border-radius:50%;background:var(--ink3)}
.rate{display:inline-flex;align-items:baseline;gap:8px;margin-top:22px;padding:10px 16px;border:1px solid var(--line2);
border-radius:12px;background:var(--p1)}
.rate .up{font-size:12px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--ink3)}
.rate .v{font-size:40px;font-weight:800;letter-spacing:-.03em;background:var(--grad);-webkit-background-clip:text;
background-clip:text;-webkit-text-fill-color:transparent;direction:ltr}
@supports not (-webkit-background-clip:text){.rate .v{color:var(--acc2);-webkit-text-fill-color:currentColor}}
.rate .l{font-size:15px;font-weight:600;color:var(--ink2)}
/* layout */
.layout{display:grid;grid-template-columns:minmax(0,1fr) 320px;gap:52px;align-items:start;
padding-top:44px;padding-bottom:20px}
.article{min-width:0;max-width:720px}
.article section{padding-bottom:14px;margin-bottom:34px;border-bottom:1px solid var(--line)}
.article section:last-child{border-bottom:none}
.article h2{font-size:clamp(23px,2.8vw,30px);line-height:1.18;letter-spacing:-.02em;font-weight:800;
margin:0 0 16px;scroll-margin-top:78px}
.article h3{font-size:17px;font-weight:700;margin:0 0 4px}
.article p{font-size:17px;line-height:1.75;color:var(--ink2);margin:0 0 16px;max-width:68ch}
.article p strong,.article li strong{color:var(--ink)}
.article .kick{margin-bottom:12px}
/* tier table */
.ttable{width:100%;border-collapse:collapse;border:1px solid var(--line);border-radius:12px;overflow:hidden;margin:6px 0 10px}
.ttable th,.ttable td{padding:12px 14px;text-align:start;font-size:14.5px;border-bottom:1px solid var(--line)}
.ttable thead th{font-size:11.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--ink3);background:var(--p1);font-weight:700}
.ttable tbody tr:last-child td{border-bottom:none}
.ttable td.rate-c{font-weight:800;font-size:17px}
.ttable tr.top td{background:rgba(255,122,26,.06)}
.ttable tr.top td.rate-c{background:var(--grad);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.tnote{font-size:13px;color:var(--ink3);margin-top:2px}
/* challenge blocks */
.chgrid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin:6px 0 14px}
.chbox{background:var(--p1);border:1px solid var(--line);border-radius:13px;padding:16px 17px}
.chbox .h{display:flex;align-items:baseline;justify-content:space-between;gap:8px;margin-bottom:3px}
.chbox .h b{font-size:15.5px}.chbox .h .mx{font-size:13px;font-weight:800;color:var(--acc2)}
.chbox .cl{font-size:13px;color:var(--ink3);margin-bottom:12px;line-height:1.5}
.qr{display:flex;align-items:center;gap:10px;padding:8px 0;border-top:1px solid var(--line);font-size:13.5px}
.qr .qn{font-weight:600}.qr .qd{color:var(--ink3);font-size:12px}
.qr .qv{margin-inline-start:auto;font-weight:800;color:var(--good)}
.reward{background:linear-gradient(135deg,rgba(255,84,18,.13),rgba(255,154,61,.05));
border:1px solid rgba(255,122,26,.3);border-radius:11px;padding:13px 16px;font-size:15px;font-weight:600;color:var(--ink);margin:4px 0 6px}
.reward b{color:var(--acc2)}
figure{margin:16px 0 4px}
figure img{width:100%;border-radius:13px;border:1px solid var(--line2);box-shadow:0 22px 55px rgba(0,0,0,.4);display:block}
figcaption{font-size:12.5px;color:var(--ink3);margin-top:9px;text-align:center}
/* payments */
.pchips{display:flex;flex-wrap:wrap;gap:8px;margin:4px 0 6px}
.pchip{background:var(--p1);border:1px solid var(--line);border-radius:9px;padding:8px 13px;font-size:14px;font-weight:600;
display:inline-flex;align-items:center;gap:8px}
.pchip .d{width:7px;height:7px;border-radius:50%;background:var(--grad)}
.pchip.first{border-color:rgba(255,122,26,.45)}
/* trust inline */
.tinline{display:grid;grid-template-columns:1fr 1fr;gap:2px;background:var(--line);border:1px solid var(--line);
border-radius:12px;overflow:hidden;margin:8px 0 6px}
.tinline>div{background:var(--bg);padding:15px 16px}
.tinline .k{font-size:19px;font-weight:800}.tinline .v{font-size:12.5px;color:var(--ink3);margin-top:2px}
/* steps */
.steps{list-style:none;padding:0;margin:6px 0 0;counter-reset:s}
.steps li{position:relative;padding-inline-start:44px;margin-bottom:18px;counter-increment:s}
.steps li::before{content:counter(s,decimal-leading-zero);position:absolute;inset-inline-start:0;top:0;
font-size:14px;font-weight:800;color:var(--acc2);background:var(--p1);border:1px solid var(--line);
width:30px;height:30px;border-radius:8px;display:flex;align-items:center;justify-content:center}
.steps b{font-size:16px}.steps p{margin:3px 0 0;font-size:14.5px}
/* faq */
.faq details{border-top:1px solid var(--line);padding:15px 0}
.faq details:last-child{border-bottom:1px solid var(--line)}
.faq summary{font-size:16px;font-weight:700;cursor:pointer;list-style:none;display:flex;justify-content:space-between;gap:14px;align-items:center}
.faq summary::-webkit-details-marker{display:none}
.faq summary::after{content:"+";color:var(--acc);font-size:21px;font-weight:400}
.faq details[open] summary::after{content:"–"}
.faq details p{margin-top:11px;font-size:15px}
/* sidebar */
.side{position:sticky;top:78px;display:flex;flex-direction:column;gap:16px}
.scard{background:var(--p1);border:1px solid var(--line);border-radius:14px;padding:16px 16px}
.side-h{font-size:11.5px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--ink3);margin-bottom:11px}
.cta-card{background:linear-gradient(180deg,var(--p2),var(--p1));border:1px solid var(--line2)}
.cta-card .st{font-size:16px;font-weight:800;margin-bottom:13px}
.pcard{padding:12px;border:1px solid var(--line);border-radius:11px;background:var(--bg);margin-bottom:11px}
.pcard .pt{font-size:14px;font-weight:700}.pcard .ps{font-size:12px;color:var(--ink3);margin:1px 0 10px}
.pcard .btns{display:flex;gap:7px}
.pcard .cta{flex:1;height:38px;font-size:13.5px}
.pcard .ghost{height:38px;padding:0 13px;font-size:13px}
.toc a{display:block;font-size:13.5px;color:var(--ink2);padding:6px 0;border-inline-start:2px solid transparent;padding-inline-start:11px}
.toc a:hover{color:var(--ink);border-color:var(--acc)}
.facts .f{display:flex;align-items:center;gap:11px;padding:8px 0;border-top:1px solid var(--line)}
.facts .f:first-child{border-top:none}
.facts .fv{font-size:18px;font-weight:800;color:var(--ink);min-width:52px}
.facts .fl{font-size:12.5px;color:var(--ink3);line-height:1.35}
.rel a{display:block;font-size:13.5px;color:var(--ink2);padding:8px 0;border-top:1px solid var(--line)}
.rel a:first-child{border-top:none}.rel a:hover{color:var(--acc2)}
/* final cta */
.final{border-top:1px solid var(--line);background:radial-gradient(700px 260px at 50% 120%,rgba(255,84,18,.1),transparent)}
.final .wrap{padding:70px 22px;text-align:center}
.final h2{font-size:clamp(25px,3.4vw,36px);font-weight:800;letter-spacing:-.02em;max-width:22ch;margin:0 auto 12px}
.final p{color:var(--ink2);font-size:16px;max-width:56ch;margin:0 auto 26px}
.final .cta{height:52px;padding:0 34px;font-size:15.5px}
.final .assn{font-size:12.5px;color:var(--ink3);margin-top:15px}
/* footer */
footer{background:var(--bg);border-top:1px solid var(--line);padding:42px 0 54px}
.fnav{display:flex;gap:18px;flex-wrap:wrap;align-items:center}.fnav img{height:21px}
.fnav .fl{margin-inline-start:auto;display:flex;gap:18px;flex-wrap:wrap}.fnav a{color:var(--ink2);font-size:14px}
.disc{font-size:12.5px;color:var(--ink3);line-height:1.7;margin-top:20px;padding-top:18px;border-top:1px solid var(--line)}
.rights{font-size:12px;color:var(--ink3);margin-top:11px}
/* ── motion + live widgets (hidden pre-state gated on .js so no-JS still shows everything) ── */
.js .reveal{opacity:0;transform:translateY(14px)}
.js .reveal.in{opacity:1;transform:none;transition:opacity .6s cubic-bezier(.16,1,.3,1),transform .6s cubic-bezier(.16,1,.3,1)}
.ahead .hwrap{display:grid;grid-template-columns:1.05fr .95fr;gap:40px;align-items:center}
.pbar{height:10px;border-radius:99px;background:rgba(255,255,255,.08);overflow:hidden}
.pbar>i{display:block;height:100%;width:0;border-radius:99px;background:var(--grad);transition:width 1.3s cubic-bezier(.16,1,.3,1)}
.in .pbar>i{width:var(--w)}
.chart{width:100%;height:auto;display:block}
.chart .ln{fill:none;stroke:var(--good);stroke-width:2.4;stroke-linecap:round;stroke-linejoin:round;stroke-dasharray:1;stroke-dashoffset:1}
.in .chart .ln{animation:draw 1.6s .15s ease-out forwards}
@keyframes draw{to{stroke-dashoffset:0}}
.chart .ar{opacity:0}.in .chart .ar{animation:fadein 1s .55s ease forwards}
.chart .edot{opacity:0}.in .chart .edot{animation:fadein .5s 1.55s ease forwards}
@keyframes fadein{to{opacity:1}}
/* hero earnings card */
.efig{background:linear-gradient(160deg,#1c2432,#15191f);border:1px solid var(--line2);border-radius:16px;
padding:18px 20px;box-shadow:0 30px 70px rgba(0,0,0,.42)}
.efig .et{display:flex;align-items:center;gap:8px;font-size:11.5px;font-weight:700;letter-spacing:.09em;text-transform:uppercase;color:var(--ink3)}
.efig .live{margin-inline-start:auto;display:inline-flex;align-items:center;gap:6px;color:var(--good);font-size:11px;font-weight:700}
.efig .live::before{content:"";width:7px;height:7px;border-radius:50%;background:var(--good);animation:pulse 1.8s infinite}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(53,201,138,.55)}70%{box-shadow:0 0 0 8px rgba(53,201,138,0)}100%{box-shadow:0 0 0 0 rgba(53,201,138,0)}}
.efig .big{font-size:clamp(34px,5vw,50px);font-weight:800;letter-spacing:-.03em;color:#fff;margin:9px 0 2px;direction:ltr}
.efig .chg{font-size:13px;color:var(--good);font-weight:600;margin-bottom:8px}
.efig .krow{display:flex;gap:8px;margin-top:14px}
.efig .kc{flex:1;background:rgba(255,255,255,.04);border:1px solid var(--line);border-radius:10px;padding:9px 11px}
.efig .kc .kn{font-size:18px;font-weight:800}
.efig .kc.g .kn{color:var(--good)}.efig .kc.b .kn{color:#5b9bff}.efig .kc.o .kn{color:var(--acc2)}
.efig .kc .kl{font-size:10px;color:var(--ink3);margin-top:1px}
.efig .prog{margin-top:15px}
.efig .prog .pl{display:flex;justify-content:space-between;font-size:12px;color:var(--ink2);margin-bottom:6px}
.efig .prog .pl b{color:var(--acc2)}
/* challenge widget (light card, green rewards) */
.cwidget{background:#fff;color:#12151d;border-radius:16px;box-shadow:0 30px 70px rgba(0,0,0,.4);overflow:hidden;margin:10px 0 4px}
.cw-head{background:linear-gradient(120deg,#181b2c,#241d3a);color:#fff;padding:15px 20px;display:flex;align-items:center;gap:10px}
.cw-head .ca{font-size:17px;font-weight:800}
.cw-head .claim{margin-inline-start:auto;background:#d9f7e6;color:#127a4d;font-size:12px;font-weight:800;border-radius:99px;padding:5px 12px}
.cw-head .claim.pending{background:rgba(255,255,255,.13);color:#aeb4c0}
.cw-body{padding:18px 20px}
/* completed mission with 3D claim button */
.cw-done{display:flex;align-items:center;gap:12px;background:#eafaf1;border:1px solid #c1ead4;border-radius:12px;padding:11px 13px;margin-bottom:16px}
.cw-done .dcheck{width:30px;height:30px;border-radius:50%;background:#1f9d67;color:#fff;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:16px;flex-shrink:0}
.cw-done .dinfo{flex:1;min-width:0}
.cw-done .dn{font-size:15px;font-weight:800;color:#12151d;display:flex;align-items:center;gap:8px}
.cw-done .dbadge{font-size:10.5px;font-weight:800;color:#127a4d;background:#d9f7e6;border-radius:99px;padding:2px 8px}
.cw-done .dsub{font-size:12px;color:#5a6472;margin-top:1px}
.claim3d{border:none;cursor:pointer;font-family:inherit;font-weight:800;font-size:13.5px;color:#fff;flex-shrink:0;
background:linear-gradient(180deg,#42d98f,#1f9d67);border-radius:11px;padding:10px 15px;white-space:nowrap;
box-shadow:0 4px 0 #14713f,0 8px 16px rgba(20,113,63,.42);text-shadow:0 1px 1px rgba(0,0,0,.18);
transition:transform .09s ease,box-shadow .09s ease,filter .12s}
.claim3d:hover{filter:brightness(1.07)}
.claim3d:active{transform:translateY(3px);box-shadow:0 1px 0 #14713f,0 3px 8px rgba(20,113,63,.42)}
.cw-mrow{display:flex;align-items:center;gap:10px;margin-bottom:4px}
.cw-mrow .mn{font-size:18px;font-weight:800}
.cw-mrow .mtag{font-size:11px;font-weight:800;color:#127a4d;background:#d9f7e6;border-radius:99px;padding:3px 10px}
.cw-mrow .mr{margin-inline-start:auto;font-size:22px;font-weight:800;color:#127a4d}
.cw-sub{font-size:12.5px;color:#7b8496;margin-bottom:12px}
.cw-bar{height:15px;border-radius:99px;background:#eef1f6;overflow:hidden;position:relative}
.cw-bar>i{display:block;height:100%;width:0;border-radius:99px;background:linear-gradient(90deg,#2f9d68,#35C98A)}
.in .cw-bar>i{width:82%;transition:width 1.5s cubic-bezier(.16,1,.3,1)}
.cw-bar .pct{position:absolute;inset-inline-end:10px;top:0;line-height:15px;font-size:11px;font-weight:800;color:#12151d}
.cw-stat{display:flex;gap:20px;margin-top:11px;font-size:13px;color:#5a6472;flex-wrap:wrap}
.cw-stat b{color:#12151d}.cw-stat .go{margin-inline-start:auto;color:#127a4d;font-weight:800}
.cw-quests{border-top:1px solid #eef1f6;padding-top:13px;margin-top:14px;display:grid;grid-template-columns:1fr 1fr;gap:9px 20px}
.cw-q{display:flex;align-items:center;gap:9px;font-size:13px}
.cw-q .qi{width:9px;height:9px;border-radius:3px;background:#35C98A;flex-shrink:0}
.cw-q .qn{font-weight:600}.cw-q .qv{margin-inline-start:auto;font-weight:800;color:#127a4d}
/* mini dashboard */
.mdash{background:linear-gradient(160deg,#1b2230,#15181f);border:1px solid var(--line2);border-radius:16px;padding:18px 20px;box-shadow:0 26px 60px rgba(0,0,0,.4);margin:10px 0 4px}
.md-kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:14px}
.md-k{background:rgba(255,255,255,.04);border:1px solid var(--line);border-radius:11px;padding:12px 13px}
.md-k .n{font-size:21px;font-weight:800}
.md-k.g .n{color:var(--good)}.md-k.b .n{color:#5b9bff}.md-k.o .n{color:var(--acc2)}.md-k.p .n{color:#a98bff}
.md-k .l{font-size:10.5px;color:var(--ink3);margin-top:2px}
.md-funnel{margin-top:14px;display:flex;flex-direction:column;gap:11px}
.md-f{display:grid;grid-template-columns:1fr auto;gap:5px 8px;align-items:center}
.md-f .fl{font-size:12.5px;color:var(--ink2)}.md-f .fv{font-size:13px;font-weight:800}
.md-f .fb{grid-column:1/-1;height:8px;border-radius:99px;background:rgba(255,255,255,.07);overflow:hidden}
.md-f .fb>i{display:block;height:100%;width:0;border-radius:99px}
.in .md-f .fb>i{width:var(--w);transition:width 1.2s cubic-bezier(.16,1,.3,1)}
@media(max-width:900px){.ahead .hwrap{grid-template-columns:1fr;gap:28px}}
@media(max-width:600px){.cw-quests{grid-template-columns:1fr}.md-kpis{grid-template-columns:1fr 1fr}}
@media(max-width:960px){.layout{grid-template-columns:1fr;gap:12px}
.side{position:static;flex-direction:column}
.tnav{display:none}}
@media(max-width:600px){.chgrid{grid-template-columns:1fr}.tinline{grid-template-columns:1fr}
.top .brandtag{display:none}.ahead h1{font-size:30px}}
@media(max-width:460px){.top .ghost{display:none}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}*{transition:none!important;animation:none!important}
.js .reveal{opacity:1;transform:none}
.pbar>i,.md-f .fb>i{width:var(--w)!important}.cw-bar>i{width:82%!important}
.chart .ln{stroke-dashoffset:0}.chart .ar,.chart .edot{opacity:1}}
"""

def flag_svg(iso): return FLAGS.get(iso, FLAGS["GB"])

def alt_url(code, slug):
    return (f"{SITE}/partners/{slug}/" if code == "en" else f"{SITE}/{code}/partners/{slug}/")


# ---------- live widget builders (animated, colourful, NO screenshots) ----------
def area_chart_svg(points, w=560, h=150, cid="c"):
    """Green area+line chart. pathLength=1 so the CSS draw animation is length-independent."""
    n = len(points); pad = 10
    xs = [i * (w / (n - 1)) for i in range(n)]
    ys = [h - pad - (h - 2 * pad) * p for p in points]
    line = "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in zip(xs, ys))
    area = line + f" L {w:.1f} {h:.1f} L 0 {h:.1f} Z"
    ex, ey = xs[-1], ys[-1]
    return (f'<svg class="chart" viewBox="0 0 {w} {h}" preserveAspectRatio="none" aria-hidden="true">'
            f'<defs><linearGradient id="g{cid}" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0" stop-color="#35C98A" stop-opacity=".35"/>'
            f'<stop offset="1" stop-color="#35C98A" stop-opacity="0"/></linearGradient></defs>'
            f'<path class="ar" d="{area}" fill="url(#g{cid})"/>'
            f'<path class="ln" d="{line}" pathLength="1"/>'
            f'<circle class="edot" cx="{ex:.1f}" cy="{ey:.1f}" r="4" fill="#35C98A"/></svg>')

CURVE = [.28, .40, .33, .52, .45, .64, .55, .74, .62, .84, .70, .78, .88, .8, .96]

def hero_figure(s, ui):
    chart = area_chart_svg(CURVE, cid="h")
    return f'''<div class="efig reveal">
<div class="et"><span>{esc(ui["earnings"])}</span><span class="live">{esc(ui["live"])}</span></div>
<div class="big"><span data-count="12480" data-prefix="$">$0</span></div>
<div class="chg">▲ 12% · {esc(ui["this_mo"])}</div>
{chart}
<div class="krow">
<div class="kc g"><div class="kn"><span data-count="48">0</span></div><div class="kl">{esc(ui["clients"])}</div></div>
<div class="kc b"><div class="kn"><span data-count="312">0</span></div><div class="kl">{esc(ui["lots"])}</div></div>
<div class="kc o"><div class="kn"><span data-count="24">0</span></div><div class="kl">{esc(ui["funded"])}</div></div>
</div>
<div class="prog"><div class="pl"><span>Diamond → Legendary</span><b><span class="num">98%</span></b></div>
<div class="pbar"><i style="--w:98%"></i></div></div></div>'''

def challenge_widget(s, ui, L):
    quests = "".join(
        f'<div class="cw-q"><span class="qi"></span><span class="qn">{esc(w["name"])}</span>'
        f'<span class="qv"><span class="num">+${w["reward"]}</span></span></div>' for w in WEEKLY_N)
    return f'''<div class="cwidget reveal">
<div class="cw-head"><span>⚔️</span><span class="ca">{esc(s["challenges_kicker"])}</span>
<span class="claim pending">⏳ <span class="num">$600</span></span></div>
<div class="cw-body">
<div class="cw-done"><div class="dcheck">✓</div>
<div class="dinfo"><div class="dn">Momentum <span class="dbadge"><span class="num">100%</span></span></div>
<div class="dsub">Diamond → Legendary · <span class="num">+$250</span></div></div>
<button type="button" class="claim3d">{esc(ui["claim"])} · <span class="num">$250</span></button></div>
<div class="cw-mrow"><span class="mn">Rising Star</span><span class="mtag">{esc(ui["active_mission"])}</span>
<span class="mr"><span class="num">+$600</span></span></div>
<div class="cw-sub"><span class="num">25</span> {esc(ui["funded"])} · <span class="num">500</span> {esc(ui["lots"])} · Diamond → Legendary</div>
<div class="cw-bar"><i></i><span class="pct"><span class="num">82%</span></span></div>
<div class="cw-stat"><span><b><span class="num">20</span></b> / <span class="num">25</span> {esc(ui["funded"])}</span>
<span><b><span class="num">410</span></b> / <span class="num">500</span> {esc(ui["lots"])}</span>
<span class="go">✨ +$600</span></div>
<div class="cw-quests">{quests}</div></div></div>'''

def mini_dashboard(s, ui):
    chart = area_chart_svg(CURVE, w=560, h=130, cid="d")
    funnel = [(ui["clients"], "129", "100%", "#5b9bff"),
              (ui["funded"], "24", "58%", "#35C98A"),
              (ui["lots"], "312", "76%", "#FF9F45")]
    frows = "".join(
        f'<div class="md-f"><span class="fl">{esc(lbl)}</span><span class="fv"><span class="num">{esc(v)}</span></span>'
        f'<span class="fb"><i style="--w:{w};background:{col}"></i></span></div>'
        for lbl, v, w, col in funnel)
    return f'''<div class="mdash reveal">
<div class="md-kpis">
<div class="md-k g"><div class="n"><span data-count="12480" data-prefix="$">$0</span></div><div class="l">{esc(ui["earnings"])}</div></div>
<div class="md-k b"><div class="n"><span data-count="48">0</span></div><div class="l">{esc(ui["clients"])}</div></div>
<div class="md-k o"><div class="n"><span data-count="24">0</span></div><div class="l">{esc(ui["funded"])}</div></div>
<div class="md-k p"><div class="n"><span data-count="312">0</span></div><div class="l">{esc(ui["lots"])}</div></div>
</div>
{chart}
<div class="md-funnel">{frows}</div></div>'''


def build_page(code, slug):
    L = load_lang(code); s = L["s"]; ui = L["ui"]; t = L["topics"][slug]
    Ldir = LANGS[code]["dir"]
    canonical = alt_url(code, slug)

    # ---- head ----
    alts = "".join(f'<link rel="alternate" hreflang="{c}" href="{alt_url(c, slug)}">' for c in LANG_ORDER)
    alts += f'<link rel="alternate" hreflang="x-default" href="{alt_url("en", slug)}">'
    faq_ld = {"@context": "https://schema.org", "@type": "FAQPage",
              "mainEntity": [{"@type": "Question", "name": q["q"],
                              "acceptedAnswer": {"@type": "Answer", "text": q["a"]}} for q in L["faq"]]}
    art_ld = {"@context": "https://schema.org", "@type": "Article", "headline": t["h1"],
              "description": t["meta"], "inLanguage": code, "author": {"@type": "Organization", "name": "TNFX"},
              "publisher": {"@type": "Organization", "name": "TNFX", "logo": {"@type": "ImageObject", "url": f"{SITE}{IMG}/tnfx-logo.png"}},
              "image": f"{SITE}{IMG}/tnfx-logo.png", "mainEntityOfPage": canonical}
    crumb_ld = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": ui["partners"], "item": SITE + "/"},
        {"@type": "ListItem", "position": 2, "name": t["h1"], "item": canonical}]}
    head = f'''<!doctype html><html lang="{code}" dir="{Ldir}"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<script>document.documentElement.className+=' js'</script>
<title>{esc(t["title"])}</title>
<meta name="description" content="{esc(t["meta"])}">
{f'<meta name="keywords" content="{esc(META_KEYWORDS[slug])}">' if META_KEYWORDS.get(slug) else ''}
<link rel="canonical" href="{canonical}">{alts}
<meta property="og:type" content="article"><meta property="og:title" content="{esc(t["title"])}">
<meta property="og:description" content="{esc(t["meta"])}"><meta property="og:url" content="{canonical}">
<meta property="og:image" content="{SITE}{IMG}/tnfx-logo.png"><meta property="og:locale" content="{code}">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="{IMG}/tnfx-mark.png">
<script type="application/ld+json">{json.dumps(faq_ld, ensure_ascii=False)}</script>
<script type="application/ld+json">{json.dumps(art_ld, ensure_ascii=False)}</script>
<script type="application/ld+json">{json.dumps(crumb_ld, ensure_ascii=False)}</script>
<style>{CSS}</style></head><body>'''

    # ---- top bar ----
    nav = "".join(f'<a href="#{h}">{esc(ui[k])}</a>' for k, h in
                  [("nav_commission", "commission"), ("nav_challenges", "challenges"),
                   ("nav_payments", "payments"), ("nav_about", "about")])
    top = f'''<header class="top"><div class="wrap">
<a href="{SITE}/"><img class="logo" src="{IMG}/tnfx-logo.png" alt="TNFX"></a>
<span class="brandtag">{esc(ui["partners"]).upper()}</span>
<nav class="tnav">{nav}</nav>
<div class="topr">
<div class="lang"><button class="langbtn" id="langbtn" aria-haspopup="true" aria-expanded="false">
<span id="langflag">{flag_svg(LANG_FLAG[code])}</span><span>{esc(LANGS[code]["native"])}</span>
<svg width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M2 4l4 4 4-4"/></svg></button>
<div class="langmenu" id="langmenu"></div></div>
<a class="ghost" href="{APP_LOGIN}">{esc(ui["login"])}</a>
<a class="cta" href="{APP_JOIN}">{esc(ui["become_partner"])}</a>
</div></div></header>'''

    # ---- article header (text-first, no giant hero image) ----
    cat = f'{esc(t["h1"])[:1]}'  # unused
    ahead = f'''<div class="ahead"><div class="wrap"><div class="hwrap"><div class="htext">
<div class="cat eyebrow">TNFX {esc(ui["partners"])}</div>
<h1>{esc(t["h1"])}</h1>
<p class="dek">{esc(t["subhead"])}</p>
<div class="byline"><span class="av">T</span><span>TNFX {esc(ui["partners"])}</span>
<span class="dot"></span><span><span class="num">6</span> {esc(ui.get("read_time","min read"))}</span>
<span class="dot"></span><span>FSA · MT4 &amp; MT5</span></div>
<div class="rate"><span class="up">{esc(ui["up_to"])}</span><span class="v">$10</span><span class="l">{esc(s["commission_rate_word"])}</span></div>
</div>{hero_figure(s, ui)}</div></div></div>'''

    # ---- article sections ----
    # commission tier table
    trows = "".join(
        f'<tr class="{"top" if tr["rate"]==10 else ""}"><td>{esc(tr["name"])}</td>'
        f'<td class="rate-c"><span class="num">${tr["rate"]}</span></td>'
        f'<td>{esc(s["commission_rate_word"])}</td></tr>' for tr in TIERS)
    tier_table = f'<table class="ttable"><tbody>{trows}</tbody></table>'

    weekly_rows = "".join(
        f'<div class="qr"><div><div class="qn">{esc(w["name"])}</div><div class="qd">{esc(wt["desc"])}</div></div>'
        f'<div class="qv"><span class="num">+${w["reward"]}</span></div></div>'
        for w, wt in zip(WEEKLY_N, L["weekly"]))
    career_rows = "".join(
        f'<div class="qr"><div class="qn">{esc(c["name"])}</div>'
        f'<div class="qv"><span class="num">+${c["reward"]:,}</span></div></div>' for c in CAREER)
    pays = "".join(f'<span class="pchip{" first" if i==0 else ""}"><span class="d"></span>{esc(p)}</span>'
                   for i, p in enumerate(PAYMENTS))
    trust = "".join(f'<div><div class="k"><span class="num">{esc(x["k"])}</span></div><div class="v">{esc(x["v"])}</div></div>'
                    for x in L["about_trust"])
    steps = "".join(f'<li><b>{esc(st["t"])}</b><p>{esc(st["d"])}</p></li>' for st in L["how_steps"])
    faqs = "".join(f'<details><summary>{esc(q["q"])}</summary><p>{esc(q["a"])}</p></details>' for q in L["faq"])

    article = f'''<main class="article">
<section id="overview"><h2>{esc(t["lead_h2"])}</h2><p>{esc(t["lead_p"])}</p></section>
<section id="commission"><div class="eyebrow kick">{esc(s["commission_kicker"])}</div>
<h2>{esc(s["commission_h2"])}</h2><p>{esc(s["commission_lead"])}</p>
{tier_table}<div class="tnote">{esc(s["commission_tiers_note"])}</div></section>
<section id="challenges"><div class="eyebrow kick">{esc(s["challenges_kicker"])}</div>
<h2>{esc(s["challenges_h2"])}</h2><p>{esc(s["challenges_lead"])}</p>
<div class="chgrid">
<div class="chbox"><div class="h"><b>{esc(s["weekly_h3"])}</b></div><div class="cl">{esc(s["weekly_lead"])}</div>{weekly_rows}</div>
<div class="chbox"><div class="h"><b>{esc(s["career_h3"])}</b></div><div class="cl">{esc(s["career_lead"])}</div>{career_rows}</div>
</div>
<div class="reward">{esc(s["weekly_reward_line"])}</div>
{challenge_widget(s, ui, L)}</section>
<section id="payments"><div class="eyebrow kick">{esc(s["payments_kicker"])}</div>
<h2>{esc(s["payments_h2"])}</h2><p>{esc(s["payments_lead"])}</p><div class="pchips">{pays}</div></section>
<section id="about"><div class="eyebrow kick">{esc(s["about_kicker"])}</div>
<h2>{esc(s["about_h2"])}</h2><p>{esc(s["about_para1"])}</p><p>{esc(s["about_para2"])}</p>
<div class="tinline">{trust}</div></section>
<section id="dashboard"><div class="eyebrow kick">{esc(s["dash_kicker"])}</div>
<h2>{esc(s["dash_h2"])}</h2>
{mini_dashboard(s, ui)}
<p>{esc(s["dash_lead"])}</p></section>
<section id="how"><div class="eyebrow kick">{esc(s["how_kicker"])}</div>
<h2>{esc(s["how_h2"])}</h2><ol class="steps">{steps}</ol></section>
<section id="faq" class="faq"><h2>{esc(L["faq"][0]["q"])}</h2>{faqs}</section>
</main>'''

    # ---- sidebar ----
    toc_items = [("overview", t["lead_h2"] if len(t["lead_h2"]) < 30 else s["commission_kicker"]),
                 ("commission", ui["nav_commission"]), ("challenges", ui["nav_challenges"]),
                 ("payments", ui["nav_payments"]), ("about", ui["nav_about"]), ("faq", "FAQ")]
    toc = "".join(f'<a href="#{i}">{esc(lbl)}</a>' for i, lbl in toc_items)
    facts = [("$10", s["commission_rate_word"]),
             ("$400", ui["nav_challenges"]),
             ("FSA", L["about_trust"][0]["v"]),
             (str(len(PAYMENTS)), ui["nav_payments"])]
    facts_html = "".join(
        f'<div class="f"><div class="fv"><span class="num">{esc(v)}</span></div><div class="fl">{esc(lbl)}</div></div>'
        for v, lbl in facts)
    rel = "".join(f'<a href="{alt_url(code, o)}">{esc(L["topics"][o]["h1"])}</a>'
                  for o in TOPIC_ORDER if o != slug)
    aside = f'''<aside class="side">
<div class="scard cta-card"><div class="st">{esc(ui["start_earning"])}</div>
<div class="pcard"><div class="pt">{esc(ui["ib_partner"])}</div><div class="ps">{esc(ui["ib_sub"])}</div>
<div class="btns"><a class="cta" href="{APP_JOIN}">{esc(ui["sign_up"])}</a><a class="ghost" href="{APP_LOGIN}">{esc(ui["login"])}</a></div></div>
<div class="pcard"><div class="pt">{esc(ui["client_area"])}</div><div class="ps">{esc(ui["client_sub"])}</div>
<div class="btns"><a class="cta" href="{CLIENT}">{esc(ui["open_account"])}</a><a class="ghost" href="{CLIENT}">{esc(ui["login"])}</a></div></div>
</div>
<div class="scard toc"><div class="side-h">{esc(ui["on_this_page"])}</div>{toc}</div>
<div class="scard facts"><div class="side-h">{esc(ui["key_facts"])}</div>{facts_html}</div>
<div class="scard rel"><div class="side-h">{esc(ui["other_pages"])}</div>{rel}</div>
</aside>'''

    layout = f'<div class="wrap layout">{article}{aside}</div>'

    final = f'''<section class="final"><div class="wrap">
<h2>{esc(s["finalcta_h2"])}</h2><p>{esc(s["finalcta_lead"])}</p>
<a class="cta" href="{APP_JOIN}">{esc(s["finalcta_btn"])}</a>
<div class="assn">{esc(s["finalcta_assurance"])}</div></div></section>'''

    footer = f'''<footer><div class="wrap"><div class="fnav">
<img src="{IMG}/tnfx-logo.png" alt="TNFX">
<div class="fl"><a href="{APP_LOGIN}">{esc(s["footer_login"])}</a><a href="{SITE}/">{esc(s["footer_home"])}</a></div></div>
<div class="disc">{esc(s["footer_disclaimer"])}</div>
<div class="rights">{esc(s["footer_rights"])}</div></div></footer>'''

    # ---- geo + lang JS ----
    langmap = {c: {"native": LANGS[c]["native"], "flag": LANG_FLAG[c], "url": alt_url(c, slug)} for c in LANG_ORDER}
    js = f'''<script>
(function(){{
var CUR="{code}";
var LANGS={json.dumps(langmap, ensure_ascii=False)};
var FLAGS={json.dumps({k: FLAGS[k] for k in FLAGS}, ensure_ascii=False)};
var COUNTRY_LANGS={json.dumps(COUNTRY_LANGS)};
var AR_FLAG={json.dumps(COUNTRY_AR_FLAG)};
var UI={json.dumps({k: ui[k] for k in ["suggest_prefix","suggest_yes","suggest_no"]}, ensure_ascii=False)};
var menu=document.getElementById("langmenu"), btn=document.getElementById("langbtn");
function draw(list, arFlag){{
  menu.innerHTML=list.map(function(c){{var L=LANGS[c];if(!L)return "";
    var fl=(c==="ar"&&arFlag&&FLAGS[arFlag])?FLAGS[arFlag]:FLAGS[L.flag];
    return '<a href="'+L.url+'" class="'+(c===CUR?"cur":"")+'">'+fl+'<span>'+L.native+'</span></a>';}}).join("");
}}
draw(Object.keys(LANGS), null);
btn.onclick=function(e){{e.stopPropagation();var o=menu.classList.toggle("open");btn.setAttribute("aria-expanded",o);}};
document.addEventListener("click",function(){{menu.classList.remove("open");}});
fetch("/cdn-cgi/trace").then(function(r){{return r.text();}}).then(function(txt){{
  var m=/loc=([A-Z]{{2}})/.exec(txt);if(!m)return;var cc=m[1];
  var offer=COUNTRY_LANGS[cc];if(!offer)return;var arFlag=AR_FLAG[cc]||null;
  draw(offer.filter(function(c){{return LANGS[c];}}), arFlag);
  try{{if(localStorage.getItem("tnfx_lang_dismiss")==="1")return;var pref=offer[0];
    if(pref&&pref!==CUR&&LANGS[pref]){{var b=document.createElement("div");b.className="suggest";
      var fl=(pref==="ar"&&arFlag&&FLAGS[arFlag])?FLAGS[arFlag]:FLAGS[LANGS[pref].flag];
      b.innerHTML='<span class="t">'+fl+' &nbsp;'+UI.suggest_prefix+' '+LANGS[pref].native+'?</span>'+
        '<a class="cta" href="'+LANGS[pref].url+'">'+UI.suggest_yes+'</a><button class="x">'+UI.suggest_no+'</button>';
      document.body.appendChild(b);requestAnimationFrame(function(){{b.classList.add("show");}});
      b.querySelector(".x").onclick=function(){{b.classList.remove("show");try{{localStorage.setItem("tnfx_lang_dismiss","1");}}catch(e){{}}}};
    }}}}catch(e){{}}
}}).catch(function(){{}});
}})();
(function(){{
var reduce=window.matchMedia&&window.matchMedia("(prefers-reduced-motion: reduce)").matches;
function fmt(n){{return n.toLocaleString("en-US");}}
function countUp(el){{
  var to=parseFloat(el.getAttribute("data-count"))||0,pre=el.getAttribute("data-prefix")||"",suf=el.getAttribute("data-suffix")||"";
  if(reduce){{el.textContent=pre+fmt(to)+suf;return;}}
  var t0=null,dur=1100;
  function step(t){{if(!t0)t0=t;var p=Math.min(1,(t-t0)/dur),e=1-Math.pow(1-p,3);
    el.textContent=pre+fmt(Math.round(to*e))+suf;if(p<1)requestAnimationFrame(step);}}
  requestAnimationFrame(step);
}}
var io=new IntersectionObserver(function(es){{es.forEach(function(e){{if(e.isIntersecting){{
  e.target.classList.add("in");
  e.target.querySelectorAll("[data-count]").forEach(countUp);
  io.unobserve(e.target);}}}});}},{{threshold:.2}});
document.querySelectorAll(".reveal").forEach(function(el){{io.observe(el);}});
}})();
</script>'''

    return head + top + ahead + layout + final + footer + js + "</body></html>"


def write_page(code, slug):
    htmlp = build_page(code, slug)
    sub = f"partners/{slug}" if code == "en" else f"{code}/partners/{slug}"
    d = os.path.join(OUT, sub); os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "index.html"), "w", encoding="utf-8") as f:
        f.write(htmlp)
    return "/" + sub + "/"


def build_all(langs=None):
    return [write_page(c, slug) for c in (langs or LANG_ORDER) for slug in TOPIC_ORDER]


def write_sitemap(langs):
    rows = []
    for slug in TOPIC_ORDER:
        alt_links = "".join(f'<xhtml:link rel="alternate" hreflang="{c}" href="{alt_url(c, slug)}"/>' for c in langs)
        alt_links += f'<xhtml:link rel="alternate" hreflang="x-default" href="{alt_url("en", slug)}"/>'
        for c in langs:
            rows.append(f'<url><loc>{alt_url(c, slug)}</loc>{alt_links}<changefreq>weekly</changefreq><priority>0.8</priority></url>')
    sm = ('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
          'xmlns:xhtml="http://www.w3.org/1999/xhtml">\n' + "\n".join(rows) + "\n</urlset>")
    with open(os.path.join(OUT, "partners-sitemap.xml"), "w", encoding="utf-8") as f:
        f.write(sm)


if __name__ == "__main__":
    import sys
    langs = sys.argv[1:] or LANG_ORDER
    urls = build_all(langs)
    write_sitemap([c for c in LANG_ORDER if c in langs])
    print(f"generated {len(urls)} pages for langs={langs}")

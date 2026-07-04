"""make_all_in_one.py — ONE image: all commission profiles side-by-side (rules x profiles matrix)."""
import os
import psycopg2
from PIL import Image, ImageDraw, ImageFont
import ib_commission as IC

OUT = r"C:\Broker-crm\IB commission setting\ALL_PROFILES.png"

BG, HEADER_BG = (24, 26, 32), (38, 41, 50)
TXT, HEAD_TXT, MUTED = (225, 228, 235), (255, 255, 255), (150, 158, 170)
YELLOW, YELLOW_TXT = (60, 54, 20), (240, 210, 90)
GREEN, ORANGE, DIFF = (0, 229, 160), (255, 170, 0), (90, 170, 255)
GRID = (52, 56, 66)
PAD, ROWH = 16, 32

def font(sz, bold=False):
    return ImageFont.truetype(r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf", sz)
F, FB, FT, FS = font(13), font(13, True), font(20, True), font(11)

def fit(d, t, f, maxw):
    if d.textlength(t, font=f) <= maxw: return t
    while t and d.textlength(t + "…", font=f) > maxw: t = t[:-1]
    return t + "…"

def main():
    cn = psycopg2.connect(IC.PG_DSN); cur = cn.cursor()
    cur.execute("SELECT id, name, ib_level FROM commission_profiles")
    profs = []
    for pid, name, lvl in cur.fetchall():
        cur.execute("SELECT priority, name, symbols, distribution, value FROM commission_rules WHERE profile_id=%s ORDER BY priority", (pid,))
        rules = cur.fetchall()
        vals = {r[0]: r[4] for r in rules}
        markup = vals.get(20, 0) / 10.0
        profs.append(dict(name=name, level=lvl, markup=markup, vals=vals, rules=rules))
    cn.close()
    profs.sort(key=lambda p: p["markup"])              # columns by markup ascending
    base = next(p for p in profs if p["markup"] == 0.5)
    rule_rows = [(r[0], r[1], r[2], r[3]) for r in base["rules"]]   # priority,name,symbols,dist (identical across)

    LEFT = [("Pri", 45), ("Name", 150), ("Symbol pattern", 430), ("Dist", 80)]
    VW = 62                                             # value column width
    width = PAD * 2 + sum(w for _, w in LEFT) + VW * len(profs)
    height = 16 + 28 + 40 + ROWH * (len(rule_rows) + 1) + 30
    img = Image.new("RGB", (width, height), BG); d = ImageDraw.Draw(img)

    d.text((PAD, 12), "IB Commission Profiles — all levels & tiers", font=FT, fill=HEAD_TXT)
    d.text((PAD, 38), "value = pips/lot (USD-per-lot for Zero); only the FX+XAUUSD rules (15/17/18/20) change between profiles", font=FS, fill=MUTED)
    y0 = 64
    # header
    d.rectangle([PAD, y0, width - PAD, y0 + 40], fill=HEADER_BG)
    x = PAD
    for lbl, w in LEFT:
        d.text((x + 6, y0 + 13), lbl, font=FB, fill=HEAD_TXT); x += w
    for p in profs:
        lbl = f"IB{p['level']}" if p["level"] else "tier"
        d.text((x + 6, y0 + 5), lbl, font=FB, fill=HEAD_TXT)
        d.text((x + 6, y0 + 21), f"{p['markup']:g}p", font=FS, fill=GREEN)
        x += VW
    y = y0 + 40
    # rows
    for i, (pri, name, syms, dist) in enumerate(rule_rows):
        is15 = pri == 15
        d.rectangle([PAD, y, width - PAD, y + ROWH], fill=(YELLOW if is15 else ((30, 33, 40) if i % 2 else BG)))
        x = PAD
        cells = [str(pri), name, syms, ("Pips" if dist == "pips" else "USD/lot")]
        for (lbl, w), val in zip(LEFT, cells):
            col = YELLOW_TXT if is15 else (MUTED if lbl == "Symbol pattern" else TXT)
            d.text((x + 6, y + 8), fit(d, val, F, w - 10), font=F, fill=col); x += w
        baseval = base["vals"].get(pri)
        for p in profs:
            v = p["vals"].get(pri)
            vs = (str(int(v)) if float(v).is_integer() else f"{v:g}")
            differs = (v != baseval)
            col = YELLOW_TXT if is15 else (DIFF if differs else TXT)
            d.text((x + 6, y + 8), vs, font=(FB if differs or is15 else F), fill=col); x += VW
        d.line([PAD, y, width - PAD, y], fill=GRID)
        y += ROWH
    # column separators
    xx = PAD + sum(w for _, w in LEFT)
    for _ in range(len(profs) + 1):
        d.line([xx, y0, xx, y], fill=GRID); xx += VW
    d.rectangle([PAD, y0, width - PAD, y], outline=GRID)
    d.text((PAD, y + 8), "blue = differs from base 0.5 profile   ·   yellow = Zero (priority 15), pending IB-manager confirm", font=FS, fill=MUTED)
    img.save(OUT)
    print("saved:", OUT, img.size)

if __name__ == "__main__":
    main()

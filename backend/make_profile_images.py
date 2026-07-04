"""make_profile_images.py — render a PNG table for every commission profile (like the IB-5 photo)."""
import os
import psycopg2
from PIL import Image, ImageDraw, ImageFont
import ib_commission as IC

OUT = r"C:\Broker-crm\IB commission setting\profiles"
os.makedirs(OUT, exist_ok=True)

# colors (dark theme to match the screenshot)
BG, HEADER_BG, ROW_A, ROW_B = (24, 26, 32), (38, 41, 50), (24, 26, 32), (30, 33, 40)
TXT, HEAD_TXT, MUTED = (225, 228, 235), (255, 255, 255), (150, 158, 170)
YELLOW = (60, 54, 20)          # priority-15 row highlight
YELLOW_TXT = (240, 210, 90)
GREEN, ORANGE = (0, 229, 160), (255, 170, 0)
GRID = (52, 56, 66)

# columns: (label, key, width, align)
COLS = [("ID", "serial", 55, "l"), ("Priority", "priority", 80, "l"), ("Name", "name", 190, "l"),
        ("Symbol pattern", "symbols", 720, "l"), ("Distribution", "distribution", 120, "l"),
        ("Value", "value", 75, "l")]
PAD = 14
ROWH = 34

def font(sz, bold=False):
    p = r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf"
    return ImageFont.truetype(p, sz)

F, FB, FT = font(14), font(14, True), font(18, True)

def fit(draw, text, f, maxw):
    if draw.textlength(text, font=f) <= maxw:
        return text
    while text and draw.textlength(text + "…", font=f) > maxw:
        text = text[:-1]
    return text + "…"

def render(profile_name, ib_level, rules, serial_base, path):
    width = sum(c[2] for c in COLS) + PAD * 2
    height = 16 + 30 + 8 + ROWH * (len(rules) + 1) + 16   # title + header + rows
    img = Image.new("RGB", (width, height), BG)
    d = ImageDraw.Draw(img)
    y = 14
    label = f"IB-{ib_level}" if ib_level else "tier"
    d.text((PAD, y), f"{profile_name}   ({label})", font=FT, fill=HEAD_TXT)
    y += 32
    # header
    d.rectangle([PAD, y, width - PAD, y + ROWH], fill=HEADER_BG)
    x = PAD
    for lbl, key, w, al in COLS:
        d.text((x + 8, y + 9), lbl, font=FB, fill=HEAD_TXT)
        x += w
    y += ROWH
    # rows
    for i, r in enumerate(rules):
        is15 = r["priority"] == 15
        bg = YELLOW if is15 else (ROW_B if i % 2 else ROW_A)
        d.rectangle([PAD, y, width - PAD, y + ROWH], fill=bg)
        x = PAD
        for lbl, key, w, al in COLS:
            v = r.get(key, "")
            if key == "distribution":
                v = "Pips" if v == "pips" else "USD Per Lot"
            v = str(v)
            col = TXT
            if is15:
                col = YELLOW_TXT
            elif key == "distribution":
                col = GREEN if r["distribution"] == "pips" else ORANGE
            elif key == "symbols":
                col = MUTED
            d.text((x + 8, y + 9), fit(d, v, F, w - 14), font=(FB if is15 and key in ("priority", "name") else F), fill=col)
            x += w
        d.line([PAD, y, width - PAD, y], fill=GRID)
        y += ROWH
    d.rectangle([PAD, 46, width - PAD, y], outline=GRID)
    img.save(path)


def main():
    cn = psycopg2.connect(IC.PG_DSN); cur = cn.cursor()
    cur.execute("SELECT id, name, ib_level FROM commission_profiles ORDER BY COALESCE(ib_level,9999), id")
    profs = cur.fetchall()
    for idx, (pid, name, lvl) in enumerate(profs):
        cur.execute("""SELECT priority, name, symbols, distribution, value
                       FROM commission_rules WHERE profile_id=%s ORDER BY priority""", (pid,))
        rules = [dict(priority=r[0], name=r[1], symbols=r[2], distribution=r[3],
                      value=(int(r[4]) if float(r[4]).is_integer() else r[4]),
                      serial=idx * 16 + i + 1) for i, r in enumerate(cur.fetchall())]
        safe = name.replace("/", "-").replace(" ", "_")
        fname = f"{idx+1:02d}_{('IB'+str(lvl)) if lvl else 'tier'}_{safe}.png"
        path = os.path.join(OUT, fname)
        render(name, lvl, rules, idx * 16, path)
        print(f"  {fname}  ({len(rules)} rules)")
    cn.close()
    print(f"\nDone -> {OUT}")


if __name__ == "__main__":
    main()

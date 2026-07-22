"""Strip emoji from the frontend/portal UI source. Removes pictographic emoji + emoji-style
symbols and their VS16/ZWJ/keycap modifiers, cleaning up the adjacent space so 'X IB List' -> 'IB List'.
KEEPS functional glyphs that aren't really 'emoji': arrows (U+2190-21FF: -> <- up/down/sort),
the plain check/close marks (checkU2713, xU2715, U2717) and the mid-dot separator."""
import re, glob, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# removable emoji ranges — NOTE we carve out 2713/2715/2717 (check/x/close) and leave 2190-21FF (arrows) untouched
REMOVABLE = ("[\U0001F000-\U0001FAFF"      # all pictographs/emoticons/transport/symbols/supplemental
             "☀-✒✔✖✘-➿"   # misc symbols + dingbats, minus checkU2713 xU2715 U2717
             "⬀-⯿"               # stars/emoji arrows (star, up/down emoji arrows)
             "⤴⤵〰〽㊗㊙©®"
             "️‍⃣]")         # VS16 / ZWJ / keycap combiner
# a cluster of removable chars, optionally with ONE adjacent space to absorb
PAT = re.compile(r" ?(?:" + REMOVABLE + r")+ ?")

def repl(m):
    s = m.group(0)
    return " " if (s[:1] == " " and s[-1:] == " ") else ""

files = []
for base in ("C:/Broker-crm/frontend/src", "C:/Broker-crm/portal/src"):
    files += glob.glob(base + "/**/*.tsx", recursive=True)
    files += glob.glob(base + "/**/*.ts", recursive=True)

changed = 0; removed = 0
for f in files:
    t = open(f, encoding="utf-8").read()
    before = len(PAT.findall(t))
    if not before:
        continue
    nt = PAT.sub(repl, t)
    # tidy: empty label quotes left like ''  ->  keep; collapse "  " that we may have created inside quotes only
    open(f, "w", encoding="utf-8").write(nt)
    changed += 1; removed += before
    print(f"  {before:4}  {f.split('src/')[-1]}")
print(f"\nstripped emoji from {changed} files ({removed} clusters)")

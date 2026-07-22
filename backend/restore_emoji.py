"""Re-add the emoji the strip removed, ONLY to IBAdmin.tsx / IBPortal.tsx (the two files that also
carry this session's edits, so they can't just be git-checked-out). We derive the mapping from the
committed (HEAD) versions: for every emoji cluster + short following text, compute its STRIPPED form
and map it back to the original. Keys include the leading delimiter (quote / > ) so they are precise.
Applied to the current file, this reverses the strip exactly where a label survived unchanged."""
import re, subprocess, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REMOVABLE = ("[\U0001F000-\U0001FAFF"
             "☀-✒✔✖✘-➿"
             "⬀-⯿"
             "⤴⤵〰〽㊗㊙©®"
             "️‍⃣]")
PAT = re.compile(r" ?(?:" + REMOVABLE + r")+ ?")
def strip(s):
    return PAT.sub(lambda m: " " if (m.group(0)[:1] == " " and m.group(0)[-1:] == " ") else "", s)
HASEMOJI = re.compile(REMOVABLE)

for path in ("C:/Broker-crm/frontend/src/IBAdmin.tsx", "C:/Broker-crm/frontend/src/IBPortal.tsx"):
    rel = path.split("Broker-crm/")[1]
    head = subprocess.run(["git", "show", "HEAD:" + rel], capture_output=True, encoding="utf-8", cwd="C:/Broker-crm").stdout
    # emoji cluster + up to 30 following chars that are NOT a quote/backtick/angle (a label body),
    # with the ONE leading delimiter char captured for precision
    mapping = {}
    for m in re.finditer(r"([\'\"\`>])((?:" + REMOVABLE + r")[^\'\"\`<>]{0,30})", head):
        orig = m.group(1) + m.group(2)
        st = strip(orig)
        if st != orig and st not in mapping:
            mapping[st] = orig
    cur = open(path, encoding="utf-8").read()
    applied = 0
    # longest keys first so we don't partially match
    for st in sorted(mapping, key=len, reverse=True):
        if st in cur:
            cur = cur.replace(st, mapping[st])
            applied += 1
    open(path, "w", encoding="utf-8").write(cur)
    left = len(HASEMOJI.findall(cur))
    print(f"{rel}: {len(mapping)} emoji labels in HEAD, re-added {applied}, emoji now present: {left}")

p = r"C:\broker-crm\frontend\src\Dashboard.tsx"
s = open(p, encoding="utf-8").read()

changed = []

# 1. Add import after NegBalance import
if "import Loyalty from './Loyalty'" not in s:
    s = s.replace("import NegBalance from './NegBalance';",
                  "import NegBalance from './NegBalance';\nimport Loyalty from './Loyalty';")
    changed.append("import")

# 2. Add menu item after the Abuse Detection menu line
if "key: 'loyalty'" not in s:
    # find the abuse menu item line and add loyalty after it
    import re
    m = re.search(r"(\{ icon: '[^']*', label: 'Abuse Detection',\s*key: 'abuse' \},)", s)
    if m:
        s = s.replace(m.group(1), m.group(1) + "\n      { icon: '\U0001F381', label: 'Loyalty', key: 'loyalty' },")
        changed.append("menu")

# 3. Add render line after the abuse render line
if "active === 'loyalty'" not in s:
    s = s.replace("{active === 'abuse'          && <AbuseDetection />}",
                  "{active === 'abuse'          && <AbuseDetection />}\n          {active === 'loyalty'        && <Loyalty />}")
    changed.append("render")

open(p, "w", encoding="utf-8").write(s)
print("Edits applied:", changed if changed else "none (already present)")

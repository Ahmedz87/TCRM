p = "Dashboard.tsx"
s = open(p, encoding="utf-8").read()
ch = []
if "import PaymentSettings" not in s:
    s = s.replace("import ScoreSettings from './ScoreSettings';",
        "import ScoreSettings from './ScoreSettings';\nimport PaymentSettings from './PaymentSettings';\nimport AccountTypes from './AccountTypes';", 1)
    ch.append("imports")
nav_anchor = "{ icon: '\U0001f464', label: 'Users & roles',     key: 'settings_users' },"
if nav_anchor in s and "settings_payments" not in s:
    s = s.replace(nav_anchor,
        nav_anchor + "\n      { icon: '\U0001f4b3', label: 'Payment methods',   key: 'settings_payments' },\n      { icon: '\U0001f5c2', label: 'Account types',     key: 'settings_account_types' },", 1)
    ch.append("nav")
render_anchor = "{active === 'settings_users' && <UserManagement />}"
if render_anchor in s and "settings_payments' &&" not in s:
    s = s.replace(render_anchor,
        render_anchor + "\n          {active === 'settings_payments' && <PaymentSettings />}\n          {active === 'settings_account_types' && <AccountTypes />}", 1)
    ch.append("render")
if "active !== 'settings_payments'" not in s:
    s = s.replace("active !== 'neg_balance'",
        "active !== 'neg_balance' && active !== 'settings_payments' && active !== 'settings_account_types'")
    ch.append("exclusion")
if "'settings_score','settings_users'" in s and "'settings_payments'" not in s:
    s = s.replace("'settings_score','settings_users'",
        "'settings_score','settings_users','settings_payments','settings_account_types'")
    ch.append("overflow")
open(p, "w", encoding="utf-8").write(s)
print("Dashboard.tsx patched:", ch)

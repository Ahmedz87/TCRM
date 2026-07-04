p = r"C:\broker-crm\frontend\src\NegBalance.tsx"
s = open(p, encoding="utf-8").read()

# The Run button is disabled unless eligible. Make it ALWAYS clickable (manual cover allowed for all).
old = """<button onClick={() => coverOne(a.login)} disabled={busy === a.login || !eligible}
                        style={{ padding: '4px 10px', borderRadius: 6, border: 'none', background: eligible ? '#00e5a0' : '#222', color: eligible ? '#000' : '#555', fontWeight: 600, cursor: eligible ? 'pointer' : 'default', fontSize: 11, marginRight: 4, fontFamily: 'inherit' }}>
                        {busy === a.login ? '...' : 'Run'}
                      </button>"""

new = """<button onClick={() => coverOne(a.login)} disabled={busy === a.login}
                        style={{ padding: '4px 10px', borderRadius: 6, border: 'none', background: eligible ? '#00e5a0' : '#ff8800', color: '#000', fontWeight: 600, cursor: 'pointer', fontSize: 11, marginRight: 4, fontFamily: 'inherit' }}
                        title={eligible ? 'Cover this account' : 'Manual cover (not auto-eligible)'}>
                        {busy === a.login ? '...' : 'Run'}
                      </button>"""

if old in s:
    s = s.replace(old, new)
    open(p, "w", encoding="utf-8").write(s)
    print("Run button now clickable for ALL accounts (eligible=green, manual=orange)")
else:
    print("Button pattern not matched - showing current Run button:")
    i = s.find("coverOne(a.login)")
    print(s[i-60:i+300])

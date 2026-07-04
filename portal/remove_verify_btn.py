p = r"C:\broker-crm\frontend\src\NegBalance.tsx"
s = open(p, encoding="utf-8").read()

# Remove the Verify button (keep the Run button after it)
old = """<button onClick={() => verifyOne(a.login)} disabled={busy === a.login}
                        style={{ padding: '4px 9px', borderRadius: 6, border: '1px solid #00aaff', background: 'transparent', color: '#00aaff', fontWeight: 600, cursor: 'pointer', fontSize: 11, marginRight: 4, fontFamily: 'inherit' }}
                        title="Check live balance & floating PnL">
                        {busy === a.login ? '...' : 'Verify'}
                      </button>
                      """
if old in s:
    s = s.replace(old, "")
    print("Verify button removed")
else:
    print("Verify button pattern not matched")
    i = s.find("verifyOne(a.login)")
    print(repr(s[i-100:i+150]) if i>0 else "verifyOne not in file")

open(p, "w", encoding="utf-8").write(s)
print("Saved")

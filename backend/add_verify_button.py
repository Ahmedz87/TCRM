p = r"C:\broker-crm\frontend\src\NegBalance.tsx"
s = open(p, encoding="utf-8").read()

# Find the Run button and add Verify before it + disable Run when positive PnL
old = """<button onClick={() => coverOne(a.login)} disabled={busy === a.login}
                        style={{ padding: '4px 10px', borderRadius: 6, border: 'none', background: eligible ? '#00e5a0' : '#ff8800', color: '#000', fontWeight: 600, cursor: 'pointer', fontSize: 11, marginRight: 4, fontFamily: 'inherit' }}
                        title={eligible ? 'Cover this account' : 'Manual cover (not auto-eligible)'}>
                        {busy === a.login ? '...' : 'Run'}
                      </button>"""

new = """<button onClick={() => verifyOne(a.login)} disabled={busy === a.login}
                        style={{ padding: '4px 9px', borderRadius: 6, border: '1px solid #00aaff', background: 'transparent', color: '#00aaff', fontWeight: 600, cursor: 'pointer', fontSize: 11, marginRight: 4, fontFamily: 'inherit' }}
                        title="Check live balance & floating PnL">
                        {busy === a.login ? '...' : 'Verify'}
                      </button>
                      <button onClick={() => coverOne(a.login)} disabled={busy === a.login || a.status === 'has_positions_positive_pnl'}
                        style={{ padding: '4px 10px', borderRadius: 6, border: 'none', background: a.status === 'has_positions_positive_pnl' ? '#333' : (eligible ? '#00e5a0' : '#ff8800'), color: a.status === 'has_positions_positive_pnl' ? '#666' : '#000', fontWeight: 600, cursor: a.status === 'has_positions_positive_pnl' ? 'default' : 'pointer', fontSize: 11, marginRight: 4, fontFamily: 'inherit' }}
                        title={a.status === 'has_positions_positive_pnl' ? 'Positive PnL — cannot cover' : (eligible ? 'Cover this account' : 'Manual cover')}>
                        {busy === a.login ? '...' : 'Run'}
                      </button>"""

if old in s:
    s = s.replace(old, new)
    open(p, "w", encoding="utf-8").write(s)
    print("Verify button added + Run disabled for Positive PnL")
else:
    print("Run button pattern not matched - showing current:")
    i = s.find("coverOne(a.login)")
    print(s[i-80:i+300])

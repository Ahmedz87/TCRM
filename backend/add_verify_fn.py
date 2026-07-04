p = r"C:\broker-crm\frontend\src\NegBalance.tsx"
s = open(p, encoding="utf-8").read()

# 1. Add a verifyOne function near coverOne
if "const verifyOne" not in s:
    anchor = "const coverOne = async (login: number) => {"
    verify_fn = '''const verifyOne = async (login: number) => {
    setBusy(login);
    try {
      const r = await fetch(`${API}/neg-cover/verify/${login}`, { headers: { Authorization: `Bearer ${tok()}` } });
      const d = await r.json();
      if (d.error) { addLog(`#${login} verify failed`); }
      else {
        setData((prev: any) => ({
          ...prev,
          accounts: prev.accounts.map((a: any) => a.login === login ? { ...a, status: d.status, balance: d.balance, credit: d.credit, deficit: d.deficit, floating_pnl: d.floating_pnl, positions: d.positions, verified: true } : a)
        }));
        addLog(`✓ #${login} verified: PnL ${d.floating_pnl?.toFixed(2)}, ${d.positions} pos → ${d.status}`);
      }
    } catch { addLog(`#${login} verify error`); }
    setBusy(null);
  };

  const coverOne = async (login: number) => {'''
    s = s.replace(anchor, verify_fn)
    print("1. verifyOne function added")

# 2. Add "Positive PnL" to STATUS_INFO
if "has_positions_positive_pnl" not in s:
    s = s.replace(
        "credit_low:       { label:'Credit too low',  color:'#ff8800' },",
        "credit_low:       { label:'Credit too low',  color:'#ff8800' },\n  has_positions_positive_pnl: { label:'Positive PnL',   color:'#00aaff' },"
    )
    print("2. Positive PnL status added")

open(p, "w", encoding="utf-8").write(s)
print("Saved")

p = r"C:\broker-crm\frontend\src\NegBalance.tsx"
s = open(p, encoding="utf-8").read()

# 1. Update table header — add Credit, Network, Abuse columns
old_head = "{['Login', 'Name', 'Balance', 'Credit', 'Deficit', 'Status', ''].map(h => ("
new_head = "{['Login', 'Name', 'Balance', 'Credit', 'Deficit', 'Network', 'Abuse', 'Status', ''].map(h => ("
s = s.replace(old_head, new_head)

# 2. Update colspan for empty state
s = s.replace("<td colSpan={7}", "<td colSpan={9}")

# 3. Update each row — add credit-low red styling + Network + Abuse cells
old_row = """                return (
                  <tr key={a.login} style={{ borderBottom: '1px solid #1a1d24', opacity: a.no_auto_cover ? 0.5 : 1 }}>
                    <td style={{ padding: '9px 8px', fontFamily: 'monospace' }}>#{a.login}</td>
                    <td style={{ padding: '9px 8px' }}>{a.name}</td>
                    <td style={{ padding: '9px 8px', color: '#ff4d4d', fontWeight: 600 }}>{a.balance?.toFixed(2)}</td>
                    <td style={{ padding: '9px 8px', color: '#888' }}>{a.credit?.toFixed(2)}</td>
                    <td style={{ padding: '9px 8px', color: '#ff8800' }}>{a.deficit?.toFixed(2)}</td>
                    <td style={{ padding: '9px 8px' }}>
                      <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, border: `1px solid ${si.color}`, color: si.color }}>{si.label}</span>
                      {a.no_auto_cover && <span style={{ fontSize: 9, color: '#888', marginLeft: 4 }}>🚫 excluded</span>}
                    </td>"""

new_row = """                const creditLow = a.status === 'credit_low';
                const net = a.network_score || 0;
                const netColor = net >= 70 ? '#ff4d4d' : net >= 40 ? '#ffaa00' : '#00e5a0';
                return (
                  <tr key={a.login} style={{ borderBottom: '1px solid #1a1d24', opacity: a.no_auto_cover ? 0.5 : 1, background: creditLow ? 'rgba(255,77,77,0.06)' : 'transparent' }}>
                    <td style={{ padding: '9px 8px', fontFamily: 'monospace' }}>#{a.login}</td>
                    <td style={{ padding: '9px 8px' }}>{a.name}</td>
                    <td style={{ padding: '9px 8px', color: '#ff4d4d', fontWeight: 600 }}>{a.balance?.toFixed(2)}</td>
                    <td style={{ padding: '9px 8px', color: creditLow ? '#ff8800' : '#00e5a0', fontWeight: 600 }}>{a.credit?.toFixed(2)}</td>
                    <td style={{ padding: '9px 8px', color: '#ff8800' }}>{a.deficit?.toFixed(2)}</td>
                    <td style={{ padding: '9px 8px' }}>
                      {net > 0 ? <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 99, border: `1px solid ${netColor}`, color: netColor, fontWeight: 600 }}>{Math.min(10, Math.round(net/10))}/10</span> : <span style={{ color: '#444' }}>—</span>}
                    </td>
                    <td style={{ padding: '9px 8px' }}>
                      {(a.is_flagged || a.in_abuse) ? <span title={a.in_abuse ? 'In abuse case' : 'Flagged'} style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, background: 'rgba(255,77,77,0.15)', color: '#ff4d4d', border: '1px solid #ff4d4d' }}>🚨 {a.in_abuse ? 'Abuse' : 'Flag'}</span> : <span style={{ color: '#444' }}>—</span>}
                    </td>
                    <td style={{ padding: '9px 8px' }}>
                      <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, border: `1px solid ${si.color}`, color: si.color }}>{si.label}</span>
                      {a.no_auto_cover && <span style={{ fontSize: 9, color: '#888', marginLeft: 4 }}>🚫 excluded</span>}
                    </td>"""

s = s.replace(old_row, new_row)

open(p, "w", encoding="utf-8").write(s)
print("Frontend updated:")
print("  Header has Network/Abuse:", "'Network', 'Abuse'" in s)
print("  Red credit-low rows:", "creditLow ? 'rgba(255,77,77,0.06)'" in s)
print("  Abuse cell:", "in_abuse ? 'In abuse case'" in s)

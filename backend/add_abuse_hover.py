p = r"C:\broker-crm\frontend\src\NegBalance.tsx"
s = open(p, encoding="utf-8").read()

# Add hover state near the other useState declarations
if "abuseHover" not in s:
    s = s.replace(
        "const [busy, setBusy] = useState<number|null>(null);",
        "const [busy, setBusy] = useState<number|null>(null);\n  const [abuseHover, setAbuseHover] = useState<number|null>(null);"
    )

# Replace the abuse cell with a hover version showing type + reason
old_abuse_cell = """                    <td style={{ padding: '9px 8px' }}>
                      {(a.is_flagged || a.in_abuse) ? <span title={a.in_abuse ? 'In abuse case' : 'Flagged'} style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, background: 'rgba(255,77,77,0.15)', color: '#ff4d4d', border: '1px solid #ff4d4d' }}>🚨 {a.in_abuse ? 'Abuse' : 'Flag'}</span> : <span style={{ color: '#444' }}>—</span>}
                    </td>"""

new_abuse_cell = """                    <td style={{ padding: '9px 8px', position: 'relative' }}>
                      {(a.is_flagged || a.in_abuse) ? (
                        <span onMouseEnter={() => setAbuseHover(a.login)} onMouseLeave={() => setAbuseHover(null)}
                          style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, background: 'rgba(255,77,77,0.15)', color: '#ff4d4d', border: '1px solid #ff4d4d', cursor: 'help' }}>
                          🚨 {a.in_abuse ? 'Abuse' : 'Flag'}
                        </span>
                      ) : <span style={{ color: '#444' }}>—</span>}
                      {abuseHover === a.login && a.abuse_info && (
                        <div style={{ position: 'absolute', bottom: '120%', left: 0, background: '#1a1d24', border: '1px solid #ff4d4d', borderRadius: 10, padding: 12, width: 260, zIndex: 999, boxShadow: '0 8px 30px rgba(0,0,0,0.6)' }}>
                          <div style={{ fontSize: 12, fontWeight: 700, color: '#ff4d4d', marginBottom: 6, textTransform: 'capitalize' }}>
                            {(a.abuse_info.type || '').replace(/_/g, ' ')}
                          </div>
                          <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
                            <span style={{ fontSize: 9, padding: '1px 6px', borderRadius: 4, background: 'rgba(255,77,77,0.2)', color: '#ff8888' }}>Severity: {a.abuse_info.severity}</span>
                            <span style={{ fontSize: 9, padding: '1px 6px', borderRadius: 4, background: 'rgba(255,170,0,0.2)', color: '#ffaa00' }}>Risk: {a.abuse_info.risk}</span>
                          </div>
                          <div style={{ fontSize: 11, color: '#ccc', lineHeight: 1.5 }}>{a.abuse_info.reason}</div>
                        </div>
                      )}
                    </td>"""

s = s.replace(old_abuse_cell, new_abuse_cell)

open(p, "w", encoding="utf-8").write(s)
print("Abuse hover added:", "abuseHover === a.login" in s)

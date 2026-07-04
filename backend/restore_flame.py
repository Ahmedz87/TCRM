p = r"C:\broker-crm\frontend\src\Leads.tsx"
s = open(p, encoding="utf-8").read()

# Check if the no-deposit badge block still exists
if "registered_no_deposit" in s and "🔥" not in s:
    # Re-add the flame badge next to the recapture badge in the name cell
    # Find the recapture badge and add no-deposit flame after it
    anchor = """{l.match_badge === 'recapture' && ("""
    # locate the full recapture span to insert after its closing
    i = s.find(anchor)
    if i > 0:
        # find the end of the recapture badge block ")}"
        end = s.find(")}", i) + 2
        flame = '''
                    {l.match_badge === 'registered_no_deposit' && (
                      <span title={`Opened account #${l.matched_login} but never deposited — hot lead!`}
                        style={{ fontSize:11, padding:'1px 5px', borderRadius:99, background:'#ff880022', border:'1px solid #ff8800', whiteSpace:'nowrap' }}>🔥</span>
                    )}'''
        s = s[:end] + flame + s[end:]
        open(p, "w", encoding="utf-8").write(s)
        print("🔥 flame badge restored for no-deposit leads")
    else:
        print("recapture anchor not found")
elif "🔥" in s:
    print("Flame already present")
else:
    print("Badge block structure changed - showing recapture area:")
    i = s.find("match_badge === 'recapture'")
    print(repr(s[i-20:i+200]))

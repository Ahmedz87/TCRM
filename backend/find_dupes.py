p = r"C:\broker-crm\backend\clients_router.py"
s = open(p, encoding="utf-8").read()

# Count how many times key mapping patterns appear
print("Number of 'all_logins' mappings:", s.count('"all_logins":'))
print("Number of 'call_score' assignments:", s.count('mapped["call_score"]'))
print("Number of 'append(mapped)':", s.count("append(mapped)"))
print("Number of 'clients.append':", s.count("clients.append"))
print("Number of 'return' with clients:", s.count("return {"))

# Find ALL places where a client dict gets built (look for "login": r[0])
import re
print("\nPlaces building client dict ('login': r[0] or r[...]):")
for m in re.finditer(r'"login":\s*r\[', s):
    i = m.start()
    print(f"  at char {i}: ...{s[i:i+40]}...")

# Is there a second endpoint or helper?
print("\nFunctions defined:")
for m in re.finditer(r'\ndef (\w+)', s):
    print(f"  def {m.group(1)}")

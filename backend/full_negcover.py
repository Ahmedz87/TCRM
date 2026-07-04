p = r"C:\broker-crm\backend\bridge.py"
s = open(p, encoding="utf-8").read()
# Show the full neg_cover function, all of it
i = s.find("def neg_cover")
j = s.find("@app.route", i+10)
if j < 0: j = i + 1200
print(s[i:j])

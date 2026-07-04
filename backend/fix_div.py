p = r"C:\broker-crm\backend\loyalty_engine.py"
s = open(p, encoding="utf-8").read()
s = s.replace("float(volume or 0)/100.0", "float(volume or 0)/10000.0")
open(p, "w", encoding="utf-8").write(s)
print("divisor -> /10000 fixed" if "/10000.0" in s else "no change needed")

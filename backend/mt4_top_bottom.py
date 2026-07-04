s = open(r"C:\broker-crm\backend\bridge_mt4.py", encoding="utf-8", errors="ignore").read()
print("=== Top of file (imports) ===")
print(s[:600])
print("\n=== End of file (startup / __main__) ===")
print(s[-700:])
# Check if Flask already imported
print("\n=== Flask present? ===")
print("Flask imported:", "from flask" in s.lower() or "import flask" in s.lower())
print("get_open_trades returns profit field:", "profit" in s[s.find("def get_open_trades"):s.find("def get_open_trades")+1500])

s = open(r"C:\broker-crm\backend\bridge_mt4.py", encoding="utf-8", errors="ignore").read()

# Show the vcall helper (how DLL methods are called)
i = s.find("def vcall")
print("=== vcall ===")
print(s[i:i+400])

# Show get_manager (how the MT4 manager connection works)
i = s.find("def get_manager")
print("\n=== get_manager ===")
print(s[i:i+300])

# Show get_all_users or get_margins (to see how account fields are read)
i = s.find("def get_margins")
print("\n=== get_margins (first 600 chars) ===")
print(s[i:i+600])

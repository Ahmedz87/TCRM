
# This patch adds sync_deals_to_transactions() call to load_all() in bridge.py
# Run: python bridge_patch.py

with open(r"C:\broker-crm\backend\bridge.py", "r", encoding="utf-8") as f:
    content = f.read()

# Add import at top of load_all
old_enrich = "        enrich_deals(traders_dict, manager)"
new_enrich = """        enrich_deals(traders_dict, manager)
        # Sync balance deals to transactions table
        try:
            from sync_transactions import sync
            new_tx = sync()
            log.info("Transaction sync: done")
        except Exception as e:
            log.error("Transaction sync error: %s", e)"""

if old_enrich in content:
    content = content.replace(old_enrich, new_enrich)
    with open(r"C:\broker-crm\backend\bridge.py", "w", encoding="utf-8") as f:
        f.write(content)
    print("Bridge patched successfully!")
else:
    print("Pattern not found - check bridge.py manually")
    # Show context
    idx = content.find("enrich_deals")
    print(content[idx-100:idx+200])

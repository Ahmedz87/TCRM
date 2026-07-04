import sys
sys.path.insert(0, r"C:\broker-crm\backend")
import MT5Manager

mgr = MT5Manager.ManagerAPI()

# Get the signature/docstring of DealerBalance
print("=== DealerBalance ===")
print("doc:", MT5Manager.ManagerAPI.DealerBalance.__doc__)
print()
print("=== DealerBalanceRaw ===")
print("doc:", MT5Manager.ManagerAPI.DealerBalanceRaw.__doc__)
print()
print("=== UserAccountGet ===")
print("doc:", MT5Manager.ManagerAPI.UserAccountGet.__doc__)
print()
# Check the deal action enum constants for balance/credit
print("=== MT5 deal action constants ===")
for name in dir(MT5Manager):
    if 'DEAL' in name.upper() or 'ENUM_DEAL' in name.upper():
        print(f"  {name}")

import sys
sys.path.insert(0, r"C:\broker-crm\backend")
import MT5Manager
# Check MTDeal.EnDealAction more directly
print("EnDealAction type:", type(MT5Manager.MTDeal.EnDealAction))
try:
    print("Value:", int(MT5Manager.MTDeal.EnDealAction))
except: pass
# Common MT5 deal actions reference
print("\nStandard MT5 codes: BUY=0, SELL=1, BALANCE=2, CREDIT=3, CHARGE=4, CORRECTION=5, BONUS=6")

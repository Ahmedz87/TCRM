import subprocess, sys, os

print("=== Checking Python architecture (must match MT4 DLL) ===")
import platform
print(f"Python: {platform.architecture()[0]} — {sys.version}")

print("\n=== Trying to install MT4 Manager wrapper ===")

# Option 1: pip install pymt4 or similar
packages = ['pymt4', 'mt4-manager', 'mtmanapi', 'MT4Manager']
for pkg in packages:
    result = subprocess.run(
        [sys.executable, '-m', 'pip', 'install', pkg, '--break-system-packages'],
        capture_output=True, text=True
    )
    if 'Successfully installed' in result.stdout:
        print(f"✓ Installed: {pkg}")
        break
    else:
        print(f"✗ {pkg}: not found on PyPI")

print("\n=== Checking for MT4 DLL files ===")
# MT4 Manager API requires mtmanapi.dll (32-bit) or mtmanapi64.dll (64-bit)
search_dirs = [
    r'C:\broker-crm\backend',
    r'C:\broker-crm',
    r'C:\MT4',
    r'C:\Program Files\MetaTrader 4',
    r'C:\Program Files (x86)\MetaTrader 4',
]
found = []
for d in search_dirs:
    if os.path.exists(d):
        for f in os.listdir(d):
            if f.lower().endswith('.dll') and ('manager' in f.lower() or 'mt4' in f.lower() or 'mtman' in f.lower()):
                found.append(os.path.join(d, f))
                print(f"  ✓ {os.path.join(d, f)}")

if not found:
    print("  No MT4 DLL files found")
    print("\n  You need to get mtmanapi64.dll from your MT4 broker/server")
    print("  Place it in C:\\broker-crm\\backend\\")
    print("  Then we can build a ctypes wrapper around it")

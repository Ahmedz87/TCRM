import os, subprocess

print("=== Finding MT4 Manager executable ===")

# Search common locations
search_dirs = [
    r'C:\Program Files',
    r'C:\Program Files (x86)',
    r'C:\Users\Ahmad\AppData\Local',
    r'C:\Users\Ahmad\Desktop',
    r'C:\MT4',
    r'C:\MetaTrader4',
]

for base in search_dirs:
    if not os.path.exists(base): continue
    for root, dirs, files in os.walk(base):
        # Skip deep dirs
        depth = root.replace(base,'').count(os.sep)
        if depth > 3: continue
        for f in files:
            if 'manager' in f.lower() and f.endswith('.exe'):
                print(f"  EXE: {os.path.join(root, f)}")
            if 'mtmanapi' in f.lower() or ('manager' in f.lower() and f.endswith('.dll')):
                print(f"  DLL: {os.path.join(root, f)}")

# Also check origin.txt to find server
print("\n=== MT4 Manager profile origin ===")
for root, dirs, files in os.walk(r'C:\Users\Ahmad\AppData\Roaming\MetaQuotes\MetaTrader 4 Manager'):
    for f in files:
        if f == 'origin.txt':
            with open(os.path.join(root, f)) as fp:
                print(f"  {os.path.join(root,f)}: {fp.read().strip()}")

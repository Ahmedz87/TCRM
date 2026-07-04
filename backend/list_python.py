import urllib.request, json
# The OLD code returned "has_positions". The NEW code can only return "has_positions_positive_pnl" or cover.
# If we get plain "has_positions", an OLD process is serving. Let's check process count.
import subprocess
result = subprocess.run(["tasklist", "/FI", "IMAGENAME eq python.exe"], capture_output=True, text=True)
print(result.stdout)

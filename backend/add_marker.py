p = r"C:\broker-crm\backend\clients_router.py"
s = open(p, encoding="utf-8").read()
# Add a marker key to the dict so we can confirm the running code is THIS file
if '"_patch_marker"' not in s:
    s = s.replace(
        '"source":              "none",\n        }',
        '"source":              "none",\n            "_patch_marker": "v2_recapture",\n        }'
    )
    open(p, "w", encoding="utf-8").write(s)
    print("Marker added. Now restart backend and check for _patch_marker in response.")
else:
    print("Marker already present.")

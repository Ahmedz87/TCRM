"""Registers meta_capi_router in main.py — run once"""
main_path = r'C:\broker-crm\backend\main.py'
with open(main_path, 'r', encoding='utf-8') as f:
    content = f.read()

if 'meta_capi_router' in content:
    print("Already registered.")
else:
    # Add import after the last 'import router as' line
    import_lines = [l for l in content.split('\n') if 'import router as' in l]
    if import_lines:
        last_import = import_lines[-1]
        content = content.replace(
            last_import,
            last_import + '\nfrom meta_capi_router import router as meta_router'
        )
    # Add include after the last include_router line
    include_lines = [l for l in content.split('\n') if 'include_router' in l]
    if include_lines:
        last_include = include_lines[-1]
        content = content.replace(
            last_include,
            last_include + '\napp.include_router(meta_router)'
        )
    with open(main_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Done! meta_capi_router registered in main.py")
    print("Now restart the backend.")

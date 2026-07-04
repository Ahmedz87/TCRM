p = "PaymentSettings.tsx"
s = open(p, encoding="utf-8").read()

old = """  const save = async () => {
    setErr(''); setBusy(true);
    try {
      const body = { ...m };
      if (isNew && !body.code) body.code = (body.name || '').toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '');
      const res: any = isNew
        ? await apiPost('/admin/payments/methods', body)
        : await apiPost(`/admin/payments/methods/${m.id}`, body).catch(() => null) || await fetchPut(m.id, body);
      if (res?.ok || res === null) onSaved();
      else setErr(res?.detail || 'Save failed');
    } catch (e: any) { setErr(e?.message || 'Save failed'); }
    finally { setBusy(false); }
  };

  // PUT helper (api.ts may not export apiPut)
  const fetchPut = async (id: number, body: any) => {
    const token = localStorage.getItem('token') || '';
    const r = await fetch(`http://127.0.0.1:8000/admin/payments/methods/${id}`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }, body: JSON.stringify(body),
    });
    return r.json();
  };"""

new = """  const save = async () => {
    setErr(''); setBusy(true);
    try {
      const body = { ...m };
      if (isNew && !body.code) body.code = (body.name || '').toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '');
      const token = localStorage.getItem('token') || '';
      const url = isNew
        ? 'http://127.0.0.1:8000/admin/payments/methods'
        : `http://127.0.0.1:8000/admin/payments/methods/${m.id}`;
      const r = await fetch(url, {
        method: isNew ? 'POST' : 'PUT',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify(body),
      });
      const res = await r.json().catch(() => ({}));
      if (r.ok && res && res.ok) onSaved();
      else setErr((res && res.detail) || `Save failed (HTTP ${r.status})`);
    } catch (e: any) { setErr(e?.message || 'Save failed'); }
    finally { setBusy(false); }
  };"""

if old in s:
    s = s.replace(old, new)
    open(p, "w", encoding="utf-8").write(s)
    print("PaymentSettings save() fixed - uses POST for new, PUT for edit, proper error reporting")
else:
    print("PATTERN NOT FOUND - the save block may differ; paste lines 132-153")

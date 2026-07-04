import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { apiGet, apiPost } from './api';

const ROLES = ['super_admin', 'admin', 'sales_manager', 'sales_agent', 'marketing', 'finance', 'risk'];
const ROLE_LABELS: Record<string, string> = {
  super_admin:   'Super admin',
  admin:         'Admin',
  sales_manager: 'Sales manager',
  sales_agent:   'Sales agent',
  marketing:     'Marketing',
  finance:       'Finance',
  risk:          'Risk',
};
const ROLE_COLORS: Record<string, [string, string]> = {
  super_admin:   ['#3a0e0e', '#ff4d4d'],
  admin:         ['#3a2a0e', '#ffaa00'],
  sales_manager: ['#0a1a3a', '#00aaff'],
  sales_agent:   ['#0e3a2a', '#00e5a0'],
  marketing:     ['#1a0e3a', '#a479ff'],
  finance:       ['#2a1a3a', '#cc88ff'],
  risk:          ['#3a1a0e', '#ff8844'],
};

interface User {
  id: number;
  full_name: string;
  email: string;
  phone?: string;
  role: string;
  department?: string;
  title?: string;
  avatar_url?: string;
  is_active: boolean;
  is_frozen?: boolean;
  is_blocked?: boolean;
  created_at: string;
  last_login?: string;
  clients_assigned?: number;
  perm_count?: number;
}

interface UserFormData {
  full_name: string;
  email: string;
  role: string;
  password: string;
}

interface CatItem { key: string; label: string; desc: string }
interface Category { category: string; items: CatItem[] }

const thS: React.CSSProperties = {
  padding: '9px 12px', textAlign: 'left', color: '#555', fontWeight: 500,
  fontSize: 11, borderBottom: '1px solid #373f4d', whiteSpace: 'nowrap',
};
const tdS: React.CSSProperties = {
  padding: '9px 12px', borderBottom: '1px solid #2c333e', verticalAlign: 'middle', fontSize: 12,
};

function UserModal({ user, onClose, onSave }: { user: Partial<User> | null; onClose: () => void; onSave: (data: UserFormData) => void }) {
  const [form, setForm] = useState<UserFormData>({
    full_name: user?.full_name || '',
    email:     user?.email    || '',
    role:      user?.role     || 'sales_agent',
    password:  '',
  });

  const isEdit = !!user?.id;

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.75)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 999 }} onClick={onClose}>
      <div style={{ background: '#2c333e', border: '1px solid #626d80', borderRadius: 14, padding: 20, width: 420, maxWidth: '95vw' }} onClick={e => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
          <span style={{ fontSize: 14, fontWeight: 600 }}>{isEdit ? 'Edit user' : 'Add new user'}</span>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#555', cursor: 'pointer', fontSize: 18 }}>✕</button>
        </div>

        {[
          { label: 'Full name', key: 'full_name', type: 'text', placeholder: 'John Smith' },
          { label: 'Email',     key: 'email',     type: 'email', placeholder: 'john@broker.com' },
          { label: isEdit ? 'New password (leave blank to keep)' : 'Password', key: 'password', type: 'password', placeholder: '••••••••' },
        ].map(f => (
          <div key={f.key} style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 11, color: '#555', marginBottom: 5 }}>{f.label}</div>
            <input type={f.type} value={(form as any)[f.key]} placeholder={f.placeholder}
              onChange={e => setForm(p => ({ ...p, [f.key]: e.target.value }))}
              style={{ width: '100%', padding: '8px 12px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 8, color: '#e0e0e0', fontSize: 12, outline: 'none', fontFamily: 'inherit' }} />
          </div>
        ))}

        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 11, color: '#555', marginBottom: 5 }}>Role</div>
          <select value={form.role} onChange={e => setForm(p => ({ ...p, role: e.target.value }))}
            style={{ width: '100%', padding: '8px 12px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 8, color: '#e0e0e0', fontSize: 12, fontFamily: 'inherit' }}>
            {ROLES.map(r => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}
          </select>
          <div style={{ fontSize: 10, color: '#555', marginTop: 5 }}>
            {form.role === 'super_admin' && 'Full access to everything'}
            {form.role === 'admin' && 'Full access except system settings'}
            {form.role === 'sales_manager' && 'Can view all clients, assign agents, see reports'}
            {form.role === 'sales_agent' && 'Can only see assigned clients'}
            {form.role === 'marketing' && 'Can access the Marketing and Leads pages only'}
            {form.role === 'finance' && 'Can approve/reject deposits and withdrawals'}
            {form.role === 'risk' && 'Can review flagged transactions and network alerts'}
          </div>
        </div>

        <div style={{ display: 'flex', gap: 8 }}>
          <button onClick={() => onSave(form)}
            style={{ flex: 1, padding: 8, background: '#00e5a0', border: 'none', borderRadius: 8, color: '#000', fontWeight: 600, cursor: 'pointer', fontSize: 13 }}>
            {isEdit ? 'Save changes' : 'Create user'}
          </button>
          <button onClick={onClose}
            style={{ padding: '8px 16px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 8, color: '#888', cursor: 'pointer', fontSize: 12 }}>
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Avatar (round image if avatar_url present, else role-coloured initials) ──
function Avatar({ user }: { user: User }) {
  const [bg, col] = ROLE_COLORS[user.role] || ['#373f4d', '#555'];
  if (user.avatar_url) {
    return (
      <img src={user.avatar_url} alt="" style={{ width: 30, height: 30, borderRadius: '50%', objectFit: 'cover', flexShrink: 0, border: `1px solid ${col}` }} />
    );
  }
  return (
    <div style={{ width: 30, height: 30, borderRadius: '50%', background: bg, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 600, color: col, flexShrink: 0 }}>
      {(user.full_name || '?').substring(0, 2).toUpperCase()}
    </div>
  );
}

// ── Per-row actions dropdown ──
const MENU_ITEM: React.CSSProperties = {
  display: 'block', width: '100%', textAlign: 'left', padding: '7px 12px',
  background: 'none', border: 'none', color: '#cfd6e0', cursor: 'pointer', fontSize: 12, whiteSpace: 'nowrap',
};

function RowActions({ user, onAction }: { user: User; onAction: (action: string, user: User) => void }) {
  const [open, setOpen] = useState(false);
  const [up, setUp] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const btnRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [open]);

  const toggle = () => {
    if (!open && btnRef.current) {
      const rect = btnRef.current.getBoundingClientRect();
      // open upward if not enough room below (menu ~ 380px tall)
      setUp(window.innerHeight - rect.bottom < 390);
    }
    setOpen(o => !o);
  };

  const item = (key: string, label: string, extra?: React.CSSProperties) => (
    <button style={{ ...MENU_ITEM, ...extra }} onMouseDown={e => e.preventDefault()}
      onClick={() => { setOpen(false); onAction(key, user); }}
      onMouseEnter={e => (e.currentTarget.style.background = '#373f4d')}
      onMouseLeave={e => (e.currentTarget.style.background = 'none')}>
      {label}
    </button>
  );

  const sep = <div style={{ height: 1, background: '#373f4d', margin: '4px 0' }} />;

  return (
    <div ref={ref} style={{ position: 'relative', display: 'inline-block' }}>
      <button ref={btnRef} onClick={toggle}
        style={{ padding: '4px 12px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 6, color: '#cfd6e0', cursor: 'pointer', fontSize: 11 }}>
        Actions ▾
      </button>
      {open && (
        <div style={{
          position: 'absolute', right: 0, [up ? 'bottom' : 'top']: 'calc(100% + 4px)',
          background: '#2c333e', border: '1px solid #626d80', borderRadius: 8, padding: '4px 0',
          minWidth: 180, zIndex: 1000, boxShadow: '0 8px 24px rgba(0,0,0,.5)',
          maxHeight: 380, overflowY: 'auto',
        }}>
          {(() => {
            const myRole = (localStorage.getItem('userRole') || '').toLowerCase();
            const canView = ['super_admin', 'admin', 'director'].includes(myRole);
            return canView ? (<>
              {item('impersonate', '👁 View as this user', { color: '#FF6A1A' })}
              {sep}
            </>) : null;
          })()}
          {item('permissions', '🔐 Permissions')}
          {item('edit', '✏️ Edit')}
          {sep}
          {item('email', '✉️ Change email')}
          {item('phone', '📞 Change phone')}
          {item('department', '🏢 Change department')}
          {item('photo', '🖼️ Upload photo')}
          {sep}
          {item('toggle-active', user.is_active ? '⏸️ Deactivate' : '▶️ Activate', { color: user.is_active ? '#ff8844' : '#00e5a0' })}
          {item('freeze', user.is_frozen ? '🟦 Unfreeze account' : '❄️ Freeze account', { color: '#00aaff' })}
          {item('block', user.is_blocked ? '✅ Unblock' : '⛔ Block', { color: user.is_blocked ? '#00e5a0' : '#ff4d4d' })}
        </div>
      )}
    </div>
  );
}

// ── Permissions editor (full-screen matrix) ──
function PermissionsEditor({ user, onClose, onSaved }: { user: User; onClose: () => void; onSaved: (count: number) => void }) {
  const [catalog, setCatalog] = useState<Category[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [search, setSearch] = useState('');
  const [savedMsg, setSavedMsg] = useState('');

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [cat, grants] = await Promise.all([
          apiGet('/users/permissions/catalog'),
          apiGet(`/users/${user.id}/permissions`),
        ]);
        if (!alive) return;
        setCatalog(cat.catalog || []);
        setSelected(new Set(grants.granted || []));
      } catch (e) { console.error(e); }
      if (alive) setLoading(false);
    })();
    return () => { alive = false; };
  }, [user.id]);

  const allKeys = useMemo(() => catalog.flatMap(c => c.items.map(i => i.key)), [catalog]);

  const term = search.trim().toLowerCase();
  const visible = useMemo(() => {
    if (!term) return catalog;
    return catalog
      .map(c => ({ category: c.category, items: c.items.filter(i =>
        i.label.toLowerCase().includes(term) || (i.desc || '').toLowerCase().includes(term) || i.key.toLowerCase().includes(term)) }))
      .filter(c => c.items.length > 0);
  }, [catalog, term]);

  const toggle = (key: string) => setSelected(s => {
    const n = new Set(s);
    n.has(key) ? n.delete(key) : n.add(key);
    return n;
  });

  const setMany = (keys: string[], on: boolean) => setSelected(s => {
    const n = new Set(s);
    keys.forEach(k => on ? n.add(k) : n.delete(k));
    return n;
  });

  const save = async () => {
    setSaving(true);
    try {
      const res = await apiPost(`/users/${user.id}/permissions`, { keys: Array.from(selected) });
      const count = res?.count ?? selected.size;
      setSavedMsg(`Saved — ${count} permission${count === 1 ? '' : 's'} granted`);
      onSaved(count);
      setTimeout(() => setSavedMsg(''), 2500);
    } catch (e: any) {
      alert(e?.detail || 'Failed to save permissions');
    }
    setSaving(false);
  };

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.8)', zIndex: 1001, display: 'flex', flexDirection: 'column' }}>
      <div style={{ background: '#23282f', flex: 1, display: 'flex', flexDirection: 'column', margin: '2vh auto', width: '96vw', maxWidth: 1200, borderRadius: 14, border: '1px solid #4f596b', overflow: 'hidden' }}>
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '14px 18px', borderBottom: '1px solid #373f4d', flexWrap: 'wrap' }}>
          <Avatar user={user} />
          <div>
            <div style={{ fontSize: 15, fontWeight: 600 }}>👤 {user.full_name}</div>
            <div style={{ fontSize: 11, color: '#555' }}>{ROLE_LABELS[user.role] || user.role} · {user.email}</div>
          </div>
          <div style={{ flex: 1 }} />
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#888', cursor: 'pointer', fontSize: 20 }}>✕</button>
        </div>

        {/* Toolbar */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 18px', borderBottom: '1px solid #373f4d', flexWrap: 'wrap' }}>
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search permissions..."
            style={{ padding: '7px 12px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 8, color: '#e0e0e0', fontSize: 12, width: 260, outline: 'none' }} />
          <span style={{ fontSize: 12, color: '#00e5a0', fontWeight: 600 }}>{selected.size} selected</span>
          <div style={{ flex: 1 }} />
          <button onClick={() => setMany(allKeys, true)}
            style={{ padding: '6px 12px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 7, color: '#cfd6e0', cursor: 'pointer', fontSize: 11 }}>Select all</button>
          <button onClick={() => setMany(allKeys, false)}
            style={{ padding: '6px 12px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 7, color: '#cfd6e0', cursor: 'pointer', fontSize: 11 }}>Clear all</button>
        </div>

        {/* Body */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '14px 18px' }}>
          {loading ? (
            <div style={{ textAlign: 'center', color: '#555', padding: 40 }}>Loading catalog...</div>
          ) : visible.length === 0 ? (
            <div style={{ textAlign: 'center', color: '#555', padding: 40 }}>No permissions match "{search}"</div>
          ) : visible.map(cat => {
            const keys = cat.items.map(i => i.key);
            const allOn = keys.every(k => selected.has(k));
            return (
              <div key={cat.category} style={{ marginBottom: 18 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8, paddingBottom: 5, borderBottom: '1px solid #373f4d' }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: '#cfd6e0' }}>{cat.category}</div>
                  <span style={{ fontSize: 10, color: '#555' }}>{keys.filter(k => selected.has(k)).length}/{keys.length}</span>
                  <div style={{ flex: 1 }} />
                  <button onClick={() => setMany(keys, !allOn)}
                    style={{ padding: '3px 10px', background: 'none', border: '1px solid #4f596b', borderRadius: 6, color: '#888', cursor: 'pointer', fontSize: 10 }}>
                    {allOn ? 'None' : 'All'}
                  </button>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '6px 18px' }}>
                  {cat.items.map(it => {
                    const on = selected.has(it.key);
                    return (
                      <label key={it.key} style={{ display: 'flex', alignItems: 'flex-start', gap: 8, cursor: 'pointer', padding: '4px 6px', borderRadius: 6, background: on ? 'rgba(0,229,160,.06)' : 'transparent' }}>
                        <input type="checkbox" checked={on} onChange={() => toggle(it.key)}
                          style={{ marginTop: 2, accentColor: '#00e5a0', cursor: 'pointer', flexShrink: 0 }} />
                        <span style={{ fontSize: 12, lineHeight: 1.35 }}>
                          <span style={{ fontWeight: 600, color: '#e0e0e0' }}>{it.label}</span>
                          {it.desc ? <span style={{ color: '#7a8392' }}> - {it.desc}</span> : null}
                        </span>
                      </label>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>

        {/* Footer */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '12px 18px', borderTop: '1px solid #373f4d' }}>
          {savedMsg && <span style={{ fontSize: 12, color: '#00e5a0', fontWeight: 600 }}>✓ {savedMsg}</span>}
          <div style={{ flex: 1 }} />
          <button onClick={onClose}
            style={{ padding: '8px 16px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 8, color: '#888', cursor: 'pointer', fontSize: 12 }}>Cancel</button>
          <button onClick={save} disabled={saving || loading}
            style={{ padding: '8px 22px', background: '#00e5a0', border: 'none', borderRadius: 8, color: '#000', fontWeight: 600, cursor: saving ? 'default' : 'pointer', fontSize: 13, opacity: saving || loading ? 0.6 : 1 }}>
            {saving ? 'Saving...' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  );
}

// downscale an image file to a small base64 data URL (<=256px longest edge)
function fileToScaledDataURL(file: File, max = 256): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const img = new Image();
      img.onload = () => {
        let { width, height } = img;
        if (width > height && width > max) { height = Math.round(height * max / width); width = max; }
        else if (height > max) { width = Math.round(width * max / height); height = max; }
        const canvas = document.createElement('canvas');
        canvas.width = width; canvas.height = height;
        const ctx = canvas.getContext('2d');
        if (!ctx) return reject(new Error('canvas unsupported'));
        ctx.drawImage(img, 0, 0, width, height);
        resolve(canvas.toDataURL('image/jpeg', 0.82));
      };
      img.onerror = () => reject(new Error('bad image'));
      img.src = reader.result as string;
    };
    reader.onerror = () => reject(new Error('read error'));
    reader.readAsDataURL(file);
  });
}

export default function UserManagement() {
  const [users, setUsers]       = useState<User[]>([]);
  const [loading, setLoading]   = useState(true);
  const [search, setSearch]     = useState('');
  const [roleFilter, setRoleFilter] = useState('');
  const [showModal, setShowModal]   = useState(false);
  const [editUser, setEditUser]     = useState<Partial<User> | null>(null);
  const [permUser, setPermUser]     = useState<User | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const photoTargetRef = useRef<User | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiGet('/users');
      setUsers(data.users || []);
    } catch (e) { console.error(e); }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleSave = async (form: UserFormData) => {
    try {
      if (editUser?.id) {
        await apiPost(`/users/${editUser.id}`, form);
      } else {
        await apiPost('/users', form);
      }
      setShowModal(false);
      setEditUser(null);
      load();
    } catch (e) { alert('Failed to save user'); }
  };

  // generic endpoint call + reload, surfacing {detail} on error
  const callAndReload = async (path: string, body: any) => {
    try {
      const res = await apiPost(path, body);
      if (res && res.detail && !res.ok) { alert(res.detail); return false; }
      await load();
      return true;
    } catch (e: any) {
      alert(e?.detail || 'Request failed');
      return false;
    }
  };

  const handleAction = async (action: string, u: User) => {
    switch (action) {
      case 'impersonate': {
        // open a read-only session AS this user: stash the admin token, swap in the imp token, reload
        try {
          const res: any = await apiPost(`/auth/impersonate/${u.id}`, {});
          if (res?.access_token) {
            const cur = localStorage.getItem('token');
            if (cur) localStorage.setItem('adminToken', cur);
            localStorage.setItem('token', res.access_token);
            window.location.reload();
          } else alert(res?.detail || 'Could not start preview.');
        } catch (e: any) { alert(e?.detail || 'Could not start preview.'); }
        break;
      }
      case 'permissions':
        setPermUser(u);
        break;
      case 'edit':
        setEditUser(u); setShowModal(true);
        break;
      case 'email': {
        const v = window.prompt(`New email for ${u.full_name}:`, u.email);
        if (v && v.trim() && v.trim() !== u.email) await callAndReload(`/users/${u.id}/email`, { value: v.trim() });
        break;
      }
      case 'phone': {
        const v = window.prompt(`New phone for ${u.full_name}:`, u.phone || '');
        if (v !== null) await callAndReload(`/users/${u.id}/phone`, { value: v.trim() });
        break;
      }
      case 'department': {
        const v = window.prompt(`Department for ${u.full_name}:`, u.department || '');
        if (v !== null) await callAndReload(`/users/${u.id}/department`, { value: v.trim() });
        break;
      }
      case 'photo':
        photoTargetRef.current = u;
        fileInputRef.current?.click();
        break;
      case 'freeze':
        await callAndReload(`/users/${u.id}/freeze`, { on: !u.is_frozen });
        break;
      case 'block':
        if (!u.is_blocked && !window.confirm(`Block ${u.full_name}? They will be logged out and lose access.`)) break;
        await callAndReload(`/users/${u.id}/block`, { on: !u.is_blocked });
        break;
      case 'toggle-active':
        await callAndReload(`/users/${u.id}/toggle-active`, {});
        break;
    }
  };

  const onPhotoPicked = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    const target = photoTargetRef.current;
    e.target.value = '';
    if (!file || !target) return;
    try {
      const dataURL = await fileToScaledDataURL(file, 256);
      await callAndReload(`/users/${target.id}/photo`, { image: dataURL });
    } catch (err: any) {
      alert(err?.message || 'Failed to process image');
    }
  };

  const filtered = users.filter(u => {
    const matchSearch = !search || u.full_name.toLowerCase().includes(search.toLowerCase()) || u.email.toLowerCase().includes(search.toLowerCase());
    const matchRole   = !roleFilter || u.role === roleFilter;
    return matchSearch && matchRole;
  });

  const roleCounts = ROLES.reduce((acc, r) => {
    acc[r] = users.filter(u => u.role === r).length;
    return acc;
  }, {} as Record<string, number>);

  return (
    <div>
      {/* hidden file input for photo upload */}
      <input ref={fileInputRef} type="file" accept="image/*" style={{ display: 'none' }} onChange={onPhotoPicked} />

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
        <div style={{ fontSize: 15, fontWeight: 600 }}>Users & roles</div>
        <div style={{ flex: 1 }} />
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search name or email..."
          style={{ padding: '6px 10px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 7, color: '#e0e0e0', fontSize: 11, width: 220, outline: 'none' }} />
        <select value={roleFilter} onChange={e => setRoleFilter(e.target.value)}
          style={{ padding: '6px 10px', background: '#373f4d', border: '1px solid #626d80', borderRadius: 7, color: '#e0e0e0', fontSize: 11 }}>
          <option value="">All roles</option>
          {ROLES.map(r => <option key={r} value={r}>{ROLE_LABELS[r]} ({roleCounts[r] || 0})</option>)}
        </select>
        <button onClick={() => { setEditUser(null); setShowModal(true); }}
          style={{ padding: '6px 16px', background: '#00e5a0', border: 'none', borderRadius: 8, color: '#000', fontSize: 12, fontWeight: 600, cursor: 'pointer' }}>
          + Add user
        </button>
      </div>

      {/* Role summary */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6,1fr)', gap: 8, marginBottom: 14 }}>
        {ROLES.map(r => {
          const [, col] = ROLE_COLORS[r];
          return (
            <div key={r} onClick={() => setRoleFilter(roleFilter === r ? '' : r)} style={{ background: '#2c333e', border: `1px solid ${roleFilter === r ? col : '#4f596b'}`, borderRadius: 8, padding: 10, cursor: 'pointer' }}>
              <div style={{ fontSize: 18, fontWeight: 600, color: col }}>{roleCounts[r] || 0}</div>
              <div style={{ fontSize: 10, color: '#555', marginTop: 3 }}>{ROLE_LABELS[r]}</div>
            </div>
          );
        })}
      </div>

      {/* Table */}
      <div style={{ background: '#2c333e', border: '1px solid #4f596b', borderRadius: 12, overflow: 'visible' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr>
              {['Name', 'Email', 'Role', 'Perms', 'Clients assigned', 'Last login', 'Created', 'Status', 'Actions'].map(h => (
                <th key={h} style={thS}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={9} style={{ textAlign: 'center', color: '#555', padding: 40 }}>Loading...</td></tr>
            ) : filtered.length === 0 ? (
              <tr><td colSpan={9} style={{ textAlign: 'center', color: '#555', padding: 40 }}>No users found</td></tr>
            ) : filtered.map(u => {
              const [bg, col] = ROLE_COLORS[u.role] || ['#373f4d', '#555'];
              return (
                <tr key={u.id}>
                  <td style={tdS}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <Avatar user={u} />
                      <span style={{ fontWeight: 500 }}>{u.full_name}</span>
                    </div>
                  </td>
                  <td style={{ ...tdS, color: '#666' }}>{u.email}</td>
                  <td style={tdS}>
                    <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, background: bg, color: col, fontWeight: 500 }}>
                      {ROLE_LABELS[u.role] || u.role}
                    </span>
                  </td>
                  <td style={tdS}>
                    <span title="Permissions granted" style={{ fontSize: 11, color: (u.perm_count || 0) > 0 ? '#cc88ff' : '#555', whiteSpace: 'nowrap' }}>
                      🔐 {u.perm_count || 0}
                    </span>
                  </td>
                  <td style={{ ...tdS, color: '#00aaff', textAlign: 'center' }}>{u.clients_assigned || 0}</td>
                  <td style={{ ...tdS, color: '#555' }}>{u.last_login ? new Date(u.last_login).toLocaleDateString() : '—'}</td>
                  <td style={{ ...tdS, color: '#555' }}>{u.created_at ? new Date(u.created_at).toLocaleDateString() : '—'}</td>
                  <td style={tdS}>
                    <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                      <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, background: u.is_active ? '#0e3a2a' : '#373f4d', color: u.is_active ? '#00e5a0' : '#555', fontWeight: 500 }}>
                        {u.is_active ? 'Active' : 'Inactive'}
                      </span>
                      {u.is_frozen && (
                        <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, background: '#0a1a3a', color: '#00aaff', fontWeight: 500 }}>Frozen</span>
                      )}
                      {u.is_blocked && (
                        <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 99, background: '#3a0e0e', color: '#ff4d4d', fontWeight: 500 }}>Blocked</span>
                      )}
                    </div>
                  </td>
                  <td style={tdS}>
                    <RowActions user={u} onAction={handleAction} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <div style={{ padding: '10px 16px', borderTop: '1px solid #373f4d' }}>
          <span style={{ color: '#555', fontSize: 11 }}>{filtered.length} users</span>
        </div>
      </div>

      {/* Add/Edit modal */}
      {showModal && (
        <UserModal user={editUser} onClose={() => { setShowModal(false); setEditUser(null); }} onSave={handleSave} />
      )}

      {/* Permissions editor */}
      {permUser && (
        <PermissionsEditor
          user={permUser}
          onClose={() => setPermUser(null)}
          onSaved={(count) => setUsers(us => us.map(x => x.id === permUser.id ? { ...x, perm_count: count } : x))}
        />
      )}
    </div>
  );
}

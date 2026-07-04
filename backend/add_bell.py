p = r"C:\broker-crm\frontend\src\Dashboard.tsx"
s = open(p, encoding="utf-8").read()

# 1. Add the NotificationBell component before the Dashboard export
if "function NotificationBell" not in s:
    bell = '''
function NotificationBell() {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<any>({ unread: 0, notifications: [] });
  const load = () => {
    const token = localStorage.getItem('token');
    fetch((process.env.REACT_APP_API_URL || 'http://localhost:8000') + '/notifications', {
      headers: { Authorization: 'Bearer ' + token }
    }).then(r => r.json()).then(setData).catch(() => {});
  };
  useEffect(() => {
    load();
    const t = setInterval(load, 30000);
    return () => clearInterval(t);
  }, []);
  const markRead = (id: number) => {
    const token = localStorage.getItem('token');
    fetch((process.env.REACT_APP_API_URL || 'http://localhost:8000') + '/notifications/' + id + '/read', {
      method: 'POST', headers: { Authorization: 'Bearer ' + token }
    }).then(() => load());
  };
  const markAll = () => {
    const token = localStorage.getItem('token');
    fetch((process.env.REACT_APP_API_URL || 'http://localhost:8000') + '/notifications/read-all', {
      method: 'POST', headers: { Authorization: 'Bearer ' + token }
    }).then(() => load());
  };
  return (
    <div style={{ position: 'relative' }}>
      <div onClick={() => setOpen(o => !o)} style={{ cursor: 'pointer', fontSize: 18, position: 'relative' }} title="Notifications">
        🔔
        {data.unread > 0 && (
          <span style={{ position: 'absolute', top: -6, right: -8, background: '#ff4d4d', color: '#fff', borderRadius: 99, fontSize: 9, fontWeight: 700, padding: '1px 5px', minWidth: 14, textAlign: 'center' }}>
            {data.unread}
          </span>
        )}
      </div>
      {open && (
        <div style={{ position: 'absolute', top: '140%', right: 0, width: 320, maxHeight: 420, overflowY: 'auto', background: '#1a1d24', border: '1px solid #333', borderRadius: 12, zIndex: 9999, boxShadow: '0 8px 30px rgba(0,0,0,0.5)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 14px', borderBottom: '1px solid #333' }}>
            <span style={{ fontSize: 13, fontWeight: 600, color: '#fff' }}>Notifications</span>
            {data.unread > 0 && <span onClick={markAll} style={{ fontSize: 11, color: '#00aaff', cursor: 'pointer' }}>Mark all read</span>}
          </div>
          {data.notifications.length === 0 ? (
            <div style={{ padding: 24, textAlign: 'center', color: '#555', fontSize: 12 }}>No notifications</div>
          ) : data.notifications.map((n: any) => (
            <div key={n.id} onClick={() => { markRead(n.id); if (n.link) window.dispatchEvent(new CustomEvent('navigate', { detail: n.link.replace('/', '') })); setOpen(false); }}
              style={{ padding: '11px 14px', borderBottom: '1px solid #222', cursor: 'pointer', background: n.is_read ? 'transparent' : 'rgba(255,77,77,0.06)' }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: n.is_read ? '#aaa' : '#ff4d4d', marginBottom: 3 }}>{n.title}</div>
              <div style={{ fontSize: 11, color: '#888', lineHeight: 1.4 }}>{n.message}</div>
              <div style={{ fontSize: 9, color: '#444', marginTop: 4 }}>{new Date(n.created_at).toLocaleString()}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function Dashboard'''
    s = s.replace("export default function Dashboard", bell, 1)
    print("NotificationBell component added")

# 2. Add the bell next to the logout button
old_logout = '''<div onClick={onLogout} style={{ cursor:'pointer', color:'var(--text3,#555)', fontSize:16 }} title="Logout">⇥</div>'''
new_logout = '''<NotificationBell />
              <div onClick={onLogout} style={{ cursor:'pointer', color:'var(--text3,#555)', fontSize:16 }} title="Logout">⇥</div>'''
if old_logout in s:
    s = s.replace(old_logout, new_logout)
    print("Bell added to top bar")
else:
    print("Logout button pattern not found")

open(p, "w", encoding="utf-8").write(s)
print("Done. Bell present:", "NotificationBell" in s)

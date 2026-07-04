// Portal API client — attaches the portal JWT to every request, handles 401.
// Relative '/api' so it works in any browser: nginx proxies /api/* -> backend (strips /api),
// turning the portal's '/portal/...' calls into '/api/portal/...' -> backend '/portal/...'.
const BASE = '/api';
const TOKEN_KEY = 'tnfx_portal_token';

export function getToken(): string | null {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}
export function setToken(t: string) {
  try { localStorage.setItem(TOKEN_KEY, t); } catch {}
}
export function clearToken() {
  try { localStorage.removeItem(TOKEN_KEY); } catch {}
}
export function isLoggedIn(): boolean {
  return !!getToken();
}

async function handle(res: Response) {
  if (res.status === 401) {
    clearToken();
    // force back to login
    window.dispatchEvent(new Event('portal_logout'));
    throw new Error('unauthorized');
  }
  const txt = await res.text();
  try { return txt ? JSON.parse(txt) : null; } catch { return null; }
}

export async function apiGet(path: string) {
  const res = await fetch(BASE + path, {
    headers: { Authorization: `Bearer ${getToken() || ''}` },
  });
  return handle(res);
}

export async function apiPost(path: string, body: any) {
  const res = await fetch(BASE + path, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${getToken() || ''}`,
    },
    body: JSON.stringify(body || {}),
  });
  return handle(res);
}

// Real client login — identifier (email / trading login / client id) + password.
export async function portalLogin(identifier: string, password: string) {
  const res = await fetch(BASE + '/portal/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ identifier, password }),
  });
  const txt = await res.text();
  if (!res.ok) {
    let msg = 'Login failed';
    try { msg = JSON.parse(txt).detail || msg; } catch {}
    throw new Error(msg);
  }
  return txt ? JSON.parse(txt) : null;
}

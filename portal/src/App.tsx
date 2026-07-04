import React, { useState, useEffect } from 'react';
import { isLoggedIn, clearToken, setToken } from './api';
import Login from './Login';
import Portal from './Portal';

export default function App() {
  // Admin "View as client": the staff app opens /portal/?imp=<read-only portal token>. We load that
  // client's portal in read-only preview (mutations are blocked server-side) and flag it for the banner.
  const [authed, setAuthed] = useState(() => {
    try {
      const imp = new URLSearchParams(window.location.search).get('imp');
      if (imp) {
        setToken(imp);
        try { sessionStorage.setItem('tnfx_imp', '1'); } catch {}
        window.history.replaceState({}, '', window.location.pathname);
        return true;
      }
    } catch {}
    return isLoggedIn();
  });

  useEffect(() => {
    const onLogout = () => setAuthed(false);
    window.addEventListener('portal_logout', onLogout);
    return () => window.removeEventListener('portal_logout', onLogout);
  }, []);

  const exit = () => { clearToken(); try { sessionStorage.removeItem('tnfx_imp'); } catch {} setAuthed(false); };
  if (!authed) return <Login onLogin={() => setAuthed(true)} />;
  return <Portal onLogout={exit} />;
}

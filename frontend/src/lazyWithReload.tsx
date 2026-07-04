import React from 'react';

/**
 * React.lazy that survives a deploy. When the app is code-split, a browser still running
 * an OLD index.html/main.js will try to import chunk hashes that the latest build deleted
 * → "ChunkLoadError" / "Failed to fetch dynamically imported module". Plain React.lazy lets
 * that error bubble uncaught and React unmounts the whole tree → BLANK SCREEN.
 *
 * lazyWithReload catches that import failure and forces ONE full reload, which (thanks to the
 * nginx `Cache-Control: no-cache` on index.html) pulls the fresh index + current chunk hashes.
 * A sessionStorage timestamp guards against an infinite reload loop if the chunk is genuinely
 * gone for another reason.
 */
export function lazyWithReload<T extends React.ComponentType<any>>(
  factory: () => Promise<{ default: T }>
) {
  return React.lazy(async () => {
    try {
      return await factory();
    } catch (err: any) {
      const KEY = 'chunkReloadAt';
      const last = Number(sessionStorage.getItem(KEY) || '0');
      // only auto-reload if we haven't just done so (avoid loops)
      if (Date.now() - last > 10000) {
        sessionStorage.setItem(KEY, String(Date.now()));
        window.location.reload();
        // hang until the reload takes over so Suspense keeps showing the fallback
        return await new Promise<{ default: T }>(() => {});
      }
      throw err;
    }
  });
}

/**
 * Backstop so a chunk/render error in one lazy page can never blank the entire app again.
 * Shows a small recover panel instead of an empty document.
 */
export class ChunkErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { failed: boolean; detail: string }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { failed: false, detail: '' };
  }
  static getDerivedStateFromError(error: any) {
    const msg = String((error && (error.message || error)) || 'Unknown error');
    const frame = String((error && error.stack) || '').split('\n')[1] || '';
    return { failed: true, detail: (msg + '  ' + frame).slice(0, 300) };
  }
  componentDidCatch(error: any, info: any) {
    const msg = String(error && (error.message || error));
    // report the REAL error to the server so we can see it without a screenshot
    try {
      fetch('/api/client-error', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          page: (document.querySelector('h1,h2')?.textContent || window.location.pathname).slice(0, 80),
          role: localStorage.getItem('userRole') || '',
          message: msg,
          stack: String((error && error.stack) || '') + '\n--- component ---' + String((info && info.componentStack) || ''),
        }),
        keepalive: true,
      }).catch(() => {});
    } catch {}
    // a stale-deploy chunk error → just reload to the fresh build (once)
    if (/ChunkLoadError|dynamically imported module|Loading chunk|Importing a module script failed/i.test(msg)) {
      const KEY = 'chunkReloadAt';
      const last = Number(sessionStorage.getItem(KEY) || '0');
      if (Date.now() - last > 10000) {
        sessionStorage.setItem(KEY, String(Date.now()));
        window.location.reload();
      }
    }
  }
  render() {
    if (this.state.failed) {
      return (
        <div style={{ minHeight: '60vh', display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center', gap: 12, padding: 24, textAlign: 'center',
          color: 'var(--text2,#888)', background: 'var(--bg,#0b0e14)' }}>
          <div>Something went wrong loading this page.</div>
          {this.state.detail && (
            <code style={{ fontSize: 12, color: '#ff8a8a', maxWidth: 720, wordBreak: 'break-word',
              background: 'rgba(255,80,80,0.08)', padding: '8px 12px', borderRadius: 8 }}>
              {this.state.detail}
            </code>
          )}
          <button onClick={() => { sessionStorage.removeItem('chunkReloadAt'); window.location.reload(); }}
            style={{ padding: '8px 18px', borderRadius: 8, border: '1px solid #444',
              background: '#1c64f2', color: '#fff', cursor: 'pointer' }}>
            Reload
          </button>
        </div>
      );
    }
    return this.props.children as React.ReactElement;
  }
}

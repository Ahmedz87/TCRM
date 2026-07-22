/* partner-sw.js — minimal service worker for the TNFX Partners PWA (partner1 only).
   Network-FIRST so the app is never stale; caches only the shell for offline fallback.
   Also handles Web Push (payout/challenge/new-FTD) when a subscription exists. */
const SHELL = 'tnfx-partners-shell-v1';

self.addEventListener('install', (e) => { self.skipWaiting(); });
self.addEventListener('activate', (e) => { e.waitUntil(self.clients.claim()); });

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET' || !req.url.startsWith(self.location.origin)) return;
  // never cache the API — always live
  if (req.url.includes('/api/')) return;
  e.respondWith(
    fetch(req)
      .then((res) => {
        // cache the navigation shell for offline
        if (req.mode === 'navigate') {
          const copy = res.clone();
          caches.open(SHELL).then((c) => c.put('/', copy)).catch(() => {});
        }
        return res;
      })
      .catch(() => caches.match(req).then((m) => m || caches.match('/')))
  );
});

// Web Push — show the notification the backend sent
self.addEventListener('push', (e) => {
  let data = { title: 'TNFX Partners', body: '' };
  try { data = e.data.json(); } catch (_) { if (e.data) data.body = e.data.text(); }
  e.waitUntil(self.registration.showNotification(data.title || 'TNFX Partners', {
    body: data.body || '', icon: '/logo192.png', badge: '/logo192.png', data: data.url || '/',
  }));
});
self.addEventListener('notificationclick', (e) => {
  e.notification.close();
  e.waitUntil(self.clients.openWindow(e.notification.data || '/'));
});

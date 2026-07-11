// CEOBurada service worker — sadece push bildirimi + tıklama.
// fetch olayını DİNLEMEZ; normal sayfa yüklemesine karışmaz.

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()));

self.addEventListener('push', (e) => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; }
  catch (_) { d = { govde: e.data ? e.data.text() : '' }; }
  const baslik = d.baslik || 'CEOBurada';
  const opts = {
    body: d.govde || '',
    icon: '/icon-192.png',
    badge: '/icon-192.png',
    tag: d.tag || undefined,
    data: { url: d.url || 'https://ceoburada.com/' },
  };
  e.waitUntil(self.registration.showNotification(baslik, opts));
});

self.addEventListener('notificationclick', (e) => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || 'https://ceoburada.com/';
  e.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((list) => {
      for (const c of list) {
        if ('focus' in c) { c.navigate && c.navigate(url); return c.focus(); }
      }
      return self.clients.openWindow ? self.clients.openWindow(url) : null;
    })
  );
});

const CACHE = 'poi-alert-v2';
const PRECACHE = ['/static/index.html', '/static/manifest.json', '/static/icon-192.png'];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE)
      .then(c => c.addAll(PRECACHE))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  if (e.request.url.includes('/api/')) return;
  e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
});

// ── Push notification handler ──────────────────────────────────────────────
self.addEventListener('push', e => {
  const data = e.data?.json() || {};
  const title = data.notification?.title || '🚨 POI ALERT!';
  const body  = data.notification?.body  || 'Price touched your level!';

  const show = self.registration.showNotification(title, {
    body,
    icon:             '/static/icon-192.png',
    badge:            '/static/icon-192.png',
    vibrate:          [500, 200, 500, 200, 500],
    requireInteraction: true,
    tag:              'poi-alert',
    renotify:         true,
  });

  // Repeat every 30s for 5 mins
  let count = 0;
  const repeat = setInterval(() => {
    count++;
    if (count >= 9) { clearInterval(repeat); return; }
    self.registration.showNotification(`🚨 POI ALERT! (${count+1}/10)`, {
      body,
      icon:             '/static/icon-192.png',
      vibrate:          [500, 200, 500],
      requireInteraction: true,
      tag:              'poi-alert-' + count,
      renotify:         true,
    });
  }, 30000);

  e.waitUntil(show);
});

// ── Notification click ─────────────────────────────────────────────────────
self.addEventListener('notificationclick', e => {
  e.notification.close();
  e.waitUntil(
    clients.matchAll({ type: 'window' }).then(list => {
      if (list.length > 0) return list[0].focus();
      return clients.openWindow('/');
    })
  );
});

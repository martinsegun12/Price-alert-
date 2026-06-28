// Service Worker for POI Alert PWA
const CACHE = 'poi-alert-v1';

// Files to cache for offline
const PRECACHE = ['/static/index.html', '/static/manifest.json'];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(PRECACHE)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

// Fetch — network first, cache fallback
self.addEventListener('fetch', e => {
  if (e.request.url.includes('/api/')) return; // Never cache API calls
  e.respondWith(
    fetch(e.request).catch(() => caches.match(e.request))
  );
});

// Firebase push notification handler
self.addEventListener('push', e => {
  const data = e.data?.json() || {};
  const title = data.notification?.title || '🚨 POI ALERT!';
  const body  = data.notification?.body  || 'Price touched your level!';

  e.waitUntil(
    self.registration.showNotification(title, {
      body,
      icon: '/static/icon-192.png',
      badge: '/static/icon-192.png',
      vibrate: [300, 100, 300, 100, 300],
      requireInteraction: true,   // stays on screen until dismissed
      tag: 'poi-alert',
      renotify: true,
      actions: [{ action: 'open', title: '📈 Open App' }]
    })
  );

  // Re-notify every 30s for 5 minutes (10 times)
  let count = 0;
  const repeat = setInterval(() => {
    count++;
    if (count >= 9) { clearInterval(repeat); return; }
    self.registration.showNotification(`🚨 POI ALERT! (${count+1}/10)`, {
      body,
      icon: '/static/icon-192.png',
      vibrate: [300, 100, 300],
      requireInteraction: true,
      tag: 'poi-alert-' + count,
      renotify: true,
    });
  }, 30000);
});

// Notification click — open app
self.addEventListener('notificationclick', e => {
  e.notification.close();
  e.waitUntil(
    clients.matchAll({ type: 'window' }).then(list => {
      if (list.length > 0) return list[0].focus();
      return clients.openWindow('/');
    })
  );
});

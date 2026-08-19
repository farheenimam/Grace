const CACHE = 'grace-v4';
const STATIC = ['./', './index.html', './css/app.css', './js/app.js', './manifest.json'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(STATIC)));
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys =>
    Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
  ));
  self.clients.claim();
});

self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return; // e.g. Supabase subscribe POST — let it pass through uncached

  const url = new URL(e.request.url);
  if (url.hostname.endsWith('.supabase.co')) {
    e.respondWith(fetch(e.request).catch(() =>
      new Response('[]', { headers: { 'Content-Type': 'application/json' } })
    ));
    return;
  }
  e.respondWith(
    caches.match(e.request).then(cached => cached || fetch(e.request).then(res => {
      const clone = res.clone();
      caches.open(CACHE).then(c => c.put(e.request, clone));
      return res;
    }))
  );
});

self.addEventListener('push', e => {
  const data = e.data?.json() || {};
  e.waitUntil(self.registration.showNotification(data.title || '🚀 New Hackathon!', {
    body: data.body || 'A new hackathon was just announced.',
    icon: 'icons/icon-192.png',
    badge: 'icons/icon-192.png',
    data: { url: data.url || './' },
    actions: [{ action: 'open', title: 'View' }, { action: 'dismiss', title: 'Dismiss' }]
  }));
});

self.addEventListener('notificationclick', e => {
  e.notification.close();
  if (e.action !== 'dismiss') {
    e.waitUntil(clients.openWindow(e.notification.data?.url || './'));
  }
});

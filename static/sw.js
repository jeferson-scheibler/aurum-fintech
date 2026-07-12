const CACHE_NAME = 'bagual-static-v1';
const STATIC_ASSETS = [
  '/static/img/logo-bagual.png',
  '/static/img/icon-192.png',
  '/static/img/icon-512.png',
  '/static/favicon.png',
  '/static/manifest.json',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);
  const isStaticAsset = STATIC_ASSETS.some((path) => url.pathname === path);

  if (isStaticAsset) {
    event.respondWith(
      caches.match(request).then((cached) => cached || fetch(request))
    );
    return;
  }

  // Páginas e dados: sempre buscar da rede, nunca servir do cache
  // (dados financeiros não podem ficar desatualizados).
  event.respondWith(fetch(request));
});

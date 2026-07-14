const CACHE_NAME = 'finflow-v2'

// Install
self.addEventListener('install', event => {
  self.skipWaiting()
})

// Activate: clean old caches
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.map(k => caches.delete(k)))
    )
  )
  self.clients.claim()
})

// Fetch: network first for everything
self.addEventListener('fetch', event => {
  const { request } = event
  const url = new URL(request.url)

  // API requests: network only
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(fetch(request))
    return
  }

  // Static: network first, fallback to cache
  event.respondWith(
    fetch(request).then(response => {
      if (response.ok) {
        const clone = response.clone()
        caches.open(CACHE_NAME).then(cache => cache.put(request, clone))
      }
      return response
    }).catch(() => caches.match(request))
  )
})

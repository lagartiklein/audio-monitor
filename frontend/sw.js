/**
 * Fichatech Audio Control - Service Worker
 * PWA con estrategia Network-First para contenido dinámico
 * y Cache-First para assets estáticos
 */

const CACHE_NAME = 'fichatech-audio-v1';
const DYNAMIC_CACHE = 'fichatech-dynamic-v1';

// Assets estáticos que se cachean en la instalación
const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/styles.css',
  '/manifest.json',
  '/assets/icon.png',
  '/assets/icon-72.png',
  '/assets/icon-96.png',
  '/assets/icon-128.png',
  '/assets/icon-144.png',
  '/assets/icon-152.png',
  '/assets/icon-192.png',
  '/assets/icon-384.png',
  '/assets/icon-512.png'
];

// CDN resources (socket.io)
const CDN_ASSETS = [
  'https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.5.4/socket.io.min.js'
];

/**
 * Instalación del Service Worker
 * Cachea todos los assets estáticos
 */
self.addEventListener('install', (event) => {
  console.log('[SW] Installing Fichatech Service Worker...');
  
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => {
        console.log('[SW] Caching static assets');
        // Cachear assets estáticos (ignorar errores de assets que no existan aún)
        return Promise.allSettled([
          ...STATIC_ASSETS.map(url => cache.add(url).catch(() => console.log(`[SW] Asset not found: ${url}`))),
          ...CDN_ASSETS.map(url => cache.add(url).catch(() => console.log(`[SW] CDN asset failed: ${url}`)))
        ]);
      })
      .then(() => {
        console.log('[SW] Installation complete');
        return self.skipWaiting(); // Activar inmediatamente
      })
  );
});

/**
 * Activación del Service Worker
 * Limpia caches antiguos
 */
self.addEventListener('activate', (event) => {
  console.log('[SW] Activating Fichatech Service Worker...');
  
  event.waitUntil(
    caches.keys()
      .then((cacheNames) => {
        return Promise.all(
          cacheNames
            .filter((name) => name !== CACHE_NAME && name !== DYNAMIC_CACHE)
            .map((name) => {
              console.log(`[SW] Deleting old cache: ${name}`);
              return caches.delete(name);
            })
        );
      })
      .then(() => {
        console.log('[SW] Activation complete');
        return self.clients.claim(); // Tomar control inmediatamente
      })
  );
});

/**
 * Interceptar requests
 * - WebSocket: pasar directamente (no cacheable)
 * - API/Socket.io: Network-only (tiempo real)
 * - Assets estáticos: Cache-first con fallback a network
 * - HTML: Network-first con fallback a cache
 */
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);
  
  // ⚠️ Ignorar WebSocket y Socket.io (tiempo real, no cacheable)
  if (
    request.url.includes('/socket.io/') ||
    request.url.includes('ws://') ||
    request.url.includes('wss://') ||
    request.headers.get('Upgrade') === 'websocket'
  ) {
    return; // No interceptar, dejar pasar
  }
  
  // ⚠️ Ignorar requests de extensiones de Chrome
  if (url.protocol === 'chrome-extension:') {
    return;
  }
  
  // Assets de CDN: Cache-first
  if (CDN_ASSETS.some(cdn => request.url.includes(cdn))) {
    event.respondWith(cacheFirst(request));
    return;
  }
  
  // Assets estáticos (imágenes, CSS, JS): Cache-first
  if (
    request.destination === 'image' ||
    request.destination === 'style' ||
    request.destination === 'script' ||
    url.pathname.startsWith('/assets/')
  ) {
    event.respondWith(cacheFirst(request));
    return;
  }
  
  // HTML y navegación: Network-first (para actualizaciones)
  if (request.destination === 'document' || request.mode === 'navigate') {
    event.respondWith(networkFirst(request));
    return;
  }
  
  // Todo lo demás: Network-first
  event.respondWith(networkFirst(request));
});

/**
 * Estrategia Cache-First
 * Ideal para assets estáticos que no cambian frecuentemente
 */
async function cacheFirst(request) {
  try {
    const cached = await caches.match(request);
    if (cached) {
      return cached;
    }
    
    const networkResponse = await fetch(request);
    
    // Cachear respuesta exitosa
    if (networkResponse.ok) {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, networkResponse.clone());
    }
    
    return networkResponse;
  } catch (error) {
    console.log('[SW] Cache-first failed:', error);
    
    // Intentar devolver algo del cache como fallback
    const cached = await caches.match(request);
    if (cached) return cached;
    
    // Fallback para imágenes
    if (request.destination === 'image') {
      return new Response('', { status: 404 });
    }
    
    throw error;
  }
}

/**
 * Estrategia Network-First
 * Ideal para contenido dinámico que puede cambiar
 */
async function networkFirst(request) {
  try {
    const networkResponse = await fetch(request);
    
    // Cachear respuesta exitosa (para offline)
    if (networkResponse.ok) {
      const cache = await caches.open(DYNAMIC_CACHE);
      cache.put(request, networkResponse.clone());
    }
    
    return networkResponse;
  } catch (error) {
    console.log('[SW] Network-first failed, trying cache:', request.url);
    
    // Fallback al cache
    const cached = await caches.match(request);
    if (cached) {
      console.log('[SW] Serving from cache:', request.url);
      return cached;
    }
    
    // Si es navegación, servir index.html cacheado (SPA)
    if (request.mode === 'navigate') {
      const index = await caches.match('/index.html');
      if (index) return index;
    }
    
    // Respuesta de error personalizada
    return new Response(
      JSON.stringify({ error: 'Offline', message: 'No hay conexión a internet' }),
      {
        status: 503,
        headers: { 'Content-Type': 'application/json' }
      }
    );
  }
}

/**
 * Background Sync (opcional, para enviar cambios cuando vuelva la conexión)
 */
self.addEventListener('sync', (event) => {
  console.log('[SW] Background sync:', event.tag);
  
  if (event.tag === 'sync-mixer-state') {
    event.waitUntil(syncMixerState());
  }
});

async function syncMixerState() {
  // Esta función podría enviar estados pendientes al servidor
  // cuando se recupere la conexión
  console.log('[SW] Syncing mixer state...');
}

/**
 * Push notifications (preparado para futuro)
 */
self.addEventListener('push', (event) => {
  if (!event.data) return;
  
  const data = event.data.json();
  
  event.waitUntil(
    self.registration.showNotification(data.title || 'Fichatech', {
      body: data.body || 'Nueva actualización',
      icon: '/assets/icon-192.png',
      badge: '/assets/icon-72.png',
      vibrate: [100, 50, 100],
      data: data.data
    })
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  
  event.waitUntil(
    clients.openWindow('/')
  );
});

console.log('[SW] Fichatech Service Worker loaded');

// ZSocial Service Worker
// Версия обновляется при каждом деплое (cache-busting)
const CACHE_VERSION = 'zsocial-v1';
const APP_SHELL = [
    '/',
    '/feed',
    '/static/css/style.css',
    '/static/js/main.js',
    '/static/manifest.json',
    '/static/img/pwa/icon-192.png',
    '/static/img/pwa/icon-512.png',
    '/static/img/pwa/apple-touch-icon.png',
];

// ===== INSTALL: кэшируем app shell =====
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_VERSION).then((cache) => {
            // addAll падает если хотя бы один ресурс недоступен;
            // используем поштучное добавление с игнорированием ошибок
            return Promise.all(
                APP_SHELL.map((url) =>
                    cache.add(url).catch(() => null)
                )
            );
        }).then(() => self.skipWaiting())
    );
});

// ===== ACTIVATE: чистим старые кэши =====
self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) =>
            Promise.all(
                keys
                    .filter((k) => k !== CACHE_VERSION)
                    .map((k) => caches.delete(k))
            )
        ).then(() => self.clients.claim())
    );
});

// ===== FETCH: стратегии кэширования =====
self.addEventListener('fetch', (event) => {
    const req = event.request;
    // Игнорируем не-GET (POST/PUT/Delete) — их кэшировать нельзя
    if (req.method !== 'GET') return;

    const url = new URL(req.url);

    // Socket.IO запросы — всегда в сеть, без кэширования
    if (url.pathname.startsWith('/socket.io/')) return;

    // API запросы (JSON) — network-first, fallback на кэш
    if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/push/')) {
        event.respondWith(networkFirst(req));
        return;
    }

    // Статика (CSS, JS, img) — cache-first, затем сеть
    if (url.pathname.startsWith('/static/')) {
        event.respondWith(cacheFirst(req));
        return;
    }

    // Страницы SPA — network-first, fallback на закэшированную страницу
    // Навигационные запросы (document) всегда идут в сеть первой
    if (req.mode === 'navigate' || (req.headers.get('accept') || '').includes('text/html')) {
        event.respondWith(networkFirstPage(req));
        return;
    }

    // Загруженные медиа (uploads) — stale-while-revalidate
    if (url.pathname.startsWith('/uploads/')) {
        event.respondWith(staleWhileRevalidate(req));
        return;
    }

    // Всё остальное — пробуем сеть, fallback на кэш
    event.respondWith(fetch(req).catch(() => caches.match(req)));
});

// ===== Стратегии =====

// Cache-first: статику отдаём из кэша мгновенно, фоном обновляем
async function cacheFirst(req) {
    const cached = await caches.match(req);
    if (cached) {
        // Фоном обновляем кэш
        fetch(req).then((res) => {
            if (res && res.status === 200) {
                caches.open(CACHE_VERSION).then((c) => c.put(req, res.clone()));
            }
        }).catch(() => {});
        return cached;
    }
    try {
        const res = await fetch(req);
        if (res && res.status === 200) {
            const cache = await caches.open(CACHE_VERSION);
            cache.put(req, res.clone());
        }
        return res;
    } catch (e) {
        return new Response('', { status: 504 });
    }
}

// Network-first: API — всегда свежие данные, если сеть недоступна — кэш
async function networkFirst(req) {
    try {
        const res = await fetch(req);
        if (res && res.status === 200) {
            const cache = await caches.open(CACHE_VERSION);
            cache.put(req, res.clone());
        }
        return res;
    } catch (e) {
        const cached = await caches.match(req);
        return cached || new Response(
            JSON.stringify({ error: 'Офлайн' }),
            { status: 503, headers: { 'Content-Type': 'application/json' } }
        );
    }
}

// Network-first для страниц: fallback на кэшированную '/'
async function networkFirstPage(req) {
    try {
        const res = await fetch(req);
        if (res && res.status === 200 && res.type === 'basic') {
            const cache = await caches.open(CACHE_VERSION);
            cache.put(req, res.clone());
        }
        return res;
    } catch (e) {
        // SPA: отдаём закэшированную страницу, браузер сам разберётся с роутингом
        const cached = await caches.match(req);
        if (cached) return cached;
        // Фолбэк на корень (app shell)
        const fallback = await caches.match('/');
        if (fallback) return fallback;
        return new Response('Офлайн режим. Подключение отсутствует.', {
            status: 503,
            headers: { 'Content-Type': 'text/html; charset=utf-8' }
        });
    }
}

// Stale-while-revalidate: медиа — отдаём кэш, фоном обновляем
async function staleWhileRevalidate(req) {
    const cache = await caches.open(CACHE_VERSION);
    const cached = await cache.match(req);
    const fetchPromise = fetch(req).then((res) => {
        if (res && res.status === 200) {
            cache.put(req, res.clone());
        }
        return res;
    }).catch(() => cached);
    return cached || fetchPromise;
}

// ===== Push-уведомления (подготовка для этапа 3b) =====
self.addEventListener('push', (event) => {
    let data = { title: 'ZSocial', body: 'Новое уведомление', url: '/feed' };
    try {
        if (event.data) data = event.data.json();
    } catch (e) {
        try { data.body = event.data.text(); } catch (_) {}
    }
    const options = {
        body: data.body,
        icon: '/static/img/pwa/icon-192.png',
        badge: '/static/img/pwa/icon-96.png',
        vibrate: [100, 50, 100],
        data: { url: data.url || '/feed' },
        tag: data.tag || 'zsocial-notification',
        renotify: true,
    };
    event.waitUntil(self.registration.showNotification(data.title, options));
});

// Клик по уведомлению — открываем/фокусируем вкладку и переходим по URL
self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    const targetUrl = (event.notification.data && event.notification.data.url) || '/feed';
    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
            // Если уже есть открытая вкладка — фокусируем и навигируем
            for (const client of clientList) {
                if (client.url.includes(self.location.origin)) {
                    client.focus();
                    if ('navigate' in client) {
                        client.navigate(targetUrl);
                    } else {
                        client.postMessage({ type: 'SPA_NAVIGATE', url: targetUrl });
                    }
                    return;
                }
            }
            // Иначе открываем новую
            if (clients.openWindow) return clients.openWindow(targetUrl);
        })
    );
});

// Message от клиента (например, для пропуска ожидания)
self.addEventListener('message', (event) => {
    if (event.data === 'SKIP_WAITING') self.skipWaiting();
});

/* Service worker: cache the app shell so the PWA launches instantly and
 * survives brief offline moments. The WebSocket (live audio) is never cached. */
const CACHE = "xiaozhi-live-v2";
const ASSETS = [
  "./",
  "index.html",
  "styles.css",
  "app.js",
  "ogg.js",
  "manifest.webmanifest",
  "vendor/recorder.min.js",
  "vendor/encoderWorker.min.js",
  "vendor/opus-decoder.min.js",
  "icons/icon-192.png",
  "icons/icon-512.png",
  "icons/apple-touch-icon.png",
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(ASSETS)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (url.pathname.endsWith("/xiaozhi_live/ws")) return; // never intercept the WS
  if (e.request.method !== "GET") return;
  e.respondWith(
    caches.match(e.request).then((hit) => hit || fetch(e.request).then((res) => {
      if (res.ok && url.origin === location.origin) {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(e.request, copy));
      }
      return res;
    }).catch(() => caches.match("index.html")))
  );
});

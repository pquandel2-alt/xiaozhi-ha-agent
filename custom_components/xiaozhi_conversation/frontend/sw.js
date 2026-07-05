/* Kill switch. Earlier versions cache-first'd the app shell, which made
 * every subsequent fix invisible to already-installed devices — they kept
 * serving whatever was cached the first time, regardless of what shipped
 * later. iOS's "Add to Home Screen" doesn't require a service worker at
 * all, so remove it entirely: wipe every cache, unregister, and reload any
 * open window so it goes straight to the network from now on. */
self.addEventListener("install", () => self.skipWaiting());

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.map((k) => caches.delete(k))))
      .then(() => self.registration.unregister())
      .then(() => self.clients.matchAll({ type: "window" }))
      .then((clients) => clients.forEach((c) => c.navigate(c.url)))
  );
});

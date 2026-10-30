const CACHE = "prisma-v2";
const PRECACHE = [
  "/offline",
  "/static/css/app.css",
  "/static/js/estudiante.js",
  "/static/js/pwa.js",
  "/static/manifest.json",
  "/static/icon.svg",
];

self.addEventListener("install", function (e) {
  e.waitUntil(
    caches.open(CACHE).then(function (c) {
      return c.addAll(PRECACHE);
    }).then(function () {
      return self.skipWaiting();
    })
  );
});

self.addEventListener("activate", function (e) {
  e.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.filter(function (k) { return k !== CACHE; }).map(function (k) { return caches.delete(k); }));
    }).then(function () {
      return self.clients.claim();
    })
  );
});

self.addEventListener("fetch", function (e) {
  var req = e.request;
  if (req.method !== "GET") return;
  var url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.indexOf("/chat/") === 0 || url.pathname.indexOf("/estudiante/interacciones") === 0) return;
  e.respondWith(
    fetch(req)
      .then(function (res) {
        if (res.ok && (url.pathname.indexOf("/estudiante/") === 0 || url.pathname.indexOf("/static/") === 0 || url.pathname === "/offline")) {
          var copia = res.clone();
          caches.open(CACHE).then(function (c) { c.put(req, copia); });
        }
        return res;
      })
      .catch(function () {
        return caches.match(req).then(function (hit) {
          return hit || caches.match("/offline");
        });
      })
  );
});

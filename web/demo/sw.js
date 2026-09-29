// Service worker of the installable demo: keeps the page, the engine and the model files
// so the demo works offline. Requests go to the network first (the browser's HTTP cache
// makes that a cheap revalidation), and the cache answers when the network can't.
// Plain JavaScript because it is served as is from web/demo/, the scope it controls; the
// site build (web/scripts/build_site.ts) replaces VERSION with the commit, so every deploy
// installs a new worker and drops the old cache.

const VERSION = "dev";
const CACHE = `glyphsketch-${VERSION}`;
// Relative to this file (web/demo/sw.js).
const SHELL = [
  "./",
  "index.html",
  "style.css",
  "favicon.svg",
  "manifest.webmanifest",
  "icons/icon-192.png",
  "../dist/demo/demo.js",
  "../dist/demo/drawingLink.js",
  "../dist/src/index.js",
  "../dist/src/charset.js",
  "../dist/src/glyphIndex.js",
  "../dist/src/model.js",
  "../dist/src/ranking.js",
  "../dist/src/rasterize.js",
  "../dist/src/recognizer.js",
  "../../export/glyphsketch-model.bin",
  "../../export/glyphsketch-index.bin",
  "../../export/glyphsketch-charset.json",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.addAll(SHELL.map((path) => new Request(path, { cache: "reload" }))))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((names) =>
        Promise.all(
          names
            .filter((name) => name.startsWith("glyphsketch-") && name !== CACHE)
            .map((name) => caches.delete(name)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET" || new URL(request.url).origin !== self.location.origin) return;
  event.respondWith(
    fetch(request)
      .then((response) => {
        if (response.ok) {
          const copy = response.clone();
          event.waitUntil(caches.open(CACHE).then((cache) => cache.put(request, copy)));
        }
        return response;
      })
      .catch(() =>
        caches.match(request, { ignoreSearch: true }).then((cached) => cached ?? Response.error()),
      ),
  );
});

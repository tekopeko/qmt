/* QMT service worker — same philosophy as MojiMakrosi's:
 *
 * The app is server-rendered and per-user (bookings, personal programmes), so
 * caching HTML would show stale sessions or another user's data on a shared
 * phone. Therefore:
 *   - NEVER cache HTML or /media (network-only),
 *   - cache only immutable static assets so the installed app has its icon,
 *   - show a small offline notice when navigation fails entirely.
 * Installability + graceful offline message; not offline functionality.
 */
const VERSION = "qmt-v1";
const STATIC = `${VERSION}-static`;
const STATIC_ASSETS = [
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
  "/static/logo.png",
  "/static/manifest.webmanifest",
];

const OFFLINE_HTML = `<!doctype html><html lang="hr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Bez veze — QMT</title>
<style>body{background:#101012;color:#f4f4f2;font-family:system-ui,sans-serif;display:flex;
min-height:100vh;align-items:center;justify-content:center;margin:0;padding:24px;text-align:center}
div{max-width:22rem}h1{font-size:1.2rem;margin:0 0 .5rem}p{color:#9a9aa0;font-size:.9rem;line-height:1.5}
button{margin-top:1rem;background:#e10600;color:#fff;border:0;border-radius:12px;padding:.6rem 1.2rem;
font-weight:600;font-size:.9rem;cursor:pointer}</style></head><body><div>
<h1>Nema internetske veze</h1>
<p>Za raspored i treninge treba veza. Provjeri mrežu pa pokušaj ponovno.</p>
<button onclick="location.reload()">Pokušaj ponovno</button></div></body></html>`;

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(STATIC).then((c) => c.addAll(STATIC_ASSETS)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== STATIC).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;

  // navigations: network-only, offline notice as the last resort
  if (e.request.mode === "navigate") {
    e.respondWith(fetch(e.request).catch(() =>
      new Response(OFFLINE_HTML, { headers: { "Content-Type": "text/html; charset=utf-8" } })));
    return;
  }
  // immutable statics: cache-first (personal /media stays network-only on purpose)
  if (url.pathname.startsWith("/static/")) {
    e.respondWith(caches.match(e.request).then((hit) => hit || fetch(e.request).then((resp) => {
      const copy = resp.clone();
      caches.open(STATIC).then((c) => c.put(e.request, copy));
      return resp;
    })));
  }
});

// Caché de solo lectura para acceder al último plan visto cuando el ordenador está apagado.
// Solo se registra tras autenticarse; un 401/403 o la pantalla de login borran toda la caché.

const CACHE = "unificador-v2";
const SHELL = [
  "./",
  "./index.html",
  "./app.css",
  "./decide.css",
  "./app.js",
  "./util.js",
  "./plan.js",
  "./decide.js",
  "./icons.js",
  "./audit.js",
  "./manifest.webmanifest",
  "./icon.svg",
  "./icon-192.png",
  "./icon-512.png",
  "./icon-maskable-512.png",
];

async function stampResponse(resp) {
  const headers = new Headers(resp.headers);
  headers.set("X-Unificador-Cached-At", new Date().toISOString());
  const buf = await resp.arrayBuffer();
  return new Response(buf, { status: resp.status, statusText: resp.statusText, headers });
}

async function wipeAll() {
  try {
    const keys = await caches.keys();
    await Promise.all(keys.map((k) => caches.delete(k)));
  } catch { /* sin acceso a caches */ }
  try {
    await self.registration.unregister();
  } catch { /* ignorar */ }
}

self.addEventListener("install", (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE);
    for (const path of SHELL) {
      const resp = await fetch(path);
      if (resp.status === 401 || resp.status === 403 || resp.headers.get("X-Unificador-Auth") === "login") {
        throw new Error("Sesión no autorizada");
      }
      if (resp.ok) await cache.put(path, await stampResponse(resp));
    }
    await self.skipWaiting();
  })());
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)));
    await self.clients.claim();
  })());
});

self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "CLEAR_CACHE") {
    event.waitUntil(wipeAll());
  }
});

async function offlineFallback(req, upstreamResp) {
  const cache = await caches.open(CACHE);
  let hit = await cache.match(req);
  if (!hit && req.mode === "navigate") {
    hit = (await cache.match("./index.html")) || (await cache.match("./"));
  }
  if (hit) {
    const headers = new Headers(hit.headers);
    headers.set("X-Unificador-Offline", "1");
    return new Response(await hit.arrayBuffer(), { status: hit.status, statusText: hit.statusText, headers });
  }
  if (upstreamResp) return upstreamResp;
  const url = new URL(req.url);
  if (url.pathname.startsWith("/api/")) {
    return new Response(JSON.stringify({ error: "Sin conexión con tu ordenador." }), {
      status: 503,
      headers: { "Content-Type": "application/json; charset=utf-8" },
    });
  }
  return new Response("Sin conexión con tu ordenador.", {
    status: 503,
    headers: { "Content-Type": "text/plain; charset=utf-8" },
  });
}

async function networkFirst(req) {
  try {
    const resp = await fetch(req);
    if (resp.status === 401 || resp.status === 403 || resp.headers.get("X-Unificador-Auth") === "login") {
      await wipeAll();
      return resp;
    }
    if (resp.status >= 502) {
      return offlineFallback(req, resp);
    }
    if (resp.ok) {
      const cache = await caches.open(CACHE);
      await cache.put(req, await stampResponse(resp.clone()));
    }
    return resp;
  } catch {
    return offlineFallback(req, null);
  }
}

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/auth/") || url.pathname === "/api/events") return;
  event.respondWith(networkFirst(req));
});

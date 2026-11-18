/* VNT Paraná: funcionamiento sin conexión */
const V = "vnt-v2";
// tope de entradas por caché para no llenar el teléfono (la zona guardada a mano va aparte, en "vnt-zona")
const LIM = { "vnt-tiles": 3000, "vnt-datos": 150 };
const puestos = {};
async function recortar(nombre) {
  const c = await caches.open(nombre), ks = await c.keys(), sobra = ks.length - LIM[nombre];
  if (sobra > 0) for (const k of ks.slice(0, sobra + Math.round(LIM[nombre] / 10))) await c.delete(k);
}
function guardar(c, nombre, k, r) {
  return c.put(k, r).then(() => { if (LIM[nombre] && (puestos[nombre] = (puestos[nombre] || 0) + 1) % 40 === 0) return recortar(nombre); }).catch(() => recortar(nombre).catch(() => {}));
}
const SHELL = ["./", "index.html", "manifest.webmanifest", "icon.svg",
  "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js",
  "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css"];
const DATOS = /(^|\.)open-meteo\.com$|^alerta\.ina\.gob\.ar$|^wms\.ign\.gob\.ar$|^raw\.githubusercontent\.com$/;
const TESELAS = /\/gwc\/service\/tms\/|arcgisonline\.com\/ArcGIS\/rest\/services\/World_Imagery/;

self.addEventListener("install", e => {
  e.waitUntil(caches.open(V).then(c => Promise.all(SHELL.map(u => c.add(u).catch(() => {})))));
  self.skipWaiting();
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys()
    .then(ks => Promise.all(ks.filter(k => k.startsWith("vnt-v") && k !== V).map(k => caches.delete(k))))
    .then(() => Promise.all(Object.keys(LIM).map(n => recortar(n).catch(() => {}))))
    .then(() => self.clients.claim()));
});

// clave sin parámetros que cambian en cada consulta (tiempo, versión)
const clave = u => u.replace(/([?&])(t|x|v|timeStart|timeEnd)=[^&]*/g, "$1").replace(/[?&]+$/, "").replace(/&&+/g, "&");

async function redPrimero(req, nombre) {
  const k = clave(req.url), c = await caches.open(nombre);
  try {
    const r = await fetch(req);
    if (r && (r.ok || r.type === "opaque")) guardar(c, nombre, k, r.clone());
    return r;
  } catch (err) {
    let m = await c.match(k);
    if (!m && req.mode === "navigate") {
      const app = await caches.open(V);
      m = await app.match(new URL("./", self.registration.scope).href) || await app.match(new URL("index.html", self.registration.scope).href);
    }
    if (m) return m;
    throw err;
  }
}
async function cachePrimero(req, nombre) {
  const c = await caches.open(nombre), m = await caches.match(req.url);
  if (m) return m;
  const r = await fetch(req);
  if (r && (r.ok || r.type === "opaque")) guardar(c, nombre, req.url, r.clone());
  return r;
}

self.addEventListener("fetch", e => {
  const r = e.request;
  if (r.method !== "GET") return;
  const u = new URL(r.url);
  if (TESELAS.test(r.url)) { e.respondWith(cachePrimero(r, "vnt-tiles")); return; }
  if (u.hostname === "cdnjs.cloudflare.com") { e.respondWith(cachePrimero(r, V)); return; }
  if (u.origin === self.location.origin) { e.respondWith(redPrimero(r, V)); return; }
  if (DATOS.test(u.hostname)) { e.respondWith(redPrimero(r, "vnt-datos")); return; }
});

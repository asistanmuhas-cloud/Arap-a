// Çevrimdışı çalışma: uygulama kabuğu önceden önbelleğe alınır; arka plan modeli ilk kullanımda önbelleğe girer.
const SURUM = "gardrop-v1";
const KABUK = [
  "./", "index.html", "manifest.webmanifest", "ikon.svg", "ikon-192.png", "css/app.css",
  "js/app.js", "js/veri.js", "js/ui.js", "js/durum.js", "js/sabitler.js", "js/renk.js", "js/oneri.js", "js/analiz.js",
  "js/gorsel.js", "js/hava.js", "js/yedek.js", "js/senkron.js",
  "js/gorunum/bugun.js", "js/gorunum/gardrop.js", "js/gorunum/parca.js", "js/gorunum/parca-form.js", "js/gorunum/ekle.js",
  "js/gorunum/kombinler.js", "js/gorunum/kombin.js", "js/gorunum/kombin-kur.js", "js/gorunum/oneri-kart.js",
  "js/gorunum/takvim.js", "js/gorunum/analiz.js", "js/gorunum/daha.js", "js/gorunum/alisveris.js",
  "js/gorunum/seyahat.js", "js/gorunum/kapsul.js", "js/gorunum/ayarlar.js",
  "vendor/arka-plan.js",
];
const MODEL = "gardrop-model-v1";

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(SURUM).then((c) => c.addAll(KABUK)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((l) => Promise.all(l.filter((k) => k !== SURUM && k !== MODEL).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", (e) => {
  const u = new URL(e.request.url);
  if (e.request.method !== "GET") return;
  // Arka plan modeli ve wasm dosyaları: değişmez, önbellekten.
  if (u.hostname === "staticimgly.com" || u.pathname.includes("/vendor/arka-plan-veri/")) {
    e.respondWith(caches.open(MODEL).then(async (c) => (await c.match(e.request)) || fetch(e.request).then((r) => { if (r.ok) c.put(e.request, r.clone()).catch(() => {}); return r; })));
    return;
  }
  if (u.origin !== location.origin) return; // hava, Supabase: doğrudan ağ
  // Kabuk: önce ağ (güncel sürüm), çevrimdışıysa önbellek.
  e.respondWith(
    fetch(e.request).then((r) => {
      if (r.ok) { const kopya = r.clone(); caches.open(SURUM).then((c) => c.put(e.request, kopya)); }
      return r;
    }).catch(() => caches.match(e.request, { ignoreSearch: true }).then((r) => r || caches.match("index.html")))
  );
});

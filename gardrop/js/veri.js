// IndexedDB katmanı. Her kayıt: id (istemci UUID), profil, olusturma, guncelleme (ISO), silindi (bool).
// Silme yumuşaktır (silindi=true), böylece bulut senkronu silmeleri de taşıyabilir. Görseller ayrı depoda blob olarak.

const AD = "gardrop";
const SURUM = 1;
export const DEPOLAR = ["profiller", "parcalar", "kombinler", "plan", "giyim", "istek", "seyahat"];
let dbVaadi = null;
const dinleyiciler = new Set();

export function uuid() {
  if (globalThis.crypto?.randomUUID) return crypto.randomUUID();
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === "x" ? r : (r & 3) | 8).toString(16);
  });
}
export const simdi = () => new Date().toISOString();

function ac() {
  if (dbVaadi) return dbVaadi;
  dbVaadi = new Promise((coz, red) => {
    const istek = indexedDB.open(AD, SURUM);
    istek.onupgradeneeded = () => {
      const db = istek.result;
      for (const d of DEPOLAR) {
        if (!db.objectStoreNames.contains(d)) {
          const s = db.createObjectStore(d, { keyPath: "id" });
          s.createIndex("profil", "profil");
        }
      }
      if (!db.objectStoreNames.contains("gorseller")) db.createObjectStore("gorseller", { keyPath: "id" });
      if (!db.objectStoreNames.contains("ayarlar")) db.createObjectStore("ayarlar", { keyPath: "anahtar" });
    };
    istek.onsuccess = () => coz(istek.result);
    istek.onerror = () => red(istek.error);
  });
  return dbVaadi;
}

function islem(depo, kip, fn) {
  return ac().then(
    (db) =>
      new Promise((coz, red) => {
        const tx = db.transaction(depo, kip);
        let sonuc;
        Promise.resolve(fn(tx.objectStore(depo), tx)).then((s) => (sonuc = s));
        tx.oncomplete = () => coz(sonuc);
        tx.onerror = () => red(tx.error);
        tx.onabort = () => red(tx.error);
      })
  );
}
const iste = (r) => new Promise((coz, red) => ((r.onsuccess = () => coz(r.result)), (r.onerror = () => red(r.error))));

export function degisinceDinle(fn) {
  dinleyiciler.add(fn);
  return () => dinleyiciler.delete(fn);
}
function bildir(depo, kayit) {
  for (const fn of dinleyiciler) {
    try { fn(depo, kayit); } catch (e) { console.error(e); }
  }
}

// --- ayarlar (profil bağımsız) ---
export async function ayarOku(anahtar, varsayilan = null) {
  const k = await islem("ayarlar", "readonly", (s) => iste(s.get(anahtar)));
  return k ? k.deger : varsayilan;
}
export function ayarYaz(anahtar, deger) {
  return islem("ayarlar", "readwrite", (s) => s.put({ anahtar, deger }));
}

// --- aktif profil ---
let aktifProfil = null;
export const profil = () => aktifProfil;
export function profilSec(id) {
  aktifProfil = id;
  return ayarYaz("aktifProfil", id);
}

// --- kayıtlar ---
export async function hepsi(depo, { silinenler = false, tumProfiller = false } = {}) {
  const liste = await islem(depo, "readonly", (s) =>
    tumProfiller || depo === "profiller" ? iste(s.getAll()) : iste(s.index("profil").getAll(aktifProfil))
  );
  return silinenler ? liste : liste.filter((k) => !k.silindi);
}
export async function getir(depo, id) {
  const k = await islem(depo, "readonly", (s) => iste(s.get(id)));
  return k && !k.silindi ? k : null;
}
export async function kaydet(depo, veri) {
  const z = simdi();
  const kayit = { silindi: false, olusturma: z, ...veri, guncelleme: z };
  if (!kayit.id) kayit.id = uuid();
  if (depo !== "profiller" && !kayit.profil) kayit.profil = aktifProfil;
  await islem(depo, "readwrite", (s) => s.put(kayit));
  bildir(depo, kayit);
  return kayit;
}
export async function guncelle(depo, id, degisiklik) {
  const eski = await islem(depo, "readonly", (s) => iste(s.get(id)));
  if (!eski) throw new Error("Kayıt bulunamadı");
  return kaydet(depo, { ...eski, ...degisiklik, id });
}
export async function sil(depo, id) {
  return guncelle(depo, id, { silindi: true });
}
// Senkron ve yedekten içe aktarma: guncelleme alanına dokunmadan yazar; daha yeni olan kazanır.
// Kimlikler HTML özniteliklerine ve linklere girer; yedek dosyası ya da bulut dışarıdan geldiği için biçim denetlenir.
const GECERLI_ID = /^[A-Za-z0-9_-]{1,64}$/;
export const gecerliKayit = (k, depo = "") => !!k && typeof k === "object" && GECERLI_ID.test(k.id) && (k.profil == null || GECERLI_ID.test(k.profil)) && (k.gorsel == null || GECERLI_ID.test(k.gorsel)) &&
  (depo !== "profiller" || k.renk == null || /^#[0-9a-f]{3,8}$/i.test(k.renk));
export async function hamYaz(depo, kayitlar) {
  let yazilan = 0;
  kayitlar = kayitlar.filter((k) => gecerliKayit(k, depo));
  await islem(depo, "readwrite", async (s) => {
    for (const k of kayitlar) {
      const eski = await iste(s.get(k.id));
      if (!eski || (eski.guncelleme || "") < (k.guncelleme || "")) {
        s.put(k);
        yazilan++;
      }
    }
  });
  if (yazilan) bildir(depo, null);
  return yazilan;
}

// --- görseller ---
// {id, blob, kucuk (blob), tur} — kucuk: liste için ~320 px.
export function gorselYaz(g) {
  const kayit = { guncelleme: simdi(), ...g, id: g.id || uuid() };
  return islem("gorseller", "readwrite", (s) => s.put(kayit)).then(() => kayit.id);
}
export function gorselOku(id) {
  if (!id) return Promise.resolve(null);
  return islem("gorseller", "readonly", (s) => iste(s.get(id)));
}
export function gorselSil(id) {
  return islem("gorseller", "readwrite", (s) => s.delete(id));
}
export function tumGorseller() {
  return islem("gorseller", "readonly", (s) => iste(s.getAll()));
}

const urlOnbellek = new Map();
// Liste görüntüsü için object URL; aynı görsel için tekrar oluşturmaz.
export async function gorselUrl(id, { kucuk = true } = {}) {
  if (!id) return null;
  const anahtar = id + (kucuk ? ":k" : ":b");
  if (urlOnbellek.has(anahtar)) return urlOnbellek.get(anahtar);
  const g = await gorselOku(id);
  if (!g) return null;
  const blob = (kucuk && g.kucuk) || g.blob;
  const url = URL.createObjectURL(blob);
  urlOnbellek.set(anahtar, url);
  return url;
}

// Yeni cihazda otomatik açılan boş profil yerine dışarıdan gelen (yedek/bulut) profile geç.
export async function bosProfildenGec() {
  const profiller = await hepsi("profiller");
  const simdiki = profiller.find((p) => p.id === aktifProfil);
  const diger = profiller.filter((p) => p.id !== aktifProfil);
  if (!simdiki || !diger.length) return false;
  for (const d of DEPOLAR) if (d !== "profiller" && (await hepsi(d)).length) return false;
  await sil("profiller", simdiki.id);
  await profilSec(diger[0].id);
  return true;
}

// --- başlangıç: profil yoksa oluştur ---
export async function baslat() {
  try { await navigator.storage?.persist?.(); } catch {}
  let profiller = await hepsi("profiller");
  if (!profiller.length) {
    const p = await kaydet("profiller", { ad: "Ben", renk: "#3b5bdb" });
    profiller = [p];
  }
  const kayitli = await ayarOku("aktifProfil");
  aktifProfil = profiller.find((p) => p.id === kayitli)?.id || profiller[0].id;
  return { profiller, aktif: aktifProfil };
}

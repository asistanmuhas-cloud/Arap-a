// Kombin üretimi: K3 (karıştır), K4 (kurallı öneri), K7 (kapsül sayımı), S3 (almadan önce test). Saf fonksiyonlar.
import { KATEGORI, DURUM } from "./sabitler.js";
import { renkUyumu } from "./renk.js";

export function mevsimBul(tarih = new Date()) {
  const a = tarih.getMonth() + 1;
  return a >= 3 && a <= 5 ? "ilkbahar" : a <= 8 && a >= 6 ? "yaz" : a >= 9 && a <= 11 ? "sonbahar" : "kis";
}
export const rolu = (p) => KATEGORI[p.kategori]?.rol || "diger";
export const hazirMi = (p) => !p.arsiv && (DURUM[p.durum || "temiz"]?.hazir ?? true);

// Parçanın verilen sıcaklığa (°C) uygunluğu: 1 uygun, 0.3 uygunsuz. Alt kategori ve kumaştan kaba bir kural.
const SICAK_ICIN = new Set(["Şort", "Atlet", "Sandalet", "Terlik", "Mayo"]);
const SOGUK_ICIN = { "Kazak": 17, "Kaban": 12, "Mont": 14, "Bot": 15, "Atkı / şal": 12, "Hırka": 20, "Sweatshirt": 22, "Yelek": 20 };
const SOGUK_KUMAS = { "Yün": 16, "Kaşmir": 16, "Polar": 15, "Triko": 18 };
export function sicaklikUygun(p, t) {
  if (t == null) return 1;
  if (SICAK_ICIN.has(p.altKategori) && t < 20) return 0.3;
  if (p.kumas === "Keten" && t < 17) return 0.5;
  const ust = Math.min(SOGUK_ICIN[p.altKategori] ?? 99, SOGUK_KUMAS[p.kumas] ?? 99);
  if (t > ust + 4) return 0.3;
  return 1;
}
export function disGerekli(t, mevsim) {
  return t != null ? t < 16 : mevsim === "kis";
}

function uygunParcalar(parcalar, { ortam, mevsim, sicaklik }) {
  return parcalar.filter((p) => {
    if (!hazirMi(p)) return false;
    if (mevsim && p.mevsimler?.length && !p.mevsimler.includes(mevsim)) return false;
    if (ortam && p.ortamlar?.length && !p.ortamlar.includes(ortam)) return false;
    if (sicaklik != null && sicaklikUygun(p, sicaklik) < 0.5) return false;
    return true;
  });
}
function gruplar(parcalar) {
  const g = { ust: [], alt: [], tek: [], dis: [], ayakkabi: [], aksesuar: [] };
  for (const p of parcalar) g[rolu(p)]?.push(p);
  return g;
}
// Gövde: üst+alt ya da tek parça; varsa ayakkabı; gerekiyorsa dış giyim.
// Toplam aday sayısı sınırı aşarsa sabit sırayla kesmek yerine rastgele örneklenir (her gövde türü şansa sahip olur).
function* adaylar(g, { dis }, ust_sinir = Infinity, rastgele = Math.random) {
  const ayak = g.ayakkabi.length ? g.ayakkabi : [null];
  const disl = dis && g.dis.length ? g.dis : [null];
  const ciftSayisi = g.ust.length * g.alt.length;
  const govdeSayisi = ciftSayisi + g.tek.length;
  const toplam = govdeSayisi * ayak.length * disl.length;
  const kur = (i) => {
    const d = disl[i % disl.length]; i = Math.floor(i / disl.length);
    const ay = ayak[i % ayak.length]; i = Math.floor(i / ayak.length);
    const govde = i < ciftSayisi ? [g.ust[i % g.ust.length], g.alt[Math.floor(i / g.ust.length)]] : [g.tek[i - ciftSayisi]];
    return [...govde, ay, d].filter(Boolean);
  };
  if (toplam <= ust_sinir) { for (let i = 0; i < toplam; i++) yield kur(i); return; }
  const gorulen = new Set();
  for (let n = 0; n < ust_sinir * 3 && gorulen.size < ust_sinir; n++) {
    const i = Math.floor(rastgele() * toplam);
    if (gorulen.has(i)) continue;
    gorulen.add(i);
    yield kur(i);
  }
}
const anaRenk = (p) => p.renkler?.[0];
const desenli = (p) => p.desen && p.desen !== "duz";
const anahtar = (ids) => [...ids].sort().join("|");

// baglam: { giyim: Map(id -> {sayi, son}), kombinler: [...], bugun: Date }
export function puanla(parcaListesi, baglam = {}, kosul = {}) {
  const nedenler = [];
  const r = renkUyumu(parcaListesi.map(anaRenk));
  nedenler.push(r.neden);
  let puan = r.puan * 0.4;

  const bugun = baglam.bugun || new Date();
  const gunler = parcaListesi.map((p) => {
    const son = baglam.giyim?.get(p.id)?.son;
    return son ? (bugun - new Date(son)) / 864e5 : 60;
  });
  const tazelik = Math.min(1, gunler.reduce((a, b) => a + b, 0) / gunler.length / 30);
  puan += tazelik * 0.25;
  if (tazelik > 0.8) nedenler.push("Bir süredir giyilmeyen parçalar");

  const favoriParcalar = new Set((baglam.kombinler || []).filter((k) => k.favori || (k.puan || 0) >= 4).flatMap((k) => k.parcalar));
  const fav = parcaListesi.filter((p) => favoriParcalar.has(p.id)).length / parcaListesi.length;
  puan += fav * 0.15;
  if (fav >= 0.5) nedenler.push("Favori kombinlerindeki parçalar");

  const hava = parcaListesi.reduce((a, p) => a + sicaklikUygun(p, kosul.sicaklik), 0) / parcaListesi.length;
  puan += hava * 0.2;
  if (kosul.sicaklik != null && hava === 1) nedenler.push(`${Math.round(kosul.sicaklik)}°C için uygun`);

  if (parcaListesi.filter(desenli).length > 1) { puan -= 0.15; nedenler.push("Birden fazla desen"); }
  const k = anahtar(parcaListesi.map((p) => p.id));
  const sonGiyilen = baglam.sonKombinler?.get(k);
  if (sonGiyilen != null && sonGiyilen < 7) { puan -= 0.2; nedenler.push("Bu hafta giyildi"); }
  return { puan: Math.max(0, Math.min(1, puan)), nedenler };
}

function begenilmeyenler(kombinler = []) {
  return new Set(kombinler.filter((k) => k.begenmedi).map((k) => anahtar(k.parcalar)));
}

// K4: en iyi `adet` öneri. kosul: {ortam, mevsim, sicaklik}. rastgele: test için enjekte edilebilir.
export function oner(parcalar, kosul = {}, baglam = {}, { adet = 5, ust_sinir = 3000, rastgele = Math.random } = {}) {
  const g = gruplar(uygunParcalar(parcalar, kosul));
  const kotu = begenilmeyenler(baglam.kombinler);
  const dis = disGerekli(kosul.sicaklik, kosul.mevsim);
  const sonuc = [];
  for (const aday of adaylar(g, { dis }, ust_sinir, rastgele)) {
    if (kotu.has(anahtar(aday.map((p) => p.id)))) continue;
    const { puan, nedenler } = puanla(aday, baglam, kosul);
    sonuc.push({ parcalar: aday.map((p) => p.id), puan: puan + rastgele() * 0.03, nedenler });
  }
  sonuc.sort((a, b) => b.puan - a.puan);
  // Çeşitlilik: aynı üst ya da tek parça en fazla iki kez.
  const sayac = new Map(), secilen = [];
  for (const s of sonuc) {
    const govde = s.parcalar[0];
    if ((sayac.get(govde) || 0) >= 2) continue;
    sayac.set(govde, (sayac.get(govde) || 0) + 1);
    secilen.push(s);
    if (secilen.length >= adet) break;
  }
  return secilen;
}

// K3: rastgele ama mantıklı bir kombin. Renk uyumu 0.5 altı olanları eler.
export function karistir(parcalar, kosul = {}, baglam = {}, rastgele = Math.random) {
  const g = gruplar(uygunParcalar(parcalar, kosul));
  const sec = (l) => (l.length ? l[Math.floor(rastgele() * l.length)] : null);
  const dis = disGerekli(kosul.sicaklik, kosul.mevsim);
  for (let deneme = 0; deneme < 60; deneme++) {
    const tekMi = g.tek.length && (!g.ust.length || !g.alt.length || rastgele() < g.tek.length / (g.tek.length + g.ust.length));
    const govde = tekMi ? [sec(g.tek)] : [sec(g.ust), sec(g.alt)];
    if (govde.some((x) => !x)) return null;
    const liste = [...govde, sec(g.ayakkabi), dis ? sec(g.dis) : null].filter(Boolean);
    if (renkUyumu(liste.map(anaRenk)).puan >= 0.5 || deneme === 59) return { parcalar: liste.map((p) => p.id), ...puanla(liste, baglam, kosul) };
  }
  return null;
}

// K7: kapsüldeki parçalarla kurulabilen renk uyumlu kombinler (dış giyim ve aksesuar sayılmaz).
// Uyum yalnız ana renklere bağlı olduğundan parçalar (rol, renk) gruplarına ayrılır ve grup kombinasyonları
// sayılır; böylece büyük gardropta da tam sayım yapılır. odak: yalnız bu parçayı içeren kombinleri say.
export function kapsulAnalizi(parcalar, { esik = 0.5, ornekSayisi = 12, odak = null } = {}) {
  const grup = (rol) => {
    const m = new Map();
    for (const p of parcalar) if (!p.arsiv && rolu(p) === rol) {
      if (odak && rolu(odak) === rol && p.id !== odak.id) continue;
      const r = anaRenk(p) || "";
      (m.get(r) || m.set(r, []).get(r)).push(p);
    }
    return [...m.entries()];
  };
  const [ust, alt, tek] = [grup("ust"), grup("alt"), grup("tek")];
  let ayak = grup("ayakkabi");
  if (!ayak.length) { if (odak && rolu(odak) === "ayakkabi") return { sayi: 0, ornekler: [], kullanilan: new Set() }; ayak = [[null, [null]]]; }
  const govdeler = [];
  if (!odak || ["ust", "alt", "ayakkabi"].includes(rolu(odak))) for (const u of ust) for (const a of alt) govdeler.push([u, a]);
  if (!odak || ["tek", "ayakkabi"].includes(rolu(odak))) for (const t of tek) govdeler.push([t]);
  let sayi = 0;
  const ornekler = [], kullanilan = new Set();
  for (const gv of govdeler) for (const ay of ayak) {
    const kume = ay[0] === null && ay[1][0] === null ? gv : [...gv, ay];
    if (renkUyumu(kume.map(([r]) => r || null)).puan < esik) continue;
    sayi += kume.reduce((n, [, l]) => n * l.length, 1);
    for (const [, l] of kume) for (const p of l) kullanilan.add(p.id);
    if (ornekler.length < ornekSayisi) ornekler.push(kume.map(([, l]) => l[ornekler.length % l.length].id));
  }
  return { sayi, ornekler, kullanilan };
}

// S3: aday parça gardroba eklenince kaç yeni uyumlu kombin açılır.
export function almadanTest(parcalar, aday) {
  const a = { ...aday, id: "__aday__" };
  const once = kapsulAnalizi(parcalar).sayi;
  const yeni = kapsulAnalizi([...parcalar, a], { odak: a });
  return { once, sonra: once + yeni.sayi, yeni: yeni.sayi, ornekler: yeni.ornekler.slice(0, 6) };
}

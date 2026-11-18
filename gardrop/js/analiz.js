// Giyim kaydı ve analiz: A2 A3 A4 P4 S2 S4 B3. Saf fonksiyonlar; tarihler 'YYYY-MM-DD'.
import { KATEGORI, RENK, DURUM, UNUTULMA_GUN, TEKRAR_GUN, KIRLENMEYEN } from "./sabitler.js";
import { kapsulAnalizi } from "./oneri.js";

export const gunStr = (d = new Date()) => {
  const z = new Date(d.getTime() - d.getTimezoneOffset() * 6e4);
  return z.toISOString().slice(0, 10);
};
export const gunFarki = (a, b) => Math.round((new Date(b + "T12:00") - new Date(a + "T12:00")) / 864e5);

// Map(parcaId -> {sayi, son, ilk})
export function giyimHaritasi(giyimler) {
  const h = new Map();
  for (const g of giyimler) for (const id of g.parcalar || []) {
    const e = h.get(id) || { sayi: 0, son: null, ilk: null };
    e.sayi++;
    if (!e.son || g.tarih > e.son) e.son = g.tarih;
    if (!e.ilk || g.tarih < e.ilk) e.ilk = g.tarih;
    h.set(id, e);
  }
  return h;
}
// Map(kombin anahtarı -> kaç gün önce giyildi), puanlamada "bu hafta giyildi" cezası için.
export function sonKombinler(giyimler, bugun = gunStr()) {
  const m = new Map();
  for (const g of giyimler) {
    const k = [...(g.parcalar || [])].sort().join("|");
    const d = gunFarki(g.tarih, bugun);
    if (d >= 0 && (!m.has(k) || d < m.get(k))) m.set(k, d);
  }
  return m;
}

// B2 kirli sepeti: parça kaç giyimde yıkanır. Parçaya özel değer genel "giyince kirli" ayarından önce gelir.
// Dönüş: sayı ya da null (sayılmaz).
export function yikamaEsigi(p, giyinceKirli = false) {
  const n = Math.floor(+p.yikamaSiklik);
  if (n >= 1) return n;
  return giyinceKirli && !KIRLENMEYEN.includes(p.kategori) ? 1 : null;
}
// Bir giyimden sonra parçanın yeni durumu: {kirliSayac, kirli} ya da null (değişmez).
export function giyimSonrasi(p, giyinceKirli = false) {
  const esik = yikamaEsigi(p, giyinceKirli);
  if (!esik || (p.durum || "temiz") !== "temiz") return null;
  const sayac = (p.kirliSayac || 0) + 1;
  return sayac >= esik ? { kirliSayac: 0, kirli: true } : { kirliSayac: sayac, kirli: false };
}
// Ekranda: "Yıkamaya 2 giyim kaldı" için.
export function yikamayaKalan(p, giyinceKirli = false) {
  const esik = yikamaEsigi(p, giyinceKirli);
  if (!esik || esik === 1 || (p.durum || "temiz") !== "temiz") return null;
  return esik - (p.kirliSayac || 0);
}

// A2: fiyat ÷ giyilme. Giyilmediyse maliyet = fiyat.
export function giyimBasiMaliyet(parca, harita) {
  if (parca.fiyat == null || parca.fiyat === "" || isNaN(+parca.fiyat)) return null;
  const sayi = harita.get(parca.id)?.sayi || 0;
  return { maliyet: +parca.fiyat / Math.max(1, sayi), sayi };
}

const eklenmeGunu = (p) => p.alisTarihi || (p.olusturma || "").slice(0, 10) || gunStr();

// A3: son giyilmesi (hiç giyilmediyse eklenmesi) `gun` günden eski olanlar.
export function unutulanlar(parcalar, harita, bugun = gunStr(), gun = UNUTULMA_GUN) {
  return parcalar
    .filter((p) => !p.arsiv)
    .map((p) => {
      const son = harita.get(p.id)?.son;
      return { parca: p, son, gun: gunFarki(son || eklenmeGunu(p), bugun), hic: !son };
    })
    .filter((x) => x.gun >= gun)
    .sort((a, b) => b.gun - a.gun);
}

// A4
export function istatistik(parcalar, giyimler, bugun = gunStr()) {
  const aktif = parcalar.filter((p) => !p.arsiv);
  const harita = giyimHaritasi(giyimler);
  const say = (f) => {
    const m = new Map();
    for (const p of aktif) { const k = f(p); if (k) m.set(k, (m.get(k) || 0) + 1); }
    return [...m].sort((a, b) => b[1] - a[1]);
  };
  const kategori = say((p) => p.kategori).map(([k, n]) => ({ id: k, ad: KATEGORI[k]?.ad || k, n }));
  const renk = say((p) => p.renkler?.[0]).map(([k, n]) => ({ id: k, ad: RENK[k]?.ad || k, rgb: RENK[k]?.rgb, n }));
  const sirali = aktif.map((p) => ({ parca: p, sayi: harita.get(p.id)?.sayi || 0 })).sort((a, b) => b.sayi - a.sayi);
  const aylar = [];
  const b = new Date(bugun + "T12:00");
  for (let i = 11; i >= 0; i--) {
    const d = new Date(b.getFullYear(), b.getMonth() - i, 1);
    aylar.push({ ay: `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`, n: 0 });
  }
  const gunler = new Set();
  for (const g of giyimler) {
    if (gunler.has(g.tarih)) continue;
    gunler.add(g.tarih);
    const a = aylar.find((x) => x.ay === g.tarih.slice(0, 7));
    if (a) a.n++;
  }
  const fiyatli = aktif.filter((p) => p.fiyat != null && p.fiyat !== "" && !isNaN(+p.fiyat));
  const toplamDeger = fiyatli.reduce((a, p) => a + +p.fiyat, 0);
  const giyilen = aktif.filter((p) => harita.get(p.id)?.sayi).length;
  const maliyetler = fiyatli.map((p) => giyimBasiMaliyet(p, harita)).filter((x) => x && x.sayi);
  // A5: gardrop değeri kategoriye göre (gardroptakiler) ve yıllık harcama (arşivdekiler dahil, alış tarihine göre).
  const degerKat = new Map();
  for (const p of fiyatli) { const e = degerKat.get(p.kategori) || { id: p.kategori, ad: KATEGORI[p.kategori]?.ad || p.kategori, toplam: 0, n: 0 }; e.toplam += +p.fiyat; e.n++; degerKat.set(p.kategori, e); }
  const yillar = new Map();
  for (const p of parcalar) {
    if (p.fiyat == null || p.fiyat === "" || isNaN(+p.fiyat)) continue;
    const y = (p.alisTarihi || "").slice(0, 4);
    if (!/^\d{4}$/.test(y)) continue;
    const e = yillar.get(y) || { yil: y, toplam: 0, n: 0 }; e.toplam += +p.fiyat; e.n++; yillar.set(y, e);
  }
  const arsivGelir = parcalar.reduce((a, p) => a + (p.arsiv?.satis > 0 ? +p.arsiv.satis : 0), 0);
  return {
    toplam: aktif.length,
    arsiv: parcalar.length - aktif.length,
    kullanimOrani: aktif.length ? giyilen / aktif.length : 0,
    kategori, renk,
    enCok: sirali.slice(0, 5).filter((x) => x.sayi),
    enAz: sirali.slice().reverse().slice(0, 5),
    aylar, toplamDeger,
    deger: {
      kategori: [...degerKat.values()].sort((a, b) => b.toplam - a.toplam),
      yillar: [...yillar.values()].sort((a, b) => b.yil.localeCompare(a.yil)),
      fiyatsiz: aktif.length - fiyatli.length,
      arsivGelir,
    },
    ortMaliyet: maliyetler.length ? maliyetler.reduce((a, m) => a + m.maliyet, 0) / maliyetler.length : null,
  };
}

// P4: tarih çevresinde aynı ya da benzer kombin. kayitlar: giyim + plan girdileri {tarih, parcalar, etkinlik, kombin}.
export function tekrarUyarisi({ parcalar, kombin, tarih, etkinlik }, kayitlar, gun = TEKRAR_GUN) {
  const set = new Set(parcalar);
  const norm = (s) => (s || "").trim().toLocaleLowerCase("tr");
  const sonuc = [];
  for (const k of kayitlar) {
    if (k.tarih === tarih && (k.kombin === kombin || !kombin)) continue;
    const d = Math.abs(gunFarki(k.tarih, tarih));
    if (d > gun) continue;
    const ortak = (k.parcalar || []).filter((id) => set.has(id)).length;
    const ayni = (kombin && k.kombin === kombin) || (ortak === set.size && ortak === (k.parcalar || []).length);
    const benzer = !ayni && ortak >= 2 && ortak / Math.max(set.size, 1) >= 0.66;
    if (!ayni && !benzer) continue;
    const guclu = !!(etkinlik && norm(k.etkinlik) && norm(k.etkinlik) === norm(etkinlik));
    sonuc.push({ tarih: k.tarih, etkinlik: k.etkinlik || "", tur: ayni ? "ayni" : "benzer", guclu, gun: d });
  }
  return sonuc.sort((a, b) => b.guclu - a.guclu || a.gun - b.gun);
}

// S2: temel parça kontrolü ve denge.
const KOYU = new Set(["siyah", "lacivert", "antrasit", "denim", "gri"]);
const TEMELLER = [
  { ad: "Beyaz ya da krem bir üst", kategori: "ust", alt: "Tişört", renk: "beyaz", f: (p) => p.kategori === "ust" && ["beyaz", "krem"].includes(p.renkler?.[0]) },
  { ad: "Koyu renk pantolon ya da kot", kategori: "alt", alt: "Kot", renk: "lacivert", f: (p) => p.kategori === "alt" && ["Pantolon", "Kot"].includes(p.altKategori) && KOYU.has(p.renkler?.[0]) },
  { ad: "Nötr renk ayakkabı", kategori: "ayakkabi", alt: "", renk: "siyah", f: (p) => p.kategori === "ayakkabi" && RENK[p.renkler?.[0]]?.notr },
  { ad: "Spor ayakkabı", kategori: "ayakkabi", alt: "Spor ayakkabı", renk: "beyaz", f: (p) => p.altKategori === "Spor ayakkabı" },
  { ad: "Kış için mont ya da kaban", kategori: "dis", alt: "Mont", renk: "", f: (p) => ["Mont", "Kaban"].includes(p.altKategori) },
  { ad: "Ara mevsim ceketi", kategori: "dis", alt: "Ceket", renk: "", f: (p) => ["Ceket", "Blazer", "Trençkot"].includes(p.altKategori) },
  { ad: "Özel gün için bir parça", kategori: "tek", alt: "", renk: "", f: (p) => p.ortamlar?.includes("ozel") },
  { ad: "İş ortamına uygun üst", kategori: "ust", alt: "Gömlek", renk: "", f: (p) => (p.kategori === "ust" || p.kategori === "tek") && p.ortamlar?.includes("is") },
];
export function eksikAnalizi(parcalar) {
  const aktif = parcalar.filter((p) => !p.arsiv);
  const eksik = TEMELLER.filter((t) => !aktif.some(t.f)).map(({ ad, kategori, alt, renk }) => ({ ad, kategori, alt, renk }));
  const n = (k) => aktif.filter((p) => p.kategori === k).length;
  const denge = [];
  const ust = n("ust"), alt = n("alt");
  if (ust && alt && ust / alt > 3) denge.push(`Üst parça ${ust}, alt parça ${alt}: alt eklemek kombin sayısını hızla artırır.`);
  if (ust && alt && alt / ust > 2) denge.push(`Alt parça ${alt}, üst parça ${ust}: üst eklemek daha çok kombin açar.`);
  if (aktif.length && !n("ayakkabi")) denge.push("Hiç ayakkabı eklenmemiş.");
  const { sayi, kullanilan } = kapsulAnalizi(aktif);
  const yetim = aktif.filter((p) => ["ust", "alt", "tek"].includes(p.kategori) && !kullanilan.has(p.id));
  return { eksik, denge, yetim, kombinSayisi: sayi };
}

// S4: elden çıkarma adayları.
export function eldenCikarma(parcalar, harita, bugun = gunStr()) {
  const { yetim } = eksikAnalizi(parcalar);
  const yetimSet = new Set(yetim.map((p) => p.id));
  const sonuc = [];
  for (const p of parcalar) {
    if (p.arsiv) continue;
    const g = harita.get(p.id);
    const eklenme = gunFarki(eklenmeGunu(p), bugun);
    const nedenler = [];
    if (!g && eklenme >= 180) nedenler.push(`${eklenme} gündür hiç giyilmedi`);
    else if (g && gunFarki(g.son, bugun) >= 365) nedenler.push(`Bir yıldır giyilmedi`);
    if (yetimSet.has(p.id) && (!g || gunFarki(g.son, bugun) >= 90)) nedenler.push("Gardroptaki hiçbir parçayla uyumlu kombin çıkmıyor");
    if (nedenler.length) sonuc.push({ parca: p, nedenler });
  }
  return sonuc;
}

// B3: terzideki / kuru temizlemedeki parçalar; teslim tarihi yaklaşan ya da geçenler önce.
export function hatirlatmalar(parcalar, bugun = gunStr()) {
  return parcalar
    .filter((p) => !p.arsiv && DURUM[p.durum]?.hatirlat)
    .map((p) => {
      const kalan = p.teslimTarihi ? gunFarki(bugun, p.teslimTarihi) : null;
      return { parca: p, kalan, gecen: p.durumTarihi ? gunFarki(p.durumTarihi, bugun) : null, acil: kalan != null && kalan <= 1 };
    })
    .sort((a, b) => (a.kalan ?? 999) - (b.kalan ?? 999));
}

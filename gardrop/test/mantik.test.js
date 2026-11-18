import { test } from "node:test";
import assert from "node:assert/strict";
import { renkUyumu, enYakinRenk, baskinRenkler } from "../js/renk.js";
import { oner, karistir, kapsulAnalizi, almadanTest, sicaklikUygun, mevsimBul } from "../js/oneri.js";
import { giyimHaritasi, giyimBasiMaliyet, unutulanlar, tekrarUyarisi, eksikAnalizi, eldenCikarma, istatistik, hatirlatmalar, yikamaEsigi, giyimSonrasi, yikamayaKalan } from "../js/analiz.js";

const P = (id, kategori, renk, ek = {}) => ({ id, kategori, renkler: [renk], durum: "temiz", ...ek });
const gardrop = [
  P("u1", "ust", "beyaz", { altKategori: "Tişört" }),
  P("u2", "ust", "kirmizi", { altKategori: "Gömlek" }),
  P("u3", "ust", "yesil", { altKategori: "Kazak", kumas: "Yün" }),
  P("a1", "alt", "denim", { altKategori: "Kot" }),
  P("a2", "alt", "turuncu", { altKategori: "Şort" }),
  P("ay1", "ayakkabi", "beyaz", { altKategori: "Spor ayakkabı" }),
  P("d1", "dis", "siyah", { altKategori: "Mont" }),
];

test("renk adı ve uyum", () => {
  assert.equal(enYakinRenk([25, 25, 25]), "siyah");
  assert.equal(enYakinRenk([200, 35, 45]), "kirmizi");
  assert.ok(renkUyumu(["beyaz", "denim"]).puan > 0.8);
  assert.ok(renkUyumu(["kirmizi", "yesil", "mor"]).puan < 0.5);
  assert.ok(renkUyumu(["kirmizi", "turuncu"]).puan >= 0.8);
});

test("baskın renk: düz arka plan atlanır", () => {
  const w = 40, h = 40, d = new Uint8ClampedArray(w * h * 4);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const i = (y * w + x) * 4, ic = x > 10 && x < 30 && y > 8 && y < 34;
    d.set(ic ? [200, 30, 40, 255] : [210, 210, 205, 255], i);
  }
  const r = baskinRenkler(d, w, h);
  assert.equal(r[0].id, "kirmizi");
});

test("sıcaklık kuralları", () => {
  assert.equal(sicaklikUygun(gardrop[4], 10), 0.3); // şort soğukta
  assert.equal(sicaklikUygun(gardrop[2], 28), 0.3); // yün kazak sıcakta
  assert.equal(sicaklikUygun(gardrop[0], 28), 1);
  assert.equal(mevsimBul(new Date(2026, 0, 5)), "kis");
  assert.equal(mevsimBul(new Date(2026, 6, 5)), "yaz");
});

test("öneri: soğukta mont eklenir, şort elenir; kirli parça girmez", () => {
  const liste = gardrop.map((p) => (p.id === "u1" ? { ...p, durum: "kirli" } : p));
  const s = oner(liste, { sicaklik: 8 }, {}, { rastgele: () => 0 });
  assert.ok(s.length > 0);
  for (const k of s) {
    assert.ok(k.parcalar.includes("d1"));
    assert.ok(!k.parcalar.includes("a2"));
    assert.ok(!k.parcalar.includes("u1"));
  }
});

test("öneri: beğenilmeyen kombin tekrar önerilmez", () => {
  const kotu = { parcalar: ["u1", "a1", "ay1"], begenmedi: true };
  const s = oner(gardrop, { sicaklik: 22 }, { kombinler: [kotu] }, { adet: 50, rastgele: () => 0 });
  assert.ok(!s.some((k) => [...k.parcalar].sort().join() === [...kotu.parcalar].sort().join()));
});

test("karıştır geçerli kombin döner", () => {
  let i = 0; const r = () => [0.1, 0.5, 0.9, 0.3][i++ % 4];
  const k = karistir(gardrop, { sicaklik: 22 }, {}, r);
  assert.ok(k.parcalar.length >= 2);
});

test("kapsül ve almadan önce test", () => {
  const n = kapsulAnalizi(gardrop).sayi;
  assert.ok(n >= 4);
  const t = almadanTest(gardrop, { kategori: "alt", renkler: ["siyah"], altKategori: "Pantolon" });
  assert.equal(t.once, n);
  assert.ok(t.yeni >= 3);
});

test("giyim başı maliyet ve unutulanlar", () => {
  const giyim = [{ tarih: "2026-11-01", parcalar: ["u1", "a1"] }, { tarih: "2026-11-10", parcalar: ["u1"] }];
  const h = giyimHaritasi(giyim);
  assert.equal(h.get("u1").sayi, 2);
  assert.equal(giyimBasiMaliyet({ id: "u1", fiyat: 300 }, h).maliyet, 150);
  assert.equal(giyimBasiMaliyet({ id: "x", fiyat: 300 }, h).maliyet, 300);
  assert.equal(giyimBasiMaliyet({ id: "x" }, h), null);
  const u = unutulanlar([{ id: "u1" }, { id: "eski", alisTarihi: "2026-01-01" }], h, "2026-11-17");
  assert.deepEqual(u.map((x) => x.parca.id), ["eski"]);
});

test("tekrar uyarısı: aynı etkinlik güçlü", () => {
  const kayit = [{ tarih: "2026-11-05", parcalar: ["u1", "a1", "ay1"], kombin: "k1", etkinlik: "Ofis" }];
  const w = tekrarUyarisi({ parcalar: ["u1", "a1", "ay1"], kombin: "k1", tarih: "2026-11-20", etkinlik: "ofis" }, kayit);
  assert.equal(w.length, 1); assert.equal(w[0].guclu, true); assert.equal(w[0].tur, "ayni");
  assert.equal(tekrarUyarisi({ parcalar: ["u1"], tarih: "2027-03-01" }, kayit).length, 0);
});

test("eksik analizi, elden çıkarma, istatistik, hatırlatma", () => {
  const e = eksikAnalizi(gardrop);
  assert.ok(e.eksik.some((x) => x.ad === "Ara mevsim ceketi" && x.kategori === "dis"));
  assert.ok(!e.eksik.some((x) => x.ad === "Spor ayakkabı"));
  const c = eldenCikarma([{ id: "z", kategori: "ust", renkler: ["beyaz"], alisTarihi: "2025-01-01" }], new Map(), "2026-11-17");
  assert.equal(c.length, 1);
  const s = istatistik(gardrop, [{ tarih: "2026-11-01", parcalar: ["u1"] }], "2026-11-17");
  assert.equal(s.toplam, 7); assert.equal(s.aylar.at(-1).n, 1);
  const hz = hatirlatmalar([{ id: "t", durum: "terzi", teslimTarihi: "2026-11-17" }], "2026-11-17");
  assert.equal(hz[0].acil, true);
});

test("büyük gardrop: elbise önerilebilir, sayım tam", () => {
  const renkler = ["beyaz", "siyah", "gri", "lacivert", "bej", "kirmizi", "yesil", "mavi"];
  const l = [];
  for (let i = 0; i < 40; i++) l.push(P("u" + i, "ust", renkler[i % 8]));
  for (let i = 0; i < 30; i++) l.push(P("a" + i, "alt", renkler[(i + 3) % 8]));
  for (let i = 0; i < 12; i++) l.push(P("s" + i, "ayakkabi", renkler[i % 4]));
  for (let i = 0; i < 8; i++) l.push(P("d" + i, "dis", renkler[i % 4]));
  for (let i = 0; i < 6; i++) l.push(P("t" + i, "tek", renkler[i % 8]));
  for (let i = 0; i < 4; i++) l.push(P("ak" + i, "aksesuar", "siyah"));
  assert.ok(l.length >= 100);
  let tohum = 7; const r = () => ((tohum = (tohum * 16807) % 2147483647) / 2147483647);
  const s = oner(l, { sicaklik: 8 }, {}, { adet: 50, rastgele: r });
  // 40×30+6 gövde × 12 ayakkabı × 8 mont = 115.776 aday; elbiseler de örneklemde olmalı
  const tum = []; for (let i = 0; i < 20; i++) tum.push(...oner(l, { sicaklik: 8 }, {}, { adet: 200, rastgele: r }));
  assert.ok(tum.some((k) => k.parcalar.some((id) => id.startsWith("t"))), "elbise hiç önerilmedi");
  assert.ok(s.every((k) => k.parcalar.some((id) => id.startsWith("d"))));
  // kapsül sayımı kaba kuvvetle aynı olmalı
  const ana = kapsulAnalizi(l);
  let kaba = 0;
  const rol = (k) => l.filter((p) => p.kategori === k);
  for (const u of rol("ust")) for (const a of rol("alt")) for (const sh of rol("ayakkabi")) if (renkUyumu([u, a, sh].map((p) => p.renkler[0])).puan >= 0.5) kaba++;
  for (const t of rol("tek")) for (const sh of rol("ayakkabi")) if (renkUyumu([t, sh].map((p) => p.renkler[0])).puan >= 0.5) kaba++;
  assert.equal(ana.sayi, kaba);
  // almadan önce test: odaklı sayım = fark
  const aday = { kategori: "alt", renkler: ["bej"] };
  const t = almadanTest(l, aday);
  assert.equal(t.sonra, kapsulAnalizi([...l, { ...aday, id: "x" }]).sayi);
});

test("B2 kirli sepeti: yıkama sıklığı ve genel ayar", () => {
  const kot = P("k", "alt", "denim", { yikamaSiklik: 3 });
  assert.equal(yikamaEsigi(kot, false), 3);
  assert.equal(yikamaEsigi(P("t", "ust", "beyaz"), false), null);
  assert.equal(yikamaEsigi(P("t", "ust", "beyaz"), true), 1);
  assert.equal(yikamaEsigi(P("ay", "ayakkabi", "siyah"), true), null); // ayakkabı tek giyimde kirlenmez
  assert.deepEqual(giyimSonrasi(kot, false), { kirliSayac: 1, kirli: false });
  assert.deepEqual(giyimSonrasi({ ...kot, kirliSayac: 2 }, false), { kirliSayac: 0, kirli: true });
  assert.equal(giyimSonrasi({ ...kot, durum: "kirli" }, false), null);
  assert.equal(yikamayaKalan({ ...kot, kirliSayac: 1 }), 2);
  assert.equal(yikamayaKalan(P("t", "ust", "beyaz"), true), null);
});

test("A5 gardrop değeri: kategori ve yıl", () => {
  const l = [
    P("x1", "ust", "beyaz", { fiyat: 500, alisTarihi: "2025-03-01" }),
    P("x2", "ust", "siyah", { fiyat: 300, alisTarihi: "2026-01-10" }),
    P("x3", "alt", "denim", { fiyat: 1000, alisTarihi: "2026-05-01" }),
    P("x4", "alt", "siyah", { fiyat: 800, alisTarihi: "2024-02-02", arsiv: { neden: "satildi", satis: 250 } }),
    P("x5", "ayakkabi", "beyaz"),
  ];
  const d = istatistik(l, []).deger;
  assert.deepEqual(d.kategori.map((x) => [x.id, x.toplam]), [["alt", 1000], ["ust", 800]]);
  assert.deepEqual(d.yillar.map((y) => [y.yil, y.toplam]), [["2026", 1300], ["2025", 500], ["2024", 800]]);
  assert.equal(d.arsivGelir, 250);
  assert.equal(d.fiyatsiz, 1);
});

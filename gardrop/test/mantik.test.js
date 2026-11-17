import { test } from "node:test";
import assert from "node:assert/strict";
import { renkUyumu, enYakinRenk, baskinRenkler } from "../js/renk.js";
import { oner, karistir, kapsulKombinleri, almadanTest, sicaklikUygun, mevsimBul } from "../js/oneri.js";
import { giyimHaritasi, giyimBasiMaliyet, unutulanlar, tekrarUyarisi, eksikAnalizi, eldenCikarma, istatistik, hatirlatmalar } from "../js/analiz.js";

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
  const n = kapsulKombinleri(gardrop).length;
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
  assert.ok(e.eksik.includes("Ara mevsim ceketi"));
  assert.ok(!e.eksik.includes("Spor ayakkabı"));
  const c = eldenCikarma([{ id: "z", kategori: "ust", renkler: ["beyaz"], alisTarihi: "2025-01-01" }], new Map(), "2026-11-17");
  assert.equal(c.length, 1);
  const s = istatistik(gardrop, [{ tarih: "2026-11-01", parcalar: ["u1"] }], "2026-11-17");
  assert.equal(s.toplam, 7); assert.equal(s.aylar.at(-1).n, 1);
  const hz = hatirlatmalar([{ id: "t", durum: "terzi", teslimTarihi: "2026-11-17" }], "2026-11-17");
  assert.equal(hz[0].acil, true);
});

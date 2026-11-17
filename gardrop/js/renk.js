// Renk işlemleri: baskın renk çıkarma (E3) ve kombin renk uyumu (K4). Saf fonksiyonlar; DOM'a dokunmaz.
import { RENKLER, RENK } from "./sabitler.js";

export function rgbHsl([r, g, b]) {
  r /= 255; g /= 255; b /= 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  const l = (max + min) / 2;
  if (max === min) return [0, 0, l];
  const d = max - min;
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
  let h = max === r ? (g - b) / d + (g < b ? 6 : 0) : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return [h * 60, s, l];
}

// sRGB -> CIE Lab; en yakın renk adını algısal uzaklıkla bulmak için.
function lab([r, g, b]) {
  const f = (c) => ((c /= 255) <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  const [R, G, B] = [f(r), f(g), f(b)];
  let x = (R * 0.4124 + G * 0.3576 + B * 0.1805) / 0.95047;
  let y = R * 0.2126 + G * 0.7152 + B * 0.0722;
  let z = (R * 0.0193 + G * 0.1192 + B * 0.9505) / 1.08883;
  const t = (v) => (v > 0.008856 ? Math.cbrt(v) : 7.787 * v + 16 / 116);
  [x, y, z] = [t(x), t(y), t(z)];
  return [116 * y - 16, 500 * (x - y), 200 * (y - z)];
}
const RENK_LAB = RENKLER.map((r) => ({ id: r.id, lab: lab(r.rgb) }));

export function enYakinRenk(rgb) {
  const L = lab(rgb);
  let en = null, enD = Infinity;
  for (const r of RENK_LAB) {
    const d = (L[0] - r.lab[0]) ** 2 + (L[1] - r.lab[1]) ** 2 + (L[2] - r.lab[2]) ** 2;
    if (d < enD) { enD = d; en = r.id; }
  }
  return en;
}

// pikseller: RGBA Uint8ClampedArray. Saydam pikseller atlanır (arka planı silinmiş görsel).
// Saydamlık yoksa kenardan 8%'lik çerçevenin renkleri arka plan sayılıp benzerleri atlanır.
// Dönüş: [{id, oran, rgb}] — en fazla 3 renk, oran > %12.
export function baskinRenkler(pikseller, genislik, yukseklik) {
  const n = genislik * yukseklik;
  let saydamVar = false;
  for (let i = 3; i < pikseller.length; i += 4 * 7) if (pikseller[i] < 200) { saydamVar = true; break; }
  const kova = new Map();
  const kenar = new Map();
  const anahtar = (r, g, b) => ((r >> 4) << 8) | ((g >> 4) << 4) | (b >> 4);
  if (!saydamVar) {
    const cx = Math.max(1, Math.round(genislik * 0.08)), cy = Math.max(1, Math.round(yukseklik * 0.08));
    for (let y = 0; y < yukseklik; y += 2) for (let x = 0; x < genislik; x += 2) {
      if (x >= cx && x < genislik - cx && y >= cy && y < yukseklik - cy) continue;
      const i = (y * genislik + x) * 4;
      const k = anahtar(pikseller[i], pikseller[i + 1], pikseller[i + 2]);
      kenar.set(k, (kenar.get(k) || 0) + 1);
    }
  }
  const kenarToplam = [...kenar.values()].reduce((a, b) => a + b, 0) || 1;
  const arkaPlan = new Set([...kenar].filter(([, v]) => v / kenarToplam > 0.05).map(([k]) => k));
  const adim = Math.max(1, Math.floor(n / 40000));
  let sayilan = 0;
  for (let p = 0; p < n; p += adim) {
    const i = p * 4;
    if (pikseller[i + 3] < 128) continue;
    const r = pikseller[i], g = pikseller[i + 1], b = pikseller[i + 2];
    const k = anahtar(r, g, b);
    if (arkaPlan.has(k)) continue;
    const e = kova.get(k) || { s: 0, r: 0, g: 0, b: 0 };
    e.s++; e.r += r; e.g += g; e.b += b;
    kova.set(k, e);
    sayilan++;
  }
  if (!sayilan) return [];
  const adlar = new Map();
  for (const e of kova.values()) {
    const rgb = [e.r / e.s, e.g / e.s, e.b / e.s];
    const id = enYakinRenk(rgb);
    const a = adlar.get(id) || { id, s: 0, rgb: [0, 0, 0] };
    a.s += e.s;
    a.rgb = a.rgb.map((v, j) => v + rgb[j] * e.s);
    adlar.set(id, a);
  }
  return [...adlar.values()]
    .map((a) => ({ id: a.id, oran: a.s / sayilan, rgb: a.rgb.map((v) => Math.round(v / a.s)) }))
    .sort((x, y) => y.oran - x.oran)
    .filter((x, i) => i === 0 || x.oran > 0.12)
    .slice(0, 3);
}

const notr = (id) => RENK[id]?.notr ?? true;
const ton = (id) => rgbHsl(RENK[id]?.rgb || [128, 128, 128])[0];
const tonFarki = (a, b) => { const d = Math.abs(ton(a) - ton(b)) % 360; return d > 180 ? 360 - d : d; };

// K4: parçaların ana renklerine göre 0..1 uyum puanı ve gerekçe.
// Kurallar: nötrler her şeyle gider; en fazla 2 canlı renk; canlı renkler tek ton (<25°), komşu (<50°)
// ya da tamamlayıcı (150–210°) ise iyi; aradaki çatışan tonlar düşük puan.
export function renkUyumu(renkIdleri) {
  const canli = [...new Set(renkIdleri.filter((r) => r && !notr(r)))];
  if (canli.length === 0) return { puan: 0.85, neden: "Nötr tonlar" };
  if (canli.length === 1) return { puan: 0.95, neden: "Nötrler üstüne tek vurgu rengi" };
  if (canli.length > 2) return { puan: 0.25, neden: "Üçten fazla canlı renk" };
  const d = tonFarki(canli[0], canli[1]);
  if (d < 25) return { puan: 0.9, neden: "Tek ton uyumu" };
  if (d < 50) return { puan: 0.8, neden: "Komşu renkler" };
  if (d >= 150) return { puan: 0.75, neden: "Tamamlayıcı renkler" };
  return { puan: 0.4, neden: "Renkler çatışabilir" };
}

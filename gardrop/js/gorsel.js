// Görsel işleme: küçültme (E1), arka plan kaldırma (E2), baskın renk (E3), kombin görseli (X2).
import { baskinRenkler } from "./renk.js";

const BUYUK = 1024, KUCUK = 320;
const UZAK_VERI = "https://staticimgly.com/@imgly/background-removal-data/1.4.5/dist/";

export async function bitmapAc(kaynak) {
  if (kaynak instanceof Blob) return createImageBitmap(kaynak, { imageOrientation: "from-image" });
  return kaynak;
}
function tuval(w, h) {
  const c = document.createElement("canvas");
  c.width = w; c.height = h;
  return c;
}
const blobAl = (c, tur, kalite) => new Promise((coz) => c.toBlob(coz, tur, kalite));

// Saydamlık varsa PNG yerine WebP (saydamlığı korur, daha küçük). Desteklenmezse PNG.
async function kodla(c, saydam) {
  const tur = saydam ? "image/webp" : "image/jpeg";
  const b = await blobAl(c, tur, 0.85);
  if (b && b.type === tur) return b;
  return blobAl(c, saydam ? "image/png" : "image/jpeg", 0.85);
}
export async function olcekle(kaynak, enFazla, saydam = false) {
  const bmp = await bitmapAc(kaynak);
  const o = Math.min(1, enFazla / Math.max(bmp.width, bmp.height));
  const c = tuval(Math.round(bmp.width * o), Math.round(bmp.height * o));
  c.getContext("2d").drawImage(bmp, 0, 0, c.width, c.height);
  return { blob: await kodla(c, saydam), tuval: c };
}

// Dosyadan kayda hazır görsel: büyük + küçük blob ve renk önerisi.
export async function hazirla(blob, { saydam = false } = {}) {
  const b = await olcekle(blob, BUYUK, saydam);
  const k = await olcekle(b.tuval, KUCUK, saydam);
  return { blob: b.blob, kucuk: k.blob, renkler: renkCikar(k.tuval) };
}
export function renkCikar(c) {
  const v = c.getContext("2d", { willReadFrequently: true }).getImageData(0, 0, c.width, c.height);
  return baskinRenkler(v.data, c.width, c.height);
}

let kutuphane = null, veriYolu = null;
async function veriYoluBul() {
  if (veriYolu) return veriYolu;
  const yerel = new URL("vendor/arka-plan-veri/", document.baseURI).href;
  try {
    const r = await fetch(yerel + "resources.json", { method: "HEAD" });
    veriYolu = r.ok ? yerel : UZAK_VERI;
  } catch { veriYolu = UZAK_VERI; }
  return veriYolu;
}
// E2. İlk kullanımda ~55 MB model iner (tarayıcı önbelleğinde kalır). ilerleme(oran, metin)
export async function arkaPlanKaldir(blob, ilerleme = () => {}) {
  kutuphane ||= await import("../vendor/arka-plan.js");
  const publicPath = await veriYoluBul();
  const sonuc = await kutuphane.removeBackground(blob, {
    publicPath,
    model: "small",
    output: { format: "image/png" },
    progress: (anahtar, simdi, toplam) => {
      if (anahtar.includes("fetch")) ilerleme(toplam ? simdi / toplam : 0, "Model indiriliyor (yalnızca ilk sefer)");
      else ilerleme(null, "Arka plan siliniyor");
    },
  });
  return kirp(sonuc);
}
// Saydam kenarları kırp ve biraz boşluk bırak; parça kartta ortalanır.
async function kirp(blob) {
  const bmp = await createImageBitmap(blob);
  const c = tuval(bmp.width, bmp.height);
  const x = c.getContext("2d", { willReadFrequently: true });
  x.drawImage(bmp, 0, 0);
  const d = x.getImageData(0, 0, c.width, c.height).data;
  let x0 = c.width, y0 = c.height, x1 = 0, y1 = 0;
  for (let y = 0; y < c.height; y += 2) for (let i = 0; i < c.width; i += 2) {
    if (d[(y * c.width + i) * 4 + 3] > 20) { if (i < x0) x0 = i; if (i > x1) x1 = i; if (y < y0) y0 = y; if (y > y1) y1 = y; }
  }
  if (x1 <= x0 || y1 <= y0) return blob;
  const pay = Math.round(Math.max(x1 - x0, y1 - y0) * 0.04);
  x0 = Math.max(0, x0 - pay); y0 = Math.max(0, y0 - pay);
  x1 = Math.min(c.width, x1 + pay); y1 = Math.min(c.height, y1 + pay);
  const k = tuval(x1 - x0, y1 - y0);
  k.getContext("2d").drawImage(c, x0, y0, k.width, k.height, 0, 0, k.width, k.height);
  return blobAl(k, "image/png");
}

// X2: kombin görseli. gorseller: [{blob|null, ad, renk: [r,g,b]}]. Düzen: 2 sütun ızgara, altta başlık.
export async function kombinGorseli(ogeler, baslik, { arka = "#f4f4f1", yazi = "#1c2230" } = {}) {
  const S = 2, hucre = 360, bosluk = 24, sutun = ogeler.length > 1 ? 2 : 1;
  const satir = Math.ceil(ogeler.length / sutun);
  const W = sutun * hucre + (sutun + 1) * bosluk, H = satir * hucre + (satir + 1) * bosluk + 90;
  const c = tuval(W * S, H * S);
  const x = c.getContext("2d");
  x.scale(S, S);
  x.fillStyle = arka; x.fillRect(0, 0, W, H);
  for (let i = 0; i < ogeler.length; i++) {
    const o = ogeler[i];
    const cx = bosluk + (i % sutun) * (hucre + bosluk), cy = bosluk + Math.floor(i / sutun) * (hucre + bosluk);
    x.fillStyle = "#ffffff"; x.beginPath(); x.roundRect(cx, cy, hucre, hucre, 16); x.fill();
    if (o.blob) {
      const b = await createImageBitmap(o.blob);
      const s = Math.min((hucre - 32) / b.width, (hucre - 32) / b.height);
      x.drawImage(b, cx + (hucre - b.width * s) / 2, cy + (hucre - b.height * s) / 2, b.width * s, b.height * s);
    } else {
      x.fillStyle = o.renk ? `rgb(${o.renk.join(",")})` : "#ccc";
      x.beginPath(); x.arc(cx + hucre / 2, cy + hucre / 2 - 20, 70, 0, 7); x.fill();
      x.fillStyle = yazi; x.font = "600 22px system-ui, sans-serif"; x.textAlign = "center";
      x.fillText(o.ad || "", cx + hucre / 2, cy + hucre - 60, hucre - 30);
    }
  }
  x.fillStyle = yazi; x.font = "700 30px system-ui, sans-serif"; x.textAlign = "left";
  x.fillText(baslik || "Kombin", bosluk, H - 38, W - 2 * bosluk);
  return blobAl(c, "image/png");
}

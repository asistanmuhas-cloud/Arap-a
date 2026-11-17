// Ortak arayüz yardımcıları: kaçışlı HTML, pencere, bildirim, parça kartı, çip seçiciler.
import { gorselUrl } from "./veri.js";
import { RENK, KATEGORI } from "./sabitler.js";

export const k = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

export const para = (n) =>
  n == null || isNaN(+n) ? "" : new Intl.NumberFormat("tr-TR", { style: "currency", currency: "TRY", maximumFractionDigits: +n < 100 ? 2 : 0 }).format(+n);
export const tarihYaz = (s, secenek = { day: "numeric", month: "long" }) =>
  s ? new Date(s + "T12:00").toLocaleDateString("tr-TR", secenek) : "";

let bildirimZaman;
export function bildir(metin) {
  const e = document.getElementById("bildirim");
  e.textContent = metin;
  e.hidden = false;
  clearTimeout(bildirimZaman);
  bildirimZaman = setTimeout(() => (e.hidden = true), 2600);
}

// Pencere: icerik HTML, alt düğmeler. Dönen nesne: {govde, kapat, sonuc (Promise)}.
export function pencere({ baslik, icerik, alt = "", genis = false }) {
  // Her pencere için yeni dialog: önceki pencerelerin dinleyicileri taşınmasın.
  const eski = document.getElementById("pencere");
  if (eski.open) eski.close();
  const d = eski.cloneNode(false);
  eski.replaceWith(d);
  d.innerHTML = `<div class="pencere-ic"><div class="pencere-bas"><h2>${k(baslik)}</h2><button class="kapat" type="button" data-kapat aria-label="Kapat">×</button></div>
    <div class="pencere-govde">${icerik}</div>${alt ? `<div class="pencere-alt">${alt}</div>` : ""}</div>`;
  d.style.maxWidth = genis ? "900px" : "";
  let coz;
  const sonuc = new Promise((c) => (coz = c));
  const kapat = (deger) => { if (d.open) d.close(); coz(deger); };
  d.onclick = (e) => {
    if (e.target === d || e.target.closest("[data-kapat]")) kapat(null);
  };
  d.onclose = () => coz(null);
  d.showModal();
  return { govde: d, kapat, sonuc };
}

export async function onayla(metin, { evet = "Evet", tehlike = false } = {}) {
  const p = pencere({
    baslik: "Emin misin?",
    icerik: `<p style="margin:0">${k(metin)}</p>`,
    alt: `<button class="dugme" data-kapat type="button">Vazgeç</button><button class="dugme ${tehlike ? "tehlike" : "ana"}" data-evet type="button">${k(evet)}</button>`,
  });
  p.govde.querySelector("[data-evet]").onclick = () => p.kapat(true);
  return !!(await p.sonuc);
}

// Görselleri sonradan doldur: <img data-gorsel="id">
export async function gorselleriDoldur(kok) {
  const imgs = [...kok.querySelectorAll("img[data-gorsel]:not([src])")];
  await Promise.all(imgs.map(async (img) => {
    const url = await gorselUrl(img.dataset.gorsel, { kucuk: img.dataset.buyuk == null });
    if (url) img.src = url; else img.replaceWith(Object.assign(document.createElement("span"), { textContent: "" }));
  }));
}

export function renkCss(id) {
  const r = RENK[id]?.rgb;
  return r ? `rgb(${r.join(",")})` : "var(--yuzey2)";
}
// Fotoğrafsız parça için renkli daire ve kısaltma.
export function yerTutucu(p) {
  const renk = renkCss(p.renkler?.[0]);
  const yazi = (p.altKategori || KATEGORI[p.kategori]?.ad || "?").slice(0, 10);
  const acik = RENK[p.renkler?.[0]] ? RENK[p.renkler[0]].rgb.reduce((a, b) => a + b, 0) > 420 : true;
  return `<span class="yer-tutucu" style="background:${renk};color:${acik ? "rgb(0 0 0 / .6)" : "rgb(255 255 255 / .85)"}">${k(yazi)}</span>`;
}
export function parcaGorsel(p, { buyuk = false } = {}) {
  return p.gorsel ? `<img data-gorsel="${k(p.gorsel)}" ${buyuk ? "data-buyuk" : ""} alt="" loading="lazy">` : yerTutucu(p);
}
export const parcaAdi = (p) => p.ad || [RENK[p.renkler?.[0]]?.ad, p.altKategori || KATEGORI[p.kategori]?.ad].filter(Boolean).join(" ") || "Parça";

export function parcaKart(p, { href, secili, rozet = "" } = {}) {
  const ic = `<span class="gorsel">${parcaGorsel(p)}</span><span class="ad">${k(parcaAdi(p))}</span>${rozet ? `<span class="rozet">${rozet}</span>` : ""}`;
  if (href) return `<a class="parca-kart" href="${href}">${ic}</a>`;
  return `<button class="parca-kart" type="button" data-parca="${k(p.id)}" ${secili != null ? `aria-pressed="${!!secili}"` : ""}>${ic}</button>`;
}

export function kolaj(parcalar) {
  const g = parcalar.slice(0, 4);
  return `<div class="kolaj n${g.length}">${g.map((p) => `<div>${parcaGorsel(p)}</div>`).join("")}</div>`;
}

// Çip grubu: tekli ya da çoklu seçim. degerler: [{id, ad, renk?}]
export function cipGrubu(ad, degerler, secili = [], { coklu = true } = {}) {
  const s = new Set([].concat(secili || []));
  return `<div class="cipler" data-cip-grup="${k(ad)}" data-coklu="${coklu}">${degerler
    .map((d) => `<button type="button" class="cip" data-deger="${k(d.id)}" aria-pressed="${s.has(d.id)}">${d.renk ? `<span class="renk-nokta" style="background:${d.renk}"></span>` : ""}${k(d.ad)}</button>`)
    .join("")}</div>`;
}
// Kök içindeki çip gruplarını tıklanabilir yapar; degisince(ad, degerler) çağrılır.
export function cipleriBagla(kok, degisince = () => {}) {
  kok.addEventListener("click", (e) => {
    const c = e.target.closest(".cip[data-deger]");
    const g = c?.closest("[data-cip-grup]");
    if (!g) return;
    const coklu = g.dataset.coklu === "true";
    const acik = c.getAttribute("aria-pressed") === "true";
    if (!coklu) g.querySelectorAll(".cip").forEach((x) => x.setAttribute("aria-pressed", "false"));
    c.setAttribute("aria-pressed", String(coklu ? !acik : !acik));
    degisince(g.dataset.cipGrup, cipDegeri(g));
  });
}
export function cipDegeri(g) {
  const v = [...g.querySelectorAll('.cip[aria-pressed="true"]')].map((c) => c.dataset.deger);
  return g.dataset.coklu === "true" ? v : v[0] || null;
}
export function cipOku(kok, ad) {
  const g = kok.querySelector(`[data-cip-grup="${ad}"]`);
  return g ? cipDegeri(g) : null;
}
export const ikon = {
  arti: '<svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg>',
  karistir: '<svg viewBox="0 0 24 24"><path d="M16 3h5v5M4 20 21 3M21 16v5h-5M15 15l6 6M4 4l5 5"/></svg>',
  arama: '<svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>',
  paylas: '<svg viewBox="0 0 24 24"><path d="M12 3v13M7 8l5-5 5 5M5 14v5a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-5"/></svg>',
  onay: '<svg viewBox="0 0 24 24"><path d="m5 12 5 5 9-10"/></svg>',
};

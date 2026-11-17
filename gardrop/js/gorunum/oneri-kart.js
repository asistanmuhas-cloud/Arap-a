// K3/K4 öneri kartı: Bugün ve Kombinler ekranında ortak. Kaydet, giydim, beğenmedim (K6 öğrenme).
import * as veri from "../veri.js";
import { giydim } from "../durum.js";
import { k, parcaKart, gorselleriDoldur, bildir, ikon } from "../ui.js";

const anahtar = (ids) => [...ids].sort().join("|");

export function oneriHtml(o, parcaHarita, i = 0) {
  const parcalar = o.parcalar.map((id) => parcaHarita.get(id)).filter(Boolean);
  return `<div class="kutu oneri" data-oneri="${i}">
    <div class="oneri-serit">${parcalar.map((p) => parcaKart(p, { href: `#/parca/${p.id}` })).join("")}</div>
    <div class="nedenler">${o.nedenler.map((n) => `<span class="etiket">${k(n)}</span>`).join("")}<span class="etiket iyi">Uyum %${Math.round(o.puan * 100)}</span></div>
    <div class="satir">
      <button class="dugme kucuk ana" type="button" data-eylem="giydim">${ikon.onay}Bugün bunu giydim</button>
      <button class="dugme kucuk" type="button" data-eylem="kaydet">Kaydet</button>
      <button class="dugme kucuk" type="button" data-eylem="begenmedim">Beğenmedim</button>
    </div>
  </div>`;
}

// Kart eylemlerini bağlar. oneriler: dizi; sonra(eylem, index) yeniden çizmek için.
export function oneriBagla(kok, oneriler, kombinler, sonra = () => {}) {
  gorselleriDoldur(kok);
  kok.addEventListener("click", async (e) => {
    const b = e.target.closest("[data-eylem]");
    const kart = b?.closest("[data-oneri]");
    if (!kart) return;
    const o = oneriler[+kart.dataset.oneri];
    const mevcut = kombinler.find((x) => anahtar(x.parcalar) === anahtar(o.parcalar));
    b.disabled = true;
    if (b.dataset.eylem === "kaydet") {
      if (mevcut && !mevcut.begenmedi) bildir("Bu kombin zaten kayıtlı");
      else { await veri.kaydet("kombinler", { ...(mevcut || {}), parcalar: o.parcalar, ad: "", kaynak: "oneri", favori: false, puan: 0, begenmedi: false, ortamlar: [], mevsimler: [] }); bildir("Kombinlere kaydedildi"); }
    } else if (b.dataset.eylem === "begenmedim") {
      if (mevcut) await veri.guncelle("kombinler", mevcut.id, { begenmedi: true, favori: false });
      else await veri.kaydet("kombinler", { parcalar: o.parcalar, kaynak: "oneri", begenmedi: true, gizli: true, ad: "", ortamlar: [], mevsimler: [] });
      bildir("Bu kombin bir daha önerilmeyecek");
    } else if (b.dataset.eylem === "giydim") {
      let kombin = mevcut;
      if (!kombin) kombin = await veri.kaydet("kombinler", { parcalar: o.parcalar, ad: "", kaynak: "oneri", favori: false, puan: 0, ortamlar: [], mevsimler: [] });
      await giydim({ parcalar: o.parcalar, kombin: kombin.id });
      bildir("Bugün giyildi olarak kaydedildi");
    }
    sonra(b.dataset.eylem, +kart.dataset.oneri);
  });
}

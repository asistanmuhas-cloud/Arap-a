// Kombin listesi + K3 karıştır + K4 öneri.
import { yukle } from "../durum.js";
import { oner, karistir, mevsimBul } from "../oneri.js";
import * as hava from "../hava.js";
import { gunStr } from "../analiz.js";
import { ORTAMLAR, MEVSIMLER } from "../sabitler.js";
import { k, kolaj, gorselleriDoldur, cipGrubu, cipleriBagla, cipOku, ikon } from "../ui.js";
import { oneriHtml, oneriBagla } from "./oneri-kart.js";
import { yenile } from "../app.js";

export const baslik = "Kombinler";
const durum = { sekme: "hepsi", ortam: null, mevsim: null, oneriler: null };

export async function ciz(kok) {
  const d = await yukle();
  const t = await hava.tahmin().catch(() => null);
  const bugunHava = t?.gunler.get(gunStr());
  const sicaklik = hava.kombinSicakligi(bugunHava);
  const gorunen = d.kombinler.filter((x) => !x.gizli && (durum.sekme !== "favori" || x.favori || (x.puan || 0) >= 4));
  kok.innerHTML = `
    <section class="kutu">
      <div class="satir ara"><h2>Ne giysem?</h2>${sicaklik != null ? `<span class="etiket">${hava.durumAdi(bugunHava.kod)[1]} Bugün ${Math.round(bugunHava.min)}–${Math.round(bugunHava.max)}°C</span>` : `<a class="kucuk" href="#/ayarlar">Hava için şehir seç</a>`}</div>
      <div class="alan"><span class="etiket-ad">Ortam</span>${cipGrubu("ortam", ORTAMLAR, durum.ortam, { coklu: false })}</div>
      <div class="alan"><span class="etiket-ad">Mevsim</span>${cipGrubu("mevsim", MEVSIMLER, durum.mevsim || mevsimBul(), { coklu: false })}</div>
      <div class="iki"><button class="dugme ana" type="button" id="oner">Öner</button><button class="dugme" type="button" id="karistir">${ikon.karistir}Karıştır</button></div>
      <div id="oneriler" class="yigin"></div>
    </section>
    <section class="bolum">
      <div class="bolum-bas"><div class="cipler"><button class="cip" type="button" data-sekme="hepsi" aria-pressed="${durum.sekme === "hepsi"}">Tümü ${d.kombinler.filter((x) => !x.gizli).length}</button><button class="cip" type="button" data-sekme="favori" aria-pressed="${durum.sekme === "favori"}">Favoriler</button></div><a class="kucuk" href="#/kapsul">Kapsül gardrop →</a></div>
      ${gorunen.length ? `<div class="kombin-liste">${gorunen.sort((a, b) => (b.guncelleme || "").localeCompare(a.guncelleme || "")).map((x) => kart(x, d)).join("")}</div>`
        : `<div class="bos-kutu">${d.kombinler.length ? "Favori kombin yok. Kombin detayından yıldız ver." : "Henüz kombin yok. Öner ya da Karıştır ile başla veya kendin kur."}</div>`}
    </section>
    <a class="dugme ana yuzen" href="#/kombin-kur/yeni">${ikon.arti}Kombin kur</a>`;
  gorselleriDoldur(kok);
  const panel = kok.querySelector(".kutu");
  cipleriBagla(panel, (ad, v) => { durum[ad] = v; });
  const kosul = () => ({ ortam: cipOku(panel, "ortam"), mevsim: cipOku(panel, "mevsim"), sicaklik });
  const goster = (liste, bosMetin) => {
    durum.oneriler = liste;
    const e = kok.querySelector("#oneriler");
    e.innerHTML = liste.length ? liste.map((o, i) => oneriHtml(o, d.parcaHarita, i)).join("") : `<div class="uyari-kutu">${bosMetin}</div>`;
    gorselleriDoldur(e);
  };
  const yetersiz = "Bu koşullara uyan yeterli parça yok. Üst ve alt (ya da elbise) parçaların temiz, mevsime ve ortama uygun olduğundan emin ol; etiketsiz parçalar her ortama uygun sayılır.";
  kok.querySelector("#oner").onclick = () => goster(oner(d.parcalar, kosul(), d.baglam, { adet: 4 }), yetersiz);
  kok.querySelector("#karistir").onclick = () => { const x = karistir(d.parcalar, kosul(), d.baglam); goster(x ? [x] : [], yetersiz); };
  kok.querySelectorAll("[data-sekme]").forEach((b) => (b.onclick = () => { durum.sekme = b.dataset.sekme; yenile(); }));
  if (durum.oneriler?.length) goster(durum.oneriler, yetersiz);
  // Eylemler: güncel durum.oneriler üzerinden
  baglaGuncel(kok.querySelector("#oneriler"), d);
}

function baglaGuncel(e, d) {
  const vekil = new Proxy([], { get: (_, p) => durum.oneriler?.[p] });
  oneriBagla(e, vekil, d.kombinler, (eylem, i) => {
    if (eylem === "begenmedim" || eylem === "giydim") {
      durum.oneriler = durum.oneriler.filter((_, j) => j !== i);
      yenile();
    }
  });
}

function kart(x, d) {
  const parcalar = x.parcalar.map((i) => d.parcaHarita.get(i)).filter(Boolean);
  const giyilme = d.giyim.filter((g) => g.kombin === x.id).length;
  return `<a class="kombin-kart" href="#/kombin/${x.id}">${kolaj(parcalar)}<span class="ad">${k(x.ad || "Kombin")}</span>
    <span class="satir kucuk soluk">${x.puan ? `<span class="yildiz">${"★".repeat(x.puan)}</span>` : ""}${x.favori ? "♥" : ""}${giyilme ? `${giyilme} kez giyildi` : ""}${x.begenmedi ? '<span class="etiket uyari">Beğenilmedi</span>' : ""}</span></a>`;
}

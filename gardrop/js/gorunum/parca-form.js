// Parça bilgi formu (G1 G2 G3). Ekleme ve düzenleme ortak kullanır.
import { KATEGORILER, KATEGORI, RENKLER, MEVSIMLER, ORTAMLAR, KUMASLAR, DESENLER, YIKAMALAR, UTULER, BAKIM_EKLERI } from "../sabitler.js";
import { k, cipGrubu, cipleriBagla, cipOku, renkCss } from "../ui.js";
import * as veri from "../veri.js";

const renkSecenek = RENKLER.map((r) => ({ id: r.id, ad: r.ad, renk: renkCss(r.id) }));

export function formHtml(p = {}, { kisa = false } = {}) {
  const kat = p.kategori || "ust";
  return `
  <div class="alan"><span class="etiket-ad">Kategori</span>${cipGrubu("kategori", KATEGORILER, kat, { coklu: false })}</div>
  <div class="alan" id="alt-kat-alan"><span class="etiket-ad">Tür</span>${altKatHtml(kat, p.altKategori)}</div>
  <div class="alan"><span class="etiket-ad">Ana renk</span>${cipGrubu("anaRenk", renkSecenek, p.renkler?.[0], { coklu: false })}</div>
  <details ${p.renkler?.length > 1 ? "open" : ""}><summary class="kucuk soluk">İkinci renk</summary><div style="margin-top:8px">${cipGrubu("digerRenk", renkSecenek, p.renkler?.slice(1) || [])}</div></details>
  <div class="alan"><span class="etiket-ad">Mevsim <span class="soluk" style="font-weight:400">(boş: her mevsim)</span></span>${cipGrubu("mevsimler", MEVSIMLER, p.mevsimler || [])}</div>
  <div class="alan"><span class="etiket-ad">Ortam</span>${cipGrubu("ortamlar", ORTAMLAR, p.ortamlar || [])}</div>
  ${kisa ? "" : detayHtml(p)}`;
}
function detayHtml(p) {
  return `
  <div class="alan"><span class="etiket-ad">Desen</span>${cipGrubu("desen", DESENLER, p.desen || "duz", { coklu: false })}</div>
  <div class="alan"><label for="f-ad">Ad <span class="soluk" style="font-weight:400">(isteğe bağlı)</span></label><input type="text" id="f-ad" value="${k(p.ad)}" placeholder="Ör. Mavi keten gömlek"></div>
  <div class="iki">
    <div class="alan"><label for="f-kumas">Kumaş</label><select id="f-kumas"><option value="">—</option>${KUMASLAR.map((x) => `<option ${p.kumas === x ? "selected" : ""}>${k(x)}</option>`).join("")}</select></div>
    <div class="alan"><label for="f-marka">Marka</label><input type="text" id="f-marka" value="${k(p.marka)}"></div>
  </div>
  <div class="uc">
    <div class="alan"><label for="f-fiyat">Fiyat (₺)</label><input type="number" inputmode="decimal" min="0" step="any" id="f-fiyat" value="${k(p.fiyat ?? "")}"></div>
    <div class="alan"><label for="f-beden">Beden</label><input type="text" id="f-beden" value="${k(p.beden)}"></div>
    <div class="alan"><label for="f-tarih">Alış tarihi</label><input type="date" id="f-tarih" value="${k(p.alisTarihi)}"></div>
  </div>
  <div class="iki">
    <div class="alan"><label for="f-magaza">Mağaza</label><input type="text" id="f-magaza" value="${k(p.magaza)}"></div>
    <div class="alan"><label for="f-link">Ürün linki</label><input type="url" id="f-link" value="${k(p.link)}" placeholder="https://"></div>
  </div>
  <div class="iki">
    <div class="alan"><label for="f-konum">Nerede duruyor</label><input type="text" id="f-konum" value="${k(p.konum)}" list="f-konumlar" placeholder="Ör. Yatak odası dolabı, kışlık kutu"><datalist id="f-konumlar"></datalist></div>
    <div class="alan"><label for="f-yikama-siklik">Kaç giyimde yıkanır</label><input type="number" inputmode="numeric" min="1" max="30" step="1" id="f-yikama-siklik" value="${k(p.yikamaSiklik ?? "")}" placeholder="Boş: ayara göre"></div>
  </div>
  <details ${p.bakim && Object.values(p.bakim).some((v) => v && (!Array.isArray(v) || v.length)) ? "open" : ""}><summary class="kucuk soluk">Bakım talimatı (etiketteki semboller)</summary>
    <div class="yigin" style="gap:10px;margin-top:8px">
      <div class="alan"><span class="etiket-ad">Yıkama</span>${cipGrubu("yikama", YIKAMALAR, p.bakim?.yikama, { coklu: false })}</div>
      <div class="alan"><span class="etiket-ad">Ütü</span>${cipGrubu("utu", UTULER, p.bakim?.utu, { coklu: false })}</div>
      <div class="alan"><span class="etiket-ad">Diğer</span>${cipGrubu("bakimEk", BAKIM_EKLERI, p.bakim?.ekler || [])}</div>
    </div>
  </details>
  <div class="alan"><label for="f-not">Not</label><textarea id="f-not">${k(p.not)}</textarea></div>`;
}
function altKatHtml(kat, secili) {
  return cipGrubu("altKategori", (KATEGORI[kat]?.alt || []).map((a) => ({ id: a, ad: a })), secili, { coklu: false });
}

export function formBagla(kok) {
  // G6: daha önce yazılan konumlar öneri olarak çıkar.
  const dl = kok.querySelector("#f-konumlar");
  if (dl) veri.hepsi("parcalar").then((l) => {
    dl.innerHTML = [...new Set(l.map((p) => (p.konum || "").trim()).filter(Boolean))].sort((a, b) => a.localeCompare(b, "tr")).map((x) => `<option value="${k(x)}">`).join("");
  }).catch(() => {});
  cipleriBagla(kok, (ad, deger) => {
    if (ad === "kategori") {
      if (!deger) { kok.querySelector('[data-cip-grup="kategori"] .cip').setAttribute("aria-pressed", "true"); deger = "ust"; }
      kok.querySelector("#alt-kat-alan").innerHTML = `<span class="etiket-ad">Tür</span>${altKatHtml(deger)}`;
    }
  });
}
// Renk önerisini (E3) forma uygula.
export function renkOner(kok, renkler) {
  if (!renkler?.length) return;
  const sec = (grup, ids) => kok.querySelectorAll(`[data-cip-grup="${grup}"] .cip`).forEach((c) => c.setAttribute("aria-pressed", String(ids.includes(c.dataset.deger))));
  sec("anaRenk", [renkler[0]]);
  sec("digerRenk", renkler.slice(1));
}

export function formOku(kok) {
  const deger = (id) => kok.querySelector("#" + id)?.value.trim();
  const ana = cipOku(kok, "anaRenk");
  const diger = (cipOku(kok, "digerRenk") || []).filter((r) => r !== ana);
  const v = {
    kategori: cipOku(kok, "kategori") || "ust",
    altKategori: cipOku(kok, "altKategori") || "",
    renkler: ana ? [ana, ...diger] : diger,
    mevsimler: cipOku(kok, "mevsimler") || [],
    ortamlar: cipOku(kok, "ortamlar") || [],
  };
  if (kok.querySelector("#f-ad")) {
    const fiyat = deger("f-fiyat");
    Object.assign(v, {
      desen: cipOku(kok, "desen") || "duz",
      ad: deger("f-ad"), kumas: deger("f-kumas"), marka: deger("f-marka"),
      fiyat: fiyat === "" ? null : +fiyat, beden: deger("f-beden"), alisTarihi: deger("f-tarih"),
      magaza: deger("f-magaza"), link: deger("f-link"), not: deger("f-not"),
      konum: deger("f-konum"),
      yikamaSiklik: +deger("f-yikama-siklik") >= 1 ? Math.min(30, Math.floor(+deger("f-yikama-siklik"))) : null,
      bakim: { yikama: cipOku(kok, "yikama"), utu: cipOku(kok, "utu"), ekler: cipOku(kok, "bakimEk") || [] },
    });
  }
  return v;
}

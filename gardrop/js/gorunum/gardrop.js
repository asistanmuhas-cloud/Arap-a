// G4: gardrop listesi, arama ve filtre.
import { yukle } from "../durum.js";
import { KATEGORILER, RENKLER, MEVSIMLER, ORTAMLAR, DURUMLAR, RENK, KATEGORI, DURUM } from "../sabitler.js";
import { k, parcaKart, gorselleriDoldur, cipGrubu, cipleriBagla, cipOku, pencere, ikon, renkCss, parcaAdi } from "../ui.js";

export const baslik = "Gardrop";
const filtre = { kategori: null, renk: [], mevsim: [], ortam: [], durum: [], konum: [], arsiv: false, metin: "" };

const normal = (s) => (s || "").toLocaleLowerCase("tr");
export function filtrele(parcalar, f) {
  const m = normal(f.metin).trim();
  return parcalar.filter((p) => {
    if (!!p.arsiv !== f.arsiv) return false;
    if (f.kategori && p.kategori !== f.kategori) return false;
    if (f.renk.length && !p.renkler?.some((r) => f.renk.includes(r))) return false;
    if (f.mevsim.length && p.mevsimler?.length && !p.mevsimler.some((x) => f.mevsim.includes(x))) return false;
    if (f.ortam.length && !p.ortamlar?.some((x) => f.ortam.includes(x))) return false;
    if (f.durum.length && !f.durum.includes(p.durum || "temiz")) return false;
    if (f.konum?.length && !f.konum.includes((p.konum || "").trim())) return false;
    if (m) {
      const metin = normal([parcaAdi(p), p.ad, p.altKategori, KATEGORI[p.kategori]?.ad, p.marka, p.kumas, p.magaza, p.not, p.konum, ...(p.renkler || []).map((r) => RENK[r]?.ad)].join(" "));
      if (!m.split(/\s+/).every((s) => metin.includes(s))) return false;
    }
    return true;
  });
}
const filtreSayisi = () => filtre.renk.length + filtre.mevsim.length + filtre.ortam.length + filtre.durum.length + filtre.konum.length + (filtre.arsiv ? 1 : 0);

export async function ciz(kok) {
  const d = await yukle();
  const sayilar = Object.fromEntries(KATEGORILER.map((c) => [c.id, d.aktif.filter((p) => p.kategori === c.id).length]));
  kok.innerHTML = `
    <div class="satir" style="flex-wrap:nowrap">
      <label class="arama" style="flex:1"><span hidden>Ara</span>${ikon.arama}<input type="search" id="ara" placeholder="Ara: marka, renk, tür…" value="${k(filtre.metin)}"></label>
      <button class="dugme" type="button" id="filtre-ac">Filtre${filtreSayisi() ? ` (${filtreSayisi()})` : ""}</button>
    </div>
    <div class="cipler kaydir" id="kategoriler">
      <button class="cip" type="button" data-kat="" aria-pressed="${!filtre.kategori}">Tümü <span class="soluk">${d.aktif.length}</span></button>
      ${KATEGORILER.filter((c) => sayilar[c.id]).map((c) => `<button class="cip" type="button" data-kat="${c.id}" aria-pressed="${filtre.kategori === c.id}">${k(c.ad)} <span class="soluk">${sayilar[c.id]}</span></button>`).join("")}
    </div>
    <div id="sonuc"></div>
    <a class="dugme ana yuzen" href="#/ekle">${ikon.arti}Parça ekle</a>`;

  const sonuc = kok.querySelector("#sonuc");
  const goster = () => {
    const liste = filtrele(d.parcalar, filtre).sort((a, b) => (b.olusturma || "").localeCompare(a.olusturma || ""));
    if (!d.parcalar.length) {
      sonuc.innerHTML = `<div class="bos-kutu"><h3>Gardrobun boş</h3><p style="margin:0">Fotoğraf çekerek ya da fotoğrafsız hızlı ekleyerek başla. Birkaç üst, alt ve ayakkabı eklediğinde kombin önerileri açılır.</p><a class="dugme ana" href="#/ekle">${ikon.arti}İlk parçayı ekle</a></div>`;
      return;
    }
    if (!liste.length) { sonuc.innerHTML = `<p class="bos">Bu filtreyle eşleşen parça yok.</p>`; return; }
    sonuc.innerHTML = `<p class="kucuk soluk" style="margin:0 0 8px">${liste.length} parça${filtre.arsiv ? " (arşiv)" : ""}</p><div class="izgara">${liste.map((p) => {
      const durum = p.durum && p.durum !== "temiz" ? `<span class="etiket uyari">${k(DURUM[p.durum]?.ad)}</span>` : "";
      return parcaKart(p, { href: `#/parca/${p.id}`, rozet: durum });
    }).join("")}</div>`;
    gorselleriDoldur(sonuc);
  };
  goster();

  kok.querySelector("#ara").addEventListener("input", (e) => { filtre.metin = e.target.value; goster(); });
  kok.querySelector("#kategoriler").addEventListener("click", (e) => {
    const c = e.target.closest("[data-kat]");
    if (!c) return;
    filtre.kategori = c.dataset.kat || null;
    kok.querySelectorAll("#kategoriler .cip").forEach((x) => x.setAttribute("aria-pressed", String(x === c)));
    goster();
  });
  const konumlar = [...new Set(d.parcalar.map((p) => (p.konum || "").trim()).filter(Boolean))].sort((a, b) => a.localeCompare(b, "tr"));
  kok.querySelector("#filtre-ac").onclick = async () => {
    const p = pencere({
      baslik: "Filtre",
      icerik: `
        <div class="alan"><span class="etiket-ad">Renk</span>${cipGrubu("renk", RENKLER.map((r) => ({ id: r.id, ad: r.ad, renk: renkCss(r.id) })), filtre.renk)}</div>
        <div class="alan"><span class="etiket-ad">Mevsim</span>${cipGrubu("mevsim", MEVSIMLER, filtre.mevsim)}</div>
        <div class="alan"><span class="etiket-ad">Ortam</span>${cipGrubu("ortam", ORTAMLAR, filtre.ortam)}</div>
        <div class="alan"><span class="etiket-ad">Durum</span>${cipGrubu("durum", DURUMLAR, filtre.durum)}</div>
        ${konumlar.length ? `<div class="alan"><span class="etiket-ad">Nerede</span>${cipGrubu("konum", konumlar.map((x) => ({ id: x, ad: x })), filtre.konum)}</div>` : ""}
        <div class="alan"><span class="etiket-ad">Göster</span>${cipGrubu("arsiv", [{ id: "aktif", ad: "Gardroptakiler" }, { id: "arsiv", ad: "Arşiv" }], filtre.arsiv ? "arsiv" : "aktif", { coklu: false })}</div>`,
      alt: `<button class="dugme" type="button" id="temizle">Temizle</button><button class="dugme ana" type="button" id="uygula">Uygula</button>`,
    });
    cipleriBagla(p.govde);
    p.govde.querySelector("#temizle").onclick = () => {
      Object.assign(filtre, { renk: [], mevsim: [], ortam: [], durum: [], konum: [], arsiv: false });
      p.kapat(true);
    };
    p.govde.querySelector("#uygula").onclick = () => {
      for (const a of ["renk", "mevsim", "ortam", "durum", "konum"]) filtre[a] = cipOku(p.govde, a) || [];
      filtre.arsiv = cipOku(p.govde, "arsiv") === "arsiv";
      p.kapat(true);
    };
    if (await p.sonuc) {
      kok.querySelector("#filtre-ac").textContent = `Filtre${filtreSayisi() ? ` (${filtreSayisi()})` : ""}`;
      goster();
    }
  };
}

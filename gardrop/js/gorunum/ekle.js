// E1 fotoğraf, E2 arka plan kaldırma, E3 renk önerisi, E5 toplu ekleme, E6 fotoğrafsız ekleme, E7 linkten ekleme.
import * as veri from "../veri.js";
import { hazirla, arkaPlanKaldir } from "../gorsel.js";
import { k, bildir, ikon } from "../ui.js";
import { formHtml, formBagla, formOku, renkOner } from "./parca-form.js";
import { RENK } from "../sabitler.js";
import { git } from "../app.js";

export const baslik = "Parça ekle";

export async function ciz(kok) {
  const otomatik = await veri.ayarOku("arkaPlanOtomatik", true);
  kok.innerHTML = `
    <section class="bolum">
      <div class="iki">
        <label class="dugme ana" style="min-height:88px;flex-direction:column"><svg viewBox="0 0 24 24"><path d="M4 8h3l2-3h6l2 3h3v11H4z"/><circle cx="12" cy="13" r="3.5"/></svg>Fotoğraf çek<input type="file" accept="image/*" capture="environment" id="kamera" hidden></label>
        <label class="dugme" style="min-height:88px;flex-direction:column"><svg viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="m21 16-5-5-9 9"/></svg>Galeriden seç<small class="soluk" style="font-weight:400">birden fazla seçebilirsin</small><input type="file" accept="image/*" multiple id="galeri" hidden></label>
      </div>
      <label class="satir kucuk"><input type="checkbox" id="otomatik" ${otomatik ? "checked" : ""}> Arka planı otomatik sil</label>
    </section>
    <section class="bolum">
      <div class="iki">
        <button class="dugme" type="button" id="fotografsiz">Fotoğrafsız ekle</button>
        <button class="dugme" type="button" id="link-ac">Linkten ekle</button>
      </div>
      <form id="link-form" class="satir" hidden style="flex-wrap:nowrap"><input type="url" id="link" placeholder="Ürün sayfasının linki" required style="flex:1"><button class="dugme ana" type="submit">Getir</button></form>
      <div id="link-durum"></div>
    </section>
    <section id="islem"></section>`;

  const islemKok = kok.querySelector("#islem");
  let kuyruk = [], sira = 0;

  kok.querySelector("#otomatik").onchange = (e) => veri.ayarYaz("arkaPlanOtomatik", e.target.checked);
  const dosyalar = (e) => {
    const l = [...e.target.files].filter((f) => f.type.startsWith("image/"));
    e.target.value = "";
    if (!l.length) return;
    kuyruk = l.map((dosya) => ({ dosya }));
    sira = 0;
    goster();
  };
  kok.querySelector("#kamera").onchange = dosyalar;
  kok.querySelector("#galeri").onchange = dosyalar;
  kok.querySelector("#fotografsiz").onclick = () => { kuyruk = [{ dosya: null }]; sira = 0; goster(); };
  kok.querySelector("#link-ac").onclick = () => { const f = kok.querySelector("#link-form"); f.hidden = !f.hidden; if (!f.hidden) f.querySelector("input").focus(); };
  kok.querySelector("#link-form").onsubmit = async (e) => {
    e.preventDefault();
    const url = kok.querySelector("#link").value.trim();
    const durum = kok.querySelector("#link-durum");
    durum.innerHTML = `<p class="kucuk soluk">Sayfa okunuyor…</p>`;
    let bilgi = null, hata = null;
    try {
      const s = await import("../senkron.js");
      bilgi = await s.urunCek(url);
    } catch (err) { hata = err.message; }
    if (!bilgi) {
      durum.innerHTML = `<div class="uyari-kutu">${k(hata || "Linkten otomatik bilgi çekmek için Ayarlar'dan bulut bağlantısını kur.")} Link parçaya kaydedilecek; fotoğrafı sonra ekleyebilirsin.</div>`;
      kuyruk = [{ dosya: null, on: { link: url } }];
    } else {
      durum.innerHTML = "";
      kuyruk = [{ dosya: bilgi.gorsel || null, on: { link: url, ad: bilgi.baslik || "", marka: bilgi.marka || "", fiyat: bilgi.fiyat ?? null, magaza: bilgi.magaza || "" } }];
    }
    sira = 0;
    goster();
  };

  async function isle(oge) {
    if (!oge.dosya || oge.hazir) return;
    oge.hazir = await hazirla(oge.dosya);
    oge.orijinal = oge.hazir;
    if (kok.querySelector("#otomatik").checked) arkaPlan(oge);
  }
  async function arkaPlan(oge) {
    oge.ap = { durum: "calisiyor", oran: null, metin: "Hazırlanıyor" };
    ciz_ilerleme(oge);
    try {
      const sonuc = await arkaPlanKaldir(oge.dosya, (oran, metin) => { oge.ap = { durum: "calisiyor", oran, metin }; ciz_ilerleme(oge); });
      oge.temiz = await hazirla(sonuc, { saydam: true });
      oge.hazir = oge.temiz;
      oge.ap = { durum: "tamam" };
    } catch (e) {
      console.error(e);
      oge.ap = { durum: "hata", metin: "Arka plan silinemedi (" + (e.message || "bilinmeyen hata") + "). Orijinal fotoğraf kullanılacak." };
    }
    if (kuyruk[sira] === oge) { onizle(oge); renkOner(islemKok, oge.hazir.renkler.map((r) => r.id)); }
  }
  function ciz_ilerleme(oge) {
    if (kuyruk[sira] !== oge) return;
    const e = islemKok.querySelector("#ap-durum");
    if (!e) return;
    const a = oge.ap;
    if (!a) { e.innerHTML = ""; return; }
    if (a.durum === "calisiyor") e.innerHTML = `<div class="kucuk soluk">${k(a.metin)}${a.oran != null ? ` %${Math.round(a.oran * 100)}` : "…"}</div><div class="ilerleme"><i style="width:${a.oran != null ? a.oran * 100 : 35}%"></i></div>`;
    else if (a.durum === "hata") e.innerHTML = `<div class="uyari-kutu kucuk">${k(a.metin)}</div>`;
    else e.innerHTML = `<div class="satir kucuk"><span class="etiket iyi">Arka plan silindi</span><button type="button" class="dugme kucuk" id="orijinal">Orijinali kullan</button></div>`;
    const o = e.querySelector("#orijinal");
    if (o) o.onclick = () => { oge.hazir = oge.orijinal; oge.ap = null; onizle(oge); };
  }
  function onizle(oge) {
    const g = islemKok.querySelector("#onizleme");
    if (!g) return;
    if (oge.hazir) {
      if (oge._url) URL.revokeObjectURL(oge._url);
      oge._url = URL.createObjectURL(oge.hazir.blob);
      g.innerHTML = `<img src="${oge._url}" alt="Önizleme">`;
      const oneri = oge.hazir.renkler;
      islemKok.querySelector("#renk-oneri").innerHTML = oneri.length
        ? `Bulunan renkler: ${oneri.map((r) => `<span class="etiket"><span class="renk-nokta" style="background:rgb(${r.rgb.join(",")})"></span>${k(RENK[r.id]?.ad)} %${Math.round(r.oran * 100)}</span>`).join(" ")}`
        : "";
    }
    ciz_ilerleme(oge);
  }

  async function goster() {
    const oge = kuyruk[sira];
    if (!oge) { islemKok.innerHTML = ""; return; }
    const toplu = kuyruk.length > 1;
    islemKok.innerHTML = `
      <div class="kutu">
        <div class="satir ara"><h2>${toplu ? `Parça ${sira + 1} / ${kuyruk.length}` : "Yeni parça"}</h2>${toplu ? `<button class="dugme kucuk" type="button" id="atla">Atla</button>` : ""}</div>
        ${oge.dosya ? `<div class="detay-gorsel" id="onizleme"><p class="soluk">Fotoğraf hazırlanıyor…</p></div><div id="ap-durum"></div><div class="kucuk soluk" id="renk-oneri"></div>` : ""}
        <form id="parca-form" class="yigin" style="gap:14px">${formHtml(oge.on || {}, { kisa: toplu })}</form>
        <button class="dugme ana genis" type="button" id="kaydet">${ikon.onay}${toplu && sira < kuyruk.length - 1 ? "Kaydet, sonrakine geç" : "Kaydet"}</button>
      </div>`;
    formBagla(islemKok.querySelector("#parca-form"));
    islemKok.querySelector("#kaydet").onclick = () => kaydet(oge);
    islemKok.querySelector("#atla")?.addEventListener("click", sonraki);
    islemKok.scrollIntoView({ behavior: "smooth", block: "start" });
    if (oge.dosya) {
      try {
        await isle(oge);
        if (kuyruk[sira] !== oge) return;
        onizle(oge);
        renkOner(islemKok, oge.hazir.renkler.map((r) => r.id));
      } catch (e) {
        islemKok.querySelector("#onizleme").innerHTML = `<p class="hata-kutu">Fotoğraf açılamadı: ${k(e.message)}</p>`;
      }
      // Sonraki fotoğrafı arkada hazırla
      const s = kuyruk[sira + 1];
      if (s && !s.hazir) isle(s).catch(() => {});
    }
  }
  async function kaydet(oge) {
    const btn = islemKok.querySelector("#kaydet");
    btn.disabled = true;
    try {
      const v = formOku(islemKok.querySelector("#parca-form"));
      let gorsel = null;
      if (oge.hazir) gorsel = await veri.gorselYaz({ blob: oge.hazir.blob, kucuk: oge.hazir.kucuk });
      const p = await veri.kaydet("parcalar", { ...(oge.on || {}), ...v, gorsel, durum: "temiz", arsiv: null });
      if (oge._url) URL.revokeObjectURL(oge._url);
      bildir("Kaydedildi");
      if (kuyruk.length === 1) return git(`parca/${p.id}`);
      sonraki();
    } catch (e) {
      btn.disabled = false;
      bildir("Kaydedilemedi: " + e.message);
    }
  }
  function sonraki() {
    sira++;
    if (sira >= kuyruk.length) { bildir(`${kuyruk.length} parça işlendi`); git("gardrop"); return; }
    goster();
  }
}

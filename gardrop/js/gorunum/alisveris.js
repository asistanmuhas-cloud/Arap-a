// S1 istek listesi, S2 eksik analizi, S3 almadan önce test, S4 elden çıkarma önerisi.
import * as veri from "../veri.js";
import { yukle } from "../durum.js";
import { almadanTest } from "../oneri.js";
import { eksikAnalizi, eldenCikarma, gunStr } from "../analiz.js";
import { KATEGORILER, KATEGORI, RENKLER, RENK } from "../sabitler.js";
import { k, para, pencere, bildir, onayla, kolaj, parcaGorsel, gorselleriDoldur, parcaAdi, cipGrubu, cipleriBagla, cipOku, renkCss, ikon } from "../ui.js";
import { git, yenile } from "../app.js";

export const baslik = "Alışveriş";
let sekme = "istek";

export async function ciz(kok) {
  const d = await yukle();
  const istekler = (await veri.hepsi("istek")).filter((x) => !x.alindi).sort((a, b) => (b.olusturma || "").localeCompare(a.olusturma || ""));
  kok.innerHTML = `
    <div class="cipler">${[["istek", `İstek listesi ${istekler.length || ""}`], ["eksik", "Eksikler"], ["cikar", "Elden çıkar"]].map(([id, ad]) => `<button class="cip" type="button" data-sekme="${id}" aria-pressed="${sekme === id}">${k(ad)}</button>`).join("")}</div>
    <div id="icerik" class="yigin" style="gap:14px"></div>`;
  kok.querySelectorAll("[data-sekme]").forEach((b) => (b.onclick = () => { sekme = b.dataset.sekme; yenile(); }));
  const ic = kok.querySelector("#icerik");
  if (sekme === "istek") istekCiz(ic, istekler, d);
  else if (sekme === "eksik") eksikCiz(ic, d);
  else cikarCiz(ic, d);
  gorselleriDoldur(kok);
}

function istekCiz(ic, istekler, d) {
  ic.innerHTML = `
    <button class="dugme ana" type="button" id="ekle">${ikon.arti}İstek ekle</button>
    ${istekler.length ? `<div class="liste">${istekler.map((x) => `<div><span class="kucuk-gorsel"><span class="renk-nokta" style="width:28px;height:28px;background:${renkCss(x.renkler?.[0])}"></span></span>
      <span class="metin"><span>${k(x.ad || KATEGORI[x.kategori]?.ad)}</span><small class="soluk">${[KATEGORI[x.kategori]?.ad, RENK[x.renkler?.[0]]?.ad, para(x.fiyat)].filter(Boolean).map(k).join(" · ")}${x.link ? ` · <a href="${k(x.link)}" target="_blank" rel="noopener">link</a>` : ""}</small></span>
      <span class="satir" style="justify-content:flex-end"><button class="dugme kucuk" type="button" data-test="${x.id}">Test et</button><button class="dugme kucuk" type="button" data-menu="${x.id}">⋯</button></span></div>`).join("")}</div>`
      : `<div class="bos-kutu">Almak istediklerini buraya ekle. "Test et" ile o parçanın gardrobunla kaç yeni kombin açacağını almadan önce gör.</div>`}`;
  ic.querySelector("#ekle").onclick = () => istekForm(null);
  ic.querySelectorAll("[data-test]").forEach((b) => (b.onclick = () => test(istekler.find((x) => x.id === b.dataset.test), d)));
  ic.querySelectorAll("[data-menu]").forEach((b) => (b.onclick = () => istekMenu(istekler.find((x) => x.id === b.dataset.menu))));
}

async function istekForm(x) {
  const pen = pencere({
    baslik: x ? "İsteği düzenle" : "İstek ekle",
    icerik: `<div class="alan"><label for="i-ad">Ne?</label><input type="text" id="i-ad" value="${k(x?.ad)}" placeholder="Ör. Bej trençkot"></div>
      <div class="alan"><span class="etiket-ad">Kategori</span>${cipGrubu("kategori", KATEGORILER, x?.kategori || "ust", { coklu: false })}</div>
      <div class="alan" id="alt-alan"></div>
      <div class="alan"><span class="etiket-ad">Renk</span>${cipGrubu("renk", RENKLER.map((r) => ({ id: r.id, ad: r.ad, renk: renkCss(r.id) })), x?.renkler?.[0], { coklu: false })}</div>
      <div class="iki"><div class="alan"><label for="i-fiyat">Fiyat (₺)</label><input type="number" min="0" id="i-fiyat" value="${k(x?.fiyat ?? "")}"></div><div class="alan"><label for="i-link">Link</label><input type="url" id="i-link" value="${k(x?.link)}"></div></div>
      <div class="alan"><label for="i-not">Not</label><textarea id="i-not">${k(x?.not)}</textarea></div>`,
    alt: `<button class="dugme" data-kapat type="button">Vazgeç</button><button class="dugme ana" type="button" id="kaydet">Kaydet</button>`,
  });
  const g = pen.govde;
  const altCiz = (kat) => (g.querySelector("#alt-alan").innerHTML = `<span class="etiket-ad">Tür</span>${cipGrubu("alt", (KATEGORI[kat]?.alt || []).map((a) => ({ id: a, ad: a })), x?.altKategori, { coklu: false })}`);
  altCiz(x?.kategori || "ust");
  cipleriBagla(g, (ad, v) => { if (ad === "kategori") altCiz(v || "ust"); });
  g.querySelector("#kaydet").onclick = async () => {
    const fiyat = g.querySelector("#i-fiyat").value;
    await veri.kaydet("istek", { ...(x || {}), ad: g.querySelector("#i-ad").value.trim(), kategori: cipOku(g, "kategori") || "ust", altKategori: cipOku(g, "alt") || "", renkler: [cipOku(g, "renk")].filter(Boolean), fiyat: fiyat ? +fiyat : null, link: g.querySelector("#i-link").value.trim(), not: g.querySelector("#i-not").value.trim() });
    pen.kapat(true);
    yenile();
  };
}

async function istekMenu(x) {
  const pen = pencere({
    baslik: x.ad || "İstek",
    icerik: `<div class="yigin"><button class="dugme ana" type="button" id="aldim">Aldım: gardroba ekle</button><button class="dugme" type="button" id="duzenle">Düzenle</button><button class="dugme tehlike" type="button" id="sil">Sil</button></div>`,
  });
  const g = pen.govde;
  g.querySelector("#duzenle").onclick = () => { pen.kapat(); istekForm(x); };
  g.querySelector("#sil").onclick = async () => { await veri.sil("istek", x.id); pen.kapat(); yenile(); };
  g.querySelector("#aldim").onclick = async () => {
    const p = await veri.kaydet("parcalar", { ad: x.ad, kategori: x.kategori, altKategori: x.altKategori, renkler: x.renkler || [], fiyat: x.fiyat, link: x.link, alisTarihi: gunStr(), durum: "temiz", mevsimler: [], ortamlar: [] });
    await veri.guncelle("istek", x.id, { alindi: true });
    pen.kapat();
    bildir("Gardroba eklendi; fotoğrafını ekleyebilirsin");
    git(`parca/${p.id}`);
  };
}

function test(x, d) {
  if (!x.renkler?.length) return bildir("Test için isteğe bir renk seç");
  const t = almadanTest(d.aktif, { kategori: x.kategori, altKategori: x.altKategori, renkler: x.renkler });
  const aday = { id: "__aday__", kategori: x.kategori, altKategori: x.altKategori, renkler: x.renkler, ad: x.ad };
  const harita = new Map([...d.parcaHarita, ["__aday__", aday]]);
  const deger = t.yeni >= 6 ? ["iyi", "Gardrobuna çok iyi oturur."] : t.yeni >= 2 ? ["", "Makul; birkaç yeni kombin açar."] : ["uyari", "Mevcut parçalarınla az kombin çıkar; almadan önce bir daha düşün."];
  pencere({
    baslik: "Almadan önce test",
    icerik: `<div class="sayilar"><div class="sayi"><b>${t.once}</b><small>şimdiki kombin</small></div><div class="sayi"><b>+${t.yeni}</b><small>yeni kombin</small></div><div class="sayi"><b>${x.fiyat && t.yeni ? para(x.fiyat / t.yeni) : "—"}</b><small>yeni kombin başına</small></div></div>
      <div class="${deger[0] === "uyari" ? "uyari-kutu" : "kutu"}">${deger[1]}</div>
      ${t.ornekler.length ? `<b>Örnek kombinler</b><div class="oneri-serit">${t.ornekler.map((ids) => `<div style="width:110px;flex-shrink:0">${kolaj(ids.map((i) => harita.get(i)))}</div>`).join("")}</div>` : ""}`,
  });
  gorselleriDoldur(document.getElementById("pencere"));
}

function eksikCiz(ic, d) {
  const e = eksikAnalizi(d.parcalar);
  ic.innerHTML = `
    <div class="kutu"><div class="satir ara"><h3>Temel parçalar</h3><span class="kucuk soluk">${8 - e.eksik.length}/8 var</span></div>
      ${e.eksik.length ? `<div class="liste">${e.eksik.map((x, i) => `<div><span class="metin"><span>${k(x.ad)}</span></span><button class="dugme kucuk" type="button" data-istek="${i}">İstek listesine</button></div>`).join("")}</div>` : `<p class="soluk" style="margin:0">Temel parçaların tamam.</p>`}</div>
    ${e.denge.length ? `<div class="kutu"><h3>Denge</h3>${e.denge.map((x) => `<p style="margin:0">${k(x)}</p>`).join("")}</div>` : ""}
    <div class="kutu"><div class="satir ara"><h3>Kombine girmeyenler</h3><span class="kucuk soluk">${e.kombinSayisi} uyumlu kombin var</span></div>
      ${e.yetim.length ? `<p class="kucuk soluk" style="margin:0">Bu parçalar renk uyumu nedeniyle hiçbir kombine girmiyor. Nötr renkte bir eşlik parçası işe yarayabilir.</p><div class="liste">${e.yetim.map((p) => `<a href="#/parca/${p.id}"><span class="kucuk-gorsel">${parcaGorsel(p)}</span><span class="metin"><span>${k(parcaAdi(p))}</span></span></a>`).join("")}</div>` : `<p class="soluk" style="margin:0">Her üst ve alt parça en az bir kombine giriyor.</p>`}</div>`;
  ic.querySelectorAll("[data-istek]").forEach((b) => (b.onclick = async () => { const x = e.eksik[+b.dataset.istek]; await veri.kaydet("istek", { ad: x.ad, kategori: x.kategori, altKategori: x.alt, renkler: x.renk ? [x.renk] : [] }); bildir("İstek listesine eklendi"); b.disabled = true; }));
}

function cikarCiz(ic, d) {
  const l = eldenCikarma(d.parcalar, d.harita);
  ic.innerHTML = l.length
    ? `<p class="soluk kucuk" style="margin:0">Uzun süredir giyilmeyen ya da kombine girmeyen parçalar. Satarsan ya da bağışlarsan arşive kaldır; istatistikler korunur.</p>
      <div class="liste">${l.map((x) => `<div><a href="#/parca/${x.parca.id}" class="kucuk-gorsel">${parcaGorsel(x.parca)}</a><span class="metin"><span>${k(parcaAdi(x.parca))}</span><small class="soluk">${x.nedenler.map(k).join(" · ")}</small></span>
        <span class="satir" style="justify-content:flex-end"><button class="dugme kucuk" type="button" data-arsiv="${x.parca.id}" data-neden="satildi">Sattım</button><button class="dugme kucuk" type="button" data-arsiv="${x.parca.id}" data-neden="bagislandi">Bağışladım</button></span></div>`).join("")}</div>`
    : `<div class="bos-kutu">Şu an elden çıkarma önerisi yok. Parçalar 6 ay hiç giyilmeyince ya da bir yıl giyilmeyince burada görünür.</div>`;
  ic.querySelectorAll("[data-arsiv]").forEach((b) => (b.onclick = async () => {
    await veri.guncelle("parcalar", b.dataset.arsiv, { arsiv: { neden: b.dataset.neden, tarih: gunStr() } });
    bildir("Arşive kaldırıldı");
    yenile();
  }));
}

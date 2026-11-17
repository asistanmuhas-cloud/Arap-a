// Parça detayı: bilgiler, A1 giydim, A2 giyim başı maliyet, G5 durum, B3 teslim tarihi, G7 arşiv, düzenleme, fotoğraf.
import * as veri from "../veri.js";
import { yukle, giydim, giyimGeriAl } from "../durum.js";
import { giyimBasiMaliyet, gunStr, gunFarki } from "../analiz.js";
import { KATEGORI, RENK, MEVSIMLER, ORTAMLAR, DESENLER, DURUMLAR, DURUM, ARSIV_NEDENLERI, adBul } from "../sabitler.js";
import { k, para, tarihYaz, pencere, onayla, bildir, parcaGorsel, gorselleriDoldur, parcaAdi, kolaj, ikon, cipGrubu, cipleriBagla, cipOku } from "../ui.js";
import { formHtml, formBagla, formOku } from "./parca-form.js";
import { hazirla, arkaPlanKaldir } from "../gorsel.js";
import { git, yenile } from "../app.js";

export const baslik = "Parça";

export async function ciz(kok, [id]) {
  const d = await yukle();
  const p = d.parcaHarita.get(id);
  if (!p || p.silindi) { kok.innerHTML = `<p class="bos">Parça bulunamadı. <a href="#/gardrop">Gardroba dön</a></p>`; return; }
  const g = d.harita.get(p.id);
  const m = giyimBasiMaliyet(p, d.harita);
  const durum = DURUM[p.durum || "temiz"];
  const kombinler = d.kombinler.filter((x) => x.parcalar.includes(p.id));
  const gecmis = d.giyim.filter((x) => x.parcalar.includes(p.id)).sort((a, b) => b.tarih.localeCompare(a.tarih));
  const bugunGiyildi = gecmis.find((x) => x.tarih === gunStr());
  const bilgi = [
    ["Kategori", [KATEGORI[p.kategori]?.ad, p.altKategori].filter(Boolean).join(" · ")],
    ["Renk", (p.renkler || []).map((r) => RENK[r]?.ad).join(", ")],
    ["Desen", p.desen && p.desen !== "duz" ? adBul(DESENLER, p.desen) : ""],
    ["Mevsim", p.mevsimler?.length ? p.mevsimler.map((x) => adBul(MEVSIMLER, x)).join(", ") : "Her mevsim"],
    ["Ortam", (p.ortamlar || []).map((x) => adBul(ORTAMLAR, x)).join(", ")],
    ["Kumaş", p.kumas], ["Marka", p.marka], ["Beden", p.beden], ["Fiyat", para(p.fiyat)],
    ["Alış", tarihYaz(p.alisTarihi, { day: "numeric", month: "long", year: "numeric" })], ["Mağaza", p.magaza],
  ].filter(([, v]) => v);

  kok.innerHTML = `
    <div class="detay-gorsel">${parcaGorsel(p, { buyuk: true })}</div>
    <div class="satir ara"><h2>${k(parcaAdi(p))}</h2>${p.arsiv ? `<span class="etiket hata">Arşivde: ${k(adBul(ARSIV_NEDENLERI, p.arsiv.neden))}</span>` : `<button class="etiket ${durum.hazir ? "iyi" : "uyari"}" style="border:0;cursor:pointer" id="durum-ac" type="button">${k(durum.ad)} ▾</button>`}</div>
    ${p.teslimTarihi && durum.hatirlat ? `<div class="uyari-kutu">${k(durum.ad)}: teslim ${tarihYaz(p.teslimTarihi)} (${teslimMetni(p.teslimTarihi)})</div>` : ""}
    ${p.arsiv ? "" : `<button class="dugme ${bugunGiyildi ? "" : "ana"} genis" type="button" id="giydim">${ikon.onay}${bugunGiyildi ? "Bugün giyildi · geri al" : "Bugün giydim"}</button>`}
    <div class="sayilar">
      <div class="sayi"><b>${g?.sayi || 0}</b><small>kez giyildi</small></div>
      <div class="sayi"><b>${g?.son ? gunFarki(g.son, gunStr()) : "—"}</b><small>${g?.son ? "gün önce" : "hiç giyilmedi"}</small></div>
      <div class="sayi"><b>${m ? para(m.maliyet) : "—"}</b><small>giyim başı maliyet</small></div>
    </div>
    <dl class="bilgi">${bilgi.map(([a, v]) => `<dt>${k(a)}</dt><dd>${k(v)}</dd>`).join("")}${p.link ? `<dt>Link</dt><dd><a href="${k(p.link)}" target="_blank" rel="noopener">Ürün sayfası</a></dd>` : ""}</dl>
    ${p.not ? `<p style="margin:0;white-space:pre-wrap">${k(p.not)}</p>` : ""}
    <div class="satir">
      <button class="dugme" type="button" id="duzenle">Düzenle</button>
      <label class="dugme">${p.gorsel ? "Fotoğrafı değiştir" : "Fotoğraf ekle"}<input type="file" accept="image/*" id="foto" hidden></label>
      ${p.gorsel ? `<button class="dugme" type="button" id="arka-plan">Arka planı sil</button>` : ""}
      ${p.arsiv ? "" : `<a class="dugme" href="#/kombin-kur/yeni/${p.id}">Bununla kombin kur</a>`}
    </div>
    ${kombinler.length ? `<section class="bolum"><h3>Bulunduğu kombinler</h3><div class="kombin-liste">${kombinler.map((x) => `<a class="kombin-kart" href="#/kombin/${x.id}">${kolaj(x.parcalar.map((i) => d.parcaHarita.get(i)).filter(Boolean))}<span class="ad">${k(x.ad || "Kombin")}</span></a>`).join("")}</div></section>` : ""}
    ${gecmis.length ? `<section class="bolum"><h3>Giyim geçmişi</h3><div class="liste">${gecmis.slice(0, 20).map((x) => `<div><span class="metin"><span>${tarihYaz(x.tarih, { day: "numeric", month: "long", year: "numeric", weekday: "short" })}</span>${x.etkinlik ? `<small class="soluk">${k(x.etkinlik)}</small>` : ""}</span><button class="dugme kucuk" type="button" data-geri="${x.id}">Sil</button></div>`).join("")}</div></section>` : ""}
    <div class="satir" style="margin-top:8px">
      ${p.arsiv ? `<button class="dugme" type="button" id="arsivden">Gardroba geri al</button>` : `<button class="dugme" type="button" id="arsivle">Arşive kaldır</button>`}
      <button class="dugme tehlike" type="button" id="sil">Sil</button>
    </div>`;
  gorselleriDoldur(kok);

  kok.querySelector("#giydim")?.addEventListener("click", async () => {
    if (bugunGiyildi) { await giyimGeriAl(bugunGiyildi.id); bildir("Geri alındı"); }
    else { await giydim({ parcalar: [p.id] }); bildir("Bugün giyildi olarak kaydedildi"); }
    yenile();
  });
  kok.querySelectorAll("[data-geri]").forEach((b) => (b.onclick = async () => { await giyimGeriAl(b.dataset.geri); yenile(); }));
  kok.querySelector("#durum-ac")?.addEventListener("click", () => durumPenceresi(p));
  kok.querySelector("#duzenle").onclick = () => duzenle(p);
  kok.querySelector("#foto").onchange = (e) => fotografDegistir(p, e.target.files[0], false);
  kok.querySelector("#arka-plan")?.addEventListener("click", async (e) => {
    const gorsel = await veri.gorselOku(p.gorsel);
    if (!gorsel) return;
    e.target.disabled = true;
    fotografDegistir(p, gorsel.blob, true, e.target);
  });
  kok.querySelector("#arsivle")?.addEventListener("click", () => arsivle(p));
  kok.querySelector("#arsivden")?.addEventListener("click", async () => { await veri.guncelle("parcalar", p.id, { arsiv: null }); bildir("Gardroba geri alındı"); yenile(); });
  kok.querySelector("#sil").onclick = async () => {
    if (!(await onayla("Bu parça ve giyim kayıtlarındaki izi kalıcı olarak silinecek. Satıldıysa ya da bağışlandıysa arşive kaldırman istatistikleri korur.", { evet: "Sil", tehlike: true }))) return;
    await veri.sil("parcalar", p.id);
    if (p.gorsel) await veri.gorselSil(p.gorsel);
    bildir("Silindi");
    git("gardrop");
  };
}

function teslimMetni(t) {
  const n = gunFarki(gunStr(), t);
  return n < 0 ? `${-n} gün gecikti` : n === 0 ? "bugün" : n === 1 ? "yarın" : `${n} gün sonra`;
}

async function duzenle(p) {
  const pen = pencere({
    baslik: "Parçayı düzenle",
    icerik: `<form id="duzen-form" class="yigin" style="gap:14px">${formHtml(p)}</form>`,
    alt: `<button class="dugme" data-kapat type="button">Vazgeç</button><button class="dugme ana" id="kaydet" type="button">Kaydet</button>`,
  });
  const f = pen.govde.querySelector("#duzen-form");
  formBagla(f);
  pen.govde.querySelector("#kaydet").onclick = async () => {
    await veri.guncelle("parcalar", p.id, formOku(f));
    pen.kapat(true);
    bildir("Güncellendi");
    yenile();
  };
}

// G5 + B3
async function durumPenceresi(p) {
  const pen = pencere({
    baslik: "Durum",
    icerik: `${cipGrubu("durum", DURUMLAR, p.durum || "temiz", { coklu: false })}
      <div class="alan" id="teslim-alan"><label for="teslim">Teslim alma tarihi</label><input type="date" id="teslim" value="${k(p.teslimTarihi || "")}"><small class="soluk">Bu tarih yaklaşınca Bugün ekranında hatırlatılır.</small></div>
      <div class="alan" id="kime-alan"><label for="kime">Kime / nereye</label><input type="text" id="kime" value="${k(p.durumNotu || "")}" placeholder="Ör. Ayşe, Kuru temizleme X"></div>`,
    alt: `<button class="dugme ana" id="kaydet" type="button">Kaydet</button>`,
  });
  const g = pen.govde;
  const goster = () => {
    const v = cipOku(g, "durum") || "temiz";
    g.querySelector("#teslim-alan").hidden = !DURUM[v].hatirlat && v !== "odunc";
    g.querySelector("#kime-alan").hidden = v === "temiz" || v === "kirli";
  };
  cipleriBagla(g, goster);
  goster();
  g.querySelector("#kaydet").onclick = async () => {
    const v = cipOku(g, "durum") || "temiz";
    const yeni = v !== (p.durum || "temiz");
    await veri.guncelle("parcalar", p.id, {
      durum: v,
      durumTarihi: yeni ? gunStr() : p.durumTarihi || gunStr(),
      teslimTarihi: v === "temiz" || v === "kirli" ? null : g.querySelector("#teslim").value || null,
      durumNotu: v === "temiz" || v === "kirli" ? "" : g.querySelector("#kime").value.trim(),
    });
    pen.kapat(true);
    yenile();
  };
}

// G7
async function arsivle(p) {
  const pen = pencere({
    baslik: "Arşive kaldır",
    icerik: `<p class="soluk" style="margin:0">Arşivdeki parçalar öneriye girmez ama geçmişi ve istatistiği korunur.</p>${cipGrubu("neden", ARSIV_NEDENLERI, "bagislandi", { coklu: false })}
      <div class="alan"><label for="satis">Satış fiyatı (₺, isteğe bağlı)</label><input type="number" min="0" id="satis"></div>`,
    alt: `<button class="dugme" data-kapat type="button">Vazgeç</button><button class="dugme ana" id="kaydet" type="button">Arşive kaldır</button>`,
  });
  cipleriBagla(pen.govde);
  pen.govde.querySelector("#kaydet").onclick = async () => {
    const satis = pen.govde.querySelector("#satis").value;
    await veri.guncelle("parcalar", p.id, { arsiv: { neden: cipOku(pen.govde, "neden") || "bagislandi", tarih: gunStr(), satis: satis ? +satis : null } });
    pen.kapat(true);
    bildir("Arşive kaldırıldı");
    yenile();
  };
}

async function fotografDegistir(p, dosya, arkaPlanSil, dugme) {
  if (!dosya) return;
  try {
    let blob = dosya;
    if (arkaPlanSil) {
      bildir("Arka plan siliniyor… İlk seferde model indirilir.");
      blob = await arkaPlanKaldir(dosya, (oran, metin) => { if (dugme) dugme.textContent = metin + (oran != null ? ` %${Math.round(oran * 100)}` : "…"); });
    }
    const h = await hazirla(blob, { saydam: arkaPlanSil });
    const eski = p.gorsel;
    const id = await veri.gorselYaz({ blob: h.blob, kucuk: h.kucuk });
    await veri.guncelle("parcalar", p.id, { gorsel: id, ...(p.renkler?.length ? {} : { renkler: h.renkler.map((r) => r.id) }) });
    if (eski) await veri.gorselSil(eski);
    bildir(arkaPlanSil ? "Arka plan silindi" : "Fotoğraf güncellendi");
    yenile();
  } catch (e) {
    console.error(e);
    bildir("İşlem başarısız: " + e.message);
    if (dugme) { dugme.disabled = false; dugme.textContent = "Arka planı sil"; }
  }
}

// Kombin detayı: K6 puan/favori, A1 giydim, P1 takvime ekle (+P4 tekrar uyarısı), X2 görsel paylaş.
import * as veri from "../veri.js";
import { yukle, giydim, giyimGeriAl, kombinParcalari } from "../durum.js";
import { renkUyumu } from "../renk.js";
import { gunStr, tekrarUyarisi } from "../analiz.js";
import { kombinGorseli } from "../gorsel.js";
import { RENK, ORTAMLAR, adBul } from "../sabitler.js";
import { k, tarihYaz, pencere, onayla, bildir, parcaKart, kolaj, gorselleriDoldur, parcaAdi, ikon } from "../ui.js";
import { git, yenile } from "../app.js";

export const baslik = "Kombin";

export async function ciz(kok, [id]) {
  const d = await yukle();
  const x = d.kombinler.find((y) => y.id === id);
  if (!x) { kok.innerHTML = `<p class="bos">Kombin bulunamadı. <a href="#/kombinler">Kombinlere dön</a></p>`; return; }
  const parcalar = kombinParcalari(x, d.parcaHarita);
  const r = renkUyumu(parcalar.map((p) => p.renkler?.[0]));
  const gecmis = d.giyim.filter((g) => g.kombin === x.id).sort((a, b) => b.tarih.localeCompare(a.tarih));
  const bugun = gecmis.find((g) => g.tarih === gunStr());
  const planlar = d.plan.filter((p) => p.kombin === x.id && p.tarih >= gunStr()).sort((a, b) => a.tarih.localeCompare(b.tarih));
  const hazirDegil = parcalar.filter((p) => p.arsiv || (p.durum && p.durum !== "temiz"));
  kok.innerHTML = `
    <div style="max-width:420px;width:100%;margin:0 auto">${kolaj(parcalar)}</div>
    <div class="satir ara"><h2>${k(x.ad || "Kombin")}</h2><button class="dugme kucuk" type="button" id="favori" aria-pressed="${!!x.favori}">${x.favori ? "♥ Favori" : "♡ Favorilere ekle"}</button></div>
    <div class="satir" id="yildizlar" role="group" aria-label="Puan">${[1, 2, 3, 4, 5].map((n) => `<button type="button" class="cip" data-puan="${n}" aria-label="${n} yıldız" style="font-size:18px;padding:2px 8px"><span class="${n <= (x.puan || 0) ? "yildiz" : "soluk"}">★</span></button>`).join("")}</div>
    <div class="nedenler"><span class="etiket ${r.puan >= 0.7 ? "iyi" : r.puan < 0.5 ? "uyari" : ""}">${k(r.neden)}</span>${(x.ortamlar || []).map((o) => `<span class="etiket">${k(adBul(ORTAMLAR, o))}</span>`).join("")}${x.begenmedi ? '<span class="etiket uyari">Beğenilmedi: öneriye girmez</span>' : ""}</div>
    ${hazirDegil.length ? `<div class="uyari-kutu">Hazır olmayan parça: ${hazirDegil.map((p) => k(parcaAdi(p))).join(", ")}</div>` : ""}
    <button class="dugme ${bugun ? "" : "ana"} genis" type="button" id="giydim">${ikon.onay}${bugun ? "Bugün giyildi · geri al" : "Bugün bunu giydim"}</button>
    <div class="iki"><button class="dugme" type="button" id="takvim">Takvime ekle</button><button class="dugme" type="button" id="paylas">${ikon.paylas}Görsel olarak paylaş</button></div>
    ${planlar.length ? `<div class="kucuk soluk">Planlandı: ${planlar.map((p) => tarihYaz(p.tarih)).join(", ")}</div>` : ""}
    <section class="bolum"><h3>Parçalar</h3><div class="izgara">${parcalar.map((p) => parcaKart(p, { href: `#/parca/${p.id}` })).join("")}</div></section>
    ${gecmis.length ? `<section class="bolum"><h3>${gecmis.length} kez giyildi</h3><div class="liste">${gecmis.slice(0, 12).map((g) => `<div><span class="metin"><span>${tarihYaz(g.tarih, { weekday: "short", day: "numeric", month: "long", year: "numeric" })}</span>${g.etkinlik ? `<small class="soluk">${k(g.etkinlik)}</small>` : ""}</span><button class="dugme kucuk" type="button" data-geri="${g.id}">Sil</button></div>`).join("")}</div></section>` : ""}
    <div class="satir"><a class="dugme" href="#/kombin-kur/${x.id}">Düzenle</a>${x.begenmedi ? `<button class="dugme" type="button" id="begen">Öneriye geri al</button>` : ""}<button class="dugme tehlike" type="button" id="sil">Sil</button></div>`;
  gorselleriDoldur(kok);

  kok.querySelector("#favori").onclick = async () => { await veri.guncelle("kombinler", x.id, { favori: !x.favori, begenmedi: false, gizli: false }); yenile(); };
  kok.querySelector("#yildizlar").onclick = async (e) => {
    const b = e.target.closest("[data-puan]");
    if (!b) return;
    const n = +b.dataset.puan;
    await veri.guncelle("kombinler", x.id, { puan: n === x.puan ? 0 : n, begenmedi: n <= 1 && n !== x.puan, gizli: false });
    yenile();
  };
  kok.querySelector("#begen")?.addEventListener("click", async () => { await veri.guncelle("kombinler", x.id, { begenmedi: false, gizli: false }); yenile(); });
  kok.querySelector("#giydim").onclick = async () => {
    if (bugun) await giyimGeriAl(bugun.id);
    else {
      await giydim({ parcalar: x.parcalar, kombin: x.id });
      const kirli = await veri.ayarOku("giyinceKirli", false);
      if (kirli) for (const p of parcalar) if (p.kategori !== "ayakkabi" && p.kategori !== "aksesuar" && p.kategori !== "dis") await veri.guncelle("parcalar", p.id, { durum: "kirli", durumTarihi: gunStr() });
    }
    bildir(bugun ? "Geri alındı" : "Bugün giyildi olarak kaydedildi");
    yenile();
  };
  kok.querySelectorAll("[data-geri]").forEach((b) => (b.onclick = async () => { await giyimGeriAl(b.dataset.geri); yenile(); }));
  kok.querySelector("#takvim").onclick = () => takvimeEkle(x, d);
  kok.querySelector("#paylas").onclick = () => paylas(x, parcalar);
  kok.querySelector("#sil").onclick = async () => {
    if (!(await onayla("Kombin silinecek. Giyim geçmişi parçalarda kalır.", { evet: "Sil", tehlike: true }))) return;
    await veri.sil("kombinler", x.id);
    for (const p of d.plan.filter((p) => p.kombin === x.id && p.tarih >= gunStr())) await veri.sil("plan", p.id);
    git("kombinler");
  };
}

// P1 + P4
export async function takvimeEkle(x, d, tarih = gunStr()) {
  const pen = pencere({
    baslik: "Takvime ekle",
    icerik: `<div class="iki"><div class="alan"><label for="t-tarih">Gün</label><input type="date" id="t-tarih" value="${tarih}"></div>
      <div class="alan"><label for="t-etkinlik">Etkinlik / kimlerle</label><input type="text" id="t-etkinlik" placeholder="Ör. Ofis, Ali'nin düğünü" list="etkinlikler"></div></div>
      <datalist id="etkinlikler">${[...new Set([...d.plan, ...d.giyim].map((p) => p.etkinlik).filter(Boolean))].map((e) => `<option value="${k(e)}">`).join("")}</datalist>
      <div id="uyari"></div>`,
    alt: `<button class="dugme" data-kapat type="button">Vazgeç</button><button class="dugme ana" type="button" id="kaydet">Ekle</button>`,
  });
  const g = pen.govde;
  const kayitlar = [...d.giyim.map((y) => ({ ...y })), ...d.plan.map((p) => ({ ...p, parcalar: d.kombinler.find((z) => z.id === p.kombin)?.parcalar || [] }))];
  const kontrol = () => {
    const w = tekrarUyarisi({ parcalar: x.parcalar, kombin: x.id, tarih: g.querySelector("#t-tarih").value, etkinlik: g.querySelector("#t-etkinlik").value }, kayitlar);
    g.querySelector("#uyari").innerHTML = w.length
      ? `<div class="${w[0].guclu ? "hata-kutu" : "uyari-kutu"}">${w[0].guclu ? `Bu kombini aynı etkinlikte (${k(w[0].etkinlik)}) ${tarihYaz(w[0].tarih)} günü de giydin/planladın.` : `${w[0].tur === "ayni" ? "Aynı kombin" : "Çok benzer bir kombin"} ${w[0].gun} gün ${w[0].tarih < g.querySelector("#t-tarih").value ? "önce" : "sonra"} (${tarihYaz(w[0].tarih)}${w[0].etkinlik ? ", " + k(w[0].etkinlik) : ""}) var.`}</div>`
      : "";
  };
  g.querySelector("#t-tarih").oninput = kontrol;
  g.querySelector("#t-etkinlik").oninput = kontrol;
  kontrol();
  g.querySelector("#kaydet").onclick = async () => {
    const t = g.querySelector("#t-tarih").value;
    if (!t) return;
    const ayni = d.plan.find((p) => p.tarih === t);
    if (ayni) await veri.guncelle("plan", ayni.id, { kombin: x.id, etkinlik: g.querySelector("#t-etkinlik").value.trim(), giyildi: false });
    else await veri.kaydet("plan", { tarih: t, kombin: x.id, etkinlik: g.querySelector("#t-etkinlik").value.trim(), giyildi: false });
    pen.kapat(true);
    bildir(`${tarihYaz(t)} gününe eklendi`);
  };
  return pen.sonuc;
}

// X2
async function paylas(x, parcalar) {
  bildir("Görsel hazırlanıyor…");
  const ogeler = await Promise.all(parcalar.map(async (p) => ({ blob: p.gorsel ? (await veri.gorselOku(p.gorsel))?.blob : null, ad: parcaAdi(p), renk: RENK[p.renkler?.[0]]?.rgb })));
  const blob = await kombinGorseli(ogeler, x.ad || "Bugünkü kombinim");
  const dosya = new File([blob], `kombin-${(x.ad || "gardrop").toLocaleLowerCase("tr").replace(/[^a-z0-9ğüşıöç]+/g, "-")}.png`, { type: "image/png" });
  if (navigator.canShare?.({ files: [dosya] })) {
    try { await navigator.share({ files: [dosya], title: x.ad || "Kombin" }); return; } catch (e) { if (e.name === "AbortError") return; }
  }
  const url = URL.createObjectURL(blob);
  const pen = pencere({ baslik: "Kombin görseli", icerik: `<img src="${url}" alt="Kombin görseli" style="border-radius:12px">`, alt: `<a class="dugme ana" href="${url}" download="${k(dosya.name)}">İndir</a>` });
  pen.sonuc.then(() => setTimeout(() => URL.revokeObjectURL(url), 1000));
}

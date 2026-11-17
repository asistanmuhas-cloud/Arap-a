// Bugün: hava (P2), hatırlatmalar (B3), günün planı (P1), öneri (K4), unutulanlar (A3).
import { yukle, giydim, kombinParcalari } from "../durum.js";
import { oner, mevsimBul } from "../oneri.js";
import { gunStr, hatirlatmalar, unutulanlar, gunFarki } from "../analiz.js";
import * as hava from "../hava.js";
import { k, tarihYaz, bildir, kolaj, gorselleriDoldur, parcaAdi, parcaKart, ikon } from "../ui.js";
import { oneriHtml, oneriBagla } from "./oneri-kart.js";
import { DURUM } from "../sabitler.js";
import { yenile } from "../app.js";

export const baslik = "Bugün";

export async function ciz(kok) {
  const d = await yukle();
  const bugun = gunStr();
  const t = await hava.tahmin().catch(() => null);
  const h = t?.gunler.get(bugun);
  const sicaklik = hava.kombinSicakligi(h);
  const plan = d.plan.find((p) => p.tarih === bugun);
  const kombin = plan && d.kombinler.find((x) => x.id === plan.kombin);
  const giyilen = d.giyim.filter((g) => g.tarih === bugun);
  const hz = hatirlatmalar(d.parcalar, bugun);
  const unutulan = unutulanlar(d.parcalar, d.harita, bugun).filter((x) => !x.hic || x.gun > 120);
  const oneriler = d.aktif.length ? oner(d.parcalar, { sicaklik, mevsim: mevsimBul() }, d.baglam, { adet: 2 }) : [];
  const konum = await hava.konum();

  kok.innerHTML = `
    <p class="soluk" style="margin:0">${tarihYaz(bugun, { weekday: "long", day: "numeric", month: "long" })}</p>
    ${h ? `<div class="kutu hava"><span style="font-size:36px">${hava.durumAdi(h.kod)[1]}</span><div style="flex:1"><b>${Math.round(t.simdi?.sicaklik ?? sicaklik)}°</b><div class="kucuk soluk">${k(hava.durumAdi(h.kod)[0])} · ${Math.round(h.min)}–${Math.round(h.max)}°C${h.yagis ? ` · yağış %${h.yagis}` : ""} · ${k(konum?.kisa || "")}</div></div></div>`
      : `<div class="kutu satir ara"><span class="soluk">Hava durumuna göre öneri için şehrini seç.</span><a class="dugme kucuk" href="#/ayarlar">Şehir seç</a></div>`}
    ${hz.length ? `<section class="bolum"><h3>Hatırlatmalar</h3><div class="liste">${hz.map((x) => `<a href="#/parca/${x.parca.id}"><span class="metin"><span>${k(parcaAdi(x.parca))} · ${k(DURUM[x.parca.durum].ad)}</span><small class="${x.acil ? "" : "soluk"}" style="${x.acil ? "color:var(--hata)" : ""}">${x.kalan == null ? `${x.gecen ?? 0} gündür orada` : x.kalan < 0 ? `Teslim ${-x.kalan} gün gecikti` : x.kalan === 0 ? "Bugün teslim al" : `Teslime ${x.kalan} gün`}${x.parca.durumNotu ? " · " + k(x.parca.durumNotu) : ""}</small></span></a>`).join("")}</div></section>` : ""}
    ${kombin ? `<section class="kutu"><div class="satir ara"><h2>Bugünün planı</h2>${plan.etkinlik ? `<span class="etiket">${k(plan.etkinlik)}</span>` : ""}</div>
        <a href="#/kombin/${kombin.id}" style="max-width:240px">${kolaj(kombinParcalari(kombin, d.parcaHarita))}</a>
        ${plan.giyildi || giyilen.some((g) => g.kombin === kombin.id) ? `<span class="etiket iyi">Giyildi</span>` : `<button class="dugme ana" type="button" id="plan-giydim">${ikon.onay}Planı giydim</button>`}</section>` : ""}
    ${giyilen.length && !kombin ? `<section class="kutu"><h3>Bugün giydiklerin</h3>${giyilen.map((g) => `<div class="oneri-serit">${g.parcalar.map((i) => d.parcaHarita.get(i)).filter(Boolean).map((p) => parcaKart(p, { href: `#/parca/${p.id}` })).join("")}</div>`).join("")}</section>` : ""}
    <section class="bolum">
      <div class="bolum-bas"><h2>${kombin ? "Başka bir şey?" : "Bugün için öneri"}</h2><a class="kucuk" href="#/kombinler">Daha fazla →</a></div>
      <div id="oneriler" class="yigin">${d.aktif.length < 3 ? `<div class="bos-kutu">Öneri için en az bir üst, bir alt (ya da elbise) ve tercihen ayakkabı ekle.<a class="dugme ana" href="#/ekle">${ikon.arti}Parça ekle</a></div>` : oneriler.length ? oneriler.map((o, i) => oneriHtml(o, d.parcaHarita, i)).join("") : `<div class="uyari-kutu">Bugünün hava ve mevsimine uygun temiz parça kombini bulunamadı. Kirli parçaları temizle ya da mevsim etiketlerini kontrol et.</div>`}</div>
    </section>
    ${unutulan.length ? `<section class="bolum"><div class="bolum-bas"><h3>Unutulanlar</h3><a class="kucuk" href="#/analiz">Tümü →</a></div><p class="kucuk soluk" style="margin:0">Bir süredir giymediklerin; bugün birini dene.</p><div class="oneri-serit">${unutulan.slice(0, 8).map((x) => parcaKart(x.parca, { href: `#/parca/${x.parca.id}`, rozet: `<span class="etiket">${x.gun} gün</span>` })).join("")}</div></section>` : ""}`;
  gorselleriDoldur(kok);
  kok.querySelector("#plan-giydim")?.addEventListener("click", async () => {
    await giydim({ parcalar: kombin.parcalar, kombin: kombin.id, etkinlik: plan.etkinlik });
    bildir("Bugün giyildi olarak kaydedildi");
    yenile();
  });
  oneriBagla(kok.querySelector("#oneriler"), oneriler, d.kombinler, (e) => { if (e !== "kaydet") yenile(); });
}

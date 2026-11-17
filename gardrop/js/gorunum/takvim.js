// P1 kombin takvimi + P2 günlük hava. Ay görünümü; güne dokununca planla / öner / giydim.
import * as veri from "../veri.js";
import { yukle, giydim, kombinParcalari } from "../durum.js";
import { oner, mevsimBul } from "../oneri.js";
import * as hava from "../hava.js";
import { gunStr } from "../analiz.js";
import { k, tarihYaz, pencere, bildir, parcaGorsel, kolaj, gorselleriDoldur, ikon } from "../ui.js";
import { oneriHtml, oneriBagla } from "./oneri-kart.js";
import { takvimeEkle } from "./kombin.js";
import { yenile } from "../app.js";

export const baslik = "Takvim";
let ay = null; // 'YYYY-MM'

export async function ciz(kok) {
  const d = await yukle();
  const t = await hava.tahmin().catch(() => null);
  const bugun = gunStr();
  ay ||= bugun.slice(0, 7);
  const [y, a] = ay.split("-").map(Number);
  const ilk = new Date(y, a - 1, 1);
  const bas = new Date(ilk); bas.setDate(1 - ((ilk.getDay() + 6) % 7));
  const gunler = [];
  for (let i = 0; i < 42; i++) { const g = new Date(bas); g.setDate(bas.getDate() + i); gunler.push(gunStr(g)); }
  while (gunler.length > 35 && gunler.slice(-7).every((g) => g.slice(0, 7) !== ay)) gunler.splice(-7);
  const planHarita = new Map(d.plan.map((p) => [p.tarih, p]));
  const giyimHarita = new Map();
  for (const g of d.giyim) (giyimHarita.get(g.tarih) || giyimHarita.set(g.tarih, []).get(g.tarih)).push(g);

  const hucre = (g) => {
    const p = planHarita.get(g);
    const giyilen = giyimHarita.get(g);
    const kombin = p && d.kombinler.find((x) => x.id === p.kombin);
    const parcalar = kombin ? kombinParcalari(kombin, d.parcaHarita) : giyilen ? giyilen[0].parcalar.map((i) => d.parcaHarita.get(i)).filter(Boolean) : [];
    const h = t?.gunler.get(g);
    return `<button type="button" class="gun ${g.slice(0, 7) !== ay ? "disari" : ""} ${g === bugun ? "bugun" : ""} ${giyilen ? "giyildi" : ""}" data-gun="${g}" aria-label="${tarihYaz(g, { weekday: "long", day: "numeric", month: "long" })}">
      <span class="no">${+g.slice(8)}</span>${h ? `<span class="hv">${hava.durumAdi(h.kod)[1]} ${Math.round(h.max)}°</span>` : ""}
      <span class="mini">${parcalar.slice(0, 4).map((x) => x.gorsel ? `<img data-gorsel="${k(x.gorsel)}" alt="">` : `<span class="renk-nokta" style="width:100%;height:100%;border-radius:4px;background:var(--yuzey2)"></span>`).join("")}</span></button>`;
  };
  const ayAdi = ilk.toLocaleDateString("tr-TR", { month: "long", year: "numeric" });
  const yaklasan = d.plan.filter((p) => p.tarih >= bugun).sort((x, z) => x.tarih.localeCompare(z.tarih)).slice(0, 5);
  kok.innerHTML = `
    <div class="takvim-bas"><button class="dugme kucuk" type="button" data-ay="-1" aria-label="Önceki ay">‹</button><h2>${k(ayAdi)}</h2><button class="dugme kucuk" type="button" data-ay="1" aria-label="Sonraki ay">›</button></div>
    <div class="hafta">${["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"].map((g) => `<span class="gun-ad">${g}</span>`).join("")}${gunler.map(hucre).join("")}</div>
    ${!t ? `<p class="kucuk soluk" style="margin:0">Günlere hava durumu eklemek için <a href="#/ayarlar">şehrini seç</a>.</p>` : ""}
    <section class="bolum"><div class="bolum-bas"><h3>Yaklaşan planlar</h3>${ay !== bugun.slice(0, 7) ? `<button class="dugme kucuk" type="button" id="bugune">Bugüne dön</button>` : ""}</div>
      ${yaklasan.length ? `<div class="liste">${yaklasan.map((p) => { const x = d.kombinler.find((z) => z.id === p.kombin); return x ? `<a href="#/kombin/${x.id}"><span class="kucuk-gorsel">${kolaj(kombinParcalari(x, d.parcaHarita).slice(0, 1))}</span><span class="metin"><span>${tarihYaz(p.tarih, { weekday: "long", day: "numeric", month: "long" })}</span><small class="soluk">${k(x.ad || "Kombin")}${p.etkinlik ? " · " + k(p.etkinlik) : ""}</small></span></a>` : ""; }).join("")}</div>` : `<p class="soluk kucuk" style="margin:0">Planlı gün yok. Bir güne dokunup kombin seç; Pazar günü haftayı planlamak sabahları kolaylaştırır.</p>`}
    </section>`;
  gorselleriDoldur(kok);
  kok.querySelectorAll("[data-ay]").forEach((b) => (b.onclick = () => {
    const n = new Date(y, a - 1 + +b.dataset.ay, 1);
    ay = `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, "0")}`;
    yenile();
  }));
  kok.querySelector("#bugune")?.addEventListener("click", () => { ay = bugun.slice(0, 7); yenile(); });
  kok.querySelector(".hafta").onclick = (e) => {
    const g = e.target.closest("[data-gun]");
    if (g) gunPenceresi(g.dataset.gun, d, t);
  };
}

async function gunPenceresi(g, d, t) {
  const p = d.plan.find((x) => x.tarih === g);
  const kombin = p && d.kombinler.find((x) => x.id === p.kombin);
  const giyilen = d.giyim.filter((x) => x.tarih === g);
  const h = t?.gunler.get(g);
  const sicaklik = hava.kombinSicakligi(h);
  const gecmis = g < gunStr();
  const pen = pencere({
    baslik: tarihYaz(g, { weekday: "long", day: "numeric", month: "long" }),
    icerik: `
      ${h ? `<div class="hava"><span style="font-size:30px">${hava.durumAdi(h.kod)[1]}</span><div><b style="font-size:20px">${Math.round(h.min)}–${Math.round(h.max)}°C</b><div class="kucuk soluk">${k(hava.durumAdi(h.kod)[0])}${h.yagis ? ` · yağış %${h.yagis}` : ""}</div></div></div>${hava.yagisli(h) ? `<div class="uyari-kutu kucuk">Yağış bekleniyor: süet ve deri ayakkabıdan kaçın, yağmurluk düşün.</div>` : ""}` : ""}
      ${kombin ? `<div class="kutu"><div class="satir ara"><b>Plan: ${k(kombin.ad || "Kombin")}</b>${p.etkinlik ? `<span class="etiket">${k(p.etkinlik)}</span>` : ""}</div><a href="#/kombin/${kombin.id}" style="max-width:200px">${kolaj(kombinParcalari(kombin, d.parcaHarita))}</a>
        <div class="satir">${!p.giyildi && g <= gunStr() ? `<button class="dugme kucuk ana" type="button" id="giydim">${ikon.onay}Giydim</button>` : ""}<button class="dugme kucuk" type="button" id="degistir">Değiştir</button><button class="dugme kucuk tehlike" type="button" id="kaldir">Plandan çıkar</button></div></div>` : ""}
      ${giyilen.length ? `<div class="yigin"><b>Giyilenler</b>${giyilen.map((x) => `<div class="oneri-serit">${x.parcalar.map((i) => d.parcaHarita.get(i)).filter(Boolean).map((pp) => `<a class="parca-kart" href="#/parca/${pp.id}" style="width:72px"><span class="gorsel">${parcaGorsel(pp)}</span></a>`).join("")}</div>`).join("")}</div>` : ""}
      ${!kombin && !gecmis ? `<div class="iki"><button class="dugme ana" type="button" id="oner">Bu güne öner</button><button class="dugme" type="button" id="sec">Kayıtlı kombinden seç</button></div>` : ""}
      ${!kombin && gecmis && !giyilen.length ? `<p class="soluk" style="margin:0">Bu güne kayıt yok.</p>` : ""}
      <div id="gun-oneri" class="yigin"></div>`,
  });
  const gv = pen.govde;
  gorselleriDoldur(gv);
  const kapatYenile = () => { pen.kapat(true); yenile(); };
  gv.querySelector("#giydim")?.addEventListener("click", async () => { await giydim({ parcalar: kombin.parcalar, kombin: kombin.id, tarih: g, etkinlik: p.etkinlik }); bildir("Giyildi olarak kaydedildi"); kapatYenile(); });
  gv.querySelector("#kaldir")?.addEventListener("click", async () => { await veri.sil("plan", p.id); kapatYenile(); });
  const sec = async () => {
    const liste = d.kombinler.filter((x) => !x.gizli && !x.begenmedi);
    const e = gv.querySelector("#gun-oneri");
    e.innerHTML = liste.length ? `<div class="kombin-liste">${liste.map((x) => `<button type="button" class="kombin-kart" data-kombin="${x.id}" style="cursor:pointer;text-align:left">${kolaj(kombinParcalari(x, d.parcaHarita))}<span class="ad">${k(x.ad || "Kombin")}</span></button>`).join("")}</div>` : `<p class="soluk">Kayıtlı kombin yok.</p>`;
    gorselleriDoldur(e);
    e.onclick = async (ev) => {
      const b = ev.target.closest("[data-kombin]");
      if (!b) return;
      pen.kapat(true);
      await takvimeEkle(d.kombinler.find((x) => x.id === b.dataset.kombin), d, g);
      yenile();
    };
  };
  gv.querySelector("#sec")?.addEventListener("click", sec);
  gv.querySelector("#degistir")?.addEventListener("click", sec);
  gv.querySelector("#oner")?.addEventListener("click", () => {
    const liste = oner(d.parcalar, { sicaklik, mevsim: mevsimBul(new Date(g + "T12:00")) }, d.baglam, { adet: 3 });
    const e = gv.querySelector("#gun-oneri");
    if (!liste.length) { e.innerHTML = `<div class="uyari-kutu">Öneri için yeterli temiz parça yok.</div>`; return; }
    e.innerHTML = liste.map((o, i) => oneriHtml(o, d.parcaHarita, i).replace("Bugün bunu giydim", "Bu güne planla")).join("");
    // "giydim" düğmesi burada planlama yapar
    e.querySelectorAll('[data-eylem="giydim"]').forEach((b) => (b.dataset.eylem = "planla"));
    oneriBagla(e, liste, d.kombinler);
    e.addEventListener("click", async (ev) => {
      const b = ev.target.closest('[data-eylem="planla"]');
      if (!b) return;
      const o = liste[+b.closest("[data-oneri]").dataset.oneri];
      const anahtar = (ids) => [...ids].sort().join("|");
      let x = d.kombinler.find((z) => anahtar(z.parcalar) === anahtar(o.parcalar));
      if (!x) x = await veri.kaydet("kombinler", { parcalar: o.parcalar, ad: "", kaynak: "oneri", favori: false, puan: 0, ortamlar: [], mevsimler: [] });
      else if (x.gizli) await veri.guncelle("kombinler", x.id, { gizli: false, begenmedi: false });
      pen.kapat(true);
      await takvimeEkle(x, { ...d, kombinler: [...d.kombinler, x] }, g);
      yenile();
    });
  });
}

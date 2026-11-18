// A4 istatistik panosu, A2 giyim başı maliyet sıralaması, A3 unutulanlar.
import { yukle } from "../durum.js";
import { istatistik, unutulanlar, giyimBasiMaliyet } from "../analiz.js";
import { k, para, parcaGorsel, gorselleriDoldur, parcaAdi, renkCss } from "../ui.js";

export const baslik = "Analiz";

export async function ciz(kok) {
  const d = await yukle();
  if (!d.parcalar.length) { kok.innerHTML = `<div class="bos-kutu">Analiz için önce gardroba parça ekle ve giydiklerini işaretle.<a class="dugme ana" href="#/ekle">Parça ekle</a></div>`; return; }
  const s = istatistik(d.parcalar, d.giyim);
  const unut = unutulanlar(d.parcalar, d.harita);
  const maliyet = d.aktif.map((p) => ({ p, m: giyimBasiMaliyet(p, d.harita) })).filter((x) => x.m);
  const pahali = maliyet.slice().sort((a, b) => b.m.maliyet - a.m.maliyet).slice(0, 5);
  const verimli = maliyet.filter((x) => x.m.sayi).sort((a, b) => a.m.maliyet - b.m.maliyet).slice(0, 5);
  const enFazlaAy = Math.max(1, ...s.aylar.map((a) => a.n));
  const enFazlaKat = Math.max(1, ...s.kategori.map((x) => x.n));
  const enFazlaDeger = Math.max(1, ...s.deger.kategori.map((x) => x.toplam));
  const satir = (p, sag) => `<a href="#/parca/${p.id}"><span class="kucuk-gorsel">${parcaGorsel(p)}</span><span class="metin"><span>${k(parcaAdi(p))}</span></span><span class="kucuk" style="font-variant-numeric:tabular-nums;text-align:right">${sag}</span></a>`;

  kok.innerHTML = `
    <div class="sayilar">
      <div class="sayi"><b>${s.toplam}</b><small>parça</small></div>
      <div class="sayi"><b>%${Math.round(s.kullanimOrani * 100)}</b><small>en az bir kez giyildi</small></div>
      <div class="sayi"><b>${s.toplamDeger ? para(s.toplamDeger) : "—"}</b><small>gardrop değeri</small></div>
    </div>
    <section class="kutu"><div class="satir ara"><h3>Aylık giyim kaydı</h3><span class="kucuk soluk">kayıtlı gün sayısı</span></div>
      <div class="cubuklar">${s.aylar.map((a) => `<div class="cubuk" style="height:${(a.n / enFazlaAy) * 100}%" title="${a.ay}: ${a.n} gün"></div>`).join("")}</div>
      <div class="cubuk-et">${s.aylar.map((a) => `<span>${new Date(a.ay + "-15").toLocaleDateString("tr-TR", { month: "narrow" })}</span>`).join("")}</div>
    </section>
    ${s.deger.kategori.length ? `<section class="kutu"><div class="satir ara"><h3>Gardrop değeri</h3><span class="kucuk soluk">${para(s.toplamDeger)}</span></div>
      ${s.deger.kategori.map((x) => `<div class="yatay"><span>${k(x.ad)}</span><span class="iz"><i style="width:${(x.toplam / enFazlaDeger) * 100}%"></i></span><b style="white-space:nowrap">${para(x.toplam)}</b></div>`).join("")}
      ${s.deger.yillar.length ? `<div class="kucuk soluk">Yıllık harcama (alış tarihine göre, arşivdekiler dahil)</div><div class="liste">${s.deger.yillar.slice(0, 5).map((y) => `<div><span class="metin"><span>${y.yil}</span><small class="soluk">${y.n} parça</small></span><b class="kucuk" style="font-variant-numeric:tabular-nums">${para(y.toplam)}</b></div>`).join("")}</div>` : ""}
      ${s.deger.arsivGelir ? `<p class="kucuk soluk" style="margin:0">Satılan parçalardan gelen: ${para(s.deger.arsivGelir)}</p>` : ""}
      ${s.deger.fiyatsiz ? `<p class="kucuk soluk" style="margin:0">${s.deger.fiyatsiz} parçanın fiyatı girilmemiş; toplam bunları içermez.</p>` : ""}
    </section>` : ""}
    <section class="kutu"><h3>Kategoriler</h3>${s.kategori.map((x) => `<div class="yatay"><span>${k(x.ad)}</span><span class="iz"><i style="width:${(x.n / enFazlaKat) * 100}%"></i></span><b>${x.n}</b></div>`).join("")}</section>
    <section class="kutu"><h3>Renk dağılımı</h3>
      <div style="display:flex;height:22px;border-radius:6px;overflow:hidden;border:1px solid var(--cizgi)">${s.renk.map((r) => `<span title="${k(r.ad)}: ${r.n}" style="flex:${r.n};background:${renkCss(r.id)}"></span>`).join("")}</div>
      <div class="cipler">${s.renk.slice(0, 8).map((r) => `<span class="etiket"><span class="renk-nokta" style="background:${renkCss(r.id)}"></span>${k(r.ad)} ${r.n}</span>`).join("")}</div>
    </section>
    <section class="kutu"><h3>En çok giyilenler</h3>${s.enCok.length ? `<div class="liste">${s.enCok.map((x) => satir(x.parca, `${x.sayi} kez`)).join("")}</div>` : `<p class="soluk kucuk" style="margin:0">Henüz giyim kaydı yok. Parça ya da kombin ekranında "Bugün giydim"e bas.</p>`}</section>
    <section class="kutu"><div class="satir ara"><h3>Giyim başı maliyet</h3>${s.ortMaliyet ? `<span class="kucuk soluk">ortalama ${para(s.ortMaliyet)}</span>` : ""}</div>
      ${maliyet.length ? `<div class="kucuk soluk">En pahalıya gelenler (fiyat ÷ giyilme)</div><div class="liste">${pahali.map((x) => satir(x.p, `${para(x.m.maliyet)}<br><small class="soluk">${x.m.sayi} kez</small>`)).join("")}</div>
      ${verimli.length ? `<div class="kucuk soluk">Parasını en çok çıkaranlar</div><div class="liste">${verimli.map((x) => satir(x.p, `${para(x.m.maliyet)}<br><small class="soluk">${x.m.sayi} kez</small>`)).join("")}</div>` : ""}`
      : `<p class="soluk kucuk" style="margin:0">Parçalara fiyat eklersen burada her giyimin sana kaça geldiğini görürsün.</p>`}</section>
    <section class="kutu"><div class="satir ara"><h3>Unutulanlar</h3><span class="kucuk soluk">90+ gün giyilmeyen</span></div>
      ${unut.length ? `<div class="liste">${unut.slice(0, 15).map((x) => satir(x.parca, x.hic ? `hiç giyilmedi<br><small class="soluk">${x.gun} gündür</small>` : `${x.gun} gün`)).join("")}</div>` : `<p class="soluk kucuk" style="margin:0">Unutulan parça yok.</p>`}</section>
    <a class="dugme" href="#/alisveris">Eksik analizi ve elden çıkarma önerileri →</a>`;
  gorselleriDoldur(kok);
}

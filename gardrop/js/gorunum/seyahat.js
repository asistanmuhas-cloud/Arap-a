// P3: seyahat bavulu. Gün gün kombin planı (varış şehrinin havasıyla), bavul listesi ve toplandı işaretleri.
import * as veri from "../veri.js";
import { yukle, kombinParcalari } from "../durum.js";
import { oner, mevsimBul, rolu } from "../oneri.js";
import * as hava from "../hava.js";
import { gunStr, gunFarki } from "../analiz.js";
import { KATEGORILER } from "../sabitler.js";
import { k, tarihYaz, pencere, bildir, onayla, kolaj, parcaGorsel, parcaKart, gorselleriDoldur, parcaAdi, ikon } from "../ui.js";
import { git, yenile } from "../app.js";

export const baslik = (p) => (p[0] ? "Seyahat" : "Seyahatler");

export async function ciz(kok, [id]) {
  const seyahatler = (await veri.hepsi("seyahat")).filter((s) => s.tur === "seyahat");
  if (id) return detay(kok, seyahatler.find((s) => s.id === id));
  const d = await yukle();
  kok.innerHTML = `
    <button class="dugme ana" type="button" id="yeni">${ikon.arti}Yeni seyahat</button>
    ${seyahatler.length ? `<div class="liste">${seyahatler.sort((a, b) => b.baslangic.localeCompare(a.baslangic)).map((s) => `<a href="#/seyahat/${s.id}"><span class="metin"><span>${k(s.ad)}</span><small class="soluk">${k(s.sehir?.kisa || "")} · ${tarihYaz(s.baslangic)} – ${tarihYaz(s.bitis)} · ${(s.toplandi || []).length}/${bavul(s, d.kombinler, d.parcaHarita).length} toplandı</small></span>${s.bitis < gunStr() ? '<span class="etiket">Geçti</span>' : ""}</a>`).join("")}</div>`
      : `<div class="bos-kutu">Seyahatin tarihini ve şehrini gir; her güne havaya uygun kombin planla, bavul listesi kendiliğinden çıksın.</div>`}`;
  kok.querySelector("#yeni").onclick = yeniSeyahat;
}

const gunlerArasi = (a, b) => { const l = []; for (let i = 0; i <= gunFarki(a, b) && i < 60; i++) { const d = new Date(a + "T12:00"); d.setDate(d.getDate() + i); l.push(gunStr(d)); } return l; };
// Bavul: günlere atanan kombinlerin parçaları + ekstralar (tekrarsız).
export const bavul = (s, kombinler = null, harita = null) => {
  const ids = new Set(s.ekstra || []);
  for (const kid of Object.values(s.gunler || {})) {
    const x = kombinler?.find((y) => y.id === kid);
    (x?.parcalar || []).forEach((i) => ids.add(i));
  }
  return [...ids].filter((i) => !harita || harita.has(i));
};

async function yeniSeyahat() {
  const bugun = gunStr();
  const pen = pencere({
    baslik: "Yeni seyahat",
    icerik: `<div class="alan"><label for="s-ad">Ad</label><input type="text" id="s-ad" placeholder="Ör. İzmir hafta sonu"></div>
      <div class="alan"><label for="s-sehir">Şehir</label><div class="satir" style="flex-wrap:nowrap"><input type="text" id="s-sehir" placeholder="Şehir ara" style="flex:1"><button class="dugme" type="button" id="ara">Ara</button></div><div id="sonuclar" class="cipler"></div></div>
      <div class="iki"><div class="alan"><label for="s-bas">Gidiş</label><input type="date" id="s-bas" value="${bugun}"></div><div class="alan"><label for="s-bit">Dönüş</label><input type="date" id="s-bit" value="${bugun}"></div></div>`,
    alt: `<button class="dugme" data-kapat type="button">Vazgeç</button><button class="dugme ana" type="button" id="kaydet">Oluştur</button>`,
  });
  const g = pen.govde;
  let sehir = null, sonuc = [];
  g.querySelector("#ara").onclick = async () => {
    const e = g.querySelector("#sonuclar");
    try {
      sonuc = await hava.konumAra(g.querySelector("#s-sehir").value);
      e.innerHTML = sonuc.length ? sonuc.map((s, i) => `<button class="cip" type="button" data-i="${i}" aria-pressed="false">${k(s.ad)}</button>`).join("") : `<span class="kucuk soluk">Bulunamadı</span>`;
    } catch { e.innerHTML = `<span class="kucuk soluk">Arama için internet gerekir. Şehir adı yine de kaydedilir.</span>`; }
  };
  g.querySelector("#sonuclar").onclick = (e) => {
    const b = e.target.closest("[data-i]");
    if (!b) return;
    sehir = sonuc[+b.dataset.i];
    g.querySelectorAll("#sonuclar .cip").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
  };
  g.querySelector("#kaydet").onclick = async () => {
    const bas = g.querySelector("#s-bas").value, bit = g.querySelector("#s-bit").value;
    if (!bas || !bit || bit < bas) return bildir("Dönüş tarihi gidişten önce olamaz");
    const ad = g.querySelector("#s-ad").value.trim() || g.querySelector("#s-sehir").value.trim() || "Seyahat";
    const s = await veri.kaydet("seyahat", { tur: "seyahat", ad, sehir: sehir || (g.querySelector("#s-sehir").value.trim() ? { kisa: g.querySelector("#s-sehir").value.trim() } : null), baslangic: bas, bitis: bit, gunler: {}, ekstra: [], toplandi: [] });
    pen.kapat(true);
    git(`seyahat/${s.id}`);
  };
}

async function detay(kok, s) {
  if (!s) { kok.innerHTML = `<p class="bos">Seyahat bulunamadı. <a href="#/seyahat">Seyahatlere dön</a></p>`; return; }
  const d = await yukle();
  const t = s.sehir?.enlem ? await hava.tahmin(s.sehir).catch(() => null) : null;
  const gunler = gunlerArasi(s.baslangic, s.bitis);
  const liste = bavul(s, d.kombinler, d.parcaHarita);
  const toplandi = new Set(s.toplandi || []);
  const gruplar = KATEGORILER.map((c) => ({ c, l: liste.map((i) => d.parcaHarita.get(i)).filter((p) => p.kategori === c.id) })).filter((x) => x.l.length);
  kok.innerHTML = `
    <div class="satir ara"><div><h2>${k(s.ad)}</h2><span class="soluk kucuk">${k(s.sehir?.ad || s.sehir?.kisa || "")} · ${gunler.length} gün</span></div><button class="dugme kucuk tehlike" type="button" id="sil">Sil</button></div>
    ${t ? "" : `<p class="kucuk soluk" style="margin:0">${s.sehir?.enlem ? "Hava tahmini en fazla 16 gün ilerisi için gelir." : "Hava tahmini için şehri aramadan seçmek gerekir."}</p>`}
    <section class="bolum"><h3>Günler</h3><div class="liste">${gunler.map((g) => {
      const h = t?.gunler.get(g);
      const x = d.kombinler.find((y) => y.id === s.gunler?.[g]);
      return `<div><span class="kucuk-gorsel" style="width:64px;height:64px">${x ? kolaj(kombinParcalari(x, d.parcaHarita)) : ""}</span><span class="metin"><span>${tarihYaz(g, { weekday: "short", day: "numeric", month: "short" })}</span><small class="soluk">${h ? `${hava.durumAdi(h.kod)[1]} ${Math.round(h.min)}–${Math.round(h.max)}°C${h.yagis >= 40 ? ` · yağış %${h.yagis}` : ""}` : ""}${x ? ` · ${k(x.ad || "Kombin")}` : ""}</small></span>
        <span class="satir" style="justify-content:flex-end"><button class="dugme kucuk ${x ? "" : "ana"}" type="button" data-oner="${g}">${x ? "Değiştir" : "Öner"}</button>${x ? `<button class="dugme kucuk" type="button" data-bosalt="${g}">×</button>` : ""}</span></div>`;
    }).join("")}</div>
      <button class="dugme" type="button" id="hepsini">Boş günlerin hepsine öner</button></section>
    <section class="bolum"><div class="bolum-bas"><h3>Bavul</h3><span class="kucuk soluk">${[...toplandi].filter((i) => liste.includes(i)).length}/${liste.length} toplandı</span></div>
      ${gruplar.length ? gruplar.map(({ c, l }) => `<div class="kutu"><b>${k(c.ad)}</b><div class="liste">${l.map((p) => `<label style="cursor:pointer"><input type="checkbox" data-topla="${p.id}" ${toplandi.has(p.id) ? "checked" : ""}><span class="kucuk-gorsel">${parcaGorsel(p)}</span><span class="metin"><span style="${toplandi.has(p.id) ? "text-decoration:line-through;opacity:.6" : ""}">${k(parcaAdi(p))}</span>${p.konum ? `<small class="soluk">${k(p.konum)}</small>` : ""}</span>${(s.ekstra || []).includes(p.id) ? `<button class="dugme kucuk" type="button" data-cikar="${p.id}">Çıkar</button>` : ""}</label>`).join("")}</div></div>`).join("") : `<p class="soluk kucuk" style="margin:0">Günlere kombin ekleyince parçalar burada listelenir.</p>`}
      <button class="dugme" type="button" id="ekstra">${ikon.arti}Ekstra parça ekle (pijama, mayo, şarj aleti çantası…)</button></section>`;
  gorselleriDoldur(kok);
  const kaydet = (ek) => veri.guncelle("seyahat", s.id, ek).then(yenile);
  kok.querySelector("#sil").onclick = async () => { if (await onayla("Seyahat silinecek.", { evet: "Sil", tehlike: true })) { await veri.sil("seyahat", s.id); git("seyahat"); } };
  kok.querySelectorAll("[data-topla]").forEach((c) => (c.onchange = () => {
    const y = new Set(s.toplandi || []);
    c.checked ? y.add(c.dataset.topla) : y.delete(c.dataset.topla);
    kaydet({ toplandi: [...y] });
  }));
  kok.querySelectorAll("[data-cikar]").forEach((b) => (b.onclick = (e) => { e.preventDefault(); kaydet({ ekstra: (s.ekstra || []).filter((i) => i !== b.dataset.cikar) }); }));
  kok.querySelectorAll("[data-bosalt]").forEach((b) => (b.onclick = () => { const g = { ...s.gunler }; delete g[b.dataset.bosalt]; kaydet({ gunler: g }); }));
  // Öneri: bavul hafif kalsın diye seyahatte zaten kullanılan parçaları tercih et.
  const gunOner = async (g, kullanilan) => {
    const h = t?.gunler.get(g);
    const kosul = { sicaklik: hava.kombinSicakligi(h), mevsim: mevsimBul(new Date(g + "T12:00")) };
    const adaylar = oner(d.parcalar, kosul, d.baglam, { adet: 12 });
    adaylar.forEach((o) => (o.puan += o.parcalar.filter((i) => kullanilan.has(i)).length * 0.08));
    adaylar.sort((a, b) => b.puan - a.puan);
    return adaylar;
  };
  const kombinBul = async (ids) => {
    const a = [...ids].sort().join("|");
    let x = d.kombinler.find((y) => [...y.parcalar].sort().join("|") === a);
    if (!x) { x = await veri.kaydet("kombinler", { parcalar: ids, ad: "", kaynak: "seyahat", favori: false, puan: 0, ortamlar: ["tatil"], mevsimler: [] }); d.kombinler.push(x); }
    return x;
  };
  kok.querySelectorAll("[data-oner]").forEach((b) => (b.onclick = async () => {
    const g = b.dataset.oner;
    const adaylar = await gunOner(g, new Set(liste));
    const harita = d.parcaHarita;
    const pen = pencere({
      baslik: tarihYaz(g, { weekday: "long", day: "numeric", month: "long" }),
      icerik: adaylar.length ? `<div class="kombin-liste">${adaylar.slice(0, 6).map((o, i) => `<button type="button" class="kombin-kart" data-i="${i}" style="cursor:pointer;text-align:left">${kolaj(o.parcalar.map((x) => harita.get(x)))}<span class="kucuk soluk">${o.parcalar.filter((x) => liste.includes(x)).length} parça zaten bavulda</span></button>`).join("")}</div>
        <b>Kayıtlı kombinlerden</b><div class="kombin-liste">${d.kombinler.filter((x) => !x.gizli && !x.begenmedi).map((x) => `<button type="button" class="kombin-kart" data-kombin="${x.id}" style="cursor:pointer;text-align:left">${kolaj(kombinParcalari(x, harita))}<span class="ad">${k(x.ad || "Kombin")}</span></button>`).join("")}</div>` : `<div class="uyari-kutu">Uygun parça yok.</div>`,
    });
    gorselleriDoldur(pen.govde);
    pen.govde.querySelector(".pencere-govde").onclick = async (e) => {
      const c = e.target.closest("[data-i],[data-kombin]");
      if (!c) return;
      const x = c.dataset.kombin ? d.kombinler.find((y) => y.id === c.dataset.kombin) : await kombinBul(adaylar[+c.dataset.i].parcalar);
      pen.kapat(true);
      kaydet({ gunler: { ...s.gunler, [g]: x.id } });
    };
  }));
  kok.querySelector("#hepsini").onclick = async () => {
    const yeni = { ...s.gunler };
    const kullanilan = new Set(liste);
    for (const g of gunler) {
      if (yeni[g]) continue;
      const a = (await gunOner(g, kullanilan))[0];
      if (!a) continue;
      const x = await kombinBul(a.parcalar);
      yeni[g] = x.id;
      a.parcalar.forEach((i) => kullanilan.add(i));
    }
    kaydet({ gunler: yeni });
    bildir("Boş günler planlandı");
  };
  kok.querySelector("#ekstra").onclick = () => {
    const secenek = d.aktif.filter((p) => !liste.includes(p.id));
    const pen = pencere({ baslik: "Ekstra parça", icerik: `<div class="izgara">${secenek.map((p) => parcaKart(p, { secili: false })).join("")}</div>`, alt: `<button class="dugme ana" type="button" id="tamam">Ekle</button>` });
    gorselleriDoldur(pen.govde);
    const sec = new Set();
    pen.govde.querySelector(".izgara").onclick = (e) => { const b = e.target.closest("[data-parca]"); if (!b) return; sec.has(b.dataset.parca) ? sec.delete(b.dataset.parca) : sec.add(b.dataset.parca); b.setAttribute("aria-pressed", String(sec.has(b.dataset.parca))); };
    pen.govde.querySelector("#tamam").onclick = () => { pen.kapat(true); kaydet({ ekstra: [...(s.ekstra || []), ...sec] }); };
  };
}

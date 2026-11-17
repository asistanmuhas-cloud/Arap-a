// K1: elle kombin kurma ve düzenleme. #/kombin-kur/<id|yeni>/<başlangıç parçası?>
import * as veri from "../veri.js";
import { yukle } from "../durum.js";
import { renkUyumu } from "../renk.js";
import { rolu } from "../oneri.js";
import { KATEGORILER, ORTAMLAR, MEVSIMLER } from "../sabitler.js";
import { k, parcaKart, kolaj, gorselleriDoldur, cipGrubu, cipleriBagla, cipOku, bildir } from "../ui.js";
import { git } from "../app.js";

export const baslik = (p) => (p[0] && p[0] !== "yeni" ? "Kombini düzenle" : "Kombin kur");

export async function ciz(kok, [id = "yeni", ilk]) {
  const d = await yukle();
  const mevcut = id !== "yeni" ? d.kombinler.find((x) => x.id === id) : null;
  const secili = new Set(mevcut?.parcalar || (ilk ? [ilk] : []));
  let kat = null;
  kok.innerHTML = `
    <div class="kutu" id="ozet"></div>
    <div class="cipler kaydir" id="kat"><button class="cip" type="button" data-kat="" aria-pressed="true">Tümü</button>${KATEGORILER.filter((c) => d.aktif.some((p) => p.kategori === c.id)).map((c) => `<button class="cip" type="button" data-kat="${c.id}" aria-pressed="false">${k(c.ad)}</button>`).join("")}</div>
    <div class="izgara" id="parcalar"></div>
    <div class="kutu">
      <div class="alan"><label for="ad">Kombin adı</label><input type="text" id="ad" value="${k(mevcut?.ad || "")}" placeholder="Ör. Cuma ofis"></div>
      <div class="alan"><span class="etiket-ad">Ortam</span>${cipGrubu("ortamlar", ORTAMLAR, mevcut?.ortamlar || [])}</div>
      <div class="alan"><span class="etiket-ad">Mevsim</span>${cipGrubu("mevsimler", MEVSIMLER, mevcut?.mevsimler || [])}</div>
      <button class="dugme ana genis" type="button" id="kaydet">Kombini kaydet</button>
    </div>`;
  cipleriBagla(kok.querySelector(".kutu:last-child"));
  if (!d.aktif.length) kok.querySelector("#parcalar").outerHTML = `<div class="bos-kutu">Önce gardroba parça ekle. <a class="dugme ana" href="#/ekle">Parça ekle</a></div>`;

  const ozet = () => {
    const l = [...secili].map((i) => d.parcaHarita.get(i)).filter(Boolean);
    const r = l.length > 1 ? renkUyumu(l.map((p) => p.renkler?.[0])) : null;
    const roller = new Set(l.map(rolu));
    const eksik = [];
    if (!roller.has("tek") && !(roller.has("ust") && roller.has("alt"))) eksik.push(roller.has("ust") ? "alt" : roller.has("alt") ? "üst" : "üst + alt ya da elbise");
    if (!roller.has("ayakkabi") && d.aktif.some((p) => rolu(p) === "ayakkabi")) eksik.push("ayakkabı");
    kok.querySelector("#ozet").innerHTML = l.length
      ? `<div style="display:grid;grid-template-columns:120px 1fr;gap:12px;align-items:center"><div>${kolaj(l)}</div><div class="yigin"><b>${l.length} parça seçildi</b>${r ? `<span class="etiket ${r.puan >= 0.7 ? "iyi" : r.puan >= 0.5 ? "" : "uyari"}">${k(r.neden)}</span>` : ""}${eksik.length ? `<span class="kucuk soluk">Eksik: ${k(eksik.join(", "))}</span>` : ""}</div></div>`
      : `<p class="soluk" style="margin:0">Aşağıdan parçalara dokunarak kombini oluştur.</p>`;
    gorselleriDoldur(kok.querySelector("#ozet"));
  };
  const liste = () => {
    const e = kok.querySelector("#parcalar");
    if (!e) return;
    const l = d.aktif.filter((p) => !kat || p.kategori === kat);
    e.innerHTML = l.map((p) => parcaKart(p, { secili: secili.has(p.id) })).join("");
    gorselleriDoldur(e);
  };
  ozet(); liste();

  kok.querySelector("#kat").onclick = (e) => {
    const c = e.target.closest("[data-kat]");
    if (!c) return;
    kat = c.dataset.kat || null;
    kok.querySelectorAll("#kat .cip").forEach((x) => x.setAttribute("aria-pressed", String(x === c)));
    liste();
  };
  kok.querySelector("#parcalar")?.addEventListener("click", (e) => {
    const b = e.target.closest("[data-parca]");
    if (!b) return;
    const pid = b.dataset.parca;
    const p = d.parcaHarita.get(pid);
    if (secili.has(pid)) secili.delete(pid);
    else {
      // Aynı rolden ikinci üst/alt/ayakkabı seçilirse eskisini bırak (aksesuar ve dış giyim çoklu olabilir).
      const tekRol = ["ust", "alt", "tek", "ayakkabi"];
      if (tekRol.includes(rolu(p))) for (const s of [...secili]) {
        const sr = rolu(d.parcaHarita.get(s));
        if (sr === rolu(p) || (rolu(p) === "tek" && (sr === "ust" || sr === "alt")) || (sr === "tek" && (rolu(p) === "ust" || rolu(p) === "alt"))) secili.delete(s);
      }
      secili.add(pid);
    }
    kok.querySelectorAll("#parcalar [data-parca]").forEach((x) => x.setAttribute("aria-pressed", String(secili.has(x.dataset.parca))));
    ozet();
  });
  kok.querySelector("#kaydet").onclick = async () => {
    if (secili.size < 2) return bildir("En az iki parça seç");
    const sirali = [...secili].sort((a, b) => sira(d.parcaHarita.get(a)) - sira(d.parcaHarita.get(b)));
    const s = kok.querySelector(".kutu:last-child");
    const kayit = await veri.kaydet("kombinler", {
      ...(mevcut || { kaynak: "elle", favori: false, puan: 0 }),
      ad: kok.querySelector("#ad").value.trim(),
      parcalar: sirali,
      ortamlar: cipOku(s, "ortamlar") || [],
      mevsimler: cipOku(s, "mevsimler") || [],
    });
    bildir("Kombin kaydedildi");
    git(`kombin/${kayit.id}`);
  };
}
const SIRA = { dis: 0, ust: 1, tek: 1, alt: 2, ayakkabi: 3, aksesuar: 4, diger: 5 };
export const sira = (p) => SIRA[rolu(p || {})] ?? 9;

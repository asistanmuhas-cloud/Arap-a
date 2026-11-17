// K7: kapsül gardrop. Parça seç, kaç uyumlu kombin çıktığını gör, kapsülü kaydet.
import * as veri from "../veri.js";
import { yukle } from "../durum.js";
import { kapsulKombinleri } from "../oneri.js";
import { KATEGORILER } from "../sabitler.js";
import { k, parcaKart, gorselleriDoldur, kolaj, bildir, onayla } from "../ui.js";
import { yenile } from "../app.js";

export const baslik = "Kapsül gardrop";
let secili = new Set(), acik = null;

export async function ciz(kok) {
  const d = await yukle();
  const kapsuller = (await veri.hepsi("seyahat")).filter((s) => s.tur === "kapsul");
  const kombinler = kapsulKombinleri([...secili].map((i) => d.parcaHarita.get(i)).filter(Boolean));
  const roller = KATEGORILER.filter((c) => ["ust", "alt", "tek", "ayakkabi", "dis"].includes(c.id));
  kok.innerHTML = `
    <p class="soluk" style="margin:0">Seyahat, mevsim ya da sade bir gardrop için 10–30 parça seç; aralarında renk uyumlu kaç kombin olduğunu anında görürsün.</p>
    ${kapsuller.length ? `<div class="cipler">${kapsuller.map((x) => `<button class="cip" type="button" data-kapsul="${x.id}" aria-pressed="${acik === x.id}">${k(x.ad)} · ${x.parcalar.length}</button>`).join("")}</div>` : ""}
    <div class="kutu">
      <div class="sayilar"><div class="sayi"><b>${secili.size}</b><small>parça</small></div><div class="sayi"><b>${kombinler.length}</b><small>uyumlu kombin</small></div><div class="sayi"><b>${secili.size ? (kombinler.length / secili.size).toFixed(1) : "—"}</b><small>parça başına</small></div></div>
      ${kombinler.length ? `<div class="oneri-serit">${kombinler.slice(0, 12).map((ids) => `<div style="width:96px;flex-shrink:0">${kolaj(ids.map((i) => d.parcaHarita.get(i)))}</div>`).join("")}</div>` : ""}
      <div class="satir"><input type="text" id="ad" placeholder="Kapsül adı (ör. Bodrum 5 gün)" value="${k(kapsuller.find((x) => x.id === acik)?.ad || "")}" style="flex:1"><button class="dugme ana" type="button" id="kaydet" ${secili.size ? "" : "disabled"}>Kaydet</button></div>
      <div class="satir">${secili.size ? `<button class="dugme kucuk" type="button" id="temizle">Seçimi temizle</button>` : ""}${acik ? `<button class="dugme kucuk tehlike" type="button" id="sil">Kapsülü sil</button>` : ""}</div>
    </div>
    ${roller.map((c) => {
      const l = d.aktif.filter((p) => p.kategori === c.id);
      return l.length ? `<section class="bolum"><h3>${k(c.ad)} <span class="soluk kucuk">${l.filter((p) => secili.has(p.id)).length}/${l.length}</span></h3><div class="izgara">${l.map((p) => parcaKart(p, { secili: secili.has(p.id) })).join("")}</div></section>` : "";
    }).join("")}`;
  gorselleriDoldur(kok);
  kok.addEventListener("click", async (e) => {
    const b = e.target.closest("[data-parca]");
    if (b) { const id = b.dataset.parca; secili.has(id) ? secili.delete(id) : secili.add(id); return yenile(); }
    const c = e.target.closest("[data-kapsul]");
    if (c) { const x = kapsuller.find((y) => y.id === c.dataset.kapsul); acik = x.id; secili = new Set(x.parcalar); return yenile(); }
  });
  kok.querySelector("#temizle")?.addEventListener("click", () => { secili.clear(); acik = null; yenile(); });
  kok.querySelector("#kaydet").onclick = async () => {
    const ad = kok.querySelector("#ad").value.trim() || "Kapsül";
    const x = await veri.kaydet("seyahat", { ...(kapsuller.find((y) => y.id === acik) || {}), tur: "kapsul", ad, parcalar: [...secili] });
    acik = x.id;
    bildir("Kapsül kaydedildi");
    yenile();
  };
  kok.querySelector("#sil")?.addEventListener("click", async () => {
    if (!(await onayla("Kapsül silinecek; parçalar gardropta kalır.", { evet: "Sil", tehlike: true }))) return;
    await veri.sil("seyahat", acik);
    acik = null; secili.clear();
    yenile();
  });
}

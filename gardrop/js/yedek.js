// X1: tüm profillerin verisi ve fotoğrafları tek JSON dosyasında. İçe aktarmada daha yeni kayıt kazanır.
import * as veri from "./veri.js";

const SURUM = 1;
const b64 = (blob) => new Promise((coz, red) => { const r = new FileReader(); r.onload = () => coz(r.result); r.onerror = () => red(r.error); r.readAsDataURL(blob); });
const blobYap = async (dataUrl) => (dataUrl ? (await fetch(dataUrl)).blob() : null);

export async function disaAktar() {
  const depolar = {};
  for (const d of veri.DEPOLAR) depolar[d] = await veri.hepsi(d, { silinenler: true, tumProfiller: true });
  const gorseller = [];
  for (const g of await veri.tumGorseller()) gorseller.push({ id: g.id, guncelleme: g.guncelleme, blob: await b64(g.blob), kucuk: g.kucuk ? await b64(g.kucuk) : null });
  const metin = JSON.stringify({ uygulama: "gardrop", surum: SURUM, tarih: new Date().toISOString(), depolar, gorseller });
  return new Blob([metin], { type: "application/json" });
}

export async function iceAktar(dosya) {
  const j = JSON.parse(await dosya.text());
  if (j.uygulama !== "gardrop") throw new Error("Bu dosya bir Gardrop yedeği değil");
  let kayit = 0, gorsel = 0;
  for (const d of veri.DEPOLAR) if (Array.isArray(j.depolar?.[d])) kayit += await veri.hamYaz(d, j.depolar[d]);
  for (const g of j.gorseller || []) {
    if (!veri.gecerliKayit(g) || (await veri.gorselOku(g.id))) continue;
    await veri.gorselYaz({ id: g.id, guncelleme: g.guncelleme, blob: await blobYap(g.blob), kucuk: await blobYap(g.kucuk) });
    gorsel++;
  }
  await veri.bosProfildenGec();
  return { kayit, gorsel };
}

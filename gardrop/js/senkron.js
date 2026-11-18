// Bulut senkronu (Supabase, kütüphanesiz REST) ve E7 ürün linki okuma.
// Kurulum: supabase/KURULUM.md. Tablo: kayitlar(kullanici, depo, id, guncelleme, degisim, veri). Fotoğraflar: Storage "gorseller".
import * as veri from "./veri.js";

const ayar = () => veri.ayarOku("bulut", null); // {url, anahtar, eposta, oturum: {access_token, refresh_token, bitis, kullanici}}
const ayarYaz = (a) => veri.ayarYaz("bulut", a);

export async function durum() {
  const a = await ayar();
  return { kurulu: !!(a?.url && a?.anahtar), girisli: !!a?.oturum, eposta: a?.eposta, son: await veri.ayarOku("senkronSon", null), hata: await veri.ayarOku("senkronHata", null) };
}
export async function kur(url, anahtar) {
  url = url.trim().replace(/\/+$/, "");
  if (!/^https:\/\/[a-z0-9-]+\.supabase\.co$/i.test(url) && !/^https:\/\//.test(url)) throw new Error("Adres https:// ile başlamalı (ör. https://xyz.supabase.co)");
  await ayarYaz({ ...(await ayar()), url, anahtar: anahtar.trim() });
}
// İmleç, gönderim zamanı ve yüklü fotoğraf listesi tek bir hesap + projeye aittir; değişince baştan eşitlenir.
async function durumSifirla() {
  for (const a of ["senkronImlec", "senkronGonderim", "senkronGorseller", "senkronSon", "senkronHata"]) await veri.ayarYaz(a, null);
}
export async function kaldir() {
  await ayarYaz(null);
  await durumSifirla();
  await veri.ayarYaz("senkronHesap", null);
}

async function istek(yol, { yontem = "GET", govde, basliklar = {}, oturumlu = true, ham = false } = {}) {
  const a = await ayar();
  if (!a?.url) throw new Error("Bulut bağlantısı kurulmadı");
  const h = { apikey: a.anahtar, ...basliklar };
  if (govde !== undefined && !(govde instanceof Blob)) h["Content-Type"] = "application/json";
  if (oturumlu) h.Authorization = `Bearer ${await erisimJetonu()}`;
  const r = await fetch(a.url + yol, { method: yontem, headers: h, body: govde === undefined ? undefined : govde instanceof Blob ? govde : JSON.stringify(govde) });
  if (!r.ok) {
    let m = `${r.status}`;
    try { const j = await r.json(); m = j.msg || j.message || j.error_description || j.error || m; } catch {}
    throw new Error(m);
  }
  if (ham) return r;
  const t = await r.text();
  return t ? JSON.parse(t) : null;
}

async function oturumKaydet(a, j) {
  const hesap = `${a.url}|${j.user?.id || a.oturum?.kullanici || ""}`;
  if ((await veri.ayarOku("senkronHesap", null)) !== hesap) { await durumSifirla(); await veri.ayarYaz("senkronHesap", hesap); }
  return ayarYaz({ ...a, oturum: { access_token: j.access_token, refresh_token: j.refresh_token, bitis: Date.now() + (j.expires_in || 3600) * 1000, kullanici: j.user?.id } });
}
export async function girisYap(eposta, parola, { kayit = false } = {}) {
  const a = await ayar();
  if (kayit) {
    const j = await istek("/auth/v1/signup", { yontem: "POST", govde: { email: eposta, password: parola }, oturumlu: false });
    if (!j?.access_token) { await ayarYaz({ ...a, eposta }); return { onayGerekli: true }; }
    await oturumKaydet({ ...a, eposta }, j);
    return { onayGerekli: false };
  }
  const j = await istek("/auth/v1/token?grant_type=password", { yontem: "POST", govde: { email: eposta, password: parola }, oturumlu: false });
  await oturumKaydet({ ...a, eposta }, j);
  return { onayGerekli: false };
}
export async function cikisYap() {
  const a = await ayar();
  await ayarYaz({ ...a, oturum: null });
}
async function erisimJetonu() {
  const a = await ayar();
  if (!a?.oturum) throw new Error("Giriş yapılmadı");
  if (Date.now() < a.oturum.bitis - 60e3) return a.oturum.access_token;
  const r = await fetch(`${a.url}/auth/v1/token?grant_type=refresh_token`, { method: "POST", headers: { apikey: a.anahtar, "Content-Type": "application/json" }, body: JSON.stringify({ refresh_token: a.oturum.refresh_token }) });
  if (!r.ok) { await ayarYaz({ ...a, oturum: null }); throw new Error("Oturum süresi doldu, yeniden giriş yap"); }
  const j = await r.json();
  await oturumKaydet(a, j);
  return j.access_token;
}

// --- senkron ---
let calisiyor = null;
export function senkronla() {
  calisiyor ||= senkronIc().finally(() => (calisiyor = null));
  return calisiyor;
}
async function senkronIc() {
  const a = await ayar();
  if (!a?.oturum) return { atlandi: true };
  try {
    const uid = a.oturum.kullanici;
    const sonGonderim = (await veri.ayarOku("senkronGonderim")) || "";
    const basla = new Date().toISOString();
    const yuklu = new Set((await veri.ayarOku("senkronGorseller")) || []);
    // 1) Çek: sunucudaki değişim imlecinden sonrakiler (degisim sunucu saatidir)
    let imlec = (await veri.ayarOku("senkronImlec")) || "1970-01-01T00:00:00Z";
    let cekilen = 0;
    for (;;) {
      const l = await istek(`/rest/v1/kayitlar?select=depo,id,veri,degisim&degisim=gt.${encodeURIComponent(imlec)}&order=degisim.asc&limit=500`);
      if (!l.length) break;
      const gruplu = {};
      for (const r of l) (gruplu[r.depo] ||= []).push(r.veri);
      for (const [d, kayitlar] of Object.entries(gruplu)) if (veri.DEPOLAR.includes(d)) cekilen += await veri.hamYaz(d, kayitlar);
      imlec = l[l.length - 1].degisim;
      await veri.ayarYaz("senkronImlec", imlec);
      if (l.length < 500) break;
    }
    // Eksik fotoğrafları indir
    for (const p of await veri.hepsi("parcalar", { tumProfiller: true })) {
      if (!p.gorsel || (await veri.gorselOku(p.gorsel))) continue;
      try {
        const blob = await (await istek(`/storage/v1/object/authenticated/gorseller/${uid}/${p.gorsel}`, { ham: true })).blob();
        let kucuk = null;
        try { kucuk = await (await istek(`/storage/v1/object/authenticated/gorseller/${uid}/${p.gorsel}_k`, { ham: true })).blob(); } catch {}
        await veri.gorselYaz({ id: p.gorsel, blob, kucuk });
        yuklu.add(p.gorsel);
      } catch (e) { console.warn("Fotoğraf indirilemedi", p.gorsel, e); }
    }
    const profilDegisti = await veri.bosProfildenGec();
    // 2) Gönder: son gönderimden sonra değişen yerel kayıtlar
    const gidecek = [];
    for (const d of veri.DEPOLAR) for (const k of await veri.hepsi(d, { silinenler: true, tumProfiller: true })) {
      if ((k.guncelleme || "") > sonGonderim) gidecek.push({ depo: d, id: k.id, guncelleme: k.guncelleme, veri: k });
    }
    for (let i = 0; i < gidecek.length; i += 200) {
      await istek("/rest/v1/kayitlar?on_conflict=kullanici,depo,id", { yontem: "POST", govde: gidecek.slice(i, i + 200), basliklar: { Prefer: "resolution=merge-duplicates,return=minimal" } });
    }
    // Fotoğraflar: parçalarda kullanılan ve henüz yüklenmemiş olanlar
    const parcalar = await veri.hepsi("parcalar", { tumProfiller: true });
    const fotoHata = [];
    for (const p of parcalar) {
      if (!p.gorsel || yuklu.has(p.gorsel)) continue;
      const g = await veri.gorselOku(p.gorsel);
      if (!g) continue;
      // Tek bir fotoğrafın hatası tüm senkronu durdurmasın; sonraki senkronda yeniden denenir.
      try {
        await istek(`/storage/v1/object/gorseller/${uid}/${g.id}`, { yontem: "POST", govde: g.blob, basliklar: { "x-upsert": "true", "Content-Type": g.blob.type } });
        if (g.kucuk) await istek(`/storage/v1/object/gorseller/${uid}/${g.id}_k`, { yontem: "POST", govde: g.kucuk, basliklar: { "x-upsert": "true", "Content-Type": g.kucuk.type } });
        yuklu.add(g.id);
        await veri.ayarYaz("senkronGorseller", [...yuklu]);
      } catch (e) { fotoHata.push(e.message); console.warn("Fotoğraf yüklenemedi", g.id, e); }
    }
    await veri.ayarYaz("senkronGonderim", basla);
    await veri.ayarYaz("senkronGorseller", [...yuklu]);
    await veri.ayarYaz("senkronSon", new Date().toISOString());
    await veri.ayarYaz("senkronHata", fotoHata.length ? `${fotoHata.length} fotoğraf yüklenemedi (${fotoHata[0]}); sonraki senkronda yeniden denenecek` : null);
    if (profilDegisti) location.reload();
    return { gonderilen: gidecek.length, cekilen };
  } catch (e) {
    await veri.ayarYaz("senkronHata", e.message);
    throw e;
  }
}

// Açılışta, çevrimiçi olunca, değişiklikten 20 sn sonra ve 5 dakikada bir.
let zamanlayici = null;
export async function otomatikBaslat() {
  const a = await ayar();
  if (!a?.oturum) return;
  const calis = () => senkronla().catch((e) => console.warn("Senkron:", e.message));
  calis();
  addEventListener("online", calis);
  setInterval(calis, 5 * 60e3);
  veri.degisinceDinle(() => { clearTimeout(zamanlayici); zamanlayici = setTimeout(calis, 20e3); });
}

// E7: sunucu fonksiyonu ürün sayfasını okur. Dönüş: {baslik, marka, fiyat, magaza, gorsel: Blob|null}
export async function urunCek(url) {
  const a = await ayar();
  if (!a?.oturum) return null;
  const j = await istek("/functions/v1/urun-cek", { yontem: "POST", govde: { url } });
  if (!j) return null;
  // Görsel alınamazsa ad, marka ve fiyat yine kullanılır.
  const gorsel = j.gorsel ? await fetch(j.gorsel).then((r) => (r.ok ? r.blob() : null)).catch(() => null) : null;
  return { ...j, gorsel };
}

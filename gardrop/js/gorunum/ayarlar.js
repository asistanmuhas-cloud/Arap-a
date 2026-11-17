// Ayarlar: şehir (P2), profiller (X3), yedekleme (X1), bulut senkron, tercihler.
import * as veri from "../veri.js";
import * as hava from "../hava.js";
import * as senkron from "../senkron.js";
import { disaAktar, iceAktar } from "../yedek.js";
import { gunStr } from "../analiz.js";
import { k, bildir, onayla } from "../ui.js";
import { yenile } from "../app.js";

export const baslik = "Ayarlar";

export async function ciz(kok) {
  const konum = await hava.konum();
  const profiller = await veri.hepsi("profiller");
  const kirli = await veri.ayarOku("giyinceKirli", false);
  const otomatik = await veri.ayarOku("arkaPlanOtomatik", true);
  const b = await senkron.durum();
  const son = await veri.ayarOku("sonYedek");
  let kullanim = "";
  try { const e = await navigator.storage.estimate(); kullanim = `${(e.usage / 1048576).toFixed(1)} MB kullanılıyor`; } catch {}
  const kalici = await navigator.storage?.persisted?.().catch(() => false);

  kok.innerHTML = `
  <section class="kutu"><h3>Şehir</h3>
    <p class="kucuk soluk" style="margin:0">${konum ? `Seçili: <b>${k(konum.ad)}</b>` : "Hava durumuna göre öneri ve takvimde tahmin için şehrini seç."}</p>
    <div class="satir" style="flex-wrap:nowrap"><input type="text" id="sehir" placeholder="Şehir ara" style="flex:1"><button class="dugme" type="button" id="ara">Ara</button></div>
    <div class="cipler" id="sonuclar"></div>
    <button class="dugme" type="button" id="konumum">Konumumu kullan</button>
  </section>

  <section class="kutu"><h3>Tercihler</h3>
    <label class="satir"><input type="checkbox" id="otomatik" ${otomatik ? "checked" : ""}> Fotoğraf eklerken arka planı otomatik sil</label>
    <label class="satir"><input type="checkbox" id="kirli" ${kirli ? "checked" : ""}> Kombini giyince giysileri "kirli" yap (ayakkabı, dış giyim, aksesuar hariç)</label>
    <button class="dugme" type="button" id="hepsi-temiz">Tüm kirlileri temiz yap</button>
  </section>

  <section class="kutu"><h3>Profiller</h3>
    <div class="liste">${profiller.map((p) => `<div><span class="renk-nokta" style="width:20px;height:20px;background:${k(p.renk)}"></span><span class="metin"><input type="text" value="${k(p.ad)}" data-profil-ad="${p.id}" aria-label="Profil adı"></span>${profiller.length > 1 ? `<button class="dugme kucuk tehlike" type="button" data-profil-sil="${p.id}">Sil</button>` : ""}</div>`).join("")}</div>
    <p class="kucuk soluk" style="margin:0">Profil değiştirmek ya da eklemek için sol üstteki isme dokun.</p>
  </section>

  <section class="kutu"><h3>Yedekleme</h3>
    <p class="kucuk soluk" style="margin:0">Tüm profiller ve fotoğraflar tek dosyaya yazılır. ${son ? `Son yedek: ${new Date(son).toLocaleDateString("tr-TR")}.` : "Henüz yedek alınmadı."} ${kullanim}${kalici ? "" : " · Tarayıcı yer azalınca veriyi silebilir; düzenli yedek al ya da bulutu aç."}</p>
    <div class="iki"><button class="dugme ana" type="button" id="yedek-al">Yedek al</button><label class="dugme">Yedekten geri yükle<input type="file" accept="application/json,.json" id="yedek-yukle" hidden></label></div>
    <div id="yedek-durum"></div>
  </section>

  <section class="kutu"><h3>Bulut senkron</h3>
    ${!b.kurulu ? `<p class="kucuk soluk" style="margin:0">Telefon ve bilgisayar arasında eşitlemek ve linkten ürün eklemek için bir Supabase projesi bağla. Adımlar repodaki <code>gardrop/supabase/KURULUM.md</code> dosyasında.</p>
      <div class="alan"><label for="b-url">Proje adresi</label><input type="url" id="b-url" placeholder="https://xxxx.supabase.co"></div>
      <div class="alan"><label for="b-anahtar">Herkese açık anahtar (anon / publishable)</label><input type="text" id="b-anahtar" autocomplete="off"></div>
      <button class="dugme ana" type="button" id="b-kur">Bağlan</button>`
    : !b.girisli ? `<p class="kucuk soluk" style="margin:0">Proje bağlı. Giriş yap ya da hesap oluştur.</p>
      <div class="alan"><label for="b-eposta">E-posta</label><input type="text" inputmode="email" id="b-eposta" value="${k(b.eposta || "")}" autocomplete="email"></div>
      <div class="alan"><label for="b-parola">Parola</label><input type="password" id="b-parola" autocomplete="current-password"></div>
      <div class="iki"><button class="dugme ana" type="button" id="b-giris">Giriş yap</button><button class="dugme" type="button" id="b-kayit">Hesap oluştur</button></div>
      <button class="dugme kucuk tehlike" type="button" id="b-kaldir">Proje bağlantısını kaldır</button>`
    : `<p style="margin:0"><b>${k(b.eposta)}</b> ile bağlı.</p>
      <p class="kucuk soluk" style="margin:0">${b.son ? `Son senkron: ${new Date(b.son).toLocaleString("tr-TR")}` : "Henüz senkron yapılmadı."}</p>
      ${b.hata ? `<div class="hata-kutu">Son senkron hatası: ${k(b.hata)}</div>` : ""}
      <div class="iki"><button class="dugme ana" type="button" id="b-senkron">Şimdi senkronla</button><button class="dugme" type="button" id="b-cikis">Çıkış yap</button></div>`}
    <div id="b-durum"></div>
  </section>
  <p class="kucuk soluk" style="margin:0;text-align:center">Arka plan silme: @imgly/background-removal (AGPL-3.0). Hava: Open-Meteo.</p>`;

  // Şehir
  let sonuc = [];
  kok.querySelector("#ara").onclick = async () => {
    const e = kok.querySelector("#sonuclar");
    try {
      sonuc = await hava.konumAra(kok.querySelector("#sehir").value);
      e.innerHTML = sonuc.length ? sonuc.map((s, i) => `<button class="cip" type="button" data-i="${i}">${k(s.ad)}</button>`).join("") : `<span class="kucuk soluk">Bulunamadı</span>`;
    } catch (err) { e.innerHTML = `<span class="kucuk soluk">${k(err.message)}</span>`; }
  };
  kok.querySelector("#sonuclar").onclick = async (e) => {
    const c = e.target.closest("[data-i]");
    if (!c) return;
    await hava.konumKaydet(sonuc[+c.dataset.i]);
    bildir("Şehir kaydedildi");
    yenile();
  };
  kok.querySelector("#konumum").onclick = async () => {
    try { await hava.konumKaydet(await hava.cihazKonumu()); bildir("Konum kaydedildi"); yenile(); } catch (e) { bildir(e.message); }
  };
  // Tercihler
  kok.querySelector("#otomatik").onchange = (e) => veri.ayarYaz("arkaPlanOtomatik", e.target.checked);
  kok.querySelector("#kirli").onchange = (e) => veri.ayarYaz("giyinceKirli", e.target.checked);
  kok.querySelector("#hepsi-temiz").onclick = async () => {
    const l = (await veri.hepsi("parcalar")).filter((p) => p.durum === "kirli");
    for (const p of l) await veri.guncelle("parcalar", p.id, { durum: "temiz", durumTarihi: gunStr() });
    bildir(`${l.length} parça temiz`);
  };
  // Profiller
  kok.querySelectorAll("[data-profil-ad]").forEach((i) => (i.onchange = async () => { if (i.value.trim()) { await veri.guncelle("profiller", i.dataset.profilAd, { ad: i.value.trim() }); bildir("Kaydedildi"); } }));
  kok.querySelectorAll("[data-profil-sil]").forEach((bt) => (bt.onclick = async () => {
    const id = bt.dataset.profilSil;
    if (!(await onayla("Bu profil ve içindeki tüm parçalar, kombinler ve kayıtlar silinecek.", { evet: "Profili sil", tehlike: true }))) return;
    const onceki = veri.profil();
    await veri.profilSec(id);
    for (const d of veri.DEPOLAR) if (d !== "profiller") for (const x of await veri.hepsi(d)) await veri.sil(d, x.id);
    await veri.sil("profiller", id);
    const kalan = (await veri.hepsi("profiller"))[0];
    await veri.profilSec(onceki !== id ? onceki : kalan.id);
    location.reload();
  }));
  // Yedek
  kok.querySelector("#yedek-al").onclick = async (e) => {
    e.target.disabled = true;
    try {
      const blob = await disaAktar();
      const ad = `gardrop-yedek-${gunStr()}.json`;
      const dosya = new File([blob], ad, { type: "application/json" });
      if (navigator.canShare?.({ files: [dosya] }) && /Android|iPhone|iPad/.test(navigator.userAgent)) {
        try { await navigator.share({ files: [dosya], title: ad }); } catch (err) { if (err.name !== "AbortError") throw err; }
      } else {
        const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: ad });
        document.body.append(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(a.href), 5000);
      }
      await veri.ayarYaz("sonYedek", new Date().toISOString());
      kok.querySelector("#yedek-durum").innerHTML = `<p class="kucuk soluk" style="margin:0">${(blob.size / 1048576).toFixed(1)} MB yedek hazırlandı.</p>`;
    } catch (err) { bildir("Yedek alınamadı: " + err.message); }
    e.target.disabled = false;
  };
  kok.querySelector("#yedek-yukle").onchange = async (e) => {
    const f = e.target.files[0];
    if (!f) return;
    try {
      const s = await iceAktar(f);
      bildir(`${s.kayit} kayıt, ${s.gorsel} fotoğraf geri yüklendi`);
      setTimeout(() => location.reload(), 900);
    } catch (err) { kok.querySelector("#yedek-durum").innerHTML = `<div class="hata-kutu">${k(err.message)}</div>`; }
  };
  // Bulut
  const durumYaz = (m, hata = false) => (kok.querySelector("#b-durum").innerHTML = m ? `<div class="${hata ? "hata-kutu" : "uyari-kutu"}">${k(m)}</div>` : "");
  const dene = (fn) => async (e) => {
    e.target.disabled = true;
    try { await fn(); } catch (err) { durumYaz(err.message, true); }
    e.target.disabled = false;
  };
  kok.querySelector("#b-kur")?.addEventListener("click", dene(async () => { await senkron.kur(kok.querySelector("#b-url").value, kok.querySelector("#b-anahtar").value); yenile(); }));
  kok.querySelector("#b-kaldir")?.addEventListener("click", dene(async () => { await senkron.kaldir(); yenile(); }));
  const giris = (kayit) => dene(async () => {
    const r = await senkron.girisYap(kok.querySelector("#b-eposta").value.trim(), kok.querySelector("#b-parola").value, { kayit });
    if (r.onayGerekli) return durumYaz("E-postana gelen onay linkine tıkla, sonra burada Giriş yap.");
    await senkron.senkronla();
    senkron.otomatikBaslat();
    bildir("Bağlandı ve senkronlandı");
    yenile();
  });
  kok.querySelector("#b-giris")?.addEventListener("click", giris(false));
  kok.querySelector("#b-kayit")?.addEventListener("click", giris(true));
  kok.querySelector("#b-senkron")?.addEventListener("click", dene(async () => { const s = await senkron.senkronla(); bildir(`${s.gonderilen} gönderildi, ${s.cekilen} alındı`); yenile(); }));
  kok.querySelector("#b-cikis")?.addEventListener("click", dene(async () => { await senkron.cikisYap(); yenile(); }));
}

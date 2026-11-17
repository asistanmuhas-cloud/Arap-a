// Uygulama kabuğu: yönlendirme (#/bolum/parametre), profil seçimi, servis çalışanı.
import * as veri from "./veri.js";
import { pencere, k, bildir } from "./ui.js";

const GORUNUMLER = {
  bugun: () => import("./gorunum/bugun.js"),
  gardrop: () => import("./gorunum/gardrop.js"),
  parca: () => import("./gorunum/parca.js"),
  ekle: () => import("./gorunum/ekle.js"),
  kombinler: () => import("./gorunum/kombinler.js"),
  kombin: () => import("./gorunum/kombin.js"),
  "kombin-kur": () => import("./gorunum/kombin-kur.js"),
  takvim: () => import("./gorunum/takvim.js"),
  analiz: () => import("./gorunum/analiz.js"),
  daha: () => import("./gorunum/daha.js"),
  alisveris: () => import("./gorunum/alisveris.js"),
  seyahat: () => import("./gorunum/seyahat.js"),
  kapsul: () => import("./gorunum/kapsul.js"),
  ayarlar: () => import("./gorunum/ayarlar.js"),
};
// Alt sekmede hangi sekme vurgulansın
const SEKME = { parca: "gardrop", ekle: "gardrop", kombin: "kombinler", "kombin-kur": "kombinler", kapsul: "kombinler" };

const kok = document.getElementById("kok");
let sayac = 0;

export function git(yol) {
  if (location.hash === "#/" + yol) cizdir();
  else location.hash = "#/" + yol;
}
export function yenile() { return cizdir({ kaydirmaKoru: true }); }

async function cizdir({ kaydirmaKoru = false } = {}) {
  const [ad = "bugun", ...param] = location.hash.replace(/^#\/?/, "").split("/").map(decodeURIComponent);
  const yukle = GORUNUMLER[ad] || GORUNUMLER.bugun;
  const bu = ++sayac;
  const y = scrollY;
  try {
    const m = await yukle();
    if (bu !== sayac) return;
    document.getElementById("baslik").textContent = typeof m.baslik === "function" ? m.baslik(param) : m.baslik;
    const sekme = SEKME[ad] || ad;
    document.querySelectorAll(".alt-nav a").forEach((a) => {
      if (a.dataset.sekme === sekme) a.setAttribute("aria-current", "page");
      else a.removeAttribute("aria-current");
    });
    const yeni = document.createElement("main");
    yeni.id = "kok"; yeni.tabIndex = -1;
    await m.ciz(yeni, param);
    if (bu !== sayac) return;
    document.getElementById("kok").replaceWith(yeni);
    scrollTo(0, kaydirmaKoru ? y : 0);
  } catch (e) {
    console.error(e);
    document.getElementById("kok").innerHTML = `<div class="hata-kutu">Bu bölüm açılamadı: ${k(e.message)}</div>`;
  }
}

async function profilGoster() {
  const profiller = await veri.hepsi("profiller");
  const aktif = profiller.find((p) => p.id === veri.profil());
  document.getElementById("profil-ad").textContent = aktif?.ad || "Ben";
  document.querySelector(".profil-dugme .nokta").style.background = aktif?.renk || "";
}

// X3
async function profilPenceresi() {
  const profiller = await veri.hepsi("profiller");
  const p = pencere({
    baslik: "Profil",
    icerik: `<div class="menu-liste">${profiller.map((x) => `<a href="#" data-profil="${k(x.id)}"><span class="satir"><span class="renk-nokta" style="background:${k(x.renk)};width:20px;height:20px"></span>${k(x.ad)}</span>${x.id === veri.profil() ? '<span class="etiket iyi">Açık</span>' : ""}</a>`).join("")}</div>
      <form class="satir" id="yeni-profil"><input type="text" id="profil-adi" placeholder="Yeni profil adı (ör. Ayşe)" required style="flex:1"><button class="dugme" type="submit">Ekle</button></form>
      <p class="kucuk soluk" style="margin:0">Her profilin gardrobu, kombinleri ve takvimi ayrıdır.</p>`,
  });
  p.govde.querySelectorAll("[data-profil]").forEach((a) => (a.onclick = async (e) => {
    e.preventDefault();
    await veri.profilSec(a.dataset.profil);
    p.kapat(); await profilGoster(); cizdir();
  }));
  const renkler = ["#3b5bdb", "#d6336c", "#2b8a3e", "#e8590c", "#7048e8", "#0c8599"];
  p.govde.querySelector("#yeni-profil").onsubmit = async (e) => {
    e.preventDefault();
    const ad = p.govde.querySelector("#profil-adi").value.trim();
    if (!ad) return;
    const yeni = await veri.kaydet("profiller", { ad, renk: renkler[profiller.length % renkler.length] });
    await veri.profilSec(yeni.id);
    p.kapat(); await profilGoster(); cizdir();
    bildir(`${ad} profili açıldı`);
  };
}

async function basla() {
  if (!("indexedDB" in window)) {
    kok.innerHTML = '<div class="hata-kutu">Bu tarayıcı yerel veritabanını desteklemiyor. Güncel bir tarayıcıda aç.</div>';
    return;
  }
  await veri.baslat();
  await profilGoster();
  document.getElementById("profil-dugme").onclick = profilPenceresi;
  addEventListener("hashchange", () => cizdir());
  veri.degisinceDinle((depo) => { if (depo === "profiller") profilGoster(); });
  cizdir();
  if ("serviceWorker" in navigator && location.protocol !== "file:") {
    navigator.serviceWorker.register("sw.js").catch((e) => console.warn("Servis çalışanı kurulamadı", e));
  }
  import("./senkron.js").then((s) => s.otomatikBaslat?.()).catch(() => {});
}
basla();

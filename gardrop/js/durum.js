// Görünümlerin ortak veri yükleyicisi ve "giydim" işlemi (A1).
import * as veri from "./veri.js";
import { giyimHaritasi, gunStr, sonKombinler, giyimSonrasi, yikamaEsigi } from "./analiz.js";

export async function yukle() {
  const [parcalar, kombinler, giyim, plan] = await Promise.all([
    veri.hepsi("parcalar"), veri.hepsi("kombinler"), veri.hepsi("giyim"), veri.hepsi("plan"),
  ]);
  const harita = giyimHaritasi(giyim);
  const parcaHarita = new Map(parcalar.map((p) => [p.id, p]));
  return {
    parcalar, kombinler, giyim, plan, harita, parcaHarita,
    aktif: parcalar.filter((p) => !p.arsiv),
    baglam: { giyim: harita, kombinler, bugun: new Date(), sonKombinler: sonKombinler(giyim) },
  };
}
export const kombinParcalari = (kombin, parcaHarita) => (kombin?.parcalar || []).map((id) => parcaHarita.get(id)).filter(Boolean);

// A1: giyim kaydı. Aynı gün aynı parça seti iki kez yazılmaz.
export async function giydim({ parcalar, kombin = null, tarih = gunStr(), etkinlik = "" }) {
  const mevcut = (await veri.hepsi("giyim")).find(
    (g) => g.tarih === tarih && [...g.parcalar].sort().join() === [...parcalar].sort().join()
  );
  if (mevcut) return { kayit: mevcut, yeni: false };
  // B2: parçanın yıkama sıklığı (yoksa "giyince kirli" ayarı) dolunca kirliye düşer.
  // Geri almada çevrilebilsin diye kirlenenler ve sayacı artanlar kayda yazılır.
  const giyinceKirli = await veri.ayarOku("giyinceKirli", false);
  const kirlenen = [], sayilan = [];
  for (const id of parcalar) {
    const p = await veri.getir("parcalar", id);
    const s = p && giyimSonrasi(p, giyinceKirli);
    if (!s) continue;
    if (s.kirli) { await veri.guncelle("parcalar", id, { durum: "kirli", durumTarihi: tarih, kirliSayac: 0 }); kirlenen.push(id); }
    else { await veri.guncelle("parcalar", id, { kirliSayac: s.kirliSayac }); sayilan.push(id); }
  }
  const kayit = await veri.kaydet("giyim", { tarih, parcalar, kombin, etkinlik, kirlenen, sayilan });
  // Takvimde o güne planlanan kombin varsa giyildi olarak işaretle
  const plan = (await veri.hepsi("plan")).find((p) => p.tarih === tarih && kombin && p.kombin === kombin);
  if (plan) await veri.guncelle("plan", plan.id, { giyildi: true });
  return { kayit, yeni: true };
}
// A1 geri alma: giydim'in yaptığı plan işaretini ve "kirli" düşürmeyi de çevirir.
export async function giyimGeriAl(id) {
  const g = await veri.getir("giyim", id);
  if (!g) return null;
  await veri.sil("giyim", id);
  if (g.kombin) {
    const baska = (await veri.hepsi("giyim")).some((x) => x.tarih === g.tarih && x.kombin === g.kombin);
    const plan = (await veri.hepsi("plan")).find((p) => p.tarih === g.tarih && p.kombin === g.kombin && p.giyildi);
    if (plan && !baska) await veri.guncelle("plan", plan.id, { giyildi: false });
  }
  const giyinceKirli = await veri.ayarOku("giyinceKirli", false);
  for (const pid of g.kirlenen || []) {
    const p = await veri.getir("parcalar", pid);
    if (p?.durum === "kirli" && p.durumTarihi === g.tarih) await veri.guncelle("parcalar", pid, { durum: "temiz", durumTarihi: g.tarih, kirliSayac: Math.max(0, (yikamaEsigi(p, giyinceKirli) || 1) - 1) });
  }
  for (const pid of g.sayilan || []) {
    const p = await veri.getir("parcalar", pid);
    if (p && (p.durum || "temiz") === "temiz" && p.kirliSayac > 0) await veri.guncelle("parcalar", pid, { kirliSayac: p.kirliSayac - 1 });
  }
  return g;
}

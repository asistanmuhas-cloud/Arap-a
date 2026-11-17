// Görünümlerin ortak veri yükleyicisi ve "giydim" işlemi (A1).
import * as veri from "./veri.js";
import { giyimHaritasi, gunStr, sonKombinler } from "./analiz.js";

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
  const kayit = await veri.kaydet("giyim", { tarih, parcalar, kombin, etkinlik });
  // Takvimde o güne planlanan kombin varsa giyildi olarak işaretle
  const plan = (await veri.hepsi("plan")).find((p) => p.tarih === tarih && kombin && p.kombin === kombin);
  if (plan) await veri.guncelle("plan", plan.id, { giyildi: true });
  return { kayit, yeni: true };
}
export async function giyimGeriAl(id) {
  return veri.sil("giyim", id);
}

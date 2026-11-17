// P2: hava durumu. Open-Meteo (anahtarsız). Konum ayarlarda {ad, enlem, boylam}. 1 saatlik önbellek.
import { ayarOku, ayarYaz } from "./veri.js";

const KOD = {
  0: ["Açık", "☀️"], 1: ["Az bulutlu", "🌤️"], 2: ["Parçalı bulutlu", "⛅"], 3: ["Kapalı", "☁️"],
  45: ["Sisli", "🌫️"], 48: ["Sisli", "🌫️"], 51: ["Çisenti", "🌦️"], 53: ["Çisenti", "🌦️"], 55: ["Çisenti", "🌦️"],
  61: ["Hafif yağmur", "🌧️"], 63: ["Yağmurlu", "🌧️"], 65: ["Kuvvetli yağmur", "🌧️"], 66: ["Dondurucu yağmur", "🌧️"], 67: ["Dondurucu yağmur", "🌧️"],
  71: ["Hafif kar", "🌨️"], 73: ["Karlı", "🌨️"], 75: ["Yoğun kar", "❄️"], 77: ["Kar taneleri", "🌨️"],
  80: ["Sağanak", "🌦️"], 81: ["Sağanak", "🌧️"], 82: ["Kuvvetli sağanak", "⛈️"], 85: ["Kar sağanağı", "🌨️"], 86: ["Kar sağanağı", "❄️"],
  95: ["Gök gürültülü", "⛈️"], 96: ["Dolu", "⛈️"], 99: ["Dolu", "⛈️"],
};
export const durumAdi = (kod) => KOD[kod] || ["", ""];
// Kombin için tek sıcaklık: gündüzü daha ağır sayan ortalama.
export const kombinSicakligi = (gun) => (gun ? gun.max * 0.6 + gun.min * 0.4 : null);
export const yagisli = (gun) => !!gun && (gun.yagis >= 50 || [61, 63, 65, 80, 81, 82, 95].includes(gun.kod));

export async function konumAra(metin) {
  const r = await fetch(`https://geocoding-api.open-meteo.com/v1/search?count=6&language=tr&name=${encodeURIComponent(metin)}`);
  if (!r.ok) throw new Error("Şehir araması başarısız");
  const j = await r.json();
  return (j.results || []).map((x) => ({ ad: [x.name, x.admin1, x.country].filter(Boolean).join(", "), kisa: x.name, enlem: x.latitude, boylam: x.longitude }));
}
export function cihazKonumu() {
  return new Promise((coz, red) => {
    if (!navigator.geolocation) return red(new Error("Bu cihaz konum vermiyor"));
    navigator.geolocation.getCurrentPosition(
      (p) => coz({ ad: "Bulunduğum yer", kisa: "Konumum", enlem: +p.coords.latitude.toFixed(3), boylam: +p.coords.longitude.toFixed(3) }),
      () => red(new Error("Konum izni verilmedi")),
      { timeout: 10000, maximumAge: 3600e3 }
    );
  });
}
export const konum = () => ayarOku("konum");
export const konumKaydet = (k) => ayarYaz("konum", k);

// Dönüş: { simdi: {sicaklik, kod}, gunler: Map(tarih -> {min, max, yagis, kod}) } ya da null (konum yok / çevrimdışı)
export async function tahmin(k = null) {
  k ||= await konum();
  if (!k) return null;
  const anahtar = `hava:${k.enlem},${k.boylam}`;
  const onbellek = await ayarOku(anahtar);
  if (onbellek && Date.now() - onbellek.zaman < 3600e3) return coz(onbellek.veri);
  try {
    const url = `https://api.open-meteo.com/v1/forecast?latitude=${k.enlem}&longitude=${k.boylam}&current=temperature_2m,weather_code&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code&timezone=auto&forecast_days=16`;
    const r = await fetch(url);
    if (!r.ok) throw new Error(r.status);
    const veri = await r.json();
    await ayarYaz(anahtar, { zaman: Date.now(), veri });
    return coz(veri);
  } catch {
    return onbellek ? coz(onbellek.veri) : null; // çevrimdışıysa eski tahmin
  }
}
function coz(v) {
  const gunler = new Map();
  const d = v.daily || {};
  (d.time || []).forEach((t, i) => gunler.set(t, { min: d.temperature_2m_min[i], max: d.temperature_2m_max[i], yagis: d.precipitation_probability_max?.[i] ?? 0, kod: d.weather_code?.[i] }));
  return { simdi: v.current ? { sicaklik: v.current.temperature_2m, kod: v.current.weather_code } : null, gunler };
}

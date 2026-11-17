// Sabit sözlükler: kategoriler, renkler, etiketler. Kod içinde kimlikler (ASCII), ekranda Türkçe adlar kullanılır.

// rol: kombinde parçanın yeri. tek = elbise/tulum (üst + alt yerine geçer).
export const KATEGORILER = [
  { id: "ust", ad: "Üst", rol: "ust", alt: ["Tişört", "Gömlek", "Bluz", "Kazak", "Sweatshirt", "Hırka", "Atlet", "Polo"] },
  { id: "alt", ad: "Alt", rol: "alt", alt: ["Pantolon", "Kot", "Şort", "Etek", "Eşofman altı", "Tayt"] },
  { id: "tek", ad: "Elbise / tulum", rol: "tek", alt: ["Elbise", "Tulum", "Takım"] },
  { id: "dis", ad: "Dış giyim", rol: "dis", alt: ["Mont", "Kaban", "Ceket", "Blazer", "Trençkot", "Yelek", "Yağmurluk"] },
  { id: "ayakkabi", ad: "Ayakkabı", rol: "ayakkabi", alt: ["Spor ayakkabı", "Bot", "Klasik", "Topuklu", "Babet", "Sandalet", "Terlik"] },
  { id: "aksesuar", ad: "Aksesuar", rol: "aksesuar", alt: ["Çanta", "Kemer", "Şapka", "Atkı / şal", "Takı", "Gözlük", "Saat", "Kravat"] },
  { id: "diger", ad: "Diğer", rol: "diger", alt: ["İç giyim", "Çorap", "Mayo", "Pijama", "Spor kıyafeti"] },
];
export const KATEGORI = Object.fromEntries(KATEGORILER.map((k) => [k.id, k]));

// notr: kombinde her renkle gider. rgb: renk çıkarımında en yakın ad için.
export const RENKLER = [
  { id: "siyah", ad: "Siyah", rgb: [20, 20, 22], notr: true },
  { id: "beyaz", ad: "Beyaz", rgb: [245, 245, 242], notr: true },
  { id: "gri", ad: "Gri", rgb: [140, 140, 142], notr: true },
  { id: "antrasit", ad: "Antrasit", rgb: [62, 64, 68], notr: true },
  { id: "lacivert", ad: "Lacivert", rgb: [28, 38, 78], notr: true },
  { id: "bej", ad: "Bej", rgb: [214, 196, 164], notr: true },
  { id: "krem", ad: "Krem", rgb: [240, 232, 210], notr: true },
  { id: "kahverengi", ad: "Kahverengi", rgb: [110, 72, 44], notr: true },
  { id: "camel", ad: "Taba", rgb: [176, 124, 72], notr: true },
  { id: "haki", ad: "Haki", rgb: [112, 112, 74], notr: true },
  { id: "denim", ad: "Kot mavisi", rgb: [72, 100, 140], notr: true },
  { id: "mavi", ad: "Mavi", rgb: [40, 90, 200], notr: false },
  { id: "acikmavi", ad: "Açık mavi", rgb: [150, 190, 230], notr: false },
  { id: "turkuaz", ad: "Turkuaz", rgb: [40, 180, 180], notr: false },
  { id: "yesil", ad: "Yeşil", rgb: [40, 140, 70], notr: false },
  { id: "zumrut", ad: "Koyu yeşil", rgb: [20, 80, 50], notr: false },
  { id: "sari", ad: "Sarı", rgb: [240, 200, 40], notr: false },
  { id: "hardal", ad: "Hardal", rgb: [200, 150, 30], notr: false },
  { id: "turuncu", ad: "Turuncu", rgb: [240, 120, 30], notr: false },
  { id: "kirmizi", ad: "Kırmızı", rgb: [200, 30, 40], notr: false },
  { id: "bordo", ad: "Bordo", rgb: [110, 20, 40], notr: false },
  { id: "pembe", ad: "Pembe", rgb: [240, 150, 180], notr: false },
  { id: "fusya", ad: "Fuşya", rgb: [210, 30, 130], notr: false },
  { id: "mor", ad: "Mor", rgb: [110, 50, 150], notr: false },
  { id: "lila", ad: "Lila", rgb: [190, 160, 220], notr: false },
  { id: "altin", ad: "Altın", rgb: [200, 170, 90], notr: true },
  { id: "gumus", ad: "Gümüş", rgb: [190, 192, 196], notr: true },
];
export const RENK = Object.fromEntries(RENKLER.map((r) => [r.id, r]));

export const MEVSIMLER = [
  { id: "ilkbahar", ad: "İlkbahar" },
  { id: "yaz", ad: "Yaz" },
  { id: "sonbahar", ad: "Sonbahar" },
  { id: "kis", ad: "Kış" },
];
export const ORTAMLAR = [
  { id: "gunluk", ad: "Günlük" },
  { id: "is", ad: "İş" },
  { id: "spor", ad: "Spor" },
  { id: "ozel", ad: "Özel gün" },
  { id: "ev", ad: "Ev" },
  { id: "tatil", ad: "Tatil" },
];
export const KUMASLAR = ["Pamuk", "Keten", "Yün", "Kaşmir", "İpek", "Polyester", "Viskon", "Denim", "Deri", "Süet", "Triko", "Polar", "Naylon"];
export const DESENLER = [
  { id: "duz", ad: "Düz" },
  { id: "cizgili", ad: "Çizgili" },
  { id: "kareli", ad: "Kareli" },
  { id: "puantiye", ad: "Puantiye" },
  { id: "cicekli", ad: "Çiçekli" },
  { id: "baskili", ad: "Baskılı / yazılı" },
  { id: "desenli", ad: "Diğer desen" },
];
// G5. kombine girer mi: kirli/ödünç/terzide/kurutemizleme parçalar öneriye girmez.
export const DURUMLAR = [
  { id: "temiz", ad: "Temiz", hazir: true },
  { id: "kirli", ad: "Kirli", hazir: false },
  { id: "odunc", ad: "Ödünç verildi", hazir: false },
  { id: "terzi", ad: "Terzide", hazir: false, hatirlat: true },
  { id: "kurutemizleme", ad: "Kuru temizlemede", hazir: false, hatirlat: true },
];
export const DURUM = Object.fromEntries(DURUMLAR.map((d) => [d.id, d]));
// G7 arşiv nedeni
export const ARSIV_NEDENLERI = [
  { id: "satildi", ad: "Satıldı" },
  { id: "bagislandi", ad: "Bağışlandı" },
  { id: "atildi", ad: "Atıldı" },
  { id: "kayboldu", ad: "Kayboldu" },
];

export const UNUTULMA_GUN = 90; // A3
export const TEKRAR_GUN = 30; // P4

export function adBul(liste, id) {
  return (liste.find((x) => x.id === id) || {}).ad || id || "";
}

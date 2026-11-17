# Gardrop — plan

Özellik seçimi: https://claude.ai/artifact/LF79xdrWoguuEdE3uEVDFg (2026-11-17)

## İlk sürüm (33)
- [x] E1 Fotoğrafla ekleme
- [x] E2 Arka plan kaldırma (cihazda)
- [x] E3 Baskın renk çıkarma
- [x] E5 Toplu ekleme
- [x] E6 Fotoğrafsız hızlı ekleme
- [~] E7 Ürün linkinden ekleme: Supabase fonksiyonu yazıldı, gerçek mağazalarda denenmedi; bulut yoksa link kaydedilir
- [x] G1 Kategori / alt kategori
- [x] G2 Etiketler (renk, mevsim, ortam, kumaş, desen)
- [x] G3 Satın alma bilgisi
- [x] G4 Arama ve filtre
- [x] G5 Durum takibi (temiz, kirli, ödünç, terzide)
- [x] G7 Arşiv
- [x] K1 Elle kombin
- [x] K3 Karıştır
- [x] K4 Kurallı akıllı öneri
- [x] K6 Favori ve puan
- [x] K7 Kapsül gardrop
- [x] P1 Kombin takvimi
- [x] P2 Hava durumu (Open-Meteo, anahtarsız)
- [x] P3 Seyahat bavulu
- [x] P4 Tekrar uyarısı
- [x] A1 Giydim işareti
- [x] A2 Giyim başı maliyet
- [x] A3 Unutulanlar (90 gün)
- [x] A4 İstatistik panosu
- [x] B3 Tadilat / kuru temizleme hatırlatıcı
- [x] S1 İstek listesi
- [x] S2 Eksik analizi
- [x] S3 Almadan önce test
- [x] S4 Elden çıkarma önerisi
- [x] X1 Yedekleme (fotoğraflar dahil)
- [x] X2 Kombin görseli paylaş
- [x] X3 Çoklu profil

## Sonra
E4, G6, K2, K5, K8 (sanal deneme), P5, A5, B1, B2

## Yok
X4

## Teknik
- Platform: PWA, derleme adımı yok (düz ES modülleri), göreli URL'ler (alt yolda da çalışır).
- Veri: cihazda IndexedDB, bulut senkron Supabase ile (ücretsiz katman). Her kayıt: istemci UUID, `guncelleme` zamanı,
  `silindi` bayrağı, `profil` kimliği. Fotoğraflar kayıtlardan ayrı, küçültülmüş blob olarak.
- YZ: yok (öneriler kural tabanlı).
- Arka plan kaldırma: cihazda.
- Dil: Türkçe.

## Durum
- Bulut senkron: istemci sahte sunucuyla iki cihaz arasında denendi (kayıt, silme, fotoğraf); gerçek Supabase projesiyle denenmedi.
- Testler: `npm test` (mantık), `node test/tarayici.cjs` ve `node test/senkron-sahte.cjs` (Playwright, `python3 -m http.server 8822` ile).

## Dilimler
1. E1 E3 E6 G1–G4 K1 K3 K6 A1 X1
2. E2 E5 G5 G7 K4 K7 P1 A2 A3
3. P2 P3 P4 A4 S1–S4 B3 X2 X3
4. Bulut senkron, E7

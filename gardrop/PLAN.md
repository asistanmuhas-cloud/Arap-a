# Gardrop — plan

Özellik seçimi: https://claude.ai/artifact/LF79xdrWoguuEdE3uEVDFg (2026-11-17)

## İlk sürüm (33)
- [ ] E1 Fotoğrafla ekleme
- [ ] E2 Arka plan kaldırma (cihazda)
- [ ] E3 Baskın renk çıkarma
- [ ] E5 Toplu ekleme
- [ ] E6 Fotoğrafsız hızlı ekleme
- [ ] E7 Ürün linkinden ekleme (sunucu fonksiyonu gerekir; yoksa görsel linki yapıştırma)
- [ ] G1 Kategori / alt kategori
- [ ] G2 Etiketler (renk, mevsim, ortam, kumaş, desen)
- [ ] G3 Satın alma bilgisi
- [ ] G4 Arama ve filtre
- [ ] G5 Durum takibi (temiz, kirli, ödünç, terzide)
- [ ] G7 Arşiv
- [ ] K1 Elle kombin
- [ ] K3 Karıştır
- [ ] K4 Kurallı akıllı öneri
- [ ] K6 Favori ve puan
- [ ] K7 Kapsül gardrop
- [ ] P1 Kombin takvimi
- [ ] P2 Hava durumu (Open-Meteo, anahtarsız)
- [ ] P3 Seyahat bavulu
- [ ] P4 Tekrar uyarısı
- [ ] A1 Giydim işareti
- [ ] A2 Giyim başı maliyet
- [ ] A3 Unutulanlar (90 gün)
- [ ] A4 İstatistik panosu
- [ ] B3 Tadilat / kuru temizleme hatırlatıcı
- [ ] S1 İstek listesi
- [ ] S2 Eksik analizi
- [ ] S3 Almadan önce test
- [ ] S4 Elden çıkarma önerisi
- [ ] X1 Yedekleme (fotoğraflar dahil)
- [ ] X2 Kombin görseli paylaş
- [ ] X3 Çoklu profil

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

## Dilimler
1. E1 E3 E6 G1–G4 K1 K3 K6 A1 X1
2. E2 E5 G5 G7 K4 K7 P1 A2 A3
3. P2 P3 P4 A4 S1–S4 B3 X2 X3
4. Bulut senkron, E7

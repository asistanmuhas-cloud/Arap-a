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

## İkinci sürüm
- [x] G6 Konum: parçanın durduğu yer; öneri listesi, filtre, aramada ve bavul listesinde görünür
- [x] A5 Gardrop değeri: kategoriye göre değer, yıllık harcama, satışlardan gelen
- [x] B1 Bakım talimatı: yıkama, ütü, ek uyarılar (etiket sembollerinin metni)
- [x] B2 Kirli sepeti: parçaya "kaç giyimde yıkanır"; dolunca kirliye düşer, geri alınca sayaç geri gelir

## Sonra
E4 (YZ etiketleme), K2 (kolaj tuvali), K5 (YZ stilist), K8 (sanal deneme), P5 (sabah bildirimi)

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
Her [x] maddesi telefon boyutunda tarayıcı testinde tıklanarak denendi (`test/tarayici.cjs`, Chromium, Android
öykünmesi, İstanbul saat dilimi). Mantık birim testleri: `npm test`.

Denenmeyenler:
- E7 ve bulut senkron gerçek bir Supabase projesiyle denenmedi. Senkron istemcisi sahte sunucuyla iki cihaz arasında
  denendi (`test/senkron-sahte.cjs`: kayıt, silme, fotoğraf). `urun-cek` fonksiyonu hiç çalıştırılmadı.
- iPhone / Safari denenmedi.
- Arka plan modelinin varsayılan CDN adresine (staticimgly.com) bu ortamdan ulaşılamadı; `kur.sh --model` önerilir.

Çalıştırma: `python3 -m http.server 8822` (gardrop/ içinde), sonra `node test/tarayici.cjs`.
Arka plan testi için model: `npm pack @imgly/background-removal-data@1.4.5` → `package/dist` → `vendor/arka-plan-veri`.

## Dilimler
1. E1 E3 E6 G1–G4 K1 K3 K6 A1 X1
2. E2 E5 G5 G7 K4 K7 P1 A2 A3
3. P2 P3 P4 A4 S1–S4 B3 X2 X3
4. Bulut senkron, E7

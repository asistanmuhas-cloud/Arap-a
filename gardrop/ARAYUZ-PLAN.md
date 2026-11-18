# Gardrop — arayüz düzenleme planı

Kaynak: 2026-11-18'de örnek veriyle (9 parça, 4 kombin, 3 fotoğraf) Pixel 7 boyutunda açık ve koyu temada alınmış
ekran görüntüleri. Efor: **S** birkaç saat · **M** yaklaşık bir gün.

Bu incelemede düzeltilen: `hidden` özniteliği `.satir` / `.alan` kurallarına yeniliyordu; link formu ve durum
penceresindeki "teslim tarihi / kime" alanları her zaman görünüyordu (`css/app.css` başına genel kural eklendi).

## 1. Hızlı düzeltmeler (öncelikli)

| # | Ekran | Sorun | Öneri | Efor |
|---|---|---|---|---|
| 1 | Her yer | Fotoğrafsız parçanın yer tutucusunda yazı kesiliyor ("Spor ayakk", "Pantolo") | Yazı yerine kategoriye göre SVG siluet (tişört, pantolon, elbise, mont, ayakkabı, çanta), parçanın rengiyle boyanmış; ad kartın altında zaten var | M |
| 2 | Kombinler | Kayıtlı kombinlerin hepsi "Kombin" adını taşıyor, ayırt edilemiyor | Ad boşsa parçalardan otomatik ad ("Yeşil üst + kot"); altında ortam ve "son giyilme: 12 gün önce" | S |
| 3 | Bugün | Öneri kartında yatay şerit 4. parçayı kesiyor, kaydırılabildiği belli değil; 4–5 gerekçe çipi kalabalık | Öneriyi kolajla göster (kayıtlı kombinlerle aynı dil); gerekçeleri tek satır metne indir, "Uyum %89" küçük rozet olsun | S |
| 4 | Bugün | "Giyildi" etiketi kartın tüm genişliğine yayılıyor; 3 parçalı kolajda sağda boşluk kalıyor | Etiketi başlığın yanına rozet olarak taşı; kolaj kartın genişliğini doldursun | S |
| 5 | Bugün | Hatırlatmalar düz metin; dokunulabilir olduğu anlaşılmıyor | Küçük görsel + sağda ok olan liste satırı (Analiz'deki listelerle aynı) | S |
| 6 | Parça detayı | 5 eylem düğmesi iki satıra taşıyor; "Sil" ile "Arşive kaldır" yan yana ve bildirimin altında kalıyor | "Bugün giydim" tek ana düğme; Düzenle ve Fotoğraf görselin üstünde ikon düğme; Arşiv / Sil "⋯" menüsünde | M |
| 7 | Parça detayı | Fotoğrafsız parçada dev renkli daire ekranın yarısını kaplıyor | Yer tutucuyu küçült, içine "Fotoğraf ekle" çağrısı koy | S |
| 8 | Kombinler | "Ne giysem?" paneli ilk ekranın yarısını kaplıyor; yüzen "Kombin kur" düğmesi son kartın üstüne biniyor | Paneli katlanır yap (seçimler hatırlansın) ya da çipleri tek satır kaydırılabilir yap; liste altına yüzen düğme kadar boşluk | S |
| 9 | Takvim | Ay okları küçük (dokunma hedefi 44 px altında); boş günler çok yer tutuyor | Okları büyüt; hafta görünümü seçeneği (planlama çoğunlukla haftalık) | M |
| 10 | Koyu tema | Lacivert / siyah parçaların yer tutucusu arka planda kayboluyor | Yer tutucuya ince açık halka; renk kontrastına göre kenar | S |

## 2. Akış iyileştirmeleri

- **Parça ekle ekranının altı boş.** Son eklenen 6 parçayı ve "toplu eklemede ilk 3 fotoğrafı bekle" gibi ipuçlarını göster. Fotoğrafsız ekleme ve link aynı satırda kalabilir. (S)
- **Kombin kur:** seçilen parçalar üstteki özette kolaj olarak duruyor; kaydet düğmesi sayfanın en altında kalıyor. Alt sabit çubuk: "3 parça · Uyum iyi · Kaydet". (S)
- **Boş ve yükleniyor durumları:** bölüm geçişlerinde "Yükleniyor…" yazısı yerine kart iskeleti; ilk kullanımda Bugün ekranına 3 adımlı başlangıç kartı (şehir seç → 5 parça ekle → ilk öneri). (M)
- **Analiz uzun tek sütun:** üstte sekme ya da çip ile "Kullanım · Değer · Maliyet · Unutulanlar" bölümlerine atla. (S)

## 3. Görsel kimlik

- Kategori siluetleri (madde 1) aynı zamanda alt sekmeler ve filtre çiplerinde ikon olarak kullanılabilir; uygulama tek bir görsel dile kavuşur.
- Kart kenarları ve gölgeler tutarlı değil (öneri kartı gölgesiz, kombin kartı kenarlı, detay kutusu ikisi de): tek kart stili belirle.
- Başlık yazı tipi sistem yazısı; başlıklar için tek bir karakterli yazı tipi (ör. yerel olarak sunulan bir değişken yazı tipi) uygulamaya kimlik verir. Çevrimdışı çalıştığı için dosya `vendor/` altına konmalı.

## Önerilen sıra

1. Madde 1, 2, 3, 10: bir arada yapılır, en görünür etki (yaklaşık 1,5 gün).
2. Madde 4–8 ve kombin kur alt çubuğu (yaklaşık 1 gün).
3. Takvim hafta görünümü, başlangıç kartı, analiz sekmeleri.
4. Görsel kimlik.

Her adımdan sonra `test/tarayici.cjs` çalıştırılmalı; seçiciler (`#giydim`, `#kaydet`, `.parca-kart`) değişirse test de güncellenir.

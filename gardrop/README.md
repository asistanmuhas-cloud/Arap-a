# Gardrop

Kıyafet takibi ve kombin planlama uygulaması. Telefona kurulan web uygulaması (PWA); derleme adımı yok,
veriler cihazda (IndexedDB) durur, isteğe bağlı Supabase ile cihazlar arası senkron yapar.

**Yerelde çalıştırma:** `cd gardrop && python3 -m http.server 8822` → http://localhost:8822
(kamera, telefona kurulum ve çevrimdışı çalışma için yayında HTTPS gerekir).

**Yayınlama:** `sudo bash gardrop/deploy/kur.sh gardrop.alanadin.com` (nginx + certbot).
**Bulut:** `supabase/KURULUM.md`.

Bölümler: Bugün (hava, plan, öneri, hatırlatmalar) · Gardrop (arama, filtre, durum, arşiv) · Kombinler
(elle kurma, karıştır, kurallı öneri, puan, kapsül) · Takvim (plan, hava, tekrar uyarısı) · Analiz
(giyim başı maliyet, unutulanlar, istatistik) · Alışveriş (istek listesi, almadan önce test, eksikler,
elden çıkarma) · Seyahat bavulu · Profiller · Yedekleme.

Özellik listesi ve durumu: `PLAN.md`.

Arka plan silme `vendor/arka-plan.js`: @imgly/background-removal 1.4.5, AGPL-3.0 (`vendor/arka-plan.LICENSE.md`).
Model ilk kullanımda staticimgly.com'dan iner (~55 MB) ya da `kur.sh --model` ile sunucudan sunulur.

# Bulut senkronu kurulumu (Supabase)

İsteğe bağlıdır. Kurulmazsa uygulama her şeyi cihazda tutar; yedekleme Ayarlar'dan yapılır.
Kurulunca telefon ve bilgisayar aynı gardrobu görür, linkten ürün ekleme (E7) çalışır.

1. https://supabase.com üzerinde ücretsiz bir proje aç.
2. **SQL Editor** → `kurulum.sql` dosyasının tamamını yapıştır → Run.
3. **Authentication → Providers → Email** açık olsun. Onay e-postası istemiyorsan "Confirm email"i kapatabilirsin.
4. **Authentication → URL Configuration → Site URL**: uygulamanın adresi (ör. `https://gardrop.fremensu.com.tr`).
5. **Project Settings → API**: *Project URL* ve *anon / publishable key*'i kopyala.
   Bu anahtar herkese açık olacak şekilde tasarlanmıştır; verini satır düzeyi güvenlik (RLS) korur.
   `service_role` anahtarını asla uygulamaya girme.
6. Uygulamada **Ayarlar → Bulut senkron**: adresi ve anahtarı gir → Bağlan → Hesap oluştur / Giriş yap.

## Linkten ürün ekleme fonksiyonu (E7)

Supabase CLI ile (bir kez):

```sh
supabase login
supabase link --project-ref <proje-kimligi>
supabase functions deploy urun-cek          # JWT doğrulaması açık kalsın: --no-verify-jwt KULLANMA
```

Fonksiyon yalnızca giriş yapmış kullanıcıya yanıt verir, yalnız http(s) linklerine gider, özel/yerel ağ
adreslerini reddeder ve her yönlendirmede bunu yeniden kontrol eder. Bazı mağazalar bot isteklerini
engeller; o zaman uygulama linki kaydeder, fotoğrafı elle eklersin.

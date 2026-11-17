const { chromium, devices } = require('playwright');
const URL = process.env.GARDROP_URL || 'http://localhost:8822/';
process.chdir(__dirname);
(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ ...devices['Pixel 7'], timezoneId: 'Europe/Istanbul', locale: 'tr-TR' });
  const hatalar = [];
  const p = await ctx.newPage();
  p.on('pageerror', (e) => hatalar.push('pageerror: ' + e.message));
  p.on('console', (m) => { if (m.type() === 'error') hatalar.push('console: ' + m.text().slice(0, 200)); });
  const bugun = new Date();
  const gun = (i) => { const d = new Date(bugun); d.setDate(d.getDate() + i); return d.toISOString().slice(0, 10); };
  await ctx.route('https://api.open-meteo.com/**', (r) => r.fulfill({ json: { current: { temperature_2m: 9, weather_code: 3 }, daily: { time: [0, 1, 2, 3, 4, 5, 6].map(gun), temperature_2m_max: [12, 13, 11, 10, 14, 15, 12], temperature_2m_min: [5, 6, 4, 3, 7, 8, 5], precipitation_probability_max: [10, 60, 0, 0, 20, 0, 0], weather_code: [3, 63, 1, 0, 2, 0, 1] } } }));
  await ctx.route('https://geocoding-api.open-meteo.com/**', (r) => r.fulfill({ json: { results: [{ name: 'İstanbul', admin1: 'İstanbul', country: 'Türkiye', latitude: 41.01, longitude: 28.97 }] } }));
  const adim = async (ad, fn) => {
    const t = Date.now();
    try { await fn(); console.log('OK', ad, Date.now() - t + 'ms'); }
    catch (e) { console.log('FAIL', ad, e.message.split('\n')[0]); await p.screenshot({ path: 'fail.png' }); throw e; }
  };
  await adim('açılış', async () => { await p.goto(URL); await p.waitForSelector('text=Hava durumuna göre öneri'); });
  await adim('şehir seç', async () => { await p.goto(URL + '#/ayarlar'); await p.fill('#sehir', 'istanbul'); await p.click('#ara'); await p.click('#sonuclar .cip'); await p.waitForSelector('text=Seçili:'); });
  await adim('fotoğraflı ekleme + arka plan', async () => {
    await p.goto(URL + '#/ekle'); await p.waitForSelector('#galeri', { state: 'attached' });
    await p.setInputFiles('#galeri', 'tisort.jpg');
    await p.waitForSelector('text=Arka plan silindi', { timeout: 120000 });
    const ana = await p.$eval('[data-cip-grup="anaRenk"] .cip[aria-pressed="true"]', (e) => e.dataset.deger);
    console.log('   önerilen ana renk:', ana);
    await p.click('[data-cip-grup="altKategori"] .cip >> text=Tişört');
    await p.fill('#f-fiyat', '400');
    await p.click('#kaydet'); await p.waitForURL(/#\/parca\//); await p.waitForSelector('text=Bugün giydim');
  });
  const hizli = async (kat, alt, renk) => {
    await p.goto(URL + '#/ekle'); await p.click('#fotografsiz');
    await p.click(`[data-cip-grup="kategori"] .cip[data-deger="${kat}"]`);
    await p.click(`[data-cip-grup="altKategori"] .cip >> text="${alt}"`);
    await p.click(`[data-cip-grup="anaRenk"] .cip[data-deger="${renk}"]`);
    await p.click('#kaydet'); await p.waitForURL(/#\/parca\//);
  };
  await adim('fotoğrafsız 5 parça', async () => { await hizli('alt', 'Kot', 'denim'); await hizli('alt', 'Pantolon', 'siyah'); await hizli('ayakkabi', 'Spor ayakkabı', 'beyaz'); await hizli('dis', 'Mont', 'lacivert'); await hizli('ust', 'Kazak', 'gri'); });
  await adim('gardrop + arama', async () => { await p.goto(URL + '#/gardrop'); await p.waitForSelector('text=6 parça'); await p.fill('#ara', 'kot'); await p.waitForSelector('text=1 parça'); });
  await adim('bugün önerisi (9°C mont içerir)', async () => { await p.goto(URL + '#/bugun'); await p.waitForSelector('.oneri'); const t = await p.textContent('#oneriler'); if (!/Mont/.test(t)) throw new Error('Montsuz öneri: ' + t.slice(0, 200)); });
  await adim('elle kombin kur', async () => {
    await p.goto(URL + '#/kombin-kur/yeni'); await p.waitForSelector('#parcalar [data-parca]');
    for (const i of [0, 1, 3]) await p.click(`#parcalar [data-parca] >> nth=${i}`);
    await p.fill('#ad', 'Test kombini'); await p.click('#kaydet'); await p.waitForURL(/#\/kombin\//);
  });
  await adim('puan + takvime ekle + giydim', async () => {
    await p.click('[data-puan="4"]'); await p.waitForSelector('[data-puan="4"] .yildiz');
    await p.click('#takvim'); await p.fill('#t-etkinlik', 'Ofis'); await p.click('#pencere #kaydet');
    await p.click('#giydim'); await p.waitForSelector('text=Bugün giyildi · geri al');
  });
  await adim('takvim gösteriyor', async () => { await p.goto(URL + '#/takvim'); await p.waitForSelector('.gun.bugun.giyildi'); await p.waitForSelector('text=Test kombini'); });
  await adim('tekrar uyarısı', async () => {
    await p.goto(URL + '#/kombinler'); await p.click('.kombin-kart'); await p.click('#takvim');
    await p.fill('#t-tarih', gun(3)); await p.fill('#t-etkinlik', 'ofis'); await p.waitForSelector('#uyari .hata-kutu'); await p.click('#pencere [data-kapat]');
  });
  await adim('analiz', async () => { await p.goto(URL + '#/analiz'); await p.waitForSelector('text=En çok giyilenler'); await p.waitForSelector('text=₺400'); });
  await adim('alışveriş + test', async () => {
    await p.goto(URL + '#/alisveris'); await p.click('#ekle'); await p.fill('#i-ad', 'Bej pantolon');
    await p.click('#pencere [data-cip-grup="kategori"] .cip[data-deger="alt"]'); await p.click('#pencere [data-cip-grup="renk"] .cip[data-deger="bej"]'); await p.click('#pencere #kaydet');
    await p.click('[data-test]'); await p.waitForSelector('text=yeni kombin'); await p.click('#pencere [data-kapat]');
    await p.click('[data-sekme="eksik"]'); await p.waitForSelector('text=Temel parçalar'); await p.click('[data-sekme="cikar"]');
  });
  await adim('kapsül', async () => {
    await p.goto(URL + '#/kapsul'); await p.click('[data-parca] >> nth=0'); await p.waitForTimeout(300); await p.click('[data-parca] >> nth=3'); await p.waitForTimeout(300);
    console.log('   kapsül:', (await p.textContent('.sayilar')).replace(/\s+/g, ' '));
  });
  await adim('seyahat', async () => {
    await p.goto(URL + '#/seyahat'); await p.click('#yeni'); await p.fill('#s-ad', 'İzmir'); await p.fill('#s-sehir', 'istanbul'); await p.click('#pencere #ara'); await p.click('#sonuclar .cip'); await p.fill('#s-bit', gun(2)); await p.click('#pencere #kaydet');
    await p.waitForURL(/#\/seyahat\//); await p.click('#hepsini'); await p.waitForSelector('[data-topla]');
    console.log('   bavul:', (await p.$$('[data-topla]')).length, 'parça');
  });

  await adim('büyük fotoğraf (4000×3000) + toplu ekleme (E5)', async () => {
    const jpeg = async (w, h, renk) => Buffer.from((await p.evaluate(([w, h, renk]) => {
      const c = document.createElement('canvas'); c.width = w; c.height = h; const x = c.getContext('2d');
      x.fillStyle = '#d8d4cc'; x.fillRect(0, 0, w, h); x.fillStyle = renk;
      x.fillRect(w * 0.3, h * 0.2, w * 0.4, h * 0.65); x.fillRect(w * 0.18, h * 0.2, w * 0.64, h * 0.15);
      return c.toDataURL('image/jpeg', 0.9).split(',')[1];
    }, [w, h, renk])), 'base64');
    await p.goto(URL + '#/ekle'); await p.waitForSelector('#galeri', { state: 'attached' });
    await p.setInputFiles('#galeri', [
      { name: 'buyuk.jpg', mimeType: 'image/jpeg', buffer: await jpeg(4000, 3000, '#1f7a4d') },
      { name: 'ikinci.jpg', mimeType: 'image/jpeg', buffer: await jpeg(900, 1200, '#f0c020') },
    ]);
    await p.waitForSelector('text=Parça 1 / 2');
    await p.waitForSelector('#onizleme img', { timeout: 60000 });
    // arka plan silme bitmeden kaydet: sonuç beklenip kaydedilmeli
    await p.click('#kaydet');
    await p.waitForSelector('text=Parça 2 / 2', { timeout: 120000 });
    await p.waitForSelector('text=Arka plan silindi', { timeout: 120000 });
    await p.click('#kaydet'); await p.waitForURL(/#\/gardrop/);
    await p.waitForTimeout(400); await p.fill('#ara', '');
    await p.waitForSelector('text=8 parça');
  });
  await adim('ilk toplu parçanın arka planı silinmiş kaydedildi', async () => {
    const tur = await p.evaluate(async () => {
      const v = await import('./js/veri.js'); const l = await v.hepsi('parcalar');
      const yesil = l.find((x) => ['yesil', 'zumrut'].includes(x.renkler?.[0]));
      if (!yesil) return ['yeşil parça yok: ' + l.map((x) => x.renkler?.[0]).join(','), 0];
      const g = await v.gorselOku(yesil.gorsel); return [g.blob.type, g.blob.size];
    });
    console.log('   kayıtlı görsel:', tur);
    if (!/webp|png/.test(tur[0])) throw new Error('arka plansız (saydam) görsel kaydedilmedi');
  });
  await adim('filtre penceresi', async () => {
    await p.goto(URL + '#/gardrop'); await p.waitForTimeout(300); await p.fill('#ara', '');
    await p.click('#filtre-ac'); await p.click('#pencere [data-cip-grup="renk"] .cip[data-deger="siyah"]'); await p.click('#pencere #uygula');
    await p.waitForSelector('text=1 parça'); await p.waitForSelector('#filtre-ac >> text=Filtre (1)');
    await p.click('#filtre-ac'); await p.click('#pencere #temizle'); await p.waitForSelector('text=8 parça');
  });
  await adim('düzenle + arşiv + geri al', async () => {
    await p.click('.parca-kart >> nth=2'); await p.click('#duzenle'); await p.fill('#pencere #f-ad', 'Deneme adı'); await p.click('#pencere #kaydet');
    await p.waitForSelector('h2 >> text=Deneme adı');
    await p.click('#arsivle'); await p.click('#pencere .cip[data-deger="satildi"]'); await p.click('#pencere #kaydet');
    await p.waitForSelector('text=Arşivde: Satıldı'); await p.click('#arsivden'); await p.waitForSelector('#arsivle');
  });
  await adim('Kombinler: Öner, Karıştır, kaydet, beğenmedim', async () => {
    await p.goto(URL + '#/kombinler'); await p.waitForSelector('.kombin-liste .kombin-kart'); const once = (await p.$$('.kombin-liste .kombin-kart')).length;
    await p.click('#oner'); await p.waitForSelector('#oneriler .oneri');
    await p.click('#oneriler [data-eylem="kaydet"] >> nth=0'); await p.waitForSelector('#bildirim >> text=/Kombinlere kaydedildi|zaten kayıtlı/'); console.log('   bildirim:', await p.textContent('#bildirim'));
    await p.click('#oneriler [data-eylem="begenmedim"] >> nth=1'); await p.waitForTimeout(500);
    await p.click('#karistir'); await p.waitForSelector('#oneriler .oneri');
    await p.goto(URL + '#/bugun'); await p.goto(URL + '#/kombinler'); await p.waitForTimeout(300);
    const sonra = (await p.$$('.kombin-liste .kombin-kart')).length;
    console.log('   kombin sayısı', once, '→', sonra);
  });
  await adim('takvim gün penceresi: öner → planla, kayıtlıdan seç', async () => {
    await p.goto(URL + '#/takvim'); await p.click('.gun.bugun ~ .gun >> nth=1');
    await p.click('#pencere #oner'); await p.waitForSelector('#pencere [data-eylem="planla"]');
    await p.click('#pencere [data-eylem="planla"] >> nth=0'); await p.click('#pencere #kaydet'); await p.waitForTimeout(400);
    await p.click('.gun.bugun ~ .gun >> nth=3'); await p.click('#pencere #sec'); await p.click('#pencere [data-kombin] >> nth=0'); await p.click('#pencere #kaydet'); await p.waitForTimeout(400);
    const plan = await p.evaluate(async () => (await (await import('./js/veri.js')).hepsi('plan')).length);
    console.log('   plan sayısı:', plan); if (plan < 3) throw new Error('günler planlanmadı');
  });
  await adim('"giyince kirli" ayarı', async () => {
    await p.goto(URL + '#/ayarlar'); await p.check('#kirli');
    await p.goto(URL + '#/kombinler'); await p.click('.kombin-liste .kombin-kart >> nth=0');
    const metin = await p.textContent('#giydim'); if (/geri al/.test(metin)) { await p.click('#giydim'); await p.waitForTimeout(300); }
    await p.click('#giydim'); await p.waitForTimeout(400);
    const kirli = await p.evaluate(async () => (await (await import('./js/veri.js')).hepsi('parcalar')).filter((x) => x.durum === 'kirli').length);
    console.log('   kirli parça:', kirli); if (!kirli) throw new Error('kirliye düşmedi');
    await p.goto(URL + '#/ayarlar'); await p.uncheck('#kirli'); await p.click('#hepsi-temiz'); await p.waitForTimeout(300);
  });
  await adim('istek → Aldım, eksikten isteğe', async () => {
    await p.goto(URL + '#/alisveris'); await p.click('[data-sekme="istek"]'); await p.click('[data-menu] >> nth=0'); await p.click('#pencere #aldim');
    await p.waitForURL(/#\/parca\//); await p.waitForSelector('h2 >> text=Bej pantolon');
    await p.goto(URL + '#/alisveris'); await p.click('[data-sekme="eksik"]'); await p.click('[data-istek] >> nth=0'); await p.waitForTimeout(300);
    const istek = await p.evaluate(async () => (await (await import('./js/veri.js')).hepsi('istek')).filter((x) => !x.alindi).map((x) => x.ad + ':' + x.kategori));
    console.log('   eksikten istek:', istek);
  });
  await adim('kapsül kaydet + bavul işaretle', async () => {
    await p.goto(URL + '#/kapsul'); await p.fill('#ad', 'Hafta sonu'); await p.click('#kaydet'); await p.waitForSelector('[data-kapsul] >> text=Hafta sonu');
    await p.goto(URL + '#/seyahat'); await p.click('.liste a >> nth=0'); await p.check('[data-topla] >> nth=0'); await p.waitForTimeout(400);
    await p.waitForSelector('text=/1\\/\\d+ toplandı/');
  });
  await adim('durum: terzide + hatırlatma', async () => {
    await p.goto(URL + '#/gardrop'); await p.waitForTimeout(400); await p.fill('#ara', ''); await p.click('.parca-kart >> nth=1'); await p.click('#durum-ac'); await p.click('#pencere .cip[data-deger="terzi"]'); await p.fill('#teslim', gun(0)); await p.click('#pencere #kaydet');
    await p.goto(URL + '#/bugun'); await p.waitForSelector('text=Bugün teslim al');
  });
  await adim('profil ekle ve geri dön', async () => {
    await p.click('#profil-dugme'); await p.fill('#profil-adi', 'Ayşe'); await p.click('#yeni-profil button'); await p.waitForSelector('#profil-ad >> text=Ayşe');
    await p.goto(URL + '#/gardrop'); await p.waitForSelector('text=Gardrobun boş'); await p.click('#profil-dugme'); await p.click('[data-profil] >> text=Ben'); await p.waitForSelector('#profil-ad >> text=Ben');
  });
  await adim('paylaş görseli', async () => { await p.goto(URL + '#/kombinler'); await p.click('.kombin-kart'); await p.click('#paylas'); await p.waitForSelector('#pencere img[alt="Kombin görseli"]', { timeout: 15000 }); await p.screenshot({ path: 'paylas.png' }); await p.click('#pencere [data-kapat]'); });
  await adim('yedek dışa aktar', async () => {
    await p.goto(URL + '#/ayarlar'); const [dl] = await Promise.all([p.waitForEvent('download'), p.click('#yedek-al')]); await dl.saveAs('yedek.json');
    const j = require('./yedek.json'); console.log('   yedek:', Object.entries(j.depolar).map(([k, v]) => k + ':' + v.length).join(' '), 'gorsel:', j.gorseller.length);
  });
  await adim('yenileyince veri kalıyor', async () => { await p.reload(); await p.goto(URL + '#/gardrop'); await p.waitForTimeout(400); await p.fill('#ara', ''); await p.waitForSelector('text=9 parça'); });
  await p.screenshot({ path: 'gardrop.png' });
  await adim('çevrimdışı açılış', async () => {
    await p.evaluate(() => navigator.serviceWorker.ready); await p.reload(); await p.waitForTimeout(1000);
    await ctx.setOffline(true); await p.reload(); await p.goto(URL + '#/kombinler'); await p.waitForSelector('text=Test kombini'); await ctx.setOffline(false);
  });
  await adim('yedekten geri yükle (yeni tarayıcı)', async () => {
    const c2 = await b.newContext({ ...devices['Pixel 7'] }); const p2 = await c2.newPage();
    await p2.goto(URL + '#/ayarlar'); await p2.setInputFiles('#yedek-yukle', 'yedek.json'); await p2.waitForTimeout(1500);
    await p2.goto(URL + '#/gardrop'); await p2.waitForSelector('text=9 parça'); await p2.waitForSelector('img[data-gorsel][src]'); await c2.close();
  });
  for (const [ad, yol] of [['bugun', '#/bugun'], ['takvim', '#/takvim'], ['analiz', '#/analiz']]) { await p.goto(URL + yol); await p.waitForTimeout(600); await p.screenshot({ path: ad + '.png' }); }
  console.log('yatay taşma:', await p.evaluate(() => document.documentElement.scrollWidth > innerWidth));
  console.log('HATALAR:', hatalar.length ? hatalar : 'yok');
  await b.close();
})().catch(() => { console.log('DURDU'); process.exit(1); });

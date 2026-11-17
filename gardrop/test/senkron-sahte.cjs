// Sahte Supabase (PostgREST + Auth + Storage alt kümesi) ile iki cihaz arası senkron testi.
const { chromium, devices } = require('playwright');
const URL = process.env.GARDROP_URL || 'http://localhost:8822/';
process.chdir(__dirname);
const SB = 'https://sahte.supabase.co';
const satirlar = new Map(); // key depo|id -> {depo,id,guncelleme,veri,degisim}
const nesneler = new Map();
let saat = Date.parse('2026-01-01T00:00:00Z');
async function sahte(route) {
  const r = route.request(); const u = new globalThis.URL(r.url()); const yol = u.pathname;
  if (r.method() === 'OPTIONS') return route.fulfill({ status: 200, headers: { 'access-control-allow-origin': '*', 'access-control-allow-headers': '*', 'access-control-allow-methods': '*' } });
  const h = { 'access-control-allow-origin': '*' };
  if (yol === '/auth/v1/token') return route.fulfill({ headers: h, json: { access_token: 'jeton', refresh_token: 'yenile', expires_in: 3600, user: { id: 'kullanici-1' } } });
  if (r.headers().authorization !== 'Bearer jeton') return route.fulfill({ status: 401, headers: h, json: { message: 'yetkisiz' } });
  if (yol === '/rest/v1/kayitlar' && r.method() === 'POST') {
    for (const s of JSON.parse(r.postData())) {
      const k = s.depo + '|' + s.id; const eski = satirlar.get(k);
      if (eski && eski.guncelleme > s.guncelleme) continue;
      satirlar.set(k, { ...s, degisim: new Date(saat += 1000).toISOString() });
    }
    return route.fulfill({ status: 201, headers: h, body: '' });
  }
  if (yol === '/rest/v1/kayitlar') {
    const gt = u.searchParams.get('degisim').slice(3);
    const l = [...satirlar.values()].filter((s) => s.degisim > gt).sort((a, b) => a.degisim.localeCompare(b.degisim)).slice(0, +u.searchParams.get('limit'));
    return route.fulfill({ headers: h, json: l });
  }
  if (yol.startsWith('/storage/v1/object/') && r.method() === 'POST') { nesneler.set(yol.replace('/storage/v1/object/', ''), { body: r.postDataBuffer(), tur: r.headers()['content-type'] }); return route.fulfill({ headers: h, json: { Key: 'ok' } }); }
  if (yol.startsWith('/storage/v1/object/authenticated/')) {
    const n = nesneler.get(yol.replace('/storage/v1/object/authenticated/', ''));
    return n ? route.fulfill({ headers: { ...h, 'content-type': n.tur }, body: n.body }) : route.fulfill({ status: 404, headers: h, json: { message: 'yok' } });
  }
  return route.fulfill({ status: 404, headers: h, json: { message: 'bilinmeyen ' + yol } });
}
(async () => {
  const b = await chromium.launch();
  const cihaz = async () => { const c = await b.newContext({ ...devices['Pixel 7'] }); await c.route(SB + '/**', sahte); const p = await c.newPage(); p.on('pageerror', (e) => console.log('pageerror', e.message)); return { c, p }; };
  const baglan = async (p) => {
    await p.goto(URL + '#/ayarlar'); await p.fill('#b-url', SB); await p.fill('#b-anahtar', 'anon'); await p.click('#b-kur');
    await p.fill('#b-eposta', 'a@b.c'); await p.fill('#b-parola', 'parola123'); await p.click('#b-giris');
    await p.waitForSelector('text=ile bağlı.');
  };
  const A = await cihaz();
  await A.p.goto(URL + '#/ayarlar'); await A.p.setInputFiles('#yedek-yukle', 'yedek.json'); await A.p.waitForTimeout(1500);
  await baglan(A.p);
  console.log('sunucu satır:', satirlar.size, 'nesne:', nesneler.size);
  const B = await cihaz();
  await baglan(B.p);
  await B.p.goto(URL + '#/gardrop'); await B.p.waitForTimeout(500);
  const sayi = await B.p.textContent('#sonuc');
  console.log('B gardrop:', sayi.match(/\d+ parça/)?.[0], 'foto:', !!(await B.p.$('img[data-gorsel][src]')));
  // B'de değişiklik -> A'ya
  const once = await A.p.evaluate(async () => (await import('./js/veri.js')).hepsi('giyim', { tumProfiller: true }).then((l) => l.length)); console.log('A giyim önce:', once); await B.p.click('.parca-kart >> nth=0'); console.log('B düğme:', await B.p.textContent('#giydim')); await B.p.click('#giydim'); await B.p.waitForTimeout(300);
  await B.p.goto(URL + '#/ayarlar'); await B.p.click('#b-senkron'); await B.p.waitForTimeout(800);
  await A.p.goto(URL + '#/ayarlar'); await A.p.click('#b-senkron'); await A.p.waitForTimeout(800);
  const giyim = await A.p.evaluate(async () => (await import('./js/veri.js')).hepsi('giyim', { tumProfiller: true }).then((l) => l.length));
  console.log('A giyim kaydı (B ekledi):', giyim);
  await b.close();
})();

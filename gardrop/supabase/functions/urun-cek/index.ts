// E7: ürün sayfasından ad, marka, fiyat ve görsel çeker.
// Güvenlik: yalnızca giriş yapmış kullanıcı (fonksiyon kendisi de /auth/v1/user ile doğrular), yalnızca http(s),
// özel / yerel ağ adreslerine gitmez (her yönlendirmede yeniden kontrol), boyut ve süre sınırı var.

const SAYFA_SINIR = 3_000_000;
const GORSEL_SINIR = 6_000_000;
const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, apikey, content-type, x-client-info",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

function ozelMi(ip: string): boolean {
  if (ip.includes(":")) {
    const s = ip.toLowerCase();
    if (s === "::1" || s === "::" || s.startsWith("fe80") || s.startsWith("fc") || s.startsWith("fd")) return true;
    const m = s.match(/::ffff:(\d+\.\d+\.\d+\.\d+)$/);
    return m ? ozelMi(m[1]) : false;
  }
  const [a, b] = ip.split(".").map(Number);
  return a === 10 || a === 127 || a === 0 || (a === 169 && b === 254) || (a === 172 && b >= 16 && b <= 31) ||
    (a === 192 && b === 168) || (a === 100 && b >= 64 && b <= 127) || a >= 224;
}
async function guvenliUrl(ham: string): Promise<URL> {
  const u = new URL(ham);
  if (u.protocol !== "https:" && u.protocol !== "http:") throw new Error("Yalnızca http(s) linkleri");
  if (u.port && !["80", "443"].includes(u.port)) throw new Error("Bu port desteklenmiyor");
  const host = u.hostname.replace(/^\[|\]$/g, "");
  if (/^[\d.]+$/.test(host) || host.includes(":")) {
    if (ozelMi(host)) throw new Error("Bu adrese erişilemez");
  } else {
    if (host === "localhost" || host.endsWith(".local") || host.endsWith(".internal")) throw new Error("Bu adrese erişilemez");
    const ipler = [
      ...(await Deno.resolveDns(host, "A").catch(() => [])),
      ...(await Deno.resolveDns(host, "AAAA").catch(() => [])),
    ];
    if (!ipler.length) throw new Error("Alan adı bulunamadı");
    if (ipler.some(ozelMi)) throw new Error("Bu adrese erişilemez");
  }
  return u;
}
async function getir(ham: string, sinir: number): Promise<{ govde: Uint8Array; tur: string; url: string }> {
  let url = ham;
  for (let i = 0; i < 4; i++) {
    const u = await guvenliUrl(url);
    const r = await fetch(u, {
      redirect: "manual",
      signal: AbortSignal.timeout(10_000),
      headers: { "User-Agent": "Mozilla/5.0 (compatible; GardropBot/1.0)", "Accept-Language": "tr,en;q=0.8" },
    });
    if (r.status >= 300 && r.status < 400 && r.headers.get("location")) {
      url = new URL(r.headers.get("location")!, u).href;
      continue;
    }
    if (!r.ok || !r.body) throw new Error(`Sayfa açılamadı (${r.status})`);
    const okuyucu = r.body.getReader();
    const parcalar: Uint8Array[] = [];
    let n = 0;
    for (;;) {
      const { done, value } = await okuyucu.read();
      if (done) break;
      n += value.length;
      if (n > sinir) { await okuyucu.cancel(); throw new Error("Dosya çok büyük"); }
      parcalar.push(value);
    }
    const govde = new Uint8Array(n);
    let o = 0;
    for (const p of parcalar) { govde.set(p, o); o += p.length; }
    return { govde, tur: r.headers.get("content-type") || "", url: u.href };
  }
  throw new Error("Çok fazla yönlendirme");
}

const meta = (html: string, ad: string) => {
  const re = new RegExp(`<meta[^>]+(?:property|name|itemprop)=["']${ad}["'][^>]*>`, "i");
  const m = html.match(re)?.[0];
  return m?.match(/content=["']([^"']*)["']/i)?.[1]?.trim() || "";
};
const coz = (s: string) => s.replace(/&amp;/g, "&").replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&lt;/g, "<").replace(/&gt;/g, ">");

function jsonLdUrun(html: string): Record<string, unknown> | null {
  for (const m of html.matchAll(/<script[^>]+application\/ld\+json[^>]*>([\s\S]*?)<\/script>/gi)) {
    try {
      const j = JSON.parse(m[1]);
      const l = Array.isArray(j) ? j : j["@graph"] || [j];
      const u = l.find((x: Record<string, unknown>) => [].concat(x["@type"] as never).includes("Product" as never));
      if (u) return u;
    } catch { /* geçersiz JSON-LD */ }
  }
  return null;
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  // Ağ geçidinin JWT kontrolüne ek olarak: istek gerçek bir oturum açmış kullanıcıdan mı?
  // Yalnız anon anahtarla gelen istek /auth/v1/user'da kullanıcı döndürmez ve reddedilir.
  const yetki = req.headers.get("authorization") || "";
  const kullanici = await fetch(`${Deno.env.get("SUPABASE_URL")}/auth/v1/user`, {
    headers: { authorization: yetki, apikey: Deno.env.get("SUPABASE_ANON_KEY") || "" },
  }).catch(() => null);
  if (!kullanici?.ok || !(await kullanici.json().catch(() => null))?.id) {
    return Response.json({ error: "Giriş gerekli" }, { status: 401, headers: CORS });
  }
  try {
    const { url } = await req.json();
    if (typeof url !== "string" || url.length > 2000) throw new Error("Geçersiz link");
    const sayfa = await getir(url, SAYFA_SINIR);
    const html = new TextDecoder().decode(sayfa.govde);
    const u = jsonLdUrun(html) as Record<string, any> | null;
    const teklif = u ? [].concat(u.offers || [])[0] as Record<string, any> | undefined : undefined;
    const baslik = coz(String(u?.name || meta(html, "og:title") || html.match(/<title>([^<]*)<\/title>/i)?.[1] || "")).trim().slice(0, 120);
    const marka = coz(String((typeof u?.brand === "object" ? u?.brand?.name : u?.brand) || meta(html, "product:brand") || "")).slice(0, 60);
    const fiyatHam = String(teklif?.price ?? teklif?.lowPrice ?? meta(html, "product:price:amount") ?? meta(html, "og:price:amount") ?? "");
    const fiyat = fiyatHam ? Number(fiyatHam.replace(/[^\d.,]/g, "").replace(/\.(?=\d{3}(\D|$))/g, "").replace(",", ".")) || null : null;
    const magaza = coz(meta(html, "og:site_name") || new URL(sayfa.url).hostname.replace(/^www\./, "")).slice(0, 60);
    const gorselUrl = [].concat(u?.image || [])[0] as unknown;
    const gorselHam = (typeof gorselUrl === "object" && gorselUrl ? (gorselUrl as Record<string, string>).url : gorselUrl as string) || meta(html, "og:image");
    let gorsel: string | null = null;
    if (gorselHam) {
      try {
        const g = await getir(new URL(coz(gorselHam), sayfa.url).href, GORSEL_SINIR);
        if (g.tur.startsWith("image/")) {
          let ikili = "";
          for (let i = 0; i < g.govde.length; i += 0x8000) ikili += String.fromCharCode(...g.govde.subarray(i, i + 0x8000));
          gorsel = `data:${g.tur.split(";")[0]};base64,${btoa(ikili)}`;
        }
      } catch { /* görsel alınamazsa yalnız metin döner */ }
    }
    return Response.json({ baslik, marka, fiyat, magaza, gorsel }, { headers: CORS });
  } catch (e) {
    return Response.json({ error: (e as Error).message }, { status: 400, headers: CORS });
  }
});

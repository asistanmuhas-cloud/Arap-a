"""5 sayfalık test: Gemini ile OCR -> harekeleme (rasm kontrollü) -> Türkçe çeviri.

Kullanım:
    pip install google-genai
    export GEMINI_API_KEY=...
    python arapca_test.py sayfa1.jpg sayfa2.jpg ...
Çıktı: sonuc/<dosya>.json ve sonuc/rapor.md
"""
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
from pathlib import Path

MODEL = os.environ.get("ARAPCA_MODEL", "gemini-3.5-flash")
OCR_MODEL = os.environ.get("ARAPCA_OCR_MODEL", MODEL)  # katman ayrımı için daha güçlü model verilebilir
# Düşünme tokenları çıktı fiyatından faturalanır; harekelemede sınırsız bırakılınca sayfa başına ~40 bin token yaktı.
AZ_DUSUN = {"thinking_config": {"thinking_level": "low"}}
HAREKE = re.compile(r"[ً-ْٰـ]")  # tenvin..sükun, hançer elif, tatvil

OCR_PROMPT = """Bu, klasik bir Arapça fıkıh kitabının (matn + şerh + hâşiye) taranmış sayfasıdır.
Sayfadaki metni okuma sırasına göre bloklara ayır:
- "serh": çerçeve içindeki ana metin (matn ifadeleri parantez içinde geçer, parantezleri koru)
- "hasiye": çerçevenin üstündeki/altındaki metin ve kenardaki sütun ("قوله" ile başlayan talikler)
- "diger": sayfa numarası, bölüm başlığı, alt not
Kurallar: harfleri olduğu gibi yaz, düzeltme/modernleştirme yapma; baskıdaki harekeleri koru,
yenisini ekleme; okunamayan kelimeyi [?] yap; satır sonu kesmelerini birleştir.
Her bloğun sayfadaki yerini "kutu" alanına [ymin, xmin, ymax, xmax] olarak 0-1000 arası normalize tam sayılarla yaz."""

HAREKE_PROMPT = """Aşağıdaki klasik Arapça metni tam harekele (i'râb dahil).
SADECE hareke ekle: hiçbir harfi, hemzeyi, noktalamayı veya boşluğu değiştirme, ekleme, silme.
Yalnızca harekeli metni döndür.

{metin}"""

CEVIRI_PROMPT = """Aşağıdaki Hanefî fıkıh metnini akademik Türkçeye çevir.
Parantez içindeki matn ifadelerini kalın (**...**) yaz. Fıkıh terimlerini yerleşik Türkçe
karşılıklarıyla ver (ör. farz, vacip, mesh). Yalnızca çeviriyi döndür.

{metin}"""

OCR_SCHEMA = {
    "type": "object",
    "properties": {
        "bloklar": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "tur": {"type": "string", "enum": ["serh", "hasiye", "diger"]},
                    "metin": {"type": "string"},
                    "kutu": {"type": "array", "items": {"type": "integer"}, "minItems": 4, "maxItems": 4},
                },
                "required": ["tur", "metin"],
            },
        }
    },
    "required": ["bloklar"],
}


def rasm(metin: str) -> str:
    """Harekeleri atılmış iskelet; harekeleme harf değiştirdi mi diye karşılaştırmak için."""
    return HAREKE.sub("", metin).strip()


IMLA = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي"})


def imla(metin: str) -> str:
    """Hemze kürsüsü, elif-i maksûre/yâ ve boşluk farklarını yok sayan gevşek iskelet."""
    return re.sub(r"\s+", "", metin.translate(IMLA))


def rasm_kontrol(kaynak: str, harekeli: str) -> dict:
    """ayni: harfi harfine aynı. imla: yalnızca hemze/yâ/boşluk farkı var. farklar: gerçek harf değişimleri."""
    a, b = rasm(kaynak), rasm(harekeli)
    x, y = imla(a), imla(b)
    farklar = [f"{x[max(0, i1 - 6):i2 + 6]} → {y[max(0, j1 - 6):j2 + 6]}"
               for t, i1, i2, j1, j2 in SequenceMatcher(None, x, y, autojunk=False).get_opcodes() if t != "equal"]
    return {"ayni": a == b, "imla": x == y, "farklar": farklar,
            "benzerlik": round(SequenceMatcher(None, a, b).ratio(), 4)}


def cagir(client, contents, model=None, **config):
    from google.genai import errors

    for deneme in range(6):
        try:
            yanit = client.models.generate_content(model=model or MODEL, contents=contents, config=config or None)
            if not (yanit.text or "").strip():
                raise RuntimeError(f"boş yanıt (finish_reason={yanit.candidates[0].finish_reason if yanit.candidates else None})")
            return yanit
        except errors.APIError as e:
            if deneme == 5 or getattr(e, "code", 0) not in (429, 500, 503):
                raise
            time.sleep(10 * (deneme + 1))


def parcali(uret, metin: str, derinlik: int = 0) -> str:
    """uret(metin) -> str. Gemini klasik metni "ezber" sayıp boş dönerse (RECITATION) metni ikiye bölüp dener."""
    try:
        return uret(metin)
    except RuntimeError as e:
        orta = metin.find(" ", len(metin) // 2)
        if "RECITATION" not in str(e) or derinlik >= 3 or orta < 0:
            raise
        return parcali(uret, metin[:orta], derinlik + 1) + " " + parcali(uret, metin[orta + 1:], derinlik + 1)


def jeton(yanit) -> list:
    """[girdi, çıktı] token sayısı; çıktıya düşünme tokenları dahildir (onlar da faturalanır)."""
    u = yanit.usage_metadata
    return [u.prompt_token_count or 0, (u.candidates_token_count or 0) + (u.thoughts_token_count or 0)]


def isle(client, yol: Path) -> dict:
    from google.genai import types

    resim = types.Part.from_bytes(data=yol.read_bytes(), mime_type="image/jpeg")
    ocr = cagir(client, [resim, OCR_PROMPT], model=OCR_MODEL,
                response_mime_type="application/json", response_schema=OCR_SCHEMA)
    bloklar = json.loads(ocr.text)["bloklar"]
    kullanim = {"ocr": jeton(ocr), "hareke": [0, 0], "ceviri": [0, 0]}
    def doldur(b):
        def uret(ad, sablon):
            def tek(metin):
                yanit = cagir(client, sablon.format(metin=metin), **AZ_DUSUN)
                kullanim[ad] = [x + z for x, z in zip(kullanim[ad], jeton(yanit))]
                return yanit.text.strip()
            return parcali(tek, b["metin"])

        with ThreadPoolExecutor(2) as h:  # harekeleme ve çeviri birbirinden bağımsız
            hareke, ceviri = h.submit(uret, "hareke", HAREKE_PROMPT), h.submit(uret, "ceviri", CEVIRI_PROMPT)
            b["harekeli"], b["ceviri"] = hareke.result(), ceviri.result()
        b["rasm"] = rasm_kontrol(b["metin"], b["harekeli"])

    with ThreadPoolExecutor(4) as h:
        list(h.map(doldur, [b for b in bloklar if b["tur"] != "diger"]))
    return {"dosya": yol.name, "model": MODEL, "ocr_model": OCR_MODEL, "jeton_girdi_cikti": kullanim, "bloklar": bloklar}


def rapor(sonuclar: list) -> str:
    satirlar = []
    for s in sonuclar:
        satirlar.append(f"# {s['dosya']} ({s.get('model', 'gemini-3.5-flash')})\n")
        for b in s.get("bloklar", []):
            if b["tur"] == "diger":
                continue
            r = rasm_kontrol(b["metin"], b["harekeli"])  # eski json'larda yeni alanlar olmayabilir
            isaret = ("✅" if r["ayni"] else "🟡 yalnız imla (hemze/yâ/boşluk)" if r.get("imla")
                      else "⚠️ harf değişti: " + " | ".join(r.get("farklar", [])[:10]))
            satirlar += [f"## {b['tur']} — rasm: {isaret}\n", f"<div dir=rtl>\n\n{b['harekeli']}\n\n</div>\n",
                         f"{b['ceviri']}\n"]
        if "hata" in s:
            satirlar.append(f"**HATA:** {s['hata']}\n")
    return "\n".join(satirlar)


def main(yollar):
    from google import genai

    client = genai.Client(http_options={"api_version": "v1beta"})  # önizleme modelleri yalnız v1beta'da; anahtar GEMINI_API_KEY'den
    cikti = Path("sonuc")
    cikti.mkdir(exist_ok=True)

    def sayfa(y: Path) -> dict:
        hedef = cikti / f"{y.stem}.json"
        if hedef.exists():  # başarıyla bitmiş sayfayı yeniden işleme (API masrafı)
            eski = json.loads(hedef.read_text(encoding="utf-8"))
            if "hata" not in eski:
                return eski
        print(f"→ {y.name}", flush=True)
        try:
            s = isle(client, y)
        except Exception as e:  # bir sayfa patlarsa diğerleri devam etsin
            s = {"dosya": y.name, "hata": f"{type(e).__name__}: {e}"}
        hedef.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
        return s

    with ThreadPoolExecutor(5) as h:
        sonuclar = list(h.map(sayfa, map(Path, yollar)))
    (cikti / "rapor.md").write_text(rapor(sonuclar), encoding="utf-8")
    print("Bitti: sonuc/rapor.md")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1:])

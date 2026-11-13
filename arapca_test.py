"""5 sayfalık test: Gemini ile OCR -> harekeleme (rasm kontrollü) -> Türkçe çeviri.

Kullanım:
    pip install google-genai
    export GEMINI_API_KEY=...
    python arapca_test.py sayfa1.jpg sayfa2.jpg ...
Çıktı: sonuc/<dosya>.json ve sonuc/rapor.md
"""
import json
import re
import sys
import time
from difflib import SequenceMatcher
from pathlib import Path

MODEL = "gemini-3.5-flash"
HAREKE = re.compile(r"[ً-ْٰـ]")  # tenvin..sükun, hançer elif, tatvil

OCR_PROMPT = """Bu, klasik bir Arapça fıkıh kitabının (matn + şerh + hâşiye) taranmış sayfasıdır.
Sayfadaki metni okuma sırasına göre bloklara ayır:
- "serh": çerçeve içindeki ana metin (matn ifadeleri parantez içinde geçer, parantezleri koru)
- "hasiye": çerçevenin üstündeki/altındaki metin ve kenardaki sütun ("قوله" ile başlayan talikler)
- "diger": sayfa numarası, bölüm başlığı, alt not
Kurallar: harfleri olduğu gibi yaz, düzeltme/modernleştirme yapma; baskıdaki harekeleri koru,
yenisini ekleme; okunamayan kelimeyi [?] yap; satır sonu kesmelerini birleştir."""

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


def rasm_kontrol(kaynak: str, harekeli: str) -> dict:
    a, b = rasm(kaynak), rasm(harekeli)
    return {"ayni": a == b, "benzerlik": round(SequenceMatcher(None, a, b).ratio(), 4)}


def cagir(client, contents, **config):
    from google.genai import errors

    for deneme in range(3):
        try:
            return client.models.generate_content(model=MODEL, contents=contents, config=config or None)
        except errors.APIError as e:
            if deneme == 2 or getattr(e, "code", 0) not in (429, 500, 503):
                raise
            time.sleep(5 * (deneme + 1))


def isle(client, yol: Path) -> dict:
    from google.genai import types

    resim = types.Part.from_bytes(data=yol.read_bytes(), mime_type="image/jpeg")
    ocr = cagir(client, [resim, OCR_PROMPT],
                response_mime_type="application/json", response_schema=OCR_SCHEMA)
    bloklar = json.loads(ocr.text)["bloklar"]
    for b in bloklar:
        if b["tur"] == "diger":
            continue
        b["harekeli"] = cagir(client, HAREKE_PROMPT.format(metin=b["metin"])).text.strip()
        b["rasm"] = rasm_kontrol(b["metin"], b["harekeli"])
        b["ceviri"] = cagir(client, CEVIRI_PROMPT.format(metin=b["metin"])).text.strip()
    return {"dosya": yol.name, "bloklar": bloklar}


def rapor(sonuclar: list) -> str:
    satirlar = []
    for s in sonuclar:
        satirlar.append(f"# {s['dosya']}\n")
        for b in s.get("bloklar", []):
            if b["tur"] == "diger":
                continue
            r = b["rasm"]
            isaret = "✅" if r["ayni"] else f"⚠️ harf değişti (benzerlik {r['benzerlik']})"
            satirlar += [f"## {b['tur']} — rasm: {isaret}\n", f"<div dir=rtl>\n\n{b['harekeli']}\n\n</div>\n",
                         f"{b['ceviri']}\n"]
        if "hata" in s:
            satirlar.append(f"**HATA:** {s['hata']}\n")
    return "\n".join(satirlar)


def main(yollar):
    from google import genai

    client = genai.Client()  # GEMINI_API_KEY ortam değişkeninden okunur
    cikti = Path("sonuc")
    cikti.mkdir(exist_ok=True)
    sonuclar = []
    for y in map(Path, yollar):
        print(f"→ {y.name}", flush=True)
        try:
            s = isle(client, y)
        except Exception as e:  # bir sayfa patlarsa diğerleri devam etsin
            s = {"dosya": y.name, "hata": f"{type(e).__name__}: {e}"}
        (cikti / f"{y.stem}.json").write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
        sonuclar.append(s)
    (cikti / "rapor.md").write_text(rapor(sonuclar), encoding="utf-8")
    print("Bitti: sonuc/rapor.md")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1:])

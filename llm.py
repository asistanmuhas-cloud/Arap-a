"""Bütün LLM çağrıları buradan geçer; adım bazında model değiştirmek için MODELLER'i ya da
MODEL_<ADIM> ortam değişkenini (ör. MODEL_OCR=gemini-3.8-flash) kullan. Kitap ayarındaki katman modeli (çeviri)
model= ile verilir ve ikisinden de önce gelir. Gece kuyruğu (Batch API) aynı model/tavan/düşünme/fiyat kurallarını
kullanır; fiyatı BATCH_ORAN ile çarpılır. HAREKE_KOMUT ayarlıysa harekeleme yerel komutla yapılır (yerel_hareke)."""
import mimetypes
import os
import shlex
import subprocess
from datetime import date
import time
from pathlib import Path

MODELLER = {
    "ocr": "gemini-3.8-flash",  # en zor test sayfasında katmanları 3.1 Pro ile aynı ayırdı, üçte bir fiyatına
    "ocr2": "gemini-3.5-flash",  # çift okuma: karşılaştırma için ikinci okuma; birincilden FARKLI bir model olmalı
    "hareke": "gemini-3.8-flash",
    "ceviri": "gemini-3.8-flash",
    "agent": "gemini-3.8-flash",
    "sozluk": "gemini-3.1-flash-lite",  # onaylı pasajlardan sözlük adayı (istek üzerine)
}
# USD / 1M token: (girdi, çıktı). Çıktıya düşünme tokenları dahildir.
FIYAT = {
    "gemini-3.5-flash": (1.50, 9.00),
    "gemini-3.1-flash-lite": (0.25, 1.50),
    "gemini-3.1-pro-preview": (2.00, 12.00),  # 200 bin tokena kadar olan istekler için (ai.google.dev fiyat sayfası)
    "gemini-3.8-flash": (0.75, 3.75),  # tanıtım fiyatı; bitişi ZAMLI'da
}
# Tanıtım fiyatı biten modeller: (yeni fiyatın başladığı gün, yeni fiyat)
ZAMLI = {"gemini-3.8-flash": (date(2027, 1, 1), (1.50, 7.50))}
# Kaçak (sonu gelmeyen) bir yanıt faturayı şişirmesin diye adım başına çıktı tavanı (token).
CIKTI_TAVANI = {"ocr": 16000, "ocr2": 16000, "ceviri": 16000, "hareke": 24000, "agent": 4000, "sozluk": 4000}
AZ_DUSUNEN = ("hareke", "ceviri", "ocr2", "sozluk")  # düşünme tokenları çıktı fiyatından faturalanır; bu adımlarda kıs
BATCH_ORAN = 0.5  # Batch API fiyatı normal fiyatın yarısı
# Inline batch isteğinin toplam boyu için güvenli sınır (bayt, görüntüler base64 olarak): aşılırsa görüntüler File API
# ile yüklenip istekte dosya adresiyle verilir. (Batch API belgelerindeki inline sınırı 20 MB; SDK'da denetim yok.)
BATCH_INLINE_SINIR = 18 * 1024 * 1024
HAREKE_ZAMAN = 120  # yerel harekeleme komutunun zaman aşımı (sn)
_client = None


def istemci():
    global _client
    if _client is None:
        from google import genai

        _client = genai.Client(http_options={"api_version": "v1beta"})  # anahtar GEMINI_API_KEY'den; önizleme modelleri yalnız v1beta'da
    return _client


def model_sec(adim: str, model: str = None) -> str:
    """Kitap ayarı (model) > MODEL_<ADIM> ortam değişkeni > MODELLER."""
    return model or os.environ.get(f"MODEL_{adim.upper()}") or MODELLER[adim]


def fiyat(model: str, bugun: date = None):
    """(girdi, çıktı) USD / 1M token; bugünün tarihine göre (tanıtım fiyatı bittiyse zamlı). Tabloda yoksa None."""
    baslangic, zamli = ZAMLI.get(model, (None, None))
    return zamli if baslangic and (bugun or date.today()) >= baslangic else FIYAT.get(model)


def maliyet(model: str, girdi: int, cikti: int) -> float:
    """Tahmini USD; tabloda olmayan model için en pahalı girdi/çıktı fiyatı varsayılır."""
    hepsi = [fiyat(m) for m in FIYAT]
    f_girdi, f_cikti = fiyat(model) or (max(f[0] for f in hepsi), max(f[1] for f in hepsi))
    return (girdi * f_girdi + cikti * f_cikti) / 1_000_000


def resim(yol: Path):
    from google.genai import types

    tur = mimetypes.guess_type(yol.name)[0] or "image/jpeg"
    return types.Part.from_bytes(data=yol.read_bytes(), mime_type=tur)


def _ayar(adim: str, config: dict) -> dict:
    if adim in AZ_DUSUNEN:
        config.setdefault("thinking_config", {"thinking_level": "low"})
    config.setdefault("max_output_tokens", CIKTI_TAVANI[adim])
    return config


def _kullanim(model: str, yanit, oran: float = 1.0) -> dict:
    u = yanit.usage_metadata
    girdi = (u and u.prompt_token_count) or 0
    cikti = ((u and u.candidates_token_count) or 0) + ((u and u.thoughts_token_count) or 0)
    return {"model": model, "girdi": girdi, "cikti": cikti, "maliyet": maliyet(model, girdi, cikti) * oran}


def _metin(model: str, yanit, tavan: int) -> str:
    """Yanıt metni; boş ya da tavanda kesilmiş yanıt hata (RuntimeError)."""
    neden = yanit.candidates[0].finish_reason if yanit.candidates else None
    if getattr(neden, "name", neden) == "MAX_TOKENS":
        raise RuntimeError(f"{model} çıktı tavanına ({tavan} token) ulaştı; yanıt kesik")
    if not (yanit.text or "").strip():
        raise RuntimeError(f"{model} boş yanıt döndürdü (finish_reason={getattr(neden, 'name', neden)})")
    return yanit.text.strip()


def llm(adim: str, contents, kayit=None, model: str = None, **config) -> str:
    """Metni döndürür. Geçici hatalarda (429/500/503) 3 kez dener; boş ya da tavanda kesilmiş yanıt hata sayılır.
    kayit({"model", "girdi", "cikti", "maliyet"}) faturalanan her yanıt için (boş olanlar dahil) çağrılır."""
    from google.genai import errors

    model = model_sec(adim, model)
    config = _ayar(adim, config)
    for deneme in range(3):
        try:
            yanit = istemci().models.generate_content(model=model, contents=contents, config=config)
        except errors.APIError as e:  # hata yanıtları faturalanmaz; yeniden denenebilir
            gunluk_kota = "per day" in str(e)  # beklemekle geçmez
            if deneme == 2 or gunluk_kota or getattr(e, "code", 0) not in (429, 500, 503):
                raise
            time.sleep(5 * (deneme + 1))
            continue
        if kayit:
            kayit(_kullanim(model, yanit))
        return _metin(model, yanit, config["max_output_tokens"])


# ---------- yerel harekeleme ----------
def yerel_hareke(metin: str, komut: str) -> str:
    """HAREKE_KOMUT'u kabuksuz çalıştırır: metin stdin'den (UTF-8) gider, harekeli metin stdout'tan okunur.
    Metin hiçbir zaman komut satırına girmez. Zaman aşımı, sıfırdan farklı çıkış kodu ve boş çıktı hatadır."""
    try:
        argv = shlex.split(komut)
    except ValueError as e:
        raise RuntimeError(f"HAREKE_KOMUT ayrıştırılamadı: {e}")
    if not argv:
        raise RuntimeError("HAREKE_KOMUT boş")
    try:
        r = subprocess.run(argv, input=metin.encode("utf-8"), capture_output=True, timeout=HAREKE_ZAMAN, shell=False)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"yerel harekeleme {HAREKE_ZAMAN} sn içinde bitmedi (zaman aşımı)")
    except OSError as e:
        raise RuntimeError(f"yerel harekeleme komutu çalıştırılamadı: {e}")
    hata = r.stderr.decode("utf-8", "replace").strip()[-300:]
    if r.returncode != 0:
        raise RuntimeError(f"yerel harekeleme komutu {r.returncode} koduyla çıktı" + (f": {hata}" if hata else ""))
    cikti = r.stdout.decode("utf-8", "replace").strip()
    if not cikti:
        raise RuntimeError("yerel harekeleme komutu boş çıktı verdi" + (f" ({hata})" if hata else ""))
    return cikti


# ---------- gece kuyruğu (Gemini Batch API) ----------
BATCH_BEKLIYOR = {"JOB_STATE_UNSPECIFIED", "JOB_STATE_QUEUED", "JOB_STATE_PENDING", "JOB_STATE_RUNNING",
                  "JOB_STATE_CANCELLING", "JOB_STATE_PAUSED", "JOB_STATE_UPDATING"}
BATCH_BITTI = {"JOB_STATE_SUCCEEDED", "JOB_STATE_PARTIALLY_SUCCEEDED"}  # tek tek yanıtlarda hata olabilir


def batch_gonder(adim: str, istekler: list, model: str = None, ad: str = "") -> dict:
    """istekler: [(anahtar, contents, config)]; contents içindeki Path bir sayfa görüntüsüdür. Model, çıktı tavanı ve
    düşünme seviyesi llm() ile aynı kurallardan gelir. Görüntülerin toplam boyu (base64) BATCH_INLINE_SINIR'ı aşarsa
    görüntüler File API ile yüklenir. Döner: {ad, adim, model, anahtarlar, dosyalar} (veritabanında saklanır)."""
    from google.genai import types

    model = model_sec(adim, model)
    yollar = {x for _, ct, _ in istekler if isinstance(ct, list) for x in ct if isinstance(x, Path)}
    boy = sum(y.stat().st_size for y in yollar) * 4 / 3 + sum(len(str(ct).encode()) for _, ct, _ in istekler)
    yuklenen = {}
    try:
        if boy > BATCH_INLINE_SINIR:
            for y in sorted(yollar):
                yuklenen[y] = istemci().files.upload(file=y, config={"mime_type": mimetypes.guess_type(y.name)[0]
                                                                     or "image/jpeg"})
        parca = lambda x: (types.Part.from_uri(file_uri=yuklenen[x].uri, mime_type=yuklenen[x].mime_type)  # noqa: E731
                           if x in yuklenen else resim(x)) if isinstance(x, Path) else x
        src = [{"contents": [parca(x) for x in ct] if isinstance(ct, list) else ct, "metadata": {"anahtar": a},
                "config": _ayar(adim, dict(cfg))} for a, ct, cfg in istekler]
        is_ = istemci().batches.create(model=model, src=src, config={"display_name": ad or adim})
    except Exception:
        dosya_sil([f.name for f in yuklenen.values()])
        raise
    return {"ad": is_.name, "adim": adim, "model": model, "anahtarlar": [a for a, _, _ in istekler],
            "dosyalar": [f.name for f in yuklenen.values()]}


def batch_durum(uzak: dict) -> dict:
    """{"durum": "bekliyor"|"tamam"|"hata", "hata", "yanitlar": {anahtar: {"metin"|"hata", "kayit"}}}. kayit
    (yarı fiyatlı kullanım) faturalanan her yanıtta var, boş/kesik olanlarda da. Yanıt, isteğin metadata'sındaki
    anahtarla eşlenir; metadata dönmezse istek sırasıyla."""
    is_ = istemci().batches.get(name=uzak["ad"])
    durum = str(getattr(is_.state, "value", is_.state) or "")
    if durum in BATCH_BEKLIYOR:
        return {"durum": "bekliyor", "hata": None, "yanitlar": {}}
    if durum not in BATCH_BITTI:
        neden = is_.error.message if is_.error and is_.error.message else ""
        return {"durum": "hata", "hata": f"{durum}" + (f": {neden}" if neden else ""), "yanitlar": {}}
    hedef = is_.dest
    liste = (hedef and hedef.inlined_responses) or []
    if not liste and hedef and hedef.file_name:
        return {"durum": "hata", "hata": f"sonuçlar dosyada ({hedef.file_name}); dosya çıktısı desteklenmiyor",
                "yanitlar": {}}
    tavan = CIKTI_TAVANI[uzak["adim"]]
    yanitlar = {}
    for i, r in enumerate(liste):
        anahtar = (r.metadata or {}).get("anahtar") or (uzak["anahtarlar"][i] if i < len(uzak["anahtarlar"]) else None)
        if anahtar is None:
            continue
        if r.error:  # hata yanıtı faturalanmaz
            yanitlar[anahtar] = {"hata": f"{r.error.code or ''} {r.error.message or 'hata'}".strip(), "kayit": None}
        elif r.response:
            kayit = _kullanim(uzak["model"], r.response, BATCH_ORAN)
            try:
                yanitlar[anahtar] = {"metin": _metin(uzak["model"], r.response, tavan), "kayit": kayit}
            except RuntimeError as e:
                yanitlar[anahtar] = {"hata": str(e), "kayit": kayit}
    for a in uzak["anahtarlar"]:
        yanitlar.setdefault(a, {"hata": "yanıt dönmedi", "kayit": None})
    return {"durum": "tamam", "hata": None, "yanitlar": yanitlar}


def batch_iptal(ad: str):
    istemci().batches.cancel(name=ad)


def dosya_sil(adlar: list):
    """File API'ye yüklenen görüntüleri siler (en iyi çaba; dosyalar 48 saatte kendiliğinden de silinir)."""
    for ad in adlar:
        try:
            istemci().files.delete(name=ad)
        except Exception:
            pass

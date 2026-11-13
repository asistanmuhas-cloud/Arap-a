"""Bütün LLM çağrıları buradan geçer; adım bazında model değiştirmek için MODELLER'i ya da
MODEL_<ADIM> ortam değişkenini (ör. MODEL_OCR=gemini-3.8-flash) kullan."""
import mimetypes
import os
import time
from pathlib import Path

MODELLER = {
    "ocr": "gemini-3.1-pro-preview",  # katman (şerh/hâşiye) ayrımını testte yalnız bu doğru yaptı
    "ocr2": "gemini-3.5-flash",  # çift okuma: yalnızca karşılaştırma için ikinci okuma (kitap ayarı)
    "hareke": "gemini-3.5-flash",
    "ceviri": "gemini-3.5-flash",
    "agent": "gemini-3.5-flash",
}
# USD / 1M token: (girdi, çıktı). Çıktıya düşünme tokenları dahildir.
FIYAT = {
    "gemini-3.5-flash": (1.50, 9.00),
    "gemini-3.1-flash-lite": (0.25, 1.50),
    "gemini-3.1-pro-preview": (2.00, 12.00),  # doğrula: resmî fiyat sayfasıyla karşılaştırılmadı
}
# Kaçak (sonu gelmeyen) bir yanıt faturayı şişirmesin diye adım başına çıktı tavanı (token).
CIKTI_TAVANI = {"ocr": 16000, "ocr2": 16000, "ceviri": 16000, "hareke": 24000, "agent": 4000}
_client = None


def maliyet(model: str, girdi: int, cikti: int) -> float:
    """Tahmini USD; tabloda olmayan model için en pahalı girdi/çıktı fiyatı varsayılır."""
    f_girdi, f_cikti = FIYAT.get(model) or (max(f[0] for f in FIYAT.values()), max(f[1] for f in FIYAT.values()))
    return (girdi * f_girdi + cikti * f_cikti) / 1_000_000


def resim(yol: Path):
    from google.genai import types

    tur = mimetypes.guess_type(yol.name)[0] or "image/jpeg"
    return types.Part.from_bytes(data=yol.read_bytes(), mime_type=tur)


def llm(adim: str, contents, kayit=None, **config) -> str:
    """Metni döndürür. Geçici hatalarda (429/500/503) 3 kez dener; boş ya da tavanda kesilmiş yanıt hata sayılır.
    kayit({"model", "girdi", "cikti", "maliyet"}) faturalanan her yanıt için (boş olanlar dahil) çağrılır."""
    global _client
    from google import genai
    from google.genai import errors

    if _client is None:
        _client = genai.Client(http_options={"api_version": "v1beta"})  # anahtar GEMINI_API_KEY'den; önizleme modelleri yalnız v1beta'da
    model = os.environ.get(f"MODEL_{adim.upper()}") or MODELLER[adim]
    if adim in ("hareke", "ceviri", "ocr2"):  # düşünme tokenları çıktı fiyatından faturalanır; bu adımlarda kıs
        config.setdefault("thinking_config", {"thinking_level": "low"})
    config.setdefault("max_output_tokens", CIKTI_TAVANI[adim])
    for deneme in range(3):
        try:
            yanit = _client.models.generate_content(model=model, contents=contents, config=config)
        except errors.APIError as e:  # hata yanıtları faturalanmaz; yeniden denenebilir
            gunluk_kota = "per day" in str(e)  # beklemekle geçmez
            if deneme == 2 or gunluk_kota or getattr(e, "code", 0) not in (429, 500, 503):
                raise
            time.sleep(5 * (deneme + 1))
            continue
        u = yanit.usage_metadata
        girdi = (u and u.prompt_token_count) or 0
        cikti = ((u and u.candidates_token_count) or 0) + ((u and u.thoughts_token_count) or 0)
        if kayit:
            kayit({"model": model, "girdi": girdi, "cikti": cikti, "maliyet": maliyet(model, girdi, cikti)})
        neden = yanit.candidates[0].finish_reason if yanit.candidates else None
        if getattr(neden, "name", neden) == "MAX_TOKENS":
            raise RuntimeError(f"{model} çıktı tavanına ({config['max_output_tokens']} token) ulaştı; yanıt kesik")
        if not (yanit.text or "").strip():
            raise RuntimeError(f"{model} boş yanıt döndürdü (finish_reason={neden})")
        return yanit.text.strip()

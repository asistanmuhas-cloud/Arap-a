"""Bütün LLM çağrıları buradan geçer; adım bazında model değiştirmek için MODELLER'i ya da
MODEL_<ADIM> ortam değişkenini (ör. MODEL_OCR=gemini-3.8-flash) kullan."""
import mimetypes
import os
import time
from pathlib import Path

MODELLER = {
    "ocr": "gemini-3.5-flash",
    "hareke": "gemini-3.5-flash",
    "ceviri": "gemini-3.5-flash",
    "agent": "gemini-3.5-flash",
    "ask": "gemini-3.1-flash-lite",
}
_client = None


def resim(yol: Path):
    from google.genai import types

    tur = mimetypes.guess_type(yol.name)[0] or "image/jpeg"
    return types.Part.from_bytes(data=yol.read_bytes(), mime_type=tur)


def llm(adim: str, contents, **config) -> str:
    """Metni döndürür. Geçici hatalarda (429/500/503) 3 kez dener; boş yanıt hata sayılır."""
    global _client
    from google import genai
    from google.genai import errors

    if _client is None:
        _client = genai.Client(http_options={"api_version": "v1beta"})  # anahtar GEMINI_API_KEY'den; önizleme modelleri yalnız v1beta'da
    model = os.environ.get(f"MODEL_{adim.upper()}") or MODELLER[adim]
    if adim in ("hareke", "ceviri"):  # düşünme tokenları çıktı fiyatından faturalanır; bu adımlarda kıs
        config.setdefault("thinking_config", {"thinking_level": "low"})
    for deneme in range(3):
        try:
            yanit = _client.models.generate_content(model=model, contents=contents, config=config or None)
            if not (yanit.text or "").strip():
                neden = yanit.candidates[0].finish_reason if yanit.candidates else None
                raise RuntimeError(f"{model} boş yanıt döndürdü (finish_reason={neden})")
            return yanit.text.strip()
        except errors.APIError as e:
            gunluk_kota = "per day" in str(e)  # beklemekle geçmez
            if deneme == 2 or gunluk_kota or getattr(e, "code", 0) not in (429, 500, 503):
                raise
            time.sleep(5 * (deneme + 1))

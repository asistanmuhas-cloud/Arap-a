"""Arapça kitap çeviri çalışma alanı: FastAPI + SQLite + tek HTML sayfası.

Çalıştır:
    pip install -r requirements.txt
    export GEMINI_API_KEY=...
    uvicorn app:app --host 127.0.0.1 --port 8000
Veri: data/kitap.db ve data/sayfa/ (ARAPCA_VERI ile değiştirilebilir).
"""
import io
import json
import os
import re
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

import llm as llm_modul
from arapca_test import CEVIRI_PROMPT, HAREKE_PROMPT, OCR_PROMPT, OCR_SCHEMA, imla, rasm, rasm_kontrol

KOK = Path(__file__).parent
VERI = Path(os.environ.get("ARAPCA_VERI", KOK / "data"))
RESIM_UZANTI = {".jpg", ".jpeg", ".png", ".webp"}
AZAMI_DOSYA = 200 * 1024 * 1024
TAM_BAGLAM_SINIRI = 300_000  # karakter; kitap bundan küçükse Ask'e tamamı verilir

SEMA = """
CREATE TABLE IF NOT EXISTS pages(
    id INTEGER PRIMARY KEY, no INTEGER NOT NULL, dosya TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS passages(
    id INTEGER PRIMARY KEY, page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    sira INTEGER NOT NULL, tur TEXT NOT NULL, ar TEXT NOT NULL, ar_vocalized TEXT,
    tr TEXT NOT NULL DEFAULT '', durum TEXT NOT NULL DEFAULT 'taslak');
CREATE TABLE IF NOT EXISTS glossary(
    id INTEGER PRIMARY KEY, ar TEXT NOT NULL UNIQUE, tr TEXT NOT NULL);
"""

AGENT_PROMPT = """Aşağıda klasik Hanefî fıkıh metninden bir Arapça pasaj ve Türkçe çevirisi var.
Çeviriyi asılla karşılaştır; yalnızca gerçek sorunlar için düzeltme öner: yanlış anlam, atlanmış ifade,
yanlış ya da tutarsız terim. Üslup zevki için öneri yapma; sorun yoksa boş liste döndür.
Her öneride "eski" çeviride BİREBİR geçen kısa bir parça, "yeni" onun yerine konacak metin olsun.
{sozluk}
ARAPÇA:
{ar}

ÇEVİRİ:
{tr}"""
AGENT_SCHEMA = {
    "type": "object",
    "properties": {"oneriler": {"type": "array", "items": {
        "type": "object",
        "properties": {"eski": {"type": "string"}, "yeni": {"type": "string"}, "gerekce": {"type": "string"}},
        "required": ["eski", "yeni", "gerekce"]}}},
    "required": ["oneriler"],
}
ASK_PROMPT = """Aşağıdaki kitap pasajlarına dayanarak soruyu Türkçe yanıtla. Dayandığın yeri
[s. N] biçiminde göster. Pasajlarda yanıt yoksa bunu açıkça söyle, uydurma.

PASAJLAR:
{baglam}

SORU: {soru}"""

app = FastAPI(title="Arapça çeviri çalışma alanı")


# ---------- veri katmanı ----------
def db() -> sqlite3.Connection:
    (VERI / "sayfa").mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(VERI / "kitap.db")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    c.executescript(SEMA)
    return c


def sor(sql: str, *a) -> list:
    with closing(db()) as c:
        return [dict(r) for r in c.execute(sql, a)]


def yaz(sql: str, *a) -> int:
    with closing(db()) as c, c:
        return c.execute(sql, a).lastrowid


def bul(tablo: str, kimlik: int) -> dict:
    satir = sor(f"SELECT * FROM {tablo} WHERE id=?", kimlik)
    if not satir:
        raise HTTPException(404, f"{tablo} #{kimlik} bulunamadı")
    return satir[0]


# ---------- yardımcılar ----------
def ai(adim: str, contents, **config) -> str:
    try:
        return llm_modul.llm(adim, contents, **config)
    except Exception as e:  # API/kota/ağ hatası arayüze okunur biçimde gitsin
        raise HTTPException(502, f"{adim}: {type(e).__name__}: {str(e)[:300]}")


def tr_kucuk(s: str) -> str:
    return s.replace("İ", "i").replace("I", "ı").lower()


def sozluk_eslesen(ar: str) -> list:
    """Pasajda (harekesiz, imla farkı gözetmeden) geçen sözlük terimleri."""
    govde = imla(rasm(ar))
    return [t for t in sor("SELECT * FROM glossary ORDER BY ar") if imla(rasm(t["ar"])) in govde]


def sozluk_metni(ar: str) -> str:
    terimler = sozluk_eslesen(ar)
    if not terimler:
        return ""
    return "Terim sözlüğü (bu karşılıkları kullan):\n" + "\n".join(f"- {t['ar']} = {t['tr']}" for t in terimler) + "\n"


def zengin(p: dict) -> dict:
    """Pasaja hesaplanan alanları ekler: rasm kontrolü ve sözlük sapmaları."""
    p["rasm"] = rasm_kontrol(p["ar"], p["ar_vocalized"]) if p["ar_vocalized"] else None
    p["sapma"] = ([t for t in sozluk_eslesen(p["ar"]) if tr_kucuk(t["tr"]) not in tr_kucuk(p["tr"])]
                  if p["tr"].strip() else [])
    return p


# ---------- sayfalar ----------
@app.get("/")
def anasayfa():
    return FileResponse(KOK / "index.html")


@app.get("/api/pages")
def sayfalar():
    return sor("""SELECT p.id, p.no,
                  (SELECT COUNT(*) FROM passages WHERE page_id=p.id AND tur!='diger') AS pasaj,
                  (SELECT COUNT(*) FROM passages WHERE page_id=p.id AND tur!='diger' AND durum='onayli') AS onayli
                  FROM pages p ORDER BY p.no""")


@app.post("/api/upload")
async def yukle(dosyalar: list[UploadFile]):
    """JPG/PNG sayfa görüntüleri ya da PDF (her sayfası 200 dpi JPG'ye çevrilir)."""
    eklenen = 0
    for d in sorted(dosyalar, key=lambda d: d.filename or ""):
        uzanti = Path(d.filename or "").suffix.lower()
        veri = await d.read()
        if len(veri) > AZAMI_DOSYA:
            raise HTTPException(413, f"{d.filename}: 200 MB sınırını aşıyor")
        if uzanti == ".pdf":
            import pymupdf

            try:
                belge = pymupdf.open(stream=veri, filetype="pdf")
            except Exception as e:
                raise HTTPException(400, f"{d.filename}: PDF açılamadı ({e})")
            goruntuler = [(".jpg", s.get_pixmap(dpi=200).tobytes("jpeg")) for s in belge]
        elif uzanti in RESIM_UZANTI:
            goruntuler = [(uzanti, veri)]
        else:
            raise HTTPException(400, f"{d.filename}: yalnızca PDF, JPG, PNG, WEBP kabul edilir")
        for uz, icerik in goruntuler:
            no = sor("SELECT COALESCE(MAX(no),0)+1 AS n FROM pages")[0]["n"]
            ad = f"{no:04d}{uz}"
            (VERI / "sayfa").mkdir(parents=True, exist_ok=True)
            (VERI / "sayfa" / ad).write_bytes(icerik)
            yaz("INSERT INTO pages(no, dosya) VALUES(?,?)", no, ad)
            eklenen += 1
    return {"eklenen": eklenen}


@app.get("/api/pages/{pid}")
def sayfa(pid: int):
    s = bul("pages", pid)
    s["pasajlar"] = [zengin(p) for p in sor("SELECT * FROM passages WHERE page_id=? ORDER BY sira", pid)]
    return s


@app.get("/api/pages/{pid}/image")
def sayfa_resmi(pid: int):
    yol = VERI / "sayfa" / bul("pages", pid)["dosya"]
    if not yol.exists():
        raise HTTPException(404, "görüntü dosyası yok")
    return FileResponse(yol)


@app.delete("/api/pages/{pid}")
def sayfa_sil(pid: int):
    s = bul("pages", pid)
    yaz("DELETE FROM pages WHERE id=?", pid)
    (VERI / "sayfa" / s["dosya"]).unlink(missing_ok=True)
    return {"silindi": pid}


@app.post("/api/pages/{pid}/ocr")
def ocr(pid: int, zorla: bool = False):
    s = bul("pages", pid)
    emek = sor("SELECT COUNT(*) AS n FROM passages WHERE page_id=? AND (tr!='' OR durum='onayli')", pid)[0]["n"]
    if emek and not zorla:
        raise HTTPException(409, f"Bu sayfada {emek} çevrilmiş/onaylı pasaj var; yeniden OCR bunları siler.")
    ham = ai("ocr", [llm_modul.resim(VERI / "sayfa" / s["dosya"]), OCR_PROMPT],
             response_mime_type="application/json", response_schema=OCR_SCHEMA)
    try:
        bloklar = [b for b in json.loads(ham)["bloklar"] if b["metin"].strip()]
    except (ValueError, KeyError, TypeError) as e:
        raise HTTPException(502, f"OCR yanıtı çözümlenemedi: {e}")
    with closing(db()) as c, c:
        c.execute("DELETE FROM passages WHERE page_id=?", (pid,))
        c.executemany("INSERT INTO passages(page_id, sira, tur, ar) VALUES(?,?,?,?)",
                      [(pid, i, b["tur"], b["metin"].strip()) for i, b in enumerate(bloklar)])
    return sayfa(pid)


# ---------- pasajlar ----------
class PasajGuncelle(BaseModel):
    ar: Optional[str] = Field(None, min_length=1)
    tr: Optional[str] = None
    tur: Optional[Literal["serh", "hasiye", "diger"]] = None
    durum: Optional[Literal["taslak", "onayli"]] = None


@app.patch("/api/passages/{kid}")
def pasaj_guncelle(kid: int, g: PasajGuncelle):
    p = bul("passages", kid)
    alan = g.model_dump(exclude_none=True)
    if g.durum == "onayli" and not alan.get("tr", p["tr"]).strip():
        raise HTTPException(422, "Çevirisi boş pasaj onaylanamaz")
    if "ar" in alan and alan["ar"] != p["ar"]:
        alan["ar_vocalized"] = None  # asıl metin değişti; eski harekeleme artık onu yansıtmıyor
    if alan:
        yaz(f"UPDATE passages SET {', '.join(k + '=?' for k in alan)} WHERE id=?", *alan.values(), kid)
    return zengin(bul("passages", kid))


@app.post("/api/passages/{kid}/translate")
def cevir(kid: int):
    p = bul("passages", kid)
    if p["durum"] == "onayli":
        raise HTTPException(409, "Onaylı pasaj yeniden çevrilmez; önce onayı kaldır")
    tr = ai("ceviri", sozluk_metni(p["ar"]) + CEVIRI_PROMPT.format(metin=p["ar"]))
    yaz("UPDATE passages SET tr=? WHERE id=?", tr, kid)
    return zengin(bul("passages", kid))


@app.post("/api/passages/{kid}/vocalize")
def harekele(kid: int):
    p = bul("passages", kid)
    yaz("UPDATE passages SET ar_vocalized=? WHERE id=?", ai("hareke", HAREKE_PROMPT.format(metin=p["ar"])), kid)
    return zengin(bul("passages", kid))


@app.post("/api/passages/{kid}/agent")
def agent(kid: int):
    p = bul("passages", kid)
    if not p["tr"].strip():
        raise HTTPException(422, "Önce çeviri gerekli")
    ham = ai("agent", AGENT_PROMPT.format(sozluk=sozluk_metni(p["ar"]), ar=p["ar"], tr=p["tr"]),
             response_mime_type="application/json", response_schema=AGENT_SCHEMA)
    try:
        oneriler = json.loads(ham)["oneriler"]
    except (ValueError, KeyError, TypeError) as e:
        raise HTTPException(502, f"Agent yanıtı çözümlenemedi: {e}")
    # uygulanamayan (çeviride birebir geçmeyen) ya da boş değişiklik önerilerini ele
    return [o for o in oneriler if o["eski"] and o["eski"] != o["yeni"] and p["tr"].count(o["eski"]) == 1]


# ---------- sözlük ----------
class Terim(BaseModel):
    ar: str = Field(min_length=1)
    tr: str = Field(min_length=1)


@app.get("/api/glossary")
def sozluk():
    return sor("SELECT * FROM glossary ORDER BY ar")


@app.post("/api/glossary")
def terim_ekle(t: Terim):
    yaz("INSERT INTO glossary(ar, tr) VALUES(?,?) ON CONFLICT(ar) DO UPDATE SET tr=excluded.tr",
        rasm(t.ar), t.tr.strip())
    return sozluk()


@app.delete("/api/glossary/{tid}")
def terim_sil(tid: int):
    bul("glossary", tid)
    yaz("DELETE FROM glossary WHERE id=?", tid)
    return sozluk()


# ---------- Ask ----------
class Soru(BaseModel):
    soru: str = Field(min_length=3)


@app.post("/api/ask")
def ask(s: Soru):
    pasajlar = sor("""SELECT pg.no, p.tur, p.ar, p.tr FROM passages p JOIN pages pg ON pg.id=p.page_id
                      WHERE p.tur!='diger' ORDER BY pg.no, p.sira""")
    if not pasajlar:
        raise HTTPException(422, "Henüz OCR'lanmış pasaj yok")
    if sum(len(p["ar"]) + len(p["tr"]) for p in pasajlar) > TAM_BAGLAM_SINIRI:
        # kitap büyük: sorudaki kelimeleri en çok içeren 20 pasaj
        kelimeler = [k for k in re.findall(r"\w{3,}", tr_kucuk(s.soru))]
        puan = lambda p: sum(k in tr_kucuk(p["tr"]) or k in rasm(p["ar"]) for k in kelimeler)
        pasajlar = [p for p in sorted(pasajlar, key=puan, reverse=True)[:20] if puan(p)]
        if not pasajlar:
            return {"yanit": "Sorudaki kelimelerle eşleşen pasaj bulunamadı.", "pasaj_sayisi": 0}
    baglam = "\n\n".join(f"[s. {p['no']}, {p['tur']}]\n{p['ar']}\n{p['tr']}" for p in pasajlar)
    return {"yanit": ai("ask", ASK_PROMPT.format(baglam=baglam, soru=s.soru)), "pasaj_sayisi": len(pasajlar)}


# ---------- DOCX ----------
@app.get("/api/export.docx")
def docx_cikti(sadece_onayli: bool = False):
    from docx import Document
    from docx.oxml import OxmlElement
    from docx.shared import Pt

    pasajlar = sor(f"""SELECT pg.no, p.* FROM passages p JOIN pages pg ON pg.id=p.page_id
                       WHERE p.tur!='diger' {"AND p.durum='onayli'" if sadece_onayli else ""}
                       ORDER BY pg.no, p.sira""")
    if not pasajlar:
        raise HTTPException(422, "Dışa aktarılacak pasaj yok")
    belge = Document()
    tablo = belge.add_table(rows=0, cols=2)
    tablo.style = "Table Grid"
    for p in pasajlar:
        sol, sag = tablo.add_row().cells
        par = sol.paragraphs[0]
        par.add_run(f"[s. {p['no']} · {p['tur']}] ").italic = True
        for i, parca in enumerate(re.split(r"\*\*(.+?)\*\*", p["tr"], flags=re.S)):  # **matn** -> kalın
            if parca:
                par.add_run(parca).bold = bool(i % 2)
        # rasm kontrolünden geçmeyen harekeleme çıktıya girmez
        temiz = p["ar_vocalized"] and rasm_kontrol(p["ar"], p["ar_vocalized"])["imla"]
        par = sag.paragraphs[0]
        par._p.get_or_add_pPr().append(OxmlElement("w:bidi"))
        kosu = par.add_run(p["ar_vocalized"] if temiz else p["ar"])
        kosu._r.get_or_add_rPr().append(OxmlElement("w:rtl"))
        kosu.font.size = Pt(14)
    tampon = io.BytesIO()
    belge.save(tampon)
    return Response(tampon.getvalue(),
                    media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={"Content-Disposition": 'attachment; filename="ceviri.docx"'})

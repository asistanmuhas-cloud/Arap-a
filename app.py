"""Arapça kitap çeviri çalışma alanı: FastAPI + SQLite + tek HTML sayfası.

Çalıştır:
    pip install -r requirements.txt
    export GEMINI_API_KEY=...
    uvicorn app:app --host 127.0.0.1 --port 8000
Veri: data/kitap.db, data/kitap/ (yüklenen PDF'ler, küçük resimler) ve data/sayfa/ (işlenen sayfa
görüntüleri); ARAPCA_VERI ile değiştirilebilir. Bütçe: GUNLUK_BUTCE_USD (3), AYLIK_BUTCE_USD (30).
"""
import io
import json
import os
import re
import shutil
import sqlite3
import threading
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Literal, Optional
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

import llm as llm_modul
from arapca_test import CEVIRI_PROMPT, HAREKE_PROMPT, OCR_PROMPT, OCR_SCHEMA, imla, parcali, rasm, rasm_kontrol

KOK = Path(__file__).parent
VERI = Path(os.environ.get("ARAPCA_VERI", KOK / "data"))
RESIM_UZANTI = {".jpg", ".jpeg", ".png", ".webp"}
AZAMI_DOSYA = 200 * 1024 * 1024
AZAMI_SECIM = 10  # tek toplu işte en fazla sayfa
KUCUK_GENISLIK = 240  # küçük resim genişliği (piksel)
GUNLUK_BUTCE = float(os.environ.get("GUNLUK_BUTCE_USD", "3"))
AYLIK_BUTCE = float(os.environ.get("AYLIK_BUTCE_USD", "30"))
VARSAYILAN_SAYFA_MALIYETI = 0.10  # USD; defterde geçmiş sayfa yoksa tahmin için

SEMA = """
CREATE TABLE IF NOT EXISTS books(
    id INTEGER PRIMARY KEY, ad TEXT NOT NULL, dosya TEXT, sayfa_sayisi INTEGER NOT NULL,
    olusturma TEXT NOT NULL DEFAULT (datetime('now','localtime')));
CREATE TABLE IF NOT EXISTS pages(
    id INTEGER PRIMARY KEY, no INTEGER NOT NULL, dosya TEXT NOT NULL, book_id INTEGER REFERENCES books(id));
CREATE TABLE IF NOT EXISTS passages(
    id INTEGER PRIMARY KEY, page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    sira INTEGER NOT NULL, tur TEXT NOT NULL, ar TEXT NOT NULL, ar_vocalized TEXT,
    tr TEXT NOT NULL DEFAULT '', durum TEXT NOT NULL DEFAULT 'taslak');
CREATE TABLE IF NOT EXISTS glossary(
    id INTEGER PRIMARY KEY, ar TEXT NOT NULL UNIQUE, tr TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS usage(
    id INTEGER PRIMARY KEY, zaman TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    adim TEXT NOT NULL, model TEXT NOT NULL, girdi INTEGER NOT NULL, cikti INTEGER NOT NULL,
    maliyet REAL NOT NULL, book_id INTEGER, page_id INTEGER);
CREATE INDEX IF NOT EXISTS usage_zaman ON usage(zaman);
"""
# books.dosya: VERI/kitap altındaki PDF yolu; görüntülerden oluşan kitapta NULL (sayfaları yüklenince oluşur).
# pages.no: kitaptaki (PDF'teki) sayfa numarası. usage satırları kitap silinse de kalır (bütçe hesabı için).

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

app = FastAPI(title="Arapça çeviri çalışma alanı")
_hazir: set = set()  # şeması kurulmuş/göçü yapılmış veri dizinleri
_sema_kilidi = threading.Lock()
ISLEM_KILIDI = threading.Lock()  # aynı anda tek sayfa işleme (çift tıklama/iki sekme harcamayı katlamasın)


# ---------- veri katmanı ----------
def gec(c: sqlite3.Connection):
    """Eski şemadan göç: pages.book_id yoksa ekler, sahipsiz sayfaları 'Eski sayfalar' kitabına bağlar."""
    if "book_id" not in [r["name"] for r in c.execute("PRAGMA table_info(pages)")]:
        c.execute("ALTER TABLE pages ADD COLUMN book_id INTEGER REFERENCES books(id)")
    sahipsiz = [r["id"] for r in c.execute("SELECT id FROM pages WHERE book_id IS NULL ORDER BY no, id")]
    if sahipsiz:
        bid = c.execute("INSERT INTO books(ad, sayfa_sayisi) VALUES('Eski sayfalar', ?)", (len(sahipsiz),)).lastrowid
        c.executemany("UPDATE pages SET book_id=?, no=? WHERE id=?", [(bid, n, pid) for n, pid in enumerate(sahipsiz, 1)])
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS pages_kitap_no ON pages(book_id, no)")


def db() -> sqlite3.Connection:
    (VERI / "sayfa").mkdir(parents=True, exist_ok=True)
    (VERI / "kitap").mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(VERI / "kitap.db")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    if VERI not in _hazir:
        with _sema_kilidi:
            if VERI not in _hazir:
                c.executescript(SEMA)
                with c:
                    gec(c)
                _hazir.add(VERI)
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


# ---------- kullanım defteri ve bütçe ----------
def harcama() -> dict:
    h = sor("""SELECT COALESCE(SUM(CASE WHEN zaman >= date('now','localtime') THEN maliyet END), 0) AS bugun,
                      COALESCE(SUM(maliyet), 0) AS bu_ay
               FROM usage WHERE zaman >= date('now','localtime','start of month')""")[0]
    return {**h, "gunluk_sinir": GUNLUK_BUTCE, "aylik_sinir": AYLIK_BUTCE,
            "kalan": max(0.0, min(GUNLUK_BUTCE - h["bugun"], AYLIK_BUTCE - h["bu_ay"]))}


def butce_kontrol():
    h = harcama()
    if h["bugun"] >= GUNLUK_BUTCE:
        raise HTTPException(429, f"Günlük API bütçesi doldu: bugün ${h['bugun']:.2f} harcandı (sınır ${GUNLUK_BUTCE:.2f}). "
                                 "Yarın devam edebilir ya da GUNLUK_BUTCE_USD ile sınırı yükseltebilirsin.")
    if h["bu_ay"] >= AYLIK_BUTCE:
        raise HTTPException(429, f"Aylık API bütçesi doldu: bu ay ${h['bu_ay']:.2f} harcandı (sınır ${AYLIK_BUTCE:.2f}). "
                                 "AYLIK_BUTCE_USD ile sınırı yükseltmeden yeni çağrı yapılmaz.")


def cagri(adim: str, contents, pid: Optional[int], **config) -> str:
    """Bütçeyi denetler, LLM'i çağırır, her yanıtın kullanımını deftere yazar."""
    butce_kontrol()
    kitap = sor("SELECT book_id FROM pages WHERE id=?", pid)[0]["book_id"] if pid else None
    kaydet = lambda k: yaz("INSERT INTO usage(adim, model, girdi, cikti, maliyet, book_id, page_id) VALUES(?,?,?,?,?,?,?)",
                           adim, k["model"], k["girdi"], k["cikti"], k["maliyet"], kitap, pid)
    return llm_modul.llm(adim, contents, kayit=kaydet, **config)


def ai(adim: str, contents, pid: Optional[int] = None, **config) -> str:
    try:
        return cagri(adim, contents, pid, **config)
    except HTTPException:
        raise
    except Exception as e:  # API/kota/ağ hatası arayüze okunur biçimde gitsin
        raise HTTPException(502, f"{adim}: {type(e).__name__}: {str(e)[:300]}")


def ai_parcali(adim: str, istek, metin: str, pid: Optional[int] = None) -> str:
    """istek(parça) -> prompt. RECITATION engelinde metni bölerek dener (bkz. parcali)."""
    try:
        return parcali(lambda m: cagri(adim, istek(m), pid), metin)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"{adim}: {type(e).__name__}: {str(e)[:300]}")


@contextmanager
def tek_is():
    if not ISLEM_KILIDI.acquire(blocking=False):
        raise HTTPException(409, "Başka bir sayfa işleniyor; bitmesini bekle (çift tıklama ya da ikinci sekme olabilir).")
    try:
        yield
    finally:
        ISLEM_KILIDI.release()


@app.get("/api/usage")
def kullanim():
    return harcama()


# ---------- yardımcılar ----------
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


SAYFA_OZETI = """SELECT p.id, p.no, p.book_id,
    (SELECT COUNT(*) FROM passages WHERE page_id=p.id) AS blok,
    (SELECT COUNT(*) FROM passages WHERE page_id=p.id AND tur!='diger') AS pasaj,
    (SELECT COUNT(*) FROM passages WHERE page_id=p.id AND tur!='diger' AND durum='onayli') AS onayli,
    (SELECT COUNT(*) FROM passages WHERE page_id=p.id AND tur!='diger' AND TRIM(tr)='' AND durum!='onayli') AS cevrilmemis
    FROM pages p"""


@app.get("/")
def anasayfa():
    return FileResponse(KOK / "index.html")


# ---------- kitaplar ----------
@app.post("/api/upload")
async def yukle(dosyalar: list[UploadFile]):
    """Her PDF bir kitap olur (sayfalar seçilince görüntüye çevrilir); aynı yüklemedeki
    JPG/PNG/WEBP görüntüleri tek bir kitapta, dosya adı sırasıyla toplanır."""
    import pymupdf

    pdfler, resimler = [], []
    for d in sorted(dosyalar, key=lambda d: d.filename or ""):
        ad = d.filename or "adsız"
        uzanti = Path(ad).suffix.lower()
        if uzanti != ".pdf" and uzanti not in RESIM_UZANTI:
            raise HTTPException(400, f"{ad}: yalnızca PDF, JPG, PNG, WEBP kabul edilir")
        veri = await d.read()
        if len(veri) > AZAMI_DOSYA:
            raise HTTPException(413, f"{ad}: 200 MB sınırını aşıyor")
        try:  # hepsi yazılmadan önce doğrulanır; bozuk dosya yarım kitap bırakmasın
            with pymupdf.open(stream=veri, filetype=uzanti[1:]) as belge:
                if belge.needs_pass:
                    raise ValueError("parola korumalı")
                sayi = belge.page_count
                belge[0].rect  # bozuk görüntü burada hata verir
        except Exception as e:
            raise HTTPException(400, f"{ad}: açılamadı ({e})")
        (pdfler if uzanti == ".pdf" else resimler).append((ad, uzanti, veri, sayi))

    kitaplar = []
    with closing(db()) as c, c:
        for ad, _, veri, sayi in pdfler:
            bid = c.execute("INSERT INTO books(ad, sayfa_sayisi) VALUES(?,?)", (Path(ad).stem, sayi)).lastrowid
            (VERI / "kitap" / str(bid)).mkdir(parents=True, exist_ok=True)
            (VERI / "kitap" / str(bid) / "kaynak.pdf").write_bytes(veri)
            c.execute("UPDATE books SET dosya=? WHERE id=?", (f"{bid}/kaynak.pdf", bid))
            kitaplar.append({"id": bid, "ad": Path(ad).stem, "sayfa_sayisi": sayi})
        if resimler:
            ad = Path(resimler[0][0]).stem + (f" (+{len(resimler) - 1} görüntü)" if len(resimler) > 1 else "")
            bid = c.execute("INSERT INTO books(ad, sayfa_sayisi) VALUES(?,?)", (ad, len(resimler))).lastrowid
            for no, (_, uzanti, veri, _) in enumerate(resimler, 1):
                dosya = f"{bid}-{no:04d}{uzanti}"
                (VERI / "sayfa" / dosya).write_bytes(veri)
                c.execute("INSERT INTO pages(book_id, no, dosya) VALUES(?,?,?)", (bid, no, dosya))
            kitaplar.append({"id": bid, "ad": ad, "sayfa_sayisi": len(resimler)})
    return {"kitaplar": kitaplar}


@app.get("/api/books")
def kitaplar():
    return sor("""SELECT b.*,
        (SELECT COUNT(*) FROM pages pg WHERE pg.book_id=b.id
            AND EXISTS(SELECT 1 FROM passages WHERE page_id=pg.id)) AS islenen,
        (SELECT COUNT(*) FROM passages p JOIN pages pg ON pg.id=p.page_id WHERE pg.book_id=b.id AND p.tur!='diger') AS pasaj,
        (SELECT COUNT(*) FROM passages p JOIN pages pg ON pg.id=p.page_id
            WHERE pg.book_id=b.id AND p.tur!='diger' AND p.durum='onayli') AS onayli,
        (SELECT COALESCE(SUM(maliyet), 0) FROM usage WHERE book_id=b.id) AS maliyet
        FROM books b ORDER BY b.id DESC""")


@app.get("/api/books/{bid}")
def kitap(bid: int):
    k = bul("books", bid)
    satirlar = {s["no"]: s for s in sor(SAYFA_OZETI + " WHERE p.book_id=?", bid)}
    nolar = range(1, k["sayfa_sayisi"] + 1) if k["dosya"] else sorted(satirlar)
    k["sayfalar"] = [satirlar.get(n) or {"id": None, "no": n, "blok": 0, "pasaj": 0, "onayli": 0, "cevrilmemis": 0}
                     for n in nolar]
    return k


class KitapGuncelle(BaseModel):
    ad: str = Field(min_length=1, max_length=200)


@app.patch("/api/books/{bid}")
def kitap_guncelle(bid: int, g: KitapGuncelle):
    bul("books", bid)
    if not g.ad.strip():
        raise HTTPException(422, "Kitap adı boş olamaz")
    yaz("UPDATE books SET ad=? WHERE id=?", g.ad.strip(), bid)
    return bul("books", bid)


@app.delete("/api/books/{bid}")
def kitap_sil(bid: int):
    bul("books", bid)
    dosyalar = [s["dosya"] for s in sor("SELECT dosya FROM pages WHERE book_id=?", bid)]
    with closing(db()) as c, c:
        c.execute("DELETE FROM pages WHERE book_id=?", (bid,))  # pasajlar CASCADE ile gider
        c.execute("DELETE FROM books WHERE id=?", (bid,))
    for d in dosyalar:
        (VERI / "sayfa" / d).unlink(missing_ok=True)
    shutil.rmtree(VERI / "kitap" / str(bid), ignore_errors=True)
    return {"silindi": bid}


@app.get("/api/books/{bid}/thumb/{n}")
def kucuk_resim(bid: int, n: int):
    """Düşük çözünürlüklü küçük resim; ilk istekte üretilip diske önbelleklenir."""
    k = bul("books", bid)
    hedef = VERI / "kitap" / str(bid) / "kucuk" / f"{n:04d}.jpg"
    if not hedef.exists():
        import pymupdf

        satir = sor("SELECT dosya FROM pages WHERE book_id=? AND no=?", bid, n)
        if k["dosya"] and 1 <= n <= k["sayfa_sayisi"]:
            kaynak, sira = VERI / "kitap" / k["dosya"], n - 1
        elif satir:
            kaynak, sira = VERI / "sayfa" / satir[0]["dosya"], 0
        else:
            raise HTTPException(404, f"Kitapta {n}. sayfa yok")
        try:
            with pymupdf.open(kaynak) as belge:
                s = belge[sira]
                olcek = KUCUK_GENISLIK / s.rect.width
                jpg = s.get_pixmap(matrix=pymupdf.Matrix(olcek, olcek)).tobytes("jpeg", jpg_quality=70)
        except Exception as e:
            raise HTTPException(500, f"Küçük resim üretilemedi: {e}")
        hedef.parent.mkdir(parents=True, exist_ok=True)
        gecici = hedef.with_name(f"{hedef.name}.{threading.get_ident()}.tmp")  # eşzamanlı istekler yarım dosya görmesin
        gecici.write_bytes(jpg)
        gecici.replace(hedef)
    return FileResponse(hedef, media_type="image/jpeg")


class Secim(BaseModel):
    sayfalar: list[int]


def secim_dogrula(bid: int, secim: Secim) -> tuple[dict, list]:
    k = bul("books", bid)
    nolar = sorted(set(secim.sayfalar))
    if not nolar:
        raise HTTPException(422, "Sayfa seçilmedi")
    if len(nolar) > AZAMI_SECIM:
        raise HTTPException(422, f"Tek seferde en fazla {AZAMI_SECIM} sayfa seçilebilir ({len(nolar)} seçildi)")
    gecerli = (set(range(1, k["sayfa_sayisi"] + 1)) if k["dosya"]
               else {s["no"] for s in sor("SELECT no FROM pages WHERE book_id=?", bid)})
    disarida = [n for n in nolar if n not in gecerli]
    if disarida:
        raise HTTPException(422, f"Kitapta olmayan sayfa: {', '.join(map(str, disarida))}")
    return k, nolar


def tahmin_hesapla(bid: int, nolar: list) -> dict:
    """Seçimin tahmini maliyeti: defterdeki sayfa başı ortalama (OCR+çeviri) ya da varsayılan."""
    bitmis = {s["no"] for s in sor(SAYFA_OZETI + " WHERE p.book_id=?", bid) if s["blok"] and not s["cevrilmemis"]}
    islenecek = [n for n in nolar if n not in bitmis]
    ortalama = sor("""SELECT AVG(t) AS o FROM (SELECT SUM(maliyet) AS t FROM usage
                      WHERE page_id IS NOT NULL AND adim IN ('ocr','ceviri') GROUP BY page_id)""")[0]["o"]
    sayfa_basi = ortalama or VARSAYILAN_SAYFA_MALIYETI
    h = harcama()
    tahmin = len(islenecek) * sayfa_basi
    return {"secilen": len(nolar), "islenecek": len(islenecek), "sayfa_basi": sayfa_basi,
            "ortalama_defterden": bool(ortalama), "tahmin": tahmin, "bugun_kalan": max(0.0, GUNLUK_BUTCE - h["bugun"]),
            "kalan": h["kalan"], "yeter": tahmin <= h["kalan"]}


@app.post("/api/books/{bid}/estimate")
def tahmin(bid: int, secim: Secim):
    return tahmin_hesapla(bid, secim_dogrula(bid, secim)[1])


@app.post("/api/books/{bid}/prepare")
def hazirla(bid: int, secim: Secim):
    """Seçilen sayfalar için 200 dpi görüntü ve pages satırı oluşturur (LLM çağrısı yok)."""
    k, nolar = secim_dogrula(bid, secim)
    t = tahmin_hesapla(bid, nolar)
    if not t["yeter"]:
        raise HTTPException(429, f"{t['islenecek']} sayfa ≈ ${t['tahmin']:.2f}, kalan bütçe ${t['kalan']:.2f}; iş başlatılmadı.")
    var = {s["no"] for s in sor("SELECT no FROM pages WHERE book_id=?", bid)}
    eksik = [n for n in nolar if n not in var]
    if eksik:  # yalnızca PDF kitapta olur; görüntü kitabının sayfaları yüklenince oluşur
        import pymupdf

        with pymupdf.open(VERI / "kitap" / k["dosya"]) as belge:
            for n in eksik:
                dosya = f"{bid}-{n:04d}.jpg"
                (VERI / "sayfa" / dosya).write_bytes(belge[n - 1].get_pixmap(dpi=200).tobytes("jpeg"))
                yaz("INSERT OR IGNORE INTO pages(book_id, no, dosya) VALUES(?,?,?)", bid, n, dosya)
    return sor(f"SELECT id, no FROM pages WHERE book_id=? AND no IN ({','.join('?' * len(nolar))}) ORDER BY no",
               bid, *nolar)


@app.get("/api/books/{bid}/export.docx")
def docx_cikti(bid: int, sadece_onayli: bool = False):
    from docx import Document
    from docx.oxml import OxmlElement
    from docx.shared import Pt

    k = bul("books", bid)
    pasajlar = sor(f"""SELECT pg.no, p.* FROM passages p JOIN pages pg ON pg.id=p.page_id
                       WHERE pg.book_id=? AND p.tur!='diger' {"AND p.durum='onayli'" if sadece_onayli else ""}
                       ORDER BY pg.no, p.sira""", bid)
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
                    headers={"Content-Disposition": f"attachment; filename=\"kitap-{bid}.docx\"; "
                                                    f"filename*=UTF-8''{quote(k['ad'])}.docx"})


# ---------- sayfalar ----------
@app.get("/api/pages")
def sayfalar():
    return sor(SAYFA_OZETI + " ORDER BY p.book_id, p.no")


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
    k = bul("books", s["book_id"])
    with closing(db()) as c, c:
        c.execute("DELETE FROM pages WHERE id=?", (pid,))
        if not k["dosya"]:  # görüntü kitabında sayfanın tek kaynağı bu görüntüydü
            c.execute("UPDATE books SET sayfa_sayisi=sayfa_sayisi-1 WHERE id=?", (k["id"],))
    (VERI / "sayfa" / s["dosya"]).unlink(missing_ok=True)
    if not k["dosya"]:
        (VERI / "kitap" / str(k["id"]) / "kucuk" / f"{s['no']:04d}.jpg").unlink(missing_ok=True)
    return {"silindi": pid}


def ocr_yap(pid: int):
    s = bul("pages", pid)
    ham = ai("ocr", [llm_modul.resim(VERI / "sayfa" / s["dosya"]), OCR_PROMPT], pid,
             response_mime_type="application/json", response_schema=OCR_SCHEMA)
    try:
        bloklar = [b for b in json.loads(ham)["bloklar"] if b["metin"].strip()]
    except (ValueError, KeyError, TypeError) as e:
        raise HTTPException(502, f"OCR yanıtı çözümlenemedi: {e}")
    with closing(db()) as c, c:
        c.execute("DELETE FROM passages WHERE page_id=?", (pid,))
        c.executemany("INSERT INTO passages(page_id, sira, tur, ar) VALUES(?,?,?,?)",
                      [(pid, i, b["tur"], b["metin"].strip()) for i, b in enumerate(bloklar)])


@app.post("/api/pages/{pid}/ocr")
def ocr(pid: int, zorla: bool = False):
    bul("pages", pid)
    emek = sor("SELECT COUNT(*) AS n FROM passages WHERE page_id=? AND (tr!='' OR durum='onayli')", pid)[0]["n"]
    if emek and not zorla:
        raise HTTPException(409, f"Bu sayfada {emek} çevrilmiş/onaylı pasaj var; yeniden OCR bunları siler.")
    with tek_is():
        ocr_yap(pid)
    return sayfa(pid)


@app.post("/api/pages/{pid}/process")
def isle(pid: int):
    """Toplu işin bir sayfası: OCR'lanmamışsa OCR, sonra çevirisi boş şerh/hâşiye pasajlarının çevirisi.
    Harekeleme yapılmaz. İşlenmiş sayfada OCR tekrarlanmaz, çevirisi olan pasaj yeniden çevrilmez."""
    bul("pages", pid)
    with tek_is():
        if not sor("SELECT 1 FROM passages WHERE page_id=? LIMIT 1", pid):
            ocr_yap(pid)
        for p in sor("SELECT * FROM passages WHERE page_id=? AND tur!='diger' AND TRIM(tr)='' AND durum!='onayli' "
                     "ORDER BY sira", pid):
            ceviri_yap(p)
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


def ceviri_yap(p: dict):
    sozluk_ek = sozluk_metni(p["ar"])
    tr = ai_parcali("ceviri", lambda m: sozluk_ek + CEVIRI_PROMPT.format(metin=m), p["ar"], p["page_id"])
    yaz("UPDATE passages SET tr=? WHERE id=?", tr, p["id"])


@app.post("/api/passages/{kid}/translate")
def cevir(kid: int):
    p = bul("passages", kid)
    if p["durum"] == "onayli":
        raise HTTPException(409, "Onaylı pasaj yeniden çevrilmez; önce onayı kaldır")
    ceviri_yap(p)
    return zengin(bul("passages", kid))


@app.post("/api/passages/{kid}/vocalize")
def harekele(kid: int):
    p = bul("passages", kid)
    harekeli = ai_parcali("hareke", lambda m: HAREKE_PROMPT.format(metin=m), p["ar"], p["page_id"])
    yaz("UPDATE passages SET ar_vocalized=? WHERE id=?", harekeli, kid)
    return zengin(bul("passages", kid))


@app.post("/api/passages/{kid}/agent")
def agent(kid: int):
    p = bul("passages", kid)
    if not p["tr"].strip():
        raise HTTPException(422, "Önce çeviri gerekli")
    ham = ai("agent", AGENT_PROMPT.format(sozluk=sozluk_metni(p["ar"]), ar=p["ar"], tr=p["tr"]), p["page_id"],
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

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
import math
import os
import re
import shutil
import sqlite3
import threading
from contextlib import closing, contextmanager
from difflib import SequenceMatcher
from pathlib import Path
from typing import Literal, Optional
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field, StrictBool

import llm as llm_modul
from arapca_test import (CEVIRI_PROMPT, HAREKE, HAREKE_PROMPT, IMLA, OCR_PROMPT, OCR_SCHEMA, imla, parcali, rasm,
                         rasm_kontrol)

KOK = Path(__file__).parent
VERI = Path(os.environ.get("ARAPCA_VERI", KOK / "data"))
RESIM_UZANTI = {".jpg", ".jpeg", ".png", ".webp"}
AZAMI_DOSYA = 200 * 1024 * 1024
AZAMI_SECIM = 10  # tek toplu işte en fazla sayfa
KUCUK_GENISLIK = 240  # küçük resim genişliği (piksel)
GUNLUK_BUTCE = float(os.environ.get("GUNLUK_BUTCE_USD", "3"))
AYLIK_BUTCE = float(os.environ.get("AYLIK_BUTCE_USD", "30"))
VARSAYILAN_SAYFA_MALIYETI = 0.10  # USD; defterde geçmiş sayfa yoksa tahmin için
VARSAYILAN_OCR2_MALIYETI = 0.03  # USD; çift okumanın ikinci okuması için, defterde geçmiş yoksa
BAGLAM = 300  # komşu sayfadan çeviri isteğine eklenen bağlam (karakter)
AZAMI_LEMMA = 100  # talik lemması (قوله ... ")") en fazla bu kadar karakter
AZAMI_FARK = 4  # çift okumada bundan uzun ayrışma kelime farkı değil blok/katman kaymasıdır; sayılmaz
AYARLAR = {"talik_bol": False, "cift_okuma": False}  # kitap ayarları (books.ayar JSON) ve varsayılanları

SEMA = """
CREATE TABLE IF NOT EXISTS books(
    id INTEGER PRIMARY KEY, ad TEXT NOT NULL, dosya TEXT, sayfa_sayisi INTEGER NOT NULL,
    olusturma TEXT NOT NULL DEFAULT (datetime('now','localtime')), ayar TEXT NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS pages(
    id INTEGER PRIMARY KEY, no INTEGER NOT NULL, dosya TEXT NOT NULL, book_id INTEGER REFERENCES books(id));
CREATE TABLE IF NOT EXISTS passages(
    id INTEGER PRIMARY KEY, page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    sira INTEGER NOT NULL, tur TEXT NOT NULL, ar TEXT NOT NULL, ar_vocalized TEXT,
    tr TEXT NOT NULL DEFAULT '', durum TEXT NOT NULL DEFAULT 'taslak',
    kutu TEXT, lemma TEXT, bagli_id INTEGER REFERENCES passages(id) ON DELETE SET NULL, supheli TEXT, kapali TEXT);
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
# passages.kutu: OCR'ın verdiği konum, JSON [ymin, xmin, ymax, xmax] (0-1000). lemma: talikte "قوله"den sonraki
# şerh alıntısı; bagli_id: lemmanın bulunduğu şerh pasajı. supheli: çift okumada ayrışan kelimeler, JSON
# [{kelime, diger, i}] (i: kelimenin pasajdaki sırası). kapali: şüpheli kuyruğunda "baktım" denen maddelerin anahtarları.

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
def sutun_ekle(c: sqlite3.Connection, tablo: str, *tanimlar: str):
    var = {r["name"] for r in c.execute(f"PRAGMA table_info({tablo})")}
    for t in tanimlar:
        if t.split()[0] not in var:
            c.execute(f"ALTER TABLE {tablo} ADD COLUMN {t}")


def gec(c: sqlite3.Connection):
    """Eski şemadan göç: eksik sütunları ekler, sahipsiz sayfaları 'Eski sayfalar' kitabına bağlar."""
    sutun_ekle(c, "pages", "book_id INTEGER REFERENCES books(id)")
    sutun_ekle(c, "books", "ayar TEXT NOT NULL DEFAULT '{}'")
    sutun_ekle(c, "passages", "kutu TEXT", "lemma TEXT", "bagli_id INTEGER REFERENCES passages(id) ON DELETE SET NULL",
               "supheli TEXT", "kapali TEXT")
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


def json_oku(ham, bos):
    try:
        return json.loads(ham) if ham else bos
    except ValueError:
        return bos


def ayar_coz(ham) -> dict:
    kayitli = json_oku(ham, {})
    kayitli = kayitli if isinstance(kayitli, dict) else {}
    return {k: bool(kayitli.get(k, v)) for k, v in AYARLAR.items()}


def kitap_ayari(bid: int) -> dict:
    return ayar_coz(bul("books", bid)["ayar"])


def kutu_dogrula(k) -> Optional[list]:
    """Gemini kutusu [ymin, xmin, ymax, xmax], 0-1000 arası normalize; geçersizse None (pasaj yine kaydedilir)."""
    if not isinstance(k, list) or len(k) != 4:
        return None
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in k):
        return None
    k = [round(v) for v in k]
    if not all(0 <= v <= 1000 for v in k) or k[0] >= k[2] or k[1] >= k[3]:
        return None
    return k


def oz(metin: str) -> str:
    """Karşılaştırma için iskelet: harekesiz, imla farkı ve noktalama/boşluk gözetmeden."""
    return re.sub(r"\W", "", imla(rasm(metin)))


def kelime_araligi(metin: str, bas: int, son: int) -> tuple:
    """[bas, son) karakter aralığını kapsayan kelimelerin [başı, sonu)."""
    kel = [m.span() for m in re.finditer(r"\S+", metin)] or [(0, len(metin))]
    ilk = next((i for i, (_, b) in enumerate(kel) if b > bas), len(kel) - 1)
    son_k = max([i for i, (a, _) in enumerate(kel) if a < max(son, bas + 1)] + [ilk])
    return kel[ilk][0], kel[son_k][1]


# ---------- çift okuma ----------
def okuma_karsilastir(birincil: list, ikincil: list) -> dict:
    """Katman bazında kelime düzeyinde hizalama; iki modelin blok sınırları farklı olabileceği için katmanın bütün
    metni birleştirilir. {birincil blok sırası: [{"kelime", "diger", "i"}]}; diger "" ise ikinci okumada yok."""
    sonuc = {}
    for katman in ("serh", "hasiye"):
        a = [(bi, wi, k) for bi, b in enumerate(birincil) if b["tur"] == katman
             for wi, k in enumerate(b["metin"].split()) if oz(k)]
        b = [k for x in ikincil if x["tur"] == katman for k in x["metin"].split() if oz(k)]
        if not a or not b:
            continue
        sm = SequenceMatcher(None, [oz(x[2]) for x in a], [oz(k) for k in b], autojunk=False)
        for op, i1, i2, j1, j2 in sm.get_opcodes():
            if op == "equal" or max(i2 - i1, j2 - j1) > AZAMI_FARK:
                continue
            diger = " ".join(b[j1:j2])
            if op == "insert":  # ikinci okumada fazladan kelime: komşu kelimeye bağla
                bi, wi, k = a[i1 - 1] if i1 else a[0]
                sonuc.setdefault(bi, []).append({"kelime": k, "diger": f"{k} {diger}" if i1 else f"{diger} {k}", "i": wi})
                continue
            for bi, wi, k in a[i1:i2]:
                sonuc.setdefault(bi, []).append({"kelime": k, "diger": diger, "i": wi})
    return sonuc


def supheli_gecerli(p: dict) -> list:
    """Saklanan çift okuma farklarından metinde hâlâ duranlar; kelime yer değiştirdiyse en yakın geçişe taşınır."""
    kel = p["ar"].split()
    sonuc = []
    for m in json_oku(p.get("supheli"), []):
        yerler = [i for i, k in enumerate(kel) if k == m.get("kelime")]
        if yerler:
            sonuc.append({**m, "i": min(yerler, key=lambda i: abs(i - m.get("i", 0)))})
    return sonuc


# ---------- hâşiyeyi taliklere bölme (LLM yok) ----------
_H = "[\u064b-\u0652\u0670\u0640]*"
KAVL = re.compile(rf"(?<!\S)ق{_H}و{_H}ل{_H}ه{_H}(?!\S)")  # bağımsız kelime olarak "قوله" (بقوله/لقوله/وقوله değil)
KISALTMA = re.compile(r"(?<!\S)(?:الخ|[اإ]لى آخره)(?!\S)")


def talik_parcala(metin: str) -> list:
    """Hâşiye bloğunu taliklere ayırır: [(baş, son, lemma|None)]. Talik "قوله <alıntı> )" ile başlar; alıntı kısa,
    parantezsiz ve içinde başka "قوله" yoksa bölünür, emin olunamayan yerde bölünmez. Baştaki "قوله"siz parça
    (önceki sayfadan devam) lemmasız ayrı parça olur. Bölünecek yer yoksa boş liste."""
    kesim = []
    for m in KAVL.finditer(metin):
        kapanis = metin.find(")", m.end())
        lemma = metin[m.end():kapanis].strip().lstrip("(").strip() if kapanis > 0 else ""
        if lemma and len(lemma) <= AZAMI_LEMMA and "(" not in lemma and not KAVL.search(lemma):
            kesim.append((m.start(), lemma))
    if not kesim:
        return []
    parcalar = [(0, kesim[0][0], None)] if metin[:kesim[0][0]].strip() else []
    sinirlar = [b for b, _ in kesim] + [len(metin)]
    return parcalar + [(b, sinirlar[i + 1], lemma) for i, (b, lemma) in enumerate(kesim)]


def lemma_bul(lemma: str, gruplar: list) -> Optional[int]:
    """Lemmayı ("الخ" öncesi) şerh pasajlarında harekesiz/imla farkı gözetmeden arar; gruplar öncelik sırasıyla
    (aynı sayfa, önceki sayfa). Tamamı bulunamazsa sondan kısaltarak (en az iki kelime) dener."""
    kelimeler = KISALTMA.split(lemma)[0].split()
    for n in range(len(kelimeler), min(2, len(kelimeler)) - 1, -1):
        hedef = oz(" ".join(kelimeler[:n]))
        for grup in gruplar:
            for p in grup:
                if hedef and hedef in oz(p["ar"]):
                    return p["id"]
    return None


def talik_bol(pid: int) -> dict:
    """Sayfanın hâşiye pasajlarını taliklere böler ve lemmaları şerhe bağlar. Çevirisi, harekelemesi olan ya da
    onaylı pasaj bölünmez (emek kaybolmasın); yalnızca tek talikse lemması işaretlenir."""
    s = bul("pages", pid)
    pasajlar = sor("SELECT * FROM passages WHERE page_id=? ORDER BY sira", pid)
    sira, atlanan, bolunen = [], [], 0
    with closing(db()) as c, c:
        for p in pasajlar:
            parcalar = talik_parcala(p["ar"]) if p["tur"] == "hasiye" else []
            if len(parcalar) > 1 and (p["tr"].strip() or p["durum"] == "onayli" or p["ar_vocalized"]):
                neden = "onaylı" if p["durum"] == "onayli" else "çevirisi var" if p["tr"].strip() else "harekelenmiş"
                atlanan.append({"sira": p["sira"] + 1, "neden": neden})
                parcalar = []
            if len(parcalar) == 1:
                c.execute("UPDATE passages SET lemma=? WHERE id=?", (parcalar[0][2], p["id"]))
            if len(parcalar) <= 1:
                sira.append(p["id"])
                continue
            bolunen += 1
            supheli = json_oku(p["supheli"], [])
            for n, (bas, son, lemma) in enumerate(parcalar):
                kayma = len(p["ar"][:bas].split())  # bölme kelime başında olur; kelime sırası kayar
                adet = len(p["ar"][bas:son].split())
                ps = [{**m, "i": m["i"] - kayma} for m in supheli if kayma <= m.get("i", -1) < kayma + adet]
                alan = (p["ar"][bas:son].strip(), lemma, json.dumps(ps, ensure_ascii=False) if ps else None)
                if n == 0:  # ilk parça pasajın kimliğini korur
                    c.execute("UPDATE passages SET ar=?, lemma=?, supheli=? WHERE id=?", (*alan, p["id"]))
                    sira.append(p["id"])
                else:
                    sira.append(c.execute("INSERT INTO passages(page_id, sira, tur, ar, lemma, supheli, kutu, kapali) "
                                          "VALUES(?,?,?,?,?,?,?,?)", (pid, -1, "hasiye", *alan, p["kutu"],
                                                                     p["kapali"])).lastrowid)
        c.executemany("UPDATE passages SET sira=? WHERE id=?", [(i, k) for i, k in enumerate(sira)])
        serh = lambda sid: [dict(r) for r in c.execute("SELECT id, ar FROM passages WHERE page_id=? AND tur='serh' "
                                                       "ORDER BY sira", (sid,))]
        onceki = c.execute("SELECT id FROM pages WHERE book_id=? AND no=?", (s["book_id"], s["no"] - 1)).fetchone()
        gruplar = [serh(pid), serh(onceki["id"]) if onceki else []]
        talikler = c.execute("SELECT id, lemma FROM passages WHERE page_id=? AND tur='hasiye' AND lemma IS NOT NULL",
                             (pid,)).fetchall()
        baglar = [(lemma_bul(t["lemma"], gruplar), t["id"]) for t in talikler]
        c.executemany("UPDATE passages SET bagli_id=? WHERE id=?", baglar)
    return {"talik": len(talikler), "bolunen": bolunen, "bagli": sum(1 for b, _ in baglar if b),
            "atlanan": atlanan}


# ---------- şüpheli kelime kuyruğu ----------
def iskelet_harita(metin: str) -> tuple:
    """imla(rasm(metin)) ve her harfinin metindeki konumu (rasm_kontrol'ün karşılaştırdığı dizi)."""
    konum = [i for i, h in enumerate(metin) if not HAREKE.match(h) and not h.isspace()]
    return "".join(metin[i] for i in konum).translate(IMLA), konum


def harf_farklari(kaynak: str, harekeli: str) -> list:
    """Harekelemenin yaptığı gerçek harf değişimleri (imla farkları değil): [(baş, son, harekelideki kelime)]."""
    x, kx = iskelet_harita(kaynak)
    y, ky = iskelet_harita(harekeli)
    sonuc = []
    for op, i1, i2, j1, j2 in SequenceMatcher(None, x, y, autojunk=False).get_opcodes():
        if op == "equal" or not kx:
            continue
        bas = kx[min(i1, len(kx) - 1)] if i2 > i1 else kx[max(i1 - 1, 0)]
        son = kx[i2 - 1] + 1 if i2 > i1 else bas + 1
        diger = harekeli[slice(*kelime_araligi(harekeli, ky[j1], ky[j2 - 1] + 1))] if j2 > j1 else ""
        sonuc.append((bas, son, diger))
    return sonuc


def kuyruk_maddeleri(p: dict) -> list:
    """Pasajın açık şüpheli maddeleri: okunamayan "[?]", harekelemedeki harf değişimi, çift okuma farkı."""
    ar, kapali = p["ar"], set(json_oku(p.get("kapali"), []))
    kel = [m.span() for m in re.finditer(r"\S+", ar)]
    adaylar = [("okunamadi", m.start(), m.end(), "") for m in re.finditer(r"\[\?\]", ar)]
    if p["ar_vocalized"] and not rasm_kontrol(ar, p["ar_vocalized"])["imla"]:
        adaylar += [("hareke", *f) for f in harf_farklari(ar, p["ar_vocalized"])]
    adaylar += [("cift", *kel[m["i"]], m["diger"]) for m in supheli_gecerli(p)]
    maddeler, gorulen = [], set()
    for tur, bas, son, diger in adaylar:
        bas, son = kelime_araligi(ar, bas, son)
        i = next(n for n, (a, b) in enumerate(kel) if b > bas)
        j = max(n for n, (a, b) in enumerate(kel) if a < son)
        once = ar[kel[max(i - 3, 0)][0]:bas].strip() if i else ""
        sonra = ar[son:kel[min(j + 3, len(kel) - 1)][1]].strip()
        anahtar = "|".join([tur, once, ar[bas:son], sonra, diger])
        if anahtar in kapali or anahtar in gorulen:
            continue
        gorulen.add(anahtar)
        maddeler.append({"tur": tur, "kelime": ar[bas:son], "once": once, "sonra": sonra, "diger": diger,
                         "bas": bas, "son": son, "anahtar": anahtar})
    return maddeler


def kuyruk(bid: int) -> list:
    pasajlar = sor("""SELECT pg.no, p.* FROM passages p JOIN pages pg ON pg.id=p.page_id
                      WHERE pg.book_id=? AND p.tur!='diger'
                        AND (p.ar LIKE '%[?]%' OR p.ar_vocalized IS NOT NULL OR p.supheli IS NOT NULL)
                      ORDER BY pg.no, p.sira""", bid)
    return [{"no": p["no"], "page_id": p["page_id"], "passage_id": p["id"], "katman": p["tur"], **m}
            for p in pasajlar for m in kuyruk_maddeleri(p)]


# ---------- sayfalar arası devam ----------
BAGLAM_PROMPT = """Komşu sayfa bağlamı — YALNIZCA BAĞLAM, ÇEVİRME ve çıktına koyma. Çevrilecek metin önceki sayfanın
sonundan devam ediyor ya da sonraki sayfada sürüyor olabilir; sayfa sınırında yarım kalan cümleyi bu bağlama göre
tutarlı çevir, ama yalnızca aşağıdaki asıl metni çevir.
{bolumler}--- bağlam sonu ---

"""


def komsu_baglam(p: dict) -> str:
    """Pasaj sayfadaki katmanının ilk/son pasajıysa komşu sayfanın aynı katmandaki son/ilk pasajından ~300 karakter."""
    if p["tur"] not in ("serh", "hasiye"):
        return ""
    s = bul("pages", p["page_id"])
    ayni = [x["id"] for x in sor("SELECT id FROM passages WHERE page_id=? AND tur=? ORDER BY sira", s["id"], p["tur"])]

    def komsu(no: int, sondan: bool) -> str:
        r = sor(f"""SELECT p.ar FROM passages p JOIN pages pg ON pg.id=p.page_id WHERE pg.book_id=? AND pg.no=?
                    AND p.tur=? ORDER BY p.sira {'DESC' if sondan else ''} LIMIT 1""", s["book_id"], no, p["tur"])
        return r[0]["ar"] if r else ""

    once = komsu(s["no"] - 1, True) if ayni and ayni[0] == p["id"] else ""
    sonra = komsu(s["no"] + 1, False) if ayni and ayni[-1] == p["id"] else ""
    if len(once) > BAGLAM:
        once = once[-BAGLAM:].split(" ", 1)[-1]
    if len(sonra) > BAGLAM:
        sonra = sonra[:BAGLAM].rsplit(" ", 1)[0]
    bolumler = (f"[Önceki sayfanın sonu]\n{once}\n" if once else "") + (f"[Sonraki sayfanın başı]\n{sonra}\n" if sonra else "")
    return BAGLAM_PROMPT.format(bolumler=bolumler) if bolumler else ""


def zengin(p: dict) -> dict:
    """Pasaja hesaplanan alanları ekler: rasm kontrolü, sözlük sapmaları, kutu ve geçerli çift okuma farkları."""
    p["rasm"] = rasm_kontrol(p["ar"], p["ar_vocalized"]) if p["ar_vocalized"] else None
    p["sapma"] = ([t for t in sozluk_eslesen(p["ar"]) if tr_kucuk(t["tr"]) not in tr_kucuk(p["tr"])]
                  if p["tr"].strip() else [])
    p["kutu"] = json_oku(p["kutu"], None)
    p["supheli"] = supheli_gecerli(p)
    p["kapali"] = json_oku(p["kapali"], [])
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
    return [{**b, "ayar": ayar_coz(b["ayar"])} for b in sor("""SELECT b.*,
        (SELECT COUNT(*) FROM pages pg WHERE pg.book_id=b.id
            AND EXISTS(SELECT 1 FROM passages WHERE page_id=pg.id)) AS islenen,
        (SELECT COUNT(*) FROM passages p JOIN pages pg ON pg.id=p.page_id WHERE pg.book_id=b.id AND p.tur!='diger') AS pasaj,
        (SELECT COUNT(*) FROM passages p JOIN pages pg ON pg.id=p.page_id
            WHERE pg.book_id=b.id AND p.tur!='diger' AND p.durum='onayli') AS onayli,
        (SELECT COALESCE(SUM(maliyet), 0) FROM usage WHERE book_id=b.id) AS maliyet
        FROM books b ORDER BY b.id DESC""")]


@app.get("/api/books/{bid}")
def kitap(bid: int):
    k = bul("books", bid)
    satirlar = {s["no"]: s for s in sor(SAYFA_OZETI + " WHERE p.book_id=?", bid)}
    nolar = range(1, k["sayfa_sayisi"] + 1) if k["dosya"] else sorted(satirlar)
    k["sayfalar"] = [satirlar.get(n) or {"id": None, "no": n, "blok": 0, "pasaj": 0, "onayli": 0, "cevrilmemis": 0}
                     for n in nolar]
    k["ayar"] = ayar_coz(k["ayar"])
    k["kuyruk"] = len(kuyruk(bid))
    return k


class KitapGuncelle(BaseModel):
    ad: Optional[str] = Field(None, min_length=1, max_length=200)
    ayar: Optional[dict[str, StrictBool]] = None  # yalnızca verilen ayarlar değişir


@app.patch("/api/books/{bid}")
def kitap_guncelle(bid: int, g: KitapGuncelle):
    k = bul("books", bid)
    if g.ad is not None:
        if not g.ad.strip():
            raise HTTPException(422, "Kitap adı boş olamaz")
        yaz("UPDATE books SET ad=? WHERE id=?", g.ad.strip(), bid)
    if g.ayar is not None:
        bilinmeyen = set(g.ayar) - set(AYARLAR)
        if bilinmeyen:
            raise HTTPException(422, f"Bilinmeyen ayar: {', '.join(sorted(bilinmeyen))}")
        yaz("UPDATE books SET ayar=? WHERE id=?", json.dumps({**ayar_coz(k["ayar"]), **g.ayar}), bid)
    k = bul("books", bid)
    return {**k, "ayar": ayar_coz(k["ayar"])}


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
    """Seçimin tahmini maliyeti: defterdeki sayfa başı ortalama (OCR+çeviri) ya da varsayılan; çift okuma açıksa
    OCR'lanacak her sayfaya ikinci okumanın ortalaması eklenir."""
    ozet = sor(SAYFA_OZETI + " WHERE p.book_id=?", bid)
    bitmis = {s["no"] for s in ozet if s["blok"] and not s["cevrilmemis"]}
    okunmus = {s["no"] for s in ozet if s["blok"]}
    islenecek = [n for n in nolar if n not in bitmis]
    ortalama_sql = """SELECT AVG(t) AS o FROM (SELECT SUM(maliyet) AS t FROM usage
                      WHERE page_id IS NOT NULL AND adim IN ({}) GROUP BY page_id)"""
    ortalama = sor(ortalama_sql.format("'ocr','ceviri'"))[0]["o"]
    sayfa_basi = ortalama or VARSAYILAN_SAYFA_MALIYETI
    cift = kitap_ayari(bid)["cift_okuma"]
    ocr2_ek = (len([n for n in islenecek if n not in okunmus])
               * (sor(ortalama_sql.format("'ocr2'"))[0]["o"] or VARSAYILAN_OCR2_MALIYETI)) if cift else 0.0
    h = harcama()
    tahmin = len(islenecek) * sayfa_basi + ocr2_ek
    return {"secilen": len(nolar), "islenecek": len(islenecek), "sayfa_basi": sayfa_basi,
            "ortalama_defterden": bool(ortalama), "cift_okuma": cift, "ocr2_ek": ocr2_ek, "tahmin": tahmin,
            "bugun_kalan": max(0.0, GUNLUK_BUTCE - h["bugun"]), "kalan": h["kalan"], "yeter": tahmin <= h["kalan"]}


@app.get("/api/books/{bid}/queue")
def kuyruk_listesi(bid: int):
    """Şüpheli kelime kuyruğu: okunamayan [?], harekelemede harf değişimi, çift okuma farkı."""
    bul("books", bid)
    return kuyruk(bid)


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
    s["pasajlar"] = [zengin(p) for p in sor("""SELECT p.*, b.page_id AS bagli_sayfa FROM passages p
        LEFT JOIN passages b ON b.id=p.bagli_id WHERE p.page_id=? ORDER BY p.sira""", pid)]
    talikler = {}  # şerh pasajına bağlı talikler (sonraki sayfadakiler dahil)
    for t in sor("""SELECT t.id, t.page_id, t.lemma, t.bagli_id FROM passages t JOIN pages pg ON pg.id=t.page_id
                    WHERE t.bagli_id IN (SELECT id FROM passages WHERE page_id=?) ORDER BY pg.no, t.sira""", pid):
        talikler.setdefault(t.pop("bagli_id"), []).append(t)
    for p in s["pasajlar"]:
        p["talikler"] = talikler.get(p["id"], [])
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


def ocr_oku(adim: str, s: dict) -> list:
    ham = ai(adim, [llm_modul.resim(VERI / "sayfa" / s["dosya"]), OCR_PROMPT], s["id"],
             response_mime_type="application/json", response_schema=OCR_SCHEMA)
    try:
        return [{"tur": b["tur"], "metin": b["metin"].strip(), "kutu": kutu_dogrula(b.get("kutu"))}
                for b in json.loads(ham)["bloklar"] if b["metin"].strip()]
    except (ValueError, KeyError, TypeError, AttributeError) as e:
        raise HTTPException(502, f"{adim} yanıtı çözümlenemedi: {e}")


def ocr_yap(pid: int) -> list:
    """Sayfayı okur; kitap ayarına göre ikinci modelle de okuyup farkları işaretler ve hâşiyeyi taliklere böler.
    İkinci okuma yalnızca karşılaştırma içindir; hata verirse birincil sonuç kaydedilir. Uyarıları döndürür."""
    s = bul("pages", pid)
    ayar = kitap_ayari(s["book_id"])
    bloklar = ocr_oku("ocr", s)
    uyarilar, supheli = [], {}
    if ayar["cift_okuma"]:
        try:
            supheli = okuma_karsilastir(bloklar, ocr_oku("ocr2", s))
        except HTTPException as e:
            uyarilar.append(f"s. {s['no']}: ikinci okuma yapılamadı, birincil okuma kaydedildi ({e.detail})")
    with closing(db()) as c, c:
        c.execute("DELETE FROM passages WHERE page_id=?", (pid,))
        c.executemany("INSERT INTO passages(page_id, sira, tur, ar, kutu, supheli) VALUES(?,?,?,?,?,?)",
                      [(pid, i, b["tur"], b["metin"], json.dumps(b["kutu"]) if b["kutu"] else None,
                        json.dumps(supheli[i], ensure_ascii=False) if supheli.get(i) else None)
                       for i, b in enumerate(bloklar)])
    if ayar["talik_bol"]:
        talik_bol(pid)
    return uyarilar


@app.post("/api/pages/{pid}/ocr")
def ocr(pid: int, zorla: bool = False):
    bul("pages", pid)
    emek = sor("SELECT COUNT(*) AS n FROM passages WHERE page_id=? AND (tr!='' OR durum='onayli')", pid)[0]["n"]
    if emek and not zorla:
        raise HTTPException(409, f"Bu sayfada {emek} çevrilmiş/onaylı pasaj var; yeniden OCR bunları siler.")
    with tek_is():
        uyarilar = ocr_yap(pid)
    return {**sayfa(pid), "uyarilar": uyarilar}


@app.post("/api/pages/{pid}/process")
def isle(pid: int, asama: Literal["hepsi", "ocr", "ceviri"] = "hepsi"):
    """Toplu işin bir sayfası: OCR'lanmamışsa OCR, sonra çevirisi boş şerh/hâşiye pasajlarının çevirisi.
    Harekeleme yapılmaz. İşlenmiş sayfada OCR tekrarlanmaz, çevirisi olan pasaj yeniden çevrilmez.
    Toplu iş önce bütün sayfalar için asama=ocr, sonra asama=ceviri çağırır; böylece çeviride komşu sayfa hazırdır."""
    bul("pages", pid)
    uyarilar = []
    with tek_is():
        if asama != "ceviri" and not sor("SELECT 1 FROM passages WHERE page_id=? LIMIT 1", pid):
            uyarilar = ocr_yap(pid)
        if asama != "ocr":
            for p in sor("SELECT * FROM passages WHERE page_id=? AND tur!='diger' AND TRIM(tr)='' "
                         "AND durum!='onayli' ORDER BY sira", pid):
                ceviri_yap(p)
    return {**sayfa(pid), "uyarilar": uyarilar}


@app.post("/api/pages/{pid}/split")
def taliklere_bol(pid: int):
    """Hâşiyeyi "قوله" taliklerine böler ve lemmaları şerhe bağlar; LLM çağrısı yok."""
    bul("pages", pid)
    rapor = talik_bol(pid)
    return {**sayfa(pid), "rapor": rapor}


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
        supheli = supheli_gecerli({**p, "ar": alan["ar"]})  # düzeltilen kelimenin çift okuma maddesi düşer
        alan["supheli"] = json.dumps(supheli, ensure_ascii=False) if supheli else None
    if alan:
        yaz(f"UPDATE passages SET {', '.join(k + '=?' for k in alan)} WHERE id=?", *alan.values(), kid)
    return zengin(bul("passages", kid))


def ceviri_yap(p: dict):
    ek = sozluk_metni(p["ar"]) + komsu_baglam(p)
    tr = ai_parcali("ceviri", lambda m: ek + CEVIRI_PROMPT.format(metin=m), p["ar"], p["page_id"])
    yaz("UPDATE passages SET tr=? WHERE id=?", tr, p["id"])


@app.post("/api/passages/{kid}/translate")
def cevir(kid: int):
    p = bul("passages", kid)
    if p["durum"] == "onayli":
        raise HTTPException(409, "Onaylı pasaj yeniden çevrilmez; önce onayı kaldır")
    ceviri_yap(p)
    return zengin(bul("passages", kid))


class Kapat(BaseModel):
    anahtar: str = Field(min_length=1)


@app.post("/api/passages/{kid}/dismiss")
def madde_kapat(kid: int, k: Kapat):
    """Şüpheli kuyruğundaki bir maddeyi "baktım" diye kalıcı olarak kapatır."""
    p = bul("passages", kid)
    if k.anahtar not in {m["anahtar"] for m in kuyruk_maddeleri(p)}:
        raise HTTPException(404, "Bu madde kuyrukta yok (metin değişmiş ya da zaten kapatılmış olabilir)")
    kapali = json_oku(p["kapali"], [])
    yaz("UPDATE passages SET kapali=? WHERE id=?", json.dumps(kapali + [k.anahtar], ensure_ascii=False), kid)
    return {"kalan": len(kuyruk(bul("pages", p["page_id"])["book_id"]))}


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

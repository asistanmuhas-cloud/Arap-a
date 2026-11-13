"""Uçtan uca API testi; LLM sahte, ağ gerekmez. Çalıştır: python test_app.py"""
import io
import json
import os
import shutil
import sqlite3
import tempfile
import threading
from pathlib import Path
from types import SimpleNamespace

os.environ["ARAPCA_VERI"] = tempfile.mkdtemp()
import pymupdf  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app as uyg  # noqa: E402
import llm  # noqa: E402

AR = "(وفرض الوضوء) اي ركنه"
cagrilar = []  # sahte LLM'e gelen adımlar


def sahte(adim, contents, kayit=None, **config):
    cagrilar.append(adim)
    if kayit:
        kayit({"model": "sahte", "girdi": 1000, "cikti": 100, "maliyet": 0.01})
    if adim == "ocr":
        return json.dumps({"bloklar": [{"tur": "diger", "metin": "٦"}, {"tur": "serh", "metin": AR},
                                       {"tur": "hasiye", "metin": "قوله فرض"}]})
    if adim == "hareke":
        return "(وَفَرْضُ الْوُضُوءِ) أَيْ رُكْنُهُ"  # hemze ekledi: yalnız imla farkı
    if adim == "ceviri":
        assert "فرض = farz" in contents, "sözlük çeviri isteğine eklenmeli"
        return "**Abdestin şartı** yani rüknü"  # sözlükten bilerek sapıyor
    if adim == "agent":
        return json.dumps({"oneriler": [{"eski": "şartı", "yeni": "farzı", "gerekce": "terim"},
                                        {"eski": "yok böyle", "yeni": "x", "gerekce": "uygulanamaz"}]})
    raise AssertionError(f"beklenmeyen adım: {adim}")


# ---- llm.llm'in kendisi: fiyat, çıktı tavanı, kullanım kaydı (sahte istemciyle) ----
class SahteIstemci:
    def __init__(self):
        self.models, self.yanitlar, self.configler = self, [], []

    def generate_content(self, model, contents, config):
        self.configler.append((model, config))
        metin, neden = self.yanitlar.pop(0)
        return SimpleNamespace(text=metin, candidates=[SimpleNamespace(finish_reason=SimpleNamespace(name=neden))],
                               usage_metadata=SimpleNamespace(prompt_token_count=1000, candidates_token_count=200,
                                                              thoughts_token_count=300))


istemci, defter = SahteIstemci(), []
llm._client = istemci
istemci.yanitlar = [("{}", "STOP"), ("çeviri", "STOP"), ("", "RECITATION"), ("kesik", "MAX_TOKENS"), ("x", "STOP")]
assert llm.llm("ocr", "x", kayit=defter.append) == "{}"
assert istemci.configler[-1] == ("gemini-3.1-pro-preview", {"max_output_tokens": 16000})
assert defter[-1] == {"model": "gemini-3.1-pro-preview", "girdi": 1000, "cikti": 500, "maliyet": (1000 * 2 + 500 * 12) / 1e6}
llm.llm("ceviri", "x", kayit=defter.append)
assert istemci.configler[-1][1] == {"thinking_config": {"thinking_level": "low"}, "max_output_tokens": 16000}
for beklenen in ("RECITATION", "çıktı tavanı"):  # boş/kesik yanıt hata, ama faturalandığı için deftere girer
    try:
        llm.llm("hareke", "x", kayit=defter.append)
        raise AssertionError("hata bekleniyordu")
    except RuntimeError as e:
        assert beklenen in str(e), e
assert len(defter) == 4 and istemci.configler[-1][1]["max_output_tokens"] == 24000
os.environ["MODEL_AGENT"] = "bilinmeyen-model"  # tabloda yok: en pahalı fiyat
llm.llm("agent", "x", kayit=defter.append)
del os.environ["MODEL_AGENT"]
assert defter[-1]["maliyet"] == (1000 * 2.00 + 500 * 12.00) / 1e6 and istemci.configler[-1][1]["max_output_tokens"] == 4000
assert "ask" not in llm.MODELLER

llm.llm = sahte
llm.resim = lambda yol: "resim"
c = TestClient(uyg.app)
VERI = Path(os.environ["ARAPCA_VERI"])


def jpg(genislik=60, yukseklik=90):
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, genislik, yukseklik), False)
    pix.clear_with(220)
    return pix.tobytes("jpeg")


# ---- yükleme: PDF -> kitap (sayfalar henüz görüntüye çevrilmez); görüntüler -> tek kitap ----
assert c.post("/api/upload", files=[("dosyalar", ("a.txt", b"x"))]).status_code == 400
assert c.post("/api/upload", files=[("dosyalar", ("a.jpg", b"\xff\xd8x"))]).status_code == 400  # bozuk görüntü
assert c.post("/api/upload", files=[("dosyalar", ("k.pdf", b"%PDF-bozuk"))]).status_code == 400
assert c.get("/api/books").json() == []  # reddedilen yükleme yarım kitap bırakmadı

pdf = pymupdf.open()
for i in range(12):
    pdf.new_page().insert_text((72, 72), f"sayfa {i + 1}")
k = c.post("/api/upload", files=[("dosyalar", ("Fethu'l-Kadir.pdf", pdf.tobytes()))]).json()["kitaplar"]
assert k == [{"id": 1, "ad": "Fethu'l-Kadir", "sayfa_sayisi": 12}], k
assert c.get("/api/pages").json() == []  # PDF yüklenince sayfa satırı oluşmaz
kitap = c.get("/api/books/1").json()
assert kitap["sayfa_sayisi"] == 12 and len(kitap["sayfalar"]) == 12 and all(s["id"] is None for s in kitap["sayfalar"])
assert (VERI / "kitap" / "1" / "kaynak.pdf").exists()

y = c.get("/api/books/1/thumb/3")
assert y.status_code == 200 and y.content[:2] == b"\xff\xd8"
assert pymupdf.Pixmap(y.content).width == uyg.KUCUK_GENISLIK
assert (VERI / "kitap" / "1" / "kucuk" / "0003.jpg").exists()  # önbelleklendi
assert c.get("/api/books/1/thumb/3").content == y.content
assert c.get("/api/books/1/thumb/13").status_code == 404 and c.get("/api/books/9/thumb/1").status_code == 404

g = c.post("/api/upload", files=[("dosyalar", ("b.png", jpg())), ("dosyalar", ("a.jpg", jpg()))]).json()["kitaplar"]
assert g == [{"id": 2, "ad": "a (+1 görüntü)", "sayfa_sayisi": 2}], g
assert [s["no"] for s in c.get("/api/books/2").json()["sayfalar"] if s["id"]] == [1, 2]  # görüntü sayfaları hazır
assert c.get("/api/books/2/thumb/2").status_code == 200

# ---- seçim doğrulama: en fazla 10 sayfa ----
assert c.post("/api/books/1/estimate", json={"sayfalar": list(range(1, 12))}).status_code == 422
assert c.post("/api/books/1/prepare", json={"sayfalar": list(range(1, 12))}).status_code == 422
assert c.post("/api/books/1/prepare", json={"sayfalar": []}).status_code == 422
assert c.post("/api/books/1/prepare", json={"sayfalar": [13]}).status_code == 422
assert not [s for s in c.get("/api/pages").json() if s["book_id"] == 1]  # reddedilen seçim sayfa oluşturmadı
t = c.post("/api/books/1/estimate", json={"sayfalar": [2, 3, 3]}).json()
assert t["islenecek"] == 2 and t["sayfa_basi"] == uyg.VARSAYILAN_SAYFA_MALIYETI and t["yeter"]
assert abs(t["tahmin"] - 0.2) < 1e-9 and t["kalan"] == 3

# ---- toplu iş: hazırla (200 dpi görüntü + satır) ve sayfa başına işle ----
assert c.post("/api/glossary", json={"ar": "فَرْض", "tr": "farz"}).json()[0]["ar"] == "فرض"
assert c.post("/api/glossary", json={"ar": "", "tr": "x"}).status_code == 422
hazir = c.post("/api/books/1/prepare", json={"sayfalar": [3, 2]}).json()
assert [s["no"] for s in hazir] == [2, 3] and cagrilar == []  # hazırlık LLM çağırmaz
assert c.get(f"/api/pages/{hazir[0]['id']}/image").content[:2] == b"\xff\xd8"
s = c.post(f"/api/pages/{hazir[0]['id']}/process").json()
assert [p["tur"] for p in s["pasajlar"]] == ["diger", "serh", "hasiye"]
assert [p["tr"] != "" for p in s["pasajlar"]] == [False, True, True]  # 'diger' çevrilmez
assert cagrilar == ["ocr", "ceviri", "ceviri"]  # harekeleme toplu işte yok
pid = hazir[0]["id"]
kid = s["pasajlar"][1]["id"]

# defter: her çağrı kitap/sayfa ile yazıldı
satirlar = uyg.sor("SELECT adim, model, maliyet, book_id, page_id FROM usage ORDER BY id")
assert [r["adim"] for r in satirlar] == ["ocr", "ceviri", "ceviri"]
assert all(r["book_id"] == 1 and r["page_id"] == pid and r["maliyet"] == 0.01 for r in satirlar)
assert abs(c.get("/api/usage").json()["bugun"] - 0.03) < 1e-9
t = c.post("/api/books/1/estimate", json={"sayfalar": [2, 3]}).json()
assert t["islenecek"] == 1 and abs(t["sayfa_basi"] - 0.03) < 1e-9 and t["ortalama_defterden"]  # 2. sayfa bitmiş

# işlenmiş sayfa yeniden işlenince OCR ve çeviri tekrarlanmaz
cagrilar.clear()
c.post(f"/api/pages/{pid}/process")
assert cagrilar == []
# yalnız çevirisi boş pasaj çevrilir
c.patch(f"/api/passages/{s['pasajlar'][2]['id']}", json={"tr": ""})
c.post(f"/api/pages/{pid}/process")
assert cagrilar == ["ceviri"]

# ---- pasaj düzenleme akışı (eskisi gibi) ----
assert c.post(f"/api/pages/{pid}/ocr").status_code == 409  # emek varken OCR üzerine yazmaz
c.patch(f"/api/passages/{kid}", json={"tr": ""})
assert c.patch(f"/api/passages/{kid}", json={"durum": "onayli"}).status_code == 422  # boş çeviri onaylanmaz
assert c.post(f"/api/passages/{kid}/agent").status_code == 422
p = c.post(f"/api/passages/{kid}/translate").json()
assert [t["tr"] for t in p["sapma"]] == ["farz"]  # sözlük sapması işaretlendi
p = c.post(f"/api/passages/{kid}/vocalize").json()
assert p["ar"] == AR and p["rasm"]["imla"] and not p["rasm"]["ayni"]  # asıl metin ezilmedi
assert uyg.sor("SELECT book_id, page_id FROM usage WHERE adim='hareke'") == [{"book_id": 1, "page_id": pid}]
oneri = c.post(f"/api/passages/{kid}/agent").json()
assert [o["yeni"] for o in oneri] == ["farzı"]  # uygulanamayan öneri elendi
p = c.patch(f"/api/passages/{kid}", json={"tr": "**Abdestin farzı** yani rüknü", "durum": "onayli"}).json()
assert p["sapma"] == [] and p["durum"] == "onayli"
assert c.post(f"/api/passages/{kid}/translate").status_code == 409  # onaylı pasaj ezilmez
p = c.patch(f"/api/passages/{kid}", json={"ar": AR + " ."}).json()
assert p["ar_vocalized"] is None  # asıl değişince harekeleme düşer

# ---- arşiv ----
arsiv = {b["id"]: b for b in c.get("/api/books").json()}
assert list(arsiv) == [2, 1]
b = arsiv[1]
assert (b["sayfa_sayisi"], b["islenen"], b["onayli"], b["pasaj"]) == (12, 1, 1, 2) and b["olusturma"]
assert abs(b["maliyet"] - 0.01 * len(uyg.sor("SELECT id FROM usage WHERE book_id=1"))) < 1e-9 and arsiv[2]["maliyet"] == 0
ozet = {s["no"]: s for s in c.get("/api/books/1").json()["sayfalar"]}
assert ozet[2]["blok"] == 3 and ozet[2]["onayli"] == 1 and ozet[3]["id"] and ozet[3]["blok"] == 0
assert c.patch("/api/books/1", json={"ad": "  Fethu'l-Kadîr  "}).json()["ad"] == "Fethu'l-Kadîr"
assert c.patch("/api/books/1", json={"ad": "   "}).status_code == 422

# ---- DOCX kitap bazında ----
from docx import Document  # noqa: E402

y = c.get("/api/books/1/export.docx?sadece_onayli=true")
assert y.status_code == 200 and "filename*=UTF-8''Fethu" in y.headers["content-disposition"]
hucreler = Document(io.BytesIO(y.content)).tables[0].rows[0].cells
assert "Abdestin farzı" in hucreler[0].text and "[s. 2" in hucreler[0].text and "وفرض" in hucreler[1].text
assert any(r.bold for r in hucreler[0].paragraphs[0].runs)
assert c.get("/api/books/2/export.docx").status_code == 422
assert c.get("/api/export.docx").status_code == 404

# ---- eşzamanlılık: ikinci sayfa işleme isteği 409, LLM'e gitmez ----
girdi, devam = threading.Event(), threading.Event()


def yavas(adim, contents, kayit=None, **config):
    girdi.set()
    assert devam.wait(5)
    return sahte(adim, contents, kayit, **config)


llm.llm = yavas
sonuc = {}
is1 = threading.Thread(target=lambda: sonuc.update(a=c.post(f"/api/pages/{hazir[1]['id']}/process").status_code))
is1.start()
assert girdi.wait(5)
cagrilar.clear()
y = c.post(f"/api/pages/{pid}/process")
assert y.status_code == 409 and "işleniyor" in y.json()["detail"]
devam.set()
is1.join(5)
assert sonuc["a"] == 200
llm.llm = sahte

# ---- bütçe: aşılınca 429 ve LLM çağrılmaz ----
cagrilar.clear()
uyg.GUNLUK_BUTCE = 0.05
y = c.post(f"/api/passages/{s['pasajlar'][2]['id']}/vocalize")
assert y.status_code == 429 and "Günlük API bütçesi" in y.json()["detail"] and cagrilar == []
p2 = c.post("/api/books/2/prepare", json={"sayfalar": [1]})
assert p2.status_code == 429 and c.post("/api/books/2/estimate", json={"sayfalar": [1]}).json()["yeter"] is False
pid2 = uyg.sor("SELECT id FROM pages WHERE book_id=2 AND no=1")[0]["id"]
assert c.post(f"/api/pages/{pid2}/process").status_code == 429 and cagrilar == []
uyg.GUNLUK_BUTCE, uyg.AYLIK_BUTCE = 100, 0.05
y = c.post(f"/api/pages/{pid2}/process")
assert y.status_code == 429 and "Aylık" in y.json()["detail"] and cagrilar == []
assert not uyg.ISLEM_KILIDI.locked()  # hata sonrası kilit bırakıldı
uyg.AYLIK_BUTCE = 30
assert c.get("/api/usage").json()["aylik_sinir"] == 30

llm.llm = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("kota"))
y = c.post(f"/api/pages/{pid2}/process")
assert y.status_code == 502 and "kota" in y.json()["detail"]  # LLM hatası okunur döner
llm.llm = sahte

# ---- Ask kaldırıldı ----
assert c.post("/api/ask", json={"soru": "Abdestin farzı nedir?"}).status_code == 404
assert not hasattr(uyg, "ASK_PROMPT") and not hasattr(uyg, "TAM_BAGLAM_SINIRI")

# ---- silme ----
sayfa_dosyasi = VERI / "sayfa" / uyg.bul("pages", pid2)["dosya"]
assert c.delete(f"/api/pages/{pid2}").status_code == 200 and not sayfa_dosyasi.exists()
assert c.get("/api/books/2").json()["sayfa_sayisi"] == 1  # görüntü kitabında sayfa da gider
defter_oncesi = len(uyg.sor("SELECT id FROM usage"))
assert c.delete("/api/books/1").status_code == 200
assert c.get("/api/books/1").status_code == 404 and not (VERI / "kitap" / "1").exists()
assert not uyg.sor("SELECT id FROM pages WHERE book_id=1") and not list((VERI / "sayfa").glob("1-*"))
assert len(uyg.sor("SELECT id FROM usage")) == defter_oncesi  # harcama kaydı silinmez (bütçe)
assert c.delete("/api/books/1").status_code == 404

# ---- eski şemadan göç: veri kaybı yok ----
eski = Path(tempfile.mkdtemp())
(eski / "sayfa").mkdir()
with sqlite3.connect(eski / "kitap.db") as e:
    e.executescript("""
        CREATE TABLE pages(id INTEGER PRIMARY KEY, no INTEGER NOT NULL, dosya TEXT NOT NULL);
        CREATE TABLE passages(id INTEGER PRIMARY KEY, page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
            sira INTEGER NOT NULL, tur TEXT NOT NULL, ar TEXT NOT NULL, ar_vocalized TEXT,
            tr TEXT NOT NULL DEFAULT '', durum TEXT NOT NULL DEFAULT 'taslak');
        CREATE TABLE glossary(id INTEGER PRIMARY KEY, ar TEXT NOT NULL UNIQUE, tr TEXT NOT NULL);
        INSERT INTO pages VALUES(1, 1, '0001.jpg'), (2, 4, '0004.jpg');
        INSERT INTO passages(page_id, sira, tur, ar, tr, durum) VALUES(2, 0, 'serh', 'قال', 'Dedi', 'onayli');
        INSERT INTO glossary(ar, tr) VALUES('فرض', 'farz');""")
for ad in ("0001.jpg", "0004.jpg"):
    (eski / "sayfa" / ad).write_bytes(jpg())
uyg.VERI = eski
arsiv = c.get("/api/books").json()
assert [(b["ad"], b["sayfa_sayisi"], b["islenen"], b["onayli"]) for b in arsiv] == [("Eski sayfalar", 2, 1, 1)]
kitap = c.get(f"/api/books/{arsiv[0]['id']}").json()
assert [(s["id"], s["no"]) for s in kitap["sayfalar"]] == [(1, 1), (2, 2)]
assert c.get("/api/pages/2").json()["pasajlar"][0]["tr"] == "Dedi" and len(c.get("/api/glossary").json()) == 1
assert c.get(f"/api/books/{arsiv[0]['id']}/thumb/2").status_code == 200
uyg._hazir.discard(eski)  # yeniden açılışta göç tekrarlanmaz
assert len(c.get("/api/books").json()) == 1

shutil.rmtree(os.environ["ARAPCA_VERI"])
shutil.rmtree(eski)
print("ok")

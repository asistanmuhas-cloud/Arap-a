"""Uçtan uca API testi; LLM sahte, ağ gerekmez. Çalıştır: python test_app.py"""
import io
import json
import os
import shutil
import sqlite3
import tempfile
import threading
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

os.environ["ARAPCA_VERI"] = tempfile.mkdtemp()
import pymupdf  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app as uyg  # noqa: E402
import llm  # noqa: E402

AR = "(وفرض الوضوء) اي ركنه"
cagrilar = []  # sahte LLM'e gelen adımlar
istekler = []  # (adım, contents)
OCR, OCR2 = {}, {}  # sayfa dosya adı -> sahte OCR yanıtı (str) ya da fırlatılacak hata
HAREKE = {}  # asıl metin -> sahte harekeli metin
CEVIRI = []  # doluysa sahte çeviri sıradakini döndürür
SOZLUK = []  # sahte sözlük adayı yanıtı (str)


def sahte(adim, contents, kayit=None, **config):
    cagrilar.append(adim)
    istekler.append((adim, contents))
    yanit = (OCR if adim == "ocr" else OCR2).get(contents[0]) if adim in ("ocr", "ocr2") else None
    if isinstance(yanit, Exception):
        raise yanit  # hata yanıtı faturalanmaz
    if kayit:
        kayit({"model": "sahte", "girdi": 1000, "cikti": 100, "maliyet": 0.01})
    if adim in ("ocr", "ocr2"):
        assert contents[1] == uyg.OCR_PROMPT and config["response_schema"] == uyg.OCR_SCHEMA
        if yanit:
            return yanit
    if adim == "ocr":
        return json.dumps({"bloklar": [{"tur": "diger", "metin": "٦"}, {"tur": "serh", "metin": AR},
                                       {"tur": "hasiye", "metin": "قوله فرض"}]})
    if adim == "hareke":
        metin = contents.rsplit("\n\n", 1)[-1]
        return HAREKE.get(metin, "(وَفَرْضُ الْوُضُوءِ) أَيْ رُكْنُهُ")  # varsayılan: hemze ekledi, yalnız imla farkı
    if adim == "ceviri":
        asil = contents.rsplit(" sonu ---", 1)[-1]  # bağlam/örnek/yönerge bloklarından sonraki asıl istek
        sozlukte = any(t["ar"] == "فرض" for t in uyg.sozluk())
        assert "فرض = farz" in contents or "فرض" not in asil or not sozlukte, "sözlük çeviri isteğine eklenmeli"
        return CEVIRI.pop(0) if CEVIRI else "**Abdestin şartı** yani rüknü"  # sözlükten bilerek sapıyor
    if adim == "sozluk":
        assert config["response_schema"] == uyg.SOZLUK_SCHEMA and contents.startswith(uyg.SOZLUK_PROMPT[:40])
        return SOZLUK.pop(0)
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
istemci.yanitlar = [("[]", "STOP"), ("[]", "STOP")]  # sözlük adayı: ucuz model, düşük düşünme, 4000 tavan
llm.llm("sozluk", "x", kayit=defter.append)
assert istemci.configler[-1] == ("gemini-3.1-flash-lite", {"thinking_config": {"thinking_level": "low"},
                                                          "max_output_tokens": 4000})
assert defter[-1]["maliyet"] == (1000 * 0.25 + 500 * 1.50) / 1e6
os.environ["MODEL_SOZLUK"] = "gemini-3.5-flash"
llm.llm("sozluk", "x", kayit=defter.append)
del os.environ["MODEL_SOZLUK"]
assert istemci.configler[-1][0] == "gemini-3.5-flash"

llm.llm = sahte
llm.resim = lambda yol: yol.name
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

# ---- okuma doğruluğu: gerçek OCR çıktılarıyla (sonuc/*.json) üç sayfalık kitap ----
# kutu doğrulama
assert uyg.kutu_dogrula([10, 20, 500, 900]) == [10, 20, 500, 900]
assert uyg.kutu_dogrula([10.4, 20.6, 500, 1000]) == [10, 21, 500, 1000]
for kotu in (None, "x", [1, 2, 3], [1, 2, 3, 4, 5], [0, 0, 0, 0], [500, 0, 400, 10], [0, 50, 10, 50], [-1, 0, 5, 5],
             [0, 0, 1001, 5], [True, 0, 5, 5], ["1", 0, 5, 5], [float("nan"), 0, 5, 5], {"ymin": 1}):
    assert uyg.kutu_dogrula(kotu) is None, kotu

# talik bölme kuralı: bağımsız "قوله" + kısa alıntı + ")" olmalı
assert uyg.talik_parcala("فاثبت الماسح بقاءه بقوله انما أسلمت بعد نزول المائدة ) ومحل") == []
assert uyg.talik_parcala("بل هو مسنون لقوله ويصب الماء على يمينه ثلاثا الخ ) لان") == []
assert uyg.talik_parcala("كالجنس وقوله مستقلة ) أى مع قطع النظر") == []
assert uyg.talik_parcala("النووى قوله كان يعجبهم هذا الحديث معناه ان الله تعالى قال") == []  # ")" yok
assert uyg.talik_parcala("قوله " + "كلمة " * 30 + ") شرح") == []  # alıntı makul uzunlukta değil
assert uyg.talik_parcala("قوله ( فرادى ) أقول") == [(0, len("قوله ( فرادى ) أقول"), "فرادى")]
assert uyg.talik_parcala("قَوْلُهُ فرادى ) أقول")[0][2] == "فرادى"  # harekeli yazım


def sayfa_json(ad):
    return json.loads((Path(__file__).parent / "sonuc" / f"{ad}.json").read_text(encoding="utf-8"))["bloklar"]


S1, S2, S3 = sayfa_json("224766"), sayfa_json("224769"), sayfa_json("224772")
KUTULAR = [[30, 60, 330, 940], [5, 5, 5, 5], [400, 60, 470, 940], [480, 60, 520, 940], [525, 60, 560, 940],
           [565, 60, 800, 940], [800, 60, 980, 940]]  # ikincisi geçersiz (ymin >= ymax)
S3 = [{**b, "metin": b["metin"].replace("العذار", "[?]", 1)} if b["tur"] == "serh" else b for b in S3]  # okunamayan
g = c.post("/api/upload", files=[("dosyalar", (f"s{i}.jpg", jpg())) for i in (1, 2, 3)]).json()["kitaplar"][0]
bid = g["id"]
dosya = {s["no"]: uyg.bul("pages", s["id"])["dosya"] for s in c.get(f"/api/books/{bid}").json()["sayfalar"]}
OCR[dosya[1]] = json.dumps({"bloklar": [{**b, "kutu": k} for b, k in zip(S1, KUTULAR)]})
OCR[dosya[2]] = json.dumps({"bloklar": S2})  # kutusuz
OCR[dosya[3]] = json.dumps({"bloklar": [{**b, "kutu": [100, 50, 400, 950]} for b in S3]})
# ikinci okuma: hâşiyenin iki bloğu birleşik, şerhte bir harf farkı, bir imla farkı ve bir boşluk farkı
serh1 = S1[5]["metin"]
OCR2[dosya[1]] = json.dumps({"bloklar": [
    {"tur": "hasiye", "metin": S1[0]["metin"] + " " + S1[2]["metin"]}, S1[1], S1[3], S1[4],
    {"tur": "serh", "metin": serh1.replace("مدنية", "مدينة").replace("والأول افصح", "والاول افصح")
                                   .replace("( فرض الوضوء )", "(فرض الوضوء)")}, S1[6]]})
OCR2[dosya[2]] = RuntimeError("ikinci model kapalı")
OCR2[dosya[3]] = "bozuk json"

# kitap ayarları: varsayılan kapalı, doğrulanır, yalnızca verilen değişir
k = c.get(f"/api/books/{bid}").json()
assert k["ayar"] == {"talik_bol": False, "cift_okuma": False, "ceviri_bellegi": True, "ayet_isaret": False} and k["kuyruk"] == 0
assert c.patch(f"/api/books/{bid}", json={"ayar": {"yok": True}}).status_code == 422
assert c.patch(f"/api/books/{bid}", json={"ayar": {"talik_bol": "evet"}}).status_code == 422
assert c.patch(f"/api/books/{bid}", json={"ayar": {"talik_bol": True}}).json()["ayar"] == {
    "talik_bol": True, "cift_okuma": False, "ceviri_bellegi": True, "ayet_isaret": False}
y = c.patch(f"/api/books/{bid}", json={"ayar": {"cift_okuma": True}}).json()
assert y["ayar"] == {"talik_bol": True, "cift_okuma": True, "ceviri_bellegi": True, "ayet_isaret": False} and y["ad"] == g["ad"]
assert [b["ayar"] for b in c.get("/api/books").json() if b["id"] == bid] == [y["ayar"]]

# tahmin çift okumayla artar
t = c.post(f"/api/books/{bid}/estimate", json={"sayfalar": [1, 2, 3]}).json()
assert t["cift_okuma"] and abs(t["ocr2_ek"] - 3 * uyg.VARSAYILAN_OCR2_MALIYETI) < 1e-9
assert abs(t["tahmin"] - 3 * t["sayfa_basi"] - t["ocr2_ek"]) < 1e-9

# 1. aşama: bütün sayfaların OCR'ı (çeviri yok)
cagrilar.clear()
defter_oncesi = len(uyg.sor("SELECT id FROM usage"))
sid = {n: uyg.sor("SELECT id FROM pages WHERE book_id=? AND no=?", bid, n)[0]["id"] for n in (1, 2, 3)}
uyarilar = {n: c.post(f"/api/pages/{sid[n]}/process?asama=ocr").json()["uyarilar"] for n in (1, 2, 3)}
assert cagrilar == ["ocr", "ocr2"] * 3, cagrilar
assert uyarilar[1] == [] and "ikinci model kapalı" in uyarilar[2][0] and "çözümlenemedi" in uyarilar[3][0]
assert not uyg.sor(f"SELECT id FROM passages WHERE page_id IN ({sid[1]},{sid[2]},{sid[3]}) AND tr!=''")
defter = uyg.sor("SELECT adim, page_id FROM usage ORDER BY id")[defter_oncesi:]
assert [r["adim"] for r in defter if r["page_id"] == sid[1]] == ["ocr", "ocr2"]  # iki OCR satırı
assert [r["adim"] for r in defter if r["page_id"] == sid[3]] == ["ocr", "ocr2"]  # bozuk yanıt da faturalandı
assert [r["adim"] for r in defter if r["page_id"] == sid[2]] == ["ocr"]  # hata yanıtı faturalanmaz
t = c.post(f"/api/books/{bid}/estimate", json={"sayfalar": [1, 2, 3]}).json()
assert t["ocr2_ek"] == 0  # hepsi okunmuş: ikinci okuma yeniden yapılmayacak

P = {n: c.get(f"/api/pages/{sid[n]}").json()["pasajlar"] for n in (1, 2, 3)}

# kutular saklandı; geçersiz kutu atıldı ama pasaj kaydedildi; talik parçaları bloğun kutusunu taşır
assert [p["kutu"] for p in P[1] if p["tur"] != "hasiye"] == [None, [480, 60, 520, 940], [525, 60, 560, 940],
                                                            [565, 60, 800, 940]]
assert [p["ar"] for p in P[1] if p["tur"] == "diger"][0] == "٦"
assert {tuple(p["kutu"]) for p in P[1] if p["tur"] == "hasiye"} == {(30, 60, 330, 940), (400, 60, 470, 940),
                                                                    (800, 60, 980, 940)}
assert all(p["kutu"] is None for p in P[2]) and all(p["kutu"] == [100, 50, 400, 950] for p in P[3])

# talik bölme: gerçek metinlerde elle doğrulanmış talik sayısı ve lemmalar
lemmalar = {n: [p["lemma"] for p in P[n] if p["tur"] == "hasiye"] for n in (1, 2, 3)}
assert lemmalar[1] == [None, "على التقديرين يكون بمعنى المجموع", "واصطلاحا مسائل", "شملت انواعا الخ",
                       "وهي لغة النظافة", "وشرعا النظافة المخصوصة الى آخره", None, None, "الوضوء لغة النظافة"]
assert lemmalar[2] == ["قالوا انما كان ذلك قبل نزول المائدة", None, None, "غسل الوجه"]
assert lemmalar[3] == ["خلافا لابي يوسف", "كالشارب والحاجب الخ", "واللحية تنقله", None, None, "وهو أظهر الروايات",
                       "وقال الشافعي يجب ان كانت اللحية خفيفة",
                       "وكذا لا يجب ايصال الماء الى ما تحت الشارب والحاجب", "ثم قال", None, "فرادى", "وكيفيته الخ"]
assert sum(1 for n in lemmalar for l in lemmalar[n] if l) == 6 + 2 + 9
assert [p["ar"] for p in P[1] if p["tur"] == "hasiye"][0] == "(كتاب الطهارة)"  # talikten önceki başlık ayrı kaldı
assert all(p["ar"].startswith("قوله") for n in P for p in P[n] if p["lemma"])
# kelime içi "قوله" bölünmedi: "بقوله", "لقوله", "وقوله" taliklerin içinde kaldı
assert any("بقوله انما أسلمت" in p["ar"] for p in P[2]) and any("لقوله ويصب" in p["ar"] for p in P[3])
assert any("وقوله مستقلة" in p["ar"] and p["lemma"] == "واصطلاحا مسائل" for p in P[1])
assert any(p["ar"].startswith("معاوية") and "قوله كان يعجبهم" in p["ar"] and not p["lemma"] for p in P[2])
assert any(p["ar"].endswith("الى المحيط قوله") for p in P[3])  # sonraki sayfaya taşan yarım talik bölünmedi
assert [p["sira"] for p in P[1]] == list(range(len(P[1])))
# orijinal metin kaybolmadı: parçalar birleşince blok metni çıkar
assert " ".join(p["ar"] for p in P[3] if p["tur"] == "hasiye") == " ".join(b["metin"] for b in S3 if b["tur"] == "hasiye")

# lemma bağlama: her talik aynı sayfadaki şerhe bağlı (kısaltma: "آية" eksik, "رحمه الله" eksik)
serh_id = {n: [p["id"] for p in P[n] if p["tur"] == "serh"] for n in (1, 2, 3)}
for n in (1, 2, 3):
    assert all(p["bagli_id"] in serh_id[n] and p["bagli_sayfa"] == sid[n] for p in P[n] if p["lemma"]), n
assert [t["lemma"] for t in P[2][[p["id"] for p in P[2]].index(serh_id[2][0])]["talikler"]] == lemmalar[2][::3]
# bulunamazsa önceki sayfa: lemma_bul öncelik sırası
gruplar = [[p for p in P[2] if p["tur"] == "serh"], [p for p in P[1] if p["tur"] == "serh"]]
assert uyg.lemma_bul("فان قيل آية الوضوء مدنية الخ", gruplar) == serh_id[1][-1]
assert uyg.lemma_bul("غسل الوجه", gruplar) == serh_id[2][0]
assert uyg.lemma_bul("كلام لا يوجد اصلا", gruplar) is None and uyg.lemma_bul("الخ", gruplar) is None

# çift okuma: yalnız gerçek harf farkı saklandı (imla ve boşluk farkları değil); blok sınırı farkı yanlış alarm vermedi
serh1_p = [p for p in P[1] if p["tur"] == "serh"][-1]
assert serh1_p["supheli"] == [{"kelime": "مدنية", "diger": "مدينة", "i": serh1.split().index("مدنية")}], serh1_p["supheli"]
assert sum(len(p["supheli"]) for p in P[1]) == 1
assert all(not p["supheli"] for p in P[2] + P[3])  # ikinci okuma hatasında birincil korundu, fark yok
assert len([p for p in P[2] if p["tur"] == "serh"]) == 1

# 2. aşama: çeviriler; komşu sayfa bağlamı yalnız katmanın ilk/son pasajına girer
istekler.clear()
cagrilar.clear()
for n in (1, 2, 3):
    c.post(f"/api/pages/{sid[n]}/process?asama=ceviri")
assert set(cagrilar) == {"ceviri"} and len(cagrilar) == sum(1 for n in P for p in P[n] if p["tur"] != "diger")


def istek(p):
    return [ct for a, ct in istekler if a == "ceviri" and ct.endswith(p["ar"])]


serh2 = [p for p in P[2] if p["tur"] == "serh"][0]
[ct] = istek(serh2)
assert "YALNIZCA BAĞLAM, ÇEVİRME" in ct and "[Önceki sayfanın sonu]" in ct and "[Sonraki sayfanın başı]" in ct
onceki_kisim = ct.split("[Önceki sayfanın sonu]\n")[1].split("\n")[0]
assert serh1.endswith(onceki_kisim) and len(onceki_kisim) <= uyg.BAGLAM and "فان قيل آية الوضوء مدنية" in onceki_kisim
sonraki_kisim = ct.split("[Sonraki sayfanın başı]\n")[1].split("\n")[0]
assert [b["metin"] for b in S3 if b["tur"] == "serh"][0].startswith(sonraki_kisim) and len(sonraki_kisim) <= uyg.BAGLAM
h2 = [p for p in P[2] if p["tur"] == "hasiye"]
[ct] = istek(h2[0])  # ilk hâşiye: önceki sayfanın son hâşiye pasajı, sonraki yok
assert "لنظم الكنز" in ct and "[Sonraki sayfanın başı]" not in ct
[ct] = istek(h2[-1])  # son hâşiye: sonraki sayfanın ilk hâşiyesi
assert "قوله خلافا لابي يوسف" in ct.split("[Sonraki sayfanın başı]\n")[1] and "[Önceki sayfanın sonu]" not in ct
for p in h2[1:-1]:  # ortadakiler bağlamsız
    assert "bağlam" not in istek(p)[0]
[ct] = istek([p for p in P[1] if p["tur"] == "hasiye"][0])  # ilk sayfa: önceki sayfa yok, ama sonraki değil
assert "bağlam" not in ct
# tek pasaj "Çevir" de aynı bağlamı kullanır
istekler.clear()
c.post(f"/api/passages/{serh2['id']}/translate")
assert "[Önceki sayfanın sonu]" in istekler[-1][1] and "[Sonraki sayfanın başı]" in istekler[-1][1]

# elle "Taliklere böl": çevrilmiş/onaylı hâşiye bölünmez, nedeni söylenir; çevirisi boşsa bölünür
P[3] = c.get(f"/api/pages/{sid[3]}").json()["pasajlar"]
onek = [p for p in P[3] if p["tur"] == "hasiye" and not p["lemma"] and p["ar"].startswith("العلماء")][0]
c.patch(f"/api/passages/{onek['id']}", json={"ar": "العلماء الخ قوله فرادى ) أقول فيه نظر"})
r = c.post(f"/api/pages/{sid[3]}/split").json()
assert r["rapor"]["bolunen"] == 0 and r["rapor"]["atlanan"] == [{"sira": onek["sira"] + 1, "neden": "çevirisi var"}]
assert [p["ar"] for p in r["pasajlar"]] == [p["ar"] if p["id"] != onek["id"] else "العلماء الخ قوله فرادى ) أقول فيه نظر"
                                            for p in P[3]]
c.patch(f"/api/passages/{onek['id']}", json={"durum": "onayli"})
assert c.post(f"/api/pages/{sid[3]}/split").json()["rapor"]["atlanan"][0]["neden"] == "onaylı"
c.patch(f"/api/passages/{onek['id']}", json={"durum": "taslak", "tr": ""})
r = c.post(f"/api/pages/{sid[3]}/split").json()
assert r["rapor"]["bolunen"] == 1 and not r["rapor"]["atlanan"] and len(r["pasajlar"]) == len(P[3]) + 1
yeni = r["pasajlar"][onek["sira"]:onek["sira"] + 2]
assert yeni[0]["id"] == onek["id"] and yeni[0]["ar"] == "العلماء الخ" and yeni[1]["lemma"] == "فرادى"
assert r["rapor"]["talik"] == 10 and r["rapor"]["bagli"] == 10
assert c.post(f"/api/pages/{sid[3]}/split").json()["rapor"]["bolunen"] == 0  # ikinci kez: değişiklik yok
# çevirisi olan ama tek talik olan pasaj: metni değişmez
assert c.post(f"/api/pages/{sid[2]}/split").json()["rapor"] == {"talik": 2, "bolunen": 0, "bagli": 2, "atlanan": []}

# şüpheli kuyruğu: [?], harekelemede harf değişimi, çift okuma farkı
nawawi = [p for p in P[2] if p["ar"].startswith("معاوية")][0]
c.patch(f"/api/passages/{nawawi['id']}", json={"ar": "قال الشيخ متعلق بظهر الرجل"})
HAREKE["قال الشيخ متعلق بظهر الرجل"] = "قَالَ الشَّيْخُ مُتَعَلِّقٌ بِطُهْرِ الرَّجُلِ"
c.post(f"/api/passages/{nawawi['id']}/vocalize")
HAREKE["(كتاب الطهارة)"] = "(كِتَابُ الطَّهَارَةِ)"  # yalnız hareke: kuyruğa girmez
c.post(f"/api/passages/{[p for p in P[1] if p['tur'] == 'hasiye'][0]['id']}/vocalize")
q = c.get(f"/api/books/{bid}/queue").json()
assert [(m["no"], m["katman"], m["tur"], m["kelime"], m["diger"]) for m in q] == [
    (1, "serh", "cift", "مدنية", "مدينة"), (2, "hasiye", "hareke", "بظهر", "بِطُهْرِ"), (3, "serh", "okunamadi", "[?]", "")]
assert c.get(f"/api/books/{bid}").json()["kuyruk"] == 3
m = q[1]
assert m["passage_id"] == nawawi["id"] and m["page_id"] == sid[2]
assert "قال الشيخ متعلق بظهر الرجل"[m["bas"]:m["son"]] == "بظهر" and m["once"] == "قال الشيخ متعلق" and m["sonra"] == "الرجل"
m = q[2]
assert uyg.bul("passages", m["passage_id"])["ar"][m["bas"]:m["son"]] == "[?]" and m["once"] and m["sonra"]
# "baktım": kalıcı kapanır; olmayan madde 404
assert c.post(f"/api/passages/{q[1]['passage_id']}/dismiss", json={"anahtar": "yok"}).status_code == 404
assert c.post(f"/api/passages/{q[1]['passage_id']}/dismiss", json={"anahtar": q[1]["anahtar"]}).json() == {"kalan": 2}
assert c.post(f"/api/passages/{q[1]['passage_id']}/dismiss", json={"anahtar": q[1]["anahtar"]}).status_code == 404
assert [m["tur"] for m in c.get(f"/api/books/{bid}/queue").json()] == ["cift", "okunamadi"]
# metin düzeltilince geçersiz maddeler kendiliğinden düşer
p = c.patch(f"/api/passages/{serh1_p['id']}", json={"ar": serh1.replace("مدنية", "مدينة")}).json()
assert p["supheli"] == [] and uyg.bul("passages", serh1_p["id"])["supheli"] is None
yer = uyg.bul("passages", q[2]["passage_id"])
c.patch(f"/api/passages/{yer['id']}", json={"ar": yer["ar"].replace("[?]", "العذار")})
assert c.get(f"/api/books/{bid}/queue").json() == [] and c.get(f"/api/books/{bid}").json()["kuyruk"] == 0
# çift okuma farkı kelime yer değiştirince yeni yerinde kalır
assert uyg.supheli_gecerli({"ar": "a b x c", "supheli": json.dumps([{"kelime": "x", "diger": "y", "i": 1}])}) == [
    {"kelime": "x", "diger": "y", "i": 2}]
assert c.get(f"/api/pages/{sid[2]}").json()["pasajlar"][0]["talikler"] == []  # talik şerhte değil
c.patch(f"/api/books/{bid}", json={"ayar": {"talik_bol": False, "cift_okuma": False}})

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

# ---- önceki turun şemasından göç (books.ayar, passages.kutu/lemma/bagli_id/supheli/kapali yok) ----
onceki = Path(tempfile.mkdtemp())
(onceki / "sayfa").mkdir()
with sqlite3.connect(onceki / "kitap.db") as e:
    e.executescript("""
        CREATE TABLE books(id INTEGER PRIMARY KEY, ad TEXT NOT NULL, dosya TEXT, sayfa_sayisi INTEGER NOT NULL,
            olusturma TEXT NOT NULL DEFAULT (datetime('now','localtime')));
        CREATE TABLE pages(id INTEGER PRIMARY KEY, no INTEGER NOT NULL, dosya TEXT NOT NULL, book_id INTEGER REFERENCES books(id));
        CREATE TABLE passages(id INTEGER PRIMARY KEY, page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
            sira INTEGER NOT NULL, tur TEXT NOT NULL, ar TEXT NOT NULL, ar_vocalized TEXT,
            tr TEXT NOT NULL DEFAULT '', durum TEXT NOT NULL DEFAULT 'taslak');
        INSERT INTO books(id, ad, sayfa_sayisi) VALUES(5, 'Dürer', 1);
        INSERT INTO pages VALUES(1, 1, '5-0001.jpg', 5);
        INSERT INTO passages(page_id, sira, tur, ar, tr, durum) VALUES(1, 0, 'serh', 'قال [?] الشيخ', 'Dedi', 'onayli'),
            (1, 1, 'hasiye', 'قوله قال ) اي الشيخ', '', 'taslak');""")
(onceki / "sayfa" / "5-0001.jpg").write_bytes(jpg())
uyg.VERI = onceki
k = c.get("/api/books/5").json()
assert k["ayar"] == {"talik_bol": False, "cift_okuma": False, "ceviri_bellegi": True, "ayet_isaret": False} and k["kuyruk"] == 1
assert k["sayfalar"][0]["onayli"] == 1 and k["yonerge"] == ""
pasajlar = c.get("/api/pages/1").json()["pasajlar"]
assert [(p["ar"], p["tr"], p["kutu"], p["lemma"], p["supheli"]) for p in pasajlar] == [
    ("قال [?] الشيخ", "Dedi", None, None, []), ("قوله قال ) اي الشيخ", "", None, None, [])]
r = c.post("/api/pages/1/split").json()  # göç edilmiş veride elle bölme ve bağlama
assert r["pasajlar"][1]["lemma"] == "قال" and r["pasajlar"][1]["bagli_id"] == r["pasajlar"][0]["id"]
assert [t["lemma"] for t in r["pasajlar"][0]["talikler"]] == ["قال"]
assert c.patch("/api/books/5", json={"ayar": {"cift_okuma": True}}).json()["ayar"]["cift_okuma"]
with closing(sqlite3.connect(onceki / "kitap.db")) as e:
    assert {"kutu", "lemma", "bagli_id", "supheli", "kapali"} <= {r[1] for r in e.execute("PRAGMA table_info(passages)")}
uyg._hazir.discard(onceki)
assert c.get("/api/books/5").json()["ayar"]["cift_okuma"]  # yeniden açılışta veri duruyor
with closing(sqlite3.connect(onceki / "kitap.db")) as e:
    assert "yonerge" in {r[1] for r in e.execute("PRAGMA table_info(books)")}
    assert e.execute("SELECT yonerge FROM books WHERE id=5").fetchone()[0] == ""

# ======== çeviri kalitesi (temiz veri dizininde) ========
kalite = Path(tempfile.mkdtemp())
uyg.VERI = kalite

# ---- çift okuma: kelime sınırı (boşluk) farkı sayılmaz, gerçek harf farkı sayılır ----
B = lambda metin: [{"tur": "serh", "metin": metin}]  # noqa: E731
assert uyg.okuma_karsilastir(B("قال اوالمعنى كذا وقد اعتبرا ذلك"), B("قال او المعنى كذا وقدا عتبرا ذلك")) == {}
assert uyg.okuma_karsilastir(B("قال وهو هو كذا"), B("قال و هو هو كذا")) == {}  # hizalama bölünse de
assert uyg.okuma_karsilastir(B("في الشئ ووضو كذا"), B("في الشيء ووضوء كذا")) == {}  # eski hemze yazımı
assert uyg.okuma_karsilastir(B("قال كذا ٦ ثم"), B("قال كذا ثم")) == {}  # sayfa/dipnot rakamı
assert uyg.okuma_karsilastir(B("قال اوالمعنى مدنية كذا"), B("قال او المعنى مدينة كذا")) == {
    0: [{"kelime": "مدنية", "diger": "مدينة", "i": 2}]}  # boşluk farkının yanındaki gerçek fark kalır
assert uyg.okuma_karsilastir(B("شرب الماء ثم"), B("شرب الما ثم")) == {0: [{"kelime": "الماء", "diger": "الما", "i": 1}]}
r = uyg.okuma_karsilastir(B("قال فقد نفاسها كذا"), B("قال فد تنفاسها كذا"))[0]
assert [(m["kelime"], m["diger"]) for m in r] == [("فقد", "فد"), ("نفاسها", "تنفاسها")]  # her kelime kendi karşılığıyla
r = uyg.okuma_karsilastir(B("قال وقد اعتبرا مدنية كذا"), B("قال وقدا عتبرا مدينة كذا"))[0]
assert [m["kelime"] for m in r] == ["مدنية"]  # aynı aralıkta yalnız harf farkı olan kelime
assert uyg.okuma_karsilastir(B("قال يمسح كذا"), B("قال يمسح بمسح كذا")) == {
    0: [{"kelime": "يمسح", "diger": "يمسح بمسح", "i": 1}]}  # fazladan kelime hâlâ fark

# ---- kurulum: iki kitap, onaylı/taslak pasajlar doğrudan veritabanına ----
kA = c.post("/api/upload", files=[("dosyalar", (f"a{i}.jpg", jpg())) for i in (1, 2)]).json()["kitaplar"][0]["id"]
kB = c.post("/api/upload", files=[("dosyalar", ("b1.jpg", jpg()))]).json()["kitaplar"][0]["id"]
sA = [s["id"] for s in c.get(f"/api/books/{kA}").json()["sayfalar"]]
sB = c.get(f"/api/books/{kB}").json()["sayfalar"][0]["id"]
assert c.get(f"/api/books/{kA}").json()["ayar"]["ceviri_bellegi"] is True  # bellek varsayılan açık


def pasaj(sid, tur, ar, tr="", durum="taslak"):
    return uyg.yaz("INSERT INTO passages(page_id, sira, tur, ar, tr, durum) VALUES(?, (SELECT COUNT(*) FROM passages "
                   "WHERE page_id=?), ?, ?, ?, ?)", sid, sid, tur, ar, tr, durum)


ORTAK = "غسل الوجه واليدين ومسح الرأس وغسل الرجلين فرض في الوضوء"
hedefp = pasaj(sA[1], "serh", "(وفرض الوضوء) " + ORTAK + " عند علمائنا")
benzerA = pasaj(sA[0], "serh", ORTAK + " كذا قال", "Yüzü ve elleri yıkamak, başı meshetmek A", "onayli")
hasiyeA = pasaj(sA[0], "hasiye", ORTAK + " قوله", "Hâşiye örneği A", "onayli")
benzerB = pasaj(sB, "serh", "(وفرض الوضوء) " + ORTAK + " عند علمائنا", "Öbür kitaptan birebir örnek B", "onayli")
taslakA = pasaj(sA[0], "serh", ORTAK, "Taslak çeviri", "taslak")  # onaylı değil: örnek olmaz
uzakA = pasaj(sA[0], "serh", "باب التيمم يجوز بالصعيد الطاهر عند عدم الماء", "Uzak pasaj", "onayli")  # eşik altı
uzunA = pasaj(sA[0], "serh", ORTAK + " زيادة", "Ç" * 1500, "onayli")  # benzer ama sığmaz
p = uyg.bul("passages", hedefp)
skor = lambda x: (lambda a, b: len(a & b) / len(a | b))(uyg.kelime_kumesi(p["ar"]), uyg.kelime_kumesi(x))  # noqa
assert skor(uyg.bul("passages", benzerB)["ar"]) == 1 > skor(uyg.bul("passages", benzerA)["ar"]) >= uyg.BELLEK_ESIK
assert skor(uyg.bul("passages", uzakA)["ar"]) < uyg.BELLEK_ESIK
ornekler = [o["id"] for o in uyg.benzer_ornekler(p, kA)]
assert ornekler == [benzerA, hasiyeA, benzerB], ornekler  # aynı kitap > aynı katman > benzerlik; taslak/uzak/uzun yok

istekler.clear()
assert c.post(f"/api/passages/{hedefp}/translate").status_code == 200
[ct] = [x for a, x in istekler if a == "ceviri"]
ornek_blok = ct.split("Örnek çeviriler")[1].split("--- örnekler sonu ---")[0]
assert "YALNIZCA ÜSLUP VE TERİM ÖRNEĞİ, ÇEVİRME" in ornek_blok and ct.endswith(p["ar"])
assert "Taslak" not in ct
assert "Uzak pasaj" not in ct and "ÇÇÇ" not in ct and ornek_blok.count("[Örnek ") == 3
assert sum(len(uyg.bul("passages", k)["ar"]) + len(uyg.bul("passages", k)["tr"]) for k in ornekler) <= uyg.BELLEK_SINIR
assert ct.index("Yüzü ve elleri") < ct.index("Hâşiye örneği") < ct.index("Öbür kitaptan")
# sınır: sığmayan atlanır, sonrakiler denenir
uyg.BELLEK_SINIR = len(uyg.bul("passages", benzerA)["ar"]) + len(uyg.bul("passages", benzerA)["tr"]) + 60
assert [o["id"] for o in uyg.benzer_ornekler(p, kA)] == [benzerA]
uyg.BELLEK_SINIR = 1500
# kendi kendine örnek olmaz; ayar kapalıyken örnek eklenmez
assert hedefp not in [o["id"] for o in uyg.benzer_ornekler({**p, "durum": "onayli"}, kA)]
c.patch(f"/api/books/{kA}", json={"ayar": {"ceviri_bellegi": False}})
istekler.clear()
assert c.post(f"/api/passages/{hedefp}/translate").status_code == 200
assert "Örnek çeviriler" not in istekler[-1][1]
c.patch(f"/api/books/{kA}", json={"ayar": {"ceviri_bellegi": True}})
# binlerce onaylı pasajda hız: kelime kümeleri önbellekte
import random  # noqa: E402
import time  # noqa: E402

rnd = random.Random(1)
sozcukler = ["".join(rnd.choice("ابتثجحخدذرزسشصضطظعغفقكلمنهوي") for _ in range(rnd.randint(3, 7))) for _ in range(3000)]
with closing(uyg.db()) as e, e:
    e.executemany("INSERT INTO passages(page_id, sira, tur, ar, tr, durum) VALUES(?, 99, 'serh', ?, ?, 'onayli')",
                  [(sB, " ".join(rnd.choices(sozcukler, k=120)), "x" * 600) for _ in range(5000)])
uyg.benzer_ornekler(p, kA)
bas = time.perf_counter()
for _ in range(3):
    assert [o["id"] for o in uyg.benzer_ornekler(p, kA)] == [benzerA, hasiyeA, benzerB]
sure = (time.perf_counter() - bas) / 3
assert sure < 1.0, f"bellek araması yavaş: {sure:.2f} sn"
print(f"bellek: 5000+ onaylı pasajda arama {sure * 1000:.0f} ms")
with closing(uyg.db()) as e, e:
    e.execute("DELETE FROM passages WHERE sira=99")

# ---- kitap yönergesi: çeviri ve öneri isteğine girer, en fazla 2000 karakter ----
YON = "Dua cümleleri (r.a.) biçiminde; müellif adları: Kâsânî, Serahsî."
assert c.patch(f"/api/books/{kA}", json={"yonerge": "x" * 2001}).status_code == 422
assert c.patch(f"/api/books/{kA}", json={"yonerge": 5}).status_code == 422
y = c.patch(f"/api/books/{kA}", json={"yonerge": "  " + YON + "  "}).json()
assert y["yonerge"] == YON and y["ayar"]["ceviri_bellegi"]  # ayarlar korunur
assert [b["yonerge"] for b in c.get("/api/books").json() if b["id"] == kA] == [YON]
assert c.get(f"/api/books/{kA}").json()["yonerge"] == YON
assert c.patch(f"/api/books/{kA}", json={"ayar": {"ayet_isaret": False}}).json()["yonerge"] == YON
istekler.clear()
assert c.post(f"/api/passages/{hedefp}/translate").status_code == 200
assert YON in istekler[-1][1] and istekler[-1][1].endswith(p["ar"])
c.patch(f"/api/passages/{hedefp}", json={"tr": "Abdestin farzı"})
assert c.post(f"/api/passages/{hedefp}/agent").status_code == 200
assert istekler[-1][0] == "agent" and YON in istekler[-1][1]
istekler.clear()
c.post(f"/api/passages/{uzakA}/agent")
assert YON in istekler[-1][1]  # öneri: aynı kitabın her pasajında
diger_kitap = pasaj(sB, "serh", "قال", "Dedi")
c.post(f"/api/passages/{diger_kitap}/agent")
assert YON not in istekler[-1][1]  # başka kitabın isteğine girmez
assert c.patch(f"/api/books/{kA}", json={"yonerge": ""}).json()["yonerge"] == ""
assert c.post(f"/api/passages/{hedefp}/translate").status_code == 200
assert "üslup yönergesi" not in istekler[-1][1]

# ---- âyet/hadis işaretleme: talimat yalnız ayar açıkken; etiketler kuyruğa düşer ----
istekler.clear()
assert c.post(f"/api/passages/{hedefp}/translate").status_code == 200
assert uyg.AYET_PROMPT not in istekler[-1][1]  # varsayılan kapalı
assert c.get(f"/api/books/{kA}").json()["ayar"]["ayet_isaret"] is False
c.patch(f"/api/books/{kA}", json={"ayar": {"ayet_isaret": True}})
TR = ('Nitekim *yüzlerinizi ve dirseklere kadar ellerinizi yıkayın* [Mâide 5/6] buyrulmuştur; '
      '*namaza kalktığınızda* [âyet ?] ve "Ameller niyetlere göredir" [hadis]. Ayrıca [Âl-i İmrân 3/7].')
CEVIRI.append(TR)
assert c.post(f"/api/passages/{hedefp}/translate").json()["tr"] == TR
assert uyg.AYET_PROMPT in istekler[-1][1] and istekler[-1][1].endswith(p["ar"])
q = [m for m in c.get(f"/api/books/{kA}/queue").json() if m["tur"] == "ayet"]
assert [(m["kelime"], m["alan"], m["katman"]) for m in q] == [
    ("[Mâide 5/6]", "tr", "serh"), ("[âyet ?]", "tr", "serh"), ("[Âl-i İmrân 3/7]", "tr", "serh")]
assert all(TR[m["bas"]:m["son"]] == m["kelime"] for m in q) and q[0]["once"].endswith("yıkayın*")
assert q[0]["sonra"].startswith("buyrulmuştur") and q[0]["passage_id"] == hedefp and q[0]["page_id"] == sA[1]
assert c.get(f"/api/books/{kA}").json()["kuyruk"] == 3
assert c.post(f"/api/passages/{hedefp}/dismiss", json={"anahtar": q[0]["anahtar"]}).json() == {"kalan": 2}
assert [m["kelime"] for m in c.get(f"/api/books/{kA}/queue").json()] == ["[âyet ?]", "[Âl-i İmrân 3/7]"]
c.patch(f"/api/passages/{hedefp}", json={"tr": TR.replace(" Ayrıca [Âl-i İmrân 3/7].", "")})  # etiket silindi
assert [m["kelime"] for m in c.get(f"/api/books/{kA}/queue").json()] == ["[âyet ?]"]
c.patch(f"/api/passages/{hedefp}", json={"tr": TR.replace("[âyet ?]", "[Mâide 5/6]")})  # düzeltildi: yeni madde
assert [m["kelime"] for m in c.get(f"/api/books/{kA}/queue").json()] == ["[Mâide 5/6]", "[Âl-i İmrân 3/7]"]
c.patch(f"/api/books/{kA}", json={"ayar": {"ayet_isaret": False}})
assert len(c.get(f"/api/books/{kA}/queue").json()) == 2  # ayar kapansa da çevirideki etiketler doğrulanmalı
assert uyg.AYET_ETIKET.findall("[hadis] [s. 2] [Bakara 2/255] [ayet?] [3/4]") == ["[Bakara 2/255]", "[ayet?]"]

# ---- DOCX: *italik* ve **kalın** biçime çevrilir ----
c.patch(f"/api/passages/{hedefp}", json={"tr": "**Abdestin farzı** yani *yüzlerinizi yıkayın* [Mâide 5/6] ve 2 * 3",
                                         "durum": "onayli"})
y = c.get(f"/api/books/{kA}/export.docx?sadece_onayli=true")
kosular = [r for row in Document(io.BytesIO(y.content)).tables[0].rows for r in row.cells[0].paragraphs[0].runs]
bicim = {r.text: (bool(r.bold), bool(r.italic)) for r in kosular}
assert bicim["Abdestin farzı"] == (True, False) and bicim["yüzlerinizi yıkayın"] == (False, True), bicim
assert bicim[" [Mâide 5/6] ve 2 * 3"] == (False, False) and not any("*" in t for t in bicim if "yıkayın" in t)

# ---- sözlük adayı: istek üzerine ucuz model; sunucu eler; deftere yazılır; bütçe aşılınca çağrılmaz ----
c.post("/api/glossary", json={"ar": "فرض", "tr": "farz"})
bos = c.post("/api/upload", files=[("dosyalar", ("bos.jpg", jpg()))]).json()["kitaplar"][0]["id"]
cagrilar.clear()
y = c.post(f"/api/books/{bos}/glossary-candidates")
assert y.status_code == 422 and "onaylı pasaj yok" in y.json()["detail"] and cagrilar == []
assert c.post("/api/books/999/glossary-candidates").status_code == 404
c.patch(f"/api/passages/{benzerA}", json={"tr": "Yüzü yıkamak ve başı meshetmek abdestin farzıdır; niyet sünnettir."})
SOZLUK.append(json.dumps([
    {"ar": "مَسْح", "tr": "meshetmek", "ornek": "başı meshetmek"},  # geçerli (harekesi atılır)
    {"ar": "فرض", "tr": "farz", "ornek": "farzıdır"},  # sözlükte zaten var
    {"ar": "تيمم", "tr": "teyemmüm", "ornek": ""},  # Arapça var (uzak pasaj), Türkçe çevirilerde yok
    {"ar": "نية", "tr": "niyet", "ornek": ""},  # Türkçe var, Arapça pasajlarda yok
    {"ar": "و", "tr": "ve", "ornek": ""},  # tek harf
    {"ar": "الوجه", "tr": " ", "ornek": ""},  # boş karşılık
    {"ar": "مسح", "tr": "mesh", "ornek": "tekrar"},  # aynı terim ikinci kez
    {"ar": "غسل", "tr": "Yıkamak", "ornek": "x" * 500},  # büyük/küçük harf farkı önemsiz; örnek kısaltılır
    {"tr": "eksik"}, "bozuk"]))
defter_oncesi = len(uyg.sor("SELECT id FROM usage"))
cagrilar.clear()
y = c.post(f"/api/books/{kA}/glossary-candidates").json()
assert cagrilar == ["sozluk"] and y["onerilen"] == 10 and y["pasaj"] == 5
assert [(a["ar"], a["tr"]) for a in y["adaylar"]] == [("مسح", "meshetmek"), ("غسل", "Yıkamak")], y
assert y["adaylar"][1]["ornek"] == "x" * 200
istem = istekler[-1][1]
assert "Sözlükte zaten olanları önerme: فرض" in istem and "Uzak pasaj" in istem and "Taslak çeviri" not in istem
assert istem.index("Ç" * 50) < istem.index("Uzak pasaj") < istem.index("Yüzü yıkamak")  # en yeniler önce
defter = uyg.sor("SELECT adim, book_id, page_id FROM usage")[defter_oncesi:]
assert defter == [{"adim": "sozluk", "book_id": kA, "page_id": None}]
assert [b["maliyet"] for b in c.get("/api/books").json() if b["id"] == kA][0] >= 0.01
# 20 bin karakter sınırı: sığanlar alınır, en yeniler öncelikli
for _ in range(8):
    pasaj(sA[0], "serh", "قال " * 700, "Uzun onaylı çeviri " * 40, "onayli")
SOZLUK.append("[]")
y = c.post(f"/api/books/{kA}/glossary-candidates").json()
assert len(istekler[-1][1]) < uyg.ADAY_SINIR + 2000 and 5 <= y["pasaj"] < 13 and y["adaylar"] == []
SOZLUK.append("{bozuk")
assert c.post(f"/api/books/{kA}/glossary-candidates").status_code == 502
cagrilar.clear()
uyg.GUNLUK_BUTCE = 0.0001
y = c.post(f"/api/books/{kA}/glossary-candidates")
assert y.status_code == 429 and cagrilar == []
uyg.GUNLUK_BUTCE = 100

# ---- yalnız matn görünümü (LLM yok): şerhteki ( … ) ve çevirideki **…** sırayla ----
cagrilar.clear()
m1 = pasaj(sA[1], "serh", "(فرض الوضوء) اي ركنه (غسل الوجه) وهو", "**Abdestin farzı** yani rüknü **yüzü yıkamak**")
m2 = pasaj(sA[1], "serh", "قال (ومسح ربع الرأس) و (الكعبان)", "Dedi: **başın dörtte birini meshetmek**")
m3 = pasaj(sA[1], "hasiye", "قوله فرض الوضوء ) اي (ركنه)", "**hâşiye**")  # hâşiye: matn değil
m4 = pasaj(sA[1], "serh", "(باب التيمم)", "")  # çevrilmemiş
m5 = pasaj(sA[1], "serh", "قال الشارح كذا", "Düz çeviri")  # parantez/kalın yok: listelenmez
pasaj(sA[0], "serh", "(بسم الله)", "**Besmele**")  # önceki sayfa önce gelir
liste = c.get(f"/api/books/{kA}/matn").json()
assert cagrilar == [] and c.get("/api/books/999/matn").status_code == 404
ids = [x["passage_id"] for x in liste]
assert m3 not in ids and m5 not in ids and ids.index(m1) < ids.index(m2) < ids.index(m4)
assert liste[0]["no"] == 1 and [x["metin"] for x in liste[0]["ar"]] == ["بسم الله"]
x1, x2, x4 = (liste[ids.index(k)] for k in (m1, m2, m4))
assert [a["metin"] for a in x1["ar"]] == ["فرض الوضوء", "غسل الوجه"] and not x1["uyusmaz"]
assert [t["metin"] for t in x1["tr"]] == ["Abdestin farzı", "yüzü yıkamak"] and x1["page_id"] == sA[1]
ar1, tr1 = uyg.bul("passages", m1)["ar"], uyg.bul("passages", m1)["tr"]
assert all(ar1[a["bas"]:a["son"]] == a["metin"] for a in x1["ar"])
assert all(tr1[t["bas"]:t["son"]] == t["metin"] for t in x1["tr"])
assert x2["uyusmaz"] and len(x2["ar"]) == 2 and len(x2["tr"]) == 1  # gösterilir ama işaretli
assert x4["cevrilmemis"] and not x4["uyusmaz"] and x4["tr"] == []
assert c.get(f"/api/books/{bos}/matn").json() == []

shutil.rmtree(kalite)

shutil.rmtree(os.environ["ARAPCA_VERI"])
shutil.rmtree(eski)
shutil.rmtree(onceki)
print("ok")

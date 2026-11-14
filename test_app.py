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
from datetime import date  # noqa: E402

# varsayılanlar ve tarihe bağlı fiyat
assert llm.MODELLER["ocr"] == llm.MODELLER["ceviri"] == "gemini-3.8-flash" and llm.MODELLER["ocr2"] != llm.MODELLER["ocr"]
assert llm.fiyat("gemini-3.8-flash", date(2026, 12, 31)) == (0.75, 3.75)  # tanıtım fiyatı
assert llm.fiyat("gemini-3.8-flash", date(2027, 1, 1)) == (1.50, 7.50) and llm.fiyat("yok") is None
# Aşağıdaki testler varsayılanı değil mekanizmayı sınar; iki ayrı fiyatlı sabit modelle çalışırlar.
llm.MODELLER.update(ocr="gemini-3.1-pro-preview", hareke="gemini-3.5-flash", ceviri="gemini-3.5-flash", agent="gemini-3.5-flash")

AR = "(وفرض الوضوء) اي ركنه"
cagrilar = []  # sahte LLM'e gelen adımlar
istekler = []  # (adım, contents)
OCR, OCR2 = {}, {}  # sayfa dosya adı -> sahte OCR yanıtı (str) ya da fırlatılacak hata
HAREKE = {}  # asıl metin -> sahte harekeli metin
CEVIRI = []  # doluysa sahte çeviri sıradakini döndürür
SOZLUK = []  # sahte sözlük adayı yanıtı (str)


modeller = []  # (adım, kitap ayarından gelen model) — None: varsayılan kural


def sahte(adim, contents, kayit=None, **config):
    cagrilar.append(adim)
    istekler.append((adim, contents))
    modeller.append((adim, config.pop("model", None)))
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

gercek_llm = llm.llm  # katman modeli testinde gerçek llm() sahte istemciyle çalışır
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
MODELSIZ = {"diger_cevir": False, "model_serh": None, "model_hasiye": None}  # katman modeli seçilmemiş: varsayılan çeviri modeli
assert k["ayar"] == {"talik_bol": False, "cift_okuma": False, "ceviri_bellegi": True, "ayet_isaret": False,
                     **MODELSIZ} and k["kuyruk"] == 0
assert c.patch(f"/api/books/{bid}", json={"ayar": {"yok": True}}).status_code == 422
assert c.patch(f"/api/books/{bid}", json={"ayar": {"talik_bol": "evet"}}).status_code == 422
assert c.patch(f"/api/books/{bid}", json={"ayar": {"talik_bol": True}}).json()["ayar"] == {
    "talik_bol": True, "cift_okuma": False, "ceviri_bellegi": True, "ayet_isaret": False, **MODELSIZ}
y = c.patch(f"/api/books/{bid}", json={"ayar": {"cift_okuma": True}}).json()
assert y["ayar"] == {"talik_bol": True, "cift_okuma": True, "ceviri_bellegi": True, "ayet_isaret": False,
                     **MODELSIZ} and y["ad"] == g["ad"]
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
assert k["ayar"] == {"talik_bol": False, "cift_okuma": False, "ceviri_bellegi": True, "ayet_isaret": False,
                     **MODELSIZ} and k["kuyruk"] == 1
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
    # sürüm tablosu ve not/işaret sütunları eklendi; eski satırlar varsayılanla doldu
    assert {"notu", "isaretli"} <= {r[1] for r in e.execute("PRAGMA table_info(passages)")}
    assert e.execute("SELECT COUNT(*), SUM(isaretli), MAX(notu) FROM passages").fetchone() == (2, 0, "")
    assert e.execute("SELECT COUNT(*) FROM surumler").fetchone()[0] == 0
p0 = c.get("/api/pages/1").json()["pasajlar"][0]
assert p0["tr"] == "Dedi" and p0["notu"] == "" and p0["isaretli"] is False and p0["surum"] == 0
p0 = c.patch(f"/api/passages/{p0['id']}", json={"tr": "Dedi ki", "isaretli": True, "notu": "göç"}).json()
assert p0["surum"] == 1 and c.get(f"/api/passages/{p0['id']}/versions").json()[0]["metin"] == "Dedi"
assert c.get("/api/books").json()[0]["isaretli"] == 1

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

# ======== sürüm geçmişi, arama, not/işaret, yedek, çıktı seçenekleri (temiz veri dizininde) ========
from datetime import date  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402

import yedek  # noqa: E402

son_tur = Path(tempfile.mkdtemp())
uyg.VERI = son_tur
kA = c.post("/api/upload", files=[("dosyalar", (f"a{i}.jpg", jpg())) for i in (1, 2, 3)]).json()["kitaplar"][0]["id"]
kB = c.post("/api/upload", files=[("dosyalar", ("b1.jpg", jpg()))]).json()["kitaplar"][0]["id"]
sA = [s["id"] for s in c.get(f"/api/books/{kA}").json()["sayfalar"]]
sB = c.get(f"/api/books/{kB}").json()["sayfalar"][0]["id"]
surum = lambda kid: c.get(f"/api/passages/{kid}/versions").json()  # noqa: E731

# ---- sürüm geçmişi: her neden; değişmeyen kayıt ve boş önceki metin sürüm üretmez ----
v1 = pasaj(sA[0], "serh", "قال الشيخ", "Dedi")
assert c.get(f"/api/passages/{v1}/versions").json() == [] and c.get("/api/passages/999/versions").status_code == 404
c.patch(f"/api/passages/{v1}", json={"tr": "Dedi", "ar": "قال الشيخ", "durum": "taslak", "tur": "serh"})  # aynısı
c.patch(f"/api/passages/{v1}", json={"notu": "not", "isaretli": True})  # not/işaret sürüm üretmez
assert surum(v1) == []
c.patch(f"/api/passages/{v1}", json={"tr": "Dedi ki"})
c.patch(f"/api/passages/{v1}", json={"tr": "Şeyh dedi", "neden": "oneri"})
assert c.patch(f"/api/passages/{v1}", json={"tr": "x", "neden": "geri"}).status_code == 422  # nedeni istemci seçemez
uyg.yaz("UPDATE passages SET ar_vocalized='قَالَ الشَّيْخُ' WHERE id=?", v1)
p = c.patch(f"/api/passages/{v1}", json={"ar": "قال الشيخ رحمه الله"}).json()
assert p["ar_vocalized"] is None and p["surum"] == 3  # asıl metin değişince harekeleme yine düşer
CEVIRI.append("Şeyh -rahimehullah- dedi")
assert c.post(f"/api/passages/{v1}/translate").json()["tr"] == "Şeyh -rahimehullah- dedi"
s = surum(v1)
assert [(x["alan"], x["metin"], x["neden"]) for x in s] == [
    ("tr", "Şeyh dedi", "ceviri"), ("ar", "قال الشيخ", "elle"), ("tr", "Dedi ki", "oneri"), ("tr", "Dedi", "elle")]
assert all(x["zaman"] for x in s) and [x["id"] for x in s] == sorted((x["id"] for x in s), reverse=True)
bos_tr = pasaj(sA[0], "serh", "قال", "")  # ilk çeviri: önceki metin boş, sürüm yok
c.post(f"/api/passages/{bos_tr}/translate")
assert surum(bos_tr) == [] and uyg.bul("passages", bos_tr)["tr"]
# taliklere bölme: ilk parçanın bölünmeden önceki metni "bolme" sürümü olur
bol = pasaj(sA[1], "hasiye", "العلماء الخ قوله فرادى ) أقول فيه نظر")
r = c.post(f"/api/pages/{sA[1]}/split").json()
assert uyg.bul("passages", bol)["ar"] == "العلماء الخ" and r["rapor"]["bolunen"] == 1
assert [(x["alan"], x["metin"], x["neden"]) for x in surum(bol)] == [("ar", "العلماء الخ قوله فرادى ) أقول فيه نظر", "bolme")]
# geri yükleme: şimdiki metin "geri" sürümü olur; geri alma da geri alınabilir
ilk = s[-1]  # tr "Dedi"
p = c.post(f"/api/passages/{v1}/versions/{ilk['id']}/restore").json()
assert p["tr"] == "Dedi" and p["surum"] == 5
geri = surum(v1)[0]
assert (geri["alan"], geri["metin"], geri["neden"]) == ("tr", "Şeyh -rahimehullah- dedi", "geri")
assert c.post(f"/api/passages/{v1}/versions/{geri['id']}/restore").json()["tr"] == "Şeyh -rahimehullah- dedi"
assert surum(v1)[0]["metin"] == "Dedi" and len(surum(v1)) == 6
ar_s = [x for x in surum(v1) if x["alan"] == "ar"][0]
uyg.yaz("UPDATE passages SET ar_vocalized='x' WHERE id=?", v1)
p = c.post(f"/api/passages/{v1}/versions/{ar_s['id']}/restore").json()
assert p["ar"] == "قال الشيخ" and p["ar_vocalized"] is None and surum(v1)[0]["metin"] == "قال الشيخ رحمه الله"
n = len(surum(v1))
assert c.post(f"/api/passages/{v1}/versions/{ar_s['id']}/restore").json()["surum"] == n  # zaten o metin: sürüm yok
assert c.post(f"/api/passages/{v1}/versions/{s[0]['id'] + 999}/restore").status_code == 404
assert c.post(f"/api/passages/{bos_tr}/versions/{ar_s['id']}/restore").status_code == 404  # başka pasajın sürümü
c.patch(f"/api/passages/{v1}", json={"durum": "onayli"})
y = c.post(f"/api/passages/{v1}/versions/{ilk['id']}/restore")
assert y.status_code == 409 and "onayı kaldır" in y.json()["detail"] and len(surum(v1)) == n  # onaylıda engellenir
c.patch(f"/api/passages/{v1}", json={"durum": "taslak"})
# öneri kabulü UI'da PATCH {tr, neden: "oneri"}; elle düzenleme onaylıda serbest (eskisi gibi) ve sürüm üretir
# 50 sınırı: en eskiler silinir
cok = pasaj(sA[0], "serh", "قال", "sürüm 0")
for i in range(1, 61):
    c.patch(f"/api/passages/{cok}", json={"tr": f"sürüm {i}"})
s = surum(cok)
assert len(s) == uyg.SURUM_SINIRI == 50 and s[0]["metin"] == "sürüm 59" and s[-1]["metin"] == "sürüm 10"
# pasaj silinince (sayfa silme) sürümleri de silinir
sil_s = c.post("/api/upload", files=[("dosyalar", ("sil.jpg", jpg()))]).json()["kitaplar"][0]["id"]
sil_p = c.get(f"/api/books/{sil_s}").json()["sayfalar"][0]["id"]
sil_k = pasaj(sil_p, "serh", "قال", "a")
c.patch(f"/api/passages/{sil_k}", json={"tr": "b"})
assert uyg.sor("SELECT COUNT(*) AS n FROM surumler WHERE passage_id=?", sil_k)[0]["n"] == 1
c.delete(f"/api/books/{sil_s}")
assert uyg.sor("SELECT COUNT(*) AS n FROM surumler WHERE passage_id=?", sil_k)[0]["n"] == 0

# ---- not ve "tekrar bak" işareti ----
assert c.patch(f"/api/passages/{v1}", json={"notu": "x" * 1001}).status_code == 422
assert c.patch(f"/api/passages/{v1}", json={"isaretli": "evet"}).status_code == 422
p = c.patch(f"/api/passages/{v1}", json={"notu": "  lemmaya tekrar bak  ", "isaretli": True}).json()
assert p["notu"] == "lemmaya tekrar bak" and p["isaretli"] is True
assert c.patch(f"/api/passages/{v1}", json={"notu": "x" * 1000}).status_code == 200
c.patch(f"/api/passages/{v1}", json={"notu": "lemmaya tekrar bak"})
v2 = pasaj(sA[2], "hasiye", "قوله كذا ) اي " + "كلام " * 40, "Uzun hâşiye çevirisi " * 10)
c.patch(f"/api/passages/{v2}", json={"isaretli": True})
c.patch(f"/api/passages/{v1}", json={"isaretli": True})  # ikinci kez: hâlâ bir
k = c.get(f"/api/books/{kA}").json()
assert [s["isaretli"] for s in k["sayfalar"]] == [1, 0, 1] and k["isaretli"] == 2
assert {b["id"]: b["isaretli"] for b in c.get("/api/books").json()} == {kA: 2, kB: 0}
f = c.get(f"/api/books/{kA}/flagged").json()
assert [(x["no"], x["passage_id"], x["page_id"], x["katman"], x["notu"]) for x in f] == [
    (1, v1, sA[0], "serh", "lemmaya tekrar bak"), (3, v2, sA[2], "hasiye", "")]
assert f[0]["tr"] == uyg.bul("passages", v1)["tr"] and f[1]["ar"].endswith(" …") and len(f[1]["tr"]) <= 122
assert c.get("/api/books/999/flagged").status_code == 404 and c.get(f"/api/books/{kB}/flagged").json() == []
c.patch(f"/api/passages/{v2}", json={"isaretli": False})
assert c.get(f"/api/books/{kA}").json()["isaretli"] == 1
# not/işaret de emektir: yeniden OCR onaysız silmez, uyarı geçmişi anar
notlu_s = c.post("/api/upload", files=[("dosyalar", ("n.jpg", jpg()))]).json()["kitaplar"][0]["id"]
notlu_p = c.get(f"/api/books/{notlu_s}").json()["sayfalar"][0]["id"]
c.patch(f"/api/passages/{pasaj(notlu_p, 'serh', 'قال')}", json={"notu": "bak"})
y = c.post(f"/api/pages/{notlu_p}/ocr")
assert y.status_code == 409 and "sürüm geçmişleri" in y.json()["detail"]
c.delete(f"/api/books/{notlu_s}")

# ---- arama: Arapça harekesiz/imla farkı gözetmeden, Türkçe İ/ı kurallarıyla ----
HAREKELI = "قَالَ الشَّيْخُ إِنَّ الوُضُوءَ فَرْضٌ عَلَى المُكَلَّفِ"
a1 = pasaj(sA[1], "serh", HAREKELI, "İbadetlerin ILK şartı ıslaklık değildir")
a2 = pasaj(sB, "hasiye", "قوله ان الوضوء ) فرض", "Abdest farzdır; Iğdır'da da")
q = c.get("/api/search", params={"q": "ان الوضوء"}).json()  # harekesiz, hemzesiz
assert [(x["passage_id"], x["kitap_id"], x["katman"], x["alan"]) for x in q["sonuclar"]] == [
    (a1, kA, "serh", "ar"), (a2, kB, "hasiye", "ar")] and not q["asildi"] and q["sinir"] == 100
x = q["sonuclar"][0]
assert HAREKELI[x["bas"]:x["son"]] == "إِنَّ الوُضُوءَ" == x["eslesme"]  # son harfin harekesi dahil
assert x["once"] + x["eslesme"] + x["sonra"] == HAREKELI and x["no"] == 2 and x["kitap"] == "a1 (+2 görüntü)"
assert x["page_id"] == sA[1] and x["adet"] == 1
for sorgu in ("إنّ الوُضوء", "انَّ  الوضوء", "إن الوضوء"):  # harekeli, fazla boşluk, hemzeli
    assert [r["passage_id"] for r in c.get("/api/search", params={"q": sorgu}).json()["sonuclar"]] == [a1, a2], sorgu
assert c.get("/api/search", params={"q": "ان الوضوء", "kitap": kB}).json()["sonuclar"][0]["passage_id"] == a2
assert len(c.get("/api/search", params={"q": "ان الوضوء", "kitap": kB}).json()["sonuclar"]) == 1
assert c.get("/api/search", params={"q": "الوضوء", "kitap": 999}).status_code == 404
for kisa in ("a", " ا ", "َّ", "", "  "):
    y = c.get("/api/search", params={"q": kisa})
    assert y.status_code == 422 and "en az 2" in y.json()["detail"], kisa
tr_ara = lambda sorgu, **k: [(r["passage_id"], r["eslesme"]) for r in  # noqa: E731
                             c.get("/api/search", params={"q": sorgu, **k}).json()["sonuclar"]]
assert tr_ara("ibadet") == [(a1, "İbadet")] and tr_ara("İBADET") == [(a1, "İbadet")]
assert tr_ara("ılk") == [(a1, "ILK")] and tr_ara("ilk") == []  # Türkçede I'nın küçüğü ı
assert tr_ara("ISLAK") == [(a1, "ıslak")] and tr_ara("ığdır") == [(a2, "Iğdır")]
assert tr_ara("farz") == [(a2, "farz")]  # Türkçe sorgu Arapça metinde aranmaz
y = c.get("/api/search", params={"q": "değil"}).json()["sonuclar"][0]
assert uyg.bul("passages", y["passage_id"])["tr"][y["bas"]:y["son"]] == "değil" and y["alan"] == "tr"
# uzun metinde alıntı: kelime sınırında kesilir, eşleşme ortada
uzun = pasaj(sA[2], "serh", "قال", "baş " * 30 + "aranan kelime " + "son " * 30)
y = [r for r in c.get("/api/search", params={"q": "aranan"}).json()["sonuclar"] if r["passage_id"] == uzun][0]
assert y["once"].startswith("… baş") and y["sonra"].endswith("son …") and len(y["once"]) <= uyg.ALINTI + 2
assert y["eslesme"] == "aranan" and y["once"].endswith("baş ") and y["sonra"].startswith(" kelime")
# sonuç sınırı: pasaj başına bir sonuç, en fazla 100; aşılınca söylenir
with closing(uyg.db()) as e, e:
    e.executemany("INSERT INTO passages(page_id, sira, tur, ar, tr) VALUES(?, 50, 'serh', ?, ?)",
                  [(sB, "قال", "tekrar tekrar örnek") for _ in range(105)])
y = c.get("/api/search", params={"q": "TEKRAR"}).json()
assert len(y["sonuclar"]) == 100 and y["asildi"] and y["sonuclar"][0]["adet"] == 2
with closing(uyg.db()) as e, e:
    e.execute("DELETE FROM passages WHERE sira=50")
assert not c.get("/api/search", params={"q": "tekrar"}).json()["asildi"]
# desen araması iskelet (imla(rasm)) içinde aramayla aynı sonucu verir
for metin in [HAREKELI, "فَإِنْ قِيلَ آيَةُ الوُضُوءِ مَدَنِيَّةٌ", "على الشئ ومُوسَى إلى", "ـالحمـدُ لله"]:
    for i in range(len(metin)):
        for j in range(i + 1, min(len(metin), i + 12) + 1):
            hedef = uyg.imla(uyg.rasm(metin[i:j]))
            if len(hedef) >= 2:
                m = uyg.arapca_desen(hedef).search(metin)
                assert m and uyg.imla(uyg.rasm(m.group())) == hedef, (metin[i:j], m)
    assert uyg.arapca_desen(uyg.imla(uyg.rasm("الي موسي"))).search("على الشئ ومُوسَى إلى") is None  # sıra farklı
assert uyg.arapca_desen("اليموسي").search("قال إِلَى مُوسَى") and uyg.arapca_desen("الوضو(").search("الوضوء(") is None
# hız: 30 bin pasajda
rnd = random.Random(2)
with closing(uyg.db()) as e, e:
    e.executemany("INSERT INTO passages(page_id, sira, tur, ar, tr) VALUES(?, 60, 'serh', ?, ?)",
                  [(sB, " ".join(rnd.choices(sozcukler, k=80)), " ".join(rnd.choices(["abdest", "namaz", "farz",
                                                                                      "şart", "İmam", "ılık"], k=60)))
                   for _ in range(30000)])
for sorgu, alan in (("ان الوضوء", "ar"), ("aranan kelime", "tr"), ("لا يوجد اصلا", "ar")):
    bas = time.perf_counter()
    y = c.get("/api/search", params={"q": sorgu}).json()
    sure = time.perf_counter() - bas
    assert y["alan"] == alan and sure < 3, (sorgu, sure)
    print(f"arama: 30 bin pasajda {alan} sorgusu ({len(y['sonuclar'])} sonuç) {sure * 1000:.0f} ms")
with closing(uyg.db()) as e, e:
    e.execute("DELETE FROM passages WHERE sira=60")

# ---- yedek.py: tutarlı kopya, aynı gün üzerine yazma, 14 gün temizliği, bozuk kaynakta hata kodu ----


def sayim(yol):
    with closing(sqlite3.connect(yol)) as e:
        return [e.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("books", "pages", "passages", "surumler")]


gun = date(2026, 11, 13)
(son_tur / "yedek").mkdir()
for ad in ("kitap-2026-10-29.db", "kitap-2026-10-30.db", "kitap-2026-11-12.db", "kitap-1999-01-01.txt", "baska.db"):
    (son_tur / "yedek" / ad).write_bytes(b"eski")
assert yedek.son_yedek(son_tur) == "2026-11-12" and c.get("/api/backup/status").json() == {"son": "2026-11-12"}
hedef = yedek.gece(son_tur, gun)
assert hedef == son_tur / "yedek" / "kitap-2026-11-13.db" and sayim(hedef) == sayim(son_tur / "kitap.db")
assert sayim(hedef)[3] > 50  # sürümler de yedekte
assert sorted(f.name for f in (son_tur / "yedek").iterdir()) == [  # 2026-10-29 (15 gün) silindi, 14 gün kaldı
    "baska.db", "kitap-1999-01-01.txt", "kitap-2026-10-30.db", "kitap-2026-11-12.db", "kitap-2026-11-13.db"]
pasaj(sB, "serh", "قال", "yeni")
assert yedek.gece(son_tur, gun) == hedef and sayim(hedef)[2] == sayim(son_tur / "kitap.db")[2]  # aynı gün üzerine
assert c.get("/api/backup/status").json() == {"son": "2026-11-13"}
y = c.get("/api/backup")
assert y.status_code == 200 and y.content.startswith(b"SQLite format 3\x00")
assert "kitap-" in y.headers["content-disposition"] and ".db" in y.headers["content-disposition"]
indirilen = son_tur / "indirilen.db"
indirilen.write_bytes(y.content)
assert sayim(indirilen) == sayim(son_tur / "kitap.db")
assert not list((son_tur / "yedek").glob(".indir-*")) and not list((son_tur / "yedek").glob("*.tmp"))
bozuk = Path(tempfile.mkdtemp())
with closing(sqlite3.connect(bozuk / "kitap.db")) as e, e:
    e.execute("CREATE TABLE t(id INTEGER PRIMARY KEY, x TEXT)")
    e.execute("CREATE INDEX t_x ON t(x)")
    e.executemany("INSERT INTO t(x) VALUES(?)", [(f"satır {i} " * 5,) for i in range(3000)])
ham = bytearray((bozuk / "kitap.db").read_bytes())
ham[4096 * 3 + 100:4096 * 3 + 1500] = b"\x55" * 1400  # b-ağacı sayfası bozuldu
(bozuk / "kitap.db").write_bytes(bytes(ham))
(bozuk / "yedek").mkdir()
(bozuk / "yedek" / "kitap-2026-01-01.db").write_bytes(b"eski iyi yedek")
calis = lambda: subprocess.run([sys.executable, str(Path(__file__).parent / "yedek.py")], capture_output=True,  # noqa
                               text=True, env={**os.environ, "ARAPCA_VERI": str(bozuk)})
r = calis()
assert r.returncode == 1 and "yedek alınamadı" in r.stderr, r
assert [f.name for f in (bozuk / "yedek").iterdir()] == ["kitap-2026-01-01.db"]  # bozuk kopya yok, eski silinmedi
(bozuk / "kitap.db").write_bytes(b"veritabani degil" * 300)
r = calis()
assert r.returncode == 1 and "not a database" in r.stderr
(bozuk / "kitap.db").unlink()
assert calis().returncode == 1 and not (bozuk / "kitap.db").exists()  # salt okunur: boş veritabanı yaratmaz
r = subprocess.run([sys.executable, str(Path(__file__).parent / "yedek.py")], capture_output=True, text=True,
                   env={**os.environ, "ARAPCA_VERI": str(son_tur)})
assert r.returncode == 0 and (son_tur / "yedek" / f"kitap-{date.today().isoformat()}.db").exists()
shutil.rmtree(bozuk)

# ---- DOCX çıktı seçenekleri: düzen, harekeli, katman, aralık, onaylı; dipnotlu düzende gerçek Word dipnotu ----
dx = c.post("/api/upload", files=[("dosyalar", (f"d{i}.jpg", jpg())) for i in (1, 2, 3)]).json()["kitaplar"][0]["id"]
dS = [s["id"] for s in c.get(f"/api/books/{dx}").json()["sayfalar"]]


def talik(sid, ar, tr, lemma, bagli, durum="taslak"):
    kid = pasaj(sid, "hasiye", ar, tr, durum)
    uyg.yaz("UPDATE passages SET lemma=?, bagli_id=? WHERE id=?", lemma, bagli, kid)
    return kid


d_s1 = pasaj(dS[0], "serh", "(وفرض الوضوء) غسل الوجه", "**Abdestin farzı** yüzü yıkamaktır.", "onayli")
uyg.yaz("UPDATE passages SET ar_vocalized=? WHERE id=?", "(وَفَرْضُ الْوُضُوءِ) غَسْلُ الْوَجْهِ", d_s1)
d_t1 = talik(dS[0], "قوله وفرض الوضوء ) اي ركنه", "Yani rüknü; *âyet meali*.", "وفرض الوضوء", d_s1, "onayli")
d_t2 = talik(dS[0], "قوله غسل الوجه ) حده", "Yüzün sınırı.", "غسل الوجه", d_s1)
d_h1 = pasaj(dS[0], "hasiye", "كلام بلا قوله", "Bağsız hâşiye notu.", "onayli")
pasaj(dS[0], "diger", "٦", "")
d_s2 = pasaj(dS[1], "serh", "(ومسح الرأس)", "**Başı meshetmek.**", "onayli")
d_t3 = talik(dS[2], "قوله ومسح ) ربع", "Dörtte biri.", "ومسح", d_s2)  # sonraki sayfadaki talik
d_s3 = pasaj(dS[2], "serh", "قال", "", "taslak")  # çevrilmemiş
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def cikti(**params):
    y = c.get(f"/api/books/{dx}/export.docx", params=params)
    assert y.status_code == 200, (params, y.text)
    return Document(io.BytesIO(y.content)), y


def dipnotlar(belge):
    from docx.opc.constants import RELATIONSHIP_TYPE as RT
    from lxml import etree
    try:
        parca = belge.part.part_related_by(RT.FOOTNOTES)
    except KeyError:
        return None
    return etree.fromstring(parca.blob)


# karşılıklı (eski düzen, varsayılan): harekeli yalnız rasm kontrolünden geçende; harekeli=false asıl metni verir
belge, y = cikti()
satirlar = belge.tables[0].rows
assert len(satirlar) == 7 and "kitap-" in y.headers["content-disposition"]
assert satirlar[0].cells[1].text == "(وَفَرْضُ الْوُضُوءِ) غَسْلُ الْوَجْهِ" and satirlar[0].cells[0].text.startswith("[s. 1 · serh]")
assert satirlar[6].cells[0].text == "[s. 3 · serh] "
belge, _ = cikti(harekeli="false")
assert belge.tables[0].rows[0].cells[1].text == "(وفرض الوضوء) غسل الوجه"
assert belge.tables[0].rows[0].cells[1].paragraphs[0]._p.pPr.find(W + "bidi") is not None
uyg.yaz("UPDATE passages SET ar_vocalized=? WHERE id=?", "(وَفَرْضُ الْوُضُوعِ)", d_s1)  # harf değişmiş: kullanılmaz
assert cikti()[0].tables[0].rows[0].cells[1].text == "(وفرض الوضوء) غسل الوجه"
uyg.yaz("UPDATE passages SET ar_vocalized=? WHERE id=?", "(وَفَرْضُ الْوُضُوءِ) غَسْلُ الْوَجْهِ", d_s1)
# katman / aralık / onaylı süzgeçleri
metinler = lambda b: [r.cells[0].text for r in b.tables[0].rows]  # noqa: E731
assert all("hasiye" in t for t in metinler(cikti(katman="hasiye")[0])) and len(metinler(cikti(katman="hasiye")[0])) == 4
assert [t[:12] for t in metinler(cikti(bas=2, son=3)[0])] == ["[s. 2 · serh", "[s. 3 · hasi", "[s. 3 · serh"]
assert len(metinler(cikti(bas=3)[0])) == 2 and len(metinler(cikti(son=1)[0])) == 4
assert len(metinler(cikti(sadece_onayli="true")[0])) == 4
assert len(metinler(cikti(katman=["serh", "hasiye"], sadece_onayli="true", bas=1, son=1)[0])) == 3
# geçersiz birleşimler ve boş seçim
for params, beklenen in (({"bas": 3, "son": 2}, "ters"), ({"duzen": "dipnotlu", "katman": "hasiye"}, "şerh"),
                         ({"bas": 9}, "uyan pasaj yok"), ({"katman": "serh", "sadece_onayli": "true", "bas": 3}, "uyan")):
    y = c.get(f"/api/books/{dx}/export.docx", params=params)
    assert y.status_code == 422 and beklenen in y.json()["detail"], (params, y.text)
for params in ({"duzen": "yok"}, {"katman": ""}, {"katman": "diger"}, {"bas": 0}, {"son": "x"}):
    assert c.get(f"/api/books/{dx}/export.docx", params=params).status_code == 422, params
# yalnız Türkçe: tablo yok, sayfa başlıkları, hâşiye etiketli ve lemmalı, biçim korunur
belge, y = cikti(duzen="turkce")
assert not belge.tables and "-turkce" in y.headers["content-disposition"]
paragraflar = [(p.style.name, p.text) for p in belge.paragraphs]
assert [t for st, t in paragraflar if st.startswith("Heading")] == ["s. 1", "s. 2", "s. 3"]
assert ("Normal", "Abdestin farzı yüzü yıkamaktır.") in paragraflar
assert ("Normal", "Hâşiye: وفرض الوضوء Yani rüknü; âyet meali.") in paragraflar
assert ("Normal", "[çevrilmemiş]") in paragraflar and not any("٦" in t for _, t in paragraflar)
kosular = {r.text: r for p in belge.paragraphs for r in p.runs}
assert kosular["Abdestin farzı"].bold and kosular["âyet meali"].italic and kosular["وفرض الوضوء"].bold
assert kosular["وفرض الوضوء"]._r.rPr.find(W + "rtl") is not None
assert dipnotlar(belge) is None
# dipnotlu: şerh ana metin, bağlı talikler dipnot (lemma + çeviri), bağsız hâşiye sayfa sonunda "Hâşiye" altında
belge, y = cikti(duzen="dipnotlu")
assert "-dipnotlu" in y.headers["content-disposition"] and not belge.tables
dn = dipnotlar(belge)
assert dn is not None and dn.tag == W + "footnotes"
ayirici = [(f.get(W + "type"), f.get(W + "id")) for f in dn if f.get(W + "type")]
assert ayirici == [("separator", "-1"), ("continuationSeparator", "0")]
assert dn[0].find(f"{W}p/{W}r/{W}separator") is not None and dn[1].find(f".//{W}continuationSeparator") is not None
notlar = {f.get(W + "id"): "".join(t.text for t in f.iter(W + "t")) for f in dn if not f.get(W + "type")}
assert notlar == {"1": " وفرض الوضوء Yani rüknü; âyet meali.", "2": " غسل الوجه Yüzün sınırı.",
                  "3": " ومسح Dörtte biri."}, notlar
assert all(f.find(f".//{W}footnoteRef") is not None for f in dn if not f.get(W + "type"))
govde = belge.element.body
refler = [(r.get(W + "id"), "".join(t.text for t in r.getparent().getparent().iter(W + "t")))
          for r in govde.iter(W + "footnoteReference")]
assert [i for i, _ in refler] == ["1", "2", "3"]
assert refler[0][1] == refler[1][1] == "Abdestin farzı yüzü yıkamaktır.," and refler[2][1] == "Başı meshetmek."
assert all(r.getparent().find(f"{W}rPr/{W}vertAlign").get(W + "val") == "superscript"
           for r in govde.iter(W + "footnoteReference"))
paragraflar = [(p.style.name, p.text) for p in belge.paragraphs]
assert [t for _, t in paragraflar] == ["s. 1", "Abdestin farzı yüzü yıkamaktır.,", "Hâşiye", "Bağsız hâşiye notu.",
                                      "s. 2", "Başı meshetmek.", "s. 3", "[çevrilmemiş]"], paragraflar
assert paragraflar[2][0] == "Heading 3" and "Yüzün sınırı" not in belge.element.xml.split("footnotes")[0]
fn_kosu = {"".join(t.text for t in r.iter(W + "t")): r for r in dn.iter(W + "r")}
assert fn_kosu["وفرض الوضوء"].find(f"{W}rPr/{W}rtl") is not None and fn_kosu["âyet meali"].find(f"{W}rPr/{W}i") is not None
ozel = {pn.partname: pn.content_type for pn in belge.part.package.iter_parts()}
assert ozel["/word/footnotes.xml"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml"
assert belge.settings.element.find(f"{W}footnotePr") is not None
# süzgeçler dipnotlu düzende: aralık dışındaki şerhe bağlı talik bağsız hâşiye olur; onaylı süzgeci dipnotu da süzer
belge, _ = cikti(duzen="dipnotlu", bas=3)
assert [p.text for p in belge.paragraphs] == ["s. 3", "[çevrilmemiş]", "Hâşiye", "ومسح Dörtte biri."]
assert dipnotlar(belge) is None
belge, _ = cikti(duzen="dipnotlu", sadece_onayli="true")
assert list({f.get(W + "id") for f in dipnotlar(belge) if not f.get(W + "type")}) == ["1"]
assert [p.text for p in belge.paragraphs] == ["s. 1", "Abdestin farzı yüzü yıkamaktır.", "Hâşiye",
                                             "Bağsız hâşiye notu.", "s. 2", "Başı meshetmek."]
belge, _ = cikti(duzen="dipnotlu", katman="serh")
assert dipnotlar(belge) is None and "Hâşiye" not in [p.text for p in belge.paragraphs]
# LibreOffice varsa PDF'e çevrilir ve dipnotlar sayfada görünür
import shutil as _sh  # noqa: E402
if _sh.which("soffice"):
    pdf_dizin = Path(tempfile.mkdtemp())
    (pdf_dizin / "d.docx").write_bytes(c.get(f"/api/books/{dx}/export.docx", params={"duzen": "dipnotlu"}).content)
    subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(pdf_dizin), str(pdf_dizin / "d.docx")],
                   capture_output=True, timeout=180)
    with pymupdf.open(pdf_dizin / "d.pdf") as pdf:
        yazi = "".join(sayfa.get_text() for sayfa in pdf)
    assert "Yüzün sınırı." in yazi and "Dörtte biri." in yazi and "Bağsız hâşiye notu." in yazi
    shutil.rmtree(pdf_dizin)
    print("dipnotlu DOCX: LibreOffice ile PDF'e çevrildi, dipnotlar çıktıda")
shutil.rmtree(son_tur)

# ======== maliyet: katman modeli, yerel harekeleme, gece kuyruğu (temiz veri dizininde) ========
import shlex  # noqa: E402

from google.genai import types as gtypes  # noqa: E402

maliyet_dizin = Path(tempfile.mkdtemp())
uyg.VERI = maliyet_dizin
uyg.GUNLUK_BUTCE, uyg.AYLIK_BUTCE = 3, 30


def yanit_nesnesi(metin, neden="STOP"):
    return SimpleNamespace(text=metin, candidates=[SimpleNamespace(finish_reason=SimpleNamespace(name=neden))],
                           usage_metadata=SimpleNamespace(prompt_token_count=1000, candidates_token_count=200,
                                                          thoughts_token_count=300))


class SahteSunucu:
    """Gemini tarafı: uzak batch işleri ve yüklenen dosyalar (istemci yeniden kurulsa da durur)."""
    def __init__(self):
        self.isler, self.yuklenen, self.silinen, self.iptal, self.n = {}, [], [], [], 0
        self.yanit = {}  # anahtar -> (metin, neden) ya da ("HATA", kod, ileti)
        self.iptal_hatasi = None


class SahteGemini:
    """genai.Client yerine: models.generate_content, batches.create/get/cancel, files.upload/delete."""
    def __init__(self, sunucu):
        self.s, self.models, self.uretilen = sunucu, self, []
        self.batches = SimpleNamespace(create=self.create, get=self.get, cancel=self.cancel)
        self.files = SimpleNamespace(upload=self.upload, delete=lambda name: self.s.silinen.append(name))

    def generate_content(self, model, contents, config):
        self.uretilen.append((model, contents, config))
        return yanit_nesnesi("Normal çeviri")

    def create(self, model, src, config):
        self.s.n += 1
        ad = f"batches/{self.s.n}"
        self.s.isler[ad] = {"model": model, "src": src, "config": config, "durum": "JOB_STATE_PENDING", "hata": None,
                            "metadatasiz": False}
        return SimpleNamespace(name=ad, state=gtypes.JobState("JOB_STATE_PENDING"))

    def cancel(self, name):
        if self.s.iptal_hatasi:
            raise RuntimeError(self.s.iptal_hatasi)
        self.s.iptal.append(name)
        self.s.isler[name]["durum"] = "JOB_STATE_CANCELLED"

    def upload(self, file, config):
        self.s.yuklenen.append(Path(file).name)
        return SimpleNamespace(name=f"files/{Path(file).stem}", uri=f"https://dosya/{Path(file).name}",
                               mime_type=config["mime_type"])

    def get(self, name):
        i = self.s.isler[name]
        liste = None
        if i["durum"] == "JOB_STATE_SUCCEEDED":
            liste = []
            for r in i["src"]:
                a = r["metadata"]["anahtar"]
                y = self.s.yanit.get(a) or varsayilan_gece_yaniti(a, r)
                meta = None if i["metadatasiz"] else r["metadata"]
                if y[0] == "HATA":
                    liste.append(SimpleNamespace(metadata=meta, response=None,
                                                 error=SimpleNamespace(code=y[1], message=y[2])))
                else:
                    liste.append(SimpleNamespace(metadata=meta, response=yanit_nesnesi(*y), error=None))
        return SimpleNamespace(name=name, state=gtypes.JobState(i["durum"]),
                               error=SimpleNamespace(code=13, message=i["hata"]) if i["hata"] else None,
                               dest=SimpleNamespace(inlined_responses=liste, file_name=None))


def varsayilan_gece_yaniti(anahtar, r):
    adim = anahtar.split(":")[0]
    if adim in ("ocr", "ocr2"):
        ad = r["contents"][0]  # File API ile verilen görüntüde Part
        yanit = (OCR if adim == "ocr" else OCR2).get(ad) if isinstance(ad, str) else None
        assert not isinstance(yanit, Exception)
        return (yanit or json.dumps({"bloklar": [{"tur": "serh", "metin": AR}]}), "STOP")
    return (f"Gece çevirisi {anahtar}", "STOP")


def bitir(*adlar, durum="JOB_STATE_SUCCEEDED", hata=None):
    for ad in adlar:
        sunucu.isler[ad].update(durum=durum, hata=hata)


sunucu = SahteSunucu()
gemini = SahteGemini(sunucu)
llm._client = gemini

# ---- llm: model önceliği (kitap ayarı > MODEL_<ADIM> > MODELLER) ----
assert llm.model_sec("ceviri") == "gemini-3.5-flash" and llm.model_sec("ceviri", "gemini-3.1-flash-lite") == "gemini-3.1-flash-lite"
os.environ["MODEL_CEVIRI"] = "gemini-3.1-pro-preview"
assert llm.model_sec("ceviri") == "gemini-3.1-pro-preview" and llm.model_sec("ceviri", "gemini-3.1-flash-lite") == "gemini-3.1-flash-lite"
del os.environ["MODEL_CEVIRI"]
d = []
assert gercek_llm("ceviri", "x", kayit=d.append, model="gemini-3.1-flash-lite") == "Normal çeviri"
assert gemini.uretilen[-1][0] == "gemini-3.1-flash-lite" and gemini.uretilen[-1][2]["max_output_tokens"] == 16000
assert d == [{"model": "gemini-3.1-flash-lite", "girdi": 1000, "cikti": 500, "maliyet": (1000 * 0.25 + 500 * 1.5) / 1e6}]

# ---- katman modeli: kitap ayarı, sunucu doğrulaması, fiyatlar ----
km = c.post("/api/upload", files=[("dosyalar", (f"km{i}.jpg", jpg())) for i in (1, 2)]).json()["kitaplar"][0]["id"]
kmS = [s["id"] for s in c.get(f"/api/books/{km}").json()["sayfalar"]]
cfg = c.get("/api/config").json()
assert cfg["modeller"] == [{"ad": m, "girdi": llm.fiyat(m)[0], "cikti": llm.fiyat(m)[1]} for m in llm.FIYAT]
assert cfg["ceviri_modeli"] == "gemini-3.5-flash" and cfg["batch_orani"] == 0.5
assert cfg["hareke"] == {"motor": "gemini", "model": "gemini-3.5-flash"}
for kotu in ({"model_serh": "gpt-9"}, {"model_serh": True}, {"model_hasiye": 5}, {"talik_bol": "gemini-3.5-flash"},
             {"cift_okuma": None}, {"talik_bol": "evet"}):
    y = c.patch(f"/api/books/{km}", json={"ayar": kotu})
    assert y.status_code == 422, (kotu, y.text)
assert "fiyat tablosunda olmayan" in c.patch(f"/api/books/{km}", json={"ayar": {"model_serh": "gpt-9"}}).json()["detail"]
y = c.patch(f"/api/books/{km}", json={"ayar": {"model_serh": "gemini-3.1-flash-lite"}}).json()
assert y["ayar"]["model_serh"] == "gemini-3.1-flash-lite" and y["ayar"]["model_hasiye"] is None and y["ayar"]["ceviri_bellegi"]
uyg.yaz("UPDATE books SET ayar=? WHERE id=?", json.dumps({**y["ayar"], "model_hasiye": "kaldirilmis-model"}), km)
assert c.get(f"/api/books/{km}").json()["ayar"]["model_hasiye"] is None  # tablodan çıkmış model varsayılana düşer
k_serh = pasaj(kmS[0], "serh", "قال الشيخ فرض الوضوء")
k_has = pasaj(kmS[0], "hasiye", "قوله فرض ) اي ركن")
llm.llm = gercek_llm  # gerçek kural + sahte istemci: defter gerçek model ve fiyatı yazar
defter_oncesi = len(uyg.sor("SELECT id FROM usage"))
assert c.post(f"/api/passages/{k_serh}/translate").json()["tr"] == "Normal çeviri"
assert c.post(f"/api/passages/{k_has}/translate").status_code == 200
os.environ["MODEL_CEVIRI"] = "gemini-3.1-pro-preview"  # seçilmemiş katmanın varsayılanı olmaya devam eder
c.patch(f"/api/passages/{k_serh}", json={"tr": ""})
c.patch(f"/api/passages/{k_has}", json={"tr": ""})
assert c.post(f"/api/pages/{kmS[0]}/process?asama=ceviri").status_code == 200  # toplu iş de aynı kural
del os.environ["MODEL_CEVIRI"]
d = uyg.sor("SELECT adim, model, maliyet, gece_id FROM usage")[defter_oncesi:]
fiyat = lambda m, oran=1: llm.maliyet(m, 1000, 500) * oran  # noqa: E731
assert [(r["adim"], r["model"]) for r in d] == [("ceviri", "gemini-3.1-flash-lite"), ("ceviri", "gemini-3.5-flash"),
                                                 ("ceviri", "gemini-3.1-flash-lite"), ("ceviri", "gemini-3.1-pro-preview")], d
assert all(r["maliyet"] == fiyat(r["model"]) and r["gece_id"] is None for r in d)
assert c.patch(f"/api/books/{km}", json={"ayar": {"model_serh": None}}).json()["ayar"]["model_serh"] is None
llm.llm = sahte

# ---- yerel harekeleme: HAREKE_KOMUT ile gerçek alt süreç ----
betik = maliyet_dizin / "hareke betiği.py"  # boşluklu yol: shlex ile tırnaklanır
betik.write_text('''import sys, time
kip = sys.argv[1]
metin = sys.stdin.buffer.read().decode("utf-8")
open(sys.argv[2], "w", encoding="utf-8").write(metin) if len(sys.argv) > 2 else None
if kip == "hata":
    sys.stderr.write("model yüklenemedi"); sys.exit(3)
if kip == "bos":
    sys.exit(0)
if kip == "uyu":
    time.sleep(5)
cikti = "".join(h + ("\\u064e" if "\\u0621" <= h <= "\\u064a" else "") for h in metin)
if kip == "harf":
    cikti = cikti.replace("ظ", "ط")
sys.stdout.buffer.write(cikti.encode("utf-8"))
''', encoding="utf-8")
komut = lambda kip, *ek: " ".join(shlex.quote(x) for x in (sys.executable, str(betik), kip, *ek))  # noqa: E731
gelen = maliyet_dizin / "gelen.txt"
TEHLIKE = "قال $(touch " + str(maliyet_dizin / "enjeksiyon") + "); `id` ' \" ظهر"
assert llm.yerel_hareke(TEHLIKE, komut("ok", str(gelen))) and gelen.read_text(encoding="utf-8") == TEHLIKE
assert not (maliyet_dizin / "enjeksiyon").exists()  # metin komut satırına girmedi, kabuk yok
for kip, beklenen in (("hata", "3 koduyla çıktı: model yüklenemedi"), ("bos", "boş çıktı")):
    try:
        llm.yerel_hareke("قال", komut(kip))
        raise AssertionError("hata bekleniyordu")
    except RuntimeError as e:
        assert beklenen in str(e), e
for kotu, beklenen in (("", "boş"), ("'kapanmamış", "ayrıştırılamadı"), ("/yok/boyle/komut", "çalıştırılamadı")):
    try:
        llm.yerel_hareke("قال", kotu)
        raise AssertionError("hata bekleniyordu")
    except RuntimeError as e:
        assert beklenen in str(e), e
llm.HAREKE_ZAMAN = 1
try:
    llm.yerel_hareke("قال", komut("uyu"))
    raise AssertionError("zaman aşımı bekleniyordu")
except RuntimeError as e:
    assert "zaman aşımı" in str(e)
llm.HAREKE_ZAMAN = 120
# uygulamada: bütçe dolu olsa bile çalışır, deftere 0 maliyetli "yerel" satırı, rasm kontrolü aynen
k_h = pasaj(kmS[1], "serh", "(وفرض الوضوء) متعلق بظهر")
uyg.GUNLUK_BUTCE = 0.0
cagrilar.clear()
assert c.post(f"/api/passages/{k_h}/vocalize").status_code == 429  # Gemini motoru bütçeye takılır
os.environ["HAREKE_KOMUT"] = komut("ok")
assert c.get("/api/config").json()["hareke"] == {"motor": "yerel", "model": "yerel"}
p = c.post(f"/api/passages/{k_h}/vocalize").json()
assert p["ar_vocalized"] == "".join(h + ("َ" if "ء" <= h <= "ي" else "") for h in "(وفرض الوضوء) متعلق بظهر")
assert p["rasm"]["ayni"] and cagrilar == []  # LLM çağrılmadı
r = uyg.sor("SELECT adim, model, girdi, cikti, maliyet, book_id, page_id, gece_id FROM usage ORDER BY id DESC LIMIT 1")[0]
assert r == {"adim": "hareke", "model": "yerel", "girdi": 0, "cikti": 0, "maliyet": 0.0, "book_id": km,
             "page_id": kmS[1], "gece_id": None}
os.environ["HAREKE_KOMUT"] = komut("harf")  # yerel model harf değiştirdi: rasm kontrolü ve şüpheli kuyruğu yakalar
p = c.post(f"/api/passages/{k_h}/vocalize").json()
assert not p["rasm"]["imla"] and p["rasm"]["farklar"]
assert [(m["tur"], m["kelime"]) for m in c.get(f"/api/books/{km}/queue").json() if m["passage_id"] == k_h] == [("hareke", "بظهر")]
for kip, beklenen in (("hata", "model yüklenemedi"), ("bos", "boş çıktı")):
    os.environ["HAREKE_KOMUT"] = komut(kip)
    y = c.post(f"/api/passages/{k_h}/vocalize")
    assert y.status_code == 502 and "hareke (yerel)" in y.json()["detail"] and beklenen in y.json()["detail"], y.text
assert uyg.bul("passages", k_h)["ar_vocalized"] == p["ar_vocalized"]  # hata eski harekelemeyi silmedi
del os.environ["HAREKE_KOMUT"]
uyg.GUNLUK_BUTCE = 3

# ---- gece kuyruğu: aynı içerikte iki kitap; biri normal yoldan, biri gece kuyruğundan ----
c.post("/api/glossary", json={"ar": "فرض", "tr": "farz"})
YON2 = "Müellif adları: Zeylaî."
kitaplar_ = {}
for ad in ("normal", "gece"):
    b = c.post("/api/upload", files=[("dosyalar", (f"{ad}{i}.jpg", jpg())) for i in (1, 2, 3)]).json()["kitaplar"][0]["id"]
    c.patch(f"/api/books/{b}", json={"ayar": {"talik_bol": True, "cift_okuma": True, "model_hasiye": "gemini-3.1-flash-lite"},
                                     "yonerge": YON2})
    s_ = {s["no"]: s["id"] for s in c.get(f"/api/books/{b}").json()["sayfalar"]}
    dosya = {n: uyg.bul("pages", s_[n])["dosya"] for n in s_}
    OCR[dosya[1]] = json.dumps({"bloklar": [{**b_, "kutu": k_} for b_, k_ in zip(S1, KUTULAR)]})
    OCR[dosya[2]] = json.dumps({"bloklar": S2})
    OCR[dosya[3]] = json.dumps({"bloklar": [{**b_, "kutu": [100, 50, 400, 950]} for b_ in S3]})
    OCR2[dosya[1]] = json.dumps({"bloklar": [{**S1[5], "metin": serh1.replace("مدنية", "مدينة")}]})
    OCR2[dosya[3]] = OCR[dosya[3]]
    kitaplar_[ad] = (b, s_, dosya)
kN, sN, _ = kitaplar_["normal"]
kG, sG, dG = kitaplar_["gece"]
OCR2[kitaplar_["normal"][2][2]] = RuntimeError("ikinci model kapalı")
sunucu.yanit[f"ocr2:{sG[2]}"] = ("HATA", 503, "ikinci model kapalı")
# normal yol (arayüzdeki toplu iş gibi: önce OCR, sonra çeviri)
istekler.clear()
modeller.clear()
for n in (1, 2, 3):
    c.post(f"/api/pages/{sN[n]}/process?asama=ocr")
for n in (1, 2, 3):
    c.post(f"/api/pages/{sN[n]}/process?asama=ceviri")
normal_istek = [ct for a, ct in istekler if a == "ceviri"]
normal_model = [m for a, m in modeller if a == "ceviri"]

# tahmin yarı fiyat; seçim sınırı; bütçe reddi
t = c.post(f"/api/books/{kG}/estimate?gece=true", json={"sayfalar": [1, 2, 3]}).json()
tn = c.post(f"/api/books/{kG}/estimate", json={"sayfalar": [1, 2, 3]}).json()
assert t["gece"] and abs(t["tahmin"] - tn["tahmin"] / 2) < 1e-12 and t["normal_tahmin"] == tn["tahmin"] and t["yeter"]
assert abs(t["sayfa_basi"] - tn["sayfa_basi"] / 2) < 1e-12 and abs(t["ocr2_ek"] - tn["ocr2_ek"] / 2) < 1e-12
y = c.post(f"/api/books/{kG}/batch", json={"sayfalar": list(range(1, 12))})
assert y.status_code == 422 and "en fazla 10" in y.json()["detail"]
assert c.post(f"/api/books/{kG}/batch", json={"sayfalar": [9]}).status_code == 422
uyg.GUNLUK_BUTCE = uyg.harcama()["bugun"] + t["tahmin"] * 0.9
y = c.post(f"/api/books/{kG}/batch", json={"sayfalar": [1, 2, 3]})
assert y.status_code == 429 and "yarı fiyat" in y.json()["detail"] and not sunucu.isler and not uyg.sor("SELECT * FROM gece")
uyg.GUNLUK_BUTCE = uyg.harcama()["bugun"] + t["tahmin"] * 1.5  # bir iş sığar, ikincisi rezerv yüzünden sığmaz

# gönderim: OCR aşaması, model başına bir uzak iş (ocr: pro, ocr2: flash); istek normal OCR'la aynı
g = c.post(f"/api/books/{kG}/batch", json={"sayfalar": [3, 1, 2]}).json()
assert (g["durum"], g["asama"], g["etiket"], g["sayfalar"], g["uzak"]) == ("bekliyor", "ocr", "bekliyor (OCR)", [1, 2, 3], 2)
assert abs(g["tahmin"] - t["tahmin"]) < 1e-12 and g["harcanan"] == 0 and g["kitap"]
uz = {i["model"]: i for i in sunucu.isler.values()}
assert set(uz) == {"gemini-3.1-pro-preview", "gemini-3.5-flash"}
ocr_is = uz["gemini-3.1-pro-preview"]
assert [r["metadata"]["anahtar"] for r in ocr_is["src"]] == [f"ocr:{sG[n]}" for n in (1, 2, 3)]
assert all(r["contents"] == [dG[n], uyg.OCR_PROMPT] for n, r in zip((1, 2, 3), ocr_is["src"]))
assert ocr_is["src"][0]["config"] == {**uyg.OCR_AYAR, "max_output_tokens": 16000} and ocr_is["config"]["display_name"]
assert uz["gemini-3.5-flash"]["src"][0]["config"]["thinking_config"] == {"thinking_level": "low"}  # ocr2 kuralı
h = c.get("/api/usage").json()
assert abs(h["rezerv"] - g["tahmin"]) < 1e-12 and abs(h["kalan"] - (uyg.GUNLUK_BUTCE - h["bugun"] - g["tahmin"])) < 1e-9
ikinci_kitap = c.post("/api/upload", files=[("dosyalar", (f"ik{i}.jpg", jpg())) for i in (1, 2, 3)]).json()["kitaplar"][0]["id"]
c.patch(f"/api/books/{ikinci_kitap}", json={"ayar": {"cift_okuma": True}})
y = c.post(f"/api/books/{ikinci_kitap}/batch", json={"sayfalar": [1, 2, 3]})
assert y.status_code == 429 and len(sunucu.isler) == 2  # rezerv: iki kuyruk üst üste bütçeyi aşmaz
assert c.post(f"/api/books/{ikinci_kitap}/prepare", json={"sayfalar": [1, 2, 3]}).status_code == 429  # normal iş de
uyg.GUNLUK_BUTCE = 3

# kuyruktaki sayfa elle işlenemez, yeniden kuyruğa atılamaz, silinemez
for yol in (f"/api/pages/{sG[2]}/process", f"/api/pages/{sG[2]}/ocr", f"/api/books/{kG}/batch", f"/api/books/{kG}/prepare"):
    y = c.post(yol, json={"sayfalar": [2]})
    assert y.status_code == 409 and "gece kuyruğunda" in y.json()["detail"] and "s. 2" in y.json()["detail"], (yol, y.text)
assert c.delete(f"/api/pages/{sG[1]}").status_code == 409 and c.delete(f"/api/books/{kG}").status_code == 409
assert not uyg.ISLEM_KILIDI.locked()
z = {s["no"]: s["gece"] for s in c.get(f"/api/books/{kG}").json()["sayfalar"]}
assert z == {n: {"durum": "ocr", "is": g["id"]} for n in (1, 2, 3)}
assert [x["id"] for x in c.get(f"/api/books/{kG}").json()["gece"]] == [g["id"]]

# yoklama: uzak iş sürüyorsa bekler; bir uzak iş bitip öbürü sürüyorsa da bekler
assert c.post("/api/batches/check").json()[0]["durum"] == "bekliyor"
bitir([a for a, i in sunucu.isler.items() if i["model"] == "gemini-3.1-pro-preview"][0])
assert c.post("/api/batches/check").json()[0]["asama"] == "ocr" and not uyg.sor("SELECT id FROM usage WHERE gece_id IS NOT NULL")

# sunucu yeniden başladı: yeni istemci, şema yeniden açılıyor; iş veritabanından kaldığı yerden yoklanır
gemini = SahteGemini(sunucu)
llm._client = gemini
uyg._hazir.discard(maliyet_dizin)
bitir(*sunucu.isler)
istekler.clear()
cagrilar.clear()
g = [x for x in c.post("/api/batches/check").json() if x["id"] == g["id"]][0]
assert (g["durum"], g["asama"], g["etiket"]) == ("bekliyor", "ceviri", "OCR bitti, çeviri bekliyor") and cagrilar == []
assert [h_["mesaj"] for h_ in g["hatalar"]] == [f"s. 2: ikinci okuma yapılamadı, birincil okuma kaydedildi "
                                                 f"(ocr2: 503 ikinci model kapalı)"]
# OCR sonuçları normal yolla aynı biçimde (kutu doğrulama, talik bölme, lemma bağı, çift okuma farkı)
alanlar = lambda pid: [(p["tur"], p["ar"], p["kutu"], p["lemma"], p["supheli"], p["sira"],  # noqa: E731
                        p["bagli_sayfa"] is not None) for p in c.get(f"/api/pages/{pid}").json()["pasajlar"]]
for n in (1, 2, 3):
    assert alanlar(sG[n]) == alanlar(sN[n]), n
assert any(p["supheli"] for p in c.get(f"/api/pages/{sG[1]}").json()["pasajlar"])  # ocr2 farkı işaretlendi
d = uyg.sor("SELECT adim, model, maliyet, page_id, book_id FROM usage WHERE gece_id=? ORDER BY id", g["id"])
assert sorted((r["adim"], r["page_id"]) for r in d) == sorted([("ocr", sG[n]) for n in (1, 2, 3)] + [("ocr2", sG[1]), ("ocr2", sG[3])])
assert all(r["maliyet"] == fiyat(r["model"], 0.5) and r["book_id"] == kG for r in d)  # yarı fiyat, hata yanıtı yok
assert abs(g["harcanan"] - sum(r["maliyet"] for r in d)) < 1e-12
assert abs(c.get("/api/usage").json()["rezerv"] - (g["tahmin"] - g["harcanan"])) < 1e-12
# çeviri işi kendiliğinden gönderildi: model başına bir uzak iş, istekler normal çeviriyle birebir aynı
cev = [i for a, i in sunucu.isler.items() if i["src"][0]["metadata"]["anahtar"].startswith("ceviri")]
assert sorted(i["model"] for i in cev) == ["gemini-3.1-flash-lite", "gemini-3.5-flash"] and len(sunucu.isler) == 4
gece_istek = {r["metadata"]["anahtar"]: r["contents"] for i in cev for r in i["src"]}
pG = {n: c.get(f"/api/pages/{sG[n]}").json()["pasajlar"] for n in (1, 2, 3)}
sirali = [p for n in (1, 2, 3) for p in pG[n] if p["tur"] != "diger"]
assert len(gece_istek) == len(sirali) == len(normal_istek)
for p, ct, m in zip(sirali, normal_istek, normal_model):
    assert ct == gece_istek[f"ceviri:{p['page_id']}:{p['id']}"]
    assert [i["model"] for i in cev if any(r["metadata"]["anahtar"] == f"ceviri:{p['page_id']}:{p['id']}" for r in i["src"])] == [
        llm.model_sec("ceviri", m)]
assert any("فرض = farz" in ct for ct in gece_istek.values()) and all(YON2 in ct for ct in gece_istek.values())
assert any("[Önceki sayfanın sonu]" in ct for ct in gece_istek.values())
assert all(r["config"] == {"thinking_config": {"thinking_level": "low"}, "max_output_tokens": 16000} for i in cev for r in i["src"])
# çeviri sürerken: düzenleme serbest (ama çeviri/OCR değil); gelen sonuç çevrilmiş/onaylı pasajın üzerine yazmaz
elle, onayli_, recit, kesik = sirali[0], sirali[1], sirali[2], sirali[3]
assert c.post(f"/api/passages/{elle['id']}/translate").status_code == 409
c.patch(f"/api/passages/{elle['id']}", json={"tr": "Elle çeviri"})
c.patch(f"/api/passages/{onayli_['id']}", json={"tr": "Onaylı çeviri", "durum": "onayli"})
sunucu.yanit[f"ceviri:{recit['page_id']}:{recit['id']}"] = ("", "RECITATION")
sunucu.yanit[f"ceviri:{kesik['page_id']}:{kesik['id']}"] = ("yarım", "MAX_TOKENS")
cev_adlar = [a for a, i in sunucu.isler.items() if i in cev]
sunucu.isler[cev_adlar[0]]["metadatasiz"] = True  # metadata dönmezse istek sırasıyla eşlenir
bitir(*cev_adlar)
g = [x for x in c.post("/api/batches/check").json() if x["id"] == g["id"]][0]
assert (g["durum"], g["etiket"]) == ("tamam", "tamam") and g["bitis"] and not c.get("/api/usage").json()["rezerv"]
mesajlar = [h_["mesaj"] for h_ in g["hatalar"]]
assert any("RECITATION" in m for m in mesajlar) and any("çıktı tavanına" in m for m in mesajlar) and len(mesajlar) == 3
assert {h_["passage_id"] for h_ in g["hatalar"][1:]} == {recit["id"], kesik["id"]}
yeni = {p["id"]: p for n in (1, 2, 3) for p in c.get(f"/api/pages/{sG[n]}").json()["pasajlar"]}
assert yeni[elle["id"]]["tr"] == "Elle çeviri" and yeni[onayli_["id"]]["tr"] == "Onaylı çeviri"
assert yeni[recit["id"]]["tr"] == "" and yeni[kesik["id"]]["tr"] == ""
for p in sirali[4:]:
    assert yeni[p["id"]]["tr"] == f"Gece çevirisi ceviri:{p['page_id']}:{p['id']}", p["id"]
d = uyg.sor("SELECT adim, model, maliyet FROM usage WHERE gece_id=? AND adim='ceviri'", g["id"])
assert len(d) == len(sirali) and all(r["maliyet"] == fiyat(r["model"], 0.5) for r in d)  # boş/kesik de faturalı
# iş bitti: sayfalar yeniden elle işlenebilir; başarısız pasaj elle çevrilir
z = {s["no"]: s["gece"] for s in c.get(f"/api/books/{kG}").json()["sayfalar"]}
hatali_no = {n for n in (1, 2, 3) for p in pG[n] if p["id"] in (recit["id"], kesik["id"])}
assert {n for n, v in z.items() if v} == hatali_no and all(z[n]["durum"] == "hata" for n in hatali_no)
assert c.post(f"/api/passages/{recit['id']}/translate").status_code == 200
c.post(f"/api/passages/{kesik['id']}/translate")
assert not any(s["gece"] for s in c.get(f"/api/books/{kG}").json()["sayfalar"])  # sayfa bitince hata gösterilmez
# tahmin: gece satırları normal fiyata çevrilerek ortalamaya girer
ort = uyg.sor("""SELECT AVG(t) AS o FROM (SELECT SUM(CASE WHEN gece_id IS NULL THEN maliyet ELSE maliyet * 2 END) AS t
                FROM usage WHERE page_id IS NOT NULL AND adim IN ('ocr','ceviri') GROUP BY page_id)""")[0]["o"]
assert abs(c.post(f"/api/books/{kG}/estimate", json={"sayfalar": [1]}).json()["sayfa_basi"] - ort) < 1e-12

# ---- kısmi OCR hatası, yalnız çeviri işi, görüntüler File API ile (inline sınırı aşılınca) ----
kH = c.post("/api/upload", files=[("dosyalar", (f"h{i}.jpg", jpg())) for i in (1, 2)]).json()["kitaplar"][0]["id"]
sH = {s["no"]: s["id"] for s in c.get(f"/api/books/{kH}").json()["sayfalar"]}
sunucu.yanit[f"ocr:{sH[2]}"] = ("HATA", 400, "görüntü okunamadı")
llm.BATCH_INLINE_SINIR = 0
oncesi = set(sunucu.isler)
gH = c.post(f"/api/books/{kH}/batch", json={"sayfalar": [1, 2]}).json()
[yeniH] = [sunucu.isler[a] for a in set(sunucu.isler) - oncesi]
assert sorted(sunucu.yuklenen[-2:]) == sorted(uyg.bul("pages", sH[n])["dosya"] for n in (1, 2))
assert all(r["contents"][0].file_data.file_uri.startswith("https://dosya/") for r in yeniH["src"])
llm.BATCH_INLINE_SINIR = 18 * 1024 * 1024
bitir(*(set(sunucu.isler) - oncesi))
gH = [x for x in c.post("/api/batches/check").json() if x["id"] == gH["id"]][0]
assert gH["asama"] == "ceviri" and gH["durum"] == "bekliyor", gH
assert sorted(sunucu.silinen) == sorted(f"files/{Path(uyg.bul('pages', sH[n])['dosya']).stem}" for n in (1, 2))
assert [(h_["no"], h_["mesaj"]) for h_ in gH["hatalar"]] == [(2, "OCR: 400 görüntü okunamadı")]
assert not c.get(f"/api/pages/{sH[2]}").json()["pasajlar"] and c.get(f"/api/pages/{sH[1]}").json()["pasajlar"]
assert all(i["src"][0]["metadata"]["anahtar"].startswith(f"ceviri:{sH[1]}:")
           for a, i in sunucu.isler.items() if a not in oncesi and i is not yeniH)
# tümden başarısız (süresi dolmuş) çeviri işi: iş hata, sayfalar elle işlenebilir
son = [a for a in sunucu.isler if a not in oncesi and sunucu.isler[a] is not yeniH]
bitir(*son, durum="JOB_STATE_EXPIRED", hata="48 saatte tamamlanamadı")
gH = [x for x in c.post("/api/batches/check").json() if x["id"] == gH["id"]][0]
assert gH["durum"] == "hata" and "JOB_STATE_EXPIRED" in gH["hata"] and "48 saat" in gH["hata"]
assert uyg.bekleyen_sayfalar() == {}
assert c.post(f"/api/pages/{sH[2]}/process").status_code == 200  # elle işlenebilir
z = {s["no"]: s["gece"] for s in c.get(f"/api/books/{kH}").json()["sayfalar"]}
assert z[2] is None and z[1]["durum"] == "hata"  # çevrilmemiş kaldı, son işin hatası görünür
# OCR'lanacak sayfa yoksa doğrudan çeviri işi; yalnız OCR işi tümden başarısız olursa iş hata
oncesi = set(sunucu.isler)
gH2 = c.post(f"/api/books/{kH}/batch", json={"sayfalar": [1]}).json()
assert gH2["asama"] == "ceviri" and gH2["etiket"] == "OCR bitti, çeviri bekliyor"
assert all(sunucu.isler[a]["src"][0]["metadata"]["anahtar"].startswith("ceviri:") for a in set(sunucu.isler) - oncesi)
bitir(*(set(sunucu.isler) - oncesi), durum="JOB_STATE_FAILED", hata="iç hata")
gH2 = [x for x in c.post("/api/batches/check").json() if x["id"] == gH2["id"]][0]
assert gH2["durum"] == "hata" and "iç hata" in gH2["hata"] and not uyg.sor("SELECT id FROM usage WHERE gece_id=?", gH2["id"])
y = c.post(f"/api/books/{kH}/batch", json={"sayfalar": [2]})
assert y.status_code == 422 and "zaten" in y.json()["detail"]  # 2. sayfa elle çevrildi

# ---- iptal: uzak iş de iptal edilir; iptal başarısızsa iş bekler ----
kI = c.post("/api/upload", files=[("dosyalar", ("i1.jpg", jpg()))]).json()["kitaplar"][0]["id"]
sI = c.get(f"/api/books/{kI}").json()["sayfalar"][0]["id"]
oncesi = set(sunucu.isler)
gI = c.post(f"/api/books/{kI}/batch", json={"sayfalar": [1]}).json()
sunucu.iptal_hatasi = "ağ yok"
y = c.post(f"/api/batches/{gI['id']}/cancel")
assert y.status_code == 502 and "ağ yok" in y.json()["detail"] and uyg.bul("gece", gI["id"])["durum"] == "bekliyor"
sunucu.iptal_hatasi = None
gI = c.post(f"/api/batches/{gI['id']}/cancel").json()
assert (gI["durum"], gI["etiket"]) == ("iptal", "iptal edildi") and gI["bitis"] and sunucu.iptal[-1:] == list(set(sunucu.isler) - oncesi)
assert c.post(f"/api/batches/{gI['id']}/cancel").status_code == 409 and c.post("/api/batches/999/cancel").status_code == 404
assert c.post(f"/api/pages/{sI}/ocr").status_code == 200 and c.get("/api/usage").json()["rezerv"] == 0
# gönderim yarıda kalırsa (ikinci uzak iş reddedildi) gönderilen de iptal edilir, iş kaydı kalmaz
c.patch(f"/api/books/{kI}", json={"ayar": {"cift_okuma": True}})
kJ = c.post("/api/upload", files=[("dosyalar", ("j1.jpg", jpg()))]).json()["kitaplar"][0]["id"]
c.patch(f"/api/books/{kJ}", json={"ayar": {"cift_okuma": True}})
asil_create = gemini.create
gemini.batches.create = lambda model, src, config: (asil_create(model, src, config) if "ocr2" not in config["display_name"]
                                                    else (_ for _ in ()).throw(RuntimeError("kota aşıldı")))
oncesi_is = len(uyg.sor("SELECT id FROM gece"))
y = c.post(f"/api/books/{kJ}/batch", json={"sayfalar": [1]})
assert y.status_code == 502 and "kota aşıldı" in y.json()["detail"] and len(uyg.sor("SELECT id FROM gece")) == oncesi_is
assert sunucu.isler[sunucu.iptal[-1]]["config"]["display_name"].endswith("-ocr") and not uyg.ISLEM_KILIDI.locked()
gemini.batches.create = asil_create

# ---- arka plan yoklayıcısı: bekleyen işi kendiliğinden ilerletir; başka sayfa işlenirken o turu atlar ----
oncesi = set(sunucu.isler)
gJ = c.post(f"/api/books/{kJ}/batch", json={"sayfalar": [1]}).json()
bitir(*(set(sunucu.isler) - oncesi))
dur = threading.Event()
uyg.ISLEM_KILIDI.acquire()
is_ = threading.Thread(target=uyg.gece_yoklayici, args=(dur, 0.01))
is_.start()
time.sleep(0.2)
assert uyg.bul("gece", gJ["id"])["asama"] == "ocr"  # kilit tutulurken dokunmadı
uyg.ISLEM_KILIDI.release()
bas = time.perf_counter()
while uyg.bul("gece", gJ["id"])["asama"] != "ceviri" and time.perf_counter() - bas < 5:
    time.sleep(0.02)
dur.set()
is_.join(2)
assert uyg.bul("gece", gJ["id"])["asama"] == "ceviri" and not is_.is_alive()
c.post(f"/api/batches/{gJ['id']}/cancel")
liste = c.get("/api/batches").json()
assert [x["id"] for x in liste] == sorted((x["id"] for x in liste), reverse=True) and {x["durum"] for x in liste} >= {"tamam", "hata", "iptal"}
assert [x["book_id"] for x in c.get(f"/api/batches?kitap={kH}").json()] == [kH, kH] and c.get("/api/batches?kitap=999").status_code == 404
# bitmiş işi olan kitap silinebilir; iş kayıtları gider, defter kalır
defter_say = len(uyg.sor("SELECT id FROM usage"))
assert c.delete(f"/api/books/{kH}").status_code == 200 and not uyg.sor("SELECT id FROM gece WHERE book_id=?", kH)
assert len(uyg.sor("SELECT id FROM usage")) == defter_say
shutil.rmtree(maliyet_dizin)

# ---- önceki turun şemasından göç: usage.gece_id ve gece tablosu yok ----
gocm = Path(tempfile.mkdtemp())
with sqlite3.connect(gocm / "kitap.db") as e:
    e.executescript("""
        CREATE TABLE books(id INTEGER PRIMARY KEY, ad TEXT NOT NULL, dosya TEXT, sayfa_sayisi INTEGER NOT NULL,
            olusturma TEXT NOT NULL DEFAULT (datetime('now','localtime')), ayar TEXT NOT NULL DEFAULT '{}',
            yonerge TEXT NOT NULL DEFAULT '');
        CREATE TABLE usage(id INTEGER PRIMARY KEY, zaman TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            adim TEXT NOT NULL, model TEXT NOT NULL, girdi INTEGER NOT NULL, cikti INTEGER NOT NULL,
            maliyet REAL NOT NULL, book_id INTEGER, page_id INTEGER);
        INSERT INTO books(id, ad, sayfa_sayisi, ayar) VALUES(3, 'Eski', 0, '{"talik_bol": true}');
        INSERT INTO usage(adim, model, girdi, cikti, maliyet, book_id) VALUES('ceviri', 'gemini-3.5-flash', 10, 10, 0.25, 3);""")
uyg.VERI = gocm
h = c.get("/api/usage").json()
assert h["bugun"] == 0.25 and h["rezerv"] == 0 and c.get("/api/batches").json() == []
k = c.get("/api/books/3").json()
assert k["ayar"]["talik_bol"] and k["ayar"]["model_serh"] is None and k["gece"] == []
with closing(sqlite3.connect(gocm / "kitap.db")) as e:
    assert "gece_id" in {r[1] for r in e.execute("PRAGMA table_info(usage)")}
    assert e.execute("SELECT adim, maliyet, gece_id FROM usage").fetchall() == [("ceviri", 0.25, None)]
shutil.rmtree(gocm)
print("maliyet: katman modeli, yerel harekeleme, gece kuyruğu ok")

uyg.VERI = Path(os.environ["ARAPCA_VERI"])
shutil.rmtree(os.environ["ARAPCA_VERI"])
shutil.rmtree(eski)
shutil.rmtree(onceki)
print("ok")

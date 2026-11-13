"""Uçtan uca API testi; LLM sahte, ağ gerekmez. Çalıştır: python test_app.py"""
import io
import json
import os
import shutil
import tempfile

os.environ["ARAPCA_VERI"] = tempfile.mkdtemp()
from fastapi.testclient import TestClient  # noqa: E402

import app as uyg  # noqa: E402
import llm  # noqa: E402

AR = "(وفرض الوضوء) اي ركنه"


def sahte(adim, contents, **config):
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
    return "Yanıt [s. 1]"


llm.llm = sahte
llm.resim = lambda yol: "resim"
c = TestClient(uyg.app)

assert c.post("/api/upload", files=[("dosyalar", ("a.txt", b"x"))]).status_code == 400
assert c.post("/api/upload", files=[("dosyalar", ("a.jpg", b"\xff\xd8x"))]).json() == {"eklenen": 1}
import pymupdf  # noqa: E402

pdf = pymupdf.open()
pdf.new_page(), pdf.new_page()
assert c.post("/api/upload", files=[("dosyalar", ("k.pdf", pdf.tobytes()))]).json() == {"eklenen": 2}
assert [s["no"] for s in c.get("/api/pages").json()] == [1, 2, 3]
assert c.get("/api/pages/2/image").content[:2] == b"\xff\xd8"
assert c.get("/api/pages/99").status_code == 404

assert c.post("/api/glossary", json={"ar": "فَرْض", "tr": "farz"}).json()[0]["ar"] == "فرض"
assert c.post("/api/glossary", json={"ar": "", "tr": "x"}).status_code == 422

pasajlar = c.post("/api/pages/1/ocr").json()["pasajlar"]
assert [p["tur"] for p in pasajlar] == ["diger", "serh", "hasiye"]
kid = pasajlar[1]["id"]
assert c.patch(f"/api/passages/{kid}", json={"durum": "onayli"}).status_code == 422  # boş çeviri onaylanmaz
assert c.post(f"/api/passages/{kid}/agent").status_code == 422

p = c.post(f"/api/passages/{kid}/translate").json()
assert [t["tr"] for t in p["sapma"]] == ["farz"]  # sözlük sapması işaretlendi
assert c.post("/api/pages/1/ocr").status_code == 409  # emek varken OCR üzerine yazmaz

p = c.post(f"/api/passages/{kid}/vocalize").json()
assert p["ar"] == AR and p["rasm"]["imla"] and not p["rasm"]["ayni"]  # asıl metin ezilmedi

oneri = c.post(f"/api/passages/{kid}/agent").json()
assert [o["yeni"] for o in oneri] == ["farzı"]  # uygulanamayan öneri elendi
p = c.patch(f"/api/passages/{kid}", json={"tr": "**Abdestin farzı** yani rüknü", "durum": "onayli"}).json()
assert p["sapma"] == [] and p["durum"] == "onayli"
assert c.post(f"/api/passages/{kid}/translate").status_code == 409  # onaylı pasaj ezilmez
assert c.get("/api/pages").json()[0]["onayli"] == 1

p = c.patch(f"/api/passages/{kid}", json={"ar": AR + " ."}).json()
assert p["ar_vocalized"] is None  # asıl değişince harekeleme düşer

assert c.post("/api/ask", json={"soru": "Abdestin farzı nedir?"}).json()["yanit"].startswith("Yanıt")
assert c.post("/api/ask", json={"soru": "a"}).status_code == 422

from docx import Document  # noqa: E402

y = c.get("/api/export.docx?sadece_onayli=true")
assert y.status_code == 200
hucreler = Document(io.BytesIO(y.content)).tables[0].rows[0].cells
assert "Abdestin farzı" in hucreler[0].text and "وفرض" in hucreler[1].text
assert any(r.bold for r in hucreler[0].paragraphs[0].runs)

llm.llm = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("kota"))
assert c.post(f"/api/passages/{pasajlar[2]['id']}/translate").status_code == 502  # LLM hatası okunur döner

assert c.delete("/api/pages/1").status_code == 200 and len(c.get("/api/pages").json()) == 2
shutil.rmtree(os.environ["ARAPCA_VERI"])
print("ok")

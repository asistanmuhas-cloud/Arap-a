"""Kitap ayarı diger_cevir: "diğer" katmanı toplu çeviriye girer; LLM sahte, ağ gerekmez. Çalıştır: python test_diger.py"""
import os
import shutil
import tempfile

os.environ["ARAPCA_VERI"] = tempfile.mkdtemp()
from fastapi.testclient import TestClient  # noqa: E402

import app as uyg  # noqa: E402
import llm  # noqa: E402

cagri = []


def sahte(adim, contents, kayit=None, **config):
    assert adim == "ceviri"
    cagri.append(contents)
    return "çeviri"


llm.llm = sahte
c = TestClient(uyg.app)
bid = uyg.yaz("INSERT INTO books(ad, sayfa_sayisi) VALUES('k', 1)")
sid = uyg.yaz("INSERT INTO pages(no, dosya, book_id) VALUES(1, 'a.jpg', ?)", bid)


def pasaj(sira, tur, ar):
    return uyg.yaz("INSERT INTO passages(page_id, sira, tur, ar) VALUES(?, ?, ?, ?)", sid, sira, tur, ar)


serh, numara, dipnot = pasaj(0, "serh", "قال الشيخ"), pasaj(1, "diger", "٦ - (1)"), pasaj(2, "diger", "أي الماهية والجنس")


def tr():
    return {p["id"]: p["tr"] for p in c.get(f"/api/pages/{sid}").json()["pasajlar"]}


# ---- varsayılan: kapalı; diğer katmanı çevrilmez ----
assert c.get(f"/api/books/{bid}").json()["ayar"]["diger_cevir"] is False
assert c.post(f"/api/pages/{sid}/process?asama=ceviri").status_code == 200
assert tr() == {serh: "çeviri", numara: "", dipnot: ""} and len(cagri) == 1

# ---- açık: Arapça harf içeren diğer pasajı çevrilir, harfsiz blok (sayfa numarası) çağrı harcamaz ----
assert c.patch(f"/api/books/{bid}", json={"ayar": {"diger_cevir": "evet"}}).status_code == 422
assert c.patch(f"/api/books/{bid}", json={"ayar": {"diger_cevir": True}}).json()["ayar"]["diger_cevir"] is True
assert c.post(f"/api/pages/{sid}/process?asama=ceviri").status_code == 200
assert tr() == {serh: "çeviri", numara: "", dipnot: "çeviri"} and len(cagri) == 2
assert "أي الماهية والجنس" in cagri[-1]
assert c.post(f"/api/pages/{sid}/process?asama=ceviri").status_code == 200 and len(cagri) == 2  # çevrilmiş yeniden çevrilmez

# ---- gece kuyruğu da aynı kuralı kullanır ----
ayar = uyg.kitap_ayari(bid)
p = {"tur": "diger", "ar": "باب"}
assert uyg.cevrilecek(p, ayar) and not uyg.cevrilecek(p, {**ayar, "diger_cevir": False})
assert uyg.cevrilecek({"tur": "hasiye", "ar": "١"}, {**ayar, "diger_cevir": False})
assert not uyg.cevrilecek({"tur": "diger", "ar": "٦ (1)"}, ayar)

shutil.rmtree(os.environ["ARAPCA_VERI"])
print("ok")

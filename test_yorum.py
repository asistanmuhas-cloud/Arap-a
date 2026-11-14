"""Model açıklaması (ÇN satırları) çeviriden ayrılır; LLM sahte, ağ gerekmez. Çalıştır: python test_yorum.py"""
import os
import shutil
import tempfile

os.environ["ARAPCA_VERI"] = tempfile.mkdtemp()
from fastapi.testclient import TestClient  # noqa: E402

import app as uyg  # noqa: E402
import llm  # noqa: E402

# ---- ayırıcı ----
assert uyg.yorum_ayir("**Abdestin farzı** yani rüknü") == ("**Abdestin farzı** yani rüknü", "")
assert uyg.yorum_ayir("Beyit\n\nÇN: Ma'n b. Evs'e aittir.\n**ÇN:** İstişhat için (r.a.)\n") == (
    "Beyit", "Ma'n b. Evs'e aittir.\nİstişhat için (r.a.)")
assert uyg.yorum_ayir("Bir\nÇN: ara not\n\n\n\nİki") == ("Bir\n\nİki", "ara not")  # parçalı çeviride arada da olur
assert uyg.yorum_ayir("ÇN:\n> ÇN : x") == ("", "x")  # boş açıklama düşer
assert uyg.yorum_ayir("LÇN: bu çeviridir") == ("LÇN: bu çeviridir", "")  # yalnız satır başındaki işaret
assert "ÇN:" in uyg.CEVIRI_PROMPT

# ---- uçtan uca: çeviri -> tr + yorum; elle düzenleme yorumu korur; yeniden çeviri yeniler ----
YANIT = []
istekler = []


def sahte(adim, contents, kayit=None, **config):
    assert adim == "ceviri"
    istekler.append(contents)
    return YANIT.pop(0)


llm.llm = sahte
c = TestClient(uyg.app)
bid = uyg.yaz("INSERT INTO books(ad, sayfa_sayisi) VALUES('k', 1)")
sid = uyg.yaz("INSERT INTO pages(no, dosya, book_id) VALUES(1, 'a.jpg', ?)", bid)
kid = uyg.yaz("INSERT INTO passages(page_id, sira, tur, ar) VALUES(?, 0, 'serh', 'قال الشاعر')", sid)
assert c.get(f"/api/pages/{sid}").json()["pasajlar"][0]["yorum"] == ""

YANIT.append("Şair şöyle dedi\n\nÇN: Beyit Ma'n b. Evs'e aittir.")
p = c.post(f"/api/passages/{kid}/translate").json()
assert p["tr"] == "Şair şöyle dedi" and p["yorum"] == "Beyit Ma'n b. Evs'e aittir.", p
assert "ÇN:" in istekler[-1]
p = c.patch(f"/api/passages/{kid}", json={"tr": "Şair dedi ki"}).json()
assert p["yorum"] == "Beyit Ma'n b. Evs'e aittir."  # elle düzenleme açıklamayı silmez
assert [s["alan"] for s in c.get(f"/api/passages/{kid}/versions").json()] == ["tr"]  # yorum sürüm üretmez
assert c.patch(f"/api/passages/{kid}", json={"yorum": "  "}).json()["yorum"] == ""  # Kaldır
assert c.patch(f"/api/passages/{kid}", json={"yorum": "x" * 8001}).status_code == 422

YANIT.append("Şair şöyle dedi\nÇN: yeni not")
assert c.post(f"/api/passages/{kid}/translate").json()["yorum"] == "yeni not"
YANIT.append("Şair şöyle dedi")
assert c.post(f"/api/passages/{kid}/translate").json()["yorum"] == ""  # açıklamasız yeni çeviri eskisini bırakmaz

shutil.rmtree(os.environ["ARAPCA_VERI"])
print("ok")

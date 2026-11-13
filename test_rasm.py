from arapca_test import rasm_kontrol

assert rasm_kontrol("قال الشافعي", "قَالَ الشَّافِعِيُّ")["ayni"]
assert not rasm_kontrol("قال الشافعي", "قَالَ الشَّافِعِيُّ رَحِمَهُ")["ayni"]  # kelime eklemiş
assert not rasm_kontrol("قال", "قَأل")["ayni"]  # hemze eklemiş
r = rasm_kontrol("الى ان عزمت", "إِلَى أَنْ عَزَمْتُ")  # hemze kürsüsü: imla farkı, harf değişimi değil
assert not r["ayni"] and r["imla"] and not r["farklar"]
r = rasm_kontrol("متعلق بظهر", "مُتَعَلِّقٌ بِطُهْرٍ")  # ظ -> ط gerçek harf değişimi
assert not r["imla"] and r["farklar"]
print("ok")

from arapca_test import parcali  # RECITATION: uzun metin bölünerek yeniden denenir


def ezberci(metin):
    if len(metin) > 6:
        raise RuntimeError("boş yanıt (finish_reason=RECITATION)")
    return metin


assert parcali(ezberci, "قال ابو يوسف رحمه الله") == "قال ابو يوسف رحمه الله"
print("ok parcali")

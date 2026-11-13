from arapca_test import rasm_kontrol

assert rasm_kontrol("قال الشافعي", "قَالَ الشَّافِعِيُّ")["ayni"]
assert not rasm_kontrol("قال الشافعي", "قَالَ الشَّافِعِيُّ رَحِمَهُ")["ayni"]  # kelime eklemiş
assert not rasm_kontrol("قال", "قَأل")["ayni"]  # hemze eklemiş
print("ok")

"""Yerel harekeleme sarmalayıcısı (CATT, Abjad AI'nin "catt-tashkeel" paketi; ONNX, CPU'da çalışır).

stdin'den harekesiz Arapça metni (UTF-8) alır, harekeli metni stdout'a yazar; hata olursa açıklamayı stderr'e yazıp
1 ile çıkar. Uygulama HAREKE_KOMUT ayarlıysa harekelemeyi bu komutla yapar (app.py / llm.yerel_hareke).

Yalnızca hareke eklenir: model Arapça harf dışındaki her şeyi (parantez, noktalama, rakam, [?]) atarak çalışır; burada
modelin harekeleri asıl metnin harflerine geri yerleştirilir, harfler ve diğer karakterler olduğu gibi kalır. Baskıda
zaten harekesi olan harfe model harekesi eklenmez. Model en fazla ~1000 karakter aldığı için metin kelime sınırında
parçalanır (parça sınırında bağlam kaybolur).

Kurulum (isteğe bağlı; requirements.txt'de yok). Paket onnxruntime-gpu ister; GPU'suz sunucuda o sürüm sağlayıcı
belirtilmeden oturum açmayı reddettiği için bağımlılıklar elle kurulur:
    python3 -m venv /opt/arapca/hareke-venv
    /opt/arapca/hareke-venv/bin/pip install --no-deps catt-tashkeel==1.0.2
    /opt/arapca/hareke-venv/bin/pip install onnxruntime numpy tqdm
    # (deploy/kur.sh bu dosyayı /opt/arapca/ altına kopyalar)
    # model ağırlıkları ilk çalıştırmada github.com/abjadai/catt sürümlerinden paket dizinine iner (eo 75 MB, ed 89 MB);
    # servis kullanıcısı oraya yazamayacağı için bir kez root olarak indir:
    echo "قال الشيخ" | /opt/arapca/hareke-venv/bin/python /opt/arapca/hareke_yerel.py --model eo
    # /etc/arapca.env:
    HAREKE_KOMUT=/opt/arapca/hareke-venv/bin/python /opt/arapca/hareke_yerel.py --model eo
--model eo (encoder-only, varsayılan) hızlıdır: geliştirme makinesinde CPU'da 3786 karakterlik gerçek bir sayfa model
yüklemesi dahil 1.5 sn sürdü. ed (encoder-decoder) yazarlarına göre daha isabetli ama özyinelemeli çözdüğü için aynı
sayfada 359 sn sürdü; uygulamanın 120 sn zaman aşımına takılır, yalnız kısa pasajlar için düşünülebilir.
"""
import argparse
import contextlib
import re
import sys

HARF = re.compile("[\u0621-\u063a\u0641-\u064a\u0671]")  # modelin tanıdığı harfler (ٱ elif olarak verilir)
HAREKE = re.compile("[\u064b-\u0652\u0670\u0640]")  # arapca_test.HAREKE ile aynı küme
PARCA = 800  # model girdisi en fazla 1024 konum (BOS/EOS dahil); güvenli parça boyu (karakter)


def girdi(metin: str) -> str:
    """Modele gidecek metin: yalnız harfler; hareke/tatvil atlanır, diğer her karakter kelime ayırır."""
    s = "".join("ا" if h == "ٱ" else h if HARF.match(h) else "" if HAREKE.match(h) else " " for h in metin)
    return " ".join(s.split())


def parcala(sade: str) -> list:
    parcalar, simdi = [], ""
    for k in sade.split():
        if simdi and len(simdi) + 1 + len(k) > PARCA:
            parcalar.append(simdi)
            simdi = k
        else:
            simdi = f"{simdi} {k}" if simdi else k
    return parcalar + ([simdi] if simdi else [])


def yerlestir(metin: str, harekeli_parcalar: list) -> str:
    """Model çıktısındaki her harfin harekesini asıl metindeki sıradaki harfe ekler; harf tutmazsa hareke eklenmez."""
    ciftler = []  # (harf, harekeler)
    for parca in harekeli_parcalar:
        for h in parca:
            if HARF.match(h):
                ciftler.append([h, ""])
            elif HAREKE.match(h) and ciftler:
                ciftler[-1][1] += h
    sonuc, i = [], 0
    for n, h in enumerate(metin):
        sonuc.append(h)
        if not HARF.match(h):
            continue
        harf, hareke = ciftler[i] if i < len(ciftler) else ("", "")
        i += 1
        zaten = n + 1 < len(metin) and HAREKE.match(metin[n + 1])
        if harf == ("ا" if h == "ٱ" else h) and not zaten:
            sonuc.append(hareke)
    return "".join(sonuc)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--model", choices=["eo", "ed"], default="eo")
    secim = ap.parse_args()
    metin = sys.stdin.buffer.read().decode("utf-8")
    sade = girdi(metin)
    if not sade:
        sys.stdout.write(metin)
        return
    with contextlib.redirect_stdout(sys.stderr):  # paket yükleme/indirme iletilerini stdout'a basıyor
        from catt_tashkeel import CATTEncoderDecoder, CATTEncoderOnly

        model = (CATTEncoderDecoder if secim.model == "ed" else CATTEncoderOnly)()
        cikti = model.do_tashkeel_batch(parcala(sade), batch_size=8, verbose=False)
    sys.stdout.buffer.write(yerlestir(metin, cikti).encode("utf-8"))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        sys.stderr.write(f"hareke_yerel: {type(e).__name__}: {e}\n")
        sys.exit(1)

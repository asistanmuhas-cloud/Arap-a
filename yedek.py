"""Gecelik yedek: veritabanının SQLite çevrimiçi yedekleme API'siyle (Connection.backup) alınmış tutarlı kopyası.

Çalıştır:
    python yedek.py        ->  <ARAPCA_VERI>/yedek/kitap-YYYY-AA-GG.db
Aynı gün ikinci çalıştırma o günün yedeğinin üzerine yazar. Kopya önce geçici dosyaya alınır, PRAGMA integrity_check
geçerse yerine taşınır; geçmezse geçici dosya silinir, önceki yedekler korunur ve 1 koduyla çıkılır. 14 günden eski
yedekler (dosya adındaki tarihe göre) yalnızca yedek başarılıysa silinir. Sayfa görüntüleri ve PDF'ler yedeklenmez.
"""
import os
import re
import sqlite3
import sys
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

SAKLA_GUN = 14
AD = re.compile(r"kitap-(\d{4}-\d{2}-\d{2})\.db")


class YedekHatasi(Exception):
    pass


def kopyala(kaynak: Path, hedef: Path):
    """kaynak veritabanının tutarlı kopyasını hedef'e yazar; bütünlük denetiminden geçmezse YedekHatasi."""
    if not kaynak.is_file():
        raise YedekHatasi(f"{kaynak} bulunamadı")
    gecici = hedef.with_name(hedef.name + ".tmp")
    gecici.unlink(missing_ok=True)
    try:
        # salt okunur açılır: kaynak yoksa ya da bozuksa boş veritabanı yaratılmasın
        with closing(sqlite3.connect(kaynak.resolve().as_uri() + "?mode=ro", uri=True)) as k, \
                closing(sqlite3.connect(gecici)) as h:
            k.backup(h)
            sonuc = [r[0] for r in h.execute("PRAGMA integrity_check")]
        if sonuc != ["ok"]:
            raise YedekHatasi("bütünlük denetimi başarısız: " + "; ".join(map(str, sonuc[:5])))
        gecici.replace(hedef)
    except sqlite3.Error as e:
        raise YedekHatasi(f"{type(e).__name__}: {e}") from e
    finally:
        gecici.unlink(missing_ok=True)


def temizle(dizin: Path, bugun: date) -> list:
    """Adındaki tarih bugünden SAKLA_GUN günden daha eski yedekleri siler; silinenlerin adları."""
    sinir, silinen = bugun - timedelta(days=SAKLA_GUN), []
    for f in dizin.glob("kitap-*.db"):
        m = AD.fullmatch(f.name)
        try:
            eski = m and date.fromisoformat(m[1]) < sinir
        except ValueError:
            continue
        if eski:
            f.unlink()
            silinen.append(f.name)
    return sorted(silinen)


def son_yedek(veri: Path) -> Optional[str]:
    """En yeni gecelik yedeğin tarihi (YYYY-AA-GG) ya da None."""
    tarihler = [m[1] for f in (veri / "yedek").glob("kitap-*.db") if (m := AD.fullmatch(f.name))]
    return max(tarihler, default=None)


def gece(veri: Path, bugun: Optional[date] = None) -> Path:
    bugun = bugun or date.today()
    dizin = veri / "yedek"
    dizin.mkdir(parents=True, exist_ok=True)
    hedef = dizin / f"kitap-{bugun.isoformat()}.db"
    kopyala(veri / "kitap.db", hedef)
    temizle(dizin, bugun)
    return hedef


def main() -> int:
    veri = Path(os.environ.get("ARAPCA_VERI", Path(__file__).parent / "data"))
    try:
        hedef = gece(veri)
    except (YedekHatasi, OSError) as e:
        print(f"yedek alınamadı: {e}", file=sys.stderr)
        return 1
    print(f"yedek: {hedef}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env bash
# Gardrop'u nginx ile statik site olarak yayınlar (+ certbot varsa HTTPS). Telefona kurulum, kamera ve
# çevrimdışı çalışma HTTPS ister.
# Kullanım (repo kökünde, root olarak):
#   sudo bash gardrop/deploy/kur.sh gardrop.ornek.com            # arka plan modeli CDN'den (staticimgly.com)
#   sudo bash gardrop/deploy/kur.sh gardrop.ornek.com --model    # modeli sunucuya kopyala (~130 MB, npm gerekir)
# Güncelleme: git pull && aynı komut.
set -euo pipefail

ALAN="${1:?Kullanım: sudo bash gardrop/deploy/kur.sh <alan.adi> [--model]}"
MODEL="${2:-}"
[ "$(id -u)" = 0 ] || { echo "root olarak çalıştır (sudo)"; exit 1; }
command -v nginx >/dev/null || { echo "nginx bulunamadı"; exit 1; }
KAYNAK="$(cd "$(dirname "$0")/.." && pwd)"
HEDEF=/var/www/gardrop

mkdir -p "$HEDEF"
# Uygulama dosyaları (test, plan ve sunucu fonksiyonu yayınlanmaz)
for x in index.html manifest.webmanifest sw.js ikon.svg ikon-180.png ikon-192.png ikon-512.png css js vendor; do
  rm -rf "${HEDEF:?}/$x"
  cp -r "$KAYNAK/$x" "$HEDEF/$x"
done
rm -rf "$HEDEF/vendor/arka-plan-veri"

if [ "$MODEL" = "--model" ]; then
  command -v npm >/dev/null || { echo "--model için npm gerekir"; exit 1; }
  GECICI="$(mktemp -d)"
  (cd "$GECICI" && npm pack -s @imgly/background-removal-data@1.4.5 >/dev/null && tar xzf imgly-background-removal-data-1.4.5.tgz)
  cp -r "$GECICI/package/dist" "$HEDEF/vendor/arka-plan-veri"
  rm -rf "$GECICI"
  echo "Model yerel olarak kuruldu: $HEDEF/vendor/arka-plan-veri"
fi

command -v restorecon >/dev/null && restorecon -R "$HEDEF" || true

KONF=/etc/nginx/conf.d/gardrop.conf
if [ ! -f "$KONF" ]; then
  cat > "$KONF" <<EOF
server {
    listen 80;
    server_name $ALAN;
    root $HEDEF;
    index index.html;
    types { application/manifest+json webmanifest; application/wasm wasm; }
    location = /sw.js { add_header Cache-Control "no-cache"; }
    location /vendor/arka-plan-veri/ { add_header Cache-Control "public, max-age=31536000, immutable"; }
    location / { try_files \$uri \$uri/ /index.html; add_header Cache-Control "no-cache"; }
}
EOF
  if ! nginx -t; then rm -f "$KONF"; echo "nginx ayarı geçersiz; eklenen dosya geri alındı"; exit 1; fi
fi
systemctl reload nginx
if command -v certbot >/dev/null; then
  certbot --nginx -d "$ALAN" --non-interactive --agree-tos --register-unsafely-without-email --redirect || echo "certbot başarısız; HTTPS'i elle kur"
else
  echo "certbot yok: telefona kurulum ve kamera için HTTPS gerekir."
fi
echo "Hazır: https://$ALAN"

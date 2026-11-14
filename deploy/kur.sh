#!/usr/bin/env bash
# Oracle Linux sunucusuna kurulum: systemd servisi + gecelik yedek zamanlayıcısı + nginx alt alan adı + parola +
# (varsa certbot ile) HTTPS.
# Yalnızca yeni dosya ekler; mevcut nginx ayarlarına dokunmaz, nginx -t geçmezse eklediğini geri alır.
# Kullanım (repo kökünde, root olarak):  sudo bash deploy/kur.sh ceviri.fremensu.com.tr
# Güncelleme: git pull && sudo bash deploy/kur.sh ceviri.fremensu.com.tr   (anahtar ve parola korunur)
set -euo pipefail

ALAN="${1:?Kullanım: sudo bash deploy/kur.sh <alt.alan.adi>}"
[ "$(id -u)" = 0 ] || { echo "root olarak çalıştır (sudo)"; exit 1; }
KAYNAK="$(cd "$(dirname "$0")/.." && pwd)"
HEDEF=/opt/arapca
PORT=8765
command -v nginx >/dev/null || { echo "nginx bulunamadı; bu betik nginx varsayar. Kurulu web sunucusunu bildir."; exit 1; }

# 1) Python >= 3.10
PY=""
for aday in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$aday" >/dev/null && "$aday" -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then PY="$aday"; break; fi
done
if [ -z "$PY" ]; then dnf install -y python3.11 && PY=python3.11; fi

# 2) Kod, sanal ortam, servis kullanıcısı
id arapca >/dev/null 2>&1 || useradd --system --home-dir "$HEDEF" --shell /sbin/nologin arapca
mkdir -p "$HEDEF/data"
cp "$KAYNAK"/{app.py,llm.py,arapca_test.py,yedek.py,index.html,requirements.txt} "$HEDEF/"
cp "$KAYNAK/deploy/hareke_yerel.py" "$HEDEF/"  # isteğe bağlı yerel harekeleme (kurulumu dosyanın başında)
[ -x "$HEDEF/venv/bin/pip" ] || "$PY" -m venv "$HEDEF/venv"
"$HEDEF/venv/bin/pip" install -q --upgrade pip -r "$HEDEF/requirements.txt"
chown -R arapca:arapca "$HEDEF"

# 3) Gemini anahtarı (ekrana yazılmaz, yalnız root ve servis okur)
if [ ! -s /etc/arapca.env ]; then
  read -rsp "GEMINI_API_KEY: " ANAHTAR; echo
  [ -n "$ANAHTAR" ] || { echo "anahtar boş olamaz"; exit 1; }
  (umask 077; printf 'GEMINI_API_KEY=%s\nGUNLUK_BUTCE_USD=3\nAYLIK_BUTCE_USD=30\n' "$ANAHTAR" > /etc/arapca.env)
fi

cat > /etc/systemd/system/arapca.service <<EOF
[Unit]
Description=Arapca ceviri calisma alani
After=network-online.target

[Service]
User=arapca
WorkingDirectory=$HEDEF
EnvironmentFile=/etc/arapca.env
Environment=ARAPCA_VERI=$HEDEF/data
ExecStart=$HEDEF/venv/bin/uvicorn app:app --host 127.0.0.1 --port $PORT
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF

# Gecelik yedek: SQLite çevrimiçi yedekleme API'siyle $HEDEF/data/yedek/kitap-YYYY-AA-GG.db (14 gün saklanır)
cat > /etc/systemd/system/arapca-yedek.service <<EOF
[Unit]
Description=Arapca ceviri veritabani yedegi

[Service]
Type=oneshot
User=arapca
WorkingDirectory=$HEDEF
EnvironmentFile=/etc/arapca.env
Environment=ARAPCA_VERI=$HEDEF/data
ExecStart=$HEDEF/venv/bin/python $HEDEF/yedek.py
EOF
cat > /etc/systemd/system/arapca-yedek.timer <<EOF
[Unit]
Description=Arapca ceviri veritabani yedegi (her gece)

[Timer]
OnCalendar=*-*-* 03:30:00
RandomizedDelaySec=15min
Persistent=true

[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable arapca >/dev/null
systemctl restart arapca
systemctl enable --now arapca-yedek.timer >/dev/null

# 4) nginx: parola korumalı ters vekil (uygulamanın kendi kimlik doğrulaması yok)
if [ ! -s /etc/nginx/arapca.htpasswd ]; then
  read -rp "Site kullanıcı adı: " KULLANICI
  read -rsp "Site parolası: " PAROLA; echo
  [ -n "$KULLANICI" ] && [ "${#PAROLA}" -ge 8 ] || { echo "kullanıcı adı boş olamaz, parola en az 8 karakter olmalı"; exit 1; }
  (umask 027; printf '%s:%s\n' "$KULLANICI" "$(openssl passwd -apr1 "$PAROLA")" > /etc/nginx/arapca.htpasswd)
  chgrp nginx /etc/nginx/arapca.htpasswd
fi
CONF=/etc/nginx/conf.d/arapca.conf
if [ ! -e "$CONF" ]; then  # certbot'un sonradan eklediği HTTPS satırlarını ezmemek için yalnız ilk kurulumda yazılır
  cat > "$CONF" <<EOF
server {
    listen 80;
    server_name $ALAN;
    client_max_body_size 200m;
    auth_basic "Ceviri";
    auth_basic_user_file /etc/nginx/arapca.htpasswd;
    location / {
        proxy_pass http://127.0.0.1:$PORT;
        proxy_set_header Host \$host;
        proxy_read_timeout 600s;   # OCR ve çeviri çağrıları uzun sürebilir
    }
}
EOF
  nginx -t || { rm -f "$CONF"; echo "nginx -t başarısız; $CONF geri alındı"; exit 1; }
fi
command -v setsebool >/dev/null && setsebool -P httpd_can_network_connect 1 || true  # SELinux: nginx -> 127.0.0.1
systemctl reload nginx

# 5) Doğrulama
sleep 2
systemctl is-active --quiet arapca || { journalctl -u arapca -n 30 --no-pager; echo "servis ayakta değil"; exit 1; }
curl -fsS -o /dev/null "http://127.0.0.1:$PORT/api/pages" || { echo "uygulama yanıt vermiyor"; exit 1; }
systemctl is-active --quiet arapca-yedek.timer || { echo "yedek zamanlayıcısı etkin değil"; exit 1; }
echo "Gecelik yedek: $HEDEF/data/yedek (elle denemek için: systemctl start arapca-yedek; journalctl -u arapca-yedek)"
echo "Uygulama çalışıyor: http://$ALAN (DNS'te $ALAN için A kaydı bu sunucuyu göstermeli)"

if command -v certbot >/dev/null; then
  certbot --nginx -d "$ALAN" --redirect || echo "certbot başarısız; DNS kaydını kontrol edip 'certbot --nginx -d $ALAN' ile yeniden dene"
else
  echo "UYARI: certbot yok; site şimdilik HTTP. Parola şifresiz gider, HTTPS kurmadan dışarıdan kullanma."
fi

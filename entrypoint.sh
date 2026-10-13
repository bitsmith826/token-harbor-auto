#!/bin/sh
# Entrypoint container Token Harbor Auto.
#
# Tugasnya cuma tiga:
#   1. pastikan .env ada (kalau tidak, kasih pesan jelas lalu keluar)
#   2. pastikan virtual display (Xvfb) hidup kalau headless
#   3. jalankan main.py, teruskan semua argumen (mis. --auto 2 5)
set -e

cd /app

if [ ! -f /app/.env ]; then
    echo "[X] .env tidak ada di dalam container."
    echo "    Isi dulu .env di host (folder yang di-mount), lalu jalankan lagi."
    exit 1
fi

# Xvfb: layar virtual. Camoufox disarankan headless="virtual" di Linux
# supaya fingerprint-nya tidak mencurigakan.
if [ -z "$DISPLAY" ]; then
    export DISPLAY=:99
fi
if ! pgrep -x Xvfb >/dev/null 2>&1; then
    Xvfb "$DISPLAY" -screen 0 1920x1080x24 -nolisten tcp >/tmp/xvfb.log 2>&1 &
    sleep 2
fi

exec python3 main.py "$@"
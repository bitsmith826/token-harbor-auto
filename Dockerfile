# Token Harbor Auto -- image Linux (VPS / Docker)
#
# Basis Ubuntu 22.04 supaya sama dengan VPS. Python 3.10 bawaan Ubuntu,
# cocok dengan requirements.txt (butuh >= 3.10).
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive \
    TZ=Asia/Jakarta \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    LANG=C.UTF-8

# --- 1. paket dasar + dependensi Firefox (Camoufox berbasis Firefox) ---
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 python3-pip python3-dev \
      ca-certificates curl unzip tzdata xvfb \
      libgtk-3-0 libdbus-glib-1-2 libxt6 libasound2 \
      libx11-xcb1 libxcomposite1 libxcursor1 libxdamage1 libxfixes3 \
      libxi6 libxrandr2 libxrender1 libxss1 libxtst6 libxkbcommon0 \
      libgbm1 libegl1 libgl1 libglx-mesa0 libxshmfence1 \
      fonts-liberation fonts-noto-color-emoji fontconfig \
    && ln -fs /usr/share/zoneinfo/$TZ /etc/localtime \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# --- 2. library Python (cache di layer, tidak install ulang tiap run) ---
COPY requirements.txt ./
RUN pip3 install --no-cache-dir -r requirements.txt

# --- 3. browser Camoufox (~500 MB, sekali saat build) ---
# Tersimpan di ~/.cache/camoufox, di-mount volume supaya tidak
# download ulang saat container dibuat lagi.
RUN python3 -m camoufox fetch

# --- 4. kode proyek ---
COPY . .

ENTRYPOINT ["/bin/sh", "/app/entrypoint.sh"]
CMD ["--auto", "2", "5"]
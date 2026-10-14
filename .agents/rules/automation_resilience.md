# Automation Resilience & Proxy Rules

## 1. Proxy Handling & Pacing
1. **Pacing Turnstile & Form**:
   - Selalu beri jeda sebelum klik form pendaftaran (1.2s - 2.5s) agar tidak memicu deteksi bot Cloudflare (*"doing that a bit fast"*).
2. **Reuse Working Proxies**:
   - Proxy yang sukses digunakan pendaftaran wajib dipertahankan untuk pendaftaran akun berikutnya.
   - Jangan ganti proxy selama proxy tersebut masih merespons dengan baik dan belum terkena limit.
3. **Fail-Fast Policy**:
   - Jika proxy mati, connection timeout, atau kena blokir Turnstile (*noform*), segerakan rotasi ke proxy berikutnya.
   - Jangan menunggu lebih dari 45 detik saat submit form; jika tidak ada respon dari Token Harbor dalam 45 detik, anggap timeout dan langsung ganti proxy.
4. **Heartbeat Logging**:
   - Setiap kali melakukan polling atau menunggu respon jaringan yang lebih dari 5 detik, cetak log heartbeat berkala ke konsol agar proses tidak terlihat freeze.

## 2. Upstream & Tunnel Diagnostics
1. **Cloudflare Tunnel Detection**:
   - Sebelum melaporkan form tidak ditemukan pada layanan eksternal (seperti 9Router), selalu periksa kode HTTP dan body text apakah ada Cloudflare Error 530 / 1033 (Argo Tunnel Error), 502, atau 504.
   - Berikan notifikasi yang jelas jika server upstream di VPS sedang offline.

## 3. Decoupled Downstream & Buffer Pattern
1. **Pemisahan Ketergantungan Downstream**:
   - Kegagalan atau status offline pada 9Router TIDAK BOLEH menghentikan proses pembuatan akun baru.
   - Seluruh kredensial dan API key tetap wajib disimpan langsung ke `result.txt` dan `keys.txt` sebagai antrean buffer permanen.
2. **Bulk Re-Import**:
   - Ketika 9Router kembali pulih, seluruh antrean key di `keys.txt` dapat disinkronkan sekaligus via Mode 4 (`import_keys`) tanpa duplikasi.

## 4. Unattended 24/7 Long-Running Operations
1. **Zero Prompt Blocking**:
   - Pada mode background/otomatis (`--auto` atau Docker container), sistem tidak boleh memanggil `input()` yang dapat membekukan container.
2. **Clean Memory Recycling**:
   - Gunakan context manager `with Camoufox(...) as browser:` pada setiap iterasi agar seluruh child process browser ditutup rapat dan memori dibebaskan secara berkala.

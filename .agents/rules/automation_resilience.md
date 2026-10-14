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

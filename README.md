# Token Harbor Auto

Otomasi alur pendaftaran Token Harbor: buat akun, verifikasi email, buat API key,
lalu daftarkan key ke 9Router. Memakai Camoufox (browser anti-detect berbasis
Firefox) dan berjalan headless.

## Tujuan & etika

Proyek ini dibuat untuk **belajar otomasi browser**, dengan mempelajari hal-hal
seperti:

- mengendalikan browser secara programatik (Playwright / Camoufox),
- menangani alur berisi banyak langkah yang bisa gagal di tengah,
- mengelola antrean, retry, dan penyimpanan hasil per item,
- menangani sesi login, cookie, dan proxy dalam skala banyak akun,
- menulis program yang tahan lama berjalan (batch panjang, mode 24/7).

**Yang wajib kamu patuhi:**

- **Patuhi aturan layanan** situs yang kamu pakai. Otomatisasi bisa melanggar
  ToS, dan itu tanggung jawabmu sendiri.
- **Jangan dipakai untuk spam atau penipuan.**
- **Jangan melewati sistem keamanan** yang memang dirancang melindungi layanan
  atau pengguna lain.
- **Jangan membebani server orang lain** dengan permintaan bertubi-tubi.
- **Jaga data.** `result.txt` berisi email dan password, `.env` berisi
  kredensial, `keys.txt` berisi API key. Jangan pernah di-commit ke Git.
  Kalau tidak sengaja ter-upload, segera ganti semua kredensial.

Kode ini disediakan apa adanya, untuk tujuan belajar. Semua risiko pemakaian
ada pada kamu.

## Instalasi

1. Pasang Python 3.10 atau lebih baru dari https://python.org.
   Centang **Add python.exe to PATH** saat memasang.
2. Salin `.env.example` menjadi `.env`, lalu isi nilainya (lihat bagian Konfigurasi).
3. (Opsional) Buat `proxies.txt` kalau mau memakai proxy untuk signup. Satu proxy per baris:

   ```
   host:port
   host:port:username:password
   http://username:password@host:port
   ```

4. Klik dua kali `run.bat`. Pada jalan pertama, library dan browser Camoufox
   diunduh otomatis (sekali saja).

## Pilih mode

Saat `run.bat` berjalan, pilih salah satu mode:

| Mode | Nama | Fungsi |
|------|------|--------|
| 1 | signup | Buat akun, verifikasi email, buat API key. Simpan ke `result.txt` |
| 2 | full | Sama seperti mode 1, lalu daftarkan key ke 9Router |
| 3 | create_key | Login akun dari `result.txt`, buat API key untuk yang belum punya |
| 4 | import_keys | Daftarkan key dari `keys.txt` ke 9Router. Key yang sudah ada dilewati |

Hasil disimpan per akun, jadi kalau proses berhenti, data yang sudah jadi tidak hilang.

## Konfigurasi

Isi `.env`:

| Variabel | Keterangan |
|----------|------------|
| `GMAIL_USER` | Alamat Gmail untuk membaca link verifikasi |
| `GMAIL_APP_PASSWORD` | App Password Gmail (bukan password biasa) |
| `DOMAIN` | Domain email untuk akun baru |
| `HEADLESS` | `true` = browser tidak terlihat. Disarankan untuk jalan di background |
| `ROUTER_URL` | Alamat dashboard 9Router |
| `ROUTER_PASSWORD` | Password dashboard 9Router |
| `TELEGRAM_BOT_TOKEN` | Opsional. Token bot dari @BotFather, untuk notifikasi |
| `TELEGRAM_CHAT_ID` | Opsional. ID grup, mis. `-1001234567890` |
| `TELEGRAM_THREAD_ID` | Opsional. ID topik di dalam grup |
| `TELEGRAM_NOTIF` | Opsional. `true` (default) atau `false` untuk mematikan notifikasi |
| `PROXY` | Opsional. Satu proxy tunggal, kalau tidak pakai `proxies.txt` |

## Fitur Utama & Ketahanan Otomasi

- **Direct REST API Acceleration (Hasil Reverse Engineering REA)**: Pendaftaran API key dan verifikasi koneksi ke 9Router kini diproses langsung melalui REST API internal 9Router (`/api/auth/login`, `/api/providers`, `/api/providers/validate`). Kecepatan input meningkat drastis dari ~45 detik menjadi **kurang dari 1 detik per akun** tanpa membuka browser Camoufox, memangkas penggunaan RAM dan CPU hingga 95%. Mode 4 (`import_keys`) berjalan instan dalam hitungan detik.
- **Multi-Worker Concurrency**: Eksekusi multi-threading (1 sampai 5 worker simultan) yang menjalankan instance browser independen secara paralel. Output akun dan API key meningkat berlipat ganda sesuai jumlah worker.
- **Dedicated Proxy Queue**: Antrean proxy thread-safe eksklusif di mana setiap worker memegang proxy berbeda (mencegah tabrakan IP/rate limit). Jika proxy antrean menipis (< 3), sistem secara otomatis mengunduh & menguji proxy fresh baru di latar belakang (auto-refill).
- **Smart Auto-Scraper & Latency Sorting**: Mengunduh kandidat proxy publik dari 11 sumber aktif, mengujinya secara paralel (60 threads), dan mengurutkannya dari **latensi milidetik tercepat**. Proxy paling kencang otomatis digunakan lebih dulu.
- **Thread-Safe Storage & Logging**: Penulisan ke `result.txt` dan `keys.txt` diproteksi `threading.Lock()` dengan log terminal berlabel jelas per worker (`[W-1]`, `[W-2]`, dst.).
- **Fail-Fast & Balanced Timeout (22s)**: Batas waktu `page.goto` disetel 22 detik dan batas tunggu respon disetel 27 detik, cukup toleran terhadap *jitter* proxy tanpa membuang waktu tunggu lama saat proxy macet.
- **Pacing Turnstile Manusiawi**: Jeda pengetikan manusiawi dan delay pra-submit 3.5 detik untuk memastikan token Cloudflare Turnstile selesai digenerate sebelum form dikirim (mencegah penolakan *"doing that a bit fast"*).
- **Anti-Hydration Wipe**: Memverifikasi nilai `input_value()` form secara berkala agar kredensial tidak terhapus saat JavaScript React/Next.js me-render ulang halaman.
- **Dukungan VPS / Docker 24/7 (Non-Interaktif)**: Dapat dijalankan tanpa prompt terminal menggunakan flag CLI:
  ```bash
  # Mode 1, 100 akun, pakai proxy, 3 worker simultan
  python main.py --auto 1 100 y --worker 3

  # Mode 2, UNLIMITED akun (jalan terus 24/7), 2 worker
  python main.py --auto 2 0 y --worker 2 --loop

  # Mode 4, Import seluruh keys.txt ke 9Router instan via REST API
  python main.py --auto 4
  ```

## Tips Alternatif Proxy (Bila Proxy Publik Sering Limit)

Jika proxy gratisan scraper sering terkena rate limit Cloudflare Turnstile (*"Too many sign-ups from this network"*), gunakan salah satu opsi andal berikut:
1. **USB Tethering / Hotspot HP Android (Sangat Disarankan & Gratis)**:
   - Sambungkan HP ke PC via kabel data (USB Tethering).
   - Jaringan seluler (Telkomsel/Indosat/XL) menggunakan CGNAT dengan reputasi residential yang sangat tinggi (jarang sekali diblokir Turnstile).
   - Untuk mengganti IP publik secara instan: cukup aktifkan lalu matikan Mode Pesawat di HP (bisa otomatis via ADB).
2. **Rotating Residential Proxy Berbayar Murah**:
   - Gunakan layanan proxy residential (seperti Webshare, IPRoyal, dsb.).
   - Masukkan proxy format `host:port:username:password` ke [proxies.txt](file:///d:/Coding/token-harbor-auto/proxies.txt).
3. **Pacing IP Asli (Tanpa Proxy)**:
   - Jika kebutuhan akun tidak ratusan sekaligus, jalankan dengan IP asli menggunakan delay jeda wajar antar batch.

## Perilaku saat kena limit

- **Too many sign-ups (mode 1 & 2):** buang proxy tersebut, worker mengambil proxy berikutnya dari queue.
  Jika antrean proxy menipis, bot otomatis me-refill proxy fresh baru dari internet.
- **Cloudflare sibuk / fast ("doing that a bit fast"):** toleransi jeda 18 detik (maks 2x retry) sebelum rotasi ke proxy berikutnya.
- **Proxy mati / timeout:** langsung beralih ke proxy berikutnya dalam 22 detik.
- **Too many attempts saat login (mode 3):** tunggu 30 detik, lalu coba lagi di akun yang sama.
- **Error jaringan / batas retry tercapai:** akun dilewati (tidak disimpan jika belum jadi), worker lanjut ke akun berikutnya.

## File

| File | Isi | Dibuat oleh |
|------|-----|-------------|
| `result.txt` | `email\|password\|key` | mode 1, 2, 3 |
| `keys.txt` | `email\|key` | mode 1, 2, 3 |
| `proxies.txt` | Daftar proxy | Kamu |
| `session_9router.json` | Sesi login 9Router | otomatis |

File berikut berisi data rahasia dan sudah dikecualikan di `.gitignore`.
Jangan di-upload ke GitHub: `.env`, `proxies.txt`, `keys.txt`, `result.txt`, `session_9router.json`.

## Notifikasi Telegram (opsional)

Kalau empat variabel `TELEGRAM_*` di `.env` diisi, program mengirim pesan singkat
ke grup/topik setiap ada hasil:

```
OK  API KEY BERHASIL (mode 1)
    nama@domain
    Total: 100 akun

OK  INPUT 9ROUTER SUKSES
    nama@domain
    Total: 100 akun
```

Kalau variabelnya kosong, notifikasi dilewati dan program tetap jalan normal.

Cara mendapat nilainya:
- `TELEGRAM_BOT_TOKEN` — buat bot lewat @BotFather, salin tokennya.
- `TELEGRAM_CHAT_ID` — ID grup, angkanya di depan diberi `-100`. Contoh link
  `t.me/c/1234567890/42` menjadi `-1001234567890`.
- `TELEGRAM_THREAD_ID` — angka setelah garis miring di link topik (`42`).
- Bot harus sudah jadi anggota grup dan punya izin mengirim pesan.

## Bagaimana cara kerjanya

Contoh mode 2 (`full`), satu akun:

1. **Signup lewat proxy** (kalau ada `proxies.txt`). Browser baru per akun, jadi
   IP-nya berganti.
2. **Sampai dashboard** Token Harbor, lalu **isi link verifikasi** yang dibaca
   otomatis dari inbox Gmail.
3. **Buat API key** di halaman dashboard.
4. **Verifikasi ulang lewat API** (`pastikan_verified`) — halaman web bisa
   memberi hasil palsu, jadi status dipastikan lewat API sebelum lanjut.
5. **Kirim key ke 9Router** (masih di dalam browser yang sama, IP asli).
6. **Simpan** ke `result.txt` dan `keys.txt` **per akun**, lalu kirim notifikasi
   Telegram kalau aktif.

Poin penting:

- **Login selalu IP asli**, proxy hanya untuk signup.
- **Key selalu disimpan** walau langkah 9Router gagal. Key sudah dibuat di
  Token Harbor; kalau dibuang harus login dan buat ulang. Yang gagal masuk
  bisa diulang pakai mode 4.
- **Satu akun gagal tidak menghentikan batch.** Error jaringan, verifikasi
  gagal, atau key gagal dibuat hanya melewati akun itu.

## Struktur kode

Ringkas isi tiap file, biar mudah dibaca kalau mau belajar atau mengubah:

| File | Isi utama |
|------|-----------|
| `main.py` | Menu, `mode_signup_full`, `mode_create_key`, `mode_import_keys`, `main_otomatis` (argumen `--auto`) |
| `signup.py` | `gen_email`, `gen_password`, `_jalankan_signup`, `_proses_verifikasi`, `buat_api_key`, `pastikan_verified`, `test_key_api` |
| `router9.py` | `login_router`, `daftar_koneksi`, `_buka_provider`, `tambah_api_key`, `proses_router9` |
| `gmail_inbox.py` | `cari_link_verifikasi` — baca inbox Gmail lewat IMAP, cocokkan header `To` |
| `tampilan.py` | `log`, `judul`, `bagian`, `rinci` — output berwarna dengan badge |
| `notif.py` | `kirim`, `sukses_key`, `sukses_9router` — notifikasi Telegram |
| `run.bat` | Pemasang otomatis dan launcher (Windows), memanggil `main.py` |

## Konsep yang dipakai

Kalau kamu baru belajar otomasi browser, ini istilah yang sering muncul di kode:

- **Headless browser** — browser tanpa jendela. Dipakai supaya proses jalan di
  background dan tidak mengganggu layar. Di `.env`, `HEADLESS=true`.
- **Camoufox** — browser anti-detect berbasis Firefox. Dipakai supaya sidik jari
  browser tidak mudah dikenali sebagai bot. Di VPS ia jalan di dalam Xvfb
  (layar virtual), dan berjalan sebagai `virtual` (lebih sulit dideteksi
  daripada headless murni).
- **Proxy** — jalur perantara saat signup, supaya IP berganti tiap akun. Login
  tetap dari IP asli.
- **Storage state** — file berisi cookie dan sesi login (`session_9router.json`),
  supaya tidak perlu login ulang tiap kali program dijalankan.
- **Retry & skip** — tiap langkah punya batas percobaan. Kalau tetap gagal,
  akun itu dilewati dan batch lanjut. Ini yang membuat batch panjang tidak
  mudah berhenti di tengah.
- **Idempotent** — mode 3 dan 4 aman dijalankan berulang. Yang sudah punya key
  atau sudah ada di 9Router akan dilewati, bukan diduplikasi.

## Tips pakai

- **Cek dulu sebelum batch besar.** Jalankan mode 1 dengan 1 akun untuk
  memastikan `.env` dan proxy benar.
- **Jangan hapus `keys.txt`.** Itu sumber utama mode 4. Kalau hilang, key yang
  sudah dibuat di Token Harbor tidak bisa didaftarkan ulang tanpa login.
- **Simpan `result.txt` di tempat aman.** Isinya email dan password akun.
- **Batasi jumlah per putaran** kalau proxy terbatas. Lebih baik 5 akun per
  putaran yang lancar daripada 50 yang kena limit.
- **Lihat log, bukan hanya hasil akhir.** Baris `WARN` sering menjelaskan
  kenapa sebuah akun dilewati.

## Jalan 24/7 di VPS (Docker)

Cocok untuk Ubuntu 22.04. Semua data (`keys.txt`, `result.txt`, session) di-mount
dari folder host, jadi tidak hilang walau container dibuat ulang.

### Pasang

```bash
cd /opt
git clone <url-repo> token-harbor    # atau unzip
cd token-harbor

# siapkan kredensial
cp .env.example .env
nano .env                            # isi GMAIL_*, ROUTER_*, DOMAIN
nano proxies.txt                     # daftar proxy untuk signup

docker compose build                 # sekali saja, download Camoufox ~500MB
```

### Jalankan

Mode interaktif (pilih menu seperti biasa):

```bash
docker compose run --rm th-auto
```

Mode otomatis tanpa prompt (untuk 24/7):

```bash
docker compose run --rm th-auto --auto 2 5
```

Artinya: mode `2` (full), `5` akun. Argumennya:

| Argumen | Arti |
|---------|------|
| `--auto 2 5` | mode 2, pakai proxy, 5 akun |
| `--auto 2 5 n` | mode 2, **tanpa** proxy, 5 akun |
| `--auto 3` | mode 3 (create key), 5 akun |
| `--auto 4` | mode 4 (import ke 9Router) |
| `--auto 1 5 --loop` | mode 1, 5 akun, lalu **ulang terus tanpa henti** |

Kalau argumen tidak diberi, program jalan seperti biasa (menu + prompt). `.env`
tidak pernah diubah oleh argumen.

### Auto restart & tahan reboot VPS

`docker-compose.yml` memakai `restart: unless-stopped` dan `command: ["--auto", "1", "5", "--loop"]`,
jadi berjalan 24/7 tanpa henti:

- `--loop` -> tiap 5 akun selesai, langsung mulai putaran berikutnya.
- Proses **crash / error** -> container dinyalakan ulang sendiri.
- **VPS reboot** -> Docker daemon menyalakan ulang container otomatis.
- Berhenti hanya kalau kamu jalankan `docker compose down` sendiri.

Perintah harian:

```bash
docker compose up -d                 # jalan di belakang, 24/7
docker compose logs -f               # lihat log langsung
docker compose down                  # hentikan (sengaja)
```

### Jangan merusak container lain di VPS

Project ini tidak membuka port, tidak memakai network milik project lain, dan
punya nama volume sendiri. Tetap ikuti aturan ini:

- Jangan jalankan `docker system prune`, `docker volume prune`, atau `docker image prune -a`.
- Jangan pakai `docker compose down -v` di folder project lain (`-v` menghapus volume).
- Jangan pakai `--remove-orphans` pada compose project lain.

## Windows tetap jalan seperti biasa

Windows tetap memakai `run.bat` seperti biasa. `OS_FP` di `signup.py` otomatis
mengikuti OS yang dipakai (Windows atau Linux), jadi kode yang sama jalan di dua tempat.

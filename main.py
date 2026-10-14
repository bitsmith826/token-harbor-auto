#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
main.py - Token Harbor Auto (4 MODE)

  1. signup        : signup -> enable free model -> verify email -> CREATE API KEY
  2. full          : signup -> ... -> create api key -> INPUT ke 9ROUTER
  3. create_key    : login akun lama (result.txt) -> CREATE API KEY
  4. import_keys   : input key dari keys.txt ke 9ROUTER saja

Mode 1 & 2 bisa pilih PROXY atau IP ASLI.
  - Proxy dipakai HANYA untuk step signup. Setelah itu browser proxy ditutup,
    step berikutnya (enable model, verify email, create key, input 9Router)
    pakai IP asli.
  - Proxy habis / belum dipakai, kena "Too many sign-ups ... try again in an
    hour" -> tunggu 1 jam lalu coba lagi. Tidak crash, batch lanjut.
  - Mode 3: login kena "too many attempts" -> tunggu 1 jam, coba lagi.

FILE:
  - proxies.txt : daftar proxy (mode 1 & 2, kalau pilih proxy)
  - result.txt  : email|password|key  (output mode 1 & 2, LANGSUNG per akun)
  - keys.txt    : email|key           (input mode 4)
"""

import os
import sys
import time
from pathlib import Path

import signup
import router9
import tampilan
import notif

HERE = Path(__file__).resolve().parent
RESULT_TXT = HERE / "result.txt"
KEYS_TXT = HERE / "keys.txt"


def _ambil_camoufox():
    """Import Camoufox secara on-demand agar menu startup instan."""
    from camoufox.sync_api import Camoufox
    return Camoufox


# ----------------------------------------------------------------------
# TAMPILAN
# ----------------------------------------------------------------------

CYN = "\033[96m"
GRN = "\033[92m"
YEL = "\033[93m"
RST = "\033[0m"
BOLD = "\033[1m"


def _bersihkan_layar():
    # Di container / pipe tidak ada TTY: jangan kirim escape 'clear',
    # supaya docker logs tetap bersih.
    if not sys.stdout.isatty():
        return
    os.system("cls" if os.name == "nt" else "clear")


def _header():
    _bersihkan_layar()
    tampilan.aktifkan_warna()
    tampilan.judul("TOKEN HARBOR AUTO  -  9Router", "Otomasi Akun, API Key & Input 9Router")
    tampilan.tampilkan_info_ip()
    print(f"{tampilan.BOLD}PILIH MODE EKSEKUSI:{tampilan.RST}")
    print(f"  {tampilan.CYN}[1]{tampilan.RST} {tampilan.BOLD}signup{tampilan.RST}       - buat akun baru + create API key")
    print(f"  {tampilan.CYN}[2]{tampilan.RST} {tampilan.BOLD}full{tampilan.RST}         - buat akun + create API key + input ke 9Router")
    print(f"  {tampilan.CYN}[3]{tampilan.RST} {tampilan.BOLD}create_key{tampilan.RST}   - login akun lama (result.txt) + create API key")
    print(f"  {tampilan.CYN}[4]{tampilan.RST} {tampilan.BOLD}import_keys{tampilan.RST}  - input API key dari keys.txt ke 9Router")
    print()


def pilih_mode():
    _header()
    while True:
        jawab = input(f"{BOLD}Pilih mode (1/2/3/4){RST} [default 2]: ").strip()
        if not jawab:
            return "full"
        peta = {"1": "signup", "2": "full", "3": "create_key", "4": "import_keys"}
        if jawab in peta:
            return peta[jawab]
        print(f"{YEL}Pilihan tidak dikenal: {jawab}{RST}")


def pilih_proxy():
    """Return True kalau user mau pakai proxy untuk signup."""
    while True:
        jawab = input(f"{BOLD}Pakai proxy untuk signup? (y/n){RST} [default n]: ").strip().lower()
        if not jawab or jawab == "n":
            return False
        if jawab == "y":
            return True
        print(f"{YEL}Jawab y atau n.{RST}")


def _tanya_jumlah(label):
    """Tanya berapa akun yg diproses. Return int > 0 atau 999999 untuk unlimited."""
    while True:
        jawab = input(f"{BOLD}{label}{RST} [default 1, ketik 0 untuk unlimited]: ").strip().lower()
        if not jawab:
            return 1
        if jawab in ("0", "u", "unlimited", "loop"):
            return 999999
        try:
            n = int(jawab)
            if n > 0:
                return n
        except ValueError:
            pass
        print(f"{YEL}Masukkan angka lebih dari 0, atau ketik 0 untuk unlimited.{RST}")


# ----------------------------------------------------------------------
# SIMPAN HASIL
# ----------------------------------------------------------------------

def simpan_result(email, password, key=None):
    """Tulis hasil ke result.txt (UPSERT: email sudah ada -> update, bukan append).

    Format: email|password|key (key opsional).
    Ditulis LANGSUNG per akun, gak nunggu semua selesai.
    """
    try:
        baris = f"{email}|{password}"
        if key:
            baris += f"|{key}"

        # baca semua baris, ganti baris email yg sama (upsert)
        lama = []
        if RESULT_TXT.exists():
            with open(RESULT_TXT, encoding="utf-8") as f:
                lama = [b.rstrip("\r\n") for b in f if b.strip()]

        ada = False
        for i, b in enumerate(lama):
            if b.split("|")[0] == email:
                # update: pakai key baru kalau ada, kalau gak ada keep key lama
                if key or b.count("|") < 2:
                    lama[i] = baris
                ada = True
                break
        if not ada:
            lama.append(baris)

        with open(RESULT_TXT, "w", encoding="utf-8") as f:
            f.write("\n".join(lama) + "\n")
        signup.log(f"Disimpan ke result.txt: {email}", "OK")

        # key ada -> tulis ke keys.txt juga (sekali per email)
        if key:
            _simpan_keys(email, key)
    except Exception as e:
        signup.log(f"Gagal simpan result.txt: {e}", "WARN")


def _simpan_keys(email, key):
    """Tulis email|key ke keys.txt (upsert)."""
    try:
        lama = []
        if KEYS_TXT.exists():
            with open(KEYS_TXT, encoding="utf-8") as f:
                lama = [b.rstrip("\r\n") for b in f if b.strip()]
        if any(b.split("|")[0] == email for b in lama):
            return  # sudah ada
        with open(KEYS_TXT, "a", encoding="utf-8") as f:
            f.write(f"{email}|{key}\n")
        signup.log(f"Disimpan ke keys.txt: {email}", "OK")
    except Exception as e:
        signup.log(f"Gagal simpan keys.txt: {e}", "WARN")


def baca_empas():
    """Baca result.txt -> list (email, password). Skip baris tanpa '|'."""
    if not RESULT_TXT.exists():
        return []
    out = []
    with open(RESULT_TXT, encoding="utf-8") as f:
        for baris in f:
            baris = baris.rstrip("\r\n")
            if not baris or "|" not in baris:
                continue
            bagian = baris.split("|")
            email, password = bagian[0].strip(), bagian[1].strip()
            if email and password:
                out.append((email, password))
    return out


def baca_keys():
    """Baca keys.txt -> list (email, key). Format: email|key."""
    if not KEYS_TXT.exists():
        return []
    out = []
    with open(KEYS_TXT, encoding="utf-8") as f:
        for baris in f:
            baris = baris.rstrip("\r\n")
            if not baris or "|" not in baris:
                continue
            bagian = baris.split("|", 1)
            email, key = bagian[0].strip(), bagian[1].strip()
            if email and key:
                out.append((email, key))
    return out


# ----------------------------------------------------------------------
# MODE 1 & 2: signup (+ input 9Router untuk mode full)
# ----------------------------------------------------------------------

def mode_signup_full(mode, pakai_proxy, jumlah_override=None):
    """Mode 1 (signup) & 2 (full). Perbedaan: mode 2 lanjut input 9Router.

    jumlah_override: kalau diisi (mode --auto), jangan tanya lagi.
    """
    if jumlah_override and jumlah_override > 0:
        jumlah = int(jumlah_override)
    else:
        jumlah = _tanya_jumlah("Berapa akun?")

    proxies = signup._baca_proxies() if pakai_proxy else []
    if pakai_proxy:
        if not proxies:
            signup.log("proxies.txt kosong -> otomatis mencari proxy fresh dari internet...", "WARN")
            proxies = signup.ambil_proxy_fresh_otomatis(target=20)
        elif not jumlah_override:
            try:
                tanya_fresh = input(f"{tampilan.CYN}Ambil proxy fresh baru otomatis dari internet? (y/n) [default n]: {tampilan.RST}").strip().lower()
                if tanya_fresh == "y":
                    proxies = signup.ambil_proxy_fresh_otomatis(target=20)
            except (EOFError, KeyboardInterrupt):
                pass
        if not proxies:
            signup.log("Tidak ada proxy tersedia -> signup pakai IP asli", "WARN")
            pakai_proxy = False

    headless = signup.HEADLESS_BROWSER
    Camoufox = _ambil_camoufox()
    MAX_RETRY = 5
    sukses = 0
    global_proxy_idx = 0
    max_percobaan = max(MAX_RETRY, len(proxies)) if (pakai_proxy and proxies) else MAX_RETRY

    for i in range(jumlah):
        label_total = "∞" if jumlah >= 999999 else str(jumlah)
        tampilan.bagian(f"AKUN {i + 1}/{label_total}")

        email = signup.gen_email()
        password = signup.gen_password()
        ip_info = tampilan.cek_ip_publik()
        ip_asli = ip_info.get("ipv4") or "Tidak terdeteksi"
        warp_tag = " [WARP Shared]" if ip_info.get("is_warp") else ""

        # Tentukan label jalur untuk kartu akun
        if pakai_proxy and proxies:
            p_awal = signup._parse_proxy(proxies[global_proxy_idx % len(proxies)])
            p_host = p_awal.get("server", "").replace("http://", "").replace("https://", "")
            jalur_info = f"Proxy ({p_host})"
        else:
            jalur_info = f"IP Asli ({ip_asli}{warp_tag})"

        tampilan.rinci("Email", email)
        tampilan.rinci("Password", password)
        tampilan.rinci("Jalur / IP", jalur_info)

        # ---- FASE 1: SIGNUP (browser terpisah, bisa pakai proxy) ----
        status_signup = "gagal"
        for percobaan in range(1, max_percobaan + 1):
            if percobaan > 1:
                email = signup.gen_email()
                password = signup.gen_password()
                signup.log(f"Email & password baru: {email}", "INFO")

            launch = {"headless": headless, "humanize": True,
                      "os": signup.OS_FP, "locale": ["id-ID"], "geoip": True}
            label_ip = f"IP Asli ({ip_asli})"
            if pakai_proxy:
                if not proxies or global_proxy_idx >= len(proxies):
                    signup.log("Proxy di daftar habis -> otomatis fetch proxy fresh baru dari internet...", "STEP")
                    proxies = signup.ambil_proxy_fresh_otomatis(target=20)
                    global_proxy_idx = 0
                if proxies:
                    proxy_str = proxies[global_proxy_idx]
                    p_dict = signup._parse_proxy(proxy_str)
                    launch["proxy"] = p_dict
                    p_clean = p_dict.get("server", "").replace("http://", "").replace("https://", "")
                    label_ip = f"Proxy ({p_clean}) [#{global_proxy_idx + 1}/{len(proxies)}]"
            signup.log(f"Signup via: {label_ip} (coba {percobaan})", "STEP")

            try:
                with Camoufox(**launch) as browser:
                    page = browser.new_page()
                    timeout_signup = 35_000 if (pakai_proxy and proxies) else 60_000
                    page.set_default_timeout(timeout_signup)
                    page.set_default_navigation_timeout(timeout_signup)
                    status_signup = signup._jalankan_signup(page, email, password)
            except Exception as e:
                # NS_ERROR_NET_TIMEOUT / browser crash / proxy mati
                signup.log(f"Proxy/koneksi bermasalah: {e}", "WARN")
                status_signup = "network_error"

            if status_signup == "dashboard":
                # Sukses: tetap gunakan proxy ini untuk akun berikutnya (jangan ganti sampai limit/mati)
                break

            if status_signup == "network_hour":
                # "Too many sign-ups ... try again in an hour"
                signup.log(f"Rate limit (too many sign-ups) terdeteksi pada {label_ip}", "LIMIT")
                if pakai_proxy and proxies:
                    global_proxy_idx += 1
                    signup.log("Proxy limit (too many sign-ups) -> beralih ke proxy berikutnya...", "WARN")
                    time.sleep(2)
                    continue
                signup.log("Pakai IP asli -> mulai jeda cooldown 1 jam...", "LIMIT")
                tampilan.tunggu(3600, "Cooldown IP Rate-Limit")
                continue

            if status_signup == "network_error":
                # Proxy mati / connection timeout / connection refused
                if pakai_proxy and proxies:
                    global_proxy_idx += 1
                    signup.log(f"Proxy mati/terputus -> beralih ke proxy berikutnya...", "WARN")
                    time.sleep(2)
                    continue

            if status_signup == "network_minute":
                signup.log("Server Cloudflare sibuk -> jeda cooldown 90 detik...", "LIMIT")
                tampilan.tunggu(90, "Jeda keamanan server")
                continue

            signup.log(f"Signup gagal ({status_signup})", "WARN")
            continue

        if status_signup != "dashboard":
            # signup gagal total -> akun gak ada, JANGAN disimpan
            signup.log(f"Signup gagal setelah {max_percobaan} percobaan -> "
                       "lanjut akun berikutnya (TIDAK disimpan)", "ERROR")
            continue

        signup.log("Signup sukses -> lanjut IP asli", "OK")

        # ---- FASE 2: ENABLE + VERIFY + CREATE KEY (IP asli) ----
        key = None
        router_ok = True
        try:
            with Camoufox(headless=headless, humanize=True, os=signup.OS_FP,
                          locale=["id-ID"], geoip=True) as browser:
                page = browser.new_page()
                page.set_default_timeout(90_000)
                page.set_default_navigation_timeout(90_000)

                ok = signup._proses_verifikasi(page, email, password)
                if not ok:
                    signup.log("Verifikasi email gagal (akun tetap tersimpan)",
                               "WARN")
                    simpan_result(email, password)
                    continue

                key = signup.buat_api_key(page, email)
                if not key:
                    signup.log("Create API key gagal", "ERROR")
                    simpan_result(email, password)
                    continue

                # safety net: pastikan email bener-bener verified di API.
                # (verifikasi fase 1 bisa false-positive; cek langsung API).
                if not signup.pastikan_verified(page, email, key,
                                                log=signup.log):
                    signup.log(f"Email {email} belum terverifikasi -> "
                               "simpan tanpa input 9Router", "WARN")
                    simpan_result(email, password)
                    continue

                # ---- MODE FULL: INPUT ke 9ROUTER (masih IP asli) ----
                # WAJIB di dalam with Camoufox -- kalau di luar, browser sudah
                # tertutup -> "Event loop is closed".
                if mode == "full":
                    if not signup._proses_router9(page, email, key):
                        signup.log("Input 9Router gagal", "ERROR")
                        router_ok = False
                    else:
                        signup.log("Input 9Router sukses", "OK")
                        notif.sukses_9router(email)
        except Exception as e:
            # error di fase 2 jangan bunuh batch 100 akun.
            signup.log(f"Error fase 2 (verify/key/9Router): {e}", "ERROR")
            router_ok = False

        # key SELALU disimpan walau 9Router gagal -- key-nya sudah dibuat di
        # Token Harbor; kalau dibuang harus login & buat ulang. Key yg gagal
        # masuk 9Router tinggal di-reimport pakai mode 4 (deteksi duplikat).
        if key:
            simpan_result(email, password, key)
            notif.sukses_key(email, "1" if mode != "full" else "2")
        else:
            simpan_result(email, password)
        sukses += 1

    tampilan.ringkasan({
        "Mode": mode.upper(),
        "Total Target": jumlah,
        "Sukses Key": sukses,
        "Gagal / Skip": jumlah - sukses,
        "Status Akhir": "OK" if sukses == jumlah else ("SEBAGIAN" if sukses > 0 else "GAGAL")
    }, "HASIL BATCH TOKEN HARBOR")
    tampilan.log("Semua proses selesai. Hasil tersimpan di result.txt", "OK")
    return 0 if sukses else 1


# ----------------------------------------------------------------------
# MODE 3: create_key (login akun lama)
# ----------------------------------------------------------------------

def mode_create_key():
    """Login pake email|password dari result.txt, lalu create API key.

    Bedain:
      - kredensial SALAH -> skip permanen (akun gak bisa dipakai)
      - gagal network/Turnstile -> skip, bisa diulang nanti
    """
    empas = baca_empas()
    if not empas:
        signup.log("result.txt kosong / tidak ada. Jalankan mode 1 dulu.", "ERROR")
        return 1

    # deteksi: skip akun yg SUDAH punya API key (ada di keys.txt).
    sudah_punya = {e for e, _ in baca_keys()}
    if sudah_punya:
        before = len(empas)
        empas = [(e, p) for e, p in empas if e not in sudah_punya]
        signup.log(f"Skip {before - len(empas)} akun yg sudah punya API key "
                   f"(ada di keys.txt)", "OK")
    if not empas:
        signup.log("Semua akun sudah punya API key. Tidak ada yg perlu dibuat.",
                   "OK")
        return 0

    signup.log(f"Ditemukan {len(empas)} akun di result.txt")
    jumlah = _tanya_jumlah(f"Berapa akun (max {len(empas)})?")
    jumlah = min(jumlah, len(empas))

    headless = signup.HEADLESS_BROWSER
    Camoufox = _ambil_camoufox()
    sukses = 0
    salah_pw = []
    gagal_network = []

    for i in range(jumlah):
        email, password = empas[i]
        tampilan.bagian(f"AKUN {i + 1}/{jumlah}  -  {email}")

        try:
            with Camoufox(headless=headless, humanize=True, os=signup.OS_FP,
                          locale=["id-ID"], geoip=True) as browser:
                page = browser.new_page()
                page.set_default_timeout(90_000)
                page.set_default_navigation_timeout(90_000)

                status_login = signup.login_dashboard(page, email, password)
                if status_login == "rate_limit":
                    # login kena 'too many attempts' -> tunggu 1 jam, lalu
                    # coba lagi di akun yg sama. Tanpa crash.
                    for percobaan in range(2, 4):
                        signup.log("Login rate-limit -> tunggu 1 jam "
                                   f"(coba {percobaan}/3)", "WARN")
                        time.sleep(3600)
                        try:
                            page.goto(signup.LOGIN_URL,
                                      wait_until="domcontentloaded")
                        except Exception:
                            pass
                        status_login = signup.login_dashboard(page, email,
                                                              password)
                        if status_login == "ok":
                            break
                if status_login != "ok":
                    if status_login == "salah_pw":
                        signup.log(f"Kredensial SALAH -> skip permanen: {email}",
                                   "ERROR")
                        salah_pw.append(email)
                    else:
                        signup.log(f"Gagal login (network/Turnstile): {email}",
                                   "WARN")
                        gagal_network.append(email)
                    continue

                # pastikan free models aktif (akun lama mungkin belum)
                signup._enable_free_models(page)

                key = signup.buat_api_key(page, email)
                if not key:
                    signup.log("Create API key gagal", "ERROR")
                    continue

                # CEK: email sudah verified atau belum? Kalau belum,
                # verifikasi sekarang juga (klik Verify + buka link Gmail).
                signup.pastikan_verified(page, email, key, log=signup.log)

                simpan_result(email, password, key)
                sukses += 1
        except Exception as e:
            signup.log(f"Error tak terduga: {e}", "ERROR")
            gagal_network.append(email)

    tampilan.ringkasan({
        "Mode": "CREATE_KEY",
        "Total Akun": jumlah,
        "Sukses Key": sukses,
        "Gagal PW": len(salah_pw),
        "Gagal Network": len(gagal_network),
        "Status Akhir": "OK" if sukses == jumlah else ("SEBAGIAN" if sukses > 0 else "GAGAL")
    }, "HASIL BATCH CREATE KEY")
    tampilan.log("Semua proses selesai. Hasil tersimpan di result.txt", "OK")
    return 0 if sukses else 1


# ----------------------------------------------------------------------
# MODE 4: import_keys
# ----------------------------------------------------------------------

def mode_import_keys():
    """Input key dari keys.txt ke 9Router saja."""
    keys = baca_keys()
    if not keys:
        signup.log("keys.txt kosong / tidak ada.", "ERROR")
        return 1

    signup.log(f"Ditemukan {len(keys)} key di keys.txt")

    Camoufox = _ambil_camoufox()
    with Camoufox(headless=signup.HEADLESS_BROWSER, humanize=True,
                  os=signup.OS_FP,
                  locale=["id-ID"], geoip=True) as browser:
        ctx_state = None
        if router9.SESSION_FILE.exists():
            ctx_state = browser.new_context(
                storage_state=str(router9.SESSION_FILE))
        else:
            ctx_state = browser.new_context()
        page = ctx_state.new_page()
        page.set_default_timeout(60_000)
        page.set_default_navigation_timeout(60_000)

        # login 9Router kalau perlu
        if not router9._sudah_login(page):
            try:
                if not router9.login_router(page):
                    signup.log("GAGAL LOGIN 9ROUTER", "ERROR")
                    return 1
            except Exception as e:
                signup.log(f"Error login 9ROUTER: {e}", "ERROR")
                return 1

        # deteksi duplikat: baca semua koneksi yg sudah ada di 9Router sekali
        signup.log("Membaca daftar koneksi di 9Router (deteksi anti-duplikat)...")
        try:
            sudah_ada = router9.daftar_koneksi(page)
        except Exception as e:
            signup.log(f"Gagal baca daftar koneksi: {e} -> anggap kosong",
                       "WARN")
            sudah_ada = set()
        signup.log(f"Ditemukan {len(sudah_ada)} koneksi Token Harbor sudah aktif di 9Router")
        if not router9._sudah_login(page):
            try:
                if not router9.login_router(page):
                    signup.log("GAGAL LOGIN 9ROUTER setelah baca koneksi",
                               "ERROR")
                    return 1
            except Exception as e:
                signup.log(f"Error login 9Router: {e}", "ERROR")
                return 1

        # Pastikan browser sudah berada di halaman detail provider Token Harbor sekali di awal
        if not router9._buka_provider(page):
            signup.log("Gagal membuka halaman detail provider Token Harbor", "ERROR")
            return 1

        # Dedup internal keys.txt sendiri jika ada email kembar di dalam file
        keys_unik = []
        dilihat = set()
        for em, k in keys:
            if em not in dilihat:
                dilihat.add(em)
                keys_unik.append((em, k))

        # Pisahkan key yang sudah ada vs belum ada di 9Router
        belum_ada = []
        skip_duplikat = 0
        for em, k in keys_unik:
            if em in sudah_ada:
                skip_duplikat += 1
            else:
                belum_ada.append((em, k))

        if skip_duplikat > 0:
            signup.log(f"{skip_duplikat} key sudah terdaftar di 9Router -> dilewati (anti duplikat)", "OK")

        if not belum_ada:
            signup.log("Semua key sudah tersimpan di 9Router! Tidak ada key baru yang perlu diinput.", "OK")
            router9._simpan_session(page)
            ctx_state.close()
            tampilan.ringkasan({
                "Mode": "IMPORT_KEYS",
                "Total Key": len(keys),
                "Key Unik": len(keys_unik),
                "Sudah Terdaftar": skip_duplikat,
                "Baru Diinput": 0,
                "Status Akhir": "OK"
            }, "HASIL BATCH IMPORT KEYS")
            return 0

        signup.log(f"Mulai input {len(belum_ada)} key baru ke 9Router...", "STEP")

        sukses = 0
        gagal = 0
        for pos, (email, key) in enumerate(belum_ada, 1):
            tampilan.bagian(f"KEY {pos}/{len(belum_ada)}  -  {email}")
            tampilan.rinci("key", f"{key[:14]}...  ({len(key)} char)")

            try:
                status = router9.tambah_api_key(page, email, key)
            except Exception as e:
                signup.log(f"Error input {email}: {e}", "ERROR")
                status = "error"

            if status in ("tersimpan", "sudah_ada"):
                sukses += 1
                sudah_ada.add(email)
            else:
                gagal += 1
                signup.log(f"Gagal input {email}: {status}", "ERROR")

        router9._simpan_session(page)
        ctx_state.close()

    tampilan.ringkasan({
        "Mode": "IMPORT_KEYS",
        "Total Key": len(keys),
        "Key Unik": len(keys_unik),
        "Sudah Terdaftar": skip_duplikat,
        "Sukses Baru": sukses,
        "Gagal Baru": gagal,
        "Status Akhir": "OK" if gagal == 0 else ("SEBAGIAN" if sukses > 0 else "GAGAL")
    }, "HASIL BATCH IMPORT KEYS")
    tampilan.log("Semua proses selesai. Key tersimpan di 9Router", "OK")
    return 0 if gagal == 0 else 1


# ----------------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------------

def _cek_konfigurasi(mode):
    """Cek .env sebelum mode jalan. Return True kalau siap.

    Gagal di awal lebih baik daripada gagal di tengah batch.
    """
    signup._muat_env()
    wajib = []
    if mode in ("signup", "full", "create_key"):
        if not os.environ.get("GMAIL_USER"):
            wajib.append("GMAIL_USER")
        if not os.environ.get("GMAIL_APP_PASSWORD"):
            wajib.append("GMAIL_APP_PASSWORD")
    if mode in ("full", "import_keys"):
        if not os.environ.get("ROUTER_PASSWORD"):
            wajib.append("ROUTER_PASSWORD")

    if not wajib:
        return True

    signup.log("Konfigurasi .env belum lengkap:", "ERROR")
    for kunci in wajib:
        signup.log(f"  - {kunci} kosong", "ERROR")
    signup.log("Isi file .env (salin dari .env.example), lalu jalankan ulang.",
               "WARN")
    return False


def main():
    mode = pilih_mode()

    if not _cek_konfigurasi(mode):
        return 1

    if mode in ("signup", "full"):
        pakai_proxy = pilih_proxy()
        return mode_signup_full(mode, pakai_proxy)

    if mode == "create_key":
        return mode_create_key()

    if mode == "import_keys":
        return mode_import_keys()

    return 1


# ----------------------------------------------------------------------
# MODE OTOMATIS (untuk Docker / VPS / cron -- tanpa prompt)
# ----------------------------------------------------------------------

def main_otomatis(mode, pakai_proxy, jumlah, ulang=False):
    """Jalur non-interaktif: mode diambil dari argumen command-line.

    Dipakai container Docker / VPS supaya bisa jalan 24/7 tanpa ada orang
    mengetik di layar. .env TIDAK ditambah variabel baru.

    Contoh:
        python main.py --auto 1 5            -> mode 1, 5 akun, lalu berhenti
        python main.py --auto 1 5 --loop     -> mode 1, 5 akun, ULANG TERUS
        python main.py --auto 2 5            -> mode 2, pakai proxy, 5 akun
        python main.py --auto 3              -> mode 3, tanpa proxy, 5 akun

    ulang=True: tiap putaran selesai, langsung mulai putaran berikutnya
    dengan akun baru, tanpa henti. Berhenti hanya kalau dihentikan manual
    (docker compose down / Ctrl+C / kill).
    """
    signup._muat_env()
    tampilan.aktifkan_warna()

    peta = {"1": "signup", "2": "full", "3": "create_key", "4": "import_keys"}
    nama_mode = peta.get(mode, mode)

    if nama_mode in ("signup", "full"):
        if pakai_proxy and not signup._baca_proxies():
            signup.log("proxies.txt kosong -> otomatis fetch proxy fresh baru dari internet...", "STEP")
            signup.ambil_proxy_fresh_otomatis(target=20)
            if not signup._baca_proxies():
                signup.log("Gagal fetch proxy -> signup pakai IP asli", "WARN")
                pakai_proxy = False
    else:
        pakai_proxy = False

    signup.log(f"Mode otomatis: {nama_mode} | proxy={pakai_proxy} | "
               f"jumlah={jumlah} | ulang_terus={ulang}", "INFO")

    if not _cek_konfigurasi(nama_mode):
        return 1

    putaran = 0
    while True:
        putaran += 1
        if ulang:
            signup.log(f"{'=' * 20} PUTARAN {putaran} {'=' * 20}", "INFO")
        try:
            if nama_mode in ("signup", "full"):
                mode_signup_full(nama_mode, pakai_proxy, jumlah_override=jumlah)
            elif nama_mode == "create_key":
                mode_create_key()
            else:
                mode_import_keys()
        except Exception as e:
            # Apa pun yang gagal jangan bunuh container -> log lalu lanjut.
            signup.log(f"Error putaran {putaran} (lanjut): {e}", "ERROR")

        if not ulang:
            return 0

        signup.log(f"Putaran {putaran} selesai -> mulai putaran "
                   f"{putaran + 1} (jalan terus, hentikan manual kalau mau "
                   "berhenti)", "OK")


def _baca_argumen():
    """Baca argumen `--auto <mode> [jumlah] [y|n] [--loop]`.

    Return (mode, pakai_proxy, jumlah, ulang) atau None kalau bukan --auto.
    """
    argv = sys.argv[1:]
    if not argv or argv[0] != "--auto":
        return None

    mode = "2"
    jumlah = 5
    pakai_proxy = True
    ulang = False

    sisa = list(argv[1:])
    if "--loop" in sisa:
        ulang = True
        sisa.remove("--loop")
    if "--terus" in sisa:
        ulang = True
        sisa.remove("--terus")

    if sisa and sisa[0] in ("1", "2", "3", "4"):
        mode = sisa.pop(0)
    if sisa:
        try:
            jumlah = max(1, int(sisa.pop(0)))
        except ValueError:
            pass
    if sisa:
        pakai_proxy = sisa.pop(0).strip().lower() not in ("n", "no", "0", "false")

    return mode, pakai_proxy, jumlah, ulang


if __name__ == "__main__":
    try:
        arg = _baca_argumen()
        code = main_otomatis(*arg) if arg else main()
    except KeyboardInterrupt:
        code = 0
    # Beri jeda 0.2s untuk clean shutdown async driver Playwright di Windows
    try:
        import time
        time.sleep(0.2)
    except Exception:
        pass
    sys.exit(code)

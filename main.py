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

import signup
import router9
import tampilan
import notif
from camoufox.sync_api import Camoufox

RESULT_TXT = signup.HERE / "result.txt"
KEYS_TXT = signup.HERE / "keys.txt"


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
    tampilan.judul("TOKEN HARBOR AUTO  -  9Router")
    print()
    print(f"{tampilan.BOLD}Mode:{tampilan.RST}")
    print(f"  {tampilan.BGRN}1{tampilan.RST}. signup       - buat akun + create API key")
    print(f"  {tampilan.BGRN}2{tampilan.RST}. full         - buat akun + create API key + input 9Router")
    print(f"  {tampilan.BGRN}3{tampilan.RST}. create_key   - login akun lama + create API key")
    print(f"  {tampilan.BGRN}4{tampilan.RST}. import_keys  - input key dari keys.txt ke 9Router")
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
    """Tanya berapa akun yg diproses. Return int > 0."""
    while True:
        jawab = input(f"{BOLD}{label}{RST} [default 1]: ").strip()
        if not jawab:
            return 1
        try:
            n = int(jawab)
            if n > 0:
                return n
        except ValueError:
            pass
        print(f"{YEL}Masukkan angka lebih dari 0.{RST}")


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
    if pakai_proxy and not proxies:
        signup.log("proxies.txt kosong -> signup pakai IP asli", "WARN")
        pakai_proxy = False

    headless = signup.HEADLESS_BROWSER
    MAX_RETRY = 5
    sukses = 0

    for i in range(jumlah):
        tampilan.bagian(f"AKUN {i + 1}/{jumlah}")

        email = signup.gen_email()
        password = signup.gen_password()
        tampilan.rinci("Email", email)
        tampilan.rinci("Password", password)

        # ---- FASE 1: SIGNUP (browser terpisah, bisa pakai proxy) ----
        # Retry network error: rate-limit 1 jam -> tunggu SEKALI, 1 menit -> tunggu.
        status_signup = "gagal"
        proxy_idx = 0
        # salinan daftar proxy; dikosongkan kalau proxy sudah habis, supaya
        # percobaan berikutnya benar-benar pakai IP asli (bukan proxy yang sama).
        sisa_proxy = list(proxies) if (pakai_proxy and proxies) else []
        sudah_tunggu_jam = False   # tunggu 1 jam cukup sekali per akun
        MAX_COBA_PROXY = 3         # berapa kali proxy dicoba sebelum dilepas
        coba_proxy = 0
        percobaan = 0
        # while (bukan for): tunggu 1 jam TIDAK boleh memakan jatah percobaan,
        # supaya setelah menunggu masih ada kesempatan mencoba.
        while percobaan < MAX_RETRY:
            percobaan += 1
            launch = {"headless": headless, "humanize": True,
                      "os": signup.OS_FP, "locale": ["id-ID"], "geoip": True}
            label_ip = "IP asli"
            if sisa_proxy:
                proxy_str = sisa_proxy[proxy_idx % len(sisa_proxy)]
                launch["proxy"] = signup._parse_proxy(proxy_str)
                label_ip = f"proxy {proxy_str}"
                proxy_idx += 1
            signup.log(f"Signup via: {label_ip} (coba {percobaan}/{MAX_RETRY})")

            proxy_mati = False
            try:
                with Camoufox(**launch) as browser:
                    page = browser.new_page()
                    page.set_default_timeout(90_000)
                    page.set_default_navigation_timeout(90_000)
                    status_signup = signup._jalankan_signup(page, email, password)
                # browser (proxy) tertutup di sini -> proxy berhenti dipakai
            except Exception as e:
                pesan = str(e)
                # NS_ERROR_PROXY_FORBIDDEN / PROXY_CONNECTION_REFUSED ->
                # proxy-nya sendiri yang mati/ditolak, bukan situsnya.
                # Percuma mengulang lewat proxy yang sama: langsung buang.
                if any(k in pesan for k in ("PROXY_FORBIDDEN",
                                            "PROXY_CONNECTION_REFUSED",
                                            "PROXY_CONNECTION_FAILED",
                                            "PROXY_RESOLUTION_FAILED")):
                    proxy_mati = True
                    signup.log(f"Proxy mati/ditolak -> lepas proxy, lanjut via "
                               f"IP asli", "WARN")
                else:
                    signup.log(f"Signup error jaringan/browser: {e}", "ERROR")
                status_signup = "network_error"

            if status_signup == "dashboard":
                break

            if proxy_mati and sisa_proxy:
                # Buang proxy yang mati, jangan pakai lagi.
                sisa_proxy = sisa_proxy[1:]
                proxy_idx = 0
                percobaan -= 1   # gagal proxy tidak memakan jatah percobaan
                if not sisa_proxy:
                    signup.log("Semua proxy gagal -> lanjut pakai IP asli",
                               "WARN")
                continue

            if status_signup == "network_hour":
                # "Too many sign-ups ... try again in an hour"
                # Proxy residential: IP berputar tiap koneksi. Tapi kalau jeda
                # antar percobaan cuma 5s, IP baru ikut langsung terbakar
                # (coba sebelumnya sudah menghabiskan 30s+ retry di IP lama).
                # Karena itu: tunggu 60s dulu, baru coba lewat proxy lagi.
                if sisa_proxy and coba_proxy < MAX_COBA_PROXY:
                    coba_proxy += 1
                    signup.log(f"Rate limit 1 jam -> tunggu 60s lalu coba lagi "
                               f"lewat proxy, IP akan berganti "
                               f"(percobaan proxy {coba_proxy}/{MAX_COBA_PROXY})",
                               "WARN")
                    time.sleep(60)
                    continue
                if sisa_proxy:
                    signup.log("Rate limit 1 jam -> proxy sudah cukup dicoba, "
                               "lepas proxy (berikutnya pakai IP asli)", "WARN")
                    sisa_proxy = []
                    time.sleep(5)
                    continue
                if not sudah_tunggu_jam:
                    sudah_tunggu_jam = True
                    percobaan -= 1   # tunggu 1 jam tidak memakan jatah percobaan
                    signup.log("Rate limit 1 jam -> tunggu 1 jam lalu coba lagi "
                               "(IP asli)", "WARN")
                    time.sleep(3600)
                    continue
                signup.log("Rate limit 1 jam masih berlaku -> akun ini dilewati "
                           "(tidak menunggu berjam-jam)", "WARN")
                status_signup = "rate_limit"
                break

            if status_signup == "network_minute":
                # "couldn't create your account ... try again in a minute"
                signup.log("Server sibuk -> tunggu 90 detik lalu coba lagi",
                           "WARN")
                time.sleep(90)
                continue

            signup.log(f"Signup gagal ({status_signup})", "WARN")
            continue

        if status_signup != "dashboard":
            # signup gagal total -> akun gak ada, JANGAN disimpan
            if status_signup == "rate_limit":
                signup.log("Akun ini dilewati karena rate limit masih berlaku "
                           "-> lanjut akun berikutnya", "WARN")
            else:
                signup.log(f"Signup gagal setelah {MAX_RETRY} percobaan -> "
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

    signup.log(f"Selesai: {sukses}/{jumlah} akun sukses create API key",
               "OK" if sukses else "WARN")
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

    tampilan.garis()
    signup.log(f"Selesai: {sukses}/{jumlah} akun sukses create API key",
               "OK" if sukses else "WARN")
    if salah_pw:
        signup.log(f"Kredensial SALAH ({len(salah_pw)}): "
                   f"{', '.join(salah_pw)}", "ERROR")
    if gagal_network:
        signup.log(f"Gagal network ({len(gagal_network)}): "
                   f"{', '.join(gagal_network)}", "WARN")
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

        # deteksi duplikat: baca semua koneksi yg sudah ada di 9Router sekali,
        # lalu skip key yg emailnya sudah ada (cek nama, bukan cek form).
        signup.log("Membaca daftar koneksi di 9Router (deteksi duplikat) ...")
        try:
            sudah_ada = router9.daftar_koneksi(page)
        except Exception as e:
            signup.log(f"Gagal baca daftar koneksi: {e} -> anggap kosong",
                       "WARN")
            sudah_ada = set()
        signup.log(f"Ditemukan {len(sudah_ada)} koneksi sudah ada di 9Router")
        if not router9._sudah_login(page):
            try:
                if not router9.login_router(page):
                    signup.log("GAGAL LOGIN 9ROUTER setelah baca koneksi",
                               "ERROR")
                    return 1
            except Exception as e:
                signup.log(f"Error login 9Router: {e}", "ERROR")
                return 1

        sukses = 0
        skip_duplikat = 0
        for i, (email, key) in enumerate(keys, 1):
            tampilan.bagian(f"KEY {i}/{len(keys)}  -  {email}")

            # duplikat (nama email sama persis) -> skip, jangan buka form.
            # Cukup dihitung, dirangkum di akhir (tidak dicetak 100x).
            if email in sudah_ada:
                skip_duplikat += 1
                sukses += 1
                continue

            tampilan.rinci("key", f"{key[:12]}...  ({len(key)} char)")

            # session bisa mati tengah jalan -> cek login tiap key
            if not router9._sudah_login(page):
                signup.log("Session 9Router mati -> login ulang ...", "WARN")
                try:
                    page.goto(f"{router9._router_url()}/login",
                              wait_until="domcontentloaded")
                except Exception:
                    pass
                if not router9.login_router(page):
                    signup.log(f"GAGAL re-login 9Router -> skip {email}", "ERROR")
                    continue

            try:
                status = router9.proses_router9(page, email, key)
            except Exception as e:
                signup.log(f"Error input {email}: {e}", "ERROR")
                status = "error"
            if status in ("tersimpan", "sudah_ada"):
                sukses += 1
            else:
                signup.log(f"Gagal input {email}: {status}", "ERROR")

        router9._simpan_session(page)
        ctx_state.close()

    tampilan.garis()
    tampilan.log(f"Ringkas: {len(keys)} key -> {skip_duplikat} sudah ada di 9Router (skip), "
                 f"{len(keys) - skip_duplikat} diproses", "INFO")
    signup.log(f"Selesai: {sukses}/{len(keys)} key tersimpan",
               "OK" if sukses else "WARN")
    return 0 if sukses else 1


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
            signup.log("proxies.txt kosong -> signup pakai IP asli", "WARN")
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
            tampilan.bagian(f"PUTARAN {putaran}")
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
        time.sleep(10)   # jeda kecil supaya tidak menghantam server terus-menerus


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
    arg = _baca_argumen()
    if arg:
        sys.exit(main_otomatis(*arg))
    sys.exit(main())

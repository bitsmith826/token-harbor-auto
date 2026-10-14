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

import concurrent.futures
import os
import queue
import sys
import threading
import time
from pathlib import Path

import notif
import router9
import signup
import tampilan

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


def _tanya_worker():
    """Tanya berapa worker simultan untuk multi-threading paralel."""
    while True:
        jawab = input(f"{BOLD}Berapa worker simultan?{RST} [default 2, maks 5]: ").strip()
        if not jawab:
            return 2
        try:
            n = int(jawab)
            if 1 <= n <= 5:
                return n
        except ValueError:
            pass
        print(f"{YEL}Masukkan angka antara 1 sampai 5 (default 2).{RST}")


# ----------------------------------------------------------------------
# SIMPAN HASIL (THREAD-SAFE)
# ----------------------------------------------------------------------

_file_lock = threading.Lock()
_refill_lock = threading.Lock()


def simpan_result(email, password, key=None, worker_id=None):
    """Tulis hasil ke result.txt secara thread-safe (UPSERT)."""
    with _file_lock:
        try:
            baris = f"{email}|{password}"
            if key:
                baris += f"|{key}"

            lama = []
            if RESULT_TXT.exists():
                with open(RESULT_TXT, encoding="utf-8") as f:
                    lama = [b.rstrip("\r\n") for b in f if b.strip()]

            ada = False
            for i, b in enumerate(lama):
                if b.split("|")[0] == email:
                    if key or b.count("|") < 2:
                        lama[i] = baris
                    ada = True
                    break
            if not ada:
                lama.append(baris)

            with open(RESULT_TXT, "w", encoding="utf-8") as f:
                f.write("\n".join(lama) + "\n")
            signup.log(f"Disimpan ke result.txt: {email}", "OK", worker_id=worker_id)

            if key:
                _simpan_keys(email, key, worker_id=worker_id)
        except Exception as e:
            signup.log(f"Gagal simpan result.txt: {e}", "WARN", worker_id=worker_id)


def _simpan_keys(email, key, worker_id=None):
    """Tulis email|key ke keys.txt secara thread-safe (upsert)."""
    try:
        lama = []
        if KEYS_TXT.exists():
            with open(KEYS_TXT, encoding="utf-8") as f:
                lama = [b.rstrip("\r\n") for b in f if b.strip()]
        if any(b.split("|")[0] == email for b in lama):
            return
        with open(KEYS_TXT, "a", encoding="utf-8") as f:
            f.write(f"{email}|{key}\n")
        signup.log(f"Disimpan ke keys.txt: {email}", "OK", worker_id=worker_id)
    except Exception as e:
        signup.log(f"Gagal simpan keys.txt: {e}", "WARN", worker_id=worker_id)


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

def _isi_antrean_proxy(proxy_queue, target=15, worker_id=None):
    """Thread-safe refill antrean proxy dari internet jika menipis."""
    with _refill_lock:
        if proxy_queue.qsize() >= 3:
            return
        signup.log("Antrean proxy menipis -> otomatis mengunduh & menguji proxy fresh baru...", "STEP", worker_id=worker_id)
        fresh_proxies = signup.ambil_proxy_fresh_otomatis(target=target)
        for p in fresh_proxies:
            proxy_queue.put(p)
        signup.log(f"Antrean proxy sekarang berisi {proxy_queue.qsize()} proxy aktif.", "OK", worker_id=worker_id)


def _proses_satu_akun_worker(worker_id, mode, pakai_proxy, proxy_queue, Camoufox, headless, max_percobaan=5):
    """Jalankan proses lengkap 1 akun untuk worker tertentu."""
    email = signup.gen_email()
    password = signup.gen_password()
    ip_info = tampilan.cek_ip_publik()
    ip_asli = ip_info.get("ipv4") or "Tidak terdeteksi"

    signup.log(f"Mulai registrasi akun: {email}", "STEP", worker_id=worker_id)

    status_signup = "gagal"
    current_proxy = None

    for percobaan in range(1, max_percobaan + 1):
        if percobaan > 1:
            email = signup.gen_email()
            password = signup.gen_password()
            signup.log(f"Email & password baru: {email}", "INFO", worker_id=worker_id)

        launch = {"headless": headless, "humanize": True,
                  "os": signup.OS_FP, "locale": ["id-ID"], "geoip": True}
        label_ip = f"IP Asli ({ip_asli})"

        if pakai_proxy:
            # Ambil proxy eksklusif dari antrean
            try:
                current_proxy = proxy_queue.get_nowait()
            except queue.Empty:
                current_proxy = None

            if not current_proxy:
                _isi_antrean_proxy(proxy_queue, target=15, worker_id=worker_id)
                try:
                    current_proxy = proxy_queue.get_nowait()
                except queue.Empty:
                    current_proxy = None

            if current_proxy:
                p_dict = signup._parse_proxy(current_proxy)
                launch["proxy"] = p_dict
                p_clean = p_dict.get("server", "").replace("http://", "").replace("https://", "")
                label_ip = f"Proxy ({p_clean})"

        signup.log(f"Signup via: {label_ip} (coba {percobaan}/{max_percobaan})", "STEP", worker_id=worker_id)

        try:
            with Camoufox(**launch) as browser:
                page = browser.new_page()
                timeout_signup = 22_000 if (pakai_proxy and current_proxy) else 45_000
                page.set_default_timeout(timeout_signup)
                page.set_default_navigation_timeout(timeout_signup)
                status_signup = signup._jalankan_signup(page, email, password)
        except Exception as e:
            signup.log(f"Proxy/koneksi bermasalah: {e}", "WARN", worker_id=worker_id)
            status_signup = "network_error"

        if status_signup == "dashboard":
            # Berhasil signup! Kembalikan proxy bagus ke antrean agar bisa dipakai lagi
            if current_proxy and pakai_proxy:
                proxy_queue.put(current_proxy)
            break

        if status_signup in ("network_hour", "network_minute", "network_error", "noform", "timeout", "fast"):
            signup.log(f"Proxy bermasalah / limit ({status_signup}) -> buang proxy, ambil berikutnya...", "WARN", worker_id=worker_id)
            time.sleep(1.5)
            continue

        signup.log(f"Signup gagal ({status_signup}) -> coba lagi", "WARN", worker_id=worker_id)

    if status_signup != "dashboard":
        signup.log(f"Signup gagal setelah {max_percobaan} percobaan", "ERROR", worker_id=worker_id)
        return False, email, None

    signup.log("Signup sukses -> lanjut verifikasi & API key (IP asli)", "OK", worker_id=worker_id)

    # ---- FASE 2: ENABLE + VERIFY + CREATE KEY (IP asli) ----
    key = None
    try:
        with Camoufox(headless=headless, humanize=True, os=signup.OS_FP,
                      locale=["id-ID"], geoip=True) as browser:
            page = browser.new_page()
            page.set_default_timeout(90_000)
            page.set_default_navigation_timeout(90_000)

            ok = signup._proses_verifikasi(page, email, password)
            if not ok:
                signup.log(f"Verifikasi email gagal untuk {email} (akun tetap tersimpan)", "WARN", worker_id=worker_id)
                simpan_result(email, password, worker_id=worker_id)
                return False, email, None

            key = signup.buat_api_key(page, email)
            if not key:
                signup.log(f"Create API key gagal untuk {email}", "ERROR", worker_id=worker_id)
                simpan_result(email, password, worker_id=worker_id)
                return False, email, None

            if not signup.pastikan_verified(page, email, key, log=lambda m, b="INFO": signup.log(m, b, worker_id=worker_id)):
                signup.log(f"Email {email} belum verified di API -> simpan tanpa input 9Router", "WARN", worker_id=worker_id)
                simpan_result(email, password, worker_id=worker_id)
                return False, email, None

            if mode == "full":
                if not signup._proses_router9(page, email, key):
                    signup.log("Input 9Router gagal", "ERROR", worker_id=worker_id)
                else:
                    signup.log("Input 9Router sukses", "OK", worker_id=worker_id)
                    notif.sukses_9router(email)
    except Exception as e:
        signup.log(f"Error fase 2: {e}", "ERROR", worker_id=worker_id)

    if key:
        simpan_result(email, password, key, worker_id=worker_id)
        notif.sukses_key(email, "1" if mode != "full" else "2")
        return True, email, key
    else:
        simpan_result(email, password, worker_id=worker_id)
        return False, email, None


def mode_signup_full(mode, pakai_proxy, jumlah_override=None, worker_override=None):
    """Mode 1 (signup) & 2 (full). Mendukung Multi-Worker Concurrency paralel."""
    if jumlah_override and jumlah_override > 0:
        jumlah = int(jumlah_override)
    else:
        jumlah = _tanya_jumlah("Berapa akun?")

    if worker_override and worker_override > 0:
        worker_count = int(worker_override)
    elif not jumlah_override:
        worker_count = _tanya_worker()
    else:
        worker_count = 1

    proxies = signup._baca_proxies() if pakai_proxy else []
    if pakai_proxy:
        if not proxies:
            signup.log("proxies.txt kosong -> otomatis mencari proxy fresh dari internet...", "WARN")
            proxies = signup.ambil_proxy_fresh_otomatis(target=max(20, worker_count * 5))
        elif not jumlah_override:
            try:
                tanya_fresh = input(f"{tampilan.CYN}Ambil proxy fresh baru otomatis dari internet? (y/n) [default n]: {tampilan.RST}").strip().lower()
                if tanya_fresh == "y":
                    proxies = signup.ambil_proxy_fresh_otomatis(target=max(20, worker_count * 5))
            except (EOFError, KeyboardInterrupt):
                pass
        if not proxies:
            signup.log("Tidak ada proxy tersedia -> signup pakai IP asli", "WARN")
            pakai_proxy = False

    headless = signup.HEADLESS_BROWSER
    Camoufox = _ambil_camoufox()

    # Antrean proxy thread-safe
    proxy_queue = queue.Queue()
    if pakai_proxy and proxies:
        for p in proxies:
            proxy_queue.put(p)

    total_sukses = 0
    lock_sukses = threading.Lock()
    stop_event = threading.Event()

    def _worker_loop(w_id):
        nonlocal total_sukses
        tampilan.set_worker_id(w_id)
        while not stop_event.is_set():
            with lock_sukses:
                if total_sukses >= jumlah:
                    break

            # Periksa antrean proxy jika menipis
            if pakai_proxy and proxy_queue.qsize() < worker_count:
                _isi_antrean_proxy(proxy_queue, target=max(15, worker_count * 4), worker_id=w_id)

            berhasil, em, k = _proses_satu_akun_worker(w_id, mode, pakai_proxy, proxy_queue, Camoufox, headless)
            if berhasil:
                with lock_sukses:
                    total_sukses += 1
                    label_total = "∞" if jumlah >= 999999 else str(jumlah)
                    signup.log(f"Akun sukses [{total_sukses}/{label_total}]: {em}", "OK", worker_id=w_id)
                    if total_sukses >= jumlah:
                        stop_event.set()
                        break
            time.sleep(1)

    label_total = "∞" if jumlah >= 999999 else str(jumlah)
    tampilan.bagian(f"MEMULAI {worker_count} WORKER PARALEL (Target: {label_total} Akun)")
    tampilan.rinci("Mode", mode.upper())
    tampilan.rinci("Worker Simultan", str(worker_count))
    tampilan.rinci("Jalur", f"Proxy Queue ({proxy_queue.qsize()} proxy)" if pakai_proxy else "IP Asli")

    if worker_count > 1:
        with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = [executor.submit(_worker_loop, w_id) for w_id in range(1, worker_count + 1)]
            try:
                for f in concurrent.futures.as_completed(futures):
                    f.result()
            except KeyboardInterrupt:
                signup.log("Dihentikan oleh pengguna (Ctrl+C). Menunggu worker selesai...", "WARN")
                stop_event.set()
    else:
        _worker_loop(1)

    tampilan.ringkasan({
        "Mode": mode.upper(),
        "Worker": worker_count,
        "Total Target": jumlah if jumlah < 999999 else "UNLIMITED",
        "Sukses Key": total_sukses,
        "Status Akhir": "OK" if total_sukses > 0 else "GAGAL"
    }, "HASIL MULTI-WORKER TOKEN HARBOR")
    tampilan.log("Semua proses worker selesai. Hasil tersimpan di result.txt", "OK")
    return 0 if total_sukses else 1


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

def main_otomatis(mode, pakai_proxy, jumlah, ulang=False, worker=2):
    """Jalur non-interaktif: mode diambil dari argumen command-line.

    Dipakai container Docker / VPS supaya bisa jalan 24/7 tanpa ada orang
    mengetik di layar.

    Contoh:
        python main.py --auto 1 5            -> mode 1, 5 akun, 2 worker
        python main.py --auto 1 0 --loop     -> mode 1, UNLIMITED akun, jalan terus
        python main.py --auto 2 10 y --worker 3 -> mode 2, 10 akun, 3 worker simultan
    """
    signup._muat_env()
    tampilan.aktifkan_warna()

    peta = {"1": "signup", "2": "full", "3": "create_key", "4": "import_keys"}
    nama_mode = peta.get(mode, mode)

    if nama_mode in ("signup", "full"):
        if pakai_proxy and not signup._baca_proxies():
            signup.log("proxies.txt kosong -> otomatis fetch proxy fresh baru dari internet...", "STEP")
            signup.ambil_proxy_fresh_otomatis(target=max(20, worker * 5))
            if not signup._baca_proxies():
                signup.log("Gagal fetch proxy -> signup pakai IP asli", "WARN")
                pakai_proxy = False
    else:
        pakai_proxy = False

    signup.log(f"Mode otomatis: {nama_mode} | proxy={pakai_proxy} | "
               f"jumlah={jumlah} | worker={worker} | ulang_terus={ulang}", "INFO")

    if not _cek_konfigurasi(nama_mode):
        return 1

    putaran = 0
    while True:
        putaran += 1
        if ulang:
            signup.log(f"{'=' * 20} PUTARAN {putaran} {'=' * 20}", "INFO")
        try:
            if nama_mode in ("signup", "full"):
                mode_signup_full(nama_mode, pakai_proxy, jumlah_override=jumlah, worker_override=worker)
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
    """Baca argumen `--auto <mode> [jumlah] [y|n] [--loop] [--worker N]`.

    Return (mode, pakai_proxy, jumlah, ulang, worker) atau None kalau bukan --auto.
    """
    argv = sys.argv[1:]
    if not argv or argv[0] != "--auto":
        return None

    mode = "2"
    jumlah = 5
    pakai_proxy = True
    ulang = False
    worker = 2

    sisa = list(argv[1:])
    if "--loop" in sisa:
        ulang = True
        sisa.remove("--loop")
    if "--terus" in sisa:
        ulang = True
        sisa.remove("--terus")
    if "--worker" in sisa:
        try:
            w_idx = sisa.index("--worker")
            sisa.pop(w_idx)
            if w_idx < len(sisa):
                worker = max(1, min(5, int(sisa.pop(w_idx))))
        except Exception:
            pass

    if sisa and sisa[0] in ("1", "2", "3", "4"):
        mode = sisa.pop(0)
    if sisa:
        try:
            jumlah = max(1, int(sisa.pop(0)))
        except ValueError:
            pass
    if sisa:
        pakai_proxy = sisa.pop(0).strip().lower() not in ("n", "no", "0", "false")

    return mode, pakai_proxy, jumlah, ulang, worker


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

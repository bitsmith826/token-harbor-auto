#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Token Harbor Auto - Step 1+2: Sign up + Verify email

Step 1: signup
  1. Buka https://tokenharbor.ai/ -> klik "Try free"
  2. Tunggu Cloudflare Turnstile sampai field muncul
  3. Isi email faker @example.com + password (12+ char, huruf+angka)
  4. Invite code dikosongkan
  5. Klik "Create account"
  6. Retry:
     - "You're doing that a bit fast" -> tunggu 10s, isi password lagi, klik ulang
     - "Too many sign-ups from this network" -> butuh ganti proxy
Step 2: verify
  7. Masuk dashboard -> kalo ada modal "Enable free models?" klik Enable free models
     (kalo tidak ada, scroll cari Free Access -> aktifkan)
  8. Cari tombol "Verify email" di dashboard -> klik
  9. Gmail polling link verifikasi (match by email yg didaftarkan), buka link
 10. Sukses = link terverifikasi
"""

import os
import re
import sys
import time
import random
import string
import datetime
from pathlib import Path
from faker import Faker

import gmail_inbox
import tampilan
import urllib.request
import urllib.error

# ---------------------------------------------------------------- paths
HERE = Path(__file__).resolve().parent
RESULT_TXT = HERE / "result.txt"
KEYS_TXT = HERE / "keys.txt"
LOG_DIR = HERE / "logs"
LOG_DIR.mkdir(exist_ok=True)


def _muat_env():
    """Baca .env ke environment (sederhana, tanpa library)."""
    path = HERE / ".env"
    if not path.exists():
        return
    with open(path, encoding="utf-8") as f:
        for baris in f:
            baris = baris.strip()
            if not baris or baris.startswith("#") or "=" not in baris:
                continue
            kunci, nilai = baris.split("=", 1)
            os.environ.setdefault(kunci.strip(), nilai.strip())


_muat_env()

BASE_URL = "https://tokenharbor.ai/"
SIGNUP_URL = "https://tokenharbor.ai/signup"
LOGIN_URL = "https://tokenharbor.ai/login"
DASHBOARD_URL = "https://tokenharbor.ai/dashboard"

FAST_WAIT_SEC = 20
MAX_FAST_RETRY = 10

FAST_PATTERNS = [
    "doing that a bit fast",
    "take a breath",
    "slow down",
]
HOUR_PATTERNS = [
    "too many sign-ups",
    "too many signups",
    "from this network",
    "try again in an hour",
]
MINUTE_PATTERNS = [
    "couldn't create your account",
    "our team has been alerted",
    "please try again in a minute",
]

FAKE = Faker()

# True kalau HEADLESS env di-set (selain "false"). Default: HEADLESS (UI gak ganggu).
HEADLESS = os.environ.get("HEADLESS", "true").lower() not in ("0", "false", "no")

# Profil OS untuk fingerprint browser. Ikut OS yang benar-benar dipakai,
# supaya di VPS Linux tidak berpura-pura Windows (mudah terdeteksi).
OS_FP = ("windows",) if sys.platform == "win32" else ("linux",)

# Di Linux, headless murni lebih mudah terdeteksi. Pakai virtual display
# (Xvfb) kalau tersedia; kalau tidak, jatuh ke True.
if HEADLESS and sys.platform == "linux" and os.environ.get("DISPLAY"):
    HEADLESS_BROWSER = "virtual"
else:
    HEADLESS_BROWSER = HEADLESS


def log(msg, badge="INFO", worker_id=None):
    tampilan.log(msg, badge, worker_id=worker_id)


def _email_terpakai():
    """Set username (local part) yang sudah pernah dipakai, dari result.txt."""
    dipakai = set()
    try:
        with open(RESULT_TXT, encoding="utf-8") as f:
            for baris in f:
                baris = baris.strip()
                if "|" in baris:
                    dipakai.add(baris.split("|", 1)[0].split("@", 1)[0].lower())
    except FileNotFoundError:
        pass
    return dipakai


def gen_email():
    """Username dari nama manusia (faker), 8-12 char, huruf+angka, unik."""
    domain = os.environ.get("DOMAIN", "example.com")
    dipakai = _email_terpakai()
    for _ in range(50):
        depan = FAKE.first_name()
        belakang = FAKE.last_name()
        # gabung: namadepan + namabelakang, lowercase, hanya huruf+angka
        user = (depan + belakang).lower()
        user = "".join(c for c in user if c.isalnum())
        if len(user) > 16:
            continue  # nama terlalu panjang -> cari nama lain
        # kadang pakai suffix angka, kadang gak (random kaya username faker)
        dadu = random.random()
        if dadu < 0.4:
            user += str(random.randint(2, 99))
        elif dadu < 0.6:
            user += str(random.randint(100, 999))
        if user.lower() not in dipakai:
            return f"{user}@{domain}"
    raise RuntimeError("Tidak nemu username unik setelah 50x percobaan")


def gen_password():
    """Minimal 12 char (14-18), huruf besar/kecil + angka (tanpa symbol)."""
    return FAKE.password(length=random.randint(14, 18),
                         special_chars=False, digits=True,
                         upper_case=True, lower_case=True)


def detect_notice(text):
    t = (text or "").lower()
    for p in HOUR_PATTERNS:
        if p in t:
            return "network_hour"
    for p in MINUTE_PATTERNS:
        if p in t:
            return "network_minute"
    for p in FAST_PATTERNS:
        if p in t:
            return "fast"
    return None


def _text_of(page):
    try:
        return page.evaluate("() => document.body ? document.body.innerText : ''")
    except Exception:
        return ""


def _snapshot(page, tag):
    try:
        ts = datetime.datetime.now().strftime("%H%M%S")
        page.screenshot(path=str(LOG_DIR / f"debug_{tag}_{ts}.png"))
        with open(LOG_DIR / f"debug_{tag}_{ts}.html", "w", encoding="utf-8") as f:
            f.write(page.content())
    except Exception as e:
        log(f"snapshot gagal: {e}", "WARN")


def ambil_proxy_fresh_otomatis(target=15, simpan=True):
    """Scrape proxy gratisan fresh dari internet & uji respon langsung ke tokenharbor.ai."""
    import urllib.request
    import json
    import concurrent.futures

    log("Mengunduh daftar proxy gratisan fresh dari internet ...", "STEP")
    sources = [
        "https://proxylist.geonode.com/api/proxy-list?limit=150&page=1&sort_by=lastChecked&sort_type=desc",
        "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=3000&country=all&ssl=yes&anonymity=elite",
        "https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/https.txt",
        "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/http/data.txt",
        "https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_RAW.txt",
        "https://raw.githubusercontent.com/sunny9577/proxy-scraper/master/generated/http_proxies.txt",
        "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
        "https://raw.githubusercontent.com/proxmint/free-proxy-list/main/proxies/http.txt",
        "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
        "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-https.txt",
        "https://raw.githubusercontent.com/komutan234/Proxy-List-Free/main/proxies/http.txt",
    ]
    candidates = set()
    for url in sources:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                text = resp.read().decode("utf-8", errors="ignore")
                if "geonode" in url:
                    data = json.loads(text)
                    for item in data.get("data", []):
                        ip = item.get("ip")
                        port = item.get("port")
                        if ip and port:
                            candidates.add(f"{ip}:{port}")
                else:
                    for line in text.splitlines():
                        line = line.strip()
                        if line.startswith("http://") or line.startswith("https://"):
                            line = line.split("://")[-1]
                        if ":" in line and not line.startswith("#"):
                            parts = line.split(":")
                            if len(parts) >= 2 and parts[0].replace(".", "").isdigit():
                                candidates.add(f"{parts[0]}:{parts[1]}")
        except Exception:
            pass

    cand_list = list(candidates)
    log(f"Terkumpul {len(cand_list)} kandidat proxy. Menguji respon ke Token Harbor...", "INFO")

    def _check(p):
        p_url = f"http://{p}"
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": p_url, "https": p_url}))
        t0 = time.time()
        try:
            req = urllib.request.Request("https://tokenharbor.ai/signup", headers={"User-Agent": "Mozilla/5.0"})
            with opener.open(req, timeout=3.5) as resp:
                if resp.status == 200:
                    lat_ms = int((time.time() - t0) * 1000)
                    return (p, lat_ms)
        except Exception:
            pass
        return None

    working = []
    # Uji batch kandidat secara paralel
    batch_cand = cand_list[:750]
    with concurrent.futures.ThreadPoolExecutor(max_workers=60) as executor:
        futures = [executor.submit(_check, p) for p in batch_cand]
        for f in concurrent.futures.as_completed(futures):
            res = f.result()
            if res:
                working.append(res)
                if len(working) >= target * 2:
                    executor.shutdown(wait=False, cancel_futures=True)
                    break

    # Urutkan berdasarkan latensi tercepat (ms terendah di awal)
    working.sort(key=lambda x: x[1])
    top_working = [p for p, lat in working[:target]]

    if top_working and simpan:
        header = "# Daftar proxy untuk signup Token Harbor (satu per baris)\n# Format: host:port\n# Otomatis diurutkan dari latensi tercepat\n\n"
        with open(HERE / "proxies.txt", "w", encoding="utf-8") as f:
            f.write(header + "\n".join(top_working) + "\n")
        fastest_lat = working[0][1] if working else 0
        slowest_lat = working[min(len(working) - 1, target - 1)][1] if working else 0
        log(f"Berhasil menyimpan {len(top_working)} proxy fresh (latensi {fastest_lat}ms - {slowest_lat}ms) ke proxies.txt!", "OK")
    elif not top_working:
        log("Tidak ada proxy fresh baru yang lolos uji respon", "WARN")

    return top_working


def _baca_proxies():
    """Baca daftar proxy dari .env (PROXY=...) atau file proxies.txt. Format: server:port:username:password atau http://user:pass@host:port"""
    proxies = []
    path = HERE / "proxies.txt"
    if path.exists():
        with open(path, encoding="utf-8") as f:
            for baris in f:
                baris = baris.strip()
                if not baris or baris.startswith("#"):
                    continue
                proxies.append(baris)
    env_proxy = os.environ.get("PROXY", "").strip()
    if env_proxy:
        proxies.append(env_proxy)
    return proxies


def _parse_proxy(s):
    """Ubah berbagai format proxy jadi dict {server, username, password} untuk Camoufox."""
    s = s.strip()
    if "@" in s:
        # http://user:pass@host:port
        import urllib.parse as up
        u = up.urlparse(s if "://" in s else "http://" + s)
        out = {"server": f"{u.scheme or 'http'}://{u.hostname}:{u.port}"}
        if u.username:
            out["username"] = u.username
        if u.password:
            out["password"] = u.password
        return out
    bagian = s.split(":")
    if len(bagian) == 2:
        return {"server": f"http://{bagian[0]}:{bagian[1]}"}
    if len(bagian) == 4:
        return {"server": f"http://{bagian[0]}:{bagian[1]}",
                "username": bagian[2], "password": bagian[3]}
    raise ValueError(f"format proxy gak dikenali: {s}")


def _page_context_baru(browser, proxy=None):
    """Bikin context + page. proxy=None -> IP asli."""
    ctx = browser.new_context(proxy=proxy) if proxy else browser.new_context()
    page = ctx.new_page()
    page.set_default_timeout(90_000)
    page.set_default_navigation_timeout(90_000)
    return ctx, page


def _tunggu_field(page, maks_iter=20, diam=False):
    if not diam:
        log("Menunggu field email/password (Turnstile) ...")
    try:
        # Gunakan Playwright wait_for agar seketika mendeteksi saat Turnstile lewat
        page.locator('input[type="email"]').wait_for(state="visible", timeout=maks_iter * 1000)
        page.locator('input[type="password"]').wait_for(state="visible", timeout=4000)
        return True
    except Exception:
        # Fallback pengecekan count cepat
        for _ in range(3):
            try:
                if page.locator('input[type="email"]').count() > 0 and \
                   page.locator('input[type="password"]').count() > 0:
                    return True
            except Exception:
                pass
            time.sleep(1)
        return False


def _klik_tombol(page, daftar_nama, label="tombol"):
    """Klik tombol pertama yg ketemu dari daftar nama."""
    for nama in daftar_nama:
        for ambil in (
            lambda n=nama: page.get_by_role("button", name=re.compile(re.escape(n), re.I)).first,
            lambda n=nama: page.locator(f"button:has-text('{n}')").first,
            lambda n=nama: page.get_by_role("link", name=re.compile(re.escape(n), re.I)).first,
        ):
            try:
                el = ambil()
                if el.count() > 0:
                    el.scroll_into_view_if_needed()
                    el.click()
                    return True
            except Exception:
                continue
    return False


def _tunggu_tombol_siap(page, maks_iter=30):
    """Tunggu sampai tombol submit bukan 'One moment...' (loading) lagi."""
    for _ in range(maks_iter):
        try:
            txt = _text_of(page).lower()
            if "one moment" not in txt:
                return True
        except Exception:
            pass
        time.sleep(2)
    return False


def _klik_create(page):
    strategi = [
        lambda: page.get_by_role("button", name=re.compile(r"create account", re.I)).first,
        lambda: page.get_by_role("button", name=re.compile(r"^sign up$", re.I)).first,
        lambda: page.locator('button[type="submit"]').first,
        lambda: page.locator("button:has-text('Create account')").first,
        lambda: page.locator("button:has-text('Sign up')").first,
    ]
    for s in strategi:
        try:
            el = s()
            el.wait_for(timeout=8000)
            el.click()
            return True
        except Exception:
            continue
    try:
        page.locator('input[type="password"]').press("Enter")
        return True
    except Exception as e:
        log(f"Tidak bisa klik Create account: {e}", "ERROR")
        return False


def _di_dashboard(page):
    url = (page.url or "").lower()
    if "dashboard" in url:
        return True
    # dashboard bisa juga di-render tanpa ganti url; cek konten khas
    txt = _text_of(page).lower()
    return any(x in txt for x in ("api keys", "api-keys", "dashboard overview",
                                  "free models enabled", "verify email",
                                  "billing", "usage"))


# ------------------------------------------------- step 2: dashboard
def _enable_free_models(page):
    """Klik 'Enable free models' di modal. Return True kalau sudah aktif."""
    # 1. tunggu modal muncul (bisa delay beberapa detik setelah login)
    tombol = page.locator('[data-analytics="freemodel-consent-enable"]')
    for _ in range(20):
        txt = _text_of(page).lower()
        if "free models enabled" in txt:
            log("Free models sudah aktif")
            return True
        if tombol.count() > 0:
            break
        time.sleep(1.5)
    else:
        # modal gak muncul -> aktifkan via toggle di dashboard
        log("Modal tidak muncul -> cari toggle 'Free models enabled' di dashboard")
        return _aktifkan_toggle(page)

    # 2. klik tombol Enable
    try:
        tombol.click()
        log("Klik 'Enable free models' (modal free models)")
        time.sleep(2)
    except Exception as e:
        log(f"Gagal klik Enable free models: {e}", "ERROR")
        return False

    # 3. pastikan benar-benar aktif: label "free models enabled" muncul
    for _ in range(20):
        txt = _text_of(page).lower()
        if "free models enabled" in txt:
            log("Free models AKTIF", "OK")
            return True
        time.sleep(1.5)
    log("Klik Enable tapi state 'free models enabled' tidak terdeteksi", "WARN")
    _snapshot(page, "enable_unknown")
    return False


def _aktifkan_toggle(page):
    """Fallback: aktifkan toggle 'Enable free models' di dashboard."""
    sw = page.locator('button[role="switch"][aria-label*="free models"]')
    try:
        if sw.count() == 0:
            log("Toggle free models tidak ditemukan", "ERROR")
            _snapshot(page, "no_toggle")
            return False
        for _ in range(3):
            checked = sw.get_attribute("aria-checked")
            if checked == "true":
                log("Toggle free models sudah ON", "OK")
                return True
            sw.click()
            log("Klik toggle 'Enable free models'")
            time.sleep(2)
        checked = sw.get_attribute("aria-checked")
        if checked == "true":
            log("Toggle free models ON", "OK")
            return True
    except Exception as e:
        log(f"Gagal toggle: {e}", "ERROR")
        _snapshot(page, "toggle_err")
        return False
    log("Toggle tetap OFF setelah 3x klik", "ERROR")
    _snapshot(page, "toggle_off")
    return False


def _klik_verify_email(page):
    """Cari tombol 'Verify email' di dashboard, klik. Return True kalau diklik."""
    for ambil in (
        lambda: page.get_by_role("button", name=re.compile(r"verify email", re.I)).first,
        lambda: page.get_by_role("link", name=re.compile(r"verify email", re.I)).first,
        lambda: page.locator("button:has-text('Verify email')").first,
        lambda: page.locator("a:has-text('Verify email')").first,
        lambda: page.get_by_text("Verify email", exact=False).first,
    ):
        try:
            el = ambil()
            if el.count() > 0:
                el.scroll_into_view_if_needed()
                el.click()
                log("Klik tombol 'Verify email'")
                _tunggu_email_sent(page)
                return True
        except Exception:
            continue
    log("Tombol 'Verify email' tidak ditemukan", "WARN")
    return False


def _tunggu_email_sent(page, maks_iter=30):
    """Tunggu sampai muncul indikasi email verifikasi sudah dikirim."""
    for i in range(maks_iter):
        try:
            txt = _text_of(page).lower()
        except Exception:
            time.sleep(2)
            continue
        for indikator in ("email sent", "email has been sent", "check your email",
                          "we sent", "verification email"):
            if indikator in txt:
                log(f"Konfirmasi terkirim: '{indikator}'")
                return True
        time.sleep(2)
    log("Indikasi 'Email sent' tidak muncul (30s) -- lanjut cek Gmail", "WARN")
    return False


def _buka_link_verifikasi(page, link):
    """Buka link verifikasi langsung di tab aktif, konfirmasi status verified."""
    try:
        page.goto(link, wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        log(f"Navigasi link verifikasi: {e}", "WARN")

    for _ in range(15):
        txt = _text_of(page).lower()
        url = (page.url or "").lower()
        if any(w in txt for w in ("success", "verified", "email verified", "email address verified", "thank you", "confirmed")):
            return True, page
        if "dashboard" in url and "verify" not in url:
            # sudah otomatis redirect ke dashboard setelah verifikasi
            return True, page
        time.sleep(1)
    return False, page


def buat_api_key(page, email):
    """Buat API key baru dengan label = email. Return key string atau None."""
    log("Membuat API key ...")
    sukses_buka = False
    for coba_goto in range(3):
        try:
            time.sleep(1.2)
            page.goto("https://tokenharbor.ai/dashboard/api-keys",
                      wait_until="domcontentloaded")
            sukses_buka = True
            break
        except Exception as e:
            if coba_goto == 2:
                log(f"Gagal buka halaman API keys: {e}", "ERROR")
                return None
            time.sleep(2)

    # tutup modal/cooki banner kalau ganggu
    try:
        page.keyboard.press("Escape")
    except Exception:
        pass

    # klik "+ New key" (JS click juga, antisipasi overlay)
    try:
        btn_new = page.locator("button:has-text('New key')")
        for _ in range(20):
            if btn_new.count() > 0:
                break
            time.sleep(1)
        try:
            btn_new.scroll_into_view_if_needed(timeout=5_000)
        except Exception:
            pass
        time.sleep(0.5)
        page.evaluate(
            "el => el.click()",
            btn_new.element_handle(timeout=5_000),
        )
        time.sleep(1.5)
    except Exception as e:
        log(f"Gagal klik '+ New key': {e}", "ERROR")
        _snapshot(page, "newkey_fail")
        return None

    # isi label pakai email
    try:
        inp = page.locator('input[placeholder*="Cursor"]')
        if inp.count() == 0:
            # fallback: input text pertama di form
            inp = page.locator('input[type="text"]').first
        inp.fill(email)
        time.sleep(0.8)
    except Exception as e:
        log(f"Gagal isi label: {e}", "ERROR")
        _snapshot(page, "label_fail")
        return None

    # klik "Create key" (pakai JS — elemen <ul>/<header> sering nyampul pointer events)
    try:
        btn = page.locator("button:has-text('Create key')")
        for _ in range(10):
            if btn.get_attribute("disabled") is None and btn.count() > 0:
                break
            time.sleep(1)
        # scroll ke tombol dulu
        try:
            btn.scroll_into_view_if_needed(timeout=5_000)
        except Exception:
            pass
        time.sleep(0.5)
        # pakai JS click (lolos overlay)
        page.evaluate(
            "el => el.click()",
            btn.element_handle(timeout=5_000),
        )
        time.sleep(3)
    except Exception as e:
        log(f"Gagal klik 'Create key': {e}", "ERROR")
        _snapshot(page, "createkey_fail")
        return None

    # ambil key (thk_live_xxx) — ambil dari elemen <code> dulu, paling akurat
    for _ in range(20):
        try:
            for code in page.locator("code").all():
                teks = code.text_content() or ""
                if "thk_live_" in teks:
                    key = teks.strip()
                    if key.startswith("thk_live_"):
                        log(f"API key dibuat: {key[:30]}...", "OK")
                        return key
        except Exception:
            pass
        try:
            html = page.content()
            keys = re.findall(r"thk_live_[A-Za-z0-9_-]+", html)
            if keys:
                key = keys[0]
                log(f"API key dibuat: {key[:30]}...", "OK")
                return key
        except Exception:
            pass
        time.sleep(1.5)

    log("API key tidak muncul setelah Create key", "ERROR")
    _snapshot(page, "no_apikey")
    return None


def _proses_router9(page, email, key, maks_retry=3):
    """Input API key ke 9Router. Prioritaskan REST API langsung (< 1 detik, tanpa buka context browser baru)."""
    import router9

    # 1. Coba via Direct REST API langsung (Ultra-Fast)
    try:
        status_api = router9.api_tambah_api_key(email, key)
        if status_api in ("tersimpan", "sudah_ada"):
            log("9Router: API key tersimpan via REST API", "OK")
            return True
        log(f"REST API 9Router mengembalikan status '{status_api}', mencoba fallback via browser...", "WARN")
    except Exception as e:
        log(f"REST API 9Router gagal ({e}), beralih ke fallback browser...", "WARN")

    # 2. Fallback jika REST API bermasalah -> buka browser tab 9Router
    page_router = None
    ctx_router = None
    try:
        browser = page.context.browser
        ctx_router = browser.new_context(storage_state=str(router9.SESSION_FILE)) \
            if router9.SESSION_FILE.exists() else browser.new_context()
        page_router = ctx_router.new_page()
        page_router.set_default_timeout(60_000)
        page_router.set_default_navigation_timeout(60_000)
    except Exception as e:
        log(f"Gagal bikin context 9Router, pakai page utama: {e}", "WARN")
        page_router = page

    hasil = False
    for percobaan in range(1, maks_retry + 1):
        log(f"Input 9Router via browser (percobaan {percobaan}/{maks_retry}) ...")
        try:
            status = router9.proses_router9(page_router, email, key)
        except Exception as e:
            log(f"Error 9Router: {e}", "ERROR")
            return False

        if status in ("tersimpan", "sudah_ada"):
            log("9Router: API key tersimpan", "OK")
            hasil = True
            break
        log(f"9Router: status {status} -> coba ulang...", "WARN")
        if percobaan >= maks_retry:
            log(f"9Router: gagal setelah {maks_retry} percobaan", "ERROR")
            break
        time.sleep(5)

    # tutup context router9 (hindari warning "future exception")
    if ctx_router is not None:
        try:
            ctx_router.close()
        except Exception:
            pass
    return hasil


def proses_dashboard(page, email):
    """Step 2: modal free models -> tombol verify -> buka link dari Gmail."""
    # pastikan di dashboard
    for _ in range(30):
        if _di_dashboard(page):
            break
        time.sleep(2)
    else:
        log("Tidak sampai dashboard", "ERROR")
        return False

    log("Sudah di dashboard")
    _enable_free_models(page)

    if not _klik_verify_email(page):
        _snapshot(page, "no_verify_btn")
        log("Lanjut tetap cek Gmail (mungkin email dikirim otomatis)", "WARN")

    log("Menunggu email verifikasi masuk ke Gmail (30-90s) ...")
    link = gmail_inbox.cari_link_verifikasi(email, timeout=180, interval=3, log=log)
    if not link:
        log("Link verifikasi tidak ditemukan di Gmail", "ERROR")
        _snapshot(page, "no_link")
        return False

    log("Membuka link verifikasi ...")
    ok, _ = _buka_link_verifikasi(page, link)
    if ok:
        log("EMAIL TERVERIFIKASI", "OK")
        return True
    log("Link dibuka tapi status success tidak terdeteksi", "WARN")
    _snapshot(page, "verify_unknown")
    return False


def signup_once(headless):
    """
    Signup lewat proxy, verifikasi pakai IP asli.
    Browser launch pakai proxy HANYA untuk signup, lalu ditutup.
    Browser baru tanpa proxy untuk verifikasi. Berurutan -> 1 window tiap fase.
    """
    proxies = _baca_proxies()
    if not proxies:
        log("Tidak ada proxy -> signup pakai IP asli", "WARN")
        proxies = [None]

    email = password = status = None
    network_retry = 0
    MAX_NETWORK_RETRY = max(5, len(proxies)) if (proxies and proxies != [None]) else 5
    selesai = False
    proxy_idx = 0
    while not selesai:
        proxy_str = proxies[proxy_idx % len(proxies)] if proxies else None
        email, password = gen_email(), gen_password()
        ip_info = tampilan.cek_ip_publik()
        ip_asli = ip_info.get("ipv4") or "Tidak terdeteksi"
        warp_tag = " [WARP Shared]" if ip_info.get("is_warp") else ""
        if proxy_str:
            p_dict = _parse_proxy(proxy_str)
            p_clean = p_dict.get("server", "").replace("http://", "").replace("https://", "")
            label = f"Proxy ({p_clean})"
        else:
            label = f"IP Asli ({ip_asli}{warp_tag})"

        tampilan.bagian("SIGNUP AKUN")
        tampilan.rinci("Jalur / IP", label)
        tampilan.rinci("Email", email)
        tampilan.rinci("Password", password)

        launch = {"headless": headless, "humanize": True,
                  "os": OS_FP, "locale": ["id-ID"], "geoip": True}
        if proxy_str:
            launch["proxy"] = _parse_proxy(proxy_str)

        from camoufox.sync_api import Camoufox
        try:
            with Camoufox(**launch) as browser:
                page = browser.new_page()
                timeout_proxy = 22_000 if proxy_str else 45_000
                page.set_default_timeout(timeout_proxy)
                page.set_default_navigation_timeout(timeout_proxy)
                status = _jalankan_signup(page, email, password)
        except Exception as e:
            log(f"Proxy mati/error jaringan: {e}", "WARN")
            status = "network_error"

        if status == "dashboard":
            selesai = True
            break

        network_retry += 1
        if network_retry > MAX_NETWORK_RETRY:
            log(f"Batas retry ({MAX_NETWORK_RETRY}) tercapai", "ERROR")
            break

        if status in ("network", "network_hour"):
            if not proxy_str:
                log(f"Rate limit 1 jam pada {ip_asli} -> mulai cooldown 1 jam "
                    f"(retry {network_retry}/{MAX_NETWORK_RETRY})", "LIMIT")
                tampilan.tunggu(3600, "Cooldown IP Rate-Limit")
                continue
            proxy_idx += 1
            log(f"Proxy kena limit (too many signup) -> coba proxy berikutnya (retry {network_retry}/{MAX_NETWORK_RETRY})", "WARN")
            time.sleep(2)
            continue

        if status == "network_error":
            if proxy_str:
                proxy_idx += 1
                log(f"Proxy mati/terputus -> beralih ke proxy berikutnya...", "WARN")
                time.sleep(2)
                continue

        log(f"Gagal signup ({status}) -> coba lagi", "WARN")
        continue

    if status != "dashboard":
        return email, password, (status or "gagal")

    # ---- VERIFIKASI: browser baru, IP asli, window tunggal
    log("Signup sukses. Verifikasi pakai IP asli ...")
    with Camoufox(headless=HEADLESS_BROWSER, humanize=True, os=OS_FP,
                  locale=["id-ID"], geoip=True) as browser:
        page = browser.new_page()
        page.set_default_timeout(90_000)
        page.set_default_navigation_timeout(90_000)
        ok = _proses_verifikasi(page, email, password)

    return email, password, ("verified" if ok else "dashboard_noverify")


def _ketik_manusiawi(page, selector, teks):
    """Ketik per huruf dengan jeda acak, seperti manusia.

    page.fill() mengisi seluruh teks sekaligus -> signature bot yang mudah
    ditangkap Turnstile. page.type() dengan delay menghasilkan event
    keydown/keyup per huruf seperti keyboard asli.
    """
    for _ in range(3):
        try:
            el = page.locator(selector)
            el.click()
            time.sleep(random.uniform(0.1, 0.2))
            el.type(teks, delay=random.randint(25, 55))
            return
        except Exception:
            time.sleep(0.3)
    # jalan terakhir: fill() lebih baik daripada gagal total
    page.locator(selector).fill(teks)


def _jalankan_signup(page, email, password):
    """Jalankan signup di page yg sudah ada. Return status string."""
    # Optimasi hemat kuota proxy: blokir aset gambar/media/font dekoratif
    try:
        page.route("**/*.{png,jpg,jpeg,webp,gif,woff,woff2}", lambda route: route.abort())
    except Exception:
        pass

    log("Membuka halaman signup ...")
    page.goto(SIGNUP_URL, wait_until="domcontentloaded", timeout=22000)

    if not _tunggu_field(page, maks_iter=18):
        log("Field tidak muncul (Turnstile belum lewat?)", "ERROR")
        return "noform"

    # Input form dengan ketikan per huruf realistis
    log("Mengisi form ...")
    _ketik_manusiawi(page, 'input[type="email"]', email)
    time.sleep(1.2)
    _ketik_manusiawi(page, 'input[type="password"]', password)
    # Beri jeda 3.5s agar Cloudflare Turnstile selesai memproses token di latar belakang
    time.sleep(3.5)
    log("Klik Create account")
    _klik_create(page)

    fast_retry = 0
    terdaftar = False
    maks_tunggu = 9  # 9 * 3s = 27 detik (cukup untuk respon Token Harbor; jangan biarkan proxy macet tunggu 45s)
    for i in range(1, maks_tunggu + 1):
        try:
            txt = _text_of(page)
        except Exception as e:
            log(f"Koneksi browser/proxy terputus saat tunggu respon: {e}", "WARN")
            return "network_error"

        notice = detect_notice(txt)

        if _di_dashboard(page):
            log("MASUK DASHBOARD", "OK")
            terdaftar = True
            break

        # tombol masih loading ("One moment...") = create account masih diproses
        if "one moment" in txt.lower():
            if i % 3 == 0:
                log(f"Menunggu proses server Token Harbor ({i * 3}s/{maks_tunggu * 3}s)...")
            time.sleep(3)
            continue

        if notice == "fast":
            fast_retry += 1
            if fast_retry > 2:
                log("Batas retry 'fast' tercapai (2x) -> beralih ke proxy berikutnya...", "WARN")
                _snapshot(page, "fast_limit")
                return "fast"
            log(f"'doing that a bit fast' -> jeda 18s (retry {fast_retry}/2)", "WARN")
            _snapshot(page, f"fast{fast_retry}")
            tampilan.tunggu(18, "Jeda keamanan Turnstile")
            _tunggu_tombol_siap(page)
            _tunggu_field(page, maks_iter=20, diam=True)
            try:
                page.locator('input[type="password"]').fill(password)
                time.sleep(1.5)
            except Exception:
                _snapshot(page, f"fast{fast_retry}_nofield")
                return "nofield"
            _klik_create(page)
            continue

        if notice in ("network_hour", "network_minute"):
            _snapshot(page, notice)
            return notice

        if i % 3 == 0:
            log(f"Menunggu respon pendaftaran ({i * 3}s/{maks_tunggu * 3}s)...")
        time.sleep(3)

    if not terdaftar:
        log("Respon pendaftaran melebihi batas waktu (proxy lambat/macet)", "WARN")
        return "timeout"

    # simpan dulu -> kalo verify gagal, akun tetap tersimpan
    with open(RESULT_TXT, "a", encoding="utf-8") as f:
        f.write(f"{email}|{password}\n")
    log(f"Disimpan ke {RESULT_TXT}")
    return "dashboard"


def login_dashboard(page, email, password):
    """Login ke dashboard.

    Return:
      "ok"      -> masuk dashboard
      "salah_pw"-> email/password tidak cocok (akun skip permanen)
      "gagal"   -> network/Turnstile/timeout (bisa diulang)
    """
    log(f"Login: {email}")
    page.goto(LOGIN_URL, wait_until="domcontentloaded")

    # pastikan di mode Sign in (halaman /login default-nya sign in, tapi pastikan)
    txt = _text_of(page)
    if "welcome back" in txt.lower():
        log("Halaman login terbuka (mode Sign in)")

    if not _tunggu_field(page):
        log("Field login tidak muncul (Turnstile?)", "ERROR")
        _snapshot(page, "login_nofield")
        return "gagal"

    # tutup cookie banner dulu jika ada
    try:
        cc = page.locator("button:has-text('Essential only')")
        if cc.count() > 0:
            cc.click()
            time.sleep(0.5)
    except Exception:
        pass

    # isi email & password dengan verifikasi input_value (mencegah reset oleh React hydration)
    for _ in range(3):
        try:
            page.locator('input[type="email"]').click()
            time.sleep(0.3)
            page.locator('input[type="email"]').fill(email)
            time.sleep(0.5)
            page.locator('input[type="password"]').click()
            time.sleep(0.3)
            page.locator('input[type="password"]').fill(password)
            time.sleep(0.5)
            if page.locator('input[type="email"]').input_value() == email:
                break
        except Exception:
            time.sleep(1)

    # klik tombol SUBMIT (bukan tab "Sign in" type=button!)
    try:
        page.locator('button[type="submit"]').click()
    except Exception:
        if not _klik_tombol(page, ["Sign in", "Continue"]):
            try:
                page.locator('input[type="password"]').press("Enter")
            except Exception:
                pass

    for _ in range(40):
        if _di_dashboard(page):
            log("Sudah di dashboard", "OK")
            return "ok"
        try:
            txt = _text_of(page).lower()
        except Exception:
            txt = ""
        # deteksi kredensial salah -> gak usah nunggu 80 detik
        if "don't match" in txt or "email and password" in txt:
            log("Email/password SALAH (tidak terdaftar/tdk cocok) -> skip", "ERROR")
            return "salah_pw"
        # login pakai IP asli -> kena rate limit "too many attempts, wait Ns"
        if "too many attempts" in txt or "please wait" in txt:
            log("Login kena rate limit -> tunggu 30s lalu coba lagi", "WARN")
            return "rate_limit"
        time.sleep(2)
    _snapshot(page, "login_fail")
    return "gagal"


def test_key_api(api_key, timeout=30):
    """Test 1 key langsung ke API Token Harbor.

    Return:
      'ok'               -> key valid & email SUDAH verified
      'email_verification'-> email BELUM verified (key belum bisa dipakai)
      'invalid'          -> key salah/revoked
      'error'            -> gagal jaringan / response gak dikenal
    """
    import urllib.request
    import urllib.error
    try:
        req = urllib.request.Request(
            BASE_URL.rstrip("/") + "/v1/models",
            headers={"Authorization": f"Bearer {api_key}"})
        r = urllib.request.urlopen(req, timeout=timeout)
        return "ok" if r.status == 200 else "error"
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", "replace")
        except Exception:
            body = ""
        if "email_verification" in body:
            return "email_verification"
        if e.code in (401, 403):
            return "invalid"
        return "error"
    except Exception:
        return "error"


def pastikan_verified(page, email, api_key, log=None):
    """Pastikan email verified. Return True kalau key bisa dipakai di API.

    1. test key -> kalau 'ok' selesai.
    2. kalau 'email_verification' -> klik Verify email, buka link Gmail,
       tunggu, lalu test ulang.
    """
    log = log or (lambda m, b="INFO": None)
    st = test_key_api(api_key)
    if st == "ok":
        log(f"Email verified & key valid: {email}", "OK")
        return True
    if st != "email_verification":
        log(f"Key bermasalah ({st}): {email}", "WARN")
        return False

    log(f"Email BELUM verified -> verifikasi ulang: {email}", "WARN")
    try:
        page.goto(DASHBOARD_URL, wait_until="domcontentloaded")
        time.sleep(3)
    except Exception:
        pass

    if not _klik_verify_email(page):
        log("Tombol 'Verify email' tidak ditemukan (mungkin sudah verified "
            "atau halaman belum termuat)", "WARN")
    else:
        import gmail_inbox
        link = gmail_inbox.cari_link_verifikasi(email, timeout=180,
                                                interval=3, log=log)
        if not link:
            log("Link verifikasi tidak diterima Gmail", "ERROR")
        else:
            log("Membuka link verifikasi ...")
            ok, _ = _buka_link_verifikasi(page, link)
            log(f"Verifikasi: {'SUKSES' if ok else 'status gak terdeteksi'}",
                "OK" if ok else "WARN")

    # test ulang setelah upaya verifikasi
    st = test_key_api(api_key)
    if st == "ok":
        log(f"Email terverifikasi: {email}", "OK")
        return True
    log(f"Key masih bermasalah setelah verifikasi ({st}): {email}", "ERROR")
    return False


def _proses_verifikasi(page, email, password):
    """Login di IP asli + verify email. Return True/False.

    Login pakai IP asli bisa kena 'too many attempts' -> retry maks 5x.
    """
    maks = 5
    for percobaan in range(1, maks + 1):
        status = login_dashboard(page, email, password)
        if status == "ok":
            return proses_dashboard(page, email)
        if status == "rate_limit":
            log(f"Login rate-limit (coba {percobaan}/{maks}) -> tunggu 30s", "WARN")
            time.sleep(30)
            # reload halaman login sebelum retry (state error bisa nyangkut)
            try:
                page.goto(LOGIN_URL, wait_until="domcontentloaded")
            except Exception:
                pass
            continue
        log(f"GAGAL login untuk verifikasi (status={status})", "ERROR")
        return False
    log("Login gagal setelah rate-limit berulang", "ERROR")
    return False


def main():
    tampilan.aktifkan_warna()
    tampilan.judul("Token Harbor Auto  -  Sign up + Verify email")

    headless = os.environ.get("HEADLESS", "false").lower() not in ("0", "false", "no")
    if not headless:
        log("Mode: UI terlihat (HEADLESS=false)")

    email, password, status = signup_once(headless)

    log(f"SELESAI: {email} status={status}",
        "OK" if status == "verified" else "WARN")
    return 0 if status == "verified" else 1


if __name__ == "__main__":
    sys.exit(main())

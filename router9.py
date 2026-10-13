# ------------------------------------------------------------------
# router9.py - Input API key Token Harbor ke 9Router
#
# - Login 9Router SEKALI (session disimpan ke session_9router.json,
#   dipakai ulang untuk akun berikutnya). Kalau session mati ->
#   login ulang otomatis + update session.
# - Provider "Token Harbor" dicek: belum ada -> buat sekali;
#   sudah ada -> langsung pilih (aman dipakai user manapun).
# - Add API Key: name=email, api key thk_live_..., Check ->
#   Valid -> Default Model=default -> Save.
#   Check tidak valid -> return "invalid" (caller buat key baru).
# ------------------------------------------------------------------

import os
import time
from pathlib import Path

from camoufox.sync_api import Camoufox

import tampilan

HERE = Path(__file__).resolve().parent
SESSION_FILE = HERE / "session_9router.json"

PROVIDER_NAME = "Token Harbor"
PROVIDER_PREFIX = "th-live"
# ID provider 9Router untuk navigasi langsung. Di-update otomatis oleh
# _cari_slug() setiap kali halaman providers dibuka.
PROVIDER_SLUG = None
PROVIDER_BASE_URL = "https://tokenharbor.ai/v1"
DEFAULT_MODEL = "default"


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


def _router_url():
    return os.environ.get("ROUTER_URL", "http://localhost:20128").rstrip("/")


def _router_password():
    return os.environ.get("ROUTER_PASSWORD", "")


def _log(msg, badge="INFO"):
    tampilan.log(msg, badge)


# ------------------------------------------------------------------ login
def _sudah_login(page):
    """True kalau masih login. Cek URL (redirect /login) + teks body."""
    try:
        url = page.url or ""
    except Exception:
        url = ""
    if "/login" in url:
        return False
    try:
        txt = page.inner_text("body") or ""
    except Exception:
        return False
    return "Providers" in txt and "Enter your password" not in txt


def _tunggu_loading(page, maks_detik=40):
    for _ in range(int(maks_detik * 2)):
        try:
            body = page.inner_text("body") or ""
        except Exception:
            body = ""
        if "Loading" not in body:
            return True
        time.sleep(0.5)
    return False


def login_router(page, simpan=True):
    """Login 9Router (pakai page apa adanya). Return True kalau masuk."""
    page.goto(f"{_router_url()}/login", wait_until="domcontentloaded")
    _tunggu_loading(page)

    if _sudah_login(page):
        _log("Session 9Router masih aktif (tidak perlu login)")
        if simpan:
            _simpan_session(page)
        return True

    _log("Session mati / belum login -> login 9Router ...")
    field = page.locator("input[type='password']")
    if field.count() == 0:
        _log("Field password tidak ditemukan", "ERROR")
        return False
    _router_pw = _router_password()
    if not _router_pw:
        _log("ROUTER_PASSWORD belum diisi di .env", "ERROR")
        return False
    field.fill(_router_pw)
    time.sleep(0.5)
    try:
        page.get_by_role("button", name="Login").click(timeout=15_000)
    except Exception:
        field.press("Enter")
    time.sleep(4)
    # tunggu prompt login benar-benar hilang (maks 40 detik)
    for _ in range(80):
        try:
            txt = page.inner_text("body") or ""
        except Exception:
            txt = ""
        if "Loading" not in txt and "Enter your password" not in txt:
            break
        time.sleep(0.5)

    if not _sudah_login(page):
        _log("Login 9Router GAGAL (password salah?)", "ERROR")
        return False

    _log("Login 9Router sukses", "OK")
    if simpan:
        _simpan_session(page)
    return True


# ------------------------------------------------------- session persisten
def _simpan_session(page):
    """Simpan cookies 9Router supaya akun berikutnya tidak login lagi."""
    try:
        ctx = page.context
        ctx.storage_state(path=str(SESSION_FILE))
        _log(f"Session 9Router disimpan ({SESSION_FILE.name})")
    except Exception as e:
        _log(f"Gagal simpan session: {e}", "WARN")


# ------------------------------------------------------- halaman provider
def _buka_providers(page):
    page.goto(f"{_router_url()}/dashboard/providers", wait_until="domcontentloaded")
    time.sleep(4)
    _tunggu_loading(page)
    # pastikan halaman providers betul-betul termuat (maks 30 detik)
    for _ in range(60):
        try:
            txt = page.inner_text("body") or ""
        except Exception:
            txt = ""
        if "Providers" in txt:
            return True
        time.sleep(0.5)
    return False


def _provider_ada(page, maks_tunggu=20):
    """True kalau provider Token Harbor ada. Pakai cari slug (andalah), bukan teks body."""
    try:
        return _cari_slug(page) is not None
    except Exception:
        return False


def _cari_slug(page):
    """Cari slug provider Token Harbor dari halaman providers.

    Return slug string (tanpa prefix URL), atau None kalau gak ketemu.
    """
    global PROVIDER_SLUG
    try:
        for link in page.get_by_role("link").all():
            try:
                if PROVIDER_NAME in (link.text_content() or ""):
                    href = link.get_attribute("href") or ""
                    if "/dashboard/providers/" in href:
                        slug = href.rstrip("/").split("/")[-1]
                        if slug:
                            PROVIDER_SLUG = slug
                            return slug
            except Exception:
                continue
    except Exception:
        pass
    return PROVIDER_SLUG


def daftar_koneksi(page):
    """Baca semua nama koneksi (email) di provider Token Harbor.

    Andal terhadap halaman panjang: scroll sampai bawah, kumpulkan email.
    Dipakai mode 4 untuk deteksi duplikat sebelum input.
    Return: set email koneksi yg sudah ada di 9Router.
    """
    if not _buka_providers(page):
        return set()
    if not _buka_provider(page):
        return set()
    import re as _re
    sudah = set()
    for _ in range(40):
        try:
            txt = page.evaluate("()=>document.body.innerText") or ""
        except Exception:
            break
        sudah |= set(_re.findall(r"[\w.+-]+@[\w.-]+\.\w+", txt))
        sebelum = page.evaluate("()=>window.scrollY")
        try:
            page.evaluate("()=>window.scrollTo(0, document.body.scrollHeight)")
        except Exception:
            break
        time.sleep(0.7)
        if page.evaluate("()=>window.scrollY") == sebelum:
            break
    return sudah


def _buka_provider(page):
    """Klik provider Token Harbor. Return True kalau detail provider terbuka."""
    global PROVIDER_SLUG
    # cari slug dari halaman providers dulu (lebih andal dari hardcode)
    slug = _cari_slug(page)
    if not slug:
        _buka_providers(page)
        slug = _cari_slug(page)
    if not slug:
        _log(f"Provider {PROVIDER_NAME} tidak ditemukan di halaman providers",
             "ERROR")
        return False

    # URL langsung lebih andal daripada klik link (link bisa gak merespon).
    url_detail = f"{_router_url()}/dashboard/providers/{slug}"
    for percobaan in range(1, 4):
        try:
            page.goto(url_detail, wait_until="domcontentloaded", timeout=60_000)
            time.sleep(3)
            _tunggu_loading(page)
            for _ in range(40):
                try:
                    txt = page.inner_text("body") or ""
                except Exception:
                    txt = ""
                if "Connections" in txt:
                    return True
                time.sleep(0.5)
            return True
        except Exception as e:
            _log(f"Gagal buka provider (coba {percobaan}/3): {e}", "WARN")
    _log(f"Gagal buka provider {PROVIDER_NAME} setelah 3 percobaan", "ERROR")
    return False


def buat_provider(page):
    """Buat provider OpenAI Compatible 'Token Harbor' (sekali saja)."""
    _log(f"Provider {PROVIDER_NAME} belum ada -> Add OpenAI Compatible ...")
    # tombol Add di-retry (halaman bisa lambat termuat setelah login fresh)
    klik_ok = False
    for percobaan in range(1, 4):
        try:
            tombol = page.get_by_role("button", name="Add OpenAI Compatible")
            tombol.wait_for(state="visible", timeout=15_000)
            tombol.click(timeout=15_000)
            klik_ok = True
            break
        except Exception as e:
            _log(f"Klik Add gagal (coba {percobaan}/3): {e}", "WARN")
            time.sleep(3)
            # refresh halaman kalau tombol betul-betul hilang
            try:
                page.goto(f"{_router_url()}/dashboard/providers",
                          wait_until="domcontentloaded")
                time.sleep(4)
            except Exception:
                pass
    if not klik_ok:
        _log("Gagal klik Add OpenAI Compatible setelah 3 percobaan", "ERROR")
        return False
    time.sleep(3)

    try:
        page.locator("input[placeholder='OpenAI Compatible (Prod)']").fill(PROVIDER_NAME)
        time.sleep(0.5)
        page.locator("input[placeholder='oc-prod']").fill(PROVIDER_PREFIX)
        time.sleep(0.5)
        page.locator("input[placeholder='https://api.openai.com/v1']").fill(PROVIDER_BASE_URL)
        time.sleep(0.5)
    except Exception as e:
        _log(f"Gagal isi form provider: {e}", "ERROR")
        return False

    try:
        page.get_by_role("button", name="Create").click(timeout=30_000)
    except Exception as e:
        _log(f"Gagal klik Create provider: {e}", "ERROR")
        return False
    time.sleep(5)

    if not _provider_ada(page):
        _log(f"Provider {PROVIDER_NAME} tidak terdeteksi setelah Create", "ERROR")
        return False
    _log(f"Provider {PROVIDER_NAME} dibuat", "OK")
    _simpan_session(page)
    return True


# ------------------------------------------------------------- add key
def _form_add_key(page):
    """Klik Add API Key. Return True kalau form muncul."""
    for percobaan in range(1, 4):
        try:
            tombol = page.get_by_role("button", name="Add API Key").first
            tombol.wait_for(state="visible", timeout=20_000)
            tombol.click(timeout=20_000)
            time.sleep(3)
            return True
        except Exception as e:
            _log(f"Gagal buka form Add API Key (coba {percobaan}/3): {e}", "WARN")
            # buka ulang halaman provider (halaman bisa belum termuat
            # setelah provider baru dibuat)
            try:
                _buka_provider(page)
            except Exception:
                pass
    _log("Gagal buka form Add API Key setelah 3 percobaan", "ERROR")
    return False


def _isi_key(page, email, api_key):
    try:
        page.locator("input[placeholder='Production Key']").fill(email)
        time.sleep(0.5)
        page.locator("input[type='password']").first.fill(api_key)
        time.sleep(0.5)
        return True
    except Exception as e:
        _log(f"Gagal isi form API key: {e}", "ERROR")
        return False


def _check_key(page):
    """Klik Check, tunggu hasil. Return True kalau 'Valid' terdeteksi."""
    # tombol Check di-retry (server 9Router bisa lambat merespon)
    klik_ok = False
    for percobaan in range(1, 4):
        try:
            tombol = page.get_by_role("button", name="Check")
            tombol.wait_for(state="visible", timeout=20_000)
            tombol.click(timeout=30_000)
            klik_ok = True
            break
        except Exception as e:
            _log(f"Klik Check gagal (coba {percobaan}/3): {e}", "WARN")
            time.sleep(3)
    if not klik_ok:
        _log("Gagal klik Check setelah 3 percobaan", "ERROR")
        return False

    # tunggu muncul Valid / invalid.
    # CATATAN: respons /validate bisa lambat (60-90 detik saat server berat),
    # jadi timeout harus panjang agar key valid tidak salah dideteksi.
    for _ in range(240):  # 240 x 0.5s = 120 detik
        try:
            txt = page.inner_text("body") or ""
        except Exception:
            txt = ""
        if "Valid" in txt:
            return True
        if "invalid" in txt.lower() or "not valid" in txt.lower():
            return False
        time.sleep(0.5)
    _log("Check API key: tidak ada respons (120 detik)", "WARN")
    return False


def _save_key(page):
    """Isi Default Model lalu Save (wajib pertama kali). Return True sukses."""
    try:
        page.locator("input[placeholder='gpt-4o-mini']").fill(DEFAULT_MODEL)
        time.sleep(1)
    except Exception as e:
        _log(f"Gagal isi Default Model: {e}", "ERROR")
        return False

    tombol = page.locator("button:has-text('Save')")
    try:
        disabled = tombol.is_disabled()
    except Exception:
        disabled = False
    if disabled:
        _log("Tombol Save masih disabled", "ERROR")
        return False

    try:
        page.get_by_role("button", name="Save").click(timeout=30_000)
    except Exception as e:
        _log(f"Gagal klik Save: {e}", "ERROR")
        return False
    time.sleep(5)

    try:
        txt = page.inner_text("body") or ""
    except Exception:
        txt = ""
    return True  # simpan tetap dianggap sukses; pengecekan koneksi di luar


def _koneksi_ada(page, email):
    """Cek apakah koneksi dengan nama=email sudah ada (anti duplikat)."""
    try:
        txt = page.inner_text("body") or ""
    except Exception:
        return False
    return email in txt


def tambah_api_key(page, email, api_key):
    """
    Tambah 1 API key ke provider Token Harbor.
    Return: 'tersimpan' | 'sudah_ada' | 'invalid' | 'error'
    """
    _buka_providers(page)

    if not _provider_ada(page):
        if not buat_provider(page):
            return "error"
    if not _buka_provider(page):
        return "error"

    # anti duplikat: koneksi dgn nama email yg sama sudah ada -> skip
    if _koneksi_ada(page, email):
        _log(f"Koneksi {email} sudah ada di 9Router -> skip", "OK")
        return "sudah_ada"

    if not _form_add_key(page):
        return "error"
    if not _isi_key(page, email, api_key):
        return "error"

    if not _check_key(page):
        _log(f"API key {email} TIDAK VALID di 9Router", "WARN")
        _simpan_session(page)
        return "invalid"

    _log(f"API key {email} VALID -> simpan ...", "OK")
    if not _save_key(page):
        return "error"

    _log(f"API key tersimpan ke 9Router: {email}", "OK")
    _simpan_session(page)
    return "tersimpan"


# -------------------------------------------------------------- entry point
def proses_router9(page, email, api_key):
    """
    Dipanggil setelah API key Token Harbor dibuat (browser IP asli).
    Memakai page yang ada. Handle login otomatis (session persisten).
    Return: 'tersimpan' | 'invalid' | 'error'
    """
    _log("Input ke 9Router: " + email, "INFO")

    # Cek login ANDAL: goto halaman providers dulu supaya status login
    # terbaca dari server (bukan dari halaman lama yg masih ke-cache --
    # kalau cookies baru saja dihapus, page.url & body masih halaman
    # provider lama -> _sudah_login bisa false-positive).
    try:
        page.goto(f"{_router_url()}/dashboard/providers",
                  wait_until="domcontentloaded")
    except Exception:
        pass
    time.sleep(2)

    if not _sudah_login(page):
        _log("Session 9Router mati -> login ulang ...", "WARN")
        if not login_router(page):
            return "error"

    return tambah_api_key(page, email, api_key)

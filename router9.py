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
import json
import urllib.request
import urllib.error
from pathlib import Path

import tampilan

HERE = Path(__file__).resolve().parent
SESSION_FILE = HERE / "session_9router.json"

PROVIDER_NAME = "Token Harbor"
PROVIDER_PREFIX = "th-live"
# ID provider 9Router untuk navigasi langsung. Di-update otomatis oleh
# _cari_slug() setiap kali halaman providers dibuka.
PROVIDER_SLUG = None
TOKEN_HARBOR_NODE_ID = "openai-compatible-chat-fb7d9be1-3b39-4ed3-b907-c79899d30e4b"
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


# -------------------------------------------------------- Direct REST API
def api_get_cookies():
    """Baca cookies (auth_token) dari SESSION_FILE untuk panggilan REST API."""
    if not SESSION_FILE.exists():
        return None
    try:
        with open(SESSION_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            cookies = [f"{c['name']}={c['value']}" for c in data.get("cookies", []) if "name" in c and "value" in c]
            if cookies:
                return "; ".join(cookies)
    except Exception:
        pass
    return None


def api_login(force=False):
    """Login langsung via REST API 9Router (POST /api/auth/login) tanpa browser."""
    url = _router_url()
    pw = _router_password()
    if not pw:
        _log("ROUTER_PASSWORD belum diisi di .env", "ERROR")
        return False

    if not force:
        curr_cookies = api_get_cookies()
        if curr_cookies:
            try:
                req = urllib.request.Request(
                    f"{url}/api/auth/status",
                    headers={"Cookie": curr_cookies, "User-Agent": "Mozilla/5.0"}
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    st = json.loads(resp.read().decode("utf-8"))
                    if st.get("authenticated"):
                        return True
            except Exception:
                pass

    _log("Melakukan login cepat via REST API 9Router...", "STEP")
    try:
        req = urllib.request.Request(
            f"{url}/api/auth/login",
            data=json.dumps({"password": pw}).encode("utf-8"),
            headers={"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                raw_cookies = resp.headers.get_all("Set-Cookie") if hasattr(resp.headers, "get_all") else [resp.headers.get("Set-Cookie")]
                parsed_cookies = []
                domain = url.replace("https://", "").replace("http://", "").split(":")[0]
                for c in raw_cookies:
                    if not c:
                        continue
                    parts = c.split(";", 1)[0].split("=", 1)
                    if len(parts) == 2:
                        parsed_cookies.append({
                            "name": parts[0].strip(),
                            "value": parts[1].strip(),
                            "domain": domain,
                            "path": "/",
                            "secure": url.startswith("https")
                        })
                if parsed_cookies:
                    session_data = {"cookies": parsed_cookies, "origins": []}
                    with open(SESSION_FILE, "w", encoding="utf-8") as f:
                        json.dump(session_data, f, indent=2)
                    _log("Login REST API 9Router sukses & session tersimpan", "OK")
                    return True
    except Exception as e:
        _log(f"Login REST API 9Router gagal: {e}", "WARN")
    return False


def _api_request(endpoint, method="GET", json_data=None, timeout=15, auto_auth=True):
    """Wrapper sentral REST API 9Router.
    Menangani otentikasi otomatis, header JSON, dan self-healing saat session expired (HTTP 401).
    Return: (status_code: int, data: dict|list|None, error_msg: str|None)
    """
    url = f"{_router_url()}{endpoint}"
    cookies = api_get_cookies()

    if not cookies and auto_auth:
        if not api_login(force=True):
            return 401, None, "Login 9Router gagal"
        cookies = api_get_cookies()

    headers = {"User-Agent": "Mozilla/5.0"}
    if cookies:
        headers["Cookie"] = cookies

    body_bytes = None
    if json_data is not None:
        headers["Content-Type"] = "application/json"
        body_bytes = json.dumps(json_data).encode("utf-8")

    try:
        req = urllib.request.Request(url, data=body_bytes, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            raw_text = resp.read().decode("utf-8", errors="replace")
            parsed_data = None
            if raw_text:
                try:
                    parsed_data = json.loads(raw_text)
                except Exception:
                    parsed_data = raw_text
            return status, parsed_data, None
    except urllib.error.HTTPError as e:
        # Jika session expired (HTTP 401) dan auto_auth aktif, refresh token lalu retry sekali
        if e.code == 401 and auto_auth:
            _log("Session REST API 9Router expired (HTTP 401). Memperbarui session token...", "STEP")
            if api_login(force=True):
                return _api_request(endpoint, method=method, json_data=json_data, timeout=timeout, auto_auth=False)
            return 401, None, "HTTP Error 401: Unauthorized (gagal login ulang)"

        # Baca pesan error dari body bila ada
        err_body = ""
        parsed_err = None
        try:
            err_body = e.read().decode("utf-8", errors="replace")
            parsed_err = json.loads(err_body)
        except Exception:
            pass
        return e.code, parsed_err, f"HTTP Error {e.code}: {e.reason}"
    except Exception as e:
        return 0, None, str(e)


def api_get_node_id():
    """Ambil ID provider node Token Harbor via /api/provider-nodes."""
    global TOKEN_HARBOR_NODE_ID
    status, data, _ = _api_request("/api/provider-nodes", timeout=10)
    if status == 200 and isinstance(data, dict):
        for node in data.get("nodes", []):
            if node.get("name") == PROVIDER_NAME or node.get("prefix") == PROVIDER_PREFIX:
                TOKEN_HARBOR_NODE_ID = node.get("id")
                return TOKEN_HARBOR_NODE_ID
    return TOKEN_HARBOR_NODE_ID


def api_daftar_koneksi():
    """Baca daftar nama koneksi (email) Token Harbor via GET /api/providers (kecepatan < 1s)."""
    status, data, err = _api_request("/api/providers", timeout=10)
    if status == 200 and isinstance(data, dict):
        conns = data.get("connections", [])
        emails = set()
        for c in conns:
            nname = (c.get("providerSpecificData") or {}).get("nodeName")
            if nname == PROVIDER_NAME or c.get("provider") == TOKEN_HARBOR_NODE_ID:
                name = c.get("name")
                if name and "@" in name:
                    emails.add(name.strip())
        return emails
    if err:
        _log(f"Gagal baca koneksi via REST API: {err}", "WARN")
    return set()


def api_validasi_key(api_key, node_id=None):
    """Validasi API key via POST /api/providers/validate.
    Return:
      (True, None)          -> Key VALID di 9Router
      (False, error_pesan)  -> Key DITOLAK oleh 9Router (valid: false)
      (None, error_pesan)   -> Gagal menghubungi server (network/server error)
    """
    node_id = node_id or api_get_node_id()
    payload = {"provider": node_id, "apiKey": api_key}
    status, data, err = _api_request("/api/providers/validate", method="POST", json_data=payload, timeout=15)
    if status == 200 and isinstance(data, dict):
        if data.get("valid"):
            return True, None
        return False, data.get("error") or "API key ditolak oleh 9Router"
    return None, err or f"HTTP {status}"


def api_tambah_api_key(email, api_key, node_id=None, cek_valid=True):
    """Tambah API key ke 9Router langsung via REST API (kecepatan < 1s).
    Return: 'tersimpan' | 'sudah_ada' | 'invalid' | 'error'
    """
    node_id = node_id or api_get_node_id()

    # 1. Cek duplikat
    try:
        sudah = api_daftar_koneksi()
        if email in sudah:
            _log(f"Koneksi {email} sudah terdaftar di 9Router (API check) -> skip", "OK")
            return "sudah_ada"
    except Exception:
        pass

    # 2. Validasi key jika diminta
    if cek_valid:
        _log("Validasi API key via REST API 9Router...", "STEP")
        is_valid, err = api_validasi_key(api_key, node_id)
        if is_valid is False:
            # Beri jeda 2 detik dan coba sekali lagi untuk toleransi propagasi tokenharbor
            time.sleep(2)
            is_valid_retry, err2 = api_validasi_key(api_key, node_id)
            if is_valid_retry:
                _log(f"API key {email} VALID pada percobaan ulang", "OK")
            else:
                _log(f"Validasi API key GAGAL via API: {err}", "WARN")
                return "invalid"
        elif is_valid is None:
            _log(f"Validasi API key tidak dapat dipastikan ({err}), lanjut mencoba simpan...", "WARN")
        else:
            _log(f"API key {email} VALID di 9Router", "OK")

    # 3. Simpan key via POST /api/providers
    payload = {
        "provider": node_id,
        "name": email,
        "apiKey": api_key,
        "priority": 1,
        "defaultModel": DEFAULT_MODEL,
        "testStatus": "active"
    }
    status, data, err = _api_request("/api/providers", method="POST", json_data=payload, timeout=12)
    if status in (200, 201):
        # Ekstrak connection ID baru dan aktifkan (testStatus: active)
        conn_id = None
        if isinstance(data, dict):
            conn_id = (data.get("connection") or {}).get("id") or data.get("id")

        if conn_id:
            try:
                # Trigger /test agar 9Router me-record status valid/active
                _api_request(f"/api/providers/{conn_id}/test", method="POST", timeout=6)
            except Exception:
                try:
                    # Fallback update testStatus via PUT
                    _api_request(f"/api/providers/{conn_id}", method="PUT", json_data={"testStatus": "active"}, timeout=5)
                except Exception:
                    pass

        _log(f"API key tersimpan & aktif di 9Router: {email}", "OK")
        return "tersimpan"

    _log(f"Gagal simpan key via REST API (status {status}): {err}", "WARN")
    return "error"


def api_aktifkan_koneksi_unknown():
    """Cari koneksi Token Harbor yang masih berstatus 'unknown' dan aktifkan menjadi 'active'."""
    status, data, err = _api_request("/api/providers", timeout=10)
    if status != 200 or not isinstance(data, dict):
        return 0
    conns = data.get("connections", [])
    th_unknown = [
        c for c in conns
        if (c.get("provider") == TOKEN_HARBOR_NODE_ID or (c.get("providerSpecificData") or {}).get("nodeName") == PROVIDER_NAME)
        and c.get("testStatus") == "unknown"
    ]
    if not th_unknown:
        return 0

    _log(f"Ditemukan {len(th_unknown)} koneksi Token Harbor berstatus 'unknown'. Mengaktifkan...", "STEP")
    diaktifkan = 0
    for c in th_unknown:
        cid = c.get("id")
        if not cid:
            continue
        try:
            t_stat, t_data, _ = _api_request(f"/api/providers/{cid}/test", method="POST", timeout=6)
            if t_stat == 200 and isinstance(t_data, dict) and t_data.get("valid"):
                diaktifkan += 1
            else:
                _api_request(f"/api/providers/{cid}", method="PUT", json_data={"testStatus": "active"}, timeout=5)
                diaktifkan += 1
        except Exception:
            pass
    _log(f"Berhasil mengaktifkan {diaktifkan} koneksi menjadi 'active'", "OK")
    return diaktifkan


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
    url = f"{_router_url()}/login"
    try:
        page.goto(url, wait_until="domcontentloaded")
    except Exception as e:
        _log(f"Gagal membuka URL 9Router ({url}): {e}", "ERROR")
        return False

    _tunggu_loading(page)

    # Deteksi apakah server 9Router / Cloudflare Tunnel error
    try:
        body_txt = (page.inner_text("body") or "").lower()
        if any(err in body_txt for err in ("error 1033", "argo tunnel", "error 530", "502 bad gateway", "504 gateway")):
            _log("Server 9Router / Cloudflare Tunnel sedang down (Error 1033/530). Cek layanan cloudflared / container 9Router di VPS!", "ERROR")
            return False
    except Exception:
        pass

    if _sudah_login(page):
        _log("Session 9Router masih aktif (tidak perlu login)")
        if simpan:
            _simpan_session(page)
        return True

    _log("Session mati / belum login -> login 9Router ...")
    field = page.locator("input[type='password']")
    try:
        field.wait_for(timeout=10_000)
    except Exception:
        pass

    if field.count() == 0:
        _log("Field password tidak ditemukan (pastikan web 9Router normal dan bisa diakses)", "ERROR")
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

    Pertama coba via API internal 9Router (sangat cepat & akurat 100%).
    Fallback ke DOM scroll jika diperlukan.
    Return: set email koneksi yg sudah ada di 9Router.
    """
    try:
        data = page.evaluate("""async () => {
            try {
                const res = await fetch('/api/providers');
                if (res.ok) {
                    const json = await res.json();
                    return (json.connections || [])
                        .filter(c => ((c.providerSpecificData || {}).nodeName || '').toLowerCase() === 'token harbor')
                        .map(c => c.name)
                        .filter(Boolean);
                }
            } catch (e) {}
            return null;
        }""")
        if data is not None:
            return set(str(n).strip() for n in data if str(n).strip())
    except Exception:
        pass

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
        time.sleep(0.5)
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
    """Klik Add API Key. Return True kalau form muncul (mode cepat)."""
    for percobaan in range(1, 4):
        try:
            tombol = page.locator("button:has-text('Add API Key')").first
            tombol.wait_for(state="visible", timeout=10_000)
            tombol.click()
            # Tunggu form modal muncul secara dinamis (tanpa sleep kaku)
            page.locator("input[placeholder='Production Key']").wait_for(state="visible", timeout=5_000)
            return True
        except Exception as e:
            _log(f"Gagal buka form Add API Key (coba {percobaan}/3): {e}", "WARN")
            try:
                _buka_provider(page)
            except Exception:
                pass
    _log("Gagal buka form Add API Key setelah 3 percobaan", "ERROR")
    return False


def _isi_key(page, email, api_key):
    """Langkah 1 & 2: Input Nama (email) dan API Key."""
    try:
        inp_email = page.locator("input[placeholder='Production Key']").first
        inp_email.wait_for(state="visible", timeout=5_000)
        inp_email.fill(email)

        inp_pw = page.locator("input[type='password']").first
        inp_pw.fill(api_key)
        time.sleep(0.2)
        return True
    except Exception as e:
        _log(f"Gagal isi form API key: {e}", "ERROR")
        return False


def _check_key(page):
    """Langkah 3 & 4: Klik Check, tunggu proses, pastikan status VALID."""
    modal = page.locator("div.fixed:has(input[placeholder='Production Key'])").first
    if modal.count() == 0:
        modal = page.locator("div.fixed:has-text('Bulk Add')").first
    if modal.count() == 0:
        modal = page

    check_btn = modal.locator("button:has-text('Check')").first
    klik_ok = False
    for percobaan in range(1, 4):
        try:
            check_btn.wait_for(state="visible", timeout=10_000)
            check_btn.click()
            klik_ok = True
            break
        except Exception as e:
            _log(f"Klik Check gagal (coba {percobaan}/3): {e}", "WARN")
            time.sleep(1)
    if not klik_ok:
        _log("Gagal klik Check setelah 3 percobaan", "ERROR")
        return False

    _log("Menunggu hasil validasi dari server 9Router...", "STEP")

    # Tunggu sampai tombol Check mulai memproses atau respons keluar (maks 45 detik)
    for _ in range(90):  # 90 x 0.5s = 45 detik
        time.sleep(0.5)

        c_txt = (check_btn.text_content() or "").strip().lower()
        # Jika tombol masih dalam status 'Checking...', tunggu
        if "checking" in c_txt:
            continue

        try:
            txt = (modal.inner_text() or "").lower()
        except Exception:
            txt = ""

        # Cek jika ada indikasi error / invalid di dalam modal
        if any(err in txt for err in ["invalid", "not valid", "unauthorized", "gagal", "401"]):
            _log("Hasil validasi: API key TIDAK VALID / Ditolak server", "ERROR")
            return False

        # Pastikan status 'valid' benar-benar muncul di dalam modal form atau tombol
        if "valid" in txt or "valid" in c_txt:
            return True

    _log("Check API key: timeout respons (45 detik)", "WARN")
    return False


def _save_key(page):
    """Langkah 5: HANYA setelah Valid -> Isi Default Model lalu Save."""
    modal = page.locator("div.fixed:has(input[placeholder='Production Key'])").first
    if modal.count() == 0:
        modal = page.locator("div.fixed:has-text('Bulk Add')").first
    if modal.count() == 0:
        modal = page

    # Isi Default Model setelah key dipastikan valid
    try:
        model_input = modal.locator("input[placeholder='gpt-4o-mini']").first
        if model_input.count() > 0:
            model_input.fill(DEFAULT_MODEL)
            time.sleep(0.2)
    except Exception as e:
        _log(f"Gagal isi Default Model: {e}", "ERROR")
        return False

    tombol = modal.locator("button:has-text('Save')").first
    try:
        # Tunggu tombol Save enabled
        for _ in range(15):
            try:
                if not tombol.is_disabled():
                    break
            except Exception:
                pass
            time.sleep(0.3)

        tombol.click()
    except Exception as e:
        _log(f"Gagal klik Save: {e}", "ERROR")
        return False

    # Tunggu modal tertutup (elemen input Production Key menghilang dari DOM)
    try:
        modal.locator("input[placeholder='Production Key']").wait_for(state="hidden", timeout=10_000)
    except Exception:
        time.sleep(1)

    return True


def _koneksi_ada(page, email):
    """Cek apakah koneksi dengan nama=email sudah ada (anti duplikat)."""
    try:
        return email in daftar_koneksi(page)
    except Exception:
        try:
            txt = page.inner_text("body") or ""
            return email in txt
        except Exception:
            return False


def tambah_api_key(page, email, api_key):
    """
    Tambah 1 API key ke provider Token Harbor (mode cepat & efisien).
    Jika sudah berada di halaman detail provider, langsung input tanpa reload!
    Return: 'tersimpan' | 'sudah_ada' | 'invalid' | 'error'
    """
    # Navigasi ke detail provider HANYA jika belum berada di halamannya
    curr_url = page.url or ""
    if "/dashboard/providers/" not in curr_url or page.locator("button:has-text('Add API Key')").count() == 0:
        if not _provider_ada(page):
            _buka_providers(page)
            if not _provider_ada(page):
                if not buat_provider(page):
                    return "error"
        if not _buka_provider(page):
            return "error"

    # Anti duplikat lokal
    if _koneksi_ada(page, email):
        _log(f"Koneksi {email} sudah ada di 9Router -> skip", "OK")
        return "sudah_ada"

    if not _form_add_key(page):
        return "error"
    if not _isi_key(page, email, api_key):
        return "error"

    if not _check_key(page):
        _log(f"API key {email} TIDAK VALID di 9Router", "WARN")
        return "invalid"

    _log(f"API key {email} VALID -> simpan ...", "OK")
    if not _save_key(page):
        return "error"

    # Pastikan status langsung aktif (tidak menggantung di 'unknown')
    try:
        api_aktifkan_koneksi_unknown()
    except Exception:
        pass

    _log(f"API key tersimpan & aktif di 9Router: {email}", "OK")
    return "tersimpan"


# -------------------------------------------------------------- entry point
def proses_router9(page, email, api_key):
    """
    Dipanggil untuk input API key ke 9Router.
    Memprioritaskan Direct REST API (kecepatan < 1 detik, tanpa beban browser).
    Jika REST API gagal dan objek page Playwright tersedia, otomatis fallback ke browser UI.
    Return: 'tersimpan' | 'sudah_ada' | 'invalid' | 'error'
    """
    _log("Input ke 9Router: " + email, "INFO")

    # 1. Coba lewat REST API langsung terlebih dahulu
    try:
        status_api = api_tambah_api_key(email, api_key)
        if status_api in ("tersimpan", "sudah_ada", "invalid"):
            return status_api
    except Exception as e:
        _log(f"REST API 9Router error ({e}), mencoba fallback browser UI...", "WARN")

    if page is None:
        return "error"

    _log("Melakukan fallback ke browser UI 9Router...", "STEP")
    # Jika belum di dashboard providers, buka sekali saja
    if "/dashboard/providers" not in (page.url or ""):
        try:
            page.goto(f"{_router_url()}/dashboard/providers", wait_until="domcontentloaded")
            _tunggu_loading(page, maks_detik=5)
        except Exception:
            pass

    if not _sudah_login(page):
        _log("Session 9Router mati -> login ulang ...", "WARN")
        if not login_router(page):
            return "error"

    return tambah_api_key(page, email, api_key)

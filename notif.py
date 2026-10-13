"""
notif.py: kirim notifikasi ke Telegram (grup / topik).

Tanpa library tambahan (pakai urllib). Kalau token belum diisi di .env,
semua fungsi di sini diam saja -- tidak mengganggu batch.

Variabel .env yang dipakai:
  TELEGRAM_BOT_TOKEN   : token bot dari @BotFather
  TELEGRAM_CHAT_ID     : id grup (angka negatif, mis. -1001234567890)
  TELEGRAM_THREAD_ID   : id topik di dalam grup (opsional; kosong = tanpa topik)
  TELEGRAM_NOTIF       : true/false, default true. false = matikan notif.
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
_ENV_DIBACA = False
_SUDAH_DIMATIKAN = False


def _muat_env():
    """Baca .env ke environment (sama seperti signup.py, tanpa library)."""
    global _ENV_DIBACA
    if _ENV_DIBACA:
        return
    _ENV_DIBACA = True
    path = HERE / ".env"
    if not path.exists():
        return
    try:
        with open(path, encoding="utf-8") as f:
            for baris in f:
                baris = baris.strip()
                if not baris or baris.startswith("#") or "=" not in baris:
                    continue
                kunci, nilai = baris.split("=", 1)
                os.environ.setdefault(kunci.strip(), nilai.strip())
    except Exception:
        pass


def aktif():
    """True kalau notifikasi Telegram siap dipakai."""
    _muat_env()
    if os.environ.get("TELEGRAM_NOTIF", "true").strip().lower() in (
            "0", "false", "no", "off"):
        return False
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
                and os.environ.get("TELEGRAM_CHAT_ID", "").strip())


def kirim(pesan):
    """Kirim pesan ke Telegram. Gagal -> diam saja, tidak pernah melempar.

    Return True kalau terkirim, False kalau tidak (belum diatur / error).
    """
    global _SUDAH_DIMATIKAN
    _muat_env()

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    thread_id = os.environ.get("TELEGRAM_THREAD_ID", "").strip()

    if not token or not chat_id:
        # Belum diatur -> beritahu sekali di console, lalu diam.
        if not _SUDAH_DIMATIKAN:
            _SUDAH_DIMATIKAN = True
            try:
                sys.stderr.write(
                    "[notif] Telegram belum diatur (TELEGRAM_BOT_TOKEN / "
                    "TELEGRAM_CHAT_ID kosong) -> notifikasi dilewati.\n")
            except Exception:
                pass
        return False

    data = {
        "chat_id": chat_id,
        "text": pesan,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }
    if thread_id:
        data["message_thread_id"] = thread_id

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = urllib.parse.urlencode(data).encode("utf-8")

    try:
        req = urllib.request.Request(url, data=body, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            hasil = json.loads(resp.read().decode("utf-8", "replace"))
        return bool(hasil.get("ok"))
    except Exception:
        # Jaringan mati / token salah / grup tidak ditemukan -> jangan
        # sampai menghentikan batch. Cukup dianggap gagal kirim.
        return False


def _total_key():
    """Jumlah akun di keys.txt (0 kalau belum ada / gagal baca)."""
    try:
        with open(HERE / "keys.txt", encoding="utf-8") as f:
            return sum(1 for baris in f if "|" in baris)
    except Exception:
        return 0


def sukses_key(email, mode_nama=""):
    """Notifikasi: API key berhasil dibuat."""
    label = f" (mode {mode_nama})" if mode_nama else ""
    return kirim(f"✅ <b>API KEY BERHASIL</b>{label}\n"
                 f"<code>{email}</code>\n"
                 f"Total: {_total_key()} akun")


def sukses_9router(email):
    """Notifikasi: key berhasil masuk 9Router."""
    return kirim(f"✅ <b>INPUT 9ROUTER SUKSES</b>\n"
                 f"<code>{email}</code>\n"
                 f"Total: {_total_key()} akun")
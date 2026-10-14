"""
tampilan.py: Output console modern, presisi, berwarna, dan terstruktur.

Menggunakan style card tree terbuka (seperti Vite / GitHub CLI) yang
100% rapi dan tidak akan pernah bergeser / bertabrakan di terminal Windows / Linux.
"""
import ctypes
import datetime
import json
import re
import sys
import threading
import time
import urllib.request

# Lebar default garis horizontal
LEBAR_GARIS = 66

# Reset & Formatting
RST  = "\033[0m"
BOLD = "\033[1m"
DIM  = "\033[2m"
ITAL = "\033[3m"
UNDR = "\033[4m"

# Palet Warna Terang (High Contrast & Vibrant)
WHT  = "\033[97m"  # Putih Bersih
GRY  = "\033[90m"  # Abu-abu Muted (garis & waktu)
CYN  = "\033[96m"  # Cyan Terang (Header & Label)
BLU  = "\033[94m"  # Biru Langit
GRN  = "\033[92m"  # Hijau Emerald (Sukses & OK)
YEL  = "\033[93m"  # Kuning / Gold (Peringatan & Retry)
RED  = "\033[91m"  # Merah Crimson (Error & Blokir)
MAG  = "\033[95m"  # Magenta / Ungu (Step & Jalur)

# Backward-compatible alias
BCYN = CYN
BGRN = GRN
BRED = RED
BYEL = YEL

# Konfigurasi Badge [Ikon + Label]
_BADGE_STYLE = {
    "INFO":    (CYN, "ℹ", "INFO "),
    "OK":      (GRN, "✔", " OK  "),
    "SUKSES":  (GRN, "✔", "SUKSES"),
    "WARN":    (YEL, "⚠", "WARN "),
    "LIMIT":   (YEL, "⏳", "LIMIT"),
    "ERROR":   (RED, "✖", "ERROR"),
    "GAGAL":   (RED, "✖", "GAGAL"),
    "STEP":    (MAG, "➔", "STEP "),
    "WAIT":    (YEL, "⏱", "WAIT "),
    "ROUTER":  (BLU, "🌐", "9ROUT"),
}

_IP_CACHE = None
_ip_thread = None
_box_terbuka = False


def _len_visible(s):
    """Menghitung panjang string tampak tanpa kode warna ANSI."""
    return len(re.sub(r"\033\[[0-9;]*m", "", str(s)))


def aktifkan_warna():
    """Aktifkan ANSI Virtual Terminal di Windows dan paksa UTF-8 stdout."""
    if sys.platform == "win32":
        try:
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except Exception:
            pass
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


# Otomatis aktifkan saat modul di-import
aktifkan_warna()


def tutup_box():
    """Menutup blok card jika sedang terbuka."""
    global _box_terbuka
    if _box_terbuka:
        print(f"  {GRY}└" + ("─" * LEBAR_GARIS) + f"{RST}", flush=True)
        _box_terbuka = False


def _fetch_ip_worker():
    global _IP_CACHE
    res = {"ipv4": None, "ipv6": None, "is_warp": False}

    def _get_v4():
        try:
            req = urllib.request.Request("https://api.ipify.org?format=json",
                                         headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=2.5) as r:
                res["ipv4"] = json.loads(r.read().decode())["ip"]
        except Exception:
            pass

    def _get_v6():
        try:
            req = urllib.request.Request("https://ipecho.net/plain",
                                         headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=2.5) as r:
                dual = r.read().decode().strip()
                if ":" in dual:
                    res["ipv6"] = dual
                elif not res["ipv4"]:
                    res["ipv4"] = dual
        except Exception:
            pass

    t1 = threading.Thread(target=_get_v4, daemon=True)
    t2 = threading.Thread(target=_get_v6, daemon=True)
    t1.start()
    t2.start()
    t1.join(timeout=2.5)
    t2.join(timeout=2.5)

    if res["ipv4"] and res["ipv4"].startswith("104.28."):
        res["is_warp"] = True
    elif res["ipv6"] and res["ipv6"].startswith("2a09:bac"):
        res["is_warp"] = True

    _IP_CACHE = res


def prefetch_ip():
    """Mulai pengecekan IP publik di thread latar belakang agar tidak memblokir UI."""
    global _ip_thread
    if _ip_thread is None or not _ip_thread.is_alive():
        _ip_thread = threading.Thread(target=_fetch_ip_worker, daemon=True)
        _ip_thread.start()


# Prefetch langsung saat modul di-import
prefetch_ip()


def cek_ip_publik(force=False):
    """Deteksi IP publik (IPv4 dan IPv6) secara cepat dengan cache."""
    global _IP_CACHE, _ip_thread
    if _IP_CACHE and not force:
        return _IP_CACHE

    if force:
        _fetch_ip_worker()
        return _IP_CACHE

    if _ip_thread and _ip_thread.is_alive():
        _ip_thread.join(timeout=1.5)

    if not _IP_CACHE:
        _fetch_ip_worker()

    return _IP_CACHE or {"ipv4": None, "ipv6": None, "is_warp": False}


def tampilkan_info_ip():
    """Tampilkan kartu status IP jaringan saat ini dengan format tree presisi."""
    tutup_box()
    data = cek_ip_publik()
    ipv4 = data.get("ipv4") or "Tidak terdeteksi"
    ipv6 = data.get("ipv6")
    is_warp = data.get("is_warp", False)

    warp_label = f"{YEL}(WARP Shared){RST}" if is_warp else f"{GRN}(Direct / ISP){RST}"
    header_text = "STATUS JARINGAN & IP AKTIF"
    garis_sisa = max(4, LEBAR_GARIS - len(header_text) - 3)

    print()
    print(f"  {GRY}┌─{RST} {CYN}{BOLD}{header_text}{RST} {GRY}" + ("─" * garis_sisa) + f"{RST}")
    print(f"  {GRY}│{RST}  {CYN}• IPv4 Aktif  {GRY}:{RST} {WHT}{BOLD}{ipv4}{RST} {warp_label}")
    if ipv6:
        print(f"  {GRY}│{RST}  {CYN}• IPv6 Aktif  {GRY}:{RST} {WHT}{BOLD}{ipv6}{RST}")
    if is_warp:
        print(f"  {GRY}│{RST}  {YEL}• Perhatian   {GRY}:{RST} {YEL}IPv4 WARP dipakai bersama ribuan user (rentan limit){RST}")
    print(f"  {GRY}└" + ("─" * LEBAR_GARIS) + f"{RST}")
    print()


def judul(teks, subjudul=None):
    """Banner header utama yang elegan."""
    tutup_box()
    lebar = LEBAR_GARIS + 2
    isi_teks = f" {teks} "
    garis_atas = "╭" + "─" * (lebar - 2) + "╮"
    garis_bawah = "╰" + "─" * (lebar - 2) + "╯"

    print()
    print(f"  {BOLD}{CYN}{garis_atas}{RST}")
    print(f"  {BOLD}{CYN}│{WHT}{isi_teks.center(lebar - 2)}{CYN}│{RST}")
    if subjudul:
        pad_kiri = max(1, (lebar - 2 - len(subjudul)) // 2)
        pad_kanan = max(1, lebar - 2 - len(subjudul) - pad_kiri)
        print(f"  {BOLD}{CYN}│{' ' * pad_kiri}{DIM}{subjudul}{RST}{' ' * pad_kanan}{CYN}│{RST}")
    print(f"  {BOLD}{CYN}{garis_bawah}{RST}")
    print()


def garis():
    """Garis horizontal pemisah yang rapi."""
    tutup_box()
    print(f"  {GRY}{'─' * LEBAR_GARIS}{RST}", flush=True)


def bagian(teks):
    """Membuka kartu seksi / akun baru dengan header rapi."""
    global _box_terbuka
    tutup_box()
    header_clean = str(teks).strip()
    garis_sisa = max(4, LEBAR_GARIS - len(header_clean) - 3)

    print()
    print(f"  {GRY}┌─{RST} {CYN}{BOLD}{header_clean}{RST} {GRY}" + ("─" * garis_sisa) + f"{RST}", flush=True)
    _box_terbuka = True


def rinci(label, nilai, highlight=False):
    """Menampilkan parameter key-value dengan alignment titik dua rata vertikal."""
    lbl_clean = f"{label}".strip()
    val_color = f"{WHT}{BOLD}" if highlight else f"{WHT}"
    print(f"  {GRY}│{RST}  {CYN}• {lbl_clean:<12}{GRY}:{RST} {val_color}{nilai}{RST}", flush=True)


def log(pesan, badge="INFO"):
    """Mencetak baris log dengan timestamp dan badge berwarna."""
    tutup_box()
    b_key = str(badge).upper()
    warna, ikon, nama = _BADGE_STYLE.get(b_key, (WHT, "•", f"{b_key[:5]:<5}"))

    jam = datetime.datetime.now().strftime("%H:%M:%S")
    tag = f"{warna}{BOLD}[{ikon} {nama}]{RST}"

    msg_color = WHT
    if b_key in ("ERROR", "GAGAL"):
        msg_color = RED
    elif b_key in ("WARN", "LIMIT"):
        msg_color = YEL
    elif b_key in ("OK", "SUKSES"):
        msg_color = GRN
    elif b_key == "STEP":
        msg_color = f"{CYN}{BOLD}"

    print(f"  {GRY}{jam}{RST} {tag} {msg_color}{pesan}{RST}", flush=True)


def tunggu(detik, alasan="Menunggu"):
    """Countdown interaktif di satu baris (tidak membuat console freeze atau spam)."""
    tutup_box()
    jam = datetime.datetime.now().strftime("%H:%M:%S")
    tag = f"{YEL}{BOLD}[⏱ WAIT ]{RST}"

    try:
        for sisa in range(detik, 0, -1):
            m, s = divmod(sisa, 60)
            durasi_str = f"{m}m {s:02d}s" if m > 0 else f"{s}s"
            baris = f"\r  {GRY}{jam}{RST} {tag} {YEL}{alasan}... {BOLD}{durasi_str}{RST} {DIM}(Ctrl+C untuk lewati){RST}   "
            sys.stdout.write(baris)
            sys.stdout.flush()
            time.sleep(1)
        sys.stdout.write("\r" + " " * (LEBAR_GARIS + 20) + "\r")
        sys.stdout.flush()
    except KeyboardInterrupt:
        sys.stdout.write("\r" + " " * (LEBAR_GARIS + 20) + "\r")
        sys.stdout.flush()
        log(f"{alasan} dibatalkan pengguna.", "WARN")


def ringkasan(data_dict, judul_kartu="RINGKASAN HASIL"):
    """Mencetak kartu hasil akhir (summary card) dengan format tabel rapi presisi."""
    tutup_box()
    header_clean = str(judul_kartu).strip()
    garis_sisa = max(4, LEBAR_GARIS - len(header_clean) - 3)

    # Hitung lebar label terpanjang secara dinamis agar semua titik dua (:) 100% sejajar lurus vertikal
    max_k = max((len(str(k)) for k in data_dict.keys()), default=12)
    lebar_label = max(16, max_k + 2)

    print()
    print(f"  {GRY}┌─{RST} {CYN}{BOLD}{header_clean}{RST} {GRY}" + ("─" * garis_sisa) + f"{RST}")

    for k, v in data_dict.items():
        v_str = str(v)
        k_low = str(k).lower()
        if "sukses" in k_low or "berhasil" in k_low or v_str.lower() in ("ok", "true"):
            v_colored = f"{GRN}{BOLD}{v_str}{RST}"
        elif "gagal" in k_low or "error" in k_low or v_str.lower() in ("false", "fail"):
            v_colored = f"{RED}{BOLD}{v_str}{RST}"
        elif "skip" in k_low or "duplikat" in k_low or "sudah" in k_low:
            v_colored = f"{YEL}{BOLD}{v_str}{RST}"
        else:
            v_colored = f"{WHT}{BOLD}{v_str}{RST}"

        print(f"  {GRY}│{RST}  {CYN}• {str(k):<{lebar_label}}{GRY}:{RST} {v_colored}")

    print(f"  {GRY}└" + ("─" * LEBAR_GARIS) + f"{RST}")
    print()

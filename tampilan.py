"""
tampilan.py: output console berwarna dengan badge (INFO / OK / WARN / ERROR).

Tanpa library tambahan. Aman untuk Windows cmd / PowerShell / Windows Terminal.
"""
import ctypes
import datetime
import sys

LEBAR = 60

RST = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
WHT = "\033[97m"
BCYN = "\033[96m"
BGRN = "\033[92m"
BRED = "\033[91m"
BYEL = "\033[93m"

_BADGE = {
    "INFO":  "\033[44m" + WHT + BOLD,   # biru
    "OK":    "\033[42m" + WHT + BOLD,   # hijau
    "WARN":  "\033[43m\033[30m" + BOLD, # kuning
    "ERROR": "\033[41m" + WHT + BOLD,   # merah
}
_IKON = {"INFO": "\u25cf", "OK": "\u2714", "WARN": "\u26a0", "ERROR": "\u2718"}


def aktifkan_warna():
    """Aktifkan ANSI di Windows console dan paksa UTF-8 supaya ikon tampil."""
    if sys.platform != "win32":
        return
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


def judul(teks):
    garis = "\u2500" * LEBAR
    print(BOLD + BCYN + "\u256d" + garis + "\u256e" + RST)
    print(BOLD + BCYN + "\u2502" + RST + BOLD + WHT + f" {teks} ".center(LEBAR)
          + RST + BOLD + BCYN + "\u2502" + RST)
    print(BOLD + BCYN + "\u2570" + garis + "\u256f" + RST)


def garis():
    print(DIM + "\u2500" * LEBAR + RST, flush=True)


def bagian(teks):
    """Judul blok: baris tegas berwarna, tanpa badge, lebar selalu sama.

    Panjang tampak = 3 ("▕─ ") + teks + 1 (spasi) + ekor + 1 ("▏") = LEBAR.
    Teks yang kepanjangan dipotong dengan "…" supaya garis kanan tetap lurus.
    """
    teks = str(teks)
    maks = LEBAR - 6
    if len(teks) > maks:
        teks = teks[:maks - 1] + "\u2026"
    ekor = LEBAR - len(teks) - 5
    print()
    print(f"{BOLD}{BCYN}\u2595\u2500 {teks} {chr(0x2500) * ekor}\u258f{RST}", flush=True)


def rinci(label, nilai):
    """Baris detail tanpa badge, menjorok sejajar dengan pesan log."""
    label = f"{label}:"
    print(f"{' ' * 19}{DIM}{label:<9}{RST} {nilai}", flush=True)


def log(pesan, badge="INFO"):
    """Satu baris log: jam + badge berwarna + pesan."""
    badge = str(badge).upper()
    jam = datetime.datetime.now().strftime("%H:%M:%S")
    bg = _BADGE.get(badge, DIM + WHT + BOLD)
    ikon = _IKON.get(badge, "\u00b7")
    tag = f"{bg} {ikon} {badge:<5} {RST}"
    print(f"{DIM}{jam}{RST} {tag} {pesan}", flush=True)

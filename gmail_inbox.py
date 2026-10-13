#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Token Harbor Auto - Modul Gmail inbox

Ambil link verifikasi Token Harbor dari Gmail, di-match BERDASARKAN
alamat email yang didaftarkan (header To), bukan "email terbaru".
Alasannya: satu inbox Gmail dipakai banyak akun @example.com,
jadi harus yakin link yg diambil milik akun yg sedang dikerjakan.
"""

import os
import re
import ssl
import time
import email
import imaplib
from email.header import decode_header
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENV_FILE = HERE / ".env"

GMAIL_USER = ""
GMAIL_APP_PASSWORD = ""

VERIFIKASI_DOMAIN = "tokenharbor.ai"
LINK_PATTERN = r"https?://[^\s\"'<>]+verify-email\?token=[^\s\"'<>]+"


def _env():
    """Baca .env (GMAIL_USER, GMAIL_APP_PASSWORD). Tidak pakai library tambahan."""
    global GMAIL_USER, GMAIL_APP_PASSWORD
    if os.environ.get("GMAIL_USER"):
        GMAIL_USER = os.environ["GMAIL_USER"]
    if os.environ.get("GMAIL_APP_PASSWORD"):
        GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
    if not GMAIL_USER and ENV_FILE.exists():
        with open(ENV_FILE, encoding="utf-8") as f:
            for baris in f:
                baris = baris.strip()
                if not baris or baris.startswith("#") or "=" not in baris:
                    continue
                kunci, nilai = baris.split("=", 1)
                kunci = kunci.strip()
                nilai = nilai.strip().strip('"').strip("'")
                if kunci == "GMAIL_USER" and not GMAIL_USER:
                    GMAIL_USER = nilai
                if kunci == "GMAIL_APP_PASSWORD" and not GMAIL_APP_PASSWORD:
                    GMAIL_APP_PASSWORD = nilai
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        raise RuntimeError(
            "Gmail belum dikonfigurasi. Isi .env:\n"
            "GMAIL_USER=alamat@gmail.com\n"
            "GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx"
        )


def _decode_header(s):
    if s is None:
        return ""
    out = []
    for bagian, enc in decode_header(s):
        if isinstance(bagian, bytes):
            try:
                bagian = bagian.decode(enc or "utf-8", "replace")
            except Exception:
                bagian = bagian.decode("utf-8", "replace")
        out.append(bagian)
    return "".join(out)


def _buat_koneksi():
    """Koneksi IMAP Gmail baru (TLS)."""
    ctx = ssl.create_default_context()
    conn = imaplib.IMAP4_SSL("imap.gmail.com", 993, ssl_context=ctx)
    conn.login(GMAIL_USER, GMAIL_APP_PASSWORD)
    conn.select("INBOX", readonly=True)
    return conn


def _ambil_body(conn, uid):
    """Body plain text dari satu email (by UID)."""
    typ, d = conn.fetch(uid, "(RFC822)")
    if not d or not d[0]:
        return ""
    msg = email.message_from_bytes(d[0][1])
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                body += part.get_payload(decode=True).decode(
                    part.get_content_charset() or "utf-8", "replace")
    else:
        body = msg.get_payload(decode=True).decode(
            msg.get_content_charset() or "utf-8", "replace")
    return body


def _header_to(conn, uid):
    """Isi header To + Delivered-To dari satu email (by UID)."""
    typ, d = conn.fetch(uid, "(BODY.PEEK[HEADER.FIELDS (TO DELIVERED-TO)])")
    if not d or not d[0]:
        return ""
    return _decode_header(
        email.message_from_bytes(d[0][1]).get("To", ""))


def cari_link_verifikasi(email_target, timeout=180, interval=5, log=print):
    """
    Polling inbox Gmail sampai link verifikasi untuk `email_target` masuk.

    Match berdasarkan header To yg berisi email_target (case-insensitive).
    Return link verifikasi, atau None kalau timeout.
    """
    _env()
    email_target = (email_target or "").strip().lower()
    if not email_target:
        raise ValueError("email_target kosong")

    deadline = time.time() + timeout
    conn = None
    terakhir = 0

    try:
        log(f"[GMAIL] polling link verifikasi untuk {email_target} "
            f"(timeout {timeout}s)")
        while time.time() < deadline:
            # reconnect setiap menit supaya koneksi tidak stale
            if conn is None or time.time() - terakhir > 60:
                if conn:
                    try:
                        conn.logout()
                    except Exception:
                        pass
                conn = _buat_koneksi()
                terakhir = time.time()

            try:
                # NOOP: paksa Gmail sync, biar email baru keliatan di search
                # (tanpa ini koneksi lama cache hasil -> email baru gak kedetek)
                try:
                    conn.noop()
                except Exception:
                    conn = None
                    time.sleep(3)
                    continue
                typ, data = conn.search("UTF-8", "FROM", VERIFIKASI_DOMAIN)
                uids = data[0].split() if data and data[0] else []
            except Exception:
                conn = None
                time.sleep(3)
                continue

            for uid in reversed(uids[-40:]):
                try:
                    to_header = _header_to(conn, uid).lower()
                except Exception:
                    continue
                if email_target not in to_header:
                    continue
                body = _ambil_body(conn, uid)
                links = re.findall(LINK_PATTERN, body)
                if links:
                    log(f"[GMAIL] KETEMU link verifikasi untuk {email_target}")
                    return links[0]
            time.sleep(interval)
    except Exception as e:
        log(f"[GMAIL] error: {type(e).__name__}: {e}")
    finally:
        if conn:
            try:
                conn.logout()
            except Exception:
                pass
    log(f"[GMAIL] link verifikasi untuk {email_target} TIDAK ditemukan "
        "sebelum timeout")
    return None


if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else None
    if not target:
        print("pakai: python gmail_inbox.py nama@example.com")
    else:
        link = cari_link_verifikasi(target, timeout=30)
        print("LINK:", link)

#!/usr/bin/env python3
# Kalupura Download Manager (KDM) – Final Multilingual Edition
# UPDATED: Added Download Info and Status Windows with collapsible details

import os
import sys

# macOS: reduce Qt/TSM console spam (TSMSendMessageToUIServer errors)
if sys.platform == "darwin":
    os.environ.setdefault("QT_MAC_WANTS_LAYER", "1")
    _real_stderr = sys.stderr
    class _StderrFilter:
        def write(self, s):
            if s and ("TSMSendMessageToUIServer" in s or "CFMessagePortSendRequest" in s or "com.apple.tsm.uiserver" in s or "Python version 3.9 has been deprecated" in s):
                return
            _real_stderr.write(s)
        def flush(self):
            _real_stderr.flush()
    sys.stderr = _StderrFilter()

import json, time, threading, requests, glob, ctypes, subprocess, re, tempfile, shutil, warnings
from typing import Optional
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs, urljoin, quote

from kdm.licensing import LicenseGate, run_startup_license_check, show_license_blocking_dialog
warnings.filterwarnings("ignore", message=".*Python version 3.9 has been deprecated.*")
import yt_dlp
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QToolButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QStatusBar, QSpacerItem, QSizePolicy, QProgressBar, QInputDialog,
    QMessageBox, QFrame, QComboBox, QDialog, QDialogButtonBox, QCheckBox,
    QMenu, QGroupBox, QGridLayout, QLineEdit, QPushButton, QTextEdit,
    QFileDialog
)
from PyQt6.QtGui import QPixmap, QPainter, QColor, QFont, QIcon, QAction, QGuiApplication, QDesktopServices
from PyQt6.QtCore import Qt, QSize, QTimer, QPoint, QEvent, QUrl

# Windows Shell API for Open Folder functionality only
if sys.platform.startswith("win"):
    import ctypes.wintypes
    
    SHOpenFolderAndSelectItems = ctypes.windll.shell32.SHOpenFolderAndSelectItems
    SHOpenFolderAndSelectItems.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_ulong]
    SHOpenFolderAndSelectItems.restype = ctypes.c_long
    
    ILCreateFromPath = ctypes.windll.shell32.ILCreateFromPathW
    ILCreateFromPath.argtypes = [ctypes.c_wchar_p]
    ILCreateFromPath.restype = ctypes.c_void_p
    
    ILFree = ctypes.windll.shell32.ILFree
    ILFree.argtypes = [ctypes.c_void_p]

API_HOST, API_PORT = "127.0.0.1", 9669
CONFIG_FILE = "kdm_config.json"
TRANSLATION_FILE = "translations.json"

#########################################
#  EMBED / STREAM CDN HELPERS           #
#########################################

from playwright.sync_api import sync_playwright

# MultiMovies mirrors (TLDs change often; extend this list as needed)
MULTIMOVIES_DOMAINS = [
    "multimovies.email",
    "multimovies.my",
    "multimovies.onl",
    "multimovies.world",
    "multimoviespro.com",
    "multimovies.sbs",
    "multimovies.shop",
    "multimovies.uno",
]


def _is_multimovies(url: str) -> bool:
    return bool(url) and any(d in url.lower() for d in MULTIMOVIES_DOMAINS)


def _cdn_prefers_embed_host_headers(url: str) -> bool:
    """Some CDNs (e.g. neonhorizon /pl/) need same-origin style Referer on the stream host."""
    u = (url or "").lower()
    return "neonhorizonworkshops" in u


def _apply_embed_extension_headers(
    http_headers: dict,
    referer: Optional[str],
    extension_headers: Optional[dict] = None,
    resource_url: Optional[str] = None,
) -> None:
    """
    For embed/file hosts opened from a parent movie page, many CDNs expect Origin + Referer
    to be that page. Merges optional headers from the Chrome extension.
    """
    if resource_url and _cdn_prefers_embed_host_headers(resource_url):
        http_headers.setdefault("Accept-Language", "en-US,en;q=0.9")
        http_headers.setdefault("Sec-Fetch-Dest", "empty")
        http_headers.setdefault("Sec-Fetch-Mode", "cors")
        if extension_headers:
            for k, v in extension_headers.items():
                if isinstance(k, str) and v is not None and str(v).strip():
                    lk = k.lower()
                    if lk in ("user-agent", "accept", "accept-language", "sec-ch-ua", "sec-ch-ua-mobile", "sec-ch-ua-platform", "cookie"):
                        http_headers[k] = str(v).strip()
        return
    r = (referer or "").strip()
    if not r or not r.lower().startswith("http"):
        return
    try:
        pr = urlparse(r)
        if pr.scheme and pr.netloc:
            http_headers["Origin"] = f"{pr.scheme}://{pr.netloc}"
            http_headers["Referer"] = r
    except Exception:
        return
    http_headers.setdefault("Accept-Language", "en-US,en;q=0.9")
    http_headers.setdefault("Sec-Fetch-Dest", "empty")
    http_headers.setdefault("Sec-Fetch-Mode", "cors")
    http_headers.setdefault("Sec-Fetch-Site", "cross-site")
    if extension_headers:
        for k, v in extension_headers.items():
            if isinstance(k, str) and v is not None and str(v).strip():
                http_headers[k] = str(v).strip()

def _is_bad_capture_url(url: str) -> bool:
    """JW Player analytics/API URLs etc. — not real streams; yt-dlp returns 'no data blocks'."""
    u = (url or "").lower()
    if not u.strip():
        return True
    if "jwpltx.com" in u:
        return True
    if "jwplayer" in u and ".m3u8" not in u:
        return True
    if "doubleclick.net" in u or "googletagmanager.com" in u:
        return True
    return False

def _is_stream_cdn_url(url: str, referer: Optional[str] = None) -> bool:
    """Hosts that need Origin/Referer/cookies and yt-dlp→ffmpeg fallback (403 on generic extractor)."""
    u = (url or "").lower()
    known = [
        "neonhorizonworkshops", "vidoza", "streamtape", "vidplay", "strp2p",
        "mistwolf", "filemoon", "doodstream", "streamwish", "lulustream",
        "rabbitstream", "embedrise", "vidmoly", "streamruby", "playernest",
        "upstream", "somastream", "voesx", "embedsito",
    ]
    if any(k in u for k in known):
        return True
    if ".m3u8" in u and ".m3u8.js" not in u:
        return True
    if "/pl/" in u:
        return True
    ref = (referer or "").lower()
    if "multimovies" in ref:
        try:
            pu, pr = urlparse(url or ""), urlparse(referer or "")
            if pu.scheme in ("http", "https") and pr.scheme in ("http", "https"):
                if pu.netloc and pr.netloc and pu.netloc != pr.netloc:
                    if "multimovies" in u:
                        return False
                    if any(b in u for b in ("youtube.com", "youtu.be", "dailymotion.com", "vimeo.com", "google.com", "facebook.com", "doubleclick", "googlevideo.com")):
                        return False
                    return True
        except Exception:
            pass
    return False

#########################################
#  HLS / AES-128 (embed CDNs)           #
#########################################

CHROME_WIN_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

def _merge_cookie_header_strings(*chunks: Optional[str]) -> str:
    """Merge Cookie header values; later chunks override duplicate names."""
    merged: dict = {}
    for ch in chunks:
        if not ch or not str(ch).strip():
            continue
        for part in str(ch).split(";"):
            part = part.strip()
            if not part or "=" not in part:
                continue
            k, v = part.split("=", 1)
            k = k.strip()
            if k:
                merged[k] = v.strip()
    return "; ".join(f"{k}={v}" for k, v in merged.items())

def _session_cookie_header_for_url(session: requests.Session, url: str) -> str:
    """Cookie header the session would send for this host (after warm / Set-Cookie)."""
    if not url or not session:
        return ""
    try:
        pu = urlparse(url)
        host = (pu.hostname or "").lower()
        if not host:
            return ""
        parts = []
        for c in session.cookies:
            dom = (c.domain or "").lstrip(".").lower()
            if not dom:
                continue
            if host == dom or host.endswith("." + dom):
                parts.append(f"{c.name}={c.value}")
        return "; ".join(parts)
    except Exception:
        return ""

def _hls_chrome_client_hint_headers() -> dict:
    return {
        "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
    }

def _hls_cross_site_headers(movie_referer: str, cookie_merged: Optional[str]) -> dict:
    """Browser-like cross-site request from parent page tab to stream CDN (e.g. m3u8)."""
    ref = (movie_referer or "").strip()
    pr = urlparse(ref)
    origin = f"{pr.scheme}://{pr.netloc}" if pr.scheme and pr.netloc else ""
    h = {
        "User-Agent": CHROME_WIN_UA,
        "Accept": "application/vnd.apple.mpegurl, application/x-mpegURL, */*;q=0.8",
        "Origin": origin or ref or "",
        "Referer": ref if ref else ((origin + "/") if origin else ""),
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "cross-site",
        "Accept-Language": "en-US,en;q=0.9",
    }
    h.update(_hls_chrome_client_hint_headers())
    if cookie_merged and str(cookie_merged).strip():
        h["Cookie"] = str(cookie_merged).strip()
    return h

def _warm_neonhorizon_gates(
    session: requests.Session,
    m3u8_url: str,
    movie_referer: Optional[str],
    cookie_merged: Optional[str],
) -> None:
    """Light GETs on CDN paths to pick up gate cookies (ignore failures)."""
    if "neonhorizonworkshops" not in (m3u8_url or "").lower():
        return
    try:
        ou = urlparse(m3u8_url)
        if not ou.scheme or not ou.netloc:
            return
        origin = f"{ou.scheme}://{ou.netloc}"
        ref_dir = m3u8_url.rsplit("/", 1)[0] + "/" if "/" in m3u8_url else origin + "/"
        ck = (cookie_merged or "").strip()
        gates = [ref_dir, origin + "/"]
        for gurl in gates:
            for hdr in (
                {
                    "User-Agent": CHROME_WIN_UA,
                    "Accept": "application/vnd.apple.mpegurl, application/x-mpegURL, */*;q=0.8",
                    "Origin": origin,
                    "Referer": ref_dir,
                    "Sec-Fetch-Dest": "empty",
                    "Sec-Fetch-Mode": "cors",
                    "Sec-Fetch-Site": "same-origin",
                    "Accept-Language": "en-US,en;q=0.9",
                    **(_hls_chrome_client_hint_headers()),
                    **({"Cookie": ck} if ck else {}),
                },
                (
                    _hls_cross_site_headers(movie_referer, ck or None)
                    if movie_referer and str(movie_referer).strip().lower().startswith("http")
                    else None
                ),
            ):
                if not hdr:
                    continue
                try:
                    session.get(gurl, headers=hdr, timeout=22, allow_redirects=True)
                except Exception:
                    pass
    except Exception:
        pass

def _hls_fetch_text(url: str, headers: dict, timeout: int = 45, session: Optional[requests.Session] = None) -> str:
    h = {k: v for k, v in (headers or {}).items() if v is not None}
    h.setdefault("Accept", "*/*")
    if session is not None:
        r = session.get(url, headers=h, timeout=timeout)
    else:
        r = requests.get(url, headers=h, timeout=timeout)
    r.raise_for_status()
    return r.text

def _hls_fetch_text_first_ok(
    url: str,
    header_variants: list,
    timeout: int = 45,
    session: Optional[requests.Session] = None,
) -> str:
    last_err = None
    for hdr in header_variants or [{}]:
        try:
            return _hls_fetch_text(url, hdr, timeout, session=session)
        except Exception as e:
            last_err = e
    if last_err:
        raise last_err
    raise RuntimeError("no variants")

def _build_hls_header_variants(
    stream_url: str,
    http_headers: dict,
    referer: Optional[str],
    cookie_merged: Optional[str] = None,
) -> list:
    """Ordered Referer/Origin combinations for HLS playlist, keys, and ffmpeg."""
    base = {k: v for k, v in (http_headers or {}).items() if v is not None}
    ck = (cookie_merged or "").strip() or (base.get("Cookie") or "").strip()
    ou = urlparse(stream_url or "")
    origin = f"{ou.scheme}://{ou.netloc}" if ou.scheme and ou.netloc else ""
    ref_dir = stream_url.rsplit("/", 1)[0] + "/" if stream_url and "/" in stream_url else (origin + "/" if origin else "")
    ch = _hls_chrome_client_hint_headers()
    variants = []

    # neonhorizon: same-origin first (many edges block cross-site on m3u8)
    if _cdn_prefers_embed_host_headers(stream_url) and origin:
        for ref in (ref_dir, origin + "/"):
            h = {
                "User-Agent": CHROME_WIN_UA,
                "Accept": "application/vnd.apple.mpegurl, application/x-mpegURL, */*;q=0.8",
                "Origin": origin,
                "Referer": ref,
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
                "Accept-Language": "en-US,en;q=0.9",
                **ch,
            }
            if ck:
                h["Cookie"] = ck
            variants.append(h)
        if referer and referer.strip():
            h = {
                "User-Agent": CHROME_WIN_UA,
                "Accept": "application/vnd.apple.mpegurl, application/x-mpegURL, */*;q=0.8",
                "Origin": origin,
                "Referer": referer.strip(),
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "cross-site",
                "Accept-Language": "en-US,en;q=0.9",
                **ch,
            }
            if ck:
                h["Cookie"] = ck
            variants.append(h)

    if referer and referer.strip():
        variants.append(_hls_cross_site_headers(referer, ck or None))

    variants.append(dict(base))

    if referer and referer.strip():
        try:
            pr = urlparse(referer.strip())
            if pr.scheme and pr.netloc:
                h3 = dict(base)
                h3["Referer"] = referer.strip()
                h3["Origin"] = f"{pr.scheme}://{pr.netloc}"
                h3["Sec-Fetch-Site"] = "cross-site"
                h3.update(ch)
                variants.append(h3)
        except Exception:
            pass

    seen, out = set(), []
    for h in variants:
        key = (h.get("Referer"), h.get("Origin"), h.get("Sec-Fetch-Site"))
        if key in seen:
            continue
        seen.add(key)
        out.append(h)
    return out


def _hls_is_master_playlist(text: str) -> bool:
    return bool(text) and "#EXT-X-STREAM-INF" in text

def _hls_select_best_variant_url(master_text: str, playlist_url: str) -> Optional[str]:
    best_bw, best_uri = -1, None
    lines = master_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("#EXT-X-STREAM-INF"):
            m = re.search(r"BANDWIDTH=(\d+)", line)
            bw = int(m.group(1)) if m else 0
            for j in range(i + 1, min(i + 6, len(lines))):
                u = lines[j].strip()
                if not u or u.startswith("#"):
                    continue
                abs_u = u if u.lower().startswith("http") else urljoin(playlist_url, u)
                if bw >= best_bw:
                    best_bw, best_uri = bw, abs_u
                break
        i += 1
    return best_uri

def _hls_resolve_media_playlist(
    url: str,
    header_variants: list,
    max_hops: int = 8,
    session: Optional[requests.Session] = None,
) -> tuple:
    """Follow master → media playlist. Returns (media_body, media_absolute_url)."""
    cur_url = url
    for _ in range(max_hops):
        text = _hls_fetch_text_first_ok(cur_url, header_variants, session=session)
        if not _hls_is_master_playlist(text):
            return text, cur_url
        nxt = _hls_select_best_variant_url(text, cur_url)
        if not nxt:
            return text, cur_url
        cur_url = nxt
    return text, cur_url

def _hls_parse_ext_x_key_line(line: str, playlist_url: str) -> Optional[dict]:
    if "#EXT-X-KEY" not in line:
        return None
    if re.search(r"METHOD\s*=\s*NONE", line, re.I):
        return None
    if not re.search(r"METHOD\s*=\s*AES-128", line, re.I):
        return None
    um = re.search(r'URI\s*=\s*"([^"]+)"', line, re.I)
    if not um:
        um = re.search(r"URI\s*=\s*([^,\s\n]+)", line, re.I)
    if not um:
        return None
    uri = um.group(1).strip().strip('"').strip("'")
    low = uri.lower()
    if low.startswith("skd://") or low.startswith("data:") or low.startswith("com.apple"):
        return None
    abs_uri = uri if uri.lower().startswith("http") else urljoin(playlist_url, uri)
    im = re.search(r"IV\s*=\s*(0x[0-9a-fA-F]+)", line, re.I)
    iv_hex = im.group(1) if im else None
    return {"uri": abs_uri, "iv": iv_hex, "method": "AES-128"}

def _hls_collect_aes128_key_entries(media_text: str, media_playlist_url: str) -> list:
    seen, out = set(), []
    for line in media_text.splitlines():
        if not line.startswith("#EXT-X-KEY"):
            continue
        info = _hls_parse_ext_x_key_line(line, media_playlist_url)
        if not info:
            continue
        u = info["uri"]
        if u not in seen:
            seen.add(u)
            out.append(info)
    return out

def _hls_download_key_bytes(
    key_url: str,
    headers: dict,
    timeout: int = 30,
    session: Optional[requests.Session] = None,
) -> bytes:
    h = {k: v for k, v in (headers or {}).items() if v is not None}
    h.setdefault("Accept", "*/*")
    if session is not None:
        r = session.get(key_url, headers=h, timeout=timeout)
    else:
        r = requests.get(key_url, headers=h, timeout=timeout)
    r.raise_for_status()
    return r.content

def _hls_download_key_bytes_first_ok(
    key_url: str,
    header_variants: list,
    timeout: int = 30,
    session: Optional[requests.Session] = None,
) -> bytes:
    last_err = None
    for hdr in header_variants or [{}]:
        try:
            return _hls_download_key_bytes(key_url, hdr, timeout, session=session)
        except Exception as e:
            last_err = e
    if last_err:
        raise last_err
    raise RuntimeError("no variants")

def _ffmpeg_remux_mp4_faststart_inplace(path: str) -> None:
    """Second pass: copy streams into a QuickTime-friendly MP4 (+faststart)."""
    if not shutil.which("ffmpeg") or not os.path.isfile(path):
        return
    tmp = path + ".kdmremux.mp4"
    try:
        r = subprocess.run(
            [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-i", path, "-map", "0", "-c", "copy", "-movflags", "+faststart", tmp,
            ],
            capture_output=True,
            text=True,
            timeout=7200,
        )
        if r.returncode == 0 and os.path.isfile(tmp) and os.path.getsize(tmp) > 0:
            os.replace(tmp, path)
            print("[KDM] MP4 remux (+faststart) complete")
    except Exception as e:
        print("[KDM] MP4 remux skipped:", e)
    finally:
        if os.path.isfile(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass

def _selftest_hls_parser() -> None:
    sample = (
        "#EXTM3U\n#EXT-X-VERSION:3\n"
        '#EXT-X-KEY:METHOD=AES-128,URI="https://cdn.test/secret.key",IV=0x00000000000000000000000000000000\n'
        "#EXTINF:10.0,\nseg001.ts\n"
    )
    keys = _hls_collect_aes128_key_entries(sample, "https://host/path/playlist.m3u8")
    assert len(keys) == 1 and keys[0]["uri"] == "https://cdn.test/secret.key"
    rel = '#EXT-X-KEY:METHOD=AES-128,URI="keys/key.bin"\n'
    k2 = _hls_parse_ext_x_key_line(rel, "https://example.com/hls/main.m3u8")
    assert k2 and k2["uri"] == "https://example.com/hls/keys/key.bin"
    master = (
        "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=800000\nlow.m3u8\n"
        "#EXT-X-STREAM-INF:BANDWIDTH=2800000\nhigh.m3u8\n"
    )
    assert _hls_select_best_variant_url(master, "https://x.com/m.m3u8") == "https://x.com/high.m3u8"

def _is_video_url(url: str) -> bool:
    """True if URL is a known video site or stream CDN (use yt-dlp). Else use generic download."""
    u = (url or "").lower()
    if (
        "youtube.com" in u
        or "youtu.be" in u
        or "dailymotion.com" in u
        or _is_multimovies(url)
    ):
        return True
    if ".m3u8" in u and ".m3u8.js" not in u:
        return True
    stream_cdns = [
        "neonhorizonworkshops", "vidoza", "streamtape", "vidplay", "doodstream", "streamlare", "sbplay", "filemoon",
        "mistwolf", "streamwish", "lulustream", "rabbitstream", "embedrise", "vidmoly",
    ]
    if any(cdn in u for cdn in stream_cdns):
        return True
    if "/pl/" in u or "/embed/" in u or "/stream/" in u:
        return True
    return False

def _is_magnet_url(url: str) -> bool:
    return (url or "").strip().lower().startswith("magnet:")

def _is_torrent_url(url: str) -> bool:
    u = (url or "").lower()
    return ".torrent" in u or _is_magnet_url(url)

def _is_torrent_by_title(title: str) -> bool:
    """Torrent Galaxy etc. send .torrent as torfile.bin or similar."""
    t = (title or "").strip().lower()
    return t == "torfile.bin" or t.endswith(".torrent")

def _aria2_available() -> bool:
    """True if aria2c is installed (used for built-in torrent download)."""
    return bool(shutil.which("aria2c"))

def _parse_aria2_progress(line: str):
    """Parse aria2 console line (HTTP or BT). Returns (downloaded_bytes, total_bytes, speed_bps) or None."""
    def to_bytes(val: float, unit: str) -> int:
        u = (unit or "B").strip().upper().replace(" ", "")
        if not u or u == "B":
            return int(val)
        if u == "KIB":
            return int(val * 1024)
        if u == "MIB":
            return int(val * 1024 * 1024)
        if u == "GIB":
            return int(val * 1024 * 1024 * 1024)
        return int(val)
    s = line.strip()
    # Relaxed: [#xxx 400.0KiB/33.2MiB(1%) CN:1 DL:115.7KiB] or 0B/0B for BT before metadata
    m = re.search(
        r"\[\#\S+\s+([\d.]+)\s*(B|KiB|MiB|GiB)?\s*/\s*([\d.]+)\s*(B|KiB|MiB|GiB)?\s*\((\d+)%\)",
        s,
    )
    if not m:
        return None
    try:
        d_val, d_u = float(m.group(1)), (m.group(2) or "B").strip()
        t_val, t_u = float(m.group(3)), (m.group(4) or "B").strip()
        downloaded = to_bytes(d_val, d_u)
        total = to_bytes(t_val, t_u)
        speed = 0
        dm = re.search(r"DL:\s*([\d.]+)\s*(B|KiB|MiB|GiB)?", s)
        if dm:
            speed = to_bytes(float(dm.group(1)), (dm.group(2) or "B").strip())
        return (downloaded, max(1, total) if total > 0 else 0, speed)
    except (ValueError, IndexError):
        return None

def _format_eta(eta) -> str:
    """Format eta (seconds) as 'Xm Ys' or 'Xh Ym'."""
    if eta is None or eta == "":
        return "—"
    try:
        sec = float(eta)
        if sec <= 0 or sec >= 86400:
            return "—"
        if sec < 3600:
            m, s = int(sec) // 60, int(sec) % 60
            return f"{m}m {s}s" if m else f"{s}s"
        h, r = int(sec) // 3600, int(sec) % 3600
        m, s = r // 60, r % 60
        return f"{h}h {m}m" if m else f"{h}h"
    except (ValueError, TypeError):
        return str(eta) if eta else "—"

def _extract_embed_stream_m3u8(url: str, site_label: str = "embed"):
    """Fetch embed-style streaming pages and sniff / scrape .m3u8 (MultiMovies, similar)."""
    print(f"[KDM] {site_label} → extracting player URL...")

    import re
    import requests
    from urllib.parse import unquote, urljoin

    _req_headers = {
        "User-Agent": CHROME_WIN_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Upgrade-Insecure-Requests": "1",
    }

    # STEP 1 — fetch page HTML
    try:
        html = requests.get(url, headers=_req_headers, timeout=35).text
    except Exception as e:
        print(f"[KDM] {site_label} fetch failed:", e)
        return None

    def clean(u):
        return (u or "").strip().strip('"\'<>').split(")")[0].split(",")[0]

    stream_url = None

    def _m3u8_from_html_blob(blob: str) -> Optional[str]:
        blob = unquote(blob or "")
        for m in re.finditer(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', blob):
            u = clean(m.group(0))
            if ".m3u8.js" in u:
                continue
            return u
        for m in re.finditer(r'["\']([^"\']+\.m3u8[^"\']*)["\']', blob, re.I):
            u = clean(m.group(1))
            if u.startswith("http") and ".m3u8.js" not in u:
                return u
        return None

    # STEP 2 — search HTML / JSON for m3u8
    stream_url = _m3u8_from_html_blob(html)
    if stream_url:
        print("[KDM] FOUND STREAM (in HTML):", stream_url[:80] + "..." if len(stream_url) > 80 else stream_url)
        return stream_url

    # STEP 3 — collect embed / iframe targets
    player_urls_ordered: list = []
    skip_hosts = ("google.com", "gstatic.com", "facebook.com", "doubleclick.net", "googletagmanager.com")

    def _push_player(u: Optional[str]) -> None:
        u = clean(u or "")
        if not u.startswith("http"):
            return
        ul = u.lower()
        if any(s in ul for s in skip_hosts):
            return
        if u not in player_urls_ordered:
            player_urls_ordered.append(u)

    for pattern in [
        r'https?://[^\s"\']*strp2p\.live[^\s"\']*',
        r'https?://[^\s"\']*playerp2p[^\s"\']*',
        r'https?://wf\.player[^\s"\']*',
        r'https?://[^\s"\']*(?:vidplay|vidmoly|doodstream|filemoon|streamtape|vidoza|embedrise|rabbitstream|upstream|lulustream|streamwish)[^\s"\']*',
        r'["\'](https?://[^"\']*(?:player|strp2p|embed|stream|watch|movie|iframe)[^"\']*)["\']',
        r'source["\']\s*:\s*["\']([^"\']+)',
        r'file["\']\s*:\s*["\']([^"\']+\.m3u8[^"\']*)["\']',
    ]:
        m = re.search(pattern, html, re.I)
        if m:
            u = clean(m.group(1) if m.lastindex else m.group(0))
            if u.startswith("http"):
                _push_player(u)

    for m in re.finditer(r'<iframe[^>]+src=["\']([^"\']+)["\']', html, re.I):
        u = clean(m.group(1))
        if not u.startswith("http"):
            u = urljoin(url, u)
        _push_player(u)

    m = re.search(r'atob\(["\']([^"\']+)["\']\)', html)
    if m:
        import base64

        try:
            decoded = base64.b64decode(m.group(1)).decode(errors="ignore")
            if "http" in decoded:
                for mm in re.finditer(r'https?://[^\s"\']+', decoded):
                    _push_player(mm.group(0))
        except Exception:
            pass

    for pu in player_urls_ordered:
        if ".m3u8" in pu and ".m3u8.js" not in pu:
            stream_url = unquote(pu)
            print("[KDM] FOUND STREAM (embed list):", stream_url[:80] + "..." if len(stream_url) > 80 else stream_url)
            return stream_url

    # STEP 4 — Playwright: sniff network + all frames + deeper waits
    from playwright.sync_api import sync_playwright

    def handle_req(req):
        nonlocal stream_url
        u = req.url
        if ".m3u8" in u and ".m3u8.js" not in u:
            stream_url = unquote(u)
            print("[KDM] FOUND STREAM (request):", stream_url[:80] + "..." if len(stream_url) > 80 else stream_url)

    def handle_resp(resp):
        nonlocal stream_url
        u = resp.url
        if ".m3u8" in u and ".m3u8.js" not in u:
            stream_url = unquote(u)
            print("[KDM] FOUND STREAM (response):", stream_url[:80] + "..." if len(stream_url) > 80 else stream_url)

    js_scrape = """
    () => {
        const out = [];
        const add = (u) => { if (u && typeof u === 'string' && u.includes('.m3u8') && !u.includes('.m3u8.js')) out.push(u); };
        try {
            const k = document.documentElement.getAttribute('data-kdm-m3u8');
            if (k) add(k);
        } catch (e) {}
        if (window.hlsUrl) add(window.hlsUrl);
        if (window.m3u8Url) add(window.m3u8Url);
        if (window.streamUrl) add(window.streamUrl);
        if (window.player && window.player.config && window.player.config.sources) {
            (window.player.config.sources || []).forEach(s => add(typeof s === 'string' ? s : s.src));
        }
        document.querySelectorAll('video').forEach(v => { if (v.src) add(v.src); if (v.currentSrc) add(v.currentSrc); });
        document.querySelectorAll('a[href*=".m3u8"]').forEach(a => add(a.href));
        const html = document.documentElement.outerHTML;
        const r = /https?:\\/\\/[^\\s"\'<>]+\\.m3u8[^\\s"\'<>]*/g;
        let m; while ((m = r.exec(html)) !== null) add(m[0]);
        return out[0] || null;
    }
    """

    def _scrape_all_frames(page_obj) -> Optional[str]:
        for fr in page_obj.frames:
            try:
                found = fr.evaluate(js_scrape)
                if found:
                    return unquote(str(found))
            except Exception:
                continue
        return None

    def try_load(page_ctx, target_url, label, wait_until="domcontentloaded", do_scrape=True):
        nonlocal stream_url
        try:
            pg = page_ctx.new_page()
            pg.goto(target_url, wait_until=wait_until, timeout=55000)
            pg.wait_for_timeout(12000)
            if do_scrape:
                try:
                    found = _scrape_all_frames(pg)
                    if found:
                        stream_url = found
                        print("[KDM] FOUND STREAM (page JS/HTML):", stream_url[:80] + "..." if len(stream_url) > 80 else stream_url)
                except Exception:
                    pass
            if not stream_url:
                for sel in (
                    "video",
                    "button[class*='play']",
                    ".play",
                    "[data-action='play']",
                    ".vjs-big-play-button",
                    "[class*='play']",
                    "button",
                ):
                    try:
                        pg.click(sel, timeout=4000)
                        pg.wait_for_timeout(8000)
                        if stream_url:
                            break
                        found = _scrape_all_frames(pg)
                        if found:
                            stream_url = found
                            print("[KDM] FOUND STREAM (after click):", stream_url[:80] + "..." if len(stream_url) > 80 else stream_url)
                            break
                    except Exception:
                        continue
            if not stream_url:
                try:
                    pg.evaluate("document.querySelector('video') && document.querySelector('video').play()")
                    pg.wait_for_timeout(12000)
                    found = _scrape_all_frames(pg)
                    if found:
                        stream_url = found
                        print("[KDM] FOUND STREAM (after play()):", stream_url[:80] + "..." if len(stream_url) > 80 else stream_url)
                except Exception:
                    pass
            if not stream_url:
                pg.wait_for_timeout(6000)
            pg.close()
        except Exception as e:
            print("[KDM] Playwright (%s): %s" % (label, e))

    _headed = str(os.environ.get("KDM_PLAYWRIGHT_HEADED", "")).strip().lower() in ("1", "true", "yes")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=not _headed,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent=CHROME_WIN_UA,
            viewport={"width": 1280, "height": 720},
            locale="en-US",
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": _req_headers["Accept"],
            },
        )
        context.on("request", handle_req)
        context.on("response", handle_resp)

        for i, pu in enumerate(player_urls_ordered[:14]):
            if stream_url:
                break
            print("[KDM] Trying embed/player URL %s/%s..." % (i + 1, min(len(player_urls_ordered), 14)))
            try_load(context, pu, "embed-%s" % (i + 1), do_scrape=True)

        if not stream_url:
            print(f"[KDM] Loading {site_label} page to sniff stream...")
            try_load(context, url, "page", wait_until="load", do_scrape=True)

        if not stream_url:
            print("[KDM] Retry: main page with extra play triggers...")
            try:
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=55000)
                page.wait_for_timeout(6000)
                for selector in [
                    "video",
                    "[class*='play']",
                    "[class*='Play']",
                    ".vjs-big-play-button",
                    "iframe",
                    "button",
                ]:
                    try:
                        page.click(selector, timeout=3000)
                        page.wait_for_timeout(10000)
                        if stream_url:
                            break
                        found = _scrape_all_frames(page)
                        if found:
                            stream_url = found
                            print("[KDM] FOUND STREAM (retry scrape):", stream_url[:80] + "..." if len(stream_url) > 80 else stream_url)
                            break
                    except Exception:
                        pass
                if not stream_url:
                    try:
                        page.evaluate("document.querySelector('video') && document.querySelector('video').play()")
                        page.wait_for_timeout(12000)
                    except Exception:
                        pass
                if not stream_url:
                    found = _scrape_all_frames(page)
                    if found:
                        stream_url = found
                        print("[KDM] FOUND STREAM (retry scrape):", stream_url[:80] + "..." if len(stream_url) > 80 else stream_url)
                page.close()
            except Exception as e:
                print("[KDM] Retry failed:", e)
        browser.close()

    if not stream_url:
        print(f"[KDM] No stream URL found for {site_label}")
        print(
            "[KDM] Tip: start playback in a normal browser, then use the extension capture; "
            "or set KDM_PLAYWRIGHT_HEADED=1 and retry so Chromium is visible."
        )
        return None
    return stream_url


def _yt_dlp_format_playable_url(fmt: dict) -> Optional[str]:
    """First usable URL from a yt-dlp format dict (direct, DASH manifest, fragment base, etc.)."""
    if not fmt or not isinstance(fmt, dict):
        return None
    for key in ("url", "manifest_url", "fragment_base_url"):
        u = fmt.get(key)
        if u and isinstance(u, str) and u.startswith("http"):
            return u
    return None


def get_embed_page_stream_ytdlp(url: str):
    """
    yt-dlp extract_info for MultiMovies and similar embed pages.
    Returns (stream_url, title) or (None, None).
    """
    if not (url or "").strip():
        return None, None
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 35,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url.strip(), download=False)
    except Exception as e:
        print("[KDM] embed page yt-dlp extract failed:", e)
        return None, None

    if not info:
        return None, None

    title = info.get("title") or info.get("id") or "video"

    top_u = info.get("url")
    if top_u and isinstance(top_u, str) and top_u.startswith("http"):
        return top_u, str(title)

    formats = info.get("formats") or []
    best_u = None
    best_score = float("-inf")
    for f in formats:
        u = _yt_dlp_format_playable_url(f)
        if not u:
            continue
        h = f.get("height") or 0
        try:
            h = int(h) if h is not None else 0
        except (TypeError, ValueError):
            h = 0
        vbr = f.get("vbr") or f.get("tbr") or 0
        try:
            vbr = float(vbr) if vbr is not None else 0.0
        except (TypeError, ValueError):
            vbr = 0.0
        score = h * 10000 + vbr
        if ".m3u8" in u and ".m3u8.js" not in u:
            score += 1e7
        if score >= best_score:
            best_score = score
            best_u = u
    if best_u:
        return best_u, str(title)

    if formats:
        last_u = _yt_dlp_format_playable_url(formats[-1])
        if last_u:
            return last_u, str(title)

    entries = info.get("entries")
    if entries:
        for ent in entries:
            if not ent or not isinstance(ent, dict):
                continue
            u = ent.get("url")
            if u and isinstance(u, str) and u.startswith("http"):
                return u, str(ent.get("title") or title)

    return None, None


def _extract_multimovies_m3u8(url: str):
    return _extract_embed_stream_m3u8(url, "MultiMovies")


# ---------------- Backend ----------------
class Job:
    def __init__(
        self,
        url,
        q="1080p",
        out_dir=None,
        referer=None,
        title=None,
        cookie=None,
        embed_extra_headers=None,
        headers_123movies=None,
    ):
        self.id = str(int(time.time() * 1000))
        self.url, self.quality = url, q
        self.referer = referer
        self.cookie = cookie  # optional raw Cookie header from browser (for torrent/gated downloads)
        _ex = embed_extra_headers if embed_extra_headers is not None else headers_123movies
        self.embed_extra_headers = _ex if isinstance(_ex, dict) else {}
        self.title = title  # from extension/API for display until filename is set
        self.status, self.filename = "queued", None
        self.total_bytes = self.downloaded_bytes = self.speed = 0
        self.eta, self.error = None, None
        self.created = time.strftime("%Y-%m-%d %H:%M:%S")
        self.created_ts = time.time()

        self.out_dir = out_dir or os.path.join(os.path.expanduser("~"), "Downloads")
        self.pause_flag, self.stop_flag = threading.Event(), threading.Event()
        self.thread = None

    def _hook(self, d):
        if self.stop_flag.is_set():
            raise Exception("Stopped by user")

        if self.pause_flag.is_set():
            self.status = "paused"
            while self.pause_flag.is_set() and not self.stop_flag.is_set():
                time.sleep(0.3)
            if self.stop_flag.is_set():
                raise Exception("Stopped by user")

        try:
            if not self.filename:
                fn = d.get("filename")
                if fn:
                    self.filename = os.path.basename(fn)
                else:
                    info = d.get("info_dict") or {}
                    title = info.get("title")
                    ext = info.get("ext") or "mp4"
                    if title:
                        self.filename = f"{title}.{ext}"
        except Exception:
            pass

        if d.get("status") == "downloading":
            self.status = "downloading"
            self.downloaded_bytes = d.get("downloaded_bytes", 0)
            self.total_bytes = d.get("total_bytes", 0) or d.get("total_bytes_estimate", 0)
            prog = d.get("progress") or {}
            if not self.total_bytes and isinstance(prog, dict):
                self.total_bytes = prog.get("total_bytes_estimate", 0) or prog.get("total_bytes", 0)
            self.speed, self.eta = d.get("speed", 0), d.get("eta")

        elif d.get("status") == "finished":
            fn = d.get("filename")
            if fn:
                self.filename = os.path.basename(fn)
            self.status = "completed"

    def _download_stream_ffmpeg(self, http_headers: dict):
        """Fallback: ffmpeg download; HLS/AES-128 gets protocol whitelist + AAC bitstream filter + remux."""
        out_name = (self.title or "video").replace("/", "-").replace("\\", "-")[:80] + ".mp4"
        out_path = os.path.join(self.out_dir, out_name)
        ul = (self.url or "").lower()
        is_m3u8 = ".m3u8" in ul and ".m3u8.js" not in ul
        session = None
        cookie_merged = _merge_cookie_header_strings(
            (self.cookie or "").strip(),
            (http_headers.get("Cookie") or "").strip(),
        )
        if is_m3u8 and _cdn_prefers_embed_host_headers(self.url):
            session = requests.Session()
            try:
                _warm_neonhorizon_gates(session, self.url, self.referer, cookie_merged)
                cookie_merged = _merge_cookie_header_strings(
                    cookie_merged,
                    _session_cookie_header_for_url(session, self.url),
                )
            except Exception as e:
                print("[KDM] HLS session warm (ffmpeg):", e)
        hls_variants = (
            _build_hls_header_variants(self.url, http_headers, self.referer, cookie_merged=cookie_merged or None)
            if is_m3u8
            else [http_headers]
        )

        if is_m3u8:
            try:
                media_txt, media_u = _hls_resolve_media_playlist(self.url, hls_variants, session=session)
                for entry in _hls_collect_aes128_key_entries(media_txt, media_u):
                    try:
                        kb = _hls_download_key_bytes_first_ok(entry["uri"], hls_variants, session=session)
                        ok = len(kb) == 16
                        print("[KDM] HLS AES-128 key:", entry["uri"][:80], "bytes=", len(kb), "ok" if ok else "(unexpected length)")
                    except Exception as ex:
                        print("[KDM] HLS key fetch:", entry["uri"][:80], ex)
            except Exception as ex:
                print("[KDM] HLS playlist/key probe:", ex)

        def _run_ffmpeg(cmd_list):
            p = subprocess.Popen(
                cmd_list,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            lines = []
            for line in p.stderr:
                if self.stop_flag.is_set():
                    p.terminate()
                    return -1, lines
                lines.append(line)
                m = re.search(r"time=(\d+):(\d+):(\d+)", line)
                if m:
                    h, mnt, s = int(m.group(1)), int(m.group(2)), int(m.group(3))
                    self.downloaded_bytes = (h * 3600 + mnt * 60 + s) * 2000000
            p.wait()
            return p.returncode, lines

        base_pre = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "warning", "-stats"]
        if is_m3u8:
            base_pre.extend(["-protocol_whitelist", "file,http,https,tcp,tls,crypto", "-allowed_extensions", "ALL"])
        tail_bsf = ["-map", "0", "-ignore_unknown", "-c", "copy", "-bsf:a", "aac_adtstoasc", "-movflags", "+faststart"]
        tail_plain = ["-map", "0", "-ignore_unknown", "-c", "copy", "-movflags", "+faststart"]
        tail_simple = ["-c", "copy", "-movflags", "+faststart"]

        self.status = "downloading"
        err_lines = []
        rc = -1
        variants_to_try = hls_variants if is_m3u8 else [http_headers]
        for hdr in variants_to_try:
            header_str = "\r\n".join(f"{k}: {v}" for k, v in hdr.items())
            mid = ["-headers", header_str, "-i", self.url]
            if is_m3u8:
                for tail in (tail_bsf, tail_plain):
                    try:
                        if os.path.isfile(out_path):
                            os.unlink(out_path)
                    except OSError:
                        pass
                    cmd = base_pre + mid + tail + [out_path]
                    rc, err_lines = _run_ffmpeg(cmd)
                    if self.stop_flag.is_set():
                        self.status = "stopped"
                        return
                    if rc == 0 and os.path.isfile(out_path):
                        break
                if rc == 0 and os.path.isfile(out_path):
                    break
            else:
                cmd = base_pre + mid + tail_simple + [out_path]
                try:
                    if os.path.isfile(out_path):
                        os.unlink(out_path)
                except OSError:
                    pass
                rc, err_lines = _run_ffmpeg(cmd)
                if self.stop_flag.is_set():
                    self.status = "stopped"
                    return
                break

        if self.stop_flag.is_set():
            self.status = "stopped"
            return
        if rc == 0 and os.path.isfile(out_path):
            self.filename = os.path.basename(out_path)
            self.status = "completed"
            print("[KDM] Downloaded via ffmpeg")
            if is_m3u8:
                _ffmpeg_remux_mp4_faststart_inplace(out_path)
        else:
            raise Exception("ffmpeg failed: " + (err_lines[-1] if err_lines else str(rc)))

    def _download_stream_aria2(self, http_headers: dict):
        """Fallback: download stream with aria2 when yt-dlp and ffmpeg get 403."""
        out_name = (self.title or "video").replace("/", "-").replace("\\", "-")[:80] + ".mp4"
        out_path = os.path.join(self.out_dir, out_name)
        header_args = []
        for k, v in http_headers.items():
            header_args.append(f"--header={k}: {v}")
        cmd = ["aria2c", "--auto-file-renaming=false", "-d", self.out_dir, "-o", out_name]
        cmd.extend(header_args)
        cmd.append(self.url)
        self.status = "downloading"
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        _, err = proc.communicate()
        if proc.returncode == 0 and os.path.isfile(out_path):
            self.filename = os.path.basename(out_path)
            self.status = "completed"
            print("[KDM] Downloaded via aria2")
        else:
            raise Exception("aria2 failed: " + (err.strip() if err else str(proc.returncode)))

    def _download_generic(self):
        """Download a generic file (software, game, etc.) via HTTP."""
        import re
        self.status = "starting"
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"}
            if self.referer:
                headers["Referer"] = self.referer
            if self.cookie:
                headers["Cookie"] = self.cookie
            try:
                verify = __import__("certifi").where()
            except Exception:
                verify = True
            r = None
            for attempt in range(3):
                if self.stop_flag.is_set():
                    self.status = "stopped"
                    return
                try:
                    r = requests.get(self.url, stream=True, headers=headers, timeout=45, allow_redirects=True, verify=verify)
                    r.raise_for_status()
                    break
                except (requests.exceptions.ConnectionError, OSError, requests.exceptions.ChunkedEncodingError) as e:
                    if attempt < 2:
                        time.sleep(2)
                        continue
                    self.status = "error"
                    self.error = "Connection failed after 3 tries. Try: http://httpbin.org/bytes/102400 (100KB test file)"
                    print("[KDM] Generic download error:", self.error)
                    return
            if r is None:
                return
            self.total_bytes = int(r.headers.get("Content-Length", 0)) or 0
            fn = None
            cd = r.headers.get("Content-Disposition")
            if cd:
                m = re.search(r'filename[*]?=(?:UTF-8\'\')?["\']?([^"\';]+)', cd, re.I)
                if m:
                    fn = m.group(1).strip().strip('"\'')
            if not fn:
                fn = urlparse(self.url).path.split("/")[-1] or "download"
            fn = fn.strip() or "download"
            if not os.path.splitext(fn)[1]:
                fn = fn + ".bin"
            path = os.path.join(self.out_dir, fn)
            self.filename = os.path.basename(path)
            self.downloaded_bytes = 0
            self.status = "downloading"
            chunk_size = 256 * 1024
            with open(path, "wb") as f:
                for chunk in r.iter_content(chunk_size=chunk_size):
                    if self.stop_flag.is_set():
                        self.status = "stopped"
                        return
                    while self.pause_flag.is_set() and not self.stop_flag.is_set():
                        time.sleep(0.2)
                    if not chunk:
                        continue
                    f.write(chunk)
                    self.downloaded_bytes += len(chunk)
            if not self.stop_flag.is_set():
                self.status = "completed"
        except requests.HTTPError as e:
            if self.stop_flag.is_set():
                self.status = "stopped"
            else:
                self.status = "error"
                if e.response is not None and e.response.status_code == 404:
                    self.error = "File not found (404). Test with: http://ipv4.download.thinkbroadband.com/1MB.zip"
                else:
                    self.error = str(e)
                print("[KDM] Generic download error:", self.error)
        except requests.exceptions.SSLError as e:
            if self.stop_flag.is_set():
                self.status = "stopped"
            else:
                self.status = "error"
                self.error = "SSL certificate error. Test with HTTP link: http://ipv4.download.thinkbroadband.com/1MB.zip"
                print("[KDM] Generic download error:", self.error)
        except Exception as e:
            if self.stop_flag.is_set():
                self.status = "stopped"
            else:
                self.status = "error"
                self.error = str(e)
                print("[KDM] Generic download error:", e)

    def _run_aria2_torrent(self, torrent_input: str):
        """Download torrent content via aria2 (like BitTorrent/uTorrent)."""
        self.status = "downloading"
        out_dir = os.path.abspath(self.out_dir)
        os.makedirs(out_dir, exist_ok=True)
        is_magnet = torrent_input.strip().lower().startswith("magnet:")
        aria2_bin = shutil.which("aria2c") or "aria2c"
        # Public trackers so torrents connect faster (like uTorrent/BitTorrent)
        trackers = (
            "udp://tracker.opentrackr.org:1337/announce,"
            "udp://open.stealth.si:80/announce,"
            "udp://tracker.torrent.eu.org:451/announce,"
            "udp://exodus.desync.com:6969/announce,"
            "udp://tracker.moeking.me:6969/announce"
        )
        # Minimal options to avoid exit 28 (conflict with ~/.aria2/aria2.conf on macOS)
        cmd = [
            aria2_bin,
            "--no-conf",
            "-d", out_dir,
            "--file-allocation=none",
            "--summary-interval=1",
            "--allow-overwrite=true",
            "--bt-stop-timeout=600",
            "--bt-tracker=" + trackers,
        ]
        if is_magnet:
            cmd.append(torrent_input)
        else:
            cmd.extend(["-T", os.path.abspath(torrent_input)])
        tmp_home = None
        try:
            # Use temp HOME so aria2 doesn't load ~/.aria2/aria2.conf (avoids exit 28 on macOS)
            env = os.environ.copy()
            tmp_home = tempfile.mkdtemp(prefix="kdm_aria2_")
            env["HOME"] = tmp_home
            dht_dir = os.path.join(tmp_home, ".cache", "aria2")
            os.makedirs(dht_dir, exist_ok=True)
            dht_path = os.path.join(dht_dir, "dht.dat")
            cmd.extend(["--enable-dht=true", "--dht-file-path=" + dht_path])

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env,
                cwd=out_dir,
            )
            aria2_err_lines = []
            for line in (iter(proc.stdout.readline, "") if proc.stdout else []):
                if self.stop_flag.is_set():
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    self.status = "stopped"
                    return
                if line and ("Exception" in line or "errorCode" in line or "Error" in line or "error" in line.lower()):
                    aria2_err_lines.append(line.strip())
                parsed = _parse_aria2_progress(line)
                if parsed:
                    self.downloaded_bytes, total_parsed, speed = parsed
                    if total_parsed > 0:
                        self.total_bytes = total_parsed
                    self.speed = speed
                    self.status = "downloading"
            proc.wait()
            if proc.returncode == 0 and not self.stop_flag.is_set():
                self.status = "completed"
                self.filename = "(torrent content in folder)"
                print("[KDM] Torrent download completed via aria2")
            elif not self.stop_flag.is_set():
                self.status = "error"
                err_detail = (aria2_err_lines[-1] if aria2_err_lines else "") or f"aria2 exited with code {proc.returncode}"
                self.error = err_detail
                print("[KDM]", self.error)
                for L in aria2_err_lines:
                    print("[KDM aria2]", L)
                if proc.returncode == 28:
                    fix = " (Fix: rename ~/.aria2/aria2.conf to aria2.conf.bak and restart KDM)"
                    self.error += fix
                    print("[KDM]", fix)
        except FileNotFoundError:
            self.status = "error"
            self.error = "aria2c not found. Install aria2 (e.g. brew install aria2)"
            print("[KDM]", self.error)
        except Exception as e:
            self.status = "error"
            self.error = str(e)
            print("[KDM] aria2 error:", e)
        finally:
            if tmp_home and os.path.isdir(tmp_home):
                try:
                    shutil.rmtree(tmp_home, ignore_errors=True)
                except Exception:
                    pass

    def _run(self):
        ###############################################
        #   Magnet link → KDM downloads via aria2, else open in system torrent app
        ###############################################
        if _is_magnet_url(self.url):
            if _aria2_available():
                self._run_aria2_torrent(self.url)
                if self.status == "error" and "28" in str(self.error):
                    # aria2 exit 28: try renaming user config and retry once
                    conf_path = os.path.expanduser("~/.aria2/aria2.conf")
                    if os.path.isfile(conf_path):
                        bak = conf_path + ".bak"
                        try:
                            os.rename(conf_path, bak)
                            print("[KDM] Renamed ~/.aria2/aria2.conf to .bak, retrying...")
                            self.status = "downloading"
                            self.error = ""
                            self._run_aria2_torrent(self.url)
                        except OSError as e:
                            print("[KDM] Could not rename config:", e)
            else:
                self.status = "starting"
                try:
                    if sys.platform == "darwin":
                        subprocess.Popen(["open", self.url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    elif sys.platform.startswith("win"):
                        os.startfile(self.url)
                    else:
                        subprocess.Popen(["xdg-open", self.url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    self.status = "completed"
                    self.filename = "magnet link (opened in torrent app)"
                    print("[KDM] Magnet link opened with default torrent app (install aria2 for built-in download)")
                except Exception as e:
                    self.status = "error"
                    self.error = str(e)
                    print("[KDM] Magnet open failed:", e)
            return

        # Extension sometimes sends JW Player / analytics URLs instead of .m3u8 — must not hit generic HTTP.
        if self.referer and _is_bad_capture_url(self.url):
            print("[KDM] Bad capture URL; using referer page URL for extraction")
            self.url = self.referer

        ###############################################
        #   Generic file (software, .torrent, etc) → HTTP
        #   .torrent / torfile.bin (YTS, Nyaa, Torrent Galaxy, etc.): KDM downloads via aria2
        ###############################################
        is_torrent = _is_torrent_url(self.url) or _is_torrent_by_title(self.title)
        use_video_path = _is_video_url(self.url)  # stream CDNs (neonhorizonworkshops etc) must use yt-dlp
        if not use_video_path:
            if is_torrent and _aria2_available():
                # Get .torrent file first (may be URL or already path)
                torrent_path = None
                if self.url.lower().startswith("http"):
                    # Download .torrent to temp file then run aria2 on it (like BitTorrent/uTorrent)
                    uas = [
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                    ]
                    ref = self.referer
                    ul = self.url.lower()
                    if not ref and "nyaa.si" in ul:
                        ref = "https://nyaa.si/"
                    elif not ref and "1337x" in ul:
                        ref = "https://1337x.to/"
                    elif not ref and ("thepiratebay" in ul or "tpb." in ul or "piratebay" in ul):
                        ref = "https://thepiratebay.org/"
                    elif not ref and "torrentgalaxy" in ul:
                        ref = "https://torrentgalaxy.to/"
                    elif not ref and ("yts-" in ul or "yts." in ul or "yts.lt" in ul or "yts.mx" in ul):
                        try:
                            from urllib.parse import urlparse
                            p = urlparse(self.url)
                            if p.scheme and p.netloc:
                                ref = p.scheme + "://" + p.netloc + "/"
                        except Exception:
                            ref = (self.url.rsplit("/", 1)[0] + "/") if "/" in self.url else ""
                    if not ref:
                        try:
                            from urllib.parse import urlparse
                            p = urlparse(self.url)
                            if p.scheme and p.netloc:
                                ref = p.scheme + "://" + p.netloc + "/"
                        except Exception:
                            pass
                    if not ref and "/" in self.url:
                        ref = self.url.rsplit("/", 1)[0] + "/"
                    torrent_path = None
                    last_err = None
                    for ua in uas:
                        if self.stop_flag.is_set():
                            return
                        try:
                            headers = {"User-Agent": ua, "Accept": "application/x-bittorrent,*/*"}
                            if ref:
                                headers["Referer"] = ref
                            if self.cookie:
                                headers["Cookie"] = self.cookie
                            r = requests.get(self.url, headers=headers, timeout=30, allow_redirects=True)
                            r.raise_for_status()
                            if len(r.content) < 50:
                                raise ValueError("Downloaded .torrent file is too small or empty")
                            with tempfile.NamedTemporaryFile(suffix=".torrent", delete=False) as f:
                                f.write(r.content)
                                torrent_path = f.name
                            print("[KDM] .torrent file fetched, starting aria2 (BitTorrent-style)...")
                            break
                        except Exception as e:
                            last_err = e
                            continue
                    if not torrent_path or not os.path.isfile(torrent_path):
                        self.status = "error"
                        self.error = str(last_err) if last_err else "Failed to fetch .torrent"
                        print("[KDM] Failed to fetch .torrent:", self.error)
                        return
                if torrent_path and os.path.isfile(torrent_path):
                    try:
                        self._run_aria2_torrent(torrent_path)
                        if self.status == "error" and "28" in str(self.error):
                            conf_path = os.path.expanduser("~/.aria2/aria2.conf")
                            if os.path.isfile(conf_path):
                                try:
                                    os.rename(conf_path, conf_path + ".bak")
                                    print("[KDM] Renamed ~/.aria2/aria2.conf, retrying...")
                                    self.status = "downloading"
                                    self.error = ""
                                    self._run_aria2_torrent(torrent_path)
                                except OSError:
                                    pass
                    finally:
                        try:
                            os.unlink(torrent_path)
                        except OSError:
                            pass
                else:
                    self._download_generic()
                    if self.status == "completed" and self.filename:
                        path = os.path.join(self.out_dir, self.filename)
                        if os.path.isfile(path):
                            self._run_aria2_torrent(path)
            else:
                # Stream CDN URLs (mistwolf, /pl/, .m3u8, etc.) → use yt-dlp, not generic
                u = (self.url or "").lower()
                if _is_stream_cdn_url(self.url, self.referer) and ".m3u8.js" not in u:
                    use_video_path = True
                    print("[KDM] Stream CDN detected → using yt-dlp")
                else:
                    self._download_generic()
                    if _is_torrent_url(self.url) and self.status == "completed" and self.filename:
                        path = os.path.join(self.out_dir, self.filename)
                        if os.path.isfile(path):
                            try:
                                if sys.platform == "darwin":
                                    subprocess.Popen(["open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                                elif sys.platform.startswith("win"):
                                    os.startfile(path)
                                else:
                                    subprocess.Popen(["xdg-open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                                print("[KDM] .torrent opened in default app (install aria2 for built-in download)")
                            except Exception as e:
                                print("[KDM] Could not open .torrent file:", e)
            if not use_video_path:
                return

        ###############################################
        #   PATCH: MultiMovies → Extract stream       #
        ###############################################
        if _is_multimovies(self.url):
            print("[KDM] MultiMovies detected → extracting stream...")
            try:
                real_stream, mm_title = get_embed_page_stream_ytdlp(self.url)
                if real_stream:
                    print(
                        "[KDM] MultiMovies stream (yt-dlp):",
                        real_stream[:80] + "..." if len(real_stream) > 80 else real_stream,
                    )
                    self.url = real_stream
                    if mm_title and not (self.title and str(self.title).strip()):
                        self.title = mm_title[:200]
                else:
                    print("[KDM] MultiMovies: yt-dlp had no URL → Playwright fallback...")
                    real_stream = _extract_multimovies_m3u8(self.url)
                    if real_stream:
                        print(
                            "[KDM] Stream extracted (Playwright):",
                            real_stream[:80] + "..." if len(real_stream) > 80 else real_stream,
                        )
                        self.url = real_stream
                    else:
                        self.status = "error"
                        self.error = "MultiMovies: Could not extract stream. Play the video on the page, then try again."
                        print("[KDM]", self.error)
                        return
            except Exception as e:
                self.status = "error"
                self.error = f"MultiMovies: {e}"
                print("[KDM]", self.error)
                return

        #########################################################
        #   NORMAL YT-DLP DOWNLOADER (unchanged except above)   #
        #########################################################

        # Format: "adaptive/best" = best available; "720p" etc = cap height
        if self.quality and (self.quality == "adaptive/best" or "/" in self.quality):
            fmt = "bestvideo+bestaudio/best"
        else:
            h = (self.quality or "1080p").rstrip("pP")
            if h.isdigit():
                fmt = f"bestvideo[height<={h}]+bestaudio/best"
            else:
                fmt = "bestvideo+bestaudio/best"
        ujob = (self.url or "").lower()
        is_hls_job = ".m3u8" in ujob and ".m3u8.js" not in ujob
        # Browser-like headers and YouTube client options to avoid HTTP 403 / SABR issues
        http_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-us,en;q=0.5",
        }
        if self.referer:
            http_headers["Referer"] = self.referer
        # Stream CDNs (embed players, mistwolf88, etc.): headers to avoid 403 Forbidden
        is_stream_cdn = _is_stream_cdn_url(self.url, self.referer)
        stream_base = None
        if is_stream_cdn:
            try:
                ou = urlparse(self.url)
                if ou.scheme and ou.netloc:
                    stream_base = f"{ou.scheme}://{ou.netloc}/"
                    stream_origin = ou.scheme + "://" + ou.netloc
                    http_headers["Origin"] = stream_origin
                    http_headers["Accept"] = "*/*"
                    ujl = (self.url or "").lower()
                    m3u8_with_parent_referer = (
                        ".m3u8" in ujl and ".m3u8.js" not in ujl
                        and self.referer
                        and str(self.referer).strip().lower().startswith("http")
                    )
                    neon = _cdn_prefers_embed_host_headers(self.url)
                    if m3u8_with_parent_referer:
                        # CDN auth tokens expire in seconds — no session warm before yt-dlp; Chrome cookies come from cookies_from_browser.
                        ck = (self.cookie or "").strip()
                        if neon and ou.scheme and ou.netloc:
                            ref_dir = self.url.rsplit("/", 1)[0] + "/" if "/" in self.url else stream_base
                            http_headers["User-Agent"] = CHROME_WIN_UA
                            http_headers["Accept"] = "application/vnd.apple.mpegurl, application/x-mpegURL, */*;q=0.8"
                            http_headers["Origin"] = stream_origin
                            http_headers["Referer"] = ref_dir or stream_base
                            http_headers["Sec-Fetch-Dest"] = "empty"
                            http_headers["Sec-Fetch-Mode"] = "cors"
                            http_headers["Sec-Fetch-Site"] = "same-origin"
                            http_headers.update(_hls_chrome_client_hint_headers())
                            if ck:
                                http_headers["Cookie"] = ck
                        else:
                            xs = _hls_cross_site_headers(self.referer.strip(), ck or None)
                            http_headers.update({k: v for k, v in xs.items() if v is not None and str(v).strip() != ""})
                    elif neon:
                        ref_dir = self.url.rsplit("/", 1)[0] + "/" if "/" in self.url else stream_base
                        http_headers["Referer"] = ref_dir
                        http_headers["Sec-Fetch-Site"] = "same-origin"
                    elif self.referer and "multimovies" in (self.referer or "").lower():
                        http_headers["Referer"] = self.referer
                        http_headers["Sec-Fetch-Site"] = "cross-site"
                    else:
                        http_headers["Referer"] = stream_base
                        http_headers["Sec-Fetch-Site"] = "same-origin"
                    if self.cookie and "Cookie" not in http_headers:
                        http_headers["Cookie"] = self.cookie
                    http_headers.setdefault("Sec-Fetch-Dest", "empty")
                    http_headers.setdefault("Sec-Fetch-Mode", "cors")
            except Exception:
                pass
            if self.referer and str(self.referer).strip().lower().startswith("http"):
                _apply_embed_extension_headers(http_headers, self.referer, self.embed_extra_headers, self.url)
        # Dailymotion: 403 on m3u8 – use Chrome cookies + headers
        if "dailymotion.com" in (self.url or "").lower():
            http_headers["Referer"] = http_headers.get("Referer") or "https://www.dailymotion.com/"
            http_headers["Origin"] = "https://www.dailymotion.com"
            http_headers["Cookie"] = "family_filter=off; ff=off; lang=en"

        extractor_args = {"youtube": {"player_client": ["android", "web"]}}
        opts = {
            "progress_hooks": [self._hook],
            "format": fmt,
            "merge_output_format": "mp4",
            "quiet": True,
            "noplaylist": True,
            "outtmpl": os.path.join(self.out_dir, "%(title)s.%(ext)s"),
            "continuedl": True,
            "http_headers": http_headers,
            "extractor_args": extractor_args,
            "concurrent_fragment_downloads": 16,
        }
        # Dailymotion: try Chrome cookies to avoid 403
        if "dailymotion.com" in (self.url or "").lower():
            try:
                opts["cookies_from_browser"] = ("chrome",)
            except Exception:
                pass
        if is_stream_cdn:
            for browser in (["chrome", "safari"] if sys.platform == "darwin" else ["chrome"]):
                try:
                    opts["cookies_from_browser"] = (browser,)
                    break
                except Exception:
                    continue

        self.status = "starting"

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([self.url])

            if not self.stop_flag.is_set():
                self.status = "completed"
                if is_hls_job and self.filename:
                    try:
                        out = os.path.join(self.out_dir, self.filename)
                        if os.path.isfile(out) and out.lower().endswith(".mp4"):
                            _ffmpeg_remux_mp4_faststart_inplace(out)
                    except Exception:
                        pass

        except Exception as e:
            if self.stop_flag.is_set():
                self.status = "stopped"
            else:
                err_str = str(e)
                stream_fallback_errors = ("403" in err_str or "Did not get any data blocks" in err_str or
                    "data blocks" in err_str or "No video formats" in err_str or "Unable to download" in err_str)
                if stream_fallback_errors and is_stream_cdn:
                    last_err = err_str
                    # Retry with alternate Referer (playlist dir / CDN root / parent page)
                    referers_to_try = []
                    pl_dir = (self.url.rsplit("/", 1)[0] + "/") if "/" in (self.url or "") else None
                    for cand in (pl_dir, stream_base, self.referer):
                        if cand and cand not in referers_to_try:
                            referers_to_try.append(cand)
                    for alt_ref in referers_to_try:
                        try:
                            opts2 = dict(opts)
                            opts2["http_headers"] = dict(http_headers)
                            opts2["http_headers"]["Referer"] = alt_ref
                            if _cdn_prefers_embed_host_headers(self.url):
                                try:
                                    ou = urlparse(self.url)
                                    if ou.scheme and ou.netloc:
                                        o = f"{ou.scheme}://{ou.netloc}"
                                        opts2["http_headers"]["Origin"] = o
                                        opts2["http_headers"]["Sec-Fetch-Site"] = (
                                            "same-origin" if (alt_ref or "").startswith(o) else "cross-site"
                                        )
                                except Exception:
                                    pass
                            with yt_dlp.YoutubeDL(opts2) as ydl:
                                ydl.download([self.url])
                            if not self.stop_flag.is_set():
                                self.status = "completed"
                                if is_hls_job and self.filename:
                                    try:
                                        out = os.path.join(self.out_dir, self.filename)
                                        if os.path.isfile(out) and out.lower().endswith(".mp4"):
                                            _ffmpeg_remux_mp4_faststart_inplace(out)
                                    except Exception:
                                        pass
                                return
                        except Exception:
                            pass
                    # Try ffmpeg with multiple Referers
                    if shutil.which("ffmpeg"):
                        pl_base = (self.url.rsplit("/", 1)[0] + "/") if "/" in self.url else stream_base
                        for ref in [self.referer, pl_base, stream_base]:
                            if not ref:
                                continue
                            print("[KDM] yt-dlp failed → trying ffmpeg (Referer: %s...)" % (ref[:50] or ""))
                            try:
                                hd = dict(http_headers)
                                hd["Referer"] = ref
                                self._download_stream_ffmpeg(hd)
                                return
                            except Exception as e2:
                                last_err = str(e2)
                                pass
                    # Try aria2 with headers (skip for AES-128 HLS — produces corrupt/encrypted blobs)
                    if _aria2_available():
                        ul_ar = (self.url or "").lower()
                        if ".m3u8" in ul_ar:
                            print("[KDM] Skip aria2 for HLS playlists; use ffmpeg/yt-dlp")
                        else:
                            print("[KDM] ffmpeg failed → trying aria2...")
                            pl_base = self.url.rsplit("/", 1)[0] + "/" if "/" in self.url else stream_base
                            for ref in [self.referer, pl_base, stream_base]:
                                if not ref:
                                    continue
                                try:
                                    hd = dict(http_headers)
                                    hd["Referer"] = ref
                                    self._download_stream_aria2(hd)
                                    return
                                except Exception:
                                    pass
                    self.status = "error"
                    self.error = (
                        "Stream failed. Tips: 1) Play the video in the browser tab first. "
                        "2) Start the download while the tab is still open. "
                        "3) Retry with a different server or quality if the site offers one."
                    )
                    print("[KDM]", self.error)
                else:
                    self.status = "error"
                    self.error = err_str
                    print("[KDM] yt-dlp error:", e)
    
    def start(self):
        if not self.thread or not self.thread.is_alive():
            self.stop_flag.clear()
            self.pause_flag.clear()
            if self.status in ("stopped", "paused", "error"):
                self.status = "queued"
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()

    def pause(self):
        self.pause_flag.set()
        if self.status in ("downloading", "starting"):
            self.status = "paused"

    def resume(self):
        self.pause_flag.clear()
        if self.status in ("paused", "stopped", "error"):
            self.status = "queued"
        if not (self.thread and self.thread.is_alive()):
            self.start()

    def stop(self):
        self.stop_flag.set()
        self.pause_flag.clear()
        if self.status in ("downloading", "paused", "starting", "queued"):
            self.status = "stopped"

    def soft_stop(self):
        self.pause_flag.set()
        if self.status in ("downloading", "starting", "paused", "queued"):
            self.status = "stopped"

    def to_dict(self):
        name = self.filename
        if not name and self.title:
            name = (self.title[:60] + "…") if len(self.title) > 60 else self.title
        if not name and self.url:
            name = (urlparse(self.url).path or "").strip("/").split("/")[-1] or urlparse(self.url).netloc or "(unknown)"
        if not name:
            name = "(unknown)"
        return {
            "id": self.id,
            "url": self.url,
            "name": name,
            "quality": self.quality,
            "status": self.status,
            "size": self.total_bytes,
            "downloaded": self.downloaded_bytes,
            "speed": self.speed,
            "eta": self.eta,
            "created": self.created,
            "out_dir": self.out_dir,
        }

# ---------------- Manager ----------------
class Manager:
    def __init__(self):
        self.jobs, self.lock = {}, threading.Lock()

    def add(
        self,
        url,
        q="1080p",
        out=None,
        referer=None,
        title=None,
        cookie=None,
        embed_extra_headers=None,
        headers_123movies=None,
    ):
        def _norm(u):
            return (u or "").strip().rstrip("/")
        url_norm = _norm(url)
        DEDUP_SEC = 600  # skip duplicate URL within 10 min
        with self.lock:
            for j in self.jobs.values():
                if _norm(j.url) != url_norm:
                    continue
                if j.status in ("queued", "downloading", "starting", "paused"):
                    return j  # already in progress
                if j.status in ("completed", "error", "stopped") and (time.time() - getattr(j, "created_ts", 0)) < DEDUP_SEC:
                    return j  # recently finished, avoid re-queue when Chrome reopens
        _eh = embed_extra_headers if embed_extra_headers is not None else headers_123movies
        j = Job(url, q, out, referer=referer, title=title, cookie=cookie, embed_extra_headers=_eh)
        with self.lock:
            self.jobs[j.id] = j
        j.start()
        return j

    def list(self):
        with self.lock:
            return [j.to_dict() for j in self.jobs.values()]

    def _get(self, i):
        with self.lock:
            return self.jobs.get(i)

    def pause(self, i): 
        j = self._get(i); j and j.pause()

    def resume(self, i): 
        j = self._get(i); j and j.resume()

    def stop(self, i): 
        j = self._get(i); j and j.stop()

    def soft_stop(self, i): 
        j = self._get(i); j and j.soft_stop()

    def pause_all_active(self):
        with self.lock:
            for j in self.jobs.values():
                if j.status in ("downloading", "running", "starting"):
                    j.pause()
                    j.status = "paused"

    def delete(self, job_id):
        with self.lock:
            if job_id in self.jobs:
                del self.jobs[job_id]

# ---------------- Custom Events ----------------
class DownloadEvent(QEvent):
    EVENT_TYPE = QEvent.Type(QEvent.registerEventType())

    def __init__(self, url, title, already_enqueued=True):
        super().__init__(DownloadEvent.EVENT_TYPE)
        self.url = url
        self.title = title
        self.already_enqueued = already_enqueued

# ---------------- Download Info Window ----------------
class DownloadInfoWindow(QDialog):
    def __init__(self, url, filename, parent=None, already_enqueued=False):
        super().__init__(parent)
        self.url = url
        self.filename = filename
        self.parent = parent
        self.already_enqueued = already_enqueued
        self.setWindowTitle("Download File Info")
        self.setFixedSize(500, 400)
        self.setStyleSheet("""
            QDialog {
                background-color: #111;
                color: white;
                font-family: 'Segoe UI';
            }
            QLabel {
                color: white;
                font-size: 10pt;
            }
            QLineEdit, QComboBox {
                background: #1a1a1a;
                color: white;
                border: 1px solid #333;
                padding: 6px;
                border-radius: 4px;
                font-size: 10pt;
            }
            QGroupBox {
                color: #7cc8ff;
                border: 1px solid #333;
                border-radius: 6px;
                margin-top: 10px;
                font-size: 10pt;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
            QCheckBox {
                color: #ccc;
                font-size: 9pt;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }
            QCheckBox::indicator:unchecked {
                border: 1px solid #555;
                background: #1a1a1a;
            }
            QCheckBox::indicator:checked {
                border: 1px solid #4da6ff;
                background: #0078d4;
            }
            QPushButton {
                background-color: #1a1a1a;
                color: white;
                border: 1px solid #444;
                padding: 8px 20px;
                border-radius: 4px;
                font-size: 10pt;
                min-width: 100px;
            }
            QPushButton:hover {
                background: #003366;
                border: 1px solid #4da6ff;
            }
            QPushButton:pressed {
                background: #004080;
                border: 1px solid #66b2ff;
            }
            QPushButton:disabled {
                background: #333;
                color: #666;
                border: 1px solid #555;
            }
        """)
        
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        
        # Title bar with black background (matching KDM)
        title_layout = QHBoxLayout()
        title_layout.setContentsMargins(0, 0, 0, 10)
        
        title_label = QLabel("Download File Info")
        title_label.setStyleSheet("""
            QLabel {
                color: white;
                font-size: 14pt;
                font-weight: bold;
                background: #000;
                padding: 8px 12px;
                border-radius: 4px;
            }
        """)
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        layout.addLayout(title_layout)
        
        # URL section
        url_group = QGroupBox("URL")
        url_layout = QVBoxLayout()
        self.url_label = QLabel(self.url[:80] + "..." if len(self.url) > 80 else self.url)
        self.url_label.setWordWrap(True)
        self.url_label.setStyleSheet("color: #aaa; font-size: 9pt; background: #0a0a0a; padding: 8px; border-radius: 4px;")
        url_layout.addWidget(self.url_label)
        url_group.setLayout(url_layout)
        layout.addWidget(url_group)
        
        # Category and default folder from URL
        u = (self.url or "").lower()
        if any(x in u for x in [".dmg", ".pkg", ".exe", ".msi"]):
            category, subdir = "Software", "Software"
        elif any(x in u for x in [".pdf", ".doc", ".docx", ".xls", ".txt"]):
            category, subdir = "Document", "Document"
        elif any(x in u for x in [".mp3", ".m4a", ".wav", ".flac", ".aac"]):
            category, subdir = "Audio", "Audio"
        else:
            category, subdir = "Video", "Video"
        base_downloads = os.path.join(os.path.expanduser("~"), "Downloads")
        default_dir = os.path.join(base_downloads, subdir)
        os.makedirs(default_dir, exist_ok=True)
        default_path = os.path.join(default_dir, self.filename)

        # Category section
        category_group = QGroupBox("Category")
        category_layout = QVBoxLayout()
        self.category_combo = QComboBox()
        self.category_combo.addItems(["Video", "Audio", "Document", "Software", "Other"])
        self.category_combo.setCurrentText(category)
        self.category_combo.currentTextChanged.connect(self._on_category_changed)
        self._default_filename = self.filename
        category_layout.addWidget(self.category_combo)
        category_group.setLayout(category_layout)
        layout.addWidget(category_group)
        
        # Save As section
        save_group = QGroupBox("Save As")
        save_layout = QVBoxLayout()
        
        # Folder selection
        folder_layout = QHBoxLayout()
        self.folder_edit = QLineEdit()
        self.folder_edit.setText(default_path)
        folder_layout.addWidget(self.folder_edit, 1)
        
        self.browse_btn = QPushButton("...")
        self.browse_btn.setFixedWidth(40)
        self.browse_btn.clicked.connect(self.browse_folder)
        folder_layout.addWidget(self.browse_btn)
        save_layout.addLayout(folder_layout)
        
        # Remember path checkbox
        self.remember_checkbox = QCheckBox("Remember this path for this category")
        self.remember_checkbox.setChecked(True)
        save_layout.addWidget(self.remember_checkbox)
        
        save_group.setLayout(save_layout)
        layout.addWidget(save_group)
        
        # Button row
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 10, 0, 0)
        
        self.download_later_btn = QPushButton("Download Later")
        self.download_later_btn.clicked.connect(self.download_later)
        button_layout.addWidget(self.download_later_btn)
        
        button_layout.addStretch()
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)
        
        self.start_download_btn = QPushButton("Start Download")
        self.start_download_btn.setStyleSheet("""
            QPushButton {
                background: #0078d4;
                color: white;
                font-weight: bold;
                border: 1px solid #4da6ff;
            }
            QPushButton:hover {
                background: #106ebe;
                border: 1px solid #66b2ff;
            }
        """)
        self.start_download_btn.clicked.connect(self.start_download)
        button_layout.addWidget(self.start_download_btn)
        
        layout.addLayout(button_layout)

    def _on_category_changed(self, category):
        base = os.path.join(os.path.expanduser("~"), "Downloads", category)
        os.makedirs(base, exist_ok=True)
        self.folder_edit.setText(os.path.join(base, self._default_filename))
    
    def browse_folder(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, 
            "Save Video As",
            self.folder_edit.text(),
            "Video Files (*.mp4 *.mkv *.avi *.mov *.webm);;All Files (*.*)"
        )
        if file_path:
            self.folder_edit.setText(file_path)
    
    def download_later(self):
        # Add to queue for later download
        QMessageBox.information(self, "Download Later", "Video added to queue for later download.")
        self.accept()
    
    def start_download(self):
        # Enqueue job when opened from Add URL (not when from extension; already enqueued)
        if not self.already_enqueued:
            try:
                folder = self.folder_edit.text()
                title = os.path.basename(folder) or "download"
                requests.post(
                    f"http://{API_HOST}:{API_PORT}/enqueue_with_info",
                    json={"url": self.url, "title": title},
                    timeout=5
                )
            except Exception:
                pass
        self.accept()
        return {
            'url': self.url,
            'filename': os.path.basename(self.folder_edit.text()),
            'folder': os.path.dirname(self.folder_edit.text()),
            'category': self.category_combo.currentText(),
            'description': "",  # Empty since description was removed
            'remember_path': self.remember_checkbox.isChecked()
        }

# ---------------- Download Status Window ----------------
class DownloadStatusWindow(QDialog):
    def __init__(self, download_info, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.download_info = download_info
        self.is_paused = False
        self.is_cancelled = False
        self.is_completed = False
        self.progress = 0
        self.downloaded_bytes = 0
        self.total_bytes = 0
        self.job_id = None  # set when we find matching job from backend
        self._last_job = None  # latest job dict for open-on-complete (torrent folder etc.)
        
        self.setWindowTitle("Download Status")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowCloseButtonHint | Qt.WindowType.WindowMinimizeButtonHint | Qt.WindowType.WindowMaximizeButtonHint)
        self.setStyleSheet("""
            QDialog {
                background-color: #111;
                color: white;
                font-family: 'Segoe UI';
            }
            QLabel {
                color: white;
                font-size: 10pt;
            }
            QProgressBar {
                border: 1px solid #333;
                background: #1a1a1a;
                color: white;
                text-align: center;
                border-radius: 4px;
                height: 20px;
            }
            QProgressBar::chunk {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 #0078d4, stop: 1 #00aaff
                );
                border-radius: 3px;
            }
            QGroupBox {
                color: #7cc8ff;
                border: 1px solid #333;
                border-radius: 6px;
                margin-top: 10px;
                font-size: 10pt;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
            QPushButton {
                background-color: #1a1a1a;
                color: white;
                border: 1px solid #444;
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 10pt;
                min-width: 80px;
            }
            QPushButton:hover {
                background: #003366;
                border: 1px solid #4da6ff;
            }
            QPushButton:pressed {
                background: #004080;
                border: 1px solid #66b2ff;
            }
            QPushButton:disabled {
                background: #333;
                color: #666;
                border: 1px solid #555;
            }
            QCheckBox {
                color: #ccc;
                font-size: 9pt;
            }
            QTextEdit {
                background: #0a0a0a;
                color: #aaa;
                border: 1px solid #333;
                border-radius: 4px;
                font-family: 'Consolas', monospace;
                font-size: 9pt;
            }
        """)
        
        self.init_ui()
        self.start_polling()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        
        # URL section
        url_group = QGroupBox("Download URL")
        url_layout = QVBoxLayout()
        url_text = self.download_info['url']
        self.url_label = QLabel(url_text[:100] + "..." if len(url_text) > 100 else url_text)
        self.url_label.setWordWrap(True)
        self.url_label.setStyleSheet("color: #aaa; font-size: 9pt; background: #0a0a0a; padding: 8px; border-radius: 4px;")
        url_layout.addWidget(self.url_label)
        url_group.setLayout(url_layout)
        layout.addWidget(url_group)
        
        # Status section
        status_group = QGroupBox("Download Status")
        status_layout = QGridLayout()
        status_layout.setHorizontalSpacing(20)
        status_layout.setVerticalSpacing(8)
        
        # Row 1
        status_layout.addWidget(QLabel("Status:"), 0, 0)
        self.status_label = QLabel("Downloading...")
        self.status_label.setStyleSheet("color: #4da6ff; font-weight: bold;")
        status_layout.addWidget(self.status_label, 0, 1)
        
        status_layout.addWidget(QLabel("File size:"), 0, 2)
        self.size_label = QLabel("212.00 MB")
        status_layout.addWidget(self.size_label, 0, 3)
        
        # Row 2
        status_layout.addWidget(QLabel("Downloaded:"), 1, 0)
        self.downloaded_label = QLabel("0 MB (0%)")
        status_layout.addWidget(self.downloaded_label, 1, 1)
        
        status_layout.addWidget(QLabel("Transfer rate:"), 1, 2)
        self.speed_label = QLabel("0 KB/s")
        status_layout.addWidget(self.speed_label, 1, 3)
        
        # Row 3
        status_layout.addWidget(QLabel("Time left:"), 2, 0)
        self.time_label = QLabel("--")
        status_layout.addWidget(self.time_label, 2, 1)
        
        status_layout.addWidget(QLabel("Resume capability:"), 2, 2)
        self.resume_label = QLabel("Yes")
        self.resume_label.setStyleSheet("color: #10B981;")
        status_layout.addWidget(self.resume_label, 2, 3)
        
        status_group.setLayout(status_layout)
        layout.addWidget(status_group)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        
        # Details section (collapsible)
        self.details_frame = QFrame()
        self.details_frame.setObjectName("detailsFrame")
        self.details_frame.setStyleSheet("QFrame#detailsFrame { border: none; }")
        details_layout = QVBoxLayout(self.details_frame)
        details_layout.setContentsMargins(0, 0, 0, 0)
        
        # Download Details checkbox
        self.details_checkbox = QCheckBox("✔ Download Details")
        self.details_checkbox.setChecked(True)
        self.details_checkbox.setStyleSheet("""
            QCheckBox {
                color: #7cc8ff;
                font-size: 10pt;
                font-weight: bold;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }
            QCheckBox::indicator:checked {
                image: url(none);
                border: 1px solid #4da6ff;
                background: #0078d4;
            }
            QCheckBox::indicator:unchecked {
                image: url(none);
                border: 1px solid #555;
                background: #1a1a1a;
            }
        """)
        self.details_checkbox.stateChanged.connect(self.toggle_details)
        details_layout.addWidget(self.details_checkbox)
        
        # Options on completion
        options_layout = QVBoxLayout()
        options_layout.setContentsMargins(20, 5, 0, 5)
        options_layout.addWidget(QLabel("Options on completion:"))
        
        self.open_checkbox = QCheckBox("Open file when download completes")
        self.open_checkbox.setChecked(True)
        options_layout.addWidget(self.open_checkbox)
        
        self.shutdown_checkbox = QCheckBox("Shut down computer when all downloads complete")
        options_layout.addWidget(self.shutdown_checkbox)
        
        details_layout.addLayout(options_layout)
        
        # Connections progress
        connections_label = QLabel("Start positions and download progress by connections:")
        connections_label.setStyleSheet("margin-top: 10px;")
        details_layout.addWidget(connections_label)
        
        self.connections_text = QTextEdit()
        self.connections_text.setReadOnly(True)
        self.connections_text.setMaximumHeight(100)
        self.connections_text.setText("Connection 1: 0.0-53.0 MB (0%)\nConnection 2: 53.0-106.0 MB (0%)\nConnection 3: 106.0-159.0 MB (0%)\nConnection 4: 159.0-212.0 MB (0%)")
        details_layout.addWidget(self.connections_text)
        
        layout.addWidget(self.details_frame)
        
        # Button row
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 10, 0, 0)
        
        self.hide_details_btn = QPushButton("<< Hide details")
        self.hide_details_btn.clicked.connect(self.toggle_details_ui)
        button_layout.addWidget(self.hide_details_btn)
        
        button_layout.addStretch()
        
        self.resume_btn = QPushButton("Resume")
        self.resume_btn.setEnabled(False)
        self.resume_btn.clicked.connect(self.resume_download)
        button_layout.addWidget(self.resume_btn)
        
        self.pause_btn = QPushButton("Pause")
        self.pause_btn.clicked.connect(self.pause_download)
        button_layout.addWidget(self.pause_btn)
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background: #dc3545;
                color: white;
                border: 1px solid #ff6b6b;
            }
            QPushButton:hover {
                background: #c82333;
                border: 1px solid #ff8787;
            }
        """)
        self.cancel_btn.clicked.connect(self.cancel_download)
        button_layout.addWidget(self.cancel_btn)
        
        layout.addLayout(button_layout)
        
        # Store initial height for showing/hiding details
        self.details_frame_visible = True
        self.adjustSize()
        self.initial_height = self.height()
        self.minimized_height = 300  # Height when details are hidden
        
    def toggle_details(self, state):
        if state == Qt.CheckState.Checked.value:
            self.details_frame.show()
            self.hide_details_btn.setText("<< Hide details")
            self.details_frame_visible = True
            self.resize(self.width(), self.initial_height)
        else:
            self.details_frame.hide()
            self.hide_details_btn.setText("Show details >>")
            self.details_frame_visible = False
            self.resize(self.width(), self.minimized_height)
    
    def toggle_details_ui(self):
        self.details_checkbox.setChecked(not self.details_checkbox.isChecked())
    
    def start_polling(self):
        """Poll backend for real job progress so status window and main list stay in sync."""
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_from_backend)
        self.timer.start(500)  # every 500ms
        self.update_from_backend()
    
    def _find_job_by_url(self, jobs):
        """Find job matching this window's URL; prefer by job_id if set, else by url."""
        target_url = self.download_info.get("url", "")
        if not target_url:
            return None
        # Prefer same job_id if we already have one
        if self.job_id:
            for j in jobs:
                if j.get("id") == self.job_id:
                    return j
        # Else find most recent job with matching URL (last added)
        for j in reversed(jobs):
            if j.get("url") == target_url:
                return j
        return None
    
    def update_from_backend(self):
        if self.is_cancelled or self.is_completed:
            return
        try:
            r = requests.get(f"http://{API_HOST}:{API_PORT}/jobs", timeout=3)
            if r.status_code != 200:
                return
            jobs = r.json()
        except Exception:
            return
        j = self._find_job_by_url(jobs)
        if not j:
            # Job not yet in list; show 0%
            self.progress_bar.setValue(0)
            self.downloaded_label.setText("0 MB (0%)")
            self.size_label.setText("--")
            self.speed_label.setText("0 KB/s")
            self.time_label.setText("--")
            return
        self._last_job = j
        self.job_id = j.get("id")
        status = j.get("status", "")
        self.downloaded_bytes = j.get("downloaded", 0)
        self.total_bytes = j.get("size", 0)
        if self.total_bytes <= 0 and self.downloaded_bytes > 0 and j.get("eta") and j.get("speed"):
            try:
                eta_sec = float(j.get("eta"))
                speed = float(j.get("speed", 1))
                if speed > 0 and eta_sec > 0:
                    self.total_bytes = self.downloaded_bytes + int(speed * eta_sec)
            except (ValueError, TypeError):
                pass
        if self.total_bytes <= 0:
            self.progress = 0
        else:
            self.progress = min(100.0, (self.downloaded_bytes / self.total_bytes) * 100)
        
        # Status label
        if status in ("paused", "stopped"):
            self.status_label.setText("Paused" if status == "paused" else "Stopped")
            self.status_label.setStyleSheet("color: #ffa726; font-weight: bold;")
        elif status == "completed":
            self.complete_download()
            return
        elif status == "error":
            self.timer.stop()
            self.status_label.setText("Error")
            self.status_label.setStyleSheet("color: #dc3545; font-weight: bold;")
            return
        else:
            self.status_label.setText("Connecting..." if (self.total_bytes == 0 and self.downloaded_bytes == 0) else "Downloading...")
            self.status_label.setStyleSheet("color: #4da6ff; font-weight: bold;")
        
        # Progress bar and labels
        self.progress_bar.setValue(int(self.progress))
        downloaded_mb = self.downloaded_bytes / (1024 * 1024)
        total_mb = self.total_bytes / (1024 * 1024)
        self.downloaded_label.setText(f"{downloaded_mb:.2f} MB ({self.progress:.1f}%)")
        self.size_label.setText("Connecting..." if self.total_bytes == 0 else f"{total_mb:.2f} MB")
        
        # Speed
        bps = j.get("speed", 0.0)
        if bps < 1024:
            self.speed_label.setText(f"{bps:.1f} B/s")
        elif bps < 1024 * 1024:
            self.speed_label.setText(f"{bps/1024:.1f} KB/s")
        else:
            self.speed_label.setText(f"{bps/(1024*1024):.2f} MB/s")
        
        # ETA
        self.time_label.setText(_format_eta(j.get("eta")).replace("—", "--"))
        
        self.update_connections_text()
    
    def update_connections_text(self):
        if self.total_bytes <= 0:
            self.connections_text.setText("Connecting...")
            return
        connections = []
        total_connections = 4
        total = self.total_bytes
        bytes_per_conn = total / total_connections
        
        for i in range(total_connections):
            start = i * bytes_per_conn
            end_byte = (i + 1) * bytes_per_conn
            if self.downloaded_bytes >= end_byte:
                progress = 100
            elif self.downloaded_bytes <= start:
                progress = 0
            else:
                conn_progress = ((self.downloaded_bytes - start) / bytes_per_conn) * 100
                progress = min(conn_progress, 100)
            
            connections.append(f"Connection {i+1}: {start/(1024*1024):.1f}-{end_byte/(1024*1024):.1f} MB ({progress:.0f}%)")
        
        self.connections_text.setText("\n".join(connections))
    
    def complete_download(self):
        self.timer.stop()
        self.is_completed = True
        self.status_label.setText("Completed")
        self.status_label.setStyleSheet("color: #10B981; font-weight: bold;")
        self.pause_btn.setEnabled(False)
        self.resume_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        self.hide_details_btn.setEnabled(False)
        self.details_checkbox.setEnabled(False)
        
        # Update all connections to 100%
        connections = []
        total_connections = 4
        total = max(1, self.total_bytes)
        bytes_per_conn = total / total_connections
        for i in range(total_connections):
            start = i * bytes_per_conn
            end = (i + 1) * bytes_per_conn
            connections.append(f"Connection {i+1}: {start/(1024*1024):.1f}-{end/(1024*1024):.1f} MB (100%)")
        
        self.connections_text.setText("\n".join(connections))
        
        # Update final values
        downloaded_mb = self.downloaded_bytes / (1024 * 1024)
        self.downloaded_label.setText(f"{downloaded_mb:.2f} MB (100.0%)")
        self.time_label.setText("0 sec")
        
        # Show completion message
        QMessageBox.information(self, "Download Complete", 
            f"Download completed successfully!\n\nFile saved to:\n{self.download_info['folder']}")
        
        # Auto-open file or folder when download completes (BitTorrent-style)
        if self.open_checkbox.isChecked():
            try:
                j = getattr(self, "_last_job", None) or {}
                name = (j.get("name") or self.download_info.get("filename") or "").strip()
                out_dir = j.get("out_dir")
                if "(torrent content" in name.lower() and out_dir and os.path.isdir(out_dir):
                    if sys.platform.startswith("win"):
                        os.startfile(out_dir)
                    elif sys.platform == "darwin":
                        subprocess.run(["open", out_dir])
                    else:
                        subprocess.run(["xdg-open", out_dir])
                else:
                    file_path = os.path.join(self.download_info['folder'], self.download_info['filename'])
                    if os.path.exists(file_path):
                        if sys.platform.startswith("win"):
                            os.startfile(file_path)
                        elif sys.platform == "darwin":
                            subprocess.run(["open", file_path])
                        else:
                            subprocess.run(["xdg-open", file_path])
            except Exception as e:
                print(f"Error opening file: {e}")
        
        # Close window after 3 seconds
        QTimer.singleShot(3000, self.close_window)
    
    def close_window(self):
        self.close()
    
    def resume_download(self):
        if self.job_id and self.is_paused:
            try:
                requests.post(f"http://{API_HOST}:{API_PORT}/resume?id={self.job_id}", timeout=5)
            except Exception:
                pass
            self.is_paused = False
            self.status_label.setText("Downloading...")
            self.status_label.setStyleSheet("color: #4da6ff; font-weight: bold;")
            self.resume_btn.setEnabled(False)
            self.pause_btn.setEnabled(True)
            self.timer.start(500)
    
    def pause_download(self):
        if self.job_id and not self.is_paused:
            try:
                requests.post(f"http://{API_HOST}:{API_PORT}/pause?id={self.job_id}", timeout=5)
            except Exception:
                pass
            self.is_paused = True
            self.status_label.setText("Paused")
            self.status_label.setStyleSheet("color: #ffa726; font-weight: bold;")
            self.resume_btn.setEnabled(True)
            self.pause_btn.setEnabled(False)
    
    def cancel_download(self):
        reply = QMessageBox.question(
            self, "Cancel Download",
            "Are you sure you want to cancel this download?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            if self.job_id:
                try:
                    requests.post(f"http://{API_HOST}:{API_PORT}/soft_stop?id={self.job_id}", timeout=5)
                except Exception:
                    pass
            self.is_cancelled = True
            self.timer.stop()
            self.status_label.setText("Cancelled")
            self.status_label.setStyleSheet("color: #dc3545; font-weight: bold;")
            self.resume_btn.setEnabled(False)
            self.pause_btn.setEnabled(False)
            self.cancel_btn.setEnabled(False)
            self.hide_details_btn.setEnabled(False)
            self.details_checkbox.setEnabled(False)

# ---------------- HTTP API ----------------
class Handler(BaseHTTPRequestHandler):
    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send(self, d, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self._cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(d).encode())

    def do_OPTIONS(self):
        """CORS preflight – Safari/Chrome send this before POST."""
        self.send_response(200)
        self._cors_headers()
        self.end_headers()

    def _body(self):
        ln = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(ln).decode()) if ln > 0 else {}

    def do_GET(self):
        if self.path.startswith("/jobs"):
            self._send(self.server.m.list())
        else:
            self._send({"error": "not found"}, 404)

    def do_POST(self):
        p = urlparse(self.path); q = parse_qs(p.query)
        b = self._body(); m = self.server.m

        if p.path == "/enqueue":
            if not b.get("url"):
                return self._send({"ok": False, "error": "no url"}, 400)
            j = m.add(b["url"])
            return self._send({"ok": True, "job": j.to_dict()})
        
        if p.path == "/enqueue_with_info":
            if not b.get("url"):
                return self._send({"ok": False, "error": "no url"}, 400)
            
            # From extension/API: job is enqueued below; do NOT open dialog (already_enqueued=True)
            if hasattr(self.server, 'gui_window'):
                title = b.get("title", "video")
                QApplication.instance().postEvent(
                    self.server.gui_window,
                    DownloadEvent(b["url"], title, already_enqueued=True)
                )
            
            quality = b.get("quality", "1080p")
            referer = b.get("referer")
            title = b.get("title", "")
            cookie = b.get("cookie")
            h_extra = b.get("embed_extra_headers")
            if not isinstance(h_extra, dict):
                h_extra = b.get("headers_123movies")
            if not isinstance(h_extra, dict):
                h_extra = None
            j = m.add(b["url"], q=quality, referer=referer, title=title, cookie=cookie, embed_extra_headers=h_extra)
            return self._send({"ok": True, "job": j.to_dict()})

        if p.path == "/pause": 
            m.pause(q.get("id", [""])[0]); 
            return self._send({"ok": True})

        if p.path == "/resume": 
            m.resume(q.get("id", [""])[0]); 
            return self._send({"ok": True})

        if p.path == "/stop": 
            m.stop(q.get("id", [""])[0]); 
            return self._send({"ok": True})

        if p.path == "/soft_stop": 
            m.soft_stop(q.get("id", [""])[0]); 
            return self._send({"ok": True})

        if p.path == "/stop_all": 
            m.pause_all_active(); 
            return self._send({"ok": True})

        if p.path == "/delete": 
            m.delete(q.get("id", [""])[0]); 
            return self._send({"ok": True})

        return self._send({"error": "unknown endpoint"}, 404)

def launch_api(m, gui_window):
    def run():
        srv = HTTPServer(("", API_PORT), Handler)
        srv.m = m
        srv.gui_window = gui_window
        print(f"[KDM] Backend running on http://127.0.0.1:{API_PORT} (and localhost)")
        srv.serve_forever()
    threading.Thread(target=run, daemon=True).start()

# ---------------- UI ----------------
class CustomTitleBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.drag_pos = None
        self.setFixedHeight(32)
        self.setStyleSheet("background:rgba(0,0,0,0); color:white;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 8, 0)
        layout.setSpacing(6)

        self.k_label = QLabel("K")
        self.k_label.setStyleSheet("color:white; font:bold 13pt 'Segoe UI'; background:transparent;")
        layout.addWidget(self.k_label)

        self.title = QLabel("Kalupura Download Manager (KDM)")
        self.title.setStyleSheet("color:white; font:10pt 'Segoe UI'; background:transparent;")
        layout.addWidget(self.title)

        layout.addItem(QSpacerItem(20, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))

        for sym, func in [
            ("–", self.parent.showMinimized),
            ("□", lambda: self.parent.showNormal() if self.parent.isMaximized() else self.parent.showMaximized()),
            ("✕", self.parent.close)
        ]:
            btn = QToolButton(text=sym)
            btn.setFixedSize(40, 28)
            btn.setStyleSheet("""
                QToolButton { background: transparent; color: white; border: none; font: 12pt 'Segoe UI'; }
                QToolButton:hover { background: rgba(255,255,255,0.08); }
                QToolButton:pressed { background: rgba(255,255,255,0.15); }
            """)
            btn.clicked.connect(func)
            layout.addWidget(btn)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_pos = event.globalPosition().toPoint() - self.parent.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self.drag_pos:
            self.parent.move(event.globalPosition().toPoint() - self.drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self.drag_pos = None

class KDM(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setMinimumSize(1150, 620)
        self.setStyleSheet("background:#111; color:white;")

        self.m = Manager()
        self.license_gate = LicenseGate()

        self.translations = self._load_translations()
        cfg = self._load_config()
        self.language = cfg.get("language", "English")
        self.show_delete_confirm = cfg.get("show_delete_confirm", True)
        self.language_dropdown = None
        self.just_stopped_ids = set()

        self._build_ui()
        self._retext()

        # Launch API after GUI is created
        launch_api(self.m, self)

        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh)
        self.timer.start(5000)

        self.last_selected_ids = []
        self.last_selected_name = None
        self.last_selected_id = None

    # ---- Internal File Handling Helpers ----
    def _find_actual_file_path(self, job_data):
        """Find the actual file path with multiple search strategies"""
        if not job_data or not job_data.get("name"):
            return None

        filename = job_data["name"]
        # Torrent/magnet: open folder, not a single file
        if "(torrent content" in (filename or "").lower() or "magnet link" in (filename or "").lower():
            return None
        out_dir = job_data.get("out_dir")
        downloads_dir = os.path.abspath(out_dir or os.path.join(os.path.expanduser("~"), "Downloads"))

        exact_path = os.path.join(downloads_dir, filename)
        if os.path.isfile(exact_path):
            return exact_path

        if os.path.exists(downloads_dir):
            try:
                for file_in_dir in os.listdir(downloads_dir):
                    fp = os.path.join(downloads_dir, file_in_dir)
                    if os.path.isfile(fp):
                        base1, _ = os.path.splitext(filename)
                        base2, _ = os.path.splitext(file_in_dir)
                        if (base1.lower() == base2.lower() or
                            base1.lower() in base2.lower() or
                            base2.lower() in base1.lower()):
                            return fp
            except Exception:
                pass

        base_name, _ = os.path.splitext(filename)
        video_exts = ['.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v']

        for ext in video_exts:
            test_path = os.path.join(downloads_dir, base_name + ext)
            if os.path.isfile(test_path):
                return test_path

        return None

    def _open_file_or_folder(self, job_data):
        """Open completed download: file or folder (for torrents). Torrent/magnet → open folder in KDM."""
        if not job_data:
            return
        name = (job_data.get("name") or "").strip().lower()
        out_dir = job_data.get("out_dir")
        is_torrent = "(torrent content" in name or "magnet link" in name
        if is_torrent and out_dir and os.path.isdir(out_dir):
            try:
                if sys.platform.startswith("win"):
                    os.startfile(out_dir)
                elif sys.platform == "darwin":
                    subprocess.run(["open", out_dir])
                else:
                    subprocess.run(["xdg-open", out_dir])
            except Exception as e:
                QMessageBox.warning(self, "Open", f"Could not open folder: {e}")
            return
        self._open_file(job_data)

    def _show_file_association_dialog(self, file_path):
        """Show Windows 'How do you want to open this file?' dialog"""
        try:
            if sys.platform.startswith("win"):
                abs_path = os.path.abspath(file_path)
                if not os.path.exists(abs_path):
                    return False

                try:
                    abs_path_win = abs_path.replace('/', '\\')
                    cmd = f'rundll32.exe shell32.dll,OpenAs_RunDLL "{abs_path_win}"'
                    subprocess.Popen(cmd, shell=True)
                    return True
                except Exception:
                    pass

                try:
                    r = ctypes.windll.shell32.ShellExecuteW(
                        None, "openas", abs_path, None, None, 1
                    )
                    return r > 32
                except Exception:
                    pass

            return False
        except Exception:
            return False

    def _open_file(self, job_data):
        file_path = self._find_actual_file_path(job_data)
        if not file_path:
            QMessageBox.warning(self, "Open File",
                                f"File not found in Downloads.\nExpected: {job_data.get('name')}")
            return

        try:
            if sys.platform.startswith("win"):
                try:
                    os.startfile(file_path)
                    return
                except Exception:
                    pass

                if self._show_file_association_dialog(file_path):
                    pass
                else:
                    downloads_dir = os.path.dirname(file_path)
                    QMessageBox.information(
                        self, "Open File",
                        f"Could not open file automatically.\n\n"
                        f"File location opened. Double-click manually."
                    )
                    os.startfile(downloads_dir)

            elif sys.platform == "darwin":
                subprocess.run(["open", file_path])
            else:
                subprocess.run(["xdg-open", file_path])

        except Exception as e:
            QMessageBox.warning(self, "Open File",
                                f"Could not open file:\n{str(e)}")

    def _open_containing_folder(self, job_data):
        file_path = self._find_actual_file_path(job_data)
        out_dir = (job_data or {}).get("out_dir")
        downloads_dir = os.path.abspath(out_dir or os.path.join(os.path.expanduser("~"), "Downloads"))

        try:
            if file_path and os.path.isfile(file_path):
                if sys.platform.startswith("win"):
                    pidl = ILCreateFromPath(file_path)
                    if pidl:
                        try:
                            SHOpenFolderAndSelectItems(pidl, 0, None, 0)
                        finally:
                            ILFree(pidl)
                    else:
                        os.startfile(downloads_dir)
                elif sys.platform == "darwin":
                    subprocess.run(["open", "-R", file_path])
                else:
                    subprocess.run(["xdg-open", downloads_dir])
            else:
                if sys.platform.startswith("win"):
                    os.startfile(downloads_dir)
                elif sys.platform == "darwin":
                    subprocess.run(["open", downloads_dir])
                else:
                    subprocess.run(["xdg-open", downloads_dir])

        except Exception as e:
            QMessageBox.warning(self, "Open Folder", f"Could not open folder: {e}")
    
    # ---- config / translations ----
    def _load_translations(self):
        try:
            with open(TRANSLATION_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}

    def _load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                return json.load(open(CONFIG_FILE, "r", encoding="utf-8"))
            except:
                pass
        return {"language": "English", "show_delete_confirm": True}

    def _save_config(self):
        cfg = {}
        if os.path.isfile(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
            except Exception:
                cfg = {}
        cfg["language"] = self.language
        cfg["show_delete_confirm"] = self.show_delete_confirm
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)

    def tr(self, key):
        return self.translations.get(self.language, {}).get(
            key, self.translations.get("English", {}).get(key, key)
        )

    # ---- Event Handling ----
    def event(self, event):
        if isinstance(event, DownloadEvent):
            self.show_download_windows(event.url, event.title, getattr(event, "already_enqueued", True))
            return True
        return super().event(event)

    def show_download_windows(self, url, title, already_enqueued=False):
        """Show the download info window (URL, category, Save As, Start Download)."""
        info_window = DownloadInfoWindow(url, title, self, already_enqueued=already_enqueued)
        if info_window.exec() == QDialog.DialogCode.Accepted:
            download_info = info_window.start_download()
            if download_info:
                status_window = DownloadStatusWindow(download_info, self)
                status_window.exec()

    # ---- UI build ----
    def _build_ui(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addWidget(CustomTitleBar(self))
        v.addWidget(self._toolbar())
        v.addWidget(self._table(), 1)
        v.addWidget(self._statusbar())
        self.setCentralWidget(w)

    def _toolbar(self):
        bar = QWidget()
        h = QHBoxLayout(bar)
        h.setContentsMargins(12, 8, 12, 8)
        h.setSpacing(20)
        bar.setStyleSheet("background:#0c0c0c; border-bottom:1px solid #222;")

        def mk(icon_char, key, fn):
            b = QToolButton()
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            b.setFixedSize(95, 70)
            b.setIconSize(QSize(34, 34))

            pm = QPixmap(34, 34)
            pm.fill(Qt.GlobalColor.transparent)
            p = QPainter(pm)
            p.setPen(QColor("#7cc8ff"))
            p.setFont(QFont("Segoe UI Symbol", 22))
            p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, icon_char)
            p.end()

            b.setIcon(QIcon(pm))
            b.clicked.connect(fn)
            b.setStyleSheet("""
                QToolButton {
                    background:#111; color:white; border:1px solid #1a1a1a; border-radius:6px;
                }
                QToolButton:hover {
                    background:qradialgradient(cx:0.5,cy:0.5,radius:1,
                        stop:0 rgba(120,200,255,40%), stop:1 rgba(0,0,0,0));
                    border:1px solid #4da6ff;
                }
                QToolButton:pressed { background:#0a3d5a; border:1px solid #4da6ff; }
            """)
            h.addWidget(b)
            return key, b

        self.btns = {}
        for icon, key, fn in [
            ("➕", "Add URL", self.add_url),
            ("📂", "Open", self._open_selected),
            ("▶", "Resume", self.resume),
            ("⏹", "Stop", self.stop),
            ("✋", "Stop All", self.stop_all),
            ("❌", "Delete", self.delete_job),
            ("🌐", "Language", self.toggle_lang),
            ("📁", "Open Folder", self._open_downloads_folder),
            ("📝", "Registration", self._registration_license),
            ("🛒", "Buy Now", self._buy_now),
            ("🔗", "Share", self.share),
            ("ℹ", "About", lambda: QMessageBox.information(self, self.tr("About"), "Kalupura Download Manager\nBackend Port 9669")),
        ]:
            k, b = mk(icon, key, fn)
            self.btns[k] = b

        if "Buy Now" in self.btns:
            bn = self.btns["Buy Now"]
            bn.setStyleSheet("""
                QToolButton {
                    background:#142914; color:#b8f0c8; border:1px solid #2d7a3e; border-radius:6px;
                }
                QToolButton:hover {
                    background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #1f4a28,stop:1 #142914);
                    border:1px solid #4ddb82;
                }
                QToolButton:pressed { background:#0d1f12; border:1px solid #2d7a3e; }
            """)
            bn.setToolTip(self.tr("buy_now_tooltip"))

        h.addItem(QSpacerItem(20, 20, QSizePolicy.Policy.Expanding))
        return bar

    def _open_downloads_folder(self):
        try:
            downloads_path = os.path.join(os.path.expanduser("~"), "Downloads")
            if sys.platform.startswith("win"):
                os.startfile(downloads_path)
            elif sys.platform == "darwin":
                subprocess.run(["open", downloads_path])
            else:
                subprocess.run(["xdg-open", downloads_path])
        except Exception as e:
            QMessageBox.warning(self, "Open Folder", f"Could not open Downloads: {e}")

    def _table(self):
        t = QTableWidget()
        t.setColumnCount(8)
        t.setHorizontalHeaderLabels([
            "File Name", "Q", "Size", "Status", "Time left",
            "Transfer rate", "Last Try", "Description"
        ])

        t.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        t.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)

        t.verticalHeader().setVisible(False)
        t.setShowGrid(True)
        t.setStyleSheet("""
            QTableWidget{
                background:#141414; color:white; border:none;
                gridline-color:#2a2a2a;
                selection-background-color:#003366;
                selection-color:white;
                outline:none;
            }
            QHeaderView::section{
                background:#000; color:white;
                border:1px solid #2d2d2d; padding:6px;
            }
            QTableWidget::item:selected { background:#003366; color:white; }
            QTableWidget::item:focus { outline:none; border:none; }
        """)

        t.setFrameShape(QFrame.Shape.NoFrame)
        t.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        t.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        h = t.horizontalHeader()
        h.setStretchLastSection(True)
        h.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        self.table = t
        self._fill_rows()

        t.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        t.customContextMenuRequested.connect(self._show_context_menu)
        t.cellDoubleClicked.connect(self._on_row_double_clicked)

        t.viewport().installEventFilter(self)

        return t

    def _on_row_double_clicked(self, row, col):
        """Double-click completed job → open file or folder (BitTorrent-style)."""
        it0 = self.table.item(row, 0)
        if not it0 or not it0.data(Qt.ItemDataRole.UserRole):
            return
        jid = it0.data(Qt.ItemDataRole.UserRole)
        try:
            jobs = requests.get(f"http://{API_HOST}:{API_PORT}/jobs", timeout=2).json()
        except Exception:
            return
        for j in jobs:
            if j.get("id") == jid and j.get("status") == "completed":
                self._open_file_or_folder(j)
                break

    def _open_selected(self):
        """Open selected completed download (file or folder)."""
        ids = self._selected_job_ids()
        if not ids:
            QMessageBox.information(self, "Open", "Select a completed download first.")
            return
        try:
            jobs = requests.get(f"http://{API_HOST}:{API_PORT}/jobs", timeout=2).json()
        except Exception:
            return
        for j in jobs:
            if j.get("id") == ids[0] and j.get("status") == "completed":
                self._open_file_or_folder(j)
                return
        QMessageBox.information(self, "Open", "Select a completed download to open.")
    
    def _fill_rows(self):
        t = self.table
        rh = t.verticalHeader().defaultSectionSize() or 22
        vis = max(15, int(t.viewport().height() / rh))
        while t.rowCount() < vis:
            r = t.rowCount()
            t.insertRow(r)
            for c in range(t.columnCount()):
                item = QTableWidgetItem("")
                item.setFlags(Qt.ItemFlag.NoItemFlags)
                t.setItem(r, c, item)

    def eventFilter(self, obj, e):
        if obj is self.table.viewport():
            if e.type() == e.Type.MouseButtonPress:
                index = self.table.indexAt(e.pos())
                if index.isValid():
                    item = self.table.item(index.row(), 0)
                    if item and item.data(Qt.ItemDataRole.UserRole):
                        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                        for col in range(1, self.table.columnCount()):
                            it = self.table.item(index.row(), col)
                            if it:
                                it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                    else:
                        e.ignore()
                        return True
            elif e.type() == e.Type.Resize:
                self._fill_rows()
        return super().eventFilter(obj, e)

    def _statusbar(self):
        s = QStatusBar()
        s.setStyleSheet("background:#1a1a1a; color:#aaa;")
        s.showMessage("Ready")
        self.status = s
        self._refresh_license_status_message()
        return s

    def _refresh_license_status_message(self):
        self.license_gate.reload()
        g = self.license_gate
        if g.has_valid_saved_license():
            extra = self.tr("license_licensed")
        else:
            left = g.trial_days_remaining()
            if left is None:
                extra = ""
            elif left <= 0:
                extra = self.tr("license_trial_expired")
            else:
                extra = self.tr("license_trial_days").format(n=left)
        base = self.tr("Ready")
        self.status.showMessage(f"{base} · {extra}" if extra else base)
        self._update_buy_now_visibility()

    def _purchase_or_distribution_url(self) -> str:
        try:
            if os.path.isfile(CONFIG_FILE):
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    d = json.load(f)
                    return (
                        (d.get("purchase_url") or d.get("distribution_page") or "")
                        .strip()
                    )
        except Exception:
            pass
        return ""

    def _buy_now(self):
        url = self._purchase_or_distribution_url()
        if url:
            QDesktopServices.openUrl(QUrl(url))
        else:
            QMessageBox.information(
                self,
                self.tr("Buy Now"),
                self.tr("buy_now_no_url"),
            )

    def _update_buy_now_visibility(self):
        if "Buy Now" not in self.btns:
            return
        licensed = self.license_gate.has_valid_saved_license()
        self.btns["Buy Now"].setVisible(not licensed)

    def _registration_license(self):
        g = self.license_gate
        buy = self._purchase_or_distribution_url()
        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr("Registration"))
        dlg.setMinimumWidth(440)
        dlg.setStyleSheet("""
            QDialog { background:#111; color:white; font-family:'Segoe UI'; }
            QLabel { color:#ddd; }
            QLineEdit { background:#1a1a1a; color:#eee; border:1px solid #444; padding:8px; border-radius:4px; }
            QPushButton {
                background:#1a1a1a; color:white; border:1px solid #444;
                padding:6px 14px; border-radius:4px;
            }
            QPushButton:hover { background:#003366; border:1px solid #4da6ff; }
        """)
        v = QVBoxLayout(dlg)
        if g.has_valid_saved_license():
            v.addWidget(QLabel(self.tr("license_licensed")))
        else:
            left = g.trial_days_remaining()
            if left is None:
                v.addWidget(QLabel(""))
            elif left <= 0:
                v.addWidget(QLabel(self.tr("license_trial_expired")))
            else:
                v.addWidget(QLabel(self.tr("license_trial_days").format(n=left)))
        v.addWidget(QLabel(self.tr("license_enter_key")))
        le = QLineEdit()
        le.setPlaceholderText(self.tr("license_key_placeholder"))
        v.addWidget(le)
        row = QHBoxLayout()
        b_buy = QPushButton(self.tr("Buy Now"))
        b_buy.setToolTip(self.tr("buy_now_tooltip"))
        b_buy.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #3cb371, stop:1 #2e8b57);
                color: white; font-weight: bold; border: 1px solid #5acd8c; border-radius: 4px;
            }
            QPushButton:hover { background: #4ddb82; color: #111; }
            QPushButton:disabled { background: #333; color: #777; border: 1px solid #444; }
        """)
        b_act = QPushButton(self.tr("license_activate"))
        row.addWidget(b_buy)
        row.addWidget(b_act)
        row.addStretch()
        v.addLayout(row)

        def do_buy():
            if buy:
                QDesktopServices.openUrl(QUrl(buy))

        def do_act():
            k = le.text().strip()
            if not k:
                QMessageBox.warning(dlg, self.tr("Registration"), self.tr("license_need_key"))
                return
            ok, err = g.apply_license_key(k)
            if ok:
                QMessageBox.information(dlg, self.tr("Registration"), self.tr("license_activated"))
                self._refresh_license_status_message()
                dlg.accept()
            else:
                QMessageBox.warning(dlg, self.tr("Registration"), err)

        b_buy.clicked.connect(do_buy)
        b_act.clicked.connect(do_act)
        b_buy.setEnabled(bool(buy))
        if not buy:
            b_buy.setToolTip(self.tr("buy_now_no_url"))
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(dlg.reject)
        if bb.button(QDialogButtonBox.StandardButton.Close):
            bb.button(QDialogButtonBox.StandardButton.Close).setText(self.tr("Close"))
        v.addWidget(bb)
        dlg.exec()

    # ---- Context Menu ----
    def _show_context_menu(self, position):
        selected_ids = self._selected_job_ids()
        if not selected_ids:
            return

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background:#1a1a1a; color:white; border:1px solid #333; }
            QMenu::item { padding: 5px 20px; }
            QMenu::item:selected { background:#003366; }
            QMenu::separator { height:1px; background:#333; }
        """)

        try:
            jobs = requests.get(f"http://{API_HOST}:{API_PORT}/jobs", timeout=2).json()
        except:
            jobs = []

        job_data = None
        jid = selected_ids[0]
        for j in jobs:
            if j["id"] == jid:
                job_data = j
                break

        self._current_context_job = job_data

        open_action = QAction("Open", self)
        open_action.triggered.connect(lambda: self._open_file_or_folder(self._current_context_job))
        menu.addAction(open_action)

        menu.addSeparator()

        open_folder_action = QAction("Open Folder", self)
        open_folder_action.triggered.connect(lambda: self._open_containing_folder(self._current_context_job))
        menu.addAction(open_folder_action)

        menu.addSeparator()

        resume_action = QAction("Resume Download", self)
        resume_action.triggered.connect(self.resume)
        menu.addAction(resume_action)

        stop_action = QAction("Stop Download", self)
        stop_action.triggered.connect(self.stop)
        menu.addAction(stop_action)

        menu.addSeparator()

        remove_action = QAction("Remove", self)
        remove_action.triggered.connect(self.delete_job)
        menu.addAction(remove_action)

        if job_data:
            file_exists = self._find_actual_file_path(job_data) is not None
            is_torrent_folder = "(torrent content" in (job_data.get("name") or "") and job_data.get("out_dir")
            open_action.setEnabled(
                job_data.get("status") == "completed" and (file_exists or is_torrent_folder)
            )
            open_folder_action.setEnabled(True)

            status = job_data.get("status", "")
            resume_action.setEnabled(status in ("paused", "stopped", "error"))
            stop_action.setEnabled(status in ("downloading", "starting", "paused"))
        else:
            open_action.setEnabled(False)
            open_folder_action.setEnabled(False)
            resume_action.setEnabled(False)
            stop_action.setEnabled(False)

        menu.exec(self.table.viewport().mapToGlobal(position))
        self._current_context_job = None

    # ---- actions ----
    def add_url(self):
        u, ok = QInputDialog.getText(self, self.tr("Add URL"), self.tr("Enter URL:"))
        if ok and u.strip():
            # Get video title from page if possible
            import re
            title = "video"
            if "youtube.com" in u or "youtu.be" in u:
                # Try to extract title from YouTube URL
                try:
                    if "v=" in u:
                        video_id = u.split("v=")[1].split("&")[0]
                        title = f"youtube_video_{video_id}"
                except:
                    pass
            
            # Show download windows
            self.show_download_windows(u, title)
    
    def _selected_job_ids(self):
        ids = []
        for index in self.table.selectionModel().selectedRows():
            it0 = self.table.item(index.row(), 0)
            if it0 and it0.data(Qt.ItemDataRole.UserRole):
                ids.append(it0.data(Qt.ItemDataRole.UserRole))
        return ids
    
    def pause(self):
        for jid in self._selected_job_ids():
            try:
                requests.post(f"http://{API_HOST}:{API_PORT}/pause?id={jid}", timeout=5)
            except:
                pass
        self.refresh()

    def resume(self):
        selected = self._selected_job_ids()
        for jid in selected:
            try:
                if jid in self.just_stopped_ids:
                    self.just_stopped_ids.remove(jid)
                requests.post(f"http://{API_HOST}:{API_PORT}/resume?id={jid}", timeout=5)
            except:
                pass
        self.refresh()

    def stop(self):
        selected = self._selected_job_ids()
        for jid in selected:
            try:
                requests.post(f"http://{API_HOST}:{API_PORT}/soft_stop?id={jid}", timeout=5)
            except:
                pass
        self.just_stopped_ids.update(selected)
        for row in range(self.table.rowCount()):
            it0 = self.table.item(row, 0)
            if it0:
                jid = it0.data(Qt.ItemDataRole.UserRole)
                if jid in selected:
                    status_item = self.table.item(row, 3)
                    if status_item:
                        status_item.setText("stopped")
        self.refresh()

    def stop_all(self):
        try:
            requests.post(f"http://{API_HOST}:{API_PORT}/stop_all", timeout=5)
        except:
            pass
        self.refresh()

    def _distribution_page_url(self) -> str:
        return self._purchase_or_distribution_url()

    def _share_blurb(self, store_url: str) -> str:
        link = store_url or "https://your-website.com/kdm"
        return (
            "Kalupura Download Manager (KDM) — video, streams & torrents.\n"
            f"Download for Windows, macOS & Linux: {link}"
        )

    def share(self):
        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr("Share"))
        dlg.setMinimumWidth(520)
        dlg.setStyleSheet("""
            QDialog { background:#111; color:white; font-family:'Segoe UI'; }
            QLabel { color:#ddd; font-size:10pt; }
            QTextEdit { background:#1a1a1a; color:#eee; border:1px solid #333; border-radius:4px; }
            QPushButton {
                background:#1a1a1a; color:white; border:1px solid #444;
                padding:6px 14px; border-radius:4px;
            }
            QPushButton:hover { background:#003366; border:1px solid #4da6ff; }
        """)
        layout = QVBoxLayout(dlg)
        layout.setSpacing(10)

        job = None
        ids = self._selected_job_ids()
        if ids:
            try:
                jobs = requests.get(f"http://{API_HOST}:{API_PORT}/jobs", timeout=5).json()
                for j in jobs:
                    if j["id"] == ids[0]:
                        job = j
                        break
            except Exception:
                pass

        if job:
            layout.addWidget(QLabel(self.tr("Selected download")))
            url_te = QTextEdit()
            url_te.setReadOnly(True)
            url_te.setPlainText(job.get("url") or "")
            url_te.setMaximumHeight(68)
            layout.addWidget(url_te)
            row = QHBoxLayout()
            cu = QPushButton(self.tr("Copy URL"))
            cu.clicked.connect(lambda: QGuiApplication.clipboard().setText(job.get("url") or ""))
            row.addWidget(cu)
            row.addStretch()
            layout.addLayout(row)
            layout.addWidget(
                QLabel(f"{self.tr('File Name')}: {job.get('name') or '—'}")
            )
            layout.addWidget(QFrame())
        else:
            layout.addWidget(
                QLabel(self.tr("No row selected — share app links below, or select a download to copy its URL."))
            )

        layout.addWidget(QLabel(self.tr("Kalupura DM — tell others")))
        store = self._distribution_page_url()
        if store:
            store_te = QTextEdit()
            store_te.setReadOnly(True)
            store_te.setPlainText(store)
            store_te.setMaximumHeight(52)
            layout.addWidget(store_te)
            row2 = QHBoxLayout()
            cs = QPushButton(self.tr("Copy store link"))

            def _copy_store():
                QGuiApplication.clipboard().setText(store)

            cs.clicked.connect(_copy_store)
            ob = QPushButton(self.tr("Open in browser"))
            ob.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(store)))
            row2.addWidget(cs)
            row2.addWidget(ob)
            row2.addStretch()
            layout.addLayout(row2)
        else:
            cfg_abs = os.path.abspath(CONFIG_FILE)
            layout.addWidget(
                QLabel(
                    self.tr("Tip: add your sales page to kdm_config.json")
                    + f'\n"distribution_page": "https://…"\n'
                    + cfg_abs
                )
            )

        layout.addWidget(QLabel(self.tr("Ready-to-send message")))
        blurb = self._share_blurb(store)
        msg_te = QTextEdit()
        msg_te.setReadOnly(True)
        msg_te.setPlainText(blurb)
        msg_te.setMaximumHeight(88)
        layout.addWidget(msg_te)
        row_msg = QHBoxLayout()
        cm = QPushButton(self.tr("Copy message"))
        cm.clicked.connect(lambda: QGuiApplication.clipboard().setText(blurb))
        row_msg.addWidget(cm)
        share_menu_btn = QToolButton()
        share_menu_btn.setText(self.tr("Share via…"))
        share_menu_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        share_menu_btn.setStyleSheet("""
            QToolButton {
                background:#1a1a1a; color:white; border:1px solid #444;
                padding:6px 14px; border-radius:4px;
            }
            QToolButton:hover { background:#003366; border:1px solid #4da6ff; }
            QToolButton::menu-indicator { image: none; width: 0px; }
        """)
        sm = QMenu(share_menu_btn)
        sm.setStyleSheet("""
            QMenu { background:#1a1a1a; color:white; border:1px solid #333; }
            QMenu::item { padding: 6px 24px; }
            QMenu::item:selected { background:#003366; }
        """)
        enc_text = quote(blurb, safe="")
        enc_url = quote(store or "https://example.com", safe="")
        subj = quote(self.tr("Share email subject"))
        sm.addAction(
            self.tr("Share email…"),
            lambda: QDesktopServices.openUrl(QUrl(f"mailto:?subject={subj}&body={enc_text}")),
        )
        sm.addAction("WhatsApp", lambda: QDesktopServices.openUrl(
            QUrl(f"https://wa.me/?text={enc_text}")
        ))
        sm.addAction("Telegram", lambda: QDesktopServices.openUrl(
            QUrl(f"https://t.me/share/url?url={enc_url}&text={quote(blurb.split(chr(10))[0], safe='')}")
        ))
        sm.addAction("X (Twitter)", lambda: QDesktopServices.openUrl(
            QUrl(f"https://twitter.com/intent/tweet?text={enc_text}")
        ))
        sm.addAction("Facebook", lambda: QDesktopServices.openUrl(
            QUrl(f"https://www.facebook.com/sharer/sharer.php?u={enc_url}&quote={enc_text}")
        ))
        sm.addAction(self.tr("Copy message"), lambda: QGuiApplication.clipboard().setText(blurb))
        share_menu_btn.setMenu(sm)
        row_msg.addWidget(share_menu_btn)
        row_msg.addStretch()
        layout.addLayout(row_msg)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(dlg.reject)
        bb.accepted.connect(dlg.accept)
        if bb.button(QDialogButtonBox.StandardButton.Close):
            bb.button(QDialogButtonBox.StandardButton.Close).setText(self.tr("Close"))
        layout.addWidget(bb)
        dlg.exec()

    # ---- delete flow ----
    def delete_job(self):
        ids = self._selected_job_ids()
        if not ids:
            return

        try:
            jobs = requests.get(f"http://{API_HOST}:{API_PORT}/jobs", timeout=5).json()
        except:
            return

        by_id = {j["id"]: j for j in jobs}
        not_allowed = [
            j for j in ids
            if by_id.get(j, {}).get("status") not in ("paused", "stopped", "completed", "error")
        ]

        if not_allowed:
            QMessageBox.warning(self, "Delete",
                "You can only delete paused, stopped, completed, or error downloads.")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("Confirm deletion of downloads")
        dlg.setStyleSheet("""
            QDialog { background-color: #111; color:white; font-family:'Segoe UI'; }
            QLabel { color:white; font-size:10pt; }
            QCheckBox { color:#ccc; font-size:9pt; }
            QPushButton {
                background-color:#1a1a1a; color:white; border:1px solid #444;
                padding:4px 14px; min-width:75px;
            }
            QPushButton:hover { background:#003366; border:1px solid #4da6ff; }
            QPushButton:pressed { background:#004080; border:1px solid #66b2ff; }
        """)
        layout = QVBoxLayout(dlg)
        msg = QLabel("Are you sure you want to delete selected downloads?")
        msg.setWordWrap(True)
        layout.addWidget(msg)

        cb_disk = QCheckBox("Delete files from disk as well.")
        cb_hide = QCheckBox("Don't show this dialog again")
        layout.addWidget(cb_disk)
        layout.addWidget(cb_hide)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Yes |
            QDialogButtonBox.StandardButton.No
        )
        layout.addWidget(buttons)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        delete_files = cb_disk.isChecked()
        self.show_delete_confirm = not cb_hide.isChecked()
        self._save_config()

        deleted_count = 0
        file_delete_errors = []

        for jid in ids:
            try:
                requests.post(f"http://{API_HOST}:{API_PORT}/stop?id={jid}", timeout=5)
            except:
                pass
            time.sleep(0.5)

            job = by_id.get(jid, {})

            if delete_files and job.get("name"):
                filename = job["name"]
                downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
                exact = os.path.join(downloads_dir, filename)

                if os.path.isfile(exact):
                    try:
                        os.remove(exact)
                        deleted_count += 1
                    except Exception as e:
                        file_delete_errors.append(str(e))

            try:
                requests.post(f"http://{API_HOST}:{API_PORT}/delete?id={jid}", timeout=5)
            except:
                pass

        msg = f"Deleted {len(ids)} job(s)."
        if delete_files:
            msg += f"\nDeleted {deleted_count} file(s)."
        if file_delete_errors:
            msg += "\nErrors:\n" + "\n".join(file_delete_errors[:3])

        QMessageBox.information(self, "Deleted", msg)
        self.refresh()

    # ---- Language + refresh ----
    def toggle_lang(self):
        if self.language_dropdown and self.language_dropdown.isVisible():
            self.language_dropdown.hide()
            return

        langs = list(self.translations.keys()) or ["English"]
        cb = QComboBox(self)
        cb.addItems(langs)
        cb.setStyleSheet("""
            QComboBox { background:#000; color:white; border:1px solid #333; padding:4px; }
            QComboBox QAbstractItemView { background:#000; color:white; selection-background-color:#222; }
        """)
        cb.setMaximumWidth(220)
        cb.setEditable(False)
        cb.setCurrentText(self.language)
        cb.activated.connect(lambda _: self._set_lang(cb.currentText()))
        self.language_dropdown = cb

        pos = self.btns["Language"].mapToGlobal(QPoint(0, self.btns["Language"].height()))
        cb.move(pos)
        cb.showPopup()
        cb.show()

    def _set_lang(self, lang):
        self.language = lang
        self._save_config()
        self._retext()
        QMessageBox.information(self, "Language", f"Language set to {lang}")
        if self.language_dropdown:
            self.language_dropdown.hide()

    def _retext(self):
        for k, b in self.btns.items():
            b.setText(self.tr(k))
        if "Share" in self.btns:
            self.btns["Share"].setToolTip(self.tr("Share tooltip"))
        if "Buy Now" in self.btns:
            self.btns["Buy Now"].setToolTip(self.tr("buy_now_tooltip"))
        self.findChild(CustomTitleBar).title.setText(
            f"Kalupura Download Manager (KDM) – {self.language}"
        )
        self._refresh_license_status_message()

        headers = [
            "File Name", "Q", "Size", "Status", "Time left",
            "Transfer rate", "Last Try", "Description"
        ]
        for i, h in enumerate(headers):
            self.table.horizontalHeaderItem(i).setText(self.tr(h))

    def refresh(self):
        try:
            r = requests.get(f"http://{API_HOST}:{API_PORT}/jobs", timeout=5)
            if r.status_code == 200:
                self._update(r.json())
        except:
            pass
        self._refresh_license_status_message()
        if not self.license_gate.is_allowed():
            app = QApplication.instance()
            if app and not show_license_blocking_dialog(
                app, self.license_gate, self._purchase_or_distribution_url()
            ):
                import sys
                sys.exit(0)

    def _update(self, jobs):
        t = self.table
        t.blockSignals(True)
        t.setUpdatesEnabled(False)

        current_selection = self._selected_job_ids()

        t.setRowCount(len(jobs))
        for r, j in enumerate(jobs):
            sz_j = j.get("size", 0)
            pct = min(100, int((j.get("downloaded", 0) / max(1, sz_j)) * 100)) if sz_j > 0 else 0
            bps = j.get("speed", 0.0)
            kbps = bps / 1024.0

            if kbps < 1024:
                speed_str = f"{kbps:.0f} KB/s"
            elif kbps < 1048576:
                speed_str = f"{kbps/1024.0:.1f} MB/s"
            else:
                speed_str = f"{kbps/1048576.0:.2f} GB/s"

            status_text = j.get("status", "")
            if j.get("id") in self.just_stopped_ids and status_text in ("paused","downloading","starting"):
                status_text = "stopped"

            sz = j.get("size", 0)
            size_str = f"{sz/1048576:.1f} MB" if sz else "—"
            vals = [
                j.get("name", ""),
                j.get("quality", "1080p"),
                size_str,
                status_text,
                _format_eta(j.get("eta")),
                speed_str,
                j.get("created", ""),
                (j.get("url", "") or "")[:80] + ("…" if len(j.get("url", "")) > 80 else "")
            ]

            for i, v in enumerate(vals):
                it = QTableWidgetItem(v)
                it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                if i == 0:
                    it.setData(Qt.ItemDataRole.UserRole, j.get("id"))
                t.setItem(r, i, it)

            pb = QProgressBar()
            pb.setValue(pct)
            pb.setStyleSheet("""
                QProgressBar {
                    border:1px solid #333; background:#111; color:white;
                    text-align:center; border-radius:3px;
                }
                QProgressBar::chunk {
                    background-color:#00aaff; border-radius:2px;
                }
            """)
            t.setCellWidget(r, 6, pb)

        self._fill_rows()

        if current_selection:
            for row in range(t.rowCount()):
                it0 = t.item(row, 0)
                if it0 and it0.data(Qt.ItemDataRole.UserRole) in current_selection:
                    t.selectRow(row)

        t.blockSignals(False)
        t.setUpdatesEnabled(True)

# ---- entry ----
if __name__ == "__main__":
    if "--test-hls" in sys.argv:
        _selftest_hls_parser()
        print("[KDM] --test-hls OK")
        sys.exit(0)
    app = QApplication(sys.argv)
    if not run_startup_license_check(app):
        sys.exit(0)
    win = KDM()
    win.show()
    sys.exit(app.exec())
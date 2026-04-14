"""
HLS (.m3u8) download via ffmpeg (copy codecs, AAC bitstream filter, faststart).
Formerly hls_ffmpeg.py — use this module name in new layout.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Any, Optional

_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def download_hls(
    stream_url: str,
    output_path: str,
    *,
    referer: Optional[str] = None,
    user_agent: Optional[str] = None,
    stop_flag: Optional[Any] = None,
) -> bool:
    """
    Download and remux HLS to MP4 using ffmpeg.

    ``stop_flag`` optional threading.Event with ``is_set()`` for cooperative cancel.
    Returns True if output file exists and is non-empty.
    """
    if not shutil.which("ffmpeg"):
        print("[KDM] download_hls: ffmpeg not found in PATH")
        return False
    stream_url = (stream_url or "").strip()
    if not stream_url:
        return False

    out_dir = os.path.dirname(os.path.abspath(output_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    ua = user_agent or _DEFAULT_UA
    hdr_lines = [f"User-Agent: {ua}"]
    if referer:
        hdr_lines.append(f"Referer: {referer}")
    header_str = "\r\n".join(hdr_lines)

    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-stats",
        "-protocol_whitelist",
        "file,http,https,tcp,tls,crypto",
        "-allowed_extensions",
        "ALL",
        "-headers",
        header_str,
        "-i",
        stream_url,
        "-map",
        "0",
        "-ignore_unknown",
        "-c",
        "copy",
        "-bsf:a",
        "aac_adtstoasc",
        "-movflags",
        "+faststart",
        output_path,
    ]

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        assert proc.stderr is not None
        for _line in proc.stderr:
            if stop_flag is not None and getattr(stop_flag, "is_set", lambda: False)():
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except Exception:
                    pass
                return False
        proc.wait()
        if proc.returncode == 0 and os.path.isfile(output_path) and os.path.getsize(output_path) > 0:
            return True
    except Exception as e:
        print("[KDM] download_hls error:", e)
    return False

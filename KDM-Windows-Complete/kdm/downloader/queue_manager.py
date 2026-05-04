"""
Download queue integration: HLS vs direct URL routing (ffmpeg).

Called from the main app for embed-style streams that need a dedicated HLS path.
"""

from __future__ import annotations

from typing import Any, Optional

from kdm.downloader.hls_downloader import download_hls


def is_hls_playlist_url(url: str) -> bool:
    u = (url or "").lower()
    return ".m3u8" in u and ".m3u8.js" not in u


def run_hls_download(
    stream_url: str,
    output_path: str,
    *,
    page_referer: str,
    user_agent: Optional[str] = None,
    stop_flag: Any = None,
) -> bool:
    """ffmpeg HLS → MP4; ``page_referer`` is usually the original movie page URL."""
    return download_hls(
        stream_url,
        output_path,
        referer=page_referer,
        user_agent=user_agent,
        stop_flag=stop_flag,
    )

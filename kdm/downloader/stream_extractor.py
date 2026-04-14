"""
Fallback stream discovery when the primary Playwright sniffer misses the URL.

Uses context-level request/response listeners, longer waits, multi-frame JS scrape,
and play triggers — aligned with the deeper embed logic in ``kdm.py``.
"""

from __future__ import annotations

import re
from typing import Optional, Tuple
from urllib.parse import unquote

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from kdm.downloader.smart_extractor import _bad_capture_url

_DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_JS_SCRAPE = """
() => {
    const out = [];
    const add = (u) => {
        if (u && typeof u === 'string' && u.includes('.m3u8') && !u.includes('.m3u8.js')) out.push(u);
    };
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


def _capture_candidate(url: str) -> bool:
    u = url or ""
    return (
        ".m3u8" in u
        or ".mp4" in u
        or "master.json" in u
    ) and ".m3u8.js" not in u and not _bad_capture_url(u)


def _scrape_all_frames(page) -> Optional[str]:
    for fr in page.frames:
        try:
            found = fr.evaluate(_JS_SCRAPE)
            if found:
                return unquote(str(found))
        except Exception:
            continue
    return None


def extract_stream_url(
    page_url: str,
    *,
    headless: bool = True,
    timeout_sec: int = 15,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Second-pass Playwright extraction for embed pages.

    Returns ``(stream_url, page_title)`` or ``(None, None)``.
    """
    nav_timeout = max(45_000, int(timeout_sec) * 1000)
    stream_url: Optional[str] = None
    title: Optional[str] = None

    def _take(u: str) -> None:
        nonlocal stream_url
        if stream_url or not u:
            return
        if _capture_candidate(u):
            stream_url = unquote(u)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent=_DEFAULT_UA,
            viewport={"width": 1280, "height": 720},
            locale="en-US",
        )
        context.on("request", lambda req: _take(req.url))
        context.on("response", lambda resp: _take(resp.url))

        page = context.new_page()
        try:
            try:
                page.goto(page_url, timeout=nav_timeout, wait_until="load")
            except PlaywrightTimeoutError:
                page.goto(page_url, timeout=nav_timeout, wait_until="domcontentloaded")

            page.wait_for_timeout(2000)
            found = _scrape_all_frames(page)
            if found:
                stream_url = found

            if not stream_url:
                for sel in (
                    'button[aria-label="play"]',
                    ".vjs-big-play-button",
                    "button[class*='play']",
                    ".play",
                    "[data-action='play']",
                    "video",
                ):
                    try:
                        page.click(sel, timeout=3000)
                        page.wait_for_timeout(6000)
                        if stream_url:
                            break
                        found = _scrape_all_frames(page)
                        if found:
                            stream_url = found
                            break
                    except Exception:
                        continue

            if not stream_url:
                try:
                    page.evaluate(
                        "document.querySelector('video') && document.querySelector('video').play()"
                    )
                    page.wait_for_timeout(10000)
                    found = _scrape_all_frames(page)
                    if found:
                        stream_url = found
                except Exception:
                    pass

            if not stream_url:
                html = page.content()
                m = re.search(r'(https?://[^\s"\']+\.m3u8[^\s"\']*)', html)
                if m:
                    cand = m.group(1)
                    if ".m3u8.js" not in cand and not _bad_capture_url(cand):
                        stream_url = cand

            title = page.title() or None
        except Exception:
            pass
        finally:
            browser.close()

    return stream_url, title

"""
Universal embed-page extractor: yt-dlp first, then Playwright network sniff.
MultiMovies and similar sites.

Dependencies (install separately)::

    pip install yt-dlp playwright
    playwright install chromium

The ``playwright install chromium`` step downloads the browser binaries; run it once
after installing the ``playwright`` Python package.
"""

from __future__ import annotations

import logging
import re
import sys
import time

import yt_dlp
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

_DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _bad_capture_url(u: str) -> bool:
    ul = (u or "").lower()
    return any(
        x in ul
        for x in (
            "google.com",
            "gstatic.com",
            "doubleclick.net",
            "googletagmanager.com",
            "facebook.com",
            "analytics",
        )
    )


class SmartVideoExtractor:
    """
    Universal extractor for MultiMovies-style embed pages, etc.
    Pehle yt-dlp try karta hai, agar fail ho to Playwright browser use karta hai.
    """

    def __init__(self, timeout: int = 15, headless: bool = True):
        self.logger = logging.getLogger("KDM.Extractor")
        if not self.logger.handlers:
            _h = logging.StreamHandler()
            _h.setFormatter(logging.Formatter("[KDM] %(message)s"))
            self.logger.addHandler(_h)
            self.logger.setLevel(logging.INFO)
        self.timeout = timeout
        self.headless = headless

    def extract_stream_url(self, page_url: str):
        """
        Kisi bhi video page URL se stream URL nikalta hai.
        Returns: (stream_url, title) or (None, None)
        """
        self.logger.info("SmartVideoExtractor processing: %s", page_url[:120])

        stream_url, title = self._extract_with_ytdlp(page_url)
        if stream_url:
            self.logger.info("yt-dlp successful")
            return stream_url, title

        self.logger.info("yt-dlp failed; falling back to Playwright...")
        stream_url, title = self._extract_with_playwright(page_url)
        if stream_url:
            self.logger.info("Playwright successful")
            return stream_url, title

        self.logger.error("Could not extract stream URL")
        return None, None

    def _extract_with_ytdlp(self, url: str):
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
            "noplaylist": True,
            "socket_timeout": 35,
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
            formats = info.get("formats") or []
            title = info.get("title", "video")

            top = info.get("url")
            if top and isinstance(top, str) and top.startswith("http"):
                return top, title

            if formats:
                best = formats[-1]
                stream_url = best.get("url")
                if not stream_url and "manifest_url" in best:
                    stream_url = best.get("manifest_url")
                if not stream_url and "fragment_base_url" in best:
                    stream_url = best.get("fragment_base_url")
                if stream_url and isinstance(stream_url, str) and stream_url.startswith("http"):
                    return stream_url, title

            for f in reversed(formats):
                if not f:
                    continue
                for key in ("url", "manifest_url", "fragment_base_url"):
                    u = f.get(key)
                    if u and isinstance(u, str) and u.startswith("http"):
                        return u, title
        except Exception as e:
            self.logger.warning("yt-dlp error: %s", str(e)[:120])
        return None, None

    def _extract_with_playwright(self, url: str):
        stream_url = None
        title = None

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=self.headless,
                args=["--disable-blink-features=AutomationControlled"],
            )
            context = browser.new_context(
                user_agent=_DEFAULT_UA,
                viewport={"width": 1280, "height": 720},
            )
            page = context.new_page()

            def capture_response(response):
                nonlocal stream_url
                if stream_url:
                    return
                resp_url = response.url
                if ".m3u8" in resp_url or ".mp4" in resp_url or "master.json" in resp_url:
                    if ".m3u8.js" in resp_url:
                        return
                    if _bad_capture_url(resp_url):
                        return
                    stream_url = resp_url
                    self.logger.info("Captured: %s", resp_url[:100])

            page.on("response", capture_response)

            try:
                self.logger.info("Loading page...")
                page.goto(url, timeout=self.timeout * 1000, wait_until="domcontentloaded")

                try:
                    video = page.wait_for_selector("video", timeout=5000)
                    if video:
                        src = video.get_attribute("src")
                        if src and (".mp4" in src or ".m3u8" in src):
                            stream_url = src
                except Exception:
                    pass

                if not stream_url:
                    for frame in page.frames:
                        if frame == page.main_frame:
                            continue
                        try:
                            video = frame.wait_for_selector("video", timeout=3000)
                            if video:
                                src = video.get_attribute("src")
                                if src and (".mp4" in src or ".m3u8" in src):
                                    stream_url = src
                                    break
                        except Exception:
                            continue

                if not stream_url:
                    self.logger.info("Waiting for video to start...")
                    try:
                        page.click(
                            'button[aria-label="play"], .play-button, .vjs-big-play-button',
                            timeout=2000,
                        )
                    except Exception:
                        pass
                    time.sleep(5)

                if not stream_url:
                    html = page.content()
                    m3u8_match = re.search(r'(https?://[^\s"\']+\.m3u8[^\s"\']*)', html)
                    if m3u8_match:
                        stream_url = m3u8_match.group(1)
                        self.logger.info("Found m3u8 in HTML")

                title = page.title()
            except PlaywrightTimeoutError:
                self.logger.warning("Page load timeout")
            except Exception as e:
                self.logger.error("Playwright error: %s", e)
            finally:
                browser.close()

        if not stream_url:
            self.logger.info("Primary sniffer did not capture stream; trying fallback extractor...")
            try:
                from kdm.downloader.stream_extractor import extract_stream_url as fallback_extract_stream_url

                fb_url, fb_title = fallback_extract_stream_url(
                    url,
                    headless=self.headless,
                    timeout_sec=self.timeout,
                )
            except Exception as e:
                self.logger.warning("Fallback extractor error: %s", str(e)[:120])
                fb_url, fb_title = None, None
            if fb_url:
                stream_url = fb_url
                if fb_title:
                    title = fb_title

        return stream_url, title


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    e = SmartVideoExtractor()
    url = sys.argv[1] if len(sys.argv) > 1 else input("Enter URL: ")
    stream, title = e.extract_stream_url(url)
    print(stream)

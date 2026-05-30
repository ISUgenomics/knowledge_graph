#!/usr/bin/env python3
"""
fetch_with_fallback.py — URL fetch with bot-wall hard stop.

Best practice #25: When scraping fails, stop and ask for local files.
No retries, no header rotation, no proxy attempts.
"""

import re
import urllib.request


TIMEOUT = 20

# Bot challenge indicators in response body
BOT_MARKERS = [
    "recaptcha",
    "g-recaptcha",
    "cf-browser-verification",
    "cloudflare",
    "challenge-platform",
    "just a moment",
    "checking your browser",
    "access denied",
    "please verify you are a human",
    "bot detection",
    "are you a robot",
    "enable javascript",
    "ray id",
]


def fetch_url_or_stop(url: str, description: str = "") -> dict:
    """
    Fetch a URL. If blocked, return a hard stop with download instructions.

    Returns:
        {
            "status": "ok" | "blocked" | "error",
            "text": str,
            "chars": int,
            "message": str,
        }
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate",
        "Accept-Language": "en-US,en;q=0.9",
    }
    req = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read()
            # Decompress if needed
            encoding = resp.headers.get("Content-Encoding", "")
            if encoding == "gzip":
                import gzip
                raw = gzip.decompress(raw)
            elif encoding == "deflate":
                import zlib
                raw = zlib.decompress(raw, -zlib.MAX_WBITS)
            body = raw.decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        if e.code in (403, 429):
            return _blocked(url, f"HTTP {e.code}")
        return _error(url, f"HTTP {e.code}: {e.reason}")
    except urllib.error.URLError as e:
        return _error(url, f"Connection failed: {e.reason}")
    except Exception as e:
        return _error(url, str(e))

    # Check for bot challenges in the response
    body_lower = body.lower()
    for marker in BOT_MARKERS:
        if marker in body_lower:
            return _blocked(url, f"Bot challenge detected ({marker})")

    # Check for suspiciously short responses
    cleaned = _clean_html(body)
    if len(cleaned) < 200:
        # Very short page — might be a redirect or empty template
        if any(w in body_lower for w in ("redirect", "moved", "location")):
            return _error(url, "Page redirects — content not accessible")
        # Accept short pages if they have real content
        if len(cleaned) < 50:
            return _blocked(url, "Response too short — likely blocked or empty")

    return {
        "status": "ok",
        "text": cleaned,
        "chars": len(cleaned),
        "message": f"Fetched {len(cleaned)} chars from {url}",
    }


def _blocked(url: str, reason: str) -> dict:
    """Return a hard stop message with download instructions."""
    message = (
        f"BLOCKED: {url}\n"
        f"Reason: {reason}\n"
        f"\n"
        f"This page cannot be fetched programmatically.\n"
        f"\n"
        f"To proceed:\n"
        f"  1. Open this URL in your browser: {url}\n"
        f"  2. Save the page as HTML or copy the content to a text file\n"
        f"  3. Place it in a folder and re-run with: --folder /path/to/folder"
    )
    return {"status": "blocked", "text": "", "chars": 0, "message": message}


def _error(url: str, reason: str) -> dict:
    """Return an error message."""
    return {
        "status": "error",
        "text": "",
        "chars": 0,
        "message": f"ERROR fetching {url}: {reason}",
    }


def _clean_html(html: str, max_chars: int = 50000) -> str:
    """Strip HTML tags, scripts, styles and return clean text."""
    for tag in ("script", "style", "nav", "footer", "header", "noscript"):
        html = re.sub(rf"<{tag}[^>]*>.*?</{tag}>", "", html, flags=re.DOTALL | re.I)
    html = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)
    html = re.sub(r"<(br|hr|/p|/div|/li|/tr|/h[1-6])[^>]*>", "\n", html, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", html)
    for ent, ch in [("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                     ("&quot;", '"'), ("&#39;", "'"), ("&nbsp;", " ")]:
        text = text.replace(ent, ch)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()[:max_chars]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Fetch URL with bot-wall detection")
    parser.add_argument("url", help="URL to fetch")
    args = parser.parse_args()

    result = fetch_url_or_stop(args.url)
    print(f"Status: {result['status']}")
    print(f"Message: {result['message']}")
    if result["text"]:
        print(f"\n--- Text ({result['chars']} chars) ---")
        print(result["text"][:2000])

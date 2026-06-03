"""Shared HTTP constants and helpers for the Play Store scraper."""

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
)
PLAY_BASE = "https://play.google.com"


def fetch(url: str, headers: dict | None = None, timeout: int = 15) -> str:
    """GET a URL and return the response text (utf-8, errors ignored)."""
    import urllib.request
    h = {"user-agent": USER_AGENT}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="ignore")

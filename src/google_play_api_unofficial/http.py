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


def post_form(url: str, form: dict, headers: dict | None = None,
              timeout: int = 30) -> str:
    """POST a urlencoded form and return the response text.

    Play's internal RPC endpoint takes form-encoded JSON, so this is what the
    publisher pager talks over.
    """
    import urllib.parse
    import urllib.request
    h = {"user-agent": USER_AGENT,
         "content-type": "application/x-www-form-urlencoded;charset=UTF-8",
         "accept-language": "en-US,en;q=0.9"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(
        url, data=urllib.parse.urlencode(form).encode(), headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="ignore")

"""Play Store autocomplete via the teXCtc batchexecute RPC."""

import json
import urllib.parse
import urllib.request
from enum import Enum

from .http import PLAY_BASE

SUGGEST_URL = (
    f"{PLAY_BASE}/_/PlayStoreUi/data/batchexecute"
    "?rpcids=teXCtc&hl=en-US&soc-app=121&soc-platform=1&soc-device=1&rt=c"
)
SUGGEST_HEADERS = {
    "content-type": "application/x-www-form-urlencoded;charset=UTF-8",
    "origin": "https://play.google.com",
    "referer": "https://play.google.com/",
    "x-same-domain": "1",
}


class Filter(Enum):
    """Which kind of apps to include in suggestions."""
    APPS = (2, 1)
    GAMES = (2, 2)
    ALL = (2, 0)


def fetch_suggestions(
    query: str,
    filter: Filter = Filter.APPS,
    timeout: int = 10,
) -> list[str]:
    """Fetch Play Store autocomplete suggestions for a half-query.

    Args:
        query: The half-query to complete.
        filter: One of Filter.APPS (default), Filter.GAMES, or Filter.ALL.
        timeout: HTTP timeout in seconds.
    """
    inner_str = json.dumps([None, [query], [10], list(filter.value), 4])
    payload = [[["teXCtc", inner_str, None, "generic"]]]
    body = "f.req=" + urllib.parse.quote(json.dumps(payload))
    req = urllib.request.Request(
        SUGGEST_URL, data=body.encode("utf-8"),
        headers=SUGGEST_HEADERS, method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        text = r.read().decode("utf-8")
    return _parse(text)


def _parse(body: str) -> list[str]:
    text = body.lstrip()
    if text.startswith(")]}'"):
        text = text[4:].lstrip("\n")
    lines = text.split("\n")
    idx = next((i for i, ln in enumerate(lines) if ln.strip().startswith("[")), None)
    if idx is None:
        return []
    try:
        outer = json.loads(lines[idx])
    except json.JSONDecodeError:
        return []
    out: list[str] = []
    for entry in outer:
        if not (isinstance(entry, list) and len(entry) >= 3):
            continue
        if entry[0] != "wrb.fr" or entry[1] != "teXCtc":
            continue
        inner_str = entry[2]
        if not isinstance(inner_str, str):
            continue
        try:
            inner = json.loads(inner_str)
        except json.JSONDecodeError:
            continue
        for group in inner:
            if not isinstance(group, list):
                continue
            for item in group:
                if isinstance(item, list) and item and isinstance(item[0], str):
                    s = item[0].strip()
                    if 3 <= len(s) <= 100:
                        out.append(s)
    return out

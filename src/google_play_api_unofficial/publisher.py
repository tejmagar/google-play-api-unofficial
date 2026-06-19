"""Apps by a publisher/developer, fetched from Play Store search (pub: operator)."""

import re
import json
import urllib.error
import urllib.parse

from .http import PLAY_BASE, fetch
from .search import _find_apps_block, _extract


def fetch_publisher_apps(
    publisher: str,
    timeout: int = 15,
) -> list[dict]:
    """Fetch all apps found for a publisher/developer name.

    Uses the ``pub:"Publisher Name"`` Play Store search operator
    to return up to ~90 apps (one page of results).

    Args:
        publisher: Developer display name, e.g. ``"Google LLC"``.
        timeout: HTTP timeout in seconds.
    """
    query = f'pub:"{publisher}"'
    url = f"{PLAY_BASE}/store/search?q={urllib.parse.quote_plus(query)}&c=apps&hl=en-US"
    try:
        html = fetch(url, timeout=timeout)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return []
        raise

    DS4_RE = re.compile(
        r"AF_initDataCallback\(\{key:\s*'ds:4',.*?data:(.*?),\s*sideChannel",
        re.DOTALL,
    )
    m = DS4_RE.search(html)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return []

    block = _find_apps_block(data)
    if not block:
        return []

    apps: list[dict] = []
    seen: set[str] = set()
    for wrapper in block:
        if not (isinstance(wrapper, list) and wrapper):
            continue
        a = _extract(wrapper[0])
        if a and a["package"] not in seen:
            seen.add(a["package"])
            apps.append(a)
    return apps

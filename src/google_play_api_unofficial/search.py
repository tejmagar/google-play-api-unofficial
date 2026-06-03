"""Play Store search results (top 30 apps) parsed from the public search page."""

import json
import re
import urllib.error
import urllib.parse

from .http import PLAY_BASE, fetch

DS4_RE = re.compile(
    r"AF_initDataCallback\(\{key:\s*'ds:4',.*?data:(.*?),\s*sideChannel",
    re.DOTALL,
)


def _looks_like_app_entry(node) -> bool:
    """An app entry has [pkg, type] at [0], icon meta at [1], title at [3]."""
    return (
        isinstance(node, list) and len(node) >= 10
        and isinstance(node[0], list) and len(node[0]) >= 1
        and isinstance(node[0][0], str) and "." in node[0][0]
        and isinstance(node[3], str) and len(node[3]) > 1
    )


def _find_apps_block(data) -> list | None:
    """Recursively find the list-of-app-entries block in ds:4.

    Each app entry is wrapped in an extra list level. We pick the largest
    such list found.
    """
    best: list | None = None

    def walk(node):
        nonlocal best
        if isinstance(node, list):
            if len(node) >= 10 and all(
                isinstance(x, list) and len(x) == 1 and _looks_like_app_entry(x[0])
                for x in node
            ):
                if best is None or len(node) > len(best):
                    best = node
            for x in node:
                walk(x)

    walk(data)
    return best


def _extract(entry: list) -> dict | None:
    """Pull title, package, rating, category, developer, installs from one entry."""
    if not _looks_like_app_entry(entry):
        return None
    pkg = entry[0][0]
    title = entry[3]
    rating = None
    if isinstance(entry[4], list) and entry[4] and isinstance(entry[4][0], str):
        rating = entry[4][0]
    category = entry[5] if isinstance(entry[5], str) else None
    developer = entry[14] if isinstance(entry[14], str) else None
    installs = entry[15] if isinstance(entry[15], str) else None
    icon = None
    if isinstance(entry[1], list) and len(entry[1]) >= 4:
        icon_block = entry[1][3]
        if isinstance(icon_block, list) and len(icon_block) >= 3 and isinstance(icon_block[2], str):
            icon = icon_block[2]
    details = None
    if isinstance(entry[10], list) and len(entry[10]) >= 5:
        link = entry[10][4]
        if isinstance(link, list) and len(link) >= 3 and isinstance(link[2], str):
            details = PLAY_BASE + link[2]
    return {
        "package": pkg,
        "title": title,
        "rating": rating,
        "category": category,
        "developer": developer,
        "installs": installs,
        "icon": icon,
        "url": details,
    }


def fetch_apps(query: str, timeout: int = 15) -> list[dict]:
    """Fetch top app results (up to 30) for a query.

    The Play Store HTML endpoint does not paginate via &start=N — to get
    more results, run additional queries with different angles.
    """
    url = f"{PLAY_BASE}/store/search?q={urllib.parse.quote_plus(query)}&c=apps&hl=en-US"
    try:
        html = fetch(url, timeout=timeout)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return []
        raise
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

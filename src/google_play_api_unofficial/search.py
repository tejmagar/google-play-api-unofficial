"""Play Store search results (top 30 apps) parsed from the public search page."""

import html as _html
import json
import re
import urllib.error
import urllib.parse

from .http import PLAY_BASE, fetch

DS4_RE = re.compile(
    r"AF_initDataCallback\(\{key:\s*'ds:4',.*?data:(.*?),\s*sideChannel",
    re.DOTALL,
)

# The "featured" hero card (Play's MDP cluster) is a different renderer from the
# organic result list. Its anchor carries the distinctive `Qfxief` class.
FEATURED_SECTION_RE = re.compile(r'<c-wiz jsrenderer="YTx6oe".*?</section>', re.DOTALL)
FEATURED_ANCHOR_RE = re.compile(
    r'<a href="/store/apps/details\?id=([^"&]+)" aria-label="([^"]*)" class="Qfxief">'
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
        "featured": False,
    }


def _find_featured_cards(html: str) -> list[dict]:
    """Parse the featured hero card(s) Play renders above the organic results.

    Play's "featured app" is a separate cluster (jslog = apps_mdp_search_results_cluster)
    rendered by a dedicated `YTx6oe` renderer whose card anchor has the `Qfxief`
    class. The app is NOT part of the organic ds:4 list, so it is extracted from
    the HTML markup itself.
    """
    cards: list[dict] = []
    for section in FEATURED_SECTION_RE.findall(html):
        anchor = FEATURED_ANCHOR_RE.search(section)
        if not anchor:
            continue
        pkg, title = anchor.group(1), _html.unescape(anchor.group(2))
        rating = None
        m = re.search(r'aria-label="Rated ([0-9.]+) stars', section)
        if m:
            rating = m.group(1)
        installs = None
        m = re.search(r'<div class="ClM7O">([^<]*)</div><div class="g1rdde">Downloads</div>', section)
        if m:
            installs = m.group(1).strip()
        cards.append({
            "package": pkg,
            "title": title,
            "rating": rating,
            "category": None,
            "developer": None,
            "installs": installs,
            "icon": None,
            "url": f"{PLAY_BASE}/store/apps/details?id={pkg}",
            "featured": True,
        })
    return cards


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
    featured = _find_featured_cards(html)
    featured_pkgs = {c["package"] for c in featured}
    m = DS4_RE.search(html)
    if not m:
        return featured
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return featured
    block = _find_apps_block(data)
    if not block:
        return featured
    apps: list[dict] = []
    seen: set[str] = set()
    for wrapper in block:
        if not (isinstance(wrapper, list) and wrapper):
            continue
        a = _extract(wrapper[0])
        if a and a["package"] not in seen:
            seen.add(a["package"])
            a["featured"] = a["package"] in featured_pkgs
            apps.append(a)
    # Play renders the featured card above the organic list; it is often not part
    # of the ds:4 results at all, so prepend it in card order.
    for card in reversed(featured):
        if card["package"] not in seen:
            seen.add(card["package"])
            apps.insert(0, card)
    return apps

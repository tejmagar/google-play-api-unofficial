"""Apps by a publisher.

Two ways, because Play answers this question two different ways and neither one
suits both callers:

``search``
    One ``pub:"Name"`` search page. A single request, and capped near 50 apps
    however many the publisher actually has.

``full``
    Both, merged. The publisher's own page paged to the end, unioned with that
    search page - because the two clusters disagree. For one publisher of 100
    apps the search returns 50, the page walk returns 80, and only 30 are in
    both: each holds apps the other never mentions. Taking either alone and
    calling it the catalogue is how you end up 20 short without knowing it.

The full path is the developer page's own lazy scroll driven over plain HTTP -
no browser, no driver, nothing beyond urllib. The page ships a continuation
token, each response carries the next one, and the walk ends when a page adds
nothing new.

That endpoint is Play's own internal RPC and is undocumented, so its shape can
change without notice. Nothing here papers over that: if the payload stops
looking the way it does today this raises, rather than quietly returning a
short list a caller would mistake for the whole catalogue.
"""

import json
import re
import time
import urllib.error
import urllib.parse

from .http import PLAY_BASE, fetch, post_form
from .search import _extract, _find_apps_block, _looks_like_app_entry

__all__ = ["fetch_publisher_apps", "PlayShapeChanged", "SEARCH_CAP"]

#: What the search path returns at most. Exactly this many is a result to
#: distrust: it means Play stopped counting, not that the publisher stopped
#: shipping.
SEARCH_CAP = 50

# Play's cluster-pagination RPC, and the field set the store's own page asks
# for. Taken from the request the developer page makes when scrolled: the ids
# choose which columns come back, and a shorter list returns less than
# `_extract` reads.
_RPC_ID = "qnKhOb"
_RPC_URL = f"{PLAY_BASE}/_/PlayStoreUi/data/batchexecute"
_FIELDS = [96, 108, 72, 100, 27, 177, 183, 222, 8, 57, 169, 110, 11, 184, 16, 1,
           139, 152, 194, 165, 68, 163, 211, 9, 71, 31, 176, 195, 12, 64, 151,
           320, 150, 148, 113, 104, 55, 56, 145, 32, 34, 10, 122]
_PAGE_SIZE = 20

_SID_RE = re.compile(r'"FdrFJe":"([^"]+)"')
_BL_RE = re.compile(r'"cfb2h":"([^"]+)"')
_TOKEN_RE = re.compile(r'"(IAB[A-Za-z0-9_\-]{40,})"')
_DS4_RE = re.compile(
    r"AF_initDataCallback\(\{key:\s*'ds:4',.*?data:(.*?),\s*sideChannel",
    re.DOTALL,
)
# Any inline data block. The publisher page has moved its cluster between
# ds:4 and ds:3 and may move it again, so the walk scans every block and
# keeps the one with the most app entries instead of pinning a key.
_DATA_CALLBACK_RE = re.compile(
    r"AF_initDataCallback\(\{key:\s*'(ds:\d+)',.*?data:(.*?),\s*sideChannel",
    re.DOTALL,
)


class PlayShapeChanged(RuntimeError):
    """Play's payload no longer looks the way this module expects."""


def fetch_publisher_apps(
    publisher: str,
    *,
    full: bool = False,
    max_apps: int | None = None,
    timeout: int = 30,
    pause: float = 0.5,
) -> list[dict]:
    """Apps published by ``publisher``.

    Args:
        publisher: Developer display name (``"Google LLC"``), or the numeric id
            out of a ``/store/apps/dev?id=`` link.
        full: Every app, from both of Play's clusters. Costs one request per
            twenty apps plus one for the search page.
        max_apps: Stop once this many are collected. Only meaningful with
            ``full`` - a search page is one page either way.
        timeout: Per-request HTTP timeout, in seconds.
        pause: Seconds between pages, so a large catalogue is not a burst.

    Returns:
        App dicts in Play's own order, deduplicated by package.
    """
    if not full:
        return _search_once(publisher, timeout)

    # Page order first, then whatever only the search knows about, so the
    # common case reads in the order the publisher's own page presents.
    apps = {a["package"]: a
            for a in _walk_publisher_page(publisher, max_apps, timeout, pause)}
    for app in _search_once(publisher, timeout):
        apps.setdefault(app["package"], app)
    out = list(apps.values())
    return out[:max_apps] if max_apps is not None else out


def _search_once(publisher: str, timeout: int) -> list[dict]:
    """One ``pub:"Name"`` search page."""
    query = urllib.parse.quote_plus(f'pub:"{publisher}"')
    try:
        html = fetch(f"{PLAY_BASE}/store/search?q={query}&c=apps&hl=en-US",
                     timeout=timeout)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return []
        raise

    m = _DS4_RE.search(html)
    if not m:
        return []
    return _collect(_find_apps_block(json.loads(m.group(1))) or [])


def _walk_publisher_page(publisher: str, max_apps: int | None,
                         timeout: int, pause: float) -> list[dict]:
    """Page the publisher's own listing until it stops yielding new apps.

    Small publishers render their whole catalogue inline in the page with no
    continuation cursor; large ones render a first page inline and page the
    rest through the RPC. Both are read here: the inline entries first (they
    are the first page either way), then any further RPC pages.
    """
    page_url = _publisher_url(publisher)
    try:
        html = fetch(page_url, timeout=timeout)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return []
        raise
    sid, bl, token = _session(html)
    apps: dict[str, dict] = {}
    for app in _inline_entries(html):
        apps.setdefault(app["package"], app)

    while token:
        entries, token = _rpc_page(page_url, sid, bl, token, timeout)
        before = len(apps)
        for app in _collect(entries):
            apps.setdefault(app["package"], app)
        # Play keeps offering a cursor past the end of some catalogues, so a
        # page that adds nothing is the real end of the walk.
        if len(apps) == before:
            break
        if max_apps is not None and len(apps) >= max_apps:
            return list(apps.values())[:max_apps]
        if token:
            time.sleep(pause)

    return list(apps.values())


def _inline_entries(html: str) -> list[dict]:
    """Apps embedded directly in the publisher page's data blocks.

    Play renders the publisher's own games first, inline, in an
    ``AF_initDataCallback`` block before any lazy-scroll magic. Which slot the
    cluster lands in is not stable, so scan every ``ds:`` block and keep the
    largest list of app-shaped entries.
    """
    best: tuple[int, list] = (0, [])
    for m in _DATA_CALLBACK_RE.finditer(html):
        try:
            data = json.loads(m.group(2))
        except (json.JSONDecodeError, ValueError):
            continue
        entries = _largest_entries(data)
        if len(entries) > best[0]:
            best = (len(entries), entries)
    return _collect(best[1])


def _largest_entries(data) -> list:
    """The largest list of app-shaped entries anywhere in ``data``.

    Two shapes exist side by side: a ``/developer`` page wraps every entry in a
    single-element list, a ``/dev`` page ships them bare. Recursing for the
    biggest list in either shape keeps this independent of which page Play
    served and which ``ds:`` slot the cluster landed in.
    """
    best: list = []

    def walk(node):
        nonlocal best
        if not isinstance(node, list):
            return
        if all(isinstance(x, list) and len(x) == 1
               and _looks_like_app_entry(x[0]) for x in node):
            entries = [x[0] for x in node]
        elif all(_looks_like_app_entry(x) for x in node):
            entries = node
        else:
            entries = None
        if entries is not None and len(entries) > len(best):
            best = entries
        for x in node:
            walk(x)

    walk(data)
    return best


def _publisher_url(publisher: str) -> str:
    """Their page. Numeric ids live under /dev, display names under /developer."""
    path = "dev" if publisher.isdigit() else "developer"
    return (f"{PLAY_BASE}/store/apps/{path}"
            f"?id={urllib.parse.quote_plus(publisher)}&hl=en&gl=us")


def _session(html: str) -> tuple[str, str, str | None]:
    """The things the page hands its own RPC calls.

    ``f.sid`` and ``bl`` identify the session and the server build. The IAB
    token is the cursor into a *paged* cluster and carries the publisher inside
    it, which is why it must be read off their page rather than constructed.
    Small publishers render everything inline and hand out no cursor at all, so
    a missing token is ``None``: the walk has nothing further to page.
    """
    sid, bl, token = (_SID_RE.search(html), _BL_RE.search(html),
                      _TOKEN_RE.search(html))
    if not (sid and bl):
        raise PlayShapeChanged(
            "the publisher page no longer carries what this reads from it "
            "(f.sid, cfb2h)")
    return sid.group(1), bl.group(1), token.group(1) if token else None


def _rpc_page(page_url: str, sid: str, bl: str, token: str,
              timeout: int) -> tuple[list, str | None]:
    """One page of the cluster: its entries, and the cursor for the next."""
    payload = [[None, [[10, [_PAGE_SIZE]], None, None, _FIELDS], None, token], [1]]
    query = urllib.parse.urlencode({
        "rpcids": _RPC_ID, "source-path": "/store/apps/developer",
        "hl": "en", "gl": "us", "f.sid": sid, "bl": bl, "_reqid": "1", "rt": "c",
    })
    return _parse_rpc(post_form(
        f"{_RPC_URL}?{query}",
        {"f.req": json.dumps([[[_RPC_ID, json.dumps(payload), None, "generic"]]])},
        headers={"referer": page_url},
        timeout=timeout,
    ))


def _parse_rpc(body: str) -> tuple[list, str | None]:
    """Unwrap batchexecute: length-prefixed frames around a JSON string."""
    line = next((l for l in body.split("\n") if l.startswith('[["wrb.fr"')), None)
    if line is None:
        raise PlayShapeChanged("no wrb.fr frame in the RPC response")
    cluster = json.loads(json.loads(line)[0][2])[0]
    entries, token = _rpc_cluster(cluster)
    if entries is None:
        raise PlayShapeChanged("no apps cluster in the RPC response")
    return entries, token


def _rpc_cluster(cluster: list) -> tuple[list | None, str | None]:
    """The entries and the next cursor out of one cluster.

    ``/developer`` pages nest the apps at ``cluster[22][0]`` wrapped one per
    cell; ``/dev`` numeric-id pages put them bare at ``cluster[21][0]`` and may
    ship no cursor at all. The shape can shuffle again, so the block is found
    by recursing for the largest app-shaped list rather than by index, and the
    cursor is read from the sibling that usually sits next to it.
    """
    entries, parent = _largest_entries_with_parent(cluster)
    nxt = None
    if parent is not None and len(parent) > 1:
        sibling = parent[1]
        if (isinstance(sibling, list) and len(sibling) > 3
                and isinstance(sibling[3], list) and sibling[3]
                and isinstance(sibling[3][1], str)):
            nxt = sibling[3][1]
    return entries, nxt


def _largest_entries_with_parent(data) -> tuple[list, list | None]:
    """The largest app-shaped list in ``data`` and the list that holds it.

    The cursor on a ``/developer`` page lives beside the entries, so returning
    the parent is what lets the caller read it without knowing its index.
    """
    best: tuple[int, list, list | None] = (0, [], None)

    def walk(node, parent):
        nonlocal best
        if not isinstance(node, list):
            return
        if all(isinstance(x, list) and len(x) == 1
               and _looks_like_app_entry(x[0]) for x in node):
            entries = [x[0] for x in node]
        elif all(_looks_like_app_entry(x) for x in node):
            entries = node
        else:
            entries = None
        if entries is not None and len(entries) > best[0]:
            best = (len(entries), entries, parent)
        for x in node:
            walk(x, node)

    walk(data, None)
    if best[0] == 0:
        return None, None
    return best[1], best[2]


def _collect(block: list) -> list[dict]:
    """Entries (bare or single-cell-wrapped) to app dicts, in order, uniquely."""
    apps: list[dict] = []
    seen: set[str] = set()
    for cell in block:
        entry = cell
        if (isinstance(cell, list) and len(cell) == 1
                and _looks_like_app_entry(cell[0])):
            entry = cell[0]
        if not (isinstance(entry, list) and entry):
            continue
        app = _extract(entry)
        if app and app["package"] not in seen:
            seen.add(app["package"])
            apps.append(app)
    return apps

"""Per-app details fetched from a Play Store app page (ds:5 + og:image)."""

import html as html_lib
import json
import re
import urllib.error

from .http import PLAY_BASE, fetch


class AppNotFoundError(Exception):
    """Raised by fetch_app_details when the Play Store returns 404 for a package id."""
    def __init__(self, package_id: str):
        self.package_id = package_id
        super().__init__(f"app not found: {package_id}")

DS5_RE = re.compile(
    r"AF_initDataCallback\(\{key:\s*'ds:5',.*?data:(.*?),\s*sideChannel",
    re.DOTALL,
)
OG_IMAGE_RE = re.compile(r'<meta property="og:image" content="([^"]+)"')
UPDATED_RE = re.compile(r'Updated on</div><div[^>]+>([^<]+)</div>')


def _html_to_text(s: str) -> str:
    """Decode HTML entities, normalize <br>/<p>, drop other tags."""
    if not isinstance(s, str):
        return s
    s = html_lib.unescape(s)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.IGNORECASE)
    s = re.sub(r"</p\s*>", "\n", s, flags=re.IGNORECASE)
    s = re.sub(r"<[^>]+>", "", s)
    return s.strip()


def _safe(node, *path, default=None):
    """Walk a path through nested lists/dicts; return default if anything is missing."""
    cur = node
    for i in path:
        if isinstance(i, int):
            if not isinstance(cur, list) or i >= len(cur) or cur[i] is None:
                return default
            cur = cur[i]
        elif isinstance(i, str) and isinstance(cur, dict):
            cur = cur.get(i)
            if cur is None:
                return default
        else:
            return default
    return cur


def _extract_details(record: list, html_text: str = "") -> dict | None:
    """Pull rich details from one app's ds:5[1][2] record (length 100+)."""
    if not (isinstance(record, list) and len(record) >= 78):
        return None

    title = _safe(record, 0, 0, default=_safe(record, 0))
    if not isinstance(title, str):
        return None

    content_rating = None
    cr = _safe(record, 9, 0)
    if isinstance(cr, list) and cr and isinstance(cr[0], str):
        content_rating = cr[0]
    elif isinstance(cr, str):
        content_rating = cr

    released = None
    rel = _safe(record, 10, 0)
    if isinstance(rel, str):
        released = rel
    elif isinstance(rel, list) and rel and isinstance(rel[0], str):
        released = rel[0]

    installs = None
    installs_min = None
    installs_real = None
    inst = _safe(record, 13)
    if isinstance(inst, list) and inst:
        if isinstance(inst[0], str):
            installs = inst[0]
        if len(inst) >= 2 and isinstance(inst[1], int):
            installs_min = inst[1]
        if len(inst) >= 3 and isinstance(inst[2], int):
            installs_real = inst[2]

    iap_range = None
    iap = _safe(record, 19, 0)
    if isinstance(iap, str):
        iap_range = iap

    developer = None
    dev_id = None
    dev_node = _safe(record, 68)
    if isinstance(dev_node, list) and dev_node and isinstance(dev_node[0], str):
        developer = dev_node[0]
        if len(dev_node) >= 3 and isinstance(dev_node[2], str):
            dev_id = dev_node[2]
    elif isinstance(dev_node, str):
        developer = dev_node

    score = None
    score_count = None
    reviews = None
    histogram: list[tuple[int, int]] = []  # [(stars, count), ...] 5..1
    ratings = _safe(record, 51)
    if isinstance(ratings, list) and ratings:
        sc = _safe(ratings, 0, 0)
        if isinstance(sc, str):
            score = sc
        hist = _safe(ratings, 1)
        if isinstance(hist, list):
            for stars, slot in zip((5, 4, 3, 2, 1), hist[1:]):
                if isinstance(slot, list) and len(slot) >= 2 and isinstance(slot[1], int):
                    histogram.append((stars, slot[1]))
        rc = _safe(ratings, 2, 0)
        if isinstance(rc, str):
            score_count = rc
        rv = _safe(ratings, 3, 0)
        if isinstance(rv, str):
            reviews = rv

    website = None
    email = None
    address = None
    contact = _safe(record, 69)
    if isinstance(contact, list):
        w = _safe(contact, 0, 5, 2)
        if isinstance(w, str):
            website = w
        e = _safe(contact, 1, 0)
        if isinstance(e, str):
            email = e
        a = _safe(contact, 4, 1)
        if isinstance(a, str):
            address = a

    full_description = None
    desc_node = _safe(record, 72, 0, 1)
    if isinstance(desc_node, str):
        full_description = _html_to_text(desc_node)

    short_description = None
    sdesc = _safe(record, 73, 0, 1)
    if isinstance(sdesc, str):
        short_description = _html_to_text(sdesc)

    package_id = None
    pid = _safe(record, 77, 0)
    if isinstance(pid, str):
        package_id = pid

    screenshots: list[str] = []
    icon = None
    sc_shots = _safe(record, 78, 0)
    if isinstance(sc_shots, list):
        for s in sc_shots:
            if isinstance(s, list) and len(s) >= 4:
                inner = s[3]
                if isinstance(inner, list) and len(inner) >= 3 and isinstance(inner[2], str):
                    screenshots.append(inner[2])
        if screenshots:
            icon = screenshots[0]

    if html_text:
        m = OG_IMAGE_RE.search(html_text)
        if m:
            icon = m.group(1)
        m = UPDATED_RE.search(html_text)
        updated = m.group(1).strip() if m else None
    else:
        updated = None

    return {
        "package": package_id,
        "title": title,
        "score": score,
        "ratings_count": score_count,
        "reviews_count": reviews,
        "histogram": histogram,
        "installs": installs,
        "installs_min": installs_min,
        "installs_real": installs_real,
        "released": released,
        "updated": updated,
        "content_rating": content_rating,
        "category": None,
        "developer": developer,
        "developer_id": dev_id,
        "developer_email": email,
        "developer_website": website,
        "developer_address": address,
        "iap_range": iap_range,
        "short_description": short_description,
        "description": full_description,
        "icon": icon,
        "screenshots": screenshots,
        "url": f"{PLAY_BASE}/store/apps/details?id={package_id}&hl=en-US" if package_id else None,
    }


def fetch_app_details(package_id: str, timeout: int = 15) -> dict | None:
    """Fetch rich details for one Play Store app by package id.

    Raises:
        AppNotFoundError: if the Play Store returns 404 (no such package).
        urllib.error.HTTPError: for other HTTP errors (e.g. 429 rate limit).
        json.JSONDecodeError: if the page payload is malformed (rare; we
            actually catch this internally and return None).

    Returns None if the page was fetched but couldn't be parsed.
    """
    url = f"{PLAY_BASE}/store/apps/details?id={package_id}&hl=en-US&gl=us"
    try:
        html_text = fetch(url, timeout=timeout)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise AppNotFoundError(package_id) from e
        raise
    m = DS5_RE.search(html_text)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    record = _safe(data, 1, 2)
    if not isinstance(record, list):
        return None
    return _extract_details(record, html_text)

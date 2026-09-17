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


def _store(country: str) -> str:
    """A storefront code Play will accept, from whatever the caller passed."""
    code = str(country or "us").strip().lower()
    return code if len(code) == 2 and code.isalpha() else "us"


def _looks_like_app_entry(node) -> bool:
    """An app entry has [pkg, type] at [0], icon meta at [1], title at [3]."""
    return (
        isinstance(node, list) and len(node) >= 10
        and isinstance(node[0], list) and len(node[0]) >= 1
        and isinstance(node[0][0], str) and "." in node[0][0]
        and isinstance(node[3], str) and len(node[3]) > 1
    )


#: A candidate list has to be mostly app entries, and long enough that "mostly"
#: means something. Both are deliberately loose. The point is to recognise a
#: result list, not to decide what a result list must look like.
#:
#: The floor used to be ten and the test used to be `all`, and each threw away
#: real pages. Ten discarded every short page outright: "dazz cam" on the Nepali
#: store returns five apps, so the block was never picked and the search came
#: back empty rather than short. `all` was worse - a single entry the extractor
#: could not read discarded the entire list, so "all social media app" returned
#: nothing at all for a page opening with Facebook, Instagram and TikTok.
_MIN_ENTRIES = 3
_MIN_SHARE = 0.6


def _find_apps_block(data) -> list | None:
    """Recursively find the list-of-app-entries block in ds:4.

    Each app entry is wrapped in an extra list level. We pick the list with the
    most readable entries, not the longest one: a long list that is mostly
    something else is not the results.
    """
    best: list | None = None
    best_score = 0

    def readable(node) -> int:
        return sum(1 for x in node
                   if isinstance(x, list) and len(x) == 1
                   and _looks_like_app_entry(x[0]))

    def walk(node):
        nonlocal best, best_score
        if isinstance(node, list):
            if len(node) >= _MIN_ENTRIES:
                good = readable(node)
                if (good >= _MIN_ENTRIES and good >= _MIN_SHARE * len(node)
                        and good > best_score):
                    best, best_score = node, good
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


def fetch_apps(query: str, country: str = "us", lang: str = "en-US",
               timeout: int = 15) -> list[dict]:
    """Fetch top app results (up to 30) for a query, from one storefront.

    The Play Store HTML endpoint does not paginate via &start=N — to get
    more results, run additional queries with different angles.

    `country` is Play's `gl`, and it decides which store is searched. Without
    it Play picks from the requesting address, so the same call returns a
    different page depending on where it is run from — and a caller that meant
    to ask about India gets whatever the server's IP resolves to. One query,
    four storefronts, by how many of the thirty results the un-parameterised
    page also returned:

        no gl   30 apps   Venmo, Bank of America, Cash App
        gl=us   30 apps   30 shared
        gl=in   30 apps   11 shared      HDFC, Canara, SBI
        gl=np   30 apps   13 shared      NIC Asia, Global Smart
        gl=br   50 apps   16 shared      Nubank, Mercado Pago

    The language stays `en-US` on purpose, and it is not cosmetic: `hl` selects
    the localised search index, so an English request to a non-English store
    can match fewer listings than a local-language one ("dazz cam" in Nepal
    returns five in English and thirty in Nepali). English is the consistent
    answer across storefronts; a caller wanting the local page can pass `lang`.
    """
    url = (f"{PLAY_BASE}/store/search?q={urllib.parse.quote_plus(query)}"
           f"&c=apps&hl={urllib.parse.quote_plus(lang)}"
           f"&gl={urllib.parse.quote_plus(_store(country))}")
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

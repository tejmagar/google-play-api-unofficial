"""Human-facing CLI: subcommands for `suggest`, `search`, `details`.

Examples:
  google-play-api suggest vpn
  google-play-api search "habit tracker" --json
  google-play-api search "habit tracker" --with-details
  google-play-api details ch.protonvpn.android com.duolingo
  google-play-api all vpn
"""

import argparse
import json
import sys
import time

from .suggest import fetch_suggestions, Filter
from .search import fetch_apps
from .details import fetch_app_details, AppNotFoundError


def _filter_type(s: str) -> Filter:
    """argparse type: accept 'apps', 'games', 'all' (case-insensitive)."""
    key = s.lower()
    mapping = {
        "apps": Filter.APPS,
        "games": Filter.GAMES,
        "all": Filter.ALL,
    }
    if key not in mapping:
        raise argparse.ArgumentTypeError(
            f"invalid filter {s!r} (choose from: {', '.join(mapping)})"
        )
    return mapping[key]


def _print_apps_human(apps: list[dict]) -> None:
    for a in apps:
        rating = f"  {a['rating']}*" if a.get("rating") else ""
        installs = f"  {a['installs']}" if a.get("installs") else ""
        cat = f"  [{a['category']}]" if a.get("category") else ""
        print(f"    - {a['title']}{rating}{installs}{cat}")
        print(f"        {a['package']}")


def _print_details_human(d: dict) -> None:
    print(f"  Title:       {d.get('title')}")
    print(f"  Package:     {d.get('package')}")
    if d.get("score"):
        print(f"  Score:       {d['score']}  ({d.get('ratings_count', '?')} ratings, "
              f"{d.get('reviews_count', '?')} reviews)")
    if d.get("installs"):
        extras = ""
        if d.get("installs_real"):
            extras = f"  (~{d['installs_real']:,} real)"
        print(f"  Installs:    {d['installs']}{extras}")
    if d.get("released"):
        print(f"  Released:    {d['released']}")
    if d.get("updated"):
        print(f"  Updated:     {d['updated']}")
    if d.get("content_rating"):
        print(f"  Content:     {d['content_rating']}")
    if d.get("developer"):
        line = d["developer"]
        if d.get("developer_website"):
            line += f"  ({d['developer_website']})"
        if d.get("developer_email"):
            line += f"  <{d['developer_email']}>"
        print(f"  Developer:   {line}")
    if d.get("iap_range"):
        print(f"  IAP:         {d['iap_range']}")
    if d.get("histogram"):
        bar = "  ".join(f"{s}*:{c:,}" for s, c in d["histogram"])
        print(f"  Histogram:   {bar}")
    if d.get("short_description"):
        print(f"  Tagline:     {d['short_description']}")
    if d.get("description"):
        print(f"  Description:")
        for line in d["description"].split("\n"):
            print(f"    {line}")


# ---------- subcommands ----------
def cmd_suggest(args) -> int:
    out: dict[str, list[str]] = {}
    for q in args.queries:
        try:
            out[q] = fetch_suggestions(q, filter=args.filter)
        except Exception as e:
            out[q] = []
            print(f"! suggest error for '{q}': {e}", file=sys.stderr)
    if args.json:
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0
    for q, sugs in out.items():
        print(f"\n=== {q} ===")
        print(f"  Suggestions ({len(sugs)}):")
        for s in sugs:
            print(f"    - {s}")
    return 0


def cmd_search(args) -> int:
    out: dict[str, dict] = {}
    for q in args.queries:
        out[q] = {}
        try:
            apps = fetch_apps(q)
        except Exception as e:
            apps = []
            print(f"! apps error for '{q}': {e}", file=sys.stderr)
        if args.with_details and apps:
            enriched = []
            for i, a in enumerate(apps):
                try:
                    d = fetch_app_details(a["package"])
                except AppNotFoundError:
                    d = None
                    print(f"! app not found: {a['package']}", file=sys.stderr)
                except Exception as e:
                    d = None
                    print(f"! details error for '{a['package']}': {e}", file=sys.stderr)
                if d:
                    merged = {**a, **{k: v for k, v in d.items() if v not in (None, [], "")}}
                    enriched.append(merged)
                else:
                    enriched.append(a)
                if i < len(apps) - 1:
                    time.sleep(0.2)
            out[q]["apps"] = enriched
        else:
            out[q]["apps"] = apps
    if args.json:
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0
    for q, data in out.items():
        print(f"\n=== {q} ===")
        print(f"\n  Apps ({len(data['apps'])}):")
        if args.with_details:
            for a in data["apps"]:
                _print_details_human(a)
        else:
            _print_apps_human(data["apps"])
    return 0


def cmd_details(args) -> int:
    out: dict[str, dict | None] = {}
    for i, pkg in enumerate(args.packages):
        try:
            out[pkg] = fetch_app_details(pkg)
        except AppNotFoundError:
            out[pkg] = None
            print(f"! app not found: {pkg}", file=sys.stderr)
        except Exception as e:
            out[pkg] = None
            print(f"! details error for '{pkg}': {e}", file=sys.stderr)
        if i < len(args.packages) - 1:
            time.sleep(0.2)
    if args.json:
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0
    for pkg, d in out.items():
        print(f"\n=== {pkg} ===")
        if d is None:
            print("  (app not found)")
            continue
        _print_details_human(d)
    return 0


def cmd_all(args) -> int:
    """Run suggest + search together for one or more queries."""
    out: dict[str, dict] = {}
    for q in args.queries:
        out[q] = {}
        try:
            out[q]["suggestions"] = fetch_suggestions(q)
        except Exception as e:
            out[q]["suggestions"] = []
            print(f"! suggest error for '{q}': {e}", file=sys.stderr)
        try:
            out[q]["apps"] = fetch_apps(q)
        except Exception as e:
            out[q]["apps"] = []
            print(f"! apps error for '{q}': {e}", file=sys.stderr)
    if args.json:
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0
    for q, data in out.items():
        print(f"\n=== {q} ===")
        if "suggestions" in data:
            print(f"\n  Suggestions ({len(data['suggestions'])}):")
            for s in data["suggestions"]:
                print(f"    - {s}")
        if "apps" in data:
            print(f"\n  Apps ({len(data['apps'])}):")
            _print_apps_human(data["apps"])
    return 0


# ---------- main ----------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="google-play-api",
        description="Play Store research CLI: suggestions, search, and per-app details.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    p_sug = sub.add_parser("suggest", help="Autocomplete suggestions for a half-query")
    p_sug.add_argument("queries", nargs="+", help="Half-queries")
    p_sug.add_argument(
        "--filter", type=_filter_type, default=Filter.APPS,
        help="What kind of apps to include: apps, games, or all (default: apps)",
    )
    p_sug.add_argument("--json", action="store_true", help="Output as JSON")
    p_sug.set_defaults(func=cmd_suggest)

    p_sea = sub.add_parser("search", help="Top apps for a query (up to 30 results)")
    p_sea.add_argument("queries", nargs="+", help="Search queries")
    p_sea.add_argument("--with-details", action="store_true",
                       help="Also fetch per-app details (description, reviews, etc.)")
    p_sea.add_argument("--json", action="store_true", help="Output as JSON")
    p_sea.set_defaults(func=cmd_search)

    p_det = sub.add_parser("details", help="Rich details for one or more package ids")
    p_det.add_argument("packages", nargs="+", help="Package ids, e.g. com.duolingo")
    p_det.add_argument("--json", action="store_true", help="Output as JSON")
    p_det.set_defaults(func=cmd_details)

    p_all = sub.add_parser("all", help="Run suggest + search together for each query")
    p_all.add_argument("queries", nargs="+", help="Search queries")
    p_all.add_argument("--json", action="store_true", help="Output as JSON")
    p_all.set_defaults(func=cmd_all)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

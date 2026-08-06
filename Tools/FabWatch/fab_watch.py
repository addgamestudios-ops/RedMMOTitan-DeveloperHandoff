#!/usr/bin/env python3
"""fab_watch.py — Watch Fab (Epic's asset marketplace) for free & on-sale packs.

Uses Browserbase **Fetch** (no cloud browser, no LLM) via the `browse` CLI, so it runs on the
Browserbase Free plan with no bot-protection headaches and no Model Gateway token cost.

Setup (once):
    export BROWSERBASE_API_KEY=bb_live_xxx      # your key; do NOT hardcode it in this repo

Run:
    python3 fab_watch.py

It prints the current lists and writes fab_free.json next to this script for the game/tools to read.
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

FREE_URL = "https://www.fab.com/limited-time-free"
SALE_URL = "https://www.fab.com/search?min_discount_percentage=1"
LINK_RE = re.compile(r"\[([^\]]+)\]\((https://www\.fab\.com/(listings|sellers)/[^)]+)\)")


def fetch_markdown(url: str) -> str | None:
    """Return the page content as markdown via Browserbase Fetch, or None on failure."""
    try:
        proc = subprocess.run(
            ["browse", "cloud", "fetch", url, "--format", "markdown"],
            capture_output=True, text=True, timeout=120,
        )
    except FileNotFoundError:
        sys.exit("ERROR: the `browse` CLI isn't installed. Install with:  npm install -g browse@latest")
    except subprocess.TimeoutExpired:
        print(f"  timed out fetching {url}", file=sys.stderr)
        return None
    raw = proc.stdout.strip()
    brace = raw.find("{")          # skip the CLI's "Update available" banner
    if brace == -1:
        print(f"  no JSON payload from fetch of {url}", file=sys.stderr)
        return raw or None
    try:
        payload = json.loads(raw[brace:])
    except json.JSONDecodeError:
        return raw                 # some CLI builds emit raw markdown
    code = payload.get("statusCode", 200)
    if code != 200:
        print(f"  HTTP {code} fetching {url}", file=sys.stderr)
    return payload.get("content", "")


def parse_free(md: str | None):
    """Return (free_until, [{title, seller, url}]) from the Limited-Time Free section."""
    if not md:
        return None, []
    sec = re.search(
        r"Limited-Time Free \(Until ([^)]*)\)(.*?)(?:## Useful links|Get the latest Fab news|© \d{4} Epic)",
        md, re.S,
    )
    if not sec:
        return None, []
    until, body = sec.group(1).strip(), sec.group(2)
    items = []
    for text, url, kind in LINK_RE.findall(body):
        if kind == "listings":
            items.append({"title": text.strip(), "url": url, "seller": None, "free_until": until})
        elif kind == "sellers" and items and items[-1]["seller"] is None:
            items[-1]["seller"] = text.strip()
    return until, items


def parse_sale(md: str | None, limit: int = 25):
    """Best-effort list of on-sale listings (title, url). May be sparse if the page needs JS."""
    if not md:
        return []
    seen, out = set(), []
    for text, url, kind in LINK_RE.findall(md):
        if kind == "listings" and url not in seen:
            seen.add(url)
            out.append({"title": text.strip(), "url": url})
            if len(out) >= limit:
                break
    return out


def main() -> None:
    if not os.environ.get("BROWSERBASE_API_KEY"):
        sys.exit("ERROR: set BROWSERBASE_API_KEY in your environment first "
                 "(export BROWSERBASE_API_KEY=bb_live_xxx).")

    print("Fab marketplace watch  —  via Browserbase Fetch (no browser, free-tier friendly)\n")

    until, free = parse_free(fetch_markdown(FREE_URL))
    print(f"LIMITED-TIME FREE  ({len(free)} pack(s)" + (f", until {until}" if until else "") + "):")
    for it in free:
        seller = f"  —  {it['seller']}" if it.get("seller") else ""
        print(f"  • {it['title']}{seller}\n      {it['url']}")
    if not free:
        print("  (none found — the page layout may have changed)")

    sale = parse_sale(fetch_markdown(SALE_URL))
    print(f"\nON SALE  ({len(sale)} shown):")
    for it in sale:
        print(f"  • {it['title']}\n      {it['url']}")
    if not sale:
        print("  (none parsed via Fetch — the /search results are JS-rendered; see README for the "
              "Stagehand-browser upgrade if you want full on-sale coverage)")

    report = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "free_until": until,
        "limited_time_free": free,
        "on_sale_sample": sale,
    }
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fab_free.json")
    with open(out_path, "w") as fh:
        json.dump(report, fh, indent=2)
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()

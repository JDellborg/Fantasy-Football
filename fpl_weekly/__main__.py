"""Command line entry point.

    python -m fpl_weekly build                 # build the latest finished gameweek (out/ and site/)
    python -m fpl_weekly build --gameweek 9    # build a specific gameweek
    python -m fpl_weekly build --only-if-new   # skip if that gameweek was already posted
    python -m fpl_weekly post                  # send out/teams_payload.json to Teams
"""

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

from .api import FPLClient
from .render import to_markdown, to_markdown_teaser, to_teams_payload
from .site import write_site
from .stats import build_report, latest_final_gameweek

ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT / "state" / "last_posted_gameweek.txt"
OUT = ROOT / "out"
SITE = ROOT / "site"


def last_posted():
    try:
        return int(STATE_FILE.read_text().strip() or 0)
    except (FileNotFoundError, ValueError):
        return 0


def set_output(**values):
    """Pass values to later GitHub Actions steps."""
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a") as f:
            for k, v in values.items():
                f.write(f"{k}={v}\n")


def tables_ready(client, config, gw):
    """True once FPL has finished updating league tables for this gameweek.

    1. FPL's own status flag must say the leagues are "Updated" and bonus points added.
    2. Every manager's total in the classic league table must match their history total.
    """
    status = client.event_status()
    rows = [r for r in status.get("status", []) if r.get("event") == gw]
    if rows:  # gw is still the 'current' gameweek, so its status is reported
        if not all(r.get("bonus_added") for r in rows):
            return False, "bonus points not added yet"
        if status.get("leagues") != "Updated":
            return False, f"league tables still updating (status: {status.get('leagues') or 'pending'!r})"
        _league, standings = client.classic_standings(config["classic_league_id"])
        for r in standings:
            hist = {h["event"]: h for h in client.entry_history(r["entry"]).get("current", [])}
            if gw in hist and hist[gw]["total_points"] != r["total"]:
                return False, f"league table total for {r['player_name']} not updated yet"
    return True, "league tables updated"


def build(args):
    config = json.loads(Path(args.config).read_text())
    client = FPLClient()

    if args.only_if_new and not args.gameweek:
        latest = latest_final_gameweek(client.bootstrap()["events"])
        if not latest or latest <= last_posted():
            print(f"No new finished gameweek (latest final: {latest}, last posted: {last_posted()}).")
            set_output(publish="false")
            return 0
        ready, reason = tables_ready(client, config, latest)
        if not ready:
            print(f"Gameweek {latest} is finished but not ready to post: {reason}. Will try again later.")
            set_output(publish="false")
            return 0
        print(f"Gameweek {latest}: {reason}.")

    report = build_report(client, config, args.gameweek, cache_dir=ROOT / "state" / "cache")
    page = write_site(report, SITE, config.get("accent_color", "#ff6b1a"))
    link = None
    if config.get("site_url"):
        link = config["site_url"].rstrip("/") + f"/gw/{report.gameweek}.html"
    payload = to_teams_payload(report, link)
    markdown = to_markdown(report)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "teams_payload.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    (OUT / "report.md").write_text(markdown)
    (OUT / "gameweek.txt").write_text(str(report.gameweek))
    (OUT / "page.html").write_text(page.read_text())
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(to_markdown_teaser(report, link))
            f.write("\n<details><summary><b>Full web page content (click to expand)</b></summary>\n\n")
            f.write(markdown + "\n\n</details>\n")
    print(markdown)
    set_output(publish="true", gameweek=report.gameweek)
    return 0


def post(args):
    secret = "TEAMS_TEST_WEBHOOK_URL" if args.test else "TEAMS_WEBHOOK_URL"
    url = os.environ.get(secret)
    if not url:
        print(f"ERROR: {secret} is not set - add it as a GitHub secret.", file=sys.stderr)
        return 1
    payload = json.loads((OUT / "teams_payload.json").read_text())
    gameweek = int((OUT / "gameweek.txt").read_text())
    data = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        if resp.status >= 300:
            raise RuntimeError(f"Teams returned HTTP {resp.status}")
    if args.test:
        print(f"Posted gameweek {gameweek} to the TEST chat.")
        return 0
    STATE_FILE.parent.mkdir(exist_ok=True)
    STATE_FILE.write_text(f"{max(gameweek, last_posted())}\n")
    print(f"Posted gameweek {gameweek} to Teams.")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Weekly FPL roundup for Teams")
    sub = ap.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build", help="build the report, card and web page")
    b.add_argument("--gameweek", type=int, help="gameweek to report on (default: latest finished)")
    b.add_argument("--only-if-new", action="store_true",
                   help="do nothing unless a newer gameweek has finished since the last post")
    b.add_argument("--config", default=str(ROOT / "config.json"))
    p = sub.add_parser("post", help="post the built card to Teams")
    p.add_argument("--test", action="store_true", help="post to the test chat (TEAMS_TEST_WEBHOOK_URL)")
    args = ap.parse_args(argv)
    return build(args) if args.command == "build" else post(args)


if __name__ == "__main__":
    sys.exit(main())

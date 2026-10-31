"""Command line entry point.

    python -m fpl_weekly                  # preview the latest finished gameweek
    python -m fpl_weekly --gameweek 9     # preview a specific gameweek
    python -m fpl_weekly --post           # post to Teams (needs TEAMS_WEBHOOK_URL)
    python -m fpl_weekly --post --only-if-new   # what the daily schedule runs
"""

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

from .api import FPLClient
from .render import to_markdown, to_teams_payload
from .stats import build_report, latest_final_gameweek

ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = ROOT / "state" / "last_posted_gameweek.txt"


def last_posted():
    try:
        return int(STATE_FILE.read_text().strip() or 0)
    except (FileNotFoundError, ValueError):
        return 0


def post_to_teams(payload, url):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        if resp.status >= 300:
            raise RuntimeError(f"Teams returned HTTP {resp.status}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Weekly FPL roundup for Teams")
    ap.add_argument("--gameweek", type=int, help="gameweek to report on (default: latest finished)")
    ap.add_argument("--post", action="store_true", help="post the card to Teams")
    ap.add_argument("--only-if-new", action="store_true",
                    help="do nothing unless a newer gameweek has finished since the last post")
    ap.add_argument("--config", default=str(ROOT / "config.json"))
    ap.add_argument("--out", default=str(ROOT / "out"))
    args = ap.parse_args(argv)

    config = json.loads(Path(args.config).read_text())
    client = FPLClient()

    if args.only_if_new and not args.gameweek:
        latest = latest_final_gameweek(client.bootstrap()["events"])
        if not latest or latest <= last_posted():
            print(f"No new finished gameweek (latest final: {latest}, last posted: {last_posted()}).")
            return 0

    report = build_report(client, config, args.gameweek)
    payload = to_teams_payload(report)
    markdown = to_markdown(report)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "teams_payload.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    (out / "card.json").write_text(json.dumps(payload["attachments"][0]["content"], indent=2,
                                              ensure_ascii=False))
    (out / "report.md").write_text(markdown)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(markdown + "\n")
    print(markdown)

    if args.post:
        url = os.environ.get("TEAMS_WEBHOOK_URL")
        if not url:
            print("ERROR: TEAMS_WEBHOOK_URL is not set - add it as a GitHub secret.", file=sys.stderr)
            return 1
        post_to_teams(payload, url)
        STATE_FILE.parent.mkdir(exist_ok=True)
        STATE_FILE.write_text(f"{max(report.gameweek, last_posted())}\n")
        print(f"Posted gameweek {report.gameweek} to Teams.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

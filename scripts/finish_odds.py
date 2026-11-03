"""Ad hoc: chance a manager finishes in a given position in each league (and in at least one).

    python scripts/finish_odds.py --name Samir --position 2 [--sims 10000]

Method (Monte Carlo):
- Every remaining gameweek, each manager scores a random amount drawn from his own scores so far
  (normal distribution with his mean and spread, never below 0).
- One draw per FPL team per gameweek is shared by the Classic league and both H2H leagues
  (it's the same team), so those leagues move together. Draft and Challenge teams are separate.
- H2H leagues play their real remaining fixtures (3 points win, 1 draw; ties on points split by
  points scored). Classic and Challenge rank by total points.
"""

import argparse
import json
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fpl_weekly.api import CHALLENGE_URL, DRAFT_URL, FPLClient  # noqa: E402
from fpl_weekly.stats import latest_final_gameweek  # noqa: E402

LAST_GW = 38


def first(name):
    return (name or "").strip().split(" ")[0].lower()


def dist(scores):
    scores = [s for s in scores if s is not None]
    if len(scores) < 2:
        return (scores[0] if scores else 50.0), 15.0
    return statistics.mean(scores), max(statistics.pstdev(scores), 5.0)


def draw(rng, d):
    return max(0, round(rng.gauss(*d)))


def rank_of(target, table, key):
    """1-based finishing position of target (ties broken by key, then shared)."""
    ordered = sorted(table, key=key, reverse=True)
    return [e for e, *_ in ordered].index(target) + 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--position", type=int, default=2)
    ap.add_argument("--sims", type=int, default=10000)
    args = ap.parse_args()
    cfg = json.loads((ROOT / "config.json").read_text())
    who = args.name.lower()
    rng = random.Random(42)

    fpl = FPLClient()
    gw = latest_final_gameweek(fpl.bootstrap()["events"], fpl)
    left = list(range(gw + 1, LAST_GW + 1))
    print(f"Simulating gameweeks {left[0]}-{left[-1]} ({len(left)} left), {args.sims:,} seasons, "
          f"target: {args.name} finishing position {args.position}\n")

    # ---- main FPL game: classic + H2H share the same weekly scores -------------
    _lg, standings = fpl.classic_standings(cfg["classic_league_id"])
    names = {r["entry"]: r["player_name"] for r in standings}
    hist = {}
    for e in list(names):
        hist[e] = {h["event"]: h for h in fpl.entry_history(e).get("current", []) if h["event"] <= gw}
    h2h = []
    for lg in cfg.get("h2h_leagues", []):
        _l, table = fpl.h2h_standings(lg["id"])
        for r in table:
            if r["entry"] not in hist:
                names[r["entry"]] = r["player_name"]
                hist[r["entry"]] = {h["event"]: h for h in fpl.entry_history(r["entry"]).get("current", [])
                                    if h["event"] <= gw}
        h2h.append((lg.get("label"), fpl.h2h_matches(lg["id"])))
    fpl_dist = {e: dist([h["points"] - h["event_transfers_cost"] for h in hs.values()]) for e, hs in hist.items()}
    target_fpl = [e for e, n in names.items() if first(n) == who or n.lower() == who]

    # ---- challenge ------------------------------------------------------------------
    ch_client = FPLClient(CHALLENGE_URL)
    ch = next(l for l in cfg.get("extra_leagues", []) if l["game"] == "challenge")
    _l, ch_rows = ch_client.classic_standings(ch["id"])
    ch_hist = {r["entry"]: {h["event"]: h for h in ch_client.entry_history(r["entry"]).get("current", [])
                            if h["event"] <= gw and h.get("rank")} for r in ch_rows}
    ch_names = {r["entry"]: r["player_name"] for r in ch_rows}
    ch_total = {e: max(hs.values(), key=lambda h: h["event"])["total_points"] if hs else 0 for e, hs in ch_hist.items()}
    ch_dist = {e: dist([h["points"] for h in hs.values()]) for e, hs in ch_hist.items()}

    # ---- draft ------------------------------------------------------------------------
    dr_client = FPLClient(DRAFT_URL)
    dr = next(l for l in cfg.get("extra_leagues", []) if l["game"] == "draft" and l.get("id"))
    dd = dr_client.draft_league(dr["id"])
    dr_names = {e["id"]: f"{e.get('player_first_name', '')} {e.get('player_last_name', '')}" for e in dd["league_entries"]}
    dr_matches = dd.get("matches", [])
    dr_scores = defaultdict(list)
    for m in dr_matches:
        if m.get("finished") and m["event"] <= gw:
            dr_scores[m["league_entry_1"]].append(m["league_entry_1_points"])
            dr_scores[m["league_entry_2"]].append(m["league_entry_2_points"])
    dr_dist = {e: dist(s) for e, s in dr_scores.items()}

    def h2h_base(matches, upto):
        pts, pf = defaultdict(int), defaultdict(int)
        for m in matches:
            if m["event"] > upto or m.get("is_knockout"):
                continue
            for a, b in (("1", "2"), ("2", "1")):
                e = m[f"entry_{a}_entry"]
                if e is None:
                    continue
                x, y = m[f"entry_{a}_points"], m[f"entry_{b}_points"]
                pf[e] += x
                pts[e] += 3 if x > y else 1 if x == y else 0
        return pts, pf

    base_h2h = [(label, h2h_base(m, gw), [x for x in m if x["event"] > gw and not x.get("is_knockout")])
                for label, m in h2h]
    for label, _b, future in base_h2h:
        print(f"{label}: {len(future)} remaining fixtures found")

    dr_pts, dr_pf = defaultdict(int), defaultdict(int)
    for m in dr_matches:
        if m.get("finished") and m["event"] <= gw:
            a, b = m["league_entry_1"], m["league_entry_2"]
            x, y = m["league_entry_1_points"], m["league_entry_2_points"]
            dr_pf[a] += x; dr_pf[b] += y
            dr_pts[a] += 3 if x > y else 1 if x == y else 0
            dr_pts[b] += 3 if y > x else 1 if x == y else 0
    dr_future = [m for m in dr_matches if m["event"] > gw]
    print(f"FPL Draft: {len(dr_future)} remaining fixtures found\n")

    classic_members = [r["entry"] for r in standings]
    classic_total = {e: max(hist[e].values(), key=lambda h: h["event"])["total_points"] if hist[e] else 0
                     for e in classic_members}
    target_ch = [e for e, n in ch_names.items() if first(n) == who]
    target_dr = [e for e, n in dr_names.items() if first(n) == who]

    labels = ["Classic"] + [l for l, *_ in base_h2h] + ["FPL Challenge", "FPL Draft"]
    hits = defaultdict(int)
    any_hit = 0
    pos = args.position
    for _ in range(args.sims):
        got = {}
        weekly = {e: {g: draw(rng, fpl_dist[e]) for g in left} for e in fpl_dist}
        # classic
        if target_fpl and target_fpl[0] in classic_members:
            t = [(e, classic_total[e] + sum(weekly[e].values())) for e in classic_members]
            got["Classic"] = rank_of(target_fpl[0], t, key=lambda x: x[1]) == pos
        # H2H
        for label, (pts0, pf0), future in base_h2h:
            pts, pf = defaultdict(int, pts0), defaultdict(int, pf0)
            for m in future:
                a, b = m["entry_1_entry"], m["entry_2_entry"]
                x = weekly[a][m["event"]] if a in weekly else 0
                y = weekly[b][m["event"]] if b in weekly else round(statistics.mean(
                    weekly[e][m["event"]] for e in weekly))  # "league average" opponent
                if a is not None:
                    pf[a] += x; pts[a] += 3 if x > y else 1 if x == y else 0
                if b is not None:
                    pf[b] += y; pts[b] += 3 if y > x else 1 if x == y else 0
            if target_fpl and target_fpl[0] in pts:
                t = [(e, pts[e], pf[e]) for e in pts]
                got[label] = rank_of(target_fpl[0], t, key=lambda x: (x[1], x[2])) == pos
        # challenge
        if target_ch:
            t = [(e, ch_total[e] + sum(draw(rng, ch_dist[e]) for _g in left)) for e in ch_total]
            got["FPL Challenge"] = rank_of(target_ch[0], t, key=lambda x: x[1]) == pos
        # draft
        if target_dr:
            pts, pf = defaultdict(int, dr_pts), defaultdict(int, dr_pf)
            wk = {e: {g: draw(rng, dr_dist[e]) for g in left} for e in dr_dist}
            for m in dr_future:
                a, b = m["league_entry_1"], m["league_entry_2"]
                x, y = wk[a][m["event"]], wk[b][m["event"]]
                pf[a] += x; pf[b] += y
                pts[a] += 3 if x > y else 1 if x == y else 0
                pts[b] += 3 if y > x else 1 if x == y else 0
            t = [(e, pts[e], pf[e]) for e in dr_dist]
            got["FPL Draft"] = rank_of(target_dr[0], t, key=lambda x: (x[1], x[2])) == pos
        for k, v in got.items():
            hits[k] += v
        any_hit += any(got.values())

    print(f"RESULT: chance {args.name} finishes position {pos}:")
    for k in labels:
        if k in hits or k in ("Classic",):
            print(f"  {k:<16} {hits[k] / args.sims * 100:5.1f}%")
    print(f"  {'AT LEAST ONE':<16} {any_hit / args.sims * 100:5.1f}%")


if __name__ == "__main__":
    main()

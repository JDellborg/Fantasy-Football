"""Season-long features for the web page: Manager of the Month and title odds."""

import random
import statistics

SIMULATIONS = 20000


def manager_of_the_month(builder, Section, Table):
    """Leaderboard for the FPL 'month' (phase) the gameweek belongs to, plus past winners."""
    gw = builder.gw
    phases = [p for p in builder.phases if p.get("name") != "Overall" and p.get("start_event")]
    current = next((p for p in phases if p["start_event"] <= gw <= p["stop_event"]), None)
    if not current:
        return None

    def totals(phase, upto):
        weeks = range(phase["start_event"], min(phase["stop_event"], upto) + 1)
        return {m.entry: sum(m.net(g) or 0 for g in weeks) for m in builder.active
                if any(g in m.history for g in weeks)}

    now = totals(current, gw)
    ordered = sorted(now.items(), key=lambda kv: -kv[1])
    s = Section("Manager of the Month")
    done = gw == current["stop_event"]
    span = (f"GW{current['start_event']}" if gw == current["start_event"]
            else f"GW{current['start_event']}-{min(gw, current['stop_event'])}")
    leader = builder.by_entry[ordered[0][0]].name
    s.paragraphs.append(
        f"{leader} {'wins' if done else 'leads'} {current['name']} ({span}) with {ordered[0][1]} points."
        + ("" if done else f" The month runs to GW{current['stop_event']}."))
    s.table = Table(["Pos", "Manager", "Pts"],
                    [[str(i), builder.by_entry[e].name, str(p)] for i, (e, p) in enumerate(ordered[:5], 1)],
                    align=["left", "left", "right"], widths=["auto", "stretch", "auto"])

    past = []
    for p in phases:
        if p["stop_event"] < gw or (p is current and done):
            t = totals(p, p["stop_event"])
            if t:
                best = max(t.values())
                winners = [builder.by_entry[e].name for e, v in t.items() if v == best]
                past.append(f"{p['name']}: {' and '.join(winners)} ({best})")
    if past:
        s.paragraphs.append("Previous winners: " + "; ".join(past) + ".")
    return s


def title_odds(builder, Section, Table):
    """Chance of winning the classic league, by simulating the rest of the season.

    Each manager's remaining points are drawn from their own season average and spread.
    (The sum of n weekly scores is approximated by one normal draw per manager per run.)
    """
    gw = builder.gw
    left = 38 - gw
    if left <= 0 or gw < 3:
        return None
    managers = []
    for m in builder.active:
        scores = [m.net(g) for g in range(1, gw + 1) if g in m.history]
        if len(scores) < 3:
            continue
        managers.append((m, m.history[gw]["total_points"], statistics.mean(scores),
                         statistics.pstdev(scores)))
    if len(managers) < 3:
        return None
    rng = random.Random(f"odds-{builder.config['classic_league_id']}-{gw}")
    wins = {m.entry: 0.0 for m, *_ in managers}
    for _ in range(SIMULATIONS):
        finals = [(m.entry, total + rng.gauss(mean * left, sd * left ** 0.5))
                  for m, total, mean, sd in managers]
        top = max(f for _e, f in finals)
        winners = [e for e, f in finals if f == top]
        for e in winners:
            wins[e] += 1 / len(winners)
    odds = sorted(((wins[m.entry] / SIMULATIONS * 100, m, total) for m, total, *_ in managers),
                  key=lambda x: -x[0])

    def pct(p):
        return "<1%" if 0 < p < 1 else f"{p:.0f}%"
    rows = [[m.name, str(total), pct(p)] for p, m, total in odds if p >= 0.5][:6]
    rest = sum(1 for p, *_ in odds if p < 0.5)
    top3 = [(m.name, p) for p, m, _t in odds[:3] if p >= 0.5]
    if top3:
        builder.key_facts.append(["Title Odds", " · ".join(f"{n} {pct(p)}" for n, p in top3)])
    s = Section("Title odds")
    lead_p, lead_m, _ = odds[0]
    s.paragraphs.append(
        f"{lead_m.name} has a {pct(lead_p)} chance of winning the classic league, based on "
        f"{SIMULATIONS:,} simulations of the remaining {left} gameweeks using each manager's scoring so far."
        + (f" The other {rest} managers are below 1%." if rest else ""))
    s.table = Table(["Manager", "Pts", "Chance"], rows,
                    align=["left", "right", "right"], widths=["stretch", "auto", "auto"])
    return s


# --- What if? -----------------------------------------------------------------------
# How every manager would be doing if they had kept the first team they picked:
# no transfers, no chips, same captain and bench order, FPL's automatic substitution rules.

import json
from pathlib import Path

GKP, DEF, MID, FWD = 1, 2, 3, 4
MIN_IN_XI = {DEF: 3, MID: 2, FWD: 1}


def _cached(builder, name, fetch, keep=True):
    """Store unchanging data (past gameweeks) in state/cache so each run fetches less."""
    cache_dir = builder.cache_dir
    path = Path(cache_dir) / name if cache_dir else None
    if path and path.exists():
        return json.loads(path.read_text())
    data = fetch()
    if path and keep and data is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, separators=(",", ":")))
    return data


def _live_points(builder, gw):
    """{element_id: [points, minutes]} for one gameweek."""
    ev = builder.events.get(gw, {})
    final = bool(ev.get("finished") and ev.get("data_checked"))

    def fetch():
        return {str(el["id"]): [el["stats"].get("total_points", 0), el["stats"].get("minutes", 0)]
                for el in builder.client.live(gw)["elements"]}
    return _cached(builder, f"live_{gw}.json", fetch, keep=final)


def _first_team(builder, m):
    first_gw = min(m.history)

    def fetch():
        picks = builder.client.picks(m.entry, first_gw)
        if not picks:
            return None
        return {"event": first_gw,
                "picks": [[p["element"], p["position"], bool(p.get("is_captain")),
                           bool(p.get("is_vice_captain"))] for p in picks.get("picks", [])]}
    return _cached(builder, f"first_team_{m.entry}.json", fetch)


def _etype(builder, element, position):
    p = builder.players.get(element, {})
    if "element_type" in p:
        return p["element_type"]
    return GKP if position in (1, 12) else MID


def score_fixed_team(builder, team, live):
    """Points for an untouched team in one gameweek, with FPL-style automatic subs."""
    picks = sorted(team["picks"], key=lambda p: p[1])
    xi = [p for p in picks if p[1] <= 11]
    bench = [p for p in picks if p[1] > 11]
    played = lambda p: live.get(str(p[0]), [0, 0])[1] > 0
    etype = lambda p: _etype(builder, p[0], p[1])

    # goalkeeper swap
    for i, p in enumerate(xi):
        if etype(p) == GKP and not played(p):
            sub = next((b for b in bench if etype(b) == GKP and played(b)), None)
            if sub:
                xi[i] = sub
                bench.remove(sub)
    # outfield subs in bench order, keeping a valid formation
    for i, p in enumerate(list(xi)):
        if etype(p) == GKP or played(p):
            continue
        for b in [b for b in bench if etype(b) != GKP]:
            if not played(b):
                continue
            trial = xi[:i] + [b] + xi[i + 1:]
            counts = {t: sum(1 for q in trial if etype(q) == t) for t in MIN_IN_XI}
            if all(counts[t] >= n for t, n in MIN_IN_XI.items()):
                xi[i] = b
                bench.remove(b)
                break

    points = sum(live.get(str(p[0]), [0, 0])[0] for p in xi)
    captain = next((p for p in picks if p[2]), None)
    vice = next((p for p in picks if p[3]), None)
    on_pitch = {p[0] for p in xi}
    for armband in (captain, vice):
        if armband and armband[0] in on_pitch and played(armband):
            points += live.get(str(armband[0]), [0, 0])[0]  # double points
            break
    return points


def what_if(builder, Section, Table):
    gw = builder.gw
    results = []
    lives = {}
    for m in builder.active:
        team = _first_team(builder, m)
        if not team:
            continue
        total = 0
        for g in range(team["event"], gw + 1):
            if g not in lives:
                lives[g] = _live_points(builder, g)
            total += score_fixed_team(builder, team, lives[g])
        actual = m.history[gw]["total_points"]
        results.append((m, total, actual, actual - total, team["event"]))
    if len(results) < 3:
        return None
    builder.what_if_results = results
    by_whatif = sorted(results, key=lambda r: -r[1])
    best_mover = max(results, key=lambda r: r[3])
    worst_mover = min(results, key=lambda r: r[3])
    better_off = sum(1 for r in results if r[3] < 0)

    s = Section("What if?")
    leader = by_whatif[0]
    text = (f"If everyone had kept their Gameweek 1 team all season (no transfers, no chips), "
            f"{leader[0].name} would lead the league with {leader[1]} points. ")
    if best_mover[3] > 0:
        text += f"{best_mover[0].name} has gained the most from their changes ({best_mover[3]:+d}). "
    if worst_mover[3] < 0:
        text += (f"{worst_mover[0].name} would be {-worst_mover[3]} points better off "
                 f"if they had never changed their Gameweek 1 team. ")
    if better_off:
        text += (f"In total, {better_off} of {len(results)} managers would be better off with their "
                 f"Gameweek 1 team.")
    s.paragraphs.append(text.strip())
    rows = [[str(i), r[0].name, str(r[1]), str(r[2]), f"{r[3]:+d}"]
            for i, r in enumerate(by_whatif[:6], 1)]
    s.table = Table(["Pos", "Manager", "What if", "Actual", "Gain"], rows,
                    align=["left", "left", "right", "right", "right"],
                    widths=["auto", "stretch", "auto", "auto", "auto"])
    s.full_table = Table(["Pos", "Manager", "What if", "Actual", "Gain"],
                         [[str(i), r[0].name, str(r[1]), str(r[2]), f"{r[3]:+d}"]
                          for i, r in enumerate(by_whatif, 1)],
                         align=["left", "left", "right", "right", "right"])
    late = [r[0].name for r in results if r[4] > 1]
    note = ("What if = points their Gameweek 1 team would have scored, untouched. Gain = points won (or lost) "
            "by every transfer and chip since Gameweek 1. Estimate: uses FPL's automatic substitution rules; "
            "transfer hits are included in Actual.")
    if late:
        note += f" Joined after Gameweek 1, so judged on their first team: {', '.join(late)}."
    s.paragraphs.append(note)
    s.web_only = True
    return s

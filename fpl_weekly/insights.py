"""Deeper, less obvious stats ("the numbers behind the numbers").

Each insight has:
    priority  - how interesting it is this week (higher = shown first / used on the card)
    stat      - the big number shown on the web page
    label     - a short title
    text      - one or two plain sentences explaining it
"""

import statistics
from collections import defaultdict
from dataclasses import dataclass


@dataclass
class Insight:
    priority: float
    stat: str
    label: str
    text: str
    kind: str = ""       # only the strongest insight of each kind is shown


def _signed(x):
    return f"+{x:.1f}" if x >= 0 else f"{x:.1f}"


def h2h_luck(builder):
    """Compare actual H2H points with what each manager 'should' have, if they had
    played every other manager every week (the all-play method)."""
    out = []
    gw = builder.gw
    for lg, league, _table, matches in builder.h2h:
        label = lg.get("label") or league.get("name")
        by_event = defaultdict(dict)
        for mt in matches:
            if mt["event"] > gw or mt.get("is_knockout"):
                continue
            for side in ("1", "2"):
                e = mt[f"entry_{side}_entry"]
                if e is not None:
                    by_event[mt["event"]][e] = mt[f"entry_{side}_points"]
        expected = defaultdict(float)
        for scores in by_event.values():
            n = len(scores)
            if n < 3:
                continue
            for e, pts in scores.items():
                lower = sum(1 for o, p in scores.items() if o != e and p < pts)
                equal = sum(1 for o, p in scores.items() if o != e and p == pts)
                expected[e] += (3 * lower + equal) / (n - 1)
        rows, _ranks = builder.h2h_table(matches, gw)
        luck = {e: rows[e]["pts"] - expected[e] for e in expected if e in rows}
        if len(luck) < 4:
            continue
        lucky = max(luck, key=luck.get)
        unlucky = min(luck, key=luck.get)
        name = builder.names.get
        if luck[lucky] >= 3:
            out.append(Insight(
                5 + luck[lucky] / 2, _signed(luck[lucky]), f"Luckiest in the {label}",
                f"{name(lucky, '?')} has {rows[lucky]['pts']} H2H points. Playing every manager every "
                f"week, his scores would have earned about {expected[lucky]:.0f}. "
                f"The fixture list has been kind.", "luck+"))
        if luck[unlucky] <= -3:
            out.append(Insight(
                5 + -luck[unlucky] / 2, _signed(luck[unlucky]), f"Unluckiest in the {label}",
                f"{name(unlucky, '?')} has {rows[unlucky]['pts']} H2H points. Playing every manager every "
                f"week, his scores would have earned about {expected[unlucky]:.0f}. "
                f"His opponents keep having big weeks.", "luck-"))
    return out


def captain_points_missed(builder):
    """Points lost this week by not captaining the best player in each manager's own XI."""
    missed = {}
    for m in builder.active:
        cap = builder.caps.get(m.entry)
        xi = builder.xis.get(m.entry)
        if not cap or not xi:
            continue
        mult = 3 if (m.picks or {}).get("active_chip") == "3xc" else 2
        best = max(xi, key=builder.pts)
        missed[m.entry] = (builder.pts(best) * mult - cap[1], best)
    if len(missed) < 3:
        return []
    total = sum(v[0] for v in missed.values())
    worst = max(missed, key=lambda e: missed[e][0])
    perfect = [e for e, v in missed.items() if v[0] == 0]
    loss, best = missed[worst]
    text = (f"Across the league, {total} points were left behind by captaining the wrong player. "
            f"{builder.names[worst]} would have gained {loss} by giving the armband to {builder.pname(best)}.")
    if perfect:
        text += f" Only {len(perfect)} of {len(missed)} picked their best captain."
    return [Insight(3 + loss / 6, str(total), "Captain points left behind", text)]


def consistency(builder):
    gw = builder.gw
    spread = {}
    for m in builder.active:
        scores = [m.net(g) for g in range(1, gw + 1) if g in m.history]
        if len(scores) >= 4:
            spread[m.entry] = (statistics.pstdev(scores), statistics.mean(scores))
    if len(spread) < 4:
        return []
    steady = min(spread, key=lambda e: spread[e][0])
    wild = max(spread, key=lambda e: spread[e][0])
    by = builder.by_entry
    return [
        Insight(2.5, f"±{spread[wild][0]:.0f}", "Boom or bust",
                f"{by[wild].name} has the most unpredictable scores in the league, usually landing "
                f"within {spread[wild][0]:.0f} points either side of his average of {spread[wild][1]:.0f}."),
        Insight(2, f"±{spread[steady][0]:.0f}", "Most consistent",
                f"{by[steady].name} rarely has a bad week (or a great one): typically within "
                f"{spread[steady][0]:.0f} points of his average of {spread[steady][1]:.0f}."),
    ]


def catch_up(builder):
    """How many extra points per week each chaser needs to catch the leader by GW38."""
    gw = builder.gw
    left = 38 - gw
    if left <= 0:
        return []
    ordered = sorted(builder.active, key=lambda m: -m.history[gw]["total_points"])
    if len(ordered) < 4:
        return []
    leader = ordered[0]
    lead_pts = leader.history[gw]["total_points"]
    last = ordered[-1]
    gap_last = lead_pts - last.history[gw]["total_points"]
    second = ordered[1]
    gap2 = lead_pts - second.history[gw]["total_points"]
    return [Insight(
        2.2, f"{gap_last / left:.1f}", "Points per week to catch the leader",
        f"With {left} gameweeks left, {last.name} (last) needs to outscore {leader.name} by "
        f"{gap_last / left:.1f} points every week to finish top. "
        + (f"{second.name} is level on points with the leader." if gap2 == 0 else
           f"{second.name}, in second, needs just {gap2 / left:.1f} a week."))]


def squad_uniqueness(builder):
    squads = builder.squads
    if len(squads) < 5:
        return []
    from collections import Counter
    owners = Counter(el for sq in squads.values() for el in sq)
    avg = {e: sum(owners[el] for el in sq) / len(sq) for e, sq in squads.items()}
    unique = min(avg, key=avg.get)
    template = max(avg, key=avg.get)
    n = len(squads)
    return [Insight(
        1.8, f"{avg[unique]:.1f}", "Most unique squad",
        f"Each player in {builder.names[unique]}'s squad is owned by {avg[unique]:.1f} of the league's "
        f"{n} managers on average, the lowest overlap in the league. {builder.names[template]} has the "
        f"most 'template' squad ({avg[template]:.1f}).")]


def season_bench(builder):
    gw = builder.gw
    benched = {m.entry: sum(r.get("points_on_bench", 0) for g, r in m.history.items() if g <= gw)
               for m in builder.active}
    if not benched:
        return []
    e = max(benched, key=benched.get)
    avg = sum(benched.values()) / len(benched)
    return [Insight(
        1.5, str(benched[e]), "Points benched this season",
        f"{builder.names[e]} has left {benched[e]} points on the bench this season, against a league "
        f"average of {avg:.0f}. That's roughly {benched[e] / gw:.1f} points a week.")]


def world_rank(builder):
    gw = builder.gw
    total = builder.total_players
    ranked = [m for m in builder.active if m.history[gw].get("overall_rank")]
    if not total or not ranked:
        return []
    best = min(ranked, key=lambda m: m.history[gw]["overall_rank"])
    pct = best.history[gw]["overall_rank"] / total * 100
    above = sum(1 for m in ranked if m.history[gw]["overall_rank"] / total <= 0.10)
    text = (f"{best.name} is ranked {best.history[gw]['overall_rank']:,} of {total:,} players worldwide, "
            f"in the top {pct:.1f}%.")
    if above > 1:
        text += f" {above} managers in the league are in the global top 10%."
    return [Insight(1.2 + (2 if pct < 1 else 0), f"Top {pct:.1f}%", "Best in the world", text)]


def what_if_insight(builder):
    results = builder.what_if_results
    if not results:
        return []
    m, whatif, actual, gain, first = min(results, key=lambda r: r[3])
    if gain > -30:
        return []
    return [Insight(3 + -gain / 20, f"{gain:+d}", "Should have stuck",
                    f"{m.name} would have {whatif} points if he had kept his GW{first} team untouched, "
                    f"{-gain} more than he actually has ({actual}).", "whatif")]


def build_insights(builder):
    items = []
    for fn in (what_if_insight, h2h_luck, captain_points_missed, consistency, catch_up, squad_uniqueness,
               season_bench, world_rank):
        try:
            items += fn(builder)
        except Exception as e:  # an insight failing should never stop the update
            print(f"WARNING: insight {fn.__name__} failed: {e}")
    best = {}
    for i in sorted(items, key=lambda i: -i.priority):
        best.setdefault(i.kind or i.label, i)
    return list(best.values())

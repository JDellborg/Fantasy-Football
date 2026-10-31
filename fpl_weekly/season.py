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
    s = Section("Title odds")
    lead_p, lead_m, _ = odds[0]
    s.paragraphs.append(
        f"{lead_m.name} has a {pct(lead_p)} chance of winning the classic league, based on "
        f"{SIMULATIONS:,} simulations of the remaining {left} gameweeks using each manager's scoring so far."
        + (f" The other {rest} managers are below 1%." if rest else ""))
    s.table = Table(["Manager", "Pts", "Chance"], rows,
                    align=["left", "right", "right"], widths=["stretch", "auto", "auto"])
    return s

"""Crunches FPL data into a short, factual weekly report (renderer-agnostic)."""

from collections import Counter, defaultdict
from dataclasses import dataclass, field

CHIP_NAMES = {
    "wildcard": "a Wildcard",
    "freehit": "a Free Hit",
    "bboost": "a Bench Boost",
    "3xc": "a Triple Captain",
    "manager": "the Assistant Manager chip",
}
FORM_WEEKS = 4
CLASSIC_TOP = 5          # rows shown at the top of the classic table
CLASSIC_BOTTOM = 2       # rows shown at the bottom (if the league is bigger)
MAX_NOTES = 5            # bullet points in "Also this week"
NUMBER_WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]


@dataclass
class Table:
    headers: list                    # None = no header row (label/value list)
    rows: list                       # list of lists of cell text
    align: list = None               # "left" / "center" / "right" per column
    widths: list = None              # "auto" / "stretch" per column


@dataclass
class Section:
    title: str
    paragraphs: list = field(default_factory=list)
    table: Table = None
    bullets: list = field(default_factory=list)


@dataclass
class Report:
    headline: str
    standfirst: str
    gameweek: int
    league_name: str
    sections: list


@dataclass
class Manager:
    entry: int
    team: str
    player: str
    name: str = ""
    history: dict = field(default_factory=dict)
    picks: dict = None
    transfers: list = field(default_factory=list)

    def net(self, gw):
        row = self.history.get(gw)
        return None if row is None else row["points"] - row["event_transfers_cost"]


@dataclass
class Story:
    """A candidate for the headline. Higher weight = more newsworthy."""
    weight: float
    headline: str
    clause: str = None               # shorter version for "... as <clause>"
    subject: str = None              # who it's about
    topic: str = None                # which league/feature it's about


# --- small helpers ---------------------------------------------------------

def latest_final_gameweek(events):
    done = [e["id"] for e in events if e.get("finished") and e.get("data_checked")]
    return max(done) if done else None


def join_names(names):
    names = list(names)
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


def words(n):
    return NUMBER_WORDS[n] if 0 <= n < len(NUMBER_WORDS) else str(n)


def ordinal(n):
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def movement(move):
    if not move:
        return "-"
    return f"▲{move}" if move > 0 else f"▼{-move}"


def plural(n, one, many=None):
    return one if n == 1 else (many or one + "s")


def competition_rank(items, key):
    """items -> {item_id: rank}; ties share a rank (1, 2, 2, 4)."""
    ordered = sorted(items, key=key)
    ranks, prev, prev_rank = {}, object(), 0
    for i, item in enumerate(ordered, start=1):
        k = key(item)
        if k != prev:
            prev_rank, prev = i, k
        ranks[item[0]] = prev_rank
    return ranks


def make_display_names(player_names, nicknames):
    """First names, unless two people share one (then full names)."""
    firsts = Counter(n.split()[0] for n in player_names.values() if n.strip())
    out = {}
    for entry, full in player_names.items():
        first = full.split()[0] if full.strip() else full
        out[entry] = nicknames.get(str(entry)) or (first if firsts[first] == 1 else full)
    return out


# --- the report ----------------------------------------------------------------

class ReportBuilder:
    def __init__(self, client, config, gameweek=None):
        self.client = client
        self.config = config
        boot = client.bootstrap()
        self.events = {e["id"]: e for e in boot["events"]}
        self.gw = gameweek or latest_final_gameweek(boot["events"])
        if not self.gw:
            raise SystemExit("No finished gameweek yet - nothing to report.")
        self.players = {p["id"]: p for p in boot["elements"]}
        self.stories = []
        self.notes = []          # (priority, text) for "Also this week"

    def pname(self, element_id):
        p = self.players.get(element_id)
        return p["web_name"] if p else f"Player {element_id}"

    def pts(self, element_id):
        return self.live.get(element_id, {}).get("total_points", 0)

    def mins(self, element_id):
        return self.live.get(element_id, {}).get("minutes", 0)

    def note(self, priority, text):
        self.notes.append((priority, text))

    # -- data loading --
    def load(self):
        cfg = self.config
        self.league, standings = self.client.classic_standings(cfg["classic_league_id"])
        self.managers = [Manager(r["entry"], r["entry_name"], r["player_name"]) for r in standings]

        self.h2h = []
        for lg in cfg.get("h2h_leagues", []):
            league, table = self.client.h2h_standings(lg["id"])
            matches = self.client.h2h_matches(lg["id"])
            self.h2h.append((lg, league, table, matches))

        player_names = {m.entry: m.player for m in self.managers}
        for _lg, _league, table, _matches in self.h2h:
            for r in table:
                player_names.setdefault(r["entry"], r["player_name"])
        self.names = make_display_names(player_names, cfg.get("nicknames", {}))
        for m in self.managers:
            m.name = self.names[m.entry]

        gw = self.gw
        for m in self.managers:
            m.history = {row["event"]: row for row in self.client.entry_history(m.entry).get("current", [])}
        self.active = [m for m in self.managers if gw in m.history]
        if not self.active:
            raise SystemExit(f"Nobody in the league has a score for gameweek {gw}.")
        self.by_entry = {m.entry: m for m in self.managers}

        self.live = {el["id"]: el["stats"] for el in self.client.live(gw)["elements"]}
        for m in self.active:
            m.picks = self.client.picks(m.entry, gw)
            if m.history[gw].get("event_transfers"):
                m.transfers = [t for t in self.client.transfers(m.entry) if t["event"] == gw]

    # -- build --
    def build(self):
        self.load()
        gw = self.gw
        scores = {m.entry: m.net(gw) for m in self.active}
        self.top = max(scores.values())
        self.bottom = min(scores.values())
        self.best = [m for m in self.active if scores[m.entry] == self.top]
        self.worst = [m for m in self.active if scores[m.entry] == self.bottom]
        self.league_avg = round(sum(scores.values()) / len(scores), 1)

        sections = [self.week_section(), self.classic_section()]
        sections += [self.h2h_section(*h) for h in self.h2h]
        self.collect_notes()
        sections.append(self.notes_section())
        sections = [s for s in sections if s and (s.paragraphs or s.table or s.bullets)]

        return Report(
            headline=self.headline(),
            standfirst=self.standfirst(),
            gameweek=gw,
            league_name=self.config.get("title") or self.league["name"],
            sections=sections,
        )

    # -- headline --
    def headline(self):
        stories = sorted(self.stories, key=lambda s: -s.weight)
        if not stories:
            return f"Gameweek {self.gw}: {join_names(m.name for m in self.best)} top the scoring"
        main = stories[0].headline
        first = stories[0]
        for other in stories[1:]:
            if not other.clause or len(main) + len(other.clause) + 4 > 75:
                continue
            if other.subject and other.subject in (first.subject or ""):
                continue
            if first.subject and first.subject in (other.subject or ""):
                continue
            if other.topic and other.topic == first.topic:
                continue
            return f"{main} as {other.clause}"
        return main

    def standfirst(self):
        gw = self.gw
        best = join_names(m.name for m in self.best)
        verb = "were" if len(self.best) > 1 else "was"
        text = (f"{best} {verb} the top scorer{'s' if len(self.best) > 1 else ''} in Gameweek {gw} "
                f"with {self.top} points. The league averaged {self.league_avg}")
        ev = self.events.get(gw, {})
        if ev.get("average_entry_score") is not None:
            text += f", against an overall FPL average of {ev['average_entry_score']}"
        text += "."
        if getattr(self, "leader_sentence", None):
            text += " " + self.leader_sentence
        return text

    # -- sections --
    def week_section(self):
        gw = self.gw
        s = Section(f"Gameweek {gw} in numbers")
        rows = [
            ["Manager of the Week", f"{join_names(m.name for m in self.best)} ({self.top})"],
            ["Lowest score", f"{join_names(m.name for m in self.worst)} ({self.bottom})"],
            ["League average", f"{self.league_avg}"],
        ]
        caps = {m.entry: self.captain_of(m) for m in self.active}
        self.caps = {e: c for e, c in caps.items() if c}
        if self.caps:
            fav, n = Counter(c[3] for c in self.caps.values()).most_common(1)[0]
            fp = self.pts(fav)
            rows.append(["Most captained", f"{self.pname(fav)}, {n} of {len(self.caps)} "
                                           f"({fp} {plural(fp, 'pt', 'pts')})"])
        s.table = Table(None, rows, widths=["auto", "stretch"])

        avg = self.league_avg
        if self.top >= max(avg + 20, 75):
            self.stories.append(Story(55 + self.top - avg,
                                      f"{self.best[0].name} hits {self.top} to top Gameweek {gw}",
                                      f"{self.best[0].name} scores {self.top}",
                                      self.best[0].name, "week"))
        else:
            self.stories.append(Story(20 + self.top - avg,
                                      f"{self.best[0].name} tops Gameweek {gw} with {self.top}",
                                      f"{self.best[0].name} tops the week with {self.top}",
                                      self.best[0].name, "week"))
        if self.bottom <= min(avg - 20, 30):
            self.stories.append(Story(30 + avg - self.bottom,
                                      f"{self.worst[0].name} held to {self.bottom} in Gameweek {gw}",
                                      f"{self.worst[0].name} manages {self.bottom}",
                                      self.worst[0].name, "week-low"))
        return s

    def classic_section(self):
        gw = self.gw
        now = competition_rank([(m.entry, m.history[gw]["total_points"]) for m in self.active],
                               key=lambda x: -x[1])
        prev_pool = [m for m in self.active if gw - 1 in m.history]
        prev = competition_rank([(m.entry, m.history[gw - 1]["total_points"]) for m in prev_pool],
                                key=lambda x: -x[1]) if prev_pool else {}
        moves = {m.entry: (prev[m.entry] - now[m.entry]) if m.entry in prev else 0 for m in self.active}

        ordered = sorted(self.active, key=lambda m: (now[m.entry], m.name))
        if len(ordered) > CLASSIC_TOP + CLASSIC_BOTTOM + 1:
            shown = ordered[:CLASSIC_TOP] + [None] + ordered[-CLASSIC_BOTTOM:]
        else:
            shown = ordered
        rows = []
        for m in shown:
            if m is None:
                rows.append(["", "…", "", "", ""])
                continue
            rows.append([str(now[m.entry]), m.name, str(m.net(gw)),
                         str(m.history[gw]["total_points"]), movement(moves[m.entry])])
        s = Section(self.league["name"])
        s.table = Table(["Pos", "Manager", "GW", "Total", "+/-"], rows,
                        align=["left", "left", "right", "right", "right"],
                        widths=["auto", "stretch", "auto", "auto", "auto"])

        # leader story
        leader = ordered[0]
        second = ordered[1] if len(ordered) > 1 else None
        gap = leader.history[gw]["total_points"] - (second.history[gw]["total_points"] if second else 0)
        prev_leaders = [e for e, r in prev.items() if r == 1]
        joint = [m for m in ordered if now[m.entry] == 1]
        if len(joint) > 1:
            names = join_names(m.name for m in joint)
            self.leader_sentence = (f"{names} are level at the top of the classic league on "
                                    f"{leader.history[gw]['total_points']} points.")
            self.stories.append(Story(70, f"{names} level at the top of the classic league",
                                      f"{names} share top spot", names, "classic-top"))
        elif second and prev_leaders and leader.entry not in prev_leaders:
            self.leader_sentence = (f"{leader.name} goes top of the classic league, "
                                    f"{gap} {plural(gap, 'point')} ahead of {second.name}.")
            self.stories.append(Story(90, f"{leader.name} goes top of the classic league",
                                      f"{leader.name} goes top", leader.name, "classic-top"))
        elif second:
            self.leader_sentence = (f"{leader.name} stays top of the classic league, "
                                    f"{gap} {plural(gap, 'point')} clear of {second.name}.")
            self.stories.append(Story(15, f"{leader.name} stays top of the classic league",
                                      f"{leader.name} stays top", leader.name, "classic-top"))

        # movers
        up = max(moves.values())
        if up >= 3:
            who = [m for m in self.active if moves[m.entry] == up][0]
            s.paragraphs.append(f"{who.name} made the biggest jump, up {words(up)} places to "
                                f"{ordinal(now[who.entry])}.")
            self.stories.append(Story(35 + up * 2, f"{who.name} climbs {words(up)} places to "
                                      f"{ordinal(now[who.entry])}",
                                      f"{who.name} climbs {words(up)} places", who.name, "classic-move"))
        down = min(moves.values())
        if down <= -3:
            who = [m for m in self.active if moves[m.entry] == down][0]
            s.paragraphs.append(f"{who.name} had the biggest drop, down {words(-down)} places to "
                                f"{ordinal(now[who.entry])}.")
        return s

    def captain_of(self, m):
        picks = (m.picks or {}).get("picks", [])
        cap = next((p for p in picks if p.get("is_captain")), None)
        vice = next((p for p in picks if p.get("is_vice_captain")), None)
        if not cap:
            return None
        mult = 3 if (m.picks or {}).get("active_chip") == "3xc" else 2
        chosen, swapped = cap, False
        if self.mins(cap["element"]) == 0 and vice and self.mins(vice["element"]) > 0:
            chosen, swapped = vice, True
        return chosen["element"], self.pts(chosen["element"]) * mult, swapped, cap["element"]

    # -- head to head --
    def h2h_table(self, matches, upto):
        rows = defaultdict(lambda: {"pts": 0, "w": 0, "d": 0, "l": 0, "pf": 0})
        for mt in matches:
            if mt["event"] > upto or mt.get("is_knockout"):
                continue
            for side, other in (("1", "2"), ("2", "1")):
                e = mt[f"entry_{side}_entry"]
                if e is None:
                    continue
                r = rows[e]
                mine, theirs = mt[f"entry_{side}_points"], mt[f"entry_{other}_points"]
                r["pf"] += mine
                if mine > theirs:
                    r["w"] += 1
                    r["pts"] += 3
                elif mine == theirs:
                    r["d"] += 1
                    r["pts"] += 1
                else:
                    r["l"] += 1
        ranks = competition_rank([(e, r["pts"], r["pf"]) for e, r in rows.items()],
                                 key=lambda x: (-x[1], -x[2]))
        return rows, ranks

    def side_name(self, mt, side):
        e = mt[f"entry_{side}_entry"]
        if e is None:
            return "League average"
        return self.names.get(e) or mt.get(f"entry_{side}_player_name") or mt.get(f"entry_{side}_name")

    def h2h_section(self, lg, league, _table, matches):
        gw = self.gw
        label = lg.get("label") or league.get("name")
        this_week = [mt for mt in matches if mt["event"] == gw]
        if not this_week:
            return None
        s = Section(label)
        _, prev_ranks = self.h2h_table(matches, gw - 1)
        rows, ranks = self.h2h_table(matches, gw)

        results, decided = [], []
        for mt in this_week:
            n1, n2 = self.side_name(mt, "1"), self.side_name(mt, "2")
            p1, p2 = mt["entry_1_points"], mt["entry_2_points"]
            if p1 > p2:
                n1 = f"**{n1}**"
            elif p2 > p1:
                n2 = f"**{n2}**"
            results.append([n1, f"{p1}-{p2}", n2])
            if p1 != p2:
                w, l = ("1", "2") if p1 > p2 else ("2", "1")
                decided.append({
                    "winner": self.side_name(mt, w), "loser": self.side_name(mt, l),
                    "wpts": mt[f"entry_{w}_points"], "lpts": mt[f"entry_{l}_points"],
                    "went": mt[f"entry_{w}_entry"], "lent": mt[f"entry_{l}_entry"],
                    "margin": abs(p1 - p2),
                })
        s.table = Table(["Home", "Score", "Away"], results,
                        align=["right", "center", "left"], widths=["stretch", "auto", "stretch"])

        if ranks:
            ordered = sorted(ranks, key=lambda e: ranks[e])
            leader, r = ordered[0], rows[ordered[0]]
            record = f"W{r['w']} D{r['d']} L{r['l']}" if r["d"] else f"W{r['w']} L{r['l']}"
            sentence = f"{self.names.get(leader, '?')} leads on {r['pts']} points ({record})"
            prev_leaders = [e for e, rk in prev_ranks.items() if rk == 1]
            if prev_leaders and leader not in prev_leaders and gw > 1:
                sentence = f"{self.names.get(leader, '?')} is the new leader on {r['pts']} points ({record})"
                self.stories.append(Story(60, f"{self.names.get(leader, '?')} takes over at the top of the {label}",
                                          f"{self.names.get(leader, '?')} leads the {label}",
                                          self.names.get(leader, '?'), label))
            s.paragraphs.append(sentence + ".")

        upsets = [d for d in decided if d["went"] in prev_ranks and d["lent"] in prev_ranks
                  and prev_ranks[d["went"]] - prev_ranks[d["lent"]] >= 5] if gw > 1 else []
        if upsets:
            u = max(upsets, key=lambda d: prev_ranks[d["went"]] - prev_ranks[d["lent"]])
            wr, lr = prev_ranks[u["went"]], prev_ranks[u["lent"]]
            who = "leader" if lr == 1 else ordinal(lr) + "-placed"
            s.paragraphs.append(f"{u['winner']}, {ordinal(wr)} going into the week, beat {who} "
                                f"{u['loser']} {u['wpts']}-{u['lpts']}.")
            self.stories.append(Story(50 + (wr - lr) * 2,
                                      f"{u['winner']} beats {label} {who} {u['loser']}",
                                      f"{u['winner']} beats {who} {u['loser']}",
                                      f"{u['winner']} {u['loser']}", label))
        elif decided:
            big = max(decided, key=lambda d: d["margin"])
            if big["margin"] >= 15:
                s.paragraphs.append(f"Biggest win: {big['winner']} by {big['margin']} against {big['loser']}.")

        # losing / winning runs
        seqs = defaultdict(list)
        for mt in sorted(matches, key=lambda m: m["event"]):
            if mt["event"] > gw:
                continue
            for side, other in (("1", "2"), ("2", "1")):
                e = mt[f"entry_{side}_entry"]
                if e is not None:
                    a, b = mt[f"entry_{side}_points"], mt[f"entry_{other}_points"]
                    seqs[e].append("W" if a > b else "D" if a == b else "L")

        def run(seq, kind):
            n = 0
            for r in reversed(seq):
                if r != kind:
                    break
                n += 1
            return n
        for kind, word in (("W", "won"), ("L", "lost")):
            runs = {e: run(seq, kind) for e, seq in seqs.items()}
            top = max(runs.values(), default=0)
            if top >= 5:
                who = join_names(self.names.get(e, "?") for e, v in runs.items() if v == top)
                s.paragraphs.append(f"{who} {'have' if ' and ' in who else 'has'} {word} "
                                    f"{words(top)} in a row.")
                if kind == "L":
                    self.stories.append(Story(30 + top * 2,
                                              f"{who}'s losing run in the {label} reaches {words(top)}",
                                              f"{who} loses again", who, label))
        return s

    # -- also this week --
    def collect_notes(self):
        gw = self.gw
        caps = self.caps

        # chips (detail for the first two, the rest grouped into one line)
        chip_users = [m for m in self.active if (m.picks or {}).get("active_chip")]
        if len(chip_users) > 2:
            self.note(8.5, "Chips played: " + join_names(
                f"{m.name} ({CHIP_NAMES.get(m.picks['active_chip'], m.picks['active_chip']).split(' ', 1)[-1]})"
                for m in chip_users) + ".")
            chip_users = []
        for m in chip_users:
            chip = m.picks["active_chip"]
            if chip == "3xc":
                cap = self.captain_of(m)
                if cap:
                    self.note(9, f"{m.name} used a Triple Captain on {self.pname(cap[0])}, "
                                 f"worth {cap[1]} points.")
            elif chip == "bboost":
                bench = sum(self.pts(p["element"]) for p in m.picks["picks"] if p.get("position", 0) > 11)
                self.note(9, f"{m.name} played a Bench Boost; the bench added {bench} "
                             f"{plural(bench, 'point')}.")
            else:
                self.note(8, f"{m.name} played {CHIP_NAMES.get(chip, chip)} and scored {m.net(gw)}.")

        # captains
        if caps:
            best = max(c[1] for c in caps.values())
            worst = min(c[1] for c in caps.values())
            best_e = [e for e, c in caps.items() if c[1] == best]
            worst_e = [e for e, c in caps.items() if c[1] == worst]
            if len(best_e) <= 3:
                self.note(7, f"Best captain pick: {self.pname(caps[best_e[0]][0])} for "
                             f"{join_names(self.names[e] for e in best_e)} ({best} points).")
            if worst < best and len(worst_e) <= 3:
                self.note(6, f"Worst captain pick: {self.pname(caps[worst_e[0]][0])} for "
                             f"{join_names(self.names[e] for e in worst_e)} ({worst} points).")
            if worst <= 0 and len(worst_e) <= 2:
                self.stories.append(Story(40, f"{self.pname(caps[worst_e[0]][0])} captaincy costs "
                                              f"{join_names(self.names[e] for e in worst_e)}",
                                          f"{self.pname(caps[worst_e[0]][0])} lets down "
                                          f"{join_names(self.names[e] for e in worst_e)}",
                                          join_names(self.names[e] for e in worst_e), "captain"))

        # differential
        squads, xis = {}, {}
        for m in self.active:
            picks = (m.picks or {}).get("picks", [])
            if not picks:
                continue
            squads[m.entry] = {p["element"] for p in picks}
            xi = {p["element"] for p in picks if p.get("position", 0) <= 11}
            for sub in m.picks.get("automatic_subs", []):
                xi.discard(sub["element_out"])
                xi.add(sub["element_in"])
            if m.picks.get("active_chip") == "bboost":
                xi = set(squads[m.entry])
            xis[m.entry] = xi
        if len(squads) > 2:
            owners = Counter(el for sq in squads.values() for el in sq)
            diffs = [(self.pts(el), el, e) for e, xi in xis.items() for el in xi if owners[el] == 1]
            if diffs:
                pts, el, e = max(diffs)
                if pts >= 8:
                    self.note(5, f"{self.names[e]} was the only manager with {self.pname(el)}, "
                                 f"who scored {pts}.")

        # transfers and hits
        singles, hits = [], []
        for m in self.active:
            if (m.picks or {}).get("active_chip") in ("wildcard", "freehit"):
                continue
            delta = 0
            for t in m.transfers:
                d = self.pts(t["element_in"]) - self.pts(t["element_out"])
                delta += d
                singles.append((d, m, t))
            cost = m.history[gw].get("event_transfers_cost", 0)
            if cost and m.transfers:
                hits.append((delta - cost, cost, m))
        if len(hits) == 1:
            net, cost, m = hits[0]
            outcome = (f"came out {net} {plural(net, 'point')} ahead" if net > 0 else
                       "broke even" if net == 0 else
                       f"ended {-net} {plural(-net, 'point')} worse off")
            self.note(4, f"{m.name} took a -{cost} hit and {outcome}.")
        elif hits:
            paid = [m.name for net, _c, m in hits if net > 0]
            self.note(4, f"{words(len(hits)).capitalize()} managers took points hits; "
                         + (f"only {join_names(paid)} came out ahead." if paid else "none of them paid off."))
        if singles:
            d, m, t = max(singles, key=lambda x: x[0])
            if d >= 5:
                self.note(4.5, f"Best transfer: {m.name} brought in {self.pname(t['element_in'])} for "
                               f"{self.pname(t['element_out'])}, a gain of {d}.")

        # bench
        benches = [(m.history[gw].get("points_on_bench", 0), m) for m in self.active
                   if (m.picks or {}).get("active_chip") != "bboost"]
        if benches:
            top = max(b for b, _ in benches)
            who = [m for b, m in benches if b == top]
            if top >= 10 and len(who) <= 3:
                each = " each" if len(who) > 1 else ""
                self.note(3, f"{join_names(m.name for m in who)}{each} left {top} points on the bench.")

        # form
        weeks = [g for g in range(gw - FORM_WEEKS + 1, gw + 1) if g >= 1]
        if len(weeks) == FORM_WEEKS:
            form = {m.entry: sum(m.net(g) for g in weeks) for m in self.active
                    if all(g in m.history for g in weeks)}
            if len(form) > 2:
                e, p = max(form.items(), key=lambda kv: kv[1])
                self.note(2, f"Best form: {self.names[e]}, with {p} points over the last "
                             f"{words(FORM_WEEKS)} gameweeks.")

    def notes_section(self):
        notes = [t for _p, t in sorted(self.notes, key=lambda x: -x[0])][:MAX_NOTES]
        return Section("Also this week", bullets=notes)


def build_report(client, config, gameweek=None):
    return ReportBuilder(client, config, gameweek).build()

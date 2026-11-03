"""Runs the whole report against a fake, made-up league (no internet needed).

    python -m unittest discover tests
"""

import json
import random
import unittest

from fpl_weekly.render import to_markdown, to_teams_payload
from fpl_weekly.stats import build_report

GW = 6
N_PLAYERS = 60


class FakeClient:
    """Mimics the shape of the real FPL API responses with random data."""

    def __init__(self, n_managers=8, seed=1):
        rng = random.Random(seed)
        self.rng = rng
        self.entries = [1000 + i for i in range(n_managers)]
        firsts = ["Alex", "Sam", "Jo", "Chris", "Pat", "Sam", "Robin", "Kim", "Lee", "Max", "Ali", "Ash",
                  "Dev", "Eli", "Fin", "Gus"]
        self.people = {e: f"{firsts[i % len(firsts)]} Tester{i}" for i, e in enumerate(self.entries)}
        self.teams = {e: f"FC Fake {i}" for i, e in enumerate(self.entries)}
        self.live_pts = {g: {p: rng.choice([0, 1, 2, 2, 2, 3, 5, 6, 8, 12, 15]) for p in range(1, N_PLAYERS + 1)}
                         for g in range(1, GW + 1)}
        self.squads = {(e, g): rng.sample(range(1, N_PLAYERS + 1), 15) for e in self.entries
                       for g in range(1, GW + 1)}
        self.chips = {(self.entries[0], GW): "3xc", (self.entries[1], GW): "bboost",
                      (self.entries[2], GW): "wildcard"}
        self.history = {}
        for e in self.entries:
            total, rows = 0, []
            start = 1 if e != self.entries[-1] else 3  # one late joiner
            for g in range(start, GW + 1):
                sq = self.squads[(e, g)]
                pts = sum(self.live_pts[g][p] for p in sq[:11]) + self.live_pts[g][sq[0]]
                cost = rng.choice([0, 0, 0, 4, 8])
                total += pts - cost
                rows.append({"event": g, "points": pts, "total_points": total, "rank": 1,
                             "overall_rank": rng.randint(1000, 9_000_000), "bank": 5,
                             "value": rng.randint(1000, 1050),
                             "event_transfers": rng.choice([0, 1, 2, 3]), "event_transfers_cost": cost,
                             "points_on_bench": sum(self.live_pts[g][p] for p in sq[11:])})
            self.history[e] = rows

    def bootstrap(self):
        return {
            "events": [{"id": g, "finished": g <= GW, "data_checked": g <= GW,
                        "average_entry_score": 50, "highest_score": 120} for g in range(1, 39)],
            "elements": [{"id": p, "web_name": f"Player{p}"} for p in range(1, N_PLAYERS + 1)],
            "phases": [{"id": 1, "name": "Overall", "start_event": 1, "stop_event": 38},
                       {"id": 2, "name": "August", "start_event": 1, "stop_event": 3},
                       {"id": 3, "name": "September", "start_event": 4, "stop_event": 7}],
            "chips": [{"name": n, "start_event": 1, "stop_event": 19} for n in ("wildcard", "freehit", "bboost", "3xc")],
        }

    def live(self, gw):
        return {"elements": [{"id": p, "stats": {"total_points": v, "minutes": 90 if v else 0}}
                             for p, v in self.live_pts[gw].items()]}

    def entry_history(self, e):
        chips = [{"name": "wildcard", "event": 3}] if e == self.entries[0] else []
        return {"current": self.history[e], "chips": chips}

    def picks(self, e, gw):
        if (e, gw) not in self.squads or not any(r["event"] == gw for r in self.history[e]):
            return None
        sq = self.squads[(e, gw)]
        return {
            "active_chip": self.chips.get((e, gw)),
            "automatic_subs": [{"element_in": sq[11], "element_out": sq[10]}],
            "picks": [{"element": p, "position": i + 1, "multiplier": 1,
                       "is_captain": i == 0, "is_vice_captain": i == 1} for i, p in enumerate(sq)],
        }

    def transfers(self, e):
        return [{"event": GW, "element_in": self.squads[(e, GW)][2], "element_out": 59},
                {"event": GW - 1, "element_in": 1, "element_out": 2}]

    def classic_standings(self, league_id):
        return {"name": "Fake Office League"}, [
            {"entry": e, "entry_name": self.teams[e], "player_name": self.people[e]} for e in self.entries]

    def h2h_standings(self, league_id):
        return {"name": f"H2H {league_id}"}, [
            {"entry": e, "entry_name": self.teams[e], "player_name": self.people[e]} for e in self.entries]

    def h2h_matches(self, league_id):
        out = []
        pool = self.entries + [None] if len(self.entries) % 2 else list(self.entries)
        for g in range(1, GW + 1):
            order = pool[:]
            random.Random(g * league_id).shuffle(order)
            for a, b in zip(order[::2], order[1::2]):
                if a is None:
                    a, b = b, a
                out.append({"event": g, "is_knockout": False,
                            "entry_1_entry": a, "entry_1_name": self.teams[a],
                            "entry_1_player_name": self.people[a],
                            "entry_1_points": self.rng.randint(20, 110),
                            "entry_2_entry": b, "entry_2_name": self.teams.get(b, "AVERAGE"),
                            "entry_2_player_name": self.people.get(b, "AVERAGE"),
                            "entry_2_points": self.rng.randint(20, 110)})
        return out


CONFIG = {"classic_league_id": 1, "h2h_leagues": [{"id": 2, "label": "Main H2H"},
                                                   {"id": 3, "label": "Champions H2H"}],
          "title": None, "nicknames": {}}


class ReportTest(unittest.TestCase):
    def check(self, client, gameweek=None):
        report = build_report(client, CONFIG, gameweek)
        md = to_markdown(report)
        payload = to_teams_payload(report)
        size = len(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode())
        self.assertLess(size, 28_000, "Teams cards must stay under ~28KB")
        self.assertIn("Manager of the Week", md)
        self.assertIn("Highest Score", md)
        self.assertNotIn("| |", md)  # no blank table headers
        self.assertLess(len(report.headline), 90)
        self.assertEqual(payload["attachments"][0]["content"]["type"], "AdaptiveCard")
        return report, md

    def test_latest_gameweek(self):
        report, md = self.check(FakeClient())
        self.assertEqual(report.gameweek, GW)
        for heading in ("Fake Office League", "Main H2H", "Champions H2H", "Also this week",
                        "| Pos | Manager | GW | Total | +/- |", "| Home | Score | Away |"):
            self.assertIn(heading, md)
        self.assertNotIn("Season So Far", md)
        # duplicate first names fall back to full names
        self.assertIn("Sam Tester1", md)

    def test_odd_numbered_league_and_big_league(self):
        self.check(FakeClient(n_managers=7, seed=3))
        self.check(FakeClient(n_managers=16, seed=4))

    def test_first_gameweek(self):
        self.check(FakeClient(seed=5), gameweek=1)

    def test_nickname_by_display_name(self):
        cfg = dict(CONFIG, nicknames={"Kim": "Kim Sheng"})
        md = to_markdown(build_report(FakeClient(), cfg))
        self.assertIn("Kim Sheng", md)
        self.assertNotIn("| Kim |", md)

    def test_nicknames(self):
        client = FakeClient()
        cfg = dict(CONFIG, nicknames={str(client.entries[0]): "The Gaffer"})
        report = build_report(client, cfg)
        self.assertIn("The Gaffer", to_markdown(report))


if __name__ == "__main__":
    unittest.main()


class FakeChallenge:
    """Challenge league table is deliberately stale (totals lag); history is the truth."""
    HIST = {1: [(GW - 1, 40, 420), (GW, 61, 481)], 2: [(GW - 1, 70, 430), (GW, 40, 470)]}

    def classic_standings(self, league_id):
        return {"name": "Fake Challenge"}, [
            {"entry": 1, "rank": 1, "last_rank": 1, "player_name": "Alex Tester0", "event_total": 0, "total": 400},
            {"entry": 2, "rank": 2, "last_rank": 2, "player_name": "Outsider Person", "event_total": 0, "total": 390},
        ]

    def entry_history(self, entry):
        return {"current": [{"event": g, "points": p, "total_points": t, "percentile_rank": 5}
                            for g, p, t in self.HIST[entry]]}

    def bootstrap(self):
        return {"events": [{"id": GW, "average_entry_score": 50}]}


class FakeDraft:
    def draft_league(self, league_id):
        return {
            "league": {"name": "Fake Draft", "scoring": "h"},
            "league_entries": [{"id": i, "player_first_name": f, "player_last_name": "Tester"}
                               for i, f in enumerate(["Dee", "Em", "Gee", "Aitch"], start=1)],
            "matches": [{"event": GW, "finished": True, "league_entry_1": 1, "league_entry_1_points": 50,
                         "league_entry_2": 2, "league_entry_2_points": 41},
                        {"event": GW, "finished": True, "league_entry_1": 3, "league_entry_1_points": 30,
                         "league_entry_2": 4, "league_entry_2_points": 30}],
            "standings": [{"rank": i, "league_entry": i, "total": 20 - i, "matches_won": 5,
                           "matches_drawn": 1, "matches_lost": 1} for i in range(1, 5)],
        }


EXTRA_CONFIG = dict(CONFIG, extra_leagues=[{"game": "challenge", "id": 9, "label": "FPL Challenge"},
                                           {"game": "draft", "id": 8, "label": "FPL Draft"},
                                           {"game": "draft", "id": None, "label": "Not set up"}],
                    site_url="https://example.github.io/ff/")
EXTRAS = {"challenge": FakeChallenge(), "draft": FakeDraft()}


class ExtraLeaguesAndSiteTest(unittest.TestCase):
    def test_extra_leagues_and_site(self):
        import tempfile
        from pathlib import Path
        from fpl_weekly.render import to_teams_payload
        from fpl_weekly.site import write_site

        report = build_report(FakeClient(), EXTRA_CONFIG, extra_clients=EXTRAS)
        md = to_markdown(report)
        self.assertIn("## FPL Challenge", md)
        self.assertIn("## FPL Draft", md)
        self.assertNotIn("Not set up", md)
        self.assertIn("**Alex** scored 61, 11 above the Challenge average", md)  # same person, same name
        self.assertIn("| 1 | Alex | 61 | 40 | 481 | - | ▲1 |", md)   # totals from history, not stale table

        payload = to_teams_payload(report, "https://example.github.io/ff/gw/6.html")
        card = payload["attachments"][0]["content"]
        self.assertEqual(card["actions"][0]["url"], "https://example.github.io/ff/gw/6.html")
        self.assertEqual(card["actions"][1]["title"], "Your personal report")
        self.assertEqual(card["actions"][1]["url"], "https://example.github.io/ff/gw/6.html#me")

        with tempfile.TemporaryDirectory() as d:
            page = write_site(report, d).read_text()
            self.assertIn("<h1>", page)
            self.assertIn("FPL Draft", page)
            self.assertIn('class="score"', page)
            self.assertTrue((Path(d) / "index.html").exists())

    def test_broken_extra_league_is_skipped(self):
        class Broken:
            def classic_standings(self, league_id):
                raise RuntimeError("boom")
        report = build_report(FakeClient(), EXTRA_CONFIG, extra_clients={"challenge": Broken(), "draft": FakeDraft()})
        self.assertNotIn("FPL Challenge", to_markdown(report))


class SeasonFeaturesTest(unittest.TestCase):
    def test_month_and_odds(self):
        report = build_report(FakeClient(n_managers=21), EXTRA_CONFIG, extra_clients=EXTRAS)
        titles = {s.title: s for s in report.sections}
        self.assertIn("Manager of the Month", titles)
        self.assertIn("Previous winners: August", " ".join(titles["Manager of the Month"].paragraphs))
        odds = titles["Title odds"].table.rows
        total = sum(float(r[2].rstrip("%")) for r in odds if not r[2].startswith("<"))
        self.assertLessEqual(total, 101)
        self.assertNotIn("Chip tracker", titles)

    def test_missing_phases(self):
        client = FakeClient()
        boot = client.bootstrap()
        boot.pop("phases"); boot.pop("chips")
        client.bootstrap = lambda: boot
        titles = [s.title for s in build_report(client, CONFIG).sections]
        self.assertNotIn("Manager of the Month", titles)


class InsightsTest(unittest.TestCase):
    def test_insights_present_and_varied(self):
        report = build_report(FakeClient(n_managers=21), EXTRA_CONFIG, extra_clients=EXTRAS)
        section = next(s for s in report.sections if s.title == "Behind the numbers")
        kinds = [i.kind or i.label for i in section.insights]
        self.assertEqual(len(kinds), len(set(kinds)))
        self.assertLessEqual(len(section.insights), 6)
        self.assertTrue(report.card_insight)


class FinalGameweekTest(unittest.TestCase):
    class Stub:
        def __init__(self, fixtures_done=True, bonus=True):
            self.fixtures_done, self.bonus = fixtures_done, bonus

        def fixtures(self, gw):
            return [{"finished": True}, {"finished": self.fixtures_done}]

        def event_status(self):
            return {"status": [{"event": 9, "bonus_added": self.bonus}], "leagues": "Updating"}

    EVENTS = [{"id": 8, "finished": True, "data_checked": True},
              {"id": 9, "is_current": True, "finished": False, "data_checked": False}]

    def test_current_gameweek_counts_once_matches_and_bonus_done(self):
        from fpl_weekly.stats import latest_final_gameweek
        self.assertEqual(latest_final_gameweek(self.EVENTS, self.Stub()), 9)
        self.assertEqual(latest_final_gameweek(self.EVENTS, self.Stub(fixtures_done=False)), 8)
        self.assertEqual(latest_final_gameweek(self.EVENTS, self.Stub(bonus=False)), 8)
        self.assertEqual(latest_final_gameweek(self.EVENTS), 8)   # no client: FPL's flags only


class ReadinessTest(unittest.TestCase):
    class Stub:
        def __init__(self, leagues="Updated", bonus=True, table_total=100, gw=9):
            self.leagues, self.bonus, self.table_total, self.gw = leagues, bonus, table_total, gw

        def event_status(self):
            return {"status": [{"event": self.gw, "bonus_added": self.bonus}], "leagues": self.leagues}

        def classic_standings(self, league_id):
            return {}, [{"entry": 1, "player_name": "Alex Tester", "total": self.table_total}]

        def h2h_matches(self, league_id):
            return [{"event": 9, "entry_1_points": 50, "entry_2_points": 40}]

        kickoff = "2099-01-01T15:00:00Z"   # far future = "just played"

        def fixtures(self, gw):
            return [{"kickoff_time": self.kickoff, "finished": True}]

        def entry_history(self, entry):
            return {"current": [{"event": 9, "total_points": 100}]}

    def check(self, **kw):
        from fpl_weekly.__main__ import tables_ready
        return tables_ready(self.Stub(**kw), {"classic_league_id": 1, "h2h_leagues": [{"id": 2}]}, 9)[0]

    def test_ready(self):
        self.assertTrue(self.check())

    def test_global_flag_still_updating_but_our_tables_done(self):
        # FPL's global flag lags for hours; our own tables are what matter
        self.assertTrue(self.check(leagues="Updating"))
        self.assertTrue(self.check(leagues=""))

    def test_bonus_missing(self):
        self.assertFalse(self.check(bonus=False))

    def test_table_total_not_matching(self):
        self.assertFalse(self.check(table_total=90))

    def test_lagging_table_feed_stops_blocking_after_a_while(self):
        from fpl_weekly.__main__ import tables_ready
        stub = self.Stub(table_total=90)
        self.assertFalse(tables_ready(stub, {"classic_league_id": 1}, 9)[0])
        stub.kickoff = "2020-01-01T15:00:00Z"   # long ago
        self.assertTrue(tables_ready(stub, {"classic_league_id": 1}, 9)[0])

    def test_older_gameweek_is_ready(self):
        # status already reports a later gameweek -> the one we want is long done
        self.assertTrue(self.check(leagues="", gw=10))


class WhatIfTest(unittest.TestCase):
    """Scoring an untouched team with FPL's automatic substitution rules."""

    class B:  # minimal builder: element types only
        def __init__(self, types):
            self.players = {e: {"element_type": t} for e, t in types.items()}

    # elements: 1 GK, 2-5 DEF (4), 6-9 MID (4), 10-11 FWD (2) | bench 12 GK, 13 DEF, 14 MID, 15 FWD
    TYPES = {1: 1, 2: 2, 3: 2, 4: 2, 5: 2, 6: 3, 7: 3, 8: 3, 9: 3, 10: 4, 11: 4,
             12: 1, 13: 2, 14: 3, 15: 4}

    def team(self, captain=10, vice=6):
        return {"event": 1, "picks": [[e, e, e == captain, e == vice] for e in range(1, 16)]}

    def live(self, overrides=None):
        data = {str(e): [2, 90] for e in range(1, 16)}
        for e, v in (overrides or {}).items():
            data[str(e)] = v
        return data

    def score(self, live, **kw):
        from fpl_weekly.season import score_fixed_team
        return score_fixed_team(self.B(self.TYPES), self.team(**kw), live)

    def test_everyone_plays(self):
        self.assertEqual(self.score(self.live()), 11 * 2 + 2)   # XI + captain double

    def test_goalkeeper_sub(self):
        self.assertEqual(self.score(self.live({1: [0, 0], 12: [6, 90]})), 10 * 2 + 6 + 2)

    def test_outfield_sub_in_bench_order(self):
        # MID 6 doesn't play; first outfield bench player (DEF 13, 5 pts) comes on (4 DEF->5 DEF ok)
        self.assertEqual(self.score(self.live({6: [0, 0], 13: [5, 90]}), vice=7), 10 * 2 + 5 + 2)

    def test_formation_respected(self):
        # both FWDs miss: bench DEF/MID can only replace one (need >=1 FWD), so FWD 15 must come on
        live = self.live({10: [0, 0], 11: [0, 0], 13: [1, 90], 14: [1, 90], 15: [7, 90]})
        # XI: 9 starters x2 + FWD15 (7) + DEF13 (1)? -> DEF13 would leave 0 FWD, so first sub must be FWD15
        # first missing (10): DEF13 -> 0 FWD invalid; MID14 -> invalid; FWD15 -> ok (7)
        # second missing (11): DEF13 -> FWD count 1 ok (1)
        self.assertEqual(self.score(live, captain=2, vice=3), 9 * 2 + 7 + 1 + 2)

    def test_vice_captain_takes_over(self):
        self.assertEqual(self.score(self.live({10: [0, 0], 15: [0, 0], 13: [0, 0], 14: [0, 0]}), vice=6),
                         10 * 2 + 2)  # captain out, no sub plays, vice (2) doubled

    def test_what_if_section_and_cache(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            report = build_report(FakeClient(n_managers=8), CONFIG, cache_dir=d)
            titles = {s.title: s for s in report.sections}
            self.assertIn("What if?", titles)
            self.assertTrue((Path(d) / "live_1.json").exists())
            self.assertTrue(any(p.name.startswith("first_team_") for p in Path(d).iterdir()))
            again = build_report(FakeClient(n_managers=8), CONFIG, cache_dir=d)   # from cache
            self.assertEqual(titles["What if?"].table.rows,
                             {s.title: s for s in again.sections}["What if?"].table.rows)


class ManagerOfTheWeekTest(unittest.TestCase):
    def test_rounded_rating(self):
        from fpl_weekly.stats import ReportBuilder
        client = FakeClient(n_managers=12)
        b = ReportBuilder(client, CONFIG)
        report = b.build()
        by_entry = {r.manager.entry: r for r in b.motw_ratings}
        # chips are marked down (entries[0] played Triple Captain, entries[1] Bench Boost)
        self.assertTrue(any(l == "Triple Captain" and v <= 0 for l, v in by_entry[client.entries[0]].parts))
        self.assertTrue(any(l == "Bench Boost" and v <= 0 for l, v in by_entry[client.entries[1]].parts))
        # rating = points + adjustments, and the list is ordered by rating
        for r in b.motw_ratings:
            self.assertAlmostEqual(r.rating, round(r.points + sum(v for _l, v in r.parts), 1))
        self.assertEqual(b.motw_ratings, sorted(b.motw_ratings, key=lambda r: (-r.rating, -r.points)))
        _typical, line = b.motw_concentration_line
        self.assertGreaterEqual(line, 0.60)
        self.assertEqual(report.key_facts[0][0], "Highest Score")
        labels = [k for k, _v in report.key_facts]
        self.assertIn("Classic League Leader", labels)
        self.assertIn("Title Odds", labels)
        self.assertEqual(report.key_facts[1][0], "Manager of the Week")


class PersonalReportTest(unittest.TestCase):
    def test_one_report_per_manager_on_the_page(self):
        import tempfile
        from fpl_weekly.site import write_site
        report = build_report(FakeClient(n_managers=9), EXTRA_CONFIG, extra_clients=EXTRAS)
        self.assertEqual(len(report.personal), 9)
        r = report.personal[0]
        self.assertTrue(r.summary)
        self.assertEqual(r.points, r.season[-1][1])
        self.assertIsNotNone(r.captain)
        for p in r.differentials:
            self.assertLessEqual(p.league_share, 0.25)
        with tempfile.TemporaryDirectory() as d:
            page = write_site(report, d).read_text()
            self.assertIn('id="me-select"', page)
            self.assertEqual(page.count('class="me-report"'), 9)

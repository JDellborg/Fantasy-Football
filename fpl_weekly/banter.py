"""Banter lines. Edit freely - {placeholders} are filled in automatically.

Each week picks lines at random, but the same gameweek always gets the same
lines, so a preview matches what is later posted.
"""

import random

LINES = {
    "intro": [
        "Another gameweek, another set of excuses. Let's see who's been bluffing.",
        "The points are in, the bonus is confirmed, and some of you should be ashamed.",
        "Grab a brew. Some of these numbers are not for the faint-hearted.",
        "Gameweek done. Egos inflated, dreams shattered - standard stuff.",
        "Your weekly reminder that 'gut feeling' is not a transfer strategy.",
    ],
    "motw": [
        "{name} dropped **{pts}** and will now be unbearable until at least Christmas.",
        "Take a bow, {name}. **{pts}** points. Somebody check their laptop for a time machine.",
        "{name} hit **{pts}**. Expect a 20-minute 'tactical breakdown' at the coffee machine.",
        "**{pts}** for {name}. Even a stopped clock is right twice a season.",
        "All hail {name} - **{pts}** points and a level of smugness we'll all have to live with.",
    ],
    "spoon": [
        "{name} managed **{pts}**. Somewhere, a toddler picking players by shirt colour feels very smug.",
        "**{pts}** for {name}. Have you tried turning your team off and on again?",
        "{name} scored **{pts}**. The wooden spoon has been polished and is ready for collection.",
        "{name} with **{pts}**. Bold strategy - let's see if it pays off. (It won't.)",
        "Thoughts and prayers for {name}, who mustered **{pts}**. We'll get you a support group.",
    ],
    "climber": [
        "{name} rockets up **{n}** {places}. Don't get used to the view.",
        "Up **{n}** {places} for {name}. Vertigo is a real risk at this altitude.",
        "{name} climbs **{n}** {places} - finally remembered their password, by the looks of it.",
    ],
    "faller": [
        "{name} plummets **{n}** {places}. Parachute not included.",
        "Down **{n}** for {name}. The only thing falling faster is their credibility.",
        "{name} slides **{n}** {places}. Someone check they've not set their team to autopilot.",
    ],
    "hot": [
        "{name} is on fire: **{pts}** over the last {weeks} weeks. Call the fire brigade.",
        "{name} - **{pts}** in {weeks} weeks. Peaking too early? We can only hope.",
    ],
    "cold": [
        "{name} has **{pts}** in {weeks} weeks. Colder than an away end in January.",
        "{name}: **{pts}** across {weeks} weeks. Form is temporary; this seems permanent.",
    ],
    "best_captain": [
        "{name} gave the armband to {player} - **{pts}** points. Galaxy brain.",
        "{player} returned **{pts}** for {name}. Even a broken compass points north sometimes.",
    ],
    "worst_captain": [
        "{name} captained {player} for **{pts}**. The armband deserves better.",
        "{player} returned **{pts}** for {name}. Might as well have captained the kit man.",
    ],
    "bench": [
        "{name} left **{pts}** points on the bench. The subs have filed a formal complaint.",
        "**{pts}** points rotting on {name}'s bench. Inspired management.",
        "{name} benched **{pts}** points. Bold of you to assume you know better than the algorithm.",
    ],
    "hit_good": [
        "{name} took a -{cost} and came out **{net:+d}** ahead. Annoyingly, it worked.",
    ],
    "hit_bad": [
        "{name} paid -{cost} for the privilege of being **{net:+d}** down. Money well spent.",
        "{name}'s -{cost} hit returned **{net:+d}**. Accountants are weeping.",
    ],
    "differential": [
        "Nobody else had {player} - **{pts}** points for {name}. Hipster manager of the week.",
        "{name} was the only one with {player} (**{pts}** pts). 'I've been saying this for weeks' incoming.",
    ],
    "h2h_thrashing": [
        "{winner} battered {loser} by **{margin}**. Somebody call it off.",
        "{winner} beat {loser} by **{margin}**. That's not a match, that's a mugging.",
    ],
    "h2h_narrow": [
        "{winner} edged {loser} by just **{margin}**. Squeaky bum time.",
        "**{margin}** {points} separated {winner} and {loser}. Somebody's crying into their bonus points.",
    ],
    "h2h_robbed": [
        "{name} scored **{pts}** and still lost. The universe is cruel.",
    ],
    "h2h_jammy": [
        "{name} won with just **{pts}**. Jammy doesn't even cover it.",
    ],
    "h2h_upset": [
        "UPSET! {winner} (was {wrank}) toppled {loser} (was {lrank}).",
        "Giant-killing alert: {winner} (was {wrank}) knocked over {loser} (was {lrank}).",
    ],
    "outro": [
        "That's your lot. Set your team before the deadline - yes, you, {spoon}.",
        "Same time next week. {motw}, try to stay humble. (You won't.)",
        "Deadline reminders are free. Excuses are not. See you next week.",
    ],
}


class Banter:
    def __init__(self, seed):
        self.rng = random.Random(seed)

    def line(self, key, **values):
        return self.rng.choice(LINES[key]).format(**values)

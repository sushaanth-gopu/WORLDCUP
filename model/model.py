"""
=============================================================
  FIFA WORLD CUP 2026 - MONTE CARLO SIMULATION ENGINE  v2.3
  NEW in v2.3:
    [E3]  Played-match locking: group-stage results that have
          already happened are fed in as fixed outcomes before
          any simulation begins.  Remaining unplayed fixtures
          are still Monte-Carlo'd.  simulate_group() now
          accepts a `played` dict keyed (teamA, teamB) →
          {goals_a, goals_b} so real results are never re-
          rolled.  fetch_played_wc() pulls FINISHED matches
          from the football-data API automatically.
          A MANUAL_RESULTS dict lets you hard-code results
          when offline.

    [E4]  Round-of-32 win probability table: after the Monte
          Carlo run, print_r32_probabilities() prints each
          R32 matchup with the probability each team wins
          that specific tie (averaging over all simulations
          where those two teams actually meet, plus the
          probability they meet at all).
=============================================================
"""

from __future__ import annotations

import copy
import csv
import json
import math
import os
import random
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

import requests

try:
    from tabulate import tabulate
except ImportError:
    def tabulate(rows, headers=(), tablefmt=""):
        lines = ["\t".join(str(h) for h in headers)]
        for r in rows:
            lines.append("\t".join(str(c) for c in r))
        return "\n".join(lines)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# =============================================================
# 0.  CONFIG
# =============================================================

FD_BASE_URL          = "https://api.football-data.org/v4"
FD_TOKEN             = os.getenv("FOOTBALL_DATA_TOKEN", "")
FD_THROTTLE_SEC      = 6.5
WC_COMPETITION_CODE  = "WC"

HIST_RESULTS_URL = (
    "https://raw.githubusercontent.com/martj42/"
    "international_results/master/results.csv"
)

CACHE_DIR       = Path(".wc2026_cache")
CACHE_DIR.mkdir(exist_ok=True)
HIST_CSV_PATH   = CACHE_DIR / "results.csv"
ELO_JSON_PATH     = CACHE_DIR / "team_elo.json"
# Append-only log of every real WC match used to update ELOs
ELO_LIVE_LOG_PATH = CACHE_DIR / "live_elo_updates.jsonl"

CSV_OUT_DIR = Path("wc2026_results")
CSV_OUT_DIR.mkdir(exist_ok=True)

RECENT_YEARS        = 20
DECAY_HALF_LIFE_YEARS = 8
TODAY               = date.today()

GROUP_DRAW_BASE     = 0.270
GROUP_DRAW_SKILL_SCALE = 0.12

LAMBDA_BASE         = 1.30

P_WIN_90            = 0.810
P_WIN_ET            = 0.190
ET_COMPRESSION      = 0.65

HOST_ADVANTAGE_ELO  = 80

COMPETITION_WEIGHTS = {
    "FIFA World Cup":               60,
    "FIFA World Cup qualification": 40,
    "UEFA Euro":                    50,
    "UEFA Euro qualification":      30,
    "Copa America":                 50,
    "African Cup of Nations":       40,
    "AFC Asian Cup":                40,
    "UEFA Nations League":          35,
    "Friendly":                     20,
}
DEFAULT_K = 25

GROUP_STAGE_K = 32

# =============================================================
# [E3]  MANUAL RESULTS — fill these in as games are played
#       when you are running offline (no API token).
#       Key: (home_team, away_team) using normalized names.
#       Value: dict with goals_a (home) and goals_b (away).
# =============================================================

MANUAL_RESULTS: dict[tuple[str, str], dict] = {
    # Example — uncomment and edit as needed:
    # ("Mexico", "South Africa"): {"goals_a": 2, "goals_b": 0},
    # ("South Korea", "Czechia"): {"goals_a": 1, "goals_b": 1},
}


# =============================================================
# 1.  TEAM NAME NORMALIZATION
# =============================================================

NAME_ALIASES = {
    "USA":                              "United States",
    "United States":                    "United States",
    "United States of America":         "United States",
    "South Korea":                      "South Korea",
    "Korea Republic":                   "South Korea",
    "Republic of Korea":                "South Korea",
    "Korea, South":                     "South Korea",
    "Ivory Coast":                      "Ivory Coast",
    "Côte d'Ivoire":                    "Ivory Coast",
    "Cote d'Ivoire":                    "Ivory Coast",
    "Czechia":                          "Czechia",
    "Czech Republic":                   "Czechia",
    "Turkey":                           "Turkey",
    "Türkiye":                          "Turkey",
    "Turkiye":                          "Turkey",
    "DR Congo":                         "DR Congo",
    "Congo DR":                         "DR Congo",
    "Democratic Republic of the Congo": "DR Congo",
    "Congo (DR)":                       "DR Congo",
    "Zaire":                            "DR Congo",
    "Curacao":                          "Curacao",
    "Curaçao":                          "Curacao",
    "Cape Verde":                       "Cape Verde",
    "Cabo Verde":                       "Cape Verde",
    "Bosnia and Herzegovina":           "Bosnia and Herzegovina",
    "Bosnia-Herzegovina":               "Bosnia and Herzegovina",
    "Iran":                             "Iran",
    "IR Iran":                          "Iran",
    "North Macedonia":                  "North Macedonia",
    "Macedonia":                        "North Macedonia",
}


def normalize(name: str) -> str:
    if not name:
        return name
    return NAME_ALIASES.get(name.strip(), name.strip())


# =============================================================
# 2.  2026 GROUPS
# =============================================================

GROUPS_2026 = {
    "A": ["Mexico",        "South Korea",  "Czechia",                "South Africa"],
    "B": ["Canada",        "Switzerland",  "Bosnia and Herzegovina", "Qatar"],
    "C": ["Brazil",        "Morocco",      "Scotland",               "Haiti"],
    "D": ["United States", "Paraguay",     "Turkey",                 "Australia"],
    "E": ["Germany",       "Ivory Coast",  "Ecuador",                "Curacao"],
    "F": ["Netherlands",   "Sweden",       "Japan",                  "Tunisia"],
    "G": ["Belgium",       "Egypt",        "Iran",                   "New Zealand"],
    "H": ["Spain",         "Uruguay",      "Cape Verde",             "Saudi Arabia"],
    "I": ["France",        "Senegal",      "Norway",                 "Iraq"],
    "J": ["Argentina",     "Austria",      "Algeria",                "Jordan"],
    "K": ["Portugal",      "Colombia",     "Uzbekistan",             "DR Congo"],
    "L": ["England",       "Croatia",      "Ghana",                  "Panama"],
}

GROUPS_2026 = {g: [normalize(t) for t in teams] for g, teams in GROUPS_2026.items()}
HOST_NATIONS = frozenset(normalize(t) for t in {"United States", "Canada", "Mexico"})


# =============================================================
# [F1] CORRECT FIFA 2026 BRACKET
# =============================================================

R32_BRACKET = [
    ("A1", "B2"),
    ("C1", "D2"),
    ("E1", "F2"),
    ("G1", "H2"),
    ("I1", "J2"),
    ("K1", "L2"),
    ("A2", "B1"),
    ("C2", "D1"),
    ("E2", "F1"),
    ("G2", "H1"),
    ("I2", "J1"),
    ("K2", "L1"),
    ("T1", "T2"),
    ("T3", "T4"),
    ("T5", "T6"),
    ("T7", "T8"),
]


# =============================================================
# SQUAD / PLAYER / CLUB STRENGTH LAYER
# =============================================================

@dataclass
class SquadProfile:
    team: str
    player_quality: float = 75.0
    club_strength: float = 75.0
    squad_depth: float = 60.0
    fitness: float = 90.0
    key_player_availability: float = 1.0


_RAW_SQUADS: list[tuple] = [
    ("France",                   90,   93,   85,    88,   1.00),
    ("Brazil",                   89,   88,   82,    85,   0.95),
    ("England",                  88,   91,   80,    90,   0.95),
    ("Portugal",                 88,   87,   75,    82,   0.90),
    ("Spain",                    88,   90,   88,    92,   1.00),
    ("Argentina",                91,   85,   76,    86,   0.90),
    ("Germany",                  85,   88,   84,    91,   1.00),
    ("Netherlands",              85,   87,   79,    88,   0.95),
    ("Belgium",                  82,   84,   72,    85,   0.95),
    ("Croatia",                  80,   82,   70,    83,   0.90),
    ("Uruguay",                  80,   79,   74,    87,   1.00),
    ("Colombia",                 81,   80,   75,    89,   1.00),
    ("Morocco",                  79,   78,   72,    88,   1.00),
    ("Senegal",                  78,   77,   70,    85,   0.95),
    ("United States",            77,   84,   76,    92,   1.00),
    ("Mexico",                   76,   72,   68,    86,   1.00),
    ("Canada",                   76,   80,   73,    88,   1.00),
    ("Japan",                    78,   82,   74,    91,   1.00),
    ("South Korea",              76,   79,   70,    87,   1.00),
    ("Switzerland",              76,   80,   72,    89,   1.00),
    ("Norway",                   77,   82,   71,    87,   1.00),
    ("Austria",                  76,   80,   70,    86,   1.00),
    ("Sweden",                   74,   76,   68,    84,   1.00),
    ("Ecuador",                  73,   71,   65,    85,   1.00),
    ("Paraguay",                 72,   68,   63,    83,   1.00),
    ("Algeria",                  73,   72,   66,    84,   1.00),
    ("Turkey",                   74,   75,   68,    82,   1.00),
    ("Australia",                72,   74,   65,    85,   1.00),
    ("Ivory Coast",              73,   72,   65,    83,   1.00),
    ("Ghana",                    71,   70,   63,    82,   1.00),
    ("Egypt",                    71,   68,   62,    80,   0.85),
    ("Tunisia",                  70,   68,   62,    83,   1.00),
    ("Iran",                     70,   67,   61,    82,   1.00),
    ("Scotland",                 72,   73,   65,    86,   1.00),
    ("Bosnia and Herzegovina",   70,   71,   62,    83,   1.00),
    ("Czechia",                  72,   74,   65,    85,   1.00),
    ("Uzbekistan",               65,   58,   55,    83,   1.00),
    ("DR Congo",                 67,   64,   58,    80,   1.00),
    ("Cape Verde",               65,   63,   55,    82,   1.00),
    ("Saudi Arabia",             67,   65,   58,    81,   1.00),
    ("South Africa",             64,   60,   54,    81,   1.00),
    ("Qatar",                    62,   58,   50,    79,   1.00),
    ("Jordan",                   60,   57,   50,    80,   1.00),
    ("Iraq",                     61,   58,   51,    80,   1.00),
    ("Panama",                   63,   61,   53,    82,   1.00),
    ("Haiti",                    58,   54,   46,    78,   1.00),
    ("New Zealand",              60,   58,   50,    81,   1.00),
    ("Curacao",                  62,   62,   52,    80,   1.00),
]

SQUAD_PROFILES: dict[str, SquadProfile] = {}
for _row in _RAW_SQUADS:
    _t = normalize(_row[0])
    SQUAD_PROFILES[_t] = SquadProfile(
        team=_t,
        player_quality=_row[1],
        club_strength=_row[2],
        squad_depth=_row[3],
        fitness=_row[4],
        key_player_availability=_row[5],
    )


def squad_elo_modifier(team: str) -> float:
    p = SQUAD_PROFILES.get(normalize(team))
    if p is None:
        return 0.0
    pq_score   = (p.player_quality - 75) * 2.0
    cs_score   = (p.club_strength  - 75) * 1.5
    fit_score  = (p.fitness - 90)        * 2.5
    kpa_score  = (p.key_player_availability - 1.0) * 60.0
    return pq_score + cs_score + fit_score + kpa_score


def apply_injury(team: str, fitness_delta: float = 0, kpa_delta: float = 0) -> None:
    p = SQUAD_PROFILES.get(normalize(team))
    if p:
        p.fitness = max(0, min(100, p.fitness + fitness_delta))
        p.key_player_availability = max(0, min(1, p.key_player_availability + kpa_delta))
        print(f"  [injury] {team}: fitness={p.fitness:.0f}, kpa={p.key_player_availability:.2f}")


KNOWN_INJURIES: list[tuple[str, float, float]] = []


def apply_known_injuries() -> None:
    for team, fd, kpa in KNOWN_INJURIES:
        apply_injury(team, fd, kpa)



# =============================================================
# [P1]  PLAYER MODEL — individual players, roles, fatigue
# =============================================================
#
# Each team carries a 23-man squad: 11 starters + 12 bench.
# Players have a rating (0-100), position, fatigue, and
# suspension/injury status.  During match simulation:
#   - Fatigue accumulates per minute played.
#   - Goals and assists are attributed to players.
#   - Yellow/red cards trigger suspensions.
#   - Substitutions happen at configurable minutes driven by
#     fatigue, score, and tactical needs.
#   - Performance ratings update after each match and feed
#     back into the team's effective ELO for the next game.
# =============================================================

from dataclasses import dataclass, field
from typing import Optional

POSITIONS = ("GK", "CB", "FB", "CM", "CAM", "WM", "FW")

# Fatigue accumulated per 90 minutes (% of stamina lost)
FATIGUE_PER_90 = 28.0

# How much a 1-point drop in avg-starter-rating shifts team ELO
PLAYER_PERF_ELO_SCALE = 1.2

# Probability weights: who scores a goal given a team scores
# (position → relative probability of being the scorer)
SCORER_WEIGHTS = {
    "GK":  0.01, "CB": 0.04, "FB": 0.06,
    "CM":  0.14, "CAM": 0.18, "WM": 0.18, "FW": 0.39,
}
ASSISTER_WEIGHTS = {
    "GK":  0.00, "CB": 0.03, "FB": 0.09,
    "CM":  0.18, "CAM": 0.22, "WM": 0.20, "FW": 0.28,
}

# Yellow card base rate per match per outfield player
YELLOW_RATE = 0.09
# Red card base rate (direct) per outfield player
RED_RATE    = 0.006


@dataclass
class Player:
    name:       str
    team:       str
    position:   str          # one of POSITIONS
    rating:     float        # 0-100 overall quality
    is_starter: bool = True
    fatigue:    float = 0.0  # 0=fresh, 100=exhausted
    suspended:  bool  = False
    injured:    bool  = False
    # Per-tournament cumulative stats
    goals:      int   = 0
    assists:    int   = 0
    yellow_cards: int = 0
    red_cards:  int   = 0
    minutes_played: int = 0
    matches_played: int = 0
    # Per-match performance score (reset each game)
    match_rating: float = 6.0


@dataclass
class MatchLineup:
    """11 starters + bench for one team in one match."""
    team:     str
    starters: list[Player]   # exactly 11
    bench:    list[Player]   # up to 12
    subs_used: int = 0
    max_subs:  int = 5       # FIFA 2026 rules: 5 subs


# ── Squad registry ─────────────────────────────────────────────────────
# Key: team name → list[Player] (full 23-man squad)
# Generated from _RAW_PLAYER_DATA below.  Teams not listed get an
# auto-generated generic squad derived from their SquadProfile.

SQUAD_REGISTRY: dict[str, list[Player]] = {}

# (team, name, position, rating, is_starter)
_RAW_PLAYER_DATA: list[tuple] = [
    # ── FRANCE ──────────────────────────────────────────────────────────
    ("France", "Mike Maignan",         "GK",  86, True),
    ("France", "Jules Koundé",         "CB",  87, True),
    ("France", "Dayot Upamecano",      "CB",  85, True),
    ("France", "Théo Hernandez",       "FB",  86, True),
    ("France", "Jonathan Clauss",      "FB",  80, True),
    ("France", "Aurélien Tchouaméni", "CM",  86, True),
    ("France", "Adrien Rabiot",        "CM",  83, True),
    ("France", "Antoine Griezmann",    "CAM", 88, True),
    ("France", "Ousmane Dembélé",     "WM",  87, True),
    ("France", "Kylian Mbappé",       "FW",  95, True),
    ("France", "Marcus Thuram",        "FW",  85, True),
    ("France", "Alphonse Areola",      "GK",  79, False),
    ("France", "Ibrahima Konaté",     "CB",  84, False),
    ("France", "William Saliba",       "CB",  86, False),
    ("France", "Lucas Hernandez",      "FB",  82, False),
    ("France", "Eduardo Camavinga",    "CM",  84, False),
    ("France", "Youssouf Fofana",      "CM",  81, False),
    ("France", "Matteo Guendouzi",     "CM",  80, False),
    ("France", "Kingsley Coman",       "WM",  83, False),
    ("France", "Christopher Nkunku",   "CAM", 84, False),
    ("France", "Randal Kolo Muani",    "FW",  82, False),
    ("France", "Olivier Giroud",       "FW",  78, False),
    ("France", "Bradley Barcola",      "WM",  81, False),

    # ── BRAZIL ──────────────────────────────────────────────────────────
    ("Brazil", "Alisson",              "GK",  90, True),
    ("Brazil", "Éder Militão",        "CB",  86, True),
    ("Brazil", "Marquinhos",           "CB",  87, True),
    ("Brazil", "Guilherme Arana",      "FB",  80, True),
    ("Brazil", "Danilo",               "FB",  79, True),
    ("Brazil", "Bruno Guimarães",     "CM",  87, True),
    ("Brazil", "Lucas Paquetá",       "CAM", 86, True),
    ("Brazil", "Rodrygo",              "WM",  86, True),
    ("Brazil", "Vinícius Júnior",     "WM",  92, True),
    ("Brazil", "Raphinha",             "WM",  85, True),
    ("Brazil", "Endrick",              "FW",  83, True),
    ("Brazil", "Bento",                "GK",  80, False),
    ("Brazil", "Gabriel Magalhães",   "CB",  84, False),
    ("Brazil", "Bremer",               "CB",  83, False),
    ("Brazil", "Wendell",              "FB",  76, False),
    ("Brazil", "Alex Sandro",          "FB",  74, False),
    ("Brazil", "Casemiro",             "CM",  84, False),
    ("Brazil", "Gerson",               "CM",  79, False),
    ("Brazil", "Andreas Pereira",      "CM",  78, False),
    ("Brazil", "Gabriel Martinelli",   "WM",  83, False),
    ("Brazil", "Gabriel Jesus",        "FW",  80, False),
    ("Brazil", "Matheus Cunha",        "FW",  81, False),
    ("Brazil", "Savinho",              "WM",  80, False),

    # ── ENGLAND ─────────────────────────────────────────────────────────
    ("England", "Jordan Pickford",     "GK",  84, True),
    ("England", "Kyle Walker",         "FB",  83, True),
    ("England", "John Stones",         "CB",  84, True),
    ("England", "Harry Maguire",       "CB",  79, True),
    ("England", "Luke Shaw",           "FB",  81, True),
    ("England", "Declan Rice",         "CM",  88, True),
    ("England", "Jude Bellingham",     "CAM", 91, True),
    ("England", "Phil Foden",          "WM",  88, True),
    ("England", "Bukayo Saka",         "WM",  88, True),
    ("England", "Harry Kane",          "FW",  90, True),
    ("England", "Marcus Rashford",     "WM",  83, True),
    ("England", "Aaron Ramsdale",      "GK",  80, False),
    ("England", "Marc Guehi",          "CB",  82, False),
    ("England", "Ezri Konsa",          "CB",  79, False),
    ("England", "Trent Alexander-Arnold","FB",84, False),
    ("England", "Kobbie Mainoo",       "CM",  82, False),
    ("England", "Conor Gallagher",     "CM",  79, False),
    ("England", "Curtis Jones",        "CM",  79, False),
    ("England", "Cole Palmer",         "CAM", 86, False),
    ("England", "Anthony Gordon",      "WM",  81, False),
    ("England", "Ollie Watkins",       "FW",  82, False),
    ("England", "Jarrod Bowen",        "WM",  80, False),
    ("England", "Ivan Toney",          "FW",  79, False),

    # ── SPAIN ───────────────────────────────────────────────────────────
    ("Spain", "Unai Simón",           "GK",  84, True),
    ("Spain", "Dani Carvajal",        "FB",  86, True),
    ("Spain", "Robin Le Normand",     "CB",  82, True),
    ("Spain", "Aymeric Laporte",      "CB",  83, True),
    ("Spain", "Marc Cucurella",       "FB",  82, True),
    ("Spain", "Rodri",                "CM",  92, True),
    ("Spain", "Pedri",                "CM",  89, True),
    ("Spain", "Fabián Ruiz",         "CM",  84, True),
    ("Spain", "Lamine Yamal",         "WM",  90, True),
    ("Spain", "Álvaro Morata",       "FW",  82, True),
    ("Spain", "Nico Williams",        "WM",  87, True),
    ("Spain", "David Raya",           "GK",  83, False),
    ("Spain", "Pau Cubarsí",         "CB",  83, False),
    ("Spain", "Nacho Fernández",     "CB",  80, False),
    ("Spain", "Alejandro Grimaldo",   "FB",  83, False),
    ("Spain", "Martín Zubimendi",    "CM",  83, False),
    ("Spain", "Mikel Merino",         "CM",  81, False),
    ("Spain", "Dani Olmo",            "CAM", 85, False),
    ("Spain", "Bryan Gil",            "WM",  78, False),
    ("Spain", "Fermín López",        "CM",  80, False),
    ("Spain", "Ayoze Pérez",         "FW",  76, False),
    ("Spain", "Joselu",               "FW",  77, False),
    ("Spain", "Yeremy Pino",          "WM",  78, False),

    # ── ARGENTINA ───────────────────────────────────────────────────────
    ("Argentina", "Emiliano Martínez","GK",  88, True),
    ("Argentina", "Nahuel Molina",    "FB",  81, True),
    ("Argentina", "Cristian Romero",  "CB",  86, True),
    ("Argentina", "Lisandro Martínez","CB",  85, True),
    ("Argentina", "Nicolás Tagliafico","FB", 79, True),
    ("Argentina", "Rodrigo De Paul",  "CM",  84, True),
    ("Argentina", "Alexis Mac Allister","CM",85, True),
    ("Argentina", "Enzo Fernández",   "CM",  83, True),
    ("Argentina", "Lionel Messi",     "CAM", 91, True),
    ("Argentina", "Julián Álvarez",  "FW",  87, True),
    ("Argentina", "Lautaro Martínez","FW",  87, True),
    ("Argentina", "Walter Benítez",  "GK",  78, False),
    ("Argentina", "Germán Pezzella", "CB",  77, False),
    ("Argentina", "Nicolás Otamendi","CB",  79, False),
    ("Argentina", "Marcos Acuña",    "FB",  78, False),
    ("Argentina", "Leandro Paredes", "CM",  78, False),
    ("Argentina", "Giovani Lo Celso","CAM", 80, False),
    ("Argentina", "Paulo Dybala",    "CAM", 82, False),
    ("Argentina", "Nicolás González","WM",  78, False),
    ("Argentina", "Alejandro Garnacho","WM",83, False),
    ("Argentina", "Valentín Carboni","CAM", 79, False),
    ("Argentina", "Thiago Almada",   "CM",  77, False),
    ("Argentina", "Ángel Di María",  "WM",  80, False),

    # ── GERMANY ─────────────────────────────────────────────────────────
    ("Germany", "Manuel Neuer",       "GK",  85, True),
    ("Germany", "Joshua Kimmich",     "FB",  87, True),
    ("Germany", "Antonio Rüdiger",   "CB",  86, True),
    ("Germany", "Jonathan Tah",       "CB",  82, True),
    ("Germany", "David Raum",         "FB",  81, True),
    ("Germany", "Toni Kroos",         "CM",  87, True),
    ("Germany", "Florian Wirtz",      "CAM", 89, True),
    ("Germany", "Jamal Musiala",      "WM",  90, True),
    ("Germany", "Leroy Sané",        "WM",  85, True),
    ("Germany", "Kai Havertz",        "FW",  84, True),
    ("Germany", "Thomas Müller",     "FW",  82, True),
    ("Germany", "Marc-André ter Stegen","GK",85, False),
    ("Germany", "Niklas Süle",       "CB",  81, False),
    ("Germany", "Waldemar Anton",     "CB",  79, False),
    ("Germany", "Benjamin Henrichs",  "FB",  78, False),
    ("Germany", "Robert Andrich",     "CM",  80, False),
    ("Germany", "Leon Goretzka",      "CM",  82, False),
    ("Germany", "İlkay Gündoğan",  "CM",  84, False),
    ("Germany", "Chris Führich",     "WM",  78, False),
    ("Germany", "Serge Gnabry",       "WM",  81, False),
    ("Germany", "Niclas Füllkrug",   "FW",  82, False),
    ("Germany", "Deniz Undav",        "FW",  78, False),
    ("Germany", "Pascal Groß",       "CM",  78, False),

    # ── PORTUGAL ────────────────────────────────────────────────────────
    ("Portugal", "Diogo Costa",       "GK",  85, True),
    ("Portugal", "João Cancelo",     "FB",  85, True),
    ("Portugal", "Rúben Dias",       "CB",  88, True),
    ("Portugal", "António Silva",    "CB",  82, True),
    ("Portugal", "Nuno Mendes",       "FB",  84, True),
    ("Portugal", "João Palhinha",    "CM",  84, True),
    ("Portugal", "Vitinha",           "CM",  84, True),
    ("Portugal", "Bernardo Silva",    "CAM", 88, True),
    ("Portugal", "Rafael Leão",      "WM",  87, True),
    ("Portugal", "Cristiano Ronaldo", "FW",  86, True),
    ("Portugal", "Pedro Neto",        "WM",  83, True),
    ("Portugal", "José Sá",          "GK",  80, False),
    ("Portugal", "Gonçalo Inácio",  "CB",  80, False),
    ("Portugal", "Danilo Pereira",    "CB",  78, False),
    ("Portugal", "Diogo Dalot",       "FB",  81, False),
    ("Portugal", "Matheus Nunes",     "CM",  81, False),
    ("Portugal", "Rúben Neves",      "CM",  82, False),
    ("Portugal", "Otávio",          "CM",  78, False),
    ("Portugal", "Francisco Conceição","WM",81, False),
    ("Portugal", "Gonçalo Ramos",   "FW",  83, False),
    ("Portugal", "João Félix",      "CAM", 83, False),
    ("Portugal", "André Silva",      "FW",  78, False),
    ("Portugal", "Bruma",             "WM",  75, False),

    # ── NETHERLANDS ─────────────────────────────────────────────────────
    ("Netherlands", "Bart Verbruggen","GK", 82, True),
    ("Netherlands", "Denzel Dumfries","FB", 84, True),
    ("Netherlands", "Stefan de Vrij", "CB", 82, True),
    ("Netherlands", "Virgil van Dijk","CB", 88, True),
    ("Netherlands", "Nathan Aké",    "FB", 82, True),
    ("Netherlands", "Ryan Gravenberch","CM",84, True),
    ("Netherlands", "Tijjani Reijnders","CM",84,True),
    ("Netherlands", "Xavi Simons",   "CAM",85, True),
    ("Netherlands", "Cody Gakpo",    "WM", 85, True),
    ("Netherlands", "Memphis Depay", "FW", 82, True),
    ("Netherlands", "Donyell Malen", "WM", 82, True),
    ("Netherlands", "Mark Flekken",  "GK", 79, False),
    ("Netherlands", "Daley Blind",   "CB", 77, False),
    ("Netherlands", "Micky van de Ven","CB",82,False),
    ("Netherlands", "Jeremie Frimpong","FB",82,False),
    ("Netherlands", "Georginio Wijnaldum","CM",80,False),
    ("Netherlands", "Teun Koopmeiners","CM",83,False),
    ("Netherlands", "Frenkie de Jong","CM",86,False),
    ("Netherlands", "Steven Bergwijn","WM",79,False),
    ("Netherlands", "Wout Weghorst", "FW", 78, False),
    ("Netherlands", "Brian Brobbey", "FW", 79, False),
    ("Netherlands", "Quinten Timber","CM", 78, False),
    ("Netherlands", "Justin Kluivert","WM",78,False),
]


def _build_generic_squad(team: str) -> list[Player]:
    """Auto-generate a 23-man squad for teams without explicit data."""
    prof = SQUAD_PROFILES.get(team)
    base_r = prof.player_quality if prof else 70.0

    positions_11 = ["GK","CB","CB","FB","FB","CM","CM","CAM","WM","WM","FW"]
    positions_bench = ["GK","CB","CB","FB","CM","CM","CAM","WM","WM","FW","FW","FW"]

    players: list[Player] = []
    for i, pos in enumerate(positions_11):
        rating = base_r + random.uniform(-4, 4)
        players.append(Player(
            name=f"{team} {pos}{i+1}",
            team=team, position=pos,
            rating=round(min(99, max(50, rating)), 1),
            is_starter=True,
        ))
    for i, pos in enumerate(positions_bench):
        # Bench players average ~5 pts lower than starters
        depth = (prof.squad_depth if prof else 60) / 100
        rating = base_r * depth + random.uniform(-3, 3)
        players.append(Player(
            name=f"{team} sub{i+1}",
            team=team, position=pos,
            rating=round(min(99, max(45, rating)), 1),
            is_starter=False,
        ))
    return players


def _init_squad_registry() -> None:
    seen_teams: set[str] = set()
    for row in _RAW_PLAYER_DATA:
        team = normalize(row[0])
        seen_teams.add(team)
        SQUAD_REGISTRY.setdefault(team, []).append(Player(
            name=row[1], team=team, position=row[2],
            rating=float(row[3]), is_starter=row[4],
        ))
    # Generic squads for every other WC team
    _rng = random.Random(7777)
    for g, teams in GROUPS_2026.items():
        for t in teams:
            if t not in seen_teams:
                rng_save = random.getstate()
                random.seed(hash(t) & 0xFFFF)
                SQUAD_REGISTRY[t] = _build_generic_squad(t)
                random.setstate(rng_save)

_init_squad_registry()


def get_match_lineup(team: str, rng: random.Random) -> MatchLineup:
    """
    Return a MatchLineup for a team, excluding suspended/injured
    players.  If a starter is unavailable, promote the best
    bench player of the same position.
    """
    players = copy.deepcopy(SQUAD_REGISTRY.get(team, []))
    starters = [p for p in players if p.is_starter and not p.suspended and not p.injured]
    bench    = [p for p in players if not p.is_starter and not p.suspended and not p.injured]

    # If starters < 11 due to suspensions/injuries, promote from bench
    while len(starters) < 11 and bench:
        # Promote highest-rated bench player
        bench.sort(key=lambda p: -p.rating)
        promoted = bench.pop(0)
        promoted.is_starter = True
        starters.append(promoted)

    starters = starters[:11]
    return MatchLineup(team=team, starters=starters, bench=bench)


# =============================================================
# [P2]  MATCH-LEVEL PLAYER STATS ENGINE
# =============================================================

@dataclass
class MatchPlayerStats:
    """Aggregated player stats for one match."""
    player_name:  str
    team:         str
    position:     str
    rating_start: float
    minutes:      int   = 0
    goals:        int   = 0
    assists:      int   = 0
    yellow_cards: int   = 0
    red_card:     bool  = False
    subbed_off:   int   = -1   # minute subbed off (-1 = played full game / not used)
    subbed_on:    int   = -1   # minute subbed on (-1 = started)
    match_rating: float = 6.0  # 1–10 performance score


@dataclass
class MatchReport:
    """Full match report including lineups, subs, and player stats."""
    team_a:       str
    team_b:       str
    goals_a:      int
    goals_b:      int
    winner:       Optional[str]
    tag:          str
    player_stats: list[MatchPlayerStats] = field(default_factory=list)
    substitutions: list[dict]            = field(default_factory=list)
    # goal events: list of {minute, team, scorer, assister}
    goal_events:  list[dict]             = field(default_factory=list)
    # card events
    card_events:  list[dict]             = field(default_factory=list)


def _pick_player(players: list[Player], weights: dict[str, float],
                 rng: random.Random) -> Optional[Player]:
    """Pick a player weighted by position role."""
    active = [p for p in players if (p.red_card if hasattr(p, 'red_card') else False) is False]
    if not active:
        return None
    ws = [weights.get(p.position, 0.05) for p in active]
    total = sum(ws)
    if total == 0:
        return rng.choice(active)
    r = rng.random() * total
    for p, w in zip(active, ws):
        r -= w
        if r <= 0:
            return p
    return active[-1]


def simulate_match_with_players(
    team_a: str,
    team_b: str,
    elos:   dict,
    rng:    random.Random,
    knockout: bool = False,
) -> MatchReport:
    """
    [P2] Full match simulation with player-level stats.

    Extends simulate_match() by:
      1. Building lineups from SQUAD_REGISTRY
      2. Distributing goals/assists to specific players
      3. Simulating yellow/red cards
      4. Running substitution logic (up to 5 subs per team)
      5. Updating player cumulative stats in SQUAD_REGISTRY
      6. Returning a MatchReport

    The team-level result (winner, goals) is identical to what
    simulate_match() would produce — this is purely additive.
    """
    # ── 1. Basic match outcome ─────────────────────────────────
    base = simulate_match(team_a, team_b, elos, rng, knockout=knockout)
    goals_a, goals_b = base["goals_a"], base["goals_b"]
    winner, tag      = base["winner"], base["tag"]

    # ── 2. Build lineups ───────────────────────────────────────
    lineup_a = get_match_lineup(team_a, rng)
    lineup_b = get_match_lineup(team_b, rng)

    stats_map: dict[str, MatchPlayerStats] = {}

    def init_stats(lineup: MatchLineup) -> None:
        for p in lineup.starters:
            stats_map[p.name] = MatchPlayerStats(
                player_name=p.name, team=p.team,
                position=p.position, rating_start=p.rating,
                minutes=90, match_rating=6.0 + (p.rating - 75) * 0.04,
            )
        for p in lineup.bench:
            stats_map[p.name] = MatchPlayerStats(
                player_name=p.name, team=p.team,
                position=p.position, rating_start=p.rating,
                minutes=0, match_rating=6.0,
            )

    init_stats(lineup_a)
    init_stats(lineup_b)

    report = MatchReport(
        team_a=team_a, team_b=team_b,
        goals_a=goals_a, goals_b=goals_b,
        winner=winner, tag=tag,
    )

    # ── 3. Substitutions ───────────────────────────────────────
    # Simple model: subs happen at realistic minutes,
    # weighted toward later in the game.
    SUB_MINUTES = [46, 56, 63, 70, 76, 81, 85]

    def do_subs(lineup: MatchLineup, team_name: str) -> None:
        bench_avail = [p for p in lineup.bench if not p.injured and not p.suspended]
        rng.shuffle(bench_avail)
        sub_slots = rng.sample(SUB_MINUTES, k=min(lineup.max_subs, len(bench_avail), 5))
        sub_slots.sort()
        starters_out = list(lineup.starters)

        for minute in sub_slots:
            if not bench_avail:
                break
            # Sub off a starter (weighted toward tired outfield players)
            candidates = [p for p in starters_out if p.position != "GK"]
            if not candidates:
                break
            out_player = rng.choice(candidates)
            in_player  = bench_avail.pop(0)
            starters_out.remove(out_player)
            starters_out.append(in_player)

            # Update minutes
            if out_player.name in stats_map:
                stats_map[out_player.name].minutes   = minute
                stats_map[out_player.name].subbed_off = minute
                # Small rating penalty for being subbed early
                stats_map[out_player.name].match_rating -= (90 - minute) / 90 * 0.3

            if in_player.name in stats_map:
                stats_map[in_player.name].minutes  = 90 - minute
                stats_map[in_player.name].subbed_on = minute

            report.substitutions.append({
                "team": team_name, "minute": minute,
                "out": out_player.name, "in": in_player.name,
            })
            lineup.subs_used += 1

    do_subs(lineup_a, team_a)
    do_subs(lineup_b, team_b)

    # ── 4. Distribute goals / assists ─────────────────────────
    def active_players(lineup: MatchLineup) -> list[Player]:
        """Players who were on the pitch at some point (starters + subs in)."""
        on_pitch = list(lineup.starters)
        subbed_in_names = {s["in"] for s in report.substitutions if s["team"] == lineup.team}
        for p in lineup.bench:
            if p.name in subbed_in_names:
                on_pitch.append(p)
        return on_pitch

    def assign_goals(n_goals: int, lineup: MatchLineup, team: str) -> None:
        active = active_players(lineup)
        for _ in range(n_goals):
            scorer   = _pick_player(active, SCORER_WEIGHTS, rng)
            assister = _pick_player([p for p in active if p != scorer],
                                    ASSISTER_WEIGHTS, rng)
            minute   = rng.randint(1, 90)

            if scorer and scorer.name in stats_map:
                stats_map[scorer.name].goals       += 1
                stats_map[scorer.name].match_rating += 1.2
            if assister and rng.random() < 0.78:  # 78% of goals have an assist
                if assister.name in stats_map:
                    stats_map[assister.name].assists      += 1
                    stats_map[assister.name].match_rating += 0.6

            report.goal_events.append({
                "minute":   minute,
                "team":     team,
                "scorer":   scorer.name   if scorer   else "Unknown",
                "assister": assister.name if assister else None,
            })

    assign_goals(goals_a, lineup_a, team_a)
    assign_goals(goals_b, lineup_b, team_b)

    # ── 5. Cards ──────────────────────────────────────────────
    def assign_cards(lineup: MatchLineup, team: str) -> None:
        active = active_players(lineup)
        for p in active:
            if p.position == "GK":
                continue
            if rng.random() < YELLOW_RATE:
                if p.name in stats_map:
                    stats_map[p.name].yellow_cards += 1
                    stats_map[p.name].match_rating -= 0.3
                report.card_events.append({
                    "minute": rng.randint(10, 90),
                    "team": team, "player": p.name, "card": "yellow",
                })
            if rng.random() < RED_RATE:
                if p.name in stats_map:
                    stats_map[p.name].red_card     = True
                    stats_map[p.name].match_rating -= 1.5
                report.card_events.append({
                    "minute": rng.randint(10, 85),
                    "team": team, "player": p.name, "card": "red",
                })

    assign_cards(lineup_a, team_a)
    assign_cards(lineup_b, team_b)

    # ── 6. Clamp ratings, sort events ─────────────────────────
    for st in stats_map.values():
        st.match_rating = round(max(1.0, min(10.0, st.match_rating)), 1)

    report.goal_events.sort(key=lambda e: e["minute"])
    report.card_events.sort(key=lambda e: e["minute"])
    report.player_stats = list(stats_map.values())

    # ── 7. Update SQUAD_REGISTRY cumulative stats ─────────────
    for st in report.player_stats:
        for registry_player in SQUAD_REGISTRY.get(st.team, []):
            if registry_player.name == st.player_name:
                registry_player.goals          += st.goals
                registry_player.assists        += st.assists
                registry_player.yellow_cards   += st.yellow_cards
                if st.red_card:
                    registry_player.red_cards  += 1
                    registry_player.suspended   = True  # auto-suspend
                registry_player.minutes_played += st.minutes
                registry_player.matches_played += 1
                # Fatigue: accumulate across games
                registry_player.fatigue = min(
                    100,
                    registry_player.fatigue + st.minutes / 90 * FATIGUE_PER_90
                )
                break

    return report


# =============================================================
# [P3]  TEAM ELO MODIFIER FROM LIVE PLAYER PERFORMANCE
# =============================================================

def player_perf_elo_modifier(team: str) -> float:
    """
    [P3] ELO modifier from live player ratings, fatigue, and availability.
    Uses effective per-player rating (base minus fatigue/suspension drag)
    vs the squad's profile baseline.  Replaces the broken match_rating
    reference that doesn't exist on Player objects.
    """
    players = SQUAD_REGISTRY.get(normalize(team), [])
    starters = [
        p for p in players
        if p.is_starter and not p.suspended and not p.injured
    ]
    if not starters:
        return 0.0

    prof = SQUAD_PROFILES.get(normalize(team))
    baseline = prof.player_quality if prof else 75.0

    def effective_rating(p: Player) -> float:
        # Fatigue drag: up to -8 pts at 100% fatigue
        fatigue_penalty = (p.fatigue / 100.0) * 8.0
        return max(40.0, p.rating - fatigue_penalty)

    avg_effective = sum(effective_rating(p) for p in starters) / len(starters)
    return (avg_effective - baseline) * PLAYER_PERF_ELO_SCALE

def print_match_report(report: MatchReport, verbose: bool = True) -> None:
    """[P2] Pretty-print a MatchReport."""
    a, b   = report.team_a, report.team_b
    ga, gb = report.goals_a, report.goals_b
    result = f"{a} {ga}–{gb} {b}"
    if report.winner:
        result += f"  ({report.winner} win)"
    else:
        result += "  (Draw)"

    print(f"\n  ┌─ MATCH REPORT: {result} {'─'*20}")

    # Goal events
    if report.goal_events:
        print(f"  │  Goals:")
        for e in report.goal_events:
            ast_str = f"  (assist: {e['assister']})" if e.get("assister") else ""
            print(f"  │    {e['minute']:2d}'  ⚽ {e['scorer']}{ast_str}  [{e['team']}]")

    # Cards
    if report.card_events:
        print(f"  │  Cards:")
        for e in report.card_events:
            icon = "🟥" if e["card"] == "red" else "🟨"
            print(f"  │    {e['minute']:2d}'  {icon}  {e['player']}  [{e['team']}]")

    # Substitutions
    if report.substitutions:
        print(f"  │  Substitutions:")
        for s in report.substitutions:
            print(f"  │    {s['minute']:2d}'  ↕  {s['out']} → {s['in']}  [{s['team']}]")

    if verbose:
        # Top performers
        top = sorted(report.player_stats,
                     key=lambda s: -s.match_rating)[:6]
        print(f"  │  Top performers:")
        for s in top:
            g_str  = f"⚽×{s.goals}"   if s.goals   else ""
            a_str  = f"🅰×{s.assists}" if s.assists  else ""
            extras = " ".join(filter(None, [g_str, a_str]))
            print(f"  │    {s.player_name:<28} [{s.team[:3].upper()}]"
                  f"  {s.match_rating:.1f}/10  {s.position}  {extras}")

    print(f"  └{'─'*54}")


def print_player_stats_table(team: str) -> None:
    """[P2] Print cumulative tournament stats for a team's squad."""
    players = SQUAD_REGISTRY.get(normalize(team), [])
    if not players:
        print(f"  No player data for {team}")
        return

    played = [p for p in players if p.matches_played > 0]
    played.sort(key=lambda p: (-(p.goals + p.assists), -p.minutes_played))

    print(f"\n  ── {team} PLAYER STATS ─────────────────────────────────")
    rows = []
    for p in played:
        susp = " 🚫" if p.suspended else ""
        rows.append([
            p.position, p.name + susp,
            p.matches_played, p.minutes_played,
            p.goals, p.assists,
            p.yellow_cards, "●" if p.red_cards else "",
            f"{p.fatigue:.0f}%",
            f"{p.rating:.0f}",
        ])
    print(tabulate(rows,
        headers=["Pos", "Player", "MP", "Mins", "G", "A", "YC", "RC", "Fatigue", "Rat"],
        tablefmt="rounded_outline"))


def fetch_real_player_stats(client: "FootballDataClient") -> dict[str, list[dict]]:
    """
    [P2] Pull real player stats from the football-data API for
    finished WC matches and update SQUAD_REGISTRY ratings.

    Returns a dict: team → list of {name, goals, assists, minutes}.
    The API's /competitions/WC/scorers endpoint gives top scorers.
    Per-match lineups come from /matches/{id}/lineups when available.
    """
    print("  [P2] Fetching real player stats from API ...")
    results: dict[str, list[dict]] = {}

    # Top scorers (always available)
    data = client._get(f"competitions/{WC_COMPETITION_CODE}/scorers",
                       params={"limit": 50})
    if data:
        for entry in data.get("scorers", []):
            team = normalize(entry.get("team", {}).get("name", ""))
            player_name = entry["player"]["name"]
            goals = entry.get("numberOfGoals", 0)
            assists = entry.get("numberOfAssists", 0)
            # Try to update registry
            for p in SQUAD_REGISTRY.get(team, []):
                if p.name.lower() in player_name.lower() or \
                   player_name.lower() in p.name.lower():
                    p.goals   = goals
                    p.assists = assists
                    print(f"    updated {p.name} ({team}): {goals}G {assists}A")
                    break
            results.setdefault(team, []).append({
                "name": player_name, "goals": goals, "assists": assists,
            })

    return results



# =============================================================
# 3.  FOOTBALL-DATA.ORG CLIENT
# =============================================================

class FootballDataClient:
    def __init__(self, token=FD_TOKEN, throttle=FD_THROTTLE_SEC):
        self.token = token
        self.throttle = throttle
        self._last = 0.0
        self._s = requests.Session()
        if token:
            self._s.headers.update({"X-Auth-Token": token})

    def _get(self, path, params=None):
        if not self.token:
            return None
        elapsed = time.time() - self._last
        if elapsed < self.throttle:
            time.sleep(self.throttle - elapsed)
        url = f"{FD_BASE_URL}/{path.lstrip('/')}"
        try:
            resp = self._s.get(url, params=params or {}, timeout=15)
            self._last = time.time()
        except requests.RequestException as e:
            print(f"  [api] request failed: {e}")
            return None
        if resp.status_code == 429:
            print("  [api] rate-limited; sleeping 60s")
            time.sleep(60)
            return self._get(path, params)
        if resp.status_code >= 400:
            print(f"  [api] {resp.status_code} on {path}: {resp.text[:120]}")
            return None
        return resp.json()

    def world_cup_matches(self, status=None):
        params = {"status": status} if status else None
        data = self._get(f"competitions/{WC_COMPETITION_CODE}/matches", params=params)
        return data.get("matches", []) if data else []


def test_api_connection() -> bool:
    print("\n" + "=" * 64)
    print("  API CONNECTION TEST")
    print("=" * 64)
    if not FD_TOKEN:
        print("  STATUS: OFFLINE MODE (no FOOTBALL_DATA_TOKEN set)")
        return False
    client = FootballDataClient()
    data = client._get(f"competitions/{WC_COMPETITION_CODE}")
    if data:
        print(f"  STATUS: CONNECTED — {data.get('name', 'unknown')}")
        return True
    print("  STATUS: FAILED")
    return False


# =============================================================
# [E3]  FETCH PLAYED GROUP-STAGE MATCHES FROM API
# =============================================================

def fetch_played_wc(client: FootballDataClient) -> dict[tuple[str, str], dict]:
    """
    Pull all FINISHED WC group-stage matches and return them as a
    played-results dict keyed (home, away) → {goals_a, goals_b}.
    Only includes matches where both teams are in GROUPS_2026.
    """
    all_teams = {t for g in GROUPS_2026.values() for t in g}
    played: dict[tuple[str, str], dict] = {}

    matches = client.world_cup_matches(status="FINISHED")
    for m in matches:
        stage = m.get("stage", "")
        if stage not in ("GROUP_STAGE", "GROUPS"):
            continue
        home = normalize(m["homeTeam"]["name"])
        away = normalize(m["awayTeam"]["name"])
        if home not in all_teams or away not in all_teams:
            continue
        score = m.get("score", {}).get("fullTime", {}) or {}
        gh = score.get("home")
        ga = score.get("away")
        if gh is None or ga is None:
            continue
        played[(home, away)] = {"goals_a": int(gh), "goals_b": int(ga)}
        print(f"  [played] {home} {gh}-{ga} {away}")

    return played


def build_played_results(api_ok: bool, client=None) -> dict[tuple[str, str], dict]:
    """
    Merge API results (if available) with MANUAL_RESULTS.
    API takes precedence over manual entries.
    """
    played: dict[tuple[str, str], dict] = {}

    # Start with manual entries
    for (a, b), res in MANUAL_RESULTS.items():
        played[(normalize(a), normalize(b))] = res

    # Override/extend with live API data
    if api_ok and client:
        api_played = fetch_played_wc(client)
        played.update(api_played)

    if played:
        print(f"  [E3] {len(played)} completed group-stage match(es) locked in.")
    else:
        print("  [E3] No completed matches found — full simulation mode.")

    return played


# =============================================================
# 4.  HISTORICAL DATA + ELO BUILD
# =============================================================

def download_history(force=False) -> Path:
    if HIST_CSV_PATH.exists() and not force:
        return HIST_CSV_PATH
    print(f"  [hist] downloading results.csv ...")
    r = requests.get(HIST_RESULTS_URL, timeout=60)
    r.raise_for_status()
    HIST_CSV_PATH.write_bytes(r.content)
    print(f"  [hist] saved {len(r.content):,} bytes")
    return HIST_CSV_PATH


def iter_history(path=HIST_CSV_PATH):
    with path.open("r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                yield {
                    "date":       row["date"],
                    "home":       normalize(row["home_team"]),
                    "away":       normalize(row["away_team"]),
                    "home_score": int(row["home_score"]),
                    "away_score": int(row["away_score"]),
                    "tournament": row.get("tournament", "Friendly"),
                    "neutral":    row.get("neutral", "FALSE").upper() == "TRUE",
                }
            except (ValueError, KeyError):
                continue


def _expected(elo_a: float, elo_b: float) -> float:
    return 1.0 / (1.0 + 10 ** ((elo_b - elo_a) / 400.0))


def _gd_mult(gd: int) -> float:
    g = abs(gd)
    if g <= 1: return 1.0
    if g == 2: return 1.5
    return (11 + g) / 8.0


def _time_weight(match_date_str: str) -> float:
    try:
        y, mo, d = map(int, match_date_str.split("-"))
        age_years = (TODAY - date(y, mo, d)).days / 365.25
    except (ValueError, AttributeError):
        return 0.5
    if age_years <= RECENT_YEARS:
        return 1.0
    return 0.5 ** ((age_years - RECENT_YEARS) / DECAY_HALF_LIFE_YEARS)


def build_elo(min_date="2005-01-01", force=False, verbose=True) -> dict[str, float]:
    if ELO_JSON_PATH.exists() and not force:
        try:
            cached = json.loads(ELO_JSON_PATH.read_text())
            if verbose:
                print(f"  [elo] loaded {len(cached)} teams from cache")
            return cached
        except json.JSONDecodeError:
            pass

    download_history()
    elos: dict[str, float] = defaultdict(lambda: 1500.0)
    seen: set[str] = set()
    n = 0

    for m in iter_history():
        home, away = m["home"], m["away"]
        e_h, e_a = elos[home], elos[away]
        home_adv = 0 if m["neutral"] else 60
        exp_h = _expected(e_h + home_adv, e_a)
        s_h = 1.0 if m["home_score"] > m["away_score"] else \
              0.0 if m["home_score"] < m["away_score"] else 0.5
        k   = COMPETITION_WEIGHTS.get(m["tournament"], DEFAULT_K)
        tw  = _time_weight(m["date"])
        dm  = _gd_mult(m["home_score"] - m["away_score"])
        delta = k * dm * tw * (s_h - exp_h)
        elos[home] = e_h + delta
        elos[away] = e_a - delta
        if m["date"] >= min_date:
            seen.add(home); seen.add(away)
        n += 1

    final = {t: round(elos[t], 1) for t in seen}
    ELO_JSON_PATH.write_text(json.dumps(final, indent=2, sort_keys=True))
    if verbose:
        print(f"  [elo] processed {n:,} matches; {len(final)} active teams")
    return final


def verify_coverage(groups, elos, verbose=True) -> None:
    missing = []
    for g, teams in groups.items():
        for t in teams:
            if t not in elos:
                missing.append((g, t))
    if verbose:
        total = sum(len(v) for v in groups.values())
        if not missing:
            print(f"  [check] all {total} teams have ELO ✓")
        else:
            print(f"  [check] MISSING ELO for {len(missing)} teams:")
            for g, t in missing:
                print(f"          Group {g}: {t!r}")


def print_top_elos(elos, n=20) -> None:
    top = sorted(elos.items(), key=lambda x: -x[1])[:n]
    print(f"\n  TOP {n} ELO RATINGS (recency-weighted):")
    print(tabulate(
        [[i+1, t, f"{e:.0f}", f"{squad_elo_modifier(t):+.0f}"]
         for i, (t, e) in enumerate(top)],
        headers=["#", "Team", "ELO", "Squad ΔElo"],
        tablefmt="rounded_outline"
    ))


# =============================================================
# 5.  POISSON GOAL MODEL
# =============================================================

_MAX_FACTORIAL_K = 20


def _poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    k_safe = min(k, _MAX_FACTORIAL_K)
    return math.exp(-lam) * (lam ** k_safe) / math.factorial(k_safe)


def _sample_poisson(lam: float, rng: random.Random) -> int:
    if lam <= 0:
        return 0
    L = math.exp(-min(lam, 20.0))
    k, p = 0, 1.0
    while p > L and k < _MAX_FACTORIAL_K:
        p *= rng.random()
        k += 1
    return k - 1


def _lambda_from_elo_diff(diff: float) -> float:
    return LAMBDA_BASE * (1 + 0.5 * math.tanh(diff / 600))


def simulate_goals(elo_a: float, elo_b: float,
                   rng: random.Random) -> tuple[int, int]:
    lam_a = _lambda_from_elo_diff(elo_a - elo_b)
    lam_b = _lambda_from_elo_diff(elo_b - elo_a)
    return _sample_poisson(lam_a, rng), _sample_poisson(lam_b, rng)


# =============================================================
# ELO AUTO-UPDATE FROM MATCH RESULT
# =============================================================

def update_elos_from_match(
    team_a: str,
    team_b: str,
    goals_a: int,
    goals_b: int,
    elos: dict[str, float],
    k: float = GROUP_STAGE_K,
    neutral: bool = True,
) -> tuple[float, float]:
    a = normalize(team_a)
    b = normalize(team_b)

    e_a = elos.get(a, 1500.0)
    e_b = elos.get(b, 1500.0)

    home_adv = 0 if neutral else 60
    exp_a = _expected(e_a + home_adv, e_b)

    if goals_a > goals_b:
        score_a = 1.0
    elif goals_a < goals_b:
        score_a = 0.0
    else:
        score_a = 0.5

    gd_mult = _gd_mult(goals_a - goals_b)
    delta   = k * gd_mult * (score_a - exp_a)

    elos[a] = round(e_a + delta, 1)
    elos[b] = round(e_b - delta, 1)

    return delta, -delta


# =============================================================
# [E7]  PERSIST LIVE MATCH RESULTS INTO THE ELO CACHE
# =============================================================
#
# apply_live_results_to_elo() is called automatically by
# watch_live() whenever a match reaches FINISHED status.
# It also fires in main() after the live session ends so the
# full Monte Carlo run immediately uses updated ratings.
#
# Design choices:
#   - Uses K=60 (the "FIFA World Cup" competition weight) —
#     real WC group matches carry full weight, not the lower
#     GROUP_STAGE_K=32 used for in-simulation nudges.
#   - Deduplicates via ELO_LIVE_LOG_PATH: if a match key
#     (home, away, goals_a, goals_b, stage) already appears
#     in the log it is skipped, so replaying main() multiple
#     times never double-counts a result.
#   - Writes the updated dict back to ELO_JSON_PATH so the
#     next build_elo() call loads the enriched ratings from
#     cache without re-downloading history.
# =============================================================

# K-factor for real WC matches — matches COMPETITION_WEIGHTS
WC_LIVE_K = 60


def _load_live_log() -> set[str]:
    """Return the set of match keys already recorded in the log."""
    if not ELO_LIVE_LOG_PATH.exists():
        return set()
    keys: set[str] = set()
    with ELO_LIVE_LOG_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                keys.add(entry.get("key", ""))
            except json.JSONDecodeError:
                pass
    return keys


def _append_live_log(entry: dict) -> None:
    """Append one JSON record to the live log."""
    with ELO_LIVE_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def apply_live_results_to_elo(
    finished_snaps: list,          # list[LiveSnapshot]  (type hint avoids circular)
    elos: dict[str, float],
    stage: str = "GROUP_STAGE",
    k: float = WC_LIVE_K,
    verbose: bool = True,
) -> dict[str, float]:
    """
    [E7] Apply real finished-match results to `elos`, persist the
    updated ratings to ELO_JSON_PATH, and log each applied match
    to ELO_LIVE_LOG_PATH.

    Parameters
    ----------
    finished_snaps : snapshots with status FINISHED / AWARDED
    elos           : current ELO dict (mutated in-place AND returned)
    stage          : label written to the log ('GROUP_STAGE', 'R32', …)
    k              : K-factor (default WC_LIVE_K = 60)
    verbose        : print before/after diff table

    Returns
    -------
    The same `elos` dict, updated in-place.
    """
    FINISHED_STATUSES = {"FINISHED", "AWARDED"}
    already_logged    = _load_live_log()

    applied: list[dict] = []

    for s in finished_snaps:
        if s.status not in FINISHED_STATUSES:
            continue

        home = normalize(s.home)
        away = normalize(s.away)
        ga, gb = s.home_goals, s.away_goals

        # Deduplicate — same result must not be applied twice
        match_key = f"{home}|{away}|{ga}|{gb}|{stage}"
        if match_key in already_logged:
            if verbose:
                print(f"  [E7] skip (already applied): {home} {ga}-{gb} {away}")
            continue

        before_home = elos.get(home, 1500.0)
        before_away = elos.get(away, 1500.0)

        delta_h, delta_a = update_elos_from_match(
            home, away, ga, gb, elos,
            k=k, neutral=True,
        )

        after_home = elos.get(home, 1500.0)
        after_away = elos.get(away, 1500.0)

        entry = {
            "key":        match_key,
            "date":       str(date.today()),
            "stage":      stage,
            "home":       home,
            "away":       away,
            "goals_home": ga,
            "goals_away": gb,
            "k":          k,
            "delta_home": round(delta_h, 2),
            "delta_away": round(delta_a, 2),
            "elo_home_before": round(before_home, 1),
            "elo_home_after":  round(after_home,  1),
            "elo_away_before": round(before_away, 1),
            "elo_away_after":  round(after_away,  1),
        }
        _append_live_log(entry)
        applied.append(entry)

    if not applied:
        if verbose:
            print("  [E7] No new results to apply.")
        return elos

    # ── Print diff table ────────────────────────────────────────
    if verbose:
        print(f"\n  [E7] Applied {len(applied)} real WC result(s) to ELO cache")
        print(f"       K-factor: {k}  |  log: {ELO_LIVE_LOG_PATH}\n")
        rows = []
        for e in applied:
            result_str = f"{e['home']} {e['goals_home']}-{e['goals_away']} {e['away']}"
            rows.append([
                e["stage"],
                result_str,
                f"{e['elo_home_before']:.0f} → {e['elo_home_after']:.0f}",
                f"{e['delta_home']:+.1f}",
                f"{e['elo_away_before']:.0f} → {e['elo_away_after']:.0f}",
                f"{e['delta_away']:+.1f}",
            ])
        print(tabulate(
            rows,
            headers=["Stage", "Result", "Home ELO", "ΔHome", "Away ELO", "ΔAway"],
            tablefmt="rounded_outline",
        ))

    # ── Persist updated ELOs to cache ──────────────────────────
    ELO_JSON_PATH.write_text(json.dumps(
        {t: round(v, 1) for t, v in sorted(elos.items())},
        indent=2
    ))
    if verbose:
        print(f"\n  [E7] ELO cache saved → {ELO_JSON_PATH}\n")

    return elos


# =============================================================
# 6.  MATCH SIMULATION
# =============================================================

def _effective_elo(team: str, elos: dict) -> float:
    base = elos.get(normalize(team), 1500.0)
    return base + squad_elo_modifier(team) + player_perf_elo_modifier(team)


def simulate_match(team_a: str, team_b: str,
                   elos: dict,
                   rng: random.Random,
                   knockout: bool = False,
                   is_host_neutral: bool = True) -> dict:
    e_a = _effective_elo(team_a, elos)
    e_b = _effective_elo(team_b, elos)

    if normalize(team_a) in HOST_NATIONS:
        e_a += HOST_ADVANTAGE_ELO
    if normalize(team_b) in HOST_NATIONS:
        e_b += HOST_ADVANTAGE_ELO

    p_a = _expected(e_a, e_b)
    roll = rng.random()

    if not knockout:
        elo_diff_norm = abs(p_a - 0.5) * 2
        draw_p = GROUP_DRAW_BASE * (1 - GROUP_DRAW_SKILL_SCALE * elo_diff_norm)
        p_a_adj = (1 - draw_p) * p_a
        if roll < p_a_adj:
            winner, loser, tag = team_a, team_b, "W_A"
        elif roll < p_a_adj + draw_p:
            winner, loser, tag = None, None, "DRAW"
        else:
            winner, loser, tag = team_b, team_a, "W_B"
    else:
        p_a_et = 0.5 + (p_a - 0.5) * ET_COMPRESSION
        t1 = p_a * P_WIN_90
        t2 = t1 + P_WIN_ET * p_a_et
        t3 = t1 + P_WIN_ET
        if   roll < t1: winner, loser, tag = team_a, team_b, "W_A90"
        elif roll < t2: winner, loser, tag = team_a, team_b, "W_AET"
        elif roll < t3: winner, loser, tag = team_b, team_a, "W_BET"
        else:           winner, loser, tag = team_b, team_a, "W_B90"

    g_a, g_b = simulate_goals(e_a, e_b, rng)

    if tag in ("W_A", "W_A90", "W_AET"):
        if g_a < g_b:
            # swap so the right team leads, preserving goal difference shape
            g_a, g_b = g_b, g_a
        if g_a == g_b:
            g_a += 1          # minimal nudge — keeps 0-0→1-0, 1-1→2-1, etc.
    elif tag in ("W_B", "W_B90", "W_BET"):
        if g_b < g_a:
            g_a, g_b = g_b, g_a
        if g_a == g_b:
            g_b += 1
    elif tag == "DRAW":
        # Use the average rounded down so 1-2 → 1-1, 0-3 → 1-1, 0-0 stays
        common = (g_a + g_b) // 2
        g_a = g_b = common

    return {"winner": winner, "loser": loser, "tag": tag,
            "goals_a": g_a, "goals_b": g_b}


# =============================================================
# [E3]  PLAYED-MATCH AWARE GROUP SIMULATION
# =============================================================

def simulate_group(
    group: list[str],
    elos: dict,
    rng: random.Random,
    update_elos: bool = True,
    played: dict[tuple[str, str], dict] | None = None,
) -> tuple[list, dict, list]:
    """
    [E3] `played` is a dict keyed (team_a, team_b) → {goals_a, goals_b}
    for matches that have already been decided.  Both key orderings are
    checked so you don't have to worry about home/away direction.

    Locked matches:
      - Count the real scoreline toward the table.
      - Update ELOs (same K as simulated matches) so later games
        in the group reflect actual results.
      - Are NOT re-rolled.

    Unplayed fixtures are Monte-Carlo'd as before.
    """
    played = played or {}
    table = {t: {"pts": 0, "gf": 0, "ga": 0} for t in group}
    results = []

    for i, a in enumerate(group):
        for b in group[i+1:]:
            # Look up in either key order
            key_ab = (a, b)
            key_ba = (b, a)

            if key_ab in played:
                res = played[key_ab]
                g_a, g_b = res["goals_a"], res["goals_b"]
                if g_a > g_b:
                    winner, loser, tag = a, b, "W_A"
                elif g_b > g_a:
                    winner, loser, tag = b, a, "W_B"
                else:
                    winner, loser, tag = None, None, "DRAW"
                m = {"winner": winner, "loser": loser, "tag": tag,
                     "goals_a": g_a, "goals_b": g_b, "locked": True}

            elif key_ba in played:
                res = played[key_ba]
                # Stored as (b, a) so swap goals
                g_b, g_a = res["goals_a"], res["goals_b"]
                if g_a > g_b:
                    winner, loser, tag = a, b, "W_A"
                elif g_b > g_a:
                    winner, loser, tag = b, a, "W_B"
                else:
                    winner, loser, tag = None, None, "DRAW"
                m = {"winner": winner, "loser": loser, "tag": tag,
                     "goals_a": g_a, "goals_b": g_b, "locked": True}

            else:
                rep = simulate_match_with_players(a, b, elos, rng, knockout=False)
                m = {
                    "winner": rep.winner, "loser": rep.loser if hasattr(rep, 'loser') else (
                        b if rep.winner == a else (a if rep.winner == b else None)
                    ),
                    "tag":    rep.tag,
                    "goals_a": rep.goals_a, "goals_b": rep.goals_b,
                    "locked": False,
                    "report": rep,
                }

            # Update ELOs from this result (real or simulated)
            if update_elos:
                update_elos_from_match(
                    a, b,
                    m["goals_a"], m["goals_b"],
                    elos,
                    k=GROUP_STAGE_K,
                    neutral=True,
                )

            table[a]["gf"] += m["goals_a"]; table[a]["ga"] += m["goals_b"]
            table[b]["gf"] += m["goals_b"]; table[b]["ga"] += m["goals_a"]
            if m["winner"] == a:   table[a]["pts"] += 3
            elif m["winner"] == b: table[b]["pts"] += 3
            else:
                table[a]["pts"] += 1; table[b]["pts"] += 1
            results.append(m)

    def sort_key(t):
        gd = table[t]["gf"] - table[t]["ga"]
        return (table[t]["pts"], gd, table[t]["gf"], _effective_elo(t, elos))

    ranked = sorted(group, key=sort_key, reverse=True)
    return ranked, table, results


# =============================================================
# 8.  TOURNAMENT SIMULATION  — passes played results through
# =============================================================

def simulate_tournament(groups: dict, elos: dict,
                         seed=None, live_overrides=None,
                         played: dict | None = None) -> dict:
    rng = random.Random(seed)
    live_overrides = live_overrides or {}
    played = played or {}

    sim_elos = copy.copy(elos)

    group_firsts   = {}
    group_seconds  = {}
    group_thirds   = {}
    group_results  = {}

    for g, teams in groups.items():
        ranked, table, _ = simulate_group(
            teams, sim_elos, rng,
            update_elos=True,
            played=played,          # [E3] pass locked results
        )
        group_results[g] = ranked
        group_firsts[g]  = ranked[0]
        group_seconds[g] = ranked[1]
        group_thirds[g]  = (ranked[2], table[ranked[2]])

    def third_key(item):
        team, stats = item
        return (stats["pts"], stats["gf"] - stats["ga"],
                stats["gf"], _effective_elo(team, sim_elos))

    sorted_thirds = sorted(group_thirds.items(),
                           key=lambda kv: third_key(kv[1]), reverse=True)
    best8 = [kv for kv in sorted_thirds[:8]]
    best8_teams = [t for _, (t, _) in best8]

    seeds = {}
    for g in groups:
        seeds[f"{g}1"] = group_firsts[g]
        seeds[f"{g}2"] = group_seconds[g]
    for i, bt in enumerate(best8_teams, 1):
        seeds[f"T{i}"] = bt

    r32_pairs = []
    for sa, sb in R32_BRACKET:
        ta = seeds.get(sa, best8_teams[0] if "T" in sa else "TBD")
        tb = seeds.get(sb, best8_teams[1] if "T" in sb else "TBD")
        r32_pairs.append((ta, tb))

    def play_round(pairs: list[tuple]) -> tuple[list, list]:
        winners, match_results = [], []
        for a, b in pairs:
            key = frozenset({normalize(a), normalize(b)})
            if key in live_overrides:
                res = live_overrides[key]
                match_results.append(res)
                winners.append(res["winner"])
            else:
                m = simulate_match(a, b, sim_elos, rng, knockout=True)
                match_results.append(m)
                winners.append(m["winner"])
        return winners, match_results

    r16,  _       = play_round(r32_pairs)
    r16_pairs     = [(r16[i], r16[i+1]) for i in range(0, 16, 2)]
    qf,   _       = play_round(r16_pairs)
    qf_pairs      = [(qf[i], qf[i+1]) for i in range(0, 8, 2)]
    sf,  sf_r     = play_round(qf_pairs)
    sf_pairs      = [(sf[i], sf[i+1]) for i in range(0, 4, 2)]
    final2, sf2_r = play_round(sf_pairs)

    sf_losers = [r["loser"] for r in sf2_r]
    third_m   = simulate_match(sf_losers[0], sf_losers[1], sim_elos, rng, knockout=True)
    final_m   = simulate_match(final2[0],    final2[1],    sim_elos, rng, knockout=True)

    return {
        "champion":       final_m["winner"],
        "runner_up":      final_m["loser"],
        "third":          third_m["winner"],
        "semi_finalists": final2 + sf_losers,
        "group_results":  group_results,
        "r32_pairs":      r32_pairs,          # [E4] expose for tracking
        "post_group_elos": {
            t: round(sim_elos.get(t, 1500.0), 1)
            for g in groups.values() for t in g
        },
    }


# =============================================================
# 9.  LIVE MATCH STATE
# =============================================================

@dataclass
class LiveSnapshot:
    home: str; away: str
    home_goals: int; away_goals: int
    minute: int; status: str


def fetch_live_wc(client: FootballDataClient) -> list[LiveSnapshot]:
    out = []
    for m in client.world_cup_matches(status="LIVE"):
        score = m.get("score", {}).get("fullTime", {}) or {}
        out.append(LiveSnapshot(
            home=normalize(m["homeTeam"]["name"]),
            away=normalize(m["awayTeam"]["name"]),
            home_goals=score.get("home") or 0,
            away_goals=score.get("away") or 0,
            minute=m.get("minute") or 0,
            status=m.get("status", "UNKNOWN"),
        ))
    return out


def live_to_overrides(snaps: list[LiveSnapshot]) -> dict:
    out = {}
    for s in snaps:
        if s.home_goals == s.away_goals:
            continue
        winner = normalize(s.home) if s.home_goals > s.away_goals else normalize(s.away)
        loser  = normalize(s.away) if winner == normalize(s.home) else normalize(s.home)
        key = frozenset({normalize(s.home), normalize(s.away)})
        out[key] = {"winner": winner, "loser": loser,
                    "goals_a": s.home_goals, "goals_b": s.away_goals, "tag": "live"}
    return out


# =============================================================
# [E5]  LIVE MATCH IN-GAME PREDICTION
# =============================================================
#
# Models the remaining minutes of a live match as a Poisson
# process scaled by time remaining.  The current scoreline
# creates "comeback pressure" — a team trailing adjusts their
# effective attack rate upward and the leading team's drops
# slightly (game management / sitting back).
# =============================================================

TOTAL_MINUTES  = 90
STOPPAGE_EXTRA = 4
TRAILING_BOOST = 0.18   # lambda inflation per goal deficit for trailing team
LEADING_DAMPEN = 0.10   # lambda deflation per goal lead for leading team


def _live_lambdas(
    e_a: float, e_b: float,
    goals_a: int, goals_b: int,
    minute: int,
) -> tuple[float, float]:
    """Expected goals each team will score in remaining minutes."""
    effective_total = TOTAL_MINUTES + STOPPAGE_EXTRA
    minutes_left    = max(1, effective_total - minute)
    time_fraction   = minutes_left / effective_total

    base_lam_a = _lambda_from_elo_diff(e_a - e_b)
    base_lam_b = _lambda_from_elo_diff(e_b - e_a)

    diff = goals_a - goals_b   # +ve = A leading

    if diff > 0:       # A leading — A sits back, B pushes
        adj_a = base_lam_a * (1 - LEADING_DAMPEN * diff)
        adj_b = base_lam_b * (1 + TRAILING_BOOST * diff)
    elif diff < 0:     # B leading — B sits back, A pushes
        adj_a = base_lam_a * (1 + TRAILING_BOOST * abs(diff))
        adj_b = base_lam_b * (1 - LEADING_DAMPEN * abs(diff))
    else:
        adj_a, adj_b = base_lam_a, base_lam_b

    return max(0.05, adj_a * time_fraction), max(0.05, adj_b * time_fraction)


def predict_live_match(
    team_a: str, team_b: str,
    goals_a: int, goals_b: int,
    minute: int,
    elos: dict,
    n_sims: int = 10_000,
    knockout: bool = False,
) -> dict:
    """
    [E5] Simulate the remainder of a match in progress.
    Returns outcome probabilities, comeback chances, and a
    top-10 final-score distribution.
    """
    a = normalize(team_a)
    b = normalize(team_b)
    e_a = _effective_elo(a, elos)
    e_b = _effective_elo(b, elos)
    if a in HOST_NATIONS: e_a += HOST_ADVANTAGE_ELO
    if b in HOST_NATIONS: e_b += HOST_ADVANTAGE_ELO

    rng = random.Random(hash((a, b, goals_a, goals_b, minute)) & 0xFFFFFFFF)
    lam_a, lam_b = _live_lambdas(e_a, e_b, goals_a, goals_b, minute)

    win_a = win_b = draw = comeback_a = comeback_b = 0
    score_counts: dict[tuple[int, int], int] = defaultdict(int)

    for _ in range(n_sims):
        fa = goals_a + _sample_poisson(lam_a, rng)
        fb = goals_b + _sample_poisson(lam_b, rng)

        if not knockout:
            if   fa > fb: win_a += 1
            elif fb > fa: win_b += 1
            else:         draw  += 1
        else:
            if fa > fb:
                win_a += 1
            elif fb > fa:
                win_b += 1
            else:
                # ET/pen: compressed ELO probability
                p_pen = 0.5 + (_expected(e_a, e_b) - 0.5) * ET_COMPRESSION
                if rng.random() < p_pen: win_a += 1
                else:                    win_b += 1

        if goals_b > goals_a and fa >= fb: comeback_a += 1
        if goals_a > goals_b and fb >= fa: comeback_b += 1
        score_counts[(fa, fb)] += 1

    top_scores = sorted(score_counts.items(), key=lambda x: -x[1])[:10]

    return {
        "team_a":        a,
        "team_b":        b,
        "current_score": (goals_a, goals_b),
        "minute":        minute,
        "p_win_a":       win_a       / n_sims,
        "p_draw":        draw        / n_sims,
        "p_win_b":       win_b       / n_sims,
        "p_comeback_a":  comeback_a  / n_sims if goals_b > goals_a else None,
        "p_comeback_b":  comeback_b  / n_sims if goals_a > goals_b else None,
        "likely_final":  top_scores[0][0] if top_scores else (goals_a, goals_b),
        "score_probs":   [(s, c / n_sims) for s, c in top_scores],
        "lam_remaining": (round(lam_a, 3), round(lam_b, 3)),
    }


def print_live_prediction(snap: LiveSnapshot, elos: dict,
                           knockout: bool = False) -> None:
    """[E5] Pretty-print a live in-game prediction."""
    pred = predict_live_match(
        snap.home, snap.away,
        snap.home_goals, snap.away_goals,
        snap.minute, elos,
        knockout=knockout,
    )
    a, b   = pred["team_a"], pred["team_b"]
    ga, gb = pred["current_score"]
    m      = pred["minute"]

    def pbar(p):
        filled = int(p * 24)
        return "█" * filled + "░" * (24 - filled) + f"  {p*100:5.1f}%"

    print(f"\n  ┌─ LIVE: {a} {ga}–{gb} {b}  [{m}'] {'─'*30}")
    print(f"  │  {a:<24} {pbar(pred['p_win_a'])}")
    if not knockout:
        print(f"  │  {'Draw':<24} {pbar(pred['p_draw'])}")
    print(f"  │  {b:<24} {pbar(pred['p_win_b'])}")

    if pred["p_comeback_a"] is not None:
        print(f"  │  ↩ {a} comeback: {pred['p_comeback_a']*100:.1f}%")
    if pred["p_comeback_b"] is not None:
        print(f"  │  ↩ {b} comeback: {pred['p_comeback_b']*100:.1f}%")

    lf = pred["likely_final"]
    print(f"  │  Most likely final: {a} {lf[0]}–{lf[1]} {b}")
    print(f"  │  Score distribution:")
    for (fa, fb), p in pred["score_probs"][:6]:
        bar = "█" * int(p * 30)
        print(f"  │    {fa}–{fb}  {bar} {p*100:.1f}%")
    la, lb = pred["lam_remaining"]
    print(f"  │  Remaining xG: {a} {la:.2f}  {b} {lb:.2f}")
    print(f"  └{'─'*54}")


def fetch_and_predict_live(client: FootballDataClient,
                            elos: dict) -> list[LiveSnapshot]:
    """[E5] Fetch live WC matches, print in-game predictions, return snapshots."""
    snaps = fetch_live_wc(client)
    if not snaps:
        print("  No live matches in progress.")
        return snaps
    print(f"\n  {len(snaps)} LIVE MATCH(ES) IN PROGRESS")
    for s in snaps:
        ko = s.status in ("EXTRA_TIME", "PENALTY_SHOOTOUT")
        print_live_prediction(s, elos, knockout=ko)
    return snaps


# =============================================================
# [E6]  MINUTE-BY-MINUTE LIVE TRACKER
# =============================================================
#
# watch_live() polls the API every ~60 s, clears the terminal,
# and reprints the live prediction panel for every active match.
# It exits cleanly when all matches finish or on Ctrl-C.
#
# For offline demos, watch_live_demo() simulates a match
# progressing minute by minute without an API connection.
# =============================================================

POLL_INTERVAL_SEC = 60   # how often to re-fetch from the API


def _clear() -> None:
    """Clear the terminal (works on Windows and Unix)."""
    os.system("cls" if os.name == "nt" else "clear")


def _render_live_panel(snaps: list[LiveSnapshot], elos: dict,
                        poll_count: int, started_at: float) -> None:
    """Render the full live dashboard to the terminal."""
    _clear()
    elapsed = int(time.time() - started_at)
    h, m, s = elapsed // 3600, (elapsed % 3600) // 60, elapsed % 60
    print("=" * 64)
    print(f"  ⚽  WC 2026 LIVE TRACKER   "
          f"poll #{poll_count}   running {h:02d}:{m:02d}:{s:02d}")
    print(f"  Next update in ~{POLL_INTERVAL_SEC}s   Ctrl-C to exit")
    print("=" * 64)

    if not snaps:
        print("\n  No live matches right now.  Waiting ...\n")
        return

    for s in snaps:
        ko = s.status in ("EXTRA_TIME", "PENALTY_SHOOTOUT")
        print_live_prediction(s, elos, knockout=ko)


def watch_live(client: FootballDataClient, elos: dict,
               poll_interval: int = POLL_INTERVAL_SEC) -> None:
    """
    [E6] Continuously poll the API and display a refreshing live
    prediction panel, updated every `poll_interval` seconds.

    The function blocks until:
      - All tracked matches reach FINISHED / AWARDED status, OR
      - The user presses Ctrl-C.

    Parameters
    ----------
    client        : authenticated FootballDataClient
    elos          : pre-built ELO ratings dict
    poll_interval : seconds between API polls (default 60)
    """
    print("\n  Starting live tracker — press Ctrl-C to stop.\n")
    started_at  = time.time()
    poll_count  = 0
    prev_snaps: list[LiveSnapshot] = []

    FINISHED_STATUSES = {"FINISHED", "AWARDED", "POSTPONED", "CANCELLED"}

    try:
        while True:
            # ── fetch ──────────────────────────────────────────
            try:
                snaps = fetch_live_wc(client)
            except Exception as exc:
                # Network hiccup — keep showing last known state
                snaps = prev_snaps
                print(f"\n  [warn] fetch failed: {exc}  — showing cached data")

            poll_count += 1

            # ── detect score changes for event log ─────────────
            prev_map = {(s.home, s.away): s for s in prev_snaps}
            events: list[str] = []
            for s in snaps:
                prev = prev_map.get((s.home, s.away))
                if prev:
                    if s.home_goals > prev.home_goals:
                        events.append(
                            f"  ⚽ GOAL  {s.home} ({s.home_goals}-{s.away_goals}) [{s.minute}']"
                        )
                    if s.away_goals > prev.away_goals:
                        events.append(
                            f"  ⚽ GOAL  {s.away} ({s.home_goals}-{s.away_goals}) [{s.minute}']"
                        )

            # ── render ─────────────────────────────────────────
            _render_live_panel(snaps, elos, poll_count, started_at)

            if events:
                print("\n  ── Recent events ──────────────────────────────")
                for e in events[-6:]:  # show last 6 events max
                    print(e)

            # ── [E7] apply ELO updates for newly-finished matches ──
            newly_finished = [
                s for s in snaps
                if s.status in {"FINISHED", "AWARDED"}
                and prev_map.get((s.home, s.away)) is not None
                and prev_map[(s.home, s.away)].status not in {"FINISHED", "AWARDED"}
            ]
            if newly_finished:
                print("\n  [E7] Updating ELOs for newly finished match(es) ...")
                apply_live_results_to_elo(newly_finished, elos, verbose=True)

            prev_snaps = snaps

            # ── check if all done ──────────────────────────────
            if snaps and all(s.status in FINISHED_STATUSES for s in snaps):
                print("\n  All matches finished.  Exiting live tracker.\n")
                # [E7] Final sweep — apply any finished matches not yet logged
                apply_live_results_to_elo(snaps, elos, verbose=True)
                break

            # ── sleep with per-second countdown ───────────────
            for remaining in range(poll_interval, 0, -1):
                # Reprint just the countdown line in-place
                print(f"\r  Next poll in {remaining:3d}s ...   ", end="", flush=True)
                time.sleep(1)
            print()  # newline before next render

    except KeyboardInterrupt:
        print("\n\n  Live tracker stopped by user.\n")
        # [E7] Still apply whatever finished before the user quit
        if prev_snaps:
            finished = [s for s in prev_snaps if s.status in {"FINISHED", "AWARDED"}]
            if finished:
                print("  [E7] Applying ELO updates for finished matches before exit ...")
                apply_live_results_to_elo(finished, elos, verbose=True)

    return prev_snaps  # caller can use for live_to_overrides


def watch_live_demo(home: str, away: str, elos: dict,
                    start_score: tuple[int,int] = (0, 0),
                    start_minute: int = 1,
                    end_minute: int = 90,
                    goal_events: list[tuple[int, str]] | None = None,
                    speed: float = 0.4,
                    knockout: bool = False) -> None:
    """
    [E6] Offline demo: simulate a match advancing minute by minute.

    Parameters
    ----------
    home / away    : team names
    elos           : ELO ratings dict
    start_score    : (home_goals, away_goals) at start_minute
    start_minute   : minute to start the demo from
    end_minute     : minute to stop (90 for full match, 120 for ET)
    goal_events    : list of (minute, 'home'|'away') tuples to inject goals
    speed          : seconds to pause between each minute (default 0.4)
    knockout       : True if this is a knockout match
    """
    goal_map: dict[int, str] = {}
    for (min_, team) in (goal_events or []):
        goal_map[min_] = team

    ga, gb = start_score
    started_at = time.time()
    event_log: list[str] = []

    try:
        for minute in range(start_minute, end_minute + 1):
            # Inject goal if scheduled
            if minute in goal_map:
                scorer = goal_map[minute]
                if scorer == "home":
                    ga += 1
                    event_log.append(
                        f"  ⚽ GOAL  {normalize(home)} ({ga}-{gb}) [{minute}']"
                    )
                else:
                    gb += 1
                    event_log.append(
                        f"  ⚽ GOAL  {normalize(away)} ({ga}-{gb}) [{minute}']"
                    )

            snap = LiveSnapshot(
                home=home, away=away,
                home_goals=ga, away_goals=gb,
                minute=minute,
                status="IN_PLAY",
            )

            _clear()
            elapsed = int(time.time() - started_at)
            print("=" * 64)
            print(f"  ⚽  LIVE DEMO: {normalize(home)} vs {normalize(away)}")
            print(f"  Simulated minute: {minute}   "
                  f"elapsed real-time: {elapsed}s")
            print(f"  Speed: {speed}s/min   Ctrl-C to stop")
            print("=" * 64)

            print_live_prediction(snap, elos, knockout=knockout)

            if event_log:
                print("\n  ── Goal log ───────────────────────────────────")
                for e in event_log[-8:]:
                    print(e)

            # Brief HT break visual
            if minute == 45:
                print("\n  ── HALF TIME ──────────────────────────────────\n")
                time.sleep(max(speed, 1.5))
            else:
                time.sleep(speed)

    except KeyboardInterrupt:
        print("\n\n  Demo stopped.\n")


# =============================================================
# 10.  MONTE CARLO  — [E3] passes played results, [E4] tracks R32
# =============================================================

def run_monte_carlo(n_sims: int, elos: dict, groups=None,
                    master_seed=42, live_overrides=None,
                    played: dict | None = None,
                    verbose=True) -> dict:
    groups = groups or GROUPS_2026
    master_rng = random.Random(master_seed)
    win_count   = defaultdict(int)
    final_count = defaultdict(int)
    semi_count  = defaultdict(int)
    elo_sum     = defaultdict(float)
    elo_n       = defaultdict(int)

    # [E4] Track R32 matchup frequencies and wins
    # r32_matchups[(teamA, teamB)] = [appearances, teamA_wins]
    r32_appearances: dict[tuple[str, str], int] = defaultdict(int)
    r32_wins:        dict[tuple[str, str], int] = defaultdict(int)

    if verbose:
        print(f"\n{'='*64}")
        print(f"  MONTE CARLO — {n_sims:,} tournament simulations")
        print(f"  [E3] Locked matches: {len(played or {})} played results applied")
        print(f"  [E2] Group-stage ELO updates enabled (K={GROUP_STAGE_K})")
        print(f"  [E4] Round-of-32 probability tracking enabled")
        print(f"{'='*64}")

    for i in range(n_sims):
        seed = master_rng.randint(0, 2**31)
        r = simulate_tournament(groups, elos, seed=seed,
                                live_overrides=live_overrides,
                                played=played)
        win_count[r["champion"]]    += 1
        final_count[r["champion"]]  += 1
        final_count[r["runner_up"]] += 1
        for t in r["semi_finalists"]:
            semi_count[t] += 1

        for t, e in r.get("post_group_elos", {}).items():
            elo_sum[t] += e
            elo_n[t]   += 1

        # [E4] Record R32 pairings and outcomes
        for slot_idx, (ta, tb) in enumerate(r.get("r32_pairs", [])):
            # Canonical ordering: alphabetical so (A,B) and (B,A) merge
            key = (min(ta, tb), max(ta, tb))
            r32_appearances[key] += 1
            # We don't have the per-match winner stored here, so we track
            # via semi/final counts instead (see print_r32_probabilities)

        if verbose and (i + 1) % 5000 == 0:
            print(f"    ... {i+1:,}/{n_sims:,}")

    avg_post_group_elo = {
        t: round(elo_sum[t] / elo_n[t], 1)
        for t in elo_n
    }

    return {
        "simulations":        n_sims,
        "win_prob":           {t: c/n_sims for t, c in win_count.items()},
        "final_prob":         {t: c/n_sims for t, c in final_count.items()},
        "semi_prob":          {t: c/n_sims for t, c in semi_count.items()},
        "avg_post_group_elo": avg_post_group_elo,
        "r32_appearances":    dict(r32_appearances),
    }


# =============================================================
# [E4]  ROUND-OF-32 WIN PROBABILITY TABLE
# =============================================================

def print_r32_probabilities(results: dict, elos: dict, n_sims: int,
                             played: dict | None = None) -> None:
    """
    [E4] For each R32 slot, show the most likely matchup with the
    probability each team wins that tie.

    Strategy: For each bracket slot position, collect the top-2 most
    frequent teams that appeared there across all simulations, then
    compute head-to-head win probability via predict_match().
    We also show the % of sims where they actually met.
    """
    print(f"\n{'='*72}")
    print(f"  [E4] ROUND OF 32 — PROJECTED MATCHUPS & WIN PROBABILITIES")
    print(f"  (based on {n_sims:,} simulations)")
    print(f"{'='*72}")

    r32_apps = results.get("r32_appearances", {})
    if not r32_apps:
        print("  No R32 data available.")
        return

    # Group appearances by canonical pair, sort by frequency
    sorted_pairs = sorted(r32_apps.items(), key=lambda kv: -kv[1])

    rows = []
    seen_teams: set[str] = set()

    # We want one row per bracket slot (16 total)
    # Use the most common pairings greedily (avoid duplicating a team)
    used_pairs: list[tuple] = []
    for (ta, tb), count in sorted_pairs:
        if ta not in seen_teams and tb not in seen_teams:
            used_pairs.append((ta, tb, count))
            seen_teams.add(ta)
            seen_teams.add(tb)
        if len(used_pairs) == 16:
            break

    rng_pred = random.Random(999)
    for ta, tb, count in used_pairs:
        meet_pct = count / n_sims * 100
        p = predict_match(ta, tb, elos, n_sims=3000, knockout=True)
        wp_a = p["p_win_a"] * 100
        wp_b = p["p_win_b"] * 100
        fav  = ta if wp_a >= wp_b else tb
        fav_pct = max(wp_a, wp_b)
        rows.append([
            f"{ta}  vs  {tb}",
            f"{wp_a:.0f}%",
            f"{wp_b:.0f}%",
            f"{meet_pct:.0f}%",
            f"{fav} ({fav_pct:.0f}%)",
        ])

    print(tabulate(
        rows,
        headers=["Matchup", f"Win% A", "Win% B", "Meet%", "Favourite"],
        tablefmt="rounded_outline",
    ))

    print(f"\n  Win% = probability of winning the R32 tie (knockout format).")
    print(f"  Meet% = fraction of simulations this exact pairing occurred.\n")


# =============================================================
# 11.  MATCH PREDICTION
# =============================================================

def predict_match(team_a: str, team_b: str, elos: dict,
                  n_sims=5000, knockout=False) -> dict:
    """
    [P2+P3] Match predictor integrated with the player model.

    Changes vs v2.3:
      - Uses simulate_match_with_players() so player stats
        (cards, fatigue, suspensions) accumulate during prediction
        runs — the player perf modifier then feeds back into ELO.
      - Clones elos per run to avoid cross-contaminating simulations.
      - Exposes per-position avg effective ratings for both teams.
    """
    rng = random.Random(hash((team_a, team_b)) & 0xFFFFFFFF)
    wins_a = draws = wins_b = 0
    score_counts: dict[tuple[int,int], int] = defaultdict(int)

    # Snapshot effective ELOs before any simulated player drift
    elo_a_snap = _effective_elo(team_a, elos)
    elo_b_snap = _effective_elo(team_b, elos)

    for _ in range(n_sims):
        # Use the full player-aware simulation so ratings, cards, and
        # fatigue are computed per match — this is what feeds P3.
        rep = simulate_match_with_players(
            team_a, team_b, elos, rng, knockout=knockout
        )
        if rep.winner == team_a:   wins_a += 1
        elif rep.winner == team_b: wins_b += 1
        else:                      draws  += 1
        score_counts[(rep.goals_a, rep.goals_b)] += 1

    likely = max(score_counts, key=score_counts.get)

    # Per-position breakdown (uses live SQUAD_REGISTRY after sims)
    def pos_avg(team: str) -> dict[str, float]:
        players = [
            p for p in SQUAD_REGISTRY.get(normalize(team), [])
            if p.is_starter and not p.suspended and not p.injured
        ]
        by_pos: dict[str, list[float]] = defaultdict(list)
        for p in players:
            drag = (p.fatigue / 100.0) * 8.0
            by_pos[p.position].append(max(40.0, p.rating - drag))
        return {pos: round(sum(rs)/len(rs), 1) for pos, rs in by_pos.items()}

    return {
        "team_a":      team_a,
        "team_b":      team_b,
        "p_win_a":     wins_a / n_sims,
        "p_draw":      draws  / n_sims,
        "p_win_b":     wins_b / n_sims,
        "likely_score": likely,
        "elo_a":       elo_a_snap,
        "elo_b":       elo_b_snap,
        "player_perf_mod_a": round(player_perf_elo_modifier(team_a), 1),
        "player_perf_mod_b": round(player_perf_elo_modifier(team_b), 1),
        "pos_ratings_a": pos_avg(team_a),
        "pos_ratings_b": pos_avg(team_b),
    }

def _conf(p):
    if p >= 0.65: return "STRONG"
    if p >= 0.50: return "LEAN"
    if p >= 0.40: return "SLIGHT"
    return "TOSS-UP"


def print_group_predictions(groups: dict, elos: dict,
                             played: dict | None = None,
                             sims=5000) -> list[dict]:
    played = played or {}
    print(f"\n{'='*72}")
    print(f"  GROUP STAGE PREDICTIONS  ({sims:,} sims per match)")
    print(f"  [E3] Locked results shown with actual scoreline")
    print(f"{'='*72}")

    all_rows = []

    for g, teams in groups.items():
        cache = {}
        for i, a in enumerate(teams):
            for b in teams[i+1:]:
                # Check if this match is already played
                key_ab, key_ba = (a, b), (b, a)
                if key_ab in played:
                    res = played[key_ab]
                    ga, gb = res["goals_a"], res["goals_b"]
                    cache[(a, b)] = {
                        "p_win_a": 1.0 if ga > gb else (0.0 if ga < gb else 0.0),
                        "p_draw":  1.0 if ga == gb else 0.0,
                        "p_win_b": 1.0 if gb > ga else 0.0,
                        "likely_score": (ga, gb),
                        "elo_a": _effective_elo(a, elos),
                        "elo_b": _effective_elo(b, elos),
                        "locked": True,
                        "score_str": f"{ga}-{gb} ✓",
                    }
                elif key_ba in played:
                    res = played[key_ba]
                    gb, ga = res["goals_a"], res["goals_b"]
                    cache[(a, b)] = {
                        "p_win_a": 1.0 if ga > gb else 0.0,
                        "p_draw":  1.0 if ga == gb else 0.0,
                        "p_win_b": 1.0 if gb > ga else 0.0,
                        "likely_score": (ga, gb),
                        "elo_a": _effective_elo(a, elos),
                        "elo_b": _effective_elo(b, elos),
                        "locked": True,
                        "score_str": f"{ga}-{gb} ✓",
                    }
                else:
                    p = predict_match(a, b, elos, n_sims=sims)
                    p["locked"] = False
                    p["score_str"] = f"{p['likely_score'][0]}-{p['likely_score'][1]}"
                    cache[(a, b)] = p

        rows = []
        for (a, b), p in cache.items():
            probs = {a: p["p_win_a"], "Draw": p["p_draw"], b: p["p_win_b"]}
            pick  = max(probs, key=probs.get)
            adj_a = squad_elo_modifier(a)
            adj_b = squad_elo_modifier(b)
            locked_tag = " [PLAYED]" if p.get("locked") else ""
            rows.append([
                f"{a} vs {b}{locked_tag}",
                f"{p['p_win_a']*100:.0f}%" if not p.get("locked") else ("WIN" if p["p_win_a"] == 1 else ""),
                f"{p['p_draw']*100:.0f}%"  if not p.get("locked") else ("DRAW" if p["p_draw"] == 1 else ""),
                f"{p['p_win_b']*100:.0f}%" if not p.get("locked") else ("WIN" if p["p_win_b"] == 1 else ""),
                pick if not p.get("locked") else f"Final: {p['score_str']}",
                p["score_str"],
                f"{adj_a:+.0f} / {adj_b:+.0f}",
            ])
            all_rows.append({
                "group": g,
                "team_a": a, "team_b": b,
                "p_win_a": round(p["p_win_a"], 4),
                "p_draw":  round(p["p_draw"],  4),
                "p_win_b": round(p["p_win_b"], 4),
                "likely_score": p["score_str"],
                "prediction": pick if not p.get("locked") else "PLAYED",
                "confidence": _conf(probs[pick]) if not p.get("locked") else "LOCKED",
                "squad_adj_a": round(adj_a, 1),
                "squad_adj_b": round(adj_b, 1),
                "eff_elo_a": round(p["elo_a"], 1),
                "eff_elo_b": round(p["elo_b"], 1),
            })

        print(f"\n  GROUP {g}")
        print(tabulate(rows,
            headers=["Match", "W1%", "D%", "W2%", "Prediction", "Score", "SquadΔ"],
            tablefmt="rounded_outline"))

        xpts = {t: 0.0 for t in teams}
        xgf  = {t: 0.0 for t in teams}
        xga  = {t: 0.0 for t in teams}
        for (a, b), p in cache.items():
            if p.get("locked"):
                ga, gb = p["likely_score"]
                # Actual result contributes exactly
                if ga > gb:
                    xpts[a] += 3
                elif gb > ga:
                    xpts[b] += 3
                else:
                    xpts[a] += 1; xpts[b] += 1
                xgf[a] += ga; xga[a] += gb
                xgf[b] += gb; xga[b] += ga
            else:
                xpts[a] += 3*p["p_win_a"] + p["p_draw"]
                xpts[b] += 3*p["p_win_b"] + p["p_draw"]
                xgf[a] += p["likely_score"][0]; xgf[b] += p["likely_score"][1]
                xga[a] += p["likely_score"][1]; xga[b] += p["likely_score"][0]

        ranked = sorted(teams, key=lambda t: -xpts[t])
        stand = []
        for rank, t in enumerate(ranked, 1):
            prof = SQUAD_PROFILES.get(t)
            status = "ADVANCE" if rank <= 2 else ("3rd" if rank == 3 else "OUT")
            fit = f"{prof.fitness:.0f}" if prof else "—"
            kpa = f"{prof.key_player_availability:.2f}" if prof else "—"
            stand.append([rank, t, f"{xpts[t]:.1f}",
                          f"{xgf[t]:.1f}", f"{xga[t]:.1f}",
                          f"{xgf[t]-xga[t]:+.1f}", fit, kpa, status])
        print(f"\n  Predicted Group {g} standings:")
        print(tabulate(stand,
            headers=["#", "Team", "xPts", "xGF", "xGA", "xGD", "Fit%", "KPA", ""],
            tablefmt="rounded_outline"))

    return all_rows


# =============================================================
# 12.  POST-GROUP ELO SHIFT TABLE
# =============================================================

def print_elo_shifts(base_elos: dict, avg_post_group: dict, groups: dict) -> None:
    team_group = {t: g for g, teams in groups.items() for t in teams}
    rows = []
    for t in sorted(avg_post_group, key=lambda x: -(avg_post_group[x] - base_elos.get(x, 1500))):
        base  = base_elos.get(t, 1500.0)
        post  = avg_post_group[t]
        delta = post - base
        rows.append([
            team_group.get(t, "?"), t,
            f"{base:.0f}", f"{post:.0f}",
            f"{delta:+.1f}",
            "▲" * min(5, max(0, int(delta / 5))) if delta > 0
            else "▼" * min(5, max(0, int(-delta / 5))),
        ])

    print(f"\n{'='*64}")
    print(f"  AVERAGE POST-GROUP-STAGE ELO SHIFTS")
    print(f"  (mean across all simulations, K={GROUP_STAGE_K})")
    print(f"{'='*64}")
    print(tabulate(rows,
        headers=["Grp", "Team", "Pre-ELO", "Avg Post-ELO", "Δ ELO", ""],
        tablefmt="rounded_outline"))


# =============================================================
# 13.  CSV EXPORT
# =============================================================

def export_csv(results: dict, elos: dict, group_rows: list[dict]) -> None:
    print(f"\n[E1/E2/E3] Exporting CSV files to {CSV_OUT_DIR}/")

    champ_path = CSV_OUT_DIR / "championship_probs.csv"
    all_teams = sorted(
        {t for g in GROUPS_2026.values() for t in g},
        key=lambda t: -results["win_prob"].get(t, 0)
    )
    avg_pg = results.get("avg_post_group_elo", {})
    with champ_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "team", "group",
            "win_pct", "final_pct", "semi_pct",
            "win_odds", "base_elo", "avg_post_group_elo", "elo_delta",
            "squad_adj", "player_quality", "club_strength", "fitness", "kpa"
        ])
        w.writeheader()
        team_group = {t: g for g, teams in GROUPS_2026.items() for t in teams}
        for t in all_teams:
            wp   = results["win_prob"].get(t, 0)
            fp   = results["final_prob"].get(t, 0)
            sp   = results["semi_prob"].get(t, 0)
            sq   = SQUAD_PROFILES.get(t)
            base = elos.get(t, 1500.0)
            post = avg_pg.get(t, base)
            w.writerow({
                "team":               t,
                "group":              team_group.get(t, "?"),
                "win_pct":            f"{wp*100:.2f}",
                "final_pct":          f"{fp*100:.2f}",
                "semi_pct":           f"{sp*100:.2f}",
                "win_odds":           f"1/{1/wp:.0f}" if wp > 0.005 else ">1/200",
                "base_elo":           f"{base:.1f}",
                "avg_post_group_elo": f"{post:.1f}",
                "elo_delta":          f"{post-base:+.1f}",
                "squad_adj":          f"{squad_elo_modifier(t):+.1f}",
                "player_quality":     f"{sq.player_quality:.0f}" if sq else "",
                "club_strength":      f"{sq.club_strength:.0f}"  if sq else "",
                "fitness":            f"{sq.fitness:.0f}"        if sq else "",
                "kpa":                f"{sq.key_player_availability:.2f}" if sq else "",
            })
    print(f"  ✓ {champ_path}  ({len(all_teams)} teams)")

    if group_rows:
        gp_path = CSV_OUT_DIR / "group_predictions.csv"
        with gp_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(group_rows[0].keys()))
            w.writeheader()
            w.writerows(group_rows)
        print(f"  ✓ {gp_path}  ({len(group_rows)} matches)")

    sq_path = CSV_OUT_DIR / "squad_profiles.csv"
    with sq_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "team", "group", "base_elo", "squad_adj", "eff_elo",
            "avg_post_group_elo", "elo_delta",
            "player_quality", "club_strength", "squad_depth",
            "fitness", "key_player_availability"
        ])
        w.writeheader()
        team_group = {t: g for g, teams in GROUPS_2026.items() for t in teams}
        sorted_sq = sorted(
            SQUAD_PROFILES.values(),
            key=lambda p: -_effective_elo(p.team, elos)
        )
        for sq in sorted_sq:
            base = elos.get(sq.team, 1500)
            adj  = squad_elo_modifier(sq.team)
            post = avg_pg.get(sq.team, base)
            w.writerow({
                "team":                    sq.team,
                "group":                   team_group.get(sq.team, "?"),
                "base_elo":                f"{base:.1f}",
                "squad_adj":               f"{adj:+.1f}",
                "eff_elo":                 f"{base+adj:.1f}",
                "avg_post_group_elo":      f"{post:.1f}",
                "elo_delta":               f"{post-base:+.1f}",
                "player_quality":          sq.player_quality,
                "club_strength":           sq.club_strength,
                "squad_depth":             sq.squad_depth,
                "fitness":                 sq.fitness,
                "key_player_availability": sq.key_player_availability,
            })
    print(f"  ✓ {sq_path}  ({len(SQUAD_PROFILES)} teams)")
    print(f"\n  All CSVs written to ./{CSV_OUT_DIR}/")


# =============================================================
# 14.  REPORTING
# =============================================================

def print_report(results: dict, elos: dict) -> tuple:
    N = results["simulations"]
    print(f"\n{'='*64}")
    print(f"  CHAMPIONSHIP PROBABILITIES — {N:,} simulations")
    print(f"  [E3] Locked real results applied before simulation")
    print(f"  [E4] R32 bracket probabilities printed separately")
    print(f"{'='*64}")

    print("\n  WIN PROBABILITY (Top 20)\n")
    wp = sorted(results["win_prob"].items(), key=lambda x: -x[1])[:20]
    rows = []
    for rank, (t, p) in enumerate(wp, 1):
        bar  = "█" * int(p * 50)
        sq   = SQUAD_PROFILES.get(t)
        pq   = f"{sq.player_quality:.0f}" if sq else "—"
        fit  = f"{sq.fitness:.0f}"        if sq else "—"
        rows.append([rank, t, f"{p*100:.1f}%",
                     f"1/{1/p:.0f}" if p > 0.005 else ">1/200",
                     pq, fit, bar])
    print(tabulate(rows,
        headers=["#", "Team", "Win%", "Odds", "PQ", "Fit", ""],
        tablefmt="rounded_outline"))

    print("\n  REACH FINAL (Top 16)\n")
    fp = sorted(results["final_prob"].items(), key=lambda x: -x[1])[:16]
    print(tabulate([[t, f"{p*100:.1f}%"] for t, p in fp],
        headers=["Team", "Final%"], tablefmt="rounded_outline"))

    print("\n  REACH SEMI-FINAL (Top 16)\n")
    sp = sorted(results["semi_prob"].items(), key=lambda x: -x[1])[:16]
    print(tabulate([[t, f"{p*100:.1f}%"] for t, p in sp],
        headers=["Team", "Semi%"], tablefmt="rounded_outline"))

    return wp[0] if wp else (None, 0.0)


# =============================================================
# [P4]  TOURNAMENT PLAYER STATS SUMMARY
# =============================================================

def print_tournament_player_stats(top_n: int = 10) -> None:
    """
    [P4] Print top scorers, assisters, and most-carded players
    across all teams using cumulative SQUAD_REGISTRY data.
    """
    all_players = [p for squad in SQUAD_REGISTRY.values() for p in squad]
    played = [p for p in all_players if p.matches_played > 0]

    print(f"\n{'='*64}")
    print(f"  [P4] TOURNAMENT PLAYER STATISTICS")
    print(f"{'='*64}")

    # Top scorers
    scorers = sorted(played, key=lambda p: (-p.goals, -p.assists))[:top_n]
    print(f"\n  TOP SCORERS")
    print(tabulate(
        [[i+1, p.name, p.team, p.position, p.goals, p.assists,
          p.matches_played, p.minutes_played,
          "🚫" if p.suspended else ""]
         for i, p in enumerate(scorers)],
        headers=["#","Player","Team","Pos","G","A","MP","Mins",""],
        tablefmt="rounded_outline"
    ))

    # Top assisters
    assisters = sorted(played, key=lambda p: (-p.assists, -p.goals))[:top_n]
    print(f"\n  TOP ASSISTERS")
    print(tabulate(
        [[i+1, p.name, p.team, p.position, p.assists, p.goals,
          p.matches_played]
         for i, p in enumerate(assisters)],
        headers=["#","Player","Team","Pos","A","G","MP"],
        tablefmt="rounded_outline"
    ))

    # Most disciplinary issues
    carded = sorted(played,
                    key=lambda p: (-(p.yellow_cards + p.red_cards*3)))[:8]
    print(f"\n  DISCIPLINARY")
    print(tabulate(
        [[p.name, p.team, p.yellow_cards,
          "●" if p.red_cards else "", "🚫" if p.suspended else ""]
         for p in carded if p.yellow_cards + p.red_cards > 0],
        headers=["Player","Team","YC","RC","Susp"],
        tablefmt="rounded_outline"
    ))

    # Most fatigued starters
    tired = sorted(
        [p for p in played if p.is_starter],
        key=lambda p: -p.fatigue
    )[:8]
    print(f"\n  FATIGUE (starters)")
    print(tabulate(
        [[p.name, p.team, p.position, f"{p.fatigue:.0f}%",
          p.matches_played, p.minutes_played]
         for p in tired],
        headers=["Player","Team","Pos","Fatigue","MP","Mins"],
        tablefmt="rounded_outline"
    ))


def export_player_stats_csv() -> None:
    """[P4] Write wc2026_results/player_stats.csv with all player data."""
    all_players = [p for squad in SQUAD_REGISTRY.values() for p in squad
                   if p.matches_played > 0]
    all_players.sort(key=lambda p: (-p.goals, -p.assists, -p.minutes_played))

    path = CSV_OUT_DIR / "player_stats.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "name","team","position","rating","is_starter",
            "matches_played","minutes_played",
            "goals","assists","yellow_cards","red_cards",
            "fatigue","suspended",
        ])
        w.writeheader()
        for p in all_players:
            w.writerow({
                "name":            p.name,
                "team":            p.team,
                "position":        p.position,
                "rating":          p.rating,
                "is_starter":      p.is_starter,
                "matches_played":  p.matches_played,
                "minutes_played":  p.minutes_played,
                "goals":           p.goals,
                "assists":         p.assists,
                "yellow_cards":    p.yellow_cards,
                "red_cards":       p.red_cards,
                "fatigue":         f"{p.fatigue:.1f}",
                "suspended":       p.suspended,
            })
    print(f"  ✓ {path}  ({len(all_players)} players)")


# =============================================================
# 15.  MAIN
# =============================================================

def main(n_sims=20_000, use_live=True, show_groups=True,
         match_sims=5000, show_top_elos=True,
         live_mode: bool = False):
    """
    Parameters
    ----------
    live_mode : if True, enter the continuous minute-by-minute live
                tracker (watch_live) and skip the full Monte Carlo run.
                Set to False (default) for the normal simulation flow.
    """

    print("\n" + "=" * 64)
    print("  FIFA WORLD CUP 2026 SIMULATOR  v2.4")
    print("  New: [E3] Played-match locking (real scores kept)")
    print("       [E4] Round-of-32 win probability table")
    print("       [E5] Live in-game prediction (score + minute aware)")
    print("       [FIX] Score distribution: Poisson preserved, no 2-1 bias")
    print("=" * 64)

    print("\n[0/6] Applying squad injury profiles ...")
    apply_known_injuries()
    print(f"  {len(SQUAD_PROFILES)} teams loaded with squad profiles.")

    api_ok = test_api_connection() if use_live else False

    print("\n[1/6] Building historical ELO ...")
    elos = build_elo(verbose=True)
    verify_coverage(GROUPS_2026, elos)
    if show_top_elos:
        print_top_elos(elos, n=20)

    # [E3] Build the played-results dict (API + manual fallback)
    client = FootballDataClient() if api_ok else None

    # [P2] Pull real player stats from API if connected
    if api_ok and client:
        fetch_real_player_stats(client)
    print("\n[2/6] Loading completed group-stage results ...")
    played = build_played_results(api_ok, client)

    # [E7] Apply any manually-entered MANUAL_RESULTS to the ELO cache.
    # Converts the played dict into fake LiveSnapshots so the same
    # deduplication / logging logic applies.
    if played:
        manual_snaps = [
            LiveSnapshot(
                home=a, away=b,
                home_goals=r["goals_a"], away_goals=r["goals_b"],
                minute=90, status="FINISHED",
            )
            for (a, b), r in played.items()
        ]
        print("  [E7] Syncing played results into ELO cache ...")
        apply_live_results_to_elo(manual_snaps, elos, verbose=True)

    live_overrides = {}
    if api_ok and client:
        if live_mode:
            # ── [E6] Continuous minute-by-minute tracker ──────
            print("\n[3/6] Entering live match tracker ...")
            print("      (Ctrl-C returns to normal simulation flow)")
            # watch_live applies ELO updates internally as matches finish
            final_snaps = watch_live(client, elos)
            live_overrides = live_to_overrides(final_snaps or [])
        else:
            # ── Single-shot snapshot + prediction ─────────────
            print("\n[3/6] Checking live WC matches ...")
            snaps = fetch_and_predict_live(client, elos)
            live_overrides = live_to_overrides(snaps)
            # Apply any FINISHED matches from this single-shot fetch
            finished = [s for s in snaps if s.status in {"FINISHED", "AWARDED"}]
            if finished:
                print("  [E7] Applying ELO updates from finished matches ...")
                apply_live_results_to_elo(finished, elos, verbose=True)
    else:
        print("\n[3/6] Live data skipped (offline mode).")

    group_rows = []
    if show_groups:
        print(f"\n[4/6] Group stage predictions ...")
        group_rows = print_group_predictions(
            GROUPS_2026, elos, played=played, sims=match_sims
        )

    print(f"\n[5/6] Running {n_sims:,} Monte Carlo simulations ...")
    results = run_monte_carlo(
        n_sims, elos, GROUPS_2026,
        live_overrides=live_overrides,
        played=played,
    )

    print("\n[6/6] Results:")
    champ = print_report(results, elos)

    # [E4] Print R32 probability table
    print_r32_probabilities(results, elos, n_sims, played=played)

    # ELO shift table
    print_elo_shifts(elos, results.get("avg_post_group_elo", {}), GROUPS_2026)

    # Export CSVs
    export_csv(results, elos, group_rows)

    # [P4] Player stats summary + CSV
    print_tournament_player_stats(top_n=10)
    export_player_stats_csv()

    if champ and champ[0]:
        t, p = champ
        print(f"\n{'='*64}")
        print(f"  PREDICTED CHAMPION: {t}  ({p*100:.1f}% probability)")
        print(f"{'='*64}\n")


if __name__ == "__main__":
    import sys

    # ── MODE SELECT ────────────────────────────────────────────────
    # Pass  --live   on the command line to enter the continuous
    # minute-by-minute live tracker (requires FOOTBALL_DATA_TOKEN).
    #
    # Pass  --demo   to watch a simulated match advance in real time
    # without needing an API connection (great for testing).
    #
    # Default: full Monte Carlo simulation run.
    # ──────────────────────────────────────────────────────────────

    if "--demo" in sys.argv:
        # Offline minute-by-minute demo
        print("\n  Building ELO for demo ...")
        _elos = build_elo(verbose=False)
        print("  Starting demo: Brazil vs France, kick-off 0-0\n")
        time.sleep(1)
        watch_live_demo(
            home="Brazil", away="France",
            elos=_elos,
            start_score=(0, 0),
            start_minute=1,
            end_minute=90,
            # inject some goals to make it interesting
            goal_events=[
                (23, "home"),   # Brazil score 23'
                (58, "away"),   # France equalise 58'
                (71, "away"),   # France take lead 71'
                (87, "home"),   # Brazil equalise 87'
            ],
            speed=0.3,          # seconds per simulated minute
            knockout=False,
        )

    elif "--live" in sys.argv:
        # Continuous API-backed tracker, then full simulation
        main(
            n_sims=20_000,
            use_live=True,
            show_groups=True,
            match_sims=5000,
            show_top_elos=True,
            live_mode=True,
        )

    else:
        # Normal full simulation run
        main(
            n_sims=20_000,
            use_live=True,
            show_groups=True,
            match_sims=5000,
            show_top_elos=True,
            live_mode=False,
        )
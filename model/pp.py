"""
=============================================================
  STOCHASTIC CALCULUS LAYER  — wc2026_simulator v2.3
  Tagged [SC] throughout.

  THREE MECHANISMS
  ────────────────
  [SC-1]  ELO as a mean-reverting diffusion (Ornstein–Uhlenbeck)
          Each team's strength is not a fixed scalar but a random
          variable drawn from an OU process before each simulation:

            dE_t = θ(μ − E_t) dt + σ dW_t

          where
            μ  = long-run mean (the historical ELO)
            θ  = mean-reversion speed (how fast form reverts)
            σ  = volatility (calibrated per team from historical
                 ELO variance; inconsistent teams get higher σ)
            W  = standard Brownian motion

          Euler–Maruyama discretisation over dt steps gives a
          sampled ELO for that tournament simulation.  Strong
          teams stay roughly where they are (low σ, high θ);
          volatile teams can spike or crash.

  [SC-2]  Cox process (doubly-stochastic Poisson) for goals
          Instead of a fixed λ per match, the goal arrival rate
          itself follows an OU process over [0, 90] minutes:

            dλ_t = κ(λ̄ − λ_t) dt + ξ dW_t,   λ_t ≥ 0

          where λ̄ = base rate from ELO diff (unchanged formula),
          κ = intensity mean-reversion speed, ξ = intensity vol.

          Goals arrive as a non-homogeneous Poisson process with
          stochastic intensity: we integrate the path λ_t over
          time and sample a Poisson(∫λ dt) count.  This produces
          realistic goal-time clustering (early/late bursts) and
          fatter tails than plain Poisson.

  [SC-3]  Correlated Brownian motions across groups
          Group-stage form shocks (injuries, travel, weather) are
          partially correlated within a confederation.  We build
          a Cholesky-decomposed covariance matrix and draw all
          48-team form shocks jointly, so a "bad tournament for
          UEFA" is possible as a coherent event.

=============================================================
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Optional


# ─────────────────────────────────────────────────────────────
# [SC-1]  ORNSTEIN–UHLENBECK ELO DIFFUSION
# ─────────────────────────────────────────────────────────────

# Volatility σ per team (ELO points).
# Calibrated from rough historical variance clusters:
#   Tier 1 (very consistent elite): σ ≈ 25
#   Tier 2 (established nations):   σ ≈ 40
#   Tier 3 (mid-tier / rising):     σ ≈ 60
#   Tier 4 (underdogs / volatile):  σ ≈ 80
_TEAM_SIGMA: dict[str, float] = {
    # Tier 1 — battle-tested, consistent squads
    "France":        25.0,
    "Brazil":        28.0,
    "Spain":         25.0,
    "Germany":       28.0,
    "Argentina":     30.0,
    "England":       30.0,
    "Netherlands":   30.0,
    "Portugal":      32.0,
    # Tier 2
    "Belgium":       38.0,
    "Uruguay":       38.0,
    "Croatia":       40.0,
    "Colombia":      40.0,
    "Japan":         38.0,
    "Switzerland":   35.0,
    "Morocco":       42.0,
    "Senegal":       42.0,
    "United States": 42.0,
    "Mexico":        40.0,
    "Canada":        45.0,
    "Norway":        40.0,
    "Austria":       42.0,
    "South Korea":   42.0,
    # Tier 3
    "Sweden":        50.0,
    "Turkey":        52.0,
    "Algeria":       52.0,
    "Ecuador":       55.0,
    "Ivory Coast":   52.0,
    "Ghana":         55.0,
    "Australia":     50.0,
    "Scotland":      52.0,
    "Czechia":       50.0,
    "Tunisia":       55.0,
    "Iran":          55.0,
    "Egypt":         58.0,
    "Paraguay":      55.0,
    "Bosnia and Herzegovina": 55.0,
    # Tier 4
    "DR Congo":      65.0,
    "Saudi Arabia":  65.0,
    "Cape Verde":    68.0,
    "Uzbekistan":    70.0,
    "South Africa":  68.0,
    "Jordan":        72.0,
    "Iraq":          72.0,
    "Panama":        68.0,
    "Qatar":         75.0,
    "Haiti":         80.0,
    "New Zealand":   72.0,
    "Curacao":       72.0,
}
_DEFAULT_SIGMA = 55.0

# OU parameters
_THETA = 0.15    # mean-reversion speed  (higher = faster reversion)
_DT    = 1.0     # one "time step" = one tournament (unit-less)
_N_STEPS = 8     # discretise into 8 Euler–Maruyama steps for accuracy


def ou_elo_sample(
    team: str,
    base_elo: float,
    rng: random.Random,
    theta: float = _THETA,
    dt: float = _DT,
    n_steps: int = _N_STEPS,
) -> float:
    """
    [SC-1] Draw a tournament-specific ELO for `team` by simulating
    one path of the OU process E_t starting at base_elo.

    Euler–Maruyama:
        E_{t+h} = E_t + θ(μ − E_t)h + σ √h Z,   Z ~ N(0,1)

    The long-run mean μ is base_elo itself (we treat the historical
    rating as the unconditional mean).  The result is a sample from
    N(base_elo, σ²(1−e^{−2θ}) / (2θ)) at stationarity, but the
    path simulation is used so that correlated draws (Section SC-3)
    can inject a shared Z for all teams simultaneously.
    """
    sigma = _TEAM_SIGMA.get(team, _DEFAULT_SIGMA)
    h     = dt / n_steps
    sqrt_h = math.sqrt(h)
    e = base_elo  # start at historical rating
    mu = base_elo
    for _ in range(n_steps):
        z = _box_muller(rng)
        e += theta * (mu - e) * h + sigma * sqrt_h * z
    return e


def _box_muller(rng: random.Random) -> float:
    """Standard normal sample via Box–Muller transform."""
    while True:
        u1 = rng.random()
        u2 = rng.random()
        if u1 > 0:
            break
    return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)


def _box_muller_pair(rng: random.Random) -> tuple[float, float]:
    """Return TWO independent standard normals (both Box–Muller outputs)."""
    while True:
        u1 = rng.random()
        u2 = rng.random()
        if u1 > 0:
            break
    mag = math.sqrt(-2.0 * math.log(u1))
    arg = 2.0 * math.pi * u2
    return mag * math.cos(arg), mag * math.sin(arg)


# ─────────────────────────────────────────────────────────────
# [SC-2]  COX PROCESS — STOCHASTIC GOAL INTENSITY
# ─────────────────────────────────────────────────────────────

# OU parameters for the intensity process λ_t
_KAPPA  = 0.08   # intensity mean-reversion speed (slow — intensity drifts)
_XI     = 0.18   # intensity volatility (fraction of λ̄)
_T_MATCH = 90    # match length in minutes
_N_TIME_STEPS = 45  # Euler–Maruyama steps: every 2 minutes


def cox_process_goals(
    lambda_bar: float,
    rng: random.Random,
    kappa: float = _KAPPA,
    xi_frac: float = _XI,
    t_match: float = _T_MATCH,
    n_steps: int = _N_TIME_STEPS,
    max_k: int = 20,
) -> int:
    """
    [SC-2] Sample goals for ONE team via a Cox (doubly-stochastic Poisson)
    process with OU intensity.

    lambda_bar is goals-per-match (e.g. 1.30).  Internally we work in
    goals-per-minute: mu_rate = lambda_bar / t_match.  The OU process
    runs on that per-minute rate; integrating over t_match minutes
    recovers an expected total of lambda_bar goals at stationarity.

    Algorithm:
      1. mu_rate = lambda_bar / t_match   (goals / minute)
      2. Simulate λ_t (goals/min) via OU with dt in minutes:
             dλ = κ(mu_rate − λ) dt + ξ √dt dW
         where ξ = xi_frac × mu_rate  (vol scales with base rate).
      3. Integrate: Λ = ∑ max(λ_t, 0) · dt   (total expected goals)
      4. Sample goals ~ Poisson(Λ)

    At stationarity E[Λ] = lambda_bar and Var[Λ] > lambda_bar (extra
    variance from the stochastic intensity), giving fatter tails than
    plain Poisson and realistic goal-time clustering.
    """
    mu_rate = lambda_bar / t_match          # goals per minute
    xi      = xi_frac * mu_rate             # vol in goals/min units
    dt      = t_match / n_steps             # minutes per Euler step
    sqrt_dt = math.sqrt(dt)
    lam     = mu_rate                       # start at stationary mean
    integral = 0.0
    for _ in range(n_steps):
        integral += max(lam, 0.0) * dt      # accumulate goal-minutes
        z    = _box_muller(rng)
        lam += kappa * (mu_rate - lam) * dt + xi * sqrt_dt * z
    big_lambda = max(integral, 0.0)         # total expected goals
    # Sample Poisson(Λ) via inversion
    L = math.exp(-min(big_lambda, 20.0))
    k, p = 0, 1.0
    while p > L and k < max_k:
        p *= rng.random()
        k += 1
    return k - 1


# ─────────────────────────────────────────────────────────────
# [SC-3]  CORRELATED CONFEDERATION SHOCKS — CHOLESKY
# ─────────────────────────────────────────────────────────────

# Confederation membership for the 48 WC teams
_CONFEDERATION: dict[str, str] = {
    "France": "UEFA",    "Germany": "UEFA",     "Spain": "UEFA",
    "England": "UEFA",   "Netherlands": "UEFA", "Belgium": "UEFA",
    "Portugal": "UEFA",  "Croatia": "UEFA",     "Switzerland": "UEFA",
    "Norway": "UEFA",    "Austria": "UEFA",     "Sweden": "UEFA",
    "Turkey": "UEFA",    "Scotland": "UEFA",    "Czechia": "UEFA",
    "Bosnia and Herzegovina": "UEFA",
    "Brazil": "CONMEBOL",  "Argentina": "CONMEBOL", "Uruguay": "CONMEBOL",
    "Colombia": "CONMEBOL","Ecuador": "CONMEBOL",   "Paraguay": "CONMEBOL",
    "Algeria": "CAF",   "Morocco": "CAF",   "Senegal": "CAF",
    "Ivory Coast": "CAF","Ghana": "CAF",     "Egypt": "CAF",
    "Tunisia": "CAF",   "Cape Verde": "CAF","South Africa": "CAF",
    "DR Congo": "CAF",
    "Japan": "AFC",       "South Korea": "AFC",  "Australia": "AFC",
    "Iran": "AFC",        "Saudi Arabia": "AFC", "Uzbekistan": "AFC",
    "Jordan": "AFC",      "Iraq": "AFC",         "Qatar": "AFC",
    "United States": "CONCACAF", "Mexico": "CONCACAF",
    "Canada": "CONCACAF", "Panama": "CONCACAF",  "Haiti": "CONCACAF",
    "Curacao": "CONCACAF",
    "New Zealand": "OFC",
}

# Intra-confederation correlation ρ (teams from the same confed
# share some fraction of the same form shock — e.g. travel fatigue,
# local weather, same scouting exposure).
# Cross-confederation correlation is 0.
_INTRA_CORR: dict[str, float] = {
    "UEFA":      0.18,
    "CONMEBOL":  0.22,
    "CAF":       0.20,
    "AFC":       0.18,
    "CONCACAF":  0.25,
    "OFC":       0.10,
}
_DEFAULT_INTRA_CORR = 0.15


def _cholesky_2x2(rho: float) -> tuple[float, float, float]:
    """
    Cholesky decomposition of the 2×2 correlation matrix
        [[1, ρ], [ρ, 1]]
    Returns (L11, L21, L22) where L is lower-triangular.
    """
    l11 = 1.0
    l21 = rho
    l22 = math.sqrt(max(1.0 - rho ** 2, 0.0))
    return l11, l21, l22


@dataclass
class ConfederationShocks:
    """
    [SC-3] Pre-drawn confederation-level form shocks for all 48 teams.
    One shock per team, correlated within confederation via Cholesky.

    Usage:
        shocks = draw_confederation_shocks(rng)
        elo_a_adj = base_elo_a + shocks[team_a] * sigma_a
    """
    shocks: dict[str, float] = field(default_factory=dict)

    def get(self, team: str) -> float:
        return self.shocks.get(team, 0.0)


def draw_confederation_shocks(
    teams: list[str],
    rng: random.Random,
) -> ConfederationShocks:
    """
    [SC-3] Draw correlated standard-normal shocks for all `teams`.

    Algorithm (per confederation):
      For n teams in the confed with intra-corr ρ, the covariance
      matrix is  Σ = (1−ρ)I + ρ11ᵀ  (equicorrelation structure).
      Its Cholesky factor is:
        L_ii = sqrt(1−ρ + ρ²/(1+(n−1)ρ))   [diagonal]
        L_ij = ρ / L_ii   (j < i)           [off-diag, simplified]

      In practice we use the one-factor decomposition:
        Z_i = sqrt(ρ) · F + sqrt(1−ρ) · ε_i
      where F ~ N(0,1) is the shared confederation factor and
      ε_i ~ N(0,1) are idiosyncratic shocks.  This exactly produces
      Cov(Z_i, Z_j) = ρ for i≠j, Var(Z_i) = 1.
    """
    # Group teams by confederation
    conf_teams: dict[str, list[str]] = {}
    for t in teams:
        c = _CONFEDERATION.get(t, "OTHER")
        conf_teams.setdefault(c, []).append(t)

    shocks: dict[str, float] = {}

    for conf, members in conf_teams.items():
        rho = _INTRA_CORR.get(conf, _DEFAULT_INTRA_CORR)
        sqrt_rho      = math.sqrt(rho)
        sqrt_one_rho  = math.sqrt(max(1.0 - rho, 0.0))

        # Shared confederation factor
        F = _box_muller(rng)

        for t in members:
            eps = _box_muller(rng)
            shocks[t] = sqrt_rho * F + sqrt_one_rho * eps

    return ConfederationShocks(shocks=shocks)


# ─────────────────────────────────────────────────────────────
# PUBLIC API — called from simulate_tournament
# ─────────────────────────────────────────────────────────────

def sc_sample_elos(
    base_elos: dict[str, float],
    teams: list[str],
    rng: random.Random,
    confederation_shocks: Optional[ConfederationShocks] = None,
) -> dict[str, float]:
    """
    [SC-1 + SC-3] For every team in `teams`, sample a tournament-specific
    ELO via the OU diffusion, then add the (scaled) confederation shock.

    The confederation shock is already a standard normal; we scale it by
    the team's σ × shock_weight so that a 1-σ confederation event moves
    a volatile team more than a stable one.

    Returns a new dict with sampled ELOs (base_elos is unchanged).
    """
    SHOCK_WEIGHT = 0.30  # fraction of σ contributed by confed shock

    sampled: dict[str, float] = {}
    for t in teams:
        base = base_elos.get(t, 1500.0)
        # [SC-1] OU path sample
        e = ou_elo_sample(t, base, rng)
        # [SC-3] Confederation shock overlay
        if confederation_shocks is not None:
            sigma = _TEAM_SIGMA.get(t, _DEFAULT_SIGMA)
            e += confederation_shocks.get(t) * sigma * SHOCK_WEIGHT
        sampled[t] = round(e, 1)
    return sampled


def sc_simulate_goals(
    elo_a: float,
    elo_b: float,
    rng: random.Random,
    lambda_base: float = 1.30,
) -> tuple[int, int]:
    """
    [SC-2] Replace the plain Poisson goal sampler with a Cox process.
    Same interface as simulate_goals() so it's a drop-in replacement.
    """
    from math import tanh
    def lam_from_diff(diff: float) -> float:
        return lambda_base * (1 + 0.5 * tanh(diff / 600))

    lam_a = lam_from_diff(elo_a - elo_b)
    lam_b = lam_from_diff(elo_b - elo_a)
    return cox_process_goals(lam_a, rng), cox_process_goals(lam_b, rng)


# ─────────────────────────────────────────────────────────────
# DIAGNOSTICS — print a summary of the SC layer
# ─────────────────────────────────────────────────────────────

def print_sc_diagnostics(base_elos: dict[str, float], n_samples: int = 10_000)-> None:
    """
    Print theoretical and empirical statistics for the SC layer:
      - OU stationary std dev per tier
      - Cox process goal mean and variance vs plain Poisson
    """
    rng = random.Random(0)
    print("\n" + "=" * 64)
    print("  [SC] STOCHASTIC CALCULUS LAYER — DIAGNOSTICS")
    print("=" * 64)

    # OU stationary std dev: σ_stat = σ / sqrt(2θ)
    print("\n  [SC-1] OU ELO — stationary std dev by tier:")
    tier_samples = {
        "France (σ=25)":  ("France",  25.0),
        "Japan (σ=38)":   ("Japan",   38.0),
        "Ecuador (σ=55)": ("Ecuador", 55.0),
        "Qatar (σ=75)":   ("Qatar",   75.0),
    }
    for label, (team, sigma) in tier_samples.items():
        stat_std = sigma / math.sqrt(2 * _THETA)
        # Also empirical
        base = base_elos.get(team, 1500.0)
        samples = [ou_elo_sample(team, base, rng) for _ in range(n_samples)]
        emp_std = math.sqrt(sum((s - base)**2 for s in samples) / n_samples)
        emp_mean = sum(samples) / n_samples
        print(f"    {label:25s}  theory_std={stat_std:5.1f}  "
              f"emp_mean={emp_mean:7.1f}  emp_std={emp_std:5.1f}")

    print(f"\n  [SC-2] Cox process vs plain Poisson (λ̄ = 1.30, n={n_samples:,}):")
    try:
        from wc2026_simulator import _sample_poisson
    except ImportError:
        _sample_poisson = None

    for lam_bar in [0.80, 1.30, 1.80]:
        cox_samples = [cox_process_goals(lam_bar, rng) for _ in range(n_samples)]
        cox_mean = sum(cox_samples) / n_samples
        cox_var  = sum((s - cox_mean)**2 for s in cox_samples) / n_samples
        print(f"    λ̄={lam_bar:.2f}  Cox: mean={cox_mean:.3f} var={cox_var:.3f}  "
              f"[Poisson would have mean=var={lam_bar:.3f}]")

    print(f"\n  [SC-3] Confederation shock correlations:")
    # Empirically verify correlation between two UEFA teams
    n = 5_000
    all_teams = list(base_elos.keys())
    uefa = [t for t in all_teams if _CONFEDERATION.get(t) == "UEFA"][:2]
    conmebol = [t for t in all_teams if _CONFEDERATION.get(t) == "CONMEBOL"][:2]
    for pair in [uefa, conmebol]:
        if len(pair) < 2:
            continue
        s1, s2 = [], []
        for _ in range(n):
            shocks = draw_confederation_shocks(pair, rng)
            s1.append(shocks.get(pair[0]))
            s2.append(shocks.get(pair[1]))
        m1 = sum(s1)/n; m2 = sum(s2)/n
        cov  = sum((a-m1)*(b-m2) for a,b in zip(s1,s2)) / n
        std1 = math.sqrt(sum((a-m1)**2 for a in s1)/n)
        std2 = math.sqrt(sum((b-m2)**2 for b in s2)/n)
        emp_rho = cov / (std1 * std2) if std1 and std2 else 0
        conf = _CONFEDERATION.get(pair[0], "?")
        target_rho = _INTRA_CORR.get(conf, _DEFAULT_INTRA_CORR)
        print(f"    {pair[0]:20s} ↔ {pair[1]:20s}  "
              f"target ρ={target_rho:.2f}  emp ρ={emp_rho:.3f}")
    print()
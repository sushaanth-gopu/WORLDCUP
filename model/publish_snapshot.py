import os
from typing import Any

import requests

from model import GROUPS_2026, build_elo, main


def _team_payload_from_results(results: dict[str, Any], elos: dict[str, float]) -> list[dict[str, Any]]:
    teams = sorted(
        {team for group in GROUPS_2026.values() for team in group},
        key=lambda team: results.get("win_prob", {}).get(team, 0),
        reverse=True,
    )

    return [
        {
            "teamName": team,
            "winProbability": round(results.get("win_prob", {}).get(team, 0) * 100, 3),
            "finalProbability": round(results.get("final_prob", {}).get(team, 0) * 100, 3),
            "semiProbability": round(results.get("semi_prob", {}).get(team, 0) * 100, 3),
            "rating": round(elos.get(team, 1500), 1),
        }
        for team in teams
    ]


def publish_snapshot(api_base_url: str, admin_code: str, simulations: int = 20000) -> dict[str, Any]:
    """
    Runs the model, then publishes the latest probabilities to the hosted app.

    Required environment variables:
      PREDICTA_API_BASE_URL=https://your-site-name.netlify.app
      ADMIN_MODEL_CODE=your-private-code
    """
    elos = build_elo(verbose=False)
    results = main(
        n_sims=simulations,
        use_live=True,
        show_groups=False,
        match_sims=1000,
        show_top_elos=False,
        live_mode=False,
    )

    if not isinstance(results, dict):
        raise RuntimeError(
            "model.main() does not currently return the simulation results. "
            "Return the results dict from model.main() before publishing."
        )

    response = requests.post(
        f"{api_base_url.rstrip('/')}/api/model/snapshot",
        json={
            "adminCode": admin_code,
            "source": "python-model",
            "simulations": simulations,
            "teams": _team_payload_from_results(results, elos),
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


if __name__ == "__main__":
    api_base = os.getenv("PREDICTA_API_BASE_URL", "http://localhost:5173")
    code = os.getenv("ADMIN_MODEL_CODE", "")
    sims = int(os.getenv("MODEL_SIMULATIONS", "20000"))
    print(publish_snapshot(api_base, code, sims))

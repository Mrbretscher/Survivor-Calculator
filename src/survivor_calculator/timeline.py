"""Prepared out-of-training episode replays using the board's fitted model."""
from __future__ import annotations

from collections import defaultdict

from survivor_calculator.evaluation import RiskModel
from survivor_calculator.features import FeatureBuildResult

TIMELINE_NOTE = (
    "Reconstructed with the current model and source data, not an archived pre-broadcast forecast. "
    "Each checkpoint uses its recorded active roster, completed votes, and prior-episode features. "
    "Only seasons after the model's last training season are shown. "
    "Episodes without a validated voting forecast are selectable with an unavailable explanation."
)


def build_timeline(
    features: FeatureBuildResult,
    model: RiskModel,
    model_name: str,
    metadata: dict[str, object],
) -> dict[str, object]:
    """Reuse one fitted model; exclude its training seasons and earlier states.

    The stricter chronological boundary also prevents pooled-random holdouts
    from replaying seasons using a model trained on their future seasons.
    """
    from survivor_calculator.baseline import predict_board

    last_training = max(metadata["training_seasons"], default=0)
    groups: dict[tuple[int, int, int], list[dict[str, object]]] = defaultdict(list)
    rows = features.timeline_rows or features.current_rows
    for row in rows:
        season = int(row["season"])
        if season <= last_training:
            continue
        groups[season, int(row["episode"]), int(row.get("completed_exit_order", row["n_boots"]))].append(row)
    states = []
    for (season, episode, checkpoint), roster in sorted(groups.items()):
        final_n = int(roster[0]["final_n"])
        players, boot_order = predict_board(model, roster, final_n, model_name)
        states.append({
            "season": season, "episode": episode, "checkpoint": checkpoint,
            "final_n": final_n, "active_players": len(players),
            "players": players, "projected_boot_order": boot_order,
        })
    episodes = sorted(set(features.timeline_episodes) | {(season, episode) for season, episode, _checkpoint in groups})
    available = {(state["season"], state["episode"]) for state in states}
    return {"version": 1, "note": TIMELINE_NOTE, "states": states, "episodes": [
        {"season": season, "episode": episode, "available": (season, episode) in available}
        for season, episode in episodes if last_training < season <= features.current_season
        and (season < features.current_season or episode <= features.latest_episode)
    ]}

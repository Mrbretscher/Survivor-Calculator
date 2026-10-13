"""Dependency-light historical-rate baselines."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean

from survivor_calculator.evaluation import evaluate_chronological as _evaluate_chronological
from survivor_calculator.features import FEATURE_COLUMNS, FeatureBuildResult, assert_no_leakage_columns


@dataclass(frozen=True)
class PredictionBundle:
    metadata: dict[str, object]
    players: list[dict[str, object]]
    projected_boot_order: list[dict[str, object]]
    evaluation: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "metadata": self.metadata,
            "players": self.players,
            "projected_boot_order": self.projected_boot_order,
            "evaluation": self.evaluation,
        }


class HistoricalRateModel:
    """Smoothed rate model for next-boot risk."""

    def __init__(self) -> None:
        self.global_rate = 0.05
        self.group_rates: dict[str, dict[object, float]] = {}
        self.weights = {
            "final_n": 2.0,
            "tribe_status": 1.5,
            "age_bucket": 0.8,
            "gender": 0.5,
            "soc_major_group": 0.7,
            "challenge_bucket": 1.0,
            "vote_bucket": 1.3,
            "confessional_bucket": 0.8,
        }

    def fit(self, rows: list[dict[str, object]]) -> "HistoricalRateModel":
        if not rows:
            return self
        self.global_rate = mean(float(row["target_next_boot"]) for row in rows)
        feature_values = defaultdict(lambda: defaultdict(list))
        for row in rows:
            target = float(row["target_next_boot"])
            for feature, value in self._rate_features(row).items():
                feature_values[feature][value].append(target)
        self.group_rates = {
            feature: {
                value: self._smooth_rate(values)
                for value, values in grouped.items()
            }
            for feature, grouped in feature_values.items()
        }
        return self

    def predict_risk(self, row: dict[str, object]) -> float:
        total_weight = 1.0
        score = self.global_rate
        for feature, value in self._rate_features(row).items():
            rate = self.group_rates.get(feature, {}).get(value)
            if rate is None:
                continue
            weight = self.weights.get(feature, 1.0)
            score += rate * weight
            total_weight += weight
        return min(max(score / total_weight, 0.001), 0.999)

    def _smooth_rate(self, values: list[float]) -> float:
        prior_strength = 8.0
        return (sum(values) + self.global_rate * prior_strength) / (len(values) + prior_strength)

    def _rate_features(self, row: dict[str, object]) -> dict[str, object]:
        return {
            "final_n": row.get("final_n"),
            "tribe_status": row.get("tribe_status") or "",
            "age_bucket": _age_bucket(row.get("age")),
            "gender": row.get("gender") or "Unknown",
            "soc_major_group": row.get("soc_major_group") or "Unmapped",
            "challenge_bucket": _bucket(row.get("challenge_wins_to_date"), (0, 1, 3)),
            "vote_bucket": _bucket(row.get("votes_received_to_date"), (0, 1, 3)),
            "confessional_bucket": _bucket(row.get("confessionals_to_date"), (0, 2, 6, 12)),
        }


def build_predictions(features: FeatureBuildResult, workbook_path: str | Path) -> PredictionBundle:
    assert_no_leakage_columns(FEATURE_COLUMNS)
    train_rows = [
        row for row in features.historical_rows
        if int(row["season"]) < features.current_season
    ]
    model = HistoricalRateModel().fit(train_rows)
    evaluation = _evaluate_chronological(features.historical_rows, HistoricalRateModel)

    raw_player_rows = []
    for row in features.current_rows:
        raw_risk = model.predict_risk(row)
        raw_player_rows.append(
            {
                "castaway_id": row["castaway_id"],
                "castaway": row["castaway"],
                "tribe": row["tribe"],
                "tribe_status": row["tribe_status"],
                "occupation": row["occupation"],
                "soc_major_group": row["soc_major_group"] or "Unmapped",
                "raw_next_boot_risk": raw_risk,
                "next_boot_probability": 0.0,
                "winner_probability": 0.0,
                "explanation": _explain(row, raw_risk),
            }
        )

    total_risk = sum(float(player["raw_next_boot_risk"]) for player in raw_player_rows) or 1.0
    for player in raw_player_rows:
        player["next_boot_probability"] = float(player["raw_next_boot_risk"]) / total_risk

    survival_scores = [1.0 / max(0.001, float(player["raw_next_boot_risk"])) for player in raw_player_rows]
    total_survival = sum(survival_scores) or 1.0
    for player, survival_score in zip(raw_player_rows, survival_scores, strict=True):
        player["winner_probability"] = survival_score / total_survival

    player_rows = sorted(raw_player_rows, key=lambda item: item["winner_probability"], reverse=True)
    projected_boot_order = _project_boot_order(player_rows, features.latest_final_n)
    metadata = {
        "generated_at": datetime.now(UTC).isoformat(),
        "model_name": "historical_rate_baseline",
        "source_workbook": str(Path(workbook_path)),
        "current_season": features.current_season,
        "latest_episode": features.latest_episode,
        "latest_final_n": features.latest_final_n,
        "active_players": len(features.current_rows),
        "disclaimer": "For-fun baseline probabilities, not production forecasts.",
    }
    return PredictionBundle(metadata, player_rows, projected_boot_order, evaluation)


def evaluate_chronological(rows: list[dict[str, object]], holdout_seasons: int = 5) -> dict[str, object]:
    """Evaluate the historical-rate baseline with a chronological holdout split."""

    return _evaluate_chronological(rows, HistoricalRateModel, holdout_seasons)


def save_predictions(bundle: PredictionBundle, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(bundle.to_dict(), indent=2), encoding="utf-8")
    return path


def _project_boot_order(players: list[dict[str, object]], latest_final_n: int) -> list[dict[str, object]]:
    remaining = sorted(players, key=lambda item: item["next_boot_probability"], reverse=True)
    projected = []
    final_n = latest_final_n
    for index, player in enumerate(remaining, start=1):
        projected.append(
            {
                "projected_order": index,
                "projected_final_n_before_boot": final_n,
                "castaway_id": player["castaway_id"],
                "castaway": player["castaway"],
                "projected_boot_probability": player["next_boot_probability"],
            }
        )
        final_n = max(1, final_n - 1)
    return projected


def _explain(row: dict[str, object], risk: float) -> list[str]:
    reasons = [f"Baseline next-boot risk: {risk:.1%}."]
    if float(row.get("votes_received_to_date") or 0) > 0:
        reasons.append("Has received votes earlier in the season.")
    if float(row.get("individual_immunity_wins_to_date") or 0) > 0:
        reasons.append("Has individual immunity wins in the current record.")
    if float(row.get("advantages_held_to_date") or 0) > 0:
        reasons.append("Advantage timeline shows an advantage held at least once.")
    if float(row.get("confessionals_to_date") or 0) == 0:
        reasons.append("Low recorded confessional visibility so far.")
    return reasons


def _age_bucket(value: object) -> str:
    try:
        age = int(value) if value is not None else None
    except (TypeError, ValueError):
        age = None
    if age is None:
        return "unknown"
    if age < 25:
        return "under_25"
    if age < 35:
        return "25_34"
    if age < 45:
        return "35_44"
    return "45_plus"


def _bucket(value: object, thresholds: tuple[int, ...]) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0
    for threshold in thresholds:
        if number <= threshold:
            return f"<= {threshold}"
    return f"> {thresholds[-1]}"


"""Dependency-light historical-rate baselines."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Callable

from survivor_calculator.evaluation import evaluate_chronological as _evaluate_chronological
from survivor_calculator.evaluation import evaluate_pooled_random_holdout as _evaluate_pooled_random_holdout
from survivor_calculator.evaluation import PRIMARY_MODEL_NAME, RiskModel
from survivor_calculator.features import FEATURE_COLUMNS, FEATURE_TIMING_VERSION, FeatureBuildResult, assert_no_leakage_columns

EXPERIMENTAL_MODEL_NAME = "experimental_next_boot"
OCCUPATION_TEXT_MODEL_NAME = "occupation_text_next_boot"
HYBRID_MODEL_NAME = "hybrid_next_boot"
SOCIAL_MODEL_NAME = "social_rate_next_boot"
DIRECT_SOCIAL_MODEL_NAME = "social_direct_next_boot"
DEFAULT_HYBRID_NON_OCCUPATION_WEIGHT = 0.9
MODEL_NAME_ALIASES = {
    SOCIAL_MODEL_NAME: SOCIAL_MODEL_NAME,
    "social-rate-next-boot": SOCIAL_MODEL_NAME,
    DIRECT_SOCIAL_MODEL_NAME: DIRECT_SOCIAL_MODEL_NAME,
    "social-direct-next-boot": DIRECT_SOCIAL_MODEL_NAME,
    PRIMARY_MODEL_NAME: PRIMARY_MODEL_NAME,
    "historical-rate-baseline": PRIMARY_MODEL_NAME,
    "historical-rate": PRIMARY_MODEL_NAME,
    EXPERIMENTAL_MODEL_NAME: EXPERIMENTAL_MODEL_NAME,
    "experimental-next-boot": EXPERIMENTAL_MODEL_NAME,
    OCCUPATION_TEXT_MODEL_NAME: OCCUPATION_TEXT_MODEL_NAME,
    "occupation-text-next-boot": OCCUPATION_TEXT_MODEL_NAME,
    "occupation-sklearn-next-boot": OCCUPATION_TEXT_MODEL_NAME,
    HYBRID_MODEL_NAME: HYBRID_MODEL_NAME,
    "hybrid-next-boot": HYBRID_MODEL_NAME,
    "hybrid-model": HYBRID_MODEL_NAME,
}


@dataclass(frozen=True)
class PredictionBundle:
    metadata: dict[str, object]
    players: list[dict[str, object]]
    projected_boot_order: list[dict[str, object]]
    evaluation: dict[str, object]
    timeline: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        payload = {
            "metadata": self.metadata,
            "players": self.players,
            "projected_boot_order": self.projected_boot_order,
            "evaluation": self.evaluation,
        }
        if self.timeline is not None:
            payload["timeline"] = self.timeline
        return payload


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



class SocialRateModel(HistoricalRateModel):
    """Experimental historical rates augmented with observed relationship evidence.

    Fixed buckets mirror the existing baseline. They are experiment settings,
    not calibrated alliance thresholds. No contestant identifiers are features.
    """

    def __init__(self, include_protective: bool = True) -> None:
        super().__init__()
        self.include_protective = include_protective
        self.weights.update({name: 1.0 for name in self._social_columns()})

    def _social_columns(self) -> tuple[str, ...]:
        columns = ("social_known_pair_fraction", "social_strongest_partner", "social_support_sum",
                   "social_incoming_targeting", "social_original_tribe_support_gap")
        if self.include_protective:
            columns += ("social_protective_opposition_received", "social_protective_opposition_outgoing")
        return columns

    def _rate_features(self, row: dict[str, object]) -> dict[str, object]:
        return {**super()._rate_features(row), **{
            name: "unknown" if row.get(name) is None else _bucket(row[name], (0, 0.1, 0.3, 0.6))
            for name in self._social_columns()
        }}


class DirectSocialRateModel(SocialRateModel):
    """Ablation with coordination and targeting, excluding protective opposition."""

    def __init__(self) -> None:
        super().__init__(include_protective=False)


class HybridNextBootModel:
    """Blend the historical-rate and occupation-text next-boot risk models."""

    def __init__(self, non_occupation_weight: float = DEFAULT_HYBRID_NON_OCCUPATION_WEIGHT) -> None:
        if not 0.0 <= non_occupation_weight <= 1.0:
            raise ValueError("non_occupation_weight must be between 0.0 and 1.0.")
        from survivor_calculator.experimental import OccupationTextNextBootModel

        self.non_occupation_weight = non_occupation_weight
        self.non_occupation_model = HistoricalRateModel()
        self.occupation_model = OccupationTextNextBootModel()

    def fit(self, rows: list[dict[str, object]]) -> "HybridNextBootModel":
        self.non_occupation_model.fit(rows)
        self.occupation_model.fit(rows)
        return self

    def predict_risk(self, row: dict[str, object]) -> float:
        non_occupation_risk = self.non_occupation_model.predict_risk(row)
        occupation_risk = self.occupation_model.predict_risk(row)
        occupation_weight = 1.0 - self.non_occupation_weight
        blended_risk = (
            self.non_occupation_weight * non_occupation_risk
            + occupation_weight * occupation_risk
        )
        return min(max(blended_risk, 0.001), 0.999)


def build_predictions(
    features: FeatureBuildResult,
    workbook_path: str | Path,
    model_name: str = PRIMARY_MODEL_NAME,
    evaluation_strategy: str = "chronological",
) -> PredictionBundle:
    assert_no_leakage_columns(FEATURE_COLUMNS)
    resolved_model_name = resolve_model_name(model_name)
    model_factory = _model_factory(resolved_model_name)
    train_rows = [
        row for row in features.historical_rows
        if int(row["season"]) < features.current_season
    ]
    comparison_factories = (
        {PRIMARY_MODEL_NAME: HistoricalRateModel}
        if resolved_model_name != PRIMARY_MODEL_NAME
        else None
    )
    if resolved_model_name == SOCIAL_MODEL_NAME:
        comparison_factories[DIRECT_SOCIAL_MODEL_NAME] = DirectSocialRateModel
    evaluation = _evaluate_model(
        features.historical_rows,
        model_factory,
        model_name=resolved_model_name,
        evaluation_strategy=evaluation_strategy,
        comparison_model_factories=comparison_factories,
    )

    if resolved_model_name == SOCIAL_MODEL_NAME and evaluation_strategy == "chronological" and evaluation.get("status") == "ok":
        from survivor_calculator.evaluation import evaluate_relationship_diagnostics

        evaluation["relationship_diagnostics"] = evaluate_relationship_diagnostics(
            features.historical_rows, model_factory, model_name=resolved_model_name,
            comparison_model_factories=comparison_factories, holdout_seasons=evaluation["holdout_seasons"],
        )
    # Serve the same training boundary that evaluation reports. Re-fitting on
    # held-out seasons would make their Timeline predictions in-sample.
    if evaluation.get("status") == "ok":
        training_seasons = set(evaluation["split"]["training_seasons"])
        train_rows = [row for row in train_rows if int(row["season"]) in training_seasons]
    training_seasons = sorted({int(row["season"]) for row in train_rows})
    model = model_factory().fit(train_rows)
    player_rows, projected_boot_order = predict_board(
        model, features.current_rows, features.latest_final_n, resolved_model_name,
    )
    metadata = {
        "generated_at": datetime.now(UTC).isoformat(),
        "model_name": resolved_model_name,
        "model_parameters": _model_parameters(resolved_model_name),
        "feature_timing_version": FEATURE_TIMING_VERSION,
        "training_seasons": training_seasons,
        "training_policy": "evaluation_training_split" if evaluation.get("status") == "ok" else "all_available_completed_seasons",
        "excluded_non_vote_states": features.excluded_non_vote_states,
        "reconciled_state_rows": features.reconciled_state_rows,
        "excluded_unlabelable_states": features.excluded_unlabelable_states,
        "evaluation_strategy": evaluation_strategy,
        "model_selection_policy": (
            "historical_rate_baseline remains the default; experimental improvements "
            "require chronological log loss, Brier score, calibration and slice review before promotion."
        ),
        "source_workbook": str(Path(workbook_path)),
        "current_season": features.current_season,
        "latest_episode": features.latest_episode,
        "latest_final_n": features.latest_final_n,
        "active_players": len(features.current_rows),
        "disclaimer": "For-fun baseline probabilities, not production forecasts.",
    }
    from survivor_calculator.timeline import build_timeline

    timeline = build_timeline(features, model, resolved_model_name, metadata)
    return PredictionBundle(metadata, player_rows, projected_boot_order, evaluation, timeline)


def predict_board(
    model: RiskModel,
    rows: list[dict[str, object]],
    final_n: int,
    model_name: str,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Score one roster using an already fitted model, without outcome labels."""
    raw_player_rows = []
    for row in rows:
        raw_risk = model.predict_risk(row)
        raw_player_rows.append(
            {
                "castaway_id": row["castaway_id"],
                "castaway": row["castaway"],
                "tribe": row["tribe"],
                "original_tribe": row["original_tribe"],
                "tribe_status": row["tribe_status"],
                "tribe_status_display": row["tribe_status_display"],
                "occupation": row["occupation"],
                "soc_code": row["soc_code"],
                "soc_title": row["soc_title"],
                "soc_major_group": row["soc_major_group"] or "Unmapped",
                "raw_next_boot_risk": raw_risk,
                "next_boot_probability": 0.0,
                "winner_probability": 0.0,
                "explanation": _explain(row, raw_risk, model_name),
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
    return player_rows, _project_boot_order(player_rows, final_n)


def evaluate_chronological(rows: list[dict[str, object]], holdout_seasons: int = 5) -> dict[str, object]:
    """Evaluate the historical-rate baseline with a chronological holdout split."""

    return _evaluate_chronological(rows, HistoricalRateModel, holdout_seasons)


def evaluate_pooled_random_holdout(rows: list[dict[str, object]]) -> dict[str, object]:
    """Evaluate the historical-rate baseline with the pooled random 80/20 split."""

    return _evaluate_pooled_random_holdout(rows, HistoricalRateModel)


def resolve_model_name(model_name: str) -> str:
    """Return the internal model identifier for a CLI/API model name."""

    try:
        return MODEL_NAME_ALIASES[model_name]
    except KeyError as exc:
        valid = ", ".join(sorted(MODEL_NAME_ALIASES))
        raise ValueError(f"Unknown model '{model_name}'. Valid choices: {valid}") from exc


def validate_model_available(model_name: str) -> None:
    """Raise a clear error if a requested model cannot be constructed."""

    _model_factory(resolve_model_name(model_name))()


def save_predictions(bundle: PredictionBundle, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(bundle.to_dict(), indent=2), encoding="utf-8")
    return path


def _evaluate_model(
    rows: list[dict[str, object]],
    model_factory: Callable[[], RiskModel],
    *,
    model_name: str,
    evaluation_strategy: str,
    comparison_model_factories: dict[str, Callable[[], RiskModel]] | None = None,
) -> dict[str, object]:
    if evaluation_strategy == "pooled-random":
        return _evaluate_pooled_random_holdout(
            rows,
            model_factory,
            model_name=model_name,
            comparison_model_factories=comparison_model_factories,
        )
    if evaluation_strategy == "chronological":
        return _evaluate_chronological(
            rows,
            model_factory,
            model_name=model_name,
            comparison_model_factories=comparison_model_factories,
        )
    raise ValueError("evaluation_strategy must be 'pooled-random' or 'chronological'.")


def _model_parameters(model_name: str) -> dict[str, object]:
    if model_name == HYBRID_MODEL_NAME:
        return {
            "non_occupation_weight": DEFAULT_HYBRID_NON_OCCUPATION_WEIGHT,
            "occupation_weight": 1.0 - DEFAULT_HYBRID_NON_OCCUPATION_WEIGHT,
        }
    if model_name in {SOCIAL_MODEL_NAME, DIRECT_SOCIAL_MODEL_NAME}:
        return {"protective_opposition": model_name == SOCIAL_MODEL_NAME,
                "experimental": True, "social_bucket_thresholds": [0, 0.1, 0.3, 0.6]}
    return {}


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


def _model_factory(model_name: str) -> Callable[[], RiskModel]:
    if model_name == SOCIAL_MODEL_NAME:
        return SocialRateModel
    if model_name == DIRECT_SOCIAL_MODEL_NAME:
        return DirectSocialRateModel
    if model_name == PRIMARY_MODEL_NAME:
        return HistoricalRateModel
    if model_name == EXPERIMENTAL_MODEL_NAME:
        from survivor_calculator.experimental import ExperimentalNextBootModel

        return ExperimentalNextBootModel
    if model_name == OCCUPATION_TEXT_MODEL_NAME:
        from survivor_calculator.experimental import OccupationTextNextBootModel

        return OccupationTextNextBootModel
    if model_name == HYBRID_MODEL_NAME:
        return HybridNextBootModel
    raise ValueError(f"Unknown model: {model_name}")


def _explain(row: dict[str, object], risk: float, model_name: str) -> list[str]:
    if model_name in {SOCIAL_MODEL_NAME, DIRECT_SOCIAL_MODEL_NAME}:
        label = "Experimental social model"
    elif model_name == EXPERIMENTAL_MODEL_NAME:
        label = "Experimental model"
    elif model_name == OCCUPATION_TEXT_MODEL_NAME:
        label = "Occupation text model"
    elif model_name == HYBRID_MODEL_NAME:
        label = "Hybrid model"
    else:
        label = "Baseline"
    reasons = [f"{label} next-boot risk: {risk:.1%}."]
    if float(row.get("votes_received_to_date") or 0) > 0:
        reasons.append("Has received votes earlier in the season.")
    if float(row.get("individual_immunity_wins_to_date") or 0) > 0:
        reasons.append("Has individual immunity wins in the current record.")
    if float(row.get("advantages_held_to_date") or 0) > 0:
        reasons.append("Advantage timeline shows an advantage held at least once.")
    if float(row.get("confessionals_to_date") or 0) == 0:
        reasons.append("Low recorded confessional visibility so far.")
    if model_name in {SOCIAL_MODEL_NAME, DIRECT_SOCIAL_MODEL_NAME}:
        reasons.append("Voting relationships are evidence proxies, not confirmed alliances.")
        if row.get("social_strongest_partner") is None:
            reasons.append("No shared-vote evidence with current tribemates is available.")
        if float(row.get("social_protective_opposition_received") or 0) > 0:
            reasons.append("Prior targeting includes apparent allies of current tribemates; protective opposition is possible.")
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


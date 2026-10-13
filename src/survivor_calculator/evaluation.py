"""Chronological holdout evaluation for Survivor boot-risk baselines."""

from __future__ import annotations

import math
from collections import defaultdict
from statistics import mean
from typing import Callable, Protocol

from survivor_calculator.features import FEATURE_COLUMNS, assert_no_leakage_columns


class RiskModel(Protocol):
    """Minimal protocol for models evaluated as event-level risk scorers."""

    def fit(self, rows: list[dict[str, object]]) -> "RiskModel":
        """Fit the model on historical feature rows."""

    def predict_risk(self, row: dict[str, object]) -> float:
        """Return an unnormalized boot-risk score for one candidate row."""


RiskScorer = Callable[[dict[str, object]], float]

PRIMARY_MODEL_NAME = "historical_rate_baseline"


def evaluate_chronological(
    rows: list[dict[str, object]],
    model_factory: Callable[[], RiskModel],
    holdout_seasons: int = 5,
) -> dict[str, object]:
    """Evaluate boot-risk scoring on the latest completed seasons only.

    The unit of splitting is season. The unit of scoring is a boot event, where
    candidates are the players still in the game for one season/episode/n_boots
    state and exactly one candidate should have ``target_next_boot == 1``.
    """

    assert_no_leakage_columns(FEATURE_COLUMNS)
    completed_seasons = sorted({int(row["season"]) for row in rows})
    if len(completed_seasons) <= holdout_seasons:
        return {"status": "skipped", "reason": "Not enough completed seasons for chronological holdout."}

    holdout = completed_seasons[-holdout_seasons:]
    first_holdout_season = holdout[0]
    train = [row for row in rows if int(row["season"]) < first_holdout_season]
    test = [row for row in rows if int(row["season"]) in set(holdout)]
    assert_chronological_split(train, test)

    model = model_factory().fit(train)
    scorers: dict[str, RiskScorer] = {
        PRIMARY_MODEL_NAME: model.predict_risk,
        "uniform_random": lambda _row: 1.0,
        "prior_votes_heuristic": lambda row: 1.0 + _to_float(row.get("votes_received_to_date")),
    }

    event_groups = _group_events(test)
    results = [_score_events(name, scorer, event_groups) for name, scorer in scorers.items()]
    primary = results[0]
    if primary["events"] == 0:
        return {"status": "skipped", "reason": "No holdout boot events found."}

    calibration = _calibration_summary(primary["predictions"])
    primary_metrics = _metric_sections(primary)
    return {
        "status": "ok",
        "split": {
            "strategy": "chronological_holdout_by_season",
            "training_seasons": sorted({int(row["season"]) for row in train}),
            "holdout_seasons": holdout,
            "training_rows": len(train),
            "holdout_rows": len(test),
            "evaluated_events": primary["events"],
            "evaluated_candidates": primary["candidates"],
        },
        "primary_model": PRIMARY_MODEL_NAME,
        "metrics": primary_metrics,
        "baseline_comparisons": [_comparison_row(result) for result in results],
        "calibration": {
            "model": PRIMARY_MODEL_NAME,
            **calibration,
        },
        "notes": [
            "Top-k metrics are event-level ranking metrics.",
            "Brier score and calibration are candidate-level probability checks after event-level normalization.",
            "Log loss is the event-level negative log probability assigned to the actual boot.",
        ],
        # Backward-compatible summary aliases for older dashboard/API readers.
        "holdout_seasons": holdout,
        "events": primary["events"],
        "top1_accuracy": primary_metrics["ranking"]["top1_accuracy"],
        "top3_recall": primary_metrics["ranking"]["top3_recall"],
        "brier_score": primary_metrics["probability"]["brier_score"],
        "log_loss": primary_metrics["probability"]["log_loss"],
    }


def assert_chronological_split(
    train_rows: list[dict[str, object]],
    test_rows: list[dict[str, object]],
) -> None:
    """Raise when a holdout split contains same-season or future leakage."""

    if not train_rows or not test_rows:
        return
    train_seasons = {int(row["season"]) for row in train_rows}
    test_seasons = {int(row["season"]) for row in test_rows}
    overlapping = sorted(train_seasons.intersection(test_seasons))
    if overlapping:
        raise ValueError(f"Chronological split leakage: seasons appear in both train and holdout: {overlapping}")
    if max(train_seasons) >= min(test_seasons):
        raise ValueError("Chronological split leakage: training seasons must all precede holdout seasons.")


def _group_events(rows: list[dict[str, object]]) -> dict[tuple[int, int, int], list[dict[str, object]]]:
    grouped: dict[tuple[int, int, int], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        key = (int(row["season"]), int(row["episode"]), int(row["n_boots"]))
        grouped[key].append(row)
    return grouped


def _score_events(
    name: str,
    scorer: RiskScorer,
    event_groups: dict[tuple[int, int, int], list[dict[str, object]]],
) -> dict[str, object]:
    top1_hits = 0
    top3_hits = 0
    brier_values: list[float] = []
    log_losses: list[float] = []
    actual_probabilities: list[float] = []
    predictions: list[dict[str, float]] = []
    evaluated_events = 0
    evaluated_candidates = 0

    for candidates in event_groups.values():
        actual = [row for row in candidates if row["target_next_boot"] == 1]
        if not actual:
            continue
        evaluated_events += 1
        probabilities = _event_probabilities(candidates, scorer)
        ranked = sorted(candidates, key=lambda row: probabilities[id(row)], reverse=True)
        actual_id = actual[0]["castaway_id"]
        actual_probability = probabilities[id(actual[0])]
        actual_probabilities.append(actual_probability)
        log_losses.append(-math.log(actual_probability))

        if ranked[0]["castaway_id"] == actual_id:
            top1_hits += 1
        if any(row["castaway_id"] == actual_id for row in ranked[:3]):
            top3_hits += 1

        for row in candidates:
            target = float(row["target_next_boot"])
            probability = probabilities[id(row)]
            brier_values.append((probability - target) ** 2)
            predictions.append({"probability": probability, "target": target})
            evaluated_candidates += 1

    return {
        "name": name,
        "events": evaluated_events,
        "candidates": evaluated_candidates,
        "top1_accuracy": top1_hits / evaluated_events if evaluated_events else None,
        "top3_recall": top3_hits / evaluated_events if evaluated_events else None,
        "brier_score": mean(brier_values) if brier_values else None,
        "log_loss": mean(log_losses) if log_losses else None,
        "mean_actual_probability": mean(actual_probabilities) if actual_probabilities else None,
        "predictions": predictions,
    }


def _event_probabilities(
    candidates: list[dict[str, object]],
    scorer: RiskScorer,
) -> dict[int, float]:
    risks = {id(row): max(_to_float(scorer(row)), 1e-9) for row in candidates}
    total_risk = sum(risks.values()) or 1.0
    return {
        row_id: min(max(risk / total_risk, 1e-6), 1.0 - 1e-6)
        for row_id, risk in risks.items()
    }


def _metric_sections(result: dict[str, object]) -> dict[str, object]:
    return {
        "event_count": result["events"],
        "candidate_count": result["candidates"],
        "ranking": {
            "top1_accuracy": result["top1_accuracy"],
            "top3_recall": result["top3_recall"],
        },
        "probability": {
            "brier_score": result["brier_score"],
            "log_loss": result["log_loss"],
            "mean_actual_probability": result["mean_actual_probability"],
        },
    }


def _comparison_row(result: dict[str, object]) -> dict[str, object]:
    return {
        "name": result["name"],
        "events": result["events"],
        "top1_accuracy": result["top1_accuracy"],
        "top3_recall": result["top3_recall"],
        "brier_score": result["brier_score"],
        "log_loss": result["log_loss"],
        "mean_actual_probability": result["mean_actual_probability"],
    }


def _calibration_summary(
    predictions: list[dict[str, float]],
    bins: tuple[tuple[float, float], ...] = ((0.0, 0.05), (0.05, 0.10), (0.10, 0.20), (0.20, 0.40), (0.40, 1.0)),
) -> dict[str, object]:
    summaries: list[dict[str, object]] = []
    total = len(predictions)
    weighted_error = 0.0
    for lower, upper in bins:
        bucket = [
            prediction for prediction in predictions
            if lower <= prediction["probability"] < upper
            or (upper == 1.0 and lower <= prediction["probability"] <= upper)
        ]
        if not bucket:
            summaries.append(
                {
                    "range": f"[{lower:.2f}, {upper:.2f}]",
                    "count": 0,
                    "mean_predicted_probability": None,
                    "observed_boot_rate": None,
                    "absolute_error": None,
                }
            )
            continue
        predicted = mean(item["probability"] for item in bucket)
        observed = mean(item["target"] for item in bucket)
        absolute_error = abs(predicted - observed)
        weighted_error += absolute_error * len(bucket)
        summaries.append(
            {
                "range": f"[{lower:.2f}, {upper:.2f}]",
                "count": len(bucket),
                "mean_predicted_probability": predicted,
                "observed_boot_rate": observed,
                "absolute_error": absolute_error,
            }
        )
    return {
        "bins": summaries,
        "expected_calibration_error": weighted_error / total if total else None,
    }


def _to_float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0

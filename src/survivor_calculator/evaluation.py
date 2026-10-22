"""Chronological holdout evaluation for Survivor boot-risk baselines."""

from __future__ import annotations

import math
import random
from collections import defaultdict
from collections.abc import Sequence
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
RANKING_METRIC_VERSION = "expected_uniform_exact_ties_v1"
DEFAULT_HOLDOUT_POOL_SIZE = 10
DEFAULT_HOLDOUT_SEASONS_PER_POOL = 2
DEFAULT_HOLDOUT_RANDOM_SEED = 42


def evaluate_chronological(
    rows: list[dict[str, object]],
    model_factory: Callable[[], RiskModel],
    holdout_seasons: int = 5,
    model_name: str = PRIMARY_MODEL_NAME,
    comparison_model_factories: dict[str, Callable[[], RiskModel]] | None = None,
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

    return _evaluate_split(
        train,
        test,
        model_factory,
        model_name=model_name,
        comparison_model_factories=comparison_model_factories,
        split={
            "strategy": "chronological_holdout_by_season",
            "training_seasons": sorted({int(row["season"]) for row in train}),
            "holdout_seasons": holdout,
            "training_rows": len(train),
            "holdout_rows": len(test),
        },
    )


def evaluate_pooled_random_holdout(
    rows: list[dict[str, object]],
    model_factory: Callable[[], RiskModel],
    pool_size: int = DEFAULT_HOLDOUT_POOL_SIZE,
    holdout_seasons_per_pool: int = DEFAULT_HOLDOUT_SEASONS_PER_POOL,
    random_seed: int = DEFAULT_HOLDOUT_RANDOM_SEED,
    model_name: str = PRIMARY_MODEL_NAME,
    comparison_model_factories: dict[str, Callable[[], RiskModel]] | None = None,
) -> dict[str, object]:
    """Evaluate on random seasons drawn from chronological season pools.

    The default split creates chronological pools of ten completed seasons and
    holds out two seasons from each pool, producing an 80/20 season split for
    the current 50 completed-season data set.
    """

    assert_no_leakage_columns(FEATURE_COLUMNS)
    completed_seasons = sorted({int(row["season"]) for row in rows})
    if pool_size <= 0 or holdout_seasons_per_pool <= 0:
        raise ValueError("pool_size and holdout_seasons_per_pool must be positive.")
    if holdout_seasons_per_pool >= pool_size:
        raise ValueError("holdout_seasons_per_pool must be smaller than pool_size.")
    if len(completed_seasons) < pool_size:
        return {"status": "skipped", "reason": "Not enough completed seasons for pooled random holdout."}

    pools = [
        completed_seasons[index : index + pool_size]
        for index in range(0, len(completed_seasons), pool_size)
    ]
    full_pools = [pool for pool in pools if len(pool) == pool_size]
    if not full_pools:
        return {"status": "skipped", "reason": "No complete season pools available for pooled random holdout."}

    rng = random.Random(random_seed)
    holdout = sorted(
        season
        for pool in full_pools
        for season in rng.sample(pool, holdout_seasons_per_pool)
    )
    holdout_set = set(holdout)
    train = [row for row in rows if int(row["season"]) not in holdout_set]
    test = [row for row in rows if int(row["season"]) in holdout_set]
    assert_disjoint_season_split(train, test)

    return _evaluate_split(
        train,
        test,
        model_factory,
        model_name=model_name,
        comparison_model_factories=comparison_model_factories,
        split={
            "strategy": "pooled_random_holdout_by_season",
            "pool_size": pool_size,
            "holdout_seasons_per_pool": holdout_seasons_per_pool,
            "random_seed": random_seed,
            "season_pools": full_pools,
            "training_seasons": sorted({int(row["season"]) for row in train}),
            "holdout_seasons": holdout,
            "training_rows": len(train),
            "holdout_rows": len(test),
        },
    )


def _evaluate_split(
    train: list[dict[str, object]],
    test: list[dict[str, object]],
    model_factory: Callable[[], RiskModel],
    *,
    model_name: str,
    split: dict[str, object],
    comparison_model_factories: dict[str, Callable[[], RiskModel]] | None = None,
) -> dict[str, object]:
    if not train or not test:
        return {"status": "skipped", "reason": "Training and holdout rows are required for evaluation."}

    model = model_factory().fit(train)
    scorers: dict[str, RiskScorer] = {model_name: model.predict_risk}
    for comparison_name, comparison_factory in (comparison_model_factories or {}).items():
        if comparison_name == model_name:
            continue
        scorers[comparison_name] = comparison_factory().fit(train).predict_risk
    scorers.update(
        {
            "uniform_random": lambda _row: 1.0,
            "prior_votes_heuristic": lambda row: 1.0 + _to_float(row.get("votes_received_to_date")),
        }
    )

    event_groups = _group_events(test)
    results = [_score_events(name, scorer, event_groups) for name, scorer in scorers.items()]
    primary = results[0]
    if primary["events"] == 0:
        return {"status": "skipped", "reason": "No holdout boot events found."}

    calibration = _calibration_summary(primary["predictions"])
    primary_metrics = _metric_sections(primary)
    probability_quality = _probability_quality_summary(primary, results)
    return {
        "status": "ok",
        "split": {
            **split,
            "evaluated_events": primary["events"],
            "evaluated_candidates": primary["candidates"],
        },
        "primary_model": model_name,
        "ranking_metric_version": RANKING_METRIC_VERSION,
        "metrics": primary_metrics,
        "baseline_comparisons": [_comparison_row(result) for result in results],
        "probability_quality": probability_quality,
        "calibration": {
            "model": model_name,
            **calibration,
        },
        "notes": [
            "Top-k metrics are expected event-level hits under uniform random ordering within exactly equal scores.",
            "Brier score and calibration are candidate-level probability checks after event-level normalization.",
            "Log loss is the event-level negative log probability assigned to the actual boot.",
            "The historical-rate baseline should remain the default unless a candidate model lowers both holdout log loss and Brier score.",
        ],
        # Backward-compatible summary aliases for older dashboard/API readers.
        "holdout_seasons": split["holdout_seasons"],
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


def assert_disjoint_season_split(
    train_rows: list[dict[str, object]],
    test_rows: list[dict[str, object]],
) -> None:
    """Raise when training and holdout rows contain any overlapping season."""

    if not train_rows or not test_rows:
        return
    train_seasons = {int(row["season"]) for row in train_rows}
    test_seasons = {int(row["season"]) for row in test_rows}
    overlapping = sorted(train_seasons.intersection(test_seasons))
    if overlapping:
        raise ValueError(f"Season split leakage: seasons appear in both train and holdout: {overlapping}")


def _group_events(rows: list[dict[str, object]]) -> dict[tuple[int, int, int], list[dict[str, object]]]:
    grouped: dict[tuple[int, int, int], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        key = (int(row["season"]), int(row["episode"]), int(row.get("completed_exit_order", row["n_boots"])))
        grouped[key].append(row)
    return grouped


def expected_top_k_hit(scores: Sequence[float], actual_index: int, k: int) -> float:
    """Return expected inclusion of the actual outcome among the top k scores.

    Exactly equal numeric scores share uniformly random rank positions. If h
    scores are higher and t equal the actual score, its credit is
    max(0, min(t, k - h)) / t. Distinct scores are never rounded or merged by a
    tolerance. k=0 gives zero; k>=len(scores) gives one. Inputs must be finite,
    with a valid outcome index and a non-negative integer k.
    """
    if not scores:
        raise ValueError("Ranking requires at least one candidate score.")
    if not isinstance(k, int) or isinstance(k, bool) or k < 0:
        raise ValueError("k must be a non-negative integer.")
    if not isinstance(actual_index, int) or not 0 <= actual_index < len(scores):
        raise ValueError("actual_index must identify a candidate score.")
    if not all(math.isfinite(score) for score in scores):
        raise ValueError("Ranking scores must all be finite.")
    actual_score = scores[actual_index]
    higher = sum(score > actual_score for score in scores)
    tied = sum(score == actual_score for score in scores)
    return max(0, min(tied, k - higher)) / tied


def _score_events(
    name: str,
    scorer: RiskScorer,
    event_groups: dict[tuple[int, int, int], list[dict[str, object]]],
) -> dict[str, object]:
    top1_hits = 0.0
    top3_hits = 0.0
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
        if len(actual) != 1:
            raise ValueError("Each scored event must have exactly one actual boot.")
        evaluated_events += 1
        probabilities = _event_probabilities(candidates, scorer)
        actual_probability = probabilities[id(actual[0])]
        actual_probabilities.append(actual_probability)
        log_losses.append(-math.log(actual_probability))

        scores = [probabilities[id(row)] for row in candidates]
        actual_index = next(index for index, row in enumerate(candidates) if row is actual[0])
        top1_hits += expected_top_k_hit(scores, actual_index, 1)
        top3_hits += expected_top_k_hit(scores, actual_index, 3)

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
            "tie_handling": RANKING_METRIC_VERSION,
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


def _probability_quality_summary(
    primary: dict[str, object],
    results: list[dict[str, object]],
) -> dict[str, object]:
    baseline = next((result for result in results if result["name"] == PRIMARY_MODEL_NAME), None)
    if baseline is None or primary["name"] == PRIMARY_MODEL_NAME:
        return {
            "reference_model": PRIMARY_MODEL_NAME,
            "candidate_model": primary["name"],
            "recommendation": "baseline_default",
            "reason": "The historical-rate baseline is the primary model.",
        }

    primary_log_loss = primary["log_loss"]
    baseline_log_loss = baseline["log_loss"]
    primary_brier = primary["brier_score"]
    baseline_brier = baseline["brier_score"]
    if None in (primary_log_loss, baseline_log_loss, primary_brier, baseline_brier):
        return {
            "reference_model": PRIMARY_MODEL_NAME,
            "candidate_model": primary["name"],
            "recommendation": "keep_baseline_default",
            "reason": "Probability metrics were unavailable for at least one compared model.",
        }

    log_loss_delta = float(primary_log_loss) - float(baseline_log_loss)
    brier_delta = float(primary_brier) - float(baseline_brier)
    improves_probability_quality = log_loss_delta < 0 and brier_delta < 0
    return {
        "reference_model": PRIMARY_MODEL_NAME,
        "candidate_model": primary["name"],
        "log_loss_delta_vs_baseline": log_loss_delta,
        "brier_score_delta_vs_baseline": brier_delta,
        "improves_probability_quality": improves_probability_quality,
        "recommendation": "experimental_probability_quality_improved"
        if improves_probability_quality
        else "keep_baseline_default",
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


def evaluate_relationship_diagnostics(
    rows: list[dict[str, object]], model_factory: Callable[[], RiskModel], *,
    model_name: str, comparison_model_factories: dict[str, Callable[[], RiskModel]],
    holdout_seasons: list[int], random_seed: int = 42, bootstrap_samples: int = 1000,
) -> dict[str, object]:
    """Score full events in predefined slices and bootstrap paired season blocks.

    Use the same earlier-season training cutoff as the primary chronological
    comparison. This exploratory reused holdout does not tune model settings.
    """
    if bootstrap_samples <= 0:
        raise ValueError("bootstrap_samples must be positive.")
    if not holdout_seasons:
        return {"status": "skipped", "reason": "No chronological holdout available."}
    train = [r for r in rows if int(r["season"]) < min(holdout_seasons)]
    test = [r for r in rows if int(r["season"]) in holdout_seasons]
    groups = _group_events(test)
    def report(selected: list[dict[str, object]]) -> dict[str, object]:
        if not selected:
            return {"status": "skipped", "reason": "No eligible events in this slice."}
        result = _evaluate_split(train, selected, model_factory, model_name=model_name,
                                 comparison_model_factories=comparison_model_factories,
                                 split={"holdout_seasons": holdout_seasons, "strategy": "same_chronological_training_cutoff"})
        if result["status"] != "ok":
            return result
        return {"status": "ok", "candidates": result["split"]["evaluated_candidates"],
                "baseline_comparisons": result["baseline_comparisons"]}
    slices = {}
    for label, predicate in {
        "swapped": lambda event: any(r.get("tribe_status_display") == "Swapped" for r in event),
        "merged": lambda event: all(r.get("tribe_status_display") == "Merged" for r in event),
        "sparse_relationship_history": lambda event: sum(float(r.get("social_known_pair_fraction") or 0) for r in event) / len(event) < 0.25,
    }.items():
        slices[label] = report([r for event in groups.values() if predicate(event) for r in event])
    by_season = {str(s): report([r for r in test if int(r["season"]) == s]) for s in holdout_seasons}
    usable = [r for r in by_season.values() if r["status"] == "ok"]
    intervals = {}
    if usable and PRIMARY_MODEL_NAME in comparison_model_factories:
        generator = random.Random(random_seed)
        deltas = {"log_loss": [], "brier_score": []}
        for _ in range(bootstrap_samples):
            sample = generator.choices(usable, k=len(usable))
            for metric in deltas:
                numerator = denominator = 0.0
                for season in sample:
                    compared = {r["name"]: r for r in season["baseline_comparisons"]}
                    weight = compared[model_name]["events"] if metric == "log_loss" else season["candidates"]
                    numerator += (compared[model_name][metric] - compared[PRIMARY_MODEL_NAME][metric]) * weight
                    denominator += weight
                deltas[metric].append(numerator / denominator)
        for metric, values in deltas.items():
            values.sort()
            intervals[metric + "_delta_vs_baseline_95pct"] = [values[int(0.025 * len(values))], values[min(len(values) - 1, int(0.975 * len(values)))]]
    return {"status": "ok", "slices": slices, "per_season": by_season,
            "season_block_bootstrap": {"seed": random_seed, "samples": bootstrap_samples,
                                        "intervals": intervals},
            "notes": ["Exploratory comparison on a previously inspected holdout; no automatic promotion.",
                      "Slices preserve every candidate in each selected event.",
                      "Bootstrap resamples whole seasons; five seasons give limited uncertainty evidence.",
                      "Negative metric differences favor the social model; intervals spanning zero are inconclusive."]}

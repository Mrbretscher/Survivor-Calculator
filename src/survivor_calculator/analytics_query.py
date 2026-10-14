"""Validated analytics chart queries over player-season rows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

from survivor_calculator.analytics import ANALYTICS_PLAYER_SEASON_COLUMNS

FilterOperator = Literal["equals", "not_equals", "in", "not_in", "range", "is_true", "is_false"]
SortDirection = Literal["asc", "desc"]


class AnalyticsQueryError(ValueError):
    """Raised when an analytics chart config is invalid."""


@dataclass(frozen=True)
class DimensionDefinition:
    id: str
    label: str
    column: str
    labels: dict[str, str] | None = None


@dataclass(frozen=True)
class MetricDefinition:
    id: str
    label: str
    format: Literal["integer", "decimal", "percent"]
    default_sort_direction: SortDirection
    minimum_sample_size: int
    proxy: bool
    description: str
    warning: str | None
    compute: Callable[[list[dict[str, object]], int], tuple[float | int | None, int, str | None]]


AGE_BUCKET_LABELS = {
    "under_25": "Under 25",
    "25_34": "25-34",
    "35_44": "35-44",
    "45_plus": "45+",
    "unknown": "Unknown",
}

DIMENSIONS = {
    "occupation": DimensionDefinition("occupation", "Occupation", "occupation"),
    "age_bucket": DimensionDefinition("age_bucket", "Age Bucket", "age_bucket", AGE_BUCKET_LABELS),
    "soc_major_group": DimensionDefinition("soc_major_group", "SOC Major Group", "soc_major_group"),
    "gender": DimensionDefinition("gender", "Gender", "gender"),
    "version": DimensionDefinition("version", "Version", "version"),
}

METRICS = {
    "contestant_count": MetricDefinition(
        id="contestant_count",
        label="Contestants Cast",
        format="integer",
        default_sort_direction="desc",
        minimum_sample_size=1,
        proxy=False,
        description="Count of castaway-season rows.",
        warning=None,
        compute=lambda rows, minimum: (len(rows), len(rows), None),
    ),
    "winner_count": MetricDefinition(
        id="winner_count",
        label="Winners",
        format="integer",
        default_sort_direction="desc",
        minimum_sample_size=1,
        proxy=False,
        description="Count of castaway-season rows marked as winners.",
        warning=None,
        compute=lambda rows, minimum: (_count_true(rows, "winner"), len(rows), None),
    ),
    "team_challenge_win_rate": MetricDefinition(
        id="team_challenge_win_rate",
        label="Team Challenge Win Rate",
        format="percent",
        default_sort_direction="desc",
        minimum_sample_size=5,
        proxy=False,
        description="Team or tribal challenge wins divided by team or tribal challenge appearances.",
        warning=None,
        compute=lambda rows, minimum: _rate_from_sums(
            rows,
            "team_challenge_wins_total",
            "team_challenge_appearances_total",
            minimum,
        ),
    ),
    "individual_immunity_win_rate": MetricDefinition(
        id="individual_immunity_win_rate",
        label="Individual Immunity Win Rate",
        format="percent",
        default_sort_direction="desc",
        minimum_sample_size=3,
        proxy=False,
        description="Individual immunity wins divided by individual immunity appearances.",
        warning=None,
        compute=lambda rows, minimum: _rate_from_sums(
            rows,
            "individual_immunity_wins_total",
            "individual_immunity_appearances_total",
            minimum,
        ),
    ),
    "social_proxy_no_votes_rate": MetricDefinition(
        id="social_proxy_no_votes_rate",
        label="Social performance proxy: no-vote rate",
        format="percent",
        default_sort_direction="desc",
        minimum_sample_size=5,
        proxy=True,
        description=(
            "Share of castaway-season records with vote activity where the player received zero "
            "counted votes. This is a vote-record proxy, not a direct measure of social performance."
        ),
        warning=(
            "Social performance proxy: this vote-history signal does not measure relationships, "
            "influence, strategic agency, or jury management."
        ),
        compute=lambda rows, minimum: _rate_from_condition(
            rows,
            lambda row: _number(row.get("votes_received_total")) == 0,
            minimum,
            _has_recorded_vote_activity,
        ),
    ),
}

SUPPORTED_FILTER_FIELDS = set(ANALYTICS_PLAYER_SEASON_COLUMNS)
SORT_FIELDS = {"label", "value", "count", "sample_size", *METRICS}


PRESET_CONFIGS: tuple[dict[str, object], ...] = (
    {
        "id": "occupations_cast_most_often",
        "title": "Occupations Cast Most Often",
        "dimension": "occupation",
        "metric": "contestant_count",
        "sort": {"field": "value", "direction": "desc"},
        "limit": 20,
    },
    {
        "id": "occupations_best_team_challenge_win_rate",
        "title": "Occupations With Best Team Challenge Win Rate",
        "dimension": "occupation",
        "metric": "team_challenge_win_rate",
        "sort": {"field": "value", "direction": "desc"},
        "limit": 20,
    },
    {
        "id": "occupations_best_individual_immunity_win_rate",
        "title": "Occupations With Best Individual Immunity Win Rate",
        "dimension": "occupation",
        "metric": "individual_immunity_win_rate",
        "sort": {"field": "value", "direction": "desc"},
        "limit": 20,
    },
    {
        "id": "occupations_best_social_proxy",
        "title": "Occupations With Best Social Performance Proxy",
        "dimension": "occupation",
        "metric": "social_proxy_no_votes_rate",
        "sort": {"field": "value", "direction": "desc"},
        "limit": 20,
    },
    {
        "id": "occupations_most_winners",
        "title": "Occupations With Most Winners",
        "dimension": "occupation",
        "metric": "winner_count",
        "sort": {"field": "value", "direction": "desc"},
        "limit": 20,
    },
    {
        "id": "age_buckets_cast_most_often",
        "title": "Age Buckets Cast Most Often",
        "dimension": "age_bucket",
        "metric": "contestant_count",
        "sort": {"field": "value", "direction": "desc"},
    },
    {
        "id": "age_buckets_best_team_challenge_win_rate",
        "title": "Age Buckets With Best Team Challenge Win Rate",
        "dimension": "age_bucket",
        "metric": "team_challenge_win_rate",
        "sort": {"field": "value", "direction": "desc"},
    },
    {
        "id": "age_buckets_best_individual_immunity_win_rate",
        "title": "Age Buckets With Best Individual Immunity Win Rate",
        "dimension": "age_bucket",
        "metric": "individual_immunity_win_rate",
        "sort": {"field": "value", "direction": "desc"},
    },
    {
        "id": "age_buckets_best_social_proxy",
        "title": "Age Buckets With Best Social Performance Proxy",
        "dimension": "age_bucket",
        "metric": "social_proxy_no_votes_rate",
        "sort": {"field": "value", "direction": "desc"},
    },
    {
        "id": "age_buckets_most_winners",
        "title": "Age Buckets With Most Winners",
        "dimension": "age_bucket",
        "metric": "winner_count",
        "sort": {"field": "value", "direction": "desc"},
    },
)


def preset_configs() -> list[dict[str, object]]:
    return [dict(preset) for preset in PRESET_CONFIGS]


def run_chart_query(rows: list[dict[str, object]], config: dict[str, object]) -> dict[str, object]:
    if not isinstance(config, dict):
        raise AnalyticsQueryError("config must be an object")
    dimension = _dimension(_required_string(config, "dimension"))
    metric = _metric(_required_string(config, "metric"))
    filters = _filters(config.get("filters", []))
    minimum_sample_size = _minimum_sample_size(config, metric)
    sort = _sort(config.get("sort"), metric)
    limit = _limit(config.get("limit"))

    filtered_rows = [row for row in rows if _passes_filters(row, filters)]
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in filtered_rows:
        key = _dimension_key(row.get(dimension.column))
        grouped.setdefault(key, []).append(row)

    chart_rows = []
    warnings = []
    if metric.warning:
        warnings.append(metric.warning)
    suppressed_rows = 0
    for key, group_rows in grouped.items():
        value, sample_size, suppressed_reason = metric.compute(group_rows, minimum_sample_size)
        if suppressed_reason:
            suppressed_rows += 1
        chart_rows.append(
            {
                "key": key,
                "label": _dimension_label(dimension, key),
                "value": value,
                "count": len(group_rows),
                "sample_size": sample_size,
                "eligible": suppressed_reason is None,
                "suppressed_reason": suppressed_reason,
            }
        )

    chart_rows = _sort_rows(chart_rows, sort)
    if limit is not None:
        chart_rows = chart_rows[:limit]

    return {
        "metadata": {
            "dimension": {
                "id": dimension.id,
                "label": dimension.label,
            },
            "metric": {
                "id": metric.id,
                "label": metric.label,
                "format": metric.format,
                "proxy": metric.proxy,
                "description": metric.description,
            },
            "total_row_count": len(rows),
            "filtered_row_count": len(filtered_rows),
            "returned_row_count": len(chart_rows),
            "minimum_sample_size": minimum_sample_size,
            "suppressed_row_count": suppressed_rows,
            "warnings": warnings,
        },
        "rows": chart_rows,
    }


def _dimension(dimension_id: str) -> DimensionDefinition:
    try:
        return DIMENSIONS[dimension_id]
    except KeyError as exc:
        raise AnalyticsQueryError(f"Unsupported dimension: {dimension_id}") from exc


def _metric(metric_id: str) -> MetricDefinition:
    try:
        return METRICS[metric_id]
    except KeyError as exc:
        raise AnalyticsQueryError(f"Unsupported metric: {metric_id}") from exc


def _filters(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        raise AnalyticsQueryError("filters must be a list")
    filters = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise AnalyticsQueryError(f"filters[{index}] must be an object")
        field = _required_string(item, "field")
        operator = _required_string(item, "operator")
        if field not in SUPPORTED_FILTER_FIELDS:
            raise AnalyticsQueryError(f"Unsupported filter field: {field}")
        if operator not in {"equals", "not_equals", "in", "not_in", "range", "is_true", "is_false"}:
            raise AnalyticsQueryError(f"Unsupported filter operator: {operator}")
        if operator in {"equals", "not_equals", "range", "in", "not_in"} and "value" not in item:
            raise AnalyticsQueryError(f"Filter for {field} requires a value")
        filters.append({"field": field, "operator": operator, "value": item.get("value")})
    return filters


def _sort(value: object, metric: MetricDefinition) -> dict[str, str]:
    if value is None:
        return {"field": "value", "direction": metric.default_sort_direction}
    if not isinstance(value, dict):
        raise AnalyticsQueryError("sort must be an object")
    field = _required_string(value, "field")
    direction = _required_string(value, "direction")
    if field not in SORT_FIELDS:
        raise AnalyticsQueryError(f"Unsupported sort field: {field}")
    if direction not in {"asc", "desc"}:
        raise AnalyticsQueryError(f"Unsupported sort direction: {direction}")
    return {"field": field, "direction": direction}


def _limit(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise AnalyticsQueryError("limit must be an integer")
    if value <= 0:
        raise AnalyticsQueryError("limit must be greater than zero")
    return value


def _minimum_sample_size(config: dict[str, object], metric: MetricDefinition) -> int:
    value = config.get("minimum_sample_size", metric.minimum_sample_size)
    if isinstance(value, bool) or not isinstance(value, int):
        raise AnalyticsQueryError("minimum_sample_size must be an integer")
    if value <= 0:
        raise AnalyticsQueryError("minimum_sample_size must be greater than zero")
    return value


def _passes_filters(row: dict[str, object], filters: list[dict[str, object]]) -> bool:
    return all(_passes_filter(row, item) for item in filters)


def _passes_filter(row: dict[str, object], item: dict[str, object]) -> bool:
    actual = row.get(str(item["field"]))
    operator = item["operator"]
    expected = item.get("value")
    if operator == "equals":
        return _normalized(actual) == _normalized(expected)
    if operator == "not_equals":
        return _normalized(actual) != _normalized(expected)
    if operator == "in":
        if not isinstance(expected, list):
            raise AnalyticsQueryError("in filter value must be a list")
        return _normalized(actual) in {_normalized(value) for value in expected}
    if operator == "not_in":
        if not isinstance(expected, list):
            raise AnalyticsQueryError("not_in filter value must be a list")
        return _normalized(actual) not in {_normalized(value) for value in expected}
    if operator == "range":
        return _in_range(actual, expected)
    if operator == "is_true":
        return _bool(actual)
    if operator == "is_false":
        return not _bool(actual)
    raise AnalyticsQueryError(f"Unsupported filter operator: {operator}")


def _in_range(actual: object, expected: object) -> bool:
    if not isinstance(expected, dict):
        raise AnalyticsQueryError("range filter value must be an object")
    actual_number = _number(actual)
    if actual_number is None:
        return False
    minimum = expected.get("min")
    maximum = expected.get("max")
    if minimum is not None:
        minimum_number = _number(minimum)
        if minimum_number is None:
            raise AnalyticsQueryError("range min must be numeric")
        if actual_number < minimum_number:
            return False
    if maximum is not None:
        maximum_number = _number(maximum)
        if maximum_number is None:
            raise AnalyticsQueryError("range max must be numeric")
        if actual_number > maximum_number:
            return False
    return True


def _sort_rows(rows: list[dict[str, object]], sort: dict[str, str]) -> list[dict[str, object]]:
    field = sort["field"]
    direction = sort["direction"]

    def row_value(row: dict[str, object]) -> object:
        if field == "value" or field in METRICS:
            return row["value"]
        return row.get(field)

    def sort_value(row: dict[str, object]) -> object:
        value = row_value(row)
        if isinstance(value, str):
            return value.lower()
        return value

    populated = [row for row in rows if row_value(row) is not None]
    suppressed = [row for row in rows if row_value(row) is None]
    populated = sorted(populated, key=sort_value, reverse=direction == "desc")
    suppressed = sorted(suppressed, key=lambda row: str(row["label"]).lower())
    return populated + suppressed


def _dimension_key(value: object) -> str:
    text = "" if value is None else str(value)
    return text if text else "Unknown"


def _dimension_label(dimension: DimensionDefinition, key: str) -> str:
    if dimension.labels:
        return dimension.labels.get(key, key)
    return key


def _rate_from_sums(
    rows: list[dict[str, object]],
    numerator_column: str,
    denominator_column: str,
    minimum_sample_size: int,
) -> tuple[float | None, int, str | None]:
    numerator = sum(_number(row.get(numerator_column)) or 0.0 for row in rows)
    denominator = sum(_number(row.get(denominator_column)) or 0.0 for row in rows)
    if denominator == 0:
        return None, 0, "No supported observations for this metric."
    if denominator < minimum_sample_size:
        return None, int(denominator), f"Minimum sample size is {minimum_sample_size}."
    return numerator / denominator, int(denominator), None


def _rate_from_condition(
    rows: list[dict[str, object]],
    predicate: Callable[[dict[str, object]], bool],
    minimum_sample_size: int,
    observation_predicate: Callable[[dict[str, object]], bool] | None = None,
) -> tuple[float | None, int, str | None]:
    observations = [row for row in rows if observation_predicate is None or observation_predicate(row)]
    denominator = len(observations)
    if denominator == 0:
        return None, 0, "No supported observations for this metric."
    if denominator < minimum_sample_size:
        return None, denominator, f"Minimum sample size is {minimum_sample_size}."
    numerator = sum(1 for row in observations if predicate(row))
    return numerator / denominator, denominator, None


def _has_recorded_vote_activity(row: dict[str, object]) -> bool:
    return any(
        (_number(row.get(column)) or 0.0) > 0
        for column in ("votes_cast_total", "votes_received_total")
    )


def _count_true(rows: list[dict[str, object]], column: str) -> int:
    return sum(1 for row in rows if _bool(row.get(column)))


def _required_string(mapping: dict[str, object], field: str) -> str:
    value = mapping.get(field)
    if not isinstance(value, str) or not value:
        raise AnalyticsQueryError(f"{field} must be a non-empty string")
    return value


def _normalized(value: object) -> object:
    if isinstance(value, str):
        return value.strip().lower()
    return value


def _number(value: object) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, int | float):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value != 0
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes"}
    return False

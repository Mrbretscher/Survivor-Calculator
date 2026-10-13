"""Optional scikit-learn models for experimental Survivor predictions."""

from __future__ import annotations

from survivor_calculator.features import FEATURE_COLUMNS, assert_no_leakage_columns, to_float, to_int

EXPERIMENTAL_NEXT_BOOT_MODEL = "experimental_next_boot"

NUMERIC_FEATURES = (
    "episode",
    "n_boots",
    "final_n",
    "age",
    "tribe_size",
    "challenge_wins_to_date",
    "individual_immunity_wins_to_date",
    "votes_received_to_date",
    "votes_cast_to_date",
    "confessionals_to_date",
    "confessional_time_to_date",
    "advantages_held_to_date",
)
CATEGORICAL_FEATURES = (
    "gender",
    "soc_major_group",
    "tribe_status",
)


class ExperimentalNextBootModel:
    """Regularized logistic next-boot risk model using optional scikit-learn."""

    def __init__(self) -> None:
        try:
            from sklearn.compose import ColumnTransformer
            from sklearn.impute import SimpleImputer
            from sklearn.linear_model import LogisticRegression
            from sklearn.pipeline import Pipeline
            from sklearn.preprocessing import OneHotEncoder, StandardScaler
        except ModuleNotFoundError as exc:  # pragma: no cover - depends on optional extras
            raise RuntimeError(
                "The experimental model requires scikit-learn. "
                "Install the optional ML extras with: pip install -e \".[ml]\""
            ) from exc

        assert_no_leakage_columns(FEATURE_COLUMNS)
        numeric_pipeline = Pipeline(
            steps=[
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
            ]
        )
        categorical_pipeline = Pipeline(
            steps=[
                ("imputer", SimpleImputer(strategy="most_frequent")),
                ("one_hot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
            ]
        )
        self._pipeline = Pipeline(
            steps=[
                (
                    "preprocess",
                    ColumnTransformer(
                        transformers=[
                            ("numeric", numeric_pipeline, list(NUMERIC_FEATURES)),
                            ("categorical", categorical_pipeline, list(CATEGORICAL_FEATURES)),
                        ],
                        remainder="drop",
                    ),
                ),
                (
                    "model",
                    LogisticRegression(
                        class_weight="balanced",
                        C=0.5,
                        max_iter=1000,
                        random_state=42,
                    ),
                ),
            ]
        )
        self._constant_probability: float | None = None

    def fit(self, rows: list[dict[str, object]]) -> "ExperimentalNextBootModel":
        if not rows:
            self._constant_probability = 0.05
            return self

        targets = [int(row["target_next_boot"]) for row in rows]
        positives = sum(targets)
        if positives == 0 or positives == len(targets):
            self._constant_probability = max(min(positives / len(targets), 0.999), 0.001)
            return self

        self._pipeline.fit([_model_row(row) for row in rows], targets)
        self._constant_probability = None
        return self

    def predict_risk(self, row: dict[str, object]) -> float:
        if self._constant_probability is not None:
            return self._constant_probability
        probability = float(self._pipeline.predict_proba([_model_row(row)])[0][1])
        return min(max(probability, 0.001), 0.999)


def _model_row(row: dict[str, object]) -> dict[str, object]:
    model_row: dict[str, object] = {}
    for feature in NUMERIC_FEATURES:
        value = row.get(feature)
        if feature in {"episode", "n_boots", "final_n", "age", "tribe_size"}:
            model_row[feature] = to_int(value)
        else:
            model_row[feature] = to_float(value)
    for feature in CATEGORICAL_FEATURES:
        model_row[feature] = str(row.get(feature) or "Unknown")
    return model_row

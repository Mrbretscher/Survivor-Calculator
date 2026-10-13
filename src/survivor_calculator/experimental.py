"""Optional scikit-learn models for experimental Survivor predictions."""

from __future__ import annotations

from survivor_calculator.features import FEATURE_COLUMNS, assert_no_leakage_columns, to_float, to_int

EXPERIMENTAL_NEXT_BOOT_MODEL = "experimental_next_boot"
OCCUPATION_TEXT_NEXT_BOOT_MODEL = "occupation_text_next_boot"

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
OCCUPATION_STRUCTURED_FEATURES = (
    "gender",
    "soc_code",
    "soc_title",
    "soc_major_group",
    "tribe_status",
)
OCCUPATION_TEXT_FEATURES = (
    "occupation",
    "soc_title",
    "soc_major_group",
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


class OccupationTextNextBootModel:
    """Regularized logistic model with tokenized occupation and SOC text."""

    def __init__(self) -> None:
        try:
            from sklearn.feature_extraction import DictVectorizer
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.linear_model import LogisticRegression
            from sklearn.pipeline import FeatureUnion, Pipeline
            from sklearn.preprocessing import FunctionTransformer, StandardScaler
        except ModuleNotFoundError as exc:  # pragma: no cover - depends on optional extras
            raise RuntimeError(
                "The occupation text model requires scikit-learn. "
                "Install the optional ML extras with: pip install -e \".[ml]\""
            ) from exc

        assert_no_leakage_columns(FEATURE_COLUMNS)
        structured_pipeline = Pipeline(
            steps=[
                ("select", FunctionTransformer(_structured_rows, validate=False)),
                ("vectorize", DictVectorizer(sparse=True)),
                ("scale", StandardScaler(with_mean=False)),
            ]
        )
        occupation_text_pipeline = Pipeline(
            steps=[
                ("select", FunctionTransformer(_occupation_texts, validate=False)),
                (
                    "tokenize",
                    TfidfVectorizer(
                        lowercase=True,
                        ngram_range=(1, 2),
                        min_df=1,
                    ),
                ),
            ]
        )
        self._pipeline = Pipeline(
            steps=[
                (
                    "features",
                    FeatureUnion(
                        transformer_list=[
                            ("structured", structured_pipeline),
                            ("occupation_text", occupation_text_pipeline),
                        ]
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

    def fit(self, rows: list[dict[str, object]]) -> "OccupationTextNextBootModel":
        if not rows:
            self._constant_probability = 0.05
            return self

        targets = [int(row["target_next_boot"]) for row in rows]
        positives = sum(targets)
        if positives == 0 or positives == len(targets):
            self._constant_probability = max(min(positives / len(targets), 0.999), 0.001)
            return self

        self._pipeline.fit(rows, targets)
        self._constant_probability = None
        return self

    def predict_risk(self, row: dict[str, object]) -> float:
        if self._constant_probability is not None:
            return self._constant_probability
        probability = float(self._pipeline.predict_proba([row])[0][1])
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


def _structured_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    return [_structured_row(row) for row in rows]


def _structured_row(row: dict[str, object]) -> dict[str, object]:
    model_row: dict[str, object] = {}
    for feature in NUMERIC_FEATURES:
        value = row.get(feature)
        if feature in {"episode", "n_boots", "final_n", "age", "tribe_size"}:
            model_row[feature] = to_int(value) or 0
        else:
            model_row[feature] = to_float(value)
    for feature in OCCUPATION_STRUCTURED_FEATURES:
        model_row[feature] = str(row.get(feature) or "Unknown")
    return model_row


def _occupation_texts(rows: list[dict[str, object]]) -> list[str]:
    return [_occupation_text(row) for row in rows]


def _occupation_text(row: dict[str, object]) -> str:
    return " ".join(str(row.get(feature) or "") for feature in OCCUPATION_TEXT_FEATURES)

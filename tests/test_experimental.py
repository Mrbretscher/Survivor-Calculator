from __future__ import annotations

import importlib.util
import unittest

from fixtures import minimal_core_tables
from survivor_calculator.features import build_features


@unittest.skipUnless(importlib.util.find_spec("sklearn"), "Requires the existing optional [ml] dependency.")
class OptionalModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.features = build_features(minimal_core_tables())

    def test_logistic_fits_mixed_features_and_predicts_unseen_categories(self) -> None:
        from survivor_calculator.experimental import ExperimentalNextBootModel
        model = ExperimentalNextBootModel().fit(self.features.historical_rows)
        row = {**self.features.current_rows[0], "gender": "Unseen", "tribe_status": "New status", "age": None}
        probability = model.predict_risk(row)
        self.assertGreater(probability, 0)
        self.assertLess(probability, 1)

    def test_prediction_does_not_refit_training_imputation(self) -> None:
        from survivor_calculator.experimental import ExperimentalNextBootModel, NUMERIC_FEATURES
        model = ExperimentalNextBootModel().fit(self.features.historical_rows)
        numeric = model._pipeline.named_steps["preprocess"].named_transformers_["numeric"]
        imputer = numeric.named_steps["imputer"]
        age_index = NUMERIC_FEATURES.index("age")
        median_age = imputer.statistics_[age_index]
        self.assertEqual(median_age, 42)
        model.predict_risk({**self.features.current_rows[0], "age": 10000})
        self.assertEqual(imputer.statistics_[age_index], median_age)

    def test_constant_class_training_uses_existing_fallback(self) -> None:
        from survivor_calculator.experimental import ExperimentalNextBootModel
        model = ExperimentalNextBootModel().fit([{**r, "target_next_boot": 0} for r in self.features.historical_rows])
        self.assertEqual(model.predict_risk(self.features.current_rows[0]), 0.001)

    def test_occupation_and_hybrid_models_execute_with_same_input_contract(self) -> None:
        from survivor_calculator.baseline import HybridNextBootModel
        from survivor_calculator.experimental import OccupationTextNextBootModel
        for cls in (OccupationTextNextBootModel, HybridNextBootModel):
            with self.subTest(model=cls.__name__):
                model = cls().fit(self.features.historical_rows)
                self.assertTrue(0 < model.predict_risk(self.features.current_rows[0]) < 1)


if __name__ == "__main__":
    unittest.main()

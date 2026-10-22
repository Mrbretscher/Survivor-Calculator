from __future__ import annotations

import html
import json
import tempfile
import unittest
from pathlib import Path

from fixtures import minimal_core_tables
from survivor_calculator.baseline import build_predictions
from survivor_calculator.dashboard import build_dashboard
from survivor_calculator.evaluation import evaluate_chronological
from survivor_calculator.features import build_features
from test_evaluation import ConstantRiskModel, _evaluation_rows


class DashboardEvaluationTests(unittest.TestCase):
    def test_dashboard_preserves_fractional_metrics_and_their_method(self) -> None:
        features = build_features(minimal_core_tables())
        payload = build_predictions(features, Path("fixture.xlsx")).to_dict()
        evaluation = evaluate_chronological(_evaluation_rows(), ConstantRiskModel, holdout_seasons=2)
        payload["evaluation"] = evaluation
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "predictions.json"
            source.write_text(json.dumps(payload), encoding="utf8")
            result = build_dashboard(source, Path(directory) / "dashboard.html").read_text(encoding="utf8")
        self.assertEqual(evaluation["top1_accuracy"], 1/3)
        self.assertIn(html.escape(json.dumps(evaluation, indent=2)), result)
        self.assertIn("expected_uniform_exact_ties_v1", result)
        self.assertIn("uniform random ordering", result)


if __name__ == "__main__":
    unittest.main()

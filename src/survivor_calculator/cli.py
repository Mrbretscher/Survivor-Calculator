"""Command-line entry points for the Survivor Calculator pipeline."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from survivor_calculator.analytics import build_player_season_rows, export_player_season_rows
from survivor_calculator.baseline import (
    MODEL_NAME_ALIASES,
    build_predictions,
    resolve_model_name,
    save_predictions,
    validate_model_available,
)
from survivor_calculator.dashboard import build_dashboard
from survivor_calculator.features import build_features
from survivor_calculator.ingest import CORE_SHEETS, WorkbookReader, load_core_tables
from survivor_calculator.soc import export_soc_mapping

DEFAULT_WORKBOOK = Path("survivoR.xlsx")
DEFAULT_OUTPUT_DIR = Path("data/processed")
DEFAULT_PREDICTIONS = DEFAULT_OUTPUT_DIR / "current_predictions.json"
DEFAULT_DASHBOARD = DEFAULT_OUTPUT_DIR / "dashboard.html"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Survivor prediction pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="Inspect workbook schema")
    inspect_parser.add_argument("--workbook", default=str(DEFAULT_WORKBOOK))

    build_parser = subparsers.add_parser("build", help="Build clean tables and predictions")
    build_parser.add_argument("--workbook", default=str(DEFAULT_WORKBOOK))
    build_parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    build_parser.add_argument(
        "--model",
        choices=sorted(MODEL_NAME_ALIASES),
        default="historical-rate-baseline",
        help="Prediction model to use. The historical-rate baseline remains the default.",
    )
    build_parser.add_argument(
        "--evaluation-strategy",
        choices=("pooled-random", "chronological"),
        default="pooled-random",
        help="Validation strategy to report in prediction metadata.",
    )

    refresh_parser = subparsers.add_parser("refresh", help="Fetch changed upstream data and retrain")
    refresh_parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    refresh_parser.add_argument("--model", choices=sorted(MODEL_NAME_ALIASES), default="historical-rate-baseline")
    refresh_parser.add_argument("--force", action="store_true", help="Rebuild even when data is unchanged")

    dashboard_parser = subparsers.add_parser("dashboard", help="Build static dashboard HTML")
    dashboard_parser.add_argument("--predictions", default=str(DEFAULT_PREDICTIONS))
    dashboard_parser.add_argument("--output", default=str(DEFAULT_DASHBOARD))

    serve_parser = subparsers.add_parser("serve-api", help="Serve the local prediction API without extra dependencies")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8000)

    args = parser.parse_args(argv)
    if args.command == "refresh":
        from survivor_calculator.refresh import refresh

        try:
            changed = refresh(Path(args.output_dir), args.model, force=args.force)
        except (OSError, ValueError, RuntimeError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        print("Rebuilt from upstream data." if changed else "Upstream data unchanged; skipped retraining.")
        return 0
    if args.command == "inspect":
        return _inspect(Path(args.workbook))
    if args.command == "build":
        try:
            return _build(
                Path(args.workbook),
                Path(args.output_dir),
                resolve_model_name(args.model),
                args.evaluation_strategy,
            )
        except RuntimeError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    if args.command == "dashboard":
        output = build_dashboard(args.predictions, args.output)
        print(f"Wrote dashboard: {output}")
        return 0
    if args.command == "serve-api":
        from survivor_calculator.server import run_server

        run_server(args.host, args.port)
        return 0
    raise ValueError(f"Unknown command: {args.command}")


def _inspect(workbook: Path) -> int:
    with WorkbookReader(workbook) as reader:
        for schema in reader.schemas():
            print(f"{schema.name}: {schema.rows} rows, {len(schema.columns)} columns")
    return 0


def _build(workbook: Path, output_dir: Path, model_name: str, evaluation_strategy: str) -> int:
    validate_model_available(model_name)
    with WorkbookReader(workbook) as reader:
        exported = reader.export_csvs(output_dir / "tables", CORE_SHEETS)
    print(f"Exported {len(exported)} clean CSV tables.")

    tables = load_core_tables(workbook)
    return build_from_tables(tables, workbook, output_dir, model_name, evaluation_strategy)


def build_from_tables(
    tables: dict[str, list[dict[str, str | None]]],
    source: Path,
    output_dir: Path,
    model_name: str,
    evaluation_strategy: str,
) -> int:
    """Build the same analytics and model outputs for workbook or upstream tables."""
    analytics_rows = build_player_season_rows(tables)
    analytics_path = export_player_season_rows(analytics_rows, output_dir / "analytics_player_season.csv")
    features = build_features(tables)
    _write_feature_rows(features.historical_rows, output_dir / "historical_episode_states.csv")
    _write_feature_rows(features.current_rows, output_dir / "current_episode_state.csv")
    soc_path = export_soc_mapping(features.soc_mappings, output_dir / "soc_mapping.csv")
    predictions = build_predictions(
        features,
        source,
        model_name=model_name,
        evaluation_strategy=evaluation_strategy,
    )
    predictions_path = save_predictions(predictions, output_dir / "current_predictions.json")
    dashboard_path = build_dashboard(predictions_path, output_dir / "dashboard.html")

    print(f"Current season: {features.current_season}")
    print(f"Latest episode: {features.latest_episode}")
    print(f"Active players: {len(features.current_rows)}")
    print(f"Model: {model_name}")
    print(f"Evaluation strategy: {evaluation_strategy}")
    print(f"Wrote analytics dataset: {analytics_path}")
    print(f"Wrote SOC mapping: {soc_path}")
    print(f"Wrote predictions: {predictions_path}")
    print(f"Wrote dashboard: {dashboard_path}")
    return 0


def _write_feature_rows(rows: list[dict[str, object]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        output_path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0])
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    raise SystemExit(main())


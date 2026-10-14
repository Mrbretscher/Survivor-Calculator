"""Prepare an isolated, validated API snapshot for a Vercel deployment."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tomllib
from pathlib import Path

from survivor_calculator.api import analytics_schema_payload, prediction_payload


def prepare_bundle(repository: Path, data_dir: Path, output_dir: Path) -> Path:
    """Copy only API source and its two required outputs to a new directory.

    Refuses to overwrite a bundle. No raw workbook, secrets, caches, or logs
    are copied. The result contains derived data and is for local preparation;
    redistribution permission must be established before it is published.
    """
    predictions_path = data_dir / "current_predictions.json"
    analytics_path = data_dir / "analytics_player_season.csv"
    predictions = prediction_payload(predictions_path=predictions_path)
    analytics = analytics_schema_payload(analytics_path=analytics_path)
    if not predictions["players"] or not analytics["dataset"]["row_count"]:
        raise ValueError("Cannot prepare a deployment with empty prediction or analytics data.")
    config = tomllib.loads((repository / "pyproject.toml").read_text(encoding="utf-8"))
    api_dependencies = config["project"]["optional-dependencies"]["api"]
    package = repository / "src" / "survivor_calculator"
    source_files = sorted(package.glob("*.py"))
    if not (package / "deployment.py").is_file():
        raise FileNotFoundError("The repository is missing the hosted deployment entry point.")
    output_dir = output_dir.resolve()
    if output_dir == repository.resolve() or output_dir == data_dir.resolve():
        raise ValueError("Choose a separate output directory for the deployment bundle.")
    output_dir.mkdir(parents=True, exist_ok=False)
    target_package = output_dir / "survivor_calculator"
    target_package.mkdir()
    for source in source_files:
        shutil.copy2(source, target_package / source.name)
    target_data = output_dir / "data" / "processed"
    target_data.mkdir(parents=True)
    for source in (predictions_path, analytics_path):
        shutil.copy2(source, target_data / source.name)

    (output_dir / "app.py").write_text(
        '"""Vercel FastAPI entry point using an immutable data snapshot."""\n'
        'import os\nfrom pathlib import Path\n\n'
        'root = Path(__file__).resolve().parent\n'
        'os.environ.setdefault("SURVIVOR_PREDICTIONS_PATH", str(root / "data/processed/current_predictions.json"))\n'
        'os.environ.setdefault("SURVIVOR_ANALYTICS_PATH", str(root / "data/processed/analytics_player_season.csv"))\n'
        'from survivor_calculator.deployment import app\n',
        encoding="utf-8",
    )
    # Vercel currently supports Python 3.12+, within this project's >=3.11 requirement.
    (output_dir / ".python-version").write_text("3.12\n", encoding="utf-8")
    (output_dir / "requirements.txt").write_text("\n".join(api_dependencies) + "\n", encoding="utf-8")
    (output_dir / "vercel.json").write_text(
        json.dumps({"$schema": "https://openapi.vercel.sh/vercel.json", "framework": "fastapi"}, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / ".vercelignore").write_text("__pycache__/\n**/__pycache__/\n*.pyc\n.vercel/\n", encoding="utf-8")
    manifest = {
        "current_season": predictions["metadata"]["current_season"],
        "prediction_generated_at": predictions["metadata"]["generated_at"],
        "players": len(predictions["players"]),
        "analytics_rows": analytics["dataset"]["row_count"],
        "files": {
            str(path.relative_to(output_dir).as_posix()): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(output_dir.rglob("*"))
            if path.is_file()
        },
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--data-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--output", type=Path, default=Path("outputs/vercel-api"))
    args = parser.parse_args()
    try:
        manifest = prepare_bundle(args.repository, args.data_dir, args.output)
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(1, f"Could not prepare deployment bundle: {exc}\n")
    print(f"Validated deployment bundle: {manifest.parent}")
    print(f"Snapshot manifest: {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

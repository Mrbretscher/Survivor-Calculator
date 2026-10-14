"""Fetch a consistent upstream JSON snapshot and rebuild only when inputs change."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from survivor_calculator.baseline import resolve_model_name, validate_model_available
from survivor_calculator.ingest import CORE_SHEETS

UPSTREAM = "https://github.com/doehm/survivoR"
COMMIT_URL = "https://api.github.com/repos/doehm/survivoR/commits/master"
MAX_DOWNLOAD_BYTES = 32 * 1024 * 1024
REQUIRED_COLUMNS = {
    "Castaways": {"season", "castaway_id", "castaway", "winner"},
    "Castaway Details": {"castaway_id", "gender", "occupation"},
    "Boot Order": {"season", "order", "castaway_id"},
    "Boot Mapping": {"season", "episode", "castaway_id", "game_status", "n_boots", "final_n"},
    "Vote History": {"season", "episode", "castaway_id", "vote_id", "nullified"},
    "Challenge Results": {"season", "episode", "castaway_id", "won", "won_individual_immunity"},
    "Confessionals": {"season", "episode", "castaway_id", "confessional_count", "confessional_time"},
    "Advantage Timeline": {"season", "episode", "castaway_id", "holding"},
    "Episodes": {"season", "episode"},
    "Season Summary": {"season", "winner_id"},
}


def fetch_json(url: str) -> object:
    """Read bounded public JSON with a timeout and an actionable failure message."""
    request = Request(url, headers={"User-Agent": "survivor-calculator", "Accept": "application/json"})
    try:
        with urlopen(request, timeout=60) as response:
            payload = response.read(MAX_DOWNLOAD_BYTES + 1)
    except (URLError, TimeoutError) as exc:
        raise RuntimeError(f"Could not fetch {url}: {exc}") from exc
    if len(payload) > MAX_DOWNLOAD_BYTES:
        raise ValueError(f"Upstream response exceeds {MAX_DOWNLOAD_BYTES} bytes: {url}")
    return json.loads(payload)


def normalize_table(name: str, payload: object) -> list[dict[str, str | None]]:
    """Validate records and match the workbook reader's string/boolean contract."""
    if not isinstance(payload, list) or not payload:
        raise ValueError(f"Upstream table {name} must be a nonempty array of records.")
    columns: set[str] = set()
    rows: list[dict[str, str | None]] = []
    for record in payload:
        if not isinstance(record, dict) or not all(isinstance(key, str) for key in record):
            raise ValueError(f"Invalid record in upstream table {name}.")
        columns.update(record)
        row: dict[str, str | None] = {}
        for key, value in record.items():
            if isinstance(value, (dict, list)):
                raise ValueError(f"Nested value in {name}.{key}; upstream schema changed.")
            row[key] = str(int(value)) if isinstance(value, bool) else None if value is None else str(value)
        rows.append(row)
    missing = REQUIRED_COLUMNS[name] - columns
    if missing:
        raise ValueError(f"Upstream table {name} is missing columns: {', '.join(sorted(missing))}")
    # The model currently uses US season numbers as keys. Reject mixing franchises.
    if name != "Castaway Details":
        rows = [row for row in rows if row.get("version") == "US"]
        if not rows:
            raise ValueError(f"Upstream table {name} contains no US records.")
    return rows


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _code_digest() -> str:
    return _digest({path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in sorted(Path(__file__).parent.glob("*.py"))})


def refresh(output_dir: Path, model_name: str = "historical-rate-baseline", *, force: bool = False) -> bool:
    """Stage and validate a rebuild before replacing outputs; return whether rebuilt.

    A manifest is written last so failed runs retry. The hosted workflow deploys
    only after this function succeeds. Concurrent local writers are rejected.
    """
    from survivor_calculator.cli import _write_feature_rows, build_from_tables
    from survivor_calculator.dashboard import build_dashboard

    model_name = resolve_model_name(model_name)
    validate_model_available(model_name)
    output_dir = output_dir.resolve()
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    lock = output_dir.with_name(f".{output_dir.name}.refresh.lock")
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise RuntimeError(f"Another refresh is running (lock: {lock}). Remove a stale lock only after checking no refresh is running.") from exc
    os.close(descriptor)
    try:
        manifest_path = output_dir / "refresh_manifest.json"
        previous = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
        commit_data = fetch_json(COMMIT_URL)
        commit = commit_data.get("sha") if isinstance(commit_data, dict) else None
        if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise ValueError("Upstream did not return a valid Git commit SHA.")
        settings = {"model": model_name, "evaluation_strategy": "chronological", "code_sha256": _code_digest()}
        outputs_intact = all(
            (output_dir / name).is_file()
            and hashlib.sha256((output_dir / name).read_bytes()).hexdigest() == checksum
            for name, checksum in previous.get("output_sha256", {}).items()
        ) and bool(previous.get("output_sha256"))
        if not force and outputs_intact and previous.get("commit") == commit and previous.get("settings") == settings:
            return False

        tables = {}
        sources = {}
        for sheet in CORE_SHEETS:
            slug = sheet.lower().replace(" ", "_")
            url = f"https://raw.githubusercontent.com/doehm/survivoR/{commit}/dev/json/{slug}.json"
            payload = fetch_json(url)
            tables[sheet] = normalize_table(sheet, payload)
            sources[sheet] = {"url": url, "sha256": _digest(payload)}
        data_digest = _digest(tables)
        if not force and outputs_intact and previous.get("data_sha256") == data_digest and previous.get("settings") == settings:
            # A documentation-only upstream commit does not require retraining.
            return False

        with tempfile.TemporaryDirectory(prefix="survivor-refresh-", dir=output_dir.parent) as temporary:
            staged = Path(temporary)
            for sheet, rows in tables.items():
                columns = sorted({key for row in rows for key in row})
                _write_feature_rows([{key: row.get(key) for key in columns} for row in rows],
                                    staged / "tables" / f"{sheet.lower().replace(' ', '_')}.csv")
            build_from_tables(tables, Path("upstream-json"), staged, model_name, "chronological")
            predictions_path = staged / "current_predictions.json"
            predictions = json.loads(predictions_path.read_text(encoding="utf-8"))
            if not predictions["players"] or not (staged / "historical_episode_states.csv").stat().st_size:
                raise ValueError("Refusing to publish empty training data or current predictions.")
            provenance = {"repository": UPSTREAM, "commit": commit, "data_sha256": data_digest,
                          "retrieved_at": datetime.now(UTC).isoformat(), "tables": sources}
            # Keep the legacy field required by existing API/frontend clients.
            predictions["metadata"]["source_workbook"] = "upstream-json (no workbook)"
            predictions["metadata"]["source_data"] = provenance
            predictions_path.write_text(json.dumps(predictions, indent=2) + "\n", encoding="utf-8")
            build_dashboard(predictions_path, staged / "dashboard.html")
            manifest = {**provenance, "settings": settings, "output_sha256": {
                path.relative_to(staged).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(staged.rglob("*")) if path.is_file()
            }}
            # All network/training/validation work has succeeded before any output changes.
            output_dir.mkdir(parents=True, exist_ok=True)
            for source in sorted(staged.rglob("*")):
                if source.is_file():
                    destination = output_dir / source.relative_to(staged)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(source, destination)
            staged_manifest = staged / "refresh_manifest.json"
            staged_manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            os.replace(staged_manifest, manifest_path)
        return True
    finally:
        lock.unlink()

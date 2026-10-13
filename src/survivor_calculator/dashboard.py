"""Generate a static dashboard for quick local review."""

from __future__ import annotations

import html
import json
from pathlib import Path


def build_dashboard(predictions_path: str | Path, output_path: str | Path) -> Path:
    predictions = json.loads(Path(predictions_path).read_text(encoding="utf-8"))
    players = predictions["players"]
    metadata = predictions["metadata"]
    rows = "\n".join(_player_row(player) for player in players)
    boot_rows = "\n".join(_boot_row(row) for row in predictions["projected_boot_order"])
    evaluation = html.escape(json.dumps(predictions["evaluation"], indent=2))
    document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Survivor Calculator Dashboard</title>
  <style>
    :root {{
      color-scheme: light;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f5f7fb;
      color: #172033;
    }}
    body {{ margin: 0; }}
    header {{ background: #172033; color: white; padding: 28px 36px; }}
    main {{ padding: 28px 36px 48px; max-width: 1180px; margin: 0 auto; }}
    h1, h2 {{ margin: 0 0 12px; }}
    section {{ margin-top: 28px; }}
    table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #d9e0ea; }}
    th, td {{ padding: 10px 12px; border-bottom: 1px solid #e8edf4; text-align: left; vertical-align: top; }}
    th {{ background: #edf2f7; font-size: 13px; }}
    .bar {{ height: 10px; background: #dbe5f0; border-radius: 999px; overflow: hidden; min-width: 110px; }}
    .bar > span {{ display: block; height: 100%; background: #1f7a8c; }}
    .meta {{ color: #d9e6f2; margin: 4px 0 0; }}
    .note {{ color: #4d5c70; }}
    pre {{ white-space: pre-wrap; background: white; padding: 16px; border: 1px solid #d9e0ea; }}
  </style>
</head>
<body>
  <header>
    <h1>Survivor Calculator</h1>
    <p class="meta">Season {metadata["current_season"]}, latest episode {metadata["latest_episode"]}. {html.escape(metadata["disclaimer"])}</p>
  </header>
  <main>
    <section>
      <h2>Current Winner Board</h2>
      <table>
        <thead><tr><th>Player</th><th>Tribe</th><th>Occupation</th><th>Next boot</th><th>Winner</th><th>Signals</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </section>
    <section>
      <h2>Projected Boot Order</h2>
      <table>
        <thead><tr><th>Order</th><th>Player</th><th>Final N before boot</th><th>Boot probability</th></tr></thead>
        <tbody>{boot_rows}</tbody>
      </table>
    </section>
    <section>
      <h2>Holdout Evaluation</h2>
      <pre>{evaluation}</pre>
    </section>
  </main>
</body>
</html>
"""
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8")
    return output


def _player_row(player: dict[str, object]) -> str:
    next_boot = float(player["next_boot_probability"])
    winner = float(player["winner_probability"])
    explanation = " ".join(html.escape(str(item)) for item in player["explanation"])
    return (
        "<tr>"
        f"<td>{html.escape(str(player['castaway']))}</td>"
        f"<td>{html.escape(str(player['tribe']))}</td>"
        f"<td>{html.escape(str(player['occupation']))}</td>"
        f"<td><div class='bar'><span style='width:{next_boot * 100:.1f}%'></span></div>{next_boot:.1%}</td>"
        f"<td><div class='bar'><span style='width:{winner * 100:.1f}%'></span></div>{winner:.1%}</td>"
        f"<td class='note'>{explanation}</td>"
        "</tr>"
    )


def _boot_row(row: dict[str, object]) -> str:
    probability = float(row["projected_boot_probability"])
    return (
        "<tr>"
        f"<td>{row['projected_order']}</td>"
        f"<td>{html.escape(str(row['castaway']))}</td>"
        f"<td>{row['projected_final_n_before_boot']}</td>"
        f"<td>{probability:.1%}</td>"
        "</tr>"
    )


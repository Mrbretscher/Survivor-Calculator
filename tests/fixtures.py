from __future__ import annotations

import zipfile
from pathlib import Path


def minimal_core_tables() -> dict[str, list[dict[str, str | None]]]:
    """Return a tiny deterministic data set covering the modeling path."""

    return {
        "Castaways": [
            {"season": "1", "castaway_id": "S1-A", "castaway": "Ari", "age": "29", "winner": "0"},
            {"season": "1", "castaway_id": "S1-B", "castaway": "Bea", "age": "42", "winner": "1"},
            {"season": "2", "castaway_id": "S2-C", "castaway": "Cam", "age": "35", "winner": "0"},
            {"season": "2", "castaway_id": "S2-D", "castaway": "Dee", "age": "24", "winner": "0"},
        ],
        "Castaway Details": [
            {"castaway_id": "S1-A", "gender": "Female", "occupation": "Software engineer"},
            {"castaway_id": "S1-B", "gender": "Male", "occupation": "Teacher"},
            {"castaway_id": "S2-C", "gender": "Female", "occupation": "Nurse"},
            {"castaway_id": "S2-D", "gender": "Male", "occupation": "Student"},
        ],
        "Boot Order": [
            {"season": "1", "order": "1", "castaway_id": "S1-A"},
            {"season": "1", "order": "2", "castaway_id": "S1-B"},
        ],
        "Boot Mapping": [
            _state("1", "1", "0", "2", "S1-A", "Ari", "Tiva", "Tribal"),
            _state("1", "1", "0", "2", "S1-B", "Bea", "Tiva", "Tribal"),
            _state("1", "2", "1", "1", "S1-B", "Bea", "Tiva", "Tribal"),
            _state("2", "1", "0", "2", "S2-C", "Cam", "Luma", "Tribal"),
            _state("2", "1", "0", "2", "S2-D", "Dee", "Luma", "Tribal"),
            _state("2", "2", "0", "2", "S2-C", "Cam", "Luma", "Tribal"),
            _state("2", "2", "0", "2", "S2-D", "Dee", "Luma", "Tribal"),
        ],
        "Vote History": [
            {"season": "1", "episode": "1", "castaway_id": "S1-B", "vote_id": "S1-A", "nullified": "0"},
            {"season": "2", "episode": "1", "castaway_id": "S2-D", "vote_id": "S2-C", "nullified": "0"},
        ],
        "Challenge Results": [
            {"season": "1", "episode": "1", "castaway_id": "S1-B", "won": "1", "won_individual_immunity": "0"},
            {"season": "2", "episode": "1", "castaway_id": "S2-C", "won": "1", "won_individual_immunity": "1"},
        ],
        "Confessionals": [
            {"season": "1", "episode": "1", "castaway_id": "S1-A", "confessional_count": "2", "confessional_time": "15.5"},
            {"season": "2", "episode": "1", "castaway_id": "S2-C", "confessional_count": "3", "confessional_time": "42"},
        ],
        "Advantage Timeline": [
            {"season": "2", "episode": "1", "castaway_id": "S2-D", "holding": "1"},
        ],
        "Episodes": [],
        "Season Summary": [
            {"season": "1", "winner_id": "S1-B"},
            {"season": "2", "winner_id": ""},
        ],
    }


def write_minimal_workbook(path: Path) -> None:
    """Write the smallest XLSX package needed by WorkbookReader."""

    with zipfile.ZipFile(path, "w") as workbook:
        workbook.writestr(
            "xl/workbook.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
  xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Fixture Sheet" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>""",
        )
        workbook.writestr(
            "xl/_rels/workbook.xml.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"
    Target="worksheets/sheet1.xml"/>
</Relationships>""",
        )
        workbook.writestr(
            "xl/sharedStrings.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <si><t>castaway_id</t></si>
  <si><t>name</t></si>
  <si><t>S2-C</t></si>
</sst>""",
        )
        workbook.writestr(
            "xl/worksheets/sheet1.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <dimension ref="A1:A1"/>
  <sheetData>
    <row r="1">
      <c r="A1" t="s"><v>0</v></c>
      <c r="B1" t="s"><v>1</v></c>
      <c r="C1" t="inlineStr"><is><t>episode</t></is></c>
    </row>
    <row r="2">
      <c r="A2" t="s"><v>2</v></c>
      <c r="B2" t="inlineStr"><is><t>Cam</t></is></c>
      <c r="C2"><v>2</v></c>
    </row>
  </sheetData>
</worksheet>""",
        )


def _state(
    season: str,
    episode: str,
    n_boots: str,
    final_n: str,
    castaway_id: str,
    castaway: str,
    tribe: str,
    tribe_status: str,
) -> dict[str, str | None]:
    return {
        "season": season,
        "episode": episode,
        "n_boots": n_boots,
        "final_n": final_n,
        "castaway_id": castaway_id,
        "castaway": castaway,
        "tribe": tribe,
        "tribe_status": tribe_status,
        "game_status": "In the game",
    }

"""Workbook ingestion that does not trust stale Excel sheet dimensions."""

from __future__ import annotations

import csv
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator
from xml.etree import ElementTree

SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS = {"a": SPREADSHEET_NS, "r": REL_NS}

CORE_SHEETS = (
    "Castaways",
    "Castaway Details",
    "Boot Order",
    "Boot Mapping",
    "Vote History",
    "Challenge Results",
    "Confessionals",
    "Advantage Timeline",
    "Episodes",
    "Season Summary",
)


@dataclass(frozen=True)
class SheetSchema:
    """A compact description of one workbook sheet."""

    name: str
    rows: int
    columns: tuple[str, ...]


class WorkbookReader:
    """Read rows directly from the XLSX XML package.

    The supplied workbook has stale worksheet dimension metadata, so high-level
    Excel readers can report sheets as `A1:A1`. This reader streams the actual
    worksheet XML and resolves shared strings itself.
    """

    def __init__(self, workbook_path: str | Path) -> None:
        self.workbook_path = Path(workbook_path)
        if not self.workbook_path.exists():
            raise FileNotFoundError(f"Workbook not found: {self.workbook_path}")
        self._zip = zipfile.ZipFile(self.workbook_path)
        self._shared_strings = self._load_shared_strings()
        self._sheet_paths = self._load_sheet_paths()

    def close(self) -> None:
        self._zip.close()

    def __enter__(self) -> "WorkbookReader":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    @property
    def sheet_names(self) -> tuple[str, ...]:
        return tuple(self._sheet_paths)

    def schema(self, sheet_name: str) -> SheetSchema:
        rows = 0
        columns: tuple[str, ...] = ()
        for row in self.iter_rows(sheet_name):
            rows += 1
            if rows == 1:
                columns = tuple(row)
        return SheetSchema(name=sheet_name, rows=rows, columns=columns)

    def schemas(self) -> list[SheetSchema]:
        return [self.schema(sheet_name) for sheet_name in self.sheet_names]

    def iter_records(self, sheet_name: str) -> Iterator[dict[str, str | None]]:
        header: list[str] | None = None
        for row in self.iter_rows(sheet_name):
            if header is None:
                header = [str(value) if value is not None else "" for value in row]
                continue
            yield {
                header[index]: value
                for index, value in enumerate(row[: len(header)])
                if header[index]
            }

    def iter_rows(self, sheet_name: str) -> Iterator[list[str | None]]:
        path = self._sheet_paths.get(sheet_name)
        if path is None:
            raise KeyError(f"Sheet not found: {sheet_name}")

        with self._zip.open(path) as source:
            for _event, elem in ElementTree.iterparse(source, events=("end",)):
                if elem.tag == f"{{{SPREADSHEET_NS}}}row":
                    cells: dict[int, str | None] = {}
                    for cell in elem.findall("a:c", NS):
                        reference = cell.attrib.get("r", "")
                        column_match = re.match(r"([A-Z]+)", reference)
                        if column_match is None:
                            continue
                        cells[_column_to_index(column_match.group(1))] = self._cell_value(cell)
                    width = max(cells) + 1 if cells else 0
                    yield [cells.get(index) for index in range(width)]
                    elem.clear()

    def export_csvs(self, output_dir: str | Path, sheets: tuple[str, ...] = CORE_SHEETS) -> list[Path]:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        exported: list[Path] = []
        for sheet_name in sheets:
            destination = output / f"{_slug(sheet_name)}.csv"
            records = self.iter_records(sheet_name)
            first = next(records, None)
            if first is None:
                continue
            with destination.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(first))
                writer.writeheader()
                writer.writerow(first)
                writer.writerows(records)
            exported.append(destination)
        return exported

    def _load_shared_strings(self) -> list[str]:
        try:
            root = ElementTree.fromstring(self._zip.read("xl/sharedStrings.xml"))
        except KeyError:
            return []
        strings: list[str] = []
        for item in root.findall("a:si", NS):
            text = "".join(node.text or "" for node in item.iter(f"{{{SPREADSHEET_NS}}}t"))
            strings.append(text)
        return strings

    def _load_sheet_paths(self) -> dict[str, str]:
        workbook = ElementTree.fromstring(self._zip.read("xl/workbook.xml"))
        rels = ElementTree.fromstring(self._zip.read("xl/_rels/workbook.xml.rels"))
        rel_map = {rel.attrib["Id"]: rel.attrib["Target"].lstrip("/") for rel in rels}

        sheet_paths: dict[str, str] = {}
        sheets = workbook.find("a:sheets", NS)
        if sheets is None:
            return sheet_paths
        for sheet in sheets:
            relationship_id = sheet.attrib[f"{{{REL_NS}}}id"]
            target = rel_map[relationship_id]
            path = target if target.startswith("xl/") else f"xl/{target}"
            sheet_paths[sheet.attrib["name"]] = path
        return sheet_paths

    def _cell_value(self, cell: ElementTree.Element) -> str | None:
        cell_type = cell.attrib.get("t")
        value = cell.find("a:v", NS)
        if cell_type == "s" and value is not None:
            return self._shared_strings[int(value.text or "0")]
        if cell_type == "inlineStr":
            inline = cell.find("a:is", NS)
            if inline is None:
                return ""
            return "".join(node.text or "" for node in inline.iter(f"{{{SPREADSHEET_NS}}}t"))
        return value.text if value is not None else None


def load_core_tables(workbook_path: str | Path, sheets: tuple[str, ...] = CORE_SHEETS) -> dict[str, list[dict[str, str | None]]]:
    """Load the core modeling sheets into memory."""

    with WorkbookReader(workbook_path) as reader:
        return {sheet: list(reader.iter_records(sheet)) for sheet in sheets}


def _column_to_index(column: str) -> int:
    index = 0
    for char in column:
        index = index * 26 + ord(char) - 64
    return index - 1


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


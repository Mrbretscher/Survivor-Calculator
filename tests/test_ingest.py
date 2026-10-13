from pathlib import Path
import unittest

from survivor_calculator.ingest import WorkbookReader


WORKBOOK = Path("survivoR.xlsx")


class WorkbookReaderTests(unittest.TestCase):
    def test_workbook_reader_sees_real_dimensions(self) -> None:
        with WorkbookReader(WORKBOOK) as reader:
            schema = reader.schema("Boot Mapping")

        self.assertGreater(schema.rows, 1000)
        self.assertIn("castaway_id", schema.columns)
        self.assertIn("game_status", schema.columns)

    def test_current_workbook_has_expected_core_sheets(self) -> None:
        with WorkbookReader(WORKBOOK) as reader:
            names = set(reader.sheet_names)

        self.assertTrue({"Castaways", "Boot Mapping", "Boot Order", "Vote History"}.issubset(names))


if __name__ == "__main__":
    unittest.main()


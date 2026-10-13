from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from survivor_calculator.ingest import WorkbookReader

from fixtures import write_minimal_workbook


WORKBOOK = Path("survivoR.xlsx")


class WorkbookReaderTests(unittest.TestCase):
    def test_workbook_reader_uses_actual_rows_not_stale_dimensions(self) -> None:
        with TemporaryDirectory() as temp_dir:
            workbook_path = Path(temp_dir) / "fixture.xlsx"
            write_minimal_workbook(workbook_path)

            with WorkbookReader(workbook_path) as reader:
                schema = reader.schema("Fixture Sheet")
                records = list(reader.iter_records("Fixture Sheet"))

        self.assertEqual(schema.rows, 2)
        self.assertEqual(schema.columns, ("castaway_id", "name", "episode"))
        self.assertEqual(records, [{"castaway_id": "S2-C", "name": "Cam", "episode": "2"}])


@unittest.skipUnless(WORKBOOK.exists(), "Integration coverage requires survivoR.xlsx")
class WorkbookReaderIntegrationTests(unittest.TestCase):
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


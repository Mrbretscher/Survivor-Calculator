from pathlib import Path
import unittest

from survivor_calculator.ingest import load_core_tables
from survivor_calculator.soc import STUDENT_MAJOR_GROUP, classify_occupation


WORKBOOK = Path("survivoR.xlsx")


class SocMappingTests(unittest.TestCase):
    def test_head_of_hr_maps_to_human_resources_managers(self) -> None:
        mapping = classify_occupation("Head of HR")

        self.assertEqual(mapping.soc_code, "11-3120")
        self.assertEqual(mapping.soc_title, "Human Resources Managers")
        self.assertEqual(mapping.soc_major_group, "Management Occupations")
        self.assertFalse(mapping.review_required)

    def test_student_categories_use_project_specific_major_group(self) -> None:
        self.assert_student_mapping("Student", "ST-2000", "General Students")
        self.assert_student_mapping("Medical Student", "ST-2020", "Medical Students")
        self.assert_student_mapping("Pre-Med Student", "ST-2020", "Medical Students")
        self.assert_student_mapping("Law Student", "ST-2010", "Law Students")
        self.assert_student_mapping("Legal Student", "ST-2010", "Law Students")
        self.assert_student_mapping("Seminary Student", "ST-2030", "Seminary Students")
        self.assert_student_mapping("MBA Student", "ST-2040", "Business Students")

    def assert_student_mapping(self, occupation: str, code: str, title: str) -> None:
        mapping = classify_occupation(occupation)

        self.assertEqual(mapping.soc_code, code)
        self.assertEqual(mapping.soc_title, title)
        self.assertEqual(mapping.soc_major_group, STUDENT_MAJOR_GROUP)


@unittest.skipUnless(WORKBOOK.exists(), "Integration coverage requires survivoR.xlsx")
class SocMappingIntegrationTests(unittest.TestCase):
    def test_every_non_empty_workbook_occupation_receives_a_classification(self) -> None:
        occupations = {
            (row.get("occupation") or "").strip()
            for row in load_core_tables(WORKBOOK, ("Castaway Details",))["Castaway Details"]
        }

        unclassified = [
            occupation
            for occupation in occupations
            if occupation and not classify_occupation(occupation).soc_title
        ]

        self.assertEqual(unclassified, [])


if __name__ == "__main__":
    unittest.main()

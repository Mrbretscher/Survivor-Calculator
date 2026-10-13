"""Deterministic first-pass SOC occupation mapping."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

BLS_SOC_SOURCE_URL = "https://www.bls.gov/soc/2018/home.htm"


@dataclass(frozen=True)
class SocMapping:
    occupation: str
    soc_code: str
    soc_title: str
    soc_major_group: str
    confidence: str
    review_required: bool
    notes: str


KEYWORD_RULES: tuple[tuple[tuple[str, ...], str, str, str], ...] = (
    (("doctor", "physician", "surgeon", "pediatrician"), "29-1215", "Family Medicine Physicians", "Healthcare Practitioners and Technical Occupations"),
    (("nurse", "rn"), "29-1141", "Registered Nurses", "Healthcare Practitioners and Technical Occupations"),
    (("therapist", "counselor", "psychologist"), "21-1019", "Counselors, All Other", "Community and Social Service Occupations"),
    (("teacher", "professor", "educator", "principal"), "25-3099", "Teachers and Instructors, All Other", "Educational Instruction and Library Occupations"),
    (("attorney", "lawyer", "public defender"), "23-1011", "Lawyers", "Legal Occupations"),
    (("police", "detective", "trooper", "sheriff"), "33-3051", "Police and Sheriff's Patrol Officers", "Protective Service Occupations"),
    (("firefighter",), "33-2011", "Firefighters", "Protective Service Occupations"),
    (("software", "engineer", "developer", "programmer"), "15-1252", "Software Developers", "Computer and Mathematical Occupations"),
    (("data", "analyst", "scientist", "statistician"), "15-2051", "Data Scientists", "Computer and Mathematical Occupations"),
    (("accountant", "auditor", "cpa"), "13-2011", "Accountants and Auditors", "Business and Financial Operations Occupations"),
    (("financial", "banker", "investment", "trader"), "13-2051", "Financial and Investment Analysts", "Business and Financial Operations Occupations"),
    (("sales", "realtor", "real estate"), "41-3091", "Sales Representatives of Services, Except Advertising, Insurance, Financial Services, and Travel", "Sales and Related Occupations"),
    (("marketing", "public relations", "communications"), "11-2021", "Marketing Managers", "Management Occupations"),
    (("manager", "executive", "director", "ceo", "entrepreneur", "owner", "founder"), "11-1021", "General and Operations Managers", "Management Occupations"),
    (("student",), "00-0000", "Student or Not in Labor Force", "Not Classified in SOC"),
    (("retired",), "00-0000", "Retired or Not in Labor Force", "Not Classified in SOC"),
    (("server", "bartender", "restaurant", "chef", "cook"), "35-2019", "Cooks, All Other", "Food Preparation and Serving Related Occupations"),
    (("farmer", "rancher"), "45-2099", "Agricultural Workers, All Other", "Farming, Fishing, and Forestry Occupations"),
    (("pilot", "flight attendant"), "53-2012", "Commercial Pilots", "Transportation and Material Moving Occupations"),
    (("coach", "athlete", "trainer"), "27-2022", "Coaches and Scouts", "Arts, Design, Entertainment, Sports, and Media Occupations"),
    (("artist", "designer", "writer", "actor", "musician", "comedian"), "27-1019", "Artists and Related Workers, All Other", "Arts, Design, Entertainment, Sports, and Media Occupations"),
    (("mechanic", "technician"), "49-3023", "Automotive Service Technicians and Mechanics", "Installation, Maintenance, and Repair Occupations"),
    (("construction", "carpenter", "contractor"), "47-2031", "Carpenters", "Construction and Extraction Occupations"),
    (("military", "army", "navy", "marine", "air force", "veteran"), "55-3019", "Military Enlisted Tactical Operations and Air/Weapons Specialists and Crew Members, All Other", "Military Specific Occupations"),
)


def classify_occupation(occupation: str | None) -> SocMapping:
    raw = (occupation or "").strip()
    normalized = raw.lower()
    if not normalized:
        return SocMapping("", "", "", "", "none", True, "Missing occupation; manual review required.")

    for keywords, code, title, group in KEYWORD_RULES:
        if any(keyword in normalized for keyword in keywords):
            review = code == "00-0000"
            confidence = "medium" if not review else "low"
            notes = "Keyword match. Verify detailed SOC before public reporting."
            return SocMapping(raw, code, title, group, confidence, review, notes)

    return SocMapping(
        raw,
        "",
        "",
        "",
        "none",
        True,
        "No deterministic keyword match; manual SOC review required.",
    )


def build_soc_mapping(occupations: set[str | None]) -> list[SocMapping]:
    return sorted((classify_occupation(occupation) for occupation in occupations), key=lambda item: item.occupation.lower())


def export_soc_mapping(mappings: list[SocMapping], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(SocMapping.__dataclass_fields__))
        writer.writeheader()
        for mapping in mappings:
            writer.writerow(
                {
                    "occupation": mapping.occupation,
                    "soc_code": mapping.soc_code,
                    "soc_title": mapping.soc_title,
                    "soc_major_group": mapping.soc_major_group,
                    "confidence": mapping.confidence,
                    "review_required": mapping.review_required,
                    "notes": mapping.notes,
                }
            )
    return path


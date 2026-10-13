"""Deterministic occupation-to-SOC mapping with project-specific student groups."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

BLS_SOC_SOURCE_URL = "https://www.bls.gov/oes/2023/may/oes_stru.htm"
STUDENT_MAJOR_GROUP = "Students"
NOT_CLASSIFIED_MAJOR_GROUP = "Not Classified in SOC"


@dataclass(frozen=True)
class SocMapping:
    occupation: str
    soc_code: str
    soc_title: str
    soc_major_group: str
    confidence: str
    review_required: bool
    notes: str


@dataclass(frozen=True)
class OccupationRule:
    keywords: tuple[str, ...]
    soc_code: str
    soc_title: str
    soc_major_group: str
    confidence: str = "medium"
    review_required: bool = False
    notes: str = "Keyword inference; verify detailed SOC before public reporting."


STUDENT_RULES: tuple[OccupationRule, ...] = (
    OccupationRule(
        ("law student", "legal student", "harvard law student", "law school student", "pre law"),
        "ST-2010",
        "Law Students",
        STUDENT_MAJOR_GROUP,
        "high",
        False,
        "Project-specific student classification requested by the user.",
    ),
    OccupationRule(
        (
            "medical student",
            "bio medical student",
            "biomedical student",
            "pre med",
            "nursing student",
            "dental student",
        ),
        "ST-2020",
        "Medical Students",
        STUDENT_MAJOR_GROUP,
        "high",
        False,
        "Project-specific student classification requested by the user.",
    ),
    OccupationRule(
        ("seminary student",),
        "ST-2030",
        "Seminary Students",
        STUDENT_MAJOR_GROUP,
        "high",
        False,
        "Project-specific student classification added because multiple players share this student type.",
    ),
    OccupationRule(
        ("business student", "mba student"),
        "ST-2040",
        "Business Students",
        STUDENT_MAJOR_GROUP,
        "high",
        False,
        "Project-specific student classification added because multiple players share this student type.",
    ),
    OccupationRule(
        (
            "student",
            "grad student",
            "graduate student",
            "ph d student",
            "phd student",
            "phd candidate",
            "college student",
            "high school student",
            "ivy league student",
            "full time student",
        ),
        "ST-2000",
        "General Students",
        STUDENT_MAJOR_GROUP,
        "medium",
        False,
        "Project-specific student fallback for general or one-off student descriptions.",
    ),
)


SOC_RULES: tuple[OccupationRule, ...] = (
    OccupationRule(("crisis management",), "11-9161", "Emergency Management Directors", "Management Occupations"),
    OccupationRule(("construction company v p", "president", "vice president", "pta vice president"), "11-1021", "General and Operations Managers", "Management Occupations"),
    OccupationRule(("business development consultant", "managing consultant"), "13-1111", "Management Analysts", "Business and Financial Operations Occupations"),
    OccupationRule(("head of internal audit",), "13-2011", "Accountants and Auditors", "Business and Financial Operations Occupations"),
    OccupationRule(("insurance adjuster", "insurance claims"), "13-1031", "Claims Adjusters, Examiners, and Investigators", "Business and Financial Operations Occupations"),
    OccupationRule(("energy advisor",), "13-1199", "Business Operations Specialists, All Other", "Business and Financial Operations Occupations"),
    OccupationRule(("strategy associate",), "13-1111", "Management Analysts", "Business and Financial Operations Occupations"),
    OccupationRule(("tech investor",), "13-2051", "Financial and Investment Analysts", "Business and Financial Operations Occupations"),
    OccupationRule(("political science ph d", "diplomat"), "19-3094", "Political Scientists", "Life, Physical, and Social Science Occupations"),
    OccupationRule(("crime scene analyst",), "19-4092", "Forensic Science Technicians", "Life, Physical, and Social Science Occupations"),
    OccupationRule(("biokineticist", "wellness specialist"), "29-1128", "Exercise Physiologists", "Healthcare Practitioners and Technical Occupations"),
    OccupationRule(("emergency medical technician", "paramedic", "emt"), "29-2042", "Emergency Medical Technicians", "Healthcare Practitioners and Technical Occupations"),
    OccupationRule(("healthcare worker", "heart valve specialist"), "31-9099", "Healthcare Support Workers, All Other", "Healthcare Support Occupations"),
    OccupationRule(("bounty hunter", "private investigator"), "33-9021", "Private Detectives and Investigators", "Protective Service Occupations"),
    OccupationRule(("s w a t", "security specialist"), "33-9099", "Protective Service Workers, All Other", "Protective Service Occupations"),
    OccupationRule(("bellhop", "hotel doorman"), "39-6011", "Baggage Porters and Bellhops", "Personal Care and Service Occupations"),
    OccupationRule(("hospitality", "hotel worker"), "39-6012", "Concierges", "Personal Care and Service Occupations"),
    OccupationRule(("canyoning guide",), "39-7010", "Tour and Travel Guides", "Personal Care and Service Occupations"),
    OccupationRule(("surfing instructor",), "39-9031", "Exercise Trainers and Group Fitness Instructors", "Personal Care and Service Occupations"),
    OccupationRule(("scout troop leader",), "39-9032", "Recreation Workers", "Personal Care and Service Occupations"),
    OccupationRule(("coconut vendor", "golf course vendor"), "41-2031", "Retail Salespersons", "Sales and Related Occupations"),
    OccupationRule(("financial assistant",), "43-3099", "Financial Clerks, All Other", "Office and Administrative Support Occupations"),
    OccupationRule(("ex talent agent assistant",), "43-6014", "Secretaries and Administrative Assistants, Except Legal, Medical, and Executive", "Office and Administrative Support Occupations"),
    OccupationRule(("expert witness locator",), "23-2099", "Legal Support Workers, All Other", "Legal Occupations"),
    OccupationRule(("highway repair",), "47-4051", "Highway Maintenance Workers", "Construction and Extraction Occupations"),
    OccupationRule(("gravedigger", "caretaker"), "37-3019", "Grounds Maintenance Workers, All Other", "Building and Grounds Cleaning and Maintenance Occupations"),
    OccupationRule(("art consultant", "fashion stylist"), "27-1019", "Artists and Related Workers, All Other", "Arts, Design, Entertainment, Sports, and Media Occupations"),
    OccupationRule(("content developer", "digital content creator", "social media influencer", "social media strategist", "media consultant", "travel blogger", "reality star", "former tv personality", "former tv teen star", "youtube sensation", "motivational speaker", "freelance marketer"), "27-3091", "Media and Communication Workers, All Other", "Arts, Design, Entertainment, Sports, and Media Occupations"),
    OccupationRule(("radio show host",), "27-3011", "Broadcast Announcers and Radio Disc Jockeys", "Arts, Design, Entertainment, Sports, and Media Occupations"),
    OccupationRule(("magician", "magician s assistant", "memory champion", "fire dancer", "witch"), "27-2099", "Entertainers and Performers, Sports and Related Workers, All Other", "Arts, Design, Entertainment, Sports, and Media Occupations"),
    OccupationRule(("professional dancer", "professional competitive latin american dancer", "roller girl"), "27-2031", "Dancers", "Arts, Design, Entertainment, Sports, and Media Occupations"),
    OccupationRule(("aflw player", "football player", "rugby player", "afl legend", "nrl legend", "dual code football legend", "medalist", "sprinter", "pole vaulter", "snowboard", "barrel racer", "competitive eater", "wood chopper", "strongman", "survival expert", "survivalist", "footy fanatic", "paralympian", "freestyle skier", "swimming legend"), "27-2022", "Coaches and Scouts", "Arts, Design, Entertainment, Sports, and Media Occupations"),
    OccupationRule(("club promoter",), "39-3099", "Entertainment Attendants and Related Workers, All Other", "Personal Care and Service Occupations"),
    OccupationRule(("merchandiser",), "27-1026", "Merchandise Displayers and Window Trimmers", "Arts, Design, Entertainment, Sports, and Media Occupations"),
    OccupationRule(("wedding celebrant",), "21-2011", "Clergy", "Community and Social Service Occupations"),
    OccupationRule(("pet cremator",), "39-4031", "Morticians, Undertakers, and Funeral Arrangers", "Personal Care and Service Occupations"),
    OccupationRule(("rural developer",), "19-3051", "Urban and Regional Planners", "Life, Physical, and Social Science Occupations"),
    OccupationRule(("head of partnerships", "partnerships"), "11-1021", "General and Operations Managers", "Management Occupations"),
    OccupationRule(("property developer", "real estate developer", "real estate"), "41-9022", "Real Estate Sales Agents", "Sales and Related Occupations"),
    OccupationRule(("ice cream maker", "toymaker"), "51-9199", "Production Workers, All Other", "Production Occupations"),
    OccupationRule(("jeweler",), "51-9071", "Jewelers and Precious Stone and Metal Workers", "Production Occupations"),
    OccupationRule(("lumberjill", "shepherdess"), "45-2099", "Agricultural Workers, All Other", "Farming, Fishing, and Forestry Occupations"),
    OccupationRule(("oil tanker crewman",), "53-5011", "Sailors and Marine Oilers", "Transportation and Material Moving Occupations"),
    OccupationRule(("chemical disposal",), "47-4041", "Hazardous Materials Removal Workers", "Construction and Extraction Occupations"),
    OccupationRule(("structural engineering draughtsman",), "17-3011", "Architectural and Civil Drafters", "Architecture and Engineering Occupations"),
    OccupationRule(("water treatment tech",), "51-8031", "Water and Wastewater Treatment Plant and System Operators", "Production Occupations"),
    OccupationRule(("medical marijuana dispenser",), "41-2031", "Retail Salespersons", "Sales and Related Occupations"),
    OccupationRule(("ice cream entrepreneur", "i t entrepeneur", "freelancer"), "11-1021", "General and Operations Managers", "Management Occupations"),
    OccupationRule(("ivy league graduate",), "ST-2000", "General Students", STUDENT_MAJOR_GROUP, "low", True, "Project-specific fallback for education-status descriptions."),
    OccupationRule(("public servant",), "13-1041", "Compliance Officers", "Business and Financial Operations Occupations"),
    OccupationRule(("warehouse associate",), "43-5081", "Stockers and Order Fillers", "Office and Administrative Support Occupations"),
    OccupationRule(("chief executive", " ceo ", "charity ceo", "publishing ceo", "business mogul"), "11-1011", "Chief Executives", "Management Occupations"),
    OccupationRule(("head of hr", "hr director", "hr manager", "hr executive", "human resources manager"), "11-3120", "Human Resources Managers", "Management Occupations", "high"),
    OccupationRule(("human resources", "hr consultant", "recruiter", "recruiting", "recruitment"), "13-1071", "Human Resources Specialists", "Business and Financial Operations Occupations"),
    OccupationRule(("financial manager", "finance manager", "chief financial officer", "cfo", "finance risk manager"), "11-3031", "Financial Managers", "Management Occupations"),
    OccupationRule(("marketing manager", "marketing director", "marketing executive", "brand manager", "brand strategist", "digital marketing manager"), "11-2021", "Marketing Managers", "Management Occupations"),
    OccupationRule(("sales manager", "district sales manager", "financial sales manager"), "11-2022", "Sales Managers", "Management Occupations"),
    OccupationRule(("public relations manager", "pr manager", "communications manager", "director of communications", "political communications director"), "11-2032", "Public Relations Managers", "Management Occupations"),
    OccupationRule(("construction manager", "construction supervisor"), "11-9021", "Construction Managers", "Management Occupations"),
    OccupationRule(("engineering manager", "software development manager"), "11-9041", "Architectural and Engineering Managers", "Management Occupations"),
    OccupationRule(("restaurant owner", "restaurateur", "restauranteur", "bar manager", "pizzeria manager", "food service manager"), "11-9051", "Food Service Managers", "Management Occupations"),
    OccupationRule(("hotel manager", "guest house owner", "hotel guest liaison"), "11-9081", "Lodging Managers", "Management Occupations"),
    OccupationRule(("medical and health services manager", "healthcare consultant", "health club consultant"), "11-9111", "Medical and Health Services Managers", "Management Occupations"),
    OccupationRule(("social media manager", "ymca program director", "non profit", "homeless shelter manager"), "11-9151", "Social and Community Service Managers", "Management Occupations"),
    OccupationRule(("manager", "executive", "director", "company director", "project manager", "office manager", "internet projects manager", "pensions manager", "asset manager", "talent manager", "vip gaming manager"), "11-1021", "General and Operations Managers", "Management Occupations"),
    OccupationRule(("entrepreneur", "business owner", "small business owner", "owner", "founder", "franchisee", "self employed", "businesswoman", "businessman"), "11-1021", "General and Operations Managers", "Management Occupations"),
    OccupationRule(("farmer", "rancher", "jillaroo"), "11-9013", "Farmers, Ranchers, and Other Agricultural Managers", "Management Occupations"),
    OccupationRule(("accountant", "auditor", "chartered accountant", "bookkeeper", "tax accountant"), "13-2011", "Accountants and Auditors", "Business and Financial Operations Occupations"),
    OccupationRule(("actuary",), "15-2011", "Actuaries", "Computer and Mathematical Occupations"),
    OccupationRule(("financial analyst", "investment analyst", "investment banker", "equity research", "financial consultant", "investment advisor", "banker", "financial executive", "hedge fund"), "13-2051", "Financial and Investment Analysts", "Business and Financial Operations Occupations"),
    OccupationRule(("loan officer", "home loans consultant"), "13-2072", "Loan Officers", "Business and Financial Operations Occupations"),
    OccupationRule(("risk consultant", "financial crime consultant", "fraud prevention", "compliance"), "13-1041", "Compliance Officers", "Business and Financial Operations Occupations"),
    OccupationRule(("business analyst", "business consultant", "management consultant", "strategy consultant", "corporate consultant", "immigration consultant", "career consultant"), "13-1111", "Management Analysts", "Business and Financial Operations Occupations"),
    OccupationRule(("event planner", "events planner", "events co ordinator", "global events", "wedding planner"), "13-1121", "Meeting, Convention, and Event Planners", "Business and Financial Operations Occupations"),
    OccupationRule(("fundraiser", "charity worker", "charity organizer"), "13-1131", "Fundraisers", "Business and Financial Operations Occupations"),
    OccupationRule(("marketing", "market research", "advertising", "media buyer", "public relations", "communications", "pr consultant", "brand mentor"), "13-1161", "Market Research Analysts and Marketing Specialists", "Business and Financial Operations Occupations"),
    OccupationRule(("purchaser", "buyer", "retail buyer"), "13-1020", "Buyers and Purchasing Agents", "Business and Financial Operations Occupations"),
    OccupationRule(("logistics",), "13-1081", "Logisticians", "Business and Financial Operations Occupations"),
    OccupationRule(("program coordinator", "project coordinator", "business support coordinator", "research coordinator"), "13-1082", "Project Management Specialists", "Business and Financial Operations Occupations"),
    OccupationRule(("software engineer", "software developer", "app developer", "programmer", "software publisher", "security software engineer"), "15-1252", "Software Developers", "Computer and Mathematical Occupations"),
    OccupationRule(("web producer", "web editor", "web developer"), "15-1254", "Web Developers", "Computer and Mathematical Occupations"),
    OccupationRule(("ux designer", "web and digital", "digital interface"), "15-1255", "Web and Digital Interface Designers", "Computer and Mathematical Occupations"),
    OccupationRule(("cyber security", "information security"), "15-1212", "Information Security Analysts", "Computer and Mathematical Occupations"),
    OccupationRule(("data scientist", "network data scientist"), "15-2051", "Data Scientists", "Computer and Mathematical Occupations"),
    OccupationRule(("data analyst", "statistician", "quantitative strategist", "operations research"), "15-2041", "Statisticians", "Computer and Mathematical Occupations"),
    OccupationRule(("ai expert", "ai research", "computer engineer", "computer projects", "it consultant", "it quality analyst", "technology executive", "tech product", "gamer", "professional gamer"), "15-1299", "Computer Occupations, All Other", "Computer and Mathematical Occupations"),
    OccupationRule(("architect", "urban planner"), "17-1011", "Architects, Except Landscape and Naval", "Architecture and Engineering Occupations"),
    OccupationRule(("aerospace", "astronaut", "rocket scientist", "rocket technician", "missile engineer"), "17-2011", "Aerospace Engineers", "Architecture and Engineering Occupations"),
    OccupationRule(("biomedical engineer", "bio medical"), "17-2031", "Bioengineers and Biomedical Engineers", "Architecture and Engineering Occupations"),
    OccupationRule(("chemical engineer",), "17-2041", "Chemical Engineers", "Architecture and Engineering Occupations"),
    OccupationRule(("civil engineer",), "17-2051", "Civil Engineers", "Architecture and Engineering Occupations"),
    OccupationRule(("industrial engineer",), "17-2112", "Industrial Engineers", "Architecture and Engineering Occupations"),
    OccupationRule(("mechanical engineer", "nuclear engineer", "engineer", "engineering graduate"), "17-2199", "Engineers, All Other", "Architecture and Engineering Occupations"),
    OccupationRule(("chemist", "biochemist"), "19-2031", "Chemists", "Life, Physical, and Social Science Occupations"),
    OccupationRule(("astrophysicist", "physics"), "19-2012", "Physicists", "Life, Physical, and Social Science Occupations"),
    OccupationRule(("environmental advocate", "environmental"), "19-2041", "Environmental Scientists and Specialists, Including Health", "Life, Physical, and Social Science Occupations"),
    OccupationRule(("psychologist", "forensic psychologist"), "19-3033", "Clinical and Counseling Psychologists", "Life, Physical, and Social Science Occupations"),
    OccupationRule(("behavioral research", "pain researcher", "research assistant"), "19-3099", "Social Scientists and Related Workers, All Other", "Life, Physical, and Social Science Occupations"),
    OccupationRule(("therapist", "mental health counselor", "drug counselor", "substance abuse counselor", "sex therapist", "troubled teens mentor"), "21-1018", "Substance Abuse, Behavioral Disorder, and Mental Health Counselors", "Community and Social Service Occupations"),
    OccupationRule(("career counselor", "admissions counselor", "guidance counselor"), "21-1012", "Educational, Guidance, and Career Counselors and Advisors", "Community and Social Service Occupations"),
    OccupationRule(("social worker", "case manager", "housing case manager"), "21-1029", "Social Workers, All Other", "Community and Social Service Occupations"),
    OccupationRule(("pastor", "minister", "clergy", "missionary", "youth pastor"), "21-2011", "Clergy", "Community and Social Service Occupations"),
    OccupationRule(("youth mentor", "youth worker", "diversity advocate", "hearing advocate", "charity projects"), "21-1099", "Community and Social Service Specialists, All Other", "Community and Social Service Occupations"),
    OccupationRule(("attorney", "lawyer", "barrister", "public defender", "prosecutor", "district attorney", "law graduate", "candidate attorney", "law worker"), "23-1011", "Lawyers", "Legal Occupations"),
    OccupationRule(("judge",), "23-1023", "Judges, Magistrate Judges, and Magistrates", "Legal Occupations"),
    OccupationRule(("law clerk",), "23-1012", "Judicial Law Clerks", "Legal Occupations"),
    OccupationRule(("legal secretary",), "43-6012", "Legal Secretaries and Administrative Assistants", "Office and Administrative Support Occupations"),
    OccupationRule(("teacher", "educator", "professor", "lecturer", "student teacher"), "25-3099", "Teachers and Instructors, All Other", "Educational Instruction and Library Occupations"),
    OccupationRule(("principal", "college administrator", "college admissions director", "academic professional"), "25-9039", "Education Administrators, All Other", "Educational Instruction and Library Occupations"),
    OccupationRule(("school librarian",), "25-4022", "Librarians and Media Collections Specialists", "Educational Instruction and Library Occupations"),
    OccupationRule(("writer", "author", "technical writer", "journalist", "reporter", "crime reporter", "travel writer"), "27-3043", "Writers and Authors", "Arts, Design, Entertainment, Sports, and Media Occupations"),
    OccupationRule(("editor",), "27-3041", "Editors", "Arts, Design, Entertainment, Sports, and Media Occupations"),
    OccupationRule(("photographer",), "27-4021", "Photographers", "Arts, Design, Entertainment, Sports, and Media Occupations"),
    OccupationRule(("videographer", "video editor", "visual effects"), "27-4032", "Film and Video Editors", "Arts, Design, Entertainment, Sports, and Media Occupations"),
    OccupationRule(("producer", "film director", "director/writer", "television writer", "audio post producer", "digital producer"), "27-2012", "Producers and Directors", "Arts, Design, Entertainment, Sports, and Media Occupations"),
    OccupationRule(("actor", "actress", "comedian", "performer", "showgirl", "stunt performer", "broadway"), "27-2011", "Actors", "Arts, Design, Entertainment, Sports, and Media Occupations"),
    OccupationRule(("musician", "singer", "songwriter", "drummer", "recording artist", "hip hop artist", "dj", "music producer", "pop star"), "27-2042", "Musicians and Singers", "Arts, Design, Entertainment, Sports, and Media Occupations"),
    OccupationRule(("designer", "artist", "sculptor", "make up artist", "make-up artist", "graphic designer", "fashion designer", "interior designer", "jewelry designer", "footwear designer"), "27-1019", "Artists and Related Workers, All Other", "Arts, Design, Entertainment, Sports, and Media Occupations"),
    OccupationRule(("model", "pageant", "miss ", "mrs ", "pin up"), "27-2099", "Entertainers and Performers, Sports and Related Workers, All Other", "Arts, Design, Entertainment, Sports, and Media Occupations"),
    OccupationRule(("radio host", "radio presenter", "television presenter", "broadcaster", "podcast host", "e sports commentator"), "27-3011", "Broadcast Announcers and Radio Disc Jockeys", "Arts, Design, Entertainment, Sports, and Media Occupations"),
    OccupationRule(("coach", "athlete", "trainer", "pro athlete", "footballer", "nfl", "nba", "nhl", "mlb", "afl", "nrl", "mma", "boxer", "wrestler", "surfer", "cyclist", "olympian", "poker player", "poker champion", "racecar", "skater", "powerlifter", "bodybuilder", "triathlete", "swimmer", "volleyball", "gymnastics"), "27-2022", "Coaches and Scouts", "Arts, Design, Entertainment, Sports, and Media Occupations"),
    OccupationRule(("doctor", "physician", "surgeon", "anesthesiologist", "obgyn", "urologist", "neurosurgeon", "podiatrist", "resident", "medical doctor"), "29-1215", "Family Medicine Physicians", "Healthcare Practitioners and Technical Occupations"),
    OccupationRule(("dentist",), "29-1021", "Dentists, General", "Healthcare Practitioners and Technical Occupations"),
    OccupationRule(("veterinarian",), "29-1131", "Veterinarians", "Healthcare Practitioners and Technical Occupations"),
    OccupationRule(("pharmacist",), "29-1051", "Pharmacists", "Healthcare Practitioners and Technical Occupations"),
    OccupationRule(("dietitian", "dietician"), "29-1031", "Dietitians and Nutritionists", "Healthcare Practitioners and Technical Occupations"),
    OccupationRule(("registered nurse", "nurse practitioner", "critical care nurse", "pediatric nurse", "personal nurse", "nurse", "midwife"), "29-1141", "Registered Nurses", "Healthcare Practitioners and Technical Occupations"),
    OccupationRule(("physical therapist", "phyiscal therapist"), "29-1123", "Physical Therapists", "Healthcare Practitioners and Technical Occupations"),
    OccupationRule(("speech pathologist",), "29-1127", "Speech-Language Pathologists", "Healthcare Practitioners and Technical Occupations"),
    OccupationRule(("chiropractor",), "29-1011", "Chiropractors", "Healthcare Practitioners and Technical Occupations"),
    OccupationRule(("acupuncturist",), "29-1291", "Acupuncturists", "Healthcare Practitioners and Technical Occupations"),
    OccupationRule(("phlebotomist", "medical assistant"), "31-9099", "Healthcare Support Workers, All Other", "Healthcare Support Occupations"),
    OccupationRule(("pharmaceutical", "medical sales", "medical device sales"), "41-4011", "Sales Representatives, Wholesale and Manufacturing, Technical and Scientific Products", "Sales and Related Occupations"),
    OccupationRule(("police", "detective", "trooper", "sheriff", "swat", "fbi", "federal agent", "special forces", "hostage negotiator", "customs officer", "correctional officer", "corrections officer", "probation officer", "security officer", "loss prevention"), "33-3051", "Police and Sheriff's Patrol Officers", "Protective Service Occupations"),
    OccupationRule(("firefighter", "fire fighter", "fire captain", "fire lieutenant", "fireman", "aviation fire"), "33-2011", "Firefighters", "Protective Service Occupations"),
    OccupationRule(("lifeguard",), "33-9092", "Lifeguards, Ski Patrol, and Other Recreational Protective Service Workers", "Protective Service Occupations"),
    OccupationRule(("chef", "cook", "sushi chef", "personal chef", "caterer"), "35-2019", "Cooks, All Other", "Food Preparation and Serving Related Occupations"),
    OccupationRule(("bartender", "barista", "waiter", "waitress", "server", "fast food", "kitchen staff", "school lunch", "ice cream scooper"), "35-3031", "Waiters and Waitresses", "Food Preparation and Serving Related Occupations"),
    OccupationRule(("cleaner", "housekeeper"), "37-2012", "Maids and Housekeeping Cleaners", "Building and Grounds Cleaning and Maintenance Occupations"),
    OccupationRule(("landscaper", "gardener", "grounds"), "37-3011", "Landscaping and Groundskeeping Workers", "Building and Grounds Cleaning and Maintenance Occupations"),
    OccupationRule(("hairdresser", "hairstylist", "cosmetologist", "nail salon", "beautician"), "39-5012", "Hairdressers, Hairstylists, and Cosmetologists", "Personal Care and Service Occupations"),
    OccupationRule(("nanny", "aftercare", "childcare"), "39-9011", "Childcare Workers", "Personal Care and Service Occupations"),
    OccupationRule(("animal trainer", "dog trainer", "horse trainer", "dolphin trainer", "marine animal trainer"), "39-2011", "Animal Trainers", "Personal Care and Service Occupations"),
    OccupationRule(("zookeeper",), "39-2021", "Animal Caretakers", "Personal Care and Service Occupations"),
    OccupationRule(("fitness", "personal trainer", "pilates", "yoga instructor", "yogi", "crossfit", "boot camp instructor", "martial arts instructor", "surf instructor", "wilderness therapy guide"), "39-9031", "Exercise Trainers and Group Fitness Instructors", "Personal Care and Service Occupations"),
    OccupationRule(("tour guide", "adventure guide", "hiking guide", "fishing guide", "nature guide", "river guide", "wilderness guide", "sailing instructor", "water skiing instructor", "children's adventure guide"), "39-7010", "Tour and Travel Guides", "Personal Care and Service Occupations"),
    OccupationRule(("mortician", "mortuary", "funeral"), "39-4031", "Morticians, Undertakers, and Funeral Arrangers", "Personal Care and Service Occupations"),
    OccupationRule(("realtor", "real estate agent", "estate agent", "real estate broker", "property broker", "land broker"), "41-9022", "Real Estate Sales Agents", "Sales and Related Occupations"),
    OccupationRule(("sales representative", "sales rep", "sales consultant", "sales executive", "salesman", "saleswoman", "retail sales", "copier sales", "vehicle salesman", "elevator sales", "graphic sales", "shoe salesman", "slot machine salesman", "sales ", "retail worker", "retail salesperson"), "41-3091", "Sales Representatives of Services, Except Advertising, Insurance, Financial Services, and Travel", "Sales and Related Occupations"),
    OccupationRule(("insurance agent", "insurance sales"), "41-3021", "Insurance Sales Agents", "Sales and Related Occupations"),
    OccupationRule(("travel agent", "travel consultant", "vacation club sales", "timeshare"), "41-3041", "Travel Agents", "Sales and Related Occupations"),
    OccupationRule(("administrative assistant", "admin clerk", "personal assistant", "office assistant", "celebrity assistant", "administrative officer"), "43-6014", "Secretaries and Administrative Assistants, Except Legal, Medical, and Executive", "Office and Administrative Support Occupations"),
    OccupationRule(("customer service", "service consultant"), "43-4051", "Customer Service Representatives", "Office and Administrative Support Occupations"),
    OccupationRule(("clerk", "document manager", "grocery clerk", "broking assistant"), "43-9061", "Office Clerks, General", "Office and Administrative Support Occupations"),
    OccupationRule(("mail carrier", "postal worker", "post office"), "43-5052", "Postal Service Mail Carriers", "Office and Administrative Support Occupations"),
    OccupationRule(("airline agent", "gate agent"), "43-4181", "Reservation and Transportation Ticket Agents and Travel Clerks", "Office and Administrative Support Occupations"),
    OccupationRule(("farrier",), "45-2099", "Agricultural Workers, All Other", "Farming, Fishing, and Forestry Occupations"),
    OccupationRule(("fisherman", "commercial fisherman", "fishing boat captain", "fishmonger"), "45-3031", "Fishing and Hunting Workers", "Farming, Fishing, and Forestry Occupations"),
    OccupationRule(("logger", "logging"), "45-4022", "Logging Equipment Operators", "Farming, Fishing, and Forestry Occupations"),
    OccupationRule(("construction worker", "builder", "contractor", "carpenter", "residential builder", "highway construction", "stonemason"), "47-2061", "Construction Laborers", "Construction and Extraction Occupations"),
    OccupationRule(("plumber",), "47-2152", "Plumbers, Pipefitters, and Steamfitters", "Construction and Extraction Occupations"),
    OccupationRule(("electrician",), "47-2111", "Electricians", "Construction and Extraction Occupations"),
    OccupationRule(("mechanic", "motorcycle repair", "tire repair", "aerospace tech", "mining technician", "telephone technician", "maintenance", "elevator"), "49-9071", "Maintenance and Repair Workers, General", "Installation, Maintenance, and Repair Occupations"),
    OccupationRule(("factory worker", "truck assembler", "steelworker", "fifo worker", "warehouse operator", "oil driller", "gold miner", "labourer", "tradie", "furniture company"), "51-9199", "Production Workers, All Other", "Production Occupations"),
    OccupationRule(("pilot", "flight attendant", "air traffic controller", "airport ramp", "marine stewardess"), "53-2012", "Commercial Pilots", "Transportation and Material Moving Occupations"),
    OccupationRule(("truck driver", "bus driver", "limousine driver", "courier driver", "delivery rider", "u s mail carrier"), "53-3032", "Heavy and Tractor-Trailer Truck Drivers", "Transportation and Material Moving Occupations"),
    OccupationRule(("military", "army", "navy", "marine", "air force", "veteran", "drill sergeant", "special ops", "navy seal"), "55-3019", "Military Enlisted Tactical Operations and Air/Weapons Specialists and Crew Members, All Other", "Military Specific Occupations"),
    OccupationRule(("homemaker", "stay at home", "mother", "single mom"), "NL-1000", "Homemakers", NOT_CLASSIFIED_MAJOR_GROUP, "medium", True, "Project-specific non-SOC classification for unpaid household roles."),
    OccupationRule(("retired",), "NL-2000", "Retired", NOT_CLASSIFIED_MAJOR_GROUP, "medium", True, "Project-specific non-SOC classification when no active occupation is stated."),
)


def classify_occupation(occupation: str | None) -> SocMapping:
    raw = (occupation or "").strip()
    normalized = _normalize(raw)
    if not normalized:
        return SocMapping("", "", "", "", "none", True, "Missing occupation; manual review required.")

    for rule in (*STUDENT_RULES, *SOC_RULES):
        if _matches(rule, normalized):
            return _mapping_from_rule(raw, rule)

    return SocMapping(
        raw,
        "00-0000",
        "All Occupations",
        "All Occupations",
        "low",
        True,
        "Fallback classification; manual SOC review required.",
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


def _mapping_from_rule(occupation: str, rule: OccupationRule) -> SocMapping:
    return SocMapping(
        occupation,
        rule.soc_code,
        rule.soc_title,
        rule.soc_major_group,
        rule.confidence,
        rule.review_required,
        rule.notes,
    )


def _matches(rule: OccupationRule, normalized: str) -> bool:
    padded = f" {normalized} "
    return any(f" {_normalize(keyword)} " in padded for keyword in rule.keywords)


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()

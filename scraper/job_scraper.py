#!/usr/bin/env python3
"""
Kanzlei Job-Scraper V4.1 - Optimiert für GitHub Actions
Scrapt Karriereseiten von Kanzleien und extrahiert Stellenanzeigen.
Nutzt Gemini Flash als LLM-Fallback für maximale Kosteneffizienz.
"""

import os
import sys
import json
import csv
import logging
import time
import re
import hashlib
from datetime import date, datetime
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# Optionale Imports
try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

# Gemini API Konfiguration
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

# ===================== LOGGING =====================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


# ===================== KONFIGURATION =====================
@dataclass
class Config:
    """Zentrale Konfiguration für den Scraper."""
    base_timeout: int = 30000
    max_concurrent: int = 3  # Konservativ für GitHub Actions (2-4 Cores)
    max_retries: int = 1
    direct_api_timeout: int = 15
    llm_model: str = "gemini-3-flash-preview"
    llm_max_tokens: int = 4000
    chunk_chars: int = 12000
    
    # ATS-Signaturen für Erkennung und direkte API-Aufrufe
    ats_signatures: Dict[str, Dict] = field(default_factory=lambda: {
        "personio": {
            "patterns": ["personio.de", "personio.com"],
            "api_template": "https://{slug}.jobs.personio.de/xml"
        },
        "greenhouse": {
            "patterns": ["greenhouse.io", "boards.greenhouse"],
            "api_template": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
        },
        "lever": {
            "patterns": ["lever.co", "jobs.lever"],
            "api_template": "https://api.lever.co/v0/postings/{slug}"
        },
        "recruitee": {
            "patterns": ["recruitee.com"],
            "api_template": "https://{slug}.recruitee.com/api/offers"
        },
        "workable": {
            "patterns": ["workable.com", "apply.workable"],
            "api_template": "https://apply.workable.com/api/v1/widget/accounts/{slug}"
        },
        "smartrecruiters": {
            "patterns": ["smartrecruiters.com"],
            "api_template": "https://api.smartrecruiters.com/v1/companies/{slug}/postings"
        },
        "ashby": {
            "patterns": ["ashbyhq.com", "jobs.ashbyhq"],
            "api_template": "https://api.ashbyhq.com/posting-api/job-board/{slug}"
        },
        "bamboohr": {
            "patterns": ["bamboohr.com"],
            "api_template": "https://{slug}.bamboohr.com/careers/list"
        },
        "breezyhr": {
            "patterns": ["breezy.hr"],
            "api_template": "https://{slug}.breezy.hr/json"
        },
        "softgarden": {
            "patterns": ["softgarden.io", "softgarden.de"],
        },
        "join": {
            "patterns": ["join.com"],
        },
        "teamtailor": {
            "patterns": ["teamtailor.com"],
        },
        "workday": {
            "patterns": ["myworkdayjobs.com", "workday.com/de"],
        },
        "taleo": {
            "patterns": ["taleo.net"],
        },
        "successfactors": {
            "patterns": ["successfactors.com", "successfactors.eu"],
        },
        "dvinci": {
            "patterns": ["dvinci.de", "d-vinci.de"],
        },
        "rexx": {
            "patterns": ["rexx-systems.com", "rexx-recruitment"],
        },
        "concludis": {
            "patterns": ["concludis.de"],
        },
        "coveto": {
            "patterns": ["coveto.de"],
        },
        "haufe": {
            "patterns": ["umantis.com", "haufe-talent"],
        },
    })
    
    # Deutsche Städte und Bundesländer für Standort-Filterung
    german_indicators: List[str] = field(default_factory=lambda: [
        "berlin", "hamburg", "münchen", "munich", "köln", "cologne",
        "frankfurt", "stuttgart", "düsseldorf", "dortmund", "essen",
        "leipzig", "bremen", "dresden", "hannover", "nürnberg",
        "duisburg", "bochum", "wuppertal", "bielefeld", "bonn",
        "münster", "karlsruhe", "mannheim", "augsburg", "wiesbaden",
        "mönchengladbach", "aachen", "braunschweig", "kiel", "chemnitz",
        "halle", "magdeburg", "freiburg", "lübeck", "erfurt",
        "rostock", "mainz", "kassel", "oberhausen", "saarbrücken",
        "heidelberg", "potsdam", "darmstadt", "regensburg", "würzburg",
        "wolfsburg", "ulm", "offenbach", "ingolstadt", "göttingen",
        "heilbronn", "pforzheim", "reutlingen", "koblenz", "trier",
        "jena", "erlangen", "konstanz", "bamberg", "bayreuth",
        "deutschland", "germany", "german", "deutsch", "bundesweit",
        "remote deutschland", "dach", "d-a-ch",
        "bayern", "baden-württemberg", "nordrhein-westfalen", "nrw",
        "hessen", "niedersachsen", "sachsen", "rheinland-pfalz",
        "schleswig-holstein", "brandenburg", "thüringen",
        "sachsen-anhalt", "mecklenburg-vorpommern", "saarland",
    ])
    
    foreign_indicators: List[str] = field(default_factory=lambda: [
        "usa", "united states", "uk", "united kingdom", "france",
        "italy", "spain", "london", "paris", "new york", "vienna",
        "zurich", "zürich", "amsterdam", "brussels", "bruxelles",
        "singapore", "hong kong", "tokyo", "sydney", "dubai",
        "moscow", "beijing", "shanghai", "toronto", "chicago",
        "los angeles", "san francisco", "boston", "washington",
        "australia", "canada", "india", "china", "japan",
    ])
    
    def is_german_location(self, location: str) -> bool:
        """Prüft ob ein Standort in Deutschland liegt."""
        if not location or not location.strip():
            return True  # Leerer Standort = vermutlich Deutschland (Kanzlei-Kontext)
        loc = location.lower().strip()
        
        # PLZ-Erkennung (5-stellig)
        if re.search(r'\b[0-9]{5}\b', loc):
            return True
        
        # Explizit deutsch
        if any(ind in loc for ind in self.german_indicators):
            return True
        
        # Explizit ausländisch
        if any(ind in loc for ind in self.foreign_indicators):
            return False
        
        # "Remote" ohne weitere Angabe = Deutschland im Kanzlei-Kontext
        if loc in ["remote", "hybrid", "homeoffice", "home office"]:
            return True
        
        return True  # Im Zweifel: Deutschland (Kanzlei-Kontext)


config = Config()


# ===================== DATENMODELLE =====================
@dataclass
class Job:
    """Repräsentiert eine gefundene Stellenanzeige."""
    title: str
    employer: str
    location: str = ""
    date: str = ""
    link: str = ""
    email: str = ""
    ats: str = "unknown"
    extraction_method: str = "unknown"
    
    def to_csv_row(self) -> List[str]:
        """Konvertiert in das CSV-Format: Kanzlei, Jobtitel, Standort, URL, Datum, E-Mail"""
        return [
            self.employer,
            self.title,
            self.location if self.location else "Zentrale/Unbekannt",
            self.link,
            self.date if self.date else date.today().isoformat(),
            self.email,
        ]


@dataclass
class Company:
    """Repräsentiert eine zu scrapende Kanzlei."""
    name: str
    url: str  # Jobboard-URL oder Domain
    domain: str = ""
    ats: str = "unknown"
    
    def __post_init__(self):
        if self.url and not self.url.startswith("http"):
            self.url = "https://" + self.url.lstrip("/")


# ===================== HILFSFUNKTIONEN =====================
def is_valid_job(job) -> bool:
    """Zentrale Validierung: Ist dieser Eintrag eine echte Stellenanzeige?
    Wird nach ALLEN Extraktionsmethoden als finaler Filter angewendet."""
    title = job.title.strip()
    title_lower = title.lower()
    url = job.link.lower() if job.link else ""
    
    # === REGEL 1: Mindestlänge ===
    if len(title) < 4:
        return False
    
    # === REGEL 2: Offensichtliche Nicht-Jobs (exakt) ===
    reject_exact = {
        "bottom-left", "bottom-right", "top-left", "top-right",
        "news & events", "jobs & karriere", "karriere", "careers",
        "alle stellenangebote", "alle offenen stellenanzeigen",
        "view all locations", "mehr erfahren", "weiterlesen",
    }
    if title_lower in reject_exact:
        return False
    
    # === REGEL 3: URL-basierte Ausschlüsse ===
    non_job_url_segments = [
        "/sectors/", "/services/", "/insights/", "/news/",
        "/rechtsgebiete/", "/rechtsgebiete#", "/transformation/",
        "/solutions", "/for-good", "/locations",
        "/lawyers/", "/people/", "/team/",
        "/blog/", "/alumni/", "/events/",
        "/california-privacy", "/website-privacy", "/uk-tax-strategy",
        "javascript:",
    ]
    if url and any(seg in url for seg in non_job_url_segments):
        # Ausnahme: URL enthält auch Job-Hinweise
        job_url_hints = ["/job", "/stelle", "/position", "/vacancy", "/opening", "/career"]
        if not any(hint in url for hint in job_url_hints):
            return False
    
    # === REGEL 4: Muster-basierte Ausschlüsse für Titel ===
    reject_patterns = [
        r"^careers? in ",  # "Careers in Belgium"
        r"^view all",
        r"^learn more",
        r"^alle (karriere|offenen|stellen)",
        r"^einstieg bei ",
        r"^ihre chancen bei",
        r"^deine karriere",
        r"privacy (notice|policy)",
        r"tax strategy",
        r"scam communications",
        r"\bpodcast\b.*\d{4}",  # Podcast mit Datum = Blog
        r"^\".*\"\s*-\s",  # Zitate = Blog
        r"\binterview\b.*(partnerinnen|partner).*\d{4}",  # Partner-Interviews = Blog
        r"^what.*(clients|horizon)",  # "What our clients..." / "What's on the horizon"
        r"cbh in der presse",
    ]
    if any(re.search(p, title_lower) for p in reject_patterns):
        return False
    
    # === REGEL 4b: Kategorieseiten (enthalten Job-Keywords aber sind keine Stellen) ===
    # Muster: Komma-getrennte Berufsgruppen als Navigations-Kategorie
    if re.match(r'^[^(]+,\s*[^(]+,\s*[^(]+$', title) and '(m' not in title_lower and '(w' not in title_lower:
        if not re.search(r'/d\)|/x\)', title):
            return False
    
    # Muster: "X & Y" als Kategorieseite (nur wenn es ein kurzer Titel ohne Job-Keywords ist)
    if re.match(r'^[\w\säöüÄÖÜ-]+\s*&\s*[\w\säöüÄÖÜ-]+$', title):
        if len(title) < 40 and not re.search(r'rechtsanwalt|steuer|notar|fachangestellte|buchhalter|assisten|referendar|studium|ausbildung|praktik', title_lower):
            return False
    
    # === REGEL 5: Personennamen (z.B. Anwaltsprofile) ===
    if "/lawyers/" in url or "/people/" in url or "/team/" in url:
        return False
    if re.match(r'^[A-Z][a-zäöü]+\.?\s+[A-Z]', title) and len(title.split()) <= 4:
        if not re.search(r

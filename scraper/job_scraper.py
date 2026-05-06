#!/usr/bin/env python3
"""
Kanzlei Job-Scraper V4.0 - Optimiert für GitHub Actions
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
    max_concurrent: int = 3  # Konservativ für GitHub Actions
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
        # Hinweis: "Zur Initiativbewerbung" wird als generischer Link behandelt,
        # da es kein spezifischer Jobtitel ist. Echte Initiativbewerbungen haben
        # typischerweise "Initiativbewerbung (m/w/d)" als Titel.
    ]
    if any(re.search(p, title_lower) for p in reject_patterns):
        return False
    
    # === REGEL 4b: Kategorieseiten (enthalten Job-Keywords aber sind keine Stellen) ===
    # Muster: Komma-getrennte Berufsgruppen als Navigations-Kategorie
    if re.match(r'^[^(]+,\s*[^(]+,\s*[^(]+$', title) and '(m' not in title_lower and '(w' not in title_lower:
        # "Rechtsanwälte, Wirtschaftsprüfer, Steuerberater" = Kategorie
        # Aber "Referendar (m/w/d), wissenschaftliche Mitarbeiter (m/w/d)" = echte Stelle
        if not re.search(r'/d\)|/x\)', title):
            return False
    
    # Muster: "X & Y" als Kategorieseite (nur wenn es ein kurzer Titel ohne Job-Keywords ist)
    if re.match(r'^[\w\säöüÄÖÜ-]+\s*&\s*[\w\säöüÄÖÜ-]+$', title):
        # Nur wenn KEIN Job-Keyword enthalten UND kurz (< 40 Zeichen)
        if len(title) < 40 and not re.search(r'rechtsanwalt|steuer|notar|fachangestellte|buchhalter|assisten|referendar|studium|ausbildung|praktik', title_lower):
            return False
    
    # === REGEL 5: Personennamen (z.B. Anwaltsprofile) ===
    # Muster: "Vorname Nachname" ohne Job-Keywords, URL enthält /lawyers/
    if "/lawyers/" in url or "/people/" in url or "/team/" in url:
        return False
    # Kurze Namen (2-3 Wörter, nur Großbuchstaben-Anfang, keine Job-Keywords)
    if re.match(r'^[A-Z][a-zäöü]+\.?\s+[A-Z]', title) and len(title.split()) <= 4:
        # Prüfe ob es ein Name ist (keine Job-Keywords enthalten)
        if not re.search(r'rechtsanwalt|steuer|notar|fachangestellte|buchhalter|assisten|referendar|jurist|anwalt|praktikant|mitarbeiter|manager|consultant|\(m/w|\(w/m', title_lower):
            return False
    
    # === REGEL 6: Reine Kategorien/Rechtsgebiete (ohne Job-Indikator) ===
    category_patterns = [
        r"^(energy|financial services|life sciences|mobility|retail|technology)",
        r"^(real estate|regulatory|artificial intelligence|online safety)$",
        r"^(the built environment|urban dynamics|workforce solutions)$",
        r"^(unternehmen|infrastruktur|geistiges eigentum|immobilien).*&",
        r"^(handels-|mergers & acquisitions|venture capital|banken)",
        r"^(startup-beratung|professional liability|innovation contest)$",
        r"^(wirtschaftsjuristen|business services)$",
        r"^(esg|esg \u2013|it and data)$",
        r"^osborne clarke",
    ]
    if any(re.search(p, title_lower) for p in category_patterns):
        # Nur ablehnen wenn kein starker Job-Indikator vorhanden
        if not re.search(r'\(m/w/d\)|\(w/m/d\)|\(m/f/d\)', title):
            return False
    
    return True


def detect_ats(url: str) -> str:
    """Erkennt das ATS-System anhand der URL."""
    if not url:
        return "unknown"
    url_lower = url.lower()
    for ats_name, sig in config.ats_signatures.items():
        if any(p in url_lower for p in sig["patterns"]):
            return ats_name
    return "unknown"


def extract_company_slug(url: str, ats: str) -> Optional[str]:
    """Extrahiert den Company-Slug aus einer ATS-URL."""
    parsed = urlparse(url)
    path_parts = [p for p in parsed.path.strip("/").split("/") if p]
    host_parts = parsed.hostname.split(".") if parsed.hostname else []
    
    if ats == "greenhouse":
        # boards.greenhouse.io/SLUG oder boards-api.greenhouse.io/v1/boards/SLUG
        if path_parts:
            return path_parts[0] if "embed" not in path_parts[0] else (path_parts[1] if len(path_parts) > 1 else None)
    elif ats == "lever":
        # jobs.lever.co/SLUG
        if path_parts:
            return path_parts[0]
    elif ats == "personio":
        # SLUG.jobs.personio.de
        if host_parts and "personio" in parsed.hostname:
            return host_parts[0]
    elif ats == "recruitee":
        # SLUG.recruitee.com
        if host_parts:
            return host_parts[0]
    elif ats == "workable":
        # apply.workable.com/SLUG
        if path_parts:
            return path_parts[0]
    elif ats == "smartrecruiters":
        # jobs.smartrecruiters.com/SLUG
        if path_parts:
            return path_parts[0]
    elif ats == "ashby":
        # jobs.ashbyhq.com/SLUG
        if path_parts:
            return path_parts[0]
    elif ats == "bamboohr":
        # SLUG.bamboohr.com
        if host_parts:
            return host_parts[0]
    elif ats == "breezyhr":
        # SLUG.breezy.hr
        if host_parts:
            return host_parts[0]
    
    return None


def try_parse_json(text: str) -> Optional[Any]:
    """Versucht JSON aus einem Text zu extrahieren."""
    if not text or not text.strip():
        return None
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # JSONP-Callback entfernen
    jsonp_match = re.match(r'^[a-zA-Z_]\w*\s*\((.*)\)\s*;?\s*$', text, re.DOTALL)
    if jsonp_match:
        try:
            return json.loads(jsonp_match.group(1))
        except json.JSONDecodeError:
            pass
    
    # JSON aus Text extrahieren
    for start_char, end_char in [("{", "}"), ("[", "]")]:
        start = text.find(start_char)
        if start == -1:
            continue
        depth = 0
        for i in range(start, len(text)):
            if text[i] == start_char:
                depth += 1
            elif text[i] == end_char:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i+1])
                    except json.JSONDecodeError:
                        break
    return None


def normalize_url(base_url: str, href: str) -> str:
    """Normalisiert relative URLs."""
    if not href:
        return ""
    if href.startswith(("http://", "https://")):
        return href
    return urljoin(base_url, href)


# ===================== DIREKTE API-CLIENTS =====================
class DirectATSClient:
    """Ruft Jobs direkt über ATS-APIs ab (ohne Browser)."""
    
    def __init__(self, employer: str, source_url: str, ats: str):
        self.employer = employer
        self.source_url = source_url
        self.ats = ats
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/xml, */*",
            "Accept-Language": "de-DE,de;q=0.9",
        })
    
    def fetch_jobs(self) -> Optional[List[Job]]:
        """Versucht Jobs über die direkte API des ATS abzurufen."""
        try:
            method = getattr(self, f"_fetch_{self.ats}", None)
            if method:
                result = method()
                if result:
                    logger.info(f"  Direkte API ({self.ats}): {len(result)} Jobs für {self.employer}")
                return result
        except Exception as e:
            logger.debug(f"  Direkte API fehlgeschlagen für {self.employer}: {e}")
        return None
    
    def _fetch_greenhouse(self) -> Optional[List[Job]]:
        slug = extract_company_slug(self.source_url, "greenhouse")
        if not slug:
            return None
        url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
        resp = self.session.get(url, timeout=config.direct_api_timeout)
        resp.raise_for_status()
        data = resp.json()
        jobs_data = data.get("jobs", [])
        if not jobs_data:
            return None
        return [
            Job(
                title=j.get("title", "").strip(),
                employer=self.employer,
                location=j.get("location", {}).get("name", "") if isinstance(j.get("location"), dict) else str(j.get("location", "")),
                date=str(j.get("updated_at", ""))[:10],
                link=j.get("absolute_url", self.source_url),
                ats="greenhouse",
                extraction_method="direct_api",
            )
            for j in jobs_data if j.get("title")
        ]
    
    def _fetch_lever(self) -> Optional[List[Job]]:
        slug = extract_company_slug(self.source_url, "lever")
        if not slug:
            return None
        url = f"https://api.lever.co/v0/postings/{slug}"
        resp = self.session.get(url, timeout=config.direct_api_timeout)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list):
            return None
        jobs = []
        for j in data:
            title = j.get("text", "").strip()
            if not title:
                continue
            categories = j.get("categories", {})
            location = categories.get("location", "") if isinstance(categories, dict) else ""
            date_str = ""
            created = j.get("createdAt")
            if created and isinstance(created, (int, float)):
                try:
                    date_str = datetime.fromtimestamp(created / 1000).strftime("%Y-%m-%d")
                except Exception:
                    pass
            jobs.append(Job(
                title=title,
                employer=self.employer,
                location=location if isinstance(location, str) else str(location),
                date=date_str,
                link=j.get("hostedUrl", self.source_url),
                ats="lever",
                extraction_method="direct_api",
            ))
        return jobs if jobs else None
    
    def _fetch_personio(self) -> Optional[List[Job]]:
        slug = extract_company_slug(self.source_url, "personio")
        if not slug:
            return None
        url = f"https://{slug}.jobs.personio.de/xml"
        resp = self.session.get(url, timeout=config.direct_api_timeout)
        resp.raise_for_status()
        # XML-Parsing
        soup = BeautifulSoup(resp.text, "html.parser")
        positions = soup.find_all("position")
        if not positions:
            return None
        jobs = []
        for pos in positions:
            title_el = pos.find("name")
            title = title_el.get_text(strip=True) if title_el else ""
            if not title:
                continue
            loc_el = pos.find("office")
            location = loc_el.get_text(strip=True) if loc_el else ""
            id_el = pos.find("id")
            job_id = id_el.get_text(strip=True) if id_el else ""
            link = f"https://{slug}.jobs.personio.de/job/{job_id}" if job_id else self.source_url
            jobs.append(Job(
                title=title,
                employer=self.employer,
                location=location,
                link=link,
                ats="personio",
                extraction_method="direct_api",
            ))
        return jobs if jobs else None
    
    def _fetch_recruitee(self) -> Optional[List[Job]]:
        slug = extract_company_slug(self.source_url, "recruitee")
        if not slug:
            return None
        url = f"https://{slug}.recruitee.com/api/offers"
        resp = self.session.get(url, timeout=config.direct_api_timeout)
        resp.raise_for_status()
        data = resp.json()
        offers = data.get("offers", [])
        if not offers:
            return None
        return [
            Job(
                title=o.get("title", "").strip(),
                employer=self.employer,
                location=o.get("location", ""),
                date=str(o.get("published_at", ""))[:10],
                link=o.get("careers_url", self.source_url),
                ats="recruitee",
                extraction_method="direct_api",
            )
            for o in offers if o.get("title")
        ]
    
    def _fetch_workable(self) -> Optional[List[Job]]:
        slug = extract_company_slug(self.source_url, "workable")
        if not slug:
            return None
        url = f"https://apply.workable.com/api/v1/widget/accounts/{slug}"
        resp = self.session.get(url, timeout=config.direct_api_timeout)
        resp.raise_for_status()
        data = resp.json()
        jobs_data = data.get("jobs", [])
        if not jobs_data:
            return None
        return [
            Job(
                title=j.get("title", "").strip(),
                employer=self.employer,
                location=j.get("location", ""),
                link=f"https://apply.workable.com/{slug}/j/{j.get('shortcode', '')}/",
                ats="workable",
                extraction_method="direct_api",
            )
            for j in jobs_data if j.get("title")
        ]
    
    def _fetch_smartrecruiters(self) -> Optional[List[Job]]:
        slug = extract_company_slug(self.source_url, "smartrecruiters")
        if not slug:
            return None
        url = f"https://api.smartrecruiters.com/v1/companies/{slug}/postings"
        resp = self.session.get(url, timeout=config.direct_api_timeout)
        resp.raise_for_status()
        data = resp.json()
        postings = data.get("content", [])
        if not postings:
            return None
        return [
            Job(
                title=p.get("name", "").strip(),
                employer=self.employer,
                location=p.get("location", {}).get("city", "") if isinstance(p.get("location"), dict) else "",
                link=p.get("ref", self.source_url),
                ats="smartrecruiters",
                extraction_method="direct_api",
            )
            for p in postings if p.get("name")
        ]
    
    def _fetch_ashby(self) -> Optional[List[Job]]:
        slug = extract_company_slug(self.source_url, "ashby")
        if not slug:
            return None
        url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
        resp = self.session.get(url, timeout=config.direct_api_timeout)
        resp.raise_for_status()
        data = resp.json()
        jobs_data = data.get("jobs", [])
        if not jobs_data:
            return None
        return [
            Job(
                title=j.get("title", "").strip(),
                employer=self.employer,
                location=j.get("location", ""),
                link=j.get("jobUrl", self.source_url),
                ats="ashby",
                extraction_method="direct_api",
            )
            for j in jobs_data if j.get("title")
        ]
    
    def _fetch_bamboohr(self) -> Optional[List[Job]]:
        slug = extract_company_slug(self.source_url, "bamboohr")
        if not slug:
            return None
        url = f"https://{slug}.bamboohr.com/careers/list"
        resp = self.session.get(url, timeout=config.direct_api_timeout, headers={"Accept": "application/json"})
        resp.raise_for_status()
        data = resp.json()
        results = data.get("result", [])
        if not results:
            return None
        jobs = []
        for r in results:
            title = r.get("jobOpeningName", "").strip()
            if title:
                jobs.append(Job(
                    title=title,
                    employer=self.employer,
                    location=r.get("location", {}).get("city", "") if isinstance(r.get("location"), dict) else "",
                    link=f"https://{slug}.bamboohr.com/careers/{r.get('id', '')}",
                    ats="bamboohr",
                    extraction_method="direct_api",
                ))
        return jobs if jobs else None
    
    def _fetch_breezyhr(self) -> Optional[List[Job]]:
        slug = extract_company_slug(self.source_url, "breezyhr")
        if not slug:
            return None
        url = f"https://{slug}.breezy.hr/json"
        resp = self.session.get(url, timeout=config.direct_api_timeout)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list):
            return None
        return [
            Job(
                title=j.get("name", "").strip(),
                employer=self.employer,
                location=j.get("location", {}).get("name", "") if isinstance(j.get("location"), dict) else "",
                link=j.get("url", self.source_url),
                ats="breezyhr",
                extraction_method="direct_api",
            )
            for j in data if j.get("name")
        ]


# ===================== DOM PARSER =====================
class DOMParser:
    """Extrahiert Jobs aus HTML-Seiten."""
    
    def __init__(self, employer: str, source_url: str, ats: str):
        self.employer = employer
        self.source_url = source_url
        self.ats = ats
    
    def extract(self, html: str) -> Tuple[List[Job], int]:
        """Extrahiert Jobs aus HTML. Gibt (jobs, filtered_count) zurück."""
        soup = BeautifulSoup(html, "html.parser")
        
        # Strategie 1: JSON-LD / Schema.org
        jobs = self._extract_jsonld(soup)
        if jobs:
            return self._filter_german(jobs)
        
        # Strategie 2: Bekannte ATS-DOM-Strukturen
        jobs = self._extract_ats_specific(soup)
        if jobs:
            return self._filter_german(jobs)
        
        # Strategie 3: Semantische Link-Analyse
        jobs = self._extract_semantic_links(soup)
        if jobs:
            return self._filter_german(jobs)
        
        # Strategie 4: Tabellen-Extraktion
        jobs = self._extract_tables(soup)
        if jobs:
            return self._filter_german(jobs)
        
        return [], 0
    
    def _filter_german(self, jobs: List[Job]) -> Tuple[List[Job], int]:
        """Filtert auf deutsche Standorte und dedupliziert."""
        german_jobs = []
        filtered = 0
        seen = set()
        
        for job in jobs:
            key = (job.title.lower().strip(), job.employer.lower())
            if key in seen:
                continue
            seen.add(key)
            if config.is_german_location(job.location):
                german_jobs.append(job)
            else:
                filtered += 1
        
        return german_jobs, filtered
    
    def _extract_jsonld(self, soup: BeautifulSoup) -> List[Job]:
        """Extrahiert Jobs aus JSON-LD Structured Data."""
        jobs = []
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
                if isinstance(data, list):
                    for item in data:
                        job = self._parse_jsonld_item(item)
                        if job:
                            jobs.append(job)
                elif isinstance(data, dict):
                    if data.get("@type") == "JobPosting":
                        job = self._parse_jsonld_item(data)
                        if job:
                            jobs.append(job)
                    # ItemList mit JobPostings
                    elif data.get("@type") == "ItemList":
                        for item in data.get("itemListElement", []):
                            if isinstance(item, dict):
                                actual = item.get("item", item)
                                job = self._parse_jsonld_item(actual)
                                if job:
                                    jobs.append(job)
                    # Graph
                    elif "@graph" in data:
                        for item in data["@graph"]:
                            job = self._parse_jsonld_item(item)
                            if job:
                                jobs.append(job)
            except (json.JSONDecodeError, TypeError):
                continue
        return jobs
    
    def _parse_jsonld_item(self, item: dict) -> Optional[Job]:
        """Parst ein einzelnes JSON-LD JobPosting."""
        if not isinstance(item, dict):
            return None
        if item.get("@type") not in ["JobPosting", "jobPosting"]:
            return None
        
        title = item.get("title", item.get("name", "")).strip()
        if not title:
            return None
        
        # Location extrahieren
        location = ""
        job_loc = item.get("jobLocation")
        if isinstance(job_loc, dict):
            address = job_loc.get("address", {})
            if isinstance(address, dict):
                location = address.get("addressLocality", address.get("streetAddress", ""))
            elif isinstance(address, str):
                location = address
            if not location:
                location = job_loc.get("name", "")
        elif isinstance(job_loc, list) and job_loc:
            first = job_loc[0]
            if isinstance(first, dict):
                address = first.get("address", {})
                location = address.get("addressLocality", "") if isinstance(address, dict) else str(address)
        
        # URL
        url = item.get("url", item.get("sameAs", ""))
        if not url:
            url = self.source_url
        
        # Datum
        date_posted = item.get("datePosted", "")
        if date_posted:
            date_posted = str(date_posted)[:10]
        
        return Job(
            title=title,
            employer=self.employer,
            location=location,
            date=date_posted,
            link=url,
            ats=self.ats,
            extraction_method="jsonld",
        )
    
    def _extract_ats_specific(self, soup: BeautifulSoup) -> List[Job]:
        """Extrahiert Jobs aus bekannten ATS-DOM-Strukturen."""
        jobs = []
        
        # Personio-spezifische Selektoren
        for el in soup.select("[data-qa='job-title'], .job-title, .position-title"):
            title = el.get_text(strip=True)
            if title and len(title) > 3:
                link = ""
                parent_a = el.find_parent("a")
                if parent_a and parent_a.get("href"):
                    link = normalize_url(self.source_url, parent_a["href"])
                elif el.name == "a":
                    link = normalize_url(self.source_url, el.get("href", ""))
                
                # Location suchen
                location = ""
                parent = el.parent
                if parent:
                    loc_el = parent.find(class_=re.compile(r"location|city|standort|ort", re.I))
                    if loc_el:
                        location = loc_el.get_text(strip=True)
                
                jobs.append(Job(
                    title=title,
                    employer=self.employer,
                    location=location,
                    link=link or self.source_url,
                    ats=self.ats,
                    extraction_method="dom_ats",
                ))
        
        return jobs
    
    def _extract_semantic_links(self, soup: BeautifulSoup) -> List[Job]:
        """Extrahiert Jobs aus semantischen Link-Strukturen."""
        jobs = []
        
        # Job-relevante Container finden
        job_containers = soup.find_all(
            class_=re.compile(r"job|position|stelle|karriere|career|vacancy|opening", re.I)
        )
        
        # Auch nach IDs suchen
        job_containers += soup.find_all(
            id=re.compile(r"job|position|stelle|karriere|career|vacancy|opening", re.I)
        )
        
        # Links in Job-Containern
        processed_links = set()
        for container in job_containers:
            for link in container.find_all("a", href=True):
                href = link.get("href", "")
                if href in processed_links:
                    continue
                processed_links.add(href)
                
                text = link.get_text(strip=True)
                if self._is_likely_job_title(text):
                    full_url = normalize_url(self.source_url, href)
                    
                    # Location aus Nachbar-Elementen
                    location = self._find_nearby_location(link)
                    
                    jobs.append(Job(
                        title=text,
                        employer=self.employer,
                        location=location,
                        link=full_url,
                        ats=self.ats,
                        extraction_method="dom_semantic",
                    ))
        
        # Fallback: Alle Links mit job-relevanten URLs
        if not jobs:
            for link in soup.find_all("a", href=True):
                href = link.get("href", "").lower()
                if href in processed_links:
                    continue
                
                # URL enthält Job-Hinweise
                if any(kw in href for kw in ["/job", "/stelle", "/position", "/career", "/vacancy", "/opening", "job_id=", "jobid="]):
                    text = link.get_text(strip=True)
                    if self._is_likely_job_title(text):
                        processed_links.add(link.get("href", ""))
                        full_url = normalize_url(self.source_url, link.get("href", ""))
                        location = self._find_nearby_location(link)
                        jobs.append(Job(
                            title=text,
                            employer=self.employer,
                            location=location,
                            link=full_url,
                            ats=self.ats,
                            extraction_method="dom_links",
                        ))
        
        return jobs
    
    def _extract_tables(self, soup: BeautifulSoup) -> List[Job]:
        """Extrahiert Jobs aus HTML-Tabellen."""
        jobs = []
        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            if len(rows) < 2:
                continue
            
            # Header-Zeile analysieren
            headers = [th.get_text(strip=True).lower() for th in rows[0].find_all(["th", "td"])]
            title_col = None
            loc_col = None
            
            for i, h in enumerate(headers):
                if any(kw in h for kw in ["stelle", "position", "titel", "job", "bezeichnung", "title"]):
                    title_col = i
                elif any(kw in h for kw in ["standort", "ort", "location", "stadt", "city"]):
                    loc_col = i
            
            if title_col is None:
                title_col = 0  # Erste Spalte als Fallback
            
            for row in rows[1:]:
                cells = row.find_all(["td", "th"])
                if len(cells) <= title_col:
                    continue
                
                title_cell = cells[title_col]
                title_link = title_cell.find("a")
                title = title_cell.get_text(strip=True)
                link = ""
                
                if title_link:
                    title = title_link.get_text(strip=True) or title
                    link = normalize_url(self.source_url, title_link.get("href", ""))
                
                if not self._is_likely_job_title(title):
                    continue
                
                location = ""
                if loc_col is not None and len(cells) > loc_col:
                    location = cells[loc_col].get_text(strip=True)
                
                jobs.append(Job(
                    title=title,
                    employer=self.employer,
                    location=location,
                    link=link or self.source_url,
                    ats=self.ats,
                    extraction_method="dom_table",
                ))
        
        return jobs
    
    def _is_likely_job_title(self, text: str) -> bool:
        """Prüft ob ein Text wahrscheinlich ein Job-Titel ist."""
        if not text or len(text) < 4 or len(text) > 200:
            return False
        
        text_lower = text.lower().strip()
        
        # Definitiv kein Job-Titel: exakte Matches
        non_job_exact = [
            "impressum", "datenschutz", "kontakt", "about", "login",
            "menü", "menu", "home", "cookie", "agb", "terms", "privacy",
            "faq", "hilfe", "help", "suche", "search", "blog", "news",
            "mehr erfahren", "weiterlesen", "zurück", "back",
            "alle anzeigen", "filter", "sortieren", "bottom-left",
            "bottom-right", "top-left", "top-right",
            "news & events", "veranstaltungen & seminare",
            "jobs & karriere", "alle stellenangebote", "alle offenen stellenanzeigen",
            "view all locations", "careers", "karriere",
        ]
        if text_lower in non_job_exact:
            return False
        
        # Definitiv kein Job-Titel: Muster-basiert
        non_job_patterns = [
            r"^careers? in ",  # "Careers in Belgium", "Careers in France"
            r"^view all",  # "View All Locations"
            r"privacy (notice|policy)",
            r"tax strategy",
            r"scam communications",
            r"^learn more",
            r"^alle (karriere|offenen|stellen)",
            r"^einstieg bei ",
            r"^ihre chancen",
            r"^deine karriere",
            r"^cbh in der presse",
            r"^(unternehmen|infrastruktur|geistiges eigentum|immobilien).*&",  # Rechtsgebiete
            r"^(handels-|mergers|venture|banken|betriebliche|vorstände)",  # Praxisgruppen
            r"^(energy|financial|life sciences|mobility|retail|technology|urban)",  # Sektoren
            r"^(regulatory|artificial intelligence|online safety|knowledge notes)",  # Topics
            r"^(european electronic|the new deal|the built environment)",  # Topics
            r"^osborne clarke",  # Firmenname als Titel
            r"california privacy",
            r"^alumni",
            r"^(what our clients|what's on the horizon)",
            r"^(innovation contest|business services)$",  # Kategorien ohne Job-Kontext
            r"^wirtschaftsjuristen$",  # Kategorie
            r"^(startup-beratung|professional liability)$",
            r"\bpodcast\b",  # Blog/Podcast-Einträge
            r"\binterview\b.*\d{4}",  # "Interview ... 2022" = Blog
            r"^\".*\"\s*-\s",  # Zitate = Blog-Einträge
        ]
        if any(re.search(p, text_lower) for p in non_job_patterns):
            return False
        
        # Starke Job-Indikatoren (definitiv ein Job)
        # Basierend auf Analyse von 638 echten Stellentiteln aus Kanzleien
        job_indicators = [
            # === Gender-Kennzeichnungen (stärkster Indikator) ===
            r"\(m/w/d\)", r"\(w/m/d\)", r"\(m/f/d\)", r"\(m/f/x\)",
            r"\(all genders\)", r"\(d/m/w\)", r"\(gn\)", r"\(m/w/x\)",
            r"\(m/w\)", r"\(w/m\)",  # Ältere Variante ohne d
            r"m/w/d",  # Auch ohne Klammern (z.B. "Rechtsanwaltsfachangestellte m/w/d")
            # === Juristische Berufe ===
            r"rechtsanwalt", r"rechtsanwält", r"\banwalt", r"\banwält",
            r"rechtsanwalts-", r"fachanwalt", r"fachanwält",
            r"volljurist", r"syndikus", r"jurist",
            r"\bnotar", r"notariats",
            r"patentanwalt", r"patentanwält", r"patentingenieur",
            # === Fachangestellte / Assistenz ===
            r"fachangestellte", r"fachkraft", r"rechtsfachwirt",
            r"\bparalegal\b", r"\breno[s]?\b",
            r"sekretär", r"\bassistenz\b", r"\bassistent", r"teamassist",
            r"empfang", r"bürokraft", r"bürofach", r"bürokauf",
            r"schreibkraft", r"office.?manager",
            r"kanzleiassist",
            # === Steuer / WP / Buchhaltung ===
            r"steuer", r"wirtschaftsprüf", r"prüfungsassist", r"prüfungsleiter",
            r"buchhalter", r"buchhaltung", r"bilanzbuch",
            r"lohnbuch", r"lohnsach", r"lohnfach", r"payroll",
            r"finanzbuch", r"finanzwirt",
            # === Nachwuchs / Ausbildung ===
            r"referendar", r"referendarin",
            r"praktikant", r"praktikum", r"praktika\b",
            r"werkstudent", r"werkstudentin",
            r"\btrainee", r"\bazubi", r"auszubildende",
            r"ausbildung", r"berufsausbildung", r"berufseinsteiger", r"berufsanfänger",
            r"duales studium", r"studiengang",
            r"wissenschaftliche", r"studentische",
            r"law student", r"research assistant",
            # === Management / Consulting ===
            r"\bmanager\b", r"\bconsultant\b", r"\bcoordinator\b",
            r"unternehmensberater",
            # === IT / Tech ===
            r"\bdeveloper\b", r"\bengineer\b", r"\banalyst\b",
            r"it-administ", r"it-mitarbeiter", r"it-system", r"fachinformatiker",
            # === Sonstige häufige Titel ===
            r"\bberater\b", r"sachbearbeiter", r"sachbearbeitung",
            r"mitarbeiter\b", r"\bmitarbeit\b",
            r"initiativbewerbung", r"quereinsteiger",
            r"insolvenzsach", r"insolvenzabwickl", r"insolvenzbuch",
            r"fremdsprachenkorrespondent",
            r"reinigungskräfte", r"servicekraft",
            r"kauffrau", r"kaufmann", r"kaufleute", r"kaufmännisch",
            r"diplom-jurist", r"diplom-finanzwirt",
            r"\btalent pool\b",
            # === Programm-basierte Stellen ===
            r"programm.*(praktik|summer|winter)",
            r"(lift off|insight).*\d{4}",
            # === Englische Jobtitel (internationale Kanzleien) ===
            r"\blawyer[s]?\b", r"\battorney[s]?\b", r"\blateral\b",
            r"\breceptionist\b", r"\baccountant\b",
            r"\bprofessionals\b",  # "Business Professionals"
        ]
        if any(re.search(p, text_lower) for p in job_indicators):
            return True
        
        # Schwache Indikatoren: Nur akzeptieren wenn zusätzlicher Job-Kontext vorhanden
        weak_indicators = [
            r"\bassociate\b", r"\bcounsel\b", r"\bpartner\b",
            r"\bsenior\b", r"\bjunior\b",
        ]
        if any(re.search(p, text_lower) for p in weak_indicators):
            # Akzeptieren wenn es nach einem Job klingt
            if re.search(r"\(m/w|m/f|stelle|position|bewerbung|senior |junior ", text_lower):
                return True
            # Oder wenn es ein zusammengesetzter Titel ist (z.B. "Senior Associate")
            if re.search(r"(senior|junior)\s+(associate|counsel|manager|consultant)", text_lower):
                return True
        
        # Einzelwort-Berufsbezeichnungen (ohne m/w/d, aber trotzdem valide)
        # Diese kommen häufig vor bei Kanzleien die keine Gender-Kennzeichnung nutzen
        standalone_jobs = [
            r"^rechtsanwaltsfachangestellte/?r?$",
            r"^rechtsanwaltsfachangestellte:r$",
            r"^notarfachangestellte/?r?$",
            r"^steuerfachangestellte/?r?$",
            r"^steuerfachwirt/?in$",
            r"^steuerfachwirt:in$",
            r"^steuerberater/?in$",
            r"^steuerberater:in(nen)?$",
            r"^bilanzbuchhalter/?in$",
            r"^bilanzbuchhalter:in$",
            r"^finanzbuchhalter/?in$",
            r"^lohnbuchhalter/?in$",
            r"^rechtsfachwirt/?in$",
            r"^volljurist:in$",
            r"^rechtsanwält:in$",
            r"^anwalt:in$", r"^anwältin/anwalt$",
            r"^referendar/?in$", r"^referendar:in(nen)?$",
            r"^werkstudent/?in$", r"^werkstudent:in$",
            r"^praktikant/?in$", r"^praktikant:in(nen)?$",
            r"^paralegal$",
            r"^teamassistenz$",
            r"^referendare$", r"^referendarinnen$",
            r"^auszubildende/?r?$",
            r"^ausbildung$", r"^berufsausbildung$",
            r"^referendariat$", r"^referendarausbildung$",
            r"^praktikum$", r"^praktika$",
        ]
        if any(re.search(p, text_lower) for p in standalone_jobs):
            return True
        
        # KEIN generischer Fallback!
        # Der alte Code akzeptierte alles mit Großbuchstaben und >10 Zeichen.
        # Das führte zu massiven False Positives (Rechtsgebiete, Sektoren, etc.)
        return False
    
    def _find_nearby_location(self, element) -> str:
        """Sucht den Standort in der Nähe eines Elements."""
        parent = element.parent
        if not parent:
            return ""
        
        # Suche in Geschwister-Elementen
        for sibling in parent.find_all(class_=re.compile(r"location|city|standort|ort", re.I)):
            text = sibling.get_text(strip=True)
            if text and len(text) < 100:
                return text
        
        # Suche in Nachbar-Spans/Divs
        for tag in parent.find_all(["span", "div", "p", "small"]):
            text = tag.get_text(strip=True)
            if text and len(text) < 50:
                # Prüfe ob es wie ein Standort aussieht
                if any(ind in text.lower() for ind in config.german_indicators[:50]):
                    return text
        
        return ""


# ===================== JSON API PARSER =====================
class JSONAPIParser:
    """Parst JSON-Responses von Karriereseiten."""
    
    def __init__(self, employer: str, source_url: str, ats: str):
        self.employer = employer
        self.source_url = source_url
        self.ats = ats
    
    def parse(self, json_responses: List[str]) -> Tuple[List[Job], int]:
        """Parst alle JSON-Responses und extrahiert Jobs."""
        all_jobs = []
        
        for resp_text in json_responses:
            data = try_parse_json(resp_text)
            if not data:
                continue
            
            jobs = self._extract_from_data(data)
            all_jobs.extend(jobs)
        
        # Deduplizieren und filtern
        german_jobs = []
        filtered = 0
        seen = set()
        
        for job in all_jobs:
            key = (job.title.lower().strip(), job.location.lower().strip())
            if key in seen:
                continue
            seen.add(key)
            if config.is_german_location(job.location):
                german_jobs.append(job)
            else:
                filtered += 1
        
        return german_jobs, filtered
    
    def _extract_from_data(self, data: Any, depth: int = 0) -> List[Job]:
        """Rekursive Extraktion von Jobs aus JSON-Daten."""
        if depth > 5:
            return []
        
        jobs = []
        
        if isinstance(data, list):
            # Prüfe ob es eine Liste von Job-Objekten ist
            if data and isinstance(data[0], dict):
                if self._looks_like_job_list(data):
                    for item in data:
                        job = self._parse_job_object(item)
                        if job:
                            jobs.append(job)
                    return jobs
            # Rekursiv in Listen suchen
            for item in data:
                jobs.extend(self._extract_from_data(item, depth + 1))
        
        elif isinstance(data, dict):
            # Bekannte Job-Array-Keys
            job_keys = [
                "jobs", "jobPostings", "positions", "postings", "results",
                "openings", "vacancies", "offers", "listings", "items",
                "data", "content", "searchResults", "jobResults",
                "stellenangebote", "stellen",
            ]
            
            for key in job_keys:
                if key in data and isinstance(data[key], list):
                    sub_jobs = self._extract_from_data(data[key], depth + 1)
                    if sub_jobs:
                        jobs.extend(sub_jobs)
                        return jobs
            
            # Einzelnes Job-Objekt?
            job = self._parse_job_object(data)
            if job:
                return [job]
            
            # Rekursiv in verschachtelten Dicts suchen
            for key, value in data.items():
                if isinstance(value, (dict, list)):
                    jobs.extend(self._extract_from_data(value, depth + 1))
        
        return jobs
    
    def _looks_like_job_list(self, data: list) -> bool:
        """Prüft ob eine Liste wie eine Job-Liste aussieht."""
        if not data:
            return False
        sample = data[0]
        if not isinstance(sample, dict):
            return False
        
        job_fields = ["title", "name", "text", "position", "jobTitle", "bezeichnung", "stellentitel"]
        return any(f in sample for f in job_fields)
    
    def _parse_job_object(self, obj: dict) -> Optional[Job]:
        """Parst ein einzelnes Job-Objekt."""
        if not isinstance(obj, dict):
            return None
        
        # Titel extrahieren
        title_keys = ["title", "name", "text", "position", "jobTitle",
                      "displayTitle", "positionTitle", "job_title",
                      "stellentitel", "bezeichnung", "headline"]
        title = ""
        for key in title_keys:
            if key in obj and isinstance(obj[key], str) and obj[key].strip():
                title = obj[key].strip()
                break
        
        if not title or len(title) < 3 or len(title) > 200:
            return None
        
        # Nicht-Job-Titel filtern
        title_lower = title.lower()
        if title_lower in ["home", "impressum", "datenschutz", "kontakt", "about", "login"]:
            return None
        
        # Location
        loc_keys = ["location", "locationsText", "city", "office", "standort", "ort", "locationName"]
        location = ""
        for key in loc_keys:
            val = obj.get(key)
            if isinstance(val, str) and val.strip():
                location = val.strip()
                break
            elif isinstance(val, dict):
                location = val.get("name", val.get("city", val.get("label", "")))
                break
            elif isinstance(val, list) and val:
                first = val[0]
                location = first.get("name", str(first)) if isinstance(first, dict) else str(first)
                break
        
        # Link
        link_keys = ["url", "absolute_url", "hostedUrl", "apply_url", "link", "href", "careers_url"]
        link = ""
        for key in link_keys:
            if key in obj and isinstance(obj[key], str) and obj[key].startswith("http"):
                link = obj[key]
                break
        
        # Datum
        date_keys = ["date", "datePosted", "published_at", "created_at", "updated_at", "createdAt"]
        job_date = ""
        for key in date_keys:
            if key in obj:
                val = obj[key]
                if isinstance(val, str) and val:
                    job_date = val[:10]
                    break
                elif isinstance(val, (int, float)):
                    try:
                        job_date = datetime.fromtimestamp(val / 1000 if val > 1e12 else val).strftime("%Y-%m-%d")
                    except Exception:
                        pass
                    break
        
        return Job(
            title=title,
            employer=self.employer,
            location=location,
            date=job_date,
            link=link or self.source_url,
            ats=self.ats,
            extraction_method="json_api",
        )


# ===================== LLM FALLBACK =====================
class LLMExtractor:
    """Nutzt Gemini 3 Flash als Fallback für schwierige Seiten."""
    
    def __init__(self):
        if HAS_OPENAI and GEMINI_API_KEY:
            self.client = OpenAI(
                api_key=GEMINI_API_KEY,
                base_url=GEMINI_BASE_URL,
            )
        elif HAS_OPENAI and os.environ.get("OPENAI_API_KEY"):
            # Fallback: Standard OpenAI-Konfiguration
            self.client = OpenAI()
        else:
            self.client = None
    
    def extract(self, html: str, company: Company) -> Tuple[List[Job], int]:
        """Extrahiert Jobs via LLM-Analyse."""
        if not self.client:
            return [], 0
        
        # HTML bereinigen
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "aside"]):
            tag.decompose()
        
        # Links sammeln für Kontext
        links_text = ""
        links = soup.find_all("a", href=True)
        job_links = []
        for link in links:
            href = link.get("href", "")
            text = link.get_text(strip=True)
            if text and len(text) > 3 and any(kw in href.lower() for kw in ["job", "stelle", "career", "position", "vacancy"]):
                job_links.append(f"- {text} → {href}")
        if job_links:
            links_text = "\n\nGefundene Job-Links:\n" + "\n".join(job_links[:50])
        
        # Text extrahieren
        text = soup.get_text("\n", strip=True)
        text = re.sub(r"\n{3,}", "\n\n", text)
        
        if not text.strip() and not links_text:
            return [], 0
        
        # Chunks erstellen
        full_text = text[:config.chunk_chars] + links_text
        
        try:
            jobs = self._call_llm(full_text, company)
            
            # Filtern
            german_jobs = []
            filtered = 0
            for job in jobs:
                if config.is_german_location(job.location):
                    german_jobs.append(job)
                else:
                    filtered += 1
            
            return german_jobs, filtered
        except Exception as e:
            logger.debug(f"  LLM-Fehler für {company.name}: {e}")
            return [], 0
    
    def _call_llm(self, text: str, company: Company) -> List[Job]:
        """Ruft das LLM auf und parst die Antwort."""
        system_prompt = """Du bist ein Experte für die Extraktion von Stellenanzeigen aus Karriereseiten von Kanzleien und Rechtsanwaltskanzleien in Deutschland.

Deine Aufgabe: Extrahiere ALLE tatsächlichen Stellenanzeigen/offenen Positionen aus dem gegebenen Text.

Typische Jobtitel in Kanzleien (enthalten fast immer "(m/w/d)" oder ähnliche Gender-Kennzeichnungen):
- Rechtsanwalt/Rechtsanwältin (m/w/d), Partner, Associate, Counsel, Of Counsel
- Rechtsanwaltsfachangestellte/r (ReFa), Rechtsfachwirt/in
- Notar/in, Notarfachangestellte/r
- Steuerfachangestellte/r, Steuerberater/in, Wirtschaftsprüfer/in
- Referendar/in, Praktikant/in, Werkstudent/in, Wissenschaftliche/r Mitarbeiter/in
- Sekretär/in, Partnerassistent/in, Office Manager, Assistenz
- Syndikusrechtsanwalt/-anwältin, Volljurist/in
- IT-Administrator, Marketing Manager, HR Manager, Sachbearbeiter/in
- Auszubildende/r, Duales Studium

STRENGE Regeln:
1. Gib NUR tatsächliche Stellenanzeigen zurück - das sind konkrete offene Positionen, auf die man sich bewerben kann
2. KEINE Rechtsgebiete, Praxisgruppen, Sektoren oder Fachbereiche (z.B. "Real Estate", "Corporate/M&A", "Arbeitsrecht")
3. KEINE Navigations-Elemente, Menüpunkte, Footer-Links, Kategorien
4. KEINE Blog-Einträge, News, Podcasts, Interviews, Veranstaltungen
5. KEINE Personennamen (Anwaltsprofile)
6. KEINE generischen Links wie "Mehr erfahren", "Alle Stellen", "Karriere"
7. Ein echter Jobtitel enthält typischerweise eine Berufsbezeichnung UND oft (m/w/d)
8. Wenn keine echten Stellen gefunden werden, gib ein leeres Array zurück
9. Standort: Wenn nicht angegeben, leer lassen
10. Datum: Wenn nicht angegeben, leer lassen
11. Link: Wenn ein spezifischer Job-Link vorhanden ist, diesen verwenden

Antworte AUSSCHLIESSLICH mit validem JSON im Format:
{"jobs": [{"title": "...", "location": "...", "date": "YYYY-MM-DD", "link": "..."}]}"""

        user_prompt = f"Kanzlei: {company.name}\nKarriere-URL: {company.url}\n\nSeiteninhalt:\n{text}"
        
        response = self.client.chat.completions.create(
            model=config.llm_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.0,
            max_tokens=config.llm_max_tokens,
        )
        
        content = response.choices[0].message.content.strip()
        # Markdown-Code-Blöcke entfernen
        content = re.sub(r"^\s*```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```\s*$", "", content)
        
        try:
            data = json.loads(content)
            jobs = []
            for j in data.get("jobs", []):
                title = j.get("title", "").strip()
                if title and len(title) >= 4:
                    jobs.append(Job(
                        title=title,
                        employer=company.name,
                        location=j.get("location", "").strip(),
                        date=j.get("date", "").strip(),
                        link=j.get("link", company.url).strip(),
                        ats=company.ats,
                        extraction_method="llm_fallback",
                    ))
            return jobs
        except json.JSONDecodeError:
            return []


# ===================== BROWSER MANAGER =====================
class BrowserScraper:
    """Browser-basiertes Scraping mit Playwright."""
    
    def __init__(self):
        self.json_responses = []
    
    def scrape(self, company: Company) -> Tuple[str, List[str]]:
        """Scrapt eine Seite mit dem Browser. Gibt (html, json_responses) zurück."""
        if not HAS_PLAYWRIGHT:
            # Fallback: Einfacher HTTP-Request
            return self._simple_request(company.url)
        
        self.json_responses = []
        
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    viewport={"width": 1440, "height": 900},
                    extra_http_headers={"Accept-Language": "de-DE,de;q=0.9"}
                )
                
                # Ressourcen sparen: Bilder, Fonts, Media blockieren
                context.route("**/*", lambda route: route.abort() 
                    if route.request.resource_type in ["image", "font", "media", "stylesheet"]
                    else route.continue_())
                
                page = context.new_page()
                
                # JSON-Responses abfangen
                def on_response(response):
                    try:
                        ct = response.headers.get("content-type", "").lower()
                        if "json" in ct or "xml" in ct:
                            body = response.body()
                            if body and len(body) <= 5 * 1024 * 1024:
                                text = body.decode("utf-8", errors="ignore")
                                if "{" in text or "[" in text or "<position" in text.lower():
                                    self.json_responses.append(text)
                    except Exception:
                        pass
                
                page.on("response", on_response)
                
                # Seite laden
                page.goto(company.url, wait_until="domcontentloaded", timeout=config.base_timeout)
                time.sleep(2)
                
                # Cookie-Banner schließen
                self._close_cookies(page)
                
                # Auf dynamische Inhalte warten
                time.sleep(1)
                
                # "Mehr laden" / Paginierung
                self._handle_load_more(page)
                
                # Iframe-Check
                iframe_url = self._check_iframes(page)
                if iframe_url:
                    # Iframe-URL als zusätzliche Quelle
                    try:
                        page.goto(iframe_url, wait_until="domcontentloaded", timeout=config.base_timeout)
                        time.sleep(2)
                    except Exception:
                        pass
                
                html = page.content()
                json_responses = self.json_responses.copy()
                
                context.close()
                browser.close()
                
                return html, json_responses
                
        except Exception as e:
            logger.debug(f"  Browser-Fehler für {company.name}: {e}")
            return self._simple_request(company.url)
    
    def _simple_request(self, url: str) -> Tuple[str, List[str]]:
        """Fallback: Einfacher HTTP-Request ohne Browser."""
        try:
            resp = requests.get(
                url,
                timeout=15,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "de-DE,de;q=0.9",
                },
                allow_redirects=True,
            )
            resp.raise_for_status()
            return resp.text, []
        except Exception as e:
            logger.debug(f"  HTTP-Fehler für {url}: {e}")
            return "", []
    
    def _close_cookies(self, page):
        """Schließt Cookie-Banner."""
        cookie_selectors = [
            'button:has-text("Akzeptieren")',
            'button:has-text("Alle akzeptieren")',
            'button:has-text("Accept")',
            'button:has-text("Accept All")',
            'button:has-text("Zustimmen")',
            '[id*="cookie"] button',
            '[class*="cookie"] button',
            'button[data-testid*="accept"]',
        ]
        for selector in cookie_selectors:
            try:
                btn = page.locator(selector).first
                if btn.count() > 0 and btn.is_visible():
                    btn.click(timeout=2000)
                    time.sleep(0.5)
                    break
            except Exception:
                continue
    
    def _handle_load_more(self, page):
        """Klickt auf 'Mehr laden' Buttons und handhabt Paginierung."""
        load_more_selectors = [
            'button:has-text("Mehr")',
            'button:has-text("Weitere")',
            'button:has-text("Alle anzeigen")',
            'button:has-text("Load more")',
            'button:has-text("Show all")',
            'a:has-text("Alle Stellen")',
            'a:has-text("Alle Jobs")',
            '[class*="load-more"]',
            '[class*="show-more"]',
        ]
        
        for _ in range(5):  # Max 5 Klicks
            clicked = False
            for selector in load_more_selectors:
                try:
                    btn = page.locator(selector).first
                    if btn.count() > 0 and btn.is_visible():
                        btn.click(timeout=3000)
                        time.sleep(2)
                        clicked = True
                        break
                except Exception:
                    continue
            if not clicked:
                break
    
    def _check_iframes(self, page) -> Optional[str]:
        """Prüft ob relevante ATS-Iframes vorhanden sind."""
        try:
            iframes = page.query_selector_all("iframe")
            for iframe in iframes:
                src = iframe.get_attribute("src") or ""
                if not src:
                    continue
                src_lower = src.lower()
                for ats_name, sig in config.ats_signatures.items():
                    if any(p in src_lower for p in sig["patterns"]):
                        return src
        except Exception:
            pass
        return None


# ===================== HAUPT-SCRAPER =====================
class JobScraper:
    """Orchestriert den gesamten Scraping-Prozess."""
    
    def __init__(self):
        self.llm = LLMExtractor()
        self.browser = BrowserScraper()
    
    def scrape_company(self, company: Company) -> List[Job]:
        """Scrapt eine einzelne Kanzlei und gibt gefundene Jobs zurück."""
        logger.info(f"  Scraping: {company.name} ({company.url})")
        
        # Schritt 1: ATS erkennen
        ats = detect_ats(company.url)
        company.ats = ats
        
        # Schritt 2: Direkte API versuchen (schnellster Weg)
        if ats != "unknown":
            client = DirectATSClient(company.name, company.url, ats)
            jobs = client.fetch_jobs()
            if jobs:
                german_jobs = [j for j in jobs if config.is_german_location(j.location)]
                if german_jobs:
                    return self._apply_final_filter(german_jobs)
        
        # Schritt 3: Browser-basiertes Scraping
        html, json_responses = self.browser.scrape(company)
        
        if not html and not json_responses:
            return []
        
        # Schritt 4: JSON-API-Responses parsen
        if json_responses:
            parser = JSONAPIParser(company.name, company.url, ats)
            jobs, filtered = parser.parse(json_responses)
            if jobs:
                logger.info(f"    → {len(jobs)} Jobs via JSON-API ({filtered} gefiltert)")
                return self._apply_final_filter(jobs)
        
        # Schritt 5: DOM-Parsing
        if html:
            dom_parser = DOMParser(company.name, company.url, ats)
            jobs, filtered = dom_parser.extract(html)
            if jobs:
                logger.info(f"    → {len(jobs)} Jobs via DOM ({filtered} gefiltert)")
                return self._apply_final_filter(jobs)
        
        # Schritt 6: LLM-Fallback
        if html:
            jobs, filtered = self.llm.extract(html, company)
            if jobs:
                logger.info(f"    → {len(jobs)} Jobs via LLM ({filtered} gefiltert)")
                return self._apply_final_filter(jobs)
        
        logger.info(f"    → Keine Jobs gefunden für {company.name}")
        return []
    
    def _apply_final_filter(self, jobs: List[Job]) -> List[Job]:
        """Wendet den zentralen is_valid_job Filter auf alle extrahierten Jobs an."""
        valid = [j for j in jobs if is_valid_job(j)]
        rejected = len(jobs) - len(valid)
        if rejected > 0:
            logger.info(f"    → {rejected} False Positives herausgefiltert")
        return valid


# ===================== BATCH-VERARBEITUNG =====================
def load_companies(csv_path: str, batch_index: int = 0, batch_size: int = 0) -> List[Company]:
    """Lädt Kanzleien aus der target_firms_full.csv."""
    companies = []
    
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("Unternehmensname", "").strip()
            domain = row.get("Domainname des Unternehmens", "").strip()
            jobboard_url = row.get("Jobboard_URL", "").strip()
            
            if not name:
                continue
            
            # Bevorzuge Jobboard-URL, Fallback auf Domain + /karriere
            url = jobboard_url if jobboard_url else f"https://www.{domain}/karriere" if domain else ""
            
            if not url:
                continue
            
            companies.append(Company(
                name=name,
                url=url,
                domain=domain,
            ))
    
    # Batch-Aufteilung
    if batch_size > 0:
        start = batch_index * batch_size
        end = start + batch_size
        companies = companies[start:end]
    
    return companies


def load_existing_jobs(csv_path: str) -> Dict[str, set]:
    """Lädt bestehende Jobs für Deduplizierung."""
    existing = {}  # employer -> set of titles
    
    if not os.path.exists(csv_path):
        return existing
    
    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) >= 2:
                    employer = row[0].strip()
                    title = row[1].strip()
                    if employer not in existing:
                        existing[employer] = set()
                    existing[employer].add(title.lower())
    except Exception as e:
        logger.warning(f"Fehler beim Laden bestehender Jobs: {e}")
    
    return existing


def run_batch(batch_index: int, batch_size: int, target_csv: str, output_dir: str):
    """Führt einen Batch des Scraping-Prozesses aus."""
    logger.info(f"=== Batch {batch_index} gestartet (Size: {batch_size}) ===")
    
    companies = load_companies(target_csv, batch_index, batch_size)
    if not companies:
        logger.info(f"Batch {batch_index}: Keine Kanzleien zu verarbeiten")
        return
    
    logger.info(f"Batch {batch_index}: {len(companies)} Kanzleien geladen")
    
    scraper = JobScraper()
    all_jobs = []
    stats = {"success": 0, "no_jobs": 0, "error": 0}
    
    for i, company in enumerate(companies, 1):
        try:
            jobs = scraper.scrape_company(company)
            all_jobs.extend(jobs)
            
            if jobs:
                stats["success"] += 1
            else:
                stats["no_jobs"] += 1
            
            if i % 50 == 0:
                logger.info(f"  Fortschritt: {i}/{len(companies)} ({len(all_jobs)} Jobs bisher)")
            
        except Exception as e:
            stats["error"] += 1
            logger.error(f"  Fehler bei {company.name}: {e}")
        
        # Rate-Limiting
        time.sleep(0.5)
    
    # Ergebnisse speichern
    output_file = os.path.join(output_dir, f"batch_{batch_index}_results.csv")
    os.makedirs(output_dir, exist_ok=True)
    
    with open(output_file, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        for job in all_jobs:
            writer.writerow(job.to_csv_row())
    
    logger.info(f"=== Batch {batch_index} abgeschlossen ===")
    logger.info(f"  Jobs gefunden: {len(all_jobs)}")
    logger.info(f"  Erfolg: {stats['success']}, Keine Jobs: {stats['no_jobs']}, Fehler: {stats['error']}")
    logger.info(f"  Ergebnis: {output_file}")


def merge_results(output_dir: str, master_csv: str):
    """Merged alle Batch-Ergebnisse in die Master-CSV."""
    logger.info("=== Merge der Batch-Ergebnisse ===")
    
    # Neue Jobs aus allen Batches laden
    new_jobs = []
    batch_files = sorted(Path(output_dir).glob("batch_*_results.csv"))
    
    for batch_file in batch_files:
        with open(batch_file, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) >= 2 and row[0].strip() and row[1].strip():
                    new_jobs.append(row)
    
    logger.info(f"  {len(new_jobs)} neue Jobs aus {len(batch_files)} Batches")
    
    # Bestehende Jobs laden (für Deduplizierung)
    existing_keys = set()
    existing_rows = []
    
    if os.path.exists(master_csv):
        with open(master_csv, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) >= 2:
                    key = (row[0].strip().lower(), row[1].strip().lower())
                    existing_keys.add(key)
                    existing_rows.append(row)
    
    # Neue Jobs deduplizieren und hinzufügen
    added = 0
    today = date.today().isoformat()
    
    for row in new_jobs:
        # Sicherstellen, dass die Zeile 6 Spalten hat
        while len(row) < 6:
            row.append("")
        
        # Datum aktualisieren
        row[4] = today
        
        key = (row[0].strip().lower(), row[1].strip().lower())
        if key not in existing_keys:
            existing_rows.append(row)
            existing_keys.add(key)
            added += 1
    
    # Master-CSV schreiben
    with open(master_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        # Sortiert nach Kanzlei-Name
        existing_rows.sort(key=lambda r: r[0].lower() if r else "")
        writer.writerows(existing_rows)
    
    logger.info(f"  {added} neue Jobs hinzugefügt")
    logger.info(f"  Gesamt in Master-CSV: {len(existing_rows)}")
    
    # Statistik-Datei schreiben
    stats_file = os.path.join(output_dir, "merge_stats.json")
    with open(stats_file, "w") as f:
        json.dump({
            "date": today,
            "batches_processed": len(batch_files),
            "new_jobs_total": len(new_jobs),
            "new_jobs_added": added,
            "duplicates_skipped": len(new_jobs) - added,
            "master_total": len(existing_rows),
        }, f, indent=2)


# ===================== HAUPTPROGRAMM =====================
def main():
    """Haupteinstiegspunkt - wird von GitHub Actions aufgerufen."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Kanzlei Job-Scraper")
    parser.add_argument("--mode", choices=["batch", "merge", "full"], default="full",
                       help="Ausführungsmodus")
    parser.add_argument("--batch-index", type=int, default=0,
                       help="Batch-Index (0-basiert)")
    parser.add_argument("--batch-size", type=int, default=400,
                       help="Anzahl Kanzleien pro Batch")
    parser.add_argument("--target-csv", default="target_firms_full.csv",
                       help="Pfad zur Kanzlei-Liste")
    parser.add_argument("--master-csv", default="jobs_master.csv",
                       help="Pfad zur Master-CSV")
    parser.add_argument("--output-dir", default="batch_results",
                       help="Verzeichnis für Batch-Ergebnisse")
    
    args = parser.parse_args()
    
    if args.mode == "batch":
        run_batch(args.batch_index, args.batch_size, args.target_csv, args.output_dir)
    elif args.mode == "merge":
        merge_results(args.output_dir, args.master_csv)
    elif args.mode == "full":
        # Alles in einem Durchlauf (für lokale Tests)
        companies = load_companies(args.target_csv)
        logger.info(f"Voller Durchlauf: {len(companies)} Kanzleien")
        
        scraper = JobScraper()
        all_jobs = []
        
        for i, company in enumerate(companies, 1):
            try:
                jobs = scraper.scrape_company(company)
                all_jobs.extend(jobs)
                if i % 100 == 0:
                    logger.info(f"Fortschritt: {i}/{len(companies)} ({len(all_jobs)} Jobs)")
            except Exception as e:
                logger.error(f"Fehler bei {company.name}: {e}")
            time.sleep(0.5)
        
        # Ergebnisse speichern
        os.makedirs(args.output_dir, exist_ok=True)
        output_file = os.path.join(args.output_dir, "batch_0_results.csv")
        with open(output_file, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            for job in all_jobs:
                writer.writerow(job.to_csv_row())
        
        # Merge
        merge_results(args.output_dir, args.master_csv)


if __name__ == "__main__":
    main()

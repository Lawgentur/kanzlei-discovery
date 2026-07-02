from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from .models import Job, MASTER_COLUMNS


DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

REJECT_EXACT = {
    "about",
    "agb",
    "alle anzeigen",
    "alle jobs",
    "alle offenen stellenanzeigen",
    "alle stellenangebote",
    "anwälte",
    "anwaltwerden.de",
    "back",
    "blog",
    "careers",
    "cookie",
    "datenschutz",
    "filter",
    "home",
    "impressum",
    "initiativbewerbung",
    "jobs & karriere",
    "karriere",
    "kontakt",
    "learn more",
    "login",
    "mehr erfahren",
    "menu",
    "menü",
    "news",
    "news & events",
    "notariat",
    "privacy",
    "search",
    "suche",
    "view all locations",
    "weiterlesen",
    "zurück",
}

REJECT_PATTERNS = [
    r"^careers? in ",
    r"^einstieg bei ",
    r"^ihre chancen bei",
    r"^deine karriere",
    r"^view all",
    r"^what.*(clients|horizon)",
    r"privacy (notice|policy)",
    r"tax strategy",
    r"scam communications",
    r"\bpodcast\b",
    r"\binterview\b.*\d{4}",
    r"^\".*\"\s*-\s",
    r"^cbh in der presse",
    r"^©",
    r"copyright",
    r"^kontakt fragen",
    r"fachanwalt f.*miet- und wohnungseigentumsrecht",
    r"master of ms office",
    r"rechtsanwalt rechtsanw.*steuerberater in kooperation",
    r"rechtsanwaltsvergütungsgesetz",
    r"r.*ckforderung wertzuwachssteuer",
    r"sozialleistungs.*beratung und vertretung",
    r"sozialversicherungs.*beratung und vertretung",
    r"strafrecht.*rechtsanwalt als verteidiger",
    r"verordnung .*notarieller akten",
    r"notare in köln$",
    r"^search lawyers practices",
    r"^anw[aä]lte kompetenzen",
]

NON_JOB_URL_SEGMENTS = [
    "/about",
    "/alumni",
    "/blog",
    "/events",
    "/insights",
    "/lawyers",
    "/locations",
    "/news",
    "/people",
    "/privacy",
    "/rechtsgebiete",
    "/sectors",
    "/services",
    "/team",
]

JOB_HINTS = [
    "anwalt",
    "anwält",
    "assistant",
    "assistenz",
    "associate",
    "ausbildung",
    "berater",
    "buchhalter",
    "counsel",
    "fachangestellte",
    "jurist",
    "kanzleiassist",
    "lawyer",
    "manager",
    "mitarbeiter",
    "notar",
    "paralegal",
    "patent",
    "praktik",
    "recruit",
    "referendar",
    "reno",
    "rechts",
    "sekret",
    "steuer",
    "student",
    "trainee",
    "volljurist",
    "werkstudent",
    "wirtschaftsprüf",
]

JOB_MARKERS = [
    "(m/w/d)",
    "(w/m/d)",
    "(m/f/d)",
    "(m/f/x)",
    "(all genders)",
    "(gn)",
    "m/w/d",
    "w/m/d",
]

TRUSTED_BOARD_SOURCES = (
    "api:cms",
    "api:bdo-typesense",
    "api:dlapiper",
    "api:pwc-phenom",
    "browser:cms",
    "browser:wts",
    "dom:dlapiper",
    "dom:fieldfisher",
    "dom:winheller",
    "personio:eagle",
    "radancy:aoshearman",
    "reader:cms",
    "reader:skadden",
)


def repair_text(value: str) -> str:
    text = str(value or "").strip()
    if not any(marker in text for marker in ("Ã", "Â", "â", "ðŸ")):
        return text
    try:
        repaired = text.encode("latin1").decode("utf-8")
    except UnicodeError:
        return text
    return repaired if repaired else text


def normalize_url(base_url: str, href: str) -> str:
    href = (href or "").strip()
    if not href or href.startswith(("mailto:", "tel:", "javascript:")):
        return ""
    return href if href.startswith(("http://", "https://")) else urljoin(base_url, href)


def canonical_link(link: str) -> str:
    parsed = urlparse((link or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    kept_query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith(("utm_", "fbclid", "gclid", "msclkid"))
    ]
    path = parsed.path.rstrip("/") or "/"
    return urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            path,
            "",
            urlencode(kept_query),
            "",
        )
    )


def normalize_date(value: str, default: str) -> str:
    value = (value or "").strip()
    if DATE_RE.match(value):
        return value
    if "T" in value and DATE_RE.match(value.split("T", 1)[0]):
        return value.split("T", 1)[0]
    for fmt in ("%d.%m.%Y", "%Y/%m/%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass
    return default


def is_likely_job_title(title: str, link: str = "") -> bool:
    text = re.sub(r"\s+", " ", (title or "").strip())
    lower = text.lower()
    link_lower = (link or "").lower()

    if len(text) < 5 or len(text) > 220:
        return False
    if lower in REJECT_EXACT:
        return False
    if any(re.search(pattern, lower) for pattern in REJECT_PATTERNS):
        return False
    if any(segment in link_lower for segment in NON_JOB_URL_SEGMENTS):
        if not any(hint in link_lower for hint in ("/job", "/jobs", "/stelle", "/karriere", "/career", "/position")):
            return False
    if re.match(r"^[A-ZÄÖÜ][a-zäöüß]+\.?\s+[A-ZÄÖÜ]", text) and len(text.split()) <= 4:
        if not any(hint in lower for hint in JOB_HINTS):
            return False
    if any(marker in lower for marker in JOB_MARKERS):
        return True
    if any(hint in lower for hint in JOB_HINTS):
        return True
    if re.search(r"\b(senior|junior)\s+(associate|counsel|manager|consultant)\b", lower):
        return True
    return False


def normalize_job_row(row: dict[str, str], today: str) -> dict[str, str] | None:
    title = repair_text(row.get("Titel") or row.get("Jobtitel") or row.get("Job_Titel") or row.get("Job_Title") or "")
    link = canonical_link(row.get("Link") or row.get("Titel_url") or row.get("Job_URL") or "")
    firm = repair_text(row.get("Kanzlei") or row.get("Name_des_Unternehmens") or row.get("Company_Name") or "")
    city = repair_text(row.get("Stadt") or row.get("Location") or row.get("Standort") or "")
    source = repair_text(row.get("Quelle") or "")

    if not title or not firm or not link:
        return None
    if not is_likely_job_title(title, link) and not is_trusted_board_title(title, source):
        return None

    first_seen = normalize_date(row.get("first_seen") or row.get("Erstes_Funddatum") or row.get("Erscheinen") or row.get("Posted_Date") or "", today)
    last_seen = normalize_date(row.get("last_seen") or row.get("Zuletzt_Gesehen") or "", today)
    posting_date = normalize_date(row.get("posting_date") or row.get("Posted_Date") or row.get("Erscheinen") or first_seen, first_seen)
    imported_at = normalize_date(row.get("imported_at") or row.get("Upload am") or row.get("imported") or first_seen, first_seen)
    scraped_at = normalize_date(row.get("scraped_at") or row.get("Scraped am") or last_seen, last_seen)
    last_checked_at = normalize_date(row.get("last_checked_at") or row.get("checked_at") or last_seen, last_seen)
    status = repair_text(row.get("status") or "active").lower()
    if status not in {"active", "stale", "removed", "uncertain"}:
        status = "active"
    if source.lower() == "nan":
        source = ""

    return {
        "Titel": title,
        "Link": link,
        "Kanzlei": firm,
        "Stadt": city,
        "Quelle": source or "legacy",
        "first_seen": first_seen,
        "last_seen": last_seen,
        "posting_date": posting_date,
        "imported_at": imported_at,
        "scraped_at": scraped_at,
        "last_checked_at": last_checked_at,
        "source_url": canonical_link(row.get("source_url") or row.get("Source_URL") or link) or link,
        "status": status,
        "canonical_firm_id": row.get("canonical_firm_id") or canonical_firm_id(firm),
    }


def normalize_job(job: Job, today: str) -> dict[str, str] | None:
    return normalize_job_row(job.to_master_row(today), today)


def ensure_master_columns(row: dict[str, str]) -> dict[str, str]:
    return {column: (row.get(column) or "").strip() for column in MASTER_COLUMNS}


def canonical_firm_id(name: str) -> str:
    value = repair_text(name).casefold()
    value = value.replace("&", " und ")
    value = value.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    value = re.sub(
        r"\b(llp|mbb|partg|partgmbb|gmbh|ag|kg|ohg|partnerschaft|rechtsanwälte|rechtsanwaelte|rechtsanwalt|steuerberater|wirtschaftsprüfer|wirtschaftspruefer|notare|notar|kanzlei|law|legal|partner|partners)\b",
        " ",
        value,
    )
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value or "unknown"


def is_trusted_board_title(title: str, source: str) -> bool:
    if not is_trusted_board_source(source):
        return False
    text = re.sub(r"\s+", " ", (title or "").strip())
    lower = text.lower()
    if len(text) < 5 or len(text) > 220 or len(text.split()) > 24:
        return False
    if lower in REJECT_EXACT:
        return False
    if re.search(r"cookie|datenschutz|impressum|privacy|newsletter|login|registrieren", lower):
        return False
    return True


def is_trusted_board_source(source: str) -> bool:
    return any((source or "").startswith(prefix) for prefix in TRUSTED_BOARD_SOURCES)

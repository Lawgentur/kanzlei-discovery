from __future__ import annotations

import csv
import re
from pathlib import Path
from urllib.parse import urlparse

from .models import Firm
from .quality import canonical_firm_id, repair_text
from .storage import load_firms, read_csv_rows, write_csv_rows


NO_JOB_COLUMNS = [
    "Unternehmensname",
    "Domainname des Unternehmens",
    "Jobboard_URL",
    "diagnosis_status",
    "diagnosis_reason",
    "recommended_action",
    "job_count_name",
    "job_count_domain",
    "last_checked_at",
    "canonical_firm_id",
]


def write_no_job_diagnosis(target_file: str | Path, master_file: str | Path, output_file: str | Path, today: str) -> dict[str, int]:
    firms = load_firms(target_file)
    jobs = read_csv_rows(master_file)
    name_counts: dict[str, int] = {}
    domain_counts: dict[str, int] = {}

    for job in jobs:
        firm_id = job.get("canonical_firm_id") or canonical_firm_id(job.get("Kanzlei", ""))
        if firm_id:
            name_counts[firm_id] = name_counts.get(firm_id, 0) + 1
        host = host_domain(job.get("Link", ""))
        if host:
            domain_counts[host] = domain_counts.get(host, 0) + 1

    rows = []
    matched = 0
    for firm in firms:
        firm_id = canonical_firm_id(firm.name)
        name_hits = name_counts.get(firm_id, 0)
        domain_hits = sum(count for host, count in domain_counts.items() if domain_matches(firm.domain, host))
        if name_hits or domain_hits:
            matched += 1
            continue
        status, reason, action = diagnose_firm(firm)
        rows.append(
            {
                "Unternehmensname": firm.name,
                "Domainname des Unternehmens": firm.domain,
                "Jobboard_URL": firm.jobboard_url,
                "diagnosis_status": status,
                "diagnosis_reason": reason,
                "recommended_action": action,
                "job_count_name": str(name_hits),
                "job_count_domain": str(domain_hits),
                "last_checked_at": today,
                "canonical_firm_id": firm_id,
            }
        )

    write_csv_rows(output_file, rows, NO_JOB_COLUMNS)
    return {"targets": len(firms), "matched": matched, "no_jobs": len(rows)}


def diagnose_firm(firm: Firm) -> tuple[str, str, str]:
    if not firm.domain:
        return (
            "missing_domain",
            "Keine Domain in target_firms_full.csv vorhanden.",
            "Domain manuell ergänzen und danach Karriere-/Jobboard-URL suchen.",
        )
    if not firm.jobboard_url:
        return (
            "missing_jobboard_url",
            "Domain vorhanden, aber keine gecachte Jobboard_URL.",
            "Karriereseite entdecken und Jobboard_URL in target_firms_full.csv ergänzen.",
        )
    if looks_like_homepage(firm.jobboard_url, firm.domain):
        return (
            "jobboard_needs_review",
            "Jobboard_URL wirkt wie Startseite oder generische Domain, nicht wie konkrete Karriereseite.",
            "Karriere-/Stellenangebote-URL manuell prüfen und spezifischer speichern.",
        )
    return (
        "no_master_match",
        "Jobboard_URL vorhanden, aber kein Treffer in jobs_master.csv nach Kanzleiname oder Domain.",
        "Seite manuell prüfen: keine Jobs, Parser-Lücke, JS/Cookie-Problem oder spezielles ATS möglich.",
    )


def host_domain(url: str) -> str:
    try:
        host = (urlparse(url or "").hostname or "").casefold()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def domain_matches(target_domain: str, host: str) -> bool:
    target = (target_domain or "").casefold().strip()
    if target.startswith("www."):
        target = target[4:]
    return bool(target and host and (host == target or host.endswith("." + target)))


def looks_like_homepage(url: str, domain: str) -> bool:
    parsed = urlparse(url or "")
    host = host_domain(url)
    path = (parsed.path or "/").strip("/")
    generic_paths = {"", "#", "de", "de-de", "en", "en-us", "karriere", "career", "careers", "jobs"}
    if domain_matches(domain, host) and path.casefold() in generic_paths:
        return True
    return bool(re.match(r"^https?://(www\.)?[^/]+/?#?$", url or "", re.I))


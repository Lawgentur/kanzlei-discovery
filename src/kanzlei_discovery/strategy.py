from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import requests

from .ats import detect_ats
from .extractors import discover_jobboard_url, extract_dom_jobs, parse_embedded_json_jobs
from .models import Firm
from .quality import canonical_firm_id
from .special_adapters import identify_special_adapter
from .storage import load_firms, read_csv_rows, write_csv_rows


STRATEGY_COLUMNS = [
    "canonical_firm_id",
    "Unternehmensname",
    "Domainname des Unternehmens",
    "Jobboard_URL",
    "strategy",
    "adapter",
    "ats",
    "status",
    "reason",
    "http_status",
    "html_job_count",
    "json_job_count",
    "signals",
    "analyzed_at",
]


@dataclass(frozen=True)
class SiteStrategy:
    firm_id: str
    strategy: str
    adapter: str = ""
    ats: str = "unknown"
    status: str = "unknown"
    reason: str = ""
    jobboard_url: str = ""

    @classmethod
    def from_row(cls, row: dict[str, str]) -> "SiteStrategy":
        return cls(
            firm_id=row.get("canonical_firm_id", ""),
            strategy=row.get("strategy", ""),
            adapter=row.get("adapter", ""),
            ats=row.get("ats", "unknown") or "unknown",
            status=row.get("status", "unknown") or "unknown",
            reason=row.get("reason", ""),
            jobboard_url=row.get("Jobboard_URL", ""),
        )


def analyze_strategy_file(
    target_file: str | Path,
    output_file: str | Path,
    today: str,
    limit: int | None = None,
) -> dict[str, int]:
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 KanzleiDiscovery/0.1", "Accept-Language": "de-DE,de;q=0.9,en;q=0.5"})
    firms = load_firms(target_file)
    if limit:
        firms = firms[:limit]

    existing = {row.get("canonical_firm_id", ""): row for row in read_csv_rows(output_file)}
    rows: list[dict[str, str]] = []
    processed: set[str] = set()
    stats = {"analyzed": 0, "reused": 0, "errors": 0}

    for index, firm in enumerate(firms, start=1):
        firm_id = canonical_firm_id(firm.name)
        try:
            row = analyze_firm_strategy(session, firm, today)
            stats["analyzed"] += 1
        except requests.RequestException as exc:
            row = base_strategy_row(firm, firm.jobboard_url, today)
            row.update({"strategy": "llm_fallback", "status": "request_error", "reason": type(exc).__name__})
            stats["errors"] += 1
        except Exception as exc:
            row = base_strategy_row(firm, firm.jobboard_url, today)
            row.update({"strategy": "manual_review", "status": "analysis_error", "reason": type(exc).__name__})
            stats["errors"] += 1
        existing[firm_id] = row
        rows.append(row)
        processed.add(firm_id)
        if index % 50 == 0:
            write_csv_rows(output_file, rows + remaining_rows(existing, processed), STRATEGY_COLUMNS)
            print(f"STRATEGY_CHECKPOINT {index}/{len(firms)} errors={stats['errors']}")

    for firm_id, row in existing.items():
        if firm_id and firm_id not in processed:
            rows.append(row)
            stats["reused"] += 1

    write_csv_rows(output_file, rows, STRATEGY_COLUMNS)
    return stats


def remaining_rows(existing: dict[str, dict[str, str]], processed: set[str]) -> list[dict[str, str]]:
    return [row for firm_id, row in existing.items() if firm_id and firm_id not in processed]


def analyze_firm_strategy(session: requests.Session, firm: Firm, today: str) -> dict[str, str]:
    jobboard_url = discover_jobboard_url(session, firm)
    row = base_strategy_row(firm, jobboard_url, today)
    if not jobboard_url:
        row.update({"strategy": "manual_review", "status": "missing_jobboard_url", "reason": "Keine Jobboard_URL und keine Domain."})
        return row

    adapter = identify_special_adapter(firm, jobboard_url)
    ats = detect_ats(jobboard_url)
    row["adapter"] = adapter
    row["ats"] = ats

    if adapter:
        row.update(strategy_from_adapter(adapter))
        return row
    if ats in {"greenhouse", "lever", "personio", "recruitee"}:
        row.update({"strategy": "ats_api", "status": "ready", "reason": f"Direkter {ats}-ATS-Client verfügbar."})
        return row

    response = session.get(jobboard_url, timeout=25)
    row["http_status"] = str(response.status_code)
    response.raise_for_status()
    html = response.text or ""
    signals = detect_page_signals(html, response.url)
    row["signals"] = ",".join(signals)

    json_jobs = parse_embedded_json_jobs(html, firm, response.url)
    dom_jobs = extract_dom_jobs(html, firm, response.url)
    row["json_job_count"] = str(len(json_jobs))
    row["html_job_count"] = str(len(dom_jobs))

    if json_jobs:
        row.update({"strategy": "embedded_json", "status": "ready", "reason": "Eingebettete strukturierte Jobdaten gefunden."})
    elif dom_jobs:
        row.update({"strategy": "dom", "status": "ready", "reason": "Joblinks sind direkt im HTML sichtbar."})
    elif "js_app" in signals or "load_more" in signals or "pagination" in signals:
        row.update({"strategy": "playwright", "status": "needs_browser", "reason": "Seite wirkt JavaScript-/Pagination-getrieben."})
    elif "blocked" in signals:
        row.update({"strategy": "reader_or_llm", "status": "blocked", "reason": "Seite wirkt geblockt oder leer fuer normale Requests."})
    else:
        row.update({"strategy": "llm_fallback", "status": "fallback", "reason": "Keine Jobs im HTML/JSON erkannt."})
    return row


def load_strategy_cache(path: str | Path) -> dict[str, SiteStrategy]:
    return {row.get("canonical_firm_id", ""): SiteStrategy.from_row(row) for row in read_csv_rows(path) if row.get("canonical_firm_id")}


def strategy_for_firm(cache: dict[str, SiteStrategy], firm: Firm) -> SiteStrategy | None:
    return cache.get(canonical_firm_id(firm.name))


def base_strategy_row(firm: Firm, jobboard_url: str, today: str) -> dict[str, str]:
    return {
        "canonical_firm_id": canonical_firm_id(firm.name),
        "Unternehmensname": firm.name,
        "Domainname des Unternehmens": firm.domain,
        "Jobboard_URL": jobboard_url,
        "strategy": "",
        "adapter": "",
        "ats": "unknown",
        "status": "unknown",
        "reason": "",
        "http_status": "",
        "html_job_count": "0",
        "json_job_count": "0",
        "signals": "",
        "analyzed_at": today,
    }


def strategy_from_adapter(adapter: str) -> dict[str, str]:
    if adapter.startswith("skip:"):
        return {"strategy": "skip", "status": "intentional_skip", "reason": "Ziel wird bewusst nicht separat gescraped."}
    if adapter.startswith("api:") or adapter.startswith("radancy:") or adapter.startswith("personio:"):
        return {"strategy": "special_api", "status": "ready", "reason": f"Spezialadapter {adapter} erkannt."}
    if adapter.startswith("browser:"):
        return {"strategy": "playwright", "status": "ready", "reason": f"Browser-Adapter {adapter} erkannt."}
    if adapter.startswith("reader:"):
        return {"strategy": "reader_or_llm", "status": "ready", "reason": f"Reader-Adapter {adapter} erkannt."}
    return {"strategy": "special_dom", "status": "ready", "reason": f"Spezialadapter {adapter} erkannt."}


def detect_page_signals(html: str, url: str) -> list[str]:
    lower = (html or "").lower()
    signals: list[str] = []
    if "__next_data__" in lower:
        signals.append("next_data")
    if "__nuxt__" in lower or "_payload.json" in lower:
        signals.append("nuxt")
    if "application/ld+json" in lower:
        signals.append("json_ld")
    if re.search(r"mehr\s+(anzeigen|ergebnisse|laden)|load\s+more|show\s+more", lower):
        signals.append("load_more")
    if re.search(r"pagination|pager|seite\s+\d+|page=\d+", lower):
        signals.append("pagination")
    if re.search(r"cloudflare|captcha|access denied|forbidden|checking your browser", lower):
        signals.append("blocked")
    if re.search(r"react|vue|angular|webpack|vite|spa-root|app-root", lower) or len(re.sub(r"<[^>]+>", "", html or "").strip()) < 500:
        signals.append("js_app")
    host = urlparse(url or "").hostname or ""
    if host:
        signals.append(f"host:{host.lower()}")
    return dedupe(signals)


def dedupe(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result

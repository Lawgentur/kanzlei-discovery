from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import requests

from . import drive
from .extractors import DirectATSClient, discover_jobboard_url, extract_dom_jobs, extract_llm_jobs, parse_embedded_json_jobs
from .merge import merge_jobs, remove_stale
from .models import Firm, Job
from .quality import normalize_job_row
from .storage import load_firms, load_master, read_csv_rows, save_firms, save_master, write_csv_rows
from .models import MASTER_COLUMNS


@dataclass
class PipelineConfig:
    target_file: Path = Path("target_firms_full.csv")
    master_file: Path = Path("jobs_master.csv")
    public_export: Path = Path("media/jobs_master_public.csv")
    state_file: Path = Path("sync_state.json")
    days_until_deletion: int = 30
    scrape: bool = False
    sync_drive: bool = True
    limit: int | None = None
    llm_fallback: bool = False
    today: str = date.today().isoformat()


def run_pipeline(config: PipelineConfig) -> dict[str, int]:
    master = load_master(config.master_file, config.today)
    stats = {"new": 0, "updated": 0, "skipped": 0, "expired": 0, "scraped_firms": 0, "drive_files": 0}

    if config.sync_drive and drive.env_available():
        incoming_rows, processed_ids = drive.sync_drive_excels(config.state_file)
        incoming_jobs = rows_to_jobs(incoming_rows, config.today)
        master, drive_stats = merge_jobs(master, incoming_jobs, config.today)
        add_stats(stats, drive_stats)
        stats["drive_files"] = len(processed_ids)
        state = drive.load_state(config.state_file)
        state["last_sync"] = config.today
        drive.save_state(config.state_file, state)

    if config.scrape:
        firms = load_firms(config.target_file)
        if config.limit:
            firms = firms[: config.limit]
        scraped_jobs, updated_firms = scrape_firms(firms, config)
        master, scrape_stats = merge_jobs(master, scraped_jobs, config.today)
        add_stats(stats, scrape_stats)
        stats["scraped_firms"] = len(firms)
        if updated_firms:
            save_firms(config.target_file, updated_firms)

    master, expired = remove_stale(master, config.today, config.days_until_deletion)
    stats["expired"] = expired
    save_master(config.master_file, master)
    write_csv_rows(config.public_export, master, MASTER_COLUMNS)
    return stats


def sanitize_only(config: PipelineConfig) -> dict[str, int]:
    before_rows = len(read_csv_rows(config.master_file))
    master = load_master(config.master_file, config.today)
    save_master(config.master_file, master)
    write_csv_rows(config.public_export, master, MASTER_COLUMNS)
    firms = load_firms(config.target_file)
    save_firms(config.target_file, firms)
    return {"kept_jobs": len(master), "removed_jobs": max(before_rows - len(master), 0), "firms": len(firms)}


def rows_to_jobs(rows: list[dict[str, str]], today: str) -> list[Job]:
    jobs = []
    for row in rows:
        normalized = normalize_job_row(row, today)
        if normalized:
            jobs.append(
                Job(
                    title=normalized["Titel"],
                    link=normalized["Link"],
                    firm=normalized["Kanzlei"],
                    city=normalized["Stadt"],
                    source=normalized["Quelle"],
                    first_seen=normalized["first_seen"],
                    last_seen=normalized["last_seen"],
                )
            )
    return jobs


def scrape_firms(firms: list[Firm], config: PipelineConfig) -> tuple[list[Job], list[Firm]]:
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 KanzleiDiscovery/0.1", "Accept-Language": "de-DE,de;q=0.9,en;q=0.5"})
    ats_client = DirectATSClient(session=session)
    jobs: list[Job] = []
    updated_firms: list[Firm] = []

    for firm in firms:
        jobboard_url = discover_jobboard_url(session, firm)
        updated_firms.append(Firm(name=firm.name, domain=firm.domain, jobboard_url=jobboard_url or firm.jobboard_url))
        if not jobboard_url:
            continue

        firm_jobs = ats_client.fetch(firm, jobboard_url)
        if not firm_jobs:
            try:
                response = session.get(jobboard_url, timeout=25)
                response.raise_for_status()
            except requests.RequestException:
                continue
            firm_jobs = parse_embedded_json_jobs(response.text, firm, response.url)
            if not firm_jobs:
                firm_jobs = extract_dom_jobs(response.text, firm, response.url)
            if not firm_jobs and config.llm_fallback:
                firm_jobs = extract_llm_jobs(response.text, firm, response.url)
        jobs.extend(firm_jobs)

    return jobs, updated_firms


def add_stats(target: dict[str, int], incoming: dict[str, int]) -> None:
    for key, value in incoming.items():
        target[key] = target.get(key, 0) + value

from __future__ import annotations

import json
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
    checkpoint_file: Path = Path("state/scrape_checkpoint.json")
    checkpoint_interval: int = 50
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
        master, updated_firms, scrape_stats = scrape_firms(firms, master, config)
        add_stats(stats, scrape_stats)
        stats["scraped_firms"] = len(firms)
        if updated_firms and not config.limit:
            save_firms(config.target_file, updated_firms)

    # A limited scrape is a smoke test, not a complete crawl. Do not expire
    # global master rows from a partial sample.
    if config.scrape and config.limit:
        expired = 0
    else:
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


def scrape_firms(firms: list[Firm], master: list[dict[str, str]], config: PipelineConfig) -> tuple[list[dict[str, str]], list[Firm], dict[str, int]]:
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 KanzleiDiscovery/0.1", "Accept-Language": "de-DE,de;q=0.9,en;q=0.5"})
    ats_client = DirectATSClient(session=session)
    updated_firms: list[Firm] = list(firms)
    stats = {"new": 0, "updated": 0, "skipped": 0}
    checkpoint = load_scrape_checkpoint(config)
    start_index = checkpoint.get("next_index", 0) if should_resume_checkpoint(checkpoint, firms, config) else 0

    if start_index:
        print(f"RESUME_SCRAPE next_index={start_index} total={len(firms)}")

    for index in range(start_index, len(firms)):
        firm = firms[index]
        firm_jobs, updated_firm = scrape_one_firm(session, ats_client, firm, config)
        updated_firms[index] = updated_firm
        master, firm_stats = merge_jobs(master, firm_jobs, config.today)
        add_stats(stats, firm_stats)

        if should_write_checkpoint(index + 1, len(firms), config):
            save_scrape_outputs(master, updated_firms, config, next_index=index + 1, stats=stats)
            print(
                "CHECKPOINT "
                f"{index + 1}/{len(firms)} "
                f"new={stats['new']} updated={stats['updated']} skipped={stats['skipped']}"
            )

    save_scrape_outputs(master, updated_firms, config, next_index=len(firms), stats=stats, completed=True)
    return master, updated_firms, stats


def scrape_one_firm(session: requests.Session, ats_client: DirectATSClient, firm: Firm, config: PipelineConfig) -> tuple[list[Job], Firm]:
    jobboard_url = discover_jobboard_url(session, firm)
    updated_firm = Firm(name=firm.name, domain=firm.domain, jobboard_url=jobboard_url or firm.jobboard_url)
    if not jobboard_url:
        return [], updated_firm

    firm_jobs = ats_client.fetch(firm, jobboard_url)
    if firm_jobs:
        return firm_jobs, updated_firm

    try:
        response = session.get(jobboard_url, timeout=25)
        response.raise_for_status()
    except requests.RequestException:
        return [], updated_firm

    firm_jobs = parse_embedded_json_jobs(response.text, firm, response.url)
    if firm_jobs:
        return firm_jobs, updated_firm
    firm_jobs = extract_dom_jobs(response.text, firm, response.url)
    if firm_jobs:
        return firm_jobs, updated_firm
    if config.llm_fallback:
        return extract_llm_jobs(response.text, firm, response.url), updated_firm
    return [], updated_firm


def should_write_checkpoint(next_index: int, total: int, config: PipelineConfig) -> bool:
    if config.limit:
        return next_index == total
    interval = max(config.checkpoint_interval, 1)
    return next_index % interval == 0 or next_index == total


def save_scrape_outputs(
    master: list[dict[str, str]],
    firms: list[Firm],
    config: PipelineConfig,
    next_index: int,
    stats: dict[str, int],
    completed: bool = False,
) -> None:
    save_master(config.master_file, master)
    write_csv_rows(config.public_export, master, MASTER_COLUMNS)
    if not config.limit:
        save_firms(config.target_file, firms)
    save_scrape_checkpoint(config, next_index, len(firms), stats, completed)


def load_scrape_checkpoint(config: PipelineConfig) -> dict:
    if config.limit or not config.checkpoint_file.exists():
        return {}
    try:
        return json.loads(config.checkpoint_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def should_resume_checkpoint(checkpoint: dict, firms: list[Firm], config: PipelineConfig) -> bool:
    if config.limit or not checkpoint or checkpoint.get("completed"):
        return False
    return (
        checkpoint.get("target_file") == str(config.target_file)
        and checkpoint.get("master_file") == str(config.master_file)
        and checkpoint.get("total_firms") == len(firms)
        and 0 < int(checkpoint.get("next_index", 0)) < len(firms)
    )


def save_scrape_checkpoint(config: PipelineConfig, next_index: int, total_firms: int, stats: dict[str, int], completed: bool = False) -> None:
    config.checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "target_file": str(config.target_file),
        "master_file": str(config.master_file),
        "public_export": str(config.public_export),
        "next_index": next_index,
        "total_firms": total_firms,
        "today": config.today,
        "completed": completed,
        "stats": stats,
    }
    config.checkpoint_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def add_stats(target: dict[str, int], incoming: dict[str, int]) -> None:
    for key, value in incoming.items():
        target[key] = target.get(key, 0) + value

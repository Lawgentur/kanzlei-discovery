from __future__ import annotations

from datetime import datetime, timedelta

from .models import Job
from .quality import is_trusted_board_source, normalize_job


def merge_jobs(master_rows: list[dict[str, str]], incoming: list[Job], today: str) -> tuple[list[dict[str, str]], dict[str, int]]:
    stats = {"new": 0, "updated": 0, "skipped": 0}
    by_link = {row["Link"].lower(): idx for idx, row in enumerate(master_rows) if row.get("Link")}
    by_fallback = {
        fallback_key(row): idx
        for idx, row in enumerate(master_rows)
        if fallback_key(row)
    }

    for job in incoming:
        row = normalize_job(job, today)
        if not row:
            stats["skipped"] += 1
            continue
        idx = by_link.get(row["Link"].lower())
        use_fallback = not is_trusted_board_source(row.get("Quelle", ""))
        if idx is None and use_fallback:
            idx = by_fallback.get(fallback_key(row))
        if idx is None:
            master_rows.append(row)
            by_link[row["Link"].lower()] = len(master_rows) - 1
            if use_fallback:
                by_fallback[fallback_key(row)] = len(master_rows) - 1
            stats["new"] += 1
        else:
            existing = master_rows[idx]
            existing["last_seen"] = today
            existing["last_checked_at"] = today
            existing["scraped_at"] = today
            existing["status"] = "active"
            for field in ("Titel", "Kanzlei", "Stadt", "Quelle", "source_url", "posting_date", "canonical_firm_id"):
                if row.get(field):
                    existing[field] = row[field]
            stats["updated"] += 1

    return master_rows, stats


def remove_stale(master_rows: list[dict[str, str]], today: str, days_until_deletion: int) -> tuple[list[dict[str, str]], int]:
    cutoff = datetime.fromisoformat(today) - timedelta(days=days_until_deletion)
    kept = []
    deleted = 0
    for row in master_rows:
        try:
            last_seen = datetime.fromisoformat(row.get("last_seen", today))
        except ValueError:
            last_seen = datetime.fromisoformat(today)
        if last_seen >= cutoff:
            kept.append(row)
        else:
            deleted += 1
    return kept, deleted


def fallback_key(row: dict[str, str]) -> str:
    parts = [row.get("Kanzlei", "").lower().strip(), row.get("Titel", "").lower().strip(), row.get("Stadt", "").lower().strip()]
    return "|".join(parts) if parts[0] and parts[1] else ""

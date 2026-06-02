from __future__ import annotations

import csv
from pathlib import Path

from .models import FIRM_COLUMNS, Firm, MASTER_COLUMNS
from .quality import ensure_master_columns, normalize_job_row, repair_text


def read_csv_rows(path: str | Path) -> list[dict[str, str]]:
    path = Path(path)
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv_rows(path: str | Path, rows: list[dict[str, str]], columns: list[str]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows([{column: row.get(column, "") for column in columns} for row in rows])


def load_master(path: str | Path, today: str) -> list[dict[str, str]]:
    normalized = []
    seen = set()
    for row in read_csv_rows(path):
        clean = normalize_job_row(row, today)
        if not clean:
            continue
        key = clean["Link"].lower() or "|".join([clean["Kanzlei"].lower(), clean["Titel"].lower(), clean["Stadt"].lower()])
        if key in seen:
            continue
        seen.add(key)
        normalized.append(ensure_master_columns(clean))
    return normalized


def save_master(path: str | Path, rows: list[dict[str, str]]) -> None:
    write_csv_rows(path, rows, MASTER_COLUMNS)


def load_firms(path: str | Path) -> list[Firm]:
    rows = read_csv_rows(path)
    firms = []
    seen = set()
    for row in rows:
        firm = Firm.from_row(row)
        firm = Firm(name=repair_text(firm.name), domain=firm.domain.strip(), jobboard_url=firm.jobboard_url.strip())
        key = (firm.domain or firm.name).strip().lower()
        if not firm.name or key in seen:
            continue
        seen.add(key)
        firms.append(firm)
    return firms


def save_firms(path: str | Path, firms: list[Firm]) -> None:
    rows = [
        {
            "Unternehmensname": firm.name,
            "Domainname des Unternehmens": firm.domain,
            "Jobboard_URL": firm.jobboard_url,
        }
        for firm in firms
    ]
    write_csv_rows(path, rows, FIRM_COLUMNS)

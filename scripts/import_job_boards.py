from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from datetime import date
from pathlib import Path

import pandas as pd

from kanzlei_discovery.diagnostics import write_no_job_diagnosis
from kanzlei_discovery.merge import merge_jobs
from kanzlei_discovery.models import MASTER_COLUMNS, Job
from kanzlei_discovery.storage import load_master, save_master, write_csv_rows


REPORT_COLUMNS = [
    "file",
    "source",
    "input_rows",
    "new",
    "updated",
    "skipped",
    "master_before",
    "master_after",
]


SOURCE_COLUMNS = {
    "stepstone": {"Job_Titel", "Titel_url", "Name_des_Unternehmens", "Standort", "Erscheinen"},
    "indeed": {"Job_Title", "Job_URL", "Company_Name", "Location", "Posted_Date"},
}
SUPPORTED_IMPORT_SUFFIXES = {".csv", ".xlsx"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Import new Indeed and Stepstone CSV/Excel exports into jobs_master.csv.")
    parser.add_argument("--imports-dir", default="IMPORTS")
    parser.add_argument("--master-file", default="jobs_master.csv")
    parser.add_argument("--public-export", default="media/jobs_master_public.csv")
    parser.add_argument("--state-file", default="state/imported_board_files.json")
    parser.add_argument("--report-file", default="")
    parser.add_argument("--no-job-report", default="reports/kanzleien_ohne_jobs_diagnose.csv")
    parser.add_argument("--target-file", default="target_firms_full.csv")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument(
        "--stable-for-seconds",
        type=int,
        default=0,
        help="Only import files whose size and modification time stay unchanged for this many seconds.",
    )
    parser.add_argument("--mark-existing", action="store_true", help="Record matching files as already processed without importing them.")
    args = parser.parse_args()

    imports_dir = Path(args.imports_dir)
    report_file = Path(args.report_file) if args.report_file else Path(f"reports/import_report_{args.date}.csv")
    state_file = Path(args.state_file)
    state = load_state(state_file)

    if args.mark_existing:
        marked = 0
        for source, path in discover_import_files(imports_dir):
            fingerprint = file_fingerprint(path)
            if fingerprint in state.get("files", {}):
                continue
            state.setdefault("files", {})[fingerprint] = {
                "path": str(path),
                "source": source,
                "imported_at": args.date,
                "input_rows": 0,
                "new": 0,
                "updated": 0,
                "skipped": 0,
                "marked_existing": True,
            }
            marked += 1
        save_state(state_file, state)
        print(f"BOARD_IMPORTS marked_existing={marked}")
        return 0

    master = load_master(args.master_file, args.date)
    report_rows = []
    imported_files = 0

    import_files = stable_import_files(discover_import_files(imports_dir), args.stable_for_seconds)
    for source, path in import_files:
        fingerprint = file_fingerprint(path)
        if fingerprint in state.get("files", {}):
            continue
        before = len(master)
        jobs = load_jobs(source, path, args.date)
        master, stats = merge_jobs(master, jobs, args.date)
        after = len(master)
        state.setdefault("files", {})[fingerprint] = {
            "path": str(path),
            "source": source,
            "imported_at": args.date,
            "input_rows": len(jobs),
            "new": stats["new"],
            "updated": stats["updated"],
            "skipped": stats["skipped"],
        }
        report_rows.append(
            {
                "file": str(path),
                "source": source,
                "input_rows": str(len(jobs)),
                "new": str(stats["new"]),
                "updated": str(stats["updated"]),
                "skipped": str(stats["skipped"]),
                "master_before": str(before),
                "master_after": str(after),
            }
        )
        imported_files += 1
        print(safe_console(f"IMPORTED {source} {path.name} new={stats['new']} updated={stats['updated']} skipped={stats['skipped']}"))

    if imported_files:
        save_master(args.master_file, master)
        write_csv_rows(args.public_export, master, MASTER_COLUMNS)
        write_csv_rows(report_file, report_rows, REPORT_COLUMNS)
        write_no_job_diagnosis(args.target_file, args.master_file, args.no_job_report, args.date)
    save_state(state_file, state)
    print(f"BOARD_IMPORTS imported_files={imported_files}")
    return 0


def safe_console(value: str) -> str:
    return value.encode("ascii", errors="backslashreplace").decode("ascii")


def discover_import_files(imports_dir: Path) -> list[tuple[str, Path]]:
    if not imports_dir.exists():
        return []
    files: list[tuple[str, Path]] = []
    candidates = (
        path
        for path in imports_dir.iterdir()
        if path.is_file() and path.suffix.casefold() in SUPPORTED_IMPORT_SUFFIXES
    )
    for path in sorted(candidates, key=lambda item: item.stat().st_mtime):
        lower = path.name.casefold()
        if "stepstone" in lower:
            files.append(("stepstone", path))
        elif "indeed" in lower:
            files.append(("indeed", path))
    return files


def stable_import_files(
    files: list[tuple[str, Path]], stable_for_seconds: int
) -> list[tuple[str, Path]]:
    if stable_for_seconds <= 0 or not files:
        return files

    snapshots = {path: file_snapshot(path) for _, path in files}
    print(f"BOARD_IMPORTS waiting_for_stability={stable_for_seconds}s files={len(files)}")
    time.sleep(stable_for_seconds)

    stable: list[tuple[str, Path]] = []
    for source, path in files:
        before = snapshots[path]
        after = file_snapshot(path)
        if before is not None and before == after:
            stable.append((source, path))
        else:
            print(safe_console(f"DEFERRED_UNSTABLE {source} {path.name}"))
    return stable


def file_snapshot(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return None
    return stat.st_size, stat.st_mtime_ns


def load_jobs(source: str, path: Path, today: str) -> list[Job]:
    df = read_export(path)
    missing = SOURCE_COLUMNS[source] - set(df.columns)
    if missing:
        missing_list = ", ".join(sorted(missing))
        raise ValueError(f"{path.name}: missing required {source} columns: {missing_list}")

    jobs: list[Job] = []
    for _, row in df.iterrows():
        if source == "stepstone":
            title = clean(row.get("Job_Titel"))
            link = clean(row.get("Titel_url"))
            firm = clean(row.get("Name_des_Unternehmens"))
            city = clean(row.get("Standort"))
            posted = clean(row.get("Erscheinen"))
        else:
            title = clean(row.get("Job_Title"))
            link = clean(row.get("Job_URL"))
            firm = clean(row.get("Company_Name"))
            city = clean(row.get("Location"))
            posted = clean(row.get("Posted_Date"))
        jobs.append(
            Job(
                title=title,
                link=link,
                firm=firm,
                city=city,
                source=source,
                first_seen=today,
                last_seen=today,
                posting_date=posted,
                source_url=link,
            )
        )
    return jobs


def read_export(path: Path) -> pd.DataFrame:
    suffix = path.suffix.casefold()
    if suffix == ".xlsx":
        df = pd.read_excel(path, sheet_name=0, dtype=str)
    elif suffix == ".csv":
        df = read_csv_export(path)
    else:
        raise ValueError(f"Unsupported board export format: {path.suffix}")

    df.columns = [str(column).lstrip("\ufeff").strip() for column in df.columns]
    return df.fillna("")


def read_csv_export(path: Path) -> pd.DataFrame:
    last_error: UnicodeDecodeError | None = None
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return pd.read_csv(path, dtype=str, sep=None, engine="python", encoding=encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
    raise ValueError(f"Could not decode CSV export {path.name}") from last_error


def clean(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    if pd.isna(value):
        return ""
    return str(value).strip()


def file_fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_state(path: Path) -> dict:
    if not path.exists():
        return {"files": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"files": {}}
    if not isinstance(data.get("files"), dict):
        data["files"] = {}
    return data


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())

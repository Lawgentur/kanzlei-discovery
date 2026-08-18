from __future__ import annotations

import argparse
import csv
import os
import time
from datetime import date
from pathlib import Path
from typing import Any

import requests


BASE_URL = "https://openapi.octoparse.com"
TASKS = {
    "indeed": "OCTOPARSE_INDEED_TASK_ID",
    "stepstone": "OCTOPARSE_STEPSTONE_TASK_ID",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Download the latest completed Octoparse batches.")
    parser.add_argument("--imports-dir", default="IMPORTS")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--page-size", type=int, default=1000)
    parser.add_argument("--wait-timeout-seconds", type=int, default=0)
    parser.add_argument("--poll-seconds", type=int, default=60)
    args = parser.parse_args()

    load_env(Path(args.env_file))
    api_key = required_env("OCTOPARSE_API_KEY")
    imports_dir = Path(args.imports_dir)
    imports_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    headers = {"x-api-key": api_key}

    downloaded = 0
    for source, task_env_name in TASKS.items():
        task_id = required_env(task_env_name)
        status = wait_for_completed(
            session,
            task_id,
            headers,
            args.wait_timeout_seconds,
            args.poll_seconds,
        )
        lot_no = str(status["lotNo"])
        output = imports_dir / f"{source.title()} Octoparse API {args.date} lot-{lot_no}.csv"
        if output.exists() and output.stat().st_size > 0:
            print(f"OCTOPARSE_EXISTS source={source} file={output.name}")
            continue
        rows = fetch_batch(session, task_id, lot_no, headers, args.page_size)
        expected = int(status.get("collectedRows") or len(rows))
        if len(rows) != expected:
            raise RuntimeError(
                f"{source}: downloaded {len(rows)} rows, but Octoparse reported {expected}"
            )

        write_csv_atomic(output, rows)
        downloaded += 1
        print(f"OCTOPARSE_DOWNLOADED source={source} rows={len(rows)} file={output.name}")

    print(f"OCTOPARSE_EXPORTS downloaded_files={downloaded}")
    return 0


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"'))


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def wait_for_completed(
    session: requests.Session,
    task_id: str,
    headers: dict[str, str],
    timeout_seconds: int,
    poll_seconds: int,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while True:
        response = session.get(
            f"{BASE_URL}/api/agentTools/getTaskStatus",
            params={"taskId": task_id},
            headers=headers,
            timeout=60,
        )
        response.raise_for_status()
        status = response.json().get("data") or {}
        state = str(status.get("status", "")).casefold()
        if state == "completed":
            if not status.get("lotNo"):
                raise RuntimeError(f"Octoparse task {task_id} completed without a lot number")
            return status
        if state in {"failed", "stopped", "cancelled", "canceled"}:
            raise RuntimeError(f"Octoparse task {task_id} ended with status {state}")
        if timeout_seconds <= 0 or time.monotonic() >= deadline:
            raise RuntimeError(f"Octoparse task {task_id} is not complete: {state or 'unknown'}")
        time.sleep(max(1, poll_seconds))


def fetch_batch(
    session: requests.Session,
    task_id: str,
    lot_no: str,
    headers: dict[str, str],
    page_size: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    cursor = 0
    while True:
        response = session.get(
            f"{BASE_URL}/data/lotNo/all",
            params={
                "taskId": task_id,
                "lotNo": lot_no,
                "offset": cursor,
                "size": page_size,
            },
            headers=headers,
            timeout=120,
        )
        response.raise_for_status()
        page = response.json().get("data") or {}
        items = page.get("data") or []
        rest_total = int(page.get("restTotal") or 0)
        if not items and rest_total > 0:
            raise RuntimeError(
                f"Octoparse returned an empty page at cursor {cursor} with {rest_total} rows left"
            )
        rows.extend(dict(item) for item in items)
        if rest_total <= 0:
            break
        next_cursor = int(page.get("offset") or 0)
        if next_cursor == cursor:
            raise RuntimeError(f"Octoparse cursor did not advance from {cursor}")
        cursor = next_cursor
    return rows


def write_csv_atomic(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise RuntimeError(f"Refusing to write empty Octoparse export: {path.name}")
    fields = list(dict.fromkeys(key for row in rows for key in row))
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


if __name__ == "__main__":
    raise SystemExit(main())

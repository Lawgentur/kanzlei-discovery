from __future__ import annotations

import io
import json
import os
from pathlib import Path

import pandas as pd
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload


def env_available() -> bool:
    return bool(os.getenv("GCP_SERVICE_ACCOUNT_KEY") and os.getenv("DRIVE_FOLDER_ID"))


def get_drive_service():
    info = json.loads(os.environ["GCP_SERVICE_ACCOUNT_KEY"])
    creds = service_account.Credentials.from_service_account_info(info)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def load_state(path: str | Path) -> dict:
    path = Path(path)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"processed_ids": [], "last_sync": None}


def save_state(path: str | Path, state: dict) -> None:
    Path(path).write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def list_new_excel_files(service, processed_ids: set[str]) -> list[dict]:
    folder_id = os.environ["DRIVE_FOLDER_ID"]
    query = f"'{folder_id}' in parents and name contains '.xlsx' and not name = 'webseiten_jobsuche_master.xlsx' and trashed = false"
    files = []
    page_token = None
    while True:
        response = service.files().list(
            q=query,
            fields="nextPageToken, files(id, name, modifiedTime)",
            pageSize=100,
            orderBy="modifiedTime desc",
            pageToken=page_token,
        ).execute()
        files.extend(item for item in response.get("files", []) if item["id"] not in processed_ids)
        page_token = response.get("nextPageToken")
        if not page_token:
            return files


def download_excel(service, file_id: str) -> pd.DataFrame:
    request = service.files().get_media(fileId=file_id)
    handle = io.BytesIO()
    downloader = MediaIoBaseDownload(handle, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return pd.read_excel(io.BytesIO(handle.getvalue()))


def sync_drive_excels(state_path: str | Path) -> tuple[list[dict[str, str]], list[str]]:
    service = get_drive_service()
    state = load_state(state_path)
    processed = set(state.get("processed_ids", []))
    rows: list[dict[str, str]] = []
    newly_processed: list[str] = []
    for item in list_new_excel_files(service, processed):
        frame = download_excel(service, item["id"])
        rows.extend(frame.fillna("").astype(str).to_dict("records"))
        newly_processed.append(item["id"])
    state["processed_ids"] = sorted(processed | set(newly_processed))
    return rows, newly_processed


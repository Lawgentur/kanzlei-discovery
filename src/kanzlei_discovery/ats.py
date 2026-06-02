from __future__ import annotations

from urllib.parse import urlparse


ATS_PATTERNS = {
    "personio": ["personio.de", "personio.com"],
    "greenhouse": ["greenhouse.io", "boards.greenhouse"],
    "lever": ["lever.co", "jobs.lever"],
    "recruitee": ["recruitee.com"],
    "workable": ["workable.com", "apply.workable"],
    "smartrecruiters": ["smartrecruiters.com"],
    "ashby": ["ashbyhq.com", "jobs.ashbyhq"],
    "bamboohr": ["bamboohr.com"],
    "breezyhr": ["breezy.hr"],
    "softgarden": ["softgarden.io", "softgarden.de"],
    "join": ["join.com"],
    "teamtailor": ["teamtailor.com"],
    "workday": ["myworkdayjobs.com", "workday.com/de"],
    "dvinci": ["dvinci.de", "d-vinci.de"],
}


def detect_ats(url: str) -> str:
    lower = (url or "").lower()
    for name, patterns in ATS_PATTERNS.items():
        if any(pattern in lower for pattern in patterns):
            return name
    return "unknown"


def extract_slug(url: str, ats: str) -> str:
    parsed = urlparse(url)
    host_parts = parsed.hostname.split(".") if parsed.hostname else []
    path_parts = [part for part in parsed.path.strip("/").split("/") if part]

    if ats in {"greenhouse", "lever", "workable", "smartrecruiters", "ashby"} and path_parts:
        return path_parts[0] if path_parts[0] != "embed" else (path_parts[1] if len(path_parts) > 1 else "")
    if ats in {"personio", "recruitee", "bamboohr", "breezyhr"} and host_parts:
        return host_parts[0]
    return ""


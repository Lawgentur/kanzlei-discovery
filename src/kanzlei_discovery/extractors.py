from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Any

import requests
from bs4 import BeautifulSoup

from .ats import detect_ats, extract_slug
from .models import Firm, Job
from .quality import is_likely_job_title, normalize_url


class DirectATSClient:
    def __init__(self, session: requests.Session | None = None, timeout: int = 20) -> None:
        self.session = session or requests.Session()
        self.timeout = timeout

    def fetch(self, firm: Firm, url: str) -> list[Job]:
        ats = detect_ats(url)
        method = getattr(self, f"_fetch_{ats}", None)
        if not method:
            return []
        try:
            return method(firm, url)
        except requests.RequestException:
            return []
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return []

    def _fetch_greenhouse(self, firm: Firm, url: str) -> list[Job]:
        slug = extract_slug(url, "greenhouse")
        if not slug:
            return []
        data = self.session.get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs", timeout=self.timeout).json()
        jobs = []
        for item in data.get("jobs", []):
            location = item.get("location", {})
            jobs.append(
                Job(
                    title=item.get("title", ""),
                    link=item.get("absolute_url", url),
                    firm=firm.name,
                    city=location.get("name", "") if isinstance(location, dict) else str(location or ""),
                    source="greenhouse",
                    last_seen=str(item.get("updated_at", ""))[:10],
                )
            )
        return jobs

    def _fetch_lever(self, firm: Firm, url: str) -> list[Job]:
        slug = extract_slug(url, "lever")
        if not slug:
            return []
        data = self.session.get(f"https://api.lever.co/v0/postings/{slug}", timeout=self.timeout).json()
        jobs = []
        for item in data if isinstance(data, list) else []:
            categories = item.get("categories", {})
            created = item.get("createdAt")
            seen = ""
            if isinstance(created, (int, float)):
                seen = datetime.fromtimestamp(created / 1000).date().isoformat()
            jobs.append(
                Job(
                    title=item.get("text", ""),
                    link=item.get("hostedUrl", url),
                    firm=firm.name,
                    city=categories.get("location", "") if isinstance(categories, dict) else "",
                    source="lever",
                    last_seen=seen,
                )
            )
        return jobs

    def _fetch_personio(self, firm: Firm, url: str) -> list[Job]:
        slug = extract_slug(url, "personio")
        if not slug:
            return []
        xml = self.session.get(f"https://{slug}.jobs.personio.de/xml", timeout=self.timeout).text
        soup = BeautifulSoup(xml, "html.parser")
        jobs = []
        for position in soup.find_all("position"):
            title = _tag_text(position, "name")
            job_id = _tag_text(position, "id")
            link = f"https://{slug}.jobs.personio.de/job/{job_id}" if job_id else url
            jobs.append(Job(title=title, link=link, firm=firm.name, city=_tag_text(position, "office"), source="personio"))
        return jobs

    def _fetch_recruitee(self, firm: Firm, url: str) -> list[Job]:
        slug = extract_slug(url, "recruitee")
        if not slug:
            return []
        data = self.session.get(f"https://{slug}.recruitee.com/api/offers", timeout=self.timeout).json()
        return [
            Job(
                title=item.get("title", ""),
                link=item.get("careers_url", item.get("url", url)),
                firm=firm.name,
                city=item.get("location", ""),
                source="recruitee",
            )
            for item in data.get("offers", [])
        ]


def extract_dom_jobs(html: str, firm: Firm, base_url: str) -> list[Job]:
    soup = BeautifulSoup(html, "html.parser")
    jobs: list[Job] = []
    seen: set[str] = set()

    for tag in soup.find_all("a", href=True, limit=2000):
        href = normalize_url(base_url, tag.get("href", ""))
        text = tag.get_text(" ", strip=True)
        text = re.sub(r"\s+", " ", text)
        if not text or (href, text.lower()) in seen:
            continue
        if len(text.split()) > 18:
            continue
        if is_likely_job_title(text, href):
            seen.add((href, text.lower()))
            jobs.append(Job(title=text, link=href or base_url, firm=firm.name, city=find_nearby_location(tag), source="dom"))

    return jobs


def extract_json_jobs(payload: Any, firm: Firm, base_url: str, depth: int = 0) -> list[Job]:
    if depth > 5:
        return []
    jobs: list[Job] = []
    if isinstance(payload, list):
        for item in payload:
            jobs.extend(extract_json_jobs(item, firm, base_url, depth + 1))
    elif isinstance(payload, dict):
        parsed = parse_job_object(payload, firm, base_url)
        if parsed:
            jobs.append(parsed)
        for key in ("jobs", "jobPostings", "positions", "postings", "results", "openings", "vacancies", "offers", "items", "data"):
            value = payload.get(key)
            if isinstance(value, (list, dict)):
                jobs.extend(extract_json_jobs(value, firm, base_url, depth + 1))
    return jobs


def extract_llm_jobs(html: str, firm: Firm, base_url: str) -> list[Job]:
    providers = configured_llm_providers()
    if not providers:
        return []
    try:
        from openai import OpenAI
    except ImportError:
        return []

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)[:12000]
    if not text:
        return []

    for provider in providers:
        try:
            client = OpenAI(api_key=provider["api_key"], base_url=provider["base_url"]) if provider["base_url"] else OpenAI(api_key=provider["api_key"])
            response = client.chat.completions.create(
                model=provider["model"],
                temperature=0,
                max_tokens=2500,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Extrahiere nur echte offene Stellenanzeigen von Kanzleiseiten. "
                            "Keine Navigation, Rechtsgebiete, News, Anwaltsprofile oder generische Karrieretexte. "
                            "Antworte ausschliesslich als JSON: "
                            '{"jobs":[{"title":"","location":"","link":""}]}'
                        ),
                    },
                    {"role": "user", "content": f"Kanzlei: {firm.name}\nURL: {base_url}\n\n{text}"},
                ],
            )
            content = response.choices[0].message.content or "{}"
            match = re.search(r"\{.*\}", content, re.S)
            data = json.loads(match.group(0) if match else content)
            return [
                Job(
                    title=item.get("title", ""),
                    link=normalize_url(base_url, item.get("link", "")) or base_url,
                    firm=firm.name,
                    city=item.get("location", ""),
                    source=provider["source"],
                )
                for item in data.get("jobs", [])
                if isinstance(item, dict)
            ]
        except Exception:
            continue
    return []


def configured_llm_providers() -> list[dict[str, str | None]]:
    providers: list[dict[str, str | None]] = []
    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        providers.append(
            {
                "api_key": openai_key,
                "base_url": os.getenv("OPENAI_BASE_URL") or None,
                "model": os.getenv("OPENAI_LLM_MODEL", os.getenv("LLM_MODEL", "gpt-4.1-mini")),
                "source": "llm:gpt",
            }
        )
    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key:
        providers.append(
            {
                "api_key": gemini_key,
                "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
                "model": os.getenv("GEMINI_LLM_MODEL", "gemini-3-flash-preview"),
                "source": "llm:gemini",
            }
        )
    return providers


def parse_embedded_json_jobs(html: str, firm: Firm, base_url: str) -> list[Job]:
    soup = BeautifulSoup(html, "html.parser")
    jobs: list[Job] = []
    for script in soup.find_all("script", type=re.compile("json", re.I)):
        try:
            payload = json.loads(script.get_text(strip=True))
        except json.JSONDecodeError:
            continue
        jobs.extend(extract_json_jobs(payload, firm, base_url))
    return jobs


def parse_job_object(obj: dict[str, Any], firm: Firm, base_url: str) -> Job | None:
    title = first_string(obj, ["title", "name", "text", "position", "jobTitle", "displayTitle", "stellentitel", "bezeichnung", "headline"])
    if not title:
        return None
    link = first_string(obj, ["url", "absolute_url", "hostedUrl", "apply_url", "link", "href", "careers_url"]) or base_url
    location_value = obj.get("location") or obj.get("office") or obj.get("city") or obj.get("standort") or obj.get("ort")
    if isinstance(location_value, dict):
        city = first_string(location_value, ["name", "city", "label"])
    elif isinstance(location_value, list) and location_value:
        city = str(location_value[0].get("name", "")) if isinstance(location_value[0], dict) else str(location_value[0])
    else:
        city = str(location_value or "")
    return Job(title=title, link=normalize_url(base_url, link), firm=firm.name, city=city, source="json")


def discover_jobboard_url(session: requests.Session, firm: Firm, timeout: int = 15) -> str:
    if firm.jobboard_url:
        return firm.jobboard_url
    if not firm.domain:
        return ""
    base = firm.domain if firm.domain.startswith(("http://", "https://")) else f"https://{firm.domain}"
    try:
        response = session.get(base, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException:
        return base
    soup = BeautifulSoup(response.text, "html.parser")
    candidates = []
    for link in soup.find_all("a", href=True):
        text = link.get_text(" ", strip=True).lower()
        href = link.get("href", "").lower()
        if any(marker in text or marker in href for marker in ("karriere", "career", "jobs", "stellen", "bewerbung")):
            candidates.append(normalize_url(response.url, link.get("href", "")))
    return candidates[0] if candidates else base


def first_string(obj: dict[str, Any], keys: list[str]) -> str:
    for key in keys:
        value = obj.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def find_nearby_location(tag: Any) -> str:
    parent = tag.parent
    if not parent:
        return ""
    for candidate in parent.find_all(class_=re.compile(r"location|city|standort|ort", re.I)):
        text = candidate.get_text(" ", strip=True)
        if 2 < len(text) < 80:
            return text
    return ""


def _tag_text(parent: Any, name: str) -> str:
    tag = parent.find(name)
    return tag.get_text(" ", strip=True) if tag else ""

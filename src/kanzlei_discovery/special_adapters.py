from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from urllib.parse import quote, urlparse

import requests
from bs4 import BeautifulSoup

from .models import Firm, Job
from .quality import normalize_url


@dataclass
class SpecialAdapterResult:
    jobs: list[Job]
    handled: bool = False


def fetch_special_jobs(session: requests.Session, firm: Firm, url: str) -> SpecialAdapterResult:
    adapter = identify_special_adapter(firm, url)
    if adapter == "radancy:aoshearman":
        return SpecialAdapterResult(fetch_aoshearman_radancy(session, firm, url), handled=True)
    if adapter == "browser:wts":
        return SpecialAdapterResult(fetch_wts_browser(firm, url), handled=True)
    if adapter == "cms":
        return SpecialAdapterResult(fetch_cms_jobs(session, firm, url), handled=True)
    if adapter == "dom:fieldfisher":
        return SpecialAdapterResult(fetch_fieldfisher_jobs(session, firm, url), handled=True)
    if adapter == "dom:winheller":
        return SpecialAdapterResult(fetch_winheller_jobs(session, firm, url), handled=True)
    if adapter == "personio:eagle":
        return SpecialAdapterResult(fetch_modern_personio_jobs(session, firm, url, "personio:eagle"), handled=True)
    if adapter == "api:dlapiper":
        return SpecialAdapterResult(fetch_dlapiper_jobs(session, firm, url), handled=True)
    if adapter == "api:pwc-phenom":
        return SpecialAdapterResult(fetch_pwc_legal_jobs(session, firm, url), handled=True)
    if adapter == "skip:pwc-general":
        return SpecialAdapterResult([], handled=True)
    if adapter == "api:bdo-typesense":
        return SpecialAdapterResult(fetch_bdo_tax_legal_jobs(session, firm, url), handled=True)
    if adapter == "reader:skadden":
        return SpecialAdapterResult(fetch_skadden_reader_jobs(session, firm, url), handled=True)

    return SpecialAdapterResult([], handled=False)


def identify_special_adapter(firm: Firm, url: str) -> str:
    host = urlparse(url).netloc.lower()
    firm_key = f"{firm.name} {firm.domain} {url}".lower()

    if "careers.aoshearman.com" in host or "aoshearman" in firm_key:
        return "radancy:aoshearman"
    if "wts.com" in host or "wts legal" in firm_key:
        return "browser:wts"
    if "cms.law" in host or re.search(r"\bcms\b", firm_key):
        return "cms"
    if "fieldfisher-karriere.de" in host or "fieldfisher" in firm_key:
        return "dom:fieldfisher"
    if "winheller.com" in host or "winheller" in firm_key:
        return "dom:winheller"
    if "eagle-lsp.jobs.personio.de" in host or "eagle lsp" in firm_key:
        return "personio:eagle"
    if "careers.dlapiper.com" in host or "dla" in firm_key:
        return "api:dlapiper"
    if "jobs.pwc.de" in host or "pricewaterhousecoopers legal" in firm_key:
        if "legal-jobs" not in url and "pricewaterhousecoopers legal" not in firm_key:
            return "skip:pwc-general"
        return "api:pwc-phenom"
    if "talents.bdo.de" in host or "bdo germany" in firm_key:
        return "api:bdo-typesense"
    if "skadden.com" in host or "skadden" in firm_key:
        return "reader:skadden"
    return ""


def fetch_aoshearman_radancy(session: requests.Session, firm: Firm, url: str) -> list[Job]:
    endpoint = "https://careers.aoshearman.com/en/search-jobs/resultspost"
    base_payload = {
        "ActiveFacetID": 0,
        "Distance": 50,
        "RadiusUnitType": 2,
        "RecordsPerPage": 15,
        "CurrentPage": 1,
        "TotalPages": 1,
        "TotalContentPages": 0,
        "Keywords": "",
        "Location": "Germany",
        "Latitude": 51.5,
        "Longitude": 10.5,
        "ShowRadius": False,
        "FacetTerm": "",
        "FacetType": None,
        "SearchResultsModuleName": "Section 6 - Search Results List",
        "SearchFiltersModuleName": None,
        "SortCriteria": 0,
        "SortDirection": 0,
        "SearchType": 5,
        "SearchResultType": 1,
        "CategoryFacetTerm": None,
        "CategoryFacetType": None,
        "LocationFacetTerm": None,
        "LocationFacetType": None,
        "KeywordType": None,
        "LocationType": 2,
        "LocationPath": "2921044",
        "OrganizationIds": "3392",
        "RefinedKeywords": [],
        "PostalCode": "",
        "SaveJobs": True,
        "ResultsType": 0,
        "UseNoIndex": True,
    }
    headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/json; charset=UTF-8",
        "Origin": "https://careers.aoshearman.com",
        "Referer": "https://careers.aoshearman.com/en/search-jobs",
        "X-Requested-With": "XMLHttpRequest",
    }
    jobs: list[Job] = []
    seen: set[str] = set()

    for page in range(1, 20):
        payload = dict(base_payload)
        payload["CurrentPage"] = page
        response = session.post(endpoint, data=json.dumps(payload), headers=headers, timeout=30)
        response.raise_for_status()
        html = _html_from_response(response)
        page_jobs = parse_radancy_jobs(html, firm, "https://careers.aoshearman.com", source="radancy:aoshearman")
        new_jobs = [job for job in page_jobs if job.link not in seen]
        for job in new_jobs:
            seen.add(job.link)
        jobs.extend(new_jobs)
        if not page_jobs or len(jobs) >= _radancy_total(html, default=44):
            break

    return jobs


def parse_radancy_jobs(html: str, firm: Firm, base_url: str, source: str) -> list[Job]:
    soup = BeautifulSoup(html or "", "html.parser")
    jobs: list[Job] = []
    seen: set[str] = set()

    for link in soup.find_all("a", href=True):
        href = normalize_url(base_url, link.get("href", ""))
        if "/job/" not in href:
            continue
        title = re.sub(r"\s+", " ", link.get_text(" ", strip=True)).strip()
        if not is_plausible_board_title(title):
            continue
        city = _city_from_radancy_url(href) or _nearby_text(link, r"location|city|job-location|standort")
        key = href.lower()
        if key in seen:
            continue
        seen.add(key)
        jobs.append(Job(title=title, link=href, firm=firm.name, city=city, source=source, source_url=base_url))

    return jobs


def fetch_wts_browser(firm: Firm, url: str) -> list[Job]:
    def action(page):
        page.goto(url, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(3000)
        html = page.evaluate(
            """async () => {
                const response = await fetch('/de-de/job-listing?items=500&filterValue=', { credentials: 'include' });
                return await response.text();
            }"""
        )
        jobs = parse_wts_jobs(html, firm, "https://wts.com")
        if jobs:
            return jobs
        click_more_results(page, max_clicks=30)
        return parse_wts_jobs(page.content(), firm, "https://wts.com")

    return run_with_browser(action)


def parse_wts_jobs(html: str, firm: Firm, base_url: str) -> list[Job]:
    soup = BeautifulSoup(html or "", "html.parser")
    jobs: list[Job] = []
    seen: set[str] = set()

    for card in soup.select(".jobsResult, [class*=jobsResult]"):
        link = card.select_one("a.jobsResult-link[href], a[href]")
        title_node = card.select_one(".jobsResult-title, [class*=jobsResult-title]")
        if not link:
            continue
        title = re.sub(r"\s+", " ", (title_node or link).get_text(" ", strip=True)).strip()
        href = normalize_url(base_url, link.get("href", ""))
        if not href or not is_plausible_board_title(title):
            continue
        city = _nearby_text(card, r"location|city|standort|office|place|ort")
        key = href.lower()
        if key in seen:
            continue
        seen.add(key)
        jobs.append(Job(title=title, link=href, firm=firm.name, city=city, source="browser:wts", source_url=base_url))

    return jobs


def fetch_fieldfisher_jobs(session: requests.Session, firm: Firm, url: str) -> list[Job]:
    response = session.get(url, timeout=40)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    jobs: list[Job] = []
    seen: set[str] = set()

    for card in soup.select("div.job"):
        link = card.select_one("a[href*='/job/']")
        title_node = card.select_one("h2, h3")
        if not link or not title_node:
            continue
        title = re.sub(r"\s+", " ", title_node.get_text(" ", strip=True)).strip()
        href = normalize_url(response.url, link.get("href", ""))
        city = fieldfisher_city(card)
        if not href or not is_plausible_board_title(title):
            continue
        key = href.lower()
        if key in seen:
            continue
        seen.add(key)
        jobs.append(Job(title=title, link=href, firm=firm.name, city=city, source="dom:fieldfisher", source_url=response.url))

    return jobs


def fetch_winheller_jobs(session: requests.Session, firm: Firm, url: str) -> list[Job]:
    response = session.get(url, timeout=40)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    jobs: list[Job] = []
    seen: set[str] = set()

    for link in soup.select("a.karriere-item-link[href]"):
        title_node = link.select_one(".col-md-9, .col-12")
        city_node = link.select_one(".link-icon-location")
        title = re.sub(r"\s+", " ", (title_node or link).get_text(" ", strip=True)).strip()
        href = normalize_url(response.url, link.get("href", ""))
        city = re.sub(r"\s+", " ", city_node.get_text(" ", strip=True)).strip() if city_node else ""
        if not href or not is_plausible_board_title(title):
            continue
        key = href.lower()
        if key in seen:
            continue
        seen.add(key)
        jobs.append(Job(title=title, link=href, firm=firm.name, city=city, source="dom:winheller", source_url=response.url))

    return jobs


def fetch_modern_personio_jobs(session: requests.Session, firm: Firm, url: str, source: str) -> list[Job]:
    response = session.get(url, timeout=40)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    jobs: list[Job] = []
    seen: set[str] = set()

    for link in soup.select("a.job-box[href], a[href*='/job/']"):
        title_node = link.select_one("h3, .jb-title, [class*=jobTitle]")
        title = re.sub(r"\s+", " ", (title_node or link).get_text(" ", strip=True)).strip()
        href = normalize_url(response.url, link.get("href", ""))
        city_node = link.select_one("[class*=jobMetaText], .jb-description")
        city = re.sub(r"\s+", " ", city_node.get_text(" ", strip=True)).strip() if city_node else ""
        if not href or not is_plausible_board_title(title):
            continue
        key = href.lower()
        if key in seen:
            continue
        seen.add(key)
        jobs.append(Job(title=title, link=href, firm=firm.name, city=city, source=source, source_url=response.url))

    return jobs


def fetch_dlapiper_jobs(session: requests.Session, firm: Firm, url: str) -> list[Job]:
    api_jobs = fetch_dlapiper_api(session, firm, url)
    if api_jobs:
        return api_jobs
    response = session.get(url, timeout=40)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    jobs: list[Job] = []
    seen: set[str] = set()

    for link in soup.find_all("a", href=True):
        href = normalize_url(response.url, link.get("href", ""))
        if "/jobs/20" not in href:
            continue
        title = re.sub(r"\s+", " ", link.get_text(" ", strip=True)).strip()
        if not title or not is_dlapiper_germany_job(title):
            continue
        city = dlapiper_city(title)
        key = href.lower()
        if key in seen:
            continue
        seen.add(key)
        jobs.append(Job(title=clean_dlapiper_title(title), link=href, firm=firm.name, city=city, source="dom:dlapiper", source_url=response.url))

    return jobs


def fetch_dlapiper_api(session: requests.Session, firm: Firm, url: str) -> list[Job]:
    endpoint = "https://careers.dlapiper.com/system/modules/com.dlapiper.careers/functions/get-jobs.json"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Referer": "https://careers.dlapiper.com/jobs/index.html",
    }
    jobs: list[Job] = []
    seen: set[str] = set()

    for page in range(1, 20):
        payload = {"query": "", "country": "Germany", "page": str(page), "sort": "by-default"}
        response = session.post(endpoint, data=json.dumps(payload), headers=headers, timeout=40)
        response.raise_for_status()
        data = response.json()
        items = data.get("items") if isinstance(data, dict) else []
        if not isinstance(items, list) or not items:
            break
        for item in items:
            if not isinstance(item, dict):
                continue
            title = re.sub(r"\s+", " ", str(item.get("title") or "")).strip()
            link = normalize_url(url, str(item.get("url") or ""))
            city = normalize_dlapiper_city(str(item.get("location") or ""))
            if not link or not is_plausible_board_title(title):
                continue
            key = link.lower()
            if key in seen:
                continue
            seen.add(key)
            jobs.append(Job(title=title, link=link, firm=firm.name, city=city, source="api:dlapiper", source_url=url))
        pagination = data.get("pagination") if isinstance(data, dict) else None
        if isinstance(pagination, dict) and page >= int(pagination.get("count") or page):
            break
        if not data.get("hasMore"):
            break

    return jobs


def fetch_pwc_legal_jobs(session: requests.Session, firm: Firm, url: str) -> list[Job]:
    endpoint = "https://jobs.pwc.de/widgets"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Referer": url,
    }
    jobs: list[Job] = []
    seen: set[str] = set()

    for start in range(0, 1000, 100):
        payload = {
            "ddoKey": "refineSearch",
            "sortBy": "Most relevant",
            "subsearch": "",
            "from": start,
            "jobs": True,
            "counts": True,
            "all_fields": ["category", "country", "state", "city"],
            "pageName": "legal",
            "size": 100,
            "clearAll": False,
            "jdsource": "facets",
        }
        response = session.post(endpoint, data=json.dumps(payload), headers=headers, timeout=40)
        response.raise_for_status()
        refine = response.json().get("refineSearch", {})
        data = refine.get("data", {}) if isinstance(refine, dict) else {}
        page_jobs = data.get("jobs") if isinstance(data, dict) else []
        if not isinstance(page_jobs, list) or not page_jobs:
            break
        for item in page_jobs:
            if not isinstance(item, dict):
                continue
            categories = item.get("multi_category") or []
            if item.get("category") != "Legal" and "Legal" not in categories:
                continue
            title = re.sub(r"\s+", " ", str(item.get("title") or "")).strip()
            job_id = str(item.get("jobId") or item.get("reqId") or "").strip()
            if not job_id or not is_plausible_board_title(title):
                continue
            link = f"https://jobs.pwc.de/de/de/job/{job_id}/{slugify_for_url(title)}"
            city = normalize_location_list(item.get("multi_location") or item.get("location") or item.get("city") or "")
            key = link.lower()
            if key in seen:
                continue
            seen.add(key)
            jobs.append(Job(title=title, link=link, firm=firm.name, city=city, source="api:pwc-phenom", source_url=url))
        total = int(refine.get("totalHits") or 0) if isinstance(refine, dict) else 0
        if start + len(page_jobs) >= total:
            break

    return jobs


def fetch_bdo_tax_legal_jobs(session: requests.Session, firm: Firm, url: str) -> list[Job]:
    endpoint = "https://api.my-job-shop.com/api/typesense/multi_search"
    api_key = fetch_bdo_typesense_key(session, url)
    if not api_key:
        return []
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Tenant-Id": "bdo",
        "X-JobShop-Id": "935cebfc-0be8-482a-aea4-19271f0b18a1",
        "X-Typesense-Api-Key": api_key,
    }
    jobs: list[Job] = []
    seen: set[str] = set()

    for page in range(1, 20):
        search = {
            "collection": "offers",
            "q": "*",
            "query_by": "title, location, external_id, company, full_address, title_embed",
            "filter_by": "department:=[`Tax & Legal`]",
            "page": page,
            "per_page": 100,
            "exclude_fields": "title_embed, description, expectation, introduction, about, offering, contact_text, additional, benefits",
        }
        response = session.post(endpoint, data=json.dumps({"searches": [search]}), headers=headers, timeout=40)
        response.raise_for_status()
        result = (response.json().get("results") or [{}])[0]
        hits = result.get("hits") or []
        if not hits:
            break
        for hit in hits:
            doc = hit.get("document") or {}
            title = re.sub(r"\s+", " ", str(doc.get("title") or "")).strip()
            link = str(doc.get("url") or doc.get("application_url") or "").strip()
            if not link or not is_plausible_board_title(title):
                continue
            key = link.lower()
            if key in seen:
                continue
            seen.add(key)
            jobs.append(
                Job(
                    title=title,
                    link=link,
                    firm=firm.name,
                    city=normalize_location_list(doc.get("location") or doc.get("full_address") or ""),
                    source="api:bdo-typesense",
                    source_url=url,
                )
            )
        if page * 100 >= int(result.get("found") or 0):
            break

    return jobs


def fetch_bdo_typesense_key(session: requests.Session, url: str) -> str:
    try:
        response = session.get(url, timeout=40)
        response.raise_for_status()
    except requests.RequestException:
        return ""
    match = re.search(r'<script type="application/json" id="__NUXT_DATA__"[^>]*>(.*?)</script>', response.text, re.S)
    if not match:
        return ""
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return ""
    if isinstance(data, list):
        for value in data:
            if isinstance(value, str) and value.startswith("ZHlE"):
                return value
    return ""


def fetch_skadden_reader_jobs(session: requests.Session, firm: Firm, url: str) -> list[Job]:
    reader_url = "https://r.jina.ai/http://r.jina.ai/http://" + url
    try:
        response = session.get(reader_url, timeout=40)
        response.raise_for_status()
    except requests.RequestException:
        return []
    jobs: list[Job] = []
    pattern = re.compile(
        r"\*\s+\[(?P<title>[^\]]+)\]\((?P<link>https://www\.skadden\.com/careers/staff/opportunities/non-us-opportunities/[^)]+)\)(?P<city>[^\n]*)",
        re.I,
    )
    for match in pattern.finditer(response.text):
        title = re.sub(r"\s+", " ", match.group("title")).strip()
        city = re.sub(r"\s+", " ", match.group("city")).strip()
        if not re.search(r"frankfurt|germany|deutschland", city, re.I):
            continue
        if not is_plausible_board_title(title):
            continue
        jobs.append(Job(title=title, link=match.group("link"), firm=firm.name, city=city, source="reader:skadden", source_url=url))
    return jobs


def fetch_cms_jobs(session: requests.Session, firm: Firm, url: str) -> list[Job]:
    jobs = fetch_cms_api(session, firm, url)
    if jobs:
        return jobs
    jobs = fetch_cms_browser(firm, url)
    if jobs:
        return jobs
    return fetch_cms_reader(session, firm, url)


def fetch_cms_api(session: requests.Session, firm: Firm, url: str) -> list[Job]:
    endpoint = "https://cms.law/de/deu/search.json"
    headers = {
        "Accept": "application/json,text/javascript,*/*",
        "Accept-Language": "de-DE,de;q=0.9,en;q=0.5",
        "Referer": "https://cms.law/de/deu/stellenausschreibungen",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
    }
    limit = 10
    jobs: list[Job] = []
    seen: set[str] = set()

    for offset in range(0, 500, limit):
        params = {
            "cx": "career",
            "p": "238",
            "sb": "startdatedesc",
            "limit": str(limit),
            "pagination": "7",
            "id": "job-opportunities",
            "offset": str(offset),
        }
        response = session.get(endpoint, params=params, headers=headers, timeout=40)
        response.raise_for_status()
        data = response.json()
        total = int(data.get("total") or 0)
        html = ""
        results = data.get("results")
        if isinstance(results, dict):
            html = str(results.get("items") or "")
        page_jobs = parse_cms_jobs(html, firm, url)
        for job in page_jobs:
            if job.link.lower() in seen:
                continue
            seen.add(job.link.lower())
            jobs.append(job)
        if offset + limit >= total or not page_jobs:
            break

    return jobs


def fetch_cms_browser(firm: Firm, url: str) -> list[Job]:
    def action(page):
        page.goto(url, wait_until="domcontentloaded", timeout=120000)
        wait_for_real_page(page, markers=("Stellenangebote", "MEHR ANZEIGEN", "Deutschland"), timeout_seconds=45)
        click_more_results(page, max_clicks=12)
        return parse_cms_jobs(page.content(), firm, page.url)

    return run_with_browser(action)


def parse_cms_jobs(html: str, firm: Firm, base_url: str) -> list[Job]:
    soup = BeautifulSoup(html or "", "html.parser")
    jobs: list[Job] = []
    seen: set[str] = set()

    for card in soup.select(".expert-card"):
        title_node = card.select_one(".fs-3.fw-medium, [class*=card__title], h2, h3")
        link = card.select_one("a[href]")
        if not title_node or not link:
            continue
        title = re.sub(r"\s+", " ", title_node.get_text(" ", strip=True)).strip()
        href = normalize_url(base_url, link.get("href", ""))
        if not href or not is_plausible_board_title(title):
            continue
        city = cms_location_from_card(card)
        key = href.lower()
        if key in seen:
            continue
        seen.add(key)
        jobs.append(Job(title=title, link=href, firm=firm.name, city=city, source="api:cms", source_url=base_url))

    for link in soup.find_all("a", href=True):
        href = normalize_url(base_url, link.get("href", ""))
        href_lower = href.lower()
        if not any(marker in href_lower for marker in ("/karriere/", "/career/", "/stellen", "/job", "/jobs")):
            continue
        title = re.sub(r"\s+", " ", link.get_text(" ", strip=True)).strip()
        if not is_plausible_board_title(title):
            continue
        city = _nearby_text(link, r"location|city|standort|office|ort")
        key = href.lower()
        if key in seen:
            continue
        seen.add(key)
        jobs.append(Job(title=title, link=href, firm=firm.name, city=city, source="browser:cms", source_url=base_url))

    return jobs


def fetch_cms_reader(session: requests.Session, firm: Firm, url: str) -> list[Job]:
    reader_url = "https://r.jina.ai/http://r.jina.ai/http://" + url
    try:
        response = session.get(reader_url, timeout=40)
        response.raise_for_status()
    except requests.RequestException:
        return []
    return parse_cms_reader(response.text, firm)


def parse_cms_reader(text: str, firm: Firm) -> list[Job]:
    jobs: list[Job] = []
    pattern = re.compile(
        r"^\s*(?P<title>[^\n]+)\n\n\s*(?P<city>[^\n]*(?:DEUTSCHLAND|MEHRERE STANDORTE))\s*\n\n"
        r"\s*\[Anzeigen\]\((?P<link>https://cms\.law/de/deu/stellenausschreibungen/[^)]+)\)",
        re.I | re.M,
    )
    for match in pattern.finditer(text or ""):
        title = re.sub(r"\s+", " ", match.group("title")).strip()
        if not is_plausible_board_title(title):
            continue
        jobs.append(
            Job(
                title=title,
                link=match.group("link"),
                firm=firm.name,
                city=normalize_cms_city(match.group("city")),
                source="reader:cms",
                source_url="https://cms.law/de/deu/stellenausschreibungen",
            )
        )
    return jobs


def run_with_browser(action):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return []

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(
                locale="de-DE",
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
            )
            try:
                return action(page)
            finally:
                browser.close()
    except Exception:
        return []


def click_more_results(page, max_clicks: int) -> int:
    clicked = 0
    previous_length = 0

    for _ in range(max_clicks):
        body_text = page.locator("body").inner_text(timeout=10000)
        current_length = len(body_text)
        candidates = page.locator(
            "button:has-text('Mehr'), a:has-text('Mehr'), "
            "button:has-text('mehr'), a:has-text('mehr'), "
            "button:has-text('Load'), a:has-text('Load'), "
            "button:has-text('Show more'), a:has-text('Show more')"
        )
        if not candidates.count():
            break
        clicked_this_round = False
        for index in range(candidates.count()):
            candidate = candidates.nth(index)
            try:
                if candidate.is_visible() and candidate.is_enabled():
                    candidate.scroll_into_view_if_needed(timeout=5000)
                    candidate.click(timeout=10000)
                    page.wait_for_timeout(2500)
                    clicked += 1
                    clicked_this_round = True
                    break
            except Exception:
                continue
        if not clicked_this_round:
            break
        if current_length == previous_length and clicked > 1:
            break
        previous_length = current_length

    return clicked


def wait_for_real_page(page, markers: tuple[str, ...], timeout_seconds: int) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        text = page.locator("body").inner_text(timeout=10000)
        lower = text.lower()
        if "cloudflare" not in lower and any(marker.lower() in lower for marker in markers):
            return
        page.wait_for_timeout(2000)


def is_plausible_board_title(title: str) -> bool:
    text = re.sub(r"\s+", " ", (title or "").strip())
    lower = text.lower()
    if len(text) < 5 or len(text) > 220 or len(text.split()) > 24:
        return False
    if lower in {"mehr anzeigen", "mehr erfahren", "apply now", "bewerben", "jobs", "karriere", "stellenangebote"}:
        return False
    if re.search(r"cookie|datenschutz|impressum|privacy|newsletter|login|registrieren", lower):
        return False
    return True


def cms_location_from_card(card) -> str:
    for candidate in card.select(".text-dark-emphasis, [class*=location], [class*=standort]"):
        text = re.sub(r"\s+", " ", candidate.get_text(" ", strip=True)).strip()
        if text and not re.search(r"anzeigen|bewerben", text, re.I):
            return normalize_cms_city(text)
    return ""


def normalize_cms_city(value: str) -> str:
    text = re.sub(r"\s+", " ", (value or "").strip())
    text = re.sub(r",?\s*DEUTSCHLAND$", "", text, flags=re.I).strip()
    if re.search(r"mehrere standorte", text, re.I):
        return "Mehrere Standorte"
    replacements = {
        "BERLIN": "Berlin",
        "BRÜSSEL": "Brüssel",
        "DÜSSELDORF": "Düsseldorf",
        "FRANKFURT": "Frankfurt",
        "HAMBURG": "Hamburg",
        "KÖLN": "Köln",
        "LEIPZIG": "Leipzig",
        "MÜNCHEN": "München",
        "STUTTGART": "Stuttgart",
    }
    return replacements.get(text.upper(), text.title())


def fieldfisher_city(card) -> str:
    office = (card.get("data-office") or "").strip()
    if office:
        return office.replace("-", " ").title()
    text = card.get_text(" ", strip=True)
    match = re.search(r"\|\s*([^|]+)$", text)
    return match.group(1).strip() if match else ""


def is_dlapiper_germany_job(title: str) -> bool:
    lower = title.lower()
    germany_markers = (
        " germany",
        "munich",
        "berlin",
        "hamburg",
        "frankfurt",
        "düsseldorf",
        "dusseldorf",
        "cologne",
        "köln",
    )
    if not any(marker in lower for marker in germany_markers):
        return False
    foreign_markers = (
        "united kingdom",
        "australia",
        "netherlands",
        "belgium",
        "amsterdam",
        "brussels",
        "leeds",
        "melbourne",
        "perth",
    )
    return not any(marker in lower for marker in foreign_markers)


def dlapiper_city(title: str) -> str:
    for marker, city in (
        ("Munich", "Munich"),
        ("Berlin", "Berlin"),
        ("Hamburg", "Hamburg"),
        ("Frankfurt", "Frankfurt"),
        ("Düsseldorf", "Düsseldorf"),
        ("Dusseldorf", "Düsseldorf"),
        ("Cologne", "Köln"),
        ("Köln", "Köln"),
    ):
        if marker.lower() in title.lower():
            return city
    if "Germany" in title:
        return "Germany"
    return ""


def clean_dlapiper_title(title: str) -> str:
    return re.sub(r"\s+", " ", title).strip()


def normalize_dlapiper_city(value: str) -> str:
    text = re.sub(r"\s+", " ", (value or "").strip())
    text = re.sub(r",?\s*Germany$", "", text, flags=re.I).strip()
    replacements = {"Dusseldorf": "Düsseldorf", "Cologne": "Köln"}
    return replacements.get(text, text)


def slugify_for_url(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9ÄÖÜäöüß]+", "-", value or "").strip("-")
    return quote(text)


def normalize_location_list(value) -> str:
    if isinstance(value, list):
        cleaned = []
        for item in value:
            text = re.sub(r"\s+", " ", str(item or "")).strip()
            text = re.sub(r",?\s*DEU$", "", text, flags=re.I).strip()
            if text and text not in cleaned:
                cleaned.append(text)
        return ", ".join(cleaned)
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return re.sub(r",?\s*DEU$", "", text, flags=re.I).strip()


def _html_from_response(response: requests.Response) -> str:
    content_type = response.headers.get("content-type", "")
    if "json" not in content_type.lower():
        return response.text
    data = response.json()
    if isinstance(data, str):
        return data
    if isinstance(data, dict):
        for key in ("results", "html", "content", "SearchResults", "jobs"):
            value = data.get(key)
            if isinstance(value, str):
                return value
    return response.text


def _radancy_total(html: str, default: int) -> int:
    match = re.search(r"data-total=[\"']?(\d+)", html or "")
    if match:
        return int(match.group(1))
    return default


def _city_from_radancy_url(url: str) -> str:
    path = urlparse(url).path.strip("/").split("/")
    if "job" not in path:
        return ""
    index = path.index("job")
    if index + 1 >= len(path):
        return ""
    city = path[index + 1].replace("-", " ").strip()
    replacements = {
        "frankfurt am main": "Frankfurt am Main",
        "dusseldorf": "Düsseldorf",
        "munich": "München",
        "hamburg": "Hamburg",
    }
    return replacements.get(city.lower(), city.title())


def _nearby_text(node, class_pattern: str) -> str:
    container = node
    for _ in range(4):
        if not container:
            break
        match = container.find(class_=re.compile(class_pattern, re.I))
        if match:
            text = re.sub(r"\s+", " ", match.get_text(" ", strip=True)).strip()
            if 2 < len(text) < 100 and not re.search(r"mehr|anzeigen|filter", text, re.I):
                return text
        container = container.parent
    return ""

from __future__ import annotations

import argparse
import html
from dataclasses import dataclass
from datetime import date
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

import requests

from kanzlei_discovery.diagnostics import write_no_job_diagnosis
from kanzlei_discovery.merge import merge_jobs
from kanzlei_discovery.models import MASTER_COLUMNS, Job
from kanzlei_discovery.storage import load_master, save_master, write_csv_rows


REPORT_COLUMNS = ["feed", "source", "input_rows", "new", "updated", "skipped", "master_before", "master_after"]
DEFAULT_FEEDS = ["heyrecruit=https://www.heyrecruit.de/jobs/companyJobsXml/4741"]


@dataclass(frozen=True)
class XmlFeed:
    source: str
    url: str


def main() -> int:
    parser = argparse.ArgumentParser(description="Import configured XML job feeds into jobs_master.csv.")
    parser.add_argument("--feed", action="append", default=[], help="Feed in the form source=https://example.com/feed.xml")
    parser.add_argument("--master-file", default="jobs_master.csv")
    parser.add_argument("--public-export", default="media/jobs_master_public.csv")
    parser.add_argument("--report-file", default="")
    parser.add_argument("--no-job-report", default="reports/kanzleien_ohne_jobs_diagnose.csv")
    parser.add_argument("--target-file", default="target_firms_full.csv")
    parser.add_argument("--date", default=date.today().isoformat())
    args = parser.parse_args()

    feeds = parse_feeds(args.feed or DEFAULT_FEEDS)
    report_file = Path(args.report_file) if args.report_file else Path(f"reports/xml_feed_import_report_{args.date}.csv")
    master = load_master(args.master_file, args.date)
    report_rows = []

    for feed in feeds:
        before = len(master)
        xml = fetch_feed(feed.url)
        jobs = parse_feed_jobs(xml, feed, args.date)
        master, stats = merge_jobs(master, jobs, args.date)
        after = len(master)
        report_rows.append(
            {
                "feed": feed.url,
                "source": feed.source,
                "input_rows": str(len(jobs)),
                "new": str(stats["new"]),
                "updated": str(stats["updated"]),
                "skipped": str(stats["skipped"]),
                "master_before": str(before),
                "master_after": str(after),
            }
        )
        print(f"XML_IMPORT {feed.source} input={len(jobs)} new={stats['new']} updated={stats['updated']} skipped={stats['skipped']}")

    if report_rows:
        save_master(args.master_file, master)
        write_csv_rows(args.public_export, master, MASTER_COLUMNS)
        write_csv_rows(report_file, report_rows, REPORT_COLUMNS)
        write_no_job_diagnosis(args.target_file, args.master_file, args.no_job_report, args.date)
    print(f"XML_IMPORTS imported_feeds={len(report_rows)}")
    return 0


def parse_feeds(values: list[str]) -> list[XmlFeed]:
    feeds = []
    for value in values:
        if "=" not in value:
            raise ValueError(f"Feed must use source=url format: {value}")
        source, url = value.split("=", 1)
        source = source.strip()
        url = url.strip()
        if not source or urlparse(url).scheme not in {"http", "https"}:
            raise ValueError(f"Invalid XML feed: {value}")
        feeds.append(XmlFeed(source=source, url=url))
    return feeds


def fetch_feed(url: str) -> bytes:
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    return response.content


def parse_feed_jobs(xml: bytes | str, feed: XmlFeed, today: str) -> list[Job]:
    root = ET.fromstring(xml)
    jobs = []
    for node in root.findall(".//job"):
        title = text(node, "title")
        link = text(node, "url")
        company = text(node, "company")
        city = text(node, "city")
        state = text(node, "state")
        postalcode = text(node, "postalcode")
        location = format_location(city, state, postalcode)
        publication_date = parse_feed_date(text(node, "publication_date"), today)
        reference = text(node, "referencenumber")
        source = f"xml:{feed.source}"
        jobs.append(
            Job(
                title=title,
                link=link,
                firm=company,
                city=location,
                source=source,
                first_seen=publication_date,
                last_seen=today,
                posting_date=publication_date,
                source_url=feed.url,
            )
        )
        if reference and not link:
            jobs[-1].link = f"{feed.url}#job-{reference}"
    return jobs


def text(node: ET.Element, name: str) -> str:
    child = node.find(name)
    return html.unescape((child.text or "").strip()) if child is not None else ""


def format_location(city: str, state: str, postalcode: str) -> str:
    parts = []
    if postalcode and city:
        parts.append(f"{postalcode} {city}")
    elif city:
        parts.append(city)
    if state and state.casefold() != city.casefold():
        parts.append(state)
    return ", ".join(parts)


def parse_feed_date(value: str, default: str) -> str:
    value = (value or "").strip()
    if not value:
        return default
    try:
        return parsedate_to_datetime(value).date().isoformat()
    except (TypeError, ValueError, IndexError, OverflowError):
        return default


if __name__ == "__main__":
    raise SystemExit(main())

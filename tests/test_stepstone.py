import json
from pathlib import Path

from kanzlei_discovery.stepstone import (
    SearchSpec,
    StepstoneClient,
    canonical_job_url,
    item_to_export_row,
    load_resumable_checkpoint,
    merge_search_rows,
    parse_result_state,
    save_checkpoint,
    search_fingerprint,
    write_export_atomic,
)
import pytest


class FakeResponse:
    def __init__(self, html: str, status_code: int = 200):
        self.text = html
        self.status_code = status_code
        self.headers = {"content-type": "text/html; charset=utf-8"}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, pages):
        self.pages = iter(pages)
        self.headers = {}
        self.urls = []

    def get(self, url, timeout):
        self.urls.append(url)
        return FakeResponse(next(self.pages))


def make_page(page: int, page_count: int, items: list[dict]) -> str:
    state = {
        "searchResults": {
            "items": items,
            "pagination": {
                "page": page,
                "pageCount": page_count,
                "totalCount": page_count * len(items),
            },
            "unifiedPagination": {
                "links": {
                    "next": f"https://www.stepstone.de/jobs/legal?page={page + 1}"
                    if page < page_count
                    else ""
                }
            },
        }
    }
    return (
        "<html><script>window.__PRELOADED_STATE__ = window.__PRELOADED_STATE__ || {};"
        'window.__PRELOADED_STATE__["app-unifiedResultlist"] = '
        + json.dumps(state)
        + ";</script></html>"
    )


def item(job_id: int, title: str = "Rechtsanwalt (m/w/d)") -> dict:
    return {
        "id": job_id,
        "harmonisedId": f"harmonised-{job_id}",
        "title": title,
        "companyName": "Muster & Partner",
        "location": "Berlin",
        "url": f"/stellenangebote--job--{job_id}-inline.html?rltr=tracking",
        "datePosted": "2026-09-20T08:30:00+02:00",
        "textSnippet": "Beschreibung",
    }


def test_parses_embedded_result_state():
    state = parse_result_state(make_page(1, 2, [item(1)]))

    assert state["searchResults"]["pagination"]["pageCount"] == 2
    assert state["searchResults"]["items"][0]["id"] == 1


def test_canonical_job_url_removes_tracking_parameters():
    url = canonical_job_url("/stellenangebote--job--1-inline.html?rltr=1_1_25")

    assert url == "https://www.stepstone.de/stellenangebote--job--1-inline.html"


def test_fetch_search_paginates_and_deduplicates_ids():
    session = FakeSession(
        [
            make_page(1, 2, [item(1), item(2)]),
            make_page(2, 2, [item(2), item(3)]),
        ]
    )
    client = StepstoneClient(session=session, delay_seconds=0)

    result = client.fetch_search(
        SearchSpec("Legal", "https://www.stepstone.de/jobs/legal"), "2026-09-21"
    )

    assert [row["Stepstone_ID"] for row in result.rows] == ["1", "2", "3"]
    assert result.raw_rows == 4
    assert result.duplicates == 1
    assert len(session.urls) == 2


def test_export_row_matches_existing_stepstone_import_contract():
    row = item_to_export_row(item(42), "Legal", "2026-09-21")

    assert row is not None
    assert row["Job_Titel"] == "Rechtsanwalt (m/w/d)"
    assert row["Name_des_Unternehmens"] == "Muster & Partner"
    assert row["Standort"] == "Berlin"
    assert row["Erscheinen"] == "2026-09-20T08:30:00+02:00"
    assert row["Scrape_Date"] == "2026-09-21"


def test_cross_query_duplicates_keep_all_query_names():
    first = item_to_export_row(item(1), "Query A", "2026-09-21")
    second = item_to_export_row(item(1), "Query B", "2026-09-21")
    assert first is not None and second is not None
    target = {"1": first}

    duplicates = merge_search_rows(target, [second])

    assert duplicates == 1
    assert target["1"]["Search_Query"] == "Query A | Query B"


def test_incomplete_checkpoint_can_resume(tmp_path: Path):
    searches = [SearchSpec("Legal", "https://www.stepstone.de/jobs/legal")]
    fingerprint = search_fingerprint(searches)
    checkpoint = tmp_path / "stepstone.json"
    row = item_to_export_row(item(1), "Legal", "2026-09-21")
    assert row is not None
    save_checkpoint(
        checkpoint,
        scrape_date="2026-09-21",
        fingerprint=fingerprint,
        next_query_index=1,
        rows=[row],
        stats={"queries": 1, "pages": 2, "raw_rows": 3, "duplicates": 1},
        completed=False,
    )

    index, rows, stats = load_resumable_checkpoint(
        checkpoint, "2026-09-21", fingerprint
    )

    assert index == 1
    assert list(rows) == ["1"]
    assert stats["raw_rows"] == 3


def test_refuses_empty_export(tmp_path: Path):
    with pytest.raises(RuntimeError, match="empty Stepstone export"):
        write_export_atomic(tmp_path / "empty.csv", [])

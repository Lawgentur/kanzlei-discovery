from kanzlei_discovery.merge import merge_jobs, remove_stale
from kanzlei_discovery.models import Job


def test_merge_preserves_first_seen_and_updates_last_seen():
    master = [
        {
            "Titel": "Rechtsanwalt (m/w/d)",
            "Link": "https://example.com/job/1",
            "Kanzlei": "Example",
            "Stadt": "Berlin",
            "Quelle": "legacy",
            "first_seen": "2026-05-01",
            "last_seen": "2026-05-10",
        }
    ]
    merged, stats = merge_jobs(master, [Job("Rechtsanwalt (m/w/d)", "https://example.com/job/1", "Example", "Berlin", "dom")], "2026-06-02")
    assert stats["updated"] == 1
    assert merged[0]["first_seen"] == "2026-05-01"
    assert merged[0]["last_seen"] == "2026-06-02"


def test_merge_adds_new_valid_job_and_skips_bad_rows():
    merged, stats = merge_jobs([], [Job("Kontakt", "https://example.com/contact", "Example"), Job("Associate Corporate (m/w/d)", "https://example.com/jobs/2", "Example")], "2026-06-02")
    assert stats == {"new": 1, "updated": 0, "skipped": 1}
    assert merged[0]["Titel"] == "Associate Corporate (m/w/d)"


def test_merge_keeps_distinct_trusted_board_links_with_same_title_and_city():
    jobs = [
        Job("Facility Specialist", "https://careers.aoshearman.com/en/job/frankfurt/1", "A&O Shearman", "Frankfurt", "radancy:aoshearman"),
        Job("Facility Specialist", "https://careers.aoshearman.com/en/job/frankfurt/2", "A&O Shearman", "Frankfurt", "radancy:aoshearman"),
    ]
    merged, stats = merge_jobs([], jobs, "2026-06-19")
    assert stats == {"new": 2, "updated": 0, "skipped": 0}
    assert len(merged) == 2


def test_remove_stale():
    rows = [
        {"last_seen": "2026-06-01"},
        {"last_seen": "2026-04-01"},
    ]
    kept, deleted = remove_stale(rows, "2026-06-02", 30)
    assert len(kept) == 1
    assert deleted == 1

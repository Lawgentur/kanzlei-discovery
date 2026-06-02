from kanzlei_discovery.quality import canonical_link, is_likely_job_title, normalize_job_row


def test_canonical_link_removes_tracking():
    assert canonical_link("HTTPS://Example.com/jobs/123/?utm_source=x&foo=bar#apply") == "https://example.com/jobs/123?foo=bar"


def test_rejects_navigation_and_accepts_job_titles():
    assert not is_likely_job_title("Mehr erfahren", "https://example.com/karriere")
    assert not is_likely_job_title("Real Estate", "https://example.com/rechtsgebiete/real-estate")
    assert is_likely_job_title("Rechtsanwalt Arbeitsrecht (m/w/d)", "https://example.com/jobs/1")


def test_normalize_job_row_maps_legacy_columns():
    row = {
        "Kanzlei": "Test LLP",
        "Jobtitel": "Rechtsanwaltsfachangestellte (m/w/d)",
        "Location": "Berlin",
        "Link": "https://test.example/job?id=1&utm_campaign=x",
        "Erstes_Funddatum": "01.06.2026",
    }
    normalized = normalize_job_row(row, "2026-06-02")
    assert normalized["Titel"] == "Rechtsanwaltsfachangestellte (m/w/d)"
    assert normalized["Link"] == "https://test.example/job?id=1"
    assert normalized["first_seen"] == "2026-06-01"
    assert normalized["last_seen"] == "2026-06-02"


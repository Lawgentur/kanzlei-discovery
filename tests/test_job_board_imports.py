from pathlib import Path

import pytest

from scripts.import_job_boards import discover_import_files, load_jobs


def test_discovers_csv_and_excel_board_exports(tmp_path: Path):
    indeed = tmp_path / "Indeed Export.csv"
    stepstone = tmp_path / "Stepstone Export.xlsx"
    ignored = tmp_path / "notes.csv"
    indeed.touch()
    stepstone.touch()
    ignored.touch()

    discovered = {(source, path.name) for source, path in discover_import_files(tmp_path)}

    assert discovered == {
        ("indeed", "Indeed Export.csv"),
        ("stepstone", "Stepstone Export.xlsx"),
    }


def test_loads_semicolon_separated_octoparse_csv(tmp_path: Path):
    export = tmp_path / "Indeed Export.csv"
    export.write_text(
        "Job_Title;Job_URL;Company_Name;Location;Posted_Date\n"
        "Rechtsanwalt (m/w/d);https://example.com/job/1;Muster & Partner;München;2026-08-13\n",
        encoding="utf-8-sig",
    )

    jobs = load_jobs("indeed", export, "2026-08-13")

    assert len(jobs) == 1
    assert jobs[0].title == "Rechtsanwalt (m/w/d)"
    assert jobs[0].firm == "Muster & Partner"
    assert jobs[0].city == "München"
    assert jobs[0].first_seen == "2026-08-13"
    assert jobs[0].posting_date == "2026-08-13"


def test_rejects_csv_with_unexpected_columns(tmp_path: Path):
    export = tmp_path / "Stepstone Export.csv"
    export.write_text("title,url\nAssociate,https://example.com/job/1\n", encoding="utf-8")

    with pytest.raises(ValueError, match="missing required stepstone columns"):
        load_jobs("stepstone", export, "2026-08-13")

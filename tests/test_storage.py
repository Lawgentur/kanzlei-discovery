from pathlib import Path

from kanzlei_discovery.storage import load_firms, save_firms
from kanzlei_discovery.models import Firm


def test_firms_deduplicate_by_domain(tmp_path: Path):
    path = tmp_path / "firms.csv"
    save_firms(
        path,
        [
            Firm("A", "example.com", "https://example.com/jobs"),
            Firm("A duplicate", "example.com", ""),
            Firm("B", "b.example", ""),
        ],
    )
    firms = load_firms(path)
    assert [firm.name for firm in firms] == ["A", "B"]


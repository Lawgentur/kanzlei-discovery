from __future__ import annotations

from dataclasses import dataclass
from datetime import date


MASTER_COLUMNS = [
    "Titel",
    "Link",
    "Kanzlei",
    "Stadt",
    "Quelle",
    "first_seen",
    "last_seen",
    "posting_date",
    "imported_at",
    "scraped_at",
    "last_checked_at",
    "source_url",
    "status",
    "canonical_firm_id",
]
FIRM_COLUMNS = ["Unternehmensname", "Domainname des Unternehmens", "Jobboard_URL"]


@dataclass(frozen=True)
class Firm:
    name: str
    domain: str = ""
    jobboard_url: str = ""

    @classmethod
    def from_row(cls, row: dict[str, str]) -> "Firm":
        return cls(
            name=(row.get("Unternehmensname") or row.get("Kanzlei") or "").strip(),
            domain=(row.get("Domainname des Unternehmens") or row.get("Domain") or "").strip(),
            jobboard_url=(row.get("Jobboard_URL") or row.get("Karriere_URL") or "").strip(),
        )


@dataclass
class Job:
    title: str
    link: str
    firm: str
    city: str = ""
    source: str = "kanzlei"
    first_seen: str = ""
    last_seen: str = ""
    posting_date: str = ""
    source_url: str = ""
    status: str = "active"

    def to_master_row(self, today: str | None = None) -> dict[str, str]:
        stamp = today or date.today().isoformat()
        return {
            "Titel": self.title.strip(),
            "Link": self.link.strip(),
            "Kanzlei": self.firm.strip(),
            "Stadt": self.city.strip(),
            "Quelle": self.source.strip() or "kanzlei",
            "first_seen": self.first_seen.strip() or stamp,
            "last_seen": self.last_seen.strip() or stamp,
            "posting_date": self.posting_date.strip() or self.first_seen.strip() or stamp,
            "imported_at": stamp,
            "scraped_at": stamp,
            "last_checked_at": stamp,
            "source_url": self.source_url.strip() or self.link.strip(),
            "status": self.status.strip() or "active",
            "canonical_firm_id": "",
        }

from kanzlei_discovery.models import Firm
from kanzlei_discovery.special_adapters import parse_cms_jobs, parse_cms_reader, parse_radancy_jobs, parse_wts_jobs


def test_parse_radancy_jobs_extracts_city_from_url():
    html = """
    <li><a href="/en/job/frankfurt-am-main/regulatory-knowledge-lawyer/3392/1">
    Regulatory Knowledge Lawyer (m/w/d)
    </a></li>
    """
    jobs = parse_radancy_jobs(html, Firm("A&O Shearman"), "https://careers.aoshearman.com", "radancy:aoshearman")
    assert len(jobs) == 1
    assert jobs[0].city == "Frankfurt am Main"
    assert jobs[0].source == "radancy:aoshearman"


def test_parse_wts_jobs_reads_listing_cards():
    html = """
    <div class="jobsResult">
      <a class="jobsResult-link" href="/de-de/jobs/rechtsreferendar">
        <span class="jobsResult-title">Rechtsreferendar (w/m/d) Internationales Unternehmenssteuerrecht</span>
      </a>
      <span class="jobsResult-location">Berlin</span>
    </div>
    """
    jobs = parse_wts_jobs(html, Firm("WTS Legal Rechtsanwaltsgesellschaft mbH"), "https://wts.com")
    assert len(jobs) == 1
    assert jobs[0].title.startswith("Rechtsreferendar")
    assert jobs[0].city == "Berlin"


def test_parse_cms_jobs_filters_career_links():
    html = """
    <div class="expert-card">
      <div class="fs-3 fw-medium">Rechtsanwalt Corporate/M&A (m/w/d)</div>
      <div class="text-dark-emphasis">MÜNCHEN, DEUTSCHLAND</div>
      <a href="/de/deu/stellenausschreibungen/rechtsanwalt-corporate-id-1">Anzeigen</a>
    </div>
    <a href="/de/deu/insights">News</a>
    """
    jobs = parse_cms_jobs(html, Firm("CMS"), "https://cms.law/de/deu/stellenausschreibungen")
    assert len(jobs) == 1
    assert jobs[0].firm == "CMS"
    assert jobs[0].city == "München"


def test_parse_cms_reader_extracts_markdown_cards():
    text = """
    Rechtsanwälte (m/w/d) für den Bereich Arbeitsrecht

     DÜSSELDORF, DEUTSCHLAND

    [Anzeigen](https://cms.law/de/deu/stellenausschreibungen/arbeitsrecht-id-1)
    """
    jobs = parse_cms_reader(text, Firm("CMS"))
    assert len(jobs) == 1
    assert jobs[0].city == "Düsseldorf"

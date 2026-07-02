from kanzlei_discovery.models import Firm
from kanzlei_discovery.strategy import analyze_firm_strategy, detect_page_signals


class FakeResponse:
    def __init__(self, text, url="https://example.com/jobs", status_code=200):
        self.text = text
        self.url = url
        self.status_code = status_code

    def raise_for_status(self):
        return None


class FakeSession:
    headers = {}

    def __init__(self, response):
        self.response = response

    def get(self, url, timeout=25):
        return self.response


def test_strategy_detects_special_adapter_without_fetching_page():
    firm = Firm("DLA Group", "dla.com", "https://careers.dlapiper.com/jobs/index.html")
    row = analyze_firm_strategy(FakeSession(FakeResponse("")), firm, "2026-06-19")
    assert row["strategy"] == "special_api"
    assert row["adapter"] == "api:dlapiper"


def test_strategy_detects_dom_jobs():
    html = '<a href="/jobs/rechtsanwalt">Rechtsanwalt Arbeitsrecht (m/w/d)</a>'
    firm = Firm("Test Kanzlei", "example.com", "https://example.com/jobs")
    row = analyze_firm_strategy(FakeSession(FakeResponse(html)), firm, "2026-06-19")
    assert row["strategy"] == "dom"
    assert row["html_job_count"] == "1"


def test_detect_page_signals_finds_load_more_and_js_app():
    signals = detect_page_signals('<div id="app"></div><button>Mehr Ergebnisse laden</button><script src="/app.js"></script>', "https://example.com/jobs")
    assert "load_more" in signals
    assert "js_app" in signals

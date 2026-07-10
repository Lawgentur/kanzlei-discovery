from scripts.import_xml_feeds import XmlFeed, parse_feed_date, parse_feed_jobs


def test_parse_heyrecruit_feed_maps_master_fields():
    xml = """
    <source>
      <publisher>Heyrecruit</publisher>
      <job>
        <title><![CDATA[Datenschutzkoordinator (m/w/d)]]></title>
        <publication_date><![CDATA[Tue, 23 Jun 26 17:18:28]]></publication_date>
        <referencenumber><![CDATA[135218_47720]]></referencenumber>
        <url><![CDATA[https://fps-law.de/de/karriere/datenschutzkoordinator-mwd-berlin-4698?utm_source=heyrecruit]]></url>
        <company><![CDATA[FPS Rechtsanwaltsgesellschaft mbH &amp; Co. KG]]></company>
        <city><![CDATA[Berlin]]></city>
        <state><![CDATA[Berlin]]></state>
        <postalcode><![CDATA[10719]]></postalcode>
      </job>
    </source>
    """
    jobs = parse_feed_jobs(xml, XmlFeed("heyrecruit", "https://example.com/feed.xml"), "2026-07-10")
    assert len(jobs) == 1
    assert jobs[0].title == "Datenschutzkoordinator (m/w/d)"
    assert jobs[0].firm == "FPS Rechtsanwaltsgesellschaft mbH & Co. KG"
    assert jobs[0].city == "10719 Berlin"
    assert jobs[0].first_seen == "2026-06-23"
    assert jobs[0].last_seen == "2026-07-10"
    assert jobs[0].posting_date == "2026-06-23"
    assert jobs[0].source == "xml:heyrecruit"
    assert jobs[0].source_url == "https://example.com/feed.xml"


def test_parse_feed_date_falls_back_to_today():
    assert parse_feed_date("", "2026-07-10") == "2026-07-10"
    assert parse_feed_date("not a date", "2026-07-10") == "2026-07-10"

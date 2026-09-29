from app.services.fetcher import extract_html
from app.services.quality import score_source


def test_extract_html_removes_scripts_and_navigation() -> None:
    html = """
    <html><head><title>EV Market Report</title><script>ignore me</script></head>
    <body><nav>Menu content should disappear completely</nav><main>
    <h1>Indian EV Market</h1>
    <p>This is a sufficiently long evidence paragraph describing electric vehicle growth.</p>
    </main></body></html>
    """
    title, text = extract_html(html)
    assert title == "EV Market Report"
    assert "electric vehicle growth" in text
    assert "ignore me" not in text
    assert "Menu content" not in text


def test_government_source_scores_above_unknown_blog() -> None:
    text = "evidence " * 1_000
    government = score_source("https://example.gov.in/report", text)
    blog = score_source("https://unknown.example/post", text)
    assert government.score > blog.score
    assert government.details["source_type"] == "government"

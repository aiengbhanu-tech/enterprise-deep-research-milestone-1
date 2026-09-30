from app.services.tracing import summarize


def test_trace_summary_records_counts_without_raw_content() -> None:
    summary = summarize(
        {
            "status": "researched",
            "evidence": [{"content": "sensitive passage"}, {"content": "another"}],
            "query": "private user query",
        }
    )
    assert summary["evidence_count"] == 2
    assert summary["status"] == "researched"
    assert "private user query" not in str(summary)
    assert "sensitive passage" not in str(summary)

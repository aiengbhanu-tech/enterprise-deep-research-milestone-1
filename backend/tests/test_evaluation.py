from app.services.evaluation import calculate_overall_score


def test_high_quality_research_passes() -> None:
    result = calculate_overall_score(
        {
            "citation_validity": 1.0,
            "citation_coverage": 1.0,
            "source_quality": 0.85,
            "source_diversity": 0.8,
            "research_coverage": 0.9,
            "cost_efficiency": 0.95,
            "latency": 0.8,
        }
    )
    assert result.passed is True
    assert result.overall >= 0.8


def test_unsupported_citations_fail_gate() -> None:
    result = calculate_overall_score(
        {
            "citation_validity": 0.5,
            "citation_coverage": 1.0,
            "source_quality": 0.9,
            "source_diversity": 0.9,
            "research_coverage": 0.9,
            "cost_efficiency": 1.0,
            "latency": 1.0,
        }
    )
    assert result.passed is False
    assert "Citation validity is below 0.80" in result.failure_reasons


def test_missing_research_coverage_fails_gate() -> None:
    result = calculate_overall_score(
        {
            "citation_validity": 1.0,
            "citation_coverage": 1.0,
            "source_quality": 0.9,
            "source_diversity": 0.9,
            "research_coverage": 0.4,
            "cost_efficiency": 1.0,
            "latency": 1.0,
        }
    )
    assert result.passed is False
    assert "Research coverage is below 0.70" in result.failure_reasons

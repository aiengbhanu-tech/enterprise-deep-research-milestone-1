from app.services.critic import analyze_coverage, build_review, detect_contradictions

PLAN = [{"id": "market", "question": "Measure market share"}]


def test_coverage_is_sufficient_with_diverse_high_quality_evidence() -> None:
    evidence = [
        {
            "id": f"e-{index}",
            "question": "Measure market share",
            "content": "Supporting passage without a percentage.",
            "source": f"https://source-{index % 2}.example/report",
            "source_quality": 0.9,
        }
        for index in range(4)
    ]

    coverage = analyze_coverage(PLAN, evidence)

    assert coverage[0]["status"] == "sufficient"
    assert coverage[0]["independent_sources"] == 2


def test_missing_evidence_generates_followup_queries() -> None:
    result = build_review(PLAN, [], iteration=1, max_iterations=3)

    assert result.critic["decision"] == "continue"
    assert result.gaps[0]["question_id"] == "market"
    assert len(result.critic["follow_up_queries"]) == 2


def test_iteration_limit_finishes_with_limitations() -> None:
    result = build_review(PLAN, [], iteration=3, max_iterations=3)

    assert result.critic["decision"] == "complete_with_limitations"


def test_conflicting_percentages_are_recorded() -> None:
    evidence = [
        {
            "id": "11111111-1111-1111-1111-111111111111",
            "question": "Measure market share",
            "content": "The market share was 35% during the period.",
            "source": "https://one.example/report",
        },
        {
            "id": "22222222-2222-2222-2222-222222222222",
            "question": "Measure market share",
            "content": "The market share was 29% during the period.",
            "source": "https://two.example/report",
        },
    ]

    contradictions = detect_contradictions(evidence)

    assert len(contradictions) == 1
    assert contradictions[0]["status"] == "unresolved"
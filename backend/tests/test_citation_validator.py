from app.services.citation_validator import repair_report_citations, validate_report

EVIDENCE = [
    {
        "id": "11111111-1111-1111-1111-111111111111",
        "source_id": "22222222-2222-2222-2222-222222222222",
        "content": "India electric vehicle registrations increased strongly as two wheeler adoption expanded.",
    }
]


def test_validator_accepts_known_supported_evidence() -> None:
    report = {
        "sections": [
            {
                "key": "market",
                "body": "India electric vehicle registrations increased as two wheeler adoption expanded.",
                "citations": [EVIDENCE[0]["id"]],
            }
        ]
    }
    result = validate_report(report, EVIDENCE)
    assert result.valid is True
    assert result.citations[0]["status"] == "supported"


def test_validator_rejects_unknown_evidence() -> None:
    report = {
        "sections": [
            {
                "key": "market",
                "body": "A substantive market claim that needs reliable supporting evidence." * 2,
                "citations": ["unknown"],
            }
        ]
    }
    result = validate_report(report, EVIDENCE)
    assert result.valid is False
    assert result.issues[0]["type"] == "unknown_evidence"


def test_repair_replaces_unknown_citation() -> None:
    report = {
        "sections": [
            {
                "key": "market",
                "body": "India electric vehicle registrations increased with two wheeler adoption.",
                "citations": ["unknown"],
            }
        ]
    }
    repaired = repair_report_citations(report, EVIDENCE)
    assert repaired["sections"][0]["citations"] == [EVIDENCE[0]["id"]]

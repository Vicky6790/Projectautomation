from app.models import AnalysisReport, SowFinding
from app.sow.classify import analyze_scope_of_work, ground_report

_PRECISE = """
Scope of Work — Customer Portal
The vendor shall deliver a customer portal by the Go-Live date of 15 December 2026.
Acceptance criteria: UAT sign-off by the bank project manager against the test cases in Annex A.
Service levels: Severity 1 incidents receive a 15-minute response and 4-hour restore; uptime target is 99.5%.
Out of scope: mobile native applications, ATM integration, and data migration from legacy systems.
Change requests follow the change-control process in Schedule 2; variations require written approval.
Roles and responsibilities: the vendor is responsible for build; the bank is accountable for UAT and production access.
Dependencies: the bank shall provide VPN access and test data ten working days before SIT.
Assumptions: it is assumed that production hardware is already installed in the bank data centre.
"""


def test_empty_text_has_no_invented_findings() -> None:
    report = analyze_scope_of_work("   ")
    assert report.gray_areas == []
    assert report.risks == []
    assert report.missing_requirements == []
    assert "no extractable" in report.summary.casefold()


def test_short_precise_text_does_not_invent_gray_areas_or_gaps() -> None:
    report = analyze_scope_of_work("The vendor shall deliver a portal.")
    assert report.gray_areas == []
    assert report.missing_requirements == []
    assert report.risks == []


def test_vague_language_is_quoted_from_the_document() -> None:
    report = analyze_scope_of_work("The vendor shall deliver a customer portal in a reasonable time.")
    assert report.gray_areas
    assert "reasonable" in report.gray_areas[0].evidence.casefold()
    assert report.missing_requirements == []


def test_substantial_document_flags_only_absent_clauses() -> None:
    body = (
        "Scope of Work for the core banking interface. " * 8
        + "The vendor shall deliver the interface. Client shall provide VPN access. "
        "It is assumed that test data already exists."
    )
    report = analyze_scope_of_work(body)
    titles = {item.title for item in report.missing_requirements}
    assert any("Acceptance" in title for title in titles)
    assert report.dependencies
    assert "client shall" in report.dependencies[0].evidence.casefold()
    assert report.assumptions
    assert not any("timeline" in title.casefold() and "go-live" in body.casefold() for title in titles)


def test_precise_scope_has_no_false_missing_or_gray() -> None:
    report = analyze_scope_of_work(_PRECISE)
    assert report.gray_areas == []
    assert report.missing_requirements == []
    assert report.dependencies
    assert report.assumptions
    assert "vpn" in report.dependencies[0].evidence.casefold()


def test_ground_report_drops_ungrounded_ai_findings() -> None:
    invented = AnalysisReport(
        summary="The moon colony payment terms are unclear.",
        gray_areas=[
            SowFinding(
                category="gray_areas",
                title="Undefined moon colony",
                description="Payment for the lunar base is TBD.",
                recommendation="Define it.",
                evidence="Payment for the lunar base is TBD.",
            )
        ],
        risks=[],
    )
    kept = ground_report(invented, "The vendor shall deliver a portal in a reasonable time.")
    assert kept.gray_areas == []
    assert "moon" not in kept.summary.casefold()


def test_ground_report_keeps_ai_finding_when_source_supports_it() -> None:
    source = "The vendor shall deliver a portal in a reasonable time."
    report = AnalysisReport(
        gray_areas=[
            SowFinding(
                category="gray_areas",
                title="Undefined reasonable time",
                description="Term 'reasonable' is undefined",
                recommendation="Replace with a dated milestone.",
            )
        ]
    )
    kept = ground_report(report, source)
    assert kept.gray_areas
    assert "reasonable" in kept.gray_areas[0].evidence.casefold()

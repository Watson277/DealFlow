from app.models.enums import CapabilityStatus
from app.schemas.proposal import ProposalDraft, ProposalRequirementResponse
from app.services.proposal_renderer import ProposalMarkdownRenderer


def test_proposal_markdown_renderer_builds_response_matrix() -> None:
    draft = ProposalDraft(
        title="StellarCloud Proposal",
        executive_summary="A concise executive summary.",
        requirement_responses=[
            ProposalRequirementResponse(
                requirement_key="REQ-0001",
                requirement="Support SAML | SSO",
                capability_status=CapabilityStatus.SUPPORTED,
                response="Supported by the platform.",
                evidence_summary="Security Guide page 1.",
                risk_or_gap=None,
            )
        ],
        technical_solution="Technical solution.",
        security_compliance="Security response.",
        sla="Subject to SLA review.",
        deployment="Deployment approach.",
        risks_and_gaps="No material gap identified.",
        commercial_notes="Commercial review required.",
    )

    markdown = ProposalMarkdownRenderer().render(draft)

    assert markdown.startswith("# StellarCloud Proposal")
    assert "## Requirement Response Matrix" in markdown
    assert "Support SAML \\| SSO" in markdown
    assert "SUPPORTED" in markdown
    assert markdown.endswith("\n")

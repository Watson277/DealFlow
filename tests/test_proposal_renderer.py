from app.models.enums import CapabilityStatus
from app.proposals.markdown_renderer import ProposalMarkdownRenderer
from app.schemas.proposal import ProposalDraft, ProposalRequirementResponse


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
    assert "## 需求响应矩阵" in markdown
    assert "Support SAML \\| SSO" in markdown
    assert "| 支持 |" in markdown
    assert "| 需求 | 支持情况 | 回复 | 证据摘要 | 风险与差距 |" in markdown
    assert "未识别出风险或差距" in markdown
    assert "## 方案摘要" in markdown
    assert "## 商务说明" in markdown
    assert draft.requirement_responses[0].capability_status == CapabilityStatus.SUPPORTED
    assert markdown.endswith("\n")

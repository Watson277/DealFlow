from app.models.enums import CapabilityStatus
from app.schemas.proposal import ProposalDraft

CAPABILITY_LABELS = {
    CapabilityStatus.SUPPORTED: "支持",
    CapabilityStatus.PARTIALLY_SUPPORTED: "部分支持",
    CapabilityStatus.UNSUPPORTED: "不支持",
    CapabilityStatus.ENTERPRISE_ONLY: "仅企业版支持",
    CapabilityStatus.REQUIRES_CUSTOMIZATION: "需要定制",
    CapabilityStatus.NEED_REVIEW: "待确认",
}


class ProposalMarkdownRenderer:
    def render(self, draft: ProposalDraft) -> str:
        lines = [
            f"# {draft.title}",
            "",
            "## 方案摘要",
            "",
            draft.executive_summary.strip(),
            "",
            "## 需求响应矩阵",
            "",
            "| 需求 | 支持情况 | 回复 | 证据摘要 | 风险与差距 |",
            "|---|---|---|---|---|",
        ]
        for item in draft.requirement_responses:
            lines.append(
                "| "
                + " | ".join(
                    [
                        self._cell(f"{item.requirement_key}: {item.requirement}"),
                        self._cell(CAPABILITY_LABELS[item.capability_status]),
                        self._cell(item.response),
                        self._cell(item.evidence_summary),
                        self._cell(item.risk_or_gap or "未识别出风险或差距"),
                    ]
                )
                + " |"
            )
        lines.extend(
            [
                "",
                "## 技术方案",
                "",
                draft.technical_solution.strip(),
                "",
                "## 安全与合规",
                "",
                draft.security_compliance.strip(),
                "",
                "## 服务级别",
                "",
                draft.sla.strip(),
                "",
                "## 部署方案",
                "",
                draft.deployment.strip(),
                "",
                "## 风险与差距",
                "",
                draft.risks_and_gaps.strip(),
                "",
                "## 商务说明",
                "",
                draft.commercial_notes.strip(),
                "",
            ]
        )
        return "\n".join(lines)

    @staticmethod
    def _cell(value: str) -> str:
        return " ".join(value.strip().replace("|", "\\|").splitlines())

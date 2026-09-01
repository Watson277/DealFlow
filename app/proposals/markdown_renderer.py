from app.schemas.proposal import ProposalDraft


class ProposalMarkdownRenderer:
    def render(self, draft: ProposalDraft) -> str:
        lines = [
            f"# {draft.title}",
            "",
            "## Executive Summary",
            "",
            draft.executive_summary.strip(),
            "",
            "## Requirement Response Matrix",
            "",
            "| Requirement | Status | Response | Evidence | Risk / Gap |",
            "|---|---|---|---|---|",
        ]
        for item in draft.requirement_responses:
            lines.append(
                "| "
                + " | ".join(
                    [
                        self._cell(f"{item.requirement_key}: {item.requirement}"),
                        self._cell(item.capability_status.value),
                        self._cell(item.response),
                        self._cell(item.evidence_summary),
                        self._cell(item.risk_or_gap or "None identified"),
                    ]
                )
                + " |"
            )
        lines.extend(
            [
                "",
                "## Technical Solution",
                "",
                draft.technical_solution.strip(),
                "",
                "## Security & Compliance",
                "",
                draft.security_compliance.strip(),
                "",
                "## Service Levels",
                "",
                draft.sla.strip(),
                "",
                "## Deployment",
                "",
                draft.deployment.strip(),
                "",
                "## Risks & Gaps",
                "",
                draft.risks_and_gaps.strip(),
                "",
                "## Commercial Notes",
                "",
                draft.commercial_notes.strip(),
                "",
            ]
        )
        return "\n".join(lines)

    @staticmethod
    def _cell(value: str) -> str:
        return " ".join(value.strip().replace("|", "\\|").splitlines())

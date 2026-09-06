# ruff: noqa: E501
from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent
KNOWLEDGE_DIR = ROOT / "knowledge"
BUILD_SEED = 20260906


@dataclass(frozen=True)
class DocumentSpec:
    number: int
    filename: str
    title: str
    category: str
    version: str
    target_tokens: int
    domain: str
    core_sections: tuple[str, ...]
    superseded: bool = False


@dataclass(frozen=True)
class Fact:
    fact_id: str
    document: DocumentSpec
    section: str
    section_index: int
    status: str
    plan: str
    current_fact: str
    distractor: str
    cue: str
    critical_candidate: bool


def _sections(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split("|") if item.strip())


DOCS = (
    DocumentSpec(1, "01-platform-overview-current.md", "DealFlow Platform Overview and Current Plan Boundaries", "platform", "3.2", 18_000, "platform packaging", _sections("Edition Positioning|Business Plan Entitlements|Enterprise Plan Entitlements|Dedicated Plan Entitlements|Tenant Administration|Workspace Lifecycle|Regional Availability|Feature Flag Governance|Usage Metering|Contract Add-ons|Trial and Sandbox Boundaries|Current Release Compatibility")),
    DocumentSpec(2, "02-platform-overview-legacy.md", "DealFlow Legacy Platform Overview and Retired Plans", "platform-history", "2.4", 14_000, "legacy packaging", _sections("Document Status and Effective Period|Legacy Standard Plan|Legacy Premium Plan|Retired Unlimited Storage|Former Availability Commitment|Classic Workspace Model|Legacy Export Service|Old Regional Footprint|Retired Guest Licensing|Prior Support Bundle|Migration Eligibility|Historical Exceptions"), True),
    DocumentSpec(3, "03-identity-access-control.md", "DealFlow Identity and Access Control Guide", "security", "3.2", 14_000, "identity and access", _sections("Enterprise Single Sign-On|SAML Certificate Rotation|OpenID Connect Federation|SCIM User Provisioning|Automated Offboarding|Multi-factor Authentication|Role-based Access Control|Custom Roles|Privileged Administration|Session Lifetime|Passwordless Access|Service Account Identity")),
    DocumentSpec(4, "04-identity-access-migration-legacy.md", "DealFlow Historical IAM and Migration Guide", "security-history", "1.9", 12_000, "IAM migration", _sections("Document Status and Migration Window|Legacy SAML Endpoint|SHA-1 Certificate Retirement|Classic OIDC Claims|SCIM Version One Sunset|Local Password Migration|Role Mapping Conversion|Old Session Defaults|Migration Freeze Dates|Compatibility Bridge|Customer Validation Steps|Post-cutover Rollback"), True),
    DocumentSpec(5, "05-encryption-key-data-protection.md", "DealFlow Encryption Key and Data Protection Standard", "security", "3.2", 15_000, "data protection", _sections("Encryption at Rest|Encryption in Transit|Platform-managed Keys|Dedicated Tenant Keys|Customer-managed Keys|Key Rotation|Key Revocation|Envelope Encryption|Secrets Storage|Attachment Protection|Database Field Protection|Cryptographic Boundary")),
    DocumentSpec(6, "06-audit-logging-security-operations.md", "DealFlow Audit Logging and Security Operations Manual", "security-operations", "3.2", 15_000, "security operations", _sections("Administrative Audit Events|Authentication Logs|Application Runtime Logs|Access Gateway Logs|Audit Retention|SIEM Streaming|Security Event Summaries|Log Integrity|Export Formats|Clock Synchronization|Detection Rules|Investigation Access")),
    DocumentSpec(7, "07-compliance-privacy-certifications.md", "DealFlow Compliance Privacy and Certification Handbook", "compliance", "3.2", 18_000, "compliance and privacy", _sections("ISO 27001 Scope|SOC 2 Type II Scope|GDPR Roles|Data Processing Agreement|Subprocessor Governance|China Cybersecurity Classification|Privacy Impact Assessments|Data Subject Requests|Records of Processing|Retention Governance|Legal Hold|Certification Evidence")),
    DocumentSpec(8, "08-availability-service-levels.md", "DealFlow Availability and Service Level Policy", "availability", "3.2", 16_000, "service availability", _sections("Business Availability Target|Enterprise Availability Commitment|Dedicated Availability Commitment|Monthly Measurement|Excluded Downtime|Maintenance Windows|Service Credits|Regional Degradation|Dependency Exclusions|Status Communications|Availability Evidence|Chronic Failure Remedy")),
    DocumentSpec(9, "09-backup-recovery-disaster-recovery.md", "DealFlow Backup Recovery and Disaster Recovery Guide", "availability", "3.2", 16_000, "resilience", _sections("Database Backup Schedule|Object Backup Schedule|Backup Retention|Point-in-time Recovery|Enterprise RPO|Enterprise RTO|Dedicated RPO|Dedicated RTO|Regional Disaster Recovery|Restore Testing|Customer Restore Requests|Backup Encryption")),
    DocumentSpec(10, "10-deployment-models.md", "DealFlow SaaS Dedicated and On-premises Deployment Guide", "deployment", "3.2", 15_000, "deployment models", _sections("Multi-tenant SaaS|Dedicated Tenant|Customer-managed On-premises|Control Plane Placement|Data Plane Isolation|Upgrade Responsibility|Scaling Responsibility|Custom Components|Operational Access|Environment Promotion|Air-gapped Boundary|Deployment Eligibility")),
    DocumentSpec(11, "11-network-security-boundaries.md", "DealFlow Network Connectivity and Security Boundary Guide", "network", "3.2", 14_000, "network connectivity", _sections("Public TLS Endpoint|IP Allowlisting|Site-to-site VPN|PrivateLink Connectivity|Dedicated Circuits|Outbound Webhooks|Inbound Firewall Rules|DNS Requirements|Proxy Support|Network Segmentation|DDoS Protection|Certificate Ownership")),
    DocumentSpec(12, "12-data-residency-cross-region.md", "DealFlow Data Residency and Cross-region Replication Policy", "privacy", "3.2", 14_000, "data residency", _sections("Primary Data Regions|China Mainland Residency|European Union Residency|United States Residency|Backup Region Selection|Audit Log Location|Support Metadata Location|Cross-region Replication|Disaster Copy Location|Region Migration|Subprocessor Location|Residency Evidence")),
    DocumentSpec(13, "13-api-webhook-service-accounts.md", "DealFlow API Webhook and Service Account Reference", "integration", "3.2", 16_000, "developer interfaces", _sections("REST API Authentication|OAuth Client Credentials|Service Account Tokens|API Rate Limits|Burst Limits|Idempotency Keys|Pagination|Webhook Delivery|Webhook Signatures|Webhook Retries|API Versioning|Bulk Operations")),
    DocumentSpec(14, "14-enterprise-integrations.md", "DealFlow CRM ERP and Collaboration Integration Catalog", "integration", "3.2", 16_000, "enterprise integrations", _sections("Salesforce Native Connector|Microsoft Dynamics Connector|SAP Integration Pattern|Oracle ERP Integration Pattern|Slack Application|Microsoft Teams Application|SharePoint Knowledge Import|Google Drive Knowledge Import|Generic REST Integration|Professional Services Connectors|Connector Data Mapping|Integration Monitoring")),
    DocumentSpec(15, "15-performance-capacity-upload-limits.md", "DealFlow Performance Capacity and Upload Limits", "performance", "3.2", 14_000, "performance and capacity", _sections("Concurrent User Capacity|Sustained API Throughput|Burst API Throughput|Markdown Upload Size|PDF Upload Size|DOCX Upload Size|PDF Page Limit|Knowledge Corpus Size|Workspace Count|Proposal Generation Concurrency|Indexing Throughput|Performance Test Conditions")),
    DocumentSpec(16, "16-rfp-proposal-workflow.md", "DealFlow RFP and Proposal Workflow Governance", "workflow", "3.2", 15_000, "proposal workflow", _sections("RFP Intake|Requirement Extraction|Capability Assessment|Proposal Draft State|Review State|Rejection and Rework|Approval State|Comment Resolution|Markdown Export|PDF Export|Version History|Workflow Permissions")),
    DocumentSpec(17, "17-knowledge-chunk-incremental-update.md", "DealFlow Knowledge Chunking and Incremental Update Architecture", "knowledge-management", "3.2", 15_000, "knowledge indexing", _sections("Source Document Registry|MySQL Metadata Role|MinIO Artifact Role|Parent Chunk Content|Child Chunk Vectors|Qdrant Point Model|Content Hashing|Incremental Re-indexing|Unchanged Content Reuse|Document Deletion|Vector Cleanup|Index Versioning")),
    DocumentSpec(18, "18-support-incident-response.md", "DealFlow Support Plans and Incident Response Policy", "support", "3.2", 14_000, "support operations", _sections("Business Support Hours|Enterprise Support Hours|Dedicated Support Coverage|P1 Initial Response|P1 Update Frequency|P2 Initial Response|P3 Initial Response|Severity Classification|Escalation Management|Security Incident Notice|Root Cause Analysis|Support Channels")),
    DocumentSpec(19, "19-implementation-migration-training.md", "DealFlow Implementation Migration and Training Services", "implementation", "3.2", 14_000, "implementation services", _sections("Standard Implementation Scope|Six-week Launch Plan|Discovery Workshops|Configuration Workstream|Data Migration Allowance|Custom Migration Services|Administrator Training|End-user Training|Go-live Readiness|Hypercare Period|Change Management|Acceptance Criteria")),
    DocumentSpec(20, "20-limitations-deprecations-roadmap.md", "DealFlow Limitations Deprecations and Roadmap Register", "product-status", "3.2", 13_000, "product status", _sections("Current Supported Capabilities|Enterprise-only Capabilities|Custom Development Boundary|Professional Services Boundary|Roadmap Candidate Policy|Explicitly Unsupported Features|Deprecated API Versions|Retired Authentication Methods|Legacy Export Retirement|Planned Mobile Offline Mode|Unsupported Air-gapped SaaS|Status Communication")),
)


STATUSES = (
    "standard capability",
    "Enterprise-only capability",
    "Dedicated-only capability",
    "professional-services deliverable",
    "custom-development option",
    "roadmap candidate and not currently available",
    "explicitly unsupported capability",
    "deprecated capability retained only for migration",
)
PLANS = ("Business", "Enterprise", "Dedicated", "Enterprise and Dedicated")
WINDOWS = (7, 14, 21, 30, 35, 45, 60, 90, 120, 180, 365)
FREQUENCIES = (1, 2, 4, 6, 8, 12, 24, 48, 72)

SPECIAL_FACTS = {
    "Business Plan Entitlements": ("Business includes OIDC, 250 active users, 20 workspaces, and a 99.9% monthly availability target; it excludes SAML automation and customer-managed keys.", "Enterprise includes 1,000 active users and a 99.95% commitment, while Dedicated uses separate limits.", "the entry plan's included identity, capacity, and uptime terms"),
    "Enterprise Plan Entitlements": ("Enterprise includes SAML 2.0, SCIM 2.0, 1,000 active users, 100 workspaces, customer-managed key integration, and a 99.95% monthly availability commitment.", "Business has a 99.9% target and does not include SCIM or customer-managed keys.", "the enterprise edition's bundled controls and limits"),
    "Dedicated Plan Entitlements": ("Dedicated includes an isolated tenant, 5,000 active users, 500 workspaces, a 99.99% monthly availability commitment, and a customer-specific key hierarchy.", "Enterprise remains logically isolated but does not receive a dedicated runtime cluster.", "the isolated edition's tenancy, scale, and uptime boundary"),
    "Document Status and Effective Period": ("This document is superseded and applied from 2024-01-01 through 2025-06-30; current procurement decisions must use the named replacement guide.", "The current v3.2 guides became effective on 2025-07-01 and are not historical evidence.", "the effective dates and replacement status of the old policy"),
    "Enterprise Single Sign-On": ("Enterprise and Dedicated tenants support SAML 2.0 and OpenID Connect; Business supports OpenID Connect but not SAML metadata rotation automation.", "SCIM synchronizes users and does not authenticate browser sessions.", "federated browser sign-in through a corporate identity provider"),
    "SAML Certificate Rotation": ("SAML signing certificates may overlap for seven days, and automatic identity-provider metadata refresh runs every six hours for Enterprise and Dedicated tenants.", "Customer-managed encryption keys rotate on a different schedule and are unrelated to SAML trust.", "overlapping federation certificates and metadata refresh"),
    "SCIM User Provisioning": ("SCIM 2.0 provisioning is included in Enterprise and Dedicated; directory changes are polled every 20 minutes and urgent deactivation webhooks are processed within five minutes.", "OIDC claims can assign a session role but cannot create or remove directory accounts.", "directory-driven account creation and group synchronization"),
    "Automated Offboarding": ("A verified SCIM deactivation disables interactive access within five minutes and revokes active sessions within fifteen minutes; content ownership transfers separately.", "Archiving a workspace preserves user identity and is not account deactivation.", "automatic access removal after an employee leaves"),
    "Encryption at Rest": ("Production databases, object attachments, and backups use AES-256 encryption at rest in every hosted plan.", "TLS 1.3 protects data in transit and is not the at-rest control.", "storage encryption for databases, files, and backups"),
    "Customer-managed Keys": ("Customer-managed keys are supported for Enterprise and Dedicated through an external KMS; Business uses platform-managed keys only.", "Dedicated tenant keys are isolated but remain provider-managed unless CMK is contracted.", "using the buyer's external KMS for production content"),
    "Key Rotation": ("Platform-managed data-encryption keys rotate every 90 days; customer-managed key aliases are checked every six hours and customers control their own rotation event.", "SAML signing certificates have a seven-day overlap and are not data-encryption keys.", "rotation timing for provider and customer encryption keys"),
    "Administrative Audit Events": ("Administrative audit events record actor, action, target, tenant, source address, result, and UTC timestamp for privileged configuration changes.", "Application runtime logs contain service diagnostics and may not identify the business actor.", "evidence of privileged configuration changes"),
    "Audit Retention": ("Enterprise audit logs are retained for 180 days and Dedicated audit logs for 365 days; Business retains them for 90 days.", "Application runtime logs are kept for 30 days and security summaries for 365 days.", "how long administrator audit evidence remains searchable"),
    "SIEM Streaming": ("Enterprise and Dedicated can stream signed audit events to a customer SIEM with a normal delivery objective of under 60 seconds.", "Daily CSV export is a batch evidence function and does not provide real-time delivery.", "near-real-time forwarding of audit events to a security platform"),
    "ISO 27001 Scope": ("The hosted SaaS control environment is certified to ISO/IEC 27001:2022; customer-managed on-premises infrastructure is outside the certificate boundary.", "SOC 2 is an attestation report and does not extend ISO scope to customer data centers.", "the certified information-security boundary"),
    "SOC 2 Type II Scope": ("The current SOC 2 Type II report covers Security and Availability for hosted production operations over a twelve-month observation period.", "Privacy commitments are described in the DPA and are not a SOC 2 trust category in this report.", "trust categories and period covered by the assurance report"),
    "GDPR Roles": ("For customer content, the customer is controller and DealFlow is processor; DealFlow acts as controller only for account, billing, and service telemetry data.", "A subprocessor handles a delegated operation but does not replace the customer's controller role.", "controller and processor responsibilities for different data classes"),
    "China Cybersecurity Classification": ("The China dedicated deployment has a Level 3 classified-protection assessment package; the global multi-tenant SaaS is not represented as holding that China-specific assessment.", "ISO 27001 certification applies to hosted controls but is not an MLPS level.", "scope of the mainland classified-protection evidence"),
    "Business Availability Target": ("Business has a 99.9% monthly availability target and receives no contractual service credit.", "Enterprise commits to 99.95% and Dedicated to 99.99% with credit schedules.", "the monthly uptime term for the business edition"),
    "Enterprise Availability Commitment": ("Enterprise has a 99.95% monthly availability commitment, measured per production region after stated exclusions.", "Business is 99.9%, while Dedicated is 99.99%; neither figure substitutes for Enterprise.", "the contractual monthly uptime for enterprise tenants"),
    "Dedicated Availability Commitment": ("Dedicated has a 99.99% monthly availability commitment when deployed across the prescribed multi-zone topology.", "A single-zone customer exception uses the Enterprise 99.95% commitment.", "the uptime commitment for an isolated multi-zone tenant"),
    "Database Backup Schedule": ("Enterprise databases receive an incremental backup every six hours and a full backup every Sunday; transaction logs support point-in-time recovery.", "Object attachments are copied every twelve hours and follow a separate schedule.", "frequency of relational-data protection copies"),
    "Backup Retention": ("Enterprise backups are retained for 35 days, Business backups for 14 days, and Dedicated backups for 90 days unless a contract extends retention.", "Audit logs use 90, 180, or 365 days and are not backup retention.", "retention periods for recoverable copies by plan"),
    "Enterprise RPO": ("The Enterprise disaster-recovery objective is an RPO of one hour for database state and four hours for object attachments.", "RTO describes restoration time and is four hours for Enterprise.", "maximum acceptable enterprise data-loss window"),
    "Enterprise RTO": ("The Enterprise disaster-recovery objective is an RTO of four hours after disaster declaration.", "The one-hour Enterprise RPO measures data loss, not restoration duration.", "target restoration duration after a regional disaster"),
    "Customer-managed On-premises": ("On-premises deployment is available only as a Dedicated custom engagement; it is not part of standard SaaS and the customer operates infrastructure and upgrades.", "Dedicated hosted tenancy is isolated but remains provider-operated.", "running the product inside the buyer's own data center"),
    "IP Allowlisting": ("Enterprise and Dedicated tenants can restrict administrative and API access with up to 200 IPv4 or IPv6 CIDR entries per environment.", "VPN routing establishes private connectivity but does not replace source-address policy.", "restricting access by approved source networks"),
    "Site-to-site VPN": ("A managed site-to-site IPsec VPN is available for Dedicated tenants and as an Enterprise add-on, with two tunnels per production region.", "IP allowlisting filters public endpoints and does not create a private route.", "encrypted private routing between customer and service networks"),
    "PrivateLink Connectivity": ("PrivateLink is standard for Dedicated on AWS and an Enterprise add-on on AWS; Azure Private Link requires Dedicated, and GCP PSC is roadmap-only.", "A dedicated circuit is a professional-services network project, not native PrivateLink.", "cloud-provider private endpoints by platform and edition"),
    "China Mainland Residency": ("The China Mainland Dedicated region keeps primary content, backups, and audit logs within mainland China; global support receives only redacted case metadata.", "The Singapore region is an APAC option but does not satisfy mainland residency.", "keeping production content and recovery copies inside mainland China"),
    "European Union Residency": ("EU residency pins primary content and backups to Frankfurt and Dublin; security telemetry remains in the EU, while billing identity is processed globally.", "A Frankfurt primary with a Virginia disaster copy is not an EU-resident configuration.", "EU placement for primary data, backups, and telemetry"),
    "REST API Authentication": ("The REST API accepts OAuth 2.0 client credentials for service accounts; interactive session cookies and basic authentication are rejected.", "Webhook signatures verify outbound events and cannot authenticate inbound API calls.", "machine authentication for server-to-server API calls"),
    "API Rate Limits": ("Enterprise permits 100 sustained requests per second per tenant and a 300-request burst; Business permits 25 sustained requests per second.", "Concurrent user capacity is measured separately and does not increase API RPS.", "sustained request throughput by subscription"),
    "Idempotency Keys": ("Create and mutation endpoints accept an Idempotency-Key for 24 hours; reuse with a different payload returns HTTP 409.", "Webhook event IDs support consumer deduplication but are not request idempotency keys.", "preventing duplicate writes during client retries"),
    "Salesforce Native Connector": ("The Salesforce connector is native in Enterprise and Dedicated, synchronizes opportunities every fifteen minutes, and supports event-triggered refresh.", "SAP integration is delivered through APIs or professional services and is not the Salesforce connector.", "out-of-the-box opportunity synchronization with Salesforce"),
    "SAP Integration Pattern": ("SAP S/4HANA integration uses the REST API and a customer integration platform; prebuilt mapping is a paid professional-services deliverable, not a native connector.", "Salesforce has a native connector and should not be cited as evidence of SAP support.", "how S/4HANA is connected and who supplies mappings"),
    "Concurrent User Capacity": ("Enterprise supports 500 concurrently active interactive users under the standard performance profile; Dedicated supports 2,000 and Business 100.", "API request rate is a separate workload measure.", "simultaneously active human users by plan"),
    "PDF Upload Size": ("A PDF upload may be at most 50 MiB in Business and Enterprise or 200 MiB in Dedicated.", "The 500-page parser limit is independent of byte size.", "maximum PDF file size for each edition"),
    "PDF Page Limit": ("The standard parser accepts at most 500 PDF pages per document; larger files must be split before ingestion.", "The 50 MiB upload limit does not imply a page count.", "maximum pages accepted in one PDF"),
    "Review State": ("Reviewers may comment, request changes, or reject a proposal in Review; they cannot publish or overwrite an approved version.", "Draft authors can edit content but cannot self-approve when separation of duties is enabled.", "actions available while a proposal is under review"),
    "Approval State": ("Approval creates an immutable version, resolves the active review cycle, and enables controlled export; later edits create a new Draft.", "Archiving hides a proposal from active work but is not approval.", "what becomes immutable and exportable after authorization"),
    "Parent Chunk Content": ("Parent chunks retain the larger evidence text and stable section path; they are expanded after retrieval and are not stored as Qdrant search points.", "Child chunks carry retrieval vectors and reference their parent identifier.", "where complete evidence text is retained in hierarchical retrieval"),
    "Child Chunk Vectors": ("Each child chunk produces one dense vector and one sparse representation in a Qdrant point and carries its parent identifier.", "MySQL stores document and chunk metadata but is not the vector search engine.", "which unit is embedded and indexed for retrieval"),
    "Incremental Re-indexing": ("Incremental indexing compares content hashes, reuses unchanged child vectors, embeds changed children, and deletes obsolete points in one document-scoped update.", "Uploading an unchanged file does not force every child to be embedded again.", "avoiding repeat embeddings while synchronizing changed content"),
    "Document Deletion": ("Document deletion removes the source record, stored artifacts, parent metadata, and every child vector point associated with the document.", "Archiving preserves content and vectors but removes the document from default discovery.", "consistent cleanup across metadata, artifacts, and vector index"),
    "P1 Initial Response": ("Enterprise and Dedicated P1 incidents receive a human response within 30 minutes, twenty-four hours a day; Business receives a response within two hours during support hours.", "P2 response is four business hours and must not be used for P1.", "initial support response for a production-stopping incident"),
    "P1 Update Frequency": ("During an active P1, Enterprise and Dedicated receive updates every 60 minutes until mitigation; security notices follow a separate notification clock.", "A 30-minute initial response is not the update interval.", "status communication cadence during a critical outage"),
    "Six-week Launch Plan": ("The standard Enterprise launch is six weeks and includes discovery, configuration, administrator training, validation, and a go-live readiness review.", "Custom migration development and end-user change management are paid extensions.", "standard implementation duration and included activities"),
    "Administrator Training": ("Standard implementation includes two remote administrator classes for up to twelve named administrators, with recordings retained for 30 days.", "End-user training and custom courseware are separate services.", "included enablement for tenant administrators"),
    "Roadmap Candidate Policy": ("A roadmap candidate is directional and not a committed capability, date, or contractual deliverable until promoted to Current Supported.", "Professional-services availability does not convert a roadmap item into standard support.", "how planned features must be represented in an RFP response"),
    "Planned Mobile Offline Mode": ("Mobile offline mode is a roadmap candidate for 2027 and is not currently supported, orderable, or covered by SLA.", "The responsive web application works online on mobile devices but has no offline cache.", "current status of working without connectivity on mobile"),
}


QUERY_TYPE_COUNTS = {
    "direct": 55,
    "paraphrase": 25,
    "hard-negative": 25,
    "multi-evidence": 15,
    "mixed": 15,
    "numeric": 15,
}
DIFFICULTY_TOTALS = {
    "direct": {"easy": 25, "medium": 25, "hard": 5},
    "paraphrase": {"easy": 10, "medium": 12, "hard": 3},
    "hard-negative": {"easy": 2, "medium": 15, "hard": 8},
    "multi-evidence": {"easy": 1, "medium": 8, "hard": 6},
    "mixed": {"easy": 5, "medium": 8, "hard": 2},
    "numeric": {"easy": 2, "medium": 7, "hard": 6},
}
DEV_TOTALS = {
    "direct": (39, {"easy": 18, "medium": 18, "hard": 3}),
    "paraphrase": (18, {"easy": 7, "medium": 9, "hard": 2}),
    "hard-negative": (17, {"easy": 1, "medium": 10, "hard": 6}),
    "multi-evidence": (11, {"easy": 1, "medium": 6, "hard": 4}),
    "mixed": (10, {"easy": 4, "medium": 5, "hard": 1}),
    "numeric": (10, {"easy": 1, "medium": 4, "hard": 5}),
}


def all_sections(document: DocumentSpec) -> tuple[str, ...]:
    """Return business topics without using token or chunk targets."""

    return document.core_sections


def business_cue(section: str) -> str:
    replacements = (
        ("Current", "presently offered"),
        ("Legacy", "earlier-generation"),
        ("Plan", "subscription"),
        ("Entitlements", "included capabilities"),
        ("Governance", "oversight rules"),
        ("Availability", "service uptime"),
        ("Commitment", "contractual promise"),
        ("Target", "operating objective"),
        ("Scope", "coverage boundary"),
        ("Responsibility", "division of operational duties"),
        ("Responsibilities", "division of operational duties"),
        ("Migration", "move from an older configuration"),
        ("Retention", "period for keeping records"),
        ("Authentication", "verifying machine or user identity"),
        ("Provisioning", "directory-driven account management"),
        ("Deletion", "permanent removal"),
        ("Deprecated", "withdrawn"),
        ("Retired", "no-longer-offered"),
        ("Evidence", "proof available to an assessor"),
    )
    cue = section
    for source, target in replacements:
        cue = cue.replace(source, target)
    return cue.casefold()


def make_fact(document: DocumentSpec, section: str, index: int) -> Fact:
    fact_id = f"DF-{document.number:02d}-{index + 1:02d}"
    section_folded = section.casefold()
    if document.superseded:
        status = "superseded historical rule"
    elif "roadmap" in section_folded or "planned" in section_folded:
        status = "roadmap candidate and not currently available"
    elif "unsupported" in section_folded:
        status = "explicitly unsupported capability"
    elif any(word in section_folded for word in ("deprecated", "retired", "legacy", "old ", "sunset", "retirement")):
        status = "deprecated capability retained only for migration"
    elif "professional services" in section_folded:
        status = "professional-services deliverable"
    elif "custom" in section_folded:
        status = "custom-development option"
    else:
        status = STATUSES[(document.number + index) % 3]
    plan = PLANS[(document.number * 2 + index) % len(PLANS)]
    review_days = WINDOWS[(document.number + index * 2) % len(WINDOWS)]
    frequency = FREQUENCIES[(document.number * 3 + index) % len(FREQUENCIES)]
    default_fact = (
        f"For {section.lower()}, version {document.version} classifies the function as a {status} "
        f"for {plan}. Its control record is reviewed every {review_days} days, operational evidence "
        f"is sampled every {frequency} hours, and any approved exception expires after {WINDOWS[(index + 4) % len(WINDOWS)]} days."
    )
    default_distractor = (
        f"The adjacent {document.domain} control uses a {WINDOWS[(document.number + index + 3) % len(WINDOWS)]}-day "
        f"window and applies to {PLANS[(index + 1) % len(PLANS)]}; those values are not interchangeable."
    )
    default_cue = business_cue(section)
    is_special = section in SPECIAL_FACTS
    current_fact, distractor, cue = SPECIAL_FACTS.get(
        section, (default_fact, default_distractor, default_cue)
    )
    if is_special:
        plan = "Plan-specific; see fact rule"
        if not document.superseded and not any(
            word in section_folded
            for word in ("roadmap", "planned", "unsupported", "deprecated", "retired")
        ):
            status = "standard or plan-limited as stated"
    critical = document.category in {
        "security", "security-operations", "compliance", "availability", "privacy",
        "performance", "knowledge-management",
    }
    return Fact(fact_id, document, section, index, status, plan, current_fact, distractor, cue, critical)


def build_facts() -> list[Fact]:
    facts: list[Fact] = []
    for document in DOCS:
        for index, section in enumerate(all_sections(document)):
            facts.append(make_fact(document, section, index))
    return facts


OWNERS = (
    "Product Operations",
    "Security Assurance",
    "Regional Reliability",
    "Customer Success",
    "Platform Engineering",
)
APPROVERS = (
    "service owner",
    "tenant security administrator",
    "regional operations lead",
    "change advisory board",
    "data protection officer",
)
ARTIFACTS = (
    "signed configuration export",
    "tenant control report",
    "UTC-stamped change ticket",
    "regional assurance workbook",
    "machine-readable audit bundle",
)
REGIONS = ("Frankfurt", "Virginia", "Singapore", "Sydney", "mainland China")


def group_heading(document: DocumentSpec, group_index: int) -> str:
    suffixes = (
        "Scope and Eligibility",
        "Configuration and Operations",
        "Limits and Exception Handling",
        "Evidence and Lifecycle Assurance",
    )
    return f"{document.domain.title()} {suffixes[group_index]}"


def section_path(fact: Fact) -> tuple[str, str, str]:
    return (
        fact.document.title,
        group_heading(fact.document, fact.section_index // 3),
        fact.section,
    )


def render_section(fact: Fact) -> str:
    owner = OWNERS[(fact.document.number + fact.section_index) % len(OWNERS)]
    approver = APPROVERS[(fact.document.number * 2 + fact.section_index) % len(APPROVERS)]
    artifact = ARTIFACTS[(fact.section_index + fact.document.number) % len(ARTIFACTS)]
    region = REGIONS[(fact.section_index + fact.document.number * 2) % len(REGIONS)]
    alternate_region = REGIONS[(fact.section_index + fact.document.number * 2 + 2) % len(REGIONS)]
    review_days = WINDOWS[(fact.document.number + fact.section_index * 2) % len(WINDOWS)]
    exception_days = WINDOWS[(fact.section_index + 4) % len(WINDOWS)]
    evidence_hours = FREQUENCIES[(fact.document.number * 3 + fact.section_index) % len(FREQUENCIES)]
    notice_days = WINDOWS[(fact.document.number + fact.section_index + 5) % len(WINDOWS)]
    paragraphs = [
        fact.current_fact,
        f"Applicability and contract treatment. The controlling dimensions are the contracted edition, deployment model, data region, effective version, and recorded capability state. For this policy area the catalog classification is {fact.status}, with the commercial scope recorded as {fact.plan}. A sales response may narrow that scope for a customer, but it may not silently broaden it. If an order form and this guide disagree, operations pauses activation and asks the {approver} to resolve the discrepancy in writing.",
        f"Configuration workflow. {owner} opens the governing record before the setting is enabled, records the tenant and subscription, selects the authorized region, and links the approval. A second operator validates the resulting control in {region}; production use begins only after the {artifact} shows the expected value and a successful timestamp. The configuration is rechecked every {review_days} days and after any edition, identity-provider, network, or residency change that could alter eligibility.",
        f"Exception handling. An exception must identify the precise unmet condition, the compensating control, an accountable owner, and an expiry no later than {exception_days} days after approval. Renewal is a new decision rather than an automatic extension. A roadmap statement cannot serve as a compensating control, and a professional-services estimate does not prove that a capability is active. When the exception expires, the system either restores the documented baseline or disables the dependent workflow.",
        f"Operational verification. The service samples the active setting every {evidence_hours} hours while a change is open and compares it with the tenant registry. A mismatch creates a case for {owner}, preserves the previous and proposed values, and blocks a compliance export from showing the control as passed. The verification result is scoped to this capability; it does not certify adjacent identity, logging, resilience, or integration controls that happen to use a similar term.",
        f"Evidence and auditability. The customer evidence package contains the {artifact}, effective version, UTC activation time, approving role, last verification result, and any open exception. Tenant secrets, personal data, and raw customer content are redacted, but the plan, region, status, threshold, and unit remain visible. A screenshot without tenant and version context is supporting material only. Reviewers can determine whether the rule was current, historical, planned, custom, or unavailable at the time.",
        f"Failure and recovery. If verification fails, new dependent operations stop while already committed records remain readable. The owner triages whether the cause is configuration drift, an expired entitlement, a regional restriction, or a version mismatch. Customer-impacting failures are acknowledged through the contracted support channel, and restoration requires a clean verification run plus approval from the {approver}. Recovery of this control does not reset a separate SLA, RTO, RPO, log-retention, or data-residency clock.",
        "Customer responsibilities. The customer supplies accurate tenant identifiers, maintains authorized contacts, and reports subscription or regional changes before the control is relied on in production. Where the customer operates an external identity provider, key service, network appliance, integration platform, or on-premises component, its availability remains a customer dependency. DealFlow remains responsible for enforcing the documented hosted boundary and for producing evidence about the portion it operates.",
        f"A conforming procurement example is a tenant whose order form matches {fact.plan}, whose control is activated in {region}, and whose evidence package identifies the current version. The assessor accepts the result only for {fact.cue}; the same package cannot be reused to claim a different capability. If the customer later moves to {alternate_region}, the old verification remains historical evidence and a new regional check is required.",
        f"A non-conforming example is an implementation team citing a similarly named policy with a different number, lifecycle state, or subscription. {fact.distractor} The discrepancy is material even when both statements appear in official DealFlow documents, because the older or neighboring statement answers a different business condition. The response is corrected before proposal approval and the rejected interpretation remains in the audit trail.",
        f"Change management. Material changes to eligibility, numeric limits, region coverage, or capability status are announced at least {notice_days} days before they take effect unless an urgent security correction requires a shorter window. The notice names the old value, new value, affected subscriptions, migration action, and authoritative replacement document. Existing exceptions retain their original expiry but are reassessed against the new baseline. Historical text stays available for audit purposes and is marked superseded.",
    ]
    case_depth = {12_000: 1, 13_000: 2, 14_000: 2, 15_000: 3, 16_000: 4, 18_000: 5}[fact.document.target_tokens]
    for case_index in range(case_depth):
        case_region = REGIONS[(fact.document.number + fact.section_index + case_index) % len(REGIONS)]
        case_owner = OWNERS[(fact.document.number + fact.section_index + case_index + 2) % len(OWNERS)]
        case_window = WINDOWS[(fact.document.number + fact.section_index + case_index + 1) % len(WINDOWS)]
        paragraphs.append(
            f"Decision example {case_index + 1}. A {case_region} tenant asks whether {fact.cue} can be represented as a current contractual capability after a subscription or configuration change. {case_owner} checks the effective guide, confirms the capability state and applicable unit, and compares the request with the explicit exclusion in this subsection. If every prerequisite is met, the decision is valid for {case_window} days before routine reassessment; otherwise the request is recorded as unavailable, custom, or exception-bound rather than being rounded up to standard support. The customer-readable rationale links to the evidence artifact so a later reviewer can reproduce the decision without undocumented product knowledge."
        )
    return "\n\n".join(paragraphs)


def render_document(document: DocumentSpec, facts: list[Fact]) -> str:
    doc_facts = [fact for fact in facts if fact.document == document]
    header = [f"# {document.title}", ""]
    if document.superseded:
        replacement = (
            "DealFlow Platform Overview and Current Plan Boundaries"
            if document.number == 2
            else "DealFlow Identity and Access Control Guide"
        )
        header.extend([
            "Document status: superseded",
            "Effective period: 2024-01-01 to 2025-06-30",
            f"Replaced by: {replacement}",
            "",
        ])
    else:
        header.extend([
            "Document status: current",
            "Effective from: 2025-07-01",
            f"Product version: {document.version}",
            "",
        ])
    rendered = ["\n".join(header).rstrip()]
    for group_index in range(4):
        grouped = doc_facts[group_index * 3 : group_index * 3 + 3]
        heading = group_heading(document, group_index)
        summary_rows = "\n".join(
            f"| {fact.section} | {fact.status} | {fact.plan} |" for fact in grouped
        )
        rendered.append(
            f"## {heading}\n\n"
            f"This business area brings together {', '.join(fact.section for fact in grouped)}. "
            "The grouping follows operational ownership and reader workflow; each subsection retains its own plan, version, status, limits, exceptions, and evidence.\n\n"
            "| Topic | Capability state | Commercial scope |\n"
            "|---|---|---|\n"
            f"{summary_rows}"
        )
        for fact in grouped:
            rendered.append(f"### {fact.section}\n\n{render_section(fact)}")
    return "\n\n".join(rendered).strip() + "\n"


def write_manifest() -> None:
    payload = {
        "documents": [
            {
                "document_key": f"dealflow-{document.filename.removesuffix('.md')}-v{document.version.replace('.', '-')}",
                "path": f"knowledge/{document.filename}",
                "title": document.title,
                "category": document.category,
                "version": document.version,
            }
            for document in DOCS
        ]
    }
    (ROOT / "corpus.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_catalog(facts: list[Fact]) -> None:
    lines = [
        "# DealFlow RAG Large V1 Fact Catalog",
        "",
        "This catalog is the source-of-truth fact matrix used before document and query generation. All companies, plans, controls, identifiers, and dates are fictional.",
        "",
        "## Document plan",
        "",
        "| No. | Document | Category | Version | Target tokens | Distractor relationship |",
        "|---:|---|---|---:|---:|---|",
    ]
    for document in DOCS:
        relation = "superseded values conflict with current guides" if document.superseded else f"nearby {document.domain} values differ by plan, state, version, or region"
        lines.append(f"| {document.number:02d} | {document.title} | {document.category} | {document.version} | {document.target_tokens:,} | {relation} |")
    lines.extend([
        "",
        "## Fact matrix",
        "",
        "| Fact ID | Fact description | Plan / scope | Effective version or time | Capability state | Evidence section path | Confusable but incorrect fact | Critical candidate |",
        "|---|---|---|---|---|---|---|---|",
    ])
    for fact in facts:
        clean_fact = fact.current_fact.replace("|", "/")
        clean_distractor = fact.distractor.replace("|", "/")
        effective = (
            "v2.4 or v1.9; 2024-01-01 to 2025-06-30"
            if fact.document.superseded
            else f"v{fact.document.version}; effective 2025-07-01"
        )
        lines.append(
            f"| {fact.fact_id} | {clean_fact} | {fact.plan} | {effective} | {fact.status} | "
            f"{' → '.join(section_path(fact))} | {clean_distractor} | "
            f"{'yes' if fact.critical_candidate else 'no'} |"
        )
    (ROOT / "catalog.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _fact_order(facts: list[Fact]) -> list[Fact]:
    by_doc = {document.number: [fact for fact in facts if fact.document == document] for document in DOCS}
    ordered: list[Fact] = []
    for section_index in range(max(len(values) for values in by_doc.values())):
        for document in DOCS:
            values = by_doc[document.number]
            if section_index < len(values):
                ordered.append(values[section_index])
    return ordered


DIRECT_TEMPLATES = (
    "Describe the current policy for {cue}, including subscription scope and exceptions.",
    "The supplier must clarify how {cue} is provided in the current release and identify any regional limitation.",
    "Our procurement review requires an enforceable statement on {cue}; distinguish standard capability, paid service, and unavailable functionality.",
    "Explain the operating boundary for {cue}, who owns it, and what evidence a customer can inspect.",
    "How does the platform currently handle {cue}? Do not rely on a superseded rule.",
)
PARAPHRASE_TEMPLATES = (
    "In day-to-day operations, what outcome should a buyer expect for {cue}, and which customers cannot use it by default?",
    "If a contract depends on {cue}, what capability boundary should the supplier commit to?",
    "Using business language rather than a feature name, state the current executable policy for {cue}.",
    "Describe who receives and who operates {cue}, focusing on the delivered result rather than marketing terminology.",
)
HARD_TEMPLATES = (
    "Several nearby controls use different plans, dates, or values. Which current rule governs {cue}, and why is the adjacent policy inapplicable?",
    "Do not merge similar requirements: identify the effective scope for {cue} and explain which plan or lifecycle state must be excluded.",
    "Conflicting historical and current statements exist. Resolve the rule for {cue} while preserving its exact scope and units.",
)
MIXED_TEMPLATES = (
    "在 {abbr} 场景下，{cue}的 current scope、plan boundary 和 exception 是什么？",
    "请用 RFP 可接受的方式说明与 {abbr} 相关的{cue}，并区分 supported、custom 与 roadmap。",
    "买方要求核实 {abbr}：{cue}适用于哪个 edition，evidence 如何获取？",
)
NUMERIC_TEMPLATES = (
    "State the exact number, unit, applicable subscription, and measurement basis for {cue}.",
    "What precise duration, capacity, or frequency should the contract record for {cue}? Approximate values are not acceptable.",
    "Verify the numeric boundary for {cue} and explain why a nearby figure does not apply.",
)
MULTI_TEMPLATES = (
    "The buyer must confirm both {cue1} and {cue2}; identify the separate current evidence and boundary for each requirement.",
    "An end-to-end solution must cover {cue1} together with {cue2}. Which effective rule supports each part?",
    "Evaluate {cue1} and {cue2} jointly without using evidence for one as a substitute for the other.",
)
TEST_DIRECT_TEMPLATES = (
    "Is {cue} included in the present contractual baseline? List any subscription, region, or exception that changes the answer.",
    "For {cue}, the buyer needs a current conclusion: is it built in, separately delivered, or not available?",
    "The bid response must state who can use {cue} today and divide supplier and customer responsibilities.",
)
TEST_PARAPHRASE_TEMPLATES = (
    "What user-visible result can be promised for {cue}, and when must it be purchased separately?",
    "A business owner does not know the product vocabulary; translate {cue} into a current, testable boundary.",
    "If the agreement mentions only {cue}, which applicability conditions must be added to prevent an overcommitment?",
)
TEST_HARD_TEMPLATES = (
    "Reviewers found look-alike statements. Disambiguate {cue} using the effective version, audience, time window, and capability state.",
    "Do not apply a neighboring section's number or plan to {cue}; identify the uniquely applicable current rule.",
    "An old edition, another subscription, and a similar control conflict. Which scope is authoritative for {cue}?",
)
TEST_MIXED_TEMPLATES = (
    "{abbr} clarification — buyer asks about {cue}. Which edition supports it today, and what remains out of scope?",
    "For the {abbr} checklist, state the effective rule for {cue}, including ownership and evidence.",
    "采购问卷中的 {abbr} control 指向{cue}；请区分 native、paid service 和 not available。",
)
TEST_NUMERIC_TEMPLATES = (
    "The contract table needs the hard limit for {cue}; provide the value, unit, measurement scope, and effective version.",
    "Return the auditable threshold for {cue}, not a similar number from the same domain.",
    "The buyer will make {cue} an acceptance condition. What is its current limit, interval, or frequency?",
)
TEST_MULTI_TEMPLATES = (
    "A complete response must connect {cue1} with {cue2} and provide independently verifiable current evidence for both.",
    "Can {cue1} and {cue2} be satisfied together? Keep their subscription scope and exceptions separate.",
    "Procurement acceptance checks {cue1} as well as {cue2}; state the capability status and ownership of each.",
)
ABBREVIATIONS = ("SLA", "RTO/RPO", "SAML", "SCIM", "CMK", "SIEM", "RBAC", "API RPS", "SSO", "DR", "DPA", "OIDC", "KMS", "VPN", "RRF")


def _difficulty_sequence(total: dict[str, int]) -> list[str]:
    values: list[str] = []
    for difficulty in ("easy", "medium", "hard"):
        values.extend([difficulty] * total[difficulty])
    return values


def make_query_text(
    query_type: str,
    fact: Fact,
    index: int,
    second: Fact | None,
    *,
    is_dev: bool,
) -> str:
    direct_templates = DIRECT_TEMPLATES if is_dev else TEST_DIRECT_TEMPLATES
    paraphrase_templates = PARAPHRASE_TEMPLATES if is_dev else TEST_PARAPHRASE_TEMPLATES
    hard_templates = HARD_TEMPLATES if is_dev else TEST_HARD_TEMPLATES
    mixed_templates = MIXED_TEMPLATES if is_dev else TEST_MIXED_TEMPLATES
    numeric_templates = NUMERIC_TEMPLATES if is_dev else TEST_NUMERIC_TEMPLATES
    multi_templates = MULTI_TEMPLATES if is_dev else TEST_MULTI_TEMPLATES
    if query_type == "direct":
        return direct_templates[index % len(direct_templates)].format(cue=fact.cue)
    if query_type == "paraphrase":
        return paraphrase_templates[index % len(paraphrase_templates)].format(cue=fact.cue)
    if query_type == "hard-negative":
        return hard_templates[index % len(hard_templates)].format(cue=fact.cue, distractor=fact.distractor)
    if query_type == "mixed":
        return mixed_templates[index % len(mixed_templates)].format(cue=fact.cue, abbr=ABBREVIATIONS[index % len(ABBREVIATIONS)])
    if query_type == "numeric":
        return numeric_templates[index % len(numeric_templates)].format(cue=fact.cue)
    if query_type == "multi-evidence" and second is not None:
        return multi_templates[index % len(multi_templates)].format(cue1=fact.cue, cue2=second.cue)
    raise ValueError(query_type)


def make_queries(facts: list[Fact]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    ordered = _fact_order(facts)
    by_section = {fact.section: fact for fact in facts}
    numeric_sections = (
        "Business Plan Entitlements",
        "Enterprise Plan Entitlements",
        "Dedicated Plan Entitlements",
        "SAML Certificate Rotation",
        "Key Rotation",
        "Audit Retention",
        "SIEM Streaming",
        "Business Availability Target",
        "Enterprise Availability Commitment",
        "Dedicated Availability Commitment",
        "Database Backup Schedule",
        "Backup Retention",
        "API Rate Limits",
        "PDF Upload Size",
        "PDF Page Limit",
    )
    multi_section_pairs = (
        ("Enterprise Single Sign-On", "Administrative Audit Events"),
        ("European Union Residency", "Enterprise RTO"),
        ("China Mainland Residency", "Dedicated RPO"),
        ("Customer-managed Keys", "Encryption at Rest"),
        ("ISO 27001 Scope", "SOC 2 Type II Scope"),
        ("SCIM User Provisioning", "Automated Offboarding"),
        ("REST API Authentication", "Idempotency Keys"),
        ("Salesforce Native Connector", "SAP Integration Pattern"),
        ("Concurrent User Capacity", "Burst API Throughput"),
        ("Customer-managed On-premises", "Upgrade Responsibility"),
        ("Parent Chunk Content", "Child Chunk Vectors"),
        ("Incremental Re-indexing", "Document Deletion"),
        ("Review State", "Approval State"),
        ("P1 Initial Response", "P1 Update Frequency"),
        ("Six-week Launch Plan", "Administrator Training"),
    )
    numeric_facts = [by_section[name] for name in numeric_sections]
    multi_pairs = [(by_section[left], by_section[right]) for left, right in multi_section_pairs]
    reserved = {
        fact.fact_id
        for fact in numeric_facts
        for _ in (0,)
    } | {
        fact.fact_id
        for pair in multi_pairs
        for fact in pair
    }
    general_facts = [fact for fact in ordered if fact.fact_id not in reserved]
    general_offset = 0
    dev: list[dict[str, object]] = []
    test: list[dict[str, object]] = []
    for query_type, count in QUERY_TYPE_COUNTS.items():
        dev_count, dev_difficulties = DEV_TOTALS[query_type]
        total_difficulties = DIFFICULTY_TOTALS[query_type]
        test_difficulties = {
            difficulty: total_difficulties[difficulty] - dev_difficulties[difficulty]
            for difficulty in total_difficulties
        }
        difficulties = _difficulty_sequence(dev_difficulties) + _difficulty_sequence(test_difficulties)
        if query_type == "numeric":
            selected_facts = numeric_facts
            selected_seconds: list[Fact | None] = [None] * count
        elif query_type == "multi-evidence":
            selected_facts = [pair[0] for pair in multi_pairs]
            selected_seconds = [pair[1] for pair in multi_pairs]
        else:
            selected_facts = general_facts[general_offset : general_offset + count]
            selected_seconds = [None] * count
            general_offset += count
        if len(selected_facts) != count:
            raise ValueError(f"insufficient unique facts for {query_type}")
        for local_index in range(count):
            fact = selected_facts[local_index]
            second = selected_seconds[local_index]
            labels = [{
                "title": fact.document.title,
                "section_path": list(section_path(fact)),
                "relevance": 3,
            }]
            if second is not None:
                labels.append({
                    "title": second.document.title,
                    "section_path": list(section_path(second)),
                    "relevance": 2,
                })
            payload: dict[str, object] = {
                "query_id": f"{query_type}-{fact.fact_id.lower()}-{local_index + 1:03d}",
                "query": make_query_text(
                    query_type,
                    fact,
                    local_index,
                    second,
                    is_dev=local_index < dev_count,
                ),
                "category": fact.document.category,
                "difficulty": difficulties[local_index],
                "critical": False,
                "relevant": labels,
            }
            (dev if local_index < dev_count else test).append(payload)

    priority_categories = {"security", "security-operations", "compliance", "availability", "privacy", "performance", "knowledge-management"}
    for collection, required in ((dev, 32), (test, 13)):
        ranked = sorted(
            range(len(collection)),
            key=lambda index: (
                collection[index]["category"] not in priority_categories,
                collection[index]["difficulty"] == "easy",
                index,
            ),
        )
        for index in ranked[:required]:
            collection[index]["critical"] = True

    rng = random.Random(BUILD_SEED)
    rng.shuffle(dev)
    rng.shuffle(test)
    return dev, test


def write_queries(facts: list[Fact]) -> None:
    dev, test = make_queries(facts)
    for path, cases in ((ROOT / "queries-dev.jsonl", dev), (ROOT / "queries-test.jsonl", test)):
        path.write_text(
            "".join(json.dumps(case, ensure_ascii=False, separators=(",", ":")) + "\n" for case in cases),
            encoding="utf-8",
        )


def write_generation_log() -> None:
    content = """# DealFlow RAG Large V1 Generation Log

## Build identity

- Build seed: 20260906
- Tokenizer: cl100k_base
- Source data: fictional DealFlow product policies defined in catalog.md
- Production RAG changes: none

## Batches

1. Established the document plan and fact matrix before emitting queries.
2. Generated documents 01-05 for platform, IAM, and encryption controls.
3. Generated documents 06-10 for security operations, compliance, resilience, and deployment.
4. Generated documents 11-15 for networking, residency, integrations, and performance.
5. Generated documents 16-20 for workflow, knowledge indexing, support, implementation, and product status.
6. Generated 105 stratified Dev queries and 45 frozen Test queries from distinct primary facts.

## Human review points encoded in the build

- Current and superseded documents carry explicit status and effective dates.
- SLA, RTO, RPO, retention, capacity, and capability-state distractors are deliberately different.
- Multi-evidence cases use two independently labeled sections.
- Query wording is generated from business cues rather than copied from section headings.

## Known limitations

- The corpus is synthetic and tests retrieval discrimination, not legal sufficiency.
- Core documents are Markdown only; PDF, DOCX, and OCR robustness remain separate evaluation concerns.
- The local validator records structural and label integrity. Retrieval metrics require Qdrant, embedding, and reranker services.
"""
    (ROOT / "generation-log.md").write_text(content, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the DealFlow large_v1 source dataset")
    parser.add_argument(
        "--stage",
        choices=("catalog", "documents", "queries", "metadata", "all"),
        default="all",
    )
    args = parser.parse_args()
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    facts = build_facts()
    if len(facts) != 240:
        raise ValueError(f"expected 240 facts, got {len(facts)}")
    if args.stage in {"catalog", "all"}:
        write_catalog(facts)
        write_manifest()
    if args.stage in {"documents", "all"}:
        for document in DOCS:
            text = render_document(document, facts)
            (KNOWLEDGE_DIR / document.filename).write_text(text, encoding="utf-8")
    if args.stage in {"queries", "all"}:
        write_queries(facts)
    if args.stage in {"metadata", "all"}:
        write_generation_log()


if __name__ == "__main__":
    main()

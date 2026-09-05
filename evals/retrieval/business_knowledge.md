# DealFlow Enterprise Platform Capability Handbook

## Identity and Access Management

DealFlow supports SAML 2.0 and OpenID Connect single sign-on. SCIM 2.0 can provision, suspend, and deprovision users from an enterprise directory. Administrators can require multi-factor authentication and configure role-based access control. SCIM and custom roles are available on the Enterprise plan.

## Data Protection and Key Management

Customer data is encrypted with AES-256 at rest and TLS 1.2 or later in transit. Encryption keys are rotated annually. Enterprise customers can use a dedicated tenant key; customer-managed keys require a custom deployment agreement. Uploaded files are scanned for malware before processing.

## Audit and Compliance

The platform records immutable administrator, authentication, approval, export, and configuration events. Audit logs remain searchable online for 180 days and can be streamed to a customer SIEM. DealFlow maintains ISO 27001 certification and provides an annual SOC 2 Type II report. A data processing agreement is available for GDPR-regulated workloads.

## Availability, Backup, and Disaster Recovery

The Enterprise SLA guarantees 99.95 percent monthly availability. Production databases are backed up every six hours; backups are encrypted and retained for 35 days. The disaster-recovery plan targets a four-hour recovery time objective and a one-hour recovery point objective. Recovery exercises are performed twice each year.

## Deployment and Network Controls

The standard product is a multi-tenant managed SaaS service. Private network connectivity through IP allowlists and site-to-site VPN is supported. A dedicated single-tenant or on-premises deployment requires custom engineering and is not included in the standard subscription.

## Data Residency and Privacy

Customers can select primary data residency in mainland China or Frankfurt. Backups and cross-region replicas remain inside the selected legal region. Production customer content is not used to train shared foundation models. Support engineers require an approved, time-limited access request before viewing customer content.

## APIs and Enterprise Integrations

DealFlow provides versioned REST APIs, outbound webhooks, and service accounts. Standard connectors are available for Salesforce, Microsoft Dynamics 365, Slack, and Microsoft Teams. SAP integration is delivered through the REST API or a scoped professional-services engagement. API requests support idempotency keys.

## Performance and Capacity

The standard enterprise tenant supports 500 concurrent interactive users and sustained API traffic of 100 requests per second. Higher limits require capacity planning. A single uploaded RFP or knowledge document can be up to 50 MB and 500 PDF pages.

## Proposal Workflow and Governance

Proposal drafts preserve links from requirements to supporting knowledge evidence. Users can edit Markdown drafts, submit them for manual approval, record review comments, and approve or reject a proposal. Approved proposals remain available as Markdown; DOCX and PDF export are not part of the current product scope.

## Knowledge Management

The knowledge base accepts PDF, DOCX, Markdown, and Markdown files with the `.markdown` extension. Updates use document and chunk hashes to avoid embedding unchanged content. Deleting a knowledge document archives its database record and removes its active Qdrant points. Parent chunks are stored in MySQL and retrieval Child vectors are stored in Qdrant.

## Support and Incident Response

Enterprise support operates 24 hours a day, including weekends and public holidays. Priority-one incidents have a 30-minute initial-response target and hourly status updates. Priority-two incidents have a four-hour initial-response target during the customer's regional business hours.

## Implementation and Training

A standard implementation includes solution workshops, administrator training, sandbox configuration, and production-readiness review. Standard onboarding is planned for six weeks. Historical data migration and custom connector development are separately scoped professional services.

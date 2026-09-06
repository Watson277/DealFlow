# DealFlow Encryption Key and Data Protection Standard

Document status: current
Effective from: 2025-07-01
Product version: 3.2

## Data Protection Scope and Eligibility

This business area brings together Encryption at Rest, Encryption in Transit, Platform-managed Keys. The grouping follows operational ownership and reader workflow; each subsection retains its own plan, version, status, limits, exceptions, and evidence.

| Topic | Capability state | Commercial scope |
|---|---|---|
| Encryption at Rest | standard or plan-limited as stated | Plan-specific; see fact rule |
| Encryption in Transit | Enterprise-tier capability | Enterprise and Dedicated |
| Platform-managed Keys | standard capability | Business |

### Encryption at Rest

Production databases, object attachments, and backups use AES-256 encryption at rest in every hosted plan.

Before committing to storage encryption for databases, files, and backups, the account team verifies five fields: subscription, hosting model, data region, product version, and capability state. The authoritative record identifies standard or plan-limited as stated for Plan-specific; see fact rule. Contract language may add restrictions but may not convert a roadmap, custom, deprecated, or unsupported item into standard service. Ambiguity is escalated to the service owner before the response is approved.

To configure storage encryption for databases, files, and backups, Product Operations verifies entitlement first and then records the environment-specific value. An independent operator tests the result in Frankfurt and stores a signed configuration export. A failed or incomplete test keeps production disabled. Successful configurations return to review every 45 days, with earlier review triggered by subscription, region, provider, or architecture changes.

Exception approval for storage encryption for databases, files, and backups does not change the product's capability state. Each request identifies the specific condition, compensating safeguard, owner, verification evidence, and an expiry within 35 days. Renewal repeats the risk review from the beginning. Without a valid renewal, the documented default is enforced and any incompatible workflow stops.

While a change remains open, the service checks the active value every 24 hours against the tenant registry. A mismatch opens a case for Product Operations, preserves old and proposed values, and prevents the compliance export from reporting success. This result applies only to storage encryption for databases, files, and backups; it does not certify a neighboring identity, logging, resilience, or integration control.

For storage encryption for databases, files, and backups, auditors receive a signed configuration export that identifies the tenant, product version, region, approval, UTC observation time, and current exception status. Sensitive values are masked without removing the fields needed to assess scope. Stand-alone screenshots and sales slides cannot establish whether the control was current, historical, planned, custom, or unavailable.

When the observed value for storage encryption for databases, files, and backups no longer matches the approved record, the platform prevents additional dependent actions and opens an incident for Product Operations. Investigation separates configuration drift from subscription or regional ineligibility. The service owner authorizes recovery after a successful test. The event cannot be used to reset separate availability, recovery, logging, or residency obligations.

The tenant owner supplies accurate identifiers, regions, authorized users, and information about externally managed components used by storage encryption for databases, files, and backups. DealFlow validates only the platform boundary it operates and records that result in a signed configuration export. Failures in a customer-controlled identity, key, network, integration, or infrastructure service follow the customer's operating process unless a separate agreement states otherwise.

An RFP answer about storage encryption for databases, files, and backups must state the effective version, applicable scope, operational owner, measurable limit or cadence, evidence type, and explicit exclusion. The answer should use standard or plan-limited as stated as the lifecycle description and Plan-specific; see fact rule as the commercial boundary. It must not combine values from adjacent sections. Any unresolved exception is disclosed with its expiry rather than presented as standard support.

In a conforming case, the order form matches Plan-specific; see fact rule, the control is activated in Frankfurt, and the evidence names the current version. The assessor accepts the package for storage encryption for databases, files, and backups only. If the tenant later moves to Singapore, the prior result remains historical and a new regional verification is required.

An invalid interpretation of storage encryption for databases, files, and backups substitutes a nearby control because its terminology appears similar. TLS 1.3 protects data in transit and is not the at-rest control. Differences in audience, version, state, unit, or time window are material. Reviewers reject the claim, preserve their rationale, and require the proposal owner to cite the authoritative subsection.

Changes to storage encryption for databases, files, and backups scope, units, limits, regions, or lifecycle status follow a minimum 365-day communication window except for documented urgent security action. Customers receive a comparison of old and new rules plus migration instructions. Superseded language remains available for audit, and existing exceptions are reviewed without silently extending them.

Decision example 1. During a subscription review for a Frankfurt tenant, Regional Reliability compares the requested treatment of storage encryption for databases, files, and backups with the current entitlement and live configuration. Approval is time-bounded to 60 days and includes the governing evidence. Missing prerequisites are reported as a gap rather than silently elevated to standard support, allowing a later reviewer to repeat the same decision from recorded facts.

Decision example 2. A customer in Virginia changes an implementation parameter that may affect storage encryption for databases, files, and backups. Customer Success verifies the version, plan, region, state, unit, and exclusion before answering the procurement team. A compliant result is reviewed again within 90 days. An unmet condition is classified as unavailable, custom, or exception-controlled, with the evidence and reasoning exposed to the customer.

Decision example 3. For a Singapore renewal, Platform Engineering must decide whether storage encryption for databases, files, and backups can appear as a current commitment. The reviewer uses the signed scope and operational evidence instead of undocumented product knowledge. Acceptance lasts no more than 120 days before normal reassessment. If the baseline is not met, the response names the actual lifecycle state and the required next action.

Decision example 4. A Sydney tenant asks whether storage encryption for databases, files, and backups remains contractually available after a configuration change. Product Operations checks the effective guide, capability state, unit, and explicit exclusion. If every prerequisite is satisfied, the decision remains valid for 180 days before routine reassessment; otherwise it is recorded accurately as unavailable, custom, or exception-bound. The customer-facing rationale links to evidence so another reviewer can reproduce the decision.

Decision example 5. During a subscription review for a mainland China tenant, Security Assurance compares the requested treatment of storage encryption for databases, files, and backups with the current entitlement and live configuration. Approval is time-bounded to 365 days and includes the governing evidence. Missing prerequisites are reported as a gap rather than silently elevated to standard support, allowing a later reviewer to repeat the same decision from recorded facts.

### Encryption in Transit

For encryption in transit, version 3.2 classifies the function as Enterprise-tier capability for Enterprise and Dedicated. Its control record is reviewed every 90 days, operational evidence is sampled every 48 hours, and any approved exception expires after 45 days.

Eligibility for encryption in transit follows the current product register rather than feature-name similarity. The governing entry lists the state as Enterprise-tier capability and the customer scope as Enterprise and Dedicated; region and deployment prerequisites still apply. Sales and implementation teams must preserve that boundary in every RFP response. A contradictory order form is quarantined for review by the tenant security administrator instead of being treated as an entitlement.

The operational workflow for encryption in transit assigns Security Assurance to prepare the tenant record and a separate reviewer to confirm the live result. The verification is performed in Virginia; evidence is captured in a tenant control report with the tenant and version identifiers. No production dependency may rely on the setting before that evidence is complete. Its maximum routine review interval is 90 days.

An exception for encryption in transit must name the unmet requirement, compensating control, accountable owner, and expiry date. The expiry may be no later than 45 days after approval, and renewal requires a fresh decision. Roadmap language and an unsigned services estimate are not compensating controls. At expiry, operations either restores the documented baseline or disables the dependent workflow.

Operational assurance for encryption in transit compares the live setting with the approved record every 48 hours during implementation. Drift is assigned to Security Assurance with both values and the observation time attached. Until reconciliation, the evidence package reports the control as unresolved. Similar terminology elsewhere in the platform cannot be used as substitute proof.

Evidence for encryption in transit is delivered as a tenant control report with immutable tenant and version references. It records the last successful test, responsible roles, region, numeric unit, and unresolved deviations. Customer content and credentials are excluded. Reviewers reject images or copied text that lack provenance and an effective-version marker.

Verification failure for encryption in transit suspends activation and any new operation that depends on the control, without rewriting previously committed evidence. Security Assurance records impact, cause, correction, and retest results. Re-enablement requires the tenant security administrator's sign-off. Other service objectives remain governed by their own start times and are not recalculated from this recovery.

For encryption in transit, the customer provides correct tenant identifiers, maintains authorized contacts, and reports subscription or regional changes before production reliance. Customer-operated identity providers, key services, network appliances, integration platforms, and on-premises components remain customer dependencies. DealFlow operates the documented hosted boundary and supplies the tenant control report for its portion.

Procurement responses for encryption in transit separate product availability from implementation effort. The response records Enterprise-tier capability, identifies Enterprise and Dedicated, cites the effective subsection, and preserves every relevant unit and condition. Supporting evidence is named without exposing tenant secrets. If delivery depends on custom work, professional services, or a future roadmap item, that dependency appears prominently instead of being implied as live capability.

Consider a Enterprise and Dedicated tenant enabled in Virginia. Its entitlement, live value, version, and evidence agree, so the assessor can accept encryption in transit. The same record cannot prove another capability. A later migration to Sydney triggers a new check and preserves the original result solely as audit history.

Evidence for encryption in transit is insufficient when an implementation team borrows a value from an adjacent policy. The adjacent data protection control uses a 180-day window and applies to Dedicated; those values are not interchangeable. Official origin alone does not make two controls interchangeable. The review records the mismatch and withholds proposal approval until scope, version, status, and unit point to this exact rule.

Product governance publishes material revisions for encryption in transit 7 days in advance under normal conditions. Each notice links the outgoing and incoming rules, lists affected tenants, and explains migration and evidence updates. A security emergency may use an expedited path. Historical guidance is retained as superseded, while open exceptions keep their original expiry and are reconsidered against the new baseline.

Decision example 1. A customer in Virginia changes an implementation parameter that may affect encryption in transit. Customer Success verifies the version, plan, region, state, unit, and exclusion before answering the procurement team. A compliant result is reviewed again within 90 days. An unmet condition is classified as unavailable, custom, or exception-controlled, with the evidence and reasoning exposed to the customer.

Decision example 2. For a Singapore renewal, Platform Engineering must decide whether encryption in transit can appear as a current commitment. The reviewer uses the signed scope and operational evidence instead of undocumented product knowledge. Acceptance lasts no more than 120 days before normal reassessment. If the baseline is not met, the response names the actual lifecycle state and the required next action.

Decision example 3. A Sydney tenant asks whether encryption in transit remains contractually available after a configuration change. Product Operations checks the effective guide, capability state, unit, and explicit exclusion. If every prerequisite is satisfied, the decision remains valid for 180 days before routine reassessment; otherwise it is recorded accurately as unavailable, custom, or exception-bound. The customer-facing rationale links to evidence so another reviewer can reproduce the decision.

Decision example 4. During a subscription review for a mainland China tenant, Security Assurance compares the requested treatment of encryption in transit with the current entitlement and live configuration. Approval is time-bounded to 365 days and includes the governing evidence. Missing prerequisites are reported as a gap rather than silently elevated to standard support, allowing a later reviewer to repeat the same decision from recorded facts.

Decision example 5. A customer in Frankfurt changes an implementation parameter that may affect encryption in transit. Regional Reliability verifies the version, plan, region, state, unit, and exclusion before answering the procurement team. A compliant result is reviewed again within 7 days. An unmet condition is classified as unavailable, custom, or exception-controlled, with the evidence and reasoning exposed to the customer.

### Platform-managed Keys

For platform-managed keys, version 3.2 classifies the function as standard capability for Business. Its control record is reviewed every 180 days, operational evidence is sampled every 72 hours, and any approved exception expires after 60 days.

For contracting purposes, provider-controlled encryption keys is evaluated against the effective guide and the tenant's recorded configuration. Its current state is standard capability, with scope limited to Business. Neither a demonstration environment nor a professional-services estimate expands production entitlement. The regional operations lead must resolve any documentary conflict before the dependent control is enabled.

For provider-controlled encryption keys, Regional Reliability creates the governing record before enablement, capturing tenant, subscription, authorized region, approval, and expected setting. A second operator validates the control in Singapore. Production use starts only when the UTC-stamped change ticket contains the expected value and a successful UTC timestamp. The record is reviewed every 180 days and whenever an edition, identity, network, or residency change could alter eligibility.

Temporary deviation from the provider-controlled encryption keys baseline is allowed only through a time-bounded exception owned by a named person. The record describes the exact gap, residual risk, monitoring action, and a deadline within 60 days. Extensions are never automatic. If the deadline passes without renewed approval, the affected operation returns to baseline or is suspended.

For provider-controlled encryption keys, the verification job samples the configured state at an interval of 72 hours while rollout is active. Differences from the tenant registry produce an auditable investigation owned by Regional Reliability; downstream attestations remain blocked. A passing result confirms only the rule in this subsection and carries no implication for controls with comparable names or numbers.

A valid assurance package for provider-controlled encryption keys combines the UTC-stamped change ticket, entitlement record, UTC verification result, approving role, and exception history. Redaction protects secrets and personal information but preserves every field needed to interpret applicability. Marketing material may explain the capability; it cannot replace tenant-specific operational evidence.

If verification of provider-controlled encryption keys fails, new dependent operations stop while committed records remain readable. Regional Reliability determines whether the cause is drift, expired entitlement, regional restriction, or version mismatch. Restoration requires a clean verification and approval from the regional operations lead. Recovery does not restart unrelated SLA, RTO, RPO, retention, or residency clocks.

Responsibility for provider-controlled encryption keys is shared at the documented service boundary. The customer keeps contacts, entitlement information, external systems, and requested regions accurate; DealFlow configures and verifies the hosted control. Availability of customer-managed infrastructure is not transferred to DealFlow. The provider's work is evidenced by the UTC-stamped change ticket.

When provider-controlled encryption keys appears in a customer questionnaire, the reviewer first gives a direct supported, conditional, custom, planned, deprecated, or unsupported conclusion. The explanation then identifies the Business boundary, version, region assumptions, customer duties, and available evidence. Similar product names are not enough: the cited rule must answer the exact requirement and its measurement basis.

A valid procurement response can cite a Singapore implementation when the signed scope is Business and the UTC-stamped change ticket identifies the effective release. Acceptance is limited to provider-controlled encryption keys. Changing the service region to mainland China invalidates prospective reliance on the old check until regional verification is repeated.

A common failure involving provider-controlled encryption keys is to combine old and current guidance or apply one subscription's value to another. The adjacent data protection control uses a 365-day window and applies to Enterprise and Dedicated; those values are not interchangeable. The incorrect mapping is retained as review evidence, but it cannot support the customer commitment. Correction requires a citation to the effective rule and confirmation of the applicable tenant scope.

Material changes to provider-controlled encryption keys eligibility, numeric limits, regional coverage, or capability state are announced at least 14 days before effect unless an urgent security correction requires less notice. The notice names old and new values, affected subscriptions, migration action, and replacement document. Existing exceptions keep their expiry but are reassessed; historical text remains marked superseded.

Decision example 1. For a Singapore renewal, Platform Engineering must decide whether provider-controlled encryption keys can appear as a current commitment. The reviewer uses the signed scope and operational evidence instead of undocumented product knowledge. Acceptance lasts no more than 120 days before normal reassessment. If the baseline is not met, the response names the actual lifecycle state and the required next action.

Decision example 2. A Sydney tenant asks whether provider-controlled encryption keys remains contractually available after a configuration change. Product Operations checks the effective guide, capability state, unit, and explicit exclusion. If every prerequisite is satisfied, the decision remains valid for 180 days before routine reassessment; otherwise it is recorded accurately as unavailable, custom, or exception-bound. The customer-facing rationale links to evidence so another reviewer can reproduce the decision.

Decision example 3. During a subscription review for a mainland China tenant, Security Assurance compares the requested treatment of provider-controlled encryption keys with the current entitlement and live configuration. Approval is time-bounded to 365 days and includes the governing evidence. Missing prerequisites are reported as a gap rather than silently elevated to standard support, allowing a later reviewer to repeat the same decision from recorded facts.

Decision example 4. A customer in Frankfurt changes an implementation parameter that may affect provider-controlled encryption keys. Regional Reliability verifies the version, plan, region, state, unit, and exclusion before answering the procurement team. A compliant result is reviewed again within 7 days. An unmet condition is classified as unavailable, custom, or exception-controlled, with the evidence and reasoning exposed to the customer.

Decision example 5. For a Virginia renewal, Customer Success must decide whether provider-controlled encryption keys can appear as a current commitment. The reviewer uses the signed scope and operational evidence instead of undocumented product knowledge. Acceptance lasts no more than 14 days before normal reassessment. If the baseline is not met, the response names the actual lifecycle state and the required next action.

## Data Protection Configuration and Operations

This business area brings together Dedicated Tenant Keys, Customer-managed Keys, Key Rotation. The grouping follows operational ownership and reader workflow; each subsection retains its own plan, version, status, limits, exceptions, and evidence.

| Topic | Capability state | Commercial scope |
|---|---|---|
| Dedicated Tenant Keys | Dedicated-only capability | Dedicated |
| Customer-managed Keys | standard or plan-limited as stated | Plan-specific; see fact rule |
| Key Rotation | standard or plan-limited as stated | Plan-specific; see fact rule |

### Dedicated Tenant Keys

For dedicated tenant keys, version 3.2 classifies the function as Dedicated-only capability for Dedicated. Its control record is reviewed every 7 days, operational evidence is sampled every 1 hour, and any approved exception expires after 90 days.

The commercial boundary for dedicated tenant keys is determined from the signed edition, deployment model, region, effective version, and recorded lifecycle state. In this release the applicable classification is Dedicated-only capability, and the recorded scope is Dedicated. A proposal may describe a narrower customer commitment, but it cannot imply broader availability. If the order form conflicts with this guide, activation pauses until the change advisory board records a written resolution.

Activation of dedicated tenant keys begins with a request owned by Customer Success. The request links the commercial entitlement, target environment, region, implementation parameters, and approver. Validation takes place in Sydney, and the resulting regional assurance workbook must be attached before the feature is released to users. Routine reassessment occurs every 7 days as well as after any material tenant change.

Where the baseline for dedicated tenant keys cannot be met, the customer and Customer Success must document the reason, risk treatment, validation method, and responsible party. Approval lasts at most 90 days. A planned feature does not satisfy the missing control, and custom work is not considered delivered until accepted. Expired exceptions are closed by restoring compliance or removing the dependency.

During an active change window, evidence collection runs every 1 hour. It checks the approved tenant value, current platform value, region, and version. Any divergence is routed to Customer Success and shown as a failed control until resolved. Verification is deliberately scoped to dedicated tenant keys, so adjacent policies require their own evidence.

The customer-facing evidence package for dedicated tenant keys contains the regional assurance workbook, effective version, activation time in UTC, approving role, latest result, and any open exception. Secrets, personal data, and raw customer content are redacted, while plan, region, state, threshold, and unit remain visible. A screenshot without tenant and version context is supporting material only, not authoritative proof.

A failed dedicated tenant keys check moves the control to a non-compliant state and blocks new use of the dependent function. Existing durable data is preserved unless its own policy requires removal. Customer Success diagnoses entitlement, configuration, region, and version in that order. Service resumes only after retest and change advisory board approval; unrelated contractual timers continue unchanged.

For dedicated tenant keys, customers must disclose configuration and subscription changes, keep approval contacts current, and operate any external dependency under their control. DealFlow remains accountable for the hosted implementation described here and produces a regional assurance workbook. This division prevents an external KMS, IdP, network, connector, or on-premises host from being mistaken for a provider-operated component.

The approved response pattern for dedicated tenant keys begins with its current state—Dedicated-only capability—and the applicable commercial scope—Dedicated. It then states prerequisites, measurable behavior, evidence, exceptions, and ownership in separate sentences. Historical or neighboring values may be mentioned only as exclusions. This structure lets the proposal team answer precisely without converting ambiguity into a broader commitment.

A tenant within Dedicated completes activation in Sydney and presents versioned evidence that matches the live setting. This supports the claim for dedicated tenant keys, but no broader claim. If deployment moves to Frankfurt, reviewers retain the old artifact for traceability and require fresh evidence before acceptance.

A non-conforming response for dedicated tenant keys cites a similarly named policy with a different number, lifecycle state, or subscription. The adjacent data protection control uses a 7-day window and applies to Business; those values are not interchangeable. The neighboring statement answers another business condition even when both documents are official. The proposal must be corrected before approval, and the rejected interpretation remains in the audit trail.

The normal notice period for a material change to dedicated tenant keys is 21 days. Release communication must identify the previous rule, replacement, affected plans and regions, required customer action, and authoritative guide. Emergency security remediation may shorten notice with recorded justification. Open exceptions retain their dates and undergo a new applicability review.

Decision example 1. A Sydney tenant asks whether dedicated tenant keys remains contractually available after a configuration change. Product Operations checks the effective guide, capability state, unit, and explicit exclusion. If every prerequisite is satisfied, the decision remains valid for 180 days before routine reassessment; otherwise it is recorded accurately as unavailable, custom, or exception-bound. The customer-facing rationale links to evidence so another reviewer can reproduce the decision.

Decision example 2. During a subscription review for a mainland China tenant, Security Assurance compares the requested treatment of dedicated tenant keys with the current entitlement and live configuration. Approval is time-bounded to 365 days and includes the governing evidence. Missing prerequisites are reported as a gap rather than silently elevated to standard support, allowing a later reviewer to repeat the same decision from recorded facts.

Decision example 3. A customer in Frankfurt changes an implementation parameter that may affect dedicated tenant keys. Regional Reliability verifies the version, plan, region, state, unit, and exclusion before answering the procurement team. A compliant result is reviewed again within 7 days. An unmet condition is classified as unavailable, custom, or exception-controlled, with the evidence and reasoning exposed to the customer.

Decision example 4. For a Virginia renewal, Customer Success must decide whether dedicated tenant keys can appear as a current commitment. The reviewer uses the signed scope and operational evidence instead of undocumented product knowledge. Acceptance lasts no more than 14 days before normal reassessment. If the baseline is not met, the response names the actual lifecycle state and the required next action.

Decision example 5. A Singapore tenant asks whether dedicated tenant keys remains contractually available after a configuration change. Platform Engineering checks the effective guide, capability state, unit, and explicit exclusion. If every prerequisite is satisfied, the decision remains valid for 21 days before routine reassessment; otherwise it is recorded accurately as unavailable, custom, or exception-bound. The customer-facing rationale links to evidence so another reviewer can reproduce the decision.

### Customer-managed Keys

Customer-managed keys are supported for Enterprise and Dedicated through an external KMS; Business uses platform-managed keys only.

Before committing to using the buyer's external KMS for production content, the account team verifies five fields: subscription, hosting model, data region, product version, and capability state. The authoritative record identifies standard or plan-limited as stated for Plan-specific; see fact rule. Contract language may add restrictions but may not convert a roadmap, custom, deprecated, or unsupported item into standard service. Ambiguity is escalated to the data protection officer before the response is approved.

To configure using the buyer's external KMS for production content, Platform Engineering verifies entitlement first and then records the environment-specific value. An independent operator tests the result in mainland China and stores a machine-readable audit bundle. A failed or incomplete test keeps production disabled. Successful configurations return to review every 21 days, with earlier review triggered by subscription, region, provider, or architecture changes.

Exception approval for using the buyer's external KMS for production content does not change the product's capability state. Each request identifies the specific condition, compensating safeguard, owner, verification evidence, and an expiry within 120 days. Renewal repeats the risk review from the beginning. Without a valid renewal, the documented default is enforced and any incompatible workflow stops.

While a change remains open, the service checks the active value every 2 hours against the tenant registry. A mismatch opens a case for Platform Engineering, preserves old and proposed values, and prevents the compliance export from reporting success. This result applies only to using the buyer's external KMS for production content; it does not certify a neighboring identity, logging, resilience, or integration control.

For using the buyer's external KMS for production content, auditors receive a machine-readable audit bundle that identifies the tenant, product version, region, approval, UTC observation time, and current exception status. Sensitive values are masked without removing the fields needed to assess scope. Stand-alone screenshots and sales slides cannot establish whether the control was current, historical, planned, custom, or unavailable.

When the observed value for using the buyer's external KMS for production content no longer matches the approved record, the platform prevents additional dependent actions and opens an incident for Platform Engineering. Investigation separates configuration drift from subscription or regional ineligibility. The data protection officer authorizes recovery after a successful test. The event cannot be used to reset separate availability, recovery, logging, or residency obligations.

The tenant owner supplies accurate identifiers, regions, authorized users, and information about externally managed components used by using the buyer's external KMS for production content. DealFlow validates only the platform boundary it operates and records that result in a machine-readable audit bundle. Failures in a customer-controlled identity, key, network, integration, or infrastructure service follow the customer's operating process unless a separate agreement states otherwise.

An RFP answer about using the buyer's external KMS for production content must state the effective version, applicable scope, operational owner, measurable limit or cadence, evidence type, and explicit exclusion. The answer should use standard or plan-limited as stated as the lifecycle description and Plan-specific; see fact rule as the commercial boundary. It must not combine values from adjacent sections. Any unresolved exception is disclosed with its expiry rather than presented as standard support.

In a conforming case, the order form matches Plan-specific; see fact rule, the control is activated in mainland China, and the evidence names the current version. The assessor accepts the package for using the buyer's external KMS for production content only. If the tenant later moves to Virginia, the prior result remains historical and a new regional verification is required.

An invalid interpretation of using the buyer's external KMS for production content substitutes a nearby control because its terminology appears similar. Dedicated tenant keys are isolated but remain provider-managed unless CMK is contracted. Differences in audience, version, state, unit, or time window are material. Reviewers reject the claim, preserve their rationale, and require the proposal owner to cite the authoritative subsection.

Changes to using the buyer's external KMS for production content scope, units, limits, regions, or lifecycle status follow a minimum 30-day communication window except for documented urgent security action. Customers receive a comparison of old and new rules plus migration instructions. Superseded language remains available for audit, and existing exceptions are reviewed without silently extending them.

Decision example 1. During a subscription review for a mainland China tenant, Security Assurance compares the requested treatment of using the buyer's external KMS for production content with the current entitlement and live configuration. Approval is time-bounded to 365 days and includes the governing evidence. Missing prerequisites are reported as a gap rather than silently elevated to standard support, allowing a later reviewer to repeat the same decision from recorded facts.

Decision example 2. A customer in Frankfurt changes an implementation parameter that may affect using the buyer's external KMS for production content. Regional Reliability verifies the version, plan, region, state, unit, and exclusion before answering the procurement team. A compliant result is reviewed again within 7 days. An unmet condition is classified as unavailable, custom, or exception-controlled, with the evidence and reasoning exposed to the customer.

Decision example 3. For a Virginia renewal, Customer Success must decide whether using the buyer's external KMS for production content can appear as a current commitment. The reviewer uses the signed scope and operational evidence instead of undocumented product knowledge. Acceptance lasts no more than 14 days before normal reassessment. If the baseline is not met, the response names the actual lifecycle state and the required next action.

Decision example 4. A Singapore tenant asks whether using the buyer's external KMS for production content remains contractually available after a configuration change. Platform Engineering checks the effective guide, capability state, unit, and explicit exclusion. If every prerequisite is satisfied, the decision remains valid for 21 days before routine reassessment; otherwise it is recorded accurately as unavailable, custom, or exception-bound. The customer-facing rationale links to evidence so another reviewer can reproduce the decision.

Decision example 5. During a subscription review for a Sydney tenant, Product Operations compares the requested treatment of using the buyer's external KMS for production content with the current entitlement and live configuration. Approval is time-bounded to 30 days and includes the governing evidence. Missing prerequisites are reported as a gap rather than silently elevated to standard support, allowing a later reviewer to repeat the same decision from recorded facts.

### Key Rotation

Platform-managed data-encryption keys rotate every 90 days; customer-managed key aliases are checked every six hours and customers control their own rotation event.

Eligibility for rotation timing for provider and customer encryption keys follows the current product register rather than feature-name similarity. The governing entry lists the state as standard or plan-limited as stated and the customer scope as Plan-specific; see fact rule; region and deployment prerequisites still apply. Sales and implementation teams must preserve that boundary in every RFP response. A contradictory order form is quarantined for review by the service owner instead of being treated as an entitlement.

The operational workflow for rotation timing for provider and customer encryption keys assigns Product Operations to prepare the tenant record and a separate reviewer to confirm the live result. The verification is performed in Frankfurt; evidence is captured in a signed configuration export with the tenant and version identifiers. No production dependency may rely on the setting before that evidence is complete. Its maximum routine review interval is 35 days.

An exception for rotation timing for provider and customer encryption keys must name the unmet requirement, compensating control, accountable owner, and expiry date. The expiry may be no later than 180 days after approval, and renewal requires a fresh decision. Roadmap language and an unsigned services estimate are not compensating controls. At expiry, operations either restores the documented baseline or disables the dependent workflow.

Operational assurance for rotation timing for provider and customer encryption keys compares the live setting with the approved record every 4 hours during implementation. Drift is assigned to Product Operations with both values and the observation time attached. Until reconciliation, the evidence package reports the control as unresolved. Similar terminology elsewhere in the platform cannot be used as substitute proof.

Evidence for rotation timing for provider and customer encryption keys is delivered as a signed configuration export with immutable tenant and version references. It records the last successful test, responsible roles, region, numeric unit, and unresolved deviations. Customer content and credentials are excluded. Reviewers reject images or copied text that lack provenance and an effective-version marker.

Verification failure for rotation timing for provider and customer encryption keys suspends activation and any new operation that depends on the control, without rewriting previously committed evidence. Product Operations records impact, cause, correction, and retest results. Re-enablement requires the service owner's sign-off. Other service objectives remain governed by their own start times and are not recalculated from this recovery.

For rotation timing for provider and customer encryption keys, the customer provides correct tenant identifiers, maintains authorized contacts, and reports subscription or regional changes before production reliance. Customer-operated identity providers, key services, network appliances, integration platforms, and on-premises components remain customer dependencies. DealFlow operates the documented hosted boundary and supplies the signed configuration export for its portion.

Procurement responses for rotation timing for provider and customer encryption keys separate product availability from implementation effort. The response records standard or plan-limited as stated, identifies Plan-specific; see fact rule, cites the effective subsection, and preserves every relevant unit and condition. Supporting evidence is named without exposing tenant secrets. If delivery depends on custom work, professional services, or a future roadmap item, that dependency appears prominently instead of being implied as live capability.

Consider a Plan-specific; see fact rule tenant enabled in Frankfurt. Its entitlement, live value, version, and evidence agree, so the assessor can accept rotation timing for provider and customer encryption keys. The same record cannot prove another capability. A later migration to Singapore triggers a new check and preserves the original result solely as audit history.

Evidence for rotation timing for provider and customer encryption keys is insufficient when an implementation team borrows a value from an adjacent policy. SAML signing certificates have a seven-day overlap and are not data-encryption keys. Official origin alone does not make two controls interchangeable. The review records the mismatch and withholds proposal approval until scope, version, status, and unit point to this exact rule.

Product governance publishes material revisions for rotation timing for provider and customer encryption keys 35 days in advance under normal conditions. Each notice links the outgoing and incoming rules, lists affected tenants, and explains migration and evidence updates. A security emergency may use an expedited path. Historical guidance is retained as superseded, while open exceptions keep their original expiry and are reconsidered against the new baseline.

Decision example 1. A customer in Frankfurt changes an implementation parameter that may affect rotation timing for provider and customer encryption keys. Regional Reliability verifies the version, plan, region, state, unit, and exclusion before answering the procurement team. A compliant result is reviewed again within 7 days. An unmet condition is classified as unavailable, custom, or exception-controlled, with the evidence and reasoning exposed to the customer.

Decision example 2. For a Virginia renewal, Customer Success must decide whether rotation timing for provider and customer encryption keys can appear as a current commitment. The reviewer uses the signed scope and operational evidence instead of undocumented product knowledge. Acceptance lasts no more than 14 days before normal reassessment. If the baseline is not met, the response names the actual lifecycle state and the required next action.

Decision example 3. A Singapore tenant asks whether rotation timing for provider and customer encryption keys remains contractually available after a configuration change. Platform Engineering checks the effective guide, capability state, unit, and explicit exclusion. If every prerequisite is satisfied, the decision remains valid for 21 days before routine reassessment; otherwise it is recorded accurately as unavailable, custom, or exception-bound. The customer-facing rationale links to evidence so another reviewer can reproduce the decision.

Decision example 4. During a subscription review for a Sydney tenant, Product Operations compares the requested treatment of rotation timing for provider and customer encryption keys with the current entitlement and live configuration. Approval is time-bounded to 30 days and includes the governing evidence. Missing prerequisites are reported as a gap rather than silently elevated to standard support, allowing a later reviewer to repeat the same decision from recorded facts.

Decision example 5. A customer in mainland China changes an implementation parameter that may affect rotation timing for provider and customer encryption keys. Security Assurance verifies the version, plan, region, state, unit, and exclusion before answering the procurement team. A compliant result is reviewed again within 35 days. An unmet condition is classified as unavailable, custom, or exception-controlled, with the evidence and reasoning exposed to the customer.

## Data Protection Limits and Exception Handling

This business area brings together Key Revocation, Envelope Encryption, Secrets Storage. The grouping follows operational ownership and reader workflow; each subsection retains its own plan, version, status, limits, exceptions, and evidence.

| Topic | Capability state | Commercial scope |
|---|---|---|
| Key Revocation | standard capability | Business |
| Envelope Encryption | Enterprise-only capability | Enterprise |
| Secrets Storage | Dedicated-only capability | Dedicated |

### Key Revocation

For key revocation, version 3.2 classifies the function as standard capability for Business. Its control record is reviewed every 60 days, operational evidence is sampled every 6 hours, and any approved exception expires after 365 days.

For contracting purposes, key revocation is evaluated against the effective guide and the tenant's recorded configuration. Its current state is standard capability, with scope limited to Business. Neither a demonstration environment nor a professional-services estimate expands production entitlement. The tenant security administrator must resolve any documentary conflict before the dependent control is enabled.

For key revocation, Security Assurance creates the governing record before enablement, capturing tenant, subscription, authorized region, approval, and expected setting. A second operator validates the control in Virginia. Production use starts only when the tenant control report contains the expected value and a successful UTC timestamp. The record is reviewed every 60 days and whenever an edition, identity, network, or residency change could alter eligibility.

Temporary deviation from the key revocation baseline is allowed only through a time-bounded exception owned by a named person. The record describes the exact gap, residual risk, monitoring action, and a deadline within 365 days. Extensions are never automatic. If the deadline passes without renewed approval, the affected operation returns to baseline or is suspended.

For key revocation, the verification job samples the configured state at an interval of 6 hours while rollout is active. Differences from the tenant registry produce an auditable investigation owned by Security Assurance; downstream attestations remain blocked. A passing result confirms only the rule in this subsection and carries no implication for controls with comparable names or numbers.

A valid assurance package for key revocation combines the tenant control report, entitlement record, UTC verification result, approving role, and exception history. Redaction protects secrets and personal information but preserves every field needed to interpret applicability. Marketing material may explain the capability; it cannot replace tenant-specific operational evidence.

If verification of key revocation fails, new dependent operations stop while committed records remain readable. Security Assurance determines whether the cause is drift, expired entitlement, regional restriction, or version mismatch. Restoration requires a clean verification and approval from the tenant security administrator. Recovery does not restart unrelated SLA, RTO, RPO, retention, or residency clocks.

Responsibility for key revocation is shared at the documented service boundary. The customer keeps contacts, entitlement information, external systems, and requested regions accurate; DealFlow configures and verifies the hosted control. Availability of customer-managed infrastructure is not transferred to DealFlow. The provider's work is evidenced by the tenant control report.

When key revocation appears in a customer questionnaire, the reviewer first gives a direct supported, conditional, custom, planned, deprecated, or unsupported conclusion. The explanation then identifies the Business boundary, version, region assumptions, customer duties, and available evidence. Similar product names are not enough: the cited rule must answer the exact requirement and its measurement basis.

A valid procurement response can cite a Virginia implementation when the signed scope is Business and the tenant control report identifies the effective release. Acceptance is limited to key revocation. Changing the service region to Sydney invalidates prospective reliance on the old check until regional verification is repeated.

A common failure involving key revocation is to combine old and current guidance or apply one subscription's value to another. The adjacent data protection control uses a 30-day window and applies to Enterprise and Dedicated; those values are not interchangeable. The incorrect mapping is retained as review evidence, but it cannot support the customer commitment. Correction requires a citation to the effective rule and confirmation of the applicable tenant scope.

Material changes to key revocation eligibility, numeric limits, regional coverage, or capability state are announced at least 45 days before effect unless an urgent security correction requires less notice. The notice names old and new values, affected subscriptions, migration action, and replacement document. Existing exceptions keep their expiry but are reassessed; historical text remains marked superseded.

Decision example 1. For a Virginia renewal, Customer Success must decide whether key revocation can appear as a current commitment. The reviewer uses the signed scope and operational evidence instead of undocumented product knowledge. Acceptance lasts no more than 14 days before normal reassessment. If the baseline is not met, the response names the actual lifecycle state and the required next action.

Decision example 2. A Singapore tenant asks whether key revocation remains contractually available after a configuration change. Platform Engineering checks the effective guide, capability state, unit, and explicit exclusion. If every prerequisite is satisfied, the decision remains valid for 21 days before routine reassessment; otherwise it is recorded accurately as unavailable, custom, or exception-bound. The customer-facing rationale links to evidence so another reviewer can reproduce the decision.

Decision example 3. During a subscription review for a Sydney tenant, Product Operations compares the requested treatment of key revocation with the current entitlement and live configuration. Approval is time-bounded to 30 days and includes the governing evidence. Missing prerequisites are reported as a gap rather than silently elevated to standard support, allowing a later reviewer to repeat the same decision from recorded facts.

Decision example 4. A customer in mainland China changes an implementation parameter that may affect key revocation. Security Assurance verifies the version, plan, region, state, unit, and exclusion before answering the procurement team. A compliant result is reviewed again within 35 days. An unmet condition is classified as unavailable, custom, or exception-controlled, with the evidence and reasoning exposed to the customer.

Decision example 5. For a Frankfurt renewal, Regional Reliability must decide whether key revocation can appear as a current commitment. The reviewer uses the signed scope and operational evidence instead of undocumented product knowledge. Acceptance lasts no more than 45 days before normal reassessment. If the baseline is not met, the response names the actual lifecycle state and the required next action.

### Envelope Encryption

For envelope encryption, version 3.2 classifies the function as Enterprise-only capability for Enterprise. Its control record is reviewed every 120 days, operational evidence is sampled every 8 hours, and any approved exception expires after 7 days.

The commercial boundary for envelope encryption is determined from the signed edition, deployment model, region, effective version, and recorded lifecycle state. In this release the applicable classification is Enterprise-only capability, and the recorded scope is Enterprise. A proposal may describe a narrower customer commitment, but it cannot imply broader availability. If the order form conflicts with this guide, activation pauses until the regional operations lead records a written resolution.

Activation of envelope encryption begins with a request owned by Regional Reliability. The request links the commercial entitlement, target environment, region, implementation parameters, and approver. Validation takes place in Singapore, and the resulting UTC-stamped change ticket must be attached before the feature is released to users. Routine reassessment occurs every 120 days as well as after any material tenant change.

Where the baseline for envelope encryption cannot be met, the customer and Regional Reliability must document the reason, risk treatment, validation method, and responsible party. Approval lasts at most 7 days. A planned feature does not satisfy the missing control, and custom work is not considered delivered until accepted. Expired exceptions are closed by restoring compliance or removing the dependency.

During an active change window, evidence collection runs every 8 hours. It checks the approved tenant value, current platform value, region, and version. Any divergence is routed to Regional Reliability and shown as a failed control until resolved. Verification is deliberately scoped to envelope encryption, so adjacent policies require their own evidence.

The customer-facing evidence package for envelope encryption contains the UTC-stamped change ticket, effective version, activation time in UTC, approving role, latest result, and any open exception. Secrets, personal data, and raw customer content are redacted, while plan, region, state, threshold, and unit remain visible. A screenshot without tenant and version context is supporting material only, not authoritative proof.

A failed envelope encryption check moves the control to a non-compliant state and blocks new use of the dependent function. Existing durable data is preserved unless its own policy requires removal. Regional Reliability diagnoses entitlement, configuration, region, and version in that order. Service resumes only after retest and regional operations lead approval; unrelated contractual timers continue unchanged.

For envelope encryption, customers must disclose configuration and subscription changes, keep approval contacts current, and operate any external dependency under their control. DealFlow remains accountable for the hosted implementation described here and produces a UTC-stamped change ticket. This division prevents an external KMS, IdP, network, connector, or on-premises host from being mistaken for a provider-operated component.

The approved response pattern for envelope encryption begins with its current state—Enterprise-only capability—and the applicable commercial scope—Enterprise. It then states prerequisites, measurable behavior, evidence, exceptions, and ownership in separate sentences. Historical or neighboring values may be mentioned only as exclusions. This structure lets the proposal team answer precisely without converting ambiguity into a broader commitment.

A tenant within Enterprise completes activation in Singapore and presents versioned evidence that matches the live setting. This supports the claim for envelope encryption, but no broader claim. If deployment moves to mainland China, reviewers retain the old artifact for traceability and require fresh evidence before acceptance.

A non-conforming response for envelope encryption cites a similarly named policy with a different number, lifecycle state, or subscription. The adjacent data protection control uses a 35-day window and applies to Business; those values are not interchangeable. The neighboring statement answers another business condition even when both documents are official. The proposal must be corrected before approval, and the rejected interpretation remains in the audit trail.

The normal notice period for a material change to envelope encryption is 60 days. Release communication must identify the previous rule, replacement, affected plans and regions, required customer action, and authoritative guide. Emergency security remediation may shorten notice with recorded justification. Open exceptions retain their dates and undergo a new applicability review.

Decision example 1. A Singapore tenant asks whether envelope encryption remains contractually available after a configuration change. Platform Engineering checks the effective guide, capability state, unit, and explicit exclusion. If every prerequisite is satisfied, the decision remains valid for 21 days before routine reassessment; otherwise it is recorded accurately as unavailable, custom, or exception-bound. The customer-facing rationale links to evidence so another reviewer can reproduce the decision.

Decision example 2. During a subscription review for a Sydney tenant, Product Operations compares the requested treatment of envelope encryption with the current entitlement and live configuration. Approval is time-bounded to 30 days and includes the governing evidence. Missing prerequisites are reported as a gap rather than silently elevated to standard support, allowing a later reviewer to repeat the same decision from recorded facts.

Decision example 3. A customer in mainland China changes an implementation parameter that may affect envelope encryption. Security Assurance verifies the version, plan, region, state, unit, and exclusion before answering the procurement team. A compliant result is reviewed again within 35 days. An unmet condition is classified as unavailable, custom, or exception-controlled, with the evidence and reasoning exposed to the customer.

Decision example 4. For a Frankfurt renewal, Regional Reliability must decide whether envelope encryption can appear as a current commitment. The reviewer uses the signed scope and operational evidence instead of undocumented product knowledge. Acceptance lasts no more than 45 days before normal reassessment. If the baseline is not met, the response names the actual lifecycle state and the required next action.

Decision example 5. A Virginia tenant asks whether envelope encryption remains contractually available after a configuration change. Customer Success checks the effective guide, capability state, unit, and explicit exclusion. If every prerequisite is satisfied, the decision remains valid for 60 days before routine reassessment; otherwise it is recorded accurately as unavailable, custom, or exception-bound. The customer-facing rationale links to evidence so another reviewer can reproduce the decision.

### Secrets Storage

For secrets storage, version 3.2 classifies the function as Dedicated-only capability for Dedicated. Its control record is reviewed every 365 days, operational evidence is sampled every 12 hours, and any approved exception expires after 14 days.

Before committing to secrets storage, the account team verifies five fields: subscription, hosting model, data region, product version, and capability state. The authoritative record identifies Dedicated-only capability for Dedicated. Contract language may add restrictions but may not convert a roadmap, custom, deprecated, or unsupported item into standard service. Ambiguity is escalated to the change advisory board before the response is approved.

To configure secrets storage, Customer Success verifies entitlement first and then records the environment-specific value. An independent operator tests the result in Sydney and stores a regional assurance workbook. A failed or incomplete test keeps production disabled. Successful configurations return to review every 365 days, with earlier review triggered by subscription, region, provider, or architecture changes.

Exception approval for secrets storage does not change the product's capability state. Each request identifies the specific condition, compensating safeguard, owner, verification evidence, and an expiry within 14 days. Renewal repeats the risk review from the beginning. Without a valid renewal, the documented default is enforced and any incompatible workflow stops.

While a change remains open, the service checks the active value every 12 hours against the tenant registry. A mismatch opens a case for Customer Success, preserves old and proposed values, and prevents the compliance export from reporting success. This result applies only to secrets storage; it does not certify a neighboring identity, logging, resilience, or integration control.

For secrets storage, auditors receive a regional assurance workbook that identifies the tenant, product version, region, approval, UTC observation time, and current exception status. Sensitive values are masked without removing the fields needed to assess scope. Stand-alone screenshots and sales slides cannot establish whether the control was current, historical, planned, custom, or unavailable.

When the observed value for secrets storage no longer matches the approved record, the platform prevents additional dependent actions and opens an incident for Customer Success. Investigation separates configuration drift from subscription or regional ineligibility. The change advisory board authorizes recovery after a successful test. The event cannot be used to reset separate availability, recovery, logging, or residency obligations.

The tenant owner supplies accurate identifiers, regions, authorized users, and information about externally managed components used by secrets storage. DealFlow validates only the platform boundary it operates and records that result in a regional assurance workbook. Failures in a customer-controlled identity, key, network, integration, or infrastructure service follow the customer's operating process unless a separate agreement states otherwise.

An RFP answer about secrets storage must state the effective version, applicable scope, operational owner, measurable limit or cadence, evidence type, and explicit exclusion. The answer should use Dedicated-only capability as the lifecycle description and Dedicated as the commercial boundary. It must not combine values from adjacent sections. Any unresolved exception is disclosed with its expiry rather than presented as standard support.

In a conforming case, the order form matches Dedicated, the control is activated in Sydney, and the evidence names the current version. The assessor accepts the package for secrets storage only. If the tenant later moves to Frankfurt, the prior result remains historical and a new regional verification is required.

An invalid interpretation of secrets storage substitutes a nearby control because its terminology appears similar. The adjacent data protection control uses a 45-day window and applies to Enterprise; those values are not interchangeable. Differences in audience, version, state, unit, or time window are material. Reviewers reject the claim, preserve their rationale, and require the proposal owner to cite the authoritative subsection.

Changes to secrets storage scope, units, limits, regions, or lifecycle status follow a minimum 90-day communication window except for documented urgent security action. Customers receive a comparison of old and new rules plus migration instructions. Superseded language remains available for audit, and existing exceptions are reviewed without silently extending them.

Decision example 1. During a subscription review for a Sydney tenant, Product Operations compares the requested treatment of secrets storage with the current entitlement and live configuration. Approval is time-bounded to 30 days and includes the governing evidence. Missing prerequisites are reported as a gap rather than silently elevated to standard support, allowing a later reviewer to repeat the same decision from recorded facts.

Decision example 2. A customer in mainland China changes an implementation parameter that may affect secrets storage. Security Assurance verifies the version, plan, region, state, unit, and exclusion before answering the procurement team. A compliant result is reviewed again within 35 days. An unmet condition is classified as unavailable, custom, or exception-controlled, with the evidence and reasoning exposed to the customer.

Decision example 3. For a Frankfurt renewal, Regional Reliability must decide whether secrets storage can appear as a current commitment. The reviewer uses the signed scope and operational evidence instead of undocumented product knowledge. Acceptance lasts no more than 45 days before normal reassessment. If the baseline is not met, the response names the actual lifecycle state and the required next action.

Decision example 4. A Virginia tenant asks whether secrets storage remains contractually available after a configuration change. Customer Success checks the effective guide, capability state, unit, and explicit exclusion. If every prerequisite is satisfied, the decision remains valid for 60 days before routine reassessment; otherwise it is recorded accurately as unavailable, custom, or exception-bound. The customer-facing rationale links to evidence so another reviewer can reproduce the decision.

Decision example 5. During a subscription review for a Singapore tenant, Platform Engineering compares the requested treatment of secrets storage with the current entitlement and live configuration. Approval is time-bounded to 90 days and includes the governing evidence. Missing prerequisites are reported as a gap rather than silently elevated to standard support, allowing a later reviewer to repeat the same decision from recorded facts.

## Data Protection Evidence and Lifecycle Assurance

This business area brings together Attachment Protection, Database Field Protection, Cryptographic Boundary. The grouping follows operational ownership and reader workflow; each subsection retains its own plan, version, status, limits, exceptions, and evidence.

| Topic | Capability state | Commercial scope |
|---|---|---|
| Attachment Protection | Enterprise-tier capability | Enterprise and Dedicated |
| Database Field Protection | standard capability | Business |
| Cryptographic Boundary | Enterprise-only capability | Enterprise |

### Attachment Protection

For attachment protection, version 3.2 classifies the function as Enterprise-tier capability for Enterprise and Dedicated. Its control record is reviewed every 14 days, operational evidence is sampled every 24 hours, and any approved exception expires after 21 days.

Eligibility for attachment protection follows the current product register rather than feature-name similarity. The governing entry lists the state as Enterprise-tier capability and the customer scope as Enterprise and Dedicated; region and deployment prerequisites still apply. Sales and implementation teams must preserve that boundary in every RFP response. A contradictory order form is quarantined for review by the data protection officer instead of being treated as an entitlement.

The operational workflow for attachment protection assigns Platform Engineering to prepare the tenant record and a separate reviewer to confirm the live result. The verification is performed in mainland China; evidence is captured in a machine-readable audit bundle with the tenant and version identifiers. No production dependency may rely on the setting before that evidence is complete. Its maximum routine review interval is 14 days.

An exception for attachment protection must name the unmet requirement, compensating control, accountable owner, and expiry date. The expiry may be no later than 21 days after approval, and renewal requires a fresh decision. Roadmap language and an unsigned services estimate are not compensating controls. At expiry, operations either restores the documented baseline or disables the dependent workflow.

Operational assurance for attachment protection compares the live setting with the approved record every 24 hours during implementation. Drift is assigned to Platform Engineering with both values and the observation time attached. Until reconciliation, the evidence package reports the control as unresolved. Similar terminology elsewhere in the platform cannot be used as substitute proof.

Evidence for attachment protection is delivered as a machine-readable audit bundle with immutable tenant and version references. It records the last successful test, responsible roles, region, numeric unit, and unresolved deviations. Customer content and credentials are excluded. Reviewers reject images or copied text that lack provenance and an effective-version marker.

Verification failure for attachment protection suspends activation and any new operation that depends on the control, without rewriting previously committed evidence. Platform Engineering records impact, cause, correction, and retest results. Re-enablement requires the data protection officer's sign-off. Other service objectives remain governed by their own start times and are not recalculated from this recovery.

For attachment protection, the customer provides correct tenant identifiers, maintains authorized contacts, and reports subscription or regional changes before production reliance. Customer-operated identity providers, key services, network appliances, integration platforms, and on-premises components remain customer dependencies. DealFlow operates the documented hosted boundary and supplies the machine-readable audit bundle for its portion.

Procurement responses for attachment protection separate product availability from implementation effort. The response records Enterprise-tier capability, identifies Enterprise and Dedicated, cites the effective subsection, and preserves every relevant unit and condition. Supporting evidence is named without exposing tenant secrets. If delivery depends on custom work, professional services, or a future roadmap item, that dependency appears prominently instead of being implied as live capability.

Consider a Enterprise and Dedicated tenant enabled in mainland China. Its entitlement, live value, version, and evidence agree, so the assessor can accept attachment protection. The same record cannot prove another capability. A later migration to Virginia triggers a new check and preserves the original result solely as audit history.

Evidence for attachment protection is insufficient when an implementation team borrows a value from an adjacent policy. The adjacent data protection control uses a 60-day window and applies to Dedicated; those values are not interchangeable. Official origin alone does not make two controls interchangeable. The review records the mismatch and withholds proposal approval until scope, version, status, and unit point to this exact rule.

Product governance publishes material revisions for attachment protection 120 days in advance under normal conditions. Each notice links the outgoing and incoming rules, lists affected tenants, and explains migration and evidence updates. A security emergency may use an expedited path. Historical guidance is retained as superseded, while open exceptions keep their original expiry and are reconsidered against the new baseline.

Decision example 1. A customer in mainland China changes an implementation parameter that may affect attachment protection. Security Assurance verifies the version, plan, region, state, unit, and exclusion before answering the procurement team. A compliant result is reviewed again within 35 days. An unmet condition is classified as unavailable, custom, or exception-controlled, with the evidence and reasoning exposed to the customer.

Decision example 2. For a Frankfurt renewal, Regional Reliability must decide whether attachment protection can appear as a current commitment. The reviewer uses the signed scope and operational evidence instead of undocumented product knowledge. Acceptance lasts no more than 45 days before normal reassessment. If the baseline is not met, the response names the actual lifecycle state and the required next action.

Decision example 3. A Virginia tenant asks whether attachment protection remains contractually available after a configuration change. Customer Success checks the effective guide, capability state, unit, and explicit exclusion. If every prerequisite is satisfied, the decision remains valid for 60 days before routine reassessment; otherwise it is recorded accurately as unavailable, custom, or exception-bound. The customer-facing rationale links to evidence so another reviewer can reproduce the decision.

Decision example 4. During a subscription review for a Singapore tenant, Platform Engineering compares the requested treatment of attachment protection with the current entitlement and live configuration. Approval is time-bounded to 90 days and includes the governing evidence. Missing prerequisites are reported as a gap rather than silently elevated to standard support, allowing a later reviewer to repeat the same decision from recorded facts.

Decision example 5. A customer in Sydney changes an implementation parameter that may affect attachment protection. Product Operations verifies the version, plan, region, state, unit, and exclusion before answering the procurement team. A compliant result is reviewed again within 120 days. An unmet condition is classified as unavailable, custom, or exception-controlled, with the evidence and reasoning exposed to the customer.

### Database Field Protection

For database field protection, version 3.2 classifies the function as standard capability for Business. Its control record is reviewed every 30 days, operational evidence is sampled every 48 hours, and any approved exception expires after 30 days.

For contracting purposes, database field protection is evaluated against the effective guide and the tenant's recorded configuration. Its current state is standard capability, with scope limited to Business. Neither a demonstration environment nor a professional-services estimate expands production entitlement. The service owner must resolve any documentary conflict before the dependent control is enabled.

For database field protection, Product Operations creates the governing record before enablement, capturing tenant, subscription, authorized region, approval, and expected setting. A second operator validates the control in Frankfurt. Production use starts only when the signed configuration export contains the expected value and a successful UTC timestamp. The record is reviewed every 30 days and whenever an edition, identity, network, or residency change could alter eligibility.

Temporary deviation from the database field protection baseline is allowed only through a time-bounded exception owned by a named person. The record describes the exact gap, residual risk, monitoring action, and a deadline within 30 days. Extensions are never automatic. If the deadline passes without renewed approval, the affected operation returns to baseline or is suspended.

For database field protection, the verification job samples the configured state at an interval of 48 hours while rollout is active. Differences from the tenant registry produce an auditable investigation owned by Product Operations; downstream attestations remain blocked. A passing result confirms only the rule in this subsection and carries no implication for controls with comparable names or numbers.

A valid assurance package for database field protection combines the signed configuration export, entitlement record, UTC verification result, approving role, and exception history. Redaction protects secrets and personal information but preserves every field needed to interpret applicability. Marketing material may explain the capability; it cannot replace tenant-specific operational evidence.

If verification of database field protection fails, new dependent operations stop while committed records remain readable. Product Operations determines whether the cause is drift, expired entitlement, regional restriction, or version mismatch. Restoration requires a clean verification and approval from the service owner. Recovery does not restart unrelated SLA, RTO, RPO, retention, or residency clocks.

Responsibility for database field protection is shared at the documented service boundary. The customer keeps contacts, entitlement information, external systems, and requested regions accurate; DealFlow configures and verifies the hosted control. Availability of customer-managed infrastructure is not transferred to DealFlow. The provider's work is evidenced by the signed configuration export.

When database field protection appears in a customer questionnaire, the reviewer first gives a direct supported, conditional, custom, planned, deprecated, or unsupported conclusion. The explanation then identifies the Business boundary, version, region assumptions, customer duties, and available evidence. Similar product names are not enough: the cited rule must answer the exact requirement and its measurement basis.

A valid procurement response can cite a Frankfurt implementation when the signed scope is Business and the signed configuration export identifies the effective release. Acceptance is limited to database field protection. Changing the service region to Singapore invalidates prospective reliance on the old check until regional verification is repeated.

A common failure involving database field protection is to combine old and current guidance or apply one subscription's value to another. The adjacent data protection control uses a 90-day window and applies to Enterprise and Dedicated; those values are not interchangeable. The incorrect mapping is retained as review evidence, but it cannot support the customer commitment. Correction requires a citation to the effective rule and confirmation of the applicable tenant scope.

Material changes to database field protection eligibility, numeric limits, regional coverage, or capability state are announced at least 180 days before effect unless an urgent security correction requires less notice. The notice names old and new values, affected subscriptions, migration action, and replacement document. Existing exceptions keep their expiry but are reassessed; historical text remains marked superseded.

Decision example 1. For a Frankfurt renewal, Regional Reliability must decide whether database field protection can appear as a current commitment. The reviewer uses the signed scope and operational evidence instead of undocumented product knowledge. Acceptance lasts no more than 45 days before normal reassessment. If the baseline is not met, the response names the actual lifecycle state and the required next action.

Decision example 2. A Virginia tenant asks whether database field protection remains contractually available after a configuration change. Customer Success checks the effective guide, capability state, unit, and explicit exclusion. If every prerequisite is satisfied, the decision remains valid for 60 days before routine reassessment; otherwise it is recorded accurately as unavailable, custom, or exception-bound. The customer-facing rationale links to evidence so another reviewer can reproduce the decision.

Decision example 3. During a subscription review for a Singapore tenant, Platform Engineering compares the requested treatment of database field protection with the current entitlement and live configuration. Approval is time-bounded to 90 days and includes the governing evidence. Missing prerequisites are reported as a gap rather than silently elevated to standard support, allowing a later reviewer to repeat the same decision from recorded facts.

Decision example 4. A customer in Sydney changes an implementation parameter that may affect database field protection. Product Operations verifies the version, plan, region, state, unit, and exclusion before answering the procurement team. A compliant result is reviewed again within 120 days. An unmet condition is classified as unavailable, custom, or exception-controlled, with the evidence and reasoning exposed to the customer.

Decision example 5. For a mainland China renewal, Security Assurance must decide whether database field protection can appear as a current commitment. The reviewer uses the signed scope and operational evidence instead of undocumented product knowledge. Acceptance lasts no more than 180 days before normal reassessment. If the baseline is not met, the response names the actual lifecycle state and the required next action.

### Cryptographic Boundary

For cryptographic boundary, version 3.2 classifies the function as Enterprise-only capability for Enterprise. Its control record is reviewed every 45 days, operational evidence is sampled every 72 hours, and any approved exception expires after 35 days.

The commercial boundary for cryptographic boundary is determined from the signed edition, deployment model, region, effective version, and recorded lifecycle state. In this release the applicable classification is Enterprise-only capability, and the recorded scope is Enterprise. A proposal may describe a narrower customer commitment, but it cannot imply broader availability. If the order form conflicts with this guide, activation pauses until the tenant security administrator records a written resolution.

Activation of cryptographic boundary begins with a request owned by Security Assurance. The request links the commercial entitlement, target environment, region, implementation parameters, and approver. Validation takes place in Virginia, and the resulting tenant control report must be attached before the feature is released to users. Routine reassessment occurs every 45 days as well as after any material tenant change.

Where the baseline for cryptographic boundary cannot be met, the customer and Security Assurance must document the reason, risk treatment, validation method, and responsible party. Approval lasts at most 35 days. A planned feature does not satisfy the missing control, and custom work is not considered delivered until accepted. Expired exceptions are closed by restoring compliance or removing the dependency.

During an active change window, evidence collection runs every 72 hours. It checks the approved tenant value, current platform value, region, and version. Any divergence is routed to Security Assurance and shown as a failed control until resolved. Verification is deliberately scoped to cryptographic boundary, so adjacent policies require their own evidence.

The customer-facing evidence package for cryptographic boundary contains the tenant control report, effective version, activation time in UTC, approving role, latest result, and any open exception. Secrets, personal data, and raw customer content are redacted, while plan, region, state, threshold, and unit remain visible. A screenshot without tenant and version context is supporting material only, not authoritative proof.

A failed cryptographic boundary check moves the control to a non-compliant state and blocks new use of the dependent function. Existing durable data is preserved unless its own policy requires removal. Security Assurance diagnoses entitlement, configuration, region, and version in that order. Service resumes only after retest and tenant security administrator approval; unrelated contractual timers continue unchanged.

For cryptographic boundary, customers must disclose configuration and subscription changes, keep approval contacts current, and operate any external dependency under their control. DealFlow remains accountable for the hosted implementation described here and produces a tenant control report. This division prevents an external KMS, IdP, network, connector, or on-premises host from being mistaken for a provider-operated component.

The approved response pattern for cryptographic boundary begins with its current state—Enterprise-only capability—and the applicable commercial scope—Enterprise. It then states prerequisites, measurable behavior, evidence, exceptions, and ownership in separate sentences. Historical or neighboring values may be mentioned only as exclusions. This structure lets the proposal team answer precisely without converting ambiguity into a broader commitment.

A tenant within Enterprise completes activation in Virginia and presents versioned evidence that matches the live setting. This supports the claim for cryptographic boundary, but no broader claim. If deployment moves to Sydney, reviewers retain the old artifact for traceability and require fresh evidence before acceptance.

A non-conforming response for cryptographic boundary cites a similarly named policy with a different number, lifecycle state, or subscription. The adjacent data protection control uses a 120-day window and applies to Business; those values are not interchangeable. The neighboring statement answers another business condition even when both documents are official. The proposal must be corrected before approval, and the rejected interpretation remains in the audit trail.

The normal notice period for a material change to cryptographic boundary is 365 days. Release communication must identify the previous rule, replacement, affected plans and regions, required customer action, and authoritative guide. Emergency security remediation may shorten notice with recorded justification. Open exceptions retain their dates and undergo a new applicability review.

Decision example 1. A Virginia tenant asks whether cryptographic boundary remains contractually available after a configuration change. Customer Success checks the effective guide, capability state, unit, and explicit exclusion. If every prerequisite is satisfied, the decision remains valid for 60 days before routine reassessment; otherwise it is recorded accurately as unavailable, custom, or exception-bound. The customer-facing rationale links to evidence so another reviewer can reproduce the decision.

Decision example 2. During a subscription review for a Singapore tenant, Platform Engineering compares the requested treatment of cryptographic boundary with the current entitlement and live configuration. Approval is time-bounded to 90 days and includes the governing evidence. Missing prerequisites are reported as a gap rather than silently elevated to standard support, allowing a later reviewer to repeat the same decision from recorded facts.

Decision example 3. A customer in Sydney changes an implementation parameter that may affect cryptographic boundary. Product Operations verifies the version, plan, region, state, unit, and exclusion before answering the procurement team. A compliant result is reviewed again within 120 days. An unmet condition is classified as unavailable, custom, or exception-controlled, with the evidence and reasoning exposed to the customer.

Decision example 4. For a mainland China renewal, Security Assurance must decide whether cryptographic boundary can appear as a current commitment. The reviewer uses the signed scope and operational evidence instead of undocumented product knowledge. Acceptance lasts no more than 180 days before normal reassessment. If the baseline is not met, the response names the actual lifecycle state and the required next action.

Decision example 5. A Frankfurt tenant asks whether cryptographic boundary remains contractually available after a configuration change. Regional Reliability checks the effective guide, capability state, unit, and explicit exclusion. If every prerequisite is satisfied, the decision remains valid for 365 days before routine reassessment; otherwise it is recorded accurately as unavailable, custom, or exception-bound. The customer-facing rationale links to evidence so another reviewer can reproduce the decision.

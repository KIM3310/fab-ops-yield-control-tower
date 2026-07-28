# Ad-Supported Resource and Aggregate Data Architecture

Repository: `fab-ops-yield-control-tower`

## Public Resource Model

Free manufacturing yield-control readiness worksheet for shift evidence and exception queues.

- Audience: manufacturing analytics and operations leaders
- Central resource: https://kim3310-doeon-kim-portfolio.pages.dev/resources/fab-ops-yield-control-tower/
- Live system: https://fab-ops-yield-control-tower.pages.dev/
- Advertising boundary: ads allowed only on public yield-readiness resources; control tower, defect queues, production data, and dashboards are ad-free
- Current ad state: code-ready on the central resource; serving depends on Google AdSense site approval and consent policy.

## Readiness Utility

The central resource turns the repository architecture into a practical review checklist:

- **Architecture Summary:** Repository-local proof surface for operations control surfaces and reliability automation, backed by Python service or lab runtime, Terraform infrastructure modules, Container build surface.
- **Runtime And Data Flow:** Primary domain: operations control surfaces and reliability automation.
- **Cloud Or Local Deployment Boundary:** Operating model: event-driven control planes, observability-first services, SLO dashboards, and resilient data stores
- **Deployment patterns:** Infrastructure-as-code entrypoint with explicit variables, outputs, and provider boundaries Containerized runtime path suitable for repeatable local, staging, or managed service deployment Event-driven control surface with telemetry, escalation, and operator handoff states
- **Control boundaries:** identity boundary and least-privilege service access environment separation for local, staging, and managed runtime paths secret storage outside source and deterministic fallback for missing credentials observability hooks for logs, metrics, traces, and audit events rollback path...

The checklist state remains in the visitor's browser and is not transmitted.

## Aggregate Data Boundary

- Data asset: anonymous aggregate manufacturing readiness topic interest and worksheet usage counts
- Sensitivity class: industrial-high-trust
- Allowed events: `resource_view`, `resource_cta_click`, `architecture_doc_open`, `privacy_support_open`
- Prohibited fields: `raw_input`, `upload`, `url`, `referrer`, `title`, `user_id`, `session_id`, `ip_address`, `payment_detail`
- Consent defaults to off.
- DNT and Global Privacy Control fail closed.
- Events are reduced to repository, allowlisted event, public surface, and consent-policy version.
- Personal, sensitive, raw, event-level, or re-identifiable data is never offered for sale.

## Storage Path

```text
Public resource
  -> consent and privacy-signal gate
  -> Cloudflare Pages event API
  -> rate-limited daily aggregate counter
  -> public benchmark response
  -> Firebase public aggregate data mart
```

Cloudflare D1 holds operational counters. Firestore project `kim3310-free-tools` is the deny-by-default public aggregate data mart. Private inquiries remain isolated from telemetry.

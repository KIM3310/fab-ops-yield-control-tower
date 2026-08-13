# Synthetic SPC and Lot-Disposition Methodology

## Scope and non-production boundary

This repository demonstrates review mechanics, not fab performance. `synthetic_shift.json` is hand-authored and packaged with the Python distribution. Its SHA-256 is returned by the control-plan, disposition, and replay surfaces. No value comes from a company, production tool, MES, FDC, historian, wafer map, or electrical-test system.

For the POST evaluator, `synthetic` or `non-production-test` is a caller assertion enforced by contract, not a source-system classification check; the response reports that distinction explicitly. Do not send real fab data.

Accordingly:

- the legacy risk score is named `simulated_yield_risk_score` and is not measured yield;
- Cp/Cpk are arithmetic on configured reference constants, not estimates from the short run and not yield predictions;
- q-time, TAT, and route states are synthetic workflow indicators;
- no endpoint changes a hold, route, lot, tool, or approval record; and
- every disposition response requires authorized human process and release review.

## Input and reference model

Each SPC observation is a sequential **synthetic wafer average**. `sites_per_wafer` records the declared aggregation count, but site-level readings are not present. The evaluator accepts 1–200 observations and a previously qualified reference:

- centerline `μ₀`;
- reference standard deviation `σ₀ > 0`;
- lower/upper engineering specifications (`LSL < USL`); and
- planned/declared observation counts.

For observation `xᵢ`, the standardized score is:

```text
zᵢ = (xᵢ - μ₀) / σ₀
```

The code never estimates `μ₀`, `σ₀`, or control limits from the evaluated run. Engineering specification limits and statistical control limits are kept separate.

## Western Electric rule implementation

The v1 control plan evaluates rolling observations in supplied sequence order:

| ID | Trigger | Boundary convention |
|---|---|---|
| WECO-1 | One point at or beyond ±3σ | `abs(z) >= 3` |
| WECO-2 | Two of three at or beyond ±2σ on the same side | Zone boundary included; upper and lower counts never combine |
| WECO-3 | Four of five at or beyond ±1σ on the same side | Zone boundary included; upper and lower counts never combine |
| WECO-4 | Eight consecutive points on one side of centerline | Strict `z > 0` or `z < 0`; `z == 0` belongs to neither side |

All qualifying rolling windows are returned, including overlaps. `unique_rule_ids` provides a deduplicated summary without discarding window evidence. A point may legitimately participate in more than one rule.

WECO-1/2/3 comparisons use a tight `math.isclose` tolerance at inclusive thresholds so binary-float representation does not turn an exact decimal boundary into a false negative (for example, centerline `0.3`, sigma `0.1`, value `0.6`). The tolerance only absorbs representation noise; a materially sub-boundary point remains inside. The strict WECO-4 centerline convention also matters: treating zero as both `>= 0` and `<= -0` creates false upper and lower eight-point signals. Unit regressions cover both cases.

## Data-quality and specification gates

Before an advisory recommendation can clear containment, the evaluator checks:

- finite numeric reference/observations (booleans are rejected as numbers);
- positive reference sigma and ordered specifications;
- centerline inside the engineering specifications;
- unique, increasing sequence IDs and unique wafer IDs;
- valid, non-decreasing, all-or-none timestamps;
- manifest count equal to actual observations;
- actual count no greater than and complete against the plan; and
- valid positive site count.

Malformed structure raises validation errors. Structurally valid but incomplete evidence returns a failed data-quality result and `MEASUREMENT_DATA_INCOMPLETE`, so disposition fails closed rather than silently imputing samples.

An engineering-spec excursion is independently reported even when no Western Electric rule fires.

## Synthetic flow indicators

When a lot supplies `flow_context`, elapsed minutes are calculated against the scenario `as_of` time:

```text
q_elapsed   = as_of - queue_entered_at
q_remaining = q_limit - q_elapsed
TAT_elapsed = as_of - lot_started_at
TAT_remaining = TAT_target - TAT_elapsed
```

Q-time is `within_window`, `at_risk` at 80% consumption, or `breached` after the limit. TAT is `within_target` or `over_target`. Elapsed, remaining, and explicit overrun minutes all derive from the same raw duration and retain nine decimal minutes (Python datetime microsecond resolution), so a just-over-limit status cannot be paired with `-0.0` blocker evidence. Routing reports route ID, current/next step and operation, and a fixture route state. The evaluator reports `route_changed: false` in every response.

A q-time breach or active route hold is a containment blocker. An at-risk q-time, over-target TAT, or pending engineering route is a review flag. Missing `flow_context` produces `FLOW_CONTEXT_MISSING` and human `ENGINEERING_REVIEW`; the demo cannot verify an authoritative MES hold and therefore never recommends release from SPC/equipment evidence alone. These policies are illustrative and must be replaced by route-qualified site procedures in any real integration.

## Disposition precedence

The advisory gate evaluates evidence in this order:

1. **Contain:** data-quality failure, SPC special cause, out-of-spec value, tool alarm, critical linked alarm, q-time breach, or route hold → `HOLD_FOR_CONTAINMENT`.
2. **Human engineering review:** missing flow context, warning equipment, non-critical linked alarm, missing owner acknowledgement, q-time at risk, TAT over target, or pending route review → `ENGINEERING_REVIEW`.
3. **Sampling recommendation:** complete synthetic flow context and no displayed blocker/flag → `RELEASE_WITH_SAMPLING`.

The third label is still only a recommendation. Every response states `human_approval_status: not_recorded`, `human_release_authority_required: true`, and `material_state_changed: false`. Missing MES genealogy, authoritative hold state, FDC, gauge R&R, wafer-map/defect context, and downstream test are listed explicitly.

## Executed replay evidence

`GET /api/fab-ops/v1/evals/replays` executes:

- three fixture disposition cases (contain, engineering review, sampling recommendation); and
- six detector boundaries (WECO-1, WECO-2, WECO-3, WECO-4, centerline-zero negative case, and opposite-side negative case).

Each run contains expected, actual, and boolean `passed` values. The aggregate status is calculated from those assertions at request time. Editing the algorithm or fixture can therefore turn the endpoint red; it is not a static list of pass labels.

## Authentication and integrity wording

The exact `demo` runtime profile permits a credential-free synthetic walkthrough and uses an openly documented demo HMAC credential. Any other mode fails sensitive routes closed if operator/signing credentials are absent. Fab and scanner audit-feed routes authenticate before invoking optional S3, DynamoDB, or SQS writers.

HMAC-SHA256 authenticates canonical JSON under a shared secret and detects payload modification. The signed fab manifest includes an `spc_evidence_binding` section with fixture SHA-256, control-plan/disposition contracts and revision, recommendation, WECO rule IDs, q-time/TAT/routing status, and unchanged human/material authority fields. `POST /api/fab-ops/shift-handoff/verify` hashes the exact caller-presented manifest and checks every field in the exact, extra-forbidden export envelope; it never rebuilds a trusted local manifest from `signed_at`. Headline or lineage-binding tamper with unchanged proof therefore fails digest and HMAC checks. Outer digest-preview, generator/channel/purpose, human-approval/authority, verification method/route, or ordered-step tamper fails deterministic envelope checks, and unknown outer fields fail request validation. HMAC does **not** identify a human signer, record consent, satisfy electronic-signature governance, or approve material release.

## References

- NIST/SEMATECH, [Control Chart](https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc31.htm) and [Zone Tests](https://www.itl.nist.gov/div898/handbook/pmc/section3/pmc32.htm).
- Western Electric Company, *Statistical Quality Control Handbook* (rule family; the repository documents its exact boundary convention above).

These references ground the detector semantics, not the synthetic process values or site disposition policy.

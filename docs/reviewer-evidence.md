# Reviewer Evidence Guide

## Fast path (about two minutes)

1. Start the explicit local demo with `make run`.
2. Open the UI at `/` and confirm the top banner says **Synthetic fixture only**.
3. Open `/api/fab-ops/v1/control-plan`; verify `measured_fab_data` is `false` and human release authority is required.
4. Open `/api/fab-ops/v1/lots/lot-8812/disposition`; trace WECO evidence, q-time/TAT/routing, blockers, fixture hash, and the unchanged material state.
5. Open `/api/fab-ops/v1/evals/replays`; inspect assertion objects rather than only the aggregate score. An unavailable API is no pass evidence.
6. Export `/api/fab-ops/shift-handoff/signature`, then POST its `payload` unchanged to `/api/fab-ops/shift-handoff/verify`; inspect the signed SPC lineage binding.
7. Read [`fab-yield-methodology.md`](fab-yield-methodology.md), then run `make verify-strict`.

## Expected deterministic story

| Case | Expected actual evidence |
|---|---|
| `lot-8812` | `HOLD_FOR_CONTAINMENT`; WECO-1/2/3; synthetic q-time `breached`; route `hold`; no material change |
| `lot-8821` | `ENGINEERING_REVIEW`; no SPC signal; warning/high-alarm and route-review flags |
| `lot-8836` | `RELEASE_WITH_SAMPLING`; no displayed SPC/equipment blocker; human approval still `not_recorded` |
| WECO-4 positive case | Eight strictly positive standardized values trigger WECO-4 |
| Centerline regression | Eight zero standardized values trigger no rule |
| Replay aggregate | Nine executed scenarios, 54 passed assertions, zero failed assertions |

The scenario timestamp and fixture SHA are deterministic. Live wrapper timestamps and persisted route-hit counts are intentionally variable.

## Traceability map

| Claim | Implementation | Independent check |
|---|---|---|
| Fixture and UI ship in the package | `pyproject.toml` package-data + resource/static loading | `make package-check` installs the wheel, imports `app.main` from it, and smokes static/API routes |
| Rule boundaries are intentional | tolerant inclusive WECO-1/2/3 comparisons plus strict WECO-4 sides | decimal center/sigma, parametrized boundary, and negative regressions in `test_fab_ops_spc.py` |
| Replay is executed | `execute_replay_suite` builds actual results and compares expectations | tests assert actual values and intentionally patched failure behavior |
| Incomplete data fails closed | SPC integrity checks + disposition precedence | incomplete-plan test expects containment blocker |
| Flow indicators are deterministic and fail closed | `evaluate_flow_indicators` + disposition precedence | coherent just-over-limit elapsed/remaining/overrun and missing-context review tests |
| Production mode closes missing credentials | shared operator/signature configuration + `/ready` | API tests set non-demo mode and expect HTTP 503; cloud writers are not called before audit auth |
| HMAC binds caller-presented SPC lineage but is not human approval | signed `spc_evidence_binding` + exact-envelope POST verifier | manifest/fixture-hash and every exported outer-field tamper regression fail while authority remains `not_recorded`; extras are rejected |
| Persistence readiness is write-aware | SQLite query or both JSONL domain stores opened for append | unusable fab/scanner path and unsupported-backend tests expect 503/fail-closed behavior |
| SQLite Kubernetes ledger is durable but single-writer | one `Recreate` replica + `ReadWriteOnce` PVC; no HPA | deployment validator/test reject `emptyDir`, multiple replicas, or HPA reintroduction |
| No measured-yield claim | renamed legacy score, common evidence boundary, synthetic trend compatibility route | API and static UI assertions |

## Commands

```bash
make lint          # Ruff over app and tests
make typecheck     # mypy over app
make coverage      # full pytest suite with branch coverage report
make package-check # install wheel; smoke packaged fixture, static UI, import, and APIs
make smoke         # live uvicorn + canonical control/disposition/replay routes
make validate      # architecture and repository-surface validators
make verify-strict # complete local gate
```

A focused runtime exercise also asserts response content:

```bash
SEMICONDUCTOR_OPS_MODE=demo PERSISTENCE_BACKEND=jsonl .venv/bin/python scripts/exercise_runtime.py
```

## Failure evidence worth sampling

- Change a POST classification to `production`: FastAPI returns 422.
- Omit a planned observation: the request remains structurally valid but disposition contains `MEASUREMENT_DATA_INCOMPLETE` and containment advice.
- Request an unknown fixture lot: HTTP 404.
- Call a sensitive route with `SEMICONDUCTOR_OPS_MODE=production` and no token: HTTP 503 (configuration fail closed).
- Call the deprecated query verifier: HTTP 405 with direction to POST the exact exported envelope; no proof fields are reconstructed.
- POST a caller manifest with a modified headline or SPC fixture hash while retaining the envelope: HTTP 200 with `overall_valid: false`; no approval or state change follows.
- Omit `flow_context` from an otherwise clean synthetic POST: the result is human `ENGINEERING_REVIEW`, never release advice.
- Run production readiness without both domains’ token/signing Secret values: `/ready` returns HTTP 503.

## Review boundary

This evidence demonstrates software design, statistical-rule implementation, contract validation, testability, lineage, and safety wording. It does not demonstrate production process capability, actual yield improvement, approved OCAP content, MES/FDC integration, or fab release qualification.

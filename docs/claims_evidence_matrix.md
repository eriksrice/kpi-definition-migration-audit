# Claims-to-Evidence Matrix

These bounded assets are approved for release-candidate review. They do not support stronger production, enterprise, scale, autonomy, causal-inference, or universal-impact claims.

## Approved headline

> Built a deterministic KPI-definition migration trial that identifies semantic breaks, determines restatement feasibility from declared source-coverage evidence, and quantifies threshold, ranking, and trend consequences before cutover.

## Auditable claim boundaries

| Permitted claim | Machine artifact | Exact evidence | Supporting test | Prohibited overclaim |
|---|---|---|---|---|
| Deterministic KPI-definition migration trial | `bundle_manifest.json`; `definition_diff.json` | Canonical bundle ID; `semantic_relation=NON_EQUIVALENT` | C12; D01; D10 | Enterprise metric-governance platform |
| Determines restatement feasibility from declared source evidence | `cohort_reconstructability.json`; `horizon_coverage.json` | April v2 `NOT_RECONSTRUCTABLE`; May/June v2 `FULLY_RECONSTRUCTABLE`; horizon `PARTIAL` | C07; C17; D01 | Automatically discovers all missing history |
| Quantifies demonstrated decision consequences | `calculations.json`; `decision_changes.json`; `comparisons.json` | May Alpha result IDs; threshold/rank change IDs; both trend comparison IDs | C08–C09; H01–H03; D03–D05 | Proves universal business impact |
| Produces a recommendation pending human approval | `migration_plan.json` | `PARTIAL_RESTATEMENT`; four actions; approval `PENDING` | C11; C20; H04–H05; EC08–EC11; D06 | Autonomously approves migrations |
| Refuses definition-only attribution under a context change | `controls.json`; `context_differences.json` | G3 attribution `false`; `INSUFFICIENT_EVIDENCE`; `REJECT_PENDING_EVIDENCE` | C10; H06; EC13–EC15; D07 | General causal-inference system |
| Reproducible local evidence bundle | `bundle_manifest.json`; `artifacts/golden/*`; `schemas/*` | 15 artifacts; 26 schemas; byte-identical replay | C12; D01–D02; D10 | Production deployment or warehouse-scale system |

## Additional boundaries

- The synthetic 80% threshold demonstrates consequence propagation; it is not an empirically optimal threshold.
- `PARTIAL_RESTATEMENT` is a recommendation, not approval.
- The fixture proves the mechanism for one activation-rate migration, not prevalence or generality.
- Source coverage is declared evidence; missing warehouse history is not automatically discovered.

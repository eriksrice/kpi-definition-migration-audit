# KPI Definition Migration Audit

> Built a deterministic KPI-definition migration audit that identifies semantic breaks, determines restatement feasibility from declared source-coverage evidence, and quantifies threshold, ranking, and trend consequences before cutover.

## The problem

A KPI can keep the same name while a changed denominator alters its meaning, breaks historical comparability, and reverses decisions. This audit holds the records and decision contract fixed, changes one KPI definition, and determines what can be safely restated.

**Same records. Different KPI meaning. Different decisions.**

## The 60-second proof

1. v1 divides activated accounts by activity-qualified accounts; v2 divides them by all eligible matured signups.
2. May Alpha changes from `7/8` to `7/10`: `87.5% → 70.0%`.
3. The launch threshold flips `PASS → FAIL`, and rank flips `Alpha > Beta → Beta > Alpha`.
4. A cross-version stitch suggests `-7.5 pp`, but it is prohibited; like-for-like v2 restatement shows a valid `+10.0 pp`.
5. April cannot be restated because its all-signup population was not retained; May and June can be restated.
6. The result is a four-action partial-restatement recommendation, while a changed source context triggers `REJECT_PENDING_EVIDENCE`.

| Evidence | Before | After / finding |
|---|---:|---:|
| May Alpha KPI | `7/8` · `87.5%` | `7/10` · `70.0%` |
| Launch threshold | `PASS` | `FAIL` |
| Channel rank | `Alpha > Beta` | `Beta > Alpha` |
| Historical trend | stitched `-7.5 pp` | restated v2 `+10.0 pp` |
| April coverage | v1 available | v2 not reconstructable |

## Run the demonstration

Prepare the locked Python 3.12 environment once, then run:

```sh
./scripts/bootstrap_environment
./scripts/run_demo
```

`run_demo` creates a temporary golden evaluation, requires every generated artifact and schema to match the checked-in canonical evidence byte-for-byte, and only then prints the machine-derived story. It does not overwrite canonical evidence or access the network.

The one-screen companion is [the evidence card](artifacts/demo/evidence_card.md). The spoken walkthrough and recovery steps are in [the demo runbook](docs/demo_runbook.md).

## What the system produces

- explicit v1/v2 definition identities and a denominator-only semantic diff;
- record-level exact calculations with retained membership evidence;
- cohort and horizon restatement feasibility;
- scoped threshold, rank, and trend consequences;
- a four-action migration recommendation with human approval still `PENDING`; and
- a controlled-context refusal when source evidence changes too.

## Why this is not Goodhart or tool choice

**Goodhart:** Goodhart holds the metric fixed and changes behavior under pressure; this audit holds the records fixed, changes the metric's meaning, and determines what history and decisions must be restated.

**Tool choice:** Tool-choice evaluation tests whether a selected tool satisfies a declared task contract; this audit tests whether KPI definitions denote comparable quantities and what history must be restated.

## Architecture and reliability

The proof is a narrow local Python evaluator over strict JSON fixtures. Typed models reject invalid metric results, memberships, coverage states, comparisons, decisions, and plans. Exact rational arithmetic avoids threshold and trend rounding ambiguity. A pre-serialization consistency barrier independently rebuilds comparisons, decision changes, impact, operand outcomes, and migration plans before canonical JSON is emitted.

Reliability evidence includes:

- 15 deterministic canonical artifacts and 26 JSON Schemas;
- explicit record, definition, provenance, analysis, comparison, decision, policy, and action references;
- same-input replay and complete artifact manifests;
- positive and adversarial G1–G4 controls; and
- fail-closed demo integrity checks against the canonical bytes.

Start technical inspection with `artifacts/golden/report.md`, then use `artifacts/golden/bundle_manifest.json`, [architecture.md](docs/architecture.md), and [evaluation.md](docs/evaluation.md).

## Reproducibility

```sh
./scripts/test_golden
```

The environment is locked by `uv.lock`. Setup, replay, and version details are documented in [reproducibility.md](docs/reproducibility.md).

## Limitations and claim boundaries

- This is one synthetic activation-rate definition migration, not a general metric platform.
- Source coverage is declared input evidence; missing history is not automatically discovered.
- The frozen threshold is a synthetic consequence contract, not an empirical optimum.
- The migration plan is a recommendation and cannot self-approve.
- There is no dashboard, database, warehouse integration, deployment layer, LLM, or agent.
- No production, enterprise, performance, scalability, causal-inference, or universal-impact claim is supported.

See [limitations.md](docs/limitations.md) and the [claims-to-evidence matrix](docs/claims_evidence_matrix.md).

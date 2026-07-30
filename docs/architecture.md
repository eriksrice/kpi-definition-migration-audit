# Architecture

## Purpose

This repository evaluates one bounded question: when a KPI definition changes while source records and the decision contract remain fixed, which historical values remain comparable, which periods can be restated, and which decisions change?

## Evidence flow

1. Strict JSON fixtures declare versioned metric definitions, synthetic account records, source provenance, source coverage, the decision contract, and the migration policy.
2. Typed models validate identifiers, predicates, coverage states, memberships, exact results, comparisons, decisions, controls, and migration actions.
3. The calculator evaluates both definition versions with exact rational arithmetic and retains record-level denominator and numerator membership.
4. The evaluator compares controlled arms, calculates decision consequences, determines restatement coverage, and derives the migration plan.
5. The consistency barrier independently recomputes endpoint projections, deltas, decision changes, impact, policy operands, rule traces, and plans before serialization.
6. Canonical serialization writes stable JSON artifacts, JSON Schemas, a report, and a hash manifest.
7. The demo generates a fresh temporary bundle, requires byte equality with the checked-in canonical evidence, and projects the story from the generated JSON.

## Module boundaries

| Module | Responsibility |
|---|---|
| `models.py` | Strict metric, evidence, comparison, decision, and policy types |
| `canonical.py` | Canonical predicates, identities, context fingerprints, and arm comparison |
| `calculation.py` | Exact record-level KPI evaluation |
| `evaluation.py` | Comparisons, decision changes, controls, and migration-plan derivation |
| `consistency.py` | Independent pre-serialization evidence recomputation |
| `runner.py` | Frozen scenario orchestration and canonical output writing |
| `reporting.py` | Machine-evidence report projection |
| `demo.py` | Narrow public demonstration projection and fail-closed byte comparison |

## Deliberate constraints

The project has no database, SQL layer, dashboard, web application, LLM, agent, deployment system, or general rule engine. The accepted result is a recommendation with human approval remaining `PENDING`.

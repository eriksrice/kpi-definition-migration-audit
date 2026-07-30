# Evaluation

## Frozen scenario

The synthetic trial changes only the denominator of `qualified_activation_rate`:

- v1: activated accounts divided by eligible activity-qualified accounts;
- v2: activated accounts divided by all eligible matured signups.

Records, cutoff, timezone, grouping, maturity rule, threshold, ranking rule, and trend contract remain fixed. The key May Alpha result changes from `7/8` to `7/10` because the numerator remains seven while the denominator expands from eight to ten.

## Accepted consequences

| Evidence | Result |
|---|---|
| Threshold | `PASS → FAIL` for May Alpha |
| Rank | `Alpha > Beta → Beta > Alpha` for May |
| Cross-version stitch | `-3/40`, or `-7.5 pp`; invalid and prohibited |
| Like-for-like v2 restatement | `1/10`, or `+10.0 pp`; valid |
| April v2 | Not reconstructable because the authoritative signup population was not retained |
| May–June v2 | Fully reconstructable |
| Migration recommendation | Four-action `PARTIAL_RESTATEMENT`, human approval `PENDING` |

## Controls

- **G1:** record-level calculations match the frozen aggregate oracle; unavailable April v2 emits no number.
- **G2:** a presentation-only definition revision changes artifact identity but preserves semantic projections.
- **G3:** a source-context change blocks definition-only attribution and emits `REJECT_PENDING_EVIDENCE`.
- **G4:** equal observed output does not imply semantic equivalence.

## Test layers

The 105-test suite covers contracts and identity, calculation and source coverage, context and decisions, deterministic artifacts, adversarial evidence-consistency tests, and deterministic demo-integrity tests. The D01–D11 tests specifically prove fresh byte equality, fail-closed mismatch behavior, exact value/trend/decision/action/control projection, evidence-card parity, command replay, and absence of frozen calculated outcomes in the renderer.

The canonical proof comprises 15 evidence artifacts and 26 deterministic JSON Schemas.

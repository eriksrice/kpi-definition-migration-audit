# KPI Definition Migration Audit - Evidence Card

**Same records. Different KPI meaning. Different decisions.**

## Definition change

- **v1:** activated accounts divided by activity-qualified accounts
- **v2:** activated accounts divided by all eligible matured signups

## Decision impact

| Scope | Before | After |
|---|---:|---:|
| 2026-05 Alpha | 7/8 · 87.5% | 7/10 · 70.0% |
| Threshold | PASS | FAIL |
| Channel rank | Alpha > Beta | Beta > Alpha |

## Historical interpretation

- **Prohibited stitch:** -7.5 pp - valid `false`; `NOT_COMPARABLE_WITHOUT_BRIDGE`
- **Valid v2 restatement:** +10.0 pp - valid `true`; `COMPARABLE_AFTER_RESTATEMENT`

## Coverage

- 2026-04: not reconstructable under v2
- 2026-05 through 2026-06: fully reconstructable

## Migration plan

`PARTIAL_RESTATEMENT` - human approval `PENDING`

1. Restate 2026-05 through 2026-06.
2. Dual-report 2026-05 through 2026-06.
3. Begin the official v2 series in 2026-06.
4. Mark 2026-04 and cross-version stitches non-comparable.

## Confound safeguard

Source-context change detected `true`; attribution refused `true`; comparison valid `false`. Result: `INSUFFICIENT_EVIDENCE` -> `REJECT_PENDING_EVIDENCE`.

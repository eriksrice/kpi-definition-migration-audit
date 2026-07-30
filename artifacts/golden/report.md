# Golden KPI Definition Migration Evidence

## 1. Denominator definition change

The registered intervention changes only `denominator_population`: v1 uses eligible activity-qualified accounts; v2 uses all eligible matured signups. The structured diff contains 1 independent semantic change.

- v1 artifact: `sha256:9b76f744c63a626974716ba0ced66b07b31d9ae3ef0598a57cea7eaa5f042728`
- v1 semantic: `sha256:0341262b43a4b1bfc268a671e463db827ddec9b40ffee96102fe52130b8bf1b2`
- v2 artifact: `sha256:299a521de6b46d3853d5039f9589dc6a4be64495d6f76a891a6fab37417afd69`
- v2 semantic: `sha256:bcb2ce4b5fd1804d7c2c2a2427167ae0e68fbd3dcc04b3edefea979512e01321`

## 2. Matched non-metric context

`controlled_context_match=true`. Metric identities are retained separately; the non-metric difference set is empty.

## 3. April all-signup population is unavailable

April retains the complete activity-qualified fact required by v1, but not an authoritative all-signup roster. Therefore v1 is exact and v2 has no number.

| Cohort | v2 definition | Reconstructability | Evidence result |
| --- | --- | --- | --- |
| 2026-04 | 2.0.0 | NOT_RECONSTRUCTABLE | UNAVAILABLE_NOT_RETAINED:population.authoritative_signup_roster |
| 2026-05 | 2.0.0 | FULLY_RECONSTRUCTABLE | all dependencies complete |
| 2026-06 | 2.0.0 | FULLY_RECONSTRUCTABLE | all dependencies complete |

## 4. Partial horizon coverage

The closed `2026-04..2026-06` horizon is `PARTIAL`: full for 2026-05, 2026-06; not reconstructable for 2026-04.

## 5. Exact calculations and scoped trends

| Cohort | Channel | Version | Numerator | Denominator | Exact result |
| --- | --- | --- | ---: | ---: | --- |
| 2026-04 | Alpha | 1.0.0 | 6 | 7 | `6/7` |
| 2026-04 | Beta | 1.0.0 | 7 | 9 | `7/9` |
| 2026-05 | Alpha | 1.0.0 | 7 | 8 | `7/8` |
| 2026-05 | Alpha | 2.0.0 | 7 | 10 | `7/10` |
| 2026-05 | Beta | 1.0.0 | 8 | 10 | `4/5` |
| 2026-05 | Beta | 2.0.0 | 8 | 10 | `4/5` |
| 2026-06 | Alpha | 1.0.0 | 8 | 9 | `8/9` |
| 2026-06 | Alpha | 2.0.0 | 8 | 10 | `4/5` |
| 2026-06 | Beta | 1.0.0 | 8 | 10 | `4/5` |
| 2026-06 | Beta | 2.0.0 | 8 | 10 | `4/5` |

The prohibited stitch `CA-STITCH-ALPHA-2026-05-V1-TO-2026-06-V2` retains its apparent delta `-3/40` (`-0.075`), but is invalid with verdict `NOT_COMPARABLE_WITHOUT_BRIDGE`.

The restated comparison `CA-RESTATED-ALPHA-2026-05-V2-TO-2026-06-V2` has exact delta `1/10` (`+0.10`), is valid, and has verdict `COMPARABLE_AFTER_RESTATEMENT`.

## 6. Threshold and ranking reversals

- `DC-THRESHOLD-2026-05-ALPHA`: PASS → FAIL.
- `DC-RANKING-2026-05`: Alpha > Beta → Beta > Alpha.
- `DC-TREND-INTERPRETATION-ALPHA`: PROHIBITED_APPARENT_DECLINE_-3/40 → VALID_RESTATED_IMPROVEMENT_1/10.

## 7. Four-action migration plan

Recommendation: `PARTIAL_RESTATEMENT`; human approval: `PENDING`.

1. `RESTATE_COHORT_RANGE` — `2026-05..2026-06`; rule `MP-R01_RESTATE_FULL`.
2. `DUAL_REPORT_COHORT_RANGE` — `2026-05..2026-06`; rule `MP-R02_BRIDGE_MIN_TWO`.
3. `START_OFFICIAL_SERIES` — `2026-06..2026-06`; rule `MP-R03_START_EFFECTIVE`.
4. `MARK_NON_COMPARABLE` — `2026-04..2026-04`; rule `MP-R04_NO_SPLICE`.

## 8. G3 refusal

G3 discovers this actual non-metric fingerprint difference: `source_snapshot_hash` (sha256:10a2a65b97f72042addc93710ba0633dff71fc9cafaace317726acb264b65fe2 → sha256:0896f5d4642b57cc5bc6090dfc3edfcec36d7a8f40964b70451259474ba6b608). It emits `INSUFFICIENT_EVIDENCE` and only `REJECT_PENDING_EVIDENCE`. The definition diff remains retained.

This report is a deterministic projection of the checked-in machine evidence. It does not grant human approval or make a public claim.

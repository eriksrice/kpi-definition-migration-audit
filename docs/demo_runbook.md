# Demonstration Runbook

## Setup and execution

```sh
./scripts/bootstrap_environment
./scripts/run_demo
```

`run_demo` uses no network access. It generates evidence and schemas in a temporary directory, requires byte equality with the canonical trees, reads the generated machine evidence, prints the projection, and removes the temporary directory.

## Before speaking

Have a terminal with `./scripts/run_demo` ready and `artifacts/demo/evidence_card.md` visible beside it. Begin with the business problem, not source code, schemas, hashes, or policy traces.

## Speaking sequence

1. State that changed KPI meaning can reverse decisions even when records stay fixed.
2. Point to the denominator change and May Alpha result.
3. Walk through threshold and rank reversals.
4. Contrast the prohibited stitch with valid v2 restatement.
5. Explain April's coverage limit and the four-action plan.
6. Finish with the source-context refusal and one-sentence Goodhart distinction.

## Technical follow-ups

| Question | Evidence |
|---|---|
| Where do `7/8` and `7/10` come from? | `artifacts/golden/calculations.json` |
| Why is one trend prohibited? | `artifacts/golden/comparisons.json` |
| Where are the decision reversals? | `artifacts/golden/decision_changes.json` |
| Why can April not be restated? | `cohort_reconstructability.json` and `horizon_coverage.json` |
| Where is the four-action plan? | `artifacts/golden/migration_plan.json` |
| How is confounding refused? | `artifacts/golden/controls.json`, section `g3` |

## Recovery

If the environment is missing, run `./scripts/bootstrap_environment`. If `run_demo` reports a canonical mismatch, stop: run `git status --short` and `./scripts/test_golden`, inspect the reported path, and restore a clean verified checkout. Never bypass the comparison or narrate values from memory after failure.

## Timing

The spoken body is 173 whitespace-delimited words. At ordinary speaking rates of approximately 140–170 words per minute, estimated duration is about 61–74 seconds, within the 60–90 second target.

Final live rehearsal remains an owner task:

- Owner practice 1: `_____ seconds`
- Owner practice 2: `_____ seconds`
- Owner practice 3: `_____ seconds`

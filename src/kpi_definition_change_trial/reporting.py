from __future__ import annotations

from decimal import Decimal, localcontext
from typing import Any


def _ratio(value: dict[str, int]) -> str:
    return f"{value['numerator']}/{value['denominator']}"


def _decimal(value: dict[str, int], places: int) -> str:
    with localcontext() as context:
        context.prec = 24
        number = Decimal(value["numerator"]) / Decimal(value["denominator"])
        return f"{number:.{places}f}"


def render_report(evidence: dict[str, Any]) -> str:
    identities = evidence["identities"]
    arm_analysis = evidence["context_differences"]["golden"]
    reconstructability = evidence["cohort_reconstructability"]
    horizon = evidence["horizon_coverage"]
    calculations = evidence["calculations"]["golden"]
    comparisons = evidence["comparisons"]
    changes = evidence["decision_changes"]["changes"]
    plan = evidence["migration_plan"]
    g3 = evidence["controls"]["g3"]

    exact_results = [item for item in calculations if item["status"] == "EXACT"]
    result_lines = [
        f"| {item['cohort']} | {item['channel']} | {item['definition_ref'].rsplit('/', 1)[1]} "
        f"| {item['numerator_count']} | {item['denominator_count']} | "
        f"`{_ratio(item['exact_value'])}` |"
        for item in exact_results
    ]
    reconstruction_lines = [
        f"| {item['cohort']} | {item['definition_ref'].rsplit('/', 1)[1]} | {item['status']} | "
        f"{', '.join(item['reason_codes']) or 'all dependencies complete'} |"
        for item in reconstructability
        if item["definition_ref"].endswith("/2.0.0")
    ]
    action_lines = [
        f"{item['sequence']}. `{item['action_type']}` — "
        f"`{item['scope_start']}..{item['scope_end']}`; "
        f"rule `{item['policy_rule_ids'][0]}`."
        for item in plan["actions"]
    ]
    g3_differences = ", ".join(
        f"`{item['field']}` ({item['left']} → {item['right']})"
        for item in g3["arm_difference"]["non_metric_context_differences"]
    )

    lines = [
        "# Golden KPI Definition Migration Evidence",
        "",
        "## 1. Denominator definition change",
        "",
        "The registered intervention changes only `denominator_population`: v1 uses eligible "
        "activity-qualified accounts; v2 uses all eligible matured signups. The structured diff "
        f"contains {len(evidence['definition_diff']['independent_semantic_changes'])} independent "
        "semantic change.",
        "",
        f"- v1 artifact: `{identities['v1']['artifact_hash']}`",
        f"- v1 semantic: `{identities['v1']['semantic_hash']}`",
        f"- v2 artifact: `{identities['v2']['artifact_hash']}`",
        f"- v2 semantic: `{identities['v2']['semantic_hash']}`",
        "",
        "## 2. Matched non-metric context",
        "",
        f"`controlled_context_match={str(arm_analysis['controlled_context_match']).lower()}`. "
        "Metric identities are retained separately; the non-metric difference set is empty.",
        "",
        "## 3. April all-signup population is unavailable",
        "",
        "April retains the complete activity-qualified fact required by v1, but not an "
        "authoritative all-signup roster. Therefore v1 is exact and v2 has no number.",
        "",
        "| Cohort | v2 definition | Reconstructability | Evidence result |",
        "| --- | --- | --- | --- |",
        *reconstruction_lines,
        "",
        "## 4. Partial horizon coverage",
        "",
        f"The closed `{horizon['first_cohort']}..{horizon['last_cohort']}` horizon is "
        f"`{horizon['status']}`: full for {', '.join(horizon['fully_reconstructable_cohorts'])}; "
        f"not reconstructable for {', '.join(horizon['non_reconstructable_cohorts'])}.",
        "",
        "## 5. Exact calculations and scoped trends",
        "",
        "| Cohort | Channel | Version | Numerator | Denominator | Exact result |",
        "| --- | --- | --- | ---: | ---: | --- |",
        *result_lines,
        "",
        f"The prohibited stitch `{comparisons[0]['assessment_id']}` retains its apparent delta "
        f"`{_ratio(comparisons[0]['exact_delta'])}` "
        f"(`{_decimal(comparisons[0]['exact_delta'], 3)}`), but is invalid with verdict "
        f"`{comparisons[0]['verdict']}`.",
        "",
        f"The restated comparison `{comparisons[1]['assessment_id']}` has exact delta "
        f"`{_ratio(comparisons[1]['exact_delta'])}` "
        f"(`+{_decimal(comparisons[1]['exact_delta'], 2)}`), is valid, and has verdict "
        f"`{comparisons[1]['verdict']}`.",
        "",
        "## 6. Threshold and ranking reversals",
        "",
        *[
            f"- `{item['change_id']}`: {item['before_state']} → {item['after_state']}."
            for item in changes
        ],
        "",
        "## 7. Four-action migration plan",
        "",
        f"Recommendation: `{plan['recommendation']}`; human approval: "
        f"`{plan['human_approval_state']}`.",
        "",
        *action_lines,
        "",
        "## 8. G3 refusal",
        "",
        f"G3 discovers this actual non-metric fingerprint difference: {g3_differences}. "
        f"It emits `{g3['comparison']['verdict']}` and only "
        f"`{g3['plan']['actions'][0]['action_type']}`. The definition diff remains retained.",
        "",
        "This report is a deterministic projection of the checked-in machine evidence. It does "
        "not grant human approval or make a public claim.",
        "",
    ]
    return "\n".join(lines)


def semantic_result_projection(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "cohort": item["cohort"],
            "channel": item["channel"],
            "status": item["status"],
            "numerator_count": item["numerator_count"],
            "denominator_count": item["denominator_count"],
            "exact_value": item["exact_value"],
            "membership": item["membership"],
        }
        for item in results
    ]

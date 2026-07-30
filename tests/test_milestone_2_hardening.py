from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import pytest
from conftest import load_json
from pydantic import ValidationError

from kpi_definition_change_trial.canonical import (
    analyze_arm_difference,
    build_arm,
    definition_diff,
)
from kpi_definition_change_trial.evaluation import (
    build_decision_changes,
    build_g3_comparison,
    build_migration_plan,
)
from kpi_definition_change_trial.models import (
    ArmDifferenceAnalysis,
    AssumptionRecord,
    CohortReconstructability,
    ComparisonAssessment,
    ControlResult,
    CoverageDeclaration,
    CoverageStatus,
    DecisionChange,
    DecisionContract,
    ExactValue,
    HorizonRestatementCoverage,
    ImpactIndex,
    MembershipTrace,
    MetricResult,
    MigrationPlan,
    MigrationPolicy,
    ReconstructabilityStatus,
    SourceProvenance,
    TrialArm,
)
from kpi_definition_change_trial.runner import validate_reference_graph


def _typed_policy_inputs(evidence):
    provenance = evidence["provenance_assumptions"]
    return {
        "policy": MigrationPolicy.model_validate(provenance["migration_policy"]),
        "horizon": HorizonRestatementCoverage.model_validate(evidence["horizon_coverage"]),
        "reconstructability": tuple(
            CohortReconstructability.model_validate(item)
            for item in evidence["cohort_reconstructability"]
        ),
        "comparisons": tuple(
            ComparisonAssessment.model_validate(item) for item in evidence["comparisons"]
        ),
        "decision_changes": tuple(
            DecisionChange.model_validate(item) for item in evidence["decision_changes"]["changes"]
        ),
        "arm_analysis": ArmDifferenceAnalysis.model_validate(
            evidence["context_differences"]["golden"]
        ),
        "contract": DecisionContract.model_validate(provenance["decision_contract"]),
        "required_controls": tuple(
            ControlResult.model_validate(item) for item in evidence["controls"]["results"]
        ),
    }


def _only_rejection(plan: MigrationPlan) -> bool:
    return [item.action_type for item in plan.actions] == ["REJECT_PENDING_EVIDENCE"]


@pytest.mark.parametrize(
    ("comparison_index", "delta"),
    [(0, Fraction(-1, 5)), (1, Fraction(3, 20))],
)
def test_h01_trend_state_follows_mutated_comparison_delta(evidence, comparison_index, delta):
    results = tuple(
        MetricResult.model_validate(item) for item in evidence["calculations"]["golden"]
    )
    comparisons = tuple(
        ComparisonAssessment.model_validate(item) for item in evidence["comparisons"]
    )
    baseline, _ = build_decision_changes(
        results,
        comparisons,
        DecisionContract.model_validate(evidence["provenance_assumptions"]["decision_contract"]),
    )
    mutated = list(comparisons)
    mutated[comparison_index] = mutated[comparison_index].model_copy(
        update={"exact_delta": ExactValue(numerator=delta.numerator, denominator=delta.denominator)}
    )
    changed, _ = build_decision_changes(
        results,
        tuple(mutated),
        DecisionContract.model_validate(evidence["provenance_assumptions"]["decision_contract"]),
    )
    baseline_state = baseline[2].before_state if comparison_index == 0 else baseline[2].after_state
    changed_state = changed[2].before_state if comparison_index == 0 else changed[2].after_state
    assert changed_state != baseline_state
    assert changed_state.endswith(str(delta))


def test_h02_authoritative_trend_logic_has_no_literal_golden_answers():
    source = (
        Path(__file__).resolve().parents[1] / "src/kpi_definition_change_trial/evaluation.py"
    ).read_text(encoding="utf-8")
    assert "PROHIBITED_APPARENT_DECLINE_-3/40" not in source
    assert "VALID_RESTATED_IMPROVEMENT_1/10" not in source


def test_h03_equal_threshold_and_ranking_states_are_unchanged(evidence):
    results = tuple(
        MetricResult.model_validate(item) for item in evidence["calculations"]["golden"]
    )
    by_id = {item.result_id: item for item in results}
    replacements = {
        "RESULT-2026-05-ALPHA-V2_0_0": by_id["RESULT-2026-05-ALPHA-V1_0_0"].model_copy(
            update={
                "result_id": "RESULT-2026-05-ALPHA-V2_0_0",
                "definition_ref": "qualified_activation_rate/2.0.0",
            }
        ),
        "RESULT-2026-05-BETA-V2_0_0": by_id["RESULT-2026-05-BETA-V1_0_0"].model_copy(
            update={
                "result_id": "RESULT-2026-05-BETA-V2_0_0",
                "definition_ref": "qualified_activation_rate/2.0.0",
            }
        ),
    }
    mutated_results = tuple(replacements.get(item.result_id, item) for item in results)
    changes, _ = build_decision_changes(
        mutated_results,
        tuple(ComparisonAssessment.model_validate(item) for item in evidence["comparisons"]),
        DecisionContract.model_validate(evidence["provenance_assumptions"]["decision_contract"]),
    )
    assert [(item.before_state, item.after_state, item.classification) for item in changes[:2]] == [
        ("PASS", "PASS", "UNCHANGED"),
        ("Alpha > Beta", "Alpha > Beta", "UNCHANGED"),
    ]


@pytest.mark.parametrize(
    "mutation",
    ["missing_bridge", "nonreconstructable_restatement", "unresolved_comparison", "failed_control"],
)
def test_h04_policy_evidence_mutations_permit_only_rejection(evidence, mutation):
    inputs = _typed_policy_inputs(evidence)
    if mutation == "missing_bridge":
        inputs["reconstructability"] = tuple(
            item
            for item in inputs["reconstructability"]
            if not (item.definition_ref.endswith("/2.0.0") and item.cohort == "2026-06")
        )
    elif mutation == "nonreconstructable_restatement":
        inputs["reconstructability"] = tuple(
            item.model_copy(
                update={
                    "status": ReconstructabilityStatus.NOT_RECONSTRUCTABLE,
                    "reason_codes": ("HARDENING_MUTATION",),
                }
            )
            if item.definition_ref.endswith("/2.0.0") and item.cohort == "2026-05"
            else item
            for item in inputs["reconstructability"]
        )
    elif mutation == "unresolved_comparison":
        inputs["comparisons"] = tuple(
            item.model_copy(update={"assessment_id": f"MUTATED-{item.assessment_id}"})
            if item.kind == "TREND_STITCH"
            else item
            for item in inputs["comparisons"]
        )
    else:
        inputs["required_controls"] = tuple(
            item.model_copy(update={"status": "FAIL"}) if item.control_id == "G2" else item
            for item in inputs["required_controls"]
        )
    plan = build_migration_plan(**inputs)
    assert plan.recommendation == "REJECT_PENDING_EVIDENCE"
    assert _only_rejection(plan)


def test_h05_positive_rule_trace_records_actual_operands(evidence):
    plan = MigrationPlan.model_validate(evidence["migration_plan"])
    assert all(trace.evaluated_operands for trace in plan.rule_trace)
    assert all(operand.passed for trace in plan.rule_trace for operand in trace.evaluated_operands)
    assert all(
        trace.condition
        == " AND ".join(
            f"{operand.name}[{operand.operator}]" for operand in trace.evaluated_operands
        )
        for trace in plan.rule_trace
    )
    assert all("action_preconditions" not in trace.condition for trace in plan.rule_trace)


def test_h06_referenced_linkage_mutation_blocks_definition_attribution(
    evidence, definitions, records, coverage, decision_contract
):
    provenance = tuple(
        SourceProvenance.model_validate(item) for item in load_json("sources/provenance.json")
    )
    target = "SRC-MAY-SIGNUP-ROSTER"
    assert any(record.provenance_id == target for record in records)
    mutated_provenance = tuple(
        item.model_copy(update={"linkage_version": "account-linkage/1.0.1-hardening"})
        if item.provenance_id == target
        else item
        for item in provenance
    )

    def arm(arm_id, definition, source_provenance):
        dumped_provenance = [item.model_dump(mode="json") for item in source_provenance]
        return build_arm(
            arm_id=arm_id,
            definition=definition,
            source_snapshot={
                "records": [item.model_dump(mode="json") for item in records],
                "provenance": dumped_provenance,
            },
            source_schema_linkage_completeness={
                "schema_linkage_completeness": [
                    {
                        "schema_version": item.schema_version,
                        "linkage_version": item.linkage_version,
                        "completeness_declaration_id": item.completeness_declaration_id,
                    }
                    for item in source_provenance
                ],
                "coverage": [item.model_dump(mode="json") for item in coverage],
            },
            cutoff=decision_contract.cutoff,
            timezone=decision_contract.timezone,
            grouping={"grain": "signup_month_channel", "channels": ["Alpha", "Beta"]},
            decision_contract=decision_contract,
        )

    left = arm("H06-LEFT", definitions["v1"], provenance)
    right = arm("H06-RIGHT", definitions["v2"], mutated_provenance)
    diff = definition_diff(definitions["v1"], definitions["v2"])
    analysis = analyze_arm_difference(left, right, diff, analysis_id="H06-REFERENCED-LINKAGE")
    assert (
        left.controlled_context.source_snapshot_hash
        != right.controlled_context.source_snapshot_hash
    )
    assert (
        left.controlled_context.source_schema_linkage_completeness_hash
        != right.controlled_context.source_schema_linkage_completeness_hash
    )
    assert analysis.controlled_context_match is False
    assert analysis.attribution_valid is False
    assert analysis.reason_codes == ("CONTROLLED_CONTEXT_MISMATCH",)
    assert diff == definition_diff(definitions["v1"], definitions["v2"])

    inputs = _typed_policy_inputs(evidence)
    results = tuple(
        MetricResult.model_validate(item) for item in evidence["calculations"]["golden"]
    )
    comparison = build_g3_comparison(results, analysis)
    inputs.update(arm_analysis=analysis, comparisons=(comparison,))
    plan = build_migration_plan(**inputs)
    assert comparison.verdict == "INSUFFICIENT_EVIDENCE"
    assert _only_rejection(plan)


@pytest.mark.parametrize("count_field", ["numerator_count", "denominator_count"])
def test_h07_result_count_must_match_membership(evidence, count_field):
    result = next(
        item for item in evidence["calculations"]["golden"] if item["status"] == "EXACT"
    ).copy()
    result[count_field] += 1
    with pytest.raises(ValidationError, match="count must equal"):
        MetricResult.model_validate(result)


def test_h08_exact_value_must_match_reduced_counts(evidence):
    result = next(
        item for item in evidence["calculations"]["golden"] if item["status"] == "EXACT"
    ).copy()
    result["exact_value"] = {"numerator": 1, "denominator": 2}
    with pytest.raises(ValidationError, match="reduced count ratio"):
        MetricResult.model_validate(result)


@pytest.mark.parametrize("field", ["denominator_record_ids", "numerator_record_ids"])
def test_h09_membership_ids_must_be_unique(field):
    values = {
        "denominator_record_ids": ("A", "B"),
        "numerator_record_ids": ("A",),
        "excluded_records": (),
    }
    values[field] = ("A", "A")
    with pytest.raises(ValidationError, match="membership IDs must be unique"):
        MembershipTrace.model_validate(values)


def test_h10_coverage_categories_must_be_disjoint():
    with pytest.raises(ValidationError, match="mutually disjoint"):
        CoverageDeclaration(
            cohort="2026-05",
            complete=("field.account_id",),
            partial=("field.account_id",),
        )


def test_h11_required_dependency_statuses_cannot_conflict(evidence):
    reconstruction = evidence["cohort_reconstructability"][0].copy()
    duplicate = reconstruction["dependency_statuses"][0].copy()
    duplicate["status"] = CoverageStatus.UNKNOWN
    reconstruction["dependency_statuses"] = [
        *reconstruction["dependency_statuses"],
        duplicate,
    ]
    with pytest.raises(ValidationError, match="contradictory statuses"):
        CohortReconstructability.model_validate(reconstruction)


@pytest.mark.parametrize("collection", ["actions", "rule_trace"])
def test_h12_policy_sequences_must_be_unique_and_contiguous(evidence, collection):
    plan = evidence["migration_plan"].copy()
    plan[collection] = [item.copy() for item in plan[collection]]
    plan[collection][1]["sequence"] = 1
    with pytest.raises(ValidationError, match="unique and contiguous"):
        MigrationPlan.model_validate(plan)


def _reference_args(evidence, definitions, records, coverage):
    provenance_section = evidence["provenance_assumptions"]
    source_provenance = tuple(
        SourceProvenance.model_validate(item) for item in provenance_section["source_provenance"]
    )
    g3_provenance = SourceProvenance.model_validate(provenance_section["g3_source_provenance"])
    arms = {
        item["arm_id"]: TrialArm.model_validate(item)
        for group in evidence["trial_arms"].values()
        for item in group
    }
    analyses = tuple(
        ArmDifferenceAnalysis.model_validate(item)
        for item in evidence["context_differences"].values()
    )
    comparisons = (
        *(ComparisonAssessment.model_validate(item) for item in evidence["comparisons"]),
        ComparisonAssessment.model_validate(evidence["controls"]["g3"]["comparison"]),
    )
    return {
        "definitions": tuple(definitions.values()),
        "records": records,
        "provenance": (*source_provenance, g3_provenance),
        "coverage": coverage,
        "contract": DecisionContract.model_validate(provenance_section["decision_contract"]),
        "policy": MigrationPolicy.model_validate(provenance_section["migration_policy"]),
        "assumptions": tuple(
            AssumptionRecord.model_validate(item) for item in provenance_section["assumptions"]
        ),
        "arms": tuple(arms.values()),
        "analyses": analyses,
        "reconstructability": tuple(
            CohortReconstructability.model_validate(item)
            for item in evidence["cohort_reconstructability"]
        ),
        "horizon": HorizonRestatementCoverage.model_validate(evidence["horizon_coverage"]),
        "results": tuple(
            MetricResult.model_validate(item)
            for group in evidence["calculations"].values()
            for item in group
        ),
        "comparisons": comparisons,
        "decision_changes": tuple(
            DecisionChange.model_validate(item) for item in evidence["decision_changes"]["changes"]
        ),
        "impact": ImpactIndex.model_validate(evidence["decision_changes"]["impact_index"]),
        "plans": (
            MigrationPlan.model_validate(evidence["migration_plan"]),
            MigrationPlan.model_validate(evidence["controls"]["g3"]["plan"]),
        ),
        "controls": tuple(
            ControlResult.model_validate(item) for item in evidence["controls"]["results"]
        ),
    }


@pytest.mark.parametrize("reference_kind", ["result", "scope"])
def test_h13_reference_graph_rejects_dangling_references(
    evidence, definitions, records, coverage, reference_kind
):
    arguments = _reference_args(evidence, definitions, records, coverage)
    if reference_kind == "result":
        first = arguments["comparisons"][0]
        mutated_left = first.left.model_copy(update={"result_id": "MISSING-RESULT"})
        arguments["comparisons"] = (
            first.model_copy(update={"left": mutated_left}),
            *arguments["comparisons"][1:],
        )
    else:
        first_plan = arguments["plans"][0]
        first_action = first_plan.actions[0].model_copy(update={"scope_refs": ("MISSING-SCOPE",)})
        arguments["plans"] = (
            first_plan.model_copy(update={"actions": (first_action, *first_plan.actions[1:])}),
            arguments["plans"][1],
        )
    with pytest.raises(ValueError, match=f"unresolved .* {reference_kind}"):
        validate_reference_graph(**arguments)

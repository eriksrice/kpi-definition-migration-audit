from __future__ import annotations

import pytest

from kpi_definition_change_trial.models import (
    ArmDifferenceAnalysis,
    AssumptionRecord,
    CohortReconstructability,
    ComparisonAssessment,
    ComparisonEndpoint,
    ControlResult,
    DecisionChange,
    DecisionContract,
    ExactValue,
    HorizonRestatementCoverage,
    ImpactIndex,
    MetricResult,
    MigrationPlan,
    MigrationPolicy,
    SourceProvenance,
    TrialArm,
)
from kpi_definition_change_trial.runner import validate_evidence_consistency


def _typed_arguments(evidence, definitions, records, coverage):
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
        "analyses": tuple(
            ArmDifferenceAnalysis.model_validate(item)
            for item in evidence["context_differences"].values()
        ),
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
        "comparisons": (
            *(ComparisonAssessment.model_validate(item) for item in evidence["comparisons"]),
            ComparisonAssessment.model_validate(evidence["controls"]["g3"]["comparison"]),
        ),
        "decision_changes": tuple(
            DecisionChange.model_validate(item) for item in evidence["decision_changes"]["changes"]
        ),
        "impact": ImpactIndex.model_validate(evidence["decision_changes"]["impact_index"]),
        "plans": (
            MigrationPlan.model_validate(evidence["migration_plan"]),
            MigrationPlan.model_validate(evidence["controls"]["g3"]["plan"]),
        ),
        "controls": tuple(
            ControlResult.model_validate(value) for value in evidence["controls"]["results"]
        ),
    }


def _replace(items, index, value):
    return (*items[:index], value, *items[index + 1 :])


def _replace_plan(arguments, plan_index, plan):
    arguments["plans"] = _replace(arguments["plans"], plan_index, plan)


def _mutate_operand(plan, trace_index, operand_index, **updates):
    trace = plan.rule_trace[trace_index]
    operand = trace.evaluated_operands[operand_index].model_copy(update=updates)
    trace = trace.model_copy(
        update={"evaluated_operands": _replace(trace.evaluated_operands, operand_index, operand)}
    )
    return plan.model_copy(update={"rule_trace": _replace(plan.rule_trace, trace_index, trace)})


def _endpoint(result):
    return ComparisonEndpoint(
        result_id=result.result_id,
        cohort=result.cohort,
        channel=result.channel,
        definition_ref=result.definition_ref,
        exact_value=result.exact_value,
    )


def test_ec00_golden_evidence_consistency_accepts(evidence, definitions, records, coverage):
    validate_evidence_consistency(**_typed_arguments(evidence, definitions, records, coverage))


def test_ec01_rejects_comparison_delta_inconsistent_with_endpoints(
    evidence, definitions, records, coverage
):
    arguments = _typed_arguments(evidence, definitions, records, coverage)
    comparison = arguments["comparisons"][0].model_copy(
        update={"exact_delta": ExactValue(numerator=1, denominator=2)}
    )
    arguments["comparisons"] = _replace(arguments["comparisons"], 0, comparison)
    with pytest.raises(ValueError, match="exact delta"):
        validate_evidence_consistency(**arguments)


def test_ec02_rejects_comparison_endpoint_value_inconsistent_with_result(
    evidence, definitions, records, coverage
):
    arguments = _typed_arguments(evidence, definitions, records, coverage)
    comparison = arguments["comparisons"][0]
    left = comparison.left.model_copy(
        update={"exact_value": ExactValue(numerator=1, denominator=2)}
    )
    arguments["comparisons"] = _replace(
        arguments["comparisons"], 0, comparison.model_copy(update={"left": left})
    )
    with pytest.raises(ValueError, match="left endpoint"):
        validate_evidence_consistency(**arguments)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("cohort", "2026-06"),
        ("channel", "Beta"),
        ("definition_ref", "qualified_activation_rate/2.0.0"),
    ],
)
def test_ec03_rejects_comparison_endpoint_metadata_inconsistent_with_result(
    evidence, definitions, records, coverage, field, value
):
    arguments = _typed_arguments(evidence, definitions, records, coverage)
    comparison = arguments["comparisons"][0]
    left = comparison.left.model_copy(update={field: value})
    arguments["comparisons"] = _replace(
        arguments["comparisons"], 0, comparison.model_copy(update={"left": left})
    )
    with pytest.raises(ValueError, match="left endpoint"):
        validate_evidence_consistency(**arguments)


def test_ec04_rejects_decision_state_inconsistent_with_recomputation(
    evidence, definitions, records, coverage
):
    arguments = _typed_arguments(evidence, definitions, records, coverage)
    change = arguments["decision_changes"][0].model_copy(update={"before_state": "MUTATED"})
    arguments["decision_changes"] = _replace(arguments["decision_changes"], 0, change)
    with pytest.raises(ValueError, match="decision changes"):
        validate_evidence_consistency(**arguments)


def test_ec05_rejects_decision_delta_inconsistent_with_recomputation(
    evidence, definitions, records, coverage
):
    arguments = _typed_arguments(evidence, definitions, records, coverage)
    change = arguments["decision_changes"][0].model_copy(
        update={"exact_delta": ExactValue(numerator=1, denominator=2)}
    )
    arguments["decision_changes"] = _replace(arguments["decision_changes"], 0, change)
    with pytest.raises(ValueError, match="decision changes"):
        validate_evidence_consistency(**arguments)


def test_ec06_rejects_false_equals_operand_stored_as_passing(
    evidence, definitions, records, coverage
):
    arguments = _typed_arguments(evidence, definitions, records, coverage)
    plan = _mutate_operand(arguments["plans"][0], 2, 0, actual="2026-05")
    _replace_plan(arguments, 0, plan)
    with pytest.raises(ValueError, match="stored operand outcome"):
        validate_evidence_consistency(**arguments)


def test_ec07_rejects_unresolved_operand_stored_as_passing(
    evidence, definitions, records, coverage
):
    arguments = _typed_arguments(evidence, definitions, records, coverage)
    plan = _mutate_operand(
        arguments["plans"][0],
        3,
        0,
        actual="2026-05/v1-only-history",
    )
    _replace_plan(arguments, 0, plan)
    with pytest.raises(ValueError, match="stored operand outcome"):
        validate_evidence_consistency(**arguments)


def test_ec08_rejects_positive_recommendation_with_rejection_actions(
    evidence, definitions, records, coverage
):
    arguments = _typed_arguments(evidence, definitions, records, coverage)
    positive, rejection = arguments["plans"]
    plan = positive.model_copy(
        update={"actions": rejection.actions, "rule_trace": rejection.rule_trace}
    )
    _replace_plan(arguments, 0, plan)
    with pytest.raises(ValueError, match="PARTIAL_RESTATEMENT"):
        validate_evidence_consistency(**arguments)


def test_ec09_rejects_rejection_recommendation_with_positive_actions(
    evidence, definitions, records, coverage
):
    arguments = _typed_arguments(evidence, definitions, records, coverage)
    positive, rejection = arguments["plans"]
    plan = rejection.model_copy(
        update={"actions": positive.actions, "rule_trace": positive.rule_trace}
    )
    _replace_plan(arguments, 1, plan)
    with pytest.raises(ValueError, match="REJECT_PENDING_EVIDENCE"):
        validate_evidence_consistency(**arguments)


def test_ec10_rejects_positive_plan_with_independently_failed_operand(
    evidence, definitions, records, coverage
):
    arguments = _typed_arguments(evidence, definitions, records, coverage)
    operand = arguments["plans"][0].rule_trace[0].evaluated_operands[1]
    actual = (*operand.actual[:-1], "2026-06:MISSING")
    plan = _mutate_operand(arguments["plans"][0], 0, 1, actual=actual, passed=False)
    _replace_plan(arguments, 0, plan)
    with pytest.raises(ValueError, match="positive rule trace"):
        validate_evidence_consistency(**arguments)


def test_ec11_rejects_action_to_rule_trace_mismatch(evidence, definitions, records, coverage):
    arguments = _typed_arguments(evidence, definitions, records, coverage)
    plan = arguments["plans"][0]
    action = plan.actions[0].model_copy(update={"policy_rule_ids": ("MP-R02_BRIDGE_MIN_TWO",)})
    plan = plan.model_copy(update={"actions": _replace(plan.actions, 0, action)})
    _replace_plan(arguments, 0, plan)
    with pytest.raises(ValueError, match="action-to-trace"):
        validate_evidence_consistency(**arguments)


def test_ec12_rejects_incomplete_impact_index(evidence, definitions, records, coverage):
    arguments = _typed_arguments(evidence, definitions, records, coverage)
    arguments["impact"] = arguments["impact"].model_copy(
        update={"decision_change_ids": arguments["impact"].decision_change_ids[:-1]}
    )
    with pytest.raises(ValueError, match="impact index"):
        validate_evidence_consistency(**arguments)


def test_ec13_rejects_comparison_control_context_inconsistent_with_analysis(
    evidence, definitions, records, coverage
):
    arguments = _typed_arguments(evidence, definitions, records, coverage)
    comparison = arguments["comparisons"][0].model_copy(update={"controlled_context_match": False})
    arguments["comparisons"] = _replace(arguments["comparisons"], 0, comparison)
    with pytest.raises(ValueError, match="controlled-context"):
        validate_evidence_consistency(**arguments)


def test_ec14_rejects_valid_definition_impact_without_valid_attribution(
    evidence, definitions, records, coverage
):
    arguments = _typed_arguments(evidence, definitions, records, coverage)
    comparison = arguments["comparisons"][2].model_copy(update={"valid": True})
    arguments["comparisons"] = _replace(arguments["comparisons"], 2, comparison)
    with pytest.raises(ValueError, match="attribution-valid"):
        validate_evidence_consistency(**arguments)


def test_ec15_rejects_valid_insufficient_evidence_comparison(
    evidence, definitions, records, coverage
):
    arguments = _typed_arguments(evidence, definitions, records, coverage)
    comparison = arguments["comparisons"][2].model_copy(
        update={
            "arm_difference_analysis_id": "ARM-DIFF-GOLDEN-V1-V2",
            "controlled_context_match": True,
            "valid": True,
        }
    )
    arguments["comparisons"] = _replace(arguments["comparisons"], 2, comparison)
    with pytest.raises(ValueError, match="insufficient-evidence"):
        validate_evidence_consistency(**arguments)


def test_ec16_rejects_restated_comparison_across_semantic_versions(
    evidence, definitions, records, coverage
):
    arguments = _typed_arguments(evidence, definitions, records, coverage)
    result = next(
        item for item in arguments["results"] if item.result_id == "RESULT-2026-05-ALPHA-V1_0_0"
    )
    comparison = arguments["comparisons"][1].model_copy(
        update={
            "left": _endpoint(result),
            "exact_delta": ExactValue(numerator=-3, denominator=40),
        }
    )
    arguments["comparisons"] = _replace(arguments["comparisons"], 1, comparison)
    with pytest.raises(ValueError, match="one semantic definition"):
        validate_evidence_consistency(**arguments)


def test_ec17_rejects_unregistered_noncomparable_same_definition(
    evidence, definitions, records, coverage
):
    arguments = _typed_arguments(evidence, definitions, records, coverage)
    result = next(
        item for item in arguments["results"] if item.result_id == "RESULT-2026-05-ALPHA-V2_0_0"
    )
    comparison = arguments["comparisons"][0].model_copy(
        update={
            "left": _endpoint(result),
            "exact_delta": ExactValue(numerator=1, denominator=10),
            "reason_codes": ("UNREGISTERED_INCOMPATIBILITY",),
        }
    )
    arguments["comparisons"] = _replace(arguments["comparisons"], 0, comparison)
    with pytest.raises(ValueError, match="lacks a semantic incompatibility"):
        validate_evidence_consistency(**arguments)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("scope_refs", ("2026-06",)),
        (
            "evidence_ids",
            ("CA-STITCH-ALPHA-2026-05-V1-TO-2026-06-V2",),
        ),
        ("assumption_ids", ("A_MIN_BRIDGE_COHORTS_2",)),
    ],
)
def test_ec18_rejects_action_projection_inconsistent_with_policy_evidence(
    evidence, definitions, records, coverage, field, value
):
    arguments = _typed_arguments(evidence, definitions, records, coverage)
    plan = arguments["plans"][0]
    action = plan.actions[0].model_copy(update={field: value})
    plan = plan.model_copy(update={"actions": _replace(plan.actions, 0, action)})
    _replace_plan(arguments, 0, plan)
    with pytest.raises(ValueError, match="disagree with recomputed policy"):
        validate_evidence_consistency(**arguments)


def test_ec19_rejects_rule_trace_with_unrelated_evidence(evidence, definitions, records, coverage):
    arguments = _typed_arguments(evidence, definitions, records, coverage)
    plan = arguments["plans"][0]
    trace = plan.rule_trace[0].model_copy(update={"evidence_ids": ("RESULT-2026-05-ALPHA-V1_0_0",)})
    plan = plan.model_copy(update={"rule_trace": _replace(plan.rule_trace, 0, trace)})
    _replace_plan(arguments, 0, plan)
    with pytest.raises(ValueError, match="unrelated"):
        validate_evidence_consistency(**arguments)


def test_ec20_rejection_requires_an_independently_failed_operand(
    evidence, definitions, records, coverage
):
    arguments = _typed_arguments(evidence, definitions, records, coverage)
    plan = _mutate_operand(arguments["plans"][1], 0, 0, actual=True, passed=True)
    _replace_plan(arguments, 1, plan)
    with pytest.raises(ValueError, match="lacks an independently failed"):
        validate_evidence_consistency(**arguments)


@pytest.mark.parametrize(
    ("actual", "message"),
    [(1, "stored operand outcome"), ("2", "requires integers")],
)
def test_ec21_recomputes_at_least_using_integer_operands(
    evidence, definitions, records, coverage, actual, message
):
    arguments = _typed_arguments(evidence, definitions, records, coverage)
    plan = _mutate_operand(arguments["plans"][0], 1, 1, actual=actual)
    _replace_plan(arguments, 0, plan)
    with pytest.raises(ValueError, match=message):
        validate_evidence_consistency(**arguments)


@pytest.mark.parametrize(
    ("updates", "message"),
    [({"condition": "MUTATED"}, "condition disagrees"), ({"outcome": "NOT_FIRED"}, "did not fire")],
)
def test_ec22_rejects_false_rule_trace_declarations(
    evidence, definitions, records, coverage, updates, message
):
    arguments = _typed_arguments(evidence, definitions, records, coverage)
    plan = arguments["plans"][0]
    trace = plan.rule_trace[0].model_copy(update=updates)
    plan = plan.model_copy(update={"rule_trace": _replace(plan.rule_trace, 0, trace)})
    _replace_plan(arguments, 0, plan)
    with pytest.raises(ValueError, match=message):
        validate_evidence_consistency(**arguments)


def test_ec23_human_approval_must_remain_pending(evidence, definitions, records, coverage):
    arguments = _typed_arguments(evidence, definitions, records, coverage)
    plan = arguments["plans"][0].model_copy(update={"human_approval_state": "APPROVED"})
    _replace_plan(arguments, 0, plan)
    with pytest.raises(ValueError, match="disagree with recomputed policy"):
        validate_evidence_consistency(**arguments)

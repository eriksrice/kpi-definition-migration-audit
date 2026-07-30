from __future__ import annotations

from fractions import Fraction

from .evaluation import build_decision_changes, build_migration_plan
from .models import (
    ArmDifferenceAnalysis,
    CohortReconstructability,
    ComparisonAssessment,
    ComparisonEndpoint,
    ComparisonVerdict,
    ControlResult,
    DecisionChange,
    DecisionContract,
    EvaluatedOperand,
    ExactValue,
    HorizonRestatementCoverage,
    ImpactIndex,
    MetricResult,
    MigrationPlan,
    MigrationPolicy,
    ReconstructabilityStatus,
    ResultStatus,
)

_GOLDEN_ANALYSIS_ID = "ARM-DIFF-GOLDEN-V1-V2"
_G3_ANALYSIS_ID = "ARM-DIFF-G3-V1-V2"
_POSITIVE_ACTION_TYPES = (
    "RESTATE_COHORT_RANGE",
    "DUAL_REPORT_COHORT_RANGE",
    "START_OFFICIAL_SERIES",
    "MARK_NON_COMPARABLE",
)
_POSITIVE_RULE_IDS = (
    "MP-R01_RESTATE_FULL",
    "MP-R02_BRIDGE_MIN_TWO",
    "MP-R03_START_EFFECTIVE",
    "MP-R04_NO_SPLICE",
)
_REJECTION_RULE_ID = "MP-R05_REJECT_CONTEXT_OR_EVIDENCE_GAP"
_REGISTERED_INCOMPATIBILITY_REASONS = {"CROSS_SEMANTIC_VERSION_TREND_PROHIBITED"}
_V2_DEFINITION_REF = "qualified_activation_rate/2.0.0"


def _unique_index[Item](items: tuple[Item, ...], attribute: str, label: str) -> dict[str, Item]:
    index: dict[str, Item] = {}
    for item in items:
        key = getattr(item, attribute)
        if key in index:
            raise ValueError(f"duplicate {label} identifier: {key}")
        index[key] = item
    return index


def _fraction(value: ExactValue) -> Fraction:
    return Fraction(value.numerator, value.denominator)


def _exact(value: Fraction) -> ExactValue:
    return ExactValue(numerator=value.numerator, denominator=value.denominator)


def _endpoint_from_result(result: MetricResult) -> ComparisonEndpoint:
    if result.status != ResultStatus.EXACT or result.exact_value is None:
        raise ValueError(f"comparison endpoint result is not exact: {result.result_id}")
    return ComparisonEndpoint(
        result_id=result.result_id,
        cohort=result.cohort,
        channel=result.channel,
        definition_ref=result.definition_ref,
        exact_value=result.exact_value,
    )


def _invalid_scoped_comparison(
    comparison: ComparisonAssessment,
    policy: MigrationPolicy,
) -> bool:
    return (
        not comparison.valid
        and comparison.kind == "TREND_STITCH"
        and comparison.left.cohort == policy.bridge_start
        and comparison.right.cohort == policy.bridge_end
        and comparison.left.channel == comparison.right.channel
        and comparison.left.definition_ref != comparison.right.definition_ref
    )


def _validate_comparisons(
    comparisons: tuple[ComparisonAssessment, ...],
    result_by_id: dict[str, MetricResult],
    analysis_by_id: dict[str, ArmDifferenceAnalysis],
) -> None:
    for comparison in comparisons:
        try:
            left_result = result_by_id[comparison.left.result_id]
            right_result = result_by_id[comparison.right.result_id]
        except KeyError as error:
            raise ValueError(
                f"comparison endpoint result is unresolved: {comparison.assessment_id}"
            ) from error
        expected_left = _endpoint_from_result(left_result)
        expected_right = _endpoint_from_result(right_result)
        if comparison.left != expected_left:
            raise ValueError(
                f"comparison left endpoint disagrees with its result: {comparison.assessment_id}"
            )
        if comparison.right != expected_right:
            raise ValueError(
                f"comparison right endpoint disagrees with its result: {comparison.assessment_id}"
            )
        expected_delta = _exact(
            _fraction(right_result.exact_value) - _fraction(left_result.exact_value)
        )
        if comparison.exact_delta != expected_delta:
            raise ValueError(
                f"comparison exact delta disagrees with its endpoints: {comparison.assessment_id}"
            )
        try:
            analysis = analysis_by_id[comparison.arm_difference_analysis_id]
        except KeyError as error:
            raise ValueError(
                f"comparison analysis is unresolved: {comparison.assessment_id}"
            ) from error
        if comparison.controlled_context_match != analysis.controlled_context_match:
            raise ValueError(
                "comparison controlled-context result disagrees with its analysis: "
                f"{comparison.assessment_id}"
            )
        if comparison.kind == "DEFINITION_IMPACT" and comparison.valid:
            if not analysis.attribution_valid:
                raise ValueError(
                    "valid definition-impact comparison requires attribution-valid analysis: "
                    f"{comparison.assessment_id}"
                )
        if comparison.verdict == ComparisonVerdict.INSUFFICIENT_EVIDENCE and comparison.valid:
            raise ValueError(
                f"insufficient-evidence comparison cannot be valid: {comparison.assessment_id}"
            )
        if comparison.verdict == ComparisonVerdict.COMPARABLE_AFTER_RESTATEMENT:
            if comparison.left.definition_ref != comparison.right.definition_ref:
                raise ValueError(
                    "restated comparison endpoints must use one semantic definition: "
                    f"{comparison.assessment_id}"
                )
        if comparison.verdict == ComparisonVerdict.NOT_COMPARABLE_WITHOUT_BRIDGE:
            explicitly_incompatible = bool(
                set(comparison.reason_codes) & _REGISTERED_INCOMPATIBILITY_REASONS
            )
            if (
                comparison.left.definition_ref == comparison.right.definition_ref
                and not explicitly_incompatible
            ):
                raise ValueError(
                    "non-comparable comparison lacks a semantic incompatibility: "
                    f"{comparison.assessment_id}"
                )


def _decision_comparisons(
    comparisons: tuple[ComparisonAssessment, ...],
) -> tuple[ComparisonAssessment, ComparisonAssessment]:
    stitches = tuple(item for item in comparisons if item.kind == "TREND_STITCH")
    restated = tuple(item for item in comparisons if item.kind == "RESTATED_TREND")
    if len(stitches) != 1 or len(restated) != 1:
        raise ValueError("frozen decision path requires one stitch and one restated comparison")
    return stitches[0], restated[0]


def _validate_decisions(
    results: tuple[MetricResult, ...],
    comparisons: tuple[ComparisonAssessment, ...],
    contract: DecisionContract,
    decision_changes: tuple[DecisionChange, ...],
    impact: ImpactIndex,
) -> tuple[tuple[DecisionChange, ...], tuple[ComparisonAssessment, ComparisonAssessment]]:
    decision_comparisons = _decision_comparisons(comparisons)
    expected_changes, expected_impact = build_decision_changes(
        results, decision_comparisons, contract
    )
    if decision_changes != expected_changes:
        raise ValueError("serialized decision changes disagree with independent recomputation")
    if impact != expected_impact:
        raise ValueError("impact index disagrees with recomputed decision changes")
    return expected_changes, decision_comparisons


def _resolve_operand(
    operand: EvaluatedOperand,
    *,
    policy: MigrationPolicy,
    reconstructability: tuple[CohortReconstructability, ...],
    comparison_by_id: dict[str, ComparisonAssessment],
) -> bool:
    if operand.name == "non_reconstructable_history_reference":
        if not isinstance(operand.actual, str) or not isinstance(operand.expected, str):
            return False
        expected_scope = f"{policy.non_reconstructable_cohort}/v1-only-history"
        record = next(
            (
                item
                for item in reconstructability
                if item.definition_ref == _V2_DEFINITION_REF
                and item.cohort == policy.non_reconstructable_cohort
            ),
            None,
        )
        return (
            operand.actual == expected_scope
            and operand.expected == "NOT_RECONSTRUCTABLE"
            and record is not None
            and record.status == ReconstructabilityStatus.NOT_RECONSTRUCTABLE
        )
    if operand.name == "invalid_comparison_reference":
        if not isinstance(operand.actual, str) or operand.expected != "INVALID_SCOPED_COMPARISON":
            return False
        comparison = comparison_by_id.get(operand.actual)
        return comparison is not None and _invalid_scoped_comparison(comparison, policy)
    raise ValueError(f"unsupported frozen RESOLVES operand: {operand.name}")


def _recompute_operand(
    operand: EvaluatedOperand,
    *,
    policy: MigrationPolicy,
    reconstructability: tuple[CohortReconstructability, ...],
    comparison_by_id: dict[str, ComparisonAssessment],
) -> bool:
    if operand.operator == "EQUALS":
        return operand.actual == operand.expected
    if operand.operator == "AT_LEAST":
        if type(operand.actual) is not int or type(operand.expected) is not int:
            raise ValueError(f"AT_LEAST operand requires integers: {operand.name}")
        return operand.actual >= operand.expected
    if operand.operator == "ALL_TRUE":
        if not isinstance(operand.actual, tuple) or not isinstance(operand.expected, tuple):
            raise ValueError(f"ALL_TRUE operand requires status tuples: {operand.name}")
        if not all(isinstance(item, str) for item in (*operand.actual, *operand.expected)):
            raise ValueError(f"ALL_TRUE operand contains a non-status value: {operand.name}")
        return operand.actual == operand.expected
    if operand.operator == "RESOLVES":
        return _resolve_operand(
            operand,
            policy=policy,
            reconstructability=reconstructability,
            comparison_by_id=comparison_by_id,
        )
    raise ValueError(f"unsupported frozen operand operator: {operand.operator}")


def _condition(operands: tuple[EvaluatedOperand, ...]) -> str:
    return " AND ".join(f"{item.name}[{item.operator}]" for item in operands)


def _validate_plan(
    plan: MigrationPlan,
    expected: MigrationPlan,
    *,
    policy: MigrationPolicy,
    horizon: HorizonRestatementCoverage,
    reconstructability: tuple[CohortReconstructability, ...],
    comparison_by_id: dict[str, ComparisonAssessment],
) -> None:
    action_types = tuple(item.action_type for item in plan.actions)
    trace_by_rule = _unique_index(plan.rule_trace, "rule_id", "rule-trace")
    if plan.recommendation == "PARTIAL_RESTATEMENT":
        if action_types != _POSITIVE_ACTION_TYPES:
            raise ValueError(
                "PARTIAL_RESTATEMENT requires exactly the four approved positive actions"
            )
        if any(item.action_type == "REJECT_PENDING_EVIDENCE" for item in plan.actions):
            raise ValueError("PARTIAL_RESTATEMENT cannot contain a rejection action")
        if tuple(item.rule_id for item in plan.rule_trace) != _POSITIVE_RULE_IDS:
            raise ValueError("PARTIAL_RESTATEMENT requires the four approved positive traces")
        if horizon.status != "PARTIAL":
            raise ValueError("PARTIAL_RESTATEMENT requires partial horizon coverage")
    else:
        if action_types != ("REJECT_PENDING_EVIDENCE",):
            raise ValueError("REJECT_PENDING_EVIDENCE requires exactly one rejection action")
        if tuple(item.rule_id for item in plan.rule_trace) != (_REJECTION_RULE_ID,):
            raise ValueError("REJECT_PENDING_EVIDENCE requires the MP-R05 trace")

    for action in plan.actions:
        if len(action.policy_rule_ids) != 1:
            raise ValueError("every migration action must cite exactly one policy rule")
        rule_id = action.policy_rule_ids[0]
        trace = trace_by_rule.get(rule_id)
        if trace is None or trace.sequence != action.sequence:
            raise ValueError(
                f"action-to-trace policy rule is missing or mismatched: sequence {action.sequence}"
            )

    recomputed_by_rule: dict[str, tuple[bool, ...]] = {}
    operands_match_expected = True
    expected_trace_by_rule = {item.rule_id: item for item in expected.rule_trace}
    for trace in plan.rule_trace:
        if trace.outcome != "FIRED":
            raise ValueError(f"serialized rule trace did not fire: {trace.rule_id}")
        if trace.condition != _condition(trace.evaluated_operands):
            raise ValueError(f"rule-trace condition disagrees with its operands: {trace.rule_id}")
        expected_trace = expected_trace_by_rule.get(trace.rule_id)
        if expected_trace is None:
            raise ValueError(f"unexpected rule trace for plan: {trace.rule_id}")
        expected_operand_by_name = _unique_index(
            expected_trace.evaluated_operands, "name", "expected operand"
        )
        _unique_index(trace.evaluated_operands, "name", "operand")
        recomputed: list[bool] = []
        for operand in trace.evaluated_operands:
            outcome = _recompute_operand(
                operand,
                policy=policy,
                reconstructability=reconstructability,
                comparison_by_id=comparison_by_id,
            )
            recomputed.append(outcome)
            if operand.passed != outcome:
                raise ValueError(
                    f"stored operand outcome disagrees with recomputation: {operand.name}"
                )
            if plan.recommendation == "PARTIAL_RESTATEMENT" and not outcome:
                raise ValueError("positive rule trace contains an independently failed operand")
            expected_operand = expected_operand_by_name.get(operand.name)
            if expected_operand is None or operand != expected_operand:
                operands_match_expected = False
        recomputed_by_rule[trace.rule_id] = tuple(recomputed)
        corresponding_actions = tuple(
            action for action in plan.actions if trace.rule_id in action.policy_rule_ids
        )
        related_evidence = {
            *(item for operand in trace.evaluated_operands for item in operand.evidence_ids),
            *(item for action in corresponding_actions for item in action.evidence_ids),
        }
        unrelated = tuple(item for item in trace.evidence_ids if item not in related_evidence)
        if unrelated:
            raise ValueError(
                f"rule trace cites evidence unrelated to its operands or action: {unrelated}"
            )

    if plan.recommendation == "PARTIAL_RESTATEMENT":
        if not all(outcome for outcomes in recomputed_by_rule.values() for outcome in outcomes):
            raise ValueError("positive rule trace contains an independently failed operand")
    elif not any(not outcome for outcomes in recomputed_by_rule.values() for outcome in outcomes):
        raise ValueError("rejection plan lacks an independently failed evidence operand")

    if not operands_match_expected:
        raise ValueError("serialized operands disagree with referenced evidence")

    if plan != expected:
        raise ValueError(
            "migration recommendation, actions, or rule trace disagree with recomputed policy"
        )


def validate_derived_evidence(
    *,
    policy: MigrationPolicy,
    horizon: HorizonRestatementCoverage,
    reconstructability: tuple[CohortReconstructability, ...],
    results: tuple[MetricResult, ...],
    comparisons: tuple[ComparisonAssessment, ...],
    analyses: tuple[ArmDifferenceAnalysis, ...],
    contract: DecisionContract,
    decision_changes: tuple[DecisionChange, ...],
    impact: ImpactIndex,
    plans: tuple[MigrationPlan, ...],
    controls: tuple[ControlResult, ...],
) -> None:
    """Validate the frozen scenario's derived evidence before serialization."""
    result_by_id = _unique_index(results, "result_id", "metric-result")
    comparison_by_id = _unique_index(comparisons, "assessment_id", "comparison")
    analysis_by_id = _unique_index(analyses, "analysis_id", "arm-analysis")
    _validate_comparisons(comparisons, result_by_id, analysis_by_id)
    expected_changes, decision_comparisons = _validate_decisions(
        results, comparisons, contract, decision_changes, impact
    )

    try:
        golden_analysis = analysis_by_id[_GOLDEN_ANALYSIS_ID]
        g3_analysis = analysis_by_id[_G3_ANALYSIS_ID]
    except KeyError as error:
        raise ValueError("frozen migration plan analysis is unresolved") from error
    g3_comparisons = tuple(item for item in comparisons if item.kind == "DEFINITION_IMPACT")
    if len(g3_comparisons) != 1:
        raise ValueError("frozen G3 plan requires one definition-impact comparison")

    expected_positive = build_migration_plan(
        policy,
        horizon,
        reconstructability,
        decision_comparisons,
        expected_changes,
        golden_analysis,
        contract,
        controls,
    )
    expected_rejection = build_migration_plan(
        policy,
        horizon,
        reconstructability,
        g3_comparisons,
        expected_changes,
        g3_analysis,
        contract,
        (),
    )
    expected_by_id = {
        expected_positive.plan_id: expected_positive,
        expected_rejection.plan_id: expected_rejection,
    }
    plan_by_id = _unique_index(plans, "plan_id", "migration-plan")
    if set(plan_by_id) != set(expected_by_id):
        raise ValueError("serialized migration-plan set disagrees with recomputed plans")
    for plan_id, plan in plan_by_id.items():
        _validate_plan(
            plan,
            expected_by_id[plan_id],
            policy=policy,
            horizon=horizon,
            reconstructability=reconstructability,
            comparison_by_id=comparison_by_id,
        )

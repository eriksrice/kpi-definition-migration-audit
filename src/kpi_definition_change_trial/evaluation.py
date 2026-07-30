from __future__ import annotations

from fractions import Fraction

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
    MigrationAction,
    MigrationPlan,
    MigrationPolicy,
    ReconstructabilityStatus,
    ResultStatus,
    RuleTraceEntry,
)


def as_fraction(value: ExactValue) -> Fraction:
    return Fraction(value.numerator, value.denominator)


def exact(value: Fraction) -> ExactValue:
    return ExactValue(numerator=value.numerator, denominator=value.denominator)


def _require_result(
    results: tuple[MetricResult, ...], definition_ref: str, cohort: str, channel: str
) -> MetricResult:
    for result in results:
        if (
            result.definition_ref == definition_ref
            and result.cohort == cohort
            and result.channel == channel
        ):
            if result.status != ResultStatus.EXACT or result.exact_value is None:
                raise ValueError(
                    f"required exact result is absent: {definition_ref}/{cohort}/{channel}"
                )
            return result
    raise ValueError(f"result not found: {definition_ref}/{cohort}/{channel}")


def _endpoint(result: MetricResult) -> ComparisonEndpoint:
    if result.exact_value is None:
        raise ValueError("comparison endpoint must be exact")
    return ComparisonEndpoint(
        result_id=result.result_id,
        cohort=result.cohort,
        channel=result.channel,
        definition_ref=result.definition_ref,
        exact_value=result.exact_value,
    )


def build_comparisons(
    results: tuple[MetricResult, ...],
    arm_analysis: ArmDifferenceAnalysis,
) -> tuple[ComparisonAssessment, ...]:
    may_v1 = _require_result(results, "qualified_activation_rate/1.0.0", "2026-05", "Alpha")
    may_v2 = _require_result(results, "qualified_activation_rate/2.0.0", "2026-05", "Alpha")
    june_v2 = _require_result(results, "qualified_activation_rate/2.0.0", "2026-06", "Alpha")
    stitch_delta = as_fraction(june_v2.exact_value) - as_fraction(may_v1.exact_value)
    restated_delta = as_fraction(june_v2.exact_value) - as_fraction(may_v2.exact_value)
    return (
        ComparisonAssessment(
            assessment_id="CA-STITCH-ALPHA-2026-05-V1-TO-2026-06-V2",
            kind="TREND_STITCH",
            left=_endpoint(may_v1),
            right=_endpoint(june_v2),
            arm_difference_analysis_id=arm_analysis.analysis_id,
            controlled_context_match=arm_analysis.controlled_context_match,
            valid=False,
            verdict=ComparisonVerdict.NOT_COMPARABLE_WITHOUT_BRIDGE,
            exact_delta=exact(stitch_delta),
            reason_codes=("CROSS_SEMANTIC_VERSION_TREND_PROHIBITED",),
            evidence_ids=(may_v1.result_id, june_v2.result_id, arm_analysis.analysis_id),
            assumption_ids=("A_TREND_SAME_SEMANTICS",),
        ),
        ComparisonAssessment(
            assessment_id="CA-RESTATED-ALPHA-2026-05-V2-TO-2026-06-V2",
            kind="RESTATED_TREND",
            left=_endpoint(may_v2),
            right=_endpoint(june_v2),
            arm_difference_analysis_id=arm_analysis.analysis_id,
            controlled_context_match=arm_analysis.controlled_context_match,
            valid=True,
            verdict=ComparisonVerdict.COMPARABLE_AFTER_RESTATEMENT,
            exact_delta=exact(restated_delta),
            reason_codes=("BOTH_ENDPOINTS_RESTATED_UNDER_V2",),
            evidence_ids=(may_v2.result_id, june_v2.result_id, arm_analysis.analysis_id),
            assumption_ids=("A_TREND_SAME_SEMANTICS",),
        ),
    )


def build_g3_comparison(
    results: tuple[MetricResult, ...],
    arm_analysis: ArmDifferenceAnalysis,
) -> ComparisonAssessment:
    left = _require_result(results, "qualified_activation_rate/1.0.0", "2026-05", "Alpha")
    right = _require_result(results, "qualified_activation_rate/2.0.0", "2026-05", "Alpha")
    return ComparisonAssessment(
        assessment_id="CA-G3-CONFOUNDED-DEFINITION-IMPACT-2026-05-ALPHA",
        kind="DEFINITION_IMPACT",
        left=_endpoint(left),
        right=_endpoint(right),
        arm_difference_analysis_id=arm_analysis.analysis_id,
        controlled_context_match=arm_analysis.controlled_context_match,
        valid=False,
        verdict=ComparisonVerdict.INSUFFICIENT_EVIDENCE,
        exact_delta=exact(as_fraction(right.exact_value) - as_fraction(left.exact_value)),
        reason_codes=("CONTROLLED_CONTEXT_MISMATCH",),
        evidence_ids=(left.result_id, right.result_id, arm_analysis.analysis_id),
        assumption_ids=(),
    )


def _threshold_state(value: ExactValue, contract: DecisionContract) -> str:
    return "PASS" if as_fraction(value) >= as_fraction(contract.threshold) else "FAIL"


def _ranking(alpha: ExactValue, beta: ExactValue) -> str:
    left = as_fraction(alpha)
    right = as_fraction(beta)
    if left == right:
        return "Alpha = Beta"
    return "Alpha > Beta" if left > right else "Beta > Alpha"


def _change_classification(before_state: str, after_state: str) -> str:
    return "CHANGED" if before_state != after_state else "UNCHANGED"


def _trend_state(comparison: ComparisonAssessment) -> str:
    delta = as_fraction(comparison.exact_delta)
    if comparison.valid and comparison.verdict == ComparisonVerdict.COMPARABLE_AFTER_RESTATEMENT:
        authority = "VALID_RESTATED"
    elif (
        not comparison.valid
        and comparison.verdict == ComparisonVerdict.NOT_COMPARABLE_WITHOUT_BRIDGE
    ):
        authority = "PROHIBITED_APPARENT"
    else:
        authority = "VALID" if comparison.valid else "INVALID"
    direction = "IMPROVEMENT" if delta > 0 else "DECLINE" if delta < 0 else "NO_CHANGE"
    return f"{authority}_{direction}_{delta}"


def _operand_condition(operands: tuple[EvaluatedOperand, ...]) -> str:
    return " AND ".join(f"{item.name}[{item.operator}]" for item in operands)


def build_decision_changes(
    results: tuple[MetricResult, ...],
    comparisons: tuple[ComparisonAssessment, ...],
    contract: DecisionContract,
) -> tuple[tuple[DecisionChange, ...], ImpactIndex]:
    may_alpha_v1 = _require_result(results, "qualified_activation_rate/1.0.0", "2026-05", "Alpha")
    may_alpha_v2 = _require_result(results, "qualified_activation_rate/2.0.0", "2026-05", "Alpha")
    may_beta_v1 = _require_result(results, "qualified_activation_rate/1.0.0", "2026-05", "Beta")
    may_beta_v2 = _require_result(results, "qualified_activation_rate/2.0.0", "2026-05", "Beta")
    stitch, restated = comparisons
    threshold_before = _threshold_state(may_alpha_v1.exact_value, contract)
    threshold_after = _threshold_state(may_alpha_v2.exact_value, contract)
    ranking_before = _ranking(may_alpha_v1.exact_value, may_beta_v1.exact_value)
    ranking_after = _ranking(may_alpha_v2.exact_value, may_beta_v2.exact_value)
    trend_before = _trend_state(stitch)
    trend_after = _trend_state(restated)
    changes = (
        DecisionChange(
            change_id="DC-THRESHOLD-2026-05-ALPHA",
            change_type="THRESHOLD",
            scope="2026-05/Alpha",
            before_state=threshold_before,
            after_state=threshold_after,
            classification=_change_classification(threshold_before, threshold_after),
            exact_delta=exact(
                as_fraction(may_alpha_v2.exact_value) - as_fraction(may_alpha_v1.exact_value)
            ),
            comparison_ids=(),
            evidence_ids=(may_alpha_v1.result_id, may_alpha_v2.result_id, contract.contract_id),
            assumption_ids=("A_THRESHOLD_SYNTHETIC_080",),
        ),
        DecisionChange(
            change_id="DC-RANKING-2026-05",
            change_type="RANKING",
            scope="2026-05/Alpha,Beta",
            before_state=ranking_before,
            after_state=ranking_after,
            classification=_change_classification(ranking_before, ranking_after),
            comparison_ids=(),
            evidence_ids=(
                may_alpha_v1.result_id,
                may_beta_v1.result_id,
                may_alpha_v2.result_id,
                may_beta_v2.result_id,
            ),
            assumption_ids=(),
        ),
        DecisionChange(
            change_id="DC-TREND-INTERPRETATION-ALPHA",
            change_type="TREND_INTERPRETATION",
            scope="2026-05..2026-06/Alpha",
            before_state=trend_before,
            after_state=trend_after,
            classification=_change_classification(trend_before, trend_after),
            comparison_ids=(stitch.assessment_id, restated.assessment_id),
            evidence_ids=(stitch.assessment_id, restated.assessment_id),
            assumption_ids=("A_TREND_SAME_SEMANTICS",),
        ),
    )
    impact = ImpactIndex(value="MULTIPLE", decision_change_ids=tuple(x.change_id for x in changes))
    return changes, impact


def build_migration_plan(
    policy: MigrationPolicy,
    horizon: HorizonRestatementCoverage,
    reconstructability: tuple[CohortReconstructability, ...],
    comparisons: tuple[ComparisonAssessment, ...],
    decision_changes: tuple[DecisionChange, ...],
    arm_analysis: ArmDifferenceAnalysis,
    contract: DecisionContract,
    required_controls: tuple[ControlResult, ...],
) -> MigrationPlan:
    if not arm_analysis.attribution_valid:
        evidence = (arm_analysis.analysis_id,)
        attribution_operands = (
            EvaluatedOperand(
                name="definition_only_attribution_valid",
                operator="EQUALS",
                actual=arm_analysis.attribution_valid,
                expected=True,
                passed=arm_analysis.attribution_valid,
                evidence_ids=evidence,
            ),
        )
        return MigrationPlan(
            plan_id="PLAN-G3-REJECT",
            policy_id=policy.policy_id,
            horizon_start="2026-04",
            horizon_end="2026-06",
            recommendation="REJECT_PENDING_EVIDENCE",
            actions=(
                MigrationAction(
                    sequence=1,
                    action_type="REJECT_PENDING_EVIDENCE",
                    scope_start="2026-04",
                    scope_end="2026-06",
                    scope_refs=(arm_analysis.analysis_id,),
                    rationale="A non-metric controlled-context fingerprint differs.",
                    evidence_ids=evidence,
                    assumption_ids=(),
                    policy_rule_ids=("MP-R05_REJECT_CONTEXT_OR_EVIDENCE_GAP",),
                ),
            ),
            rule_trace=(
                RuleTraceEntry(
                    sequence=1,
                    rule_id="MP-R05_REJECT_CONTEXT_OR_EVIDENCE_GAP",
                    condition=_operand_condition(attribution_operands),
                    outcome="FIRED",
                    evaluated_operands=attribution_operands,
                    evidence_ids=evidence,
                ),
            ),
            human_approval_state="PENDING",
        )

    ordered_cohorts = ("2026-04", "2026-05", "2026-06")

    def cohort_range(start: str, end: str) -> tuple[str, ...]:
        try:
            start_index = ordered_cohorts.index(start)
            end_index = ordered_cohorts.index(end)
        except ValueError as error:
            raise ValueError("policy range is outside the frozen horizon") from error
        if start_index > end_index:
            raise ValueError("policy range start must not exceed its end")
        return ordered_cohorts[start_index : end_index + 1]

    reconstructability_by_cohort = {
        item.cohort: item
        for item in reconstructability
        if item.definition_ref == "qualified_activation_rate/2.0.0"
    }
    restatement_cohorts = cohort_range(policy.restatement_start, policy.restatement_end)
    bridge_cohorts = cohort_range(policy.bridge_start, policy.bridge_end)

    def statuses(cohorts: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(
            f"{cohort}:{reconstructability_by_cohort[cohort].status}"
            if cohort in reconstructability_by_cohort
            else f"{cohort}:MISSING"
            for cohort in cohorts
        )

    expected_restatement = tuple(
        f"{cohort}:{ReconstructabilityStatus.FULLY_RECONSTRUCTABLE}"
        for cohort in restatement_cohorts
    )
    expected_bridge = tuple(
        f"{cohort}:{ReconstructabilityStatus.FULLY_RECONSTRUCTABLE}" for cohort in bridge_cohorts
    )
    actual_restatement = statuses(restatement_cohorts)
    actual_bridge = statuses(bridge_cohorts)
    complete_bridge_count = sum(
        reconstructability_by_cohort.get(cohort) is not None
        and reconstructability_by_cohort[cohort].status
        == ReconstructabilityStatus.FULLY_RECONSTRUCTABLE
        for cohort in bridge_cohorts
    )
    comparison_by_id = {item.assessment_id: item for item in comparisons}
    non_comparable_scope_refs = (
        f"{policy.non_reconstructable_cohort}/v1-only-history",
        "CA-STITCH-ALPHA-2026-05-V1-TO-2026-06-V2",
    )
    history_record = reconstructability_by_cohort.get(policy.non_reconstructable_cohort)
    history_resolves = (
        history_record is not None
        and history_record.status == ReconstructabilityStatus.NOT_RECONSTRUCTABLE
    )
    comparison_ref = non_comparable_scope_refs[1]
    comparison_record = comparison_by_id.get(comparison_ref)
    comparison_resolves = (
        comparison_record is not None
        and not comparison_record.valid
        and comparison_record.kind == "TREND_STITCH"
        and comparison_record.left.cohort == policy.bridge_start
        and comparison_record.right.cohort == policy.bridge_end
        and comparison_record.left.channel == comparison_record.right.channel
        and comparison_record.left.definition_ref != comparison_record.right.definition_ref
    )
    controls_actual = tuple(
        f"{item.control_id}:{item.status}"
        for item in sorted(required_controls, key=lambda x: x.control_id)
    )
    controls_expected = tuple(f"G{index}:PASS" for index in range(1, 5))
    operands = {
        "horizon": EvaluatedOperand(
            name="horizon_restatement_coverage",
            operator="EQUALS",
            actual=str(horizon.status),
            expected="PARTIAL",
            passed=horizon.status == "PARTIAL",
            evidence_ids=(horizon.horizon_id,),
        ),
        "restatement": EvaluatedOperand(
            name="restatement_cohort_reconstructability",
            operator="ALL_TRUE",
            actual=actual_restatement,
            expected=expected_restatement,
            passed=actual_restatement == expected_restatement,
            evidence_ids=tuple(
                reconstructability_by_cohort[item].reconstructability_id
                for item in restatement_cohorts
                if item in reconstructability_by_cohort
            ),
        ),
        "bridge": EvaluatedOperand(
            name="bridge_cohort_reconstructability",
            operator="ALL_TRUE",
            actual=actual_bridge,
            expected=expected_bridge,
            passed=actual_bridge == expected_bridge,
            evidence_ids=tuple(
                reconstructability_by_cohort[item].reconstructability_id
                for item in bridge_cohorts
                if item in reconstructability_by_cohort
            ),
        ),
        "bridge_minimum": EvaluatedOperand(
            name="complete_bridge_cohort_count",
            operator="AT_LEAST",
            actual=complete_bridge_count,
            expected=policy.minimum_complete_bridge_cohorts,
            passed=complete_bridge_count >= policy.minimum_complete_bridge_cohorts,
            evidence_ids=(horizon.horizon_id,),
        ),
        "effective": EvaluatedOperand(
            name="effective_cohort",
            operator="EQUALS",
            actual=policy.effective_cohort,
            expected=contract.effective_cohort,
            passed=policy.effective_cohort == contract.effective_cohort,
            evidence_ids=(contract.contract_id, policy.policy_id),
        ),
        "history_ref": EvaluatedOperand(
            name="non_reconstructable_history_reference",
            operator="RESOLVES",
            actual=non_comparable_scope_refs[0],
            expected="NOT_RECONSTRUCTABLE",
            passed=history_resolves,
            evidence_ids=(
                (history_record.reconstructability_id if history_record else horizon.horizon_id),
            ),
        ),
        "comparison_ref": EvaluatedOperand(
            name="invalid_comparison_reference",
            operator="RESOLVES",
            actual=comparison_ref,
            expected="INVALID_SCOPED_COMPARISON",
            passed=comparison_resolves,
            evidence_ids=((comparison_ref,) if comparison_ref in comparison_by_id else ()),
        ),
        "controls": EvaluatedOperand(
            name="required_control_results",
            operator="ALL_TRUE",
            actual=controls_actual,
            expected=controls_expected,
            passed=controls_actual == controls_expected,
            evidence_ids=tuple(item.control_id for item in required_controls),
        ),
    }
    if not all(item.passed for item in operands.values()):
        failed = tuple(item for item in operands.values() if not item.passed)
        evidence = tuple(dict.fromkeys(item for operand in failed for item in operand.evidence_ids))
        return MigrationPlan(
            plan_id="PLAN-EVIDENCE-GATE-REJECT",
            policy_id=policy.policy_id,
            horizon_start="2026-04",
            horizon_end="2026-06",
            recommendation="REJECT_PENDING_EVIDENCE",
            actions=(
                MigrationAction(
                    sequence=1,
                    action_type="REJECT_PENDING_EVIDENCE",
                    scope_start="2026-04",
                    scope_end="2026-06",
                    scope_refs=tuple(item.name for item in failed),
                    rationale="One or more required policy evidence gates failed.",
                    evidence_ids=evidence,
                    assumption_ids=(),
                    policy_rule_ids=("MP-R05_REJECT_CONTEXT_OR_EVIDENCE_GAP",),
                ),
            ),
            rule_trace=(
                RuleTraceEntry(
                    sequence=1,
                    rule_id="MP-R05_REJECT_CONTEXT_OR_EVIDENCE_GAP",
                    condition=_operand_condition(failed),
                    outcome="FIRED",
                    evaluated_operands=failed,
                    evidence_ids=evidence,
                ),
            ),
            human_approval_state="PENDING",
        )

    comparison_ids = tuple(item.assessment_id for item in comparisons)
    change_ids = tuple(item.change_id for item in decision_changes)
    common_evidence = (horizon.horizon_id, *comparison_ids, *change_ids)
    actions = (
        MigrationAction(
            sequence=1,
            action_type="RESTATE_COHORT_RANGE",
            scope_start=policy.restatement_start,
            scope_end=policy.restatement_end,
            scope_refs=restatement_cohorts,
            rationale="Both declared cohorts are fully reconstructable under v2.",
            evidence_ids=(horizon.horizon_id,),
            assumption_ids=("A_TREND_SAME_SEMANTICS",),
            policy_rule_ids=("MP-R01_RESTATE_FULL",),
        ),
        MigrationAction(
            sequence=2,
            action_type="DUAL_REPORT_COHORT_RANGE",
            scope_start=policy.bridge_start,
            scope_end=policy.bridge_end,
            scope_refs=bridge_cohorts,
            rationale="Exactly two complete cohorts satisfy the frozen bridge assumption.",
            evidence_ids=common_evidence,
            assumption_ids=("A_MIN_BRIDGE_COHORTS_2",),
            policy_rule_ids=("MP-R02_BRIDGE_MIN_TWO",),
        ),
        MigrationAction(
            sequence=3,
            action_type="START_OFFICIAL_SERIES",
            scope_start=policy.effective_cohort,
            scope_end=policy.effective_cohort,
            scope_refs=("2026-06/v2-official",),
            rationale="The owner-frozen effective cohort is 2026-06.",
            evidence_ids=(horizon.horizon_id,),
            assumption_ids=("A_TREND_SAME_SEMANTICS",),
            policy_rule_ids=("MP-R03_START_EFFECTIVE",),
        ),
        MigrationAction(
            sequence=4,
            action_type="MARK_NON_COMPARABLE",
            scope_start=policy.non_reconstructable_cohort,
            scope_end=policy.non_reconstructable_cohort,
            scope_refs=non_comparable_scope_refs,
            rationale=(
                "April cannot be reconstructed under v2; cross-version trend stitches "
                "are prohibited."
            ),
            evidence_ids=(horizon.horizon_id, comparisons[0].assessment_id),
            assumption_ids=("A_TREND_SAME_SEMANTICS",),
            policy_rule_ids=("MP-R04_NO_SPLICE",),
        ),
    )
    restatement_operands = (operands["horizon"], operands["restatement"], operands["controls"])
    bridge_operands = (operands["bridge"], operands["bridge_minimum"], operands["controls"])
    effective_operands = (operands["effective"], operands["controls"])
    non_comparable_operands = (
        operands["history_ref"],
        operands["comparison_ref"],
        operands["controls"],
    )
    trace = (
        RuleTraceEntry(
            sequence=1,
            rule_id="MP-R01_RESTATE_FULL",
            condition=_operand_condition(restatement_operands),
            outcome="FIRED",
            evaluated_operands=restatement_operands,
            evidence_ids=actions[0].evidence_ids,
        ),
        RuleTraceEntry(
            sequence=2,
            rule_id="MP-R02_BRIDGE_MIN_TWO",
            condition=_operand_condition(bridge_operands),
            outcome="FIRED",
            evaluated_operands=bridge_operands,
            evidence_ids=actions[1].evidence_ids,
        ),
        RuleTraceEntry(
            sequence=3,
            rule_id="MP-R03_START_EFFECTIVE",
            condition=_operand_condition(effective_operands),
            outcome="FIRED",
            evaluated_operands=effective_operands,
            evidence_ids=actions[2].evidence_ids,
        ),
        RuleTraceEntry(
            sequence=4,
            rule_id="MP-R04_NO_SPLICE",
            condition=_operand_condition(non_comparable_operands),
            outcome="FIRED",
            evaluated_operands=non_comparable_operands,
            evidence_ids=actions[3].evidence_ids,
        ),
    )
    return MigrationPlan(
        plan_id="PLAN-GOLDEN-PARTIAL-RESTATEMENT",
        policy_id=policy.policy_id,
        horizon_start="2026-04",
        horizon_end="2026-06",
        recommendation="PARTIAL_RESTATEMENT",
        actions=actions,
        rule_trace=trace,
        human_approval_state="PENDING",
    )

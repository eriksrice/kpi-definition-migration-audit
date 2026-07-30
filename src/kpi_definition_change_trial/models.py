from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from fractions import Fraction
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CoverageStatus(StrEnum):
    AVAILABLE_COMPLETE = "AVAILABLE_COMPLETE"
    AVAILABLE_PARTIAL = "AVAILABLE_PARTIAL"
    UNAVAILABLE_NOT_RETAINED = "UNAVAILABLE_NOT_RETAINED"
    UNKNOWN = "UNKNOWN"


class ResultStatus(StrEnum):
    EXACT = "EXACT"
    NOT_COMPUTABLE = "NOT_COMPUTABLE"


class ReconstructabilityStatus(StrEnum):
    FULLY_RECONSTRUCTABLE = "FULLY_RECONSTRUCTABLE"
    NOT_RECONSTRUCTABLE = "NOT_RECONSTRUCTABLE"


class HorizonStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    NONE = "NONE"


class ComparisonVerdict(StrEnum):
    HISTORICALLY_COMPARABLE = "HISTORICALLY_COMPARABLE"
    COMPARABLE_AFTER_RESTATEMENT = "COMPARABLE_AFTER_RESTATEMENT"
    NOT_COMPARABLE_WITHOUT_BRIDGE = "NOT_COMPARABLE_WITHOUT_BRIDGE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class HumanApprovalState(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class EligibilityClause(StrictModel):
    kind: Literal["eligibility_at_signup"]
    required: Literal[True] = True


class ExcludeAccountClassesClause(StrictModel):
    kind: Literal["exclude_account_classes"]
    values: tuple[str, ...] = Field(min_length=1)


class SignupCohortClause(StrictModel):
    kind: Literal["signup_cohort"]
    granularity: Literal["MONTH"] = "MONTH"


class MaturityClause(StrictModel):
    kind: Literal["elapsed_day_maturity"]
    days: Literal[14] = 14


class ActivityWithinDaysClause(StrictModel):
    kind: Literal["qualifying_activity_within_days"]
    days: Literal[14] = 14


class CoreActionWithinDaysClause(StrictModel):
    kind: Literal["core_action_within_days"]
    days: Literal[14] = 14


class AllEligibleMaturedSignupsClause(StrictModel):
    kind: Literal["all_eligible_matured_signups"]


AtomicClause = Annotated[
    EligibilityClause
    | ExcludeAccountClassesClause
    | SignupCohortClause
    | MaturityClause
    | ActivityWithinDaysClause
    | CoreActionWithinDaysClause
    | AllEligibleMaturedSignupsClause,
    Field(discriminator="kind"),
]


class AndClause(StrictModel):
    kind: Literal["and"]
    members: tuple[AtomicClause, ...] = Field(min_length=1)


Predicate = Annotated[AtomicClause | AndClause, Field(discriminator="kind")]


_BASE_DEPENDENCIES = {
    "control.cutoff_timezone",
    "field.account_id",
}

_CLAUSE_DEPENDENCIES: dict[str, set[str]] = {
    "eligibility_at_signup": {"field.eligible_at_signup"},
    "exclude_account_classes": {"field.account_class"},
    "signup_cohort": {"field.signup_at", "field.channel"},
    "elapsed_day_maturity": {"field.signup_at"},
    "qualifying_activity_within_days": {
        "population.activity_qualified_account_fact",
        "field.activity_at",
        "field.activity_received_at",
    },
    "core_action_within_days": {"field.core_action_at", "field.core_action_received_at"},
    "all_eligible_matured_signups": {"population.authoritative_signup_roster"},
}


def derive_dependencies(*predicates: Predicate) -> tuple[str, ...]:
    dependencies = set(_BASE_DEPENDENCIES)
    for predicate in predicates:
        clauses = predicate.members if isinstance(predicate, AndClause) else (predicate,)
        for clause in clauses:
            dependencies.update(_CLAUSE_DEPENDENCIES[clause.kind])
    return tuple(sorted(dependencies))


class DependencyProjection(StrictModel):
    authority: Literal["GENERATED_FROM_REGISTERED_CLAUSES"] = "GENERATED_FROM_REGISTERED_CLAUSES"
    dependencies: tuple[str, ...]


class MetricDefinition(StrictModel):
    metric_id: Literal["qualified_activation_rate"]
    version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    entity: Literal["account"] = "account"
    grain: Literal["signup_month_channel"] = "signup_month_channel"
    numerator: Predicate
    denominator: Predicate
    aggregation: Literal["EXACT_RATIO"] = "EXACT_RATIO"
    direction: Literal["HIGHER_IS_BETTER"] = "HIGHER_IS_BETTER"
    missingness: Literal["NO_ESTIMATION"] = "NO_ESTIMATION"
    description: str
    owner: str
    effective_from: str
    provenance_id: str
    supersedes_version: str | None = None
    dependency_projection: DependencyProjection | None = None

    @model_validator(mode="after")
    def validate_projection(self) -> MetricDefinition:
        derived = derive_dependencies(self.numerator, self.denominator)
        if self.dependency_projection is None:
            object.__setattr__(
                self,
                "dependency_projection",
                DependencyProjection(dependencies=derived),
            )
        elif self.dependency_projection.dependencies != derived:
            raise ValueError("serialized dependency projection disagrees with registered clauses")
        return self


class ArtifactIdentity(StrictModel):
    definition_ref: str
    artifact_hash: str
    semantic_hash: str


class DefinitionChange(StrictModel):
    path: str
    semantic_dimension: str
    before: object
    after: object
    classification: Literal["NON_SEMANTIC", "SEMANTIC", "UNKNOWN"]
    derived_dependency_implications: tuple[str, ...] = ()


class DefinitionDiff(StrictModel):
    diff_id: str
    before_ref: str
    after_ref: str
    independent_semantic_changes: tuple[DefinitionChange, ...]
    non_semantic_changes: tuple[DefinitionChange, ...]
    semantic_relation: Literal["EQUIVALENT", "NON_EQUIVALENT", "UNDETERMINED"]


class SourceProvenance(StrictModel):
    provenance_id: str
    snapshot_id: str
    schema_version: str
    linkage_version: str
    completeness_declaration_id: str


class AccountRecord(StrictModel):
    account_id: str
    cohort: str = Field(pattern=r"^2026-(04|05|06)$")
    channel: Literal["Alpha", "Beta"]
    population: Literal["ACTIVITY_QUALIFIED_ACCOUNT_FACT", "AUTHORITATIVE_SIGNUP_ROSTER"]
    signup_at: datetime
    eligible_at_signup: bool
    account_class: Literal["CUSTOMER", "TEST", "INTERNAL"]
    activity_at: datetime | None
    activity_received_at: datetime | None
    core_action_at: datetime | None
    core_action_received_at: datetime | None
    provenance_id: str

    @model_validator(mode="after")
    def paired_timestamps(self) -> AccountRecord:
        if (self.activity_at is None) != (self.activity_received_at is None):
            raise ValueError("activity and receipt timestamps must be paired")
        if (self.core_action_at is None) != (self.core_action_received_at is None):
            raise ValueError("core action and receipt timestamps must be paired")
        return self


class CoverageDeclaration(StrictModel):
    cohort: str = Field(pattern=r"^2026-(04|05|06)$")
    complete: tuple[str, ...]
    partial: tuple[str, ...] = ()
    unavailable: tuple[str, ...] = ()
    unknown: tuple[str, ...] = ()

    @model_validator(mode="after")
    def categories_are_disjoint(self) -> CoverageDeclaration:
        categories = {
            "complete": self.complete,
            "partial": self.partial,
            "unavailable": self.unavailable,
            "unknown": self.unknown,
        }
        for name, values in categories.items():
            if len(values) != len(set(values)):
                raise ValueError(f"coverage category {name} contains duplicate dependencies")
        names = tuple(categories)
        for index, left_name in enumerate(names):
            for right_name in names[index + 1 :]:
                overlap = set(categories[left_name]).intersection(categories[right_name])
                if overlap:
                    raise ValueError(
                        "coverage categories are not mutually disjoint: "
                        f"{left_name}/{right_name}={sorted(overlap)}"
                    )
        return self


class SourceCoverage(StrictModel):
    coverage_id: str
    cohort: str
    dependency: str
    status: CoverageStatus
    evidence_ids: tuple[str, ...]


class CohortReconstructability(StrictModel):
    reconstructability_id: str
    cohort: str
    definition_ref: str
    status: ReconstructabilityStatus
    dependency_statuses: tuple[SourceCoverage, ...]
    reason_codes: tuple[str, ...]
    evidence_ids: tuple[str, ...]

    @model_validator(mode="after")
    def dependency_statuses_are_unambiguous(self) -> CohortReconstructability:
        dependencies = [item.dependency for item in self.dependency_statuses]
        if len(dependencies) != len(set(dependencies)):
            raise ValueError("required dependency coverage contains contradictory statuses")
        return self


class HorizonRestatementCoverage(StrictModel):
    horizon_id: str
    first_cohort: Literal["2026-04"]
    last_cohort: Literal["2026-06"]
    cohorts: tuple[str, ...]
    fully_reconstructable_cohorts: tuple[str, ...]
    non_reconstructable_cohorts: tuple[str, ...]
    status: HorizonStatus
    evidence_ids: tuple[str, ...]


class ExactValue(StrictModel):
    numerator: int
    denominator: int = Field(gt=0)

    @model_validator(mode="after")
    def reduced(self) -> ExactValue:
        reduced = Fraction(self.numerator, self.denominator)
        if (reduced.numerator, reduced.denominator) != (self.numerator, self.denominator):
            raise ValueError("exact value must be reduced")
        return self


class ExcludedRecord(StrictModel):
    account_id: str
    reason_codes: tuple[str, ...]


class MembershipTrace(StrictModel):
    denominator_record_ids: tuple[str, ...]
    numerator_record_ids: tuple[str, ...]
    excluded_records: tuple[ExcludedRecord, ...]

    @model_validator(mode="after")
    def membership_invariants(self) -> MembershipTrace:
        if len(self.denominator_record_ids) != len(set(self.denominator_record_ids)):
            raise ValueError("denominator membership IDs must be unique")
        if len(self.numerator_record_ids) != len(set(self.numerator_record_ids)):
            raise ValueError("numerator membership IDs must be unique")
        if not set(self.numerator_record_ids).issubset(self.denominator_record_ids):
            raise ValueError("numerator membership must be a denominator subset")
        return self


class MetricResult(StrictModel):
    result_id: str
    definition_ref: str
    cohort: str
    channel: str
    status: ResultStatus
    numerator_count: int | None
    denominator_count: int | None
    exact_value: ExactValue | None
    membership: MembershipTrace | None
    reason_codes: tuple[str, ...]
    source_evidence_ids: tuple[str, ...]

    @model_validator(mode="after")
    def result_consistency(self) -> MetricResult:
        numeric = (self.numerator_count, self.denominator_count, self.exact_value, self.membership)
        if self.status == ResultStatus.EXACT and any(item is None for item in numeric):
            raise ValueError("exact result requires counts, value, and membership")
        if self.status == ResultStatus.NOT_COMPUTABLE and any(item is not None for item in numeric):
            raise ValueError("non-computable result cannot contain a numeric projection")
        if self.status == ResultStatus.EXACT:
            assert self.membership is not None
            assert self.numerator_count is not None
            assert self.denominator_count is not None
            assert self.exact_value is not None
            if self.numerator_count != len(self.membership.numerator_record_ids):
                raise ValueError("numerator count must equal numerator membership length")
            if self.denominator_count != len(self.membership.denominator_record_ids):
                raise ValueError("denominator count must equal denominator membership length")
            if self.denominator_count <= 0:
                raise ValueError("exact result requires a positive denominator count")
            expected = Fraction(self.numerator_count, self.denominator_count)
            actual = Fraction(self.exact_value.numerator, self.exact_value.denominator)
            if actual != expected:
                raise ValueError("exact value must equal the reduced count ratio")
        return self


class DecisionContract(StrictModel):
    contract_id: Literal["golden_activation_decision_contract/1.0.0"]
    threshold: ExactValue
    threshold_operator: Literal["GREATER_THAN_OR_EQUAL"]
    ranking: Literal["DESCENDING_EXACT_WITH_TIES"]
    trend_rule: Literal["SAME_SEMANTICS_OR_EXPLICIT_RESTATEMENT"]
    horizon_start: Literal["2026-04"]
    horizon_end: Literal["2026-06"]
    effective_cohort: Literal["2026-06"]
    cutoff: datetime
    timezone: Literal["UTC"]
    maturity_days: Literal[14]
    assumption_ids: tuple[str, ...]


class AssumptionRecord(StrictModel):
    assumption_id: str
    statement: str
    classification: Literal["SYNTHETIC_SCENARIO_ASSUMPTION"]


class MigrationRule(StrictModel):
    rule_id: str
    description: str


class MigrationPolicy(StrictModel):
    policy_id: Literal["golden_activation_migration_policy/1.0.0"]
    minimum_complete_bridge_cohorts: Literal[2]
    restatement_start: Literal["2026-05"]
    restatement_end: Literal["2026-06"]
    bridge_start: Literal["2026-05"]
    bridge_end: Literal["2026-06"]
    effective_cohort: Literal["2026-06"]
    non_reconstructable_cohort: Literal["2026-04"]
    rules: tuple[MigrationRule, ...]


class EvaluationContextFingerprint(StrictModel):
    source_snapshot_hash: str
    source_schema_linkage_completeness_hash: str
    cutoff: datetime
    timezone: Literal["UTC"]
    grouping_hash: str
    decision_contract_hash: str
    evaluator_version: Literal["kpi-trial-evaluator/1.0.0"]


class TrialArm(StrictModel):
    arm_id: str
    definition_ref: str
    metric_artifact_hash: str
    metric_semantic_hash: str
    controlled_context: EvaluationContextFingerprint


class ContextDifference(StrictModel):
    field: str
    left: object
    right: object


class ArmDifferenceAnalysis(StrictModel):
    analysis_id: str
    left_arm_id: str
    right_arm_id: str
    metric_artifact_identity_different: bool
    metric_semantic_identity_different: bool
    non_metric_context_differences: tuple[ContextDifference, ...]
    controlled_context_match: bool
    attribution_valid: bool
    reason_codes: tuple[str, ...]


class ComparisonEndpoint(StrictModel):
    result_id: str
    cohort: str
    channel: str
    definition_ref: str
    exact_value: ExactValue


class ComparisonAssessment(StrictModel):
    assessment_id: str
    kind: Literal["TREND_STITCH", "RESTATED_TREND", "DEFINITION_IMPACT"]
    left: ComparisonEndpoint
    right: ComparisonEndpoint
    arm_difference_analysis_id: str
    controlled_context_match: bool
    valid: bool
    verdict: ComparisonVerdict
    exact_delta: ExactValue
    reason_codes: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    assumption_ids: tuple[str, ...]


class DecisionChange(StrictModel):
    change_id: str
    change_type: Literal["THRESHOLD", "RANKING", "TREND_INTERPRETATION"]
    scope: str
    before_state: str
    after_state: str
    classification: Literal["CHANGED", "UNCHANGED"]
    exact_delta: ExactValue | None = None
    comparison_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    assumption_ids: tuple[str, ...]

    @model_validator(mode="after")
    def classification_matches_states(self) -> DecisionChange:
        expected = "CHANGED" if self.before_state != self.after_state else "UNCHANGED"
        if self.classification != expected:
            raise ValueError("decision-change classification must be derived from its states")
        return self


class ImpactIndex(StrictModel):
    value: Literal["MULTIPLE"]
    decision_change_ids: tuple[str, ...]


OperandValue = bool | int | str | tuple[str, ...]


class EvaluatedOperand(StrictModel):
    name: str
    operator: Literal["EQUALS", "AT_LEAST", "ALL_TRUE", "RESOLVES"]
    actual: OperandValue
    expected: OperandValue
    passed: bool
    evidence_ids: tuple[str, ...]


class RuleTraceEntry(StrictModel):
    sequence: int = Field(ge=1)
    rule_id: str
    condition: str
    outcome: Literal["FIRED", "NOT_FIRED"]
    evaluated_operands: tuple[EvaluatedOperand, ...] = Field(min_length=1)
    evidence_ids: tuple[str, ...]


class MigrationAction(StrictModel):
    sequence: int = Field(ge=1)
    action_type: Literal[
        "RESTATE_COHORT_RANGE",
        "DUAL_REPORT_COHORT_RANGE",
        "START_OFFICIAL_SERIES",
        "MARK_NON_COMPARABLE",
        "REJECT_PENDING_EVIDENCE",
    ]
    scope_start: str
    scope_end: str
    scope_refs: tuple[str, ...] = Field(min_length=1)
    rationale: str
    evidence_ids: tuple[str, ...]
    assumption_ids: tuple[str, ...]
    policy_rule_ids: tuple[str, ...]


class MigrationPlan(StrictModel):
    plan_id: str
    policy_id: str
    horizon_start: Literal["2026-04"]
    horizon_end: Literal["2026-06"]
    recommendation: Literal["PARTIAL_RESTATEMENT", "REJECT_PENDING_EVIDENCE"]
    actions: tuple[MigrationAction, ...] = Field(min_length=1)
    rule_trace: tuple[RuleTraceEntry, ...] = Field(min_length=1)
    human_approval_state: Literal[HumanApprovalState.PENDING]

    @model_validator(mode="after")
    def sequences_are_unique_and_contiguous(self) -> MigrationPlan:
        action_sequences = [item.sequence for item in self.actions]
        trace_sequences = [item.sequence for item in self.rule_trace]
        if action_sequences != list(range(1, len(action_sequences) + 1)):
            raise ValueError("policy action sequences must be unique and contiguous")
        if trace_sequences != list(range(1, len(trace_sequences) + 1)):
            raise ValueError("rule-trace sequences must be unique and contiguous")
        return self


class HumanApprovalRecord(StrictModel):
    plan_id: str
    state: Literal[HumanApprovalState.APPROVED, HumanApprovalState.REJECTED]
    human_author: str = Field(min_length=1)
    decided_at: datetime
    rationale: str = Field(min_length=1)


class ControlResult(StrictModel):
    control_id: Literal["G1", "G2", "G3", "G4"]
    status: Literal["PASS", "FAIL"]
    assertions: tuple[str, ...]
    evidence_ids: tuple[str, ...]


class G4ControlInput(StrictModel):
    control_id: Literal["G4"]
    cohort: str = Field(pattern=r"^2026-(04|05|06)$")
    channel: Literal["Alpha", "Beta"]
    left_definition_ref: str
    right_definition_ref: str

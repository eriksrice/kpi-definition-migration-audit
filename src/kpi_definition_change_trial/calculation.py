from __future__ import annotations

from datetime import datetime, timedelta
from fractions import Fraction

from .canonical import definition_ref
from .models import (
    AccountRecord,
    AndClause,
    CohortReconstructability,
    CoverageDeclaration,
    CoverageStatus,
    ExactValue,
    ExcludedRecord,
    HorizonRestatementCoverage,
    HorizonStatus,
    MembershipTrace,
    MetricDefinition,
    MetricResult,
    ReconstructabilityStatus,
    ResultStatus,
    SourceCoverage,
)


def coverage_records(
    declaration: CoverageDeclaration,
    dependencies: tuple[str, ...],
) -> tuple[SourceCoverage, ...]:
    declared: dict[str, CoverageStatus] = {}
    for dependency in declaration.complete:
        declared[dependency] = CoverageStatus.AVAILABLE_COMPLETE
    for dependency in declaration.partial:
        declared[dependency] = CoverageStatus.AVAILABLE_PARTIAL
    for dependency in declaration.unavailable:
        declared[dependency] = CoverageStatus.UNAVAILABLE_NOT_RETAINED
    for dependency in declaration.unknown:
        declared[dependency] = CoverageStatus.UNKNOWN
    return tuple(
        SourceCoverage(
            coverage_id=f"COV-{declaration.cohort}-{dependency.replace('.', '-').upper()}",
            cohort=declaration.cohort,
            dependency=dependency,
            status=declared.get(dependency, CoverageStatus.UNKNOWN),
            evidence_ids=(f"COVERAGE-DECLARATION-{declaration.cohort}",),
        )
        for dependency in dependencies
    )


def assess_reconstructability(
    definition: MetricDefinition,
    declaration: CoverageDeclaration,
) -> CohortReconstructability:
    dependencies = definition.dependency_projection.dependencies
    statuses = coverage_records(declaration, dependencies)
    gaps = tuple(item for item in statuses if item.status != CoverageStatus.AVAILABLE_COMPLETE)
    status = (
        ReconstructabilityStatus.FULLY_RECONSTRUCTABLE
        if not gaps
        else ReconstructabilityStatus.NOT_RECONSTRUCTABLE
    )
    reasons = () if not gaps else tuple(f"{item.status}:{item.dependency}" for item in gaps)
    return CohortReconstructability(
        reconstructability_id=(
            f"RECON-{declaration.cohort}-{definition.version.replace('.', '_')}"
        ),
        cohort=declaration.cohort,
        definition_ref=definition_ref(definition),
        status=status,
        dependency_statuses=statuses,
        reason_codes=reasons,
        evidence_ids=tuple(item.coverage_id for item in statuses),
    )


def _clause_kinds(definition: MetricDefinition, part: str) -> set[str]:
    predicate = getattr(definition, part)
    clauses = predicate.members if isinstance(predicate, AndClause) else (predicate,)
    return {clause.kind for clause in clauses}


def _within_days(event_at: datetime | None, signup_at: datetime, days: int) -> bool:
    return event_at is not None and signup_at <= event_at <= signup_at + timedelta(days=days)


def calculate_metric(
    definition: MetricDefinition,
    records: tuple[AccountRecord, ...],
    declaration: CoverageDeclaration,
    cohort: str,
    channel: str,
    cutoff: datetime,
) -> MetricResult:
    reconstructability = assess_reconstructability(definition, declaration)
    result_id = f"RESULT-{cohort}-{channel.upper()}-V{definition.version.replace('.', '_')}"
    if reconstructability.status != ReconstructabilityStatus.FULLY_RECONSTRUCTABLE:
        return MetricResult(
            result_id=result_id,
            definition_ref=definition_ref(definition),
            cohort=cohort,
            channel=channel,
            status=ResultStatus.NOT_COMPUTABLE,
            numerator_count=None,
            denominator_count=None,
            exact_value=None,
            membership=None,
            reason_codes=reconstructability.reason_codes,
            source_evidence_ids=reconstructability.evidence_ids,
        )

    denominator_kinds = _clause_kinds(definition, "denominator")
    numerator_kinds = _clause_kinds(definition, "numerator")
    if "qualifying_activity_within_days" in denominator_kinds:
        expected_population = (
            "ACTIVITY_QUALIFIED_ACCOUNT_FACT"
            if cohort == "2026-04"
            else "AUTHORITATIVE_SIGNUP_ROSTER"
        )
    elif "all_eligible_matured_signups" in denominator_kinds:
        expected_population = "AUTHORITATIVE_SIGNUP_ROSTER"
    else:
        raise ValueError("unsupported denominator population clause")

    cohort_records = tuple(
        sorted(
            (
                record
                for record in records
                if record.cohort == cohort
                and record.channel == channel
                and record.population == expected_population
            ),
            key=lambda item: item.account_id,
        )
    )
    denominator_ids: list[str] = []
    numerator_ids: list[str] = []
    excluded: list[ExcludedRecord] = []

    for record in cohort_records:
        reasons: list[str] = []
        if not record.eligible_at_signup:
            reasons.append("INELIGIBLE_AT_SIGNUP")
        if record.account_class in {"TEST", "INTERNAL"}:
            reasons.append("EXCLUDED_ACCOUNT_CLASS")
        if record.signup_at + timedelta(days=14) > cutoff:
            reasons.append("NOT_MATURE_AT_CUTOFF")
        if record.signup_at.strftime("%Y-%m") != cohort:
            reasons.append("COHORT_LINKAGE_MISMATCH")

        base_included = not reasons
        denominator_included = base_included
        if "qualifying_activity_within_days" in denominator_kinds:
            activity_valid = _within_days(record.activity_at, record.signup_at, 14) and (
                record.activity_received_at is not None and record.activity_received_at <= cutoff
            )
            if not activity_valid:
                reasons.append("NO_QUALIFYING_ACTIVITY_BY_CUTOFF")
                denominator_included = False

        numerator_included = base_included
        if "core_action_within_days" in numerator_kinds:
            core_valid = _within_days(record.core_action_at, record.signup_at, 14) and (
                record.core_action_received_at is not None
                and record.core_action_received_at <= cutoff
            )
            numerator_included = numerator_included and core_valid

        if numerator_included and not denominator_included:
            raise ValueError(f"numerator member {record.account_id} is outside denominator")
        if denominator_included:
            denominator_ids.append(record.account_id)
        if numerator_included:
            numerator_ids.append(record.account_id)
        if not denominator_included:
            excluded.append(
                ExcludedRecord(
                    account_id=record.account_id,
                    reason_codes=tuple(sorted(set(reasons))) or ("NOT_IN_DENOMINATOR",),
                )
            )

    if not denominator_ids:
        raise ValueError(f"complete coverage produced empty denominator for {cohort}/{channel}")
    exact = Fraction(len(numerator_ids), len(denominator_ids))
    membership = MembershipTrace(
        denominator_record_ids=tuple(denominator_ids),
        numerator_record_ids=tuple(numerator_ids),
        excluded_records=tuple(excluded),
    )
    return MetricResult(
        result_id=result_id,
        definition_ref=definition_ref(definition),
        cohort=cohort,
        channel=channel,
        status=ResultStatus.EXACT,
        numerator_count=len(numerator_ids),
        denominator_count=len(denominator_ids),
        exact_value=ExactValue(numerator=exact.numerator, denominator=exact.denominator),
        membership=membership,
        reason_codes=(),
        source_evidence_ids=(
            reconstructability.reconstructability_id,
            f"SOURCE-RECORDS-{cohort}",
        ),
    )


def horizon_coverage(
    reconstructability: tuple[CohortReconstructability, ...],
) -> HorizonRestatementCoverage:
    cohorts = ("2026-04", "2026-05", "2026-06")
    by_cohort = {record.cohort: record for record in reconstructability}
    full = tuple(
        cohort
        for cohort in cohorts
        if by_cohort[cohort].status == ReconstructabilityStatus.FULLY_RECONSTRUCTABLE
    )
    missing = tuple(cohort for cohort in cohorts if cohort not in full)
    status = (
        HorizonStatus.COMPLETE
        if len(full) == 3
        else HorizonStatus.NONE
        if not full
        else HorizonStatus.PARTIAL
    )
    return HorizonRestatementCoverage(
        horizon_id="HORIZON-V2-2026-04-TO-2026-06",
        first_cohort="2026-04",
        last_cohort="2026-06",
        cohorts=cohorts,
        fully_reconstructable_cohorts=full,
        non_reconstructable_cohorts=missing,
        status=status,
        evidence_ids=tuple(by_cohort[cohort].reconstructability_id for cohort in cohorts),
    )

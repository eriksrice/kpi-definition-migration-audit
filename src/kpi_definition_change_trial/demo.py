from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any

_DENOMINATOR_LABELS = {
    "qualifying_activity_within_days": "activity-qualified accounts",
    "all_eligible_matured_signups": "all eligible matured signups",
}
_ACTION_LABELS = {
    "RESTATE_COHORT_RANGE": "Restate {scope_start} through {scope_end}",
    "DUAL_REPORT_COHORT_RANGE": "Dual-report {scope_start} through {scope_end}",
    "START_OFFICIAL_SERIES": "Begin the official {version} series in {scope_start}",
    "MARK_NON_COMPARABLE": ("Mark {scope_start} and cross-version stitches non-comparable"),
}


@dataclass(frozen=True)
class DemoAction:
    sequence: int
    action_type: str
    label: str


@dataclass(frozen=True)
class DemoEvidence:
    context_fixed: bool
    contract_id: str
    before_definition_ref: str
    after_definition_ref: str
    before_denominator: str
    after_denominator: str
    cohort: str
    channel: str
    before_numerator: int
    before_denominator_count: int
    before_value: Fraction
    after_numerator: int
    after_denominator_count: int
    after_value: Fraction
    threshold_before: str
    threshold_after: str
    rank_before: str
    rank_after: str
    stitch_delta: Fraction
    stitch_valid: bool
    stitch_verdict: str
    restated_delta: Fraction
    restated_valid: bool
    restated_verdict: str
    non_reconstructable_cohorts: tuple[str, ...]
    reconstructable_cohorts: tuple[str, ...]
    horizon_status: str
    recommendation: str
    human_approval_state: str
    actions: tuple[DemoAction, ...]
    confound_context_match: bool
    confound_attribution_valid: bool
    confound_comparison_valid: bool
    confound_verdict: str
    confound_recommendation: str


def _load(root: Path, name: str) -> Any:
    return json.loads((root / name).read_text(encoding="utf-8"))


def _fraction(exact_value: dict[str, int]) -> Fraction:
    return Fraction(exact_value["numerator"], exact_value["denominator"])


def _one(items: list[dict[str, Any]], *, label: str, **fields: Any) -> dict[str, Any]:
    matches = [
        item
        for item in items
        if all(item.get(field) == expected for field, expected in fields.items())
    ]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one {label}, found {len(matches)}")
    return matches[0]


def _denominator_label(predicate: dict[str, Any]) -> str:
    kinds = {item.get("kind") for item in predicate.get("members", ()) if isinstance(item, dict)}
    labels = [_DENOMINATOR_LABELS[kind] for kind in _DENOMINATOR_LABELS if kind in kinds]
    if len(labels) != 1:
        raise ValueError(f"unsupported demo denominator predicate kinds: {sorted(kinds)}")
    return labels[0]


def _version_label(definition_ref: str) -> str:
    version = definition_ref.rsplit("/", 1)[-1]
    return f"v{version.split('.', 1)[0]}"


def _action_label(action: dict[str, Any], definition_ref: str) -> str:
    try:
        template = _ACTION_LABELS[action["action_type"]]
    except KeyError as error:
        raise ValueError(f"unsupported demo action: {action.get('action_type')}") from error
    return template.format(
        scope_start=action["scope_start"],
        scope_end=action["scope_end"],
        version=_version_label(definition_ref),
    )


def load_demo_evidence(evidence_root: Path) -> DemoEvidence:
    definition_diff = _load(evidence_root, "definition_diff.json")
    semantic_change = _one(
        definition_diff["independent_semantic_changes"],
        label="denominator semantic change",
        path="$.denominator",
    )
    calculations = _load(evidence_root, "calculations.json")["golden"]
    before_ref = definition_diff["before_ref"]
    after_ref = definition_diff["after_ref"]
    cohort = "2026-05"
    channel = "Alpha"
    before_result = _one(
        calculations,
        label="before demo result",
        cohort=cohort,
        channel=channel,
        definition_ref=before_ref,
    )
    after_result = _one(
        calculations,
        label="after demo result",
        cohort=cohort,
        channel=channel,
        definition_ref=after_ref,
    )

    decisions = _load(evidence_root, "decision_changes.json")["changes"]
    threshold = _one(decisions, label="threshold decision", change_type="THRESHOLD")
    ranking = _one(decisions, label="ranking decision", change_type="RANKING")

    comparisons = _load(evidence_root, "comparisons.json")
    stitch = _one(comparisons, label="trend stitch", kind="TREND_STITCH")
    restated = _one(comparisons, label="restated trend", kind="RESTATED_TREND")

    horizon = _load(evidence_root, "horizon_coverage.json")
    plan = _load(evidence_root, "migration_plan.json")
    actions = tuple(
        DemoAction(
            sequence=action["sequence"],
            action_type=action["action_type"],
            label=_action_label(action, after_ref),
        )
        for action in sorted(plan["actions"], key=lambda item: item["sequence"])
    )

    controls = _load(evidence_root, "controls.json")
    confound = controls["g3"]
    context = _load(evidence_root, "context_differences.json")["golden"]
    provenance = _load(evidence_root, "provenance_assumptions.json")

    return DemoEvidence(
        context_fixed=context["controlled_context_match"],
        contract_id=provenance["decision_contract"]["contract_id"],
        before_definition_ref=before_ref,
        after_definition_ref=after_ref,
        before_denominator=_denominator_label(semantic_change["before"]),
        after_denominator=_denominator_label(semantic_change["after"]),
        cohort=cohort,
        channel=channel,
        before_numerator=before_result["numerator_count"],
        before_denominator_count=before_result["denominator_count"],
        before_value=_fraction(before_result["exact_value"]),
        after_numerator=after_result["numerator_count"],
        after_denominator_count=after_result["denominator_count"],
        after_value=_fraction(after_result["exact_value"]),
        threshold_before=threshold["before_state"],
        threshold_after=threshold["after_state"],
        rank_before=ranking["before_state"],
        rank_after=ranking["after_state"],
        stitch_delta=_fraction(stitch["exact_delta"]),
        stitch_valid=stitch["valid"],
        stitch_verdict=stitch["verdict"],
        restated_delta=_fraction(restated["exact_delta"]),
        restated_valid=restated["valid"],
        restated_verdict=restated["verdict"],
        non_reconstructable_cohorts=tuple(horizon["non_reconstructable_cohorts"]),
        reconstructable_cohorts=tuple(horizon["fully_reconstructable_cohorts"]),
        horizon_status=horizon["status"],
        recommendation=plan["recommendation"],
        human_approval_state=plan["human_approval_state"],
        actions=actions,
        confound_context_match=confound["arm_difference"]["controlled_context_match"],
        confound_attribution_valid=confound["arm_difference"]["attribution_valid"],
        confound_comparison_valid=confound["comparison"]["valid"],
        confound_verdict=confound["comparison"]["verdict"],
        confound_recommendation=confound["plan"]["recommendation"],
    )


def _decimal(value: Fraction) -> Decimal:
    return Decimal(value.numerator) / Decimal(value.denominator)


def format_percent(value: Fraction) -> str:
    percent = (_decimal(value) * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return f"{percent}%"


def format_percentage_points(value: Fraction) -> str:
    points = (_decimal(value) * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return f"{points:+}"


def _cohort_range(cohorts: tuple[str, ...]) -> str:
    if not cohorts:
        raise ValueError("demo cohort range is empty")
    return cohorts[0] if len(cohorts) == 1 else f"{cohorts[0]} through {cohorts[-1]}"


def render_terminal(evidence: DemoEvidence) -> str:
    before_metric = (
        f"{evidence.before_numerator}/{evidence.before_denominator_count} "
        f"({format_percent(evidence.before_value)})"
    )
    after_metric = (
        f"{evidence.after_numerator}/{evidence.after_denominator_count} "
        f"({format_percent(evidence.after_value)})"
    )
    lines = [
        "KPI DEFINITION CHANGE TRIAL",
        "Same records. Different KPI meaning. Different decisions.",
        "",
        f"1. DEFINITION - SAME RECORDS + DECISION CONTRACT: {str(evidence.context_fixed).upper()}",
        f"   Contract: {evidence.contract_id}",
        f"   v1: activated accounts / {evidence.before_denominator}",
        f"   v2: activated accounts / {evidence.after_denominator}",
        "",
        f"2. DECISION CONSEQUENCES - {evidence.cohort} {evidence.channel}",
        f"   KPI: {before_metric} -> {after_metric}",
        f"   Launch threshold: {evidence.threshold_before} -> {evidence.threshold_after}",
        f"   Channel rank: {evidence.rank_before} -> {evidence.rank_after}",
        "",
        "3. HISTORY",
        "   Prohibited cross-version stitch: "
        f"{format_percentage_points(evidence.stitch_delta)} pp "
        f"[valid={str(evidence.stitch_valid).lower()}; {evidence.stitch_verdict}]",
        "   Valid like-for-like v2 restatement: "
        f"{format_percentage_points(evidence.restated_delta)} pp "
        f"[valid={str(evidence.restated_valid).lower()}; {evidence.restated_verdict}]",
        "   Coverage: "
        f"{_cohort_range(evidence.non_reconstructable_cohorts)} not reconstructable; "
        f"{_cohort_range(evidence.reconstructable_cohorts)} fully reconstructable",
        "",
        f"4. POLICY-DERIVED PLAN - {evidence.recommendation}; "
        f"HUMAN APPROVAL {evidence.human_approval_state}",
        *(f"   {action.sequence}. {action.label}" for action in evidence.actions),
        "",
        "5. CONFOUND SAFEGUARD",
        "   Source-context change detected: "
        f"{str(not evidence.confound_context_match).upper()} -> "
        f"attribution refused: {str(not evidence.confound_attribution_valid).upper()}",
        f"   {evidence.confound_verdict} -> {evidence.confound_recommendation}",
        "",
    ]
    return "\n".join(lines)


def render_evidence_card(evidence: DemoEvidence) -> str:
    before_metric = (
        f"{evidence.before_numerator}/{evidence.before_denominator_count} · "
        f"{format_percent(evidence.before_value)}"
    )
    after_metric = (
        f"{evidence.after_numerator}/{evidence.after_denominator_count} · "
        f"{format_percent(evidence.after_value)}"
    )
    lines = [
        "# KPI Definition Change Trial - Evidence Card",
        "",
        "**Same records, different KPI meaning, different decisions.**",
        "",
        "## Definition change",
        "",
        f"- **v1:** activated accounts divided by {evidence.before_denominator}",
        f"- **v2:** activated accounts divided by {evidence.after_denominator}",
        "",
        "## Decision impact",
        "",
        "| Scope | Before | After |",
        "|---|---:|---:|",
        f"| {evidence.cohort} {evidence.channel} | {before_metric} | {after_metric} |",
        f"| Threshold | {evidence.threshold_before} | {evidence.threshold_after} |",
        f"| Channel rank | {evidence.rank_before} | {evidence.rank_after} |",
        "",
        "## Historical interpretation",
        "",
        "- **Prohibited stitch:** "
        f"{format_percentage_points(evidence.stitch_delta)} pp - "
        f"valid `{str(evidence.stitch_valid).lower()}`; `{evidence.stitch_verdict}`",
        "- **Valid v2 restatement:** "
        f"{format_percentage_points(evidence.restated_delta)} pp - "
        f"valid `{str(evidence.restated_valid).lower()}`; `{evidence.restated_verdict}`",
        "",
        "## Coverage",
        "",
        f"- {_cohort_range(evidence.non_reconstructable_cohorts)}: not reconstructable under v2",
        f"- {_cohort_range(evidence.reconstructable_cohorts)}: fully reconstructable",
        "",
        "## Migration plan",
        "",
        f"`{evidence.recommendation}` - human approval `{evidence.human_approval_state}`",
        "",
        *(f"{action.sequence}. {action.label}." for action in evidence.actions),
        "",
        "## Confound safeguard",
        "",
        f"Source-context change detected `{str(not evidence.confound_context_match).lower()}`; "
        f"attribution refused `{str(not evidence.confound_attribution_valid).lower()}`; "
        f"comparison valid `{str(evidence.confound_comparison_valid).lower()}`. "
        f"Result: `{evidence.confound_verdict}` -> "
        f"`{evidence.confound_recommendation}`.",
        "",
    ]
    return "\n".join(lines)


def _files(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def validate_canonical_match(
    generated_evidence: Path,
    accepted_evidence: Path,
    generated_schemas: Path,
    accepted_schemas: Path,
) -> None:
    failures: list[str] = []
    for label, generated, accepted in (
        ("evidence", generated_evidence, accepted_evidence),
        ("schemas", generated_schemas, accepted_schemas),
    ):
        generated_files = _files(generated)
        accepted_files = _files(accepted)
        for relative in sorted(set(generated_files) | set(accepted_files)):
            if generated_files.get(relative) != accepted_files.get(relative):
                failures.append(f"{label}/{relative}")
    if failures:
        raise ValueError(
            "fresh canonical output differs from accepted canonical evidence: "
            + ", ".join(failures)
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Render the fixed KPI-definition trial demo")
    parser.add_argument("--generated-evidence", type=Path, required=True)
    parser.add_argument("--accepted-evidence", type=Path, required=True)
    parser.add_argument("--generated-schemas", type=Path, required=True)
    parser.add_argument("--accepted-schemas", type=Path, required=True)
    args = parser.parse_args()
    try:
        validate_canonical_match(
            args.generated_evidence,
            args.accepted_evidence,
            args.generated_schemas,
            args.accepted_schemas,
        )
        evidence = load_demo_evidence(args.generated_evidence)
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise SystemExit(f"FAIL: {error}") from error
    print(render_terminal(evidence), end="")


if __name__ == "__main__":
    main()

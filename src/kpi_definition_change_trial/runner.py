from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from .calculation import assess_reconstructability, calculate_metric, horizon_coverage
from .canonical import (
    analyze_arm_difference,
    artifact_hash,
    build_arm,
    canonical_json_bytes,
    definition_diff,
    semantic_hash,
    sha256_value,
)
from .consistency import validate_derived_evidence
from .evaluation import (
    build_comparisons,
    build_decision_changes,
    build_g3_comparison,
    build_migration_plan,
)
from .models import (
    AccountRecord,
    ArmDifferenceAnalysis,
    AssumptionRecord,
    CohortReconstructability,
    ComparisonAssessment,
    ControlResult,
    CoverageDeclaration,
    DecisionChange,
    DecisionContract,
    DefinitionDiff,
    DependencyProjection,
    EvaluatedOperand,
    EvaluationContextFingerprint,
    ExactValue,
    G4ControlInput,
    HorizonRestatementCoverage,
    HumanApprovalRecord,
    ImpactIndex,
    MembershipTrace,
    MetricDefinition,
    MetricResult,
    MigrationAction,
    MigrationPlan,
    MigrationPolicy,
    SourceCoverage,
    SourceProvenance,
    TrialArm,
)
from .reporting import render_report, semantic_result_projection


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _models(path: Path, model: type[BaseModel]) -> tuple[Any, ...]:
    return tuple(model.model_validate(item) for item in _load(path))


def _dump(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, tuple | list):
        return [_dump(item) for item in value]
    if isinstance(value, dict):
        return {key: _dump(item) for key, item in value.items()}
    return value


def _result_set(
    definition: MetricDefinition,
    records: tuple[AccountRecord, ...],
    coverage: tuple[CoverageDeclaration, ...],
    cutoff: Any,
) -> tuple[MetricResult, ...]:
    declarations = {item.cohort: item for item in coverage}
    return tuple(
        calculate_metric(definition, records, declarations[cohort], cohort, channel, cutoff)
        for cohort in ("2026-04", "2026-05", "2026-06")
        for channel in ("Alpha", "Beta")
    )


def _semantic_decision_projection(
    results: tuple[MetricResult, ...], contract: DecisionContract
) -> dict[str, Any]:
    exact_results = tuple(item for item in results if item.exact_value is not None)
    threshold = Fraction(contract.threshold.numerator, contract.threshold.denominator)
    threshold_states = {
        f"{item.cohort}/{item.channel}": (
            "PASS"
            if Fraction(item.exact_value.numerator, item.exact_value.denominator) >= threshold
            else "FAIL"
        )
        for item in exact_results
    }
    rankings: dict[str, str] = {}
    for cohort in sorted({item.cohort for item in exact_results}):
        values = {
            item.channel: Fraction(item.exact_value.numerator, item.exact_value.denominator)
            for item in exact_results
            if item.cohort == cohort
        }
        if set(values) != {"Alpha", "Beta"}:
            continue
        rankings[cohort] = (
            "Alpha = Beta"
            if values["Alpha"] == values["Beta"]
            else "Alpha > Beta"
            if values["Alpha"] > values["Beta"]
            else "Beta > Alpha"
        )
    return {"rankings": rankings, "threshold_states": threshold_states}


def _require_resolved(label: str, references: tuple[str, ...], registry: set[str]) -> None:
    unresolved = tuple(reference for reference in references if reference not in registry)
    if unresolved:
        raise ValueError(f"unresolved {label}: {unresolved}")


def validate_reference_graph(
    *,
    definitions: tuple[MetricDefinition, ...],
    records: tuple[AccountRecord, ...],
    provenance: tuple[SourceProvenance, ...],
    coverage: tuple[CoverageDeclaration, ...],
    contract: DecisionContract,
    policy: MigrationPolicy,
    assumptions: tuple[AssumptionRecord, ...],
    arms: tuple[TrialArm, ...],
    analyses: tuple[ArmDifferenceAnalysis, ...],
    reconstructability: tuple[CohortReconstructability, ...],
    horizon: HorizonRestatementCoverage,
    results: tuple[MetricResult, ...],
    comparisons: tuple[ComparisonAssessment, ...],
    decision_changes: tuple[DecisionChange, ...],
    impact: ImpactIndex,
    plans: tuple[MigrationPlan, ...],
    controls: tuple[ControlResult, ...],
) -> None:
    """Reject dangling typed references before evidence serialization."""
    definition_refs = {f"{item.metric_id}/{item.version}" for item in definitions}
    provenance_ids = {item.provenance_id for item in provenance}
    assumption_ids = {item.assumption_id for item in assumptions}
    arm_ids = {item.arm_id for item in arms}
    analysis_ids = {item.analysis_id for item in analyses}
    coverage_ids = {
        item.coverage_id
        for reconstruction in reconstructability
        for item in reconstruction.dependency_statuses
    }
    reconstruction_ids = {item.reconstructability_id for item in reconstructability}
    result_ids = {item.result_id for item in results}
    comparison_ids = {item.assessment_id for item in comparisons}
    decision_change_ids = {item.change_id for item in decision_changes}
    control_ids = {item.control_id for item in controls}
    policy_rule_ids = {item.rule_id for item in policy.rules}
    cohort_ids = {item.cohort for item in coverage}
    declared_source_ids = {
        *(f"COVERAGE-DECLARATION-{cohort}" for cohort in cohort_ids),
        *(f"SOURCE-RECORDS-{cohort}" for cohort in cohort_ids),
    }
    artifact_ids = {
        "calculations.json",
        "cohort_reconstructability.json",
        "context_differences.json",
        "controls.json",
        "definition_diff.json",
        "identities.json",
    }
    evidence_registry = {
        contract.contract_id,
        policy.policy_id,
        horizon.horizon_id,
        *assumption_ids,
        *analysis_ids,
        *coverage_ids,
        *reconstruction_ids,
        *result_ids,
        *comparison_ids,
        *decision_change_ids,
        *control_ids,
        *declared_source_ids,
        *artifact_ids,
    }

    _require_resolved(
        "record provenance references",
        tuple(item.provenance_id for item in records),
        provenance_ids,
    )
    _require_resolved(
        "arm definition references", tuple(item.definition_ref for item in arms), definition_refs
    )
    for analysis in analyses:
        _require_resolved(
            f"{analysis.analysis_id} arm references",
            (analysis.left_arm_id, analysis.right_arm_id),
            arm_ids,
        )
    for reconstruction in reconstructability:
        _require_resolved(
            f"{reconstruction.reconstructability_id} definition reference",
            (reconstruction.definition_ref,),
            definition_refs,
        )
        _require_resolved(
            f"{reconstruction.reconstructability_id} evidence",
            reconstruction.evidence_ids,
            evidence_registry,
        )
        for dependency in reconstruction.dependency_statuses:
            _require_resolved(
                f"{dependency.coverage_id} evidence",
                dependency.evidence_ids,
                evidence_registry,
            )
    _require_resolved("horizon evidence", horizon.evidence_ids, evidence_registry)
    for result in results:
        _require_resolved(
            f"{result.result_id} definition reference", (result.definition_ref,), definition_refs
        )
        _require_resolved(
            f"{result.result_id} source evidence", result.source_evidence_ids, evidence_registry
        )
    for comparison in comparisons:
        _require_resolved(
            f"{comparison.assessment_id} result endpoints",
            (comparison.left.result_id, comparison.right.result_id),
            result_ids,
        )
        _require_resolved(
            f"{comparison.assessment_id} definition endpoints",
            (comparison.left.definition_ref, comparison.right.definition_ref),
            definition_refs,
        )
        _require_resolved(
            f"{comparison.assessment_id} arm analysis",
            (comparison.arm_difference_analysis_id,),
            analysis_ids,
        )
        _require_resolved(
            f"{comparison.assessment_id} evidence", comparison.evidence_ids, evidence_registry
        )
        _require_resolved(
            f"{comparison.assessment_id} assumptions",
            comparison.assumption_ids,
            assumption_ids,
        )
    for change in decision_changes:
        _require_resolved(f"{change.change_id} comparisons", change.comparison_ids, comparison_ids)
        _require_resolved(f"{change.change_id} evidence", change.evidence_ids, evidence_registry)
        _require_resolved(f"{change.change_id} assumptions", change.assumption_ids, assumption_ids)
    _require_resolved("impact-index changes", impact.decision_change_ids, decision_change_ids)
    for control in controls:
        _require_resolved(f"{control.control_id} evidence", control.evidence_ids, evidence_registry)
    for plan in plans:
        _require_resolved(f"{plan.plan_id} policy", (plan.policy_id,), {policy.policy_id})
        operand_names = {
            operand.name for trace in plan.rule_trace for operand in trace.evaluated_operands
        }
        scope_registry = {
            *cohort_ids,
            *analysis_ids,
            *comparison_ids,
            *operand_names,
            *(f"{cohort}/v1-only-history" for cohort in cohort_ids),
            *(f"{cohort}/v2-official" for cohort in cohort_ids),
        }
        for action in plan.actions:
            _require_resolved(f"{plan.plan_id} action scope", action.scope_refs, scope_registry)
            _require_resolved(
                f"{plan.plan_id} action evidence", action.evidence_ids, evidence_registry
            )
            _require_resolved(
                f"{plan.plan_id} action assumptions", action.assumption_ids, assumption_ids
            )
            _require_resolved(
                f"{plan.plan_id} action policy rules",
                action.policy_rule_ids,
                policy_rule_ids,
            )
        for trace in plan.rule_trace:
            _require_resolved(
                f"{plan.plan_id} trace policy rule", (trace.rule_id,), policy_rule_ids
            )
            _require_resolved(
                f"{plan.plan_id} trace evidence", trace.evidence_ids, evidence_registry
            )
            for operand in trace.evaluated_operands:
                _require_resolved(
                    f"{plan.plan_id} operand {operand.name} evidence",
                    operand.evidence_ids,
                    evidence_registry,
                )


def validate_evidence_consistency(
    *,
    definitions: tuple[MetricDefinition, ...],
    records: tuple[AccountRecord, ...],
    provenance: tuple[SourceProvenance, ...],
    coverage: tuple[CoverageDeclaration, ...],
    contract: DecisionContract,
    policy: MigrationPolicy,
    assumptions: tuple[AssumptionRecord, ...],
    arms: tuple[TrialArm, ...],
    analyses: tuple[ArmDifferenceAnalysis, ...],
    reconstructability: tuple[CohortReconstructability, ...],
    horizon: HorizonRestatementCoverage,
    results: tuple[MetricResult, ...],
    comparisons: tuple[ComparisonAssessment, ...],
    decision_changes: tuple[DecisionChange, ...],
    impact: ImpactIndex,
    plans: tuple[MigrationPlan, ...],
    controls: tuple[ControlResult, ...],
) -> None:
    """Reject unresolved or internally contradictory evidence before serialization."""
    validate_reference_graph(
        definitions=definitions,
        records=records,
        provenance=provenance,
        coverage=coverage,
        contract=contract,
        policy=policy,
        assumptions=assumptions,
        arms=arms,
        analyses=analyses,
        reconstructability=reconstructability,
        horizon=horizon,
        results=results,
        comparisons=comparisons,
        decision_changes=decision_changes,
        impact=impact,
        plans=plans,
        controls=controls,
    )
    validate_derived_evidence(
        policy=policy,
        horizon=horizon,
        reconstructability=reconstructability,
        results=results,
        comparisons=comparisons,
        analyses=analyses,
        contract=contract,
        decision_changes=decision_changes,
        impact=impact,
        plans=plans,
        controls=controls,
    )


def build_evidence(fixtures_dir: Path) -> dict[str, Any]:
    v1 = MetricDefinition.model_validate(_load(fixtures_dir / "definitions/v1.json"))
    v2 = MetricDefinition.model_validate(_load(fixtures_dir / "definitions/v2.json"))
    v101 = MetricDefinition.model_validate(_load(fixtures_dir / "definitions/v1_0_1.json"))
    records = _models(fixtures_dir / "sources/account_records.json", AccountRecord)
    provenance = _models(fixtures_dir / "sources/provenance.json", SourceProvenance)
    g3_provenance = SourceProvenance.model_validate(
        _load(fixtures_dir / "controls/g3_provenance.json")
    )
    g4_input = G4ControlInput.model_validate(_load(fixtures_dir / "controls/g4_case.json"))
    if (
        g4_input.left_definition_ref != "qualified_activation_rate/1.0.0"
        or g4_input.right_definition_ref != "qualified_activation_rate/2.0.0"
    ):
        raise ValueError("G4 definition references must resolve to the frozen v1/v2 pair")
    coverage = _models(fixtures_dir / "sources/coverage.json", CoverageDeclaration)
    contract = DecisionContract.model_validate(_load(fixtures_dir / "contracts/decision.json"))
    policy = MigrationPolicy.model_validate(_load(fixtures_dir / "contracts/migration_policy.json"))
    assumptions = _models(fixtures_dir / "contracts/assumptions.json", AssumptionRecord)
    provenance_ids = {item.provenance_id for item in provenance}
    if len({item.account_id for item in records}) != len(records):
        raise ValueError("source account IDs must be unique")
    if any(item.provenance_id not in provenance_ids for item in records):
        raise ValueError("every source record must resolve to declared provenance")

    diff = definition_diff(v1, v2)
    g2_diff = definition_diff(v1, v101)
    source_snapshot = {"records": _dump(records), "provenance": _dump(provenance)}
    source_context = {
        "schema_linkage_completeness": [
            {
                "schema_version": item.schema_version,
                "linkage_version": item.linkage_version,
                "completeness_declaration_id": item.completeness_declaration_id,
            }
            for item in provenance
        ],
        "coverage": _dump(coverage),
    }
    common_arm_args = {
        "source_snapshot": source_snapshot,
        "source_schema_linkage_completeness": source_context,
        "cutoff": contract.cutoff,
        "timezone": contract.timezone,
        "grouping": {"grain": "signup_month_channel", "channels": ["Alpha", "Beta"]},
        "decision_contract": contract,
    }
    arm_v1 = build_arm(arm_id="ARM-GOLDEN-V1", definition=v1, **common_arm_args)
    arm_v2 = build_arm(arm_id="ARM-GOLDEN-V2", definition=v2, **common_arm_args)
    golden_analysis = analyze_arm_difference(
        arm_v1, arm_v2, diff, analysis_id="ARM-DIFF-GOLDEN-V1-V2"
    )

    g3_snapshot = {
        "records": _dump(records),
        "provenance": [*_dump(provenance), _dump(g3_provenance)],
    }
    g3_arm_v2 = build_arm(
        arm_id="ARM-G3-V2-CONFOUNDED",
        definition=v2,
        **{**common_arm_args, "source_snapshot": g3_snapshot},
    )
    g3_analysis = analyze_arm_difference(arm_v1, g3_arm_v2, diff, analysis_id="ARM-DIFF-G3-V1-V2")

    v1_results = _result_set(v1, records, coverage, contract.cutoff)
    v2_results = _result_set(v2, records, coverage, contract.cutoff)
    v101_results = _result_set(v101, records, coverage, contract.cutoff)
    golden_results = tuple(sorted((*v1_results, *v2_results), key=lambda item: item.result_id))
    reconstructability = tuple(
        assess_reconstructability(definition, declaration)
        for definition in (v1, v2, v101)
        for declaration in coverage
    )
    v2_reconstructability = tuple(
        item for item in reconstructability if item.definition_ref.endswith("/2.0.0")
    )
    horizon = horizon_coverage(v2_reconstructability)
    comparisons = build_comparisons(golden_results, golden_analysis)
    decision_changes, impact = build_decision_changes(golden_results, comparisons, contract)
    g3_comparison = build_g3_comparison(golden_results, g3_analysis)
    g3_plan = build_migration_plan(
        policy,
        horizon,
        reconstructability,
        (g3_comparison,),
        decision_changes,
        g3_analysis,
        contract,
        (),
    )

    v1_projection = semantic_result_projection(_dump(v1_results))
    v101_projection = semantic_result_projection(_dump(v101_results))
    v1_decision_projection = _semantic_decision_projection(v1_results, contract)
    v101_decision_projection = _semantic_decision_projection(v101_results, contract)
    may_beta_v1 = next(
        item
        for item in v1_results
        if item.cohort == g4_input.cohort and item.channel == g4_input.channel
    )
    may_beta_v2 = next(
        item
        for item in v2_results
        if item.cohort == g4_input.cohort and item.channel == g4_input.channel
    )
    expected_g1 = {
        ("1.0.0", "2026-04", "Alpha"): (6, 7),
        ("1.0.0", "2026-04", "Beta"): (7, 9),
        ("1.0.0", "2026-05", "Alpha"): (7, 8),
        ("1.0.0", "2026-05", "Beta"): (8, 10),
        ("1.0.0", "2026-06", "Alpha"): (8, 9),
        ("1.0.0", "2026-06", "Beta"): (8, 10),
        ("2.0.0", "2026-05", "Alpha"): (7, 10),
        ("2.0.0", "2026-05", "Beta"): (8, 10),
        ("2.0.0", "2026-06", "Alpha"): (8, 10),
        ("2.0.0", "2026-06", "Beta"): (8, 10),
    }
    actual_g1 = {
        (item.definition_ref.rsplit("/", 1)[1], item.cohort, item.channel): (
            item.numerator_count,
            item.denominator_count,
        )
        for item in golden_results
        if item.status == "EXACT"
    }
    april_v2_absent = all(
        item.status == "NOT_COMPUTABLE" for item in v2_results if item.cohort == "2026-04"
    )
    control_results = (
        ControlResult(
            control_id="G1",
            status="PASS" if actual_g1 == expected_g1 and april_v2_absent else "FAIL",
            assertions=(
                "record-level counts match the frozen aggregate oracle",
                "April v2 has no result",
            ),
            evidence_ids=("calculations.json", "cohort_reconstructability.json"),
        ),
        ControlResult(
            control_id="G2",
            status=(
                "PASS"
                if artifact_hash(v1) != artifact_hash(v101)
                and semantic_hash(v1) == semantic_hash(v101)
                and v1_projection == v101_projection
                and v1_decision_projection == v101_decision_projection
                else "FAIL"
            ),
            assertions=(
                "artifact hashes differ",
                "semantic hashes match",
                "semantic membership/calculation/decision projections match",
            ),
            evidence_ids=("identities.json", "controls.json"),
        ),
        ControlResult(
            control_id="G3",
            status=(
                "PASS"
                if not g3_analysis.controlled_context_match
                and g3_comparison.verdict == "INSUFFICIENT_EVIDENCE"
                and len(g3_plan.actions) == 1
                else "FAIL"
            ),
            assertions=(
                "actual non-metric fingerprint difference discovered",
                "definition diff retained and attribution refused",
                "only rejection action emitted",
            ),
            evidence_ids=("context_differences.json", "controls.json"),
        ),
        ControlResult(
            control_id="G4",
            status=(
                "PASS"
                if may_beta_v1.exact_value == may_beta_v2.exact_value
                and semantic_hash(v1) != semantic_hash(v2)
                else "FAIL"
            ),
            assertions=(
                "May Beta values are both 4/5",
                "semantic relation remains non-equivalent",
            ),
            evidence_ids=("calculations.json", "definition_diff.json"),
        ),
    )
    plan = build_migration_plan(
        policy,
        horizon,
        reconstructability,
        comparisons,
        decision_changes,
        golden_analysis,
        contract,
        control_results,
    )
    controls = {
        "results": control_results,
        "g2": {
            "definition_diff": g2_diff,
            "v1_semantic_result_projection": v1_projection,
            "v1_0_1_semantic_result_projection": v101_projection,
            "v1_semantic_decision_projection": v1_decision_projection,
            "v1_0_1_semantic_decision_projection": v101_decision_projection,
        },
        "g3": {
            "arm_difference": g3_analysis,
            "definition_diff": diff,
            "comparison": g3_comparison,
            "plan": g3_plan,
        },
        "g4": {
            "input": g4_input,
            "scope": f"{g4_input.cohort}/{g4_input.channel}",
            "v1_exact_value": may_beta_v1.exact_value,
            "v2_exact_value": may_beta_v2.exact_value,
            "numeric_delta": ExactValue(numerator=0, denominator=1),
            "semantic_relation": "NON_EQUIVALENT",
        },
    }

    validate_evidence_consistency(
        definitions=(v1, v2, v101),
        records=records,
        provenance=(*provenance, g3_provenance),
        coverage=coverage,
        contract=contract,
        policy=policy,
        assumptions=assumptions,
        arms=(arm_v1, arm_v2, g3_arm_v2),
        analyses=(golden_analysis, g3_analysis),
        reconstructability=reconstructability,
        horizon=horizon,
        results=(*golden_results, *v101_results),
        comparisons=(*comparisons, g3_comparison),
        decision_changes=decision_changes,
        impact=impact,
        plans=(plan, g3_plan),
        controls=control_results,
    )

    evidence = {
        "identities": {
            "v1": {
                "definition_ref": "qualified_activation_rate/1.0.0",
                "artifact_hash": artifact_hash(v1),
                "semantic_hash": semantic_hash(v1),
            },
            "v2": {
                "definition_ref": "qualified_activation_rate/2.0.0",
                "artifact_hash": artifact_hash(v2),
                "semantic_hash": semantic_hash(v2),
            },
            "v1_0_1": {
                "definition_ref": "qualified_activation_rate/1.0.1",
                "artifact_hash": artifact_hash(v101),
                "semantic_hash": semantic_hash(v101),
            },
            "canonical_input_bundle_hash": sha256_value(
                {
                    "definitions": _dump((v1, v2, v101)),
                    "records": _dump(records),
                    "provenance": _dump(provenance),
                    "coverage": _dump(coverage),
                    "contract": _dump(contract),
                    "policy": _dump(policy),
                    "assumptions": _dump(assumptions),
                    "g3_provenance": _dump(g3_provenance),
                    "g4_input": _dump(g4_input),
                }
            ),
        },
        "trial_arms": {"golden": (arm_v1, arm_v2), "g3": (arm_v1, g3_arm_v2)},
        "context_differences": {"golden": golden_analysis, "g3": g3_analysis},
        "definition_diff": diff,
        "source_coverage": tuple(
            sorted(
                {
                    status.coverage_id: status
                    for item in reconstructability
                    for status in item.dependency_statuses
                }.values(),
                key=lambda item: item.coverage_id,
            )
        ),
        "cohort_reconstructability": reconstructability,
        "horizon_coverage": horizon,
        "calculations": {
            "golden": golden_results,
            "v1_0_1": v101_results,
        },
        "comparisons": comparisons,
        "decision_changes": {"changes": decision_changes, "impact_index": impact},
        "migration_plan": plan,
        "controls": controls,
        "provenance_assumptions": {
            "source_provenance": provenance,
            "g3_source_provenance": g3_provenance,
            "assumptions": assumptions,
            "decision_contract": contract,
            "migration_policy": policy,
        },
    }
    return _dump(evidence)


_SCHEMA_MODELS: tuple[type[BaseModel], ...] = (
    MetricDefinition,
    DependencyProjection,
    DefinitionDiff,
    SourceProvenance,
    AccountRecord,
    SourceCoverage,
    CohortReconstructability,
    HorizonRestatementCoverage,
    DecisionContract,
    MigrationPolicy,
    AssumptionRecord,
    TrialArm,
    EvaluationContextFingerprint,
    ArmDifferenceAnalysis,
    ExactValue,
    EvaluatedOperand,
    MembershipTrace,
    MetricResult,
    ComparisonAssessment,
    DecisionChange,
    ImpactIndex,
    MigrationAction,
    MigrationPlan,
    HumanApprovalRecord,
    ControlResult,
    G4ControlInput,
)


def write_schemas(schemas_dir: Path) -> None:
    schemas_dir.mkdir(parents=True, exist_ok=True)
    for model in _SCHEMA_MODELS:
        name = "".join(
            [f"_{char.lower()}" if char.isupper() else char for char in model.__name__]
        ).lstrip("_")
        (schemas_dir / f"{name}.schema.json").write_bytes(
            canonical_json_bytes(model.model_json_schema())
        )


def write_evidence(evidence: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_names = (
        "identities",
        "trial_arms",
        "context_differences",
        "definition_diff",
        "source_coverage",
        "cohort_reconstructability",
        "horizon_coverage",
        "calculations",
        "comparisons",
        "decision_changes",
        "migration_plan",
        "controls",
        "provenance_assumptions",
    )
    for name in artifact_names:
        (output_dir / f"{name}.json").write_bytes(canonical_json_bytes(evidence[name]))
    report = render_report(evidence)
    (output_dir / "report.md").write_text(report, encoding="utf-8", newline="\n")
    manifest = {
        "bundle_id": evidence["identities"]["canonical_input_bundle_hash"],
        "artifacts": {
            path.name: "sha256:" + __import__("hashlib").sha256(path.read_bytes()).hexdigest()
            for path in sorted(output_dir.iterdir(), key=lambda item: item.name)
            if path.is_file() and path.name != "bundle_manifest.json"
        },
    }
    (output_dir / "bundle_manifest.json").write_bytes(canonical_json_bytes(manifest))


def execute(fixtures_dir: Path, output_dir: Path, schemas_dir: Path) -> dict[str, Any]:
    evidence = build_evidence(fixtures_dir)
    failed_controls = [
        item["control_id"] for item in evidence["controls"]["results"] if item["status"] != "PASS"
    ]
    if failed_controls:
        raise ValueError(f"golden validation failed controls: {failed_controls}")
    if not evidence["context_differences"]["golden"]["attribution_valid"]:
        raise ValueError("golden arm attribution is invalid")
    write_evidence(evidence, output_dir)
    write_schemas(schemas_dir)
    return evidence

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel

from .models import (
    AndClause,
    ArmDifferenceAnalysis,
    ContextDifference,
    DefinitionChange,
    DefinitionDiff,
    EvaluationContextFingerprint,
    MetricDefinition,
    Predicate,
    TrialArm,
)


def canonical_json_bytes(value: Any) -> bytes:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()


def sha256_value(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def canonical_predicate(predicate: Predicate) -> dict[str, Any]:
    if isinstance(predicate, AndClause):
        members = [canonical_predicate(member) for member in predicate.members]
        members.sort(key=lambda item: canonical_json_bytes(item))
        return {"kind": "and", "members": members}
    value = predicate.model_dump(mode="json")
    if value["kind"] == "exclude_account_classes":
        value["values"] = sorted(value["values"])
    return value


def semantic_projection(definition: MetricDefinition) -> dict[str, Any]:
    projection = {
        "aggregation": definition.aggregation,
        "denominator": canonical_predicate(definition.denominator),
        "direction": definition.direction,
        "entity": definition.entity,
        "grain": definition.grain,
        "metric_id": definition.metric_id,
        "missingness": definition.missingness,
        "numerator": canonical_predicate(definition.numerator),
        "dependency_projection": definition.dependency_projection.model_dump(mode="json"),
    }
    return projection


def artifact_hash(definition: MetricDefinition) -> str:
    return sha256_value(definition)


def semantic_hash(definition: MetricDefinition) -> str:
    return sha256_value(semantic_projection(definition))


def definition_ref(definition: MetricDefinition) -> str:
    return f"{definition.metric_id}/{definition.version}"


def definition_diff(before: MetricDefinition, after: MetricDefinition) -> DefinitionDiff:
    before_projection = semantic_projection(before)
    after_projection = semantic_projection(after)
    before_dependencies = set(before.dependency_projection.dependencies)
    after_dependencies = set(after.dependency_projection.dependencies)
    implications = tuple(
        [f"ADDED:{item}" for item in sorted(after_dependencies - before_dependencies)]
        + [f"REMOVED:{item}" for item in sorted(before_dependencies - after_dependencies)]
    )

    independent: list[DefinitionChange] = []
    semantic_keys = sorted(set(before_projection) | set(after_projection))
    for key in semantic_keys:
        if key == "dependency_projection":
            continue
        if before_projection.get(key) == after_projection.get(key):
            continue
        dimension = "denominator_population" if key == "denominator" else key
        independent.append(
            DefinitionChange(
                path=f"$.{key}",
                semantic_dimension=dimension,
                before=before_projection.get(key),
                after=after_projection.get(key),
                classification="SEMANTIC",
                derived_dependency_implications=implications if key == "denominator" else (),
            )
        )

    non_semantic: list[DefinitionChange] = []
    for key in ("version", "description", "provenance_id", "effective_from", "supersedes_version"):
        left = getattr(before, key)
        right = getattr(after, key)
        if left != right:
            non_semantic.append(
                DefinitionChange(
                    path=f"$.{key}",
                    semantic_dimension="artifact_metadata",
                    before=left,
                    after=right,
                    classification="NON_SEMANTIC",
                )
            )

    relation = "EQUIVALENT" if not independent else "NON_EQUIVALENT"
    return DefinitionDiff(
        diff_id=f"DIFF-{before.version}-TO-{after.version}",
        before_ref=definition_ref(before),
        after_ref=definition_ref(after),
        independent_semantic_changes=tuple(independent),
        non_semantic_changes=tuple(non_semantic),
        semantic_relation=relation,
    )


def build_arm(
    *,
    arm_id: str,
    definition: MetricDefinition,
    source_snapshot: Any,
    source_schema_linkage_completeness: Any,
    cutoff: Any,
    timezone: str,
    grouping: Any,
    decision_contract: Any,
) -> TrialArm:
    context = EvaluationContextFingerprint(
        source_snapshot_hash=sha256_value(source_snapshot),
        source_schema_linkage_completeness_hash=sha256_value(source_schema_linkage_completeness),
        cutoff=cutoff,
        timezone=timezone,
        grouping_hash=sha256_value(grouping),
        decision_contract_hash=sha256_value(decision_contract),
        evaluator_version="kpi-trial-evaluator/1.0.0",
    )
    return TrialArm(
        arm_id=arm_id,
        definition_ref=definition_ref(definition),
        metric_artifact_hash=artifact_hash(definition),
        metric_semantic_hash=semantic_hash(definition),
        controlled_context=context,
    )


def analyze_arm_difference(
    left: TrialArm,
    right: TrialArm,
    diff: DefinitionDiff,
    *,
    analysis_id: str,
) -> ArmDifferenceAnalysis:
    left_context = left.controlled_context.model_dump(mode="json")
    right_context = right.controlled_context.model_dump(mode="json")
    differences = tuple(
        ContextDifference(field=key, left=left_context[key], right=right_context[key])
        for key in sorted(left_context)
        if left_context[key] != right_context[key]
    )
    artifact_different = left.metric_artifact_hash != right.metric_artifact_hash
    semantic_different = left.metric_semantic_hash != right.metric_semantic_hash
    exactly_denominator = (
        len(diff.independent_semantic_changes) == 1
        and diff.independent_semantic_changes[0].semantic_dimension == "denominator_population"
    )
    match = not differences
    valid = artifact_different and semantic_different and exactly_denominator and match
    reasons: list[str] = []
    if not match:
        reasons.append("CONTROLLED_CONTEXT_MISMATCH")
    if semantic_different and not exactly_denominator:
        reasons.append("UNAPPROVED_SEMANTIC_INTERVENTION")
    if not artifact_different:
        reasons.append("METRIC_ARTIFACT_UNCHANGED")
    if not semantic_different:
        reasons.append("METRIC_SEMANTICS_UNCHANGED")
    if valid:
        reasons.append("APPROVED_DENOMINATOR_INTERVENTION_ONLY")
    return ArmDifferenceAnalysis(
        analysis_id=analysis_id,
        left_arm_id=left.arm_id,
        right_arm_id=right.arm_id,
        metric_artifact_identity_different=artifact_different,
        metric_semantic_identity_different=semantic_different,
        non_metric_context_differences=differences,
        controlled_context_match=match,
        attribution_valid=valid,
        reason_codes=tuple(reasons),
    )

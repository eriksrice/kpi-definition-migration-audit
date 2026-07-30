from __future__ import annotations

from copy import deepcopy

import pytest
from conftest import load_json
from pydantic import ValidationError

from kpi_definition_change_trial.canonical import (
    artifact_hash,
    canonical_predicate,
    definition_diff,
    semantic_hash,
)
from kpi_definition_change_trial.models import (
    ExactValue,
    HumanApprovalRecord,
    MembershipTrace,
    MetricDefinition,
)


def test_c01_definitions_are_explicit_valid_and_versioned(definitions):
    assert {item.version for item in definitions.values()} == {"1.0.0", "1.0.1", "2.0.0"}
    invalid = deepcopy(load_json("definitions/v1.json"))
    invalid["version"] = "latest"
    with pytest.raises(ValidationError):
        MetricDefinition.model_validate(invalid)


def test_c01_extra_or_unregistered_fields_are_rejected():
    invalid = deepcopy(load_json("definitions/v1.json"))
    invalid["sql"] = "select *"
    with pytest.raises(ValidationError):
        MetricDefinition.model_validate(invalid)


def test_clarification_b_dependencies_are_derived(definitions):
    dependencies = definitions["v2"].dependency_projection.dependencies
    assert "population.authoritative_signup_roster" in dependencies
    assert "population.activity_qualified_account_fact" not in dependencies


def test_clarification_b_mismatched_projection_is_rejected():
    invalid = deepcopy(load_json("definitions/v2.json"))
    invalid["dependency_projection"] = {
        "authority": "GENERATED_FROM_REGISTERED_CLAUSES",
        "dependencies": ["field.account_id"],
    }
    with pytest.raises(ValidationError, match="disagrees"):
        MetricDefinition.model_validate(invalid)


def test_c02_golden_diff_is_exactly_one_denominator_change(definitions):
    diff = definition_diff(definitions["v1"], definitions["v2"])
    assert len(diff.independent_semantic_changes) == 1
    assert diff.independent_semantic_changes[0].semantic_dimension == "denominator_population"
    assert diff.independent_semantic_changes[0].derived_dependency_implications


def test_c03_artifact_and_semantic_identity_are_separate(definitions):
    assert artifact_hash(definitions["v1"]) != artifact_hash(definitions["v101"])
    assert semantic_hash(definitions["v1"]) == semantic_hash(definitions["v101"])
    assert definition_diff(definitions["v1"], definitions["v101"]).semantic_relation == "EQUIVALENT"


def test_c04_equal_output_does_not_imply_equivalence(evidence):
    g4 = evidence["controls"]["g4"]
    assert g4["v1_exact_value"] == g4["v2_exact_value"] == {"numerator": 4, "denominator": 5}
    assert g4["semantic_relation"] == "NON_EQUIVALENT"


def test_c18_registered_commutative_order_and_sets_normalize(definitions):
    assert canonical_predicate(definitions["v1"].numerator) == canonical_predicate(
        definitions["v101"].numerator
    )
    assert canonical_predicate(definitions["v1"].denominator) == canonical_predicate(
        definitions["v101"].denominator
    )


@pytest.mark.parametrize("kind", ["sql", "python", "or", "function"])
def test_c18_unsupported_predicates_refuse(kind):
    invalid = deepcopy(load_json("definitions/v1.json"))
    invalid["denominator"] = {"kind": kind, "expression": "x"}
    with pytest.raises(ValidationError):
        MetricDefinition.model_validate(invalid)


def test_exact_values_must_be_reduced():
    with pytest.raises(ValidationError, match="reduced"):
        ExactValue(numerator=8, denominator=10)


def test_numerator_subset_is_a_schema_invariant():
    with pytest.raises(ValidationError, match="subset"):
        MembershipTrace(
            denominator_record_ids=("A",),
            numerator_record_ids=("B",),
            excluded_records=(),
        )


def test_c20_approval_requires_separate_human_record():
    approval = HumanApprovalRecord(
        plan_id="P",
        state="APPROVED",
        human_author="owner@example.invalid",
        decided_at="2026-07-29T00:00:00Z",
        rationale="Separate human evidence decision.",
    )
    assert approval.state == "APPROVED"

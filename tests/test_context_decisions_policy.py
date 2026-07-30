from __future__ import annotations

from kpi_definition_change_trial.canonical import analyze_arm_difference, build_arm, definition_diff
from kpi_definition_change_trial.models import ExactValue


def test_c16_valid_golden_context_excludes_metric_identity(evidence):
    analysis = evidence["context_differences"]["golden"]
    assert analysis["metric_artifact_identity_different"] is True
    assert analysis["metric_semantic_identity_different"] is True
    assert analysis["non_metric_context_differences"] == []
    assert analysis["controlled_context_match"] is True
    assert analysis["attribution_valid"] is True


def test_c09_scoped_comparisons_coexist(evidence):
    stitch, restated = evidence["comparisons"]
    assert (stitch["valid"], stitch["verdict"], stitch["exact_delta"]) == (
        False,
        "NOT_COMPARABLE_WITHOUT_BRIDGE",
        {"numerator": -3, "denominator": 40},
    )
    assert (restated["valid"], restated["verdict"], restated["exact_delta"]) == (
        True,
        "COMPARABLE_AFTER_RESTATEMENT",
        {"numerator": 1, "denominator": 10},
    )


def test_c08_individual_decision_changes_are_retained(evidence):
    changes = evidence["decision_changes"]["changes"]
    assert [(item["before_state"], item["after_state"]) for item in changes] == [
        ("PASS", "FAIL"),
        ("Alpha > Beta", "Beta > Alpha"),
        ("PROHIBITED_APPARENT_DECLINE_-3/40", "VALID_RESTATED_IMPROVEMENT_1/10"),
    ]
    assert evidence["decision_changes"]["impact_index"]["decision_change_ids"] == [
        item["change_id"] for item in changes
    ]


def test_c11_migration_plan_is_exact_and_rule_traced(evidence):
    plan = evidence["migration_plan"]
    assert plan["recommendation"] == "PARTIAL_RESTATEMENT"
    assert plan["human_approval_state"] == "PENDING"
    assert [
        (item["action_type"], item["scope_start"], item["scope_end"]) for item in plan["actions"]
    ] == [
        ("RESTATE_COHORT_RANGE", "2026-05", "2026-06"),
        ("DUAL_REPORT_COHORT_RANGE", "2026-05", "2026-06"),
        ("START_OFFICIAL_SERIES", "2026-06", "2026-06"),
        ("MARK_NON_COMPARABLE", "2026-04", "2026-04"),
    ]
    assert [item["sequence"] for item in plan["rule_trace"]] == [1, 2, 3, 4]
    assert all(item["evidence_ids"] and item["policy_rule_ids"] for item in plan["actions"])


def test_c10_g3_actual_context_difference_refuses(evidence):
    g3 = evidence["controls"]["g3"]
    differences = g3["arm_difference"]["non_metric_context_differences"]
    assert len(differences) == 1
    assert differences[0]["field"] == "source_snapshot_hash"
    assert g3["definition_diff"] == evidence["definition_diff"]
    assert g3["comparison"]["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert g3["comparison"]["reason_codes"] == ["CONTROLLED_CONTEXT_MISMATCH"]
    assert [item["action_type"] for item in g3["plan"]["actions"]] == ["REJECT_PENDING_EVIDENCE"]


def test_changed_threshold_is_a_nonmetric_context_mismatch(
    definitions, decision_contract, records, coverage
):
    common = {
        "source_snapshot": {"records": [item.model_dump(mode="json") for item in records]},
        "source_schema_linkage_completeness": {
            "coverage": [item.model_dump(mode="json") for item in coverage]
        },
        "cutoff": decision_contract.cutoff,
        "timezone": decision_contract.timezone,
        "grouping": {"grain": "signup_month_channel"},
    }
    left = build_arm(
        arm_id="LEFT",
        definition=definitions["v1"],
        decision_contract=decision_contract,
        **common,
    )
    changed_contract = decision_contract.model_copy(
        update={"threshold": ExactValue(numerator=3, denominator=4)}
    )
    right = build_arm(
        arm_id="RIGHT",
        definition=definitions["v2"],
        decision_contract=changed_contract,
        **common,
    )
    analysis = analyze_arm_difference(
        left,
        right,
        definition_diff(definitions["v1"], definitions["v2"]),
        analysis_id="THRESHOLD-MISMATCH",
    )
    assert analysis.controlled_context_match is False
    assert [item.field for item in analysis.non_metric_context_differences] == [
        "decision_contract_hash"
    ]


def test_c13_recommendation_does_not_mutate_observed_facts(evidence):
    assert "recommendation" not in evidence["horizon_coverage"]
    assert "human_approval_state" not in evidence["calculations"]["golden"][0]


def test_c20_engine_plan_cannot_self_approve(evidence):
    assert evidence["migration_plan"]["human_approval_state"] == "PENDING"
    assert "approver" not in evidence["migration_plan"]


def test_all_g1_to_g4_controls_pass(evidence):
    assert {item["control_id"]: item["status"] for item in evidence["controls"]["results"]} == {
        "G1": "PASS",
        "G2": "PASS",
        "G3": "PASS",
        "G4": "PASS",
    }

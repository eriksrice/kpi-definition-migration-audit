from __future__ import annotations

import json
import subprocess
from fractions import Fraction

import pytest
from conftest import FIXTURES, ROOT

from kpi_definition_change_trial.demo import (
    format_percent,
    format_percentage_points,
    load_demo_evidence,
    render_evidence_card,
    render_terminal,
    validate_canonical_match,
)
from kpi_definition_change_trial.runner import execute

GOLDEN = ROOT / "artifacts/golden"
SCHEMAS = ROOT / "schemas"


def _load(name):
    return json.loads((GOLDEN / name).read_text(encoding="utf-8"))


def _fraction(value):
    return Fraction(value["numerator"], value["denominator"])


def test_d01_fresh_demo_evidence_matches_accepted_canonical_bytes(tmp_path):
    generated_evidence = tmp_path / "artifacts/golden"
    generated_schemas = tmp_path / "schemas"
    execute(FIXTURES, generated_evidence, generated_schemas)
    validate_canonical_match(generated_evidence, GOLDEN, generated_schemas, SCHEMAS)


def test_d02_demo_validation_fails_closed_on_canonical_difference(tmp_path):
    generated_evidence = tmp_path / "artifacts/golden"
    generated_schemas = tmp_path / "schemas"
    execute(FIXTURES, generated_evidence, generated_schemas)
    calculations = generated_evidence / "calculations.json"
    calculations.write_bytes(calculations.read_bytes() + b" ")
    with pytest.raises(ValueError, match=r"evidence/calculations\.json"):
        validate_canonical_match(generated_evidence, GOLDEN, generated_schemas, SCHEMAS)


def test_d03_displayed_kpi_values_match_calculations():
    view = load_demo_evidence(GOLDEN)
    calculations = _load("calculations.json")["golden"]
    selected = {
        item["definition_ref"]: item
        for item in calculations
        if item["cohort"] == view.cohort and item["channel"] == view.channel
    }
    before = selected[view.before_definition_ref]
    after = selected[view.after_definition_ref]
    assert (view.before_numerator, view.before_denominator_count, view.before_value) == (
        before["numerator_count"],
        before["denominator_count"],
        _fraction(before["exact_value"]),
    )
    assert (view.after_numerator, view.after_denominator_count, view.after_value) == (
        after["numerator_count"],
        after["denominator_count"],
        _fraction(after["exact_value"]),
    )


def test_d04_displayed_trends_and_validity_match_comparisons():
    view = load_demo_evidence(GOLDEN)
    comparisons = {item["kind"]: item for item in _load("comparisons.json")}
    stitch = comparisons["TREND_STITCH"]
    restated = comparisons["RESTATED_TREND"]
    assert (view.stitch_delta, view.stitch_valid, view.stitch_verdict) == (
        _fraction(stitch["exact_delta"]),
        stitch["valid"],
        stitch["verdict"],
    )
    assert (view.restated_delta, view.restated_valid, view.restated_verdict) == (
        _fraction(restated["exact_delta"]),
        restated["valid"],
        restated["verdict"],
    )


def test_d05_displayed_decisions_match_decision_changes():
    view = load_demo_evidence(GOLDEN)
    changes = {item["change_type"]: item for item in _load("decision_changes.json")["changes"]}
    assert (view.threshold_before, view.threshold_after) == (
        changes["THRESHOLD"]["before_state"],
        changes["THRESHOLD"]["after_state"],
    )
    assert (view.rank_before, view.rank_after) == (
        changes["RANKING"]["before_state"],
        changes["RANKING"]["after_state"],
    )


def test_d06_displayed_actions_match_migration_plan():
    view = load_demo_evidence(GOLDEN)
    plan = _load("migration_plan.json")
    assert view.recommendation == plan["recommendation"]
    assert view.human_approval_state == plan["human_approval_state"]
    assert tuple(item.action_type for item in view.actions) == tuple(
        item["action_type"] for item in plan["actions"]
    )
    assert tuple(item.sequence for item in view.actions) == tuple(
        item["sequence"] for item in plan["actions"]
    )


def test_d07_displayed_g3_refusal_matches_controls():
    view = load_demo_evidence(GOLDEN)
    g3 = _load("controls.json")["g3"]
    assert view.confound_context_match == g3["arm_difference"]["controlled_context_match"]
    assert view.confound_attribution_valid == g3["arm_difference"]["attribution_valid"]
    assert view.confound_comparison_valid == g3["comparison"]["valid"]
    assert view.confound_verdict == g3["comparison"]["verdict"]
    assert view.confound_recommendation == g3["plan"]["recommendation"]


def test_d08_terminal_and_card_project_the_same_machine_records():
    view = load_demo_evidence(GOLDEN)
    terminal = render_terminal(view)
    card = render_evidence_card(view)
    shared_projections = (
        format_percent(view.before_value),
        format_percent(view.after_value),
        format_percentage_points(view.stitch_delta),
        format_percentage_points(view.restated_delta),
        view.threshold_before,
        view.threshold_after,
        view.rank_before,
        view.rank_after,
        view.recommendation,
        view.confound_verdict,
        view.confound_recommendation,
        *(action.label for action in view.actions),
    )
    assert all(value in terminal and value in card for value in shared_projections)


def test_d09_checked_in_evidence_card_is_an_exact_projection():
    expected = render_evidence_card(load_demo_evidence(GOLDEN))
    actual = (ROOT / "artifacts/demo/evidence_card.md").read_text(encoding="utf-8")
    assert actual == expected


def test_d10_run_demo_executes_the_verified_projection():
    completed = subprocess.run(
        ["./scripts/run_demo"],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == render_terminal(load_demo_evidence(GOLDEN))
    assert completed.stderr == ""


def test_d11_renderer_contains_no_frozen_calculated_outcomes():
    source = (ROOT / "src/kpi_definition_change_trial/demo.py").read_text(encoding="utf-8")
    for frozen_outcome in ("87.5%", "70.0%", "-7.5", "+10.0", "PASS -> FAIL"):
        assert frozen_outcome not in source

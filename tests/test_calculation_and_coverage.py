from __future__ import annotations

import pytest
from pydantic import ValidationError

from kpi_definition_change_trial.calculation import (
    calculate_metric,
)
from kpi_definition_change_trial.models import AccountRecord, CoverageDeclaration, MetricResult


def _index(evidence):
    return {item["result_id"]: item for item in evidence["calculations"]["golden"]}


def test_c05_g1_exact_record_level_oracle(evidence):
    results = _index(evidence)
    expected = {
        "RESULT-2026-04-ALPHA-V1_0_0": (6, 7, (6, 7)),
        "RESULT-2026-04-BETA-V1_0_0": (7, 9, (7, 9)),
        "RESULT-2026-05-ALPHA-V1_0_0": (7, 8, (7, 8)),
        "RESULT-2026-05-BETA-V1_0_0": (8, 10, (4, 5)),
        "RESULT-2026-06-ALPHA-V1_0_0": (8, 9, (8, 9)),
        "RESULT-2026-06-BETA-V1_0_0": (8, 10, (4, 5)),
        "RESULT-2026-05-ALPHA-V2_0_0": (7, 10, (7, 10)),
        "RESULT-2026-05-BETA-V2_0_0": (8, 10, (4, 5)),
        "RESULT-2026-06-ALPHA-V2_0_0": (8, 10, (4, 5)),
        "RESULT-2026-06-BETA-V2_0_0": (8, 10, (4, 5)),
    }
    for result_id, (numerator, denominator, ratio) in expected.items():
        result = results[result_id]
        assert result["status"] == "EXACT"
        assert (result["numerator_count"], result["denominator_count"]) == (
            numerator,
            denominator,
        )
        assert (result["exact_value"]["numerator"], result["exact_value"]["denominator"]) == ratio


def test_c06_april_v1_membership_is_explicit(evidence):
    results = _index(evidence)
    alpha = results["RESULT-2026-04-ALPHA-V1_0_0"]
    beta = results["RESULT-2026-04-BETA-V1_0_0"]
    assert len(alpha["membership"]["denominator_record_ids"]) == 7
    assert len(beta["membership"]["denominator_record_ids"]) == 9
    assert all(item.startswith("APR-") for item in alpha["membership"]["denominator_record_ids"])


def test_c07_april_v2_has_no_number(evidence):
    for channel in ("ALPHA", "BETA"):
        result = _index(evidence)[f"RESULT-2026-04-{channel}-V2_0_0"]
        assert result["status"] == "NOT_COMPUTABLE"
        assert result["exact_value"] is None
        assert result["numerator_count"] is None
        assert result["denominator_count"] is None


def test_c07_may_june_v2_are_fully_reconstructable(evidence):
    records = {
        item["cohort"]: item
        for item in evidence["cohort_reconstructability"]
        if item["definition_ref"].endswith("/2.0.0")
    }
    assert records["2026-04"]["status"] == "NOT_RECONSTRUCTABLE"
    assert records["2026-05"]["status"] == "FULLY_RECONSTRUCTABLE"
    assert records["2026-06"]["status"] == "FULLY_RECONSTRUCTABLE"


@pytest.mark.parametrize(
    ("field", "status"),
    [
        ("partial", "AVAILABLE_PARTIAL"),
        ("unavailable", "UNAVAILABLE_NOT_RETAINED"),
        ("unknown", "UNKNOWN"),
    ],
)
def test_c15_incomplete_population_never_yields_number(
    field, status, definitions, records, decision_contract
):
    declaration = CoverageDeclaration(
        cohort="2026-05",
        complete=tuple(
            item
            for item in definitions["v2"].dependency_projection.dependencies
            if item != "population.authoritative_signup_roster"
        ),
        **{field: ("population.authoritative_signup_roster",)},
    )
    result = calculate_metric(
        definitions["v2"], records, declaration, "2026-05", "Alpha", decision_contract.cutoff
    )
    assert result.status == "NOT_COMPUTABLE"
    assert result.exact_value is None
    assert any(status in reason for reason in result.reason_codes)


def test_membership_retains_exclusion_reasons(evidence):
    result = _index(evidence)["RESULT-2026-05-ALPHA-V2_0_0"]
    exclusions = {
        item["account_id"]: item["reason_codes"]
        for item in result["membership"]["excluded_records"]
    }
    assert exclusions["MAY-A-XTEST"] == ["EXCLUDED_ACCOUNT_CLASS"]
    assert exclusions["MAY-A-XINTERNAL"] == ["EXCLUDED_ACCOUNT_CLASS"]
    assert exclusions["MAY-A-XINELIGIBLE"] == ["INELIGIBLE_AT_SIGNUP"]


def test_maturity_and_cutoff_exclude_late_record(definitions, records, coverage, decision_contract):
    late = AccountRecord(
        **{
            **records[16].model_dump(),
            "account_id": "JUN-A-LATE-MATURITY",
            "cohort": "2026-06",
            "channel": "Alpha",
            "signup_at": "2026-07-10T00:00:00Z",
            "activity_at": None,
            "activity_received_at": None,
            "core_action_at": None,
            "core_action_received_at": None,
            "provenance_id": "SRC-JUN-SIGNUP-ROSTER",
        }
    )
    june = next(item for item in coverage if item.cohort == "2026-06")
    result = calculate_metric(
        definitions["v2"], (*records, late), june, "2026-06", "Alpha", decision_contract.cutoff
    )
    excluded = next(
        item for item in result.membership.excluded_records if item.account_id == late.account_id
    )
    assert "NOT_MATURE_AT_CUTOFF" in excluded.reason_codes


def test_noncomputable_model_rejects_numeric_leakage():
    with pytest.raises(ValidationError, match="cannot contain"):
        MetricResult(
            result_id="X",
            definition_ref="D",
            cohort="2026-04",
            channel="Alpha",
            status="NOT_COMPUTABLE",
            numerator_count=0,
            denominator_count=1,
            exact_value=None,
            membership=None,
            reason_codes=("UNKNOWN",),
            source_evidence_ids=("E",),
        )


def test_c17_cohort_and_horizon_coverage_are_separate_types(evidence):
    assert evidence["horizon_coverage"]["status"] == "PARTIAL"
    assert evidence["horizon_coverage"]["fully_reconstructable_cohorts"] == [
        "2026-05",
        "2026-06",
    ]
    assert all(
        "fully_reconstructable_cohorts" not in item
        for item in evidence["cohort_reconstructability"]
    )

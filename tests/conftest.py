from __future__ import annotations

import json
from pathlib import Path

import pytest

from kpi_definition_change_trial.models import (
    AccountRecord,
    CoverageDeclaration,
    DecisionContract,
    MetricDefinition,
)
from kpi_definition_change_trial.runner import build_evidence

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"


def load_json(relative: str):
    return json.loads((FIXTURES / relative).read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def evidence():
    return build_evidence(FIXTURES)


@pytest.fixture(scope="session")
def definitions():
    return {
        name: MetricDefinition.model_validate(load_json(f"definitions/{filename}"))
        for name, filename in {
            "v1": "v1.json",
            "v2": "v2.json",
            "v101": "v1_0_1.json",
        }.items()
    }


@pytest.fixture(scope="session")
def records():
    return tuple(
        AccountRecord.model_validate(item) for item in load_json("sources/account_records.json")
    )


@pytest.fixture(scope="session")
def coverage():
    return tuple(
        CoverageDeclaration.model_validate(item) for item in load_json("sources/coverage.json")
    )


@pytest.fixture(scope="session")
def decision_contract():
    return DecisionContract.model_validate(load_json("contracts/decision.json"))

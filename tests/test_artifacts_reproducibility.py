from __future__ import annotations

import ast
import json
import shutil
from pathlib import Path

from conftest import FIXTURES, ROOT

from kpi_definition_change_trial.canonical import canonical_json_bytes
from kpi_definition_change_trial.runner import build_evidence, execute, write_schemas


def _files(path: Path) -> dict[str, bytes]:
    return {
        item.relative_to(path).as_posix(): item.read_bytes()
        for item in sorted(path.rglob("*"))
        if item.is_file()
    }


def test_deterministic_json_schemas_are_checked_in(tmp_path):
    generated = tmp_path / "schemas"
    write_schemas(generated)
    assert _files(generated) == _files(ROOT / "schemas")
    assert len(_files(generated)) >= 20


def test_c12_same_input_complete_bundle_is_byte_identical(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    execute(FIXTURES, first / "artifacts", first / "schemas")
    execute(FIXTURES, second / "artifacts", second / "schemas")
    assert _files(first) == _files(second)


def test_c03_g2_semantic_projections_match_but_full_artifacts_do_not(evidence):
    identities = evidence["identities"]
    assert identities["v1"]["artifact_hash"] != identities["v1_0_1"]["artifact_hash"]
    assert identities["v1"]["semantic_hash"] == identities["v1_0_1"]["semantic_hash"]
    g2 = evidence["controls"]["g2"]
    assert g2["v1_semantic_result_projection"] == g2["v1_0_1_semantic_result_projection"]
    assert g2["v1_semantic_decision_projection"] == g2["v1_0_1_semantic_decision_projection"]


def test_c19_expected_labels_are_not_read(tmp_path):
    fixture_copy = tmp_path / "fixtures"
    shutil.copytree(FIXTURES, fixture_copy)
    baseline = canonical_json_bytes(build_evidence(fixture_copy))
    label_file = fixture_copy / "expected_labels.json"
    label_file.write_text('{"verdict":"WRONG","confound":false,"plan":"WRONG"}\n')
    mutated = canonical_json_bytes(build_evidence(fixture_copy))
    assert mutated == baseline


def test_c21_report_is_checked_machine_projection(evidence):
    report = (ROOT / "artifacts/golden/report.md").read_text(encoding="utf-8")
    assert evidence["identities"]["v1"]["artifact_hash"] in report
    assert evidence["identities"]["v2"]["semantic_hash"] in report
    assert "UNAVAILABLE_NOT_RETAINED:population.authoritative_signup_roster" in report
    for comparison in evidence["comparisons"]:
        assert comparison["assessment_id"] in report
    for action in evidence["migration_plan"]["actions"]:
        assert action["action_type"] in report


def test_manifest_hashes_every_generated_artifact():
    output = ROOT / "artifacts/golden"
    manifest = json.loads((output / "bundle_manifest.json").read_text())
    expected_files = {item.name for item in output.iterdir() if item.name != "bundle_manifest.json"}
    assert set(manifest["artifacts"]) == expected_files


def test_c14_no_network_llm_database_or_dataframe_imports():
    prohibited = {
        "anthropic",
        "duckdb",
        "httpx",
        "langchain",
        "litellm",
        "numpy",
        "openai",
        "pandas",
        "requests",
        "sqlalchemy",
    }
    imported: set[str] = set()
    for path in (ROOT / "src").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
    assert not imported.intersection(prohibited)


def test_all_canonical_outputs_end_with_lf():
    for path in [*(ROOT / "artifacts/golden").glob("*.json"), *(ROOT / "schemas").glob("*.json")]:
        assert path.read_bytes().endswith(b"\n")

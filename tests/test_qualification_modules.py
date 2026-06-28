import json
import tempfile
import unittest
from pathlib import Path

from scripts import qualification_case, qualification_result


def make_case(root, name="behavior-change"):
    case_dir = Path(root) / "qualification" / "cases" / name
    case_dir.mkdir(parents=True)
    (case_dir / "task.md").write_text("task\n", encoding="utf-8")
    (case_dir / "allowed-paths.txt").write_text("app/target.py\n", encoding="utf-8")
    (case_dir / "accept.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    return case_dir


def complete_result(case="behavior-change", revision="rev-1"):
    return {
        "status": "PASSED",
        "adapter": "qualification-simulated-agent",
        "case": case,
        "run_id": f"run-{case}",
        "patch_sha256": f"patch-{case}",
        "case_spec": {
            "task": {"path": f"qualification/cases/{case}/task.md", "sha256": f"task-{case}"},
            "allowed_paths": {
                "path": f"qualification/cases/{case}/allowed-paths.txt",
                "sha256": f"scope-{case}",
            },
            "acceptance": {
                "path": f"qualification/cases/{case}/accept.sh",
                "sha256": f"acceptance-{case}",
            },
        },
        "scope": "PASSED",
        "acceptance": "PASSED",
        "run_validation": "PASSED",
        "patch_verification": "PASSED",
        "adapter_configuration": {
            "adapter_script": "agents/qualification-simulated-agent.sh",
            "adapter_script_revision": revision,
            "cli_command": "python",
            "cli_path": "/fixture/python",
            "cli_version": "Python 3",
            "selected_model": "fixture-model",
            "relevant_configuration": {"protocol": "fixture-v1"},
        },
    }


class QualificationModuleTests(unittest.TestCase):
    def test_case_module_loads_layout_and_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_case(tmp)

            case = qualification_case.load_case(tmp, "behavior-change")
            allowed_paths = case.allowed_paths
            case_spec = case.case_spec

        self.assertEqual(case.task_repo_path, "qualification/cases/behavior-change/task.md")
        self.assertEqual(allowed_paths, ["app/target.py"])
        self.assertEqual(set(case_spec), {"task", "allowed_paths", "acceptance"})
        self.assertTrue(case_spec["task"]["sha256"])

    def test_case_module_preserves_missing_allowed_paths_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            case_dir = make_case(tmp)
            (case_dir / "allowed-paths.txt").unlink()

            with self.assertRaises(qualification_case.QualificationCaseError) as caught:
                qualification_case.load_case(tmp, "behavior-change")

        self.assertEqual(caught.exception.reason, "missing_qualification_allowed_paths")

    def test_result_writer_uses_case_module_for_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            make_case(tmp)
            run_dir = Path(tmp) / "runs" / "run-1"
            run_dir.mkdir(parents=True)
            record = {
                "run_id": "run-1",
                "base_sha": "abc123",
                "patch_sha256": "patch-hash",
                "cli_command": "python",
                "cli_path": "/fixture/python",
                "cli_version": "Python 3",
            }
            record_path = run_dir / "record.json"
            record_path.write_text(json.dumps(record), encoding="utf-8")
            config_path = Path(tmp) / "agents" / "qualification-simulated-agent.qualification.json"
            config_path.parent.mkdir()
            config_path.write_text(
                json.dumps(
                    {
                        "selected_model": "fixture-model",
                        "relevant_configuration": {"protocol": "fixture-v1"},
                    }
                ),
                encoding="utf-8",
            )

            result = qualification_result.build_result(
                root=tmp,
                status="PASSED",
                stage="complete",
                failure_reason="",
                adapter="qualification-simulated-agent",
                case="behavior-change",
                record_path=record_path,
                adapter_script="agents/qualification-simulated-agent.sh",
                adapter_script_revision="rev-1",
                adapter_configuration_path=config_path,
                run_validation="PASSED",
                patch_verification="PASSED",
                scope="PASSED",
                acceptance="PASSED",
            )

        self.assertEqual(result["task_file"], "qualification/cases/behavior-change/task.md")
        self.assertEqual(result["allowed_paths"], ["app/target.py"])
        self.assertEqual(result["run_id"], "run-1")
        self.assertEqual(result["adapter_configuration"]["selected_model"], "fixture-model")
        self.assertTrue(result["case_spec"]["acceptance"]["sha256"])

    def test_result_completeness_and_identity_preserve_series_semantics(self):
        behavior = complete_result("behavior-change")
        new = complete_result("new-behavior")
        edge = complete_result("edge-case")

        outcome = qualification_result.evaluate([behavior, new, edge])

        self.assertEqual(outcome["status"], "QUALIFIED")
        self.assertIsNone(outcome["reason"])

    def test_series_resets_on_incomplete_unknown_duplicate_and_drift(self):
        behavior = complete_result("behavior-change")
        incomplete = complete_result("new-behavior")
        incomplete["case_spec"]["task"]["sha256"] = None
        self.assertEqual(
            qualification_result.evaluate([behavior, incomplete])["reason"],
            "incomplete_result",
        )

        unknown = complete_result("unknown-case")
        self.assertEqual(
            qualification_result.evaluate([behavior, unknown])["reason"],
            "unknown_case",
        )

        duplicate = complete_result("behavior-change")
        self.assertEqual(
            qualification_result.evaluate([behavior, duplicate])["reason"],
            "duplicate_case",
        )

        drift = complete_result("new-behavior", revision="rev-2")
        self.assertEqual(
            qualification_result.evaluate([behavior, drift])["reason"],
            "configuration_drift",
        )

    def test_identity_requires_relevant_configuration_dict(self):
        result = complete_result()
        result["adapter_configuration"]["relevant_configuration"] = "not-a-dict"

        self.assertIsNone(qualification_result.identity_for(result))


if __name__ == "__main__":
    unittest.main()

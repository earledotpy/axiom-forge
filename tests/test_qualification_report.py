import subprocess
import sys
import tempfile
import json
import unittest
from pathlib import Path

from scripts import qualification_report


def qualified_outcome(adapter="test-adapter", revision="rev-1"):
    """Minimal QUALIFIED outcome dict matching qualification_result.evaluate() shape."""
    pinned = {
        "adapter_script": "agents/test-adapter.sh",
        "adapter_script_revision": revision,
        "cli_command": "test-cli",
        "cli_path": "/fixture/test-cli",
        "cli_version": "test-cli 1.2.3",
        "selected_model": "fixture-model",
        "relevant_configuration": {"protocol": "fixture-v1"},
    }
    cases = ["behavior-change", "new-behavior", "edge-case"]
    qualifying_results = [
        {
            "run_id": f"run-{case}",
            "case": case,
            "patch_sha256": f"patchhash-{case}",
            "case_spec": {
                "task": {
                    "path": f"qualification/cases/{case}/task.md",
                    "sha256": f"taskhash-{case}",
                },
                "allowed_paths": {
                    "path": f"qualification/cases/{case}/allowed-paths.txt",
                    "sha256": f"allowhash-{case}",
                },
                "acceptance": {
                    "path": f"qualification/cases/{case}/accept.sh",
                    "sha256": f"accepthash-{case}",
                },
            },
            "scope": "PASS",
            "acceptance": "PASS",
        }
        for case in cases
    ]
    return {
        "schema_version": 1,
        "status": "QUALIFIED",
        "reason": None,
        "adapter": adapter,
        "pinned_configuration": pinned,
        "qualifying_results": qualifying_results,
        "resets": [],
    }


def not_qualified_outcome():
    return {
        "schema_version": 1,
        "status": "NOT_QUALIFIED",
        "reason": "series_incomplete",
        "adapter": None,
        "pinned_configuration": None,
        "qualifying_results": [],
        "resets": [],
    }


class RenderQualificationSnippetTests(unittest.TestCase):
    def setUp(self):
        self.outcome = qualified_outcome()
        self.snippet = qualification_report.render_qualification_snippet(self.outcome)

    def test_snippet_contains_adapter_name(self):
        self.assertIn("test-adapter", self.snippet)

    def test_snippet_contains_all_run_ids(self):
        for case in ["behavior-change", "new-behavior", "edge-case"]:
            self.assertIn(f"run-{case}", self.snippet)

    def test_snippet_contains_case_spec_paths_and_hashes(self):
        for case in ["behavior-change", "new-behavior", "edge-case"]:
            self.assertIn(f"qualification/cases/{case}/task.md", self.snippet)
            self.assertIn(f"taskhash-{case}", self.snippet)
            self.assertIn(f"allowhash-{case}", self.snippet)
            self.assertIn(f"accepthash-{case}", self.snippet)

    def test_snippet_contains_patch_sha256_values(self):
        for case in ["behavior-change", "new-behavior", "edge-case"]:
            self.assertIn(f"patchhash-{case}", self.snippet)

    def test_snippet_contains_scope_and_acceptance_status(self):
        self.assertGreaterEqual(self.snippet.count("PASS"), 6)

    def test_snippet_contains_pinned_configuration_fields(self):
        self.assertIn("test-cli", self.snippet)
        self.assertIn("/fixture/test-cli", self.snippet)
        self.assertIn("test-cli 1.2.3", self.snippet)
        self.assertIn("fixture-model", self.snippet)
        self.assertIn("agents/test-adapter.sh", self.snippet)
        self.assertIn("rev-1", self.snippet)

    def test_render_raises_for_not_qualified_outcome(self):
        with self.assertRaises(ValueError) as caught:
            qualification_report.render_qualification_snippet(not_qualified_outcome())
        self.assertIn("not_qualified", str(caught.exception))

    def test_snippet_does_not_mutate_committed_docs(self):
        # The function is pure — it returns a string, not a path, and
        # the string must not reference adapter-evidence.md by path.
        self.assertNotIn("adapter-evidence.md", self.snippet)


class QualificationReportCLITests(unittest.TestCase):
    def test_cli_prints_snippet_to_stdout_from_result_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter = "test-adapter"
            cases = ["behavior-change", "new-behavior", "edge-case"]
            results_dir = Path(tmp) / "qualification" / "results" / adapter
            results_dir.mkdir(parents=True)

            for i, case in enumerate(cases, 1):
                result_path = results_dir / f"{i:04d}-{case}.json"
                result_path.write_text(
                    json.dumps(
                        {
                            "schema_version": 1,
                            "status": "PASSED",
                            "stage": "complete",
                            "failure_reason": None,
                            "adapter": adapter,
                            "case": case,
                            "run_id": f"run-{case}",
                            "base_sha": "abc123",
                            "patch_sha256": f"patchhash-{case}",
                            "case_spec": {
                                "task": {
                                    "path": f"qualification/cases/{case}/task.md",
                                    "sha256": f"taskhash-{case}",
                                },
                                "allowed_paths": {
                                    "path": f"qualification/cases/{case}/allowed-paths.txt",
                                    "sha256": f"allowhash-{case}",
                                },
                                "acceptance": {
                                    "path": f"qualification/cases/{case}/accept.sh",
                                    "sha256": f"accepthash-{case}",
                                },
                            },
                            "run_validation": "PASSED",
                            "patch_verification": "PASSED",
                            "scope": "PASSED",
                            "acceptance": "PASSED",
                            "adapter_configuration": {
                                "adapter_script": "agents/test-adapter.sh",
                                "adapter_script_revision": "rev-1",
                                "cli_command": "test-cli",
                                "cli_path": "/fixture/test-cli",
                                "cli_version": "test-cli 1.2.3",
                                "selected_model": "fixture-model",
                                "relevant_configuration": {"protocol": "fixture-v1"},
                            },
                            "task_file": f"qualification/cases/{case}/task.md",
                            "allowed_paths": ["app/target.py"],
                        }
                    ),
                    encoding="utf-8",
                )

            # Initialize a git repo and commit the results so check_results_clean passes
            subprocess.run(["git", "init", tmp], check=True, capture_output=True)
            subprocess.run(["git", "-C", tmp, "add", "."], check=True, capture_output=True)
            subprocess.run(
                [
                    "git", "-C", tmp,
                    "-c", "user.email=test@test.com",
                    "-c", "user.name=Test",
                    "commit", "-m", "test results",
                ],
                check=True,
                capture_output=True,
            )

            proc = subprocess.run(
                [
                    sys.executable, "scripts/qualification_report.py",
                    "--adapter", adapter,
                    "--root", tmp,
                ],
                capture_output=True,
                text=True,
                cwd=str(Path(__file__).parent.parent),
            )

        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        self.assertIn("test-adapter", proc.stdout)
        self.assertIn("run-behavior-change", proc.stdout)
        self.assertIn("patchhash-new-behavior", proc.stdout)


def result_file(adapter, case, *, run_validation="PASSED", patch_verification="PASSED",
                 acceptance="PASSED", status="PASSED", identity=True):
    adapter_configuration = {
        "adapter_script": f"agents/{adapter}.sh",
        "adapter_script_revision": "rev-1",
        "cli_command": "test-cli",
        "cli_path": "/fixture/test-cli",
        "cli_version": "test-cli 1.2.3",
        "selected_model": "fixture-model" if identity else None,
        "relevant_configuration": {"protocol": "fixture-v1"},
    }
    return {
        "schema_version": 1,
        "status": status,
        "stage": "complete",
        "failure_reason": None,
        "adapter": adapter,
        "case": case,
        "run_id": f"run-{case}",
        "base_sha": "abc123",
        "patch_sha256": f"patchhash-{case}",
        "case_spec": {
            "task": {"path": f"qualification/cases/{case}/task.md", "sha256": f"taskhash-{case}"},
            "allowed_paths": {
                "path": f"qualification/cases/{case}/allowed-paths.txt",
                "sha256": f"allowhash-{case}",
            },
            "acceptance": {
                "path": f"qualification/cases/{case}/accept.sh",
                "sha256": f"accepthash-{case}",
            },
        },
        "run_validation": run_validation,
        "patch_verification": patch_verification,
        "scope": "PASSED",
        "acceptance": acceptance,
        "adapter_configuration": adapter_configuration,
        "task_file": f"qualification/cases/{case}/task.md",
        "allowed_paths": ["app/target.py"],
    }


def init_committed_results(tmp, adapter, results):
    results_dir = Path(tmp) / "qualification" / "results" / adapter
    results_dir.mkdir(parents=True)
    for i, result in enumerate(results, 1):
        (results_dir / f"{i:04d}-{result['case']}.json").write_text(
            json.dumps(result), encoding="utf-8"
        )
    subprocess.run(["git", "init", tmp], check=True, capture_output=True)
    subprocess.run(["git", "-C", tmp, "add", "."], check=True, capture_output=True)
    subprocess.run(
        [
            "git", "-C", tmp,
            "-c", "user.email=test@test.com",
            "-c", "user.name=Test",
            "commit", "-m", "test results",
        ],
        check=True,
        capture_output=True,
    )


class RenderEvidenceReuseSnippetTests(unittest.TestCase):
    def test_snippet_lists_source_and_both_evidence_axes(self):
        classification = {
            "adapter": "test-adapter",
            "standard_trust_status": "NOT_QUALIFIED",
            "standard_trust_reason": "series_incomplete",
            "items": [
                {
                    "run_id": "run-behavior-change",
                    "case": "behavior-change",
                    "compatibility_evidence": True,
                    "identity_status": "complete",
                    "failure_reason": None,
                    "source": "qualification/results/test-adapter/0001-behavior-change.json",
                    "standard_trust_contribution": True,
                },
                {
                    "run_id": "run-new-behavior",
                    "case": "new-behavior",
                    "compatibility_evidence": True,
                    "identity_status": "incomplete",
                    "failure_reason": "incomplete_result",
                    "source": "qualification/results/test-adapter/0002-new-behavior.json",
                    "standard_trust_contribution": False,
                },
            ],
        }

        snippet = qualification_report.render_evidence_reuse_snippet(classification)

        self.assertIn("test-adapter", snippet)
        self.assertIn("NOT_QUALIFIED", snippet)
        self.assertIn("series_incomplete", snippet)
        self.assertIn("qualification/results/test-adapter/0001-behavior-change.json", snippet)
        self.assertIn("qualification/results/test-adapter/0002-new-behavior.json", snippet)
        self.assertIn("run-behavior-change", snippet)
        self.assertIn("incomplete", snippet)


class EvidenceReuseCLITests(unittest.TestCase):
    def test_cli_reports_compatibility_evidence_for_result_that_failed_acceptance(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter = "test-adapter"
            failed_acceptance = result_file(adapter, "behavior-change", acceptance="FAILED", status="FAILED")
            init_committed_results(tmp, adapter, [failed_acceptance])

            proc = subprocess.run(
                [
                    sys.executable, "scripts/qualification_report.py",
                    "--adapter", adapter,
                    "--root", tmp,
                    "--evidence-reuse",
                ],
                capture_output=True,
                text=True,
                cwd=str(Path(__file__).parent.parent),
            )

        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        self.assertIn("run-behavior-change", proc.stdout)
        self.assertIn("qualification/results/test-adapter/0001-behavior-change.json", proc.stdout)
        self.assertIn("NOT_QUALIFIED", proc.stdout)

    def test_cli_evidence_reuse_requires_committed_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            adapter = "test-adapter"
            results_dir = Path(tmp) / "qualification" / "results" / adapter
            results_dir.mkdir(parents=True)
            (results_dir / "0001-behavior-change.json").write_text(
                json.dumps(result_file(adapter, "behavior-change")), encoding="utf-8"
            )
            subprocess.run(["git", "init", tmp], check=True, capture_output=True)

            proc = subprocess.run(
                [
                    sys.executable, "scripts/qualification_report.py",
                    "--adapter", adapter,
                    "--root", tmp,
                    "--evidence-reuse",
                ],
                capture_output=True,
                text=True,
                cwd=str(Path(__file__).parent.parent),
            )

        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("results_not_committed", proc.stderr)


if __name__ == "__main__":
    unittest.main()

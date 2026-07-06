import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts import delegation_artifact_set


class DelegationArtifactSetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write_task(self, name: str, scope: str | None, acceptance: str | None = "echo ok\n") -> Path:
        task = self.root / f"{name}.task.md"
        task.write_text(f"# {name}\n", encoding="utf-8")
        if scope is not None:
            (self.root / f"{name}.allowed-paths.txt").write_text(scope, encoding="utf-8")
        if acceptance is not None:
            (self.root / f"{name}.accept.sh").write_text(acceptance, encoding="utf-8")
        return task

    def test_derives_task_scope_and_acceptance_paths(self):
        task = self.root / "ready.task.md"

        self.assertEqual(
            delegation_artifact_set.scope_sidecar_path(task),
            self.root / "ready.allowed-paths.txt",
        )
        self.assertEqual(
            delegation_artifact_set.acceptance_check_path(task),
            self.root / "ready.accept.sh",
        )

    def test_invalid_task_file_has_stable_reason(self):
        with self.assertRaises(delegation_artifact_set.DelegationArtifactSetError) as caught:
            delegation_artifact_set.scope_sidecar_path(self.root / "ready.md")

        self.assertEqual(caught.exception.reason, "invalid_delegation_task_file")

    def test_missing_task_file_has_stable_reason(self):
        with self.assertRaises(delegation_artifact_set.DelegationArtifactSetError) as caught:
            delegation_artifact_set.load_task_artifact_set(self.root / "missing.task.md")

        self.assertEqual(caught.exception.reason, "missing_delegation_task_file")

    def test_task_without_scope_is_draft(self):
        task = self.write_task("draft", None)

        artifact_set = delegation_artifact_set.load_task_artifact_set(task)

        self.assertEqual(artifact_set.state, "draft")
        self.assertEqual(artifact_set.reason, "missing_delegation_scope_file")

    def test_task_without_acceptance_check_is_draft(self):
        task = self.write_task("draft", "app/target.py\n", acceptance=None)

        artifact_set = delegation_artifact_set.load_task_artifact_set(task)

        self.assertEqual(artifact_set.state, "draft")
        self.assertEqual(artifact_set.reason, "missing_delegation_acceptance_check")

    def test_empty_acceptance_check_is_draft(self):
        task = self.write_task("draft", "app/target.py\n", acceptance="\n")

        artifact_set = delegation_artifact_set.load_task_artifact_set(task)

        self.assertEqual(artifact_set.state, "draft")
        self.assertEqual(artifact_set.reason, "empty_delegation_acceptance_check")

    def test_invalid_scope_sidecar_has_stable_reason(self):
        task = self.write_task("bad-scope", "../outside.py\n")

        with self.assertRaises(delegation_artifact_set.DelegationArtifactSetError) as caught:
            delegation_artifact_set.load_task_artifact_set(task)

        self.assertEqual(caught.exception.reason, "target_scope_traversal")

    def test_invalid_scope_is_reported_before_missing_acceptance(self):
        task = self.write_task("bad-scope", "../outside.py\n", acceptance=None)

        with self.assertRaises(delegation_artifact_set.DelegationArtifactSetError) as caught:
            delegation_artifact_set.load_task_artifact_set(task)

        self.assertEqual(caught.exception.reason, "target_scope_traversal")

    def test_delegation_ready_task_includes_approved_paths(self):
        task = self.write_task("ready", "app/target.py\ntests/test_target.py\n")

        artifact_set = delegation_artifact_set.load_task_artifact_set(task)

        self.assertEqual(artifact_set.state, "delegation-ready")
        self.assertIsNone(artifact_set.reason)
        self.assertEqual(
            artifact_set.approved_paths,
            frozenset({"app/target.py", "tests/test_target.py"}),
        )


    def test_prepare_target_run_artifacts_copies_scope_and_records_evidence(self):
        task = self.write_task("ready", "app/target.py\n")
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.email", "test@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.name", "Axiom Test"], check=True)
        subprocess.run(["git", "-C", str(self.root), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.root), "commit", "-q", "-m", "artifact set"], check=True)
        revision = subprocess.check_output(["git", "-C", str(self.root), "rev-parse", "HEAD"], text=True).strip()
        run_dir = self.root / "runs" / "run-1"
        run_dir.mkdir(parents=True)

        result = delegation_artifact_set.prepare_target_run_artifacts(
            task_file=task,
            run_dir=run_dir,
            forge_root=self.root,
            delegation_artifact_revision=revision,
        )

        self.assertEqual(result["target_scope_file"], "allowed-paths.txt")
        self.assertEqual(result["delegation_artifact_revision"], revision)
        self.assertEqual(result["delegation_task_file"], "ready.task.md")
        self.assertEqual((run_dir / "allowed-paths.txt").read_text(encoding="utf-8"), "app/target.py\n")
        self.assertEqual(
            result["target_scope_sha256"],
            delegation_artifact_set._sha256_file(run_dir / "allowed-paths.txt"),
        )

    def test_prepare_target_run_artifacts_rejects_acceptance_inside_scope(self):
        task = self.write_task("bad", "app/target.py\nbad.accept.sh\n")

        with self.assertRaises(delegation_artifact_set.DelegationArtifactSetError) as caught:
            delegation_artifact_set.prepare_target_run_artifacts(
                task_file=task,
                run_dir=self.root,
                forge_root=self.root,
                delegation_artifact_revision="HEAD",
            )

        self.assertEqual(caught.exception.reason, "target_acceptance_check_in_scope")


if __name__ == "__main__":
    unittest.main()

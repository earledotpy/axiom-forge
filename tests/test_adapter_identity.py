import unittest

from scripts import adapter_identity


def record(**overrides):
    data = {
        "cli_command": "python",
        "cli_path": "/fixture/python",
        "cli_version": "Python 3",
    }
    data.update(overrides)
    return data


def configuration(**overrides):
    data = {
        "selected_model": "fixture-model",
        "relevant_configuration": {"protocol": "fixture-v1"},
    }
    data.update(overrides)
    return data


class AdapterIdentityTests(unittest.TestCase):
    def test_build_identity_evidence_captures_required_fields(self):
        identity = adapter_identity.build_identity_evidence(
            adapter_script="agents/example.sh",
            adapter_script_revision="rev-1",
            record=record(),
            adapter_configuration=configuration(),
        )

        self.assertEqual(identity["adapter_script"], "agents/example.sh")
        self.assertEqual(identity["adapter_script_revision"], "rev-1")
        self.assertEqual(identity["cli_command"], "python")
        self.assertEqual(identity["selected_model"], "fixture-model")
        self.assertEqual(identity["relevant_configuration"], {"protocol": "fixture-v1"})

    def test_missing_cli_provenance_fails_with_existing_reason(self):
        with self.assertRaises(adapter_identity.AdapterIdentityError) as caught:
            adapter_identity.require_cli_provenance(record(cli_version=""))

        self.assertEqual(caught.exception.reason, "cli_provenance_incomplete")

    def test_missing_adapter_configuration_fails_with_existing_reason(self):
        with self.assertRaises(adapter_identity.AdapterIdentityError) as caught:
            adapter_identity.require_adapter_configuration(
                configuration(relevant_configuration=None)
            )

        self.assertEqual(caught.exception.reason, "adapter_configuration_incomplete")

    def test_partial_identity_evidence_preserves_available_fields(self):
        identity = adapter_identity.build_partial_identity_evidence(
            adapter_script="agents/example.sh",
            adapter_script_revision="",
            record=record(cli_version=None),
            adapter_configuration={},
        )

        self.assertEqual(identity["adapter_script"], "agents/example.sh")
        self.assertEqual(identity["cli_command"], "python")
        self.assertIsNone(identity["adapter_script_revision"])
        self.assertIsNone(identity["cli_version"])
        self.assertIsNone(identity["selected_model"])

    def test_identity_for_requires_adapter_script_and_configuration_facts(self):
        identity = adapter_identity.build_identity_evidence(
            adapter_script="agents/example.sh",
            adapter_script_revision="rev-1",
            record=record(),
            adapter_configuration=configuration(),
        )

        self.assertEqual(adapter_identity.identity_for(identity), identity)

        identity["adapter_script_revision"] = None
        self.assertIsNone(adapter_identity.identity_for(identity))

    def test_configuration_drift_sensitive_fields_are_part_of_identity(self):
        first = adapter_identity.build_identity_evidence(
            adapter_script="agents/example.sh",
            adapter_script_revision="rev-1",
            record=record(),
            adapter_configuration=configuration(),
        )
        second = adapter_identity.build_identity_evidence(
            adapter_script="agents/example.sh",
            adapter_script_revision="rev-2",
            record=record(),
            adapter_configuration=configuration(),
        )

        self.assertNotEqual(adapter_identity.identity_for(first), adapter_identity.identity_for(second))


class CaptureCliProvenanceTests(unittest.TestCase):
    def test_capture_returns_exact_provenance_keys_for_found_command(self):
        provenance = adapter_identity.capture_cli_provenance("python")

        self.assertCountEqual(list(provenance.keys()), ["cli_command", "cli_path", "cli_version"])
        self.assertEqual(provenance["cli_command"], "python")
        self.assertIsInstance(provenance["cli_path"], str)
        self.assertTrue(provenance["cli_path"])

    def test_capture_raises_adapter_identity_error_for_missing_cli(self):
        with self.assertRaises(adapter_identity.AdapterIdentityError) as caught:
            adapter_identity.capture_cli_provenance("axiom-cli-that-does-not-exist")

        self.assertEqual(
            caught.exception.reason, "axiom-cli-that-does-not-exist_cli_not_found"
        )

    def test_capture_version_is_string_or_none(self):
        provenance = adapter_identity.capture_cli_provenance("python")

        self.assertIn(type(provenance["cli_version"]), (str, type(None)))

    def test_capture_result_satisfies_require_cli_provenance_when_version_present(self):
        provenance = adapter_identity.capture_cli_provenance("python")

        if provenance["cli_version"] is not None:
            validated = adapter_identity.require_cli_provenance(provenance)
            self.assertEqual(validated["cli_command"], "python")


if __name__ == "__main__":
    unittest.main()

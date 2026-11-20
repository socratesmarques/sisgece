"""Testes de guardas do ativador de feedback sem contato com Docker/produção."""
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
ACTIVATOR = ROOT / "deploy" / "ativar-avaliacoes-evolution.py"

spec = importlib.util.spec_from_file_location("ativacao_feedback", ACTIVATOR)
activation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(activation)


class FeedbackActivationTests(unittest.TestCase):
    def test_null_and_empty_hook(self):
        for payload in (None, {}, [], {"webhook": None}, {"webhook": {}}):
            with self.subTest(payload=payload):
                self.assertIsNone(activation.existing_webhook(payload))

    def test_disallow_multiple_hooks_and_unexpected_format(self):
        for payload in ([{}, {}], "text", {"webhook": ["other"]}):
            with self.subTest(payload=payload), self.assertRaises(RuntimeError):
                activation.existing_webhook(payload)

    def test_normalize_single_hook(self):
        hook = {"enabled": True, "url": "http://example"}
        self.assertEqual(activation.existing_webhook(hook), hook)
        self.assertEqual(activation.existing_webhook({"webhook": hook}), hook)
        self.assertEqual(activation.existing_webhook([hook]), hook)

    def test_webhook_matching_requires_auth_and_event(self):
        token = "test-" * 10
        hook = {
            "enabled": True,
            "url": activation.WEBHOOK_DESTINATION,
            "events": ["MESSAGES_UPSERT"],
            "byEvents": False,
            "headers": {"X-SISGECE-Evolution-Secret": token},
        }
        self.assertTrue(activation.webhook_matches(hook, token))
        for field, bad_value in (
            ("enabled", False),
            ("url", "http://other"),
            ("events", ["CONNECTION_UPDATE"]),
            ("byEvents", True),
            ("headers", {}),
        ):
            with self.subTest(field=field):
                invalid = dict(hook, **{field: bad_value})
                self.assertFalse(activation.webhook_matches(invalid, token))
        self.assertFalse(activation.webhook_matches(hook, "different"))

    def test_duplicate_env_variable_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            env = Path(directory) / "worker.env"
            env.write_text("A=1\nA=2\n")
            with self.assertRaises(RuntimeError):
                activation.load_env(env)
            env.write_text("#comment\nA=1\nB=2\n")
            self.assertEqual(activation.load_env(env), {"A": "1", "B": "2"})

    def test_feedback_compose_override(self):
        source = activation.feedback_override()
        self.assertIn("sisgece-feedback-net", source)
        self.assertIn("external: true", source)
        self.assertIn("  evolution:", source)
        self.assertIn("      - default", source)

    def test_check_never_calls_mutation(self):
        with patch.object(activation, "verify_settings") as check, \
             patch.object(activation, "enable") as apply, \
             patch("sys.argv", ["ativar", "--check"]):
            activation.main()
            check.assert_called_once_with()
            apply.assert_not_called()


if __name__ == "__main__":
    unittest.main()

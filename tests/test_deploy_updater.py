"""Regressões do atualizador Evolution sem acessar Docker nem produção."""

import re
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UPDATER = ROOT / "deploy" / "atualizar-sisgece-evolution.sh"


class DeployUpdaterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = UPDATER.read_text(encoding="utf-8")

    def test_shell_syntax(self):
        result = subprocess.run(["bash", "-n", str(UPDATER)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_all_compose_calls_supply_image(self):
        commands = [line.strip() for line in self.source.splitlines()
                    if "docker compose" in line and not line.lstrip().startswith("#")]
        self.assertGreaterEqual(len(commands), 5)
        for command in commands:
            with self.subTest(command=command):
                self.assertRegex(command,
                                 r'^SISGECE_IMAGE="\$(?:OLD_IMAGE|NEW_IMAGE)" docker compose\b')

    def test_stop_worker_uses_old_image_and_does_not_stop_when_inactive(self):
        start = self.source.index(
            'if [[ "$WORKER_RUNNING" == true ]]; then\n  (\n    cd "$EVO_DIR"\n'
        )
        end = self.source.index("\nfi", start) + len("\nfi")
        stop_block = self.source[start:end]
        prelude = r'''
set -euo pipefail
EVO_DIR="$1"
COMPOSE="$EVO_DIR/compose.worker.yaml"
OLD_IMAGE="sisgece:anterior"
PROJECT="evolution-sisgece"
WORKER_RUNNING="$2"
WORKER_STOPPED=false
docker() {
  [[ "${SISGECE_IMAGE:-}" == "$OLD_IMAGE" ]] || { echo "Imagem ausente" >&2; return 42; }
  [[ "$*" == "compose -p $PROJECT -f $COMPOSE stop sisgece-notifications" ]] || return 43
  echo "worker-parado"
}
'''
        for running in ("true", "false"):
            with self.subTest(worker_running=running), tempfile.TemporaryDirectory() as tmp:
                script = prelude + "\n" + stop_block + '\n[[ "$WORKER_STOPPED" == "$WORKER_RUNNING" ]]\n'
                result = subprocess.run(["bash", "-c", script, "test-updater", tmp, running],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(),
                                 "worker-parado" if running == "true" else "")


if __name__ == "__main__":
    unittest.main()

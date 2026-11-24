"""Regressões do atualizador Evolution sem acessar Docker nem produção."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UPDATER = ROOT / "deploy" / "atualizar-sisgece-evolution.sh"


DOCKER_RESTART_MOCK = r"""#!/usr/bin/env bash
set -eu
case "$1 $2" in
  'container inspect')
    case "$4" in
      '{{.Id}}') echo "$5-id" ;;
      '{{.State.Running}}')
        if [[ "$5" == sisgece-app-id || -f "$HOME/worker-started" ]]; then
          echo true
        else
          echo "${WORKER_ACTIVE:-false}"
        fi ;;
      *com.docker.compose.service*)
        [[ "$5" != evolution-id ]] || echo evolution ;;
      *) exit 98 ;;
    esac ;;
  'container ls')
    [[ "$*" == *'label=com.docker.compose.project=evolution-sisgece'* &&
       "$*" == *'label=com.docker.compose.oneoff=False'* ]] || exit 98
    printf '%s\n' redis-id pg-evolution-id evolution-sisgece-sisgece-notifications-1-id
    [[ "${MISSING_EVOLUTION:-0}" == 1 ]] || echo evolution-id ;;
  *)
    printf '%s\n' "$*" >> "$HOME/actions"
    [[ "$*" != "${FAIL_ACTION:-}" ]] || exit 42
    if [[ "$*" == 'restart evolution-sisgece-sisgece-notifications-1-id' ]]; then
      touch "$HOME/worker-started"
    fi ;;
esac
"""


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
            'if [[ "$WORKER_RUNNING" == true ]]; then\n  WORKER_CHANGED=true\n  (\n    cd "$EVO_DIR"\n'
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
WORKER_CHANGED=false
docker() {
  [[ "${SISGECE_IMAGE:-}" == "$OLD_IMAGE" ]] || { echo "Imagem ausente" >&2; return 42; }
  [[ "$*" == "compose -p $PROJECT -f $COMPOSE stop sisgece-notifications" ]] || return 43
  echo "worker-parado"
}
'''
        for running in ("true", "false"):
            with self.subTest(worker_running=running), tempfile.TemporaryDirectory() as tmp:
                script = prelude + "\n" + stop_block + '\n[[ "$WORKER_CHANGED" == "$WORKER_RUNNING" ]]\n'
                result = subprocess.run(["bash", "-c", script, "test-updater", tmp, running],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(),
                                 "worker-parado" if running == "true" else "")

    def test_apply_recovers_after_backup_or_worker_failure(self):
        for failure in ("backup", "worker"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as tmp:
                home = Path(tmp)
                repo = home / "repo"
                (repo / ".git").mkdir(parents=True)
                config = "PGHOST=sisgece-db\nPGPORT=5432\nPGDATABASE=local\nPGUSER=local\nPGPASSWORD=test\n"
                app = config + "NOTIFICATIONS_PROVIDER=evolution\nWHATSAPP_REAL_SEND_ENABLED=0\n"
                worker = config + (
                    "NOTIFICATIONS_PROVIDER=evolution\nWHATSAPP_REAL_SEND_ENABLED=1\n"
                    "EVOLUTION_LAB_ENABLED=1\nEVOLUTION_API_KEY=test\nEVOLUTION_INSTANCE=test\n"
                    "EVOLUTION_API_URL=http://evolution:8080\n"
                )
                (home / "sisgece-prod-evolution.env").write_text(app)
                (home / "worker.env").write_text(worker)
                (home / "compose.worker.yaml").touch()
                scripts = {
                    "git": """#!/usr/bin/env bash
case "$3" in
    branch) echo main ;;
    rev-parse) echo abc123 ;;
    pull|status) ;;
    *) exit 98 ;;
esac
""",
                    "curl": """#!/usr/bin/env bash
echo '{"ok":true}'
""",
                    "docker": r"""#!/usr/bin/env bash
set -eu
printf '%s %s\n' "${SISGECE_IMAGE:-}" "$*" >> "$HOME/actions"
case "$1 $2" in
    'container inspect')
        case "${4:-}" in
            '{{.HostConfig.NetworkMode}}') echo sisgece-net ;;
            '{{len .Mounts}}') echo 0 ;;
            '{{.Config.Image}}') echo sisgece:anterior ;;
            '{{.State.Running}}') echo true ;;
            *Config.Env*) cat "$HOME/sisgece-prod-evolution.env" ;;
        esac ;;
    'port sisgece-app') echo 127.0.0.1:18081 ;;
    'exec sisgece-db') echo 'test dump' ;;
    'exec -i')
        cat >/dev/null
        [[ "$FAILURE" != backup ]] || exit 42 ;;
    'exec sisgece-app') echo evolution ;;
    'compose -p')
        if [[ "$*" == *'up -d'* && "$SISGECE_IMAGE" == sisgece:prod-abc123 ]]; then
            [[ "$FAILURE" != worker ]] || exit 42
        fi ;;
    'build -t'|'stop sisgece-app'|'rename '*|'run -d'|'rm -f'|'start sisgece-app') ;;
    *) exit 98 ;;
esac
""",
                }
                for name, content in scripts.items():
                    file = home / name
                    file.write_text(content)
                    file.chmod(0o700)
                env = {
                    **os.environ, "HOME": tmp, "PATH": f"{tmp}:{os.environ['PATH']}",
                    "SISGECE_REPO": str(repo), "SISGECE_EVOLUTION_DIR": tmp, "FAILURE": failure,
                }
                result = subprocess.run(["bash", str(UPDATER), "--apply"], env=env,
                                        capture_output=True, text=True, timeout=10)
                actions = (home / "actions").read_text().splitlines()
                self.assertEqual(result.returncode, 42, result.stderr)
                self.assertEqual(result.stderr.count("Tentando restaurar"), 1)
                self.assertIn(" start sisgece-app", actions)
                self.assertTrue(any(line.startswith("sisgece:anterior compose ") and
                                    "up -d" in line for line in actions))
                self.assertEqual(" rm -f sisgece-app" in actions, failure == "worker")

    def run_restart(self, **settings):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            scripts = {
                "docker": DOCKER_RESTART_MOCK,
                "curl": """#!/usr/bin/env bash
echo ready >> "$HOME/actions"
echo '{"ok": true}'
""",
            }
            for name, content in scripts.items():
                file = home / name
                file.write_text(content)
                file.chmod(0o700)
            env = {**os.environ, "HOME": tmp, "PATH": f"{tmp}:{os.environ['PATH']}", **settings}
            result = subprocess.run(["bash", str(UPDATER), "--restart"], env=env,
                                    capture_output=True, text=True, timeout=10)
            log = home / "actions"
            return result, log.read_text().splitlines() if log.exists() else []

    def test_restart_starts_inactive_worker_after_app_readiness(self):
        result, actions = self.run_restart()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(actions, [
            "stop sisgece-app-id",
            "restart sisgece-db-id",
            "restart redis-id pg-evolution-id",
            "restart evolution-id",
            "restart sisgece-app-id",
            "ready",
            "restart evolution-sisgece-sisgece-notifications-1-id",
        ])

    def test_restart_checks_evolution_before_stopping_anything(self):
        result, actions = self.run_restart(MISSING_EVOLUTION="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Evolution não encontrado", result.stderr)
        self.assertEqual(actions, [])

    def test_restart_recovers_running_consumers_after_dependency_failure(self):
        result, actions = self.run_restart(WORKER_ACTIVE="true", FAIL_ACTION="restart sisgece-db-id")
        self.assertEqual(result.returncode, 42, result.stderr)
        self.assertEqual(actions, [
            "stop evolution-sisgece-sisgece-notifications-1-id",
            "stop sisgece-app-id",
            "restart sisgece-db-id",
            "start sisgece-app-id",
            "start evolution-sisgece-sisgece-notifications-1-id",
        ])


if __name__ == "__main__":
    unittest.main()

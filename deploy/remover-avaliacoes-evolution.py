#!/usr/bin/env python3
"""Remove a pesquisa Evolution no lsdserver sem desligar avisos de andamento.

Após integrar a PR na main:
  cd ~/sisgece && git pull --ff-only && python3 deploy/remover-avaliacoes-evolution.py --apply

Mantém o PostgreSQL e todos os dados históricos; não reinicia a Evolution.
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

HOME = Path.home()
EVO = HOME / "evolution-sisgece"
APP_ENV = EVO / "sisgece-prod-evolution.env"
WORKER_ENV = EVO / "worker.env"
UPDATER = HOME / "atualizar-sisgece.sh"
NEW_UPDATER = Path(__file__).resolve().parent / "atualizar-sisgece-evolution.sh"
WEBHOOK_URL = "http://sisgece-app:3000/api/notificacoes/evolution/avaliacao"
EVOLUTION_API = "http://127.0.0.1:18082"


def ensure(condition, message):
    if not condition:
        raise RuntimeError(message)


def env(path):
    values = {}
    for raw in path.read_text().splitlines():
        if raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def webhook_request(endpoint, key, data=None):
    headers = {"apikey": key}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = Request(
        endpoint,
        data=json.dumps(data).encode() if data is not None else None,
        headers=headers, method="POST" if data is not None else "GET",
    )
    with urlopen(req, timeout=12) as res:
        data = res.read(65537)
    ensure(len(data) <= 65536, "Resposta Evolution inválida.")
    return json.loads(data) if data else None


def find_webhook(instance, key):
    response = webhook_request(
        f"{EVOLUTION_API}/webhook/find/{quote(instance, safe='')}", key
    )
    if response in (None, [], {}):
        return None
    if isinstance(response, list):
        ensure(len(response) == 1, "Há múltiplos webhooks. Abortando.")
        response = response[0]
    ensure(isinstance(response, dict), "Formato inesperado de webhook.")
    response = response.get("webhook", response)
    ensure(response is None or isinstance(response, dict),
           "Formato inesperado de webhook.")
    return response or None


def exec_cmd(*args):
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL)


def clean_env(path):
    """Remove somente chaves exclusivas de avaliação; preserva a Evolution."""
    raw = path.read_text()
    revised = re.sub(r"(?m)^EVOLUTION_FEEDBACK_[A-Z_]+=[^\n]*\n?", "", raw)
    if revised != raw:
        path.write_text(revised)
        path.chmod(0o600)


def cleanup_network():
    # Só elimina overrides exatamente equivalentes aos criados para a pesquisa.
    expected = """services:
  evolution:
    networks:
      - default
      - feedback

networks:
  feedback:
    external: true
    name: sisgece-feedback-net
"""
    for filename in ("compose.override.yaml", "compose.feedback.yaml"):
        path = EVO / filename
        if path.is_file() and path.read_text().strip() == expected.strip():
            path.unlink()
    # Remover o isolamento extra nunca deve impedir avisos normais.
    for container in ("evolution-sisgece-evolution-1", "sisgece-app"):
        state = subprocess.run(
            ["docker", "network", "disconnect", "sisgece-feedback-net", container],
            capture_output=True,
        )
        if state.returncode:
            print(f"Rede extra não desconectada de {container}; não afeta avisos.")
    result = subprocess.run(
        ["docker", "network", "rm", "sisgece-feedback-net"], capture_output=True,
    )
    if result.returncode:
        print("Rede extra preservada (possível contêiner antigo de backup).")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="desativar webhook e implantar código sem avaliações")
    args = parser.parse_args()
    if not args.apply:
        parser.error("use --apply para executar a remoção")

    ensure(APP_ENV.is_file() and WORKER_ENV.is_file()
           and NEW_UPDATER.is_file(), "Arquivos da instalação não encontrados.")
    worker = env(WORKER_ENV)
    instance = worker.get("EVOLUTION_INSTANCE", "")
    key = worker.get("EVOLUTION_API_KEY", "")
    ensure(re.fullmatch(r"[A-Za-z0-9_-]{1,64}", instance or ""),
           "Instância Evolution inválida.")
    ensure(bool(key), "EVOLUTION_API_KEY ausente.")
    ensure(worker.get("WHATSAPP_REAL_SEND_ENABLED") == "1",
           "Envio normal do worker não está habilitado.")
    ensure(worker.get("NOTIFICATIONS_PROVIDER") == "evolution",
           "Worker não usa Evolution.")

    hook = find_webhook(instance, key)
    if hook:
        ensure(hook.get("url") == WEBHOOK_URL,
               "Outro webhook está configurado; não vou modificá-lo.")

    # Backup inclui credenciais: só o operador terá acesso.
    backup = HOME / "sisgece-backups" / (
        "remocao-avaliacoes-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    )
    backup.mkdir(parents=True, mode=0o700)
    backup.chmod(0o700)
    for path in (APP_ENV, WORKER_ENV, UPDATER):
        if path.is_file():
            shutil.copy2(path, backup / path.name)
    for name in ("compose.override.yaml", "compose.feedback.yaml"):
        path = EVO / name
        if path.is_file():
            shutil.copy2(path, backup / name)

    # Primeiro desliga o webhook; só após confirmação muda os envs.
    if hook and hook.get("enabled") is not False:
        headers = hook.get("headers")
        if not isinstance(headers, dict):
            headers = {}
        webhook_request(
            f"{EVOLUTION_API}/webhook/set/{quote(instance, safe='')}", key,
            {"webhook": {
                "enabled": False,
                "url": WEBHOOK_URL,
                "headers": headers,
                "byEvents": False,
                "base64": False,
                "events": ["MESSAGES_UPSERT"],
            }},
        )
        after = find_webhook(instance, key)
        ensure(not after or after.get("enabled") is False,
               "Webhook ainda ativo. Abortando sem implantar.")
    print("Webhook de avaliações desativado.", flush=True)

    clean_env(APP_ENV)
    clean_env(WORKER_ENV)
    shutil.copy2(NEW_UPDATER, UPDATER)
    UPDATER.chmod(0o700)
    try:
        exec_cmd("bash", "-n", str(UPDATER))
        exec_cmd(str(UPDATER), "--check")
        print("Atualizando app e worker, sem reiniciar Evolution/DB...", flush=True)
        # O atualizador oficial reconstrói a imagem, salva um dump do banco
        # e preserva o contêiner antigo para recuperação.
        subprocess.run([str(UPDATER), "--apply"], check=True)
    except Exception:
        print("Falha na atualização. O webhook permanece desativado.",
              file=sys.stderr)
        print("Backups:", backup, file=sys.stderr)
        raise

    cleanup_network()
    print("\nAvaliações removidas do SISGECE. Avisos WhatsApp preservados.")
    print("Backup:", backup)
    print("O esquema histórico foi mantido para permitir recuperação.")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError, subprocess.CalledProcessError):
        print("Remoção incompleta; não repita sem verificar o estado.",
              file=sys.stderr)
        raise SystemExit(1)

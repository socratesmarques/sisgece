#!/usr/bin/env python3
"""Ativa avaliações Evolution no lsdserver, com pré-verificação e recuperação.

Uso após merge:
    python3 deploy/ativar-avaliacoes-evolution.py --check
    python3 deploy/ativar-avaliacoes-evolution.py --apply

Nunca imprime segredos, não reinicia Evolution, Redis ou PostgreSQL.
Este procedimento é específico para os nomes/rede/portas da produção atual.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

HOME = Path.home()
EVO = HOME / "evolution-sisgece"
APP_ENV = EVO / "sisgece-prod-evolution.env"
WORKER_ENV = EVO / "worker.env"
WORKER_COMPOSE = EVO / "compose.worker.yaml"
EVOLUTION_COMPOSE = EVO / "compose.yaml"
EVOLUTION_OVERRIDE = EVO / "compose.override.yaml"
FEEDBACK_NET = "sisgece-feedback-net"
APP = "sisgece-app"
WORKER = "evolution-sisgece-sisgece-notifications-1"
EVOLUTION = "evolution-sisgece-evolution-1"
DB = "sisgece-db"
BASE_EVOLUTION = "http://127.0.0.1:18082"
WEBHOOK_PATH = "/api/notificacoes/evolution/avaliacao"
WEBHOOK_DESTINATION = f"http://{APP}:3000{WEBHOOK_PATH}"


def command(*parts, env=None):
    return subprocess.check_output(
        parts, cwd=EVO, env=env, text=True, stderr=subprocess.DEVNULL
    ).strip()


def action(*parts, env=None):
    subprocess.run(parts, cwd=EVO, env=env, check=True,
                   stdout=subprocess.DEVNULL)


def ensure(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def load_env(path):
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        ensure("=" in line, f"Linha inválida: {path.name}")
        key, value = line.split("=", 1)
        key = key.strip()
        ensure(key not in result, f"Variável duplicada em {path.name}: {key}")
        result[key] = value.strip().strip('"').strip("'")
    return result


def get_container(name):
    records = json.loads(command("docker", "inspect", name))
    ensure(len(records) == 1, f"Contêiner ausente: {name}")
    return records[0]


def env_of(container):
    return dict(value.split("=", 1) for value in container["Config"]["Env"])


def connected(container, network):
    return network in container["NetworkSettings"]["Networks"]


def http_json(url, *, api_key=None, token=None, payload=None):
    headers = {}
    if api_key:
        headers["apikey"] = api_key
    if token:
        headers["X-SISGECE-Evolution-Secret"] = token
    body = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload).encode("utf-8")
    request = Request(url, data=body, headers=headers,
                      method="POST" if payload is not None else "GET")
    with urlopen(request, timeout=12) as response:
        raw = response.read(65537)
        ensure(len(raw) <= 65536, "Resposta da API muito grande.")
        return json.loads(raw) if raw else None


def existing_webhook(payload):
    """A Evolution pode responder null, [] ou objeto."""
    if payload is None or payload == [] or payload == {}:
        return None
    if isinstance(payload, list):
        ensure(len(payload) == 1, "Mais de um webhook já configurado.")
        payload = payload[0]
    ensure(isinstance(payload, dict), "Formato inesperado do webhook.")
    hook = payload.get("webhook", payload)
    if hook is None or hook == {}:
        return None
    ensure(isinstance(hook, dict), "Formato inesperado do webhook.")
    return hook


def webhook_matches(hook, token):
    if not hook:
        return False
    headers = hook.get("headers")
    return (
        hook.get("enabled") is True
        and hook.get("url") == WEBHOOK_DESTINATION
        and "MESSAGES_UPSERT" in (hook.get("events") or [])
        and hook.get("byEvents", hook.get("webhookByEvents")) is False
        and isinstance(headers, dict)
        and headers.get("X-SISGECE-Evolution-Secret") == token
    )


def feedback_override():
    return """services:
  evolution:
    networks:
      - default
      - feedback

networks:
  feedback:
    external: true
    name: sisgece-feedback-net
"""


def worker_compose():
    return (
        "docker", "compose", "-p", "evolution-sisgece",
        "-f", str(WORKER_COMPOSE),
    )


def verify_settings():
    for path in (APP_ENV, WORKER_ENV, WORKER_COMPOSE, EVOLUTION_COMPOSE):
        ensure(path.is_file(), f"Arquivo obrigatório ausente: {path}")
    for name in ("docker", "python3"):
        ensure(shutil.which(name) is not None, f"Comando ausente: {name}")

    app = load_env(APP_ENV)
    worker = load_env(WORKER_ENV)
    token = app.get("EVOLUTION_FEEDBACK_WEBHOOK_TOKEN", "")
    instance = worker.get("EVOLUTION_INSTANCE", "")
    key = worker.get("EVOLUTION_API_KEY", "")
    ensure(re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", instance or ""),
           "Instância Evolution inválida.")
    ensure(app.get("EVOLUTION_INSTANCE") == instance,
           "EVOLUTION_INSTANCE diferente no app e no worker.")
    ensure(len(token) >= 32 and "\n" not in token and "\r" not in token,
           "Segredo do webhook ausente ou inválido.")
    ensure(bool(key) and "\n" not in key and "\r" not in key,
           "EVOLUTION_API_KEY inválida.")
    ensure(app.get("EVOLUTION_FEEDBACK_ENABLED") == "1"
           and worker.get("EVOLUTION_FEEDBACK_ENABLED") == "1"
           and worker.get("EVOLUTION_FEEDBACK_LIST_ENABLED") == "1",
           "Variáveis de avaliação não estão preparadas.")
    ensure(app.get("NOTIFICATIONS_PROVIDER") == "evolution"
           and app.get("WHATSAPP_REAL_SEND_ENABLED") == "0",
           "Configuração do app não corresponde ao ambiente esperado.")
    ensure(worker.get("NOTIFICATIONS_PROVIDER") == "evolution"
           and worker.get("WHATSAPP_REAL_SEND_ENABLED") == "1"
           and worker.get("EVOLUTION_LAB_ENABLED") == "1"
           and worker.get("EVOLUTION_API_URL") == "http://evolution:8080",
           "Configuração do worker não corresponde ao ambiente esperado.")

    app_container = get_container(APP)
    worker_container = get_container(WORKER)
    evolution_container = get_container(EVOLUTION)
    get_container(DB)
    ensure(worker_container["State"]["Running"]
           and evolution_container["State"]["Running"],
           "Worker e Evolution devem estar ativos.")
    ensure(app_container["State"]["Running"],
           "O SISGECE deve estar ativo antes da atualização.")
    ensure(app_container["HostConfig"]["NetworkMode"] == "sisgece-net"
           and not app_container["Mounts"],
           "Rede principal ou montagens do SISGECE mudaram.")
    ports = app_container["NetworkSettings"]["Ports"]
    ensure(any(p.get("HostIp") == "127.0.0.1"
               and p.get("HostPort") == "18081"
               for p in (ports.get("3000/tcp") or [])),
           "Porta do SISGECE não corresponde à produção.")
    ensure(connected(app_container, "sisgece-net")
           and connected(app_container, FEEDBACK_NET)
           and connected(evolution_container, FEEDBACK_NET),
           "Rede privada de avaliação não está conectada.")
    ensure(all(env_of(app_container).get(k) == app.get(k)
               for k in ("PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD")),
           "Credenciais de banco diferentes do contêiner de produção.")
    image = app_container["Config"]["Image"]
    ensure(re.fullmatch(r"sisgece:prod-[a-f0-9]{7,40}", image),
           "Imagem do SISGECE não corresponde à esperada.")
    ensure(worker_container["Config"]["Image"] == image,
           "App e worker não utilizam a mesma imagem.")

    env = {**os.environ, "SISGECE_IMAGE": image}
    action(*worker_compose(), "config", "--quiet", env=env)

    # Não sobrescreva overrides de terceiros ou configurações de webhook.
    if EVOLUTION_OVERRIDE.exists():
        ensure("sisgece-feedback-net" in EVOLUTION_OVERRIDE.read_text(),
               "compose.override.yaml existente precisa de revisão.")
        configured = json.loads(command(
            "docker", "compose", "-f", str(EVOLUTION_COMPOSE),
            "-f", str(EVOLUTION_OVERRIDE), "config", "--format", "json"
        ))
        service = configured["services"]["evolution"]
        ensure("feedback" in service.get("networks", {}),
               "Override atual não adiciona a rede feedback.")
    else:
        ensure(not EVOLUTION_OVERRIDE.is_symlink(),
               "Override não pode ser um link simbólico.")

    find_url = f"{BASE_EVOLUTION}/webhook/find/{quote(instance, safe='')}"
    hook = existing_webhook(http_json(find_url, api_key=key))
    ensure(not hook or webhook_matches(hook, token),
           "Webhook já configurado para outro destino ou credencial. "
           "Não será sobrescrito.")
    return app, worker, token, instance, key, image, bool(hook)


def configure_override(backup_dir):
    if EVOLUTION_OVERRIDE.exists():
        return
    # Compose padrão carrega esse arquivo em operações futuras sem -f.
    EVOLUTION_OVERRIDE.write_text(feedback_override(), encoding="utf-8")
    EVOLUTION_OVERRIDE.chmod(0o600)
    configured = json.loads(command(
        "docker", "compose", "-f", str(EVOLUTION_COMPOSE),
        "-f", str(EVOLUTION_OVERRIDE), "config", "--format", "json"
    ))
    ensure("feedback" in configured["services"]["evolution"]["networks"],
           "Compose não reconheceu a rede de avaliações.")


def check_healthy():
    for _ in range(40):
        try:
            result = http_json("http://127.0.0.1:18081/api/ready")
            if isinstance(result, dict) and result.get("ok") is True:
                return
        except (OSError, ValueError, RuntimeError):
            pass
        time.sleep(1)
    raise RuntimeError("SISGECE não respondeu ao healthcheck.")


def enable():
    app_env, worker_env, token, instance, key, image, hook_exists = verify_settings()
    print("Pré-verificação concluída: ambientes, redes, credenciais e webhook.")
    current_app = env_of(get_container(APP))
    current_worker = env_of(get_container(WORKER))
    if (hook_exists
            and current_app.get("EVOLUTION_FEEDBACK_ENABLED") == "1"
            and current_app.get("EVOLUTION_INSTANCE") == instance
            and current_worker.get("EVOLUTION_FEEDBACK_ENABLED") == "1"
            and current_worker.get("EVOLUTION_FEEDBACK_LIST_ENABLED") == "1"):
        print("Avaliações já estão ativas. Nenhuma alteração necessária.")
        return

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = HOME / "sisgece-backups" / ("ativacao-avaliacoes-" + timestamp)
    backup.mkdir(parents=True, exist_ok=False, mode=0o700)
    backup.chmod(0o700)
    for path in (APP_ENV, WORKER_ENV, WORKER_COMPOSE):
        shutil.copy2(path, backup / path.name)
    if EVOLUTION_OVERRIDE.exists():
        shutil.copy2(EVOLUTION_OVERRIDE, backup / EVOLUTION_OVERRIDE.name)
    previous = f"{APP}-anterior-feedback-{timestamp}"
    worker_was_stopped = False
    old_app_stopped = False
    old_app_renamed = False
    worker_recreated = False
    compose_env = {**os.environ, "SISGECE_IMAGE": image}

    try:
        configure_override(backup)
        print("1/4 Rede persistente e backups preparados.", flush=True)
        # Marca a intenção ANTES dos comandos: se Docker parar o serviço
        # e devolver erro, a recuperação ainda tentará reiniciá-lo.
        worker_was_stopped = True
        action(*worker_compose(), "stop", "sisgece-notifications",
               env=compose_env)
        old_app_stopped = True
        action("docker", "stop", APP)
        action("docker", "rename", APP, previous)
        old_app_renamed = True

        # Mesma imagem/configuração do atualizador oficial (sem mudar o DB).
        action(
            "docker", "run", "-d", "--name", APP,
            "--network", "sisgece-net", "--restart", "unless-stopped",
            "--read-only", "--tmpfs", "/tmp", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--env-file", str(APP_ENV),
            "-p", "127.0.0.1:18081:3000", image
        )
        action("docker", "network", "connect", FEEDBACK_NET, APP)
        check_healthy()
        new_env = env_of(get_container(APP))
        ensure(new_env.get("EVOLUTION_FEEDBACK_ENABLED") == "1"
               and new_env.get("EVOLUTION_INSTANCE") == instance,
               "Configuração não aplicada no SISGECE.")
        response = http_json(
            "http://127.0.0.1:18081" + WEBHOOK_PATH,
            token=token, payload={"event": "sisgece.healthcheck"}
        )
        ensure(response == {"ok": True}, "Webhook não autenticou o teste.")
        action(
            "docker", "exec", EVOLUTION, "node", "-e",
            "fetch('http://sisgece-app:3000/api/ready')"
            ".then(r=>process.exit(r.ok?0:1))"
            ".catch(()=>process.exit(1))"
        )
        print("2/4 SISGECE e webhook responderam corretamente.", flush=True)

        set_url = f"{BASE_EVOLUTION}/webhook/set/{quote(instance, safe='')}"
        find_url = f"{BASE_EVOLUTION}/webhook/find/{quote(instance, safe='')}"
        if not hook_exists:
            http_json(set_url, api_key=key, payload={
                "webhook": {
                    "enabled": True,
                    "url": WEBHOOK_DESTINATION,
                    "headers": {"X-SISGECE-Evolution-Secret": token},
                    "byEvents": False, "base64": False,
                    "events": ["MESSAGES_UPSERT"]
                }
            })
        configured = existing_webhook(http_json(find_url, api_key=key))
        ensure(webhook_matches(configured, token),
               "Evolution não confirmou destino, eventos e autenticação.")
        print("3/4 Evolution confirmou o webhook privado.", flush=True)

        worker_recreated = True
        action(*worker_compose(), "up", "-d", "--no-deps",
               "--force-recreate", "sisgece-notifications", env=compose_env)
        time.sleep(2)
        active = get_container(WORKER)
        ensure(active["State"]["Running"], "Worker não iniciou.")
        new_worker_env = env_of(active)
        ensure(new_worker_env.get("EVOLUTION_FEEDBACK_ENABLED") == "1"
               and new_worker_env.get("EVOLUTION_FEEDBACK_LIST_ENABLED") == "1",
               "Configuração List não foi aplicada no worker.")
        ensure(new_worker_env.get("EVOLUTION_INSTANCE") == instance,
               "Instância do worker diferente da configurada.")
        print("4/4 Worker reiniciado com listas interativas.", flush=True)
    except BaseException as error:
        print(f"Falha na ativação: {type(error).__name__}. Recuperando...", file=sys.stderr)
        if old_app_renamed:
            subprocess.run(["docker", "rm", "-f", APP], check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["docker", "rename", previous, APP], check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["docker", "start", APP], check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif old_app_stopped:
            subprocess.run(["docker", "start", APP], check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if worker_was_stopped:
            if worker_recreated:
                # Se o contêiner antigo foi substituído, recupera o worker
                # com envio de notificações ativo, mas pesquisas desativadas.
                content = WORKER_ENV.read_text(encoding="utf-8")
                for flag in ("EVOLUTION_FEEDBACK_ENABLED",
                             "EVOLUTION_FEEDBACK_LIST_ENABLED"):
                    content = re.sub(
                        rf"(?m)^{flag}=.*$", f"{flag}=0", content
                    )
                WORKER_ENV.write_text(content, encoding="utf-8")
                WORKER_ENV.chmod(0o600)
                recovery = subprocess.run(
                    (*worker_compose(), "up", "-d", "--no-deps",
                     "--force-recreate", "sisgece-notifications"),
                    cwd=EVO, env=compose_env, check=False,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                if recovery.returncode:
                    print("ATENÇÃO: worker precisa de recuperação manual.",
                          file=sys.stderr)
            else:
                subprocess.run(["docker", "start", WORKER], check=False,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"Backups em {backup}. Não execute novamente sem verificar o estado.",
              file=sys.stderr)
        raise SystemExit(1)
    print("\nAVALIAÇÕES ATIVADAS — app e worker saudáveis.")
    print("Webhook registrado; nenhuma mensagem real de teste foi enviada.")
    print(f"Backup: {backup}")
    print(f"Contêiner anterior preservado: {previous}")
    print("Próximo passo: testar uma solicitação fictícia e conferir a nota.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="verifica sem mudar os serviços")
    parser.add_argument("--apply", action="store_true",
                        help="aplica em produção após homologação")
    args = parser.parse_args()
    if args.check == args.apply:
        parser.error("informe somente --check ou --apply")
    try:
        if args.check:
            verify_settings()
            print("Pré-verificação OK. Nenhuma alteração realizada.")
        else:
            enable()
    except (RuntimeError, OSError, ValueError, subprocess.CalledProcessError,
            HTTPError, URLError) as error:
        # Não imprime detalhes das respostas HTTP que poderiam conter segredos.
        print(f"Falha: {type(error).__name__}. Revise pré-requisitos.", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()

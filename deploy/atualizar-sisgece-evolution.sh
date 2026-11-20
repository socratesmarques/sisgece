#!/usr/bin/env bash
# Atualiza o SISGECE no lsdserver preservando a configuração Evolution e o worker.
# Uso: bash atualizar-sisgece.sh --check | --apply
set -Eeuo pipefail
umask 077

[[ $# -eq 1 && ( "$1" == "--check" || "$1" == "--apply" ) ]] || {
  echo "Uso: $0 --check | --apply" >&2
  exit 2
}
MODE="$1"
REPO="${SISGECE_REPO:-$HOME/sisgece}"
EVO_DIR="${SISGECE_EVOLUTION_DIR:-$HOME/evolution-sisgece}"
APP_ENV="$EVO_DIR/sisgece-prod-evolution.env"
WORKER_ENV="$EVO_DIR/worker.env"
COMPOSE="$EVO_DIR/compose.worker.yaml"
PROJECT=evolution-sisgece
APP=sisgece-app
DB=sisgece-db
WORKER=evolution-sisgece-sisgece-notifications-1
BACKUP_ROOT="$HOME/sisgece-backups"

get_env() {
  sed -n "s/^$2=//p" "$1" | tail -n 1
}
require_env() {
  [[ -n "$(get_env "$1" "$2")" ]] || {
    echo "Falta $2 no arquivo $(basename "$1")" >&2
    exit 1
  }
}

for cmd in docker git curl; do
  command -v "$cmd" >/dev/null || { echo "Falta o comando $cmd" >&2; exit 1; }
done
[[ -d "$REPO/.git" ]] || { echo "Checkout não encontrado: $REPO" >&2; exit 1; }
for file in "$APP_ENV" "$WORKER_ENV" "$COMPOSE"; do
  [[ -f "$file" ]] || { echo "Arquivo ausente: $file" >&2; exit 1; }
done
for field in PGHOST PGPORT PGDATABASE PGUSER PGPASSWORD; do
  require_env "$APP_ENV" "$field"
  require_env "$WORKER_ENV" "$field"
done
for field in EVOLUTION_API_KEY EVOLUTION_API_URL EVOLUTION_INSTANCE; do
  require_env "$WORKER_ENV" "$field"
done
[[ "$(get_env "$APP_ENV" NOTIFICATIONS_PROVIDER)" == evolution ]] || {
  echo "Provedor Evolution ausente no ambiente do app." >&2; exit 1;
}
[[ "$(get_env "$APP_ENV" WHATSAPP_REAL_SEND_ENABLED)" == 0 ]] || {
  echo "Envio real deve ficar apenas no worker." >&2; exit 1;
}
[[ "$(get_env "$WORKER_ENV" NOTIFICATIONS_PROVIDER)" == evolution ]] || {
  echo "Provedor Evolution ausente no worker." >&2; exit 1;
}
[[ "$(get_env "$WORKER_ENV" WHATSAPP_REAL_SEND_ENABLED)" == 1 &&
   "$(get_env "$WORKER_ENV" EVOLUTION_LAB_ENABLED)" == 1 ]] || {
  echo "O worker não está autorizado para envio real. Não alterei essa decisão." >&2; exit 1;
}
[[ "$(get_env "$WORKER_ENV" EVOLUTION_API_URL)" == http://evolution:8080 ]] || {
  echo "Endpoint da Evolution diferente do esperado." >&2; exit 1;
}

[[ "$(git -C "$REPO" branch --show-current)" == main ]] || {
  echo "O checkout do servidor deve estar na branch main." >&2; exit 1;
}
[[ -z "$(git -C "$REPO" status --porcelain)" ]] || {
  echo "O checkout tem alterações locais. Preserve-as antes de atualizar." >&2; exit 1;
}
docker inspect "$APP" >/dev/null
docker inspect "$DB" >/dev/null
docker inspect "$WORKER" >/dev/null
[[ "$(docker inspect -f '{{.HostConfig.NetworkMode}}' "$APP")" == sisgece-net &&
   "$(docker inspect -f '{{len .Mounts}}' "$APP")" == 0 &&
   "$(docker port "$APP" 3000/tcp)" == 127.0.0.1:18081 ]] || {
  echo "Rede, montagens ou porta do SISGECE mudaram. Não prosseguirei." >&2; exit 1;
}

OLD_IMAGE="$(docker inspect -f '{{.Config.Image}}' "$APP")"
WORKER_RUNNING="$(docker inspect -f '{{.State.Running}}' "$WORKER")"
(
  cd "$EVO_DIR"
  SISGECE_IMAGE="$OLD_IMAGE" docker compose -p "$PROJECT" -f "$COMPOSE" config --quiet
)

# Confere as credenciais do banco sem revelá-las na saída.
for field in PGHOST PGPORT PGDATABASE PGUSER PGPASSWORD; do
  running="$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$APP" |
    sed -n "s/^$field=//p" | tail -n 1)"
  [[ "$running" == "$(get_env "$APP_ENV" "$field")" ]] || {
    echo "A variável $field diverge do app em produção." >&2; exit 1;
  }
done

printf 'App: %s | Evolution: ativo | Worker em execução: %s\n' "$OLD_IMAGE" "$WORKER_RUNNING"
if [[ "$MODE" == --check ]]; then
  echo "Pré-verificação concluída; nenhuma alteração realizada."
  exit 0
fi

git -C "$REPO" pull --ff-only origin main
SHA="$(git -C "$REPO" rev-parse --short HEAD)"
NEW_IMAGE="sisgece:prod-$SHA"
if [[ "$OLD_IMAGE" == "$NEW_IMAGE" ]]; then
  echo "SISGECE já utiliza $NEW_IMAGE; nenhuma atualização necessária."
  exit 0
fi

# Constrói a imagem antes da janela de indisponibilidade.
docker build -t "$NEW_IMAGE" "$REPO"

STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="$BACKUP_ROOT/$STAMP"
PREVIOUS="sisgece-app-anterior-$STAMP"
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
cp -p "$APP_ENV" "$BACKUP_DIR/app.env"
cp -p "$WORKER_ENV" "$BACKUP_DIR/worker.env"
cp -p "$COMPOSE" "$BACKUP_DIR/compose.worker.yaml"
printf '%s\n' "$OLD_IMAGE" > "$BACKUP_DIR/imagem-anterior.txt"
printf '%s\n' "$NEW_IMAGE" > "$BACKUP_DIR/imagem-nova.txt"
printf '%s\n' "$PREVIOUS" > "$BACKUP_DIR/container-anterior.txt"

DB_USER="$(get_env "$APP_ENV" PGUSER)"
DB_NAME="$(get_env "$APP_ENV" PGDATABASE)"
STAGE=initial
WORKER_STOPPED=false

restore_on_error() {
  local code="$1"
  trap - ERR INT TERM
  set +e
  echo "Falha na atualização. Tentando restaurar os contêineres anteriores..." >&2
  if [[ "$STAGE" == renamed || "$STAGE" == new ]]; then
    docker rm -f "$APP" >/dev/null 2>&1 || true
    if docker inspect "$PREVIOUS" >/dev/null 2>&1; then
      docker rename "$PREVIOUS" "$APP" && docker start "$APP"
    fi
  elif [[ "$STAGE" == stopped ]]; then
    docker start "$APP"
  fi
  if [[ "$WORKER_STOPPED" == true && "$WORKER_RUNNING" == true ]]; then
    (
      cd "$EVO_DIR"
      SISGECE_IMAGE="$OLD_IMAGE" docker compose -p "$PROJECT" -f "$COMPOSE" \
        up -d --no-deps --force-recreate sisgece-notifications
    ) || echo "ATENÇÃO: reative o worker antigo manualmente." >&2
  fi
  echo "Backup em $BACKUP_DIR. Migrações de banco exigem avaliação antes de eventual restauração." >&2
  exit "$code"
}
trap 'restore_on_error $?' ERR
trap 'restore_on_error 130' INT
trap 'restore_on_error 143' TERM

if [[ "$WORKER_RUNNING" == true ]]; then
  (
    cd "$EVO_DIR"
    docker compose -p "$PROJECT" -f "$COMPOSE" stop sisgece-notifications
  )
  WORKER_STOPPED=true
fi

docker stop "$APP"
STAGE=stopped
docker exec "$DB" pg_dump -U "$DB_USER" -d "$DB_NAME" -Fc > "$BACKUP_DIR/sisgece.dump"
[[ -s "$BACKUP_DIR/sisgece.dump" ]] || { echo "Backup PostgreSQL vazio." >&2; false; }
docker rename "$APP" "$PREVIOUS"
STAGE=renamed

docker run -d --name "$APP" --network sisgece-net \
  --restart unless-stopped --read-only --tmpfs /tmp --cap-drop ALL \
  --security-opt no-new-privileges \
  --env-file "$APP_ENV" -p 127.0.0.1:18081:3000 "$NEW_IMAGE"
STAGE=new

HEALTHY=false
for attempt in $(seq 1 30); do
  if curl -fsS --max-time 3 http://127.0.0.1:18081/api/ready 2>/dev/null |
     grep -q '"ok":true'; then
    HEALTHY=true
    break
  fi
  sleep 2
done
[[ "$HEALTHY" == true ]] || { echo "SISGECE não respondeu /api/ready." >&2; false; }
[[ "$(docker exec "$APP" printenv NOTIFICATIONS_PROVIDER)" == evolution ]] || {
  echo "Configuração Evolution não foi preservada." >&2; false;
}

# Troca a imagem do worker sem mudar se ele estava ligado ou desligado.
if [[ "$WORKER_RUNNING" == true ]]; then
  (
    cd "$EVO_DIR"
    SISGECE_IMAGE="$NEW_IMAGE" docker compose -p "$PROJECT" -f "$COMPOSE" \
      up -d --no-deps --force-recreate sisgece-notifications
  )
  [[ "$(docker inspect -f '{{.State.Running}}' "$WORKER")" == true ]] || {
    echo "Novo worker não iniciou." >&2; false;
  }
else
  (
    cd "$EVO_DIR"
    SISGECE_IMAGE="$NEW_IMAGE" docker compose -p "$PROJECT" -f "$COMPOSE" \
      create --no-deps --force-recreate sisgece-notifications
  )
fi

trap - ERR INT TERM
printf '\nSISGECE atualizado: %s\nBackup: %s\nContêiner anterior: %s\nWorker estava ativo: %s\n' \
  "$NEW_IMAGE" "$BACKUP_DIR" "$PREVIOUS" "$WORKER_RUNNING"

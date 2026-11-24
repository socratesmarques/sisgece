#!/usr/bin/env bash
# Atualiza o SISGECE no lsdserver preservando a configuração Evolution e o worker.
# Uso: bash atualizar-sisgece.sh --check | --apply | --restart
set -euo pipefail
umask 077

[[ $# -eq 1 && ( "$1" == "--check" || "$1" == "--apply" || "$1" == "--restart" ) ]] || {
  echo "Uso: $0 --check | --apply | --restart" >&2
  exit 2
}
MODE="$1"
REPO="${SISGECE_REPO:-$HOME/sisgece}"
EVO_DIR="${SISGECE_EVOLUTION_DIR:-$HOME/evolution-sisgece}"
APP_ENV="$EVO_DIR/sisgece-prod-evolution.env"
WORKER_ENV="$EVO_DIR/worker.env"
COMPOSE="$EVO_DIR/compose.worker.yaml"
PROJECT="evolution-sisgece"
APP="sisgece-app"
DB="sisgece-db"
WORKER="evolution-sisgece-sisgece-notifications-1"
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

wait_for_app() {
  local attempt
  for ((attempt = 1; attempt <= 30; attempt++)); do
    if curl --noproxy '*' -fsS --max-time 3 http://127.0.0.1:18081/api/ready 2>/dev/null |
       grep -E '"ok"[[:space:]]*:[[:space:]]*true' >/dev/null; then
      return 0
    fi
    [[ "$attempt" -eq 30 ]] || sleep 2
  done
  echo "SISGECE não respondeu /api/ready." >&2
  return 1
}

lock_operation() {
  command -v flock >/dev/null || { echo "Falta o comando flock" >&2; exit 1; }
  mkdir -p "$BACKUP_ROOT"
  exec 9>"$BACKUP_ROOT/.atualizador.lock"
  flock -n 9 || { echo "Já existe uma operação do SISGECE em andamento." >&2; exit 1; }
}

restart_stack() {
  local containers id service app_id db_id worker_id evolution=
  local -a dependencies=()
  app_id="$(docker container inspect -f '{{.Id}}' "$APP")"
  db_id="$(docker container inspect -f '{{.Id}}' "$DB")"
  worker_id="$(docker container inspect -f '{{.Id}}' "$WORKER")"
  containers="$(docker container ls -aq --no-trunc \
    --filter "label=com.docker.compose.project=$PROJECT" \
    --filter 'label=com.docker.compose.oneoff=False')"
  while IFS= read -r id; do
    [[ -n "$id" && "$id" != "$app_id" && "$id" != "$db_id" && "$id" != "$worker_id" ]] || continue
    service="$(docker container inspect -f '{{index .Config.Labels "com.docker.compose.service"}}' "$id")"
    if [[ "$service" == evolution ]]; then
      [[ -z "$evolution" ]] || { echo "Mais de um contêiner Evolution encontrado." >&2; return 1; }
      evolution="$id"
    else
      dependencies+=("$id")
    fi
  done <<< "$containers"
  [[ -n "$evolution" ]] || { echo "Contêiner Evolution não encontrado no projeto $PROJECT." >&2; return 1; }

  # Pare os consumidores antes de reiniciar seus bancos.
  local app_running worker_running
  app_running="$(docker container inspect -f '{{.State.Running}}' "$app_id")"
  worker_running="$(docker container inspect -f '{{.State.Running}}' "$worker_id")"
  local recovery
  printf -v recovery 'recover_restart "$?" %q %q %q %q' "$app_id" "$worker_id" "$app_running" "$worker_running"
  # Capture os argumentos locais agora e o código de saída na execução do trap.
  # shellcheck disable=SC2064
  trap "$recovery" EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  [[ "$worker_running" != true ]] || docker stop "$worker_id"
  [[ "$app_running" != true ]] || docker stop "$app_id"
  docker restart "$db_id"
  if (( ${#dependencies[@]} > 0 )); then
    docker restart "${dependencies[@]}"
  fi
  docker restart "$evolution"
  docker restart "$app_id"
  wait_for_app
  docker restart "$worker_id"
  [[ "$(docker container inspect -f '{{.State.Running}}' "$worker_id")" == true ]] || {
    echo "Worker não iniciou." >&2; return 1;
  }
  trap - EXIT INT TERM
  echo "Contêineres do SISGECE e da Evolution reiniciados."
}

recover_restart() {
  local code="$1" app_id="$2" worker_id="$3" app_running="$4" worker_running="$5"
  trap - EXIT INT TERM
  if (( code != 0 )); then
    echo "Falha no reinício. Confira o estado dos contêineres." >&2
    if [[ "$app_running" == true ]]; then
      docker start "$app_id" || echo "Não foi possível iniciar o app." >&2
    fi
    if [[ "$worker_running" == true ]]; then
      docker start "$worker_id" || echo "Não foi possível iniciar o worker." >&2
    fi
  fi
  exit "$code"
}

if [[ "$MODE" != --check ]]; then
  lock_operation
fi

if [[ "$MODE" == --restart ]]; then
  restart_stack
  exit 0
fi

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
docker container inspect "$APP" >/dev/null
docker container inspect "$DB" >/dev/null
docker container inspect "$WORKER" >/dev/null
[[ "$(docker container inspect -f '{{.HostConfig.NetworkMode}}' "$APP")" == sisgece-net &&
   "$(docker container inspect -f '{{len .Mounts}}' "$APP")" == 0 &&
   "$(docker port "$APP" 3000/tcp)" == 127.0.0.1:18081 ]] || {
  echo "Rede, montagens ou porta do SISGECE mudaram. Não prosseguirei." >&2; exit 1;
}

OLD_IMAGE="$(docker container inspect -f '{{.Config.Image}}' "$APP")"
APP_RUNNING="$(docker container inspect -f '{{.State.Running}}' "$APP")"
WORKER_RUNNING="$(docker container inspect -f '{{.State.Running}}' "$WORKER")"
(
  cd "$EVO_DIR"
  SISGECE_IMAGE="$OLD_IMAGE" docker compose -p "$PROJECT" -f "$COMPOSE" config --quiet
)

# Confere as credenciais do banco sem revelá-las na saída.
for field in PGHOST PGPORT PGDATABASE PGUSER PGPASSWORD; do
  running="$(docker container inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$APP" |
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
BACKUP_DIR="$(mktemp -d "$BACKUP_ROOT/$STAMP-XXXXXX")"
PREVIOUS="sisgece-app-anterior-${BACKUP_DIR##*/}"
cp "$APP_ENV" "$BACKUP_DIR/app.env"
cp "$WORKER_ENV" "$BACKUP_DIR/worker.env"
cp "$COMPOSE" "$BACKUP_DIR/compose.worker.yaml"
printf '%s\n' "$OLD_IMAGE" > "$BACKUP_DIR/imagem-anterior.txt"
printf '%s\n' "$NEW_IMAGE" > "$BACKUP_DIR/imagem-nova.txt"
printf '%s\n' "$PREVIOUS" > "$BACKUP_DIR/container-anterior.txt"

DB_USER="$(get_env "$APP_ENV" PGUSER)"
DB_NAME="$(get_env "$APP_ENV" PGDATABASE)"
STAGE=initial
WORKER_CHANGED=false

restore_on_error() {
  local code="$1"
  trap - EXIT INT TERM
  if (( code == 0 )); then
    return 0
  fi
  set +e
  echo "Falha na atualização. Tentando restaurar os contêineres anteriores..." >&2
  if [[ "$STAGE" == renaming ]] && docker container inspect "$PREVIOUS" >/dev/null 2>&1; then
    if docker container inspect "$APP" >/dev/null 2>&1; then
      docker rm -f "$APP" || echo "Não foi possível remover o novo app." >&2
    fi
    docker rename "$PREVIOUS" "$APP" || echo "Não foi possível recuperar o nome do app anterior." >&2
  fi
  if [[ "$STAGE" != initial && "$APP_RUNNING" == true ]]; then
    docker start "$APP" || echo "Não foi possível iniciar o app anterior." >&2
  fi
  if [[ "$WORKER_CHANGED" == true ]]; then
    (
      cd "$EVO_DIR"
      if [[ "$WORKER_RUNNING" == true ]]; then
        SISGECE_IMAGE="$OLD_IMAGE" docker compose -p "$PROJECT" -f "$COMPOSE" \
          up -d --no-deps --force-recreate sisgece-notifications
      else
        SISGECE_IMAGE="$OLD_IMAGE" docker compose -p "$PROJECT" -f "$COMPOSE" \
          create --no-deps --force-recreate sisgece-notifications
      fi
    ) || echo "ATENÇÃO: restaure o worker antigo manualmente." >&2
  fi
  echo "Backup em $BACKUP_DIR. Migrações de banco exigem avaliação antes de eventual restauração." >&2
  exit "$code"
}
trap 'restore_on_error "$?"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if [[ "$WORKER_RUNNING" == true ]]; then
  WORKER_CHANGED=true
  (
    cd "$EVO_DIR"
    SISGECE_IMAGE="$OLD_IMAGE" docker compose -p "$PROJECT" -f "$COMPOSE" stop sisgece-notifications
  )
fi

STAGE=stopping
[[ "$APP_RUNNING" != true ]] || docker stop "$APP"
docker exec "$DB" pg_dump -U "$DB_USER" -d "$DB_NAME" -Fc > "$BACKUP_DIR/sisgece.dump"
[[ -s "$BACKUP_DIR/sisgece.dump" ]] || { echo "Backup PostgreSQL vazio." >&2; false; }
docker exec -i "$DB" pg_restore --file=/dev/null < "$BACKUP_DIR/sisgece.dump"
STAGE=renaming
docker rename "$APP" "$PREVIOUS"

docker run -d --name "$APP" --network sisgece-net \
  --restart unless-stopped --read-only --tmpfs /tmp --cap-drop ALL \
  --security-opt no-new-privileges \
  --env-file "$APP_ENV" -p 127.0.0.1:18081:3000 "$NEW_IMAGE"
wait_for_app
[[ "$(docker exec "$APP" printenv NOTIFICATIONS_PROVIDER)" == evolution ]] || {
  echo "Configuração Evolution não foi preservada." >&2; false;
}

# Troca a imagem do worker sem mudar se ele estava ligado ou desligado.
WORKER_CHANGED=true
if [[ "$WORKER_RUNNING" == true ]]; then
  (
    cd "$EVO_DIR"
    SISGECE_IMAGE="$NEW_IMAGE" docker compose -p "$PROJECT" -f "$COMPOSE" \
      up -d --no-deps --force-recreate sisgece-notifications
  )
  [[ "$(docker container inspect -f '{{.State.Running}}' "$WORKER")" == true ]] || {
    echo "Novo worker não iniciou." >&2; false;
  }
else
  (
    cd "$EVO_DIR"
    SISGECE_IMAGE="$NEW_IMAGE" docker compose -p "$PROJECT" -f "$COMPOSE" \
      create --no-deps --force-recreate sisgece-notifications
  )
fi

trap - EXIT INT TERM
printf '\nSISGECE atualizado: %s\nBackup: %s\nContêiner anterior: %s\nWorker estava ativo: %s\n' \
  "$NEW_IMAGE" "$BACKUP_DIR" "$PREVIOUS" "$WORKER_RUNNING"

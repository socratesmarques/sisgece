# Atualizar o SISGECE no servidor

Este roteiro usa o servidor Linux com Docker e HTTPS documentado no README:
contêineres `sisgece-app` e `sisgece-db`, rede `sisgece-net`, banco e usuário
`sisgece`, porta local 8004 e arquivo `app.env.local` já configurado.
Se a instalação usa outros nomes, ajuste os comandos antes de executá-los.
O PostgreSQL, o volume de dados, as credenciais e o proxy Caddy existentes
continuam sendo usados. Execute os blocos em ordem, no mesmo terminal Bash.

## 1. Integrar a atualização no GitHub

Revise o pull request, aguarde a CI passar e faça o merge na `main`.
Os comandos abaixo devem ser executados **depois do merge**.

## 2. Conferir a instalação e baixar o código

Entre por SSH e acesse a pasta onde o repositório já está instalado:

```bash
set -euo pipefail
umask 077
cd /caminho/real/do/sisgece

git status --short
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
docker inspect --format '{{json .Mounts}}' sisgece-db
docker inspect --format '{{json .NetworkSettings.Networks}}' sisgece-app
```

Se `git status` mostrar alterações locais em arquivos do projeto, preserve-as
antes de continuar. Não use `git reset --hard` para atualizar o servidor.
Confirme a rede real e a existência do arquivo `app.env.local`; não compartilhe
seu conteúdo, pois ele contém credenciais. Não crie outro volume ou outro banco
para a atualização normal.

```bash
test -f app.env.local
git switch main
git pull --ff-only origin main
VERSAO=$(git rev-parse --short HEAD)
MARCA=$(date +%Y%m%d-%H%M%S)
IMAGEM="sisgece:atualizacao-${VERSAO}"
ANTERIOR="sisgece-app-anterior-${MARCA}"
BACKUP_DIR="$(pwd)/backups/${MARCA}"
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
printf '%s\n' "$IMAGEM" > "$BACKUP_DIR/imagem-nova.txt"
printf '%s\n' "$ANTERIOR" > "$BACKUP_DIR/container-anterior.txt"
docker inspect --format '{{.Image}}' sisgece-app > "$BACKUP_DIR/imagem-anterior.txt"
```

## 3. Construir a imagem antes da parada

```bash
docker build -t "$IMAGEM" .
```

Se o build falhar, corrija a causa antes de parar o sistema. A aplicação que já
está em execução continua usando a imagem anterior.

## 4. Parar a aplicação e fazer backup do banco

Programe uma breve janela de manutenção. Pare apenas a aplicação; mantenha o
PostgreSQL em execução. O backup é feito após a parada, para não receber novos
pedidos entre a cópia e a migração.

```bash
docker stop sisgece-app
docker exec sisgece-db pg_dump -U sisgece -d sisgece -Fc > "$BACKUP_DIR/sisgece.dump"
test -s "$BACKUP_DIR/sisgece.dump"
```

Ensaie a restauração em um banco temporário, separado do banco em uso:

```bash
BANCO_TESTE="sisgece_validacao_${MARCA//-/_}"
docker exec sisgece-db createdb -U sisgece "$BANCO_TESTE"
docker exec -i sisgece-db pg_restore --exit-on-error --no-owner --no-acl -U sisgece -d "$BANCO_TESTE" < "$BACKUP_DIR/sisgece.dump"
docker exec sisgece-db dropdb -U sisgece "$BANCO_TESTE"
```

Continue somente se os comandos terminarem sem erro. Se o backup ou a restauração
falhar, não inicie a versão nova. Como a migração ainda não começou, você pode
retomar o serviço anterior com `docker start sisgece-app` enquanto investiga.
Guarde também uma cópia do backup fora desse servidor, com acesso restrito.

## 5. Trocar apenas o contêiner da aplicação

```bash
docker rename sisgece-app "$ANTERIOR"
docker run -d --name sisgece-app \
  --network sisgece-net \
  --restart unless-stopped \
  --read-only --tmpfs /tmp \
  --cap-drop ALL --security-opt no-new-privileges \
  --env-file app.env.local \
  -p 127.0.0.1:8004:3000 \
  "$IMAGEM"
```

Este comando é para a instalação com HTTPS. Preserve em `app.env.local` os valores
PG* e o `SISGECE_PROXY_SECRET` que já combinam com o banco e o Caddy. Se a instalação
possui opções adicionais de rede, arquivos montados ou variáveis, mantenha essas
opções no novo `docker run`. Não use `LOCAL_HTTP=1` no servidor com HTTPS.

A inicialização executa `python backend/manage.py migrate` automaticamente antes
de iniciar o servidor web. Não é necessário executar SQL manualmente. A migração
006 muda entradas `RECEBIDA` para `PENDENTE`, mantendo IDs, dados e códigos de
consulta. A coordenação e o superusuário poderão aprovar ou recusar essas entradas.
A aprovação não comprova a entrada física no campus.

## 6. Conferir a atualização

```bash
docker logs --tail 100 sisgece-app
curl --retry 15 --retry-all-errors --retry-delay 2 --max-time 5 \
  -fsS http://127.0.0.1:8004/api/ready
docker inspect --format '{{.State.Health.Status}}' sisgece-app
```

O endpoint deve retornar `{"ok":true}`. O healthcheck pode ficar em `starting`
por alguns instantes; depois deve passar para `healthy`.
Confirme a versão da migração no banco:

```bash
docker exec sisgece-db psql -U sisgece -d sisgece \
  -c "SELECT nome FROM versoes ORDER BY nome;"
```

Confira que `006.sql` está na lista. Pelo domínio HTTPS habitual, entre com as
contas existentes e confira os filtros, o histórico e os botões de análise de
uma entrada pendente. Verifique também a visualização no celular. Use um ambiente
de homologação para criar solicitações fictícias e ensaiar os fluxos completos.
Se a aparência antiga permanecer, faça uma atualização completa da página.

As contas e senhas existentes permanecem. Não é necessário criar outro
superusuário. Não apague o contêiner anterior nem os backups antes de terminar
a validação.

## Se for necessário voltar

Se a versão nova chegou a iniciar a migração, pare-a antes de investigar:

```bash
docker stop sisgece-app
```

Não aponte a versão antiga diretamente para um banco migrado sem verificar a
compatibilidade. Para uma reversão completa, restaure o backup em **outro banco**:

```bash
BANCO_RETORNO="sisgece_retorno_${MARCA//-/_}"
docker exec sisgece-db createdb -U sisgece "$BANCO_RETORNO"
docker exec -i sisgece-db pg_restore --exit-on-error --no-owner --no-acl \
  -U sisgece -d "$BANCO_RETORNO" < "$BACKUP_DIR/sisgece.dump"
docker rename sisgece-app "sisgece-app-falha-${MARCA}"
docker run -d --name sisgece-app \
  --network sisgece-net \
  --restart unless-stopped \
  --read-only --tmpfs /tmp \
  --cap-drop ALL --security-opt no-new-privileges \
  --env-file app.env.local \
  -e PGDATABASE="$BANCO_RETORNO" \
  -p 127.0.0.1:8004:3000 \
  "$(cat "$BACKUP_DIR/imagem-anterior.txt")"
```

O retorno usa a imagem anterior e mantém o banco migrado separado para análise.
Confira `/api/ready` e o acesso HTTPS novamente. Pedidos registrados após o backup
não estarão no banco restaurado; preserve-os no banco migrado para reconciliação
antes de retomar o atendimento. Atualize a configuração operacional do banco
escolhido antes de uma próxima implantação.

## Complemento: versão com notificações (migração 007)

Leia [o procedimento específico](../docs/NOTIFICACOES.md#docker-e-atualização).
A migração 007 é aditiva e não autoriza telefones antigos. Confirme `007.sql` em
`versoes`. Mantenha `NOTIFICATIONS_PROVIDER=mock` e `WHATSAPP_REAL_SEND_ENABLED=0`
na primeira implantação. O exemplo de variáveis não deve sobrescrever seus PG*
e SISGECE_PROXY_SECRET existentes.

Se o worker `sisgece-notifications` já existir, pare-o **junto com a aplicação,
antes do backup**, e substitua-o pela mesma imagem nova depois da migração.
Na primeira implantação crie-o conforme a documentação, sem `-p`, com o
healthcheck HTTP herdado desativado. Mantenha o PostgreSQL privado e o volume atual.

Em qualquer rollback, pare também o worker. Não volte a processar uma fila de
backup com envio real habilitado: mensagens aceitas após o backup podem ser
repetidas. Preserve o banco migrado e concilie os registros antes de reativar.
A publicação do webhook e habilitação Meta são mudanças operacionais futuras que
exigem revisão institucional. Este roteiro não executa essas ações automaticamente.

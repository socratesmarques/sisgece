# SISGECE

Sistema de solicitações escolares do IFCE — Campus Maranguape, com Node.js 22+, Express e PostgreSQL 17.

## Comportamento de produção

A página inicial abre o **painel real da coordenação**. Administradores autenticados podem registrar solicitações por matrícula, consultar pendências e histórico e aprovar/reprovar com observação. As decisões gravam o administrador autenticado e a data da análise; uma solicitação analisada não pode receber outra decisão.

Todas as rotas de estudantes, responsáveis e solicitações exigem uma conta administrativa ativa. Matrícula e CPF são identificadores, **não credenciais**. O autoatendimento de estudantes/responsáveis, perfis separados de portaria/recepção e registro efetivo de entrada/saída ainda não foram implementados na API. Não use uma solicitação aprovada como registro de saída realizada.

A interface conceitual anterior foi preservada para desenvolvimento em `/demo`, com dados fictícios locais. Ela não está disponível em produção e não é incluída na imagem Docker. As contas fictícias não autenticam na API.

## Instalação com Docker

Requer Git, Docker Engine com Compose ou Docker Desktop. Execute na raiz do projeto:

```bash
git clone https://github.com/socratesmarques/sisgece.git
cd sisgece
cp backend/.env.example backend/.env
```

No PowerShell, use `Copy-Item backend/.env.example backend/.env`.

Edite `backend/.env`: preencha `PGPASSWORD` com uma senha forte e `JWT_SECRET` com uma chave aleatória. Gere a chave com `openssl rand -hex 32` ou:

```bash
node -e "console.log(require('node:crypto').randomBytes(32).toString('hex'))"
```

Não envie `.env` ao Git. A aplicação exige uma chave de ao menos 32 caracteres, inclusive em desenvolvimento. O Compose configura `PGHOST=db`, `PGPORT=5432`, `PORT=3000` e `NODE_ENV=production`.

```bash
docker compose --env-file backend/.env config -q
docker compose --env-file backend/.env up -d --build --wait
docker compose --env-file backend/.env ps
curl --fail http://localhost:8004/api/health
curl --fail http://localhost:8004/api/ready
```

O banco inicializa `db/init/001_schema.sql` apenas em volumes novos. O volume nomeado `sisgece_postgres` mantém os dados. A atualização não altera o esquema nem remove volumes existentes.

Por padrão, **8004 fica vinculada a 127.0.0.1**, acessível apenas no servidor, para uso atrás de um proxy HTTPS. O PostgreSQL não publica a porta 5432. A página de login é `/pages/admin-login.html`; os cookies usam `Secure`, `HttpOnly` e `SameSite=Strict`. Para computadores remotos, use HTTPS: acessar por `http://IP:8004` não permite manter a sessão segura. Navegadores permitem a exceção de desenvolvimento em `http://localhost:8004`.

### Criar administrador

Não há senha padrão. Em Bash/Linux, leia a senha sem colocá-la no histórico:

```bash
read -r -p "E-mail: " ADMIN_EMAIL
read -r -s -p "Senha (mínimo 12 caracteres, máximo 72 bytes): " ADMIN_PASSWORD
echo
export ADMIN_EMAIL ADMIN_PASSWORD
docker compose --env-file backend/.env exec -e ADMIN_EMAIL -e ADMIN_PASSWORD app node scripts/criarAdmin.js
unset ADMIN_PASSWORD
```

`ADMIN_NAME` é opcional. O script normaliza o e-mail e preserva senhas de contas existentes. Para revogar o acesso de uma conta, defina `administradores.ativo = false` via manutenção autorizada do banco: a próxima requisição com aquela sessão será recusada. Trocar `JWT_SECRET` invalida todas as sessões. O logout remove o cookie do navegador; um token previamente copiado continua válido até o vencimento (1 hora) ou a desativação da conta.

### Cadastrar estudantes

O cadastro é uma operação da instituição. Para um registro, sem sobrescrever matrículas existentes:

```bash
docker compose --env-file backend/.env exec \
  -e STUDENT_NAME='Nome do estudante' \
  -e STUDENT_ENROLLMENT='20260001' \
  -e STUDENT_COURSE='Informática' \
  -e STUDENT_CLASS='Turma A' \
  app node scripts/cadastrarEstudante.js
```

Para carga em lote ou vínculos de responsáveis, use importação SQL revisada pela instituição. A API valida o vínculo quando uma solicitação informa `responsavel_id`. O formulário interno registra solicitações da equipe, sem atribuí-las a um responsável.

## Publicar com HTTPS

1. Aponte um domínio para o servidor e libere somente 80/443 para acesso público.
2. Instale Caddy no **host**, substitua `sisgece.exemplo.com` em `deploy/Caddyfile` pelo domínio real e configure esse arquivo no serviço Caddy. Ele encaminha para `127.0.0.1:8004` e gerencia certificados.
3. Mantenha `APP_BIND_ADDRESS=127.0.0.1`. Defina `TRUST_PROXY` somente com o IP/CIDR do proxy que a aplicação realmente enxerga. No Docker Linux, o proxy no host costuma aparecer como o gateway da rede Docker; identifique-o antes de configurar. Exemplo para descobrir o gateway:

```bash
docker inspect sisgece-app --format '{{range .NetworkSettings.Networks}}{{.Gateway}}{{end}}'
```

Se o gateway retornado for `172.18.0.1`, use `TRUST_PROXY=172.18.0.1`. O valor depende da rede local; não copie esse IP sem verificar. Sem proxy, mantenha `false`; em execução direta no host atrás de Caddy local, use `loopback`. São aceitos IPs/CIDRs explícitos separados por vírgula. Não se aceita confiança global (`true` ou `0.0.0.0/0`). Não exponha a porta da aplicação diretamente quando confiar em cabeçalhos encaminhados.

```bash
docker compose --env-file backend/.env up -d --build --wait
```

Acesse `https://SEU_DOMINIO`, faça login e valide criação/análise com um cadastro de teste autorizado. O limite de login é de 10 tentativas por IP em 15 minutos; o limite geral é 120 requisições por minuto. Os contadores são locais ao processo. Esta configuração destina-se a **uma instância** da aplicação; múltiplas réplicas exigem um armazenamento compartilhado para os limites. Sem `TRUST_PROXY` correto, usuários atrás do proxy compartilham os limites.

Nenhum servidor é atualizado automaticamente pelo PR: domínio, certificados, segredos e aplicação no servidor devem ser configurados no ambiente de destino.

## Atualizar, fazer backup e restaurar

Antes de atualizar, proteja o arquivo de backup (contém dados pessoais):

```bash
mkdir -p backups
chmod 700 backups
umask 077
docker compose --env-file backend/.env exec -T db sh -c 'pg_dump -Fc -U "$POSTGRES_USER" "$POSTGRES_DB"' > "backups/sisgece-$(date +%Y%m%d-%H%M%S).dump"
```

Copie os backups para outro local protegido e teste a restauração periodicamente. Para testar uma restauração **em banco separado**, crie um banco descartável `sisgece_restore_test` no mesmo PostgreSQL, com espaço disponível:

```bash
docker compose --env-file backend/.env exec -T db sh -c 'createdb -U "$POSTGRES_USER" sisgece_restore_test'
docker compose --env-file backend/.env exec -T db sh -c 'pg_restore --exit-on-error --no-owner -U "$POSTGRES_USER" -d sisgece_restore_test' < backups/ARQUIVO.dump
```

O banco restaurado também contém dados pessoais: controle o acesso e remova-o após verificar a recuperação. Não restaure sobre o banco ativo sem uma janela de manutenção e um plano de recuperação.

```bash
git pull --ff-only
docker compose --env-file backend/.env up -d --build --wait
docker compose --env-file backend/.env logs --tail=100 app db
```

Esta versão invalida tokens antigos, troca sessões em sessionStorage por cookies e restringe as antigas rotas públicas. Os usuários precisam fazer login novamente. Reversão de código: volte ao commit anterior e reconstrua os contêineres, preservando o volume. A reversão também restaura os problemas de acesso da versão anterior.

**Nunca execute `docker compose down -v` em produção:** isso apaga o volume. Para parar mantendo dados, use `docker compose --env-file backend/.env down`.

### Volume antigo sem tabelas

Após backup, confira o esquema:

```bash
docker compose --env-file backend/.env exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "\dt"'
```

Se as tabelas não existirem, aplique o esquema inicial sem remover o volume:

```bash
docker compose --env-file backend/.env exec -T db sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < db/init/001_schema.sql
```

Os comandos com redirecionamento são para Bash/WSL. `CREATE TABLE IF NOT EXISTS` não migra formatos incompatíveis de tabelas existentes. Alterar `PGPASSWORD` no `.env` também não muda a senha já armazenada no PostgreSQL.

## Desenvolvimento e testes

```bash
npm ci --prefix backend
cp backend/.env.example backend/.env
# Preencha as variáveis, inclusive JWT_SECRET, e configure um PostgreSQL local.
npm start --prefix backend
npm test --prefix backend
npm audit --prefix backend --omit=dev
```

Sem `NODE_ENV=production`, o cookie permite HTTP local e `/demo` está disponível com dados fictícios. O painel real continua exigindo banco e login.

Os testes de segurança funcionam sem banco. Para incluir testes de integração HTTP/SQL, use exclusivamente um banco **descartável com nome terminado em `_test`** e configure `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD` e `PGDATABASE`:

```bash
RUN_DATABASE_TESTS=1 npm test --prefix backend
```

O teste instala o esquema inicial e cria/remove somente seus registros de teste. Não o execute sobre dados reais. A CI executa testes com PostgreSQL 17, auditoria de dependências, build Docker e teste do navegador.

O endpoint `/api/health` verifica o processo; `/api/ready` verifica o banco e a presença das tabelas. Há timeout de conexão/consulta, encerramento gracioso, cabeçalhos de segurança, CSP e rotação de logs. A aplicação executa sem root, com filesystem somente leitura e sem capabilities no Compose. Listagens são limitadas a 500 registros (pendências mais antigas ou histórico mais recente); consultas específicas por matrícula continuam disponíveis.

## Equipe

Mario — Tech Leader; Gilvan, Miguel, Socrates e Wendel — Desenvolvimento FullStack. O histórico original foi preservado no repositório consolidado.

## Licença

A licença geral do projeto ainda não foi definida.

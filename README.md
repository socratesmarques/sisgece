# SISGECE

Sistema de gerenciamento de entrada, saída e solicitações escolares do IFCE — Campus Maranguape.

Este repositório reúne a API Node.js/Express/PostgreSQL, o painel administrativo e a interface de demonstração.

## Subir com Docker (Linux ou Windows com Docker Desktop)

**Pré-requisitos:** Git, Docker Engine + plugin Docker Compose (ou Docker Desktop). A porta **8004/TCP** deve estar livre no servidor. Não é necessário instalar Node.js nem PostgreSQL no host.

### 1. Clonar e entrar na pasta

```bash
git clone https://github.com/socratesmarques/sisgece.git
cd sisgece
```

### 2. Preparar as variáveis de ambiente

No Linux, macOS ou terminal Bash:

```bash
cp backend/.env.example backend/.env
```

No PowerShell:

```powershell
Copy-Item backend/.env.example backend/.env
```

Abra `backend/.env` em um editor (por exemplo, `nano backend/.env` no Linux). Defina **PGPASSWORD** com uma senha forte, e **JWT_SECRET** com uma chave aleatória de pelo menos 32 caracteres. Gere a chave com Node.js, caso esteja instalado:

```bash
node -e "console.log(require('node:crypto').randomBytes(32).toString('hex'))"
```

Ou no Linux com OpenSSL:

```bash
openssl rand -hex 32
```

Exemplo **ilustrativo** de `backend/.env` (troque os dois valores marcados; não utilize o exemplo em produção):

```dotenv
PORT=3000
PGHOST=localhost
PGPORT=5432
PGUSER=postgres
PGPASSWORD=SUBSTITUA_POR_UMA_SENHA_FORTE
PGDATABASE=sisgece
JWT_SECRET=SUBSTITUA_POR_UMA_CHAVE_ALEATORIA_DE_64_CARACTERES
```

**Não envie** `backend/.env` para o Git. O Compose sobrescreve `PGHOST=db`, `PGPORT=5432` e `PORT=3000` internamente. A porta externa continua sendo **8004**.

### 3. Validar e iniciar os contêineres

Execute na raiz do repositório:

```bash
docker compose --env-file backend/.env config -q
docker compose --env-file backend/.env up -d --build --wait
```

Na primeira inicialização com banco vazio, o PostgreSQL cria o banco e executa automaticamente `db/init/001_schema.sql`, criando as tabelas necessárias. Os dados ficam no volume nomeado `sisgece_postgres`.

### 4. Conferir status e acessar o sistema

```bash
docker compose --env-file backend/.env ps
curl http://localhost:8004/api/health
curl http://localhost:8004/api/ready
```

Se não tiver `curl`, abra os endereços no navegador. `/api/health` verifica o servidor HTTP; `/api/ready` também exige que o PostgreSQL esteja acessível e que as tabelas esperadas existam.

Acesso local:

- Interface: http://localhost:8004
- Painel administrativo: http://localhost:8004/pages/admin-login.html
- Diagnóstico: http://localhost:8004/api/ready

Para acessar de outro computador, use `http://IP_DO_SERVIDOR:8004`. Libere a porta **8004/TCP** no firewall do servidor, se necessário; não exponha a porta 5432 do banco.

### 5. Criar um administrador

O sistema **não cria usuário ou senha padrão**. Informe nome (opcional), e-mail e uma senha **com no mínimo 12 caracteres** ao executar o comando abaixo. Os valores são exemplos e devem ser substituídos:

```bash
docker compose --env-file backend/.env exec -e ADMIN_NAME=Coordenador -e ADMIN_EMAIL=admin@exemplo.com -e ADMIN_PASSWORD='TROQUE-ESTA-SENHA-FORTE' app node scripts/criarAdmin.js
```

**Segurança:** a senha passada diretamente na linha de comando pode ficar no histórico do terminal. Para evitar isso em Linux/Bash, você pode informá-la sem ecoá-la:

```bash
read -r -p "E-mail do administrador: " ADMIN_EMAIL
read -r -s -p "Senha do administrador (minimo 12 caracteres): " ADMIN_PASSWORD
echo
export ADMIN_EMAIL ADMIN_PASSWORD
docker compose --env-file backend/.env exec -e ADMIN_EMAIL -e ADMIN_PASSWORD app node scripts/criarAdmin.js
unset ADMIN_PASSWORD
```

Se o e-mail já estiver cadastrado, o script não altera a senha existente. Para fazer login, acesse a página administrativa e use as credenciais criadas.

### 6. Operações úteis

```bash
# Ver logs da aplicação e do banco
docker compose --env-file backend/.env logs -f app db

# Ver status
docker compose --env-file backend/.env ps

# Reconstruir depois de um git pull
git pull
docker compose --env-file backend/.env up -d --build --wait

# Parar mantendo os dados
docker compose --env-file backend/.env down
```

**Nunca use `docker compose down -v` em um banco com dados importantes:** `-v` remove o volume PostgreSQL. Faça backups antes de alterar a configuração ou atualizar o banco.

### Banco já existente (volume anterior)

O PostgreSQL executa scripts em `/docker-entrypoint-initdb.d` **somente quando o diretório de dados está vazio**. Uma instalação antiga mantém seus dados e não recebe o novo esquema automaticamente.

**Faça backup e confira se as tabelas já existem** antes de aplicar o esquema:

```bash
docker compose --env-file backend/.env exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > sisgece-backup.sql
docker compose --env-file backend/.env exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "\dt"'
```

Se o banco anterior **não tiver as tabelas**, aplique o arquivo SQL sem apagar o volume:

```bash
docker compose --env-file backend/.env exec -T db sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < db/init/001_schema.sql
```

Esse comando de redirecionamento é para Bash/Linux; no Windows use um terminal Bash/WSL. O SQL cria as tabelas que faltarem, mas **não migra formatos de tabelas existentes**. Se já houver tabelas com estrutura diferente, revise antes de aplicar em produção.

### Se algo não iniciar

1. Execute `docker compose --env-file backend/.env config -q`. Se falhar, confira `PGUSER`, `PGPASSWORD`, `PGDATABASE` e `JWT_SECRET` no arquivo `backend/.env`.
2. Consulte `docker compose --env-file backend/.env logs --tail=100 app db`.
3. Se a API estiver `unhealthy`, teste `/api/ready` e confira as tabelas.
4. Se a porta 8004 estiver ocupada, libere-a no host; a configuração padrão do projeto usa **8004:3000**.
5. Alterar a senha do PostgreSQL no `.env` após o banco ter sido inicializado **não muda automaticamente a senha gravada no volume**.

## Estado da integração

A interface principal usa dados de demonstração no navegador (`CONFIG.USE_MOCK = true` em `frontend/assets/js/app.js`). Ela ainda **não persiste solicitações no PostgreSQL**.

O painel de `/pages/admin-login.html` utiliza a API real, autenticação JWT e análise de solicitações. A interface principal espera um contrato diferente do backend atual; apenas mudar `USE_MOCK` não resolve a integração.

**Atenção ao uso público:** as rotas legadas de estudantes e responsáveis ainda precisam de um modelo completo de autenticação e autorização para dados pessoais. Não use informações reais de estudantes em uma implantação pública antes de revisar esses controles, HTTPS e política de acesso.

## Executar sem Docker (desenvolvimento)

Requer Node.js 20+ e um PostgreSQL configurado separadamente para as rotas persistentes:

```bash
npm ci --prefix backend
cp backend/.env.example backend/.env
# Edite backend/.env antes de iniciar.
npm start --prefix backend
```

A interface de demonstração fica em http://localhost:3000. Para iniciar com o esquema, execute `db/init/001_schema.sql` no banco PostgreSQL configurado.

## Estrutura

```text
Dockerfile                    Imagem do backend e frontend estático
docker-compose.yml            Aplicação e PostgreSQL
db/init/001_schema.sql        Esquema inicial para banco novo
backend/app.js                API Express e health/readiness
backend/scripts/criarAdmin.js Cadastro manual de administrador
backend/src/                  Rotas, controllers, autenticação e conexão
frontend/                     Interface de demonstração e painel admin
.github/workflows/            Smoke test Docker em pull requests
```

## Equipe

Mario — Tech Leader; Gilvan, Miguel, Miguel, Socrates e Wendel — Desenvolvimento FullStack. O histórico original foi preservado no repositório consolidado.

## Licença

A licença geral do projeto ainda não foi definida.

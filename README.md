# SISGECE · IFCE Campus Maranguape

Sistema de Gerenciamento de Entrada e Saída de Estudantes. Esta versão acompanha saídas pontuais. Na página inicial, aluno ou responsável informa os dados declarados e recebe um protocolo e um código secreto. Guarde ambos. O recibo indica que o pedido foi salvo. A coordenação verifica identidade, filiação e autorização pelos procedimentos institucionais antes de decidir.

Em **Área do funcionário**, a coordenação pode buscar, analisar, escrever mensagem pública e manter observações internas. A recepção confere a autorização aprovada. A portaria registra a saída efetiva depois da recepção. Cada confirmação identifica o funcionário e o instante no histórico. O superusuário administra contas e análises. As confirmações operacionais exigem o perfil da etapa. Reabrir uma análise invalida as duas etapas; corrigir a recepção também invalida a portaria. Os eventos anteriores permanecem disponíveis.

## Instalação nova com Docker

No PowerShell com Docker Desktop em modo Linux, ou no terminal Linux com Docker Engine, execute os comandos a partir da raiz do repositório. Reserve os nomes abaixo para esta instalação. Crie dois arquivos locais UTF-8, um valor por linha. Substitua SENHA_GERADA por uma senha longa aleatória idêntica em ambos.

**db.env.local**
```ini
POSTGRES_DB=sisgece
POSTGRES_USER=sisgece
POSTGRES_PASSWORD=SENHA_GERADA
```

**app.env.local**
```ini
PGHOST=sisgece-db
PGPORT=5432
PGDATABASE=sisgece
PGUSER=sisgece
PGPASSWORD=SENHA_GERADA
```

No Linux proteja esses arquivos com `chmod 600 *.env.local`. No Windows restrinja o acesso ao operador usando as permissões NTFS. Os parâmetros PG* são lidos diretamente pelo cliente PostgreSQL. A aplicação exige acesso de escrita e permissão para migrar as tabelas. É possível provisionar um banco e um usuário proprietário dedicados em um PostgreSQL administrado.

```sh
docker network create sisgece-net
docker volume create sisgece-dados
docker build -t sisgece:python .
docker run -d --name sisgece-db --network sisgece-net --restart unless-stopped --env-file db.env.local -v sisgece-dados:/var/lib/postgresql/data postgres:17
docker exec sisgece-db pg_isready -U sisgece -d sisgece
```

Aguarde o banco aceitar conexões. Escolha o comando de aplicação conforme o ambiente.

**Teste em localhost no Windows** (PowerShell, uma linha). LOCAL_HTTP=1 permite o cookie em HTTP no computador de teste.

```powershell
docker run -d --name sisgece-app --network sisgece-net --restart unless-stopped --env-file app.env.local -e LOCAL_HTTP=1 -p 127.0.0.1:8004:3000 sisgece:python
```

**Servidor Linux da rede interna** (com HTTPS). A aplicação usa cookies Secure por padrão. Configure no DNS interno o nome do servidor, ajuste o domínio em deploy/Caddyfile e configure o Caddy no host para encaminhar ao endereço abaixo. Use certificado institucional ou CA interna confiável nas estações. Libere a porta 443 para a rede autorizada e mantenha PostgreSQL e a porta 8004 privados. Não use LOCAL_HTTP em produção.

```sh
docker run -d --name sisgece-app --network sisgece-net --restart unless-stopped --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges --env-file app.env.local -p 127.0.0.1:8004:3000 sisgece:python
```

Crie explicitamente o primeiro superusuário e informe nome, e-mail e senha no terminal interativo.

```sh
docker exec -it sisgece-app python backend/manage.py superuser
```

Abra http://localhost:8004 no teste local ou o domínio HTTPS no servidor. Entre em Área do funcionário e crie as contas da coordenação, recepção e portaria. A desativação e as mudanças de perfil invalidam as sessões da conta. O sistema preserva a identificação de quem atuou.

## Atualização e migração

Pare a aplicação antiga antes da migração. Identifique o banco, versão principal do PostgreSQL, rede e volume existentes com `docker inspect sisgece-db`. Mantenha esse banco e suas credenciais. Criar outro volume fará a instalação parecer vazia. Faça backup e ensaie a restauração antes da atualização. Use o procedimento de backup abaixo com os nomes reais do banco e usuário.

A inicialização aplica os scripts numerados de db em uma transação protegida por bloqueio. A tabela versoes controla reaplicações. A migração mantém IDs, estudantes, responsáveis, vínculos institucionais, datas e decisões. Copia os dados disponíveis no legado para consulta interna, com protocolo LEG-id. Como nenhum segredo foi entregue originalmente, esses registros ficam disponíveis somente à equipe. Tipos antigos diferentes de saída permanecem históricos. As contas antigas mantêm o estado ativo e o hash bcrypt e passam a coordenação. Crie uma conta distinta pelo comando superuser e revise os perfis. Sessões antigas exigem novo login.

Construa a imagem com outra etiqueta, pare e renomeie apenas o contêiner da aplicação, depois repita o comando docker run correspondente apontando para a imagem nova e o mesmo banco. Exemplo:

```sh
docker build -t sisgece:atualizada .
docker stop sisgece-app
docker rename sisgece-app sisgece-app-anterior
```

## Backup, restauração e diagnóstico

```sh
docker exec sisgece-db pg_dump -U sisgece -d sisgece -Fc -f /tmp/sisgece.dump
docker cp sisgece-db:/tmp/sisgece.dump ./sisgece.dump
docker logs --tail 100 sisgece-app
docker logs --tail 100 sisgece-db
docker inspect --format "{{.State.Health.Status}}" sisgece-app
```

Guarde o dump com acesso restrito. Para verificar restauração, copie-o para um banco de teste e restaure em um banco vazio separado:

```sh
docker cp ./sisgece.dump sisgece-db:/tmp/restaurar.dump
docker exec sisgece-db createdb -U sisgece sisgece_restaurado
docker exec sisgece-db pg_restore --exit-on-error -U sisgece -d sisgece_restaurado /tmp/restaurar.dump
```

Se uma migração falhar, examine os logs, confirme PGHOST, credenciais, rede e privilégios, corrija e reinicie a aplicação. Para reverter após a migração, restaure o backup anterior em banco separado e aponte a versão anterior para esse banco após verificar os dados. Avalie separadamente solicitações registradas depois do backup. O endpoint /api/ready verifica acesso ao esquema.

## Testes

Use Python 3.12 e PostgreSQL descartável. Configure PGHOST, PGPORT, PGDATABASE, PGUSER e PGPASSWORD para esse banco. No PowerShell use, por exemplo, `$env:PGHOST='localhost'`. A suíte cria e remove um esquema exclusivo. O teste de navegador envia pedidos fictícios na aplicação indicada por TEST_URL (padrão http://127.0.0.1:8004).

```sh
python -m pip install -r requirements.txt playwright
python -m unittest discover -s tests -v
python -m playwright install chromium
python tests/browser.py
```

A CI exercita PostgreSQL 17, a imagem Docker e Chromium. O navegador usa apenas arquivos locais ao servidor. O limite de tentativas é compartilhado no banco por endereço de conexão, em janelas de dez minutos. Atrás de proxy, clientes do mesmo proxy compartilham esse limite. A aplicação ignora cabeçalhos de IP enviados pelo cliente.

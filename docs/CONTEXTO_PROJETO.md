# SISGECE — contexto técnico para transferência entre IAs e desenvolvedores

> **Fotografia do repositório em 17/11/2026.** Base: arquivos da branch `main`, README, documentação de implantação e PR #9. **Não é um atestado do estado do servidor**: código versionado, recurso em PR, testes, homologação e produção são estados diferentes.

## 1. Identificação e objetivo

- **Nome:** SISGECE — Sistema de Gerenciamento de Entrada e Saída de Estudantes.
- **Instituição atendida:** Instituto Federal do Ceará (IFCE), Campus Maranguape.
- **Repositório:** https://github.com/socratesmarques/sisgece
- **Finalidade:** permitir que alunos/responsáveis façam pedidos de entrada ou saída sem conta e acompanhem o resultado por código, enquanto funcionários autorizados analisam pedidos e registram o fluxo operacional de saídas.
- **Públicos:** alunos, responsáveis, coordenação, recepção, portaria e superusuário.
- **Premissa crítica:** o formulário registra uma declaração; não comprova por si só identidade, filiação, autorização ou movimentação física. Conferências institucionais continuam sendo necessárias.

## 2. Matriz de maturidade: o que está onde

| Capacidade | Situação verificada em 17/11/2026 | Evidência |
| --- | --- | --- |
| Solicitar Entrada e Saída | Implementado na `main` | `backend/app.py`, `frontend/templates/home.html` |
| Consultar pedido por código de 10 caracteres | Implementado na `main`; há compatibilidade com recibos antigos | `backend/app.py` |
| Aprovar/reprovar entradas e saídas | Implementado na `main`; reprovação exige mensagem | `backend/app.py`, `db/006.sql` |
| Conferir saída na recepção e na portaria | Implementado na `main`, apenas para saídas aprovadas | `backend/app.py` |
| Histórico de eventos e correções | Implementado na `main` | `backend/app.py`, `db/002.sql` |
| Login e gestão de contas por perfil | Implementado na `main` | `backend/app.py`, `backend/manage.py` |
| Máscaras de CPF/telefone e parentesco | Integrado à `main` no PR #8 | `frontend/static/main.js`, template |
| Notificações WhatsApp | **PR #9 aberto, NÃO integrado à `main`** | https://github.com/socratesmarques/sisgece/pull/9 |
| Envio real de WhatsApp e homologação com a Meta | **Não realizado no PR #9** | `docs/NOTIFICACOES.md` na branch do PR |
| Versão e integridade do serviço institucional atualmente em execução | **Não verificado neste levantamento** | Exige acesso autorizado ao servidor |

Outras referências: PR #6 (análise de entradas) e PR #7 (restauração da interface) foram mesclados; PR #5 foi encerrado **sem** merge. Não extrapolar funcionalidades de branches encerradas ou abertas para `main`.

## 3. Stack e arquitetura

**Versões diretas verificadas** em `requirements.txt` e no Dockerfile:

| Camada | Tecnologia |
| --- | --- |
| Linguagem | Python 3.12 (`python:3.12-slim`) |
| Web/API | Flask 3.1.3 |
| Servidor WSGI | Waitress 3.0.2 |
| Persistência | PostgreSQL 17; `psycopg[binary] 3.3.8` |
| Senhas/sessões | bcrypt (compatibilidade legada), hashing de senha Werkzeug; tokens aleatórios de sessão armazenados como hash |
| Templates/UI | Jinja2, HTML, CSS e JavaScript puro |
| Aplicação | Docker; usuário de sistema `sisgece` sem root |
| Transporte de produção recomendado | Proxy reverso HTTPS (exemplo Caddy em `deploy/Caddyfile`) |
| Testes | `unittest`, PostgreSQL descartável, Playwright/Chromium, GitHub Actions |

Fluxo de alto nível:

```text
Navegador (aluno/responsável ou funcionário)
    -> HTTPS / proxy institucional (quando implantado)
    -> aplicação Waitress/Flask :3000
    -> PostgreSQL (solicitações, sessões, limites, eventos)
```

Referência de execução Docker: porta do host `127.0.0.1:8004` encaminha para a porta 3000 da aplicação. O PostgreSQL não deve ser publicado para a Internet. A configuração real do servidor pode ser diferente: inspecionar antes de prescrever comandos.

### Arquivos principais

| Caminho | Responsabilidade |
| --- | --- |
| `backend/app.py` | Rotas Flask, validação, autenticação, papéis, regras de solicitações e auditoria |
| `backend/manage.py` | Aplicar migrações e criar primeiro superusuário interativamente |
| `frontend/templates/home.html` | Página pública e área de funcionários |
| `frontend/static/main.js`, `main.css` | Requisições, máscaras, interatividade e estilos |
| `db/*.sql` | Migrações SQL numeradas |
| `Dockerfile`, `requirements.txt` | Empacotamento e dependências |
| `tests/` | Integração, rotinas HTTP/SQL e testes de navegador |
| `deploy/Caddyfile`, `deploy/ATUALIZACAO.md` | Exemplo de proxy e roteiro de atualização com backup |
| `docs/BRIEFING_RAPIDO.md` | Versão curta deste contexto |

## 4. Regras de negócio que não devem ser quebradas

### Solicitação pública

1. A origem declarada pode ser `Aluno` ou `Responsável`; o formulário solicita nome, matrícula, responsável/filiação, telefone, data, hora, justificativa e tipo de movimentação. Quando a origem é Responsável, há campos de CPF e parentesco.
2. O backend valida dados e cria uma solicitação com estado inicial `PENDENTE`.
3. O solicitante recebe a confirmação de cadastro e acompanha o andamento pelo WhatsApp quando habilitado.

### Decisão institucional

- Coordenação e superusuário podem analisar pedidos pendentes.
- **Aprovação** muda a situação para `APROVADA`; **reprovação** para `REPROVADA` e exige mensagem visível ao solicitante.
- Observação interna, mensagem pública, autor e histórico não são equivalentes; preserve a separação.
- Aprovar uma **Entrada** não registra entrada física. O fluxo de entrada não passa por recepção/portaria.

### Saídas e conferências

- Apenas **Saída APROVADA** pode passar pela recepção, seguida da portaria.
- A recepção marca `recepção confirmada`; a portaria marca `saída concluída`.
- Cada etapa exige o perfil específico, identifica funcionário e instante.
- Reabrir análise zera as etapas de uma saída. Corrigir recepção invalida portaria; corrigir portaria volta à etapa anterior. Eventos antigos permanecem no histórico.
- Pedidos legados de outros tipos são históricos, não objetos de novas operações.

### Contas e acesso

- Perfis: `coordenação`, `recepção`, `portaria`, `superusuário`.
- O superusuário gerencia contas e auditoria administrativa. Contas desativadas ou com perfil alterado têm sessões invalidadas; não é permitido remover o último superusuário ativo.
- Recepção e portaria veem apenas o necessário para saídas aprovadas, com ocultação de campos privados em detalhes.
- Eventos são atribuídos ao operador; decisões simultâneas são serializadas com bloqueios transacionais.

## 5. Modelo de dados e migrações

- O PostgreSQL guarda `solicitacoes`, `administradores`, `sessoes`, `eventos`, `limites` e tabelas legadas de estudantes, responsáveis e vínculos.
- Dados declarados do pedido ficam em `solicitacoes.declarado` como JSONB, junto de campos estruturados para estado, tipo, protocolo, código hasheado, análise e etapas.
- A tabela `versoes` registra scripts aplicados; `backend/manage.py migrate` executa os arquivos SQL em ordem sob bloqueio transacional.
- **`001.sql`** estabelece esquema inicial; **`002.sql`** introduz JSONB, etapas, eventos, sessões e limites; **`003.sql`** indexa consulta; **`004.sql`** adapta estados de entrada; **`005.sql`** cria usuários derivados de e-mails legados; **`006.sql`** migra entradas antigas `RECEBIDA` para `PENDENTE`.
- Migração **`007` de notificações existe no PR #9**, não na `main` observada.

**Nunca** recrie volume para uma atualização normal ou aponte produção para um banco vazio. Antes de aplicar migrações, identificar banco, rede, volume e versão efetivos; fazer `pg_dump`, validar uma restauração separada e registrar plano de retorno.

## 6. API principal da `main`

| Método | Rota | Finalidade |
| --- | --- | --- |
| GET | `/`, `/equipe` | Formulário público e área do funcionário |
| GET | `/api/ready` | Readiness com consulta ao esquema do banco |
| POST | `/api/solicitar` | Criar solicitação |
| POST | `/api/login`, `/api/logout` | Sessão do funcionário |
| GET | `/api/me` | Funcionário autenticado |
| GET | `/api/pedidos`, `/api/pedidos/<id>` | Listar e detalhar pedidos com permissões |
| POST | `/api/pedidos/<id>` | Aprovar, reprovar, registrar ou corrigir etapas |
| GET | `/api/historico` | Histórico de ações |
| GET, POST | `/api/contas` | Contas administrativas (conforme rota e perfil) |
| GET | `/api/auditoria` | Auditoria administrativa do superusuário |

Nas requisições POST JSON, o backend exige o cabeçalho `X-SISGECE: 1`. Não substituir validações de backend apenas por condições na interface.

## 7. Segurança, privacidade e implantação

- Sessões por cookie HttpOnly, SameSite Strict e Secure fora de `LOCAL_HTTP=1`. O token de sessão é aleatório, armazenado em hash e validado junto com a conta ativa.
- Em HTTPS, há HSTS e outros cabeçalhos defensivos; é necessário validar certificados, DNS e configuração de proxy na instalação real.
- `SISGECE_PROXY_SECRET` autentica o endereço encaminhado pelo proxy, evitando confiar em cabeçalhos fornecidos pelo cliente. Nunca publicá-lo.
- Limites de tentativa residem no PostgreSQL em janelas de dez minutos; logins válidos não consomem o contador de falhas.
- O Dockerfile executa em usuário não-root; o guia de deploy recomenda `--read-only`, `--tmpfs /tmp`, redução de capabilities e banco/porta da aplicação privados.
- Dados incluem informações de estudantes e responsáveis. Exigir controle institucional sobre acesso, finalidade, retenção, backups e notificações; evitar usar dados reais em testes.
- **Atenção:** “tem Docker e HTTPS no README” não significa “está homologado/seguro para produção”. O estado do serviço institucional precisa de inspeção autorizada.

### Situação operacional conhecida x desconhecida

Há histórico de uso de Ubuntu/Linux, Docker, PostgreSQL e proxy Caddy no ambiente institucional; os nomes `sisgece-app` e `sisgece-db` aparecem nos procedimentos. **Este documento não verificou o host em execução** nem sua versão, portas ativas, certificado ou domínio definitivo. Antes de agir: conferir `git rev-parse HEAD`, `docker ps`, `docker inspect`, health/readiness, logs e proxy **sem divulgar segredos**.

## 8. Desenvolvimento e testes isolados

Preferência para desenvolvimento local: **WSL2/Ubuntu**, Python 3.12, ambiente virtual Python, PostgreSQL 17 descartável ou Docker isolado. Não misturar dados de produção.

Com PostgreSQL de teste configurado via variáveis `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt playwright
python -m unittest discover -s tests -v
python -m playwright install chromium
# Com a instância de teste iniciada:
TEST_URL=http://127.0.0.1:8004 python tests/browser.py
```

O backend também pode ser executado em Docker conforme o README. Em teste HTTP local, `LOCAL_HTTP=1` habilita cookie sem Secure **somente em localhost**. O `/api/ready` e os logs ajudam a diagnosticar inicialização. Não executar o comando de testes contra o banco institucional.

A contagem de testes é sensível à branch; não apresentar o total do PR #9 como se fosse resultado da `main` sem executá-la.

## 9. Notificações WhatsApp — PR #9 (não mesclado)

**Objetivo:** informar o solicitante pelo WhatsApp sobre a criação do pedido e as mudanças de situação.

**Escopo presente na branch `feat/notificacoes-whatsapp`:**

- Consentimento versionado, escolha do titular, prova de controle do telefone via desafio e revogação; nenhum opt-in automático para registros antigos.
- Migração aditiva `007`, tabelas de assinatura, desafios e **outbox** transacional PostgreSQL.
- Worker independente, `FOR UPDATE SKIP LOCKED`, tentativas limitadas, backoff, limites de ritmo e estado `uncertain` para despachos ambíguos.
- **Mock** local padrão, sem chamadas externas. Provedor opcional da **WhatsApp Cloud API oficial da Meta**, templates e webhooks autenticados com HMAC-SHA256.
- Interface para optar, confirmar e revogar; registros de envio restritos à coordenação e superusuário.
- PR informa **25 testes automatizados aprovados**, roteiros de navegador e CI final aprovada; isso é **evidência de validação técnica do PR**, não de integração, envio real ou homologação institucional.

**Limites decisivos:** sem ativação real da Meta, templates homologados, política institucional para menores/consentimento, orçamento e acesso público controlado ao webhook, **não enviar mensagens reais**. Não há garantia de entrega externa exatamente uma vez; mensagens `uncertain` não podem ser reenviadas cegamente. Não existe estado institucional de cancelamento de solicitação — `cancelled` no PR é estado de notificação.

Leitura essencial na branch do PR: [documentação de notificações](https://github.com/socratesmarques/sisgece/blob/feat/notificacoes-whatsapp/docs/NOTIFICACOES.md), [validação](https://github.com/socratesmarques/sisgece/blob/feat/notificacoes-whatsapp/docs/VALIDACAO-NOTIFICACOES.md), [PR #9](https://github.com/socratesmarques/sisgece/pull/9).

## 10. Prioridades e pendências

1. Revisar o PR #9 e validar seu fluxo mock no WSL/Ubuntu em **banco de teste separado**, sem credenciais Meta ou serviços pagos.
2. Confrontar versão realmente implantada com `main` antes de qualquer atualização, preservando a instalação institucional.
3. Planejar homologação funcional com perfis reais de operador, privacidade/retenção, acesso por HTTPS, backups, auditoria e procedimentos institucionais.
4. Para adoção futura do WhatsApp, obter decisões institucionais sobre destinatários menores de idade, opt-in, textos, orçamento, templates, retenção e exposição restrita do webhook.
5. Revalidar testes e documentação após merges, mudanças de dependências ou alterações na infraestrutura.

**Não assuma que esses itens já foram concluídos.** Registre o resultado, o commit, a data e a evidência quando forem verificados.

## 11. Como usar este contexto em outra conversa

1. Forneça [BRIEFING_RAPIDO.md](BRIEFING_RAPIDO.md) para orientar rapidamente.
2. Acrescente este arquivo para decisões de implementação, arquitetura e operação.
3. Informe explicitamente qual **branch/commit**, **ambiente** (WSL, teste, homologação ou produção) e **tarefa** serão abordados.
4. Peça ao assistente que consulte o código e os PRs atuais em vez de tratar este retrato datado como verdade permanente.
5. Exija distinção entre código escrito, testes executados, revisão aprovada, merge realizado e implantação verificada.

### Prompt de continuação

> Assuma o SISGECE como projeto existente, não como aplicativo a reescrever. Use os arquivos `docs/BRIEFING_RAPIDO.md` e `docs/CONTEXTO_PROJETO.md` como ponto de partida, mas valide o código e o estado dos PRs na branch relevante. Preserve fluxo de Entrada/Saída, perfis, consulta por código, histórico, transações e dados institucionais. Não confunda o PR #9 com produção. Ao propor alterações, apresente arquivos impactados, migrações, testes, segurança e rollback. Ambiente de trabalho: **[informar]**. Tarefa: **[informar]**.

## 12. Referências e manutenção deste documento

Fontes primárias da `main`: [README](../README.md), [backend/app.py](../backend/app.py), [backend/manage.py](../backend/manage.py), [requirements.txt](../requirements.txt), [Dockerfile](../Dockerfile), [frontend](../frontend/), [db](../db/), [roteiro de atualização](../deploy/ATUALIZACAO.md).

**Política de atualização:** revise o briefing e este contexto após merges que alterem arquitetura, regras de negócio, banco, autenticação, implantação ou WhatsApp. Atualize a data e os estados de PR/produção; não acrescente segredos nem dados reais.

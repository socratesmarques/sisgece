# Notificações WhatsApp

## Escopo e garantias

O recurso complementa a consulta pelo código. Não muda aprovação, reprovação,
recepção, portaria ou reabertura. Não existe cancelamento institucional de pedido
no SISGECE; `cancelled` é somente um estado de notificação.

Telefone já existente em `solicitacoes.declarado.telefone` é normalizado para E.164
nos novos cadastros. Não há outro campo de telefone no formulário nem na assinatura.
A fila conserva o destinatário do envio. Registros antigos não recebem opt-in.

O solicitante escolhe se o titular é solicitante ou responsável, aceita o texto
versionado e recebe o código habitual. O titular envia `CONFIRMAR <desafio>` pelo
próprio WhatsApp para o número institucional. O desafio é independente do código
de consulta, expira em 15 minutos e só funciona uma vez. O banco guarda seu hash.
A comparação usa o telefone informado pela Meta em um webhook autenticado. Se a
Meta omitir esse telefone (por exemplo, identificação somente por BSUID), a
ativação é recusada de forma segura. Não inferimos vínculo por nome ou username.
A confirmação comprova controle do número, não identidade, filiação ou autorização
de saída; a verificação institucional existente continua necessária.

A revogação pode ser feita após consultar pelo código ou enviando PARAR, SAIR ou
STOP do telefone verificado ao número institucional. Pelo WhatsApp, interrompe
todas as assinaturas Meta desse telefone. Nenhuma mensagem de resposta é disparada.
O portal mostra o estado atualizado. Uma autorização revogada não é reativada
automaticamente. Não se pode recolher uma mensagem já despachada.

## Arquitetura

`backend/notifications/` contém configuração, consentimento, normalização,
outbox, provedores, worker, webhook, rotas e ferramentas do operador.

1. A rota valida o perfil e bloqueia a solicitação, como antes.
2. A decisão, o evento de histórico e a fila são gravados na mesma transação.
3. Um worker usa `FOR UPDATE SKIP LOCKED` para reservar uma pendência.
4. Revalida consentimento, verificação, telefone e situação antes de despachar.
5. Grava o resultado sem expor payloads ou credenciais em logs.
6. Webhooks atualizam a entrega, inclusive se chegarem antes da resposta HTTP.

Falhas da Meta nunca entram no caminho HTTP de aprovação. Se o próprio PostgreSQL
não puder gravar o evento/fila, a transação falha integralmente: não se confirma
uma aprovação perdendo sua notificação silenciosamente.

Unicidade `(evento, canal, assinatura)` evita duplicação local. Não há unicidade
por status: uma nova aprovação após reabertura é um novo evento legítimo.
Mudanças novas cancelam avisos antigos ainda não despachados. Não se envia uma
rajada de etapas antigas depois de o titular confirmar o número. Sem confirmação,
a pendência não é enviada; avisos expiram após 24 horas. Esses prazos devem ser
validados pela instituição antes da ativação real.

Estados: `pending`, `processing`, `sent` (aceita pelo provedor), `delivered`,
`failed`, `cancelled`, `uncertain`. Mock registra `sent`, sem alegar entrega real.
`read` no webhook comprova entrega e é reduzido a `delivered`; não armazenamos
histórico de leitura individual.

Há no máximo cinco tentativas, com backoff de 30 segundos exponencial até uma hora
mais jitter; `Retry-After` numérico da API é respeitado até 24 horas. Ritmo persistido: um despacho por segundo por provedor e intervalo
mínimo de seis segundos por telefone. São limites locais conservadores, não uma
promessa de quota da Meta. Erros de limite podem reduzir a capacidade efetiva.

Reservas duram 120 segundos. Após queda, reservas anteriores ao despacho voltam
para `pending`; se o despacho já pode ter ocorrido, passam a `uncertain`.
Timeout, resposta inválida e HTTP 5xx ambíguo não causam reenvio cego. Rejeições
explícitas por limite e falhas comprovadamente anteriores à conexão têm retry.
Falha assíncrona de entrega fica `failed`, sem reenvio automático.

**Limite distribuído:** não há garantia de exatamente uma entrega externa se a
Meta aceitar a mensagem e a resposta se perder. Sem ID externo, o operador deve
investigar; não associamos eventos por telefone/horário e não oferecemos botão
para reenviar resultados incertos. A consulta pelo código permanece disponível.
Uma alteração ou revogação depois de autorizado/iniciado o despacho não consegue
interromper com certeza essa chamada em andamento.

## Desenvolvimento sem custos

Use Python 3.12 e PostgreSQL 17 descartável. Instale em venv:

```sh
python -m venv work/venv
. work/venv/bin/activate
pip install -r requirements.txt playwright
export PGHOST=127.0.0.1 PGPORT=5432 PGUSER=postgres
# Configure PGPASSWORD e PGDATABASE para o banco exclusivo de desenvolvimento.
export NOTIFICATIONS_PROVIDER=mock WHATSAPP_REAL_SEND_ENABLED=0 LOCAL_HTTP=1
python backend/manage.py migrate
waitress-serve --listen=127.0.0.1:8004 backend.app:app
```

Em outro terminal com o mesmo ambiente:

```sh
python -m backend.notifications.worker
# Ou uma reserva/tentativa por execução:
python -m backend.notifications.worker --once
```

Crie um pedido fictício com opt-in. Clique em “Confirmar número no WhatsApp”. No
mock, não aparece link para enviar mensagem real. Copie somente o token exibido:

```sh
python -m backend.notifications.admin mock-confirm
```

A ferramenta pede token e telefone fictício via entrada oculta. Só aceita
assinaturas mock. Atualize a confirmação no portal. Para inspecionar o conteúdo
padronizado, sem imprimir telefone:

```sh
python -m backend.notifications.admin stats
python -m backend.notifications.admin mock-preview --id 1
```

`NOTIFICATIONS_MOCK_OUTCOME` pode ser `success`, `temporary`, `permanent` ou
`timeout`. Reinicie o worker ao alterar o ambiente. O resultado mock nunca é
convertido em despacho real, mesmo quando se muda o provedor configurado.

## Testes

Somente em banco descartável, nunca produção. A suíte unittest cria e remove
esquemas próprios; navegador usa a aplicação indicada e cria dados fictícios.

```sh
python -m unittest discover -s tests -v
python -m playwright install chromium
TEST_URL=http://127.0.0.1:8004 python tests/browser.py
TEST_URL=http://127.0.0.1:8004 python tests/browser_notifications.py
```

Para Chromium já instalado: `BROWSER_EXECUTABLE=/usr/bin/chromium`. O novo roteiro
exige servidor mock e nenhum worker em paralelo, pois controla o processamento.
As rotas reais são testadas com transporte HTTP substituído. A suíte não precisa
de credenciais nem chama a Meta. Resultados em `VALIDACAO-NOTIFICACOES.md`.

## Configuração futura da Meta (manual)

Não executada por esta implementação. Exige aprovação institucional de tratamento
de dados e orçamento, conta empresarial e número institucional adequados.

1. Configure a conta WhatsApp Business, aplicativo e número na Meta. Gere token
   de sistema com as permissões necessárias, incluindo `whatsapp_business_messaging`.
   Guarde credenciais somente no ambiente restrito, nunca no Git ou no navegador.
2. Escolha uma versão suportada da Graph API e informe `WHATSAPP_API_VERSION`
   explicitamente (formato `vNN.0`). Valide a versão na homologação da instituição.
3. Crie e obtenha aprovação dos quatro templates abaixo, idioma `pt_BR`, sem
   variáveis pessoais ou componentes dinâmicos. Configure os nomes aprovados nas
   variáveis `WHATSAPP_TEMPLATE_*`. O ID de template pode permanecer nulo: a API
   de envio identifica o template por nome e idioma. O tipo e nome utilizados
   ficam fixados no registro da fila. Não altere o conteúdo aprovado sem revisão.
4. Configure WABA ID, Phone Number ID, número institucional (DDI+DDD+número,
   apenas dígitos), app secret e verify token aleatório com pelo menos 32 caracteres.
5. Publique **somente** `/api/notificacoes/webhook` com HTTPS publicamente acessível
   e certificado válido. Uma CA apenas interna não atende à Meta. Preserve o
   acesso restrito das demais rotas, a porta local da aplicação e o banco privado.
6. Cadastre o callback e o verify token e assine o campo `messages`. O GET valida
   o challenge; o POST exige HMAC-SHA256 dos bytes originais. Não use o verify
   token como substituto do app secret. Não registre query strings do GET no proxy.
7. Configure `NOTIFICATIONS_PROVIDER=meta` na aplicação e no worker. Primeiro
   mantenha `WHATSAPP_REAL_SEND_ENABLED=0`: o worker Meta recusa iniciar. Só após
   autorização explícita do operador, configure `1` no worker e inicie-o.
   Isso é uma ação operacional futura, não parte da implantação automática.

Templates propostos (os textos exatos estão em `outbox.py`):

| Variável | Nome padrão | Uso |
|---|---|---|
| `WHATSAPP_TEMPLATE_CADASTRO` | `sisgece_cadastro` | Recebimento |
| `WHATSAPP_TEMPLATE_APROVACAO` | `sisgece_aprovacao` | Aprovação |
| `WHATSAPP_TEMPLATE_ATUALIZACAO` | `sisgece_atualizacao` | Reprovação, reabertura e correções |
| `WHATSAPP_TEMPLATE_ETAPA` | `sisgece_etapa` | Recepção e portaria |

Solicite classificação apropriada para avisos transacionais; aprovação e categoria
final são decididas pela Meta. Não há envio livre de texto como fallback de template
rejeitado. Nenhuma mensagem inclui nome, CPF, matrícula, justificativa ou código.

## Docker e atualização

Use a mesma imagem do app, banco e rede existentes. O Dockerfile garante leitura
do código pelo usuário não-root mesmo em checkouts com permissões restritas. O worker não publica portas e
não executa migrações. Aplique 007 pela inicialização do app antes de iniciá-lo:

```sh
docker run -d --name sisgece-notifications --network sisgece-net \
  --restart unless-stopped --read-only --tmpfs /tmp --cap-drop ALL \
  --security-opt no-new-privileges --no-healthcheck \
  --env-file app.env.local sisgece:atualizada \
  python -m backend.notifications.worker
```

`--no-healthcheck` retira o healthcheck HTTP herdado, inadequado para um worker.
Monitore processo/container e idade da fila com `admin stats`; processo ativo
sozinho não comprova progresso. A flag de envio real deve existir apenas nos
contêineres que precisam enviar. Um arquivo separado para o worker pode conter
seu token; o app precisa dos segredos de webhook, não do token de envio.

Para atualizar: construa a imagem; pare app e worker; faça backup/restauração de
ensaio conforme `deploy/ATUALIZACAO.md`; substitua o app; confirme 007 e readiness;
substitua o worker com a mesma imagem; verifique fila e fluxos em homologação.
Não crie outro volume de produção. Na primeira implantação mantenha mock.
Em retorno à versão anterior, pare também o worker e preserve o banco migrado.
Não reproduza uma fila restaurada contra a Meta: pode conter envios já realizados
após o backup. Concilie antes de qualquer reativação real.

## Monitoramento e privacidade

Coordenação/superusuário veem os últimos 50 resultados no detalhe do pedido;
recepção/portaria não acessam esses registros. Não há telefone, token, código de
consulta ou resposta bruta da Meta nessa lista. Códigos de erro são sanitizados.

- `pending`: verificar confirmação, vencimento, próxima tentativa e se o worker
  usa o provedor correspondente. Credenciais inválidas não devem disparar retries.
- `processing` além de 120 s: verificar processo/banco; recuperação ocorre no
  próximo ciclo. Não executar UPDATE manual para reenviar um despacho incerto.
- `uncertain`: investigar aceitação/entrega; preservar evidência e não reenviar.
- `failed`: conferir código, template aprovado, idioma, credenciais e limites.
- Webhook 403: conferir app secret/assinatura ou verify token no GET.
- Webhook 503: configuração incompleta. Banco indisponível também retorna erro,
  sem reconhecer recebimento; a Meta poderá repetir o evento.
- Webhook 413: limite de 1 MiB excedido. Avaliar lotes na homologação antes de
  ampliar o limite, sem alterar o limite de 16 KiB das demais rotas.

O módulo não define sozinho a política legal de retenção. Antes do envio real,
a instituição deve aprovar texto de consentimento, legitimidade da autorização
quando há menores, prazos de retenção, transferência/tratamento pela Meta,
responsáveis pelo atendimento e orçamento. Não há promessa de conformidade LGPD
apenas por existir checkbox. Proteja banco, backups e arquivos de ambiente.
Não cole dados reais nos testes. Desafios vencidos deixam de funcionar mesmo
quando o registro permanece no banco. Defina rotina de expurgo com a instituição;
a fila e os comprovantes não são apagados automaticamente nesta versão.

## Fontes oficiais e custos

Consultadas durante a implementação em novembro de 2026:
- [Messages API](https://developers.facebook.com/documentation/business-messaging/whatsapp/reference/whatsapp-business-phone-number/message-api)
- [Mensagens, opt-in e janela de atendimento](https://developers.facebook.com/documentation/business-messaging/whatsapp/messages/send-messages)
- [Endpoint, assinatura e repetição de webhooks](https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/create-webhook-endpoint)
- [Estrutura e identificadores dos webhooks](https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/reference/messages)
- [Códigos de erro](https://developers.facebook.com/documentation/business-messaging/whatsapp/support/error-codes)
- [Preços](https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing)

A página de preços exigiu login na consulta. Não fixamos preços nem presumimos
gratuidade. Confirme tarifas, categoria, país, limites e condições vigentes na
conta oficial antes de habilitar o envio. Aprovação de templates, cobrança e
testes com conta real não foram executados. Mock é integralmente local e sem
custo de mensagens; infraestrutura local pode ter seus próprios custos.

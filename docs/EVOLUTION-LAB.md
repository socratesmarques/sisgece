# SISGECE — Evolution API e notificações pelo WhatsApp

Esta branch experimental foi criada sobre a PR #9. O provedor Evolution é
uma integração não oficial com WhatsApp Web e pode sofrer restrições da
plataforma. Não implante institucionalmente sem avaliação de segurança,
privacidade, conformidade e autorização do IFCE. Use dados fictícios para
homologação.

## Funcionamento padrão do formulário

A página inicial não exibe checkboxes de WhatsApp. Ao
**enviar uma solicitação pelo site**, o sistema com
`NOTIFICATIONS_PROVIDER=evolution` registra avisos vinculados ao telefone
informado, **sem lista de números permitidos**. O telefone é validado e
normalizado para E.164. Somente a movimentação daquela solicitação gera
mensagens; não existem campanhas nem importação de contatos.

O formulário informa previamente que aquele contato receberá atualizações
por WhatsApp, com possibilidade de revogar pelo código do recibo. A API
preserva recusas explícitas de clientes antigos: enviar
`whatsapp_consent=false` não gera inscrição e não gera avisos quando há recusa explícita.

A nova inscrição recebe `consentimento_versao=2026-11-17-auto-contact`
para distinguir o cadastro de contato dos consentimentos anteriores.
A inscrição não é uma comprovação jurídica de consentimento do titular
do telefone: a instituição deve definir a base legal, a transparência e
um mecanismo de oposição apropriado antes de usar números reais.

Os provedores `mock` e `meta` continuam com as regras anteriores de
autorização. A fila PostgreSQL, a deduplicação, a revogação, os estados,
a expiração de mensagens e o controle de ritmo permanecem ativos.

## Configuração local no WSL

A instância Evolution `sisgece-teste` e o SISGECE devem estar na rede
Docker privada `sisgece-net`. Se necessário, atribua o alias `evolution`
ao contêiner da Evolution:

```sh
docker network connect --alias evolution sisgece-net NOME_DO_CONTAINER_EVOLUTION
```

No **app web**, em `app.evolution.env.local`:

```ini
NOTIFICATIONS_PROVIDER=evolution
LOCAL_HTTP=1
```

No **worker**, em `worker.evolution.env.local` (arquivo com permissão 600):

```ini
NOTIFICATIONS_PROVIDER=evolution
WHATSAPP_REAL_SEND_ENABLED=1
EVOLUTION_LAB_ENABLED=1
EVOLUTION_API_URL=http://evolution:8080
EVOLUTION_INSTANCE=sisgece-teste
EVOLUTION_API_KEY=CHAVE_PRIVADA
```

Não é necessário nem usado `EVOLUTION_ALLOWED_RECIPIENTS`.
`EVOLUTION_LAB_AUTO_FLOW` também não controla mais novas solicitações.
A flag `EVOLUTION_LAB_ENABLED` permanece como habilitação explícita
do transporte experimental. Não compartilhe a chave do worker com o
contêiner web nem no Git ou em logs.

Para aplicar alterações de código, reconstrua a imagem Docker, recrie
o app web e o worker com os env-files existentes e preserve o PostgreSQL
e seus volumes. Não use `docker compose down -v`.

## Mensagens institucionais

Os textos de `backend/notifications/outbox.py` são usados por mock e
Evolution. Não recomendam consultar o portal. A mensagem de aprovação
inclui tipo, data e horário da solicitação, mas omite nome, CPF, matrícula,
justificativa e código de consulta. Os templates da API oficial Meta
permanecem independentes.

## Testes e reversão

No ambiente PostgreSQL descartável configurado para testes:

```sh
python -m unittest discover -s tests -v
```

A CI também valida o navegador e a imagem Docker. Para interromper os
envios, pare `sisgece-evolution-worker` e defina
`WHATSAPP_REAL_SEND_ENABLED=0` em seu ambiente antes de recriá-lo.
Para voltar ao envio de convite **somente por texto**, coloque
`EVOLUTION_FEEDBACK_LIST_ENABLED=0` no worker e recrie-o.
Para desligar por completo o convite de avaliação, use
`EVOLUTION_FEEDBACK_ENABLED=0` em app e worker e desative o webhook.

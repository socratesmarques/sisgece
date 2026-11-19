# SISGECE — Evolution API e avaliação pelo WhatsApp

Esta branch experimental foi criada sobre a PR #9. O provedor Evolution é
uma integração não oficial com WhatsApp Web e pode sofrer restrições da
plataforma. Não implante institucionalmente sem avaliação de segurança,
privacidade, conformidade e autorização do IFCE. Use dados fictícios para
homologação.

## Funcionamento padrão do formulário

A página inicial não exibe checkboxes de WhatsApp ou avaliação. Ao
**enviar uma solicitação pelo site**, o sistema com
`NOTIFICATIONS_PROVIDER=evolution` registra avisos vinculados ao telefone
informado, **sem lista de números permitidos**. O telefone é validado e
normalizado para E.164. Somente a movimentação daquela solicitação gera
mensagens; não existem campanhas nem importação de contatos.

O formulário informa previamente que aquele contato receberá atualizações
por WhatsApp, com possibilidade de revogar pelo código do recibo. A API
preserva recusas explícitas de clientes antigos: enviar
`whatsapp_consent=false` não gera inscrição e a combinação de recusa
explícita com pedido de avaliação é rejeitada.

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

## Avaliação após encerramento

A pesquisa só é incluída no último aviso quando
`EVOLUTION_FEEDBACK_ENABLED=1` estiver ativo tanto no app quanto no
worker e a integração de retorno estiver configurada. Os eventos finais
são: entrada confirmada pela recepção, recusa ou saída registrada pela portaria. A aprovação da entrada pela coordenação ainda não encerra o processo; somente a recepção registra a conclusão da entrada, sem etapa de portaria.

O destinatário recebe um comando no formato:

```text
AVALIAR 0123456789ABCDEF 5
```

O código é exclusivo do convite e vence em sete dias. A resposta deve
vir do mesmo telefone destinatário. O sistema grava a primeira nota
válida (de 1 a 5), impede reenvios idênticos, cancela convites após
revogação/reabertura e exibe somente estatísticas agregadas para
coordenação e superusuário.

A migração correspondente é `db/009.sql`; é executada na inicialização
da aplicação atualizada.

### Webhook privado da Evolution v2.3.7

Gere um segredo aleatório de pelo menos 32 caracteres e configure somente
no ambiente do app:

```ini
EVOLUTION_FEEDBACK_ENABLED=1
EVOLUTION_FEEDBACK_WEBHOOK_TOKEN=SEGREDO_PRIVADO
```

No worker: `EVOLUTION_FEEDBACK_ENABLED=1` (sem o segredo).

Configure a instância da Evolution pelo endpoint
`POST /webhook/set/sisgece-teste` com `apikey`, enviando:

```json
{
  "webhook": {
    "enabled": true,
    "url": "http://sisgece-app:3000/api/notificacoes/evolution/avaliacao",
    "headers": {
      "X-SISGECE-Evolution-Secret": "MESMO_SEGREDO_PRIVADO"
    },
    "byEvents": false,
    "base64": false,
    "events": ["MESSAGES_UPSERT"]
  }
}
```

O webhook deve ser acessível somente pela rede Docker. Não exponha essa
rota nem a API Evolution por um túnel público e não registre mensagens
recebidas, telefones ou segredos em logs. Na versão utilizada, a Evolution
suporta headers personalizados no webhook da instância.

O recebimento de notas é verificado por testes com payloads simulados.
Isso não substitui um teste ponta a ponta com uma conta de WhatsApp real.

## Testes e reversão

No ambiente PostgreSQL descartável configurado para testes:

```sh
python -m unittest discover -s tests -v
```

A CI também valida o navegador e a imagem Docker. Para interromper os
envios, pare `sisgece-evolution-worker` e defina
`WHATSAPP_REAL_SEND_ENABLED=0` em seu ambiente antes de recriá-lo.
Para desligar o convite de avaliação, use
`EVOLUTION_FEEDBACK_ENABLED=0` em app e worker e desative o webhook.

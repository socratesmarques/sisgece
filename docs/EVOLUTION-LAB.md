# Evolution API — integração experimental (somente laboratório)

Esta branch parte de `feat/notificacoes-whatsapp` (PR #9). O provedor `evolution`
preserva a fila PostgreSQL, consentimento v2, cancelamento, limites de frequência,
revalidação no worker e tratamento conservador de respostas incertas.

**Não usar na implantação institucional.** Evolution/Baileys é integração não
oficial com sessão WhatsApp Web. Há risco de bloqueio e tratamento indevido de
dados, inclusive contatos sincronizados. Use uma conta de laboratório separada e
exclusivamente solicitações fictícias. Esta implementação não altera `main`.

## Pré-requisitos no WSL

- SISGECE e PostgreSQL isolados em `sisgece-net`, com PR #9 + esta branch
- Evolution API v2.3.7 em Docker, com instância `sisgece-teste` conectada
- Um número de teste que autorizou receber mensagens

Conecte o contêiner Evolution à rede do SISGECE com um alias fixo
(substitua `NOME_CONTAINER_EVOLUTION` pelo nome obtido em `docker ps`):

```sh
docker network connect --alias evolution sisgece-net NOME_CONTAINER_EVOLUTION
```

Use um **arquivo de ambiente exclusivo do worker** com permissões 600; não
coloque a chave Evolution no app web, no Git ou em logs. O banco deve ser
descartável. Para criar novas solicitações de laboratório com provedor
`evolution`, o **app também precisa** de `NOTIFICATIONS_PROVIDER=evolution`,
mas não precisa da chave, do allowlist nem de habilitação de envio.

No ambiente do worker configure:

```ini
NOTIFICATIONS_PROVIDER=evolution
WHATSAPP_REAL_SEND_ENABLED=1
EVOLUTION_LAB_ENABLED=1
EVOLUTION_API_URL=http://evolution:8080
EVOLUTION_INSTANCE=sisgece-teste
EVOLUTION_API_KEY=CHAVE_PRIVADA
EVOLUTION_ALLOWED_RECIPIENTS=+5585987654321
```

Substitua o número de exemplo pelo destinatário autorizado. O worker falha
fechado sem **ambas** as flags, URL local aprovada, chave e allowlist. O
allowlist comporta no máximo cinco números. O backend pode continuar com
`WHATSAPP_REAL_SEND_ENABLED=0` e jamais precisa da chave de envio.

**Importante:** o provedor é selecionado no momento do cadastro, e fica
registrado na assinatura e na fila. Solicitações antigas marcadas como
`mock` não se transformam em Evolution após mudar o ambiente. Gere uma
solicitação fictícia nova, com consentimento específico.

Para uma checagem sem envio, mantenha as flags em 0 ou execute somente os
testes com transporte substituído:

```sh
python -m unittest tests.test_evolution -v
```

A suíte completa requer PostgreSQL 17 descartável:

```sh
python -m unittest discover -s tests -v
```

A inicialização da aplicação aplica `db/008.sql`. O worker Evolution deve
subir **somente depois** da migração.

## Limites conhecidos

- O estado `sent` significa aceito pela Evolution, não entrega comprovada.
  Ainda não há integração de webhooks de confirmação da Evolution.
- Erro de rede após tentativa potencialmente iniciada deixa `uncertain`;
  não há reenvio cego.
- Nenhuma mensagem inclui nome, CPF, matrícula ou código de consulta.
- Não exponha a API da Evolution na internet; mantenha o serviço em
  `127.0.0.1` e na rede Docker privada.
- O volume de sessões vinculado à conta WhatsApp é sensível.
- Não implementar envios em massa, nem ativar em dados reais da instituição.

## Desativação

Pare o worker Evolution, defina `EVOLUTION_LAB_ENABLED=0` e
`WHATSAPP_REAL_SEND_ENABLED=0` e recrie o contêiner com essas flags.
Não altere estados da fila manualmente. A versão anterior permanece funcional
com `mock` e `meta`.


## Página inicial e mensagens

A página pública apresenta a marca vertical do IFCE diretamente do acervo
oficial e substitui somente o quadro de consulta por código. A API
`/api/consulta` e o código gerado após o envio continuam disponíveis como
alternativa de suporte e para compatibilidade; não há mais formulário de
consulta na página inicial.

As oito mensagens dos provedores `mock` e `evolution` deixaram de
recomendar o portal para acompanhamento. Os textos estão em
`backend/notifications/outbox.py`. A mensagem de aprovação permanece com
tipo, data e horário do pedido. Os templates enviados pela Meta seguem sendo
gerenciados na plataforma Meta e não são alterados por esses textos.

## Pesquisa opcional de satisfação via WhatsApp

**Experimental e desativada por padrão.** O formulário oferece uma
autorização específica para receber um convite de avaliação. Marcar
autorização de avisos NÃO marca automaticamente o convite de avaliação.
Consentimentos de solicitações antigas não são convertidos.

No encerramento do pedido — **saída registrada na portaria, aprovação
de entrada ou solicitação recusada** — a notificação final pelo provedor
`evolution` pode convidar a pessoa a atribuir nota de 1 a 5.

O convite é acrescentado **à mensagem de encerramento**, não gera
envio extra em massa e é único por evento. O destinatário responde:

```text
AVALIAR CODIGO_DA_MENSAGEM 5
```

Substitua o último dígito pela nota escolhida. O código é gerado no
banco para a solicitação e vence em sete dias. Cada convite aceita
somente a primeira avaliação válida do mesmo telefone autorizado.
Não são armazenados nome, mensagem livre ou telefone na tabela de notas.
Convites são invalidados quando a solicitação é reaberta/corrigida ou
a autorização de WhatsApp é revogada.

### Preparar app e worker separados

Depois de recriar a imagem e aplicar a migração `db/009.sql`, configure
apenas em arquivos de ambiente com permissão 600.

No app web `app.evolution.env.local`:

```ini
EVOLUTION_FEEDBACK_ENABLED=1
EVOLUTION_FEEDBACK_WEBHOOK_TOKEN=COLOQUE_UMA_CHAVE_ALEATORIA_DE_32_OU_MAIS_CARACTERES
```

No worker `worker.evolution.env.local`:

```ini
EVOLUTION_FEEDBACK_ENABLED=1
```

Não é necessário expor a chave de envio da Evolution no app web.
O worker não precisa conhecer a chave do webhook. O token é próprio
e independente da API key administrativa da Evolution.

### Habilitar webhook na Evolution API v2.3.7

O endpoint de configuração da versão utilizada aceita um objeto
`webhook` com `headers`. A Evolution e o SISGECE precisam estar
na mesma rede privada `sisgece-net`. Configure **apenas a instância
de testes**:

```json
{
  "webhook": {
    "enabled": true,
    "url": "http://sisgece-app:3000/api/notificacoes/evolution/avaliacao",
    "headers": {
      "X-SISGECE-Evolution-Secret": "MESMO_TOKEN_CONFIGURADO_NO_APP"
    },
    "byEvents": false,
    "base64": false,
    "events": ["MESSAGES_UPSERT"]
  }
}
```

Envie a configuração usando `POST /webhook/set/sisgece-teste` com
`apikey` no header e o objeto acima no corpo JSON. **Não registre
o segredo em Git, histórico de shell, capturas de tela ou logs**.
Valide o header recebido na versão exata do contêiner antes de
habilitar a pesquisa; caso o header não chegue, o webhook retornará
403 por segurança. Não ative endpoints públicos nem túneis para
esse webhook — comunicação exclusivamente pela rede Docker local.

A API receptora usa `messages.upsert`, ignora mensagens próprias,
grupos, mídia e mensagens fora do comando de nota, verifica o número
E.164, o código do convite, o consentimento e o encerramento atual
da solicitação. O comando não gera resposta automática; o resultado
fica na área da coordenação.

### Visualizar as avaliações

Funcionários de **coordenação** e **superusuário** veem o resumo
no painel SISGECE: número de avaliações, média de 1 a 5 e
distribuição por nota. Outros perfis não podem acessar a API
`GET /api/notificacoes/avaliacoes/estatisticas`. Não são mostrados
nomes, telefones ou textos livres.

### Testes locais

```sh
python -m unittest discover -s tests -v
```

A integração de avaliação usa a fila e o banco PostgreSQL existente,
mas depende de configuração manual do webhook na instância da Evolution.
A CI não envia mensagens reais e não comprova recebimento no
WhatsApp; é necessário um teste separado com dois números consentidos
(uma conta emissora e outra receptora).

Para desativar imediatamente, pare o worker de testes, altere
`EVOLUTION_FEEDBACK_ENABLED=0` no app/worker, recrie os
contêineres e desabilite o webhook na instância da Evolution.

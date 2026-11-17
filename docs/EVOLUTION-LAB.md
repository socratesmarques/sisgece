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

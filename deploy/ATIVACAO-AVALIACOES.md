# Ativação das avaliações Evolution — lsdserver

Este procedimento é **específico** do ambiente de produção com
\`sisgece-app\`, \`sisgece-db\`, Evolution \`2.4.0-rc2\`, worker
\`evolution-sisgece-sisgece-notifications-1\` e rede
\`sisgece-feedback-net\`. Não utilize em outros servidores sem revisão.

## Antes de executar

A PR que adicionou este script deve estar integrada à \`main\`.
O operador já deve ter preparado os seguintes arquivos locais
(com permissões restritas \`600\`):

- \`~/evolution-sisgece/sisgece-prod-evolution.env\`: \`EVOLUTION_INSTANCE\`
  idêntica ao worker, \`EVOLUTION_FEEDBACK_ENABLED=1\` e
  \`EVOLUTION_FEEDBACK_WEBHOOK_TOKEN\` gerado localmente (32+ caracteres).
- \`~/evolution-sisgece/worker.env\`:
  \`EVOLUTION_FEEDBACK_ENABLED=1\`,
  \`EVOLUTION_FEEDBACK_LIST_ENABLED=1\` e configuração Evolution
  previamente funcional (API key mantida só neste arquivo).
- Rede Docker privada \`sisgece-feedback-net\`, conectada ao
  \`sisgece-app\` e \`evolution-sisgece-evolution-1\`. O teste
  \`http://sisgece-app:3000/api/ready\` já deve responder 200
  **a partir do contêiner Evolution**.

O script interrompe brevemente o SISGECE e o worker e **não reinicia**
Evolution, PostgreSQL, Redis nem o proxy. Realize em janela de manutenção.
O script só trata o webhook quando a instância não possui outro webhook
ou quando o existente corresponde exatamente à configuração esperada.
Nunca sobrepõe um webhook de terceiros.

## Execução: uma linha por modo

Depois de fazer o merge no GitHub, no \`lsdserver\`:

\`\`\`bash
cd ~/sisgece && git pull --ff-only && python3 deploy/ativar-avaliacoes-evolution.py --check
\`\`\`

Se passar e houver uma janela adequada, execute:

\`\`\`bash
cd ~/sisgece && python3 deploy/ativar-avaliacoes-evolution.py --apply
\`\`\`

\`--check\` não altera contêineres, rede nem webhook.
\`--apply\` realiza a configuração e inclui backup em
\`~/sisgece-backups/ativacao-avaliacoes-<data>/\` (sem exibir segredos).

O script:

1. Compara instância, habilitações, imagem do app/worker, credenciais
   do PostgreSQL, redes e webhook já configurado.
2. Prepara o Compose override para persistir a rede privada da Evolution.
3. Para o worker, preserva o contêiner antigo do SISGECE, e recria o
   app com **a mesma imagem e suas configurações de segurança**.
4. Conecta a rede privada, verifica \`/api/ready\` e envia ao webhook
   **apenas um evento fictício de teste**, sem registrar avaliação.
5. Registra o webhook na Evolution:
   \`POST /webhook/set/{instance}\`, \`MESSAGES_UPSERT\`,
   cabeçalho privado \`X-SISGECE-Evolution-Secret\`.
6. Recria o worker com as novas variáveis do arquivo de ambiente.

Se uma etapa falhar, tenta restaurar o contêiner antigo do SISGECE e
reiniciar o worker. Caso a falha ocorra **durante a substituição do worker**,
desativa as duas flags de avaliação no \`worker.env\` e tenta restabelecer
as notificações comuns. Verifique o resultado antes de reexecutar;
recuperação em falhas de Docker não pode ser garantida.

**Não publique** o segredo do webhook, a API key, o conteúdo dos
\`.env\` ou logs que contenham informações pessoais.

## Teste final

Use um **pedido fictício com número pessoal autorizado**. Confirme a
entrada na recepção ou a saída na portaria, escolha uma das cinco notas
no WhatsApp e verifique os totais em **Avaliações do SISGECE** no painel
da coordenação/superusuário. A mensagem de confirmação do envio pelo
provedor e um HTTP 200 no webhook não provam, isoladamente, que a nota
foi registrada. Não faça testes com dados reais de alunos.

Na Evolution 2.4.0-rc2 há relatos de webhook que perde configuração
após reinicializar; após qualquer recriação, consulte o webhook da
instância novamente antes de liberar o fluxo.

## Atualizações futuras

O atualizador de produção versionado em
\`deploy/atualizar-sisgece-evolution.sh\` já conecta a rede de feedback.
A cópia \`~/atualizar-sisgece.sh\` não é alterada apenas com \`git pull\`.
Após o merge e fora da ativação, instale a versão versionada se necessário:

\`\`\`bash
install -m 700 ~/sisgece/deploy/atualizar-sisgece-evolution.sh ~/atualizar-sisgece.sh
\`\`\`

Para recriar a Evolution com Compose usando opções \`-f\` explícitas,
inclua também \`-f compose.override.yaml\`, mas **não recrie a Evolution
como parte da ativação inicial**.

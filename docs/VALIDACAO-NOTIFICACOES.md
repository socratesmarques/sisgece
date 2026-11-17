# Evidências de validação

Base: main de4de6f. Desenvolvimento em feat/notificacoes-whatsapp.
Ambiente isolado: Python 3.12, venv fora do repositório, PostgreSQL 17 em
contêiner descartável, porta somente loopback. Nenhum acesso a produção.

## Incremento 1

Antes de modificar a aplicação:
- `python -m unittest discover -s tests -v`: 5 testes aprovados (6,156 s).
- Dependências originais instaladas em venv.
- Chromium do sistema usado como executable_path no runner de diagnóstico;
  download do Chromium do Playwright bloqueado pela política de rede.

Todos os testes de notificações devem usar mock ou transporte HTTP substituído.
Não são evidência de homologação com a conta real da Meta.
- Roteiro original `tests/browser.py`: aprovado com Chromium do sistema,
  incluindo máscaras, cadastro/consulta, decisão de entrada e saída,
  recepção/portaria e responsividade (390, 768, 1024 e 1440 px).

## Incremento 2

Migração aditiva 007, telefone canônico no JSONB existente, consentimento explícito,
desafios de uso único e revogação. Testes cobrem número inválido, consentimento
malformado/desatualizado, remetente incorreto, isolamento mock/Meta, expiração,
reutilização e manutenção da consulta pelo código.
- Incremento 2: 9 testes aprovados em PostgreSQL 17 (6,492 s).

## Incremento 3

Fila inserida na mesma transação do evento e da decisão. Restrição única por
evento/canal/assinatura; supersessão de pendências antigas. Testes adicionais de
rollback por falha na fila e aprovação concorrente (um 200 e um 409).
- Incremento 3: 11 testes aprovados (7,020 s).

## Incremento 4

Worker com SKIP LOCKED, reserva limitada, recuperação conservadora, backoff,
limite de tentativas e ritmo global/por destinatário persistido. Mock permite
inspeção em memória e sucesso/falhas sem chamadas externas.
- 15 testes aprovados (7,950 s), incluindo quatro workers concorrentes,
  timeout ambíguo, falha permanente/temporária e reinicialização.

## Incremento 5

API oficial com templates, TLS, host fixo, sem redirects ou retry HTTP implícito.
Webhook HMAC-SHA256 sobre bytes originais, validação WABA/Phone Number ID,
deduplicação, confirmação/revogação e armazenamento mínimo de estados de entrega.
Callbacks anteriores à resposta HTTP são conciliados pelo ID externo; sem
correlação heurística entre solicitações.
- 21 testes aprovados (7,915 s), com transporte Meta sempre substituído.
- Documentação oficial consultada em 17/11/2026 UTC: Messages API, mensagens
  de serviço/templates, referência de webhooks, criação do endpoint e erros.

## Incremento 6

Interface preservada, escolha explícita do titular, checkbox opt-in e controles
na consulta. Resultado de envio somente para coordenação/superusuário.
- Roteiro original de navegador aprovado novamente.
- Novo roteiro WhatsApp aprovado em 390/1280 px: consentir, confirmar em mock,
  processar, revogar e continuar consultando.
- Uma execução inicial encontrou orçamento compartilhado de consultas/ações;
  contadores separados corrigiram o problema. A repetição completa passou.

## Incremento 7 e validação final

- `python -m unittest discover -s tests -v`: **25 testes aprovados**, 10,104 s.
  Inclui os cinco testes originais. Cobertura adicional: todas as transições
  institucionais existentes, permissões dos quatro perfis, limite de tentativas,
  ritmo compartilhado, expiração, Retry-After e resposta tardia após reserva expirada.
- `git diff --check`, compilação dos módulos Python e `node --check
  frontend/static/main.js`: sem erros.
- Build Docker inicial encontrou CA do proxy ausente. Repetido com Dockerfile
  temporário fora do repositório e CA montada como segredo BuildKit, apenas para
  o pip; TLS permaneceu validado e nenhuma CA foi copiada para a imagem final.
- Primeira inicialização Docker encontrou permissões 600/700 do checkout desta
  máquina. Dockerfile corrigido para tornar código empacotado legível pelo usuário
  não-root. Imagem reconstruída com sucesso.
- Imagem final executada como `sisgece`, `--read-only`, tmpfs, sem capabilities,
  no-new-privileges e publicação apenas em loopback. `/api/ready`: HTTP 200,
  `{"ok":true}`. Migração aplicada ao banco descartável `sisgece_review`.
- Contra essa imagem: `tests/browser.py` aprovado, incluindo operações originais
  e responsividade; `tests/browser_notifications.py` aprovado em 390/1280 px.
- Worker da mesma imagem executado em contêiner separado, sem portas,
  `python -m backend.notifications.worker --once`: saída 0.

Não houve tráfego real de mensagens Meta, configuração de cobrança, acesso ao
servidor de produção ou merge. Homologação com conta/template real e revisão
institucional permanecem necessárias antes da habilitação real.

## Correção identificada pela CI do PR

A primeira execução remota aprovou os 25 testes e build/readiness Docker, mas
revelou uma corrida no navegador: o recibo aparecia antes de a consulta auxiliar
de notificações terminar, e o bloqueio global da interface ignorava um clique
imediato na consulta pelo código. A consulta auxiliar agora roda sem bloquear
a principal e descarta respostas antigas. O novo teste mantém essa requisição
pendente deliberadamente e exige que a consulta principal continue funcionando.
O roteiro novo e o original passaram novamente contra a imagem Docker corrigida.

## Simplificação solicitada pelo mantenedor

Consentimento v2: somente a frase curta solicitada, sem textos de simulação,
seleção extra de titular ou botão de confirmação. O telefone continua identificado
como contato do responsável. Novos opt-ins v2 são processados automaticamente;
`verificado_em` permanece nulo, e assinaturas v1 não são habilitadas retroativamente.
O risco de número incorreto sem prova de posse está registrado em NOTIFICACOES.md.

Validação local desta alteração: 26 testes unittest aprovados (11,766 s), roteiro
WhatsApp em 390/1280 px aprovado sem confirmação e roteiro original de navegador
aprovado, incluindo consulta pelo código e responsividade. Envio real desabilitado.

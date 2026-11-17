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

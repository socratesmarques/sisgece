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

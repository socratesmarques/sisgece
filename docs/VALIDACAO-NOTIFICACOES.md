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

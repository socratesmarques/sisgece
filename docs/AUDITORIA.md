# Auditoria inicial e plano — 2026-11-11

Base: Flask/Waitress, psycopg, PostgreSQL, HTML Jinja e JavaScript sem framework.
Inspecionados backend, cinco migrações, frontend, Dockerfile, Caddyfile, testes e CI.
Não há migração de linguagem necessária. RBAC, sessões com hash, CSRF por cabeçalho,
SQL parametrizado, bloqueios transacionais e minimização de respostas já existem.

Prioridades:
1. Bloquear duplicações concorrentes e expirar consultas públicas; preservar recibos antigos.
2. Separar liveness/readiness e registrar metadados sem dados pessoais.
3. Compose isolado, exemplos de configuração e procedimentos operacionais.
4. Executar regressões PostgreSQL, navegador e análise de dependências.
5. Registrar evidências e lacunas; não declarar homologação institucional sem executá-la.

Lacunas adicionais para revisão: retenção institucional ainda não definida,
autorizações sem validade operacional explícita, privilégio DDL do usuário da aplicação,
recuperação administrativa de senha sem procedimento formal, ausência de testes de desastre.

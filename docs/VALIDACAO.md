# Evidências — 2026-11-11

Execução local com dados exclusivamente fictícios:

- unittest: 3 testes aprovados, 5,619 s; suíte inclui fluxos de entrada/saída,
  estudante/responsável, RBAC, rejeição, concorrência, legado, limites de login,
  duplicação simultânea e expiração de consulta.
- Playwright Chromium: envio e consulta em 1280/390 px sem overflow; aprovação,
  recepção e portaria aprovadas na interface.
- pip-audit -r requirements.txt: nenhuma vulnerabilidade conhecida encontrada
  na resolução instalada. Isso não constitui auditoria completa de segurança.
- Ruff: análise F e formatação aprovadas; git diff --check aprovado.
- Docker build aprovado com CA fornecida por secret efêmero do BuildKit.
- docker compose config --quiet aprovado com valores fictícios.
- pg_dump/pg_restore --exit-on-error: restauração em banco separado aprovada;
  duas solicitações fictícias presentes no banco restaurado.

## Limitações e bloqueios para produção

A entrega é incremental e NÃO PRONTA para produção. Não houve homologação no IFCE.
Ainda são necessários: validade operacional de autorizações; política institucional
 de retenção e implementação de expurgo; separação de credenciais de migração e
runtime; lock completo de dependências/imagens e varredura das imagens; limites de
recursos e execução não root de todos os serviços; testes de carga, acessibilidade
completa e recuperação de desastre com RPO/RTO; validação de HTTPS/DNS/firewall no
ambiente institucional. Compose não foi validado integralmente com certificado real.
A suíte de navegador não cobre todos os fluxos negativos. Não foi feita auditoria
completa do histórico Git em busca de segredos. O CI remoto depende da execução
no GitHub e não é presumido aprovado.

A consulta pública continua retornando mensagem escrita pela coordenação: a equipe
não deve publicar dados pessoais nesse campo. A posse do recibo permite consulta
do status; não comprova identidade nem libera histórico pessoal.

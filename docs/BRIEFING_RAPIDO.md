# SISGECE — briefing rápido para transferência de contexto

> Atualizado em 17/11/2026. Fonte: código e README da `main` e situação dos pull requests no GitHub. Este documento **não comprova** que a versão da `main` esteja instalada no servidor institucional.

## Em uma frase

O **SISGECE — Sistema de Gerenciamento de Entrada e Saída de Estudantes**, do **IFCE Campus Maranguape**, recebe e acompanha solicitações de entrada/saída, com análise da coordenação e, nas saídas aprovadas, conferências posteriores pela recepção e portaria.

## Stack e estrutura

- **Backend:** Python 3.12, Flask 3.1.3, Waitress 3.0.2, psycopg 3.3.8 e PostgreSQL 17.
- **Frontend:** HTML/Jinja2, CSS e JavaScript sem framework SPA.
- **Segurança:** sessões em cookies HttpOnly/Secure/SameSite, hash de token no banco, perfis, proteção de requisições, controles de tentativas e trilha de eventos.
- **Execução:** Docker; aplicação na porta interna 3000, normalmente publicada em `127.0.0.1:8004`, banco isolado e HTTPS por proxy reverso Caddy no servidor.
- **Caminhos essenciais:** `backend/app.py`, `backend/manage.py`, `frontend/`, `db/`, `tests/`, `deploy/`.

## Fluxo funcional atual na `main`

1. Aluno ou responsável declara os dados do pedido de **Entrada** ou **Saída**, incluindo contato e justificativa.
2. A coordenação ou o superusuário **aprova/reprova** o pedido; a reprovação exige mensagem pública.
3. Para **Saída aprovada**, a recepção confere a autorização e a portaria registra a saída efetiva, nessa ordem. **Entrada aprovada não significa entrada física registrada**.
4. O usuário recebe atualizações pelo WhatsApp quando habilitado; funcionários consultam pedidos, histórico e permissões por perfil.
5. Reabertura/correções preservam eventos anteriores e invalidam etapas dependentes quando aplicável.

**Perfis:** `coordenação`, `recepção`, `portaria`, `superusuário`. Ações institucionais exigem autenticação e autorização no backend.

## Estado de implementação (17/11/2026)

- **`main`:** fluxo de solicitações, notificações pelo WhatsApp, análise de entradas/saídas, conferência de saídas, gestão de funcionários, histórico, máscaras de CPF/telefone, migrações até `006.sql`.
- **PR #9 aberto e não mesclado:** notificações opcionais via WhatsApp, consentimento/validação de número, fila PostgreSQL, worker, provedor mock e integração configurável com a API da Meta; testes e CI reportados como aprovados. **Não presumir envio real, homologação institucional ou implantação.**
- **PR #5 encerrado sem merge:** não tratar seus itens como incluídos só por constarem na descrição.
- **Produção:** há uma instalação institucional discutida separadamente; **versão realmente instalada, DNS, certificados e estado dos contêineres precisam ser verificados no próprio servidor**. Nunca deduzir deploy a partir de PR ou README.

## Regras para uma IA assumir o projeto

- Leia primeiro [CONTEXTO_PROJETO.md](CONTEXTO_PROJETO.md), depois o [README](../README.md) e os arquivos reais do repositório.
- Diferencie explicitamente **implementado na main**, **presente apenas em PR**, **testado**, **homologado** e **implantado**.
- Preserve regras institucionais, códigos existentes, dados e volumes PostgreSQL; não introduza envio externo sem opt-in/autorizações.
- Antes de qualquer mudança operacional: plano de backup, ensaio de restauração, migração, testes e rollback.
- Não exiba nem peça para publicar segredos, senhas, tokens, CPF, telefone ou dados reais de estudantes.
- Para desenvolvimento local, prefira Python 3.12, WSL/Ubuntu, PostgreSQL isolado e, para notificações, `mock` com envio real desabilitado.

## Links úteis

- Repositório: https://github.com/socratesmarques/sisgece
- Notificações em revisão: https://github.com/socratesmarques/sisgece/pull/9
- Instruções de atualização: [deploy/ATUALIZACAO.md](../deploy/ATUALIZACAO.md)
- Documento aprofundado: [CONTEXTO_PROJETO.md](CONTEXTO_PROJETO.md)

## Prompt pronto para colar em outra conversa

> Você vai trabalhar no projeto SISGECE do IFCE Campus Maranguape. Leia este briefing e o arquivo `docs/CONTEXTO_PROJETO.md` do repositório `socratesmarques/sisgece`. Considere o código da branch relevante como fonte de verdade e confirme PRs/estado atual antes de afirmar que algo está pronto. Separe main, PR, testes e produção. Preserve os fluxos de autorização de entrada e saída, o histórico e a segurança dos dados. Antes de alterar código ou implantação, explique o impacto, os arquivos envolvidos e como validar. Minha tarefa nesta conversa é: **[descreva aqui a tarefa]**.

# SISGECE

Sistema de gerenciamento de entrada, saída e solicitações escolares do IFCE — Campus Maranguape.

Repositório consolidado: https://github.com/socratesmarques/sisgece

## Origem

Este repositório reúne os históricos completos de `socratesmarques/sisgece` (API Node.js/PostgreSQL e telas administrativas) e `Gabriel-msv/sisgece` (interface de solicitações, gestão e recepção/portaria). A união foi feita por merge, sem reescrever os commits originais. As branches de trabalho das origens continuam nos respectivos repositórios.

## Executar

Requer Node.js 20 ou superior e npm.

```sh
npm ci --prefix backend
cp backend/.env.example backend/.env
npm start --prefix backend
```

Acesse http://localhost:3000 para a interface principal e http://localhost:3000/pages/admin-login.html para o painel administrativo conectado à API. O diagnóstico da API está em `/api/health`.

Para usar a API com banco, configure PostgreSQL e `JWT_SECRET` em `backend/.env`. O esquema SQL e as migrações não foram fornecidos nos repositórios originais; é necessário disponibilizar as tabelas esperadas pelos controllers: `administradores`, `estudantes`, `responsaveis`, `responsavel_estudante` e `solicitacoes`. O servidor e a demonstração podem iniciar sem banco; as rotas que consultam PostgreSQL dependem dele.

## Estado da integração

A interface principal mantém o modo de demonstração original (`CONFIG.USE_MOCK = true` em `frontend/assets/js/app.js`), com dados no navegador. As contas exibidas nela são exclusivas da demonstração. Os pedidos dessa interface ainda não são enviados ao PostgreSQL.

O painel em `/pages/admin-login.html` usa o backend real, com autenticação JWT e análise de solicitações. Os contratos das duas versões são diferentes: a interface principal espera `/api`, sessão por cookie e perfis de gestão, recepção e portaria; a API existente usa `/auth`, `/estudantes`, `/responsaveis` e `/solicitacoes`, com token Bearer e administrador. Alterar somente `USE_MOCK` não basta para conectá-las. A adaptação desses contratos e a persistência das etapas de recepção/portaria são trabalho futuro.

## Estrutura

```text
frontend/
  index.html              Interface principal (demonstração)
  assets/css/             Estilos das duas interfaces
  assets/js/              Scripts das duas interfaces
  pages/                  Login e painel administrativo da API
backend/
  app.js                  Servidor Express e arquivos estáticos
  scripts/                Utilitários administrativos
  src/                    Configuração, controllers, rotas e autenticação
index.html                Entrada para hospedagem estática (GitHub Pages)
```

Para demonstração estática, sirva a raiz do repositório; `index.html` encaminha para `frontend/`. O painel administrativo requer o servidor Node.js.

## Equipe

Mario — Tech Leader; Gilvan, Miguel, Socrates e Wendel — Desenvolvimento FullStack. A autoria original está preservada nos commits dos dois projetos.

## Licença

A licença geral do projeto ainda não foi definida.

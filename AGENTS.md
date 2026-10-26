# AGENTS.md

## Sobre o projeto

Este projeto é um sistema de gerenciamento de entrada e saída de estudantes do IFCE.

O sistema terá três tipos principais de usuários:

- Estudante
- Responsável
- Administrador / Coordenador

## Objetivo

Permitir o controle de entrada e saída dos estudantes e facilitar solicitações de autorização feitas pelos responsáveis.

## Regras básicas

- Mantenha o código simples e organizado.
- Use nomes de variáveis e funções claros.
- Não altere arquivos sem necessidade.
- Antes de criar uma nova funcionalidade, verifique se já existe algo semelhante no projeto.
- Separe frontend, backend e banco de dados de forma organizada.
- Evite código duplicado.

## Funcionalidades iniciais

### Estudante

- Acessar usando matrícula.
- Registrar entrada.
- Registrar saída.
- Consultar seu status de entrada/saída.

### Responsável

- Acessar usando CPF.
- Visualizar estudantes vinculados.
- Criar solicitação de saída.
- Consultar o status da solicitação.

### Administrador

- Fazer login.
- Visualizar solicitações.
- Aprovar solicitações.
- Reprovar solicitações.
- Consultar estudantes.
- Consultar histórico de entradas e saídas.

## Ao modificar o projeto

Sempre:

1. Entenda a estrutura existente.
2. Faça apenas as mudanças necessárias.
3. Mantenha o padrão de código do projeto.
4. Não remova funcionalidades existentes sem necessidade.
5. Explique brevemente as alterações realizadas.

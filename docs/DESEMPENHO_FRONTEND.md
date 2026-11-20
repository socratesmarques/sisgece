# Desempenho do frontend — etapa 4

## Escopo

A página pública carrega `shared.js` e `public.js`, sem código de gerenciamento de funcionários. A área de equipe carrega `shared.js` e `staff.js`. Dois scripts `defer` são executados na ordem, sem dependência externa. O arquivo `main.js` antigo foi substituído por estes três arquivos.

O HTML aponta para CSS e JS com `?v=<12 caracteres do SHA-256>`, calculado ao iniciar o Flask. Apenas a versão atual tem cache imutável por um ano. Versões erradas ou sem versão revalidam; páginas e APIs mantêm `no-store`.

## Medição — bytes UTF-8 sem compressão

| Recursos carregados pela página inicial | Antes | Depois |
| --- | ---: | ---: |
| JavaScript | 26253 B | 5666 B |
| CSS | 21846 B | 21846 B |
| CSS + JavaScript | 48099 B | 27512 B |

Redução do JavaScript público: **78.4%**. Redução de CSS+JavaScript: **42.8%**. JS da área administrativa (compartilhado + específico): 24398 B.

São tamanhos brutos do código, não testes de tempo real, arquivos comprimidos, LCP ou Lighthouse. Para checar os tamanhos: `wc -c frontend/static/{shared,public,staff}.js frontend/static/main.css`. Para confirmar o impacto em produção, comparar métricas Lighthouse mobile e desktop antes/depois usando mesma conexão e dispositivo.

A CI executa os testes de cache e scripts; os testes de navegador garantem envio e painel de funcionários. Após aprovação e merge, usar o atualizador habitual do lsdserver, sem sobrescrever a configuração Evolution.

# Editor de mensagens automáticas

Acesso: **Área do funcionário → Mensagens automáticas**, somente para **superusuários**.

## Recursos

- Oito avisos independentes: cadastro, aprovação, reprovação, recepção, portaria, reabertura, correção da recepção e correção da portaria.
- Texto personalizado com 10 a 1.500 caracteres, prévia sem envio, botão para restaurar o padrão e opção de pausar novos avisos por evento.
- Marcadores permitidos: `{tipo}`, `{data}`, `{horario}` (sem nome, CPF, matrícula, telefone, justificativa ou código do estudante). Exemplos de prévia: **Entrada**, **21/01/2030**, **14:30**.
- Cabeçalho institucional, rodapé, informação complementar de recepção e convite de avaliação (quando habilitado) continuam definidos no código e aparecem na prévia. Não podem ser modificados pelo editor.
- Controle de edição simultânea: se outro superusuário alterar o modelo, uma tentativa de salvar a versão antiga recebe **409** e precisa recarregar.
- Histórico das últimas 15 versões por evento (texto, status, autor, data). A auditoria institucional também registra a ação, sem duplicar o conteúdo no log geral.

## Quando a alteração passa a valer

O **SISGECE Evolution** copia o corpo configurado para `notificacoes.corpo_personalizado` ao gerar **cada novo evento**. Assim o worker envia exatamente a versão do corpo vigente no cadastro/decisão, mesmo se o superusuário editar o modelo entre a criação da fila e o despacho.

Desativar um modelo impede **novos avisos daquele evento**, mas **não cancela envios já na fila**. Não interfere no pedido, na sua análise nem no restante das mensagens. Se houver necessidade de interromper envios pendentes, siga o procedimento operacional de pausa do worker e revisão da fila: não tente editar filas manualmente sem conciliação.

O **MetaProvider** mantém seus modelos aprovados pela Meta; este editor não altera esses modelos. Em modo `mock`, as mensagens continuam usando os textos padrão como antes, para manter os testes existentes.

## Segurança e publicação

- As três rotas de leitura e alteração são exclusivas do perfil `superusuário`. Operações POST utilizam cabeçalho `X-SISGECE: 1`, a mesma proteção já usada no site.
- Nenhuma prévia envia mensagens ou entra na fila.
- As configurações e seus históricos residem no PostgreSQL usado pelo SISGECE (migração `011.sql`). Nenhuma credencial de API fica no banco dos textos.
- Mensagens formatadas são inseridas no navegador apenas como texto, não HTML interpretado.
- A atualização do banco ocorre na inicialização da nova imagem, conforme `backend/manage.py migrate`. **Faça backup e revise o PR antes do deploy**, pois um rollback da imagem não remove automaticamente a migração.
- O worker deve usar a mesma imagem do aplicativo após o deploy. O script versionado `deploy/atualizar-sisgece-evolution.sh` gerencia ambos.

## Validação

```bash
python -m unittest discover -s tests -v
```

O teste `tests/test_message_editor.py` usa um esquema descartável e cobre permissões, conteúdo, prévia, validação, versão, histórico, auditoria, enfileiramento e desligamento. Não rode testes que criam solicitações contra produção.

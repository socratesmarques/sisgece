# Editor de mensagens automáticas

Acesso: **Área do funcionário → Mensagens automáticas**, somente para **superusuários**.

## Recursos

- Oito avisos independentes: cadastro, aprovação, reprovação, recepção, portaria, reabertura, correção da recepção e correção da portaria.
- **Mensagem integral editável** (10 a 1.500 caracteres): abertura, corpo, informações de etapa e assinatura final. Prévia sem envio, restauração do padrão e opção de pausar novos avisos por evento.
- Marcadores de solicitação: `{tipo}`, `{data}`, `{horario}` (sem nome, CPF, matrícula, telefone, justificativa ou código do estudante). Exemplos de prévia: **Entrada**, **21/01/2030**, **14:30**.
- Marcadores opcionais de bloco: `{detalhes_solicitacao}` apenas na aprovação; `{detalhes_etapa}` apenas na recepção; `{convite_avaliacao}` apenas em reprovação, recepção e portaria. O convite é expandido apenas quando houver código autorizado e etapa compatível. Um código fictício pode ser exibido na simulação, sem disparar mensagens.
- **Não existe cabeçalho, assinatura ou parágrafo obrigatório acrescentado depois do editor.** Tudo o que aparece no campo pode ser alterado, movido ou removido. Para incluir informações variáveis, posicione os marcadores nos lugares desejados; removê-los também remove o trecho correspondente. A prévia usa o mesmo renderizador que o worker da Evolution.
- Controle de edição simultânea: se outro superusuário alterar o modelo, uma tentativa de salvar a versão antiga recebe **409** e precisa recarregar.
- Histórico das últimas 15 versões por evento (texto, status, autor, data). A auditoria institucional também registra a ação, sem duplicar o conteúdo no log geral.

## Quando a alteração passa a valer

O **SISGECE Evolution** copia o texto completo configurado para `notificacoes.corpo_personalizado` e marca `mensagem_completa=true` ao gerar **cada novo evento**. Assim, o worker envia exatamente a versão vigente quando o evento é criado, expandindo apenas os marcadores permitidos. Edições posteriores não afetam a fila existente.

A migração `012.sql` acrescenta um indicador de formato nos modelos, histórico e fila. **Modelos e notificações anteriores à migração mantêm o formato legado**, preservando a lógica antiga de cabeçalho/rodapé para mensagens pendentes. Ao editar e salvar um modelo legado, ele passa a ser salvo como mensagem completa, sem alterar os itens antigos da fila.

Desativar um modelo impede **novos avisos daquele evento**, mas **não cancela envios já na fila**. Não interfere no pedido, na sua análise nem no restante das mensagens. Se houver necessidade de interromper envios pendentes, siga o procedimento operacional de pausa do worker e revisão da fila: não tente editar filas manualmente sem conciliação.

O **MetaProvider** mantém seus modelos aprovados pela Meta; este editor não altera esses modelos. Em modo `mock`, as mensagens continuam usando os textos padrão como antes, para manter os testes existentes.

## Segurança e publicação

- As três rotas de leitura e alteração são exclusivas do perfil `superusuário`. Operações POST utilizam cabeçalho `X-SISGECE: 1`, a mesma proteção já usada no site.
- Nenhuma prévia envia mensagens ou entra na fila.
- As configurações e seus históricos residem no PostgreSQL usado pelo SISGECE (migrações `011.sql` e `012.sql`). Nenhuma credencial de API fica no banco dos textos.
- Mensagens formatadas são inseridas no navegador apenas como texto, não HTML interpretado.
- A atualização do banco ocorre na inicialização da nova imagem, conforme `backend/manage.py migrate`. **Faça backup e revise o PR antes do deploy**, pois um rollback da imagem não remove automaticamente as novas colunas. Se o worker e o app usarem imagens diferentes durante a implantação, mensagens integrais poderão ser interpretadas incorretamente: mantenha o worker parado enquanto troca ambos.
- O worker deve usar a mesma imagem do aplicativo após o deploy. O script versionado `deploy/atualizar-sisgece-evolution.sh` gerencia ambos.

## Validação

```bash
python -m unittest discover -s tests -v
```

O teste `tests/test_message_editor.py` usa um esquema descartável e cobre permissões, conteúdo, prévia, validação, versão, histórico, auditoria, enfileiramento e desligamento. Não rode testes que criam solicitações contra produção.

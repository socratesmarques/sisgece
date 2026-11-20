# Atualizador de produção (SISGECE + Evolution)

Esta rotina é específica para o `lsdserver` no ambiente atual: SISGECE em `sisgece-net`, porta `127.0.0.1:18081`, PostgreSQL `sisgece-db`, Evolution em `~/evolution-sisgece` e worker do Compose `evolution-sisgece`.

**Não é um instalador genérico.** Não use em outro servidor sem revisar nomes, rede e portas. Não modifica o Caddy.

## Instalação no lsdserver

Somente **após o merge deste PR na `main`**:

```bash
cd ~/sisgece
git switch main
git pull --ff-only origin main
cp -p ~/atualizar-sisgece.sh ~/atualizar-sisgece.sh.bak.$(date +%Y%m%d-%H%M%S)
install -m 700 deploy/atualizar-sisgece-evolution.sh ~/atualizar-sisgece.sh
bash -n ~/atualizar-sisgece.sh
bash ~/atualizar-sisgece.sh --check
```

O `--check` não altera nenhum serviço. Se falhar, revise a causa antes de executar a atualização.

Para implantar uma alteração **já integrada à `main`**, durante uma janela de manutenção:

```bash
bash ~/atualizar-sisgece.sh --apply
```

## O que o script faz

1. Confere as redes, porta, contêineres, credenciais de PostgreSQL e os ambientes do app e do worker, sem imprimir segredos.
2. Faz `git pull --ff-only` e constrói uma nova imagem **antes** de interromper qualquer serviço.
3. Faz backup do ambiente e interrompe o worker apenas se já estava rodando.
4. Para o SISGECE, obtém um dump do PostgreSQL e preserva o contêiner antigo com outro nome.
5. Inicia a nova imagem usando **`sisgece-prod-evolution.env`**, preservando `NOTIFICATIONS_PROVIDER=evolution`.
6. Aguarda `/api/ready` e troca a imagem do worker, preservando se estava ativo ou parado.
7. Em erro, tenta restaurar o contêiner anterior e o worker antigo. **Não restaura automaticamente o banco**: alterações de esquema podem exigir análise e restauração manual.

## Cuidados

- A rotina mantém `WHATSAPP_REAL_SEND_ENABLED=1` **somente no worker** e `0` no app web. Não habilita envio se ele tiver sido desativado.
- A Evolution, seu PostgreSQL e o Redis não são recriados, e não se usa `--remove-orphans`.
- Backups incluem credenciais e ficam em `~/sisgece-backups/<data>`, acessíveis apenas ao operador; mantenha proteção e retenção adequadas.
- A pré-verificação **exige** que o provedor e o worker já estejam configurados. Se o serviço tiver sido migrado para outra arquitetura, não force o script.
- Verifique a UI e a fila de mensagens após cada atualização. Aplicar `--apply` pode causar breve indisponibilidade.
- Não rode os testes de navegador contra produção: eles criam solicitações fictícias.

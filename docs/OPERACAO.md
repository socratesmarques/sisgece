# Operação da versão em revisão

Não implantar antes de concluir as pendências de AUDITORIA.md e homologar.
Servidor de referência: Linux, Docker Engine e Compose v2; dimensionamento inicial
2 CPUs, 4 GiB RAM e disco monitorado, a confirmar por teste de carga.

## Instalação nova

```sh
cp .env.example .env
chmod 600 .env
openssl rand -hex 32
```

Preencha POSTGRES_PASSWORD e SISGECE_PROXY_SECRET com valores distintos gerados
localmente. Configure SISGECE_DOMAIN com o domínio institucional e DNS apontando
para o servidor. TRACKING_TTL_DAYS aceita 1–365 dias (padrão 30).

```sh
docker compose config --quiet
docker compose build
docker compose up -d
docker compose ps
docker compose exec app python backend/manage.py superuser
```

Somente o proxy publica 80/443. Restrinja o firewall às redes autorizadas; nunca
publique 5432/3000. Caddy solicita certificado público automaticamente: para domínio
interno, configure certificado institucional ou CA interna e distribua sua confiança.
Não use LOCAL_HTTP em produção. O volume dados é persistente; nunca use down -v.
As migrações são aplicadas transacionalmente na inicialização. Não apontar uma
instalação nova a dados existentes sem backup e ensaio de migração.

## Backup e restauração em banco separado

Agende com o usuário operador, diretório protegido e armazenamento externo cifrado:

```sh
umask 077
mkdir -p backups
docker compose exec -T db pg_dump -U sisgece -d sisgece -Fc > backups/sisgece.dump
docker compose exec -T db createdb -U sisgece sisgece_restore_test
docker compose exec -T db pg_restore --exit-on-error -U sisgece -d sisgece_restore_test < backups/sisgece.dump
docker compose exec -T db psql -U sisgece -d sisgece_restore_test -c 'SELECT count(*) FROM solicitacoes;'
```

Use nome novo para cada ensaio. Compare contagens e fluxos numa instância isolada.
O exemplo sobrescreve o arquivo local de backup: em agendamento, use nomes únicos.
Defina retenção de backups, RPO/RTO e política de dados com o IFCE. Não existe ainda
rotina de expurgo de dados pessoais; expiração do recibo não elimina os registros.

## Atualização e rollback

Faça backup antes de atualizar. Registre commit e etiqueta da imagem anterior.
Construa com outra etiqueta, altere SISGECE_IMAGE e execute compose up -d.
Em falha de migração, preserve o banco, examine logs e corrija a causa.
Rollback de esquema exige restaurar backup em banco separado e apontar a imagem
anterior para ele. Reconcilie registros posteriores ao backup antes de trocar tráfego.

## Monitoramento e manutenção

/api/health testa processo; /api/ready testa conexão e esquema. Monitore ambos,
latência, erros 5xx, disco e backups. Logs HTTP contêm rota parametrizada, status e
duração, sem corpo, cookie ou consulta. Não habilite logs de conteúdo no proxy.
Use docker compose logs --tail 100 e docker compose ps para diagnóstico.
Atualize dependências após CI e homologação. Recuperação de senha pode ser feita
por outro superusuário após verificação institucional de identidade. Perda de todos
os acessos exige operador autorizado com acesso ao comando superuser.

"""python -m backend.notifications.worker [--once]. Somente fila PostgreSQL."""
import argparse
import hashlib
import os
import random
import secrets
import signal
import time

import psycopg
from psycopg.rows import dict_row

from .config import provider_name, CONSENT_VERSION, LAB_AUTO_VERSION, AUTO_CONTACT_VERSION, authorized_without_challenge
from .providers import MockProvider, Result
from .webhooks import reconcile

MAX_ATTEMPTS = 5
LEASE_SECONDS = 120


def connection():
    return psycopg.connect(row_factory=dict_row, connect_timeout=4)


def recover(conn):
    reconcile(conn)
    # Nunca reenvia automaticamente quando o despacho pode ter chegado ao provedor.
    conn.execute('''UPDATE notificacoes SET
        estado=CASE WHEN despacho_em IS NULL THEN 'pending' ELSE 'uncertain' END,
        resultado=CASE WHEN despacho_em IS NULL THEN 'lease_recovered' ELSE 'dispatch_interrupted' END,
        reserva_token=CASE WHEN despacho_em IS NULL THEN NULL ELSE reserva_token END,reserva_ate=NULL
        WHERE estado='processing' AND reserva_ate<clock_timestamp()''')
    conn.execute('''UPDATE notificacoes n SET estado='cancelled',resultado='expired_or_superseded'
        FROM notificacao_assinaturas a,solicitacoes s
        WHERE n.assinatura=a.id AND n.solicitacao=s.id AND n.estado='pending'
        AND (n.expira_em<clock_timestamp() OR a.revogado_em IS NOT NULL
        OR s.status<>n.status_origem OR s.etapa IS DISTINCT FROM n.etapa_origem)''')


def claim(provider):
    with connection() as conn:
        recover(conn)
        accepted = [CONSENT_VERSION]
        if provider == 'evolution':
            accepted.append(AUTO_CONTACT_VERSION)
            if os.getenv('EVOLUTION_LAB_ENABLED') == '1' and os.getenv('EVOLUTION_LAB_AUTO_FLOW') == '1':
                accepted.append(LAB_AUTO_VERSION)
        row = conn.execute('''SELECT n.* FROM notificacoes n
            JOIN notificacao_assinaturas a ON a.id=n.assinatura
            WHERE n.estado='pending' AND n.provedor=%s AND (a.verificado_em IS NOT NULL OR a.consentimento_versao=ANY(%s))
            AND a.revogado_em IS NULL AND n.proxima_tentativa<=clock_timestamp()
            ORDER BY n.proxima_tentativa,n.id LIMIT 1 FOR UPDATE OF n SKIP LOCKED''', (provider,accepted)).fetchone()
        if not row:
            return None
        token = secrets.token_hex(16)
        return conn.execute('''UPDATE notificacoes SET estado='processing',reserva_token=%s,
            reserva_ate=clock_timestamp()+make_interval(secs=>%s),despacho_em=NULL
            WHERE id=%s RETURNING *''', (token,LEASE_SECONDS,row['id'])).fetchone()


def prepare(row):
    with connection() as conn:
        # Mesmo ordenamento de bloqueios que a revogação: assinatura, depois fila.
        active = conn.execute('''SELECT a.verificado_em,a.revogado_em,a.consentimento_versao,s.status,s.etapa,
            s.declarado->>'telefone' AS telefone, s.tipo AS solicitacao_tipo,
            s.data_solicitada AS solicitacao_data,
            s.horario_solicitado AS solicitacao_horario FROM notificacao_assinaturas a
            JOIN solicitacoes s ON s.id=a.solicitacao WHERE a.id=%s FOR UPDATE OF a''',
            (row['assinatura'],)).fetchone()
        current = conn.execute('''SELECT * FROM notificacoes WHERE id=%s AND estado='processing'
            AND reserva_token=%s AND reserva_ate>clock_timestamp() FOR UPDATE''',
            (row['id'],row['reserva_token'])).fetchone()
        if not current:
            return False
        if (not active or active['revogado_em'] or (not active['verificado_em'] and not authorized_without_challenge(active['consentimento_versao'])) or
            active['telefone'] != row['telefone'] or active['status'] != row['status_origem'] or
            active['etapa'] != row['etapa_origem']):
            conn.execute("UPDATE notificacoes SET estado='cancelled',resultado='authorization_changed' WHERE id=%s",(row['id'],))
            return False
        # Dados mínimos da solicitação já autorizada; não incluem nome, CPF,
        # matrícula, justificativa, protocolo ou código público.
        row['solicitacao_tipo'] = active['solicitacao_tipo']
        row['solicitacao_data'] = active['solicitacao_data']
        row['solicitacao_horario'] = active['solicitacao_horario']
        if current['tentativas'] >= MAX_ATTEMPTS:
            conn.execute("UPDATE notificacoes SET estado='failed',resultado='attempts_exhausted' WHERE id=%s",(row['id'],))
            return False
        # Ritmo compartilhado por todos os workers, inclusive após reinício.
        keys = [(row['provedor'] + ':global',1),
                (row['provedor'] + ':' + hashlib.sha256(row['telefone'].encode()).hexdigest(),6)]
        for key, _ in keys:
            conn.execute("INSERT INTO notificacao_ritmo VALUES (%s,clock_timestamp()) ON CONFLICT DO NOTHING",(key,))
        times = conn.execute('''SELECT chave,disponivel_em,disponivel_em>clock_timestamp() AS busy
            FROM notificacao_ritmo WHERE chave=ANY(%s) ORDER BY chave FOR UPDATE''',
            ([key for key,_ in keys],)).fetchall()
        if any(item['busy'] for item in times):
            next_time = max(item['disponivel_em'] for item in times)
            conn.execute('''UPDATE notificacoes SET estado='pending',proxima_tentativa=%s,
                reserva_token=NULL,reserva_ate=NULL WHERE id=%s''',(next_time,row['id']))
            return False
        for key, seconds in keys:
            conn.execute('UPDATE notificacao_ritmo SET disponivel_em=clock_timestamp()+make_interval(secs=>%s) WHERE chave=%s',(seconds,key))
        conn.execute('''UPDATE notificacoes SET despacho_em=clock_timestamp(),tentativas=tentativas+1
            WHERE id=%s''',(row['id'],))
        return True


def finish(row, result):
    with connection() as conn:
        current = conn.execute('''SELECT * FROM notificacoes WHERE id=%s FOR UPDATE''',(row['id'],)).fetchone()
        # Webhook pode chegar antes da resposta HTTP. Nunca rebaixar confirmação.
        if not current or current['estado'] in ('delivered','cancelled'):
            return
        if current['reserva_token'] != row['reserva_token']:
            return
        if current['estado'] != 'processing' and not (current['estado']=='uncertain' and result.state=='sent'):
            return
        state = result.state
        if state == 'retry':
            state = 'failed' if current['tentativas'] >= MAX_ATTEMPTS else 'pending'
        delay = min(3600,30 * 2 ** max(0,current['tentativas']-1)) + random.randint(0,15)
        delay = max(delay,result.retry_after)
        conn.execute('''UPDATE notificacoes SET estado=%s,resultado=%s,
            externo_id=coalesce(externo_id,%s),
            enviado_em=CASE WHEN %s='sent' THEN coalesce(enviado_em,clock_timestamp()) ELSE enviado_em END,
            proxima_tentativa=clock_timestamp()+make_interval(secs=>%s),reserva_ate=NULL,
            despacho_em=CASE WHEN %s='pending' THEN NULL ELSE despacho_em END
            WHERE id=%s''',(state,result.code,result.external_id,state,delay,state,row['id']))
        reconcile(conn)


def process_one(provider):
    row = claim(provider.name)
    if not row:
        return False
    if prepare(row):
        try:
            result = provider.send(row)
        except Exception:
            # Erro inesperado após marcar despacho: conservar para conciliação.
            result = Result('uncertain','provider_exception')
        finish(row,result)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--once',action='store_true')
    args = parser.parse_args()
    if provider_name() == 'mock':
        provider = MockProvider()
    elif provider_name() == 'meta':
        from .meta import MetaProvider
        provider = MetaProvider()
    else:
        from .evolution import EvolutionProvider
        provider = EvolutionProvider()
    stopping = False
    def stop(*_):
        nonlocal stopping
        stopping = True
    signal.signal(signal.SIGTERM,stop)
    signal.signal(signal.SIGINT,stop)
    while not stopping:
        try:
            did_work = process_one(provider)
        except psycopg.Error:
            print('notification_worker database_unavailable',flush=True)
            did_work = False
            if args.once:
                raise SystemExit(1) from None
        if args.once:
            break
        if not did_work:
            time.sleep(1)


if __name__ == '__main__':
    main()

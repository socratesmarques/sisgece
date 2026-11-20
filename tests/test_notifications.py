"""Somente PostgreSQL descartável. Rede Meta sempre substituída nos testes."""
import os
import secrets
import unittest
from unittest.mock import patch

import psycopg
from psycopg.rows import dict_row

from backend.app import app
from backend.manage import migrate
from backend.notifications.phone import normalize_phone
from backend.notifications.config import CONSENT_VERSION
from backend.notifications.consent import confirm, challenge, revoke


class Notifications(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old_options = os.environ.get('PGOPTIONS')
        cls.schema = 'notify_test_' + secrets.token_hex(8)
        with psycopg.connect() as conn:
            conn.execute('CREATE SCHEMA ' + cls.schema)
        os.environ['PGOPTIONS'] = '-c search_path=' + cls.schema
        cls.config = patch.dict(os.environ, {'NOTIFICATIONS_PROVIDER': 'mock', 'WHATSAPP_REAL_SEND_ENABLED': '0'})
        cls.config.start()
        migrate()
        migrate()

    @classmethod
    def tearDownClass(cls):
        cls.config.stop()
        if cls.old_options is None:
            os.environ.pop('PGOPTIONS', None)
        else:
            os.environ['PGOPTIONS'] = cls.old_options
        with psycopg.connect() as conn:
            conn.execute('DROP SCHEMA ' + cls.schema + ' CASCADE')

    def setUp(self):
        self.client = app.test_client()
        with self.conn() as conn:
            conn.execute('TRUNCATE limites')

    def conn(self):
        return psycopg.connect(row_factory=dict_row)

    def post(self, path, data):
        return self.client.post('/api/' + path, json=data, headers={'X-SISGECE': '1'})

    def submit(self, **kw):
        body = dict(origem='Responsável',aluno='Fictício',matricula='T',responsavel='Teste',
                    cpf='12345678901',parentesco='Mãe',telefone='(85) 98765-4321',
                    tipo='Saída',data='2030-01-01',hora='12:00',justificativa='Teste',
                    whatsapp_consent=True,whatsapp_consent_version=CONSENT_VERSION,
                    whatsapp_recipient='responsavel')
        # Reproduz o formulário atual: sem caixas ou campos ocultos de autorização.
        if kw.pop('without_whatsapp_fields', False):
            body = {key: val for key, val in body.items() if not key.startswith('whatsapp_')}
        body.update(kw)
        return self.post('solicitar', body)

    def latest(self):
        with self.conn() as conn:
            return conn.execute('SELECT id FROM solicitacoes ORDER BY id DESC LIMIT 1').fetchone()['id']

    def test_phone(self):
        for value in ('85987654321', '(85) 98765-4321', '+55 85 98765-4321'):
            self.assertEqual(normalize_phone(value), '+5585987654321')
        for value in ('123', '00000000000', 'abc', '+55 00 99999-9999', '85987654321 ext 123'):
            with self.assertRaises(ValueError):
                normalize_phone(value)
        self.assertEqual(self.submit(telefone='00000000000').status_code, 400)

    def test_consent_and_revocation(self):
        self.assertEqual(self.submit(whatsapp_consent='true').status_code,400)
        self.assertEqual(self.submit(whatsapp_consent_version='old').status_code,400)
        receipt = self.submit()
        self.assertEqual(receipt.status_code,201)
        sid = self.latest()
        code = receipt.json
        token = self.post('notificacoes/confirmar-numero', code).json['mensagem'].split()[1]
        with self.conn() as conn:
            self.assertFalse(confirm(conn,token,'5585987654322','mock'))
            self.assertFalse(confirm(conn,token,'5585987654321','meta'))
            self.assertTrue(confirm(conn,token,'5585987654321','mock'))
            self.assertFalse(confirm(conn,token,'5585987654321','mock'))
        self.assertEqual(self.post('notificacoes/estado',code).json['estado'],'ativa')
        self.assertEqual(self.post('notificacoes/revogar',code).status_code,200)
        self.assertEqual(self.post('notificacoes/estado',code).json['estado'],'revogada')
        self.assertEqual(self.post('notificacoes/confirmar-numero',code).status_code,409)
        self.assertEqual(self.post('consulta',code).status_code,200)

    def test_no_implicit_consent_and_expiry(self):
        receipt = self.submit(whatsapp_consent=False)
        self.assertEqual(self.post('notificacoes/estado',receipt.json).json['estado'],'sem autorização')
        self.submit()
        with self.conn() as conn:
            token, _ = challenge(conn,self.latest())
            conn.execute("UPDATE notificacao_assinaturas SET desafio_expira=now()-interval '1 second'")
            self.assertFalse(confirm(conn,token,'5585987654321','mock'))

    def test_evolution_auto_notifies_all_valid_phone_numbers(self):
        from backend.notifications.config import AUTO_CONTACT_VERSION
        from backend.notifications.worker import claim, prepare
        # A automatização não depende de LOCAL_HTTP, allowlist ou flags de laboratório.
        with patch.dict(os.environ, {
            'NOTIFICATIONS_PROVIDER': 'evolution',
            'LOCAL_HTTP': '0',
            'EVOLUTION_LAB_ENABLED': '0',
            'EVOLUTION_LAB_AUTO_FLOW': '0',
            'EVOLUTION_ALLOWED_RECIPIENTS': '+5511999999999',
        }):
            created_sids = []
            for phone in ('85987654321', '85988887777'):
                receipt = self.submit(telefone=phone, without_whatsapp_fields=True)
                self.assertEqual(receipt.status_code, 201)
                sid = self.latest()
                created_sids.append(sid)
                with self.conn() as conn:
                    consent = conn.execute("""SELECT a.provedor,a.consentimento_versao,
                        n.telefone,n.estado FROM notificacao_assinaturas a
                        JOIN notificacoes n ON n.assinatura=a.id
                        WHERE a.solicitacao=%s""", (sid,)).fetchone()
                    self.assertEqual(consent['provedor'], 'evolution')
                    self.assertEqual(consent['consentimento_versao'], AUTO_CONTACT_VERSION)
                    self.assertEqual(consent['estado'], 'pending')
                    self.assertTrue(consent['telefone'].startswith('+55'))
                self.assertEqual(self.post('notificacoes/estado', receipt.json).json['estado'], 'ativa')
            # Limpa fila criada neste teste; nenhum envio externo.
            with self.conn() as conn:
                conn.execute(
                    "DELETE FROM notificacoes WHERE provedor='evolution' AND solicitacao=ANY(%s)",
                    (created_sids,))
                conn.execute("TRUNCATE notificacao_ritmo")

    def test_control_security(self):
        self.assertEqual(self.client.post('/api/notificacoes/revogar',json={}).status_code,403)
        self.assertEqual(self.post('notificacoes/revogar',{'codigo':'wrong'}).status_code,404)
        self.assertEqual(self.client.get('/api/pedidos/1/notificacoes').status_code,401)

    def test_outbox_transaction_and_idempotency(self):
        from backend.notifications.outbox import enqueue
        receipt = self.submit()
        sid = self.latest()
        with self.conn() as conn:
            row = conn.execute('SELECT * FROM notificacoes WHERE solicitacao=%s',(sid,)).fetchone()
            self.assertEqual(row['estado'],'pending')
            self.assertEqual(row['telefone'],'+5585987654321')
            enqueue(conn,sid,row['evento'],'cadastro')
            self.assertEqual(conn.execute('SELECT count(*) AS n FROM notificacoes WHERE solicitacao=%s',(sid,)).fetchone()['n'],1)
        with patch('backend.app.enqueue',side_effect=psycopg.OperationalError('test')):
            self.assertEqual(self.submit().status_code,503)
        self.assertEqual(self.latest(),sid)
        self.assertEqual(self.post('consulta',receipt.json).status_code,200)

    def test_authorized_changes_only(self):
        from werkzeug.security import generate_password_hash
        from concurrent.futures import ThreadPoolExecutor
        self.submit()
        sid = self.latest()
        name = 'staff' + secrets.token_hex(4)
        with self.conn() as conn:
            conn.execute("INSERT INTO administradores(nome,usuario,senha_hash,perfil) VALUES ('Teste',%s,%s,'coordenação')",(name,generate_password_hash('test-password')))
        def act():
            c = app.test_client()
            c.post('/api/login',json={'usuario':name,'senha':'test-password'},headers={'X-SISGECE':'1'})
            return c.post('/api/pedidos/'+str(sid),json={'acao':'aprovar'},headers={'X-SISGECE':'1'}).status_code
        with ThreadPoolExecutor(2) as pool:
            self.assertEqual(sorted(pool.map(lambda _:act(),range(2))),[200,409])
        with self.conn() as conn:
            rows = conn.execute('SELECT template_tipo,estado FROM notificacoes WHERE solicitacao=%s ORDER BY id',(sid,)).fetchall()
            self.assertEqual(rows,[{'template_tipo':'cadastro','estado':'cancelled'},{'template_tipo':'aprovar','estado':'pending'}])

    def verified(self):
        self.submit()
        sid = self.latest()
        with self.conn() as conn:
            token,_ = challenge(conn,sid)
            self.assertTrue(confirm(conn,token,'5585987654321','mock'))
        return sid

    def clear_queue(self):
        with self.conn() as conn:
            conn.execute('TRUNCATE notificacao_ritmo')
            conn.execute("UPDATE notificacoes SET estado='cancelled' WHERE estado IN ('pending','processing')")

    def test_mock_and_concurrent_workers(self):
        from backend.notifications.worker import process_one
        from backend.notifications.providers import MockProvider
        from concurrent.futures import ThreadPoolExecutor
        self.clear_queue()
        sid = self.verified()
        provider = MockProvider()
        with ThreadPoolExecutor(4) as pool:
            list(pool.map(lambda _:process_one(provider),range(4)))
        self.assertEqual(len(provider.messages),1)
        self.assertIn('SISGECE',provider.messages[0]['text'])
        self.assertNotIn('telefone',provider.messages[0])
        self.assertFalse(process_one(provider))
        with self.conn() as conn:
            row = conn.execute('SELECT estado,tentativas,externo_id FROM notificacoes WHERE solicitacao=%s',(sid,)).fetchone()
            self.assertEqual(row['estado'],'sent')
            self.assertEqual(row['tentativas'],1)
            self.assertTrue(row['externo_id'].startswith('mock-'))

    def test_approval_worker_loads_request_date_and_time(self):
        from backend.notifications.worker import process_one
        from backend.notifications.providers import MockProvider
        from datetime import date, time
        self.clear_queue()
        sid = self.verified()
        # Só para o teste: transformar a notificação existente em evento de aprovação.
        with self.conn() as conn:
            conn.execute("""UPDATE solicitacoes SET status='APROVADA'
                            WHERE id=%s""", (sid,))
            conn.execute("""UPDATE notificacoes SET template_tipo='aprovar',
                            status_origem='APROVADA' WHERE solicitacao=%s""", (sid,))
        provider = MockProvider()
        self.assertTrue(process_one(provider))
        self.assertEqual(len(provider.messages), 1)
        msg = provider.messages[0]['text']
        self.assertIn('Tipo: Saída', msg)
        self.assertIn('Data: 01/01/2030', msg)
        self.assertIn('Horário: 12:00', msg)
        self.assertNotIn('Fictício', msg)
        self.assertNotIn('12345678901', msg)

    def test_evolution_status_messages_do_not_create_rating_invites(self):
        from backend.notifications.outbox import enqueue
        self.clear_queue()
        with patch.dict(os.environ, {'NOTIFICATIONS_PROVIDER':'evolution',
                                     'EVOLUTION_FEEDBACK_ENABLED':'1'}):
            self.assertEqual(self.submit(without_whatsapp_fields=True).status_code,201)
            sid = self.latest()
            with self.conn() as conn:
                conn.execute("UPDATE solicitacoes SET status='APROVADA',etapa='saída concluída' WHERE id=%s",(sid,))
                eid = conn.execute("INSERT INTO eventos(solicitacao,acao) VALUES (%s,'portaria') RETURNING id",
                                   (sid,)).fetchone()['id']
                enqueue(conn,sid,eid,'portaria')
                self.assertEqual(conn.execute("SELECT count(*) AS n FROM notificacoes WHERE solicitacao=%s",
                                              (sid,)).fetchone()['n'], 2)
        with self.conn() as conn:
            self.assertEqual(conn.execute("SELECT count(*) AS n FROM notificacao_avaliacoes WHERE solicitacao=%s",
                                          (sid,)).fetchone()['n'], 0)

    def test_retry_permanent_and_uncertain(self):
        from backend.notifications.worker import process_one
        from backend.notifications.providers import MockProvider
        for outcome, expected in [('temporary','pending'),('permanent','failed'),('timeout','uncertain')]:
            self.clear_queue()
            sid = self.verified()
            process_one(MockProvider(outcome))
            with self.conn() as conn:
                row = conn.execute('SELECT *,proxima_tentativa>now() AS future FROM notificacoes WHERE solicitacao=%s',(sid,)).fetchone()
                self.assertEqual(row['estado'],expected)
                self.assertTrue(row['future'])
                conn.execute('TRUNCATE notificacao_ritmo')
                conn.execute('UPDATE notificacoes SET proxima_tentativa=now() WHERE solicitacao=%s',(sid,))
            provider = MockProvider()
            process_one(provider)
            self.assertEqual(len(provider.messages),1 if outcome=='temporary' else 0)

    def test_restart_and_revoke_before_dispatch(self):
        from backend.notifications.worker import claim, prepare, recover, process_one
        from backend.notifications.providers import MockProvider
        self.clear_queue()
        sid = self.verified()
        row = claim('mock')
        with self.conn() as conn:
            conn.execute("UPDATE notificacoes SET reserva_ate=now()-interval '1 second' WHERE id=%s",(row['id'],))
            recover(conn)
        self.assertFalse(prepare(row))
        row = claim('mock')
        self.assertTrue(prepare(row))
        with self.conn() as conn:
            conn.execute("UPDATE notificacoes SET reserva_ate=now()-interval '1 second' WHERE id=%s",(row['id'],))
            recover(conn)
            self.assertEqual(conn.execute('SELECT estado FROM notificacoes WHERE id=%s',(row['id'],)).fetchone()['estado'],'uncertain')
        self.assertFalse(process_one(MockProvider()))
        self.clear_queue()
        sid = self.verified()
        row = claim('mock')
        with self.conn() as conn:
            revoke(conn,sid)
        self.assertFalse(prepare(row))

    def test_direct_opt_in_without_false_verification(self):
        from backend.notifications.worker import process_one
        from backend.notifications.providers import MockProvider
        self.clear_queue()
        receipt = self.submit()
        sid = self.latest()
        self.assertEqual(self.post('notificacoes/estado', receipt.json).json['estado'], 'ativa')
        with self.conn() as conn:
            self.assertIsNone(conn.execute('SELECT verificado_em FROM notificacao_assinaturas WHERE solicitacao=%s',(sid,)).fetchone()['verificado_em'])
        provider = MockProvider()
        self.assertTrue(process_one(provider))
        self.assertEqual(len(provider.messages), 1)
        self.assertFalse(process_one(provider))
        self.clear_queue()
        self.submit(whatsapp_consent=False)
        self.assertFalse(process_one(provider))

    def test_legacy_unverified_never_sent(self):
        from backend.notifications.worker import process_one
        from backend.notifications.providers import MockProvider
        self.clear_queue()
        self.submit()
        with self.conn() as conn:
            conn.execute("UPDATE notificacao_assinaturas SET consentimento_versao='2026-11-17-v1' WHERE solicitacao=%s",(self.latest(),))
        provider = MockProvider()
        self.assertFalse(process_one(provider))
        self.assertEqual(provider.messages,[])

    def webhook(self, payload, valid=True):
        import json, hmac, hashlib
        raw = json.dumps(payload).encode()
        signature = hmac.new(b's'*32,raw,hashlib.sha256).hexdigest() if valid else 'wrong'
        return self.client.post('/api/notificacoes/webhook',data=raw,content_type='application/json',headers={'X-Hub-Signature-256':'sha256='+signature})

    def envelope(self, **kw):
        return {'object':'whatsapp_business_account','entry':[{'id':'123','changes':[{'field':'messages','value':{'metadata':{'phone_number_id':'456'},**kw}}]}]}

    def test_webhook_signature_verification_and_replay(self):
        config = {'WHATSAPP_APP_SECRET':'s'*32,'WHATSAPP_WEBHOOK_VERIFY_TOKEN':'v'*32,
                  'WHATSAPP_WABA_ID':'123','WHATSAPP_PHONE_NUMBER_ID':'456','NOTIFICATIONS_PROVIDER':'meta'}
        with patch.dict(os.environ,config):
            receipt = self.submit()
            sid = self.latest()
            with self.conn() as conn:
                token,_ = challenge(conn,sid)
            payload = self.envelope(messages=[{'id':'message-1','type':'text','from':'5585987654321','text':{'body':'CONFIRMAR '+token}}])
            self.assertEqual(self.webhook(payload,False).status_code,403)
            self.assertEqual(self.webhook(payload).status_code,200)
            self.assertEqual(self.webhook(payload).status_code,200)
            self.assertEqual(self.post('notificacoes/estado',receipt.json).json['estado'],'ativa')
            self.assertEqual(self.client.get('/api/notificacoes/webhook?hub.mode=subscribe&hub.verify_token='+('v'*32)+'&hub.challenge=12345').data,b'12345')
            self.assertEqual(self.client.get('/api/notificacoes/webhook?hub.mode=subscribe&hub.verify_token=wrong').status_code,403)
            payload = self.envelope(messages=[{'id':'stop-1','type':'text','from':'5585987654321','text':{'body':'PARAR'}}])
            self.assertEqual(self.webhook(payload).status_code,200)
            self.assertEqual(self.post('notificacoes/estado',receipt.json).json['estado'],'revogada')
            self.assertEqual(self.webhook({'object':'whatsapp_business_account','entry':[None]}).status_code,400)

    def test_early_out_of_order_delivery(self):
        from backend.notifications.worker import claim, prepare, finish
        from backend.notifications.providers import Result
        self.clear_queue()
        config = {'WHATSAPP_APP_SECRET':'s'*32,'WHATSAPP_WEBHOOK_VERIFY_TOKEN':'v'*32,
                  'WHATSAPP_WABA_ID':'123','WHATSAPP_PHONE_NUMBER_ID':'456','NOTIFICATIONS_PROVIDER':'meta'}
        with patch.dict(os.environ,config):
            self.submit()
            sid = self.latest()
            with self.conn() as conn:
                token,_ = challenge(conn,sid)
                self.assertTrue(confirm(conn,token,'5585987654321','meta'))
            row = claim('meta')
            self.assertTrue(prepare(row))
            delivery = dict(id='wamid.early',status='delivered',timestamp='1794873600',recipient_id='5585987654321')
            self.assertEqual(self.webhook(self.envelope(statuses=[delivery])).status_code,200)
            finish(row,Result('sent','meta_accepted','wamid.early'))
            for state in ('sent','failed','delivered','read'):
                self.assertEqual(self.webhook(self.envelope(statuses=[dict(delivery,status=state)])).status_code,200)
            with self.conn() as conn:
                self.assertEqual(conn.execute('SELECT estado FROM notificacoes WHERE id=%s',(row['id'],)).fetchone()['estado'],'delivered')

    def test_webhook_scope_and_size(self):
        config = {'WHATSAPP_APP_SECRET':'s'*32,'WHATSAPP_WEBHOOK_VERIFY_TOKEN':'v'*32,
                  'WHATSAPP_WABA_ID':'123','WHATSAPP_PHONE_NUMBER_ID':'456'}
        with patch.dict(os.environ,config):
            payload = self.envelope(statuses=[{'id':'other','status':'sent','timestamp':'1794873600'}])
            payload['entry'][0]['id']='other-account'
            self.assertEqual(self.webhook(payload).status_code,200)
            with self.conn() as conn:
                self.assertIsNone(conn.execute("SELECT * FROM notificacao_entregas WHERE externo_id='other'").fetchone())
            self.assertEqual(self.client.post('/api/notificacoes/webhook',data=b'x'*1048577).status_code,413)


    def test_all_transitions_and_staff_visibility(self):
        from werkzeug.security import generate_password_hash
        self.submit()
        sid = self.latest()
        clients = {}
        for role in ('coordenação','recepção','portaria','superusuário'):
            name = 'u'+secrets.token_hex(6)
            with self.conn() as conn:
                conn.execute("INSERT INTO administradores(nome,usuario,senha_hash,perfil) VALUES ('Teste',%s,%s,%s)",(name,generate_password_hash('test-password'),role))
            client = app.test_client()
            self.assertEqual(client.post('/api/login',json={'usuario':name,'senha':'test-password'},headers={'X-SISGECE':'1'}).status_code,200)
            clients[role]=client
            result = client.get('/api/pedidos/'+str(sid)+'/notificacoes')
            self.assertEqual(result.status_code,200 if role in ('coordenação','superusuário') else 403)
            if result.status_code==200:
                self.assertNotIn('telefone',str(result.json))
        actions = [('coordenação','aprovar'),('recepção','recepção'),('portaria','portaria'),
                   ('coordenação','corrigir portaria'),('portaria','portaria'),
                   ('coordenação','corrigir recepção'),('coordenação','reabrir análise'),
                   ('coordenação','reprovar')]
        for role,action in actions:
            response = clients[role].post('/api/pedidos/'+str(sid),json={'acao':action,'nota':'Teste','mensagem':'Mensagem privada da decisão'},headers={'X-SISGECE':'1'})
            self.assertEqual(response.status_code,200,(action,response.json))
        with self.conn() as conn:
            rows = conn.execute('SELECT template_tipo,estado FROM notificacoes WHERE solicitacao=%s ORDER BY id',(sid,)).fetchall()
            self.assertEqual([r['template_tipo'] for r in rows],['cadastro']+[action for _,action in actions])
            self.assertEqual([r['estado'] for r in rows],['cancelled']*len(actions)+['pending'])
        self.submit(tipo='Entrada')
        entry = self.latest()
        response = clients['recepção'].post('/api/pedidos/'+str(entry),json={'acao':'recepção'},headers={'X-SISGECE':'1'})
        self.assertEqual(response.status_code,409)
        with self.conn() as conn:
            self.assertEqual(conn.execute('SELECT count(*) AS n FROM notificacoes WHERE solicitacao=%s',(entry,)).fetchone()['n'],1)

    def test_entry_reception_is_final_step_and_portaria_is_excluded(self):
        from werkzeug.security import generate_password_hash

        self.assertEqual(self.submit(tipo='Entrada').status_code, 201)
        sid = self.latest()
        clients = {}
        for role in ('coordenação', 'recepção', 'portaria'):
            username = 'entrada-' + secrets.token_hex(5)
            with self.conn() as conn:
                conn.execute(
                    "INSERT INTO administradores(nome,usuario,senha_hash,perfil) VALUES (%s,%s,%s,%s)",
                    ('Teste de entrada', username, generate_password_hash('test-password'), role))
            client = app.test_client()
            login = client.post('/api/login',
                json={'usuario': username, 'senha': 'test-password'},
                headers={'X-SISGECE': '1'})
            self.assertEqual(login.status_code, 200)
            clients[role] = client

        def action(role, name, **extra):
            return clients[role].post('/api/pedidos/' + str(sid),
                json={'acao': name, **extra}, headers={'X-SISGECE': '1'})

        def stage():
            with self.conn() as conn:
                return conn.execute(
                    'SELECT status,etapa FROM solicitacoes WHERE id=%s', (sid,)).fetchone()

        with self.conn() as conn:
            protocol = conn.execute(
                'SELECT protocolo FROM solicitacoes WHERE id=%s', (sid,)).fetchone()['protocolo']
        listing_url = '/api/pedidos?tipo=Entrada&q=' + protocol
        detail_url = '/api/pedidos/' + str(sid)
        self.assertFalse(clients['recepção'].get(listing_url).json['itens'])
        self.assertEqual(clients['recepção'].get(detail_url).status_code, 404)
        self.assertEqual(action('recepção', 'recepção').status_code, 409)
        self.assertEqual(action('portaria', 'portaria').status_code, 409)

        self.assertEqual(action('coordenação', 'aprovar').status_code, 200)
        self.assertEqual(stage(), {'status': 'APROVADA', 'etapa': 'aguardando recepção'})
        self.assertEqual(clients['recepção'].get(detail_url).status_code, 200)
        self.assertEqual(clients['recepção'].get(detail_url).json['confirmacoes'],
                         {'recepção': None})
        self.assertEqual(len(clients['recepção'].get(listing_url).json['itens']), 1)
        self.assertEqual(clients['portaria'].get(detail_url).status_code, 404)
        self.assertFalse(clients['portaria'].get(listing_url).json['itens'])
        self.assertEqual(action('coordenação', 'recepção').status_code, 403)
        self.assertEqual(action('coordenação', 'corrigir recepção', nota='Teste').status_code, 409)
        self.assertEqual(action('recepção', 'recepção').status_code, 200)
        self.assertEqual(stage(), {'status': 'APROVADA', 'etapa': 'entrada concluída'})
        self.assertIsNotNone(clients['recepção'].get(detail_url).json['confirmacoes']['recepção'])
        self.assertEqual(action('recepção', 'recepção').status_code, 409)
        self.assertEqual(action('portaria', 'portaria').status_code, 409)
        self.assertEqual(action('coordenação', 'corrigir recepção', nota='Revisão').status_code, 200)
        self.assertEqual(stage()['etapa'], 'aguardando recepção')
        self.assertEqual(action('recepção', 'recepção').status_code, 200)
        self.assertEqual(stage()['etapa'], 'entrada concluída')
        self.assertEqual(action('coordenação', 'reabrir análise', nota='Revisar').status_code, 200)
        self.assertEqual(stage(), {'status': 'PENDENTE', 'etapa': None})
        self.assertEqual(clients['recepção'].get(detail_url).status_code, 404)

    def test_retry_exhaustion_and_rate_limit(self):
        from backend.notifications.worker import process_one
        from backend.notifications.providers import MockProvider
        self.clear_queue()
        sid = self.verified()
        for attempt in range(5):
            with self.conn() as conn:
                conn.execute('TRUNCATE notificacao_ritmo')
                conn.execute('UPDATE notificacoes SET proxima_tentativa=now() WHERE solicitacao=%s',(sid,))
            self.assertTrue(process_one(MockProvider('temporary')))
        with self.conn() as conn:
            row = conn.execute('SELECT estado,tentativas FROM notificacoes WHERE solicitacao=%s',(sid,)).fetchone()
            self.assertEqual(row,{'estado':'failed','tentativas':5})
        self.clear_queue()
        self.verified()
        self.assertTrue(process_one(MockProvider()))
        sid = self.verified()
        mock = MockProvider()
        self.assertTrue(process_one(mock))
        self.assertEqual(mock.messages,[])
        with self.conn() as conn:
            row = conn.execute('SELECT estado,tentativas FROM notificacoes WHERE solicitacao=%s',(sid,)).fetchone()
            self.assertEqual(row,{'estado':'pending','tentativas':0})

    def test_expiration_and_late_response(self):
        from backend.notifications.worker import claim, prepare, recover, finish, process_one
        from backend.notifications.providers import MockProvider, Result
        self.clear_queue()
        sid = self.verified()
        with self.conn() as conn:
            conn.execute("UPDATE notificacoes SET expira_em=now()-interval '1 second' WHERE solicitacao=%s",(sid,))
        self.assertFalse(process_one(MockProvider()))
        self.clear_queue()
        self.verified()
        row = claim('mock')
        self.assertTrue(prepare(row))
        with self.conn() as conn:
            conn.execute("UPDATE notificacoes SET reserva_ate=now()-interval '1 second' WHERE id=%s",(row['id'],))
            recover(conn)
        finish(row,Result('sent','late_response','mock-late'))
        with self.conn() as conn:
            self.assertEqual(conn.execute('SELECT estado,externo_id FROM notificacoes WHERE id=%s',(row['id'],)).fetchone(),{'estado':'sent','externo_id':'mock-late'})


class MetaTransport(unittest.TestCase):
    def setUp(self):
        self.config = patch.dict(os.environ,{'WHATSAPP_REAL_SEND_ENABLED':'1',
            'WHATSAPP_ACCESS_TOKEN':'test-token','WHATSAPP_API_VERSION':'v27.0','WHATSAPP_PHONE_NUMBER_ID':'456'})
        self.config.start()
        # O guard bloqueia toda chamada acidental. Cada teste fornece transporte falso.
        self.transport = patch('backend.notifications.meta.http_send',side_effect=AssertionError('Network forbidden'))
        self.http = self.transport.start()
        self.addCleanup(self.transport.stop)
        self.addCleanup(self.config.stop)
        self.row = {'id':1,'telefone':'+5585987654321','template_nome':'sisgece_cadastro','template_idioma':'pt_BR'}

    def test_disabled_and_success_payload(self):
        import json
        from backend.notifications.meta import MetaProvider
        with patch.dict(os.environ,{'WHATSAPP_REAL_SEND_ENABLED':'0'}):
            with self.assertRaises(ValueError):
                MetaProvider()
        self.http.side_effect=None
        self.http.return_value=b'{"messages":[{"id":"wamid.test"}]}'
        result = MetaProvider().send(self.row)
        self.assertEqual(result.external_id,'wamid.test')
        req = self.http.call_args.args[0]
        self.assertEqual(req.full_url,'https://graph.facebook.com/v27.0/456/messages')
        body = json.loads(req.data)
        self.assertEqual(body['type'],'template')
        self.assertEqual(body['template'],{'name':'sisgece_cadastro','language':{'code':'pt_BR'}})
        self.assertNotIn('aluno',body)
        self.assertNotIn('codigo',body)

    def test_http_errors_timeout_and_malformed_response(self):
        from io import BytesIO
        from urllib.error import HTTPError, URLError
        import socket
        from backend.notifications.meta import MetaProvider
        for status,code,expected in [(429,130429,'retry'),(400,131056,'retry'),(401,190,'failed'),(400,132001,'failed'),(500,131000,'uncertain')]:
            self.http.side_effect=HTTPError('https://graph.facebook.com',status,'test',{},BytesIO(('{"error":{"code":%d,"message":"private"}}'%code).encode()))
            result = MetaProvider().send(self.row)
            self.assertEqual(result.state,expected)
            self.assertNotIn('private',result.code)
        for error,expected in [(TimeoutError(),'uncertain'),(URLError(socket.gaierror()),'retry'),(URLError('broken'),'uncertain')]:
            self.http.side_effect=error
            self.assertEqual(MetaProvider().send(self.row).state,expected)
        self.http.side_effect=None
        for data in (b'bad',b'{}',b'{"messages":[]}',b'x'*65537):
            self.http.return_value=data
            self.assertEqual(MetaProvider().send(self.row).state,'uncertain')

    def test_no_redirect_or_invalid_template(self):
        from backend.notifications.meta import NoRedirect, MetaProvider
        self.assertIsNone(NoRedirect().redirect_request(None,None,302,'',{},'https://other.example'))
        self.assertEqual(MetaProvider().send(dict(self.row,template_nome='../bad')).state,'failed')
        self.http.assert_not_called()

    def test_retry_after(self):
        from io import BytesIO
        from urllib.error import HTTPError
        from backend.notifications.meta import MetaProvider
        self.http.side_effect = HTTPError('https://graph.facebook.com',429,'test',{'Retry-After':'300'},BytesIO(b'{"error":{"code":130429}}'))
        self.assertEqual(MetaProvider().send(self.row).retry_after,300)

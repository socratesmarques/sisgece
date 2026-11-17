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

    def test_control_security(self):
        self.assertEqual(self.client.post('/api/notificacoes/revogar',json={}).status_code,403)
        self.assertEqual(self.post('notificacoes/revogar',{'codigo':'wrong'}).status_code,404)
        self.assertEqual(self.client.get('/api/pedidos/1/notificacoes').status_code,401)

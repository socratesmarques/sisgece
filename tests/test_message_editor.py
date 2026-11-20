"""Editor de mensagens: segurança, concorrência, auditoria e integração com a fila.

Executar somente em PostgreSQL descartável, como a suíte atual.
"""
import os
import secrets
import unittest
from datetime import date, time
from unittest.mock import patch

import psycopg
from psycopg.rows import dict_row
from werkzeug.security import generate_password_hash

from backend.app import app
from backend.manage import migrate
from backend.notifications.message_editor import validate_body
from backend.notifications.outbox import TEMPLATES, message_text


class MessageEditor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old_options = os.environ.get('PGOPTIONS')
        cls.schema = 'message_editor_test_' + secrets.token_hex(6)
        with psycopg.connect() as conn:
            conn.execute('CREATE SCHEMA ' + cls.schema)
        os.environ['PGOPTIONS'] = '-c search_path=' + cls.schema
        cls.env = patch.dict(os.environ, {
            'NOTIFICATIONS_PROVIDER': 'mock',
            'WHATSAPP_REAL_SEND_ENABLED': '0',
        })
        cls.env.start()
        migrate()
        cls.password = secrets.token_urlsafe(24)
        with psycopg.connect() as conn:
            for i, role in enumerate(('superusuário', 'coordenação')):
                conn.execute('''INSERT INTO administradores
                    (nome,usuario,perfil,senha_hash) VALUES (%s,%s,%s,%s)''',
                    ('Teste ' + role, 'editor' + str(i), role,
                     generate_password_hash(cls.password)))

    @classmethod
    def tearDownClass(cls):
        cls.env.stop()
        if cls.old_options is None:
            os.environ.pop('PGOPTIONS', None)
        else:
            os.environ['PGOPTIONS'] = cls.old_options
        with psycopg.connect() as conn:
            conn.execute('DROP SCHEMA ' + cls.schema + ' CASCADE')

    def setUp(self):
        self.public = app.test_client()
        self.admin = app.test_client()
        self.coord = app.test_client()
        for client, name in ((self.admin, 'editor0'), (self.coord, 'editor1')):
            self.assertEqual(self.post(client, 'login',
                                      {'usuario': name, 'senha': self.password}).status_code, 200)
        with psycopg.connect() as conn:
            conn.execute('DELETE FROM notificacao_modelos_historico')
            conn.execute('DELETE FROM notificacao_modelos')
            conn.execute('TRUNCATE limites')

    def post(self, client, path, data):
        return client.post('/api/' + path, json=data, headers={'X-SISGECE': '1'})

    def save(self, **kwargs):
        return self.post(self.admin, 'notificacoes/modelos',
                         {'tipo': 'cadastro', 'texto': 'Texto alterado do SISGECE.',
                          'ativo': True, 'versao': 0, **kwargs})

    def test_permission_and_csrf(self):
        for path in ('/api/notificacoes/modelos',
                     '/api/notificacoes/modelos/historico?tipo=cadastro'):
            self.assertEqual(self.public.get(path).status_code, 401)
            self.assertEqual(self.coord.get(path).status_code, 403)
        self.assertEqual(self.public.get('/api/notificacoes/modelos/prever').status_code, 405)
        for path, data in (
            ('notificacoes/modelos', {'tipo':'cadastro','versao':0,'texto':'Texto alterado','ativo':True}),
            ('notificacoes/modelos/prever', {'tipo':'cadastro','texto':'Texto suficiente.'}),
        ):
            self.assertEqual(self.post(self.public, path, data).status_code, 401)
            self.assertEqual(self.post(self.coord, path, data).status_code, 403)
            self.assertEqual(self.admin.post('/api/' + path, json=data).status_code, 403)

    def test_defaults_preview_and_dynamic_fields(self):
        result = self.admin.get('/api/notificacoes/modelos')
        self.assertEqual(result.status_code, 200)
        self.assertEqual(len(result.json['itens']), 8)
        self.assertEqual(result.json['marcadores'], ['tipo', 'data', 'horario'])
        self.assertTrue(all(row['versao'] == 0 and row['ativo'] for row in result.json['itens']))
        preview = self.post(self.admin, 'notificacoes/modelos/prever', {
            'tipo': 'recepção', 'texto': 'O pedido de {tipo} em {data} às {horario} foi processado.',
            'movimentacao': 'Entrada',
        })
        self.assertEqual(preview.status_code, 200)
        msg = preview.json['texto']
        for part in ('Entrada', '21/01/2030', '14:30', 'entrada foi concluída na recepção',
                     'SISGECE'):
            self.assertIn(part, msg)
        self.assertNotIn('Portaria ·', msg)
        self.assertEqual(self.post(self.admin, 'notificacoes/modelos/prever', {
            'tipo':'recepção', 'texto':'Simulação de {tipo}.', 'movimentacao':'Indefinida',
        }).status_code, 400)

    def test_reject_invalid_data_and_placeholders(self):
        invalid = [
            '{nome} é responsável.', '{tipo.__class__} teste', '{tipo!r} teste',
            '{tipo:20} teste', 'Texto {sem_fechar', '{aluno}', ' ',
            'a' * 1501, '\x00' + 'Texto válido com outros caracteres.',
        ]
        for body in invalid:
            with self.subTest(body=body[:35]):
                with self.assertRaises(ValueError):
                    validate_body(body)
                self.assertEqual(self.save(texto=body).status_code, 400)
        self.assertEqual(self.save(ativo='true').status_code, 400)
        self.assertEqual(self.save(versao=True).status_code, 400)
        self.assertEqual(self.save(tipo='evento desconhecido').status_code, 400)
        self.assertEqual(self.save(tipo={}).status_code, 400)
        self.assertEqual(self.save(acao='excluir').status_code, 400)
        self.assertEqual(self.save(versao=-1).status_code, 400)
        self.assertEqual(self.save(texto='<script>alert(1)</script>').status_code, 200)
        # A interface renderiza tudo via textContent, sem inserir HTML.
        self.assertNotIn('innerHTML', open('frontend/static/main.js',encoding='utf8').read())

    def test_save_revision_conflict_restore_and_audit(self):
        saved = self.save(texto='Olá! Seu pedido de {tipo} foi recebido.')
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json['modelo']['versao'], 1)
        self.assertTrue(saved.json['modelo']['personalizado'])
        self.assertEqual(self.save().status_code, 409)
        history = self.admin.get('/api/notificacoes/modelos/historico?tipo=cadastro')
        self.assertEqual(len(history.json['itens']), 1)
        self.assertEqual(history.json['itens'][0]['versao'], 1)
        self.assertEqual(history.json['itens'][0]['acao'], 'salvar')
        self.assertEqual(self.post(self.admin, 'notificacoes/modelos', {
            'tipo':'cadastro','versao':1,'ativo':False,
            'texto':'Comunicado de teste para responsáveis.',
        }).status_code, 200)
        self.assertFalse(self.admin.get('/api/notificacoes/modelos').json['itens'][0]['ativo'])
        restored = self.post(self.admin, 'notificacoes/modelos', {
            'tipo':'cadastro','versao':2,'acao':'restaurar',
        })
        self.assertEqual(restored.status_code, 200)
        self.assertEqual(restored.json['modelo']['texto'], TEMPLATES['cadastro'][1])
        self.assertEqual(restored.json['modelo']['versao'], 3)
        self.assertTrue(restored.json['modelo']['ativo'])
        history = self.admin.get('/api/notificacoes/modelos/historico?tipo=cadastro').json['itens']
        self.assertEqual([h['versao'] for h in history], [3,2,1])
        self.assertEqual(history[0]['acao'], 'restaurar')
        with psycopg.connect() as conn:
            records = conn.execute("SELECT nota FROM eventos WHERE acao='Edição de mensagem WhatsApp'")
            notes = [r[0] for r in records]
            self.assertEqual(len(notes), 3)
            self.assertTrue(all('Comunicado de teste' not in note for note in notes))

    def test_evolution_snapshot_and_disable_future_notifications(self):
        from backend.notifications.worker import claim, prepare
        with patch.dict(os.environ, {'NOTIFICATIONS_PROVIDER': 'evolution'}):
            body = 'Aviso: o pedido de {tipo} foi registrado para {data} às {horario}.'
            self.assertEqual(self.save(texto=body).status_code, 200)
            def submit():
                return self.post(self.public, 'solicitar', {
                    'origem':'Aluno','aluno':'Aluno fictício','matricula':'TESTE',
                    'responsavel':'Responsável fictício','telefone':'85987654321',
                    'tipo':'Entrada','data':'2030-01-21','hora':'14:30',
                    'justificativa':'Teste isolado de notificação',
                })
            self.assertEqual(submit().status_code, 201)
            with psycopg.connect(row_factory=dict_row) as conn:
                saved = conn.execute("SELECT * FROM notificacoes WHERE provedor='evolution' ORDER BY id DESC LIMIT 1").fetchone()
                self.assertEqual(saved['corpo_personalizado'], body)
                count = conn.execute("SELECT COUNT(*) AS n FROM notificacoes WHERE provedor='evolution'").fetchone()['n']
            self.assertEqual(self.post(self.admin, 'notificacoes/modelos', {
                'tipo':'cadastro','versao':1,'texto':'Este evento está temporariamente desligado.',
                'ativo':False,
            }).status_code, 200)
            self.assertEqual(submit().status_code, 201)
            with psycopg.connect(row_factory=dict_row) as conn:
                self.assertEqual(conn.execute("SELECT COUNT(*) AS n FROM notificacoes WHERE provedor='evolution'").fetchone()['n'], count)
            delivered = message_text('cadastro', {
                **saved, 'solicitacao_tipo':'Entrada',
                'solicitacao_data':date(2030,1,21),
                'solicitacao_horario':time(14,30),
            })
            self.assertIn('Aviso: o pedido de Entrada foi registrado para 21/01/2030 às 14:30.', delivered)
            self.assertNotIn('temporariamente desligado', delivered)


if __name__ == '__main__':
    unittest.main()

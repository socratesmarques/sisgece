"""Editor de mensagens: segurança, concorrência, auditoria e integração com a fila.

Executar somente em PostgreSQL descartável, como a suíte atual.
"""
import os
import secrets
import unittest
from datetime import date, time
from pathlib import Path
from unittest.mock import patch

import psycopg
from psycopg.rows import dict_row
from werkzeug.security import generate_password_hash

from backend.app import app
from backend.manage import migrate
from backend.notifications.message_editor import validate_body
from backend.notifications.outbox import TEMPLATES, full_template, message_text


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
        self.assertEqual(result.json['marcadores'], ['tipo', 'data', 'horario',
                'detalhes_etapa', 'detalhes_solicitacao', 'convite_avaliacao'])
        self.assertTrue(all(row['versao'] == 0 and row['ativo'] for row in result.json['itens']))
        self.assertTrue(all(row['texto'].startswith('*SISGECE') for row in result.json['itens']))
        self.assertTrue(all('mensagem automática' in row['texto'] for row in result.json['itens']))
        preview = self.post(self.admin, 'notificacoes/modelos/prever', {
            'tipo': 'recepção', 'texto': 'O pedido de {tipo} em {data} às {horario} foi processado.',
            'movimentacao': 'Entrada',
        })
        self.assertEqual(preview.status_code, 200)
        msg = preview.json['texto']
        self.assertEqual(msg, 'O pedido de Entrada em 21/01/2030 às 14:30 foi processado.')
        self.assertNotIn('SISGECE', msg)  # Sem cabeçalho/rodapé implícitos.
        with_details = self.post(self.admin, 'notificacoes/modelos/prever', {
            'tipo': 'recepção',
            'texto': 'Recepção: {detalhes_etapa}\n\n{convite_avaliacao}',
            'movimentacao': 'Entrada',
            'simular_avaliacao': True,
        })
        self.assertEqual(with_details.status_code, 200)
        self.assertIn('entrada foi concluída na recepção', with_details.json['texto'])
        self.assertIn('AVALIAR 1234567890ABCDEF 5', with_details.json['texto'])
        without_invite = self.post(self.admin, 'notificacoes/modelos/prever', {
            'tipo': 'recepção',
            'texto': 'Recepção: {detalhes_etapa}\n\n{convite_avaliacao}',
            'movimentacao': 'Saída',
            'simular_avaliacao': True,
        })
        self.assertNotIn('AVALIAR', without_invite.json['texto'])
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
        self.assertEqual(self.save(texto='Convite {convite_avaliacao} liberado.').status_code, 400)
        self.assertEqual(self.save(texto='Detalhes {detalhes_solicitacao} enviados.').status_code, 400)
        self.assertEqual(self.save(versao=True).status_code, 400)
        self.assertEqual(self.save(tipo='evento desconhecido').status_code, 400)
        self.assertEqual(self.save(tipo={}).status_code, 400)
        self.assertEqual(self.save(acao='excluir').status_code, 400)
        self.assertEqual(self.save(versao=-1).status_code, 400)
        self.assertEqual(self.save(texto='<script>alert(1)</script>').status_code, 200)
        # A interface renderiza tudo via textContent, sem inserir HTML.
        self.assertNotIn('innerHTML', Path('frontend/static/main.js').read_text(encoding='utf8'))

    def test_save_revision_conflict_restore_and_audit(self):
        with psycopg.connect() as conn:
            count_before = conn.execute(
                "SELECT count(*) FROM eventos WHERE acao='Edição de mensagem WhatsApp'"
            ).fetchone()[0]
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
        self.assertEqual(restored.json['modelo']['texto'], full_template('cadastro'))
        self.assertEqual(restored.json['modelo']['versao'], 3)
        self.assertTrue(restored.json['modelo']['ativo'])
        history = self.admin.get('/api/notificacoes/modelos/historico?tipo=cadastro').json['itens']
        self.assertEqual([h['versao'] for h in history], [3,2,1])
        self.assertEqual(history[0]['acao'], 'restaurar')
        self.assertTrue(all(h['completa'] for h in history))
        with psycopg.connect() as conn:
            records = conn.execute("SELECT nota FROM eventos WHERE acao='Edição de mensagem WhatsApp'")
            notes = [r[0] for r in records]
            self.assertEqual(len(notes) - count_before, 3)
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
                self.assertTrue(saved['mensagem_completa'])
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
            self.assertEqual(delivered, 'Aviso: o pedido de Entrada foi registrado para 21/01/2030 às 14:30.')
            self.assertNotIn('Esta é uma mensagem automática', delivered)
            self.assertNotIn('temporariamente desligado', delivered)


    def test_legacy_text_and_pending_messages_keep_old_format(self):
        from backend.notifications.outbox import HEADER, FOOTER
        legacy = {
            'corpo_personalizado': 'O pedido foi registrado pela coordenação.',
            'mensagem_completa': False, 'solicitacao_tipo': 'Saída',
            'solicitacao_data': date(2030, 1, 21),
            'solicitacao_horario': time(14, 30),
        }
        rendered = message_text('aprovar', legacy)
        self.assertTrue(rendered.startswith(HEADER))
        self.assertIn('O pedido foi registrado', rendered)
        self.assertIn('Informações da solicitação', rendered)
        self.assertTrue(rendered.endswith(FOOTER))
        with psycopg.connect() as conn:
            conn.execute("""INSERT INTO notificacao_modelos
                (tipo,corpo,ativo,versao,alterado_por)
                VALUES ('aprovar',%s,true,1,(SELECT id FROM administradores WHERE usuario='editor0'))""",
                (legacy['corpo_personalizado'],))
        model = self.admin.get('/api/notificacoes/modelos').json['itens'][1]
        self.assertTrue(model['legado'])
        self.assertTrue(model['texto'].startswith(HEADER))
        self.assertIn('O pedido foi registrado', model['texto'])
        self.assertEqual(self.post(self.admin, 'notificacoes/modelos', {
            'tipo': 'aprovar', 'versao': 1, 'texto': 'Novo aviso de aprovação completo.',
            'ativo': True,
        }).status_code, 200)
        with psycopg.connect(row_factory=dict_row) as conn:
            row = conn.execute("SELECT mensagem_completa FROM notificacao_modelos WHERE tipo='aprovar'").fetchone()
            self.assertTrue(row['mensagem_completa'])
        self.assertTrue(rendered.startswith(HEADER))  # Mensagens anteriores intactas.

    def test_complete_template_approval_and_evaluation(self):
        from backend.notifications.outbox import render_full_message
        sample = {'solicitacao_tipo':'Entrada', 'solicitacao_data':date(2030,1,21),
                  'solicitacao_horario':time(14,30)}
        text = render_full_message('aprovar', full_template('aprovar'), sample)
        self.assertEqual(text.count('*SISGECE | IFCE Campus Maranguape*'), 1)
        self.assertIn('*Informações da solicitação*', text)
        self.assertIn('Data: 21/01/2030', text)
        self.assertIn('Esta é uma mensagem automática', text)
        custom = render_full_message('aprovar', 'Aprovado: {tipo} às {horario}.', sample)
        self.assertEqual(custom, 'Aprovado: Entrada às 14:30.')
        entry = render_full_message('recepção', 'Finalizado: {detalhes_etapa}',
                                    {'solicitacao_tipo': 'Entrada'})
        self.assertIn('entrada foi concluída na recepção', entry)
        self.assertNotIn('portaria para solicitações de saída', entry)
        no_invite = render_full_message('reprovar', 'Resultado: {convite_avaliacao}',
                                        {'avaliacao_codigo':'1234567890ABCDEF'})
        self.assertIn('AVALIAR 1234567890ABCDEF 5', no_invite)
        malformed = render_full_message('reprovar', 'Resultado: {convite_avaliacao}',
                                         {'avaliacao_codigo':'invalid'})
        self.assertEqual(malformed, 'Resultado:')


if __name__ == '__main__':
    unittest.main()

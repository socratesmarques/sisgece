"""Testes de transporte Evolution sem rede, banco ou envio real."""
import json
import os
import socket
import unittest
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from backend.notifications.evolution import EvolutionProvider


CONFIG = {
    'NOTIFICATIONS_PROVIDER': 'evolution',
    'WHATSAPP_REAL_SEND_ENABLED': '1',
    'EVOLUTION_LAB_ENABLED': '1',
    'EVOLUTION_API_URL': 'http://evolution:8080',
    'EVOLUTION_INSTANCE': 'sisgece-teste',
    'EVOLUTION_API_KEY': 'test-only',
}


class EvolutionTransport(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, CONFIG)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.transport = patch('backend.notifications.evolution.http_send',
                               side_effect=AssertionError('Network forbidden'))
        self.http = self.transport.start()
        self.addCleanup(self.transport.stop)
        self.row = {'id': 1, 'telefone': '+5585987654321', 'template_tipo': 'cadastro'}

    def test_guard_requires_flags_but_no_recipient_allowlist(self):
        for change in ({'WHATSAPP_REAL_SEND_ENABLED': '0'},
                       {'EVOLUTION_LAB_ENABLED': '0'},
                       {'EVOLUTION_API_URL': 'https://example.com'},
                       {'EVOLUTION_API_URL': 'http://user:pass@evolution:8080'},
                       {'EVOLUTION_API_URL': 'http://evolution:8080/other'}):
            with patch.dict(os.environ, change):
                with self.assertRaises(ValueError):
                    EvolutionProvider()
        # Um novo telefone válido não pode ser bloqueado por uma lista de teste.
        with patch.dict(os.environ, {'EVOLUTION_ALLOWED_RECIPIENTS': '+5511999999999'}):
            self.http.side_effect = None
            self.http.return_value = b'{"key":{"id":"accepted-another"}}'
            result = EvolutionProvider().send(dict(self.row, telefone='+5585999999999'))
            self.assertEqual(result.state, 'sent')
            payload = json.loads(self.http.call_args.args[0].data)
            self.assertEqual(payload['number'], '5585999999999')
        self.http.reset_mock()
        self.http.side_effect = AssertionError('Network forbidden')
        self.assertEqual(EvolutionProvider().send(dict(self.row, template_tipo='unknown')).state, 'failed')
        self.http.assert_not_called()

    def test_post_payload_and_success(self):
        self.http.side_effect = None
        self.http.return_value = b'{"key":{"id":"evolution-message-id"},"status":"PENDING"}'
        result = EvolutionProvider().send(self.row)
        self.assertEqual((result.state, result.code, result.external_id),
                         ('sent', 'evolution_accepted', 'evolution-message-id'))
        request = self.http.call_args.args[0]
        self.assertEqual(request.full_url,
                         'http://evolution:8080/message/sendText/sisgece-teste')
        self.assertEqual(request.get_method(), 'POST')
        body = json.loads(request.data)
        self.assertEqual(body['number'], '5585987654321')
        self.assertIn('SISGECE', body['text'])
        self.assertNotIn('aluno', body)
        self.assertNotIn('codigo', body)
        self.assertNotIn('apikey', body)

    def test_approval_payload_contains_only_request_summary(self):
        from datetime import date, time
        self.http.side_effect = None
        self.http.return_value = b'{"key":{"id":"approved-123"}}'
        row = dict(self.row, template_tipo='aprovar',
                   solicitacao_tipo='Saída',
                   solicitacao_data=date(2030, 1, 2),
                   solicitacao_horario=time(14, 30),
                   aluno='NOME PRIVADO', matricula='MATRICULA PRIVADA',
                   justificativa='JUSTIFICATIVA PRIVADA')
        self.assertEqual(EvolutionProvider().send(row).state, 'sent')
        body = json.loads(self.http.call_args.args[0].data)
        for expected in ('Tipo: Saída', 'Data: 02/01/2030', 'Horário: 14:30'):
            self.assertIn(expected, body['text'])
        self.assertIn('*Informações da solicitação*\nTipo: Saída\nData: 02/01/2030\nHorário: 14:30', body['text'])
        self.assertNotIn(r'\\n', body['text'])
        for private in ('NOME PRIVADO', 'MATRICULA PRIVADA', 'JUSTIFICATIVA PRIVADA'):
            self.assertNotIn(private, body['text'])

    def test_http_and_ambiguous_errors(self):
        for status, expected in ((400,'failed'), (401,'failed'),
                                 (429,'retry'), (500,'uncertain')):
            self.http.side_effect = HTTPError('http://evolution:8080',status,'error',{},BytesIO(b'secret'))
            result = EvolutionProvider().send(self.row)
            self.assertEqual(result.state,expected)
            self.assertNotIn('secret',result.code)
        self.http.side_effect = URLError(socket.gaierror())
        self.assertEqual(EvolutionProvider().send(self.row).state,'retry')
        self.http.side_effect = TimeoutError()
        self.assertEqual(EvolutionProvider().send(self.row).state,'uncertain')
        self.http.side_effect = None
        for data in (b'bad',b'{}',b'{"key":{}}',b'x'*65537):
            self.http.return_value = data
            self.assertEqual(EvolutionProvider().send(self.row).state,'uncertain')

    def test_cannot_dispatch_after_disabling(self):
        p = EvolutionProvider()
        with patch.dict(os.environ, {'WHATSAPP_REAL_SEND_ENABLED': '0'}):
            self.assertEqual(p.send(self.row).code, 'evolution_disabled')
        self.http.assert_not_called()

    @staticmethod
    def final_notice(**overrides):
        row = dict(id=12, telefone='+5585987654321', template_tipo='recepção',
                   solicitacao_tipo='Entrada', status_origem='APROVADA',
                   etapa_origem='entrada concluída', avaliacao_codigo='0123456789ABCDEF')
        row.update(overrides)
        return row

    def test_send_five_list_options_when_enabled(self):
        self.http.side_effect = None
        self.http.return_value = b'{"key":{"id":"list-ok"}}'
        row = self.final_notice()
        self.assertEqual(EvolutionProvider().send(row).state, 'sent')
        self.assertIn('/sendText/', self.http.call_args.args[0].full_url)
        with patch.dict(os.environ, {'EVOLUTION_FEEDBACK_ENABLED': '1',
                                     'EVOLUTION_FEEDBACK_LIST_ENABLED': '1'}):
            result = EvolutionProvider().send(row)
            self.assertEqual((result.state, result.external_id), ('sent', 'list-ok'))
            request = self.http.call_args.args[0]
            self.assertIn('/message/sendList/sisgece-teste', request.full_url)
            body = json.loads(request.data)
            self.assertEqual(body['number'], '5585987654321')
            self.assertEqual(body['buttonText'], 'Escolher nota')
            self.assertIn('entrada foi concluída', body['description'])
            self.assertEqual([item['rowId'] for item in body['sections'][0]['rows']],
                             ['AVALIAR 0123456789ABCDEF ' + str(i) for i in range(1, 6)])
            self.assertNotIn('cpf', str(body).lower())
            self.assertNotIn('matricula', str(body).lower())

    def test_list_explicit_422_falls_back_to_text(self):
        self.http.side_effect = [
            HTTPError('http://evolution:8080', 422, 'unsupported', {}, BytesIO(b'no')),
            b'{"key":{"id":"fallback-ok"}}',
        ]
        with patch.dict(os.environ, {'EVOLUTION_FEEDBACK_ENABLED': '1',
                                     'EVOLUTION_FEEDBACK_LIST_ENABLED': '1'}):
            row = self.final_notice(template_tipo='portaria', solicitacao_tipo='Saída',
                                    etapa_origem='saída concluída')
            outcome = EvolutionProvider().send(row)
            self.assertEqual((outcome.state, outcome.code, outcome.external_id),
                             ('sent', 'evolution_accepted_text_fallback', 'fallback-ok'))
            self.assertEqual(self.http.call_count, 2)
            requests = [call.args[0] for call in self.http.call_args_list]
            self.assertIn('/sendList/', requests[0].full_url)
            self.assertIn('/sendText/', requests[1].full_url)
            self.assertIn('AVALIAR 0123456789ABCDEF 5',
                          json.loads(requests[1].data)['text'])

    def test_ambiguous_list_response_does_not_double_send(self):
        with patch.dict(os.environ, {'EVOLUTION_FEEDBACK_ENABLED': '1',
                                     'EVOLUTION_FEEDBACK_LIST_ENABLED': '1'}):
            for failure in (TimeoutError(), URLError('connection reset')):
                with self.subTest(failure=type(failure).__name__):
                    self.http.reset_mock()
                    self.http.side_effect = failure
                    self.assertEqual(EvolutionProvider().send(self.final_notice()).state,
                                     'uncertain')
                    self.assertEqual(self.http.call_count, 1)
            self.http.reset_mock()
            self.http.side_effect = None
            self.http.return_value = b'{}'
            self.assertEqual(EvolutionProvider().send(self.final_notice()).state, 'uncertain')
            self.assertEqual(self.http.call_count, 1)

    def test_pending_rejected_or_without_consent_always_uses_text(self):
        self.http.side_effect = None
        self.http.return_value = b'{"key":{"id":"text-ok"}}'
        with patch.dict(os.environ, {'EVOLUTION_FEEDBACK_ENABLED': '1',
                                     'EVOLUTION_FEEDBACK_LIST_ENABLED': '1'}):
            for row in (
                self.final_notice(status_origem='PENDENTE'),
                self.final_notice(etapa_origem='aguardando recepção'),
                self.final_notice(avaliacao_codigo=None),
                self.final_notice(template_tipo='reprovar', status_origem='REPROVADA'),
                self.final_notice(template_tipo='recepção', solicitacao_tipo='Saída'),
                self.final_notice(template_tipo='aprovar'),
                self.final_notice(corpo_personalizado='Mensagem sem convite de pesquisa.',
                                  mensagem_completa=True),
            ):
                with self.subTest(row=row):
                    self.assertEqual(EvolutionProvider().send(row).state, 'sent')
                    self.assertIn('/sendText/', self.http.call_args.args[0].full_url)


if __name__ == '__main__':
    unittest.main()

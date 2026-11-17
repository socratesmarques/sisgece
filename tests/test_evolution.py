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
    'EVOLUTION_ALLOWED_RECIPIENTS': '+5585987654321',
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

    def test_guard_requires_both_flags_and_allowlist(self):
        for change in ({'WHATSAPP_REAL_SEND_ENABLED': '0'},
                       {'EVOLUTION_LAB_ENABLED': '0'},
                       {'EVOLUTION_ALLOWED_RECIPIENTS': ''},
                       {'EVOLUTION_API_URL': 'https://example.com'},
                       {'EVOLUTION_API_URL': 'http://user:pass@evolution:8080'},
                       {'EVOLUTION_API_URL': 'http://evolution:8080/other'}):
            with patch.dict(os.environ, change):
                with self.assertRaises(ValueError):
                    EvolutionProvider()
        self.assertEqual(EvolutionProvider().send(dict(self.row, telefone='+5585999999999')).code,
                         'recipient_not_allowlisted')
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


if __name__ == '__main__':
    unittest.main()

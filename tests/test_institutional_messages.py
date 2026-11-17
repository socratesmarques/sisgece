"""Valida os oito textos institucionais e o link opcional sem fazer envios."""
import os
import unittest
from unittest.mock import patch

from backend.notifications.outbox import TEMPLATES, message_text, public_link


class InstitutionalMessages(unittest.TestCase):
    def test_all_eight_messages_without_placeholder_or_personal_data(self):
        self.assertEqual(len(TEMPLATES), 8)
        with patch.dict(os.environ, {'SISGECE_PUBLIC_URL': ''}):
            for action in TEMPLATES:
                with self.subTest(action=action):
                    text = message_text(action)
                    self.assertIn('SISGECE | IFCE Campus Maranguape', text)
                    self.assertIn('mensagem automática', text)
                    self.assertIn('portal oficial do SISGECE', text)
                    self.assertNotIn('[LINK DO SISGECE]', text)
                    self.assertNotIn('localhost', text)
                    self.assertNotIn('CPF', text)
                    self.assertNotIn('matrícula', text)
                    self.assertNotIn('código de consulta', text)
                    self.assertNotIn('http://', text)

    def test_optional_https_link(self):
        with patch.dict(os.environ, {'SISGECE_PUBLIC_URL': 'https://portal.exemplo.org/consulta/'}):
            for action in TEMPLATES:
                self.assertIn('https://portal.exemplo.org/consulta', message_text(action))
        for invalid in ('http://site.exemplo.org', 'http://localhost:8004',
                        'https://localhost:8004', 'https://user:secret@exemplo.org',
                        'https://portal.exemplo.org/?token=123'):
            with patch.dict(os.environ, {'SISGECE_PUBLIC_URL': invalid}):
                self.assertEqual(public_link(), '')
                self.assertNotIn(invalid, message_text('cadastro'))

    def test_specific_meaning_of_each_event(self):
        expectations = {
            'cadastro': 'pendente de análise',
            'aprovar': 'aprovada pela coordenação',
            'reprovar': 'não foi aprovada',
            'recepção': 'conferência pela recepção',
            'portaria': 'registrada pela portaria',
            'reabrir análise': 'reaberta para uma nova análise',
            'corrigir recepção': 'atualização no registro de conferência',
            'corrigir portaria': 'atualização no registro da portaria',
        }
        for action, fragment in expectations.items():
            with self.subTest(action=action):
                self.assertIn(fragment, message_text(action))


if __name__ == '__main__':
    unittest.main()

"""Valida os oito textos institucionais e o link opcional sem fazer envios."""
import os
import unittest
from unittest.mock import patch

from backend.notifications.outbox import TEMPLATES, message_text


class InstitutionalMessages(unittest.TestCase):
    def test_all_eight_messages_without_placeholder_or_personal_data(self):
        self.assertEqual(len(TEMPLATES), 8)
        with patch.dict(os.environ, {'SISGECE_PUBLIC_URL': ''}):
            for action in TEMPLATES:
                with self.subTest(action=action):
                    text = message_text(action)
                    self.assertIn('SISGECE | IFCE Campus Maranguape', text)
                    self.assertIn('mensagem automática', text)
                    self.assertNotIn('Para acompanhar o andamento', text)
                    self.assertNotIn('portal oficial do SISGECE', text)
                    self.assertNotIn('[LINK DO SISGECE]', text)
                    self.assertNotIn('localhost', text)
                    self.assertNotIn('CPF', text)
                    self.assertNotIn('matrícula', text)
                    self.assertNotIn('código de consulta', text)
                    self.assertNotIn('http://', text)

    def test_configured_link_is_not_included_in_notifications(self):
        with patch.dict(os.environ, {'SISGECE_PUBLIC_URL': 'https://portal.exemplo.org/consulta'}):
            for action in TEMPLATES:
                text = message_text(action)
                self.assertNotIn('portal.exemplo.org', text)
                self.assertNotIn('Para acompanhar o andamento', text)

    def test_removed_rating_never_appears_in_notifications(self):
        data = {'avaliacao_codigo': '1234567890ABCDEF'}
        for action in TEMPLATES:
            self.assertNotIn('AVALIAR', message_text(action, data))
        from backend.notifications.outbox import render_full_message
        rendered = render_full_message('portaria', 'Concluído. {convite_avaliacao}', data)
        self.assertEqual(rendered, 'Concluído.')

    def test_reception_message_distinguishes_entry_from_exit(self):
        entrada = message_text('recepção', {'solicitacao_tipo': 'Entrada'})
        saida = message_text('recepção', {'solicitacao_tipo': 'Saída'})
        self.assertIn('entrada foi concluída na recepção', entrada)
        self.assertIn('Não há etapa de portaria', entrada)
        self.assertIn('liberação pela portaria', saida)
        self.assertNotIn('entrada foi concluída', saida)

    def test_approval_details_only_when_typed_and_authorized(self):
        from datetime import date, time
        details = {
            'solicitacao_tipo': 'Saída',
            'solicitacao_data': date(2030, 1, 2),
            'solicitacao_horario': time(14, 30),
            'aluno': 'NOME PRIVADO',
            'cpf': '12345678901',
            'justificativa': 'MOTIVO PRIVADO',
        }
        text = message_text('aprovar', details)
        self.assertIn('Tipo: Saída', text)
        self.assertIn('Data: 02/01/2030', text)
        self.assertIn('Horário: 14:30', text)
        self.assertIn('estabelecidas pela instituição.\n\n*Informações da solicitação*\nTipo: Saída\nData: 02/01/2030\nHorário: 14:30', text)
        self.assertNotIn(r'\\n', text)
        for private in ('NOME PRIVADO', '12345678901', 'MOTIVO PRIVADO'):
            self.assertNotIn(private, text)
        self.assertNotIn('Informações da solicitação', message_text('cadastro', details))
        self.assertNotIn('Informações da solicitação', message_text('aprovar'))
        self.assertNotIn('Informações da solicitação', message_text('aprovar',
            dict(details, solicitacao_data='texto externo')))

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

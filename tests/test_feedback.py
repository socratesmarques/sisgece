"""Extrator restrito de respostas de avaliação Evolution, sem rede e sem banco."""
import os
import unittest
from unittest.mock import patch

from backend.notifications.feedback import extract_rating

CONFIG = {'EVOLUTION_INSTANCE': 'sisgece-teste'}


def payload(body, *, jid='5585987654321@s.whatsapp.net', mine=False,
            instance='sisgece-teste', event='messages.upsert', mid='test-message'):
    return {'event': event, 'instance': instance, 'data': {
        'key': {'id': mid, 'remoteJid': jid, 'fromMe': mine},
        'message': {'conversation': body}}}


class RatingParser(unittest.TestCase):
    def test_valid_rating_is_bound_to_phone_and_code(self):
        with patch.dict(os.environ, CONFIG):
            result = extract_rating(payload('AVALIAR 0123456789ABCDEF 4'))
            self.assertEqual(result[:3], ('+5585987654321', '0123456789ABCDEF', 4))
            self.assertEqual(len(result[3]), 64)

    def test_ignore_outbound_groups_and_unrelated_messages(self):
        with patch.dict(os.environ, CONFIG):
            invalid = [
                payload('AVALIAR 0123456789ABCDEF 4', mine=True),
                payload('AVALIAR 0123456789ABCDEF 4', jid='123456789@g.us'),
                payload('AVALIAR 0123456789ABCDEF 4', instance='outra'),
                payload('AVALIAR 0123456789ABCDEF 4', event='messages.update'),
                payload('AVALIAR 0123456789ABCDEF 6'),
                payload('NOTA 5'),
                payload('AVALIAR 0123456789ABCDEF 4', jid='5585987654321@lid'),
            ]
            for value in invalid:
                self.assertIsNone(extract_rating(value))
            self.assertIsNone(extract_rating({'event':'messages.upsert'}))


if __name__ == '__main__':
    unittest.main()

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

    def test_list_and_native_flow_answers(self):
        with patch.dict(os.environ, CONFIG):
            command = 'AVALIAR 0123456789ABCDEF 3'
            for message in (
                {'listResponseMessage': {'singleSelectReply': {'selectedRowId': command}}},
                {'interactiveResponseMessage': {'nativeFlowResponseMessage':
                    {'paramsJson': '{"id":"AVALIAR 0123456789ABCDEF 3"}'}}},
                {'buttonsResponseMessage': {'selectedButtonId': command}},
                {'templateButtonReplyMessage': {'selectedId': command}},
            ):
                with self.subTest(message=message):
                    item = payload(None)
                    item['data']['message'] = message
                    self.assertEqual(extract_rating(item)[:3],
                                     ('+5585987654321', '0123456789ABCDEF', 3))

    def test_reject_malicious_interactive_ids(self):
        with patch.dict(os.environ, CONFIG):
            for message in (
                {'listResponseMessage': {'singleSelectReply': {'selectedRowId': 'NOTA 5'}}},
                {'listResponseMessage': {'singleSelectReply': {'selectedRowId': 'AVALIAR 0123456789ABCDEF 6'}}},
                {'listResponseMessage': {'singleSelectReply': {'selectedRowId': 4}}},
                {'interactiveResponseMessage': {'nativeFlowResponseMessage': {'paramsJson': 'bad-json'}}},
                {'interactiveResponseMessage': {'nativeFlowResponseMessage': {'paramsJson': '["AVALIAR 0123456789ABCDEF 4"]'}}},
                {'interactiveResponseMessage': {'nativeFlowResponseMessage': {'paramsJson': '{"id":"AVALIAR 0123456789ABCDEF 4","extra":"' + 'X' * 1024 + '"}'}}},
            ):
                with self.subTest(message=message):
                    item = payload(None)
                    item['data']['message'] = message
                    self.assertIsNone(extract_rating(item))
            item = payload(None, mine=True)
            item['data']['message'] = {'listResponseMessage': {'singleSelectReply': {
                'selectedRowId': 'AVALIAR 0123456789ABCDEF 5'}}}
            self.assertIsNone(extract_rating(item))


if __name__ == '__main__':
    unittest.main()

"""Casos reais de endereçamento PN/LID do webhook Evolution, sem Docker."""
import os
import unittest
from unittest.mock import patch

from backend.notifications.feedback import consume, extract_rating, sender_phone


CODE = "A1B2C3D4E5F60708"
PHONE = "5585987654321@s.whatsapp.net"
LID = "123456789012345@lid"


def event(remote=LID, alt=PHONE, text=None):
    key = {"id": "msg-feedback-1", "fromMe": False, "remoteJid": remote}
    if alt is not None:
        key["remoteJidAlt"] = alt
    return {
        "event": "messages.upsert",
        "instance": "sisgece-teste",
        "data": {
            "key": key,
            "message": {"conversation": text or f"AVALIAR {CODE} 5"},
        },
    }


class FakeConnection:
    def __init__(self, matched=True):
        self.matched = matched
        self.params = None

    def execute(self, query, params):
        assert "UPDATE notificacao_avaliacoes" in query
        self.params = params
        return self

    def fetchone(self):
        return {"id": 1} if self.matched else None


class EvolutionFeedbackLidTests(unittest.TestCase):
    def setUp(self):
        self.patch_env = patch.dict(os.environ, {"EVOLUTION_INSTANCE": "sisgece-teste"})
        self.patch_env.start()

    def tearDown(self):
        self.patch_env.stop()

    def test_lid_uses_phone_from_alternative_jid(self):
        parsed = extract_rating(event())
        self.assertEqual(parsed[:3], ("+5585987654321", CODE, 5))
        self.assertEqual(len(parsed[3]), 64)
        db = FakeConnection()
        self.assertTrue(consume(db, event()))
        self.assertEqual(db.params[0], 5)
        self.assertEqual(db.params[2], CODE)
        self.assertEqual(db.params[3], "+5585987654321")

    def test_phone_jid_still_works(self):
        self.assertEqual(sender_phone({"remoteJid": PHONE}), "+5585987654321")
        self.assertEqual(extract_rating(event(remote=PHONE, alt=None))[:3],
                         ("+5585987654321", CODE, 5))

    def test_invalid_sender_formats_are_ignored(self):
        for bad in ("status@broadcast", "5585987654321@g.us",
                    "123456789012345@newsletter", "abc@lid", "123@lid"):
            with self.subTest(remote=bad):
                self.assertIsNone(extract_rating(event(remote=bad)))
        for bad_alt in (None, "not-a-number", "5585987654321@g.us",
                        "123456789012345@lid"):
            with self.subTest(alt=bad_alt):
                self.assertIsNone(extract_rating(event(alt=bad_alt)))
        self.assertIsNone(sender_phone({"remoteJid": LID}))

    def test_from_me_invalid_event_or_wrong_instance_is_rejected(self):
        payload = event()
        payload["data"]["key"]["fromMe"] = True
        self.assertIsNone(extract_rating(payload))
        payload["data"]["key"]["fromMe"] = False
        payload["instance"] = "outra"
        self.assertIsNone(extract_rating(payload))
        payload["instance"] = "sisgece-teste"
        payload["event"] = "messages.update"
        self.assertIsNone(extract_rating(payload))

    def test_missing_or_invalid_command_is_rejected(self):
        self.assertIsNone(extract_rating(event(text="oi")))
        self.assertIsNone(extract_rating(event(text=f"AVALIAR {CODE} 6")))
        self.assertIsNone(extract_rating(event(text="AVALIAR qualquer 5")))

    def test_list_selection_and_db_rejection(self):
        payload = event()
        payload["data"]["message"] = {"listResponseMessage": {
            "singleSelectReply": {"selectedRowId": f"AVALIAR {CODE} 4"},
        }}
        self.assertEqual(extract_rating(payload)[:3], ("+5585987654321", CODE, 4))
        db = FakeConnection(matched=False)
        self.assertFalse(consume(db, payload))
        self.assertEqual(db.params[3], "+5585987654321")


if __name__ == "__main__":
    unittest.main()

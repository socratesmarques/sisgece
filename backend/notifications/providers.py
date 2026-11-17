"""Transportes não registram tokens, telefones ou respostas brutas."""
from dataclasses import dataclass
from typing import Protocol
import os

from .outbox import message_text


@dataclass(frozen=True)
class Result:
    state: str
    code: str
    external_id: str | None = None
    retry_after: int = 0


class Provider(Protocol):
    name: str

    def send(self, notification: dict) -> Result: ...


class MockProvider:
    name = 'mock'

    def __init__(self, outcome=None):
        self.outcome = outcome or os.getenv('NOTIFICATIONS_MOCK_OUTCOME', 'success')
        if self.outcome not in ('success', 'temporary', 'permanent', 'timeout'):
            raise ValueError('Resultado mock inválido.')
        self.messages = []

    def send(self, notification):
        self.messages.append({'id': notification['id'], 'template': notification['template_nome'],
                              'text': message_text(notification['template_tipo'])})
        if self.outcome == 'temporary':
            return Result('retry','mock_temporary')
        if self.outcome == 'permanent':
            return Result('failed','mock_permanent')
        if self.outcome == 'timeout':
            return Result('uncertain','mock_timeout')
        return Result('sent','mock_accepted','mock-' + str(notification['id']))

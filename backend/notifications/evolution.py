"""Transporte Evolution API com validação de telefone e controle de envio.

Não registra tokens, telefones, URLs ou respostas brutas nos resultados.
A confirmação de envio HTTP não é comprovante de entrega no WhatsApp.
"""
import json
import os
import re
import socket
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request

from .config import real_enabled
from .meta import http_send
from .outbox import TEMPLATES, message_text
from .phone import normalize_phone
from .providers import Result


class EvolutionProvider:
    name = 'evolution'

    def __init__(self):
        if not real_enabled() or os.getenv('EVOLUTION_LAB_ENABLED') != '1':
            raise ValueError('Evolution desabilitada; exige duas habilitações explícitas.')
        endpoint = os.getenv('EVOLUTION_API_URL', '')
        parsed = urlsplit(endpoint)
        # Somente proxy local/Docker; nenhum endpoint externo ou URL com credenciais.
        if (parsed.scheme != 'http' or parsed.hostname not in
                ('evolution', 'evolution-api', 'host.docker.internal', 'localhost', '127.0.0.1')
                or parsed.path not in ('', '/') or parsed.query or parsed.fragment
                or parsed.username or parsed.password or not parsed.port):
            raise ValueError('Evolution deve usar endpoint HTTP local aprovado.')
        instance = os.getenv('EVOLUTION_INSTANCE', '')
        self.key = os.getenv('EVOLUTION_API_KEY', '')
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', instance):
            raise ValueError('Nome da instância inválido.')
        if not self.key or any(c in self.key for c in '\r\n'):
            raise ValueError('Configure EVOLUTION_API_KEY.')
        self.url = endpoint.rstrip('/') + '/message/sendText/' + quote(instance, safe='')
        self.list_url = endpoint.rstrip('/') + '/message/sendList/' + quote(instance, safe='')

    @staticmethod
    def rating_list(notification, text, number):
        """Somente eventos terminais aprovados, com convite autorizado no corpo."""
        if (os.getenv('EVOLUTION_FEEDBACK_ENABLED') != '1'
                or os.getenv('EVOLUTION_FEEDBACK_LIST_ENABLED') != '1'):
            return None
        code = notification.get('avaliacao_codigo')
        kind = notification.get('template_tipo')
        terminal = (
            notification.get('status_origem') == 'APROVADA'
            and (
                (kind == 'recepção' and notification.get('solicitacao_tipo') == 'Entrada'
                 and notification.get('etapa_origem') == 'entrada concluída')
                or (kind == 'portaria' and notification.get('solicitacao_tipo') == 'Saída'
                    and notification.get('etapa_origem') == 'saída concluída')
            )
        )
        if (not terminal or not isinstance(code, str)
                or not re.fullmatch(r'[A-F0-9]{16}', code)
                or f'AVALIAR {code} 5' not in text
                or len(text) > 1024):
            # Mensagem personalizada longa ou convite removido: usar texto.
            return None
        labels = ('Muito ruim', 'Ruim', 'Regular', 'Bom', 'Excelente')
        return {
            'number': number,
            'title': 'Avalie o SISGECE',
            'description': text,
            'buttonText': 'Escolher nota',
            'footerText': 'Avaliação opcional',
            'sections': [{
                'title': 'Sua avaliação',
                'rows': [
                    {'title': f'{score} - {label}',
                     'description': f'Nota {score} de 5',
                     'rowId': f'AVALIAR {code} {score}'}
                    for score, label in enumerate(labels, start=1)
                ],
            }],
        }

    def _request(self, url, payload):
        return Request(url, data=json.dumps(payload).encode('utf-8'),
                       headers={'apikey': self.key, 'Content-Type': 'application/json'},
                       method='POST')

    def send(self, notification):
        if not real_enabled() or os.getenv('EVOLUTION_LAB_ENABLED') != '1':
            return Result('failed', 'evolution_disabled')
        try:
            phone = normalize_phone(notification['telefone'])
        except (KeyError, ValueError):
            return Result('failed', 'invalid_recipient')
        kind = notification.get('template_tipo')
        if kind not in TEMPLATES:
            return Result('failed', 'invalid_message_type')
        text = message_text(kind, notification)
        text_payload = {'number': phone.lstrip('+'), 'text': text}
        list_payload = self.rating_list(notification, text, phone.lstrip('+'))
        request = self._request(self.list_url if list_payload else self.url,
                                list_payload or text_payload)
        used_fallback = False
        try:
            try:
                raw = http_send(request)  # Sem redirects/retries; timeout 15 s.
            except HTTPError as error:
                if list_payload is None or error.code not in (400, 404, 422):
                    raise
                # Rejeição explícita: sem confirmação de envio, permitido recorrer ao texto.
                error.close()
                used_fallback = True
                raw = http_send(self._request(self.url, text_payload))
            # Sem resposta válida/timeout: resultado ambíguo, nunca enviar duas vezes.
            if len(raw) > 65536:
                return Result('uncertain', 'evolution_invalid_response')
            data = json.loads(raw)
            message_id = data['key']['id']
            if not isinstance(message_id, str) or not 1 <= len(message_id) <= 512:
                return Result('uncertain', 'evolution_invalid_response')
            return Result('sent', 'evolution_accepted_text_fallback' if used_fallback
                          else 'evolution_accepted', message_id)
        except HTTPError as error:
            status = error.code
            error.close()
            if status == 429:
                return Result('retry', 'evolution_rate_limited')
            if status >= 500:
                return Result('uncertain', 'evolution_server_error')
            return Result('failed', 'evolution_http_' + str(status))
        except URLError as error:
            if isinstance(error.reason, (socket.gaierror, ConnectionRefusedError)):
                return Result('retry', 'evolution_connection_not_established')
            return Result('uncertain', 'evolution_transport_error')
        except (OSError, TimeoutError):
            return Result('uncertain', 'evolution_transport_error')
        except (ValueError, KeyError, IndexError, TypeError):
            return Result('uncertain', 'evolution_invalid_response')

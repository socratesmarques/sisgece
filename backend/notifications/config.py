import os

CONSENT_VERSION = '2026-11-17-v2'
CONSENT_TEXT = ('Autorizo o SISGECE a enviar pelo WhatsApp avisos sobre esta solicitação '
                'ao telefone informado.')


def authorized_without_challenge(version):
    # Não transforma autorizações antigas em opt-in sem confirmação.
    return version == CONSENT_VERSION


def provider_name():
    name = os.getenv('NOTIFICATIONS_PROVIDER', 'mock')
    if name not in ('mock', 'meta', 'evolution'):
        raise ValueError('Provedor de notificações inválido.')
    return name


def real_enabled():
    return os.getenv('WHATSAPP_REAL_SEND_ENABLED') == '1'

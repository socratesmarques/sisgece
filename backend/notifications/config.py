import os

CONSENT_VERSION = '2026-11-17-v1'
CONSENT_TEXT = ('Autorizo o SISGECE a enviar pelo WhatsApp avisos sobre esta solicitação '
                'ao telefone informado. Confirmo que sou titular do número ou tenho '
                'autorização do titular, que deverá confirmar a ativação no WhatsApp. '
                'Posso revogar a autorização a qualquer momento. A consulta pelo código continua disponível.')


def provider_name():
    name = os.getenv('NOTIFICATIONS_PROVIDER', 'mock')
    if name not in ('mock', 'meta'):
        raise ValueError('Provedor de notificações inválido.')
    return name


def real_enabled():
    return os.getenv('WHATSAPP_REAL_SEND_ENABLED') == '1'

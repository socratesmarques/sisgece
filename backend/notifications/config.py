"""Configuração de notificações e versões de inscrições."""
import os

CONSENT_VERSION = '2026-11-17-v2'
LAB_AUTO_VERSION = '2026-11-17-lab-auto'
AUTO_CONTACT_VERSION = '2026-11-17-auto-contact'
CONSENT_TEXT = ('Autorizo o SISGECE a enviar pelo WhatsApp avisos sobre esta solicitação '
                'ao telefone informado.')


def provider_name():
    name = os.getenv('NOTIFICATIONS_PROVIDER', 'mock')
    if name not in ('mock', 'meta', 'evolution'):
        raise ValueError('Provedor de notificações inválido.')
    return name


def real_enabled():
    return os.getenv('WHATSAPP_REAL_SEND_ENABLED') == '1'


def automatic_notifications_enabled():
    """Notificações como parte do cadastro para qualquer telefone válido.

    A automatização é padrão para o provedor Evolution. O mock e a Meta
    mantêm as regras de autorização existentes; o envio real ainda exige
    as credenciais e as flags próprias de cada transporte.
    """
    return provider_name() == 'evolution'


def authorized_without_challenge(version):
    if version == CONSENT_VERSION:
        return True
    if version == AUTO_CONTACT_VERSION:
        return automatic_notifications_enabled()
    # Compatibilidade com inscrições antigas do modo experimental.
    return (version == LAB_AUTO_VERSION and provider_name() == 'evolution'
            and os.getenv('EVOLUTION_LAB_ENABLED') == '1'
            and os.getenv('EVOLUTION_LAB_AUTO_FLOW') == '1')

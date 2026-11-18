import os

CONSENT_VERSION = '2026-11-17-v2'
LAB_AUTO_VERSION = '2026-11-17-lab-auto'
CONSENT_TEXT = ('Autorizo o SISGECE a enviar pelo WhatsApp avisos sobre esta solicitação '
                'ao telefone informado.')


def authorized_without_challenge(version):
    # Não transforma autorizações antigas em opt-in sem confirmação.
    return version == CONSENT_VERSION or (
        version == LAB_AUTO_VERSION
        and provider_name() == 'evolution'
        and os.getenv('EVOLUTION_LAB_ENABLED') == '1'
        and os.getenv('EVOLUTION_LAB_AUTO_FLOW') == '1')


def provider_name():
    name = os.getenv('NOTIFICATIONS_PROVIDER', 'mock')
    if name not in ('mock', 'meta', 'evolution'):
        raise ValueError('Provedor de notificações inválido.')
    return name


def real_enabled():
    return os.getenv('WHATSAPP_REAL_SEND_ENABLED') == '1'

def lab_auto_mode():
    """Atalhos de UX somente no laboratório local. Nunca habilitar em produção."""
    return (os.getenv('LOCAL_HTTP') == '1'
            and provider_name() == 'evolution'
            and os.getenv('EVOLUTION_LAB_ENABLED') == '1'
            and os.getenv('EVOLUTION_LAB_AUTO_FLOW') == '1')


def lab_auto_recipient(phone):
    """Somente números de teste explicitamente permitidos pela configuração."""
    if not lab_auto_mode():
        return False
    from .phone import normalize_phone
    allowed = os.getenv('EVOLUTION_ALLOWED_RECIPIENTS', '')
    if not allowed.strip():
        return False
    try:
        recipients = {normalize_phone(value.strip()) for value in allowed.split(',')}
        return 1 <= len(recipients) <= 5 and normalize_phone(phone) in recipients
    except ValueError:
        return False

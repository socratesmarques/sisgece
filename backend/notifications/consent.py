import hashlib
import os
import secrets

from .config import CONSENT_VERSION, AUTO_CONTACT_VERSION, provider_name, automatic_notifications_enabled
from .phone import normalize_phone


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def subscribe(conn, sid, body):
    consent = body.get('whatsapp_consent', False)
    if type(consent) is not bool:
        raise ValueError('Consentimento inválido.')
    feedback = body.get('whatsapp_feedback_consent', False)
    if type(feedback) is not bool:
        raise ValueError('Autorização de avaliação inválida.')

    # No provedor Evolution, o aviso do formulário informa que mensagens
    # de status são parte do fluxo de cada solicitação, sem caixas adicionais.
    # Não reutiliza a versão de consentimento explícito nem a versão do laboratório.
    # A ausência dos antigos campos corresponde ao formulário padrão atual.
    # Se um cliente da API declarar expressamente que não deseja mensagens,
    # respeitar essa escolha; jamais interpretá-la como autorização automática.
    explicit = 'whatsapp_consent' in body
    if explicit and not consent:
        if feedback:
            raise ValueError('Autorização de avaliação inválida.')
        return
    automatic = not explicit and automatic_notifications_enabled()
    if automatic:
        consent = True
        feedback = os.getenv('EVOLUTION_FEEDBACK_ENABLED') == '1'
    elif feedback and not consent:
        raise ValueError('Autorização de avaliação inválida.')
    if not consent:
        return
    if not automatic and body.get('whatsapp_consent_version') != CONSENT_VERSION:
        raise ValueError('Leia e aceite a versão atual da autorização.')
    target = body.get('whatsapp_recipient', 'responsavel')
    if target not in ('solicitante', 'responsavel'):
        raise ValueError('Escolha quem receberá as notificações.')
    conn.execute('''INSERT INTO notificacao_assinaturas
        (solicitacao,destinatario,provedor,consentimento_versao,avaliacao_consentida) VALUES (%s,%s,%s,%s,%s)''',
        (sid, target, provider_name(), AUTO_CONTACT_VERSION if automatic else CONSENT_VERSION, feedback))


def challenge(conn, sid):
    token = secrets.token_urlsafe(24)
    row = conn.execute('''UPDATE notificacao_assinaturas SET desafio_hash=%s,
        desafio_expira=clock_timestamp()+interval '15 minutes'
        WHERE solicitacao=%s AND revogado_em IS NULL AND verificado_em IS NULL
        RETURNING provedor''', (digest(token), sid)).fetchone()
    if not row:
        raise ValueError('Autorização ausente, revogada ou já confirmada.')
    return token, row['provedor']


def confirm(conn, token, sender, provider):
    try:
        phone = normalize_phone('+' + sender.lstrip('+'))
    except ValueError:
        return False
    row = conn.execute('''SELECT a.id,s.declarado->>'telefone' AS telefone
        FROM notificacao_assinaturas a JOIN solicitacoes s ON s.id=a.solicitacao
        WHERE a.desafio_hash=%s AND a.provedor=%s AND a.revogado_em IS NULL
        AND a.verificado_em IS NULL AND a.desafio_expira>clock_timestamp()
        FOR UPDATE OF a''', (digest(token), provider)).fetchone()
    if not row or not secrets.compare_digest(row['telefone'], phone):
        return False
    conn.execute('''UPDATE notificacao_assinaturas SET verificado_em=clock_timestamp(),
        desafio_hash=NULL,desafio_expira=NULL WHERE id=%s''', (row['id'],))
    return True


def revoke(conn, sid):
    row = conn.execute('''UPDATE notificacao_assinaturas SET
        revogado_em=coalesce(revogado_em,clock_timestamp()),desafio_hash=NULL,desafio_expira=NULL
        WHERE solicitacao=%s RETURNING id''', (sid,)).fetchone()
    if row:
        conn.execute('''UPDATE notificacoes SET estado='cancelled',resultado='consent_revoked'
            WHERE assinatura=%s AND (estado='pending' OR
            (estado='processing' AND despacho_em IS NULL))''', (row['id'],))
        conn.execute('''UPDATE notificacao_avaliacoes SET cancelado_em=clock_timestamp()
            WHERE assinatura=%s AND nota IS NULL AND cancelado_em IS NULL''',(row['id'],))
    return bool(row)

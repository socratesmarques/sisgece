import re
from urllib.parse import quote
import os

from flask import abort, request

from .config import CONSENT_TEXT, CONSENT_VERSION
from .consent import challenge, digest, revoke
from .phone import masked


def register(app, db, query, value, limit, staff):
    def lookup():
        limit('whatsapp-control', 20)
        code = value('codigo', 128)
        normalized = re.sub(r'[\s-]', '', code).upper()
        if re.fullmatch(r'[2-9A-HJ-NP-Z]{10}', normalized):
            code = normalized
        row = query('SELECT id FROM solicitacoes WHERE segredo=%s', (digest(code),)).fetchone()
        if not row:
            abort(404, 'Código de consulta inválido.')
        return row['id']

    @app.get('/api/notificacoes/config')
    def notification_config():
        return {'version': CONSENT_VERSION, 'text': CONSENT_TEXT}

    @app.post('/api/notificacoes/estado')
    def notification_status():
        sid = lookup()
        row = query('''SELECT a.destinatario,a.verificado_em,a.revogado_em,
            s.declarado->>'telefone' AS telefone FROM notificacao_assinaturas a
            JOIN solicitacoes s ON s.id=a.solicitacao WHERE a.solicitacao=%s''', (sid,)).fetchone()
        if not row:
            return {'estado': 'sem autorização'}
        return {'estado': 'revogada' if row['revogado_em'] else
                'ativa' if row['verificado_em'] else 'aguardando confirmação',
                'destinatario': row['destinatario'], 'telefone': masked(row['telefone'])}

    @app.post('/api/notificacoes/confirmar-numero')
    def start_confirmation():
        sid = lookup()
        try:
            token, provider = challenge(db(), sid)
        except ValueError as error:
            abort(409, str(error))
        business_phone = os.getenv('WHATSAPP_BUSINESS_NUMBER', '')
        if provider == 'meta' and not re.fullmatch(r'[1-9][0-9]{7,14}', business_phone):
            abort(503, 'Confirmação pelo WhatsApp ainda não configurada pela instituição.')
        message = 'CONFIRMAR ' + token
        return {'mensagem': message, 'expira_minutos': 15, 'provedor': provider,
                'url': 'https://wa.me/' + business_phone + '?text=' + quote(message) if provider == 'meta' else None}

    @app.post('/api/notificacoes/revogar')
    def revoke_notifications():
        revoke(db(), lookup())
        return {'ok': True}

    @app.get('/api/pedidos/<int:sid>/notificacoes')
    @staff('coordenação', 'superusuário')
    def notification_records(sid):
        if not query('SELECT id FROM solicitacoes WHERE id=%s', (sid,)).fetchone():
            abort(404)
        rows = query('''SELECT id,template_tipo,estado,tentativas,criado_em,enviado_em,
            entregue_em,resultado FROM notificacoes WHERE solicitacao=%s
            ORDER BY id DESC LIMIT 50''', (sid,)).fetchall()
        return {'itens': rows}

from flask import abort

from .config import CONSENT_TEXT, CONSENT_VERSION


def register(app, query, staff):
    @app.get('/api/notificacoes/config')
    def notification_config():
        return {'version': CONSENT_VERSION, 'text': CONSENT_TEXT}

    @app.get('/api/pedidos/<int:sid>/notificacoes')
    @staff('coordenação', 'superusuário')
    def notification_records(sid):
        if not query('SELECT id FROM solicitacoes WHERE id=%s', (sid,)).fetchone():
            abort(404)
        rows = query('''SELECT id,template_tipo,estado,tentativas,criado_em,enviado_em,
            entregue_em,resultado FROM notificacoes WHERE solicitacao=%s
            ORDER BY id DESC LIMIT 50''', (sid,)).fetchall()
        return {'itens': rows}

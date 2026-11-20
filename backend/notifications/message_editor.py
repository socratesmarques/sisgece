"""Editor administrativo dos textos Evolution, com auditoria e controle de versões.

A configuração salva vale apenas para novos eventos. Mensagens já enfileiradas
conservam o corpo capturado no evento. Templates Meta não são afetados.
"""
from datetime import date, time
from string import Formatter

from flask import abort, request

from .outbox import TEMPLATES, message_text

TOKENS = ('tipo', 'data', 'horario')
TITLES = {
    'cadastro': 'Solicitação recebida',
    'aprovar': 'Solicitação aprovada',
    'reprovar': 'Solicitação reprovada',
    'recepção': 'Conferência na recepção',
    'portaria': 'Saída pela portaria',
    'reabrir análise': 'Reabertura da análise',
    'corrigir recepção': 'Correção na recepção',
    'corrigir portaria': 'Correção na portaria',
}
MAX_TEXT = 1500
MIN_TEXT = 10


def validate_body(body):
    if not isinstance(body, str):
        raise ValueError('Informe o texto da mensagem.')
    body = body.replace('\r\n', '\n').strip()
    if not MIN_TEXT <= len(body) <= MAX_TEXT or '\x00' in body or '\r' in body:
        raise ValueError('O texto deve ter de 10 a 1500 caracteres.')
    try:
        for _, token, format_spec, conversion in Formatter().parse(body):
            if token is not None and (token not in TOKENS or format_spec or conversion):
                raise ValueError('Use apenas {tipo}, {data} e {horario}.')
    except ValueError as error:
        raise ValueError('Marcador inválido. Use apenas {tipo}, {data} e {horario}.') from error
    return body


def current_model(conn, action):
    row = conn.execute('''SELECT corpo, ativo, versao, alterado_em
        FROM notificacao_modelos WHERE tipo=%s''', (action,)).fetchone()
    return {
        'tipo': action,
        'titulo': TITLES[action],
        'texto': row['corpo'] if row else TEMPLATES[action][1],
        'padrao': TEMPLATES[action][1],
        'ativo': row['ativo'] if row else True,
        'versao': row['versao'] if row else 0,
        'personalizado': bool(row and row['corpo'] != TEMPLATES[action][1]),
        'alterado_em': row['alterado_em'].isoformat() if row else None,
    }


def register(app, db, staff, event):
    @app.get('/api/notificacoes/modelos')
    @staff('superusuário')
    def list_message_models():
        conn = db()
        return {'itens': [current_model(conn, action) for action in TEMPLATES],
                'marcadores': list(TOKENS)}

    @app.post('/api/notificacoes/modelos/prever')
    @staff('superusuário')
    def preview_message_model():
        payload = request.json
        action = payload.get('tipo')
        if action not in TEMPLATES:
            abort(400, 'Evento inválido.')
        try:
            body = validate_body(payload.get('texto'))
        except ValueError as error:
            abort(400, str(error))
        movement = payload.get('movimentacao', 'Entrada')
        if movement not in ('Entrada', 'Saída'):
            abort(400, 'Movimentação inválida.')
        sample = {
            'corpo_personalizado': body,
            'solicitacao_tipo': movement,
            'solicitacao_data': date(2030, 1, 21),
            'solicitacao_horario': time(14, 30),
        }
        return {'texto': message_text(action, sample)}

    @app.get('/api/notificacoes/modelos/historico')
    @staff('superusuário')
    def message_model_history():
        action = request.args.get('tipo')
        if action not in TEMPLATES:
            abort(400, 'Evento inválido.')
        rows = db().execute('''SELECT h.versao, h.corpo, h.ativo, h.acao, h.quando,
                a.nome AS autor
            FROM notificacao_modelos_historico h
            JOIN administradores a ON a.id=h.autor
            WHERE h.tipo=%s ORDER BY h.id DESC LIMIT 15''', (action,)).fetchall()
        return {'itens': [{
            'versao': row['versao'],
            'texto': row['corpo'],
            'ativo': row['ativo'],
            'acao': row['acao'],
            'quando': row['quando'].isoformat(),
            'autor': row['autor'],
        } for row in rows]}

    @app.post('/api/notificacoes/modelos')
    @staff('superusuário')
    def save_message_model():
        payload = request.json
        action = payload.get('tipo')
        if action not in TEMPLATES:
            abort(400, 'Evento inválido.')
        version = payload.get('versao')
        if type(version) is not int or version < 0:
            abort(400, 'Versão inválida.')
        operation = payload.get('acao', 'salvar')
        if operation not in ('salvar', 'restaurar'):
            abort(400, 'Ação inválida.')
        if operation == 'restaurar':
            body, enabled = TEMPLATES[action][1], True
        else:
            try:
                body = validate_body(payload.get('texto'))
            except ValueError as error:
                abort(400, str(error))
            enabled = payload.get('ativo')
            if type(enabled) is not bool:
                abort(400, 'Estado inválido.')

        conn = db()
        # O lock cobre inclusive o primeiro INSERT, evitando conflito silencioso.
        conn.execute('SELECT pg_advisory_xact_lock(%s)', (538100 + list(TEMPLATES).index(action),))
        previous = conn.execute('SELECT versao FROM notificacao_modelos WHERE tipo=%s FOR UPDATE',
                                (action,)).fetchone()
        current = previous['versao'] if previous else 0
        if current != version:
            abort(409, 'Esta mensagem foi alterada por outro administrador. Recarregue antes de salvar.')
        revision = current + 1
        conn.execute('''INSERT INTO notificacao_modelos (tipo,corpo,ativo,versao,alterado_por)
            VALUES (%s,%s,%s,%s,%s)
            ON CONFLICT(tipo) DO UPDATE SET corpo=excluded.corpo,
                ativo=excluded.ativo, versao=excluded.versao,
                alterado_por=excluded.alterado_por,alterado_em=clock_timestamp()''',
            (action, body, enabled, revision,  __import__('flask').g.user['id']))
        conn.execute('''INSERT INTO notificacao_modelos_historico
            (tipo,versao,corpo,ativo,acao,autor) VALUES (%s,%s,%s,%s,%s,%s)''',
            (action, revision, body, enabled, operation, __import__('flask').g.user['id']))
        event('Edição de mensagem WhatsApp', note=f'{action} · versão {revision} · {operation} · ' +
              ('ativa' if enabled else 'desativada'))
        return {'ok': True, 'modelo': current_model(conn, action)}

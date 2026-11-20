"""Webhook de avaliação experimental: recebe exclusivamente notas, nunca conversas."""
import hashlib
import hmac
import json
import os
import re

from flask import abort, request

from .phone import normalize_phone

PATH = '/api/notificacoes/evolution/avaliacao'
RATING = re.compile(r'AVALIAR ([A-F0-9]{16}) ([1-5])')


PHONE_JID = re.compile(r'[1-9][0-9]{7,14}@s\.whatsapp\.net')
LID_JID = re.compile(r'[1-9][0-9]{7,20}@lid')


def sender_phone(key):
    """Resolve o número do remetente Evolution quando remoteJid é @lid.

    remoteJidAlt só é usado quando remoteJid é um LID individual.
    Sem um número real válido, a nota não pode ser vinculada ao pedido.
    """
    jid = key.get('remoteJid')
    if not isinstance(jid, str):
        return None
    if PHONE_JID.fullmatch(jid):
        phone_jid = jid
    elif LID_JID.fullmatch(jid):
        phone_jid = key.get('remoteJidAlt')
        if not isinstance(phone_jid, str) or not PHONE_JID.fullmatch(phone_jid):
            return None
    else:
        return None
    try:
        return normalize_phone('+' + phone_jid.split('@', 1)[0])
    except ValueError:
        return None


def extract_rating(payload):
    """Ignora saídas próprias, grupos, mídia e qualquer texto fora do comando."""
    if not isinstance(payload, dict) or payload.get('event') != 'messages.upsert':
        return None
    if payload.get('instance') != os.getenv('EVOLUTION_INSTANCE'):
        return None
    data = payload.get('data')
    if not isinstance(data, dict):
        return None
    key = data.get('key')
    if not isinstance(key, dict) or key.get('fromMe') is not False:
        return None
    phone = sender_phone(key)
    mid = key.get('id')
    if phone is None or not isinstance(mid, str) or not 1 <= len(mid) <= 512:
        return None
    message = data.get('message')
    if not isinstance(message, dict):
        return None
    # Resposta antiga por texto; lista ou botões trazem o ID da opção clicada.
    # O ID deve conter o comando completo com código imprevisível do convite.
    body = message.get('conversation')
    if body is None:
        extended = message.get('extendedTextMessage')
        body = extended.get('text') if isinstance(extended, dict) else None
    if body is None:
        listed = message.get('listResponseMessage')
        choice = listed.get('singleSelectReply') if isinstance(listed, dict) else None
        body = choice.get('selectedRowId') if isinstance(choice, dict) else None
    if body is None:
        buttons = message.get('buttonsResponseMessage')
        body = buttons.get('selectedButtonId') if isinstance(buttons, dict) else None
    if body is None:
        template = message.get('templateButtonReplyMessage')
        body = template.get('selectedId') if isinstance(template, dict) else None
    if body is None:
        interactive = message.get('interactiveResponseMessage')
        native = interactive.get('nativeFlowResponseMessage') if isinstance(interactive, dict) else None
        raw = native.get('paramsJson') if isinstance(native, dict) else None
        if isinstance(raw, str) and len(raw) <= 1024:
            try:
                parsed = json.loads(raw)
            except (ValueError, TypeError):
                parsed = None
            body = parsed.get('id') if isinstance(parsed, dict) else None
    if not isinstance(body, str) or len(body) > 80:
        return None
    matched = RATING.fullmatch(body.strip().upper())
    if not matched:
        return None
    return phone, matched.group(1), int(matched.group(2)), hashlib.sha256(mid.encode()).hexdigest()


def consume(conn, payload):
    extracted = extract_rating(payload)
    if not extracted:
        return False
    phone, code, rating, message_hash = extracted
    row = conn.execute('''UPDATE notificacao_avaliacoes f
        SET nota=%s,respondido_em=clock_timestamp(),mensagem_id_hash=%s
        FROM notificacoes n,notificacao_assinaturas a,solicitacoes s
        WHERE f.notificacao=n.id AND f.assinatura=a.id AND f.solicitacao=s.id
        AND f.codigo=%s AND f.nota IS NULL AND f.cancelado_em IS NULL
        AND f.expira_em>clock_timestamp()
        AND a.avaliacao_consentida AND a.revogado_em IS NULL
        AND n.provedor='evolution' AND n.estado='sent'
        AND s.declarado->>'telefone'=%s
        AND (
            (n.template_tipo='recepção' AND s.tipo='Entrada' AND s.status='APROVADA'
                AND s.etapa='entrada concluída')
            OR (n.template_tipo='portaria' AND s.tipo='Saída' AND s.status='APROVADA'
                AND s.etapa='saída concluída')
        )
        RETURNING f.id''', (rating,message_hash,code,phone)).fetchone()
    return row is not None


def register(app, db, staff):
    @app.post(PATH)
    def evolution_feedback_webhook():
        if os.getenv('EVOLUTION_FEEDBACK_ENABLED') != '1':
            abort(503)
        token = os.getenv('EVOLUTION_FEEDBACK_WEBHOOK_TOKEN', '')
        if len(token) < 32:
            abort(503)
        provided = request.headers.get('X-SISGECE-Evolution-Secret', '')
        if not hmac.compare_digest(provided.encode(), token.encode()):
            abort(403)
        if not request.is_json:
            abort(400)
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            abort(400)
        consume(db(), payload)
        # Não retorna se o telefone/código existe, evita enumeração.
        return {'ok': True}


    @app.get('/api/notificacoes/avaliacoes/estatisticas')
    @staff('coordenação', 'superusuário')
    def feedback_statistics():
        rows = db().execute('''SELECT nota, count(*) AS quantidade
            FROM notificacao_avaliacoes
            WHERE nota IS NOT NULL
            GROUP BY nota ORDER BY nota''').fetchall()
        counts = {str(i): 0 for i in range(1, 6)}
        for row in rows:
            counts[str(row['nota'])] = row['quantidade']
        total = sum(counts.values())
        average = round(sum(int(score) * count for score, count in counts.items()) / total, 2) if total else None
        return {'quantidade': total, 'media': average, 'distribuicao': counts}

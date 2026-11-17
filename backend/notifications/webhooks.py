import hashlib
import hmac
import json
import os
from datetime import datetime, timezone

from flask import abort, request

from .consent import confirm, revoke
from .phone import normalize_phone

PATH = '/api/notificacoes/webhook'


def reconcile(conn):
    # Somente IDs retornados pela Meta; nenhum pareamento heurístico por telefone/data.
    conn.execute('''UPDATE notificacoes n SET estado='delivered',
        entregue_em=coalesce(n.entregue_em,e.quando),enviado_em=coalesce(n.enviado_em,e.quando),
        resultado='meta_delivered' FROM notificacao_entregas e
        WHERE n.provedor='meta' AND n.externo_id=e.externo_id
        AND e.estado IN ('delivered','read') AND n.estado<>'cancelled' ''')
    conn.execute('''UPDATE notificacoes n SET estado='failed',resultado=
        CASE WHEN e.erro_codigo IS NULL THEN 'meta_delivery_failed' ELSE 'meta_'||e.erro_codigo::text END
        FROM notificacao_entregas e WHERE n.provedor='meta' AND n.externo_id=e.externo_id
        AND e.estado='failed' AND n.estado NOT IN ('delivered','cancelled')''')
    conn.execute('''UPDATE notificacoes n SET estado='sent',resultado='meta_sent',
        enviado_em=coalesce(n.enviado_em,e.quando) FROM notificacao_entregas e
        WHERE n.provedor='meta' AND n.externo_id=e.externo_id AND e.estado='sent'
        AND n.estado IN ('processing','uncertain')''')


def entries(payload):
    if not isinstance(payload,dict) or payload.get('object')!='whatsapp_business_account':
        raise ValueError()
    result = []
    for entry in payload.get('entry',[]):
        if entry.get('id')!=os.getenv('WHATSAPP_WABA_ID'):
            continue
        for change in entry.get('changes',[]):
            value = change.get('value',{})
            if (change.get('field')=='messages' and
                value.get('metadata',{}).get('phone_number_id')==os.getenv('WHATSAPP_PHONE_NUMBER_ID')):
                result.append(value)
    return result


def consume(conn, payload):
    for value in entries(payload):
        for message in value.get('messages',[]):
            mid = message.get('id')
            if not isinstance(mid,str) or not 1<=len(mid)<=512:
                raise ValueError()
            key = hashlib.sha256(('incoming:'+mid).encode()).hexdigest()
            if not conn.execute('INSERT INTO notificacao_webhooks(chave) VALUES (%s) ON CONFLICT DO NOTHING RETURNING chave',(key,)).fetchone():
                continue
            if message.get('type')!='text' or not isinstance(message.get('from'),str):
                continue
            text = message.get('text',{}).get('body','').strip()
            if text.startswith('CONFIRMAR ') and len(text)<100:
                confirm(conn,text.removeprefix('CONFIRMAR ').strip(),message['from'],'meta')
            elif text.upper() in ('PARAR','SAIR','STOP'):
                try:
                    phone = normalize_phone('+'+message['from'].lstrip('+'))
                except ValueError:
                    continue
                subscriptions = conn.execute('''SELECT a.solicitacao FROM notificacao_assinaturas a
                    JOIN solicitacoes s ON s.id=a.solicitacao WHERE a.provedor='meta'
                    AND a.revogado_em IS NULL AND s.declarado->>'telefone'=%s
                    ORDER BY a.id''',(phone,)).fetchall()
                for subscription in subscriptions:
                    revoke(conn,subscription['solicitacao'])
        for status in value.get('statuses',[]):
            external, state = status.get('id'),status.get('status')
            if state not in ('sent','delivered','read','failed'):
                continue
            if not isinstance(external,str) or not 1<=len(external)<=512:
                raise ValueError()
            stamp = datetime.fromtimestamp(int(status['timestamp']),tz=timezone.utc)
            errors = status.get('errors',[])
            code = errors[0].get('code') if errors else None
            if type(code) is not int or not -2147483648<=code<=2147483647:
                code = None
            conn.execute('''INSERT INTO notificacao_entregas VALUES (%s,%s,%s,%s)
                ON CONFLICT(externo_id,estado) DO NOTHING''',(external,state,stamp,code))
    reconcile(conn)


def register(app, db):
    @app.route(PATH,methods=['GET','POST'])
    def whatsapp_webhook():
        secret = os.getenv('WHATSAPP_APP_SECRET','')
        verify = os.getenv('WHATSAPP_WEBHOOK_VERIFY_TOKEN','')
        if (len(secret)<32 or len(verify)<32 or not os.getenv('WHATSAPP_WABA_ID') or
            not os.getenv('WHATSAPP_PHONE_NUMBER_ID')):
            abort(503)
        if request.method=='GET':
            provided = request.args.get('hub.verify_token','')
            if request.args.get('hub.mode')!='subscribe' or not hmac.compare_digest(provided.encode(),verify.encode()):
                abort(403)
            challenge = request.args.get('hub.challenge','')
            if not challenge or len(challenge)>256:
                abort(400)
            return challenge,200,{'Content-Type':'text/plain'}
        raw = request.get_data(cache=True)
        expected = 'sha256='+hmac.new(secret.encode(),raw,hashlib.sha256).hexdigest()
        if not hmac.compare_digest(request.headers.get('X-Hub-Signature-256','').encode(),expected.encode()):
            abort(403)
        if not request.is_json:
            abort(400)
        try:
            payload = json.loads(raw)
            consume(db(),payload)
        except (ValueError,TypeError,AttributeError,KeyError,OverflowError,OSError):
            abort(400, 'Webhook inválido.')
        return {'ok':True}

import json
import os
import re
import socket
from urllib.error import HTTPError, URLError
from urllib.request import Request, HTTPRedirectHandler, build_opener

from .config import real_enabled
from .providers import Result


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def http_send(request):
    # Sem redirect, sem retries implícitos; timeout menor que a reserva do worker.
    with build_opener(NoRedirect()).open(request, timeout=15) as response:
        return response.read(65537)


class MetaProvider:
    name = 'meta'

    def __init__(self):
        if not real_enabled():
            raise ValueError('Envio real desabilitado. Exige WHATSAPP_REAL_SEND_ENABLED=1.')
        self.token = os.getenv('WHATSAPP_ACCESS_TOKEN','')
        version = os.getenv('WHATSAPP_API_VERSION','')
        phone_id = os.getenv('WHATSAPP_PHONE_NUMBER_ID','')
        if (not self.token or '\n' in self.token or '\r' in self.token or
            not re.fullmatch(r'v[0-9]+\.0',version) or not re.fullmatch(r'[0-9]+',phone_id)):
            raise ValueError('Configure token, versão explícita e Phone Number ID da Meta.')
        self.url = f'https://graph.facebook.com/{version}/{phone_id}/messages'

    def send(self, notification):
        if not real_enabled():
            return Result('failed','real_send_disabled')
        name, language = notification['template_nome'],notification['template_idioma']
        if not re.fullmatch(r'[a-z0-9_]{1,512}',name) or not re.fullmatch(r'[a-z]{2,3}(?:_[A-Z]{2})?',language):
            return Result('failed','invalid_template_config')
        payload = {'messaging_product':'whatsapp','recipient_type':'individual',
                   'to':notification['telefone'].lstrip('+'),'type':'template',
                   'template':{'name':name,'language':{'code':language}}}
        request = Request(self.url,data=json.dumps(payload).encode(),method='POST',
                          headers={'Authorization':'Bearer '+self.token,'Content-Type':'application/json'})
        try:
            raw = http_send(request)
            if len(raw)>65536:
                return Result('uncertain','invalid_api_response')
            data = json.loads(raw)
            message_id = data['messages'][0]['id']
            if not isinstance(message_id,str) or not 1<=len(message_id)<=512:
                raise ValueError()
            return Result('sent','meta_accepted',message_id)
        except HTTPError as error:
            try:
                body = json.loads(error.read(65536))
                code = body.get('error',{}).get('code')
                if type(code) is not int:
                    code = None
            except (ValueError,AttributeError,TypeError):
                code = None
            finally:
                error.close()
            label = 'meta_' + str(code) if code is not None else 'http_' + str(error.code)
            # Somente respostas explícitas de rejeição temporária permitem reenviar.
            if code in (4,80007,80008,130429,131056,131048) or error.code==429:
                return Result('retry',label)
            if error.code>=500:
                return Result('uncertain',label)
            return Result('failed',label)
        except URLError as error:
            if isinstance(error.reason,(socket.gaierror,ConnectionRefusedError)):
                return Result('retry','connection_not_established')
            return Result('uncertain','transport_error')
        except (TimeoutError,OSError):
            return Result('uncertain','transport_timeout_or_error')
        except (ValueError,KeyError,IndexError,TypeError):
            return Result('uncertain','invalid_api_response')

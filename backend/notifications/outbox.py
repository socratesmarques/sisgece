"""Textos institucionais sem dados pessoais e fila transacional de notificações.

O link público é opcional: até o operador definir uma URL HTTPS válida, nenhuma
mensagem terá placeholder, URL local ou endereço inventado.
"""
import os
from urllib.parse import urlsplit

HEADER = '*SISGECE | IFCE Campus Maranguape*'
FOOTER = 'Esta é uma mensagem automática. Não é necessário responder.'

TEMPLATES = {
    'cadastro': ('sisgece_cadastro',
        'Informamos que sua solicitação foi registrada com sucesso em nosso sistema.\n\n'
        'A solicitação encontra-se *pendente de análise pela coordenação*.'),
    'aprovar': ('sisgece_aprovacao',
        'Informamos que sua solicitação foi *aprovada pela coordenação*.\n\n'
        'A aprovação administrativa foi registrada no sistema. Caso se trate de uma '
        'solicitação de saída, ainda deverão ser cumpridas as etapas de conferência '
        'estabelecidas pela instituição.'),
    'reprovar': ('sisgece_atualizacao',
        'Informamos que, após análise da coordenação, sua solicitação *não foi aprovada*.\n\n'
        'Para consultar a justificativa registrada e outras informações sobre a decisão, '
        'acesse o portal do SISGECE.\n\n'
        'Em caso de dúvidas, procure a coordenação do campus.'),
    'recepção': ('sisgece_etapa',
        'Informamos que a etapa de *conferência pela recepção* referente à sua solicitação '
        'de saída foi concluída.\n\n'
        'A solicitação seguirá os procedimentos institucionais previstos para a liberação de saída.'),
    'portaria': ('sisgece_etapa',
        'Informamos que a *saída do estudante foi registrada pela portaria* do IFCE '
        'Campus Maranguape.\n\n'
        'O procedimento foi registrado no sistema, conforme as etapas de conferência institucional.'),
    'reabrir análise': ('sisgece_atualizacao',
        'Informamos que sua solicitação foi *reaberta para uma nova análise pela coordenação*.\n\n'
        'A decisão anterior deverá ser reavaliada e o andamento poderá sofrer alterações.'),
    'corrigir recepção': ('sisgece_atualizacao',
        'Informamos que houve uma *atualização no registro de conferência da recepção* '
        'referente à sua solicitação de saída.\n\n'
        'O histórico e a situação atualizada estão disponíveis para consulta no sistema.'),
    'corrigir portaria': ('sisgece_atualizacao',
        'Informamos que houve uma *atualização no registro da portaria* referente à sua '
        'solicitação de saída.\n\n'
        'O histórico e a situação atualizada estão disponíveis para consulta no sistema.'),
}


def public_link():
    """Somente HTTPS público; não usa localhost, IP ou URLs com credenciais."""
    raw = os.getenv('SISGECE_PUBLIC_URL', '').strip()
    if not raw:
        return ''
    try:
        url = urlsplit(raw)
        host = url.hostname or ''
        if (url.scheme != 'https' or not host or '.' not in host or
                host in ('localhost', '127.0.0.1') or host.endswith('.local') or
                url.username or url.password or url.port or url.query or url.fragment or
                any(c.isspace() for c in raw) or len(raw) > 240):
            return ''
        return raw.rstrip('/')
    except ValueError:
        return ''


def message_text(action):
    """Texto para o transporte mock/Evolution; nunca substitui os templates Meta aprovados."""
    content = TEMPLATES[action][1]
    link = public_link()
    consultation = ('Para acompanhar o andamento e consultar os detalhes, acesse:\n' + link
                    if link else 'Para acompanhar o andamento, consulte o portal oficial do SISGECE.')
    footer = ('Esta é uma mensagem automática do Sistema de Gerenciamento de Entrada e Saída '
              'de Estudantes.' if action == 'cadastro' else FOOTER)
    return f'{HEADER}\n\n{content}\n\n{consultation}\n\n{footer}'


def enqueue(conn, sid, event_id, action):
    if action not in TEMPLATES:
        return
    default_name, _ = TEMPLATES[action]
    name = os.getenv('WHATSAPP_TEMPLATE_' + default_name.removeprefix('sisgece_').upper(), default_name)
    # Configuração inválida não perde a transação: o provedor rejeita antes do HTTP.
    conn.execute('''INSERT INTO notificacoes(solicitacao,evento,assinatura,telefone,
        provedor,template_tipo,template_nome,template_idioma,status_origem,etapa_origem)
        SELECT s.id,%s,a.id,s.declarado->>'telefone',a.provedor,%s,%s,%s,s.status,s.etapa
        FROM solicitacoes s JOIN notificacao_assinaturas a ON a.solicitacao=s.id
        WHERE s.id=%s AND a.revogado_em IS NULL
        ON CONFLICT(evento,canal,assinatura) DO NOTHING''',
        (event_id, action, name, os.getenv('WHATSAPP_TEMPLATE_LANGUAGE','pt_BR'), sid))
    # Uma etapa nova torna avisos ainda não despachados antigos obsoletos.
    conn.execute('''UPDATE notificacoes SET estado='cancelled',resultado='superseded'
        WHERE solicitacao=%s AND evento<%s AND (estado='pending' OR
        (estado='processing' AND despacho_em IS NULL))''', (sid,event_id))

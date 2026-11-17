import os

TEMPLATES = {
    'cadastro': ('sisgece_cadastro', 'SISGECE — Sua solicitação foi cadastrada. Consulte o portal oficial para acompanhar o andamento.'),
    'aprovar': ('sisgece_aprovacao', 'SISGECE — Sua solicitação foi aprovada pela coordenação. Para acompanhar as próximas etapas, acesse o portal oficial do SISGECE.'),
    'reprovar': ('sisgece_atualizacao', 'SISGECE — Houve uma atualização na situação da sua solicitação. Acesse o portal oficial do SISGECE para consultar os detalhes.'),
    'recepção': ('sisgece_etapa', 'SISGECE — Uma nova etapa de sua solicitação foi concluída. Consulte o portal oficial para acompanhar o andamento.'),
    'portaria': ('sisgece_etapa', 'SISGECE — Uma nova etapa de sua solicitação foi concluída. Consulte o portal oficial para acompanhar o andamento.'),
    'reabrir análise': ('sisgece_atualizacao', 'SISGECE — Houve uma atualização na situação da sua solicitação. Acesse o portal oficial do SISGECE para consultar os detalhes.'),
    'corrigir recepção': ('sisgece_atualizacao', 'SISGECE — Houve uma atualização na situação da sua solicitação. Acesse o portal oficial do SISGECE para consultar os detalhes.'),
    'corrigir portaria': ('sisgece_atualizacao', 'SISGECE — Houve uma atualização na situação da sua solicitação. Acesse o portal oficial do SISGECE para consultar os detalhes.'),
}


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

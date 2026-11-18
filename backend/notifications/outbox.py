"""Textos institucionais sem dados pessoais e fila transacional de notificações.

O link público é opcional: até o operador definir uma URL HTTPS válida, nenhuma
mensagem terá placeholder, URL local ou endereço inventado.
"""
import os
import re
import secrets

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
        'Em caso de dúvidas sobre a decisão registrada, procure a coordenação do campus.'),
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


def approval_details(notification):
    """Resumo mínimo do pedido, exclusivamente após autorização do worker."""
    if not notification:
        return ''
    kind = notification.get('solicitacao_tipo')
    if kind not in ('Entrada', 'Saída'):
        return ''
    day = notification.get('solicitacao_data')
    hour = notification.get('solicitacao_horario')
    # Datas/horários são objetos SQL tipados; não interpolar dados arbitrários.
    from datetime import date, time
    if not isinstance(day, date):
        return ''
    if not isinstance(hour, time):
        return ''
    return ('*Informações da solicitação*\n'
            f'Tipo: {kind}\n'
            f'Data: {day:%d/%m/%Y}\n'
            f'Horário: {hour:%H:%M}')


def message_text(action, notification=None):
    """Texto mock/Evolution; não modifica templates Meta aprovados."""
    content = TEMPLATES[action][1]
    if action == 'aprovar':
        details = approval_details(notification)
        if details:
            content += '\n\n' + details
    code = notification.get('avaliacao_codigo') if notification else None
    invitation = bool(
        action in ('aprovar', 'reprovar', 'portaria')
        and isinstance(code, str)
        and re.fullmatch(r'[A-F0-9]{16}', code)
    )
    if invitation:
        content += (
            '\n\n*Avaliação opcional do SISGECE*\n'
            'Como você avalia o atendimento recebido? '
            'Escolha uma nota de 1 (muito ruim) a 5 (excelente).\n'
            f'Para avaliar, responda exatamente: AVALIAR {code} 5\n'
            'Substitua o último número pela nota desejada. '
            'Você pode ignorar este convite.'
        )
    footer = ('Esta é uma mensagem automática do Sistema de Gerenciamento de Entrada e Saída '
              'de Estudantes.' if action == 'cadastro' else
              'Esta é uma mensagem automática. Sua resposta será registrada apenas se você optar por avaliar.'
              if invitation else FOOTER)
    return f'{HEADER}\n\n{content}\n\n{footer}'


def enqueue_feedback(conn, sid, event_id, action):
    """Cria um convite apenas após evento terminal e consentimento separado."""
    # Anula convites anteriores se o pedido for reaberto/corrigido.
    conn.execute('''UPDATE notificacao_avaliacoes
        SET cancelado_em=clock_timestamp()
        WHERE solicitacao=%s AND evento<>%s
          AND nota IS NULL AND cancelado_em IS NULL''', (sid, event_id))
    if os.getenv('EVOLUTION_FEEDBACK_ENABLED') != '1':
        return
    if action not in ('aprovar', 'reprovar', 'portaria'):
        return
    code = secrets.token_hex(8).upper()
    conn.execute('''INSERT INTO notificacao_avaliacoes
        (notificacao,solicitacao,assinatura,evento,codigo)
        SELECT n.id,n.solicitacao,n.assinatura,n.evento,%s
        FROM notificacoes n JOIN notificacao_assinaturas a ON a.id=n.assinatura
        JOIN solicitacoes s ON s.id=n.solicitacao
        WHERE n.solicitacao=%s AND n.evento=%s AND n.template_tipo=%s
        AND n.provedor='evolution' AND a.avaliacao_consentida AND a.revogado_em IS NULL
        AND (
          (%s='reprovar' AND s.status='REPROVADA')
          OR (%s='aprovar' AND s.tipo='Entrada' AND s.status='APROVADA')
          OR (%s='portaria' AND s.tipo='Saída' AND s.status='APROVADA' AND s.etapa='saída concluída')
        )
        ON CONFLICT (notificacao) DO NOTHING''',
        (code,sid,event_id,action,action,action,action))


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
    enqueue_feedback(conn, sid, event_id, action)

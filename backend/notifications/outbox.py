"""Textos institucionais sem dados pessoais e fila transacional de notificações.

O link público é opcional: até o operador definir uma URL HTTPS válida, nenhuma
mensagem terá placeholder, URL local ou endereço inventado.
"""
import os
import re

HEADER = '*SISGECE | IFCE Campus Maranguape*'
FOOTER = 'Esta é uma mensagem automática. Não é necessário responder.'

TEMPLATES = {
    'cadastro': ('sisgece_cadastro',
        'Informamos que sua solicitação foi registrada com sucesso em nosso sistema.\n\n'
        'A solicitação encontra-se *pendente de análise pela coordenação*.'),
    'aprovar': ('sisgece_aprovacao',
        'Informamos que sua solicitação foi *aprovada pela coordenação*.\n\n'
        'A aprovação administrativa foi registrada no sistema. Para entradas, ainda é '
        'necessária a confirmação pela recepção. Para saídas, permanecem as etapas '
        'de conferência estabelecidas pela instituição.'),
    'reprovar': ('sisgece_atualizacao',
        'Informamos que, após análise da coordenação, sua solicitação *não foi aprovada*.\n\n'
        'Em caso de dúvidas sobre a decisão registrada, procure a coordenação do campus.'),
    'recepção': ('sisgece_etapa',
        'Informamos que a etapa de *conferência pela recepção* referente à sua solicitação '
        'foi concluída.'),
    'portaria': ('sisgece_etapa',
        'Informamos que a *saída do estudante foi registrada pela portaria* do IFCE '
        'Campus Maranguape.\n\n'
        'O procedimento foi registrado no sistema, conforme as etapas de conferência institucional.'),
    'reabrir análise': ('sisgece_atualizacao',
        'Informamos que sua solicitação foi *reaberta para uma nova análise pela coordenação*.\n\n'
        'A decisão anterior deverá ser reavaliada e o andamento poderá sofrer alterações.'),
    'corrigir recepção': ('sisgece_atualizacao',
        'Informamos que houve uma *atualização no registro de conferência da recepção* '
        'referente à sua solicitação.\n\n'
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



def full_template(action, body=None):
    """Modelo integral editável pelo superusuário, inclusive abertura e assinatura.

    Os blocos condicionais são inseridos apenas se o editor mantiver seu marcador.
    """
    if action not in TEMPLATES:
        raise KeyError(action)
    parts = [HEADER, TEMPLATES[action][1] if body is None else body]
    if action == 'recepção':
        parts.append('{detalhes_etapa}')
    if action == 'aprovar':
        parts.append('{detalhes_solicitacao}')
    parts.append(
        'Esta é uma mensagem automática do Sistema de Gerenciamento de Entrada e Saída '
        'de Estudantes.' if action == 'cadastro' else FOOTER
    )
    return '\n\n'.join(parts)


def render_full_message(action, template, notification=None):
    """Expande exclusivamente marcadores previamente validados, sem dados privados."""
    from datetime import date, time
    item = notification or {}
    kind = item.get('solicitacao_tipo')
    day = item.get('solicitacao_data')
    hour = item.get('solicitacao_horario')
    kind = kind if kind in ('Entrada', 'Saída') else ''
    safe = {
        'tipo': kind,
        'data': day.strftime('%d/%m/%Y') if isinstance(day, date) else '',
        'horario': hour.strftime('%H:%M') if isinstance(hour, time) else '',
        'detalhes_solicitacao': approval_details(item) if action == 'aprovar' else '',
        'detalhes_etapa': (
            'A *entrada foi concluída na recepção*. '
            'Não há etapa de portaria para solicitações de entrada.'
            if kind == 'Entrada' else
            'Para saídas, a solicitação seguirá os procedimentos '
            'institucionais previstos para a liberação pela portaria.'
            if kind == 'Saída' else ''
        ) if action == 'recepção' else '',
        'convite_avaliacao': '',  # Legado: marcadores já salvos ficam inertes.
    }
    # Marcadores estritos, validados antes de salvar; nenhum campo SQL arbitrário.
    rendered = template.format_map(safe)
    return re.sub(r'\n{3,}', '\n\n', rendered).strip()


def message_text(action, notification=None):
    """Compatibiliza a fila legada com mensagens integrais novas da Evolution."""
    if notification and notification.get('mensagem_completa') is True:
        source = notification.get('corpo_personalizado')
        if isinstance(source, str) and source.strip():
            return render_full_message(action, source, notification)

    # Caminho legado: preserva exatamente a composição de notificações antigas
    # (inclusive aquelas que já estavam na fila antes da migração 012.sql).
    original = (notification.get('corpo_personalizado') if notification else None) or TEMPLATES[action][1]
    values = {
        'tipo': notification.get('solicitacao_tipo') if notification else '',
        'data': notification.get('solicitacao_data') if notification else None,
        'horario': notification.get('solicitacao_horario') if notification else None,
    }
    from datetime import date, time
    safe = {
        'tipo': values['tipo'] if values['tipo'] in ('Entrada', 'Saída') else '',
        'data': values['data'].strftime('%d/%m/%Y') if isinstance(values['data'], date) else '',
        'horario': values['horario'].strftime('%H:%M') if isinstance(values['horario'], time) else '',
        'convite_avaliacao': '',  # Legado: não enviar convites antigos.
    }
    content = original.format_map(safe).strip()
    if action == 'recepção':
        if notification and notification.get('solicitacao_tipo') == 'Entrada':
            content += ('\n\nA *entrada foi concluída na recepção*. '
                        'Não há etapa de portaria para solicitações de entrada.')
        else:
            content += ('\n\nPara saídas, a solicitação seguirá os procedimentos '
                        'institucionais previstos para a liberação pela portaria.')
    if action == 'aprovar' and not any(
        marker in original for marker in ('{tipo}', '{data}', '{horario}')
    ):
        details = approval_details(notification)
        if details:
            content += '\n\n' + details
    footer = ('Esta é uma mensagem automática do Sistema de Gerenciamento de Entrada e Saída '
              'de Estudantes.' if action == 'cadastro' else FOOTER)
    return f'{HEADER}\n\n{content}\n\n{footer}'


def enqueue(conn, sid, event_id, action):
    if action not in TEMPLATES:
        return
    # A personalização afeta só a Evolution; Meta continua usando templates aprovados.
    # A cópia do corpo congela a revisão na fila, independentemente de edições futuras.
    body = None
    complete = False
    if os.getenv('NOTIFICATIONS_PROVIDER', 'mock') == 'evolution':
        setting = conn.execute(
            'SELECT corpo,ativo,mensagem_completa FROM notificacao_modelos WHERE tipo=%s',
            (action,)
        ).fetchone()
        if setting and not setting['ativo']:
            return
        if setting:
            body = setting['corpo']
            complete = setting['mensagem_completa']
        else:
            body = full_template(action)
            complete = True
    default_name, _ = TEMPLATES[action]
    name = os.getenv('WHATSAPP_TEMPLATE_' + default_name.removeprefix('sisgece_').upper(), default_name)
    # Configuração inválida não perde a transação: o provedor rejeita antes do HTTP.
    conn.execute('''INSERT INTO notificacoes(solicitacao,evento,assinatura,telefone,
        provedor,template_tipo,template_nome,template_idioma,status_origem,etapa_origem,
        corpo_personalizado,mensagem_completa)
        SELECT s.id,%s,a.id,s.declarado->>'telefone',a.provedor,%s,%s,%s,s.status,s.etapa,%s,%s
        FROM solicitacoes s JOIN notificacao_assinaturas a ON a.solicitacao=s.id
        WHERE s.id=%s AND a.revogado_em IS NULL
        ON CONFLICT(evento,canal,assinatura) DO NOTHING''',
        (event_id, action, name, os.getenv('WHATSAPP_TEMPLATE_LANGUAGE','pt_BR'), body, complete, sid))
    # Uma etapa nova torna avisos ainda não despachados antigos obsoletos.
    conn.execute('''UPDATE notificacoes SET estado='cancelled',resultado='superseded'
        WHERE solicitacao=%s AND evento<%s AND (estado='pending' OR
        (estado='processing' AND despacho_em IS NULL))''', (sid,event_id))

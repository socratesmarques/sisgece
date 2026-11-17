"""Ferramentas locais; acesso ao banco restrito ao operador. Nunca expor por HTTP."""
import argparse
import getpass
import json

from .config import provider_name
from .consent import confirm
from .outbox import TEMPLATES
from .worker import connection


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['mock-confirm','mock-preview','stats'])
    parser.add_argument('--id',type=int,help='ID da notificação para preview')
    args = parser.parse_args()
    if args.action.startswith('mock-') and provider_name()!='mock':
        parser.error('Ferramentas mock exigem NOTIFICATIONS_PROVIDER=mock.')
    with connection() as conn:
        if args.action=='mock-confirm':
            token = getpass.getpass('Token de CONFIRMAR (sem o prefixo): ').strip()
            phone = getpass.getpass('Telefone fictício com DDI: ').strip()
            if not confirm(conn,token,phone,'mock'):
                raise SystemExit('Confirmação recusada.')
            print('Confirmação simulada registrada.')
        elif args.action=='mock-preview':
            row = conn.execute("SELECT id,template_nome,template_tipo FROM notificacoes WHERE id=%s AND provedor='mock'",(args.id,)).fetchone()
            if not row:
                raise SystemExit('Notificação mock não encontrada.')
            print(json.dumps({'id':row['id'],'template':row['template_nome'],
                              'text':TEMPLATES[row['template_tipo']][1]},ensure_ascii=False))
        else:
            for row in conn.execute('''SELECT provedor,estado,count(*) AS quantidade,
                min(criado_em)::text AS mais_antiga FROM notificacoes GROUP BY provedor,estado ORDER BY provedor,estado'''):
                print(json.dumps(row,ensure_ascii=False))


if __name__=='__main__':
    main()

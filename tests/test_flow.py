"""Run only against a disposable database (the suite creates its own schema)."""
import os
import secrets
import unittest
from concurrent.futures import ThreadPoolExecutor

import psycopg
from werkzeug.security import generate_password_hash

from backend.app import app, ROLES
from backend.manage import migrate, ROOT


class Flow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = "test_"+secrets.token_hex(8)
        with psycopg.connect() as db:
            db.execute("CREATE SCHEMA "+cls.schema)
        os.environ["PGOPTIONS"]="-c search_path="+cls.schema
        with psycopg.connect() as db:
            db.execute((ROOT/"db/001.sql").read_text(encoding="utf-8-sig"))
            db.execute("INSERT INTO estudantes(nome,matricula) VALUES ('Antigo','M-1')")
            db.execute("INSERT INTO solicitacoes(estudante_id,tipo,justificativa) VALUES (1,'Saída','Legado')")
        migrate()
        migrate()
        cls.password=secrets.token_urlsafe()
        with psycopg.connect() as db:
            for role in ROLES:
                db.execute("INSERT INTO administradores(nome,email,senha_hash,perfil) VALUES (%s,%s,%s,%s)",(role,role+'@test.edu',generate_password_hash(cls.password),role))

    @classmethod
    def tearDownClass(cls):
        del os.environ["PGOPTIONS"]
        with psycopg.connect() as db:
            db.execute("DROP SCHEMA "+cls.schema+" CASCADE")

    def post(self,c,path,data):
        return c.post('/api/'+path,json=data,headers={'X-SISGECE':'1'})

    def test_workflow(self):
        public=app.test_client()
        self.assertEqual(public.get('/api/pedidos').status_code,401)
        self.assertEqual(public.post('/api/login',json={}).status_code,403)
        clients={}
        for role in ROLES:
            c=app.test_client()
            self.assertEqual(self.post(c,'login',{'email':role+'@test.edu','senha':self.password}).status_code,200)
            clients[role]=c
        coord,desk,gate,admin=clients.values()
        form=dict(origem='Aluno',aluno='Aluno teste',matricula='A-1',responsavel='Pessoa teste',telefone='85987654321',data='2030-01-01',hora='12:00',justificativa='Teste')
        receipt=self.post(public,'solicitar',form)
        self.assertEqual(receipt.status_code,201)
        form.update(origem='Responsável',cpf='123.456.789-01',parentesco='Mãe')
        second=self.post(public,'solicitar',form)
        self.assertEqual(second.status_code,201)
        ids={r['protocolo']:r['id'] for r in coord.get('/api/pedidos').json['itens']}
        self.assertIn('LEG-1',ids)
        path='pedidos/'+str(ids[receipt.json['protocolo']])
        def act(client,action,**kw):
            return self.post(client,path,dict(acao=action,**kw)).status_code
        self.assertEqual(act(desk,'aprovar'),403)
        self.assertEqual(desk.get('/api/'+path).status_code,404)
        with ThreadPoolExecutor(2) as pool:
            results=list(pool.map(lambda c:act(c,'aprovar',nota='Privado'),[coord,admin]))
        self.assertEqual(sorted(results),[200,409])
        self.assertEqual(act(gate,'portaria'),409)
        self.assertEqual(act(desk,'portaria'),403)
        self.assertEqual(act(desk,'recepção'),200)
        self.assertEqual(act(desk,'recepção'),409)
        self.assertEqual(act(gate,'portaria'),200)
        lookup=self.post(public,'consulta',receipt.json)
        self.assertEqual(lookup.json,dict(etapa='saída concluída',status='APROVADA',mensagem=''))
        self.assertEqual(self.post(public,'consulta',dict(receipt.json,codigo=second.json['codigo'])).status_code,404)
        self.assertEqual(act(coord,'corrigir recepção'),400)
        self.assertEqual(act(coord,'corrigir recepção',nota='Revisar'),200)
        self.assertEqual(act(gate,'portaria'),409)
        history=coord.get('/api/'+path).json['historico']['itens']
        self.assertEqual([e['autor'] for e in history[:3]],['coordenação','portaria','recepção'])
        path='pedidos/'+str(ids[second.json['protocolo']])
        self.assertEqual(act(coord,'reprovar'),400)
        self.assertEqual(act(coord,'reprovar',mensagem='Dados insuficientes'),200)
        account=dict(nome='Nova',email='nova@test.edu',perfil='recepção',senha=self.password)
        self.assertEqual(self.post(coord,'contas',account).status_code,403)
        self.assertEqual(self.post(admin,'contas',account).status_code,200)
        accounts=admin.get('/api/contas').json['itens']
        new=next(a for a in accounts if a['email']==account['email'])
        self.assertEqual(self.post(admin,'contas',dict(new,ativo=False)).status_code,200)
        last=next(a for a in accounts if a['perfil']=='superusuário')
        self.assertEqual(self.post(admin,'contas',dict(last,ativo=False)).status_code,409)
        self.assertEqual(self.post(public,'login',account).status_code,401)


"""Run only against a disposable database (the suite creates its own schema)."""

import os
import secrets
import unittest
from concurrent.futures import ThreadPoolExecutor

import psycopg
from werkzeug.security import generate_password_hash

from backend.app import app, ROLES
from backend.manage import migrate, ROOT
from backend.notifications.config import CONSENT_VERSION


class Flow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = "test_" + secrets.token_hex(8)
        with psycopg.connect() as db:
            db.execute("CREATE SCHEMA " + cls.schema)
        os.environ["PGOPTIONS"] = "-c search_path=" + cls.schema
        with psycopg.connect() as db:
            db.execute((ROOT / "db/001.sql").read_text(encoding="utf-8-sig"))
            db.execute("INSERT INTO estudantes(nome,matricula) VALUES ('Antigo','M-1')")
            db.execute(
                "INSERT INTO solicitacoes(estudante_id,tipo,justificativa) VALUES (1,'Saída','Legado')"
            )
        migrate()
        migrate()
        cls.password = secrets.token_urlsafe()
        with psycopg.connect() as db:
            for role in ROLES:
                db.execute(
                    "INSERT INTO administradores(nome,usuario,senha_hash,perfil) VALUES (%s,%s,%s,%s)",
                    (
                        role,
                        "user" + str(ROLES.index(role)),
                        generate_password_hash(cls.password),
                        role,
                    ),
                )

    @classmethod
    def tearDownClass(cls):
        del os.environ["PGOPTIONS"]
        with psycopg.connect() as db:
            db.execute("DROP SCHEMA " + cls.schema + " CASCADE")

    def post(self, c, path, data):
        return c.post("/api/" + path, json=data, headers={"X-SISGECE": "1"})

    def movement_state(self, client, path):
        data = client.get("/api/" + path).json
        return {key: data[key] for key in ("tipo", "status", "etapa", "mensagem")}

    def test_login_limits_count_failures_and_ignore_spoofed_headers(self):
        client = app.test_client()
        login = {"usuario": "user0", "senha": self.password}
        def attempt(body, number=0, remote="192.0.2.10"):
            return client.post("/api/login", json=body,
                environ_overrides={"REMOTE_ADDR":remote},
                headers={"X-SISGECE":"1", "X-Forwarded-For":f"198.51.100.{number}",
                         "X-SISGECE-Proxy":"incorrect", "X-SISGECE-Client":f"198.51.100.{number}"}).status_code
        for _ in range(17):
            self.assertEqual(attempt(login),200)
        for i in range(15):
            self.assertEqual(attempt(dict(login,senha="errada"),i),401)
        self.assertEqual(attempt(login,16),429)
        self.assertEqual(attempt(dict(login,usuario="user1")),200)
        self.assertEqual(attempt(login,remote="192.0.2.11"),200)

    def test_delete_request_keeps_history_and_cancels_notifications(self):
        public = app.test_client()
        matricula = "EXCLUIR-" + secrets.token_hex(5)
        self.assertEqual(self.post(public, "solicitar", dict(
            tipo="Saída", origem="Aluno", aluno="Exclusão de teste", matricula=matricula,
            responsavel="Fictício", telefone="85987654321", data="2030-01-01", hora="12:00",
            justificativa="Teste", whatsapp_consent=True, whatsapp_consent_version=CONSENT_VERSION,
        )).status_code, 201)
        clients = {}
        for index, role in enumerate(ROLES):
            clients[role] = app.test_client()
            self.assertEqual(self.post(clients[role], "login", {
                "usuario": "user" + str(index), "senha": self.password,
            }).status_code, 200)

        coordinator = clients["coordenação"]
        search_path = "/api/pedidos?q=" + matricula
        history_path = "/api/historico?q=" + matricula
        sid = coordinator.get(search_path).json["itens"][0]["id"]
        request_path = f"pedidos/{sid}"
        delete_path = request_path + "/excluir"
        self.assertEqual(self.post(coordinator, request_path, {"acao": "aprovar"}).status_code, 200)
        self.assertEqual(len(clients["recepção"].get(search_path).json["itens"]), 1)
        self.assertEqual(self.post(public, delete_path, {}).status_code, 401)
        for role in ("recepção", "portaria"):
            self.assertEqual(self.post(clients[role], delete_path, {}).status_code, 403)
        self.assertEqual(coordinator.post("/api/" + delete_path, json={}).status_code, 403)
        self.assertEqual(coordinator.get("/api/" + request_path).status_code, 200)

        self.assertEqual(self.post(coordinator, delete_path, {}).json, {"ok": True})
        self.assertEqual(self.post(clients["superusuário"], delete_path, {}).json, {"ok": True})
        for client in clients.values():
            self.assertEqual(client.get(search_path).json["itens"], [])
            self.assertEqual(client.get("/api/" + request_path).status_code, 404)
        self.assertEqual(self.post(coordinator, request_path, {"acao": "reabrir análise"}).status_code, 404)
        self.assertEqual(coordinator.get("/api/" + request_path + "/notificacoes").status_code, 404)
        self.assertEqual(clients["recepção"].get(history_path).json["itens"], [])
        history = coordinator.get(history_path).json["itens"]
        self.assertEqual([entry["acao"] for entry in history],
                         ["Solicitação excluída", "aprovar", "Saída · envio por Aluno"])
        self.assertEqual(history[0]["autor"], "coordenação")
        with psycopg.connect() as db:
            notice = db.execute(
                "SELECT estado FROM notificacoes WHERE solicitacao=%s AND template_tipo='aprovar'", (sid,)
            ).fetchone()
            self.assertEqual(notice, ("cancelled",))

    def test_entry_decisions(self):
        public = app.test_client()
        clients = {}
        for role in ROLES:
            client = app.test_client()
            self.assertEqual(self.post(client, "login", {
                "usuario": "user" + str(ROLES.index(role)), "senha": self.password,
            }).status_code, 200)
            clients[role] = client
        for role in ("coordenação", "superusuário"):
            for action, expected in (("aprovar", "APROVADA"), ("reprovar", "REPROVADA")):
                with self.subTest(role=role, action=action):
                    receipt = self.post(public, "solicitar", dict(
                        tipo="Entrada", origem="Aluno", aluno="Entrada teste",
                        matricula="E-" + secrets.token_hex(5), responsavel="Pessoa teste",
                        telefone="85987654321", data="2030-01-01", hora="12:00",
                        justificativa="Atendimento no campus",
                    ))
                    self.assertEqual(receipt.status_code, 201)
                    client = clients[role]
                    sid = client.get("/api/pedidos?tipo=Entrada").json["itens"][0]["id"]
                    path = "pedidos/" + str(sid)
                    self.assertEqual(client.get("/api/" + path).json["status"], "PENDENTE")
                    for other in ("recepção", "portaria"):
                        self.assertEqual(clients[other].get("/api/" + path).status_code, 404)
                        self.assertEqual(self.post(clients[other], path, {"acao": action}).status_code, 403)
                    if action == "reprovar":
                        self.assertEqual(self.post(client, path, {"acao": action}).status_code, 400)
                    self.assertEqual(self.post(client, path, {
                        "acao": action, "mensagem": "Orientação pública", "nota": "Anotação reservada",
                    }).status_code, 200)
                    tracked = self.movement_state(client, path)
                    expected_stage = "aguardando recepção" if action == "aprovar" else None
                    self.assertEqual(tracked, dict(tipo="Entrada", status=expected, etapa=expected_stage, mensagem="Orientação pública"))
                    self.assertEqual(self.post(client, path, {"acao": action}).status_code, 409)
                    self.assertEqual(self.post(clients["portaria"], path, {"acao": "portaria"}).status_code, 409)
                    self.assertEqual(clients["portaria"].get("/api/" + path).status_code, 404)
                    if action == "aprovar":
                        self.assertEqual(clients["recepção"].get("/api/" + path).status_code, 200)
                        self.assertEqual(self.post(clients["recepção"], path, {"acao": "recepção"}).status_code, 200)
                        self.assertEqual(client.get("/api/" + path).json["etapa"], "entrada concluída")
                        self.assertEqual(self.post(clients["recepção"], path, {"acao": "recepção"}).status_code, 409)
                        self.assertEqual(self.post(client, path, {
                            "acao": "corrigir recepção", "nota": "Revisão",
                        }).status_code, 200)
                        self.assertEqual(client.get("/api/" + path).json["etapa"], "aguardando recepção")
                    else:
                        self.assertEqual(self.post(clients["recepção"], path, {"acao": "recepção"}).status_code, 409)
                        self.assertEqual(clients["recepção"].get("/api/" + path).status_code, 404)
                        self.assertEqual(self.post(client, path, {
                            "acao": "corrigir recepção", "nota": "Revisão",
                        }).status_code, 409)
                    self.assertEqual(self.post(client, path, {"acao": "reabrir análise"}).status_code, 400)
                    self.assertEqual(self.post(client, path, {"acao": "reabrir análise", "nota": "Revisar dados"}).status_code, 200)
                    reopened = self.movement_state(client, path)
                    self.assertEqual(reopened, dict(tipo="Entrada", status="PENDENTE", etapa=None, mensagem=None))
                    history = client.get("/api/" + path).json["historico"]["itens"]
                    decision = next(event for event in history if event["acao"] == action)
                    self.assertEqual(decision["autor"], role)
                    self.assertIn("Anotação reservada", decision["nota"])

    def test_migrate_received_entries(self):
        with psycopg.connect() as db:
            sid = db.execute("""INSERT INTO solicitacoes(tipo,status,etapa,justificativa,protocolo,segredo)
                VALUES ('Entrada','RECEBIDA',NULL,'Entrada anterior à atualização','ENTRADA-ANTIGA','segredo-preservado')
                RETURNING id""").fetchone()[0]
            db.execute("DELETE FROM versoes WHERE nome='006.sql'")
        migrate()
        migrate()
        with psycopg.connect() as db:
            row = db.execute("SELECT status,etapa,protocolo,segredo FROM solicitacoes WHERE id=%s", (sid,)).fetchone()
        self.assertEqual(row, ("PENDENTE", None, "ENTRADA-ANTIGA", "segredo-preservado"))

    def test_movement_filter(self):
        client = app.test_client()
        self.assertEqual(self.post(client, "login", {"usuario": "user0", "senha": self.password}).status_code, 200)
        for movement in ("Entrada", "Saída"):
            rows = client.get("/api/pedidos?tipo=" + movement).json["itens"]
            self.assertTrue(rows)
            self.assertTrue(all(row["tipo"] == movement for row in rows))

    def test_workflow(self):
        public = app.test_client()
        self.assertEqual(public.get("/api/pedidos").status_code, 401)
        self.assertEqual(public.post("/api/login", json={}).status_code, 403)
        clients = {}
        for role in ROLES:
            c = app.test_client()
            self.assertEqual(
                self.post(
                    c, "login", {"usuario": "user" + str(ROLES.index(role)), "senha": self.password}
                ).status_code,
                200,
            )
            clients[role] = c
        coord, desk, gate, admin = clients.values()
        form = dict(
            origem="Aluno",
            aluno="Aluno teste",
            matricula="A-1",
            responsavel="Pessoa teste",
            telefone="85987654321",
            data="2030-01-01",
            hora="12:00",
            justificativa="Teste",
        )
        receipt = self.post(public, "solicitar", form)
        self.assertEqual(receipt.status_code, 201)
        form.update(origem="Responsável", cpf="123.456.789-01", parentesco="Mãe")
        second = self.post(public, "solicitar", form)
        self.assertEqual(second.status_code, 201)
        ids = {r["protocolo"]: r["id"] for r in coord.get("/api/pedidos").json["itens"]}
        self.assertIn("LEG-1", ids)
        path = "pedidos/" + str(sorted(ids.values())[-2])

        def act(client, action, **kw):
            return self.post(client, path, dict(acao=action, **kw)).status_code

        self.assertEqual(act(desk, "aprovar"), 403)
        self.assertEqual(desk.get("/api/" + path).status_code, 404)
        with ThreadPoolExecutor(2) as pool:
            results = list(
                pool.map(lambda c: act(c, "aprovar", nota="Privado"), [coord, admin])
            )
        self.assertEqual(sorted(results), [200, 409])
        self.assertEqual(act(gate, "portaria"), 409)
        self.assertEqual(act(desk, "portaria"), 403)
        self.assertEqual(act(desk, "recepção"), 200)
        self.assertEqual(act(desk, "recepção"), 409)
        self.assertEqual(act(gate, "portaria"), 200)
        self.assertEqual(receipt.json, {"ok": True})
        self.assertEqual(
            self.movement_state(coord, path),
            dict(tipo="Saída", etapa="saída concluída", status="APROVADA", mensagem=""),
        )
        self.assertEqual(act(coord, "corrigir recepção"), 400)
        self.assertEqual(act(coord, "corrigir recepção", nota="Revisar"), 200)
        self.assertEqual(act(gate, "portaria"), 409)
        history = coord.get("/api/" + path).json["historico"]["itens"]
        self.assertEqual(
            [e["autor"] for e in history[:3]], ["coordenação", "portaria", "recepção"]
        )
        path = "pedidos/" + str(max(ids.values()))
        self.assertEqual(act(coord, "reprovar"), 400)
        self.assertEqual(act(coord, "reprovar", mensagem="Dados insuficientes"), 200)
        entry = self.post(public, "solicitar", dict(form,tipo="Entrada"))
        self.assertEqual(entry.status_code,201)
        path = "pedidos/"+str(coord.get("/api/pedidos?tipo=Entrada&status=PENDENTE").json["itens"][0]["id"])
        self.assertEqual(act(coord,"aprovar"),200)
        self.assertEqual(act(desk,"recepção"),200)
        self.assertEqual(coord.get("/api/" + path).json["etapa"], "entrada concluída")
        self.assertEqual(act(gate,"portaria"),409)
        self.assertEqual(gate.get("/api/"+path).status_code,404)
        self.assertEqual(self.post(public,"solicitar",dict(form,tipo="outro")).status_code,400)
        account = dict(
            nome="Nova", usuario="nova", perfil="recepção", senha="12345678"
        )
        self.assertEqual(self.post(admin,"contas",dict(account,senha="1234567")).status_code,400)
        self.assertEqual(public.get("/api/historico").status_code,401)
        self.assertTrue(coord.get("/api/historico").json["itens"])
        self.assertTrue(any(e["tipo"]=="Entrada" for e in desk.get("/api/historico").json["itens"]))
        self.assertFalse(any(e["tipo"]=="Entrada" for e in gate.get("/api/historico").json["itens"]))
        self.assertEqual(self.post(coord, "contas", account).status_code, 403)
        self.assertEqual(self.post(admin, "contas", account).status_code, 200)
        accounts = admin.get("/api/contas").json["itens"]
        new = next(a for a in accounts if a["usuario"] == account["usuario"])
        self.assertEqual(
            self.post(admin, "contas", dict(new, ativo=False)).status_code, 200
        )
        last = next(a for a in accounts if a["perfil"] == "superusuário")
        self.assertEqual(
            self.post(admin, "contas", dict(last, ativo=False)).status_code, 409
        )
        self.assertEqual(self.post(public, "login", account).status_code, 401)

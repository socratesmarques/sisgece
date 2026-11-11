import hashlib
import json
import logging
import time as clock
from ipaddress import ip_address
import os
import re
import secrets
from datetime import date, time
from functools import wraps
from pathlib import Path
from zoneinfo import ZoneInfo

import bcrypt
import psycopg
from flask import Flask, abort, g, jsonify, render_template, request
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash

ROOT = Path(__file__).resolve().parents[1]
app = Flask(
    __name__,
    template_folder=ROOT / "frontend/templates",
    static_folder=ROOT / "frontend/static",
)
app.config["MAX_CONTENT_LENGTH"] = 16384
logging.basicConfig(level=logging.INFO)
TRACK_DAYS = int(os.getenv("TRACKING_TTL_DAYS", "30"))
if not 1 <= TRACK_DAYS <= 365:
    raise RuntimeError("TRACKING_TTL_DAYS deve estar entre 1 e 365.")
LOCAL = os.getenv("LOCAL_HTTP") == "1"
ROLES = ("coordenação", "recepção", "portaria", "superusuário")
DUMMY = generate_password_hash(secrets.token_urlsafe())
COOKIE = "sisgece_local" if LOCAL else "__Host-sisgece"


def db():
    if "db" not in g:
        g.db = psycopg.connect(row_factory=dict_row, connect_timeout=4)
    return g.db


def query(sql, args=()):
    return db().execute(sql, args)


@app.after_request
def finish(response):
    if "db" in g and response.status_code < 400:
        g.db.commit()
    response.headers.update(
        {
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
            "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
        }
    )
    if not LOCAL:
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    app.logger.info(
        json.dumps(
            {
                "event": "http",
                "method": request.method,
                "route": str(request.url_rule),
                "status": response.status_code,
                "duration_ms": round(
                    (clock.monotonic() - g.get("started", clock.monotonic())) * 1000
                ),
            }
        )
    )
    return response


@app.teardown_request
def close(error):
    if "db" in g:
        g.db.close()


@app.errorhandler(HTTPException)
def http_error(e):
    return jsonify(erro=e.description), e.code


@app.errorhandler(psycopg.Error)
def database_error(e):
    return jsonify(
        erro="Banco indisponível ou operação conflitante."
    ), 409 if isinstance(e, psycopg.IntegrityError) else 503


@app.before_request
def protect():
    g.started = clock.monotonic()
    if request.method == "POST":
        # Custom header cannot be sent cross-origin without a successful CORS preflight.
        if request.headers.get("X-SISGECE") != "1" or not request.is_json:
            abort(403)
        if not isinstance(request.get_json(), dict):
            abort(400)


def value(key, maximum=200, required=True):
    v = request.json.get(key, "")
    if (
        not isinstance(v, str)
        or len(v) > maximum
        or "\x00" in v
        or (required and not v.strip())
    ):
        abort(400, "Campo inválido: " + key)
    return v.strip()


def digest(v):
    return hashlib.sha256(v.encode()).hexdigest()


PROXY_SECRET = os.environ.get("SISGECE_PROXY_SECRET", "")
if PROXY_SECRET and len(PROXY_SECRET) < 32:
    raise RuntimeError("SISGECE_PROXY_SECRET requer pelo menos 32 caracteres.")


def client_address():
    # Caddy overwrites both private headers. Ignore untrusted forwarding chains.
    provided = request.headers.get("X-SISGECE-Proxy", "")
    if PROXY_SECRET and secrets.compare_digest(
        provided.encode(), PROXY_SECRET.encode()
    ):
        try:
            return str(ip_address(request.headers.get("X-SISGECE-Client", "")))
        except ValueError:
            pass
    return request.remote_addr or "unknown"


def increment(conn, key):
    return conn.execute(
        """INSERT INTO limites VALUES (%s,floor(extract(epoch FROM now())/600),1)
        ON CONFLICT(chave) DO UPDATE SET quantidade=CASE WHEN limites.janela=excluded.janela
        THEN limites.quantidade+1 ELSE 1 END, janela=excluded.janela RETURNING quantidade""",
        (key,),
    ).fetchone()[0]


def expire_counters(conn):
    conn.execute(
        "DELETE FROM limites WHERE janela < floor(extract(epoch FROM now())/600)-1"
    )


def limited():
    abort(429, "Limite de tentativas. Tente novamente em dez minutos.")


def limit(kind, maximum):
    with psycopg.connect() as conn:
        expire_counters(conn)
        count = increment(conn, digest(kind + ":" + client_address()))
    if count > maximum:
        limited()


def check_login_budget(username):
    address = client_address()
    pair = digest("login-pair:" + address + ":" + username)
    source = digest("login-source:" + address)
    # Serialize checks for this client; a failed-login transaction is recorded
    # before releasing the lock, even though the HTTP request returns 401.
    query("SELECT pg_advisory_xact_lock(%s)", (int(source[:15], 16),))
    if query(
        """SELECT 1 FROM limites WHERE janela=floor(extract(epoch FROM now())/600)
        AND ((chave=%s AND quantidade>=15) OR (chave=%s AND quantidade>=60))""",
        (pair, source),
    ).fetchone():
        limited()
    return pair, source


def staff(*roles):
    def decorator(fn):
        @wraps(fn)
        def wrapped(*a, **kw):
            g.user = query(
                """SELECT a.id,a.nome,a.perfil FROM administradores a JOIN sessoes s ON s.funcionario=a.id
                WHERE s.token=%s AND s.expira>now() AND a.ativo FOR SHARE OF a""",
                (digest(request.cookies.get(COOKIE, "")),),
            ).fetchone()
            if not g.user:
                abort(401)
            if roles and g.user["perfil"] not in roles:
                abort(403)
            return fn(*a, **kw)

        return wrapped

    return decorator


def event(action, sid=None, note=None):
    query(
        "INSERT INTO eventos(solicitacao,autor,acao,nota) VALUES (%s,%s,%s,%s)",
        (sid, g.get("user", {}).get("id"), action, note),
    )


@app.get("/")
@app.get("/equipe")
def home():
    return render_template("home.html", equipe=request.path == "/equipe")


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/ready")
def ready():
    query("SELECT 1 FROM sessoes LIMIT 0")
    return {"ok": True}


@app.post("/api/login")
def login():
    username = value("usuario", 64).lower()
    pair, source = check_login_budget(username)
    row = query(
        "SELECT * FROM administradores WHERE lower(usuario)=%s AND ativo",
        (username,),
    ).fetchone()
    password = request.json.get("senha")
    if not isinstance(password, str) or not 1 <= len(password) <= 512:
        abort(400, "Senha inválida.")
    hashed = row["senha_hash"] if row else DUMMY
    valid = (
        (
            len(password.encode()) <= 72
            and bcrypt.checkpw(password.encode(), hashed.encode())
        )
        if hashed.startswith("$2")
        else check_password_hash(hashed, password)
    )
    if not row or not valid:
        with psycopg.connect() as conn:
            expire_counters(conn)
            increment(conn, pair)
            increment(conn, source)
        abort(401, "Credenciais inválidas.")
    token = secrets.token_urlsafe(32)
    query("DELETE FROM sessoes WHERE expira<=now()")
    query(
        "INSERT INTO sessoes VALUES (%s,%s,now()+interval '8 hours')",
        (digest(token), row["id"]),
    )
    response = jsonify(ok=True)
    response.set_cookie(
        COOKIE, token, httponly=True, secure=not LOCAL, samesite="Strict", max_age=28800
    )
    return response


@app.post("/api/logout")
def logout():
    query(
        "DELETE FROM sessoes WHERE token=%s", (digest(request.cookies.get(COOKIE, "")),)
    )
    response = jsonify(ok=True)
    response.delete_cookie(COOKIE, secure=not LOCAL)
    return response


@app.get("/api/me")
@staff()
def me():
    return g.user


@app.post("/api/solicitar")
def submit():
    limit("envio", 30)
    data = {
        k: value(k, 80 if k == "matricula" else 200)
        for k in ("origem", "aluno", "responsavel", "matricula", "telefone")
    }
    if (
        data["origem"] not in ("Aluno", "Responsável")
        or not re.fullmatch(r"[0-9 ()+-]+", data["telefone"])
        or not 10 <= len(re.sub(r"\D", "", data["telefone"])) <= 13
    ):
        abort(400, "Tipo ou telefone inválido.")
    if data["origem"] == "Responsável":
        cpf = value("cpf", 14)
        if not re.fullmatch(
            r"(?:[0-9]{11}|[0-9]{3}\.[0-9]{3}\.[0-9]{3}-[0-9]{2})", cpf
        ):
            abort(400, "Formato de CPF inválido.")
        data.update(cpf=cpf, parentesco=value("parentesco", 80))
    dt, tm = value("data", 10), value("hora", 5)
    try:
        if (
            date.fromisoformat(dt).isoformat() != dt
            or time.fromisoformat(tm).strftime("%H:%M") != tm
        ):
            raise ValueError
    except ValueError:
        abort(400, "Data ou hora inválida.")
    movement = request.json.get("tipo", "Saída")
    if movement not in ("Entrada", "Saída"):
        abort(400, "Escolha entrada ou saída.")
    reason = value("justificativa", 2000)
    fingerprint = digest(json.dumps([data, movement, dt, tm, reason], sort_keys=True))
    query("SELECT pg_advisory_xact_lock(%s)", (int(fingerprint[:15], 16),))
    if query(
        """SELECT 1 FROM solicitacoes WHERE impressao=%s
        AND criado_em > now()-interval '10 minutes'""",
        (fingerprint,),
    ).fetchone():
        abort(
            409,
            "Solicitação já recebida nos últimos dez minutos. Use seu recibo ou procure a coordenação.",
        )
    secret = "".join(
        secrets.choice("23456789ABCDEFGHJKLMNPQRSTUVWXYZ") for _ in range(10)
    )
    protocol = secrets.token_hex(8).upper()
    sid = query(
        """INSERT INTO solicitacoes(tipo,status,etapa,declarado,protocolo,segredo,justificativa,data_solicitada,horario_solicitado)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (
            movement,
            "RECEBIDA" if movement == "Entrada" else "PENDENTE",
            None if movement == "Entrada" else "aguardando",
            Jsonb(data),
            protocol,
            digest(secret),
            value("justificativa", 2000),
            dt,
            tm,
        ),
    ).fetchone()["id"]
    query(
        "UPDATE solicitacoes SET impressao=%s, consulta_expira=now()+(%s * interval '1 day') WHERE id=%s",
        (fingerprint, TRACK_DAYS, sid),
    )
    event(movement + " · envio por " + data["origem"], sid)
    return {"codigo": secret[:5] + "-" + secret[5:]}, 201


@app.post("/api/consulta")
def track():
    limit("consulta", 40)
    code = value("codigo", 128)
    # Old receipts used a case-sensitive 32-character token.
    normalized = re.sub(r"[\s-]", "", code).upper()
    if re.fullmatch(r"[2-9A-HJ-NP-Z]{10}", normalized):
        code = normalized
    row = query(
        "SELECT tipo,status,etapa,mensagem FROM solicitacoes WHERE segredo=%s AND consulta_expira>now()",
        (digest(code),),
    ).fetchone()
    if not row:
        abort(404, "Código de consulta inválido.")
    return row


def page():
    try:
        return max(1, min(100000000, int(request.args.get("pagina", 1))))
    except ValueError:
        abort(400)


def listing(sql, args):
    rows = query(sql + " LIMIT 26 OFFSET %s", (*args, (page() - 1) * 25)).fetchall()
    return {"itens": rows[:25], "mais": len(rows) > 25}


def restricted():
    return g.user["perfil"] in ("recepção", "portaria")


@app.get("/api/pedidos")
@staff()
def requests_list():
    term = "%" + request.args.get("q", "")[:200] + "%"
    status = request.args.get("status", "")
    day = request.args.get("data", "")
    return listing(
        """SELECT id,tipo,protocolo,declarado->>'aluno' AS aluno,status,etapa FROM solicitacoes
        WHERE (protocolo ILIKE %s OR declarado->>'aluno' ILIKE %s OR declarado->>'matricula' ILIKE %s)
        AND (%s='' OR status=%s) AND (%s='' OR data_solicitada::text=%s)
        AND (%s OR (status='APROVADA' AND lower(tipo) IN ('saida','saída'))) ORDER BY id DESC""",
        (term, term, term, status, status, day, day, not restricted()),
    )


def instant(v):
    return v.astimezone(ZoneInfo("America/Fortaleza")).strftime("%d/%m/%Y %H:%M:%S")


@app.get("/api/pedidos/<int:sid>")
@staff()
def details(sid):
    row = query(
        """SELECT protocolo,declarado,justificativa,data_solicitada::text,horario_solicitado::text,tipo,status,etapa,mensagem FROM solicitacoes WHERE id=%s""",
        (sid,),
    ).fetchone()
    if (
        not row
        or restricted()
        and (
            row["status"] != "APROVADA" or row["tipo"].lower() not in ("saida", "saída")
        )
    ):
        abort(404)
    if restricted():
        row["declarado"] = {k: row["declarado"].get(k) for k in ("aluno", "matricula")}
        del row["justificativa"], row["mensagem"]
    events = listing(
        """SELECT e.acao,a.nome AS autor,e.quando,CASE WHEN %s THEN NULL ELSE nota END AS nota
        FROM eventos e LEFT JOIN administradores a ON a.id=e.autor WHERE solicitacao=%s ORDER BY e.id DESC""",
        (restricted(), sid),
    )
    for item in events["itens"]:
        item["quando"] = instant(item["quando"])
    checks = {}
    for step, valid in (
        ("recepção", row["etapa"] != "aguardando"),
        ("portaria", row["etapa"] == "saída concluída"),
    ):
        entry = None
        if valid:
            entry = query(
                """SELECT a.nome, e.quando FROM eventos e JOIN administradores a ON a.id=e.autor
                WHERE e.solicitacao=%s AND e.acao=%s ORDER BY e.id DESC LIMIT 1""",
                (sid, step),
            ).fetchone()
            if entry:
                entry["quando"] = instant(entry["quando"])
        checks[step] = entry
    return {**row, "confirmacoes": checks, "historico": events}


@app.post("/api/pedidos/<int:sid>")
@staff()
def act(sid):
    action = value("acao")
    role = g.user["perfil"]
    if (action in ("recepção", "portaria") and role != action) or (
        action not in ("recepção", "portaria")
        and role not in ("coordenação", "superusuário")
    ):
        abort(403)
    row = query(
        "SELECT status,etapa,tipo FROM solicitacoes WHERE id=%s FOR UPDATE", (sid,)
    ).fetchone()
    if not row:
        abort(404)
    if row["tipo"].lower() not in ("saida", "saída"):
        abort(409, "Esta ação é exclusiva para solicitações de saída.")
    status, stage = row["status"], row["etapa"]
    note = value("nota", 2000, False)
    if action in ("aprovar", "reprovar") and status == "PENDENTE":
        msg = value("mensagem", 2000, action == "reprovar")
        query(
            """UPDATE solicitacoes SET status=%s,administrador_id=%s,analisado_em=clock_timestamp(),mensagem=%s,observacao_coordenacao=%s WHERE id=%s""",
            (
                "APROVADA" if action == "aprovar" else "REPROVADA",
                g.user["id"],
                msg,
                note,
                sid,
            ),
        )
        note = "Mensagem ao solicitante: " + msg + "\nNota interna: " + note
    elif (
        action in ("recepção", "portaria")
        and status == "APROVADA"
        and stage
        == {"recepção": "aguardando", "portaria": "recepção confirmada"}[action]
    ):
        query(
            "UPDATE solicitacoes SET etapa=%s WHERE id=%s",
            ("recepção confirmada" if action == "recepção" else "saída concluída", sid),
        )
    elif (
        action in ("corrigir recepção", "corrigir portaria", "reabrir análise")
        and status != "PENDENTE"
    ):
        note = value("nota", 2000)
        if (
            action == "corrigir portaria"
            and stage != "saída concluída"
            or action == "corrigir recepção"
            and stage == "aguardando"
        ):
            abort(409)
        query(
            "UPDATE solicitacoes SET etapa=%s WHERE id=%s",
            (
                "recepção confirmada"
                if action == "corrigir portaria"
                else "aguardando",
                sid,
            ),
        )
        if action == "reabrir análise":
            query(
                "UPDATE solicitacoes SET status='PENDENTE',mensagem=NULL,observacao_coordenacao=NULL,administrador_id=NULL,analisado_em=NULL WHERE id=%s",
                (sid,),
            )
    else:
        abort(409, "Ação incompatível com a situação atual.")
    event(action, sid, note)
    return {"ok": True}


@app.get("/api/contas")
@staff("superusuário")
def accounts():
    term = "%" + request.args.get("q", "")[:200] + "%"
    return listing(
        "SELECT id,nome,usuario,ativo,perfil FROM administradores WHERE nome ILIKE %s OR usuario ILIKE %s ORDER BY lower(nome),id",
        (term, term),
    )


@app.get("/api/historico")
@staff()
def request_history():
    term = "%" + request.args.get("q", "")[:200] + "%"
    rows = listing(
        """SELECT s.protocolo,s.tipo,s.declarado->>'aluno' AS aluno,
        e.acao,e.quando,a.nome AS autor FROM eventos e
        JOIN solicitacoes s ON s.id=e.solicitacao
        LEFT JOIN administradores a ON a.id=e.autor
        WHERE (%s OR (s.status='APROVADA' AND lower(s.tipo) IN ('saida','saída')))
        AND (s.protocolo ILIKE %s OR s.declarado->>'aluno' ILIKE %s OR s.declarado->>'matricula' ILIKE %s)
        ORDER BY e.id DESC""",
        (not restricted(), term, term, term),
    )
    for row in rows["itens"]:
        row["quando"] = instant(row["quando"])
    return rows


@app.get("/api/auditoria")
@staff("superusuário")
def audit():
    term = "%" + request.args.get("q", "")[:200] + "%"
    rows = listing(
        """SELECT e.acao,e.nota,e.quando,a.nome FROM eventos e LEFT JOIN administradores a ON a.id=e.autor WHERE solicitacao IS NULL AND (e.acao ILIKE %s OR a.nome ILIKE %s OR e.nota ILIKE %s) ORDER BY e.id DESC""",
        (term, term, term),
    )
    for row in rows["itens"]:
        row["quando"] = instant(row["quando"])
    return rows


@app.post("/api/contas")
@staff("superusuário")
def account():
    # Serialize edits, including simultaneous demotions of different administrators.
    if not query("SELECT pg_try_advisory_xact_lock(538001) AS ok").fetchone()["ok"]:
        abort(409, "Outra edição em andamento.")
    role = value("perfil")
    usuario = value("usuario", 64).lower()
    name = value("nome")
    uid = request.json.get("id")
    active = request.json.get("ativo", True)
    password = request.json.get("senha", "")
    if not isinstance(password, str) or len(password) > 512:
        abort(400, "Senha inválida.")
    if (
        role not in ROLES
        or not re.fullmatch(r"[a-z0-9._-]{1,64}", usuario)
        or type(active) != bool
        or (password or not uid)
        and len(password) < 8
    ):
        abort(400, "Dados da conta inválidos (senha mínima de 8 caracteres).")
    hashed = generate_password_hash(password) if password else None
    if uid is None:
        uid = query(
            "INSERT INTO administradores(nome,usuario,perfil,ativo,senha_hash) VALUES (%s,%s,%s,%s,%s) RETURNING id",
            (name, usuario, role, active, hashed),
        ).fetchone()["id"]
        action = "Criação"
    else:
        if type(uid) != int:
            abort(400)
        old = query(
            "SELECT perfil,ativo FROM administradores WHERE id=%s FOR UPDATE", (uid,)
        ).fetchone()
        if not old:
            abort(404)
        if (
            old["ativo"]
            and old["perfil"] == "superusuário"
            and (not active or role != "superusuário")
            and not query(
                "SELECT 1 FROM administradores WHERE perfil='superusuário' AND ativo AND id<>%s",
                (uid,),
            ).fetchone()
        ):
            abort(409, "É necessário manter um superusuário ativo.")
        query(
            "UPDATE administradores SET nome=%s,usuario=%s,perfil=%s,ativo=%s,senha_hash=coalesce(%s,senha_hash) WHERE id=%s",
            (name, usuario, role, active, hashed, uid),
        )
        query("DELETE FROM sessoes WHERE funcionario=%s", (uid,))
        action = "Alteração"
    event(
        action + " de conta",
        note=f"Funcionário {uid} · {role} · " + ("ativo" if active else "inativo"),
    )
    return {"ok": True}

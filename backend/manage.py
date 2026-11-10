import re
import getpass
import os
import sys
from pathlib import Path

import psycopg
from werkzeug.security import generate_password_hash

ROOT = Path(__file__).resolve().parents[1]


def migrate():
    with psycopg.connect() as db:
        db.execute("SELECT pg_advisory_xact_lock(539002)")
        db.execute("CREATE TABLE IF NOT EXISTS versoes(nome text PRIMARY KEY)")
        for path in sorted((ROOT / "db").glob("*.sql")):
            if not db.execute(
                "SELECT 1 FROM versoes WHERE nome=%s", (path.name,)
            ).fetchone():
                sql = (
                    path.read_text(encoding="utf-8-sig")
                    .replace("BEGIN;", "")
                    .replace("COMMIT;", "")
                )
                db.execute(sql)
                db.execute("INSERT INTO versoes VALUES (%s)", (path.name,))


if __name__ == "__main__":
    if sys.argv[1:] == ["migrate"]:
        migrate()
    elif sys.argv[1:] == ["superuser"]:
        nome = input("Nome: ").strip()
        usuario = input("Usuário: ").strip().lower()
        senha = getpass.getpass("Senha (mínimo 8 caracteres): ")
        if (
            not nome
            or not re.fullmatch(r"[a-z0-9._-]{1,64}", usuario)
            or len(senha) < 8
            or senha != getpass.getpass("Repita a senha: ")
        ):
            sys.exit("Dados inválidos.")
        with psycopg.connect() as db:
            uid = db.execute(
                "INSERT INTO administradores(nome,usuario,senha_hash,perfil) VALUES (%s,%s,%s,'superusuário') RETURNING id",
                (nome, usuario, generate_password_hash(senha)),
            ).fetchone()[0]
            db.execute(
                "INSERT INTO eventos(autor,acao) VALUES (%s,'Criação administrativa pelo operador')",
                (uid,),
            )
    else:
        sys.exit("Use migrate ou superuser.")

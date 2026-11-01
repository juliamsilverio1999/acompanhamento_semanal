"""Configura o Postgres local e cria o schema.

    python scripts/init_db.py           # cria usuário, database e tabelas que faltarem
    python scripts/init_db.py --reset   # APAGA todas as tabelas e recria

Passos:
  1. Como superusuário (POSTGRES_ADMIN_*): cria o usuário da aplicação
     (POSTGRES_USER) e o database (POSTGRES_DB) tendo esse usuário como dono.
  2. Como usuário da aplicação: cria as tabelas a partir de app/models.py.
  3. Grava o DDL gerado em db/schema.sql (referência para revisão da modelagem).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import Enum, create_engine, text  # noqa: E402
from sqlalchemy.dialects.postgresql import CreateEnumType  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.schema import CreateIndex, CreateTable  # noqa: E402

from app import models  # noqa: E402,F401  (registra as tabelas no metadata)
from app.config import settings  # noqa: E402
from app.db import Base, engine  # noqa: E402


def criar_usuario_e_database() -> None:
    url = make_url(settings.sqlalchemy_url)
    if url.get_backend_name() != "postgresql":
        return
    admin = create_engine(settings.admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        quote = conn.dialect.identifier_preparer.quote
        usuario, database = quote(url.username), quote(url.database)

        if conn.scalar(text("SELECT 1 FROM pg_roles WHERE rolname = :n"), {"n": url.username}):
            print(f"usuário {url.username} já existe")
        else:
            senha = url.password.replace("'", "''")
            conn.execute(text(f"CREATE ROLE {usuario} LOGIN PASSWORD '{senha}'"))
            print(f"usuário {url.username} criado")

        if conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": url.database}):
            print(f"database {url.database} já existe")
        else:
            conn.execute(text(f"CREATE DATABASE {database} OWNER {usuario} ENCODING 'UTF8'"))
            print(f"database {url.database} criado (dono: {url.username})")
    admin.dispose()


def gravar_ddl() -> Path:
    dialect = engine.dialect
    partes = ["-- Gerado por scripts/init_db.py a partir de app/models.py. Não editar à mão.\n"]
    enums = {
        col.type.name: col.type
        for tabela in Base.metadata.sorted_tables
        for col in tabela.columns
        if isinstance(col.type, Enum) and col.type.name
    }
    for tipo in enums.values():
        partes.append(str(CreateEnumType(tipo).compile(dialect=dialect)).strip() + ";\n")
    for tabela in Base.metadata.sorted_tables:
        partes.append(str(CreateTable(tabela).compile(dialect=dialect)).strip() + ";\n")
        for indice in tabela.indexes:
            partes.append(str(CreateIndex(indice).compile(dialect=dialect)).strip() + ";\n")
    destino = ROOT / "db" / "schema.sql"
    destino.parent.mkdir(exist_ok=True)
    destino.write_text("\n".join(partes), encoding="utf-8")
    return destino


if __name__ == "__main__":
    criar_usuario_e_database()
    if "--reset" in sys.argv:
        Base.metadata.drop_all(engine)
        print("tabelas removidas")
    Base.metadata.create_all(engine)
    print("tabelas:", ", ".join(Base.metadata.tables))
    print("DDL gravado em", gravar_ddl().relative_to(ROOT))

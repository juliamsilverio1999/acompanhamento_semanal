# Acompanhamento Semanal de Produtividade

Ambiente de desenvolvimento local para validar a modelagem antes da implantação em Power Apps.

| Camada | Tecnologia | Onde |
|---|---|---|
| Motor de cálculo | Python puro (`Decimal`) | `app/calculos.py` |
| Persistência | PostgreSQL + SQLAlchemy 2 | `app/models.py`, `app/db.py` |
| API REST | FastAPI (docs em `/docs`) | `app/api.py`, `app/main.py` |
| Formulários / dashboard | Streamlit (consome a API via HTTP) | `dashboard/app.py` |
| Configuração | `.env` (pydantic-settings) | `.env.example`, `app/config.py` |

A análise da modelagem está em [docs/analise_modelagem.md](docs/analise_modelagem.md).

## Pré-requisitos

- Python 3.10+ (o projeto usa 3.12). O Python 3.9.7 **não** funciona: o Streamlit bloqueia essa versão.
- PostgreSQL 16 instalado nativamente (serviço `postgresql-x64-16`, porta 5432). Docker fica para depois.

## Setup

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env      # ajuste POSTGRES_ADMIN_PASSWORD para a senha definida na instalação

python scripts/init_db.py        # cria usuário, database e tabelas (--reset recria as tabelas do zero)
python scripts/seed.py           # opcional: obra de exemplo com 8 semanas
```

### Banco de dados

O `init_db.py` usa o superusuário (`POSTGRES_ADMIN_*`) só para criar:

- o usuário da aplicação `acompanhamento_app` (`POSTGRES_USER`/`POSTGRES_PASSWORD`);
- o database `acompanhamento_semanal`, com esse usuário como dono.

Em seguida cria as tabelas a partir de `app/models.py` e grava o DDL equivalente em [db/schema.sql](db/schema.sql), para revisão.
A aplicação conecta sempre com o usuário próprio, nunca com o `postgres`.

Para inspecionar com `psql`:

```powershell
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U acompanhamento_app -d acompanhamento_semanal
```

Enquanto a modelagem estiver em discussão, uma mudança em `models.py` é aplicada com `python scripts/init_db.py --reset`, que **apaga os dados**. Quando estabilizar, o próximo passo é adotar migrações (Alembic).

## Rodar

Em dois terminais (com o venv ativo):

```powershell
python -m app          # API em http://API_HOST:API_PORT  (Swagger em /docs)
python -m dashboard    # Streamlit em http://localhost:DASHBOARD_PORT
```

As portas vêm do `.env` (`API_PORT`, `DASHBOARD_PORT`, `API_BASE_URL`).

## Testes

```powershell
pytest
```

Os testes da API usam SQLite em memória, então rodam sem Postgres.

## Fluxo de uso

1. **Cadastros**: obra, atividade (com unidade) e vínculo obra × atividade.
2. **Planejamento**: gera as semanas com previsto e produtividade orçada.
3. **Apontamento semanal**: informa realizado e equipe. A prévia do índice aparece antes de salvar, e a justificativa passa a ser obrigatória abaixo de `INDICE_LIMITE_JUSTIFICATIVA`.
4. **Dashboard**: curva acumulada previsto × real e índice por semana.

Qualquer gravação (realizado ou previsto) recalcula os acumulados da série inteira da obra/atividade.

## Fórmulas

| Campo | Fórmula |
|---|---|
| `previsto_acumulado` | Σ `previsto_semana` até a semana |
| `real_acumulado` | Σ `real` até a semana (semana sem apontamento conta 0) |
| `delta_acumulado` | `real_acumulado − previsto_acumulado` |
| `prod_media_equipe_dia` | `real / (equipe × DIAS_TRABALHADOS_SEMANA)` |
| `indice_produtividade` | `prod_media_equipe_dia / prod_orcada_media_equipe_dia` |

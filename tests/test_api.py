"""Fluxo completo da API sobre SQLite em memória (não exige Postgres)."""
from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    Sessao = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def _db():
        with Sessao() as db:
            yield db

    app.dependency_overrides[get_db] = _db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _preparar(client):
    obra = client.post(
        "/obras", json={"nome": "Obra X", "cod_obra": "OB9", "uf": "rj", "cidade": "Rio"}
    ).json()
    assert obra["uf"] == "RJ"
    ativ = client.post("/atividades", json={"nome": "Reboco", "unidade_medida": "m2"}).json()
    vinculo = client.post(f"/obras/{obra['id']}/atividades", json={"atividade_id": ativ["id"]})
    assert vinculo.status_code == 201
    va = vinculo.json()["id"]
    semanas = client.post(
        f"/obra-atividades/{va}/semanas",
        json=[
            {"semana": 1, "dia_inicial_semana": "2026-10-05", "previsto_semana": "100",
             "prod_orcada_media_equipe_dia": "10"},
            {"semana": 2, "dia_inicial_semana": "2026-10-12", "previsto_semana": "100",
             "prod_orcada_media_equipe_dia": "10"},
        ],
    )
    assert semanas.status_code == 201, semanas.text
    return va, [s["id"] for s in semanas.json()]


def test_fluxo_apontamento_e_recalculo(client):
    va, (s1, s2) = _preparar(client)

    r = client.put(f"/semanas/{s1}/realizado", json={"real": "100", "equipe": 2})
    assert r.status_code == 200, r.text
    assert D(r.json()["indice_produtividade"]) == D("1")

    r = client.put(f"/semanas/{s2}/realizado", json={"real": "150", "equipe": 2})
    assert D(r.json()["real_acumulado"]) == D("250")
    assert D(r.json()["delta_acumulado"]) == D("50")

    # Corrigir a semana 1 deve recalcular o acumulado da semana 2
    client.put(f"/semanas/{s1}/realizado", json={"real": "120", "equipe": 2})
    linhas = client.get(f"/obra-atividades/{va}/acompanhamento").json()
    assert D(linhas[1]["dados"]["real_acumulado"]) == D("270")

    # Replanejar o previsto da semana 1 também recalcula
    client.patch(f"/semanas/{s1}", json={"previsto_semana": "50"})
    linhas = client.get(f"/obra-atividades/{va}/acompanhamento").json()
    assert D(linhas[1]["dados"]["previsto_acumulado"]) == D("150")
    assert D(linhas[1]["previsto_acumulado_plano"]) == D("150")


def test_justificativa_obrigatoria_abaixo_do_limite(client):
    _, (s1, _) = _preparar(client)
    corpo = {"real": "50", "equipe": 2}  # índice 0.5
    previa = client.post(f"/semanas/{s1}/realizado/previa", json=corpo).json()
    assert previa["exige_justificativa"] is True
    assert client.put(f"/semanas/{s1}/realizado", json=corpo).status_code == 422
    corpo["justificativa"] = "Falta de material"
    assert client.put(f"/semanas/{s1}/realizado", json=corpo).status_code == 200


def test_sem_prod_orcada_equipe_decimal_e_real_negativo(client):
    obra = client.post(
        "/obras", json={"nome": "Obra Y", "cod_obra": "OB8", "uf": "RJ", "cidade": "Rio"}
    ).json()
    ativ = client.post("/atividades", json={"nome": "TTS", "unidade_medida": "un"}).json()
    va = client.post(f"/obras/{obra['id']}/atividades", json={"atividade_id": ativ["id"]}).json()["id"]
    s1, s2 = [
        s["id"] for s in client.post(f"/obra-atividades/{va}/semanas", json=[
            {"semana": 1, "dia_inicial_semana": "2026-10-05", "previsto_semana": "10"},
            {"semana": 2, "dia_inicial_semana": "2026-10-12", "previsto_semana": "10"},
        ]).json()
    ]

    # Sem prod. orçada: índice não é calculado e a justificativa não é exigida
    r = client.put(f"/semanas/{s1}/realizado", json={
        "real": "1", "equipe": "3.5", "dado_extra": {"origem": "planilha"},
    })
    assert r.status_code == 200, r.text
    assert r.json()["indice_produtividade"] is None
    assert D(r.json()["equipe"]) == D("3.5")

    # Equipe ausente e real negativo (estorno)
    r = client.put(f"/semanas/{s2}/realizado", json={"real": "-0.5"})
    assert r.status_code == 200, r.text
    assert r.json()["equipe"] is None and D(r.json()["real_acumulado"]) == D("0.5")

    # Reenviar sem dado_extra (como o formulário) não apaga o que veio da importação
    r = client.put(f"/semanas/{s1}/realizado", json={"real": "2", "equipe": "3.5"})
    assert r.json()["dado_extra"] == {"origem": "planilha"}


def test_editar_atividade(client):
    ativ = client.post("/atividades", json={"nome": "Escavação", "unidade_medida": "m3"}).json()
    r = client.patch(f"/atividades/{ativ['id']}", json={"unidade_medida": "%"})
    assert r.status_code == 200
    assert r.json() == {**ativ, "unidade_medida": "%"}
    r = client.patch(f"/atividades/{ativ['id']}", json={"nome": "Escavação mecânica"})
    assert r.json()["nome"] == "Escavação mecânica" and r.json()["unidade_medida"] == "%"
    assert client.patch(f"/atividades/{ativ['id']}", json={"unidade_medida": "km"}).status_code == 422
    client.post("/atividades", json={"nome": "Reaterro", "unidade_medida": "m3"})
    dup = client.patch(f"/atividades/{ativ['id']}", json={"nome": "Reaterro"})
    assert dup.status_code == 409


def test_unicidade_e_dia_inicial(client):
    va, _ = _preparar(client)
    dup = client.post(
        f"/obra-atividades/{va}/semanas",
        json=[{"semana": 1, "dia_inicial_semana": "2026-10-19", "previsto_semana": "1"}],
    )
    assert dup.status_code == 409
    quarta = client.post(
        f"/obra-atividades/{va}/semanas",
        json=[{"semana": 3, "dia_inicial_semana": "2026-10-21", "previsto_semana": "1"}],
    )
    assert quarta.status_code == 422

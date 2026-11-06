from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import calculos, services
from app.config import settings
from app.db import get_db
from app.models import Atividade, Obra, ObraAtividade, ProdutividadeBaseSemana
from app.schemas import (
    AcompanhamentoOut,
    AtividadeIn,
    AtividadeOut,
    AtividadeUpdate,
    DadosOut,
    ObraAtividadeIn,
    ObraAtividadeOut,
    ObraIn,
    ObraOut,
    PreviaOut,
    RealizadoIn,
    SemanaBaseIn,
    SemanaBaseOut,
    SemanaBaseUpdate,
)

router = APIRouter()


def _obter(db: Session, modelo, id_: UUID):
    obj = db.get(modelo, id_)
    if obj is None:
        raise HTTPException(404, f"{modelo.__name__} {id_} não encontrado")
    return obj


# --- Obras -----------------------------------------------------------------

@router.get("/obras", response_model=List[ObraOut], tags=["cadastros"])
def listar_obras(db: Session = Depends(get_db)):
    return db.scalars(select(Obra).order_by(Obra.cod_obra)).all()


@router.post("/obras", response_model=ObraOut, status_code=201, tags=["cadastros"])
def criar_obra(payload: ObraIn, db: Session = Depends(get_db)):
    obra = Obra(**payload.model_dump())
    db.add(obra)
    db.commit()
    return obra


# --- Atividades ------------------------------------------------------------

@router.get("/atividades", response_model=List[AtividadeOut], tags=["cadastros"])
def listar_atividades(db: Session = Depends(get_db)):
    return db.scalars(select(Atividade).order_by(Atividade.nome)).all()


@router.post("/atividades", response_model=AtividadeOut, status_code=201, tags=["cadastros"])
def criar_atividade(payload: AtividadeIn, db: Session = Depends(get_db)):
    atividade = Atividade(**payload.model_dump())
    db.add(atividade)
    db.commit()
    return atividade


@router.patch("/atividades/{atividade_id}", response_model=AtividadeOut, tags=["cadastros"])
def atualizar_atividade(
    atividade_id: UUID, payload: AtividadeUpdate, db: Session = Depends(get_db)
):
    # Só troca o rótulo: valores já lançados não são convertidos para a nova unidade
    atividade = _obter(db, Atividade, atividade_id)
    for campo, valor in payload.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(atividade, campo, valor)
    db.commit()
    return atividade


# --- Obra x Atividade ------------------------------------------------------

@router.get(
    "/obras/{obra_id}/atividades", response_model=List[ObraAtividadeOut], tags=["cadastros"]
)
def listar_atividades_da_obra(obra_id: UUID, db: Session = Depends(get_db)):
    _obter(db, Obra, obra_id)
    return db.scalars(
        select(ObraAtividade)
        .where(ObraAtividade.obra_id == obra_id)
        .options(selectinload(ObraAtividade.atividade))
    ).all()


@router.post(
    "/obras/{obra_id}/atividades",
    response_model=ObraAtividadeOut,
    status_code=201,
    tags=["cadastros"],
)
def vincular_atividade(obra_id: UUID, payload: ObraAtividadeIn, db: Session = Depends(get_db)):
    _obter(db, Obra, obra_id)
    _obter(db, Atividade, payload.atividade_id)
    vinculo = ObraAtividade(obra_id=obra_id, atividade_id=payload.atividade_id)
    db.add(vinculo)
    db.commit()
    db.refresh(vinculo)
    return vinculo


# --- Planejamento (produtividade base semanal) ------------------------------

@router.post(
    "/obra-atividades/{obra_atividade_id}/semanas",
    response_model=List[SemanaBaseOut],
    status_code=201,
    tags=["planejamento"],
)
def criar_semanas(
    obra_atividade_id: UUID, payload: List[SemanaBaseIn], db: Session = Depends(get_db)
):
    _obter(db, ObraAtividade, obra_atividade_id)
    semanas = []
    for item in payload:
        services.validar_dia_inicial(item.dia_inicial_semana)
        semanas.append(
            ProdutividadeBaseSemana(obra_atividade_id=obra_atividade_id, **item.model_dump())
        )
    db.add_all(semanas)
    services.recalcular_obra_atividade(db, obra_atividade_id)
    db.commit()
    return semanas


@router.patch("/semanas/{base_id}", response_model=SemanaBaseOut, tags=["planejamento"])
def atualizar_semana(base_id: UUID, payload: SemanaBaseUpdate, db: Session = Depends(get_db)):
    base = _obter(db, ProdutividadeBaseSemana, base_id)
    alteracoes = payload.model_dump(exclude_unset=True)
    if "dia_inicial_semana" in alteracoes:
        services.validar_dia_inicial(alteracoes["dia_inicial_semana"])
    for campo, valor in alteracoes.items():
        setattr(base, campo, valor)
    services.recalcular_obra_atividade(db, base.obra_atividade_id)
    db.commit()
    return base


# --- Apontamento semanal (realizado) ---------------------------------------

@router.post(
    "/semanas/{base_id}/realizado/previa", response_model=PreviaOut, tags=["apontamento"]
)
def previa_realizado(base_id: UUID, payload: RealizadoIn, db: Session = Depends(get_db)):
    base = _obter(db, ProdutividadeBaseSemana, base_id)
    prod_media, indice = services.previa(base, payload)
    return PreviaOut(
        prod_media_equipe_dia=prod_media,
        indice_produtividade=indice,
        exige_justificativa=calculos.exige_justificativa(
            indice, settings.indice_limite_justificativa
        ),
    )


@router.put("/semanas/{base_id}/realizado", response_model=DadosOut, tags=["apontamento"])
def registrar_realizado(base_id: UUID, payload: RealizadoIn, db: Session = Depends(get_db)):
    base = _obter(db, ProdutividadeBaseSemana, base_id)
    return services.registrar_realizado(db, base, payload)


# --- Leitura consolidada ---------------------------------------------------

@router.get(
    "/obra-atividades/{obra_atividade_id}/acompanhamento",
    response_model=List[AcompanhamentoOut],
    tags=["dashboard"],
)
def acompanhamento(obra_atividade_id: UUID, db: Session = Depends(get_db)):
    _obter(db, ObraAtividade, obra_atividade_id)
    return [
        AcompanhamentoOut(
            base_id=base.id,
            semana=base.semana,
            dia_inicial_semana=base.dia_inicial_semana,
            previsto_semana=base.previsto_semana,
            prod_orcada_media_equipe_dia=base.prod_orcada_media_equipe_dia,
            previsto_acumulado_plano=calc.previsto_acumulado,
            dados=base.dados,
        )
        for base, calc in services.calcular(services.carregar_serie(db, obra_atividade_id))
    ]

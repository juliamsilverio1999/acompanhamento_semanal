"""Regras de persistência: grava apontamentos e recalcula a série inteira.

Os campos acumulados dependem das semanas anteriores, então qualquer alteração
(realizado ou previsto) recalcula todas as semanas da obra/atividade.
"""
from decimal import Decimal
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import calculos
from app.config import settings
from app.models import DadosObraAtividade, ProdutividadeBaseSemana
from app.schemas import RealizadoIn


class RegraNegocioError(ValueError):
    pass


def validar_dia_inicial(dia) -> None:
    if dia.weekday() != settings.primeiro_dia_semana:
        raise RegraNegocioError(
            f"dia_inicial_semana {dia} não cai no primeiro dia da semana "
            f"configurado (PRIMEIRO_DIA_SEMANA={settings.primeiro_dia_semana})"
        )


def carregar_serie(db: Session, obra_atividade_id: UUID) -> List[ProdutividadeBaseSemana]:
    return list(
        db.scalars(
            select(ProdutividadeBaseSemana)
            .where(ProdutividadeBaseSemana.obra_atividade_id == obra_atividade_id)
            .order_by(ProdutividadeBaseSemana.semana)
            .options(selectinload(ProdutividadeBaseSemana.dados))
        )
    )


def calcular(
    bases: List[ProdutividadeBaseSemana],
) -> List[Tuple[ProdutividadeBaseSemana, calculos.SemanaCalculada]]:
    entradas = [
        calculos.SemanaEntrada(
            semana=b.semana,
            previsto_semana=b.previsto_semana,
            prod_orcada_media_equipe_dia=b.prod_orcada_media_equipe_dia,
            real=b.dados.real if b.dados else None,
            equipe=b.dados.equipe if b.dados else None,
        )
        for b in bases
    ]
    return list(zip(bases, calculos.calcular_serie(entradas, settings.dias_trabalhados_semana)))


def recalcular_obra_atividade(db: Session, obra_atividade_id: UUID) -> None:
    db.flush()
    for base, calc in calcular(carregar_serie(db, obra_atividade_id)):
        if base.dados is None:
            continue
        base.dados.previsto_acumulado = calc.previsto_acumulado
        base.dados.real_acumulado = calc.real_acumulado
        base.dados.delta_acumulado = calc.delta_acumulado
        base.dados.prod_media_equipe_dia = calc.prod_media_equipe_dia
        base.dados.indice_produtividade = calc.indice_produtividade


def previa(
    base: ProdutividadeBaseSemana, entrada: RealizadoIn
) -> Tuple[Optional[Decimal], Optional[Decimal]]:
    """(prod_media_equipe_dia, indice_produtividade) sem gravar nada."""
    return calculos.calcular_semana(
        entrada.real,
        entrada.equipe,
        base.prod_orcada_media_equipe_dia,
        settings.dias_trabalhados_semana,
    )


def registrar_realizado(
    db: Session, base: ProdutividadeBaseSemana, entrada: RealizadoIn
) -> DadosObraAtividade:
    _, indice = previa(base, entrada)
    justificativa: Optional[str] = (entrada.justificativa or "").strip() or None
    if justificativa is None and calculos.exige_justificativa(
        indice, settings.indice_limite_justificativa
    ):
        raise RegraNegocioError(
            f"justificativa obrigatória: índice {indice} abaixo do limite "
            f"{settings.indice_limite_justificativa}"
        )

    dados = base.dados
    if dados is None:
        # Acumulados são preenchidos pelo recálculo logo abaixo
        dados = DadosObraAtividade(previsto_acumulado=0, real_acumulado=0, delta_acumulado=0)
        base.dados = dados
    dados.real = entrada.real
    dados.equipe = entrada.equipe
    dados.justificativa = justificativa
    # Só substitui o dado_extra quando enviado: o formulário não o envia e não pode apagá-lo
    if "dado_extra" in entrada.model_fields_set:
        dados.dado_extra = entrada.dado_extra

    recalcular_obra_atividade(db, base.obra_atividade_id)
    db.commit()
    return dados

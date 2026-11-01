"""Modelagem física, fiel ao diagrama "Obras Productivity Data Architecture".

Desvios em relação ao diagrama (discutidos em docs/analise_modelagem.md):
  - decimal(10,6) -> numeric(18,6): (10,6) só comporta até 9.999,999999,
    insuficiente para quantidades acumuladas (m², kg...).
  - DADOS_OBRA_ATIVIDADE 1:1 com a semana base (unique na FK), em vez de 1:N.
  - Constraints de unicidade (cod_obra, obra+atividade, obra_atividade+semana).
  - Colunas de auditoria criado_em / atualizado_em.
"""
import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

NUM = Numeric(18, 6)
JSON_TYPE = JSON().with_variant(JSONB(), "postgresql")


class UnidadeMedida(str, enum.Enum):
    M = "m"
    M2 = "m2"
    M3 = "m3"
    KG = "kg"
    T = "t"
    UN = "un"
    VB = "vb"
    H = "h"


class AuditoriaMixin:
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Obra(AuditoriaMixin, Base):
    __tablename__ = "obras"
    __table_args__ = (
        CheckConstraint("uf = upper(uf) AND length(uf) = 2", name="ck_obras_uf"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    nome: Mapped[str] = mapped_column(String(255))
    cod_obra: Mapped[str] = mapped_column(String(5), unique=True)
    uf: Mapped[str] = mapped_column(String(2))
    cidade: Mapped[str] = mapped_column(String(255))

    atividades: Mapped[List["ObraAtividade"]] = relationship(back_populates="obra")


class Atividade(AuditoriaMixin, Base):
    __tablename__ = "atividades"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    nome: Mapped[str] = mapped_column(String(255), unique=True)
    unidade_medida: Mapped[UnidadeMedida] = mapped_column(
        Enum(
            UnidadeMedida,
            name="unidade_medida",
            values_callable=lambda e: [m.value for m in e],
        )
    )


class ObraAtividade(AuditoriaMixin, Base):
    __tablename__ = "obra_atividade"
    __table_args__ = (UniqueConstraint("obra_id", "atividade_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    obra_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("obras.id"))
    atividade_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("atividades.id"))

    obra: Mapped["Obra"] = relationship(back_populates="atividades")
    atividade: Mapped["Atividade"] = relationship()
    semanas: Mapped[List["ProdutividadeBaseSemana"]] = relationship(
        back_populates="obra_atividade", order_by="ProdutividadeBaseSemana.semana"
    )


class ProdutividadeBaseSemana(AuditoriaMixin, Base):
    __tablename__ = "produtividade_base_obra_atividade_semana"
    __table_args__ = (
        UniqueConstraint("obra_atividade_id", "semana"),
        UniqueConstraint("obra_atividade_id", "dia_inicial_semana"),
        CheckConstraint("semana >= 1", name="ck_base_semana"),
        CheckConstraint("previsto_semana >= 0", name="ck_base_previsto"),
        CheckConstraint(
            "prod_orcada_media_equipe_dia > 0", name="ck_base_prod_orcada"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    obra_atividade_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("obra_atividade.id")
    )
    semana: Mapped[int]
    dia_inicial_semana: Mapped[date]
    previsto_semana: Mapped[Decimal] = mapped_column(NUM)
    prod_orcada_media_equipe_dia: Mapped[Decimal] = mapped_column(
        NUM, default=Decimal("1"), server_default="1"
    )

    obra_atividade: Mapped["ObraAtividade"] = relationship(back_populates="semanas")
    dados: Mapped[Optional["DadosObraAtividade"]] = relationship(
        back_populates="base", cascade="all, delete-orphan"
    )


class DadosObraAtividade(AuditoriaMixin, Base):
    __tablename__ = "dados_obra_atividade"
    __table_args__ = (
        CheckConstraint("real >= 0", name="ck_dados_real"),
        CheckConstraint("equipe >= 0", name="ck_dados_equipe"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    produtividade_base_obra_atividade_semana_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("produtividade_base_obra_atividade_semana.id"), unique=True
    )
    real: Mapped[Decimal] = mapped_column(NUM)
    previsto_acumulado: Mapped[Decimal] = mapped_column(NUM)
    real_acumulado: Mapped[Decimal] = mapped_column(NUM)
    delta_acumulado: Mapped[Decimal] = mapped_column(NUM)
    equipe: Mapped[int]
    prod_media_equipe_dia: Mapped[Optional[Decimal]] = mapped_column(NUM)
    indice_produtividade: Mapped[Optional[Decimal]] = mapped_column(NUM)
    justificativa: Mapped[Optional[str]] = mapped_column(Text)
    dado_extra: Mapped[Optional[dict]] = mapped_column(JSON_TYPE)

    base: Mapped["ProdutividadeBaseSemana"] = relationship(back_populates="dados")

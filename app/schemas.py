from datetime import date
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import UnidadeMedida


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ObraIn(BaseModel):
    nome: str = Field(min_length=1, max_length=255)
    cod_obra: str = Field(min_length=1, max_length=5)
    uf: str = Field(min_length=2, max_length=2)
    cidade: str = Field(min_length=1, max_length=255)

    @field_validator("uf")
    @classmethod
    def uf_maiuscula(cls, v: str) -> str:
        return v.upper()


class ObraOut(ObraIn, ORM):
    id: UUID


class AtividadeIn(BaseModel):
    nome: str = Field(min_length=1, max_length=255)
    unidade_medida: UnidadeMedida


class AtividadeOut(AtividadeIn, ORM):
    id: UUID


class ObraAtividadeIn(BaseModel):
    atividade_id: UUID


class ObraAtividadeOut(ORM):
    id: UUID
    obra_id: UUID
    atividade: AtividadeOut


class SemanaBaseIn(BaseModel):
    semana: int = Field(ge=1)
    dia_inicial_semana: date
    previsto_semana: Decimal = Field(ge=0)
    prod_orcada_media_equipe_dia: Decimal = Field(default=Decimal("1"), gt=0)


class SemanaBaseUpdate(BaseModel):
    dia_inicial_semana: Optional[date] = None
    previsto_semana: Optional[Decimal] = Field(default=None, ge=0)
    prod_orcada_media_equipe_dia: Optional[Decimal] = Field(default=None, gt=0)


class SemanaBaseOut(SemanaBaseIn, ORM):
    id: UUID
    obra_atividade_id: UUID


class RealizadoIn(BaseModel):
    real: Decimal = Field(ge=0)
    equipe: int = Field(ge=0)
    justificativa: Optional[str] = None
    dado_extra: Optional[dict] = None


class PreviaOut(BaseModel):
    prod_media_equipe_dia: Optional[Decimal]
    indice_produtividade: Optional[Decimal]
    exige_justificativa: bool


class DadosOut(ORM):
    id: UUID
    produtividade_base_obra_atividade_semana_id: UUID
    real: Decimal
    previsto_acumulado: Decimal
    real_acumulado: Decimal
    delta_acumulado: Decimal
    equipe: int
    prod_media_equipe_dia: Optional[Decimal]
    indice_produtividade: Optional[Decimal]
    justificativa: Optional[str]
    dado_extra: Optional[dict]


class AcompanhamentoOut(BaseModel):
    """Linha da série semanal: plano + realizado (quando houver)."""

    base_id: UUID
    semana: int
    dia_inicial_semana: date
    previsto_semana: Decimal
    prod_orcada_media_equipe_dia: Decimal
    # Calculado na leitura: no modelo atual o acumulado previsto só é gravado
    # em DADOS, então semanas futuras não teriam curva planejada.
    previsto_acumulado_plano: Decimal
    dados: Optional[DadosOut]

"""Motor de cálculo da produtividade semanal.

Funções puras (sem banco, sem HTTP): recebem a série de semanas de uma
obra/atividade e devolvem os campos calculados de DADOS_OBRA_ATIVIDADE.
Assim a mesma regra pode ser testada isoladamente e, no futuro, portada
para o Power Apps / Power Automate / Dataverse sem depender do backend.
"""
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import List, Optional, Sequence, Tuple

CASAS = Decimal("0.000001")
ZERO = Decimal("0")


def _q(valor: Optional[Decimal]) -> Optional[Decimal]:
    if valor is None:
        return None
    return valor.quantize(CASAS, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class SemanaEntrada:
    semana: int
    previsto_semana: Decimal
    prod_orcada_media_equipe_dia: Optional[Decimal]
    real: Optional[Decimal] = None  # None = semana ainda sem apontamento
    equipe: Optional[int] = None


@dataclass(frozen=True)
class SemanaCalculada:
    semana: int
    previsto_acumulado: Decimal
    real_acumulado: Decimal
    delta_acumulado: Decimal
    prod_media_equipe_dia: Optional[Decimal]
    indice_produtividade: Optional[Decimal]


def calcular_semana(
    real: Optional[Decimal],
    equipe: Optional[int],
    prod_orcada_media_equipe_dia: Optional[Decimal],
    dias_trabalhados_semana: int,
) -> Tuple[Optional[Decimal], Optional[Decimal]]:
    """Retorna (prod_media_equipe_dia, indice_produtividade) de uma semana.

    prod_media_equipe_dia = real / (equipe * dias_trabalhados_semana)
    indice_produtividade  = prod_media_equipe_dia / prod_orcada_media_equipe_dia
    Retorna None quando o divisor é zero/ausente, em vez de inventar um valor.
    """
    if real is None or not equipe or dias_trabalhados_semana <= 0:
        return None, None
    prod_media = real / (Decimal(equipe) * Decimal(dias_trabalhados_semana))
    if not prod_orcada_media_equipe_dia:
        return _q(prod_media), None
    return _q(prod_media), _q(prod_media / prod_orcada_media_equipe_dia)


def exige_justificativa(indice: Optional[Decimal], limite: Decimal) -> bool:
    return indice is not None and limite > 0 and indice < limite


def calcular_serie(
    semanas: Sequence[SemanaEntrada], dias_trabalhados_semana: int
) -> List[SemanaCalculada]:
    """Calcula acumulados e índices para toda a série de uma obra/atividade.

    `semanas` deve vir ordenada por número de semana, sem repetição. Semanas
    sem apontamento contam como real = 0 no acumulado.
    """
    for anterior, atual in zip(semanas, semanas[1:]):
        if atual.semana <= anterior.semana:
            raise ValueError("semanas devem estar em ordem estritamente crescente")

    previsto_acum = real_acum = ZERO
    resultado = []
    for s in semanas:
        previsto_acum += s.previsto_semana
        real_acum += s.real or ZERO
        prod_media, indice = calcular_semana(
            s.real, s.equipe, s.prod_orcada_media_equipe_dia, dias_trabalhados_semana
        )
        resultado.append(
            SemanaCalculada(
                semana=s.semana,
                previsto_acumulado=_q(previsto_acum),
                real_acumulado=_q(real_acum),
                delta_acumulado=_q(real_acum - previsto_acum),
                prod_media_equipe_dia=prod_media,
                indice_produtividade=indice,
            )
        )
    return resultado

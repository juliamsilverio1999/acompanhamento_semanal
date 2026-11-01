from decimal import Decimal as D

import pytest

from app.calculos import SemanaEntrada, calcular_semana, calcular_serie, exige_justificativa


def test_prod_media_e_indice():
    prod, indice = calcular_semana(D("150"), 2, D("15"), 5)
    assert prod == D("15.000000")
    assert indice == D("1.000000")


def test_equipe_zero_nao_divide():
    assert calcular_semana(D("10"), 0, D("15"), 5) == (None, None)


def test_sem_prod_orcada_nao_calcula_indice():
    prod, indice = calcular_semana(D("100"), 2, None, 5)
    assert prod == D("10.000000")
    assert indice is None


def test_serie_acumula_e_trata_semana_sem_apontamento():
    serie = calcular_serie(
        [
            SemanaEntrada(1, D("100"), D("10"), real=D("80"), equipe=2),
            SemanaEntrada(2, D("100"), D("10")),  # sem apontamento
            SemanaEntrada(3, D("50"), D("10"), real=D("120"), equipe=2),
        ],
        dias_trabalhados_semana=5,
    )
    assert [s.previsto_acumulado for s in serie] == [D("100"), D("200"), D("250")]
    assert [s.real_acumulado for s in serie] == [D("80"), D("80"), D("200")]
    assert serie[2].delta_acumulado == D("-50")
    assert serie[1].indice_produtividade is None
    assert serie[2].indice_produtividade == D("1.2")


def test_serie_fora_de_ordem_falha():
    with pytest.raises(ValueError):
        calcular_serie([SemanaEntrada(2, D("1"), D("1")), SemanaEntrada(1, D("1"), D("1"))], 5)


def test_regra_justificativa():
    assert exige_justificativa(D("0.85"), D("0.90"))
    assert not exige_justificativa(D("0.95"), D("0.90"))
    assert not exige_justificativa(None, D("0.90"))
    assert not exige_justificativa(D("0.10"), D("0"))

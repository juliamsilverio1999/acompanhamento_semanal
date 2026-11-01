"""Gera o payload de realizado (PUT /semanas/{base_id}/realizado, um por semana)
a partir das planilhas "PREVISTO X REALIZADO | Curvas".

    python scripts/gerar_payload_realizado.py PLANILHA.xlsx \
        --aba "Rede POÇOS Sabesp 10 C" --linha-real 20 --linha-equipe 25 --linha-prod 26 \
        --data-e-fim-da-semana --coluna-justificativa "POÇOS" --remapear-justificativa 21:41,22:42 \
        --saida data/payloads/sabesp10c_pocos_realizado.json

Cada item traz `semana` e `dia_inicial_semana` para localizar a semana planejada
(base_id) na hora da carga, e o corpo do PUT (real, equipe, justificativa, dado_extra).

Semanas com índice abaixo de INDICE_LIMITE_JUSTIFICATIVA e sem justificativa na
planilha recebem um texto padrão de importação, para não serem recusadas pela API.
"""
import argparse
import json
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import openpyxl  # noqa: E402

from app import calculos  # noqa: E402
from app.config import settings  # noqa: E402
from app.schemas import RealizadoIn  # noqa: E402
from gerar_payload_planejamento import decimal6  # noqa: E402

SEM_JUSTIFICATIVA = "[Importação] Sem justificativa registrada na planilha de origem."


def achar_aba(wb, nome):
    aba = next((n for n in wb.sheetnames if nome.lower().strip() in n.lower()), None)
    if aba is None:
        sys.exit(f"aba '{nome}' não encontrada. Abas: {wb.sheetnames}")
    return aba


def ler_justificativas(wb, aba, coluna, remapear):
    """{semana: texto} a partir da aba de justificativas (coluna 'Semana' + coluna da atividade)."""
    linhas = list(wb[achar_aba(wb, aba)].iter_rows(values_only=True))
    cabecalho = [str(c).strip().upper() if c else "" for c in linhas[0]]
    i_semana, i_texto = cabecalho.index("SEMANA"), cabecalho.index(coluna.strip().upper())
    textos = {}
    for row in linhas[1:]:
        semana, texto = row[i_semana], row[i_texto]
        if isinstance(semana, (int, float)) and texto:
            semana = remapear.get(int(semana), int(semana))
            if semana in textos:
                sys.exit(f"justificativa duplicada para a semana {semana}")
            textos[semana] = str(texto).strip()
    return textos


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("planilha")
    p.add_argument("--aba", required=True)
    p.add_argument("--linha-datas", type=int, default=2)
    p.add_argument("--linha-real", type=int, required=True)
    p.add_argument("--linha-equipe", type=int, required=True)
    p.add_argument("--linha-prod", type=int, required=True, help="prod. orçada, só para prever o índice")
    p.add_argument("--coluna-inicial", type=int, default=2)
    p.add_argument("--ate-semana", type=int, help="padrão: última semana com real > 0")
    p.add_argument("--data-e-fim-da-semana", action="store_true")
    p.add_argument("--aba-justificativas", default="Justificativas")
    p.add_argument("--coluna-justificativa", help="coluna da atividade na aba de justificativas")
    p.add_argument(
        "--remapear-justificativa", default="",
        help="corrige o número da semana na aba de justificativas, ex.: 21:41,22:42",
    )
    p.add_argument("--origem", help="nome do arquivo de origem gravado em dado_extra (padrão: nome da planilha)")
    p.add_argument("--saida", required=True)
    args = p.parse_args()

    remapear = {
        int(de): int(para)
        for par in filter(None, args.remapear_justificativa.split(","))
        for de, para in [par.split(":")]
    }
    wb = openpyxl.load_workbook(args.planilha, data_only=True, read_only=True)
    aba = achar_aba(wb, args.aba)
    linhas = {
        i: row
        for i, row in enumerate(wb[aba].iter_rows(values_only=True), start=1)
        if i in (args.linha_datas, args.linha_real, args.linha_equipe, args.linha_prod)
    }
    justificativas = (
        ler_justificativas(wb, args.aba_justificativas, args.coluna_justificativa, remapear)
        if args.coluna_justificativa else {}
    )

    def celula(linha, col):
        row = linhas[linha]
        return row[col] if col < len(row) else None

    colunas = range(args.coluna_inicial - 1, len(linhas[args.linha_datas]))
    semana_de = lambda col: col - args.coluna_inicial + 2  # noqa: E731
    ultima = args.ate_semana or max(
        semana_de(c) for c in colunas
        if isinstance(celula(args.linha_real, c), (int, float)) and celula(args.linha_real, c) > 0
    )

    payload, erros, sem_texto = [], [], []
    for col in colunas:
        semana = semana_de(col)
        if semana > ultima:
            break
        dia, real = celula(args.linha_datas, col), celula(args.linha_real, col)
        equipe, prod = celula(args.linha_equipe, col), celula(args.linha_prod, col)
        if isinstance(dia, datetime):
            dia = dia.date()
        if not isinstance(dia, date) or not isinstance(real, (int, float)) or not isinstance(equipe, (int, float)):
            erros.append(f"semana {semana}: data/real/equipe inválidos ({dia!r}, {real!r}, {equipe!r})")
            continue
        inicio = dia - timedelta(days=6) if args.data_e_fim_da_semana else dia

        _, indice = calculos.calcular_semana(
            decimal6(real), int(equipe), decimal6(prod) if prod else None,
            settings.dias_trabalhados_semana,
        )
        justificativa = justificativas.get(semana)
        if justificativa is None and calculos.exige_justificativa(indice, settings.indice_limite_justificativa):
            justificativa = SEM_JUSTIFICATIVA
            sem_texto.append(semana)

        corpo = {
            "real": str(decimal6(real)),
            "equipe": int(equipe),
            "justificativa": justificativa,
            "dado_extra": {
                "origem": args.origem or Path(args.planilha).name,
                "aba": aba,
                "semana_planilha": semana,
                **({"justificativa_remapeada_de": k for k, v in remapear.items() if v == semana}),
            },
        }
        try:
            RealizadoIn(**corpo)
        except ValueError as e:
            erros.append(f"semana {semana}: {e}")
        payload.append({
            "semana": semana,
            "dia_inicial_semana": inicio.isoformat(),
            "indice_previsto": str(indice) if indice is not None else None,
            **corpo,
        })

    if erros:
        sys.exit("payload inválido:\n  " + "\n  ".join(erros))
    sobrando = sorted(set(justificativas) - {i["semana"] for i in payload})
    saida = Path(args.saida)
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"aba: {aba}")
    print(f"{len(payload)} semanas: 1 a {ultima} | total real: {sum(Decimal(i['real']) for i in payload)}")
    print(f"com justificativa da planilha: {sum(1 for i in payload if i['semana'] in justificativas)}")
    print(f"índice < {settings.indice_limite_justificativa} sem justificativa (texto padrão): {sem_texto}")
    print(f"justificativas da planilha fora do intervalo importado: {sobrando}")
    print(f"gravado em {saida}")


if __name__ == "__main__":
    main()

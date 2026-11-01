"""Gera o payload de planejamento (POST /obra-atividades/{id}/semanas) a partir
das planilhas "PREVISTO X REALIZADO | Curvas", onde cada coluna é uma semana.

    python scripts/gerar_payload_planejamento.py PLANILHA.xlsx \
        --aba "Rede POÇOS Sabesp 10 C" --linha-previsto 19 --linha-prod 26 \
        --data-e-fim-da-semana --saida data/payloads/sabesp10c_pocos_planejamento.json

Usa só as semanas com previsto numérico. Valida cada item com o mesmo schema
da API e com a regra de PRIMEIRO_DIA_SEMANA antes de gravar o arquivo.
"""
import argparse
import json
import sys
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import openpyxl  # noqa: E402

from app.config import settings  # noqa: E402
from app.schemas import SemanaBaseIn  # noqa: E402

CASAS = Decimal("0.000001")


def decimal6(valor) -> Decimal:
    return Decimal(str(valor)).quantize(CASAS, rounding=ROUND_HALF_UP)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("planilha")
    p.add_argument("--aba", required=True, help="nome da aba (busca parcial, sem diferenciar maiúsculas)")
    p.add_argument("--linha-datas", type=int, default=2)
    p.add_argument("--linha-previsto", type=int, required=True)
    p.add_argument("--linha-prod", type=int, required=True)
    p.add_argument("--coluna-inicial", type=int, default=2, help="coluna da Sem 01 (B = 2)")
    p.add_argument(
        "--data-e-fim-da-semana", action="store_true",
        help="a data da planilha é o último dia da semana; o início é 6 dias antes",
    )
    p.add_argument("--saida", required=True)
    args = p.parse_args()

    wb = openpyxl.load_workbook(args.planilha, data_only=True, read_only=True)
    nome = next((n for n in wb.sheetnames if args.aba.lower().strip() in n.lower()), None)
    if nome is None:
        sys.exit(f"aba '{args.aba}' não encontrada. Abas: {wb.sheetnames}")
    linhas = {
        i: row
        for i, row in enumerate(wb[nome].iter_rows(values_only=True), start=1)
        if i in (args.linha_datas, args.linha_previsto, args.linha_prod)
    }

    payload, erros = [], []
    for col in range(args.coluna_inicial - 1, len(linhas[args.linha_datas])):
        dia, previsto = linhas[args.linha_datas][col], linhas[args.linha_previsto][col]
        prod = linhas[args.linha_prod][col] if col < len(linhas[args.linha_prod]) else None
        if not isinstance(previsto, (int, float)):
            continue
        if isinstance(dia, datetime):
            dia = dia.date()
        if not isinstance(dia, date):
            erros.append(f"coluna {col + 1}: data inválida {dia!r}")
            continue
        inicio = dia - timedelta(days=6) if args.data_e_fim_da_semana else dia
        item = {
            "semana": col - args.coluna_inicial + 2,
            "dia_inicial_semana": inicio.isoformat(),
            "previsto_semana": str(decimal6(previsto)),
            "prod_orcada_media_equipe_dia": str(decimal6(prod)) if prod is not None else None,
        }
        try:
            SemanaBaseIn(**item)
        except ValueError as e:
            erros.append(f"semana {item['semana']}: {e}")
        if inicio.weekday() != settings.primeiro_dia_semana:
            erros.append(
                f"semana {item['semana']}: {inicio} não cai no dia {settings.primeiro_dia_semana} "
                "(PRIMEIRO_DIA_SEMANA)"
            )
        payload.append(item)

    if erros:
        sys.exit("payload inválido:\n  " + "\n  ".join(erros))

    numeros = [i["semana"] for i in payload]
    if numeros != list(range(numeros[0], numeros[0] + len(numeros))):
        sys.exit(f"semanas com buraco no previsto: {numeros}")

    saida = Path(args.saida)
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    total = sum(Decimal(i["previsto_semana"]) for i in payload)
    print(f"aba: {nome}")
    print(f"{len(payload)} semanas: {payload[0]['semana']} ({payload[0]['dia_inicial_semana']}) "
          f"a {payload[-1]['semana']} ({payload[-1]['dia_inicial_semana']})")
    print(f"total previsto: {total}")
    print(f"prod. orçada distintas: {sorted({i['prod_orcada_media_equipe_dia'] for i in payload})}")
    print(f"gravado em {saida}")


if __name__ == "__main__":
    main()

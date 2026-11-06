"""Gera os payloads de planejamento e de realizado a partir das planilhas
"INDICADORES", cuja aba DB tem uma coluna por DIA (linha de datas) e linhas
diárias de previsto/realizado. Os dias são somados por semana (segunda a domingo).

    python scripts/gerar_payload_diario.py PLANILHA.xlsx \
        --linha-previsto 6 --linha-real 7 --linha-referencia 5 \
        --celula-prod-orcada E6 --equipe 1 \
        --saida-planejamento data/payloads/x_planejamento.json \
        --saida-realizado data/payloads/x_realizado.json

Planejamento: da primeira à última semana com previsto (semanas vazias no meio
entram com previsto 0). Realizado: semanas completas antes da data de corte
(célula --celula-data-corte), até a última com real > 0.
"""
import argparse
import json
import sys
import warnings
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import openpyxl  # noqa: E402

from app import calculos  # noqa: E402
from app.config import settings  # noqa: E402
from app.schemas import RealizadoIn, SemanaBaseIn  # noqa: E402
from gerar_payload_planejamento import decimal6  # noqa: E402
from gerar_payload_realizado import SEM_JUSTIFICATIVA  # noqa: E402

warnings.filterwarnings("ignore", module="openpyxl")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("planilha")
    p.add_argument("--aba", default="DB")
    p.add_argument("--linha-datas", type=int, default=3)
    p.add_argument("--linha-previsto", type=int, required=True)
    p.add_argument("--linha-real", type=int, required=True)
    p.add_argument("--linha-referencia", type=int, help="previsto alternativo guardado em dado_extra")
    p.add_argument("--celula-data-corte", default="C3")
    p.add_argument("--celula-prod-orcada", help="célula com a prod. orçada (ex.: E6)")
    p.add_argument("--prod-orcada", type=Decimal, help="valor fixo, se não vier de célula")
    p.add_argument("--equipe", type=int, default=1)
    p.add_argument("--origem", help="nome do arquivo gravado em dado_extra (padrão: nome da planilha)")
    p.add_argument("--saida-planejamento", required=True)
    p.add_argument("--saida-realizado", required=True)
    args = p.parse_args()

    wb = openpyxl.load_workbook(args.planilha, data_only=True)
    if args.aba not in wb.sheetnames:
        sys.exit(f"aba '{args.aba}' não encontrada. Abas: {wb.sheetnames}")
    ws = wb[args.aba]
    corte = ws[args.celula_data_corte].value
    corte = corte.date() if isinstance(corte, datetime) else corte
    if not isinstance(corte, date):
        sys.exit(f"data de corte inválida em {args.celula_data_corte}: {corte!r}")
    prod_orcada = args.prod_orcada if args.prod_orcada is not None else ws[args.celula_prod_orcada].value
    if prod_orcada is None:
        sys.exit("informe --celula-prod-orcada ou --prod-orcada")
    prod_orcada = decimal6(prod_orcada)

    linhas = {"previsto": args.linha_previsto, "real": args.linha_real}
    if args.linha_referencia:
        linhas["referencia"] = args.linha_referencia
    semanas = defaultdict(lambda: defaultdict(Decimal))
    for col in range(1, ws.max_column + 1):
        dia = ws.cell(args.linha_datas, col).value
        if not isinstance(dia, datetime):
            continue
        segunda = dia.date() - timedelta(days=dia.weekday())
        for nome, linha in linhas.items():
            v = ws.cell(linha, col).value
            if isinstance(v, (int, float)) and v:
                semanas[segunda][nome] += Decimal(str(v))

    com_previsto = sorted(s for s in semanas if semanas[s]["previsto"] > 0)
    inicio, fim = com_previsto[0], com_previsto[-1]
    planejamento, numero = [], {}
    dia = inicio
    while dia <= fim:
        numero[dia] = len(planejamento) + 1
        item = {
            "semana": numero[dia],
            "dia_inicial_semana": dia.isoformat(),
            "previsto_semana": str(decimal6(semanas[dia]["previsto"])),
            "prod_orcada_media_equipe_dia": str(prod_orcada),
        }
        SemanaBaseIn(**item)
        planejamento.append(item)
        dia += timedelta(weeks=1)

    # Só semanas fechadas antes da data de corte, até a última com real > 0
    fechadas = [s for s in numero if s + timedelta(days=6) < corte]
    ultima = max(s for s in fechadas if semanas[s]["real"] > 0)
    origem = args.origem or Path(args.planilha).name
    realizado, sem_texto = [], []
    for s in sorted(fechadas):
        if s > ultima:
            break
        real = decimal6(semanas[s]["real"])
        _, indice = calculos.calcular_semana(real, args.equipe, prod_orcada, settings.dias_trabalhados_semana)
        justificativa = None
        if calculos.exige_justificativa(indice, settings.indice_limite_justificativa):
            justificativa = SEM_JUSTIFICATIVA
            sem_texto.append(numero[s])
        dado_extra = {"origem": origem, "aba": args.aba, "semana_iso": f"{s.isocalendar()[0]}-W{s.isocalendar()[1]:02d}"}
        if "referencia" in linhas:
            dado_extra["previsto_linha_base"] = str(decimal6(semanas[s]["referencia"]))
        corpo = {"real": str(real), "equipe": args.equipe, "justificativa": justificativa, "dado_extra": dado_extra}
        RealizadoIn(**corpo)
        realizado.append({
            "semana": numero[s],
            "dia_inicial_semana": s.isoformat(),
            "indice_previsto": str(indice) if indice is not None else None,
            **corpo,
        })

    for caminho, dados in ((args.saida_planejamento, planejamento), (args.saida_realizado, realizado)):
        Path(caminho).parent.mkdir(parents=True, exist_ok=True)
        Path(caminho).write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"data de corte: {corte} | prod. orçada: {prod_orcada} | equipe: {args.equipe}")
    print(f"planejamento: {len(planejamento)} semanas ({inicio} a {fim}), "
          f"total {sum(Decimal(i['previsto_semana']) for i in planejamento)}, "
          f"semanas com previsto 0: {[i['semana'] for i in planejamento if Decimal(i['previsto_semana']) == 0]}")
    print(f"realizado: {len(realizado)} semanas ({realizado[0]['dia_inicial_semana']} a "
          f"{realizado[-1]['dia_inicial_semana']}), total {sum(Decimal(i['real']) for i in realizado)}")
    print(f"índice < {settings.indice_limite_justificativa} (texto padrão): {len(sem_texto)} semanas {sem_texto}")
    print(f"gravado em {args.saida_planejamento} e {args.saida_realizado}")


if __name__ == "__main__":
    main()

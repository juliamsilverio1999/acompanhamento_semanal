"""Importa várias atividades de uma planilha de curvas (semanas em colunas)
a partir de um arquivo de configuração por obra (data/importacoes/*.json).

    python scripts/importar_curvas.py data/importacoes/ses_teresopolis.json PLANILHA.xlsx
    python scripts/importar_curvas.py ... --persistir   # também grava via API

Para cada atividade gera dois payloads em data/payloads/:
  <prefixo>_<atividade>_planejamento.json  -> POST /obra-atividades/{id}/semanas
  <prefixo>_<atividade>_realizado.json     -> PUT /semanas/{base_id}/realizado (um por semana)

Regras:
  - a data de cada coluna é levada para a segunda-feira da semana; as semanas
    precisam ser consecutivas;
  - planejamento: da 1ª semana até a última com previsto ou com real (até a data de
    corte); semanas sem previsto entram com 0;
  - realizado: semanas com real até a semana da data de corte;
  - valores multiplicados por `fator` (ex.: km -> m = 1000; fração -> % = 100);
  - prod. orçada vazia (índice não calculado);
  - a justificativa da configuração vai na semana da data de corte.
--persistir recusa atividades que já tenham semanas planejadas.
"""
import argparse
import json
import re
import sys
import unicodedata
import warnings
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import openpyxl  # noqa: E402
import requests  # noqa: E402
from openpyxl.utils import get_column_letter  # noqa: E402

from app.config import settings  # noqa: E402
from app.schemas import RealizadoIn, SemanaBaseIn  # noqa: E402
from gerar_payload_planejamento import decimal6  # noqa: E402

warnings.filterwarnings("ignore", module="openpyxl")
API = settings.api_base_url.rstrip("/")


def slug(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", texto.lower()).strip("_")


def numero(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def montar(ws, cfg, corte: date, origem: str):
    fator = Decimal(str(cfg["fator"]))
    linhas = cfg["linhas"]
    colunas = []
    for c in range(cfg["coluna_inicial"], ws.max_column + 1):
        d = ws.cell(cfg["linha_datas"], c).value
        if isinstance(d, datetime):
            colunas.append((c, d.date() - timedelta(days=d.date().weekday())))
    erros = [
        f"{get_column_letter(c2)}: {s2} não é a semana seguinte a {s1}"
        for (_, s1), (c2, s2) in zip(colunas, colunas[1:]) if s2 != s1 + timedelta(weeks=1)
    ]
    if erros:
        sys.exit(f"{cfg['aba']}: semanas não consecutivas\n  " + "\n  ".join(erros))

    valor = lambda campo, c: ws.cell(linhas[campo], c).value if campo in linhas else None  # noqa: E731
    relevantes = [
        i for i, (c, seg) in enumerate(colunas)
        if numero(valor("previsto", c)) or (numero(valor("real", c)) and seg <= corte)
    ]
    colunas = colunas[: relevantes[-1] + 1]

    planejamento, realizado = [], []
    for n, (c, seg) in enumerate(colunas, start=1):
        previsto = valor("previsto", c)
        item = {
            "semana": n,
            "dia_inicial_semana": seg.isoformat(),
            "previsto_semana": str(decimal6(Decimal(str(previsto)) * fator if numero(previsto) else 0)),
            "prod_orcada_media_equipe_dia": None,
        }
        SemanaBaseIn(**item)
        planejamento.append(item)

        real = valor("real", c)
        if not numero(real) or seg > corte:
            continue
        equipe = valor("equipe", c)
        dado_extra = {"origem": origem, "aba": cfg["aba"], "coluna": get_column_letter(c)}
        for campo in ("equipe_prevista", "dias_trabalhados_real"):
            if numero(valor(campo, c)):
                dado_extra[campo] = valor(campo, c)
        replan = {
            rotulo: str(decimal6(Decimal(str(ws.cell(l, c).value)) * fator))
            for rotulo, l in cfg.get("replanejados", {}).items() if numero(ws.cell(l, c).value)
        }
        if replan:
            dado_extra["previsto_replanejado"] = replan
        corpo = {
            "real": str(decimal6(Decimal(str(real)) * fator)),
            "equipe": str(decimal6(equipe)) if numero(equipe) else None,
            "justificativa": cfg.get("justificativa") if seg == corte else None,
            "dado_extra": dado_extra,
        }
        RealizadoIn(**corpo)
        realizado.append({"semana": n, "dia_inicial_semana": seg.isoformat(), **corpo})
    return planejamento, realizado


def persistir(cfg, planejamento, realizado) -> None:
    va = cfg["obra_atividade_id"]
    r = requests.get(f"{API}/obra-atividades/{va}/acompanhamento", timeout=30)
    r.raise_for_status()
    if r.json():
        sys.exit(f"{cfg['atividade']}: já tem {len(r.json())} semanas planejadas; nada foi gravado")
    r = requests.post(f"{API}/obra-atividades/{va}/semanas", json=planejamento, timeout=60)
    if r.status_code != 201:
        sys.exit(f"{cfg['atividade']}: POST planejamento HTTP {r.status_code} {r.text}")
    base_por_semana = {s["semana"]: s["id"] for s in r.json()}
    for item in realizado:
        corpo = {k: item[k] for k in ("real", "equipe", "justificativa", "dado_extra")}
        r = requests.put(f"{API}/semanas/{base_por_semana[item['semana']]}/realizado", json=corpo, timeout=30)
        if r.status_code != 200:
            sys.exit(f"{cfg['atividade']} semana {item['semana']}: HTTP {r.status_code} {r.text}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("config")
    p.add_argument("planilha")
    p.add_argument("--persistir", action="store_true")
    p.add_argument("--saida-dir", default=str(ROOT / "data" / "payloads"))
    args = p.parse_args()

    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    corte = date.fromisoformat(config["data_corte"])
    wb = openpyxl.load_workbook(args.planilha, data_only=True)
    saida = Path(args.saida_dir)
    saida.mkdir(parents=True, exist_ok=True)

    gerados = []
    for cfg in config["atividades"]:
        if cfg["aba"] not in wb.sheetnames:
            sys.exit(f"aba '{cfg['aba']}' não encontrada")
        planejamento, realizado = montar(wb[cfg["aba"]], cfg, corte, config["origem"])
        base = f"{config['prefixo_payload']}_{slug(cfg['atividade'])}"
        for sufixo, dados in (("planejamento", planejamento), ("realizado", realizado)):
            (saida / f"{base}_{sufixo}.json").write_text(
                json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        gerados.append((cfg, planejamento, realizado))
        print(
            f"{cfg['atividade']}: {len(planejamento)} semanas ({planejamento[0]['dia_inicial_semana']} a "
            f"{planejamento[-1]['dia_inicial_semana']}), previsto {sum(Decimal(i['previsto_semana']) for i in planejamento)}"
            f" | realizado {len(realizado)} semanas, total {sum(Decimal(i['real']) for i in realizado)}"
        )

    if args.persistir:
        for cfg, planejamento, realizado in gerados:
            persistir(cfg, planejamento, realizado)
            print(f"gravado: {cfg['atividade']}")


if __name__ == "__main__":
    main()

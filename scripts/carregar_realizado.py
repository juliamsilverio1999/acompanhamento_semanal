"""Carrega um payload de realizado (gerado por gerar_payload_realizado.py) via API.

    python scripts/carregar_realizado.py OBRA_ATIVIDADE_ID data/payloads/arquivo.json

Para cada item: localiza a semana planejada pelo número, confere a data inicial
e faz PUT /semanas/{base_id}/realizado. Para no primeiro erro.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import requests  # noqa: E402

from app.config import settings  # noqa: E402

API = settings.api_base_url.rstrip("/")
CAMPOS = ("real", "equipe", "justificativa", "dado_extra")


def main() -> None:
    obra_atividade_id, arquivo = sys.argv[1], sys.argv[2]
    itens = json.loads(Path(arquivo).read_text(encoding="utf-8"))

    r = requests.get(f"{API}/obra-atividades/{obra_atividade_id}/acompanhamento", timeout=30)
    r.raise_for_status()
    semanas = {l["semana"]: l for l in r.json()}

    for item in itens:
        base = semanas.get(item["semana"])
        if base is None:
            sys.exit(f"semana {item['semana']} não está planejada")
        if base["dia_inicial_semana"] != item["dia_inicial_semana"]:
            sys.exit(
                f"semana {item['semana']}: data planejada {base['dia_inicial_semana']} "
                f"difere do payload {item['dia_inicial_semana']}"
            )

    for item in itens:
        base = semanas[item["semana"]]
        r = requests.put(
            f"{API}/semanas/{base['base_id']}/realizado",
            json={k: item[k] for k in CAMPOS},
            timeout=30,
        )
        if r.status_code != 200:
            sys.exit(f"semana {item['semana']}: HTTP {r.status_code} {r.text}")
    print(f"{len(itens)} semanas de realizado carregadas")


if __name__ == "__main__":
    main()

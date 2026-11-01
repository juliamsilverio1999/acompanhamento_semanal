"""Popula o banco com uma obra de exemplo (idempotente): python scripts/seed.py"""
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app import services  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import (  # noqa: E402
    Atividade,
    Obra,
    ObraAtividade,
    ProdutividadeBaseSemana,
    UnidadeMedida,
)
from app.schemas import RealizadoIn  # noqa: E402

INICIO = date(2026, 10, 5)  # segunda-feira
PREVISTO = [Decimal(v) for v in ("120", "150", "180", "180", "180", "150", "120", "80")]
REALIZADO = [  # (real, equipe, justificativa)
    (Decimal("110"), 2, "Mobilização da equipe na primeira semana"),
    (Decimal("160"), 2, None),
    (Decimal("130"), 2, "Chuva em 2 dias da semana"),
    (Decimal("175"), 2, None),
]


def main() -> None:
    with SessionLocal() as db:
        if db.scalar(select(Obra).where(Obra.cod_obra == "OB001")):
            print("seed já aplicado")
            return

        obra = Obra(nome="Obra Exemplo", cod_obra="OB001", uf="SP", cidade="São Paulo")
        atividade = Atividade(nome="Alvenaria de vedação", unidade_medida=UnidadeMedida.M2)
        vinculo = ObraAtividade(obra=obra, atividade=atividade)
        db.add(vinculo)
        bases = [
            ProdutividadeBaseSemana(
                obra_atividade=vinculo,
                semana=i + 1,
                dia_inicial_semana=INICIO + timedelta(weeks=i),
                previsto_semana=previsto,
                prod_orcada_media_equipe_dia=Decimal("15"),
            )
            for i, previsto in enumerate(PREVISTO)
        ]
        db.add_all(bases)
        db.flush()

        for base, (real, equipe, just) in zip(bases, REALIZADO):
            services.registrar_realizado(
                db, base, RealizadoIn(real=real, equipe=equipe, justificativa=just)
            )
        print(f"seed aplicado: obra {obra.cod_obra}, {len(bases)} semanas planejadas")


if __name__ == "__main__":
    main()

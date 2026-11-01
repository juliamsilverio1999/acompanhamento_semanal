from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.api import router
from app.services import RegraNegocioError

app = FastAPI(title="Acompanhamento Semanal de Produtividade", version="0.1.0")
app.include_router(router)


@app.exception_handler(IntegrityError)
def conflito(request: Request, exc: IntegrityError):
    return JSONResponse(
        status_code=409, content={"detail": f"Violação de integridade: {exc.orig}"}
    )


@app.exception_handler(RegraNegocioError)
def regra_negocio(request: Request, exc: RegraNegocioError):
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.get("/health", tags=["infra"])
def health():
    return {"status": "ok"}

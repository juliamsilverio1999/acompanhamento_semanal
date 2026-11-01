"""Sobe a API com host/porta do .env: python -m app"""
import uvicorn

from app.config import settings

uvicorn.run(
    "app.main:app",
    host=settings.api_host,
    port=settings.api_port,
    reload=settings.app_env == "development",
)

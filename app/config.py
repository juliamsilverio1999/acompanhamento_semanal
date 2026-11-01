from decimal import Decimal
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

ROOT_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_env: str = "development"

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "acompanhamento_app"
    postgres_password: str = "acompanhamento_app"
    postgres_db: str = "acompanhamento_semanal"
    database_url: Optional[str] = None
    sql_echo: bool = False

    # Superusuário: usado só pelo scripts/init_db.py para criar usuário e database
    postgres_admin_user: str = "postgres"
    postgres_admin_password: str = "postgres"

    api_host: str = "127.0.0.1"
    api_port: int = 8000

    dashboard_port: int = 8501
    api_base_url: str = "http://127.0.0.1:8000"

    dias_trabalhados_semana: int = 5
    primeiro_dia_semana: int = 0
    indice_limite_justificativa: Decimal = Decimal("0.90")

    @property
    def sqlalchemy_url(self):
        if self.database_url:
            return self.database_url
        return URL.create(
            "postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )

    @property
    def admin_url(self):
        return URL.create(
            "postgresql+psycopg",
            username=self.postgres_admin_user,
            password=self.postgres_admin_password,
            host=self.postgres_host,
            port=self.postgres_port,
            database="postgres",
        )


settings = Settings()

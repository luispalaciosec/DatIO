"""Configuración por variables de entorno (PT-01). Nunca credenciales en el código."""

from functools import lru_cache
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

MODELOS_LLM_POR_DEFECTO: dict[str, dict[str, Any]] = {
    # spec/07 §5. Se sobreescribe con LLM_MODELOS (JSON) en el ambiente.
    "clasificacion": {"proveedor": "gemini", "modelo": "gemini-3.1-flash-lite", "batch": True},
    "narrativa": {"proveedor": "gemini", "modelo": "gemini-3.7-flash"},
    "agente": {"proveedor": "deepseek", "modelo": "deepseek-v4-flash"},
    "narrativa_regulado": {"proveedor": "together_ai", "modelo": "deepseek-v4-pro"},
}


class Configuracion(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str
    ambiente: str = "desarrollo"
    zona_horaria: str = "America/Guayaquil"
    ventana_resync_dias: int = 28

    # CORS del frontend (lista JSON en el ambiente: ORIGENES_PERMITIDOS)
    origenes_permitidos: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "https://datio.vercel.app"]
    )

    # Supabase Auth (errata E-05)
    supabase_url: str = ""
    supabase_jwt_secret: str = ""

    # pgcrypto para cuentas_conectadas.credencial_cifrada
    clave_cifrado: str = ""

    # Railway Cron → POST /etl/correr
    cron_secret: str = ""

    # Service Account de Google (GA4 + Search Console). JSON completo.
    google_service_account_json: str = ""

    # Meta (PT-05 / PT-06). El token del System User se cifra en cuentas_conectadas;
    # esta variable es solo el respaldo si la cuenta no tiene credencial propia.
    meta_app_id: str = ""
    meta_app_secret: str = ""
    meta_system_user_token: str = ""
    meta_api_version: str = "v21.0"

    # Router LLM
    llm_modelos: dict[str, dict[str, Any]] = Field(
        default_factory=lambda: dict(MODELOS_LLM_POR_DEFECTO)
    )


@lru_cache
def obtener_config() -> Configuracion:
    return Configuracion()  # type: ignore[call-arg]

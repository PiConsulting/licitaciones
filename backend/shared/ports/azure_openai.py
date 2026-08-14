from __future__ import annotations

from typing import Any

from langchain_openai import AzureChatOpenAI

from shared.config import get_settings


def get_azure_openai_client() -> Any:
    """Retorna cliente LLM de Azure OpenAI para extracción."""
    settings = get_settings()

    missing: list[str] = []
    if not settings.azure_openai_endpoint.strip():
        missing.append("AZURE_OPENAI_ENDPOINT")
    if not settings.azure_openai_api_key.strip():
        missing.append("AZURE_OPENAI_API_KEY")
    if not settings.azure_openai_api_version.strip():
        missing.append("AZURE_OPENAI_API_VERSION")
    if not settings.azure_openai_chat_deployment.strip():
        missing.append("AZURE_OPENAI_DEPLOYMENT")
    if missing:
        raise RuntimeError("Configuración de chat cloud incompleta: " + ", ".join(missing))

    return AzureChatOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
        deployment_name=settings.azure_openai_chat_deployment,
        temperature=0.0,
        # FIX (2026-08-14): 4000 tokens alcanzan para ~25 items de extracción
        # (cada uno lleva el UUID del documento, su metadata y su cita). La
        # categoría `requisitos_admisibilidad` pide explícitamente "un item por
        # requisito, y si vienen en incisos, uno por inciso": en un pliego real
        # son 30-40. Pasado el tope, el JSON llega truncado, `_parse_json_response`
        # lanza, y `run_extractor` marca la categoría ENTERA como `failed` con
        # lista vacía -- que es exactamente lo que se vio en el análisis del
        # 2026-08-14. Con temperatura 0 los 3 reintentos son deterministas, así
        # que reintentar no ayuda: o entra, o se pierde la categoría.
        max_tokens=12000,
        # El timeout acompaña: la respuesta más larga es también la que más
        # tarda, y 60s era el otro techo contra el que pegaba la misma
        # categoría.
        timeout=180,
    )

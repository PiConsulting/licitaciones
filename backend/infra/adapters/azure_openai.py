from __future__ import annotations

from typing import Any

from langchain_openai import AzureChatOpenAI

from infra.config import get_settings


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
        # temperature=0.0 sola no garantiza determinismo; el seed es lo que ayuda (EXT-01), el valor es arbitrario pero debe mantenerse constante.
        seed=42,
        # 4000 tokens truncaba el JSON en categorías con muchos ítems (ej. requisitos_admisibilidad), lo que hacía fallar run_extractor (visto 2026-08-14).
        max_tokens=12000,
        # Subido junto con max_tokens: las respuestas más largas también tardan más y 60s era el otro techo que se golpeaba.
        timeout=180,
    )

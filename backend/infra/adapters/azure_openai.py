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
        # temperature=0.0 alone doesn't guarantee determinism; seed is what actually helps (EXT-01). Value is arbitrary, just needs to stay constant across calls.
        seed=42,
        # 4000 tokens truncated JSON for categories with many items (e.g. requisitos_admisibilidad, 30-40 items), which made run_extractor mark the category as failed (seen 2026-08-14).
        max_tokens=12000,
        # Raised alongside max_tokens: the longest responses also take the longest, and 60s was the other ceiling being hit.
        timeout=180,
    )

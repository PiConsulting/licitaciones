from __future__ import annotations

from typing import Any

from langchain_openai import AzureChatOpenAI

from shared.config import get_settings


def get_azure_openai_client() -> Any:
    """Retorna cliente LLM de extracción según perfil (development|production)."""
    settings = get_settings()
    if settings.is_development:
        from langchain_cohere import ChatCohere

        return ChatCohere(
            model=settings.cohere_model,
            cohere_api_key=settings.cohere_api_key,
            temperature=0.0,
            max_tokens=4000,
        )

    return AzureChatOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
        deployment_name=settings.azure_openai_chat_deployment,
        temperature=0.0,
        max_tokens=4000,
        timeout=60,
    )

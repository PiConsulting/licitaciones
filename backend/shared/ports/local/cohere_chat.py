from __future__ import annotations

from typing import Any

from shared.config import get_settings


def get_cohere_chat_client() -> Any:
    """Cliente de chat vía Cohere, usado solo cuando no hay credenciales de Azure OpenAI."""
    from langchain_cohere import ChatCohere

    settings = get_settings()
    return ChatCohere(
        model=settings.cohere_model,
        cohere_api_key=settings.cohere_api_key,
        temperature=0.0,
        max_tokens=4000,
    )

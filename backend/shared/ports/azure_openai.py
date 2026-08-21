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
        # FIX (auditoría EXT-01, 2026-08-20): el comentario de más abajo decía
        # "con temperatura 0 los 3 reintentos son deterministas" -- es falso.
        # `temperature=0.0` reduce la aleatoriedad del muestreo pero no la
        # elimina (backends con batching/paralelismo introducen variación de
        # todos modos); el parámetro que de verdad apunta a reproducibilidad
        # es `seed`, documentado por OpenAI/Azure OpenAI como "mejora
        # sustancialmente" el determinismo (no lo garantiza al 100%, pero es
        # lo que hay). Medido sin `seed`: 5 corridas del mismo análisis, con
        # retrieval idéntico verificado chunk por chunk, dieron piso de ruido
        # 1/8 categorías estables (ver EXT-01,
        # docs/docu/PENDIENTE-auditoria-rag.md punto 3.1). El valor es
        # arbitrario y fijo a propósito: lo único que importa es que sea
        # constante entre llamadas, no cuál sea.
        seed=42,
        # FIX (2026-08-14): 4000 tokens alcanzan para ~25 items de extracción
        # (cada uno lleva el UUID del documento, su metadata y su cita). La
        # categoría `requisitos_admisibilidad` pide explícitamente "un item por
        # requisito, y si vienen en incisos, uno por inciso": en un pliego real
        # son 30-40. Pasado el tope, el JSON llega truncado, `_parse_json_response`
        # lanza, y `run_extractor` marca la categoría ENTERA como `failed` con
        # lista vacía -- que es exactamente lo que se vio en el análisis del
        # 2026-08-14. (Corrección 2026-08-20: la razón original decía "con
        # temperatura 0 los 3 reintentos son deterministas, así que reintentar
        # no ayuda" -- ver el comentario de `seed` arriba, esa premisa era
        # falsa. Reintentar sí puede ayudar a que una categoría trunca entre
        # por pura variación de muestreo; el límite de tokens sigue siendo
        # necesario igual, por las mismas ~25 items de margen.)
        max_tokens=12000,
        # El timeout acompaña: la respuesta más larga es también la que más
        # tarda, y 60s era el otro techo contra el que pegaba la misma
        # categoría.
        timeout=180,
    )

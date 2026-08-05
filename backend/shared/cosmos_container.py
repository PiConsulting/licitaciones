from __future__ import annotations

from functools import lru_cache

from shared.config import get_settings


@lru_cache
def _build_container():
    from azure.cosmos import CosmosClient

    settings = get_settings()
    client = CosmosClient(url=settings.cosmos_endpoint, credential=settings.cosmos_key)
    database = client.get_database_client(settings.cosmos_database)
    return database.get_container_client(settings.cosmos_container)


def get_cosmos_container():
    return _build_container()

"""Agrega al índice de Azure AI Search los campos que el chunker ya produce
pero que el índice nunca tuvo: section_path, section_level, block_type,
table_ref.

Azure AI Search permite agregar campos nuevos a un índice existente sin
reindexar: los documentos ya cargados quedan con esos campos en null, y las
subidas nuevas los completan. No hay downtime ni pérdida de datos.

Uso:
    cd backend
    ../.venv/Scripts/python.exe scripts/migrate_search_index_add_chunk_fields.py [--dry-run]

Idempotente: si los campos ya existen, no hace ningún cambio.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.config import get_settings  # noqa: E402

NEW_FIELDS = ("section_path", "section_level", "block_type", "table_ref")


def main() -> int:
    dry_run = "--dry-run" in sys.argv

    settings = get_settings()
    if settings.is_development:
        print("APP_ENV=development / USE_LOCAL_ADAPTERS=true: no hay índice de Azure Search que migrar.")
        return 0

    from azure.core.credentials import AzureKeyCredential
    from azure.search.documents.indexes import SearchIndexClient
    from azure.search.documents.indexes.models import SearchFieldDataType, SimpleField

    client = SearchIndexClient(
        endpoint=settings.azure_search_endpoint,
        credential=AzureKeyCredential(settings.azure_search_key),
    )
    index = client.get_index(settings.azure_search_index_name)
    existing_names = {field.name for field in index.fields}

    missing = [name for name in NEW_FIELDS if name not in existing_names]
    if not missing:
        print(f"'{index.name}' ya tiene los {len(NEW_FIELDS)} campos. Nada que migrar.")
        return 0

    print(f"Índice '{index.name}': faltan {missing}")

    field_specs = {
        "section_path": SimpleField(name="section_path", type=SearchFieldDataType.String, filterable=False),
        "section_level": SimpleField(name="section_level", type=SearchFieldDataType.Int32, filterable=True),
        "block_type": SimpleField(name="block_type", type=SearchFieldDataType.String, filterable=True),
        # JSON serializado (ver extraction/ai_search.py::upload_chunks). Azure Search
        # no tiene un tipo "dict" suelto para un campo simple; guardamos texto y lo
        # deserializamos del lado del cliente, igual que ya hace el adaptador local.
        "table_ref": SimpleField(name="table_ref", type=SearchFieldDataType.String, filterable=False),
    }

    if dry_run:
        print(f"[--dry-run] Se agregarían: {missing}. No se aplicó ningún cambio.")
        return 0

    index.fields.extend(field_specs[name] for name in missing)
    client.create_or_update_index(index)

    updated = client.get_index(settings.azure_search_index_name)
    updated_names = {field.name for field in updated.fields}
    still_missing = [name for name in NEW_FIELDS if name not in updated_names]
    if still_missing:
        print(f"ERROR: tras la migración siguen faltando: {still_missing}")
        return 1

    print(f"OK. Campos de '{updated.name}' ahora: {sorted(updated_names)}")
    print(
        "Nota: los documentos ya indexados quedan con estos campos en null hasta "
        "que se vuelva a analizar el pliego correspondiente (reindexado natural, "
        "no hace falta un backfill manual)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

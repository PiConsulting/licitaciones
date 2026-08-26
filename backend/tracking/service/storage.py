"""Lectura/escritura del tracking y del analisis en Cosmos DB, con control de concurrencia optimista via ETag."""
from __future__ import annotations

from azure.core import MatchConditions
from azure.cosmos.exceptions import CosmosResourceNotFoundError

from analysis import cosmos_runtime


def _load_analysis_or_raise(analysis_id: str, user_id: str) -> dict:
    container = cosmos_runtime.get_cosmos_container()
    item_id = f"analysis::{analysis_id}"
    analysis = None
    for pk in [analysis_id, item_id]:
        try:
            analysis = container.read_item(item=item_id, partition_key=pk)
            break
        except Exception:  # noqa: BLE001
            continue
    if analysis is None or analysis.get("deleted"):
        rows = list(
            container.query_items(
                query="SELECT TOP 1 * FROM c WHERE c.type = 'analysis' AND c.analysis_id = @analysis_id",
                parameters=[{"name": "@analysis_id", "value": analysis_id}],
                enable_cross_partition_query=True,
            )
        )
        if rows:
            analysis = rows[0]
    if analysis is None or analysis.get("deleted"):
        raise ValueError("ANALYSIS_NOT_FOUND")
    if analysis.get("created_by") != user_id:
        raise PermissionError("FORBIDDEN")
    return analysis


def _load_latest_version(analysis_id: str) -> dict:
    container = cosmos_runtime.get_cosmos_container()
    rows = list(
        container.query_items(
            query=(
                "SELECT TOP 1 * FROM c WHERE c.type = 'analysis_version' "
                "AND c.analysis_id = @analysis_id ORDER BY c.version_number DESC"
            ),
            parameters=[{"name": "@analysis_id", "value": analysis_id}],
            partition_key=analysis_id,
        )
    )
    if not rows:
        raise ValueError("NO_VERSION_YET")
    return rows[0]


def _read_tracking_or_none(analysis_id: str, version_id: str) -> dict | None:
    container = cosmos_runtime.get_cosmos_container()
    item_id = _tracking_id(analysis_id, version_id)
    try:
        return container.read_item(item=item_id, partition_key=analysis_id)
    except CosmosResourceNotFoundError:
        return None
    except Exception:
        return None


def _save_tracking_with_etag(tracking: dict) -> None:
    container = cosmos_runtime.get_cosmos_container()
    etag = tracking.get("_etag")
    if etag:
        result = container.replace_item(
            item=tracking["id"],
            body=tracking,
            etag=etag,
            match_condition=MatchConditions.IfNotModified,
        )
    else:
        result = container.upsert_item(tracking)
    if isinstance(result, dict) and result.get("_etag"):
        tracking["_etag"] = result["_etag"]


def _tracking_id(analysis_id: str, version_id: str) -> str:
    return f"tracking::{analysis_id}::{version_id}"

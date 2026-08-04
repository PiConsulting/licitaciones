import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from analysis.routes import analysis_router
from shared.config import get_settings
from shared.database import engine
from shared.logging import configure_logging
from users.routes import auth_router, protected_router

logger = logging.getLogger(__name__)


def _database_health() -> tuple[str, str]:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return "ok", "Conectividad de base de datos operativa"
    except SQLAlchemyError as exc:
        logger.warning("Healthcheck: database unavailable", exc_info=exc)
        return "error", "No se pudo conectar a la base de datos"
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.warning("Healthcheck: unexpected database failure", exc_info=exc)
        return "error", "Error inesperado verificando base de datos"


def _local_storage_health(local_path: str) -> tuple[str, str]:
    try:
        target = Path(local_path)
        target.mkdir(parents=True, exist_ok=True)
        return "ok", "Storage local disponible"
    except OSError as exc:
        logger.warning("Healthcheck: local storage unavailable", exc_info=exc)
        return "error", "Storage local no disponible"


def _azure_config_health() -> tuple[str, str, list[str]]:
    settings = get_settings()
    required = {
        "AZURE_BLOB_CONNECTION_STRING": settings.azure_blob_connection_string,
        "AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT": settings.azure_document_intelligence_endpoint,
        "AZURE_DOCUMENT_INTELLIGENCE_KEY": settings.azure_document_intelligence_key,
        "AZURE_SEARCH_ENDPOINT": settings.azure_search_endpoint,
        "AZURE_SEARCH_KEY": settings.azure_search_key,
        "AZURE_SEARCH_INDEX_NAME": settings.azure_search_index_name,
        "AZURE_OPENAI_ENDPOINT": settings.azure_openai_endpoint,
        "AZURE_OPENAI_API_KEY": settings.azure_openai_api_key,
        "AZURE_OPENAI_EMBEDDING_DEPLOYMENT": settings.azure_openai_embedding_deployment,
    }
    missing = [name for name, value in required.items() if not str(value).strip()]
    if missing:
        return "error", "Falta configuración para Azure", missing
    return "ok", "Configuración de Azure presente", []


def _run_health_checks() -> tuple[int, dict[str, Any]]:
    settings = get_settings()
    timestamp = datetime.now(UTC).isoformat()

    db_status, db_message = _database_health()
    checks: dict[str, dict[str, Any]] = {
        "database": {
            "status": db_status,
            "message": db_message,
        },
    }

    if settings.use_local_adapters:
        storage_status, storage_message = _local_storage_health(settings.local_blob_storage_path)
        checks["adapters"] = {
            "status": storage_status,
            "mode": "local",
            "message": storage_message,
        }
    else:
        azure_status, azure_message, missing = _azure_config_health()
        checks["adapters"] = {
            "status": azure_status,
            "mode": "azure",
            "message": azure_message,
            "missing": missing,
        }

    has_errors = any(item["status"] != "ok" for item in checks.values())
    status_code = 503 if has_errors else 200
    payload = {
        "status": "degraded" if has_errors else "ok",
        "timestamp": timestamp,
        "checks": checks,
    }
    return status_code, payload


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title="licitaciones-pi API", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_, exc: HTTPException) -> JSONResponse:
        if isinstance(exc.detail, dict) and "error" in exc.detail:
            return JSONResponse(status_code=exc.status_code, content=exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": "HTTP_ERROR", "message": str(exc.detail)}},
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_exception_handler(_, exc: Exception) -> JSONResponse:
        logger.exception("Database connectivity error", exc_info=exc)
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "DATABASE_UNAVAILABLE",
                    "message": "No se pudo conectar a la base de datos",
                }
            },
        )

    @app.exception_handler(UnicodeDecodeError)
    async def unicode_decode_exception_handler(_, exc: UnicodeDecodeError) -> JSONResponse:
        logger.exception("Unicode decoding error", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "UNICODE_DECODE_ERROR",
                    "message": "Error de codificacion de caracteres",
                }
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled server error", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "Ocurrió un error interno",
                }
            },
        )

    @app.get("/health")
    def healthcheck() -> JSONResponse:
        status_code, payload = _run_health_checks()
        return JSONResponse(status_code=status_code, content=payload)

    @app.get("/health/liveness")
    def liveness() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(protected_router, prefix="/api/v1")
    app.include_router(analysis_router, prefix="/api/v1")
    return app


app = create_app()
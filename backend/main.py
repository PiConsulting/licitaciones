import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from analysis.routes import analysis_router
from users.routes import auth_router, protected_router

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
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
    def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(protected_router, prefix="/api/v1")
    app.include_router(analysis_router, prefix="/api/v1")
    return app


app = create_app()